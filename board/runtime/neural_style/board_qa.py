#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--backend', choices=('cpu-int8', 'pl-int8'), default='cpu-int8')
a = p.parse_args()
root = Path('/opt/rasterix/neural-style')
results = {}
for style in ('oil', 'anime'):
    for size in (('small', 'full') if a.backend == 'cpu-int8' else ('full',)):
        width, height = (7, 5) if size == 'small' else (160, 96)
        out = Path('/tmp') / f'neural-{style}-{size}-{a.backend}.bin'
        cmd = [str(root / 'bin/rix-neural-style'), '--backend', a.backend, '--model', str(root / f'models/{style}.cnn'),
               '--input', str(root / f'tests/{style}-{size}-input.bin'), '--output', str(out),
               '--width', str(width), '--height', str(height)]
        start = time.monotonic()
        process = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        expected = (root / f'tests/{style}-{size}-output.bin').read_bytes()
        actual = out.read_bytes() if out.exists() else b''
        results[f'{style}-{size}'] = {'exit': process.returncode, 'seconds_wall': time.monotonic() - start,
                                    'stdout': process.stdout, 'bytes': len(actual),
                                    'sha256': hashlib.sha256(actual).hexdigest(),
                                    'bit_exact': actual == expected}
if a.backend == 'cpu-int8' and not Path('/proc/device-tree/neural-style@a0030000').exists():
    # On the old deployed FPGA, this must refuse BEFORE probing its new address.
    result = subprocess.run([str(root / 'bin/rix-neural-style'), '--backend', 'pl-int8', '--model', str(root / 'models/oil.cnn')],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
    guard = result.returncode != 0 and 'refusing to probe' in result.stdout
else:
    guard = None
record = {'backend': a.backend, 'runs': results, 'old_firmware_probe_guard': guard,
          'passed': all(r['exit'] == 0 and r['bit_exact'] for r in results.values()) and guard is not False}
path = Path('/tmp') / f'neural-qa-{a.backend}.json'
path.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
raise SystemExit(0 if record['passed'] else 1)
