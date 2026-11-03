#!/usr/bin/env python3
"""Explicit board QA for the already loaded, boot-bound fixed-v19 FSR image.

Importing this module never accesses a device. Pixel processing is done by the
approved rix-fsr-pl executable; Python only verifies files and LCD samples.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import time

BASE = Path('/tmp/rix-fpga-fsr')
RUNTIME = BASE / 'rix-fsr-pl'
OUT = Path('/tmp/postproc-tests/fsr-pl-v19')
POST = '/opt/rasterix/postproc-touch/bin/rix-superres'
BIT_SHA256 = 'a488264602aaa053ea679def98a322947fad1ae4a71d629fab496efb7eed96a2'
SOURCE_SHA256 = '1203b18ecf2db7d2bce6bc28579693c2e438e99446741a31b45229a4d4b4db5f'
RUNTIME_SHA256 = '10f857e1e816534b434481a248e89fb0edce589ee12727a07a0bc11a21de3667'
ERRORS = ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')
CLIENTS = ('ClassiCube', 'rix-neural-style', 'rix-superres', 'rix-fsr-pl',
           'tuxracer', 'neverball', 'neverputt', 'quakespasm', 'quake3e',
           'rix-glx-probe', 'rix-smoke', 'rix-danmaku', 'th06-rix')
IDENTITIES = {
    'mc-live64': (
        '5e40c89a264d3526faea446f357bc0200139cc89ff27e3d4579b2e35737d5915',
        'eecb47383cf60999081273269bf25f1c8e29b10d94399256720ba5fe445fc0f4'),
    'mc-terrain32-0': (
        '2e336e305dc249867400d7bae52429c58b4de23e5d10f3c1da9209cbe18f118c',
        'c5a2169efa9d07820ce09f382efc1d5f53f739295e2fcbcb10349b6f65f4c250'),
    'mc-terrain32-9': (
        '75f86ae5fffcf5da847aa0117fd36bd0a7a0a9fa67ed7d12a9dbafb293225602',
        'c89d271097b2044cad1b7a91e2dffc215b40e27a9236b7d53b8be2dc5f03f18e'),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exclusive_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def private_file(path, permissions=False):
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0,
            'Expected a root-owned regular file: ' + str(path))
    require(not (info.st_mode & (0o077 if permissions else 0o022)),
            'Unsafe file permissions: ' + str(path))


def guard_space():
    thresholds = {'/': 32 * 1024**2, '/media/sd-mmcblk1p1': 16 * 1024**2,
                  '/tmp': 64 * 1024**2}
    available = {}
    for path, minimum in thresholds.items():
        volume = os.statvfs(path)
        available[path] = volume.f_bavail * volume.f_frsize
        require(available[path] >= minimum, 'Free-space guard failed: ' + path)
    return available


def stop_without_kill(process):
    """Preserve an intentional quarantine flock if the AXI master cannot drain."""
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Child PID %d did not drain; it remains alive. '
                               'Do not start another GPU client; recover/reset PL.' % process.pid)
    return process.returncode


def run_logged(command, log_path, timeout=30):
    with Path(log_path).open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_without_kill(process)
            raise RuntimeError('Command exceeded deadline: ' + command[0])
        except BaseException:
            stop_without_kill(process)
            raise
    require(process.returncode == 0, 'Command failed; see ' + str(log_path))
    return Path(log_path).read_text()


def json_line(text):
    rows = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
    require(len(rows) == 1, 'Expected exactly one statistics JSON object')
    return rows[0]


def check_gpu(value):
    require(value['status'] == 3 and value['config'] == 0x9adb505e,
            'GPU/MIG status or configuration mismatch')
    require(all(value[key] == 0 for key in ERRORS), 'GPU fault counter is nonzero')
    ids = ('frame_id', 'swap', 'copy', 'presented', 'last_presented')
    require(len({value[key] for key in ids}) == 1, 'GPU queues are not drained')
    return value


def snapshot(label):
    gpu = check_gpu(json.loads(run_logged(['plgpuctl', 'status'], OUT / (label + '-gpu.log'))))
    post = json_line(run_logged([POST, '--status'], OUT / (label + '-post.log')))
    require(post['snapshot_status'] == 0, 'An SNP1 lease remains active')
    require(post['requested'] == post['active'], 'A display switch remains active')
    return {'gpu': gpu, 'post': post}


def active_clients():
    result = subprocess.run(['pidof'] + list(CLIENTS), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True, timeout=5)
    require(result.returncode in (0, 1), 'Cannot check active GPU processes')
    return result.stdout.strip()


def receipt_identity(expected_runtime):
    require(os.geteuid() == 0, 'Root is required')
    require(not Path('/tmp/rix-fsr-pl.quarantine').exists(), 'FSR is quarantined')
    base_info = BASE.lstat()
    require(stat.S_ISDIR(base_info.st_mode) and base_info.st_uid == 0 and
            not base_info.st_mode & 0o022, 'Unsafe RAM load directory')
    for path in (RUNTIME, BASE / 'manifest.json', BASE / 'active-receipt.txt'):
        private_file(path, path.name == 'active-receipt.txt')
    require(sha(RUNTIME) == expected_runtime, 'Runtime SHA256 differs from reviewed build')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    receipt = (BASE / 'active-receipt.txt').read_text().splitlines()
    require(len(receipt) == 4 and receipt[0] == 'RIX_FSR_PL_ACTIVE_V1' and receipt[1] == boot,
            'An active receipt for this boot is required before any device command')
    manifest = json.loads((BASE / 'manifest.json').read_text())
    require(manifest['format'] == 'rix-fpga-ram-fsr1', 'Wrong load manifest format')
    require(receipt[2] == manifest['images']['new']['sha256'] and
            receipt[3] == manifest['source_sha256'], 'Receipt and load manifest differ')
    require(receipt[2] == BIT_SHA256 and receipt[3] == SOURCE_SHA256,
            'Receipt is not the reviewed fixed-v19 full-board build')
    require(all(re.fullmatch('[0-9a-f]{64}', value) for value in receipt[2:]),
            'Invalid receipt identity')
    # The runtime independently checks these identities against its compiled
    # bitstream/source constants before it maps the FSR register range.
    return {'boot_id': boot, 'bit_sha256': receipt[2], 'source_sha256': receipt[3],
            'runtime_sha256': expected_runtime}


def vectors():
    result = {}
    for name, identities in IDENTITIES.items():
        source = BASE / 'vectors' / name / 'source.rgb565'
        golden = BASE / 'vectors' / name / 'golden.xrgb'
        for path, size, identity in ((source, 192000, identities[0]),
                                     (golden, 1536000, identities[1])):
            private_file(path)
            require(path.stat().st_size == size and sha(path) == identity,
                    'Wrong fixed-v19 vector: ' + str(path))
        result[name] = (source, golden)
    return result


def compare_frame(output, golden):
    actual, expected = Path(output).read_bytes(), Path(golden).read_bytes()
    require(len(actual) == len(expected) == 1536000, 'Invalid full-frame output length')
    mismatches = sum(a != b for a, b in zip(struct.iter_unpack('<I', actual),
                                          struct.iter_unpack('<I', expected)))
    require(mismatches == 0, 'Full-frame golden mismatch: %d pixels' % mismatches)
    return {'pixels': 384000, 'mismatches': mismatches, 'output_sha256': sha(output)}


def expected_lcd(raw):
    require(len(raw) == 1536000, 'Invalid XRGB8888 image length')
    pixels = struct.unpack('<384000I', raw)
    return [((pixels[y * 8 * 800 + x * 8] >> 8) & 0xf800) |
            ((pixels[y * 8 * 800 + x * 8] >> 5) & 0x07e0) |
            ((pixels[y * 8 * 800 + x * 8] >> 3) & 0x001f)
            for y in range(60) for x in range(100)]


def case_stats(text):
    require('PASS FSR_PL_FULL_FRAME_GOLDEN 384000 pixels' in text,
            'Runtime did not confirm the golden check before presentation')
    stats = json_line(text)
    require(stats['frames'] == 1 and stats['snapshot_retries'] == 0 and
            stats['last_bank'] in (0, 1) and stats['compute_us'] > 0 and
            stats['cpu_pixel_processing_live'] is False, 'Unexpected static statistics')
    return stats


def held_lcd_case(source, golden, initial_post):
    output, capture = OUT / 'display.xrgb', OUT / 'lcd.rgb565'
    command = [str(RUNTIME), '--input', str(source), '--output', str(output),
               '--verify-output', str(golden), '--hold-seconds', '30']
    log_path = OUT / 'display-runtime.log'
    with log_path.open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 25
            while True:
                require(process.poll() is None, 'Runtime exited before the held LCD capture')
                require(time.monotonic() < deadline, 'Runtime did not reach the held-output barrier')
                text = log_path.read_text()
                if any(line.startswith('{') for line in text.splitlines()) and output.exists() and output.stat().st_size == 1536000:
                    break
                time.sleep(.05)
            stats = case_stats(text)
            full_frame = compare_frame(output, golden)
            post = json_line(run_logged([POST, '--status'], OUT / 'held-post.log'))
            expected_mode = 2 | (stats['last_bank'] << 9)
            require(post['requested'] == post['active'] == expected_mode and
                    post['snapshot_status'] == 0 and
                    post['snapshot_expirations'] == initial_post['snapshot_expirations'],
                    'LCD is not holding the verified FSR output bank')
            require(not capture.exists(), 'LCD output already exists')
            run_logged([POST, '--capture', str(capture)], OUT / 'lcd-capture.log', timeout=10)
            require(process.poll() is None, 'Display hold expired during the capture')
            raw = capture.read_bytes()
            require(len(raw) == 12000, 'LCD capture must contain 6000 RGB565 samples')
            expected = expected_lcd(output.read_bytes())
            mismatches = sum(a != b for a, b in zip(struct.unpack('<6000H', raw), expected))
            require(mismatches == 0, 'LCD sample mismatch: %d / 6000' % mismatches)
            return dict(stats=stats, full_frame=full_frame, samples=6000, mismatches=mismatches,
                        lcd_sha256=sha(capture), held_post=post, command=command)
        finally:
            require(stop_without_kill(process) == 0, 'Held runtime did not restore the display cleanly')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-sha256', required=True,
                        help='SHA256 of the reviewed runtime-r1 executable')
    arguments = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{64}', arguments.runtime_sha256), 'Invalid runtime SHA256')
    require(arguments.runtime_sha256 == RUNTIME_SHA256, 'Runtime SHA256 is not the reviewed fixed-v19 r1 build')
    identity = receipt_identity(arguments.runtime_sha256)
    spaces = guard_space()
    require(not active_clients(), 'An active GPU client prevents static QA')
    inputs = vectors()
    # No device command occurs before all identities, space, process and vector
    # checks pass. No existing report or persistent file is ever opened to write.
    OUT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_info = OUT.parent.lstat()
    require(stat.S_ISDIR(parent_info.st_mode) and parent_info.st_uid == 0 and
            not parent_info.st_mode & 0o022, 'Unsafe report parent')
    OUT.mkdir(mode=0o700)
    record = dict(format='rix-fsr-pl-fixed-v19-board-qa', passed=False, error=None,
                  identity=identity, spaces_before=spaces, cases=[], lcd=None,
                  script_sha256=sha(__file__), note='Static correctness only; no live FPS claim')
    failure = None
    try:
        before = record['before'] = snapshot('before')
        require(before['post']['requested'] == before['post']['active'] == 1,
                'Expected idle bilinear/style0 display mode')
        require(before['post']['snapshot_expirations'] == 0,
                'Snapshot expiration counter is nonzero before QA')
        for name, (source, golden) in inputs.items():
            output = OUT / (name + '.xrgb')
            command = [str(RUNTIME), '--input', str(source), '--output', str(output),
                       '--verify-output', str(golden), '--no-present']
            stats = case_stats(run_logged(command, OUT / (name + '-runtime.log'), timeout=40))
            item = dict(scene=name, command=command, stats=stats,
                        comparison=compare_frame(output, golden))
            after = snapshot(name + '-after')
            require(after['post']['requested'] == after['post']['active'] == 1 and
                    after['post']['snapshot_expirations'] == before['post']['snapshot_expirations'],
                    'A no-present case changed display/lease state')
            item['after'] = after
            record['cases'].append(item)
        source, golden = inputs['mc-live64']
        record['lcd'] = held_lcd_case(source, golden, before['post'])
        record['passed'] = True
    except Exception as exc:
        record['error'] = repr(exc)
        failure = exc
    finally:
        # If a child is intentionally quarantined, avoid further device access.
        try:
            require(not active_clients(), 'A client remains active; device state was not probed')
            require(not Path('/tmp/rix-fsr-pl.quarantine').exists(), 'FSR is quarantined')
            record['identity_after'] = receipt_identity(arguments.runtime_sha256)
            require(record['identity_after'] == identity, 'Load/boot identity changed during QA')
            after = record['after'] = snapshot('after')
            require(after['post']['requested'] == after['post']['active'] == 1 and
                    after['post']['snapshot_expirations'] == record['before']['post']['snapshot_expirations'],
                    'Runtime did not restore the original display/lease state')
            record['spaces_after'] = guard_space()
        except Exception as exc:
            record['passed'] = False
            record['cleanup_error'] = repr(exc)
            failure = failure or exc
        exclusive_json(OUT / 'result.json', record)
        print(json.dumps(dict(passed=record['passed'], report=str(OUT / 'result.json'),
                              static_cases=len(record['cases']),
                              lcd_samples=6000 if record['lcd'] else 0,
                              error=record['error'], cleanup_error=record.get('cleanup_error'))), flush=True)
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(passed=False, report=None, error=repr(exc))), flush=True)
        raise SystemExit(1)
