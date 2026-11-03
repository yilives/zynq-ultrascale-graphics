#!/usr/bin/env python3
"""Check whether the CPU limiter starves otherwise-ready LCD frames."""
import json, subprocess
from pathlib import Path

out = Path('/tmp/postproc-tests'); records = []
for flat in (True, False):
    name = 'cc_perf_cap120_' + ('flat' if flat else 'terrain') + '_v10'
    command = ['rix-classicube', '--seconds', '18', '--capture', '--fps-limit', '120',
               '--world-size', '32' if flat else '64', '--view-distance', '32', '--attempt', name]
    command += ['--flat'] if flat else ['--autoplay']
    with Path('/tmp/' + name + '.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    data = json.loads((out / name / 'result.json').read_text()); records.append(data)
    assert result.returncode == 0 and data['passed']
    print('CLASSICUBE_CAP120_PERFORMANCE', name, data['hardware_window'], flush=True)
(out / 'cc_perf_cap120_v10.json').write_text(json.dumps(records, indent=2) + '\n')
print('CLASSICUBE_CAP120_PERFORMANCE_PASS', flush=True)
