#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the optional one-command entry and orderly postprocess/game exit."""
import argparse
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--backend', choices=('cpu-int8', 'pl-int8'), default='cpu-int8')
a = p.parse_args()
out = Path('/tmp/postproc-tests')
out.mkdir(exist_ok=True)
def status():
    return json.loads(subprocess.check_output(['plgpuctl', 'status'], text=True))
result = {'backend': a.backend, 'runs': {}}
for mode, style in (('duration', 'anime'), ('signal', 'oil')):
    path = out / f'neural-cli-{a.backend}-{mode}.log'
    with path.open('w') as log:
        command = ['rix-neural-games', 'neverball', '--style', style, '--backend', a.backend, '--seconds', '16' if mode == 'duration' else '30', '--autoplay']
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        if mode == 'signal':
            deadline = time.monotonic() + 40
            while 'NEURAL_GAME_STARTED' not in path.read_text():
                assert process.poll() is None and time.monotonic() < deadline, path.read_text()
                time.sleep(0.2)
            time.sleep(3)
            process.terminate()  # wrapper handles SIGTERM; game gets WM_DELETE.
        code = process.wait(timeout=70)
    text = path.read_text()
    record = [json.loads(l.split(' ', 1)[1]) for l in text.splitlines() if l.startswith('NEURAL_GAME_RESULT ')][-1]
    result['runs'][mode] = {'exit': code, 'record': record,
                            'passed': code == 0 and record['game_exit'] == 0 and record['neural_exit'] == 0 and
                                      record['metrics']['processed_frames'] > 0 and record['error'] is None and record['stopped'] == (mode == 'signal')}
if not Path('/proc/device-tree/neural-style@a0030000/compatible').exists():
    before = status()
    process = subprocess.run(['rix-neural-games', 'neverball', '--seconds', '10'], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result['old_firmware_guard'] = process.returncode == 2 and 'NNS1' in process.stdout and status() == before
else:
    result['old_firmware_guard'] = None
result['after'] = status()
result['passed'] = all(r['passed'] for r in result['runs'].values()) and result['old_firmware_guard'] is not False and all(
    result['after'][k] == 0 for k in ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors'))
path = out / f'neural-cli-{a.backend}.json'
path.write_text(json.dumps(result, indent=2) + '\n')
print('NEURAL_CLI_QA', json.dumps(result), flush=True)
raise SystemExit(0 if result['passed'] else 1)
