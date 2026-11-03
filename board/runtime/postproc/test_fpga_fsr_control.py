#!/usr/bin/env python3
"""Host-only fault injection. Never opens serial, JTAG, sysfs, or /dev/mem."""
import contextlib
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / 'report/fsr-pl/fixed-v7/fpga-control'
spec = importlib.util.spec_from_file_location('fpga_ram_control', HERE / 'fpga_fsr_control.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
checks = {}
cases = {}


def check(name, condition):
    checks[name] = bool(condition)
    assert condition, name


def digest(value):
    return hashlib.sha256(value).hexdigest()


def manifest():
    return {'format': 'rix-fpga-ram-fsr1', 'source_sha256': 'a'*64, 'images': {
        'new': {'filename': 'new.bin', 'bytes': 3, 'sha256': digest(b'new')},
        'old': {'filename': 'old.bin', 'bytes': 3, 'sha256': digest(b'old')}}}


class MockAdapter:
    def __init__(self):
        self.data = {'new.bin': b'new', 'old.bin': b'old'}
        self.loaded = set(m.MODULES) | {'uinput', 'uio_pdrv_genirq'}
        self.bound = {r: self.expected_binding(r) for r in m.BINDINGS}
        self.refcounts = {n: 0 for n in m.MODULES}
        self.files = {n: {'path': p, 'bytes': 17, 'sha256': digest(n.encode())} for n, p in m.MODULES.items()}
        self.image = 'old'
        self.enabled = 1
        self.post = 1
        self.path = ''
        self.flag = '10'
        self.boot = 'same-boot-id'
        self.calls = []
        self.journals = []
        self.fail = {}
        self.idle_override = {}
        self.verify_override = {}
        self.locked = False
        self.receipt = None

    def rollback_proof(self, boot, sha256):
        assert boot == self.boot and sha256 == digest(b'old')

    def verify_fsr_protocol(self):
        if self.fail.get('verify:fsr'): raise RuntimeError('Injected FSR protocol failure')
        return {'passed': True, 'commands': [{'mode': 2, 'return': 0}, {'mode': 99, 'return': 2}, {'mode': 1, 'return': 1}], 'pixel_computation_tested': False}

    def activate_receipt(self, boot, bit, source):
        self.op('activate:receipt', lambda: setattr(self, 'receipt', (boot, bit, source)))

    def deactivate_receipt(self):
        self.op('deactivate:receipt', lambda: setattr(self, 'receipt', None))

    def expected_binding(self, role):
        driver, device = m.BINDINGS[role]
        return {'device': device, 'driver': driver,
                'driver_target': '/sys/bus/platform/drivers/' + driver,
                'device_target': '/sys/devices/platform/exact-pl/' + device}

    @contextlib.contextmanager
    def locks(self):
        self.locked = True
        try:
            yield
        finally:
            self.locked = False

    def preflight_paths(self):
        assert self.locked

    def image_info(self, filename):
        return {'path': str(m.BASE / filename), 'bytes': len(self.data[filename]), 'sha256': digest(self.data[filename])}

    def module_file(self, name):
        return copy.deepcopy(self.files[name])

    def runtime_state(self):
        gpu = dict(abi=0x52495801, config=0x9adb505e, status=3, enabled=self.enabled,
                   **{k: (42 if self.image == 'old' else 0) for k in m.IDS},
                   **{k: 0 for k in m.ERRORS})
        value = {'boot_id': self.boot, 'clients': '', 'gpu': gpu,
                 'post': {'requested': self.post, 'active': self.post,
                          'snapshot_status': 0, 'snapshot_expirations': 0}}
        for key, item in self.idle_override.items():
            if isinstance(item, dict):
                value[key].update(item)
            else:
                value[key] = item
        return value

    def snapshot(self):
        value = self.runtime_state()
        cnn = {'magic': 0x4e4e5332, 'shape': (96 << 16) | 160,
               'capabilities': 7,
               'adapter_abi': 0x00020001}
        if self.image == 'new':
            cnn.update(self.verify_override)
        value.update(manager_name='Xilinx ZynqMP FPGA Manager', manager_state='operating',
                     flags=self.flag, firmware_path=self.path, cnn=cnn,
                     bindings=copy.deepcopy(self.bound), module_inventory=sorted(self.loaded),
                     modules={n: {'loaded': n in self.loaded, 'refcount': self.refcounts[n],
                                  'line': n + ' 123 0 - Live 0x0', 'file': self.module_file(n)} for n in m.MODULES})
        return value

    def journal(self, record):
        self.journals.append(copy.deepcopy(record))

    def op(self, label, action):
        assert self.locked
        assert self.journals and self.journals[-1]['events'][-1]['status'] == 'pending', 'Mutation without durable intent'
        self.calls.append(label)
        remaining = self.fail.get(label, 0)
        if remaining:
            if remaining != 'always':
                self.fail[label] -= 1
            raise RuntimeError('Injected ' + label)
        action()

    def binding(self, role):
        return copy.deepcopy(self.bound[role])

    def module_loaded(self, name):
        return name in self.loaded

    def remove_module(self, name):
        self.op('remove:' + name, lambda: self.loaded.remove(name))

    def insert_module(self, name):
        self.op('insert:' + name, lambda: self.loaded.add(name))

    def unbind(self, role):
        self.op('unbind:' + role, lambda: self.bound.__setitem__(role, None))

    def bind(self, role):
        self.op('bind:' + role, lambda: self.bound.__setitem__(role, self.expected_binding(role)))

    def firmware_path(self):
        return self.path

    def flags(self):
        return self.flag

    def set_firmware_path(self, value):
        label = 'path:ram' if value == str(m.BASE) else 'path:original'
        self.op(label, lambda: setattr(self, 'path', value))

    def set_flags(self, value):
        self.op('flags:' + value, lambda: setattr(self, 'flag', value))

    def load_firmware(self, filename):
        def action():
            assert not any(n in self.loaded for n in m.MODULES)
            assert all(v is None for v in self.bound.values())
            assert self.path == str(m.BASE) and self.flag == '0'
            self.image = filename[:-4]
            self.enabled = self.post = 0
        self.op('load:' + filename, action)

    def wait_operating(self):
        label = 'wait-operating:' + self.image
        if self.fail.get(label):
            self.fail[label] -= 1
            raise RuntimeError('Injected ' + label)

    def wait_gpu_ready(self):
        assert 'plgpu_display' in self.loaded and 'rix_dma_proxy' in self.loaded

    def wait_control_ready(self):
        label = 'wait-control:' + self.image
        if self.fail.get(label):
            self.fail[label] -= 1
            raise RuntimeError('Injected MIG timeout: ' + label)
        self.calls.append(label)

    def set_enabled(self, value):
        self.op('enable:' + str(value), lambda: setattr(self, 'enabled', value))

    def set_post_mode1(self):
        self.op('post:1', lambda: setattr(self, 'post', 1))

    def wait_post_mode1(self):
        assert self.post == 1


def run(name, adapter=None, document=None):
    a = adapter or MockAdapter()
    result = m.Controller(a).run(manifest() if document is None else document)
    cases[name] = result
    check(name + '_report_finished', not a.locked and a.journals[-1] == result)
    return a, result


a, r = run('normal')
check('normal_new_success', r['passed'] and r['outcome'] == 'new-loaded-and-verified' and a.image == 'new')
check('normal_receipt_bound_to_boot_bit_and_source', a.receipt == (a.boot, digest(b'new'), 'a'*64) and r['after']['fsr']['passed'])
check('normal_original_path_flags', a.path == '' and a.flag == '10')
check('normal_exact_remove_order', a.calls[:5] == ['remove:i2c_gpio', 'remove:rix_dma_proxy', 'remove:plgpu_display', 'unbind:dma', 'unbind:gpio'])
check('normal_original_insert_order', [s for s in a.calls if s.startswith('bind:') or s.startswith('insert:')] == ['bind:gpio', 'bind:dma', 'insert:rix_dma_proxy', 'insert:plgpu_display', 'insert:i2c_gpio'])
check('normal_unrelated_modules_preserved', {'uinput', 'uio_pdrv_genirq'} <= a.loaded)
check('normal_journal_before_first_device_change', a.journals[0]['device_mutation_started'] is False and 'before' in a.journals[0])
check('normal_complete_exact_cnn_identity', r['after']['cnn']['capabilities'] == 7 and r['after']['cnn']['adapter_abi'] == 0x20001)
check('normal_MIG_wait_before_any_rebind', a.calls.index('wait-control:new') < a.calls.index('bind:gpio') < a.calls.index('bind:dma'))

a = MockAdapter();a.loaded.remove('i2c_gpio');a, r = run('optional_i2c_absent', a)
check('optional_i2c_absent_kept_absent', r['passed'] and 'i2c_gpio' not in a.loaded and not any('i2c_gpio' in s for s in a.calls))
a = MockAdapter();a.enabled = 0;a, r = run('enabled_zero', a)
check('enabled_zero_restored', r['passed'] and a.enabled == 0 and 'enable:0' in a.calls)

bad_cases = {
    'old_sha_bad': lambda a: a.data.__setitem__('old.bin', b'bad'),
    'new_sha_bad': lambda a: a.data.__setitem__('new.bin', b'bad'),
    'wrong_binding': lambda a: a.bound.__setitem__('dma', {'driver': 'PS-wrong-driver'}),
    'active_client': lambda a: a.idle_override.update(clients='123'),
    'queues_active': lambda a: a.idle_override.update(gpu={'swap': 43}),
    'gpu_fault': lambda a: a.idle_override.update(gpu={'timeouts': 1}),
    'snapshot_active': lambda a: a.idle_override.update(post={'snapshot_status': 3}),
    'snapshot_expired': lambda a: a.idle_override.update(post={'snapshot_expirations': 1}),
    'post_wrong_mode': lambda a: a.idle_override.update(post={'active': 2}),
    'module_busy': lambda a: a.refcounts.__setitem__('rix_dma_proxy', 1),
    'module_missing': lambda a: a.loaded.remove('plgpu_display'),
    'module_file_redirect': lambda a: a.files['rix_dma_proxy'].update(path='/tmp/unknown.ko'),
    'newline_original_path': lambda a: setattr(a, 'path', '/bad\n'),
}
for name, alter in bad_cases.items():
    a = MockAdapter();alter(a);a, r = run(name, a)
    check(name + '_zero_device_changes', not r['passed'] and not a.calls and not r['device_mutation_started'])

for name, alter in (
        ('manifest_traversal', lambda d: d['images']['old'].update(filename='../old.bin')),
        ('manifest_boolean_bytes', lambda d: d['images']['old'].update(bytes=True)),
        ('manifest_duplicate_roles', lambda d: d['images'].update(extra=d['images']['old'])),
        ('manifest_same_image', lambda d: d['images']['new'].update(sha256=d['images']['old']['sha256'])),
        ('manifest_unknown_field', lambda d: d.update(command='unexpected'))):
    d = manifest();alter(d);a, r = run(name, document=d)
    check(name + '_zero_device_changes', not r['passed'] and not a.calls)
try:
    json.loads('{"a":1,"a":2}', object_pairs_hook=m.unique_object)
except RuntimeError:
    check('duplicate_json_key_rejected', True)
else:
    check('duplicate_json_key_rejected', False)

recoverable = {
    'new_load_failure': 'load:new.bin',
    'new_dma_rebind_failure': 'bind:dma',
    'new_module_insert_failure': 'insert:plgpu_display',
    'restore_path_transient_failure': 'path:original',
    'restore_flags_transient_failure': 'flags:10',
    'partial_quiesce_failure': 'remove:i2c_gpio',
    'fsr_protocol_failure': 'verify:fsr',
    'fsr_receipt_failure': 'activate:receipt',
}
for name, failure in recoverable.items():
    a = MockAdapter();a.fail[failure] = 1;a, r = run(name, a)
    check(name + '_explicit_failure_with_rollback', not r['passed'] and r['outcome'] == 'rolled-back' and r['rollback']['passed'])
    check(name + '_original_restored', a.image == 'old' and a.path == '' and a.flag == '10' and all(a.bound.values()) and all(n in a.loaded for n in m.MODULES) and a.receipt is None)
    check(name + '_rollback_before_restore_modules', 'load:old.bin' not in a.calls or a.calls.index('load:old.bin') < len(a.calls) - 1 - a.calls[::-1].index('insert:rix_dma_proxy'))

a = MockAdapter();a.fail['wait-operating:new'] = 1;a, r = run('operating_timeout', a)
check('operating_timeout_rolls_back', not r['passed'] and r['rollback']['passed'] and 'load:old.bin' in a.calls)
a = MockAdapter();a.fail['wait-control:new'] = 1;a, r = run('MIG_timeout_before_rebind', a)
check('MIG_timeout_rolls_back_before_binding', not r['passed'] and r['rollback']['passed'] and a.calls.index('load:old.bin') < a.calls.index('bind:gpio'))
check('MIG_recovery_waits_before_DMA', a.calls.index('wait-control:old') < a.calls.index('bind:dma'))
a = MockAdapter();a.fail.update({'wait-control:new': 1, 'wait-control:old': 1});a, r = run('both_MIG_timeouts', a)
check('both_MIG_timeouts_do_not_probe_DMA', not r['passed'] and r['outcome'] == 'recovery-failed' and not any(s.startswith('bind:') for s in a.calls))
a = MockAdapter();a.verify_override['adapter_abi'] = 0x20002;a, r = run('new_wrong_abi', a)
check('new_wrong_abi_rolls_back', not r['passed'] and r['rollback']['passed'] and a.image == 'old')
a = MockAdapter();a.fail.update({'load:new.bin': 1, 'load:old.bin': 1});a, r = run('rollback_load_failure', a)
check('rollback_load_failure_never_claims_success', not r['passed'] and not r['rollback']['passed'] and r['outcome'] == 'recovery-failed' and 'recovery_required' in r)
check('rollback_load_failure_restores_global_parameters', a.path == '' and a.flag == '10')
check('rollback_load_failure_remains_quiesced', not any(n in a.loaded for n in m.MODULES) and all(v is None for v in a.bound.values()))
a = MockAdapter();a.fail['path:original'] = 'always';a, r = run('restore_path_permanent_failure', a)
check('permanent_path_failure_visible', not r['passed'] and r['outcome'] == 'recovery-failed' and r['rollback']['parameter_errors'])
check('permanent_path_failure_still_attempts_flags_restore', a.flag == '10')

class ChangedCandidateAfterFailure(MockAdapter):
    def load_firmware(self, filename):
        if filename == 'new.bin':
            self.data['new.bin'] = b'removed-candidate'
            self.op('load:new.bin', lambda: None)
            raise RuntimeError('Candidate failed then changed')
        return super().load_firmware(filename)
a, r = run('candidate_changed_does_not_block_old', ChangedCandidateAfterFailure())
check('candidate_changed_does_not_block_old_recovery', not r['passed'] and r['rollback']['passed'] and a.image == 'old')

class ChangedRollbackAfterFailure(MockAdapter):
    def load_firmware(self, filename):
        if filename == 'new.bin':
            self.data['old.bin'] = b'changed-rollback'
            self.op('load:new.bin', lambda: None)
            raise RuntimeError('Load failed')
        return super().load_firmware(filename)
a, r = run('rollback_changed_after_preflight', ChangedRollbackAfterFailure())
check('changed_rollback_never_loaded', not r['passed'] and r['outcome'] == 'recovery-failed' and 'load:old.bin' not in a.calls)

class Stream:
    def __init__(self):
        self.data = b''
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def write(self, data):
        self.data += data
        return len(data)
real = m.LinuxAdapter()
for value, expected in (('', b'\0'), ('/tmp/exact', b'/tmp/exact')):
    stream = Stream()
    with patch('builtins.open', return_value=stream):
        real.write_sysfs(m.FW_PATH, value)
    check('sysfs_path_bytes_' + ('empty' if not value else 'nonempty'), stream.data == expected)
with patch.object(Path, 'read_text', return_value='\n'):
    check('empty_path_getter_exact', real.firmware_path() == '')
with patch.object(Path, 'read_text', return_value='/path\n'):
    check('nonempty_path_getter_exact', real.firmware_path() == '/path')
with patch.object(real, 'ram_directory'), patch.object(Path, 'is_symlink', return_value=False), patch.object(Path, 'exists', return_value=True), patch.object(m.os, 'open') as opened:
    try:
        real.journal({'attempt': 'unrelated'})
    except RuntimeError:
        check('previous_transaction_report_never_overwritten', not opened.called)
    else:
        check('previous_transaction_report_never_overwritten', False)

def invalid_json():
    raise ValueError('Malformed manifest')
a, r = run('malformed_manifest_loader', document=invalid_json)
check('malformed_manifest_reported_without_device_changes', not r['passed'] and not a.calls and r['outcome'] == 'preflight-failed-no-device-change')

# Exercise the real scalar MMIO accessors against a normal bytearray only.
memory = bytearray(65536)
for offset, value in ((0, 0x52495801), (0x0c, 0x9adb505e), (8, 3),
                      (0x50, 0x50535431), (0x74, 0x534e5031), (0x88, 0xa1400000),
                      (0x90, 384000), (0x54, 0), (0x58, 1), (0x7c, 0), (0x8c, 0)):
    real.write32(memory, offset, value)
@contextlib.contextmanager
def fake_mmio(physical):
    assert physical == 0xa0010000
    yield memory
with patch.object(real, 'mmio', fake_mmio), patch.object(real, 'command', side_effect=AssertionError('POST CLI must not be used under held flock')):
    real.wait_control_ready()
    real.set_post_mode1()
    real.wait_post_mode1()
    check('direct_POST_restore_never_spawns_locking_child', real.read32(memory, 0x54) == 1)
    check('direct_POST_exact_lease_expired_registers', real.post_state()['snapshot_status'] == real.post_state()['snapshot_expirations'] == 0)
for offset in (1, -4, 65536):
    try:
        real.read32(memory, offset)
    except RuntimeError:
        check('unaligned_MMIO_read_rejected_' + str(offset), True)
    else:
        check('unaligned_MMIO_read_rejected_' + str(offset), False)

class NeverReady:
    def __init__(self):
        self.now = 0
    def monotonic(self):
        self.now += 11
        return self.now
real.write32(memory, 8, 1)
timer = NeverReady()
with patch.object(real, 'mmio', fake_mmio), patch.object(m.time, 'monotonic', timer.monotonic), patch.object(m.time, 'sleep'):
    try:
        real.wait_control_ready()
    except RuntimeError:
        check('direct_MIG_deadline_no_driver_probe', True)
    else:
        check('direct_MIG_deadline_no_driver_probe', False)

OUT.mkdir(parents=True, exist_ok=True)
record = {'passed': all(checks.values()), 'checks': len(checks), 'results': checks,
          'source_sha256': digest((HERE / 'fpga_fsr_control.py').read_bytes()),
          'test_sha256': digest(Path(__file__).read_bytes()),
          'case_count': len(cases), 'scope': 'Host adapter mocks only; no board, kernel manager, serial, JTAG, firmware or real sysfs operations performed'}
(OUT / 'host-tests.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
(OUT / 'mock-journals.json').write_text(json.dumps(cases, indent=2) + '\n', encoding='utf-8')
print('FPGA_RAM_CONTROL_HOST_TESTS', record['checks'], record['passed'])
