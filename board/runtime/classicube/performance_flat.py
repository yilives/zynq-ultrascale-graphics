#!/usr/bin/env python3
"""Check light-load pacing separately from menu capture stalls."""
import json, subprocess
from pathlib import Path

out = Path('/tmp/postproc-tests')
records = []
for strategy in ('async', 'pipeline'):
    name = 'cc_perf_flat_' + strategy + '_v10'
    with Path('/tmp/' + name + '.log').open('w') as log:
        result = subprocess.run(['rix-classicube', '--flat', '--world-size', '32', '--seconds', '18',
                                 '--capture', '--fps-limit', '60', '--present-strategy', strategy, '--attempt', name],
                                stdout=log, stderr=subprocess.STDOUT)
    data = json.loads((out / name / 'result.json').read_text())
    records.append(data)
    assert result.returncode == 0 and data['passed']
    print('CLASSICUBE_FLAT_PERFORMANCE', strategy, data['hardware_window'], flush=True)
(out / 'cc_perf_flat_v10.json').write_text(json.dumps(records, indent=2) + '\n')
print('CLASSICUBE_FLAT_PERFORMANCE_PASS', flush=True)
