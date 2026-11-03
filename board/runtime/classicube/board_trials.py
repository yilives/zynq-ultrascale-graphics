#!/usr/bin/env python3
"""Sequential board trials through the same public command as an interactive run."""
import json, subprocess
from pathlib import Path

trials = [('cc_terrain32_v3', 32, 60, True), ('cc_terrain24_v3', 24, 60, True),
          ('cc_terrain16_v3', 16, 60, False), ('cc_terrain32_120_v3', 32, 120, False)]
results = []
for name, view, limit, capture in trials:
    command = ['rix-classicube', '--seconds', '18', '--world-size', '64', '--view-distance', str(view),
               '--fps-limit', str(limit), '--autoplay', '--attempt', name]
    if capture:
        command.append('--capture')
    with (Path('/tmp') / (name + '.log')).open('w') as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    result = json.loads((Path('/tmp/postproc-tests') / name / 'result.json').read_text())
    results.append(result)
    assert completed.returncode == 0 and result['passed'], result
    print('CLASSICUBE_TRIAL', name, result['hardware_window'], flush=True)
Path('/tmp/postproc-tests/cc_performance_v3.json').write_text(json.dumps(results, indent=2) + '\n')
print('CLASSICUBE_TRIALS_PASS', flush=True)
