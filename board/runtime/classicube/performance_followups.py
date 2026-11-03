#!/usr/bin/env python3
"""After the ABBA timing run, validate default async input, reload and shutdown."""
import json, subprocess, time
from pathlib import Path

out = Path('/tmp/postproc-tests')
until = time.monotonic() + 400
matrix = out / 'cc_perf_validate_v15.json'
while not matrix.exists() or len(json.loads(matrix.read_text())) != 2:
    assert time.monotonic() < until, 'Long comparison did not finish'
    time.sleep(.5)
assert all(v['passed'] for v in json.loads(matrix.read_text()))
subprocess.run(['python3', '/tmp/cc_performance_capture_stress.py'], check=True)
subprocess.run(['python3', '/tmp/cc_x11_input_qa.py', 'cc_perf_input_v15'], check=True)
qa = json.loads((out / 'cc_perf_input_v15/input-qa.json').read_text())
session = json.loads((out / 'cc_perf_input_v15/result.json').read_text())
assert qa['passed'] and session['presentation_strategy'] == 'async'
profile = Path('/opt/rasterix/classicube/profile/options.txt')
def options():
    return dict(s.split('=', 1) for s in profile.read_text().splitlines() if '=' in s)
physics = options().get('singleplayerphysics', 'True')
values = options(); values['singleplayerphysics'] = 'False'
profile.write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
try:
    subprocess.run(['rix-classicube', '--map', '/opt/rasterix/classicube/profile/maps/ccperfinputv15.cw',
                    '--seconds', '10', '--capture', '--attempt', 'cc_perf_reload_v15'], check=True)
finally:
    values = options(); values['singleplayerphysics'] = physics
    profile.write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
name = 'cc_perf_early_v15'
with Path('/tmp/' + name + '.log').open('w') as log:
    child = subprocess.Popen(['rix-classicube', '--world-size', '32', '--flat', '--input-qa',
                              '--attempt', name], stdout=log, stderr=subprocess.STDOUT)
    until = time.monotonic() + 30
    while not (out / name / 'input.json').exists():
        assert child.poll() is None and time.monotonic() < until
        time.sleep(.02)
    child.terminate(); assert child.wait(timeout=20) == 0
early = json.loads((out / name / 'result.json').read_text())
assert early['passed'] and early['metrics']['seconds'] < 2
subprocess.run(['rix-games', 'glx-probe', '--seconds', '8', '--attempt', 'cc_perf_legacy_v15'], check=True)
legacy = json.loads((out / 'games-cc_perf_legacy_v15.json').read_text())
assert legacy['passed'] and legacy['all_errors_zero'] and not legacy['transport_errors']
records = {'input': session, 'reload': json.loads((out / 'cc_perf_reload_v15/result.json').read_text()),
           'early': early, 'legacy': legacy}
subprocess.run(['python3', '/tmp/cc_collect_state.py'], check=True)
(out / 'cc_perf_followups_v15.json').write_text(json.dumps(records, indent=2) + '\n')
print('CLASSICUBE_PERFORMANCE_FOLLOWUPS_PASS', flush=True)
