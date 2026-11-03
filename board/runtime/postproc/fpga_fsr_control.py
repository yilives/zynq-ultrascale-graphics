#!/usr/bin/env python3
"""Isolated, journaled whole-PL RAM loading; importing never touches hardware.

Real execution is deliberately explicit: --manifest /tmp/rix-fpga-fsr/manifest.json
--execute. All images and recovery state remain in RAM; BOOT.BIN is never changed.
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import time
from pathlib import Path

BASE = Path('/tmp/rix-fpga-fsr')
MANIFEST = BASE / 'manifest.json'
REPORT = Path('/tmp/postproc-tests/cc_fsr_fpga_load.json')
FW_PATH = Path('/sys/module/firmware_class/parameters/path')
MANAGER = Path('/sys/class/fpga_manager/fpga0')
POST = '/opt/rasterix/postproc-touch/bin/rix-superres'
MODULES = {
    'i2c_gpio': '/opt/rasterix/postproc-touch/modules/i2c-gpio.ko',
    'rix_dma_proxy': '/opt/rasterix/modules/rix_dma_proxy.ko',
    'plgpu_display': '/opt/rasterix/modules/plgpu_display.ko',
}
REMOVE = ('i2c_gpio', 'rix_dma_proxy', 'plgpu_display')
ADD = ('rix_dma_proxy', 'plgpu_display', 'i2c_gpio')
BINDINGS = {
    'dma': ('xilinx-vdma', 'a0000000.dma'),
    'gpio': ('xilinx-gpio', 'a0020000.touch-gpio'),
}
CLIENTS = ('ClassiCube', 'rix-neural-style', 'rix-superres', 'rix-fsr-pl', 'tuxracer',
           'neverball', 'neverputt', 'quakespasm', 'quake3e', 'rix-glx-probe',
           'rix-smoke', 'rix-danmaku', 'th06-rix')
IDS = ('frame_id', 'swap', 'copy', 'presented', 'last_presented')
ERRORS = ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')
LOCKS = ('rasterix-game-launch.lock', 'rix-superres.lock', 'rix-mc-style-extract.lock')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def validate_manifest(document):
    require(isinstance(document, dict) and set(document) == {'format', 'images', 'source_sha256'}, 'Unexpected manifest fields')
    require(document['format'] == 'rix-fpga-ram-fsr1', 'Wrong manifest format')
    require(isinstance(document['images'], dict) and set(document['images']) == {'new', 'old'}, 'Both new and old images required')
    require(isinstance(document['source_sha256'], str) and re.fullmatch('[0-9a-f]{64}', document['source_sha256']), 'Invalid source manifest SHA256')
    for role in ('new', 'old'):
        item = document['images'][role]
        require(isinstance(item, dict) and set(item) == {'filename', 'bytes', 'sha256'}, 'Unexpected image fields')
        require(item['filename'] == role + '.bin', 'Only fixed RAM image filenames allowed')
        require(type(item['bytes']) is int and 0 < item['bytes'] <= 64 * 1024 * 1024, 'Invalid image byte count')
        require(isinstance(item['sha256'], str) and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'Invalid lowercase SHA256')
    require(document['images']['new']['sha256'] != document['images']['old']['sha256'], 'New and rollback images must differ')


def check_gpu(gpu):
    require(gpu['abi'] == 0x52495801 and gpu['config'] == 0x9adb505e, 'GPU ABI/config mismatch')
    require(gpu['status'] == 3 and gpu['enabled'] in (0, 1), 'GPU/MIG not ready')
    require(all(type(gpu[k]) is int and gpu[k] == 0 for k in ERRORS), 'GPU fault counters must be zero')
    require(len({gpu[k] for k in IDS}) == 1, 'GPU queues are not drained')


def check_idle(snapshot):
    require(not snapshot['clients'], 'Active GPU client prevents PL loading')
    check_gpu(snapshot['gpu'])
    post = snapshot['post']
    require(post['requested'] == post['active'] == 1, 'Expected idle post mode1/style0')
    require(post['snapshot_status'] == post['snapshot_expirations'] == 0, 'Snapshot lease/expiration must be clear')


class Controller:
    """All machine effects are injected through the adapter, allowing host mocks."""
    def __init__(self, adapter):
        self.a = adapter
        self.record = {'format': 'rix-fpga-ram-load-fsr1', 'passed': False,
                       'outcome': 'starting', 'events': [], 'journal_errors': [],
                       'device_mutation_started': False, 'new_load_attempted': False,
                       'rollback': {'attempted': False, 'passed': False}, 'error': None,
                       'controller_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.recovering = False
        self.before = None

    def save(self):
        try:
            self.a.journal(self.record)
        except Exception as error:
            self.record['journal_errors'].append(repr(error))
            if not self.recovering:
                raise

    def effect(self, label, operation):
        event = {'action': label, 'status': 'pending'}
        self.record['events'].append(event)
        self.save()  # The pending operation must be durable BEFORE it starts.
        self.record['device_mutation_started'] = True
        try:
            result = operation()
        except BaseException as error:
            event.update(status='failed', error=repr(error))
            self.save()
            raise
        event['status'] = 'complete'
        self.save()
        return result

    def verify_images(self, manifest):
        found = {}
        for role in ('new', 'old'):
            item = manifest['images'][role]
            info = self.a.image_info(item['filename'])
            require(info['bytes'] == item['bytes'] and info['sha256'] == item['sha256'], role + ' image does not match manifest')
            found[role] = info
        return found

    def preflight(self, manifest):
        validate_manifest(manifest)
        self.a.preflight_paths()
        images = self.verify_images(manifest)
        before = self.a.snapshot()
        check_idle(before)
        require(before['manager_name'] == 'Xilinx ZynqMP FPGA Manager', 'Wrong FPGA manager')
        require(before['manager_state'] == 'operating', 'FPGA manager is not operating before transaction')
        require(re.fullmatch('[0-9a-fA-F]+', before['flags']) is not None, 'Invalid FPGA flags representation')
        require('\n' not in before['firmware_path'] and '\x00' not in before['firmware_path'], 'Unsupported preexisting firmware path')
        require(before['cnn']['magic'] == 0x4e4e5332 and before['cnn']['shape'] == (96 << 16) | 160, 'Unexpected original CNN')
        require(before['cnn']['capabilities'] == 7 and before['cnn']['adapter_abi'] == 0x00020001, 'Known atomic v4 rollback hardware required')
        for role in BINDINGS:
            require(before['bindings'][role] == self.a.expected_binding(role), 'Original exact binding absent: ' + role)
        for name in MODULES:
            module = before['modules'][name]
            require(module['file']['path'] == MODULES[name] and module['file']['bytes'] > 0, 'Required fixed module file absent')
            require(not module['loaded'] or module['refcount'] == 0, 'Module still referenced: ' + name)
        require(all(before['modules'][n]['loaded'] for n in ('rix_dma_proxy', 'plgpu_display')), 'Required original modules not loaded')
        self.a.rollback_proof(before['boot_id'], manifest['images']['old']['sha256'])
        self.before = before
        self.record.update(manifest=manifest, images=images, before=before, outcome='preflight-complete')
        self.record['manifest_file'] = getattr(self.a, 'manifest_info', None)
        self.save()
        # A second status observation must agree while all three locks are held.
        again = self.a.runtime_state()
        check_idle(again)
        require(again['boot_id'] == before['boot_id'] and all(again['gpu'][k] == before['gpu'][k] for k in IDS), 'GPU or boot changed during preflight')

    def quiesce(self):
        for name in REMOVE:
            if self.a.module_loaded(name):
                self.effect('remove:' + name, lambda n=name: self.a.remove_module(n))
                require(not self.a.module_loaded(name), 'Module did not unload: ' + name)
        for role in ('dma', 'gpio'):
            binding = self.a.binding(role)
            require(binding in (None, self.before['bindings'][role]), 'Foreign driver binding; refuse unbind: ' + role)
            if binding is not None:
                self.effect('unbind:' + role, lambda r=role: self.a.unbind(r))
                require(self.a.binding(role) is None, 'Device remained bound: ' + role)
        require(not any(self.a.module_loaded(n) for n in MODULES), 'Module remained active while quiescing')
        require(all(self.a.binding(r) is None for r in BINDINGS), 'PL bindings remained active')

    def load(self, role):
        # New loading requires both validated images. Recovery must not depend on
        # an already-failed candidate still being present; only old bytes matter.
        if role == 'new':
            self.verify_images(self.record['manifest'])
        else:
            item = self.record['manifest']['images']['old']
            info = self.a.image_info(item['filename'])
            require(info['bytes'] == item['bytes'] and info['sha256'] == item['sha256'], 'Rollback image changed before recovery')
        self.effect('firmware-path:ram', lambda: self.a.set_firmware_path(str(BASE)))
        require(self.a.firmware_path() == str(BASE), 'RAM firmware path readback failed')
        self.effect('flags:whole-PL', lambda: self.a.set_flags('0'))
        require(int(self.a.flags(), 16) == 0, 'Whole-PL flags readback failed')
        if role == 'new':
            self.record['new_load_attempted'] = True
        self.effect('load:' + role, lambda: self.a.load_firmware(role + '.bin'))
        self.a.wait_operating()

    def restore_devices(self):
        # Control CSR stays on the PS reset domain, while DMA AXI reset is
        # gated by MIG readiness. Never probe/bind DMA into an unready slave.
        self.a.wait_control_ready()
        for role in ('gpio', 'dma'):
            binding = self.a.binding(role)
            require(binding in (None, self.before['bindings'][role]), 'Foreign driver binding during recovery')
            if binding is None:
                self.effect('bind:' + role, lambda r=role: self.a.bind(r))
            require(self.a.binding(role) == self.before['bindings'][role], 'Exact binding restoration failed: ' + role)
        for name in ADD:
            originally = self.before['modules'][name]['loaded']
            require(originally or not self.a.module_loaded(name), 'Unexpected module appeared: ' + name)
            if originally and not self.a.module_loaded(name):
                require(self.a.module_file(name) == self.before['modules'][name]['file'], 'Module file changed before execution: ' + name)
                self.effect('insert:' + name, lambda n=name: self.a.insert_module(n))
            require(self.a.module_loaded(name) == originally, 'Original module presence not restored: ' + name)
        self.a.wait_gpu_ready()
        enabled = self.before['gpu']['enabled']
        self.effect('restore:gpu-enabled', lambda: self.a.set_enabled(enabled))
        self.effect('restore:post-mode1', self.a.set_post_mode1)
        self.a.wait_post_mode1()

    def verify_restored(self, new):
        final = self.a.snapshot()
        check_idle(final)
        require(final['boot_id'] == self.before['boot_id'], 'Boot changed during transaction')
        require(final['gpu']['enabled'] == self.before['gpu']['enabled'], 'GPU enable state not restored')
        require(final['bindings'] == self.before['bindings'], 'Original driver bindings changed')
        require(final['module_inventory'] == self.before['module_inventory'], 'Unexpected module presence change; refuse to remove unrelated modules')
        for name in MODULES:
            require(final['modules'][name]['loaded'] == self.before['modules'][name]['loaded'], 'Module state mismatch')
            require(final['modules'][name]['file'] == self.before['modules'][name]['file'], 'Original module file changed')
        if new:
            require(final['cnn'] == {'magic': 0x4e4e5332, 'shape': (96 << 16) | 160, 'capabilities': 7, 'adapter_abi': 0x00020001}, 'New atomic CNN identity not verified')
        else:
            require(final['cnn'] == self.before['cnn'], 'Rollback CNN does not match original')
        if new:
            final['fsr'] = self.a.verify_fsr_protocol()
        return final

    def restore_parameters(self):
        self.effect('restore:firmware-path', lambda: self.a.set_firmware_path(self.before['firmware_path']))
        require(self.a.firmware_path() == self.before['firmware_path'], 'Firmware path restoration readback failed')
        self.effect('restore:fpga-flags', lambda: self.a.set_flags(self.before['flags']))
        require(self.a.flags() == self.before['flags'], 'FPGA flags restoration readback failed')

    def recover(self):
        self.recovering = True
        recovery = self.record['rollback']
        recovery['attempted'] = True
        try:
            self.effect('deactivate:fsr-receipt', self.a.deactivate_receipt)
            # A failed rebind/module insertion may have partially restored new PL.
            # Requiesce every targeted device BEFORE loading the rollback image.
            self.quiesce()
            if self.record['new_load_attempted']:
                self.load('old')
                recovery['old_loaded'] = True
            else:
                recovery['old_loaded'] = False
            self.restore_devices()
            recovery['final'] = self.verify_restored(new=False)
            recovery['fabric_and_devices_restored'] = True
        except BaseException as error:
            recovery['error'] = repr(error)
            recovery['fabric_and_devices_restored'] = False
        # Global firmware search path/flags must be restored even if old loading fails.
        parameter_errors = []
        for label, action, getter, expected in (
                ('firmware-path', lambda: self.a.set_firmware_path(self.before['firmware_path']), self.a.firmware_path, self.before['firmware_path']),
                ('fpga-flags', lambda: self.a.set_flags(self.before['flags']), self.a.flags, self.before['flags'])):
            try:
                self.effect('recovery-restore:' + label, action)
                require(getter() == expected, label + ' restoration readback failed')
            except BaseException as error:
                parameter_errors.append({'parameter': label, 'error': repr(error)})
        recovery['parameter_errors'] = parameter_errors
        recovery['passed'] = recovery.get('fabric_and_devices_restored', False) and not parameter_errors
        self.record['outcome'] = 'rolled-back' if recovery['passed'] else 'recovery-failed'
        if not recovery['passed']:
            self.record['recovery_required'] = 'Do not start GPU clients; inspect this journal and restore the known SD boot with a full board power cycle.'
        self.save()

    def run(self, manifest):
        try:
            with self.a.locks():
                try:
                    self.preflight(manifest() if callable(manifest) else manifest)
                    self.quiesce()
                    self.load('new')
                    self.restore_devices()
                    self.record['after'] = self.verify_restored(new=True)
                    self.restore_parameters()
                    self.effect('activate:fsr-receipt', lambda: self.a.activate_receipt(self.before['boot_id'], self.record['manifest']['images']['new']['sha256'], self.record['manifest']['source_sha256']))
                    self.record.update(passed=True, outcome='new-loaded-and-verified')
                    self.save()
                except BaseException as error:
                    self.record.update(passed=False, error=repr(error))
                    if self.before is not None and self.record['device_mutation_started']:
                        self.recover()
                    else:
                        self.record['outcome'] = 'preflight-failed-no-device-change'
                        self.recovering = True
                        self.save()
        except BaseException as error:
            self.record.update(passed=False, outcome='lock-or-journal-failed', error=repr(error))
            self.recovering = True
            self.save()
        return self.record


class LinuxAdapter:
    """Exact board paths only. No shell commands, PS-driver operations or flash writes."""
    def __init__(self):
        self.env = dict(os.environ, PATH='/sbin:/usr/sbin:/bin:/usr/bin', LC_ALL='C')
        self.report_owned = False

    def command(self, args):
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, env=self.env, timeout=25)
        require(result.returncode == 0, 'Command failed: ' + repr(args) + ': ' + result.stdout[-2000:])
        return result.stdout

    def rollback_proof(self, boot, sha256):
        proof_path = Path('/tmp/postproc-tests/cc_v4_fpga_load.json')
        self.regular_info(proof_path)
        proof = json.loads(proof_path.read_text(), object_pairs_hook=unique_object)
        require(proof.get('passed') is True and proof.get('outcome') == 'new-loaded-and-verified', 'Original atomic-v4 load was not verified')
        require(proof['after']['boot_id'] == boot and proof['manifest']['images']['new']['sha256'] == sha256,
                'Rollback image is not the verified atomic-v4 image on this boot')

    def verify_fsr_protocol(self):
        # This method is called only after loading the manifest-verified NEW
        # image. Before loading, A0040000 is unmapped and must not be probed.
        rows = []
        with self.mmio(0xa0040000) as mm:
            for mode, expected in ((2, 0), (99, 2), (1, 1)):
                ctrl = self.read32(mm, 0)
                require(ctrl & 4 and not ctrl & 0x81, 'New FSR core is not idle')
                self.read32(mm, 0x3c)
                for offset, value in ((0x18, mode), (0x20, 0), (0x28, 0), (0x30, 0), (0, 1)):
                    self.write32(mm, offset, value)
                until = time.monotonic()+2
                while not self.read32(mm, 0) & 2:
                    require(time.monotonic() < until, 'FSR no-DDR protocol command timeout')
                    time.sleep(.001)
                returned = self.read32(mm, 0x10)
                require(returned == expected and self.read32(mm, 0x3c) & 1 and self.read32(mm, 0x38) == 0,
                        'FSR no-DDR protocol response mismatch')
                rows.append({'mode': mode, 'return': returned})
        return {'passed': True, 'commands': rows, 'pixel_computation_tested': False}

    def activate_receipt(self, boot, bit, source):
        path = BASE/'active-receipt.txt'
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('RIX_FSR_PL_ACTIVE_V1\n'+boot+'\n'+bit+'\n'+source+'\n')
            stream.flush()
            os.fsync(stream.fileno())

    def deactivate_receipt(self):
        path = BASE/'active-receipt.txt'
        if path.exists() or path.is_symlink():
            require(not path.is_symlink(), 'Refuse unexpected receipt symlink')
            path.unlink()

    @contextlib.contextmanager
    def locks(self):
        import fcntl
        with contextlib.ExitStack() as stack:
            for name in LOCKS:
                path = Path('/tmp') / name
                require(not path.is_symlink(), 'Refuse symlink lock')
                fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                stream = stack.enter_context(os.fdopen(fd, 'a+'))
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def ram_directory(self, path):
        require(path.is_dir() and not path.is_symlink(), 'RAM directory absent or symlink: ' + str(path))
        require(path.resolve() == Path('/tmp').resolve() / path.name, 'Directory escaped fixed RAM parent')
        st = path.stat()
        require(st.st_uid == 0 and not st.st_mode & 0o022, 'RAM directory must be root-owned and not group/world writable')
        best = ('', '')
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            fields, tail = line.split(' - ', 1)
            mount = fields.split()[4].replace('\\040', ' ')
            resolved = str(path.resolve())
            if (resolved == mount or resolved.startswith(mount.rstrip('/') + '/')) and len(mount) > len(best[0]):
                best = (mount, tail.split()[0])
        require(best[1] in ('tmpfs', 'ramfs'), 'Files must stay on tmpfs/ramfs: ' + str(path))

    def regular_info(self, path):
        path = Path(path)
        require(not path.is_symlink(), 'Refuse symlink file: ' + str(path))
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and not before.st_mode & 0o022, 'Unsafe non-regular/untrusted file: ' + str(path))
            digest = hashlib.sha256()
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after = os.fstat(fd)
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'File changed while hashing')
            return {'path': str(path), 'bytes': before.st_size, 'sha256': digest.hexdigest()}
        finally:
            os.close(fd)

    def image_info(self, filename):
        require(filename in ('new.bin', 'old.bin'), 'Invalid fixed image filename')
        return self.regular_info(BASE / filename)

    def module_file(self, name):
        path = Path(MODULES[name])
        require(all(not p.is_symlink() for p in (path,) + tuple(path.parents)), 'Module path must not redirect')
        return self.regular_info(path)

    def preflight_paths(self):
        require(os.name == 'posix' and os.geteuid() == 0, 'Root Linux required')
        self.ram_directory(BASE)
        self.ram_directory(REPORT.parent)
        require(not (BASE/'active-receipt.txt').exists() and not (BASE/'active-receipt.txt').is_symlink(), 'An active FSR receipt already exists')
        require(not REPORT.exists() and not REPORT.is_symlink(), 'Preserve existing load report before a new transaction')
        for path in (FW_PATH, MANAGER / 'flags', MANAGER / 'firmware', MANAGER / 'state', MANAGER / 'name'):
            require(path.exists(), 'Required sysfs attribute absent: ' + str(path))
        for path in (FW_PATH, MANAGER / 'flags', MANAGER / 'firmware'):
            require(os.access(str(path), os.W_OK), 'Required sysfs attribute is not writable: ' + str(path))
        for role, (driver, device) in BINDINGS.items():
            root = Path('/sys/bus/platform/drivers') / driver
            require((root / 'bind').exists() and (root / 'unbind').exists(), 'Missing driver bind interface')
            require((Path('/sys/bus/platform/devices') / device).exists(), 'Missing exact PL platform device')
        for name in MODULES:
            self.module_file(name)

    def read_manifest(self):
        self.ram_directory(BASE)
        self.manifest_info = self.regular_info(MANIFEST)
        require(0 < self.manifest_info['bytes'] <= 65536, 'Manifest must be bounded JSON')
        return json.loads(MANIFEST.read_text(), object_pairs_hook=unique_object)

    def expected_binding(self, role):
        driver, device = BINDINGS[role]
        return {'device': device, 'driver': driver,
                'driver_target': str((Path('/sys/bus/platform/drivers') / driver).resolve()),
                'device_target': str((Path('/sys/bus/platform/devices') / device).resolve())}

    def binding(self, role):
        driver, device = BINDINGS[role]
        dev = Path('/sys/bus/platform/devices') / device
        link = dev / 'driver'
        if not link.exists() and not link.is_symlink():
            return None
        expected = self.expected_binding(role)
        entry = Path('/sys/bus/platform/drivers') / driver / device
        require(link.is_symlink() and str(link.resolve()) == expected['driver_target'], 'Foreign exact-device driver: ' + role)
        require(entry.is_symlink() and str(entry.resolve()) == expected['device_target'], 'Driver entry does not point to exact PL device')
        return expected

    def loaded_modules(self):
        rows = {}
        for line in Path('/proc/modules').read_text().splitlines():
            item = line.split()
            rows[item[0]] = {'refcount': int(item[2]), 'line': line}
        return rows

    def module_loaded(self, name):
        return name in self.loaded_modules()

    def clients(self):
        result = subprocess.run(['pidof'] + list(CLIENTS), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, env=self.env, timeout=5)
        require(result.returncode in (0, 1), 'pidof client check failed')
        return result.stdout.strip()

    def runtime_state(self):
        return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'clients': self.clients(), 'gpu': json.loads(self.command(['plgpuctl', 'status'])),
                'post': self.post_state()}

    def firmware_path(self):
        value = FW_PATH.read_text()
        require(value.endswith('\n'), 'Unexpected firmware path sysfs output')
        return value[:-1]  # Remove only the sysfs getter's trailing newline.

    def flags(self):
        return (MANAGER / 'flags').read_text().strip()

    @contextlib.contextmanager
    def mmio(self, physical):
        import mmap
        fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
        try:
            require(physical in (0xa0010000, 0xa0030000, 0xa0040000), 'Only fixed PL control/CNN/FSR mappings permitted')
            with mmap.mmap(fd, 65536, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=physical) as mm:
                yield mm
        finally:
            os.close(fd)

    @staticmethod
    def read32(mm, offset):
        import ctypes
        require(type(offset) is int and offset % 4 == 0 and 0 <= offset <= 65532, 'Unaligned/out-of-range MMIO register')
        # An aligned native uint32 access, not a byte slice/copy on Device memory.
        # The temporary ctypes view is released before its mmap can be closed.
        return ctypes.c_uint32.from_buffer(mm, offset).value

    @staticmethod
    def write32(mm, offset, value):
        import ctypes
        require(type(offset) is int and offset % 4 == 0 and 0 <= offset <= 65532, 'Unaligned/out-of-range MMIO register')
        require(type(value) is int and 0 <= value <= 0xffffffff, 'Invalid MMIO word')
        ctypes.c_uint32.from_buffer(mm, offset).value = value

    def control_identity(self, mm):
        require(self.read32(mm, 0) == 0x52495801, 'Control CSR ABI mismatch')
        require(self.read32(mm, 0x0c) == 0x9adb505e, 'Control CSR configuration mismatch')

    def post_from_mmio(self, mm):
        self.control_identity(mm)
        require(self.read32(mm, 0x50) == 0x50535431 and self.read32(mm, 0x74) == 0x534e5031, 'PST1/SNP1 capability mismatch')
        require(self.read32(mm, 0x88) == 0xa1400000 and self.read32(mm, 0x90) == 384000, 'Snapshot address/size mismatch')
        return {'requested': self.read32(mm, 0x54), 'active': self.read32(mm, 0x58),
                'snapshot_status': self.read32(mm, 0x7c), 'snapshot_expirations': self.read32(mm, 0x8c)}

    def post_state(self):
        with self.mmio(0xa0010000) as mm:
            return self.post_from_mmio(mm)

    def cnn(self):
        with self.mmio(0xa0030000) as mm:
            magic = self.read32(mm, 0)
            require(magic == 0x4e4e5332, 'Refuse unknown CNN MMIO layout')
            capability = self.read32(mm, 0x3c)
            return {'magic': magic, 'shape': self.read32(mm, 4), 'capabilities': capability,
                    'adapter_abi': self.read32(mm, 0x44) if capability & 4 else None}

    def snapshot(self):
        result = self.runtime_state()
        loaded = self.loaded_modules()
        result.update(manager_name=(MANAGER / 'name').read_text().strip(),
                      manager_state=(MANAGER / 'state').read_text().strip(),
                      flags=self.flags(), firmware_path=self.firmware_path(),
                      cnn=self.cnn(), bindings={role: self.binding(role) for role in BINDINGS},
                      module_inventory=sorted(loaded),
                      modules={name: {'loaded': name in loaded,
                                      'refcount': loaded.get(name, {}).get('refcount', 0),
                                      'line': loaded.get(name, {}).get('line'), 'file': self.module_file(name)}
                               for name in MODULES})
        return result

    def write_sysfs(self, path, value):
        # No newline for module_param_string; empty string requires one NUL byte.
        data = value.encode() if value else b'\0'
        with open(str(path), 'wb', buffering=0) as stream:
            require(stream.write(data) == len(data), 'Short sysfs write')

    def set_firmware_path(self, value):
        self.write_sysfs(FW_PATH, value)

    def set_flags(self, value):
        self.write_sysfs(MANAGER / 'flags', value)

    def load_firmware(self, filename):
        require(filename in ('new.bin', 'old.bin'), 'Invalid load filename')
        self.write_sysfs(MANAGER / 'firmware', filename)

    def remove_module(self, name):
        require(name in MODULES, 'Only targeted PL modules may be removed')
        self.command(['rmmod', name])

    def insert_module(self, name):
        require(name in MODULES, 'Only targeted PL modules may be inserted')
        self.command(['insmod', MODULES[name]])

    def unbind(self, role):
        driver, device = BINDINGS[role]
        require(self.binding(role) == self.expected_binding(role), 'Exact binding changed before unbind')
        self.write_sysfs(Path('/sys/bus/platform/drivers') / driver / 'unbind', device)

    def bind(self, role):
        driver, device = BINDINGS[role]
        require(self.binding(role) is None, 'Device unexpectedly bound before bind')
        self.write_sysfs(Path('/sys/bus/platform/drivers') / driver / 'bind', device)

    def wait(self, predicate, message, timeout=20):
        until = time.monotonic() + timeout
        last = None
        while time.monotonic() < until:
            try:
                if predicate():
                    return
            except Exception as error:
                last = repr(error)
            time.sleep(.1)
        raise RuntimeError(message + (': ' + last if last else ''))

    def wait_operating(self):
        self.wait(lambda: (MANAGER / 'state').read_text().strip() == 'operating', 'FPGA manager failed to reach operating')

    def wait_gpu_ready(self):
        def ready():
            check_gpu(json.loads(self.command(['plgpuctl', 'status'])))
            return True
        self.wait(ready, 'GPU/MIG failed to become ready')

    def wait_control_ready(self):
        with self.mmio(0xa0010000) as mm:
            self.control_identity(mm)
            until = time.monotonic() + 20
            while time.monotonic() < until:
                status = self.read32(mm, 8)
                require(not status & 4, 'GPU/control CSR fault during MIG wait')
                if status == 3:
                    return
                time.sleep(.1)
            raise RuntimeError('MIG/GPU control CSR did not reach status3 before rebinding')

    def set_enabled(self, value):
        import fcntl
        require(value in (0, 1), 'Invalid enabled value')
        fd = os.open('/dev/plgpu_display', os.O_RDWR | os.O_CLOEXEC)
        try:
            # linux/include/plgpu-display.h: _IOW('R', 1, __u32).
            fcntl.ioctl(fd, 0x40045201, struct.pack('<I', value))
        finally:
            os.close(fd)

    def set_post_mode1(self):
        # The controller already owns rix-superres.lock. Calling the POST CLI
        # mutation path would attempt to reacquire it in a child and fail.
        with self.mmio(0xa0010000) as mm:
            post = self.post_from_mmio(mm)
            require(post['snapshot_status'] == post['snapshot_expirations'] == 0, 'Refuse post restoration with a lease/expiration')
            require(self.read32(mm, 8) == 3, 'Control CSR became unready before post restore')
            self.write32(mm, 0x54, 1)
            require(self.read32(mm, 0x54) == 1, 'Post request MMIO write failed')
            # A Device read after this same-peripheral write preserves ordered
            # access; wait for the native accepted-prepare acknowledgement.
            until = time.monotonic() + 20
            while time.monotonic() < until:
                if self.read32(mm, 0x58) == 1:
                    return
                time.sleep(.1)
            raise RuntimeError('Post mode1 acknowledgement timeout')

    def wait_post_mode1(self):
        def ready():
            state = self.post_state()
            return state['requested'] == state['active'] == 1 and state['snapshot_status'] == state['snapshot_expirations'] == 0
        self.wait(ready, 'Postprocessor failed to restore idle mode1')

    def journal(self, document):
        self.ram_directory(REPORT.parent)
        require(not REPORT.is_symlink(), 'Refuse report symlink')
        require(self.report_owned or not REPORT.exists(), 'Refuse to overwrite a previous transaction report')
        temp = REPORT.with_name(REPORT.name + '.' + str(os.getpid()) + '.pending')
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp), str(REPORT))
        self.report_owned = True
        directory = os.open(str(REPORT.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def main():
    import signal
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--execute', action='store_true', help='Explicitly execute the prepared RAM transaction')
    args = parser.parse_args()
    require(args.execute, 'Execution requires --execute; import or --help is inert')
    require(args.manifest == MANIFEST and not MANIFEST.is_symlink(), 'Only fixed RAM manifest accepted')
    adapter = LinuxAdapter()
    controller = Controller(adapter)
    def interrupted(sig, frame):
        if not controller.recovering:
            raise RuntimeError('Transaction interrupted by signal ' + str(sig))
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    result = controller.run(adapter.read_manifest)
    print('FPGA_RAM_TRANSACTION', json.dumps(result, sort_keys=True), flush=True)
    return 0 if result['passed'] else (3 if result['outcome'] == 'recovery-failed' else 2)


if __name__ == '__main__':
    raise SystemExit(main())
