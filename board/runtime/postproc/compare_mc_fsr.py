#!/usr/bin/env python3
"""Bounded MC comparison using the installed FSR1 tool; outputs stay in RAM."""
import hashlib
import json
import os
from pathlib import Path
import select
import statistics
import struct
import subprocess
import tarfile
import time

POST = '/opt/rasterix/postproc-touch/bin/rix-superres'
OUT = Path('/tmp/postproc-tests/cc_fsr_compare_20261023')
ERRORS = ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')


def run(command, timeout=15):
    return subprocess.check_output(command, universal_newlines=True, timeout=timeout)


def status():
    return json.loads(run(['plgpuctl', 'status']))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_line(text):
    return next(json.loads(line) for line in text.splitlines() if line.startswith('{'))


def check_gpu():
    value = status()
    assert value['status'] == 3 and value['config'] == 0x9adb505e, value
    assert not any(value[k] for k in ERRORS), value
    return value


def main():
    assert os.geteuid() == 0
    assert not subprocess.run(['pidof', 'ClassiCube', 'rix-neural-style', 'rix-superres'],
                              stdout=subprocess.PIPE).stdout, 'GPU client already active'
    assert os.statvfs('/').f_bavail * os.statvfs('/').f_frsize >= 32 * 1024**2
    assert os.statvfs('/media/sd-mmcblk1p1').f_bavail * os.statvfs('/media/sd-mmcblk1p1').f_frsize >= 16 * 1024**2
    assert os.statvfs('/tmp').f_bavail * os.statvfs('/tmp').f_frsize >= 64 * 1024**2
    OUT.mkdir(mode=0o700)
    profile = Path('/opt/rasterix/classicube/profile/options.txt')
    old_options = profile.read_bytes() if profile.exists() else None
    old_post = json.loads(run([POST, '--status']))
    assert old_post['requested'] in (0, 1), 'Expected idle plain nearest/bilinear mode'
    assert old_post['snapshot_status'] == 0
    record = dict(passed=False, error=None, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  before=check_gpu(), post_before=old_post, cases=[], offline=[],
                  fsr_binary_sha256=sha(POST), source_size=[400, 240], display_size=[800, 480],
                  style=0, note='PL interpolation versus existing A53 FP32 four-thread FSR1; no FPGA FSR claim')
    try:
        for mode in ('nearest', 'bilinear', 'fsr1'):
            attempt = OUT.name + '_' + mode
            command = ['rix-classicube', '--seconds', '32', '--world-size', '64', '--view-distance', '32',
                       '--fps-limit', '120', '--autoplay', '--attempt', attempt]
            case = dict(mode=mode, command=command)
            game = None
            with (OUT / (mode + '-launcher.log')).open('x') as log:
                try:
                    env = os.environ.copy()
                    env['PYTHONDONTWRITEBYTECODE'] = '1'
                    game = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
                    game_log = Path('/tmp/postproc-tests') / attempt / 'game.log'
                    deadline = time.monotonic() + 50
                    while not game_log.exists() or 'RIX_MEASURE_BEGIN' not in game_log.read_text():
                        assert game.poll() is None and time.monotonic() < deadline, 'MC startup failed'
                        time.sleep(.1)
                    time.sleep(1)
                    if mode != 'fsr1':
                        run([POST, '--pl-mode', mode, '--style', '0'])
                    before = check_gpu()
                    started = time.monotonic()
                    if mode == 'fsr1':
                        text = run([POST, '--live', '--mode', 'fsr1', '--style', '0', '--seconds', '20'], timeout=35)
                        case['fsr_live'] = json_line(text)
                    else:
                        time.sleep(20)
                    elapsed = time.monotonic() - started
                    after = check_gpu()
                    case.update(before=before, after=after, source_window_seconds=elapsed,
                                source_frames=(after['presented'] - before['presented']) & 0xffffffff)
                    case['source_fps'] = case['source_frames'] / elapsed
                    case['new_output_fps'] = case['fsr_live']['processed_fps'] if mode == 'fsr1' else case['source_fps']
                    if mode == 'fsr1':
                        capture_pair(record)
                    game.wait(timeout=45)
                    case['game_exit'] = game.returncode
                    case['game_result'] = json.loads((game_log.parent / 'result.json').read_text())
                    assert game.returncode == 0 and case['game_result']['passed'], case
                    assert case['game_result']['world'], 'World identity missing'
                    record['cases'].append(case)
                    print('MC_FSR_CASE_DONE', mode, case['new_output_fps'], flush=True)
                finally:
                    if game is not None and game.poll() is None:
                        game.terminate()
                        game.wait(timeout=25)
        # Identical frozen input for CPU-only compute and byte-level host checks.
        for trial in range(3):
            for mode in ('nearest', 'bilinear', 'fsr1'):
                output = OUT / (mode + '.xrgb')
                stats = json_line(run([POST, '--mode', mode, '--input', str(OUT / 'source.rgb565'),
                                       '--output', str(output)], timeout=20))
                stats.update(trial=trial, output_sha256=sha(output))
                record['offline'].append(stats)
        record['offline_median_ms'] = {
            mode: 1000 * statistics.median(row['seconds'] for row in record['offline'] if row['algorithm'] == mode)
            for mode in ('nearest', 'bilinear', 'fsr1')}
        assert len({json.dumps(case['game_result']['world'], sort_keys=True) for case in record['cases']}) == 1, 'Different generated worlds'
        assert all(row['snapshot_retries'] == 0 for row in [record['cases'][-1]['fsr_live']])
        record['passed'] = True
    except Exception as exc:
        record['error'] = repr(exc)
        raise
    finally:
        # Restore only after the bounded game/postprocessor children have drained.
        assert not subprocess.run(['pidof', 'ClassiCube', 'rix-neural-style', 'rix-superres'],
                                  stdout=subprocess.PIPE).stdout, 'Client remained active'
        run([POST, '--pl-mode', 'bilinear' if old_post['requested'] == 1 else 'nearest', '--style', '0'])
        if old_options is not None:
            profile.write_bytes(old_options)
        record['after'] = check_gpu()
        record['post_after'] = json.loads(run([POST, '--status']))
        record['profile_restored'] = old_options is None or profile.read_bytes() == old_options
        record['passed'] = record['passed'] and record['profile_restored'] and record['post_after']['requested'] == old_post['requested']
        record['passed'] = record['passed'] and record['post_after']['snapshot_status'] == 0
        record['passed'] = record['passed'] and record['post_after']['snapshot_expirations'] == old_post['snapshot_expirations']
        (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
        archive = OUT.with_suffix('.tar.gz')
        assert not archive.exists()
        with tarfile.open(str(archive), 'w:gz') as tf:
            for name in ('result.json', 'source.rgb565', 'fsr-lcd.rgb565'):
                if (OUT / name).exists():
                    tf.add(str(OUT / name), arcname=name)
        print('MC_FSR_COMPARISON_RESULT', record['passed'], str(archive), sha(archive), flush=True)


def capture_pair(record):
    command = [POST, '--live', '--mode', 'fsr1', '--style', '0', '--seconds', '.001',
               '--source-output', str(OUT / 'source.rgb565'), '--output', str(OUT / 'fsr-live.xrgb'),
               '--hold-last-seconds', '10']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    captured = bytearray()
    try:
        deadline = time.monotonic() + 20
        while True:
            assert time.monotonic() < deadline and process.poll() is None, 'No held FSR output'
            if select.select([process.stdout], [], [], .1)[0]:
                captured.extend(os.read(process.stdout.fileno(), 8192))
                if b'FSR_OUTPUT_HELD_FOR_CAPTURE' in captured:
                    break
        run([POST, '--capture', str(OUT / 'fsr-lcd.rgb565')], timeout=8)
        raw = (OUT / 'fsr-live.xrgb').read_bytes()
        assert len(raw) == 1536000 and (OUT / 'source.rgb565').stat().st_size == 192000
        pixels = struct.unpack('<384000I', raw)
        expected = [((pixels[y * 8 * 800 + x * 8] >> 8) & 0xf800) |
                    ((pixels[y * 8 * 800 + x * 8] >> 5) & 0x7e0) |
                    ((pixels[y * 8 * 800 + x * 8] >> 3) & 0x1f) for y in range(60) for x in range(100)]
        actual = struct.unpack('<6000H', (OUT / 'fsr-lcd.rgb565').read_bytes())
        mismatches = sum(a != b for a, b in zip(actual, expected))
        record['pair'] = dict(source_sha256=sha(OUT / 'source.rgb565'), output_sha256=sha(OUT / 'fsr-live.xrgb'),
                              lcd_sha256=sha(OUT / 'fsr-lcd.rgb565'), lcd_samples=6000, mismatches=mismatches,
                              tool_log=captured.decode())
        assert mismatches == 0, record['pair']
    finally:
        if process.poll() is None:
            process.terminate()
        remaining, _ = process.communicate(timeout=10)
        record['pair_process_exit'] = process.returncode
        record['pair_process_tail'] = remaining.decode()
        assert process.returncode == 0, remaining


if __name__ == '__main__':
    main()
