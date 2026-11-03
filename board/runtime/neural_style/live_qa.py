#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actual game -> leased source -> neural inference -> LCD sampling evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

p = argparse.ArgumentParser()
p.add_argument('--backend', choices=('cpu-int8', 'pl-int8'), required=True)
p.add_argument('--attempt', required=True)
p.add_argument('--executable', type=Path, default=Path('/opt/rasterix/neural-style/bin/rix-neural-style'))
p.add_argument('--require-display-readback', action='store_true')
p.add_argument('--require-pl-scale5', action='store_true')
a = p.parse_args()
assert a.attempt.replace('_', '').isalnum() and len(a.attempt) < 40
root = Path('/opt/rasterix/neural-style')
out = Path('/tmp/postproc-tests') / a.attempt
out.mkdir(parents=True, exist_ok=False)
def status():
    return json.loads(subprocess.check_output(['plgpuctl', 'status'], text=True))
before = status()
record = {'backend': a.backend, 'attempt': a.attempt, 'executable': str(a.executable),
          'executable_sha256': hashlib.sha256(a.executable.read_bytes()).hexdigest(), 'before': before, 'runs': {}}
game_log = open(out / 'game.log', 'w')
game = subprocess.Popen(['rix-games', 'neverball', '--seconds', '60', '--attempt', a.attempt, '--autoplay'], stdout=game_log, stderr=subprocess.STDOUT)
try:
    deadline = time.monotonic() + 45
    while status()['presented'] < before['presented'] + 3:
        if game.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Game produced no source frames; inspect game.log')
        time.sleep(0.2)
    for style in ('oil', 'anime'):
        prefix = out / style
        with open(out / f'{style}.log', 'w') as log:
            command = [str(a.executable), '--backend', a.backend, '--model', str(root / f'models/{style}.cnn'),
                       '--live', '--seconds', '6', '--hold-last-seconds', '30', '--dump-prefix', str(prefix)]
            nn = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 45
                while 'NEURAL_OUTPUT_HELD' not in (out / f'{style}.log').read_text():
                    if nn.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f'{style} failed before hold: {(out / (style + ".log")).read_text()}')
                    time.sleep(0.1)
                time.sleep(0.1)
                subprocess.run(['/opt/rasterix/postproc-touch/bin/rix-superres', '--capture', str(prefix) + '.lcd.bin'], check=True)
                post = json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres', '--status'], text=True))
                cpu = subprocess.run([str(root / 'bin/rix-neural-style'), '--model', str(root / f'models/{style}.cnn'), '--backend', 'cpu-int8',
                                      '--input', str(prefix) + '.input.bin', '--output', str(prefix) + '.cpu.bin'],
                                     text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
                actual = Path(str(prefix) + '.output.bin').read_bytes()
                cpu_data = Path(str(prefix) + '.cpu.bin').read_bytes()
                log_lines = (out / f'{style}.log').read_text().splitlines()
                metrics = [json.loads(line) for line in log_lines if line.startswith('{')][-1]
                record['runs'][style] = {'metrics': metrics, 'post': post, 'cpu_exit': cpu.returncode,
                                          'display_full_readback': ('NEURAL_DISPLAY_READBACK_PASS bytes=' + str(metrics.get('display_write_bytes', 1536000))) in '\n'.join(log_lines),
                                          'cpu_comparison_bit_exact': actual == cpu_data,
                                          'output_sha256': hashlib.sha256(actual).hexdigest(),
                                          'models_sha256': hashlib.sha256((root / f'models/{style}.cnn').read_bytes()).hexdigest()}
            finally:
                if nn.poll() is None:
                    nn.terminate()
                nn.wait(timeout=10)
                if nn.returncode != 0:
                    raise RuntimeError(f'Neural process did not exit cleanly: {nn.returncode}')
        print('NEURAL_LIVE_STYLE_DONE', style, json.dumps(record['runs'][style]), flush=True)
    record['game_exit'] = game.wait(timeout=80)
    game_log.close()
    game_result = Path('/tmp/rasterix-games/results') / a.attempt / 'result.json'
    if game_result.exists():
        record['game_result'] = json.loads(game_result.read_text())
    record['after'] = status()
    errors = ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')
    record['passed_board'] = record['game_exit'] == 0 and all(record['after'][k] == before[k] == 0 for k in errors) and all(
        r['cpu_exit'] == 0 and r['cpu_comparison_bit_exact'] and r['metrics']['processed_frames'] > 0 and
        (not a.require_display_readback or r['display_full_readback']) and (r['post']['snapshot_status'] & 3) == 0 and
        r['post']['snapshot_expirations'] == 0 and
        (not a.require_pl_scale5 or r['metrics'].get('display_backend') == 'pl-bilinear-5x') and
        (r['post']['active'] & 0x33) == (3 if r['metrics'].get('display_backend') == 'pl-bilinear-5x' else 2)
        for r in record['runs'].values())
finally:
    # Let the public launcher perform its normal WM_DELETE shutdown. Do not
    # kill a GPU process or reset its DMA while a command might be in flight.
    record['game_still_running'] = game.poll() is None
    (out / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    with tarfile.open(out.with_suffix('.tar.gz'), 'w:gz') as tf:
        for item in sorted(out.iterdir()):
            if item.is_file():
                tf.add(item, arcname=item.name)
    print('NEURAL_LIVE_EVIDENCE', str(out.with_suffix('.tar.gz')), json.dumps(record), flush=True)
raise SystemExit(0 if record.get('passed_board') else 1)
