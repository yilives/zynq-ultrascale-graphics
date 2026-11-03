#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Same board/model/tensor, alternate serialized/phase-barrier PIO timings."""
import hashlib
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import time

root = Path('/opt/rasterix/neural-style')
p = argparse.ArgumentParser()
p.add_argument('--current-only', action='store_true')
a = p.parse_args()
engine_version = 2 if (Path('/proc/device-tree/neural-style@a0030000/compatible').read_bytes() == b'rasterix,cnn-int8-v2\0') else 1
current_only = a.current_only or engine_version == 2
record = {'scope': 'idle GPU; fixed tensor; inference includes PIO and FPGA compute, excludes model loading',
          'engine_version': engine_version, 'current_only': current_only, 'styles': {}}
for style in ('oil', 'anime'):
    samples = {'phase_barrier': []} if current_only else {'serialized': [], 'phase_barrier': []}
    expected = (root / f'tests/{style}-full-output.bin').read_bytes()
    for repetition in range(6):
        order = ('phase_barrier',) if current_only else (('serialized', 'phase_barrier') if repetition % 2 == 0 else ('phase_barrier', 'serialized'))
        for version in order:
            exe = 'rix-neural-style-serialized' if version == 'serialized' else 'rix-neural-style'
            target = Path('/tmp') / f'neural-bench-{style}-{version}.bin'
            command = [str(root / 'bin' / exe), '--backend', 'pl-int8', '--model', str(root / f'models/{style}.cnn'),
                       '--input', str(root / f'tests/{style}-full-input.bin'), '--output', str(target)]
            start = time.monotonic()
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
            assert result.returncode == 0, result.stdout
            metrics = json.loads(result.stdout)
            assert metrics['backend'] == 'pl-int8' and metrics['cnn_cycles'] == (414738 if engine_version == 2 else 1843200)
            assert target.read_bytes() == expected, 'PIO changed tensor values'
            metrics['seconds_process'] = time.monotonic() - start
            if repetition:
                samples[version].append(metrics)
    medians = {v: statistics.median(r['seconds'] for r in runs) for v, runs in samples.items()}
    record['styles'][style] = {'samples': samples, 'median_inference_seconds': medians,
                               'speed_ratio': None if current_only else medians['serialized'] / medians['phase_barrier'],
                               'output_sha256': hashlib.sha256(expected).hexdigest(), 'bit_exact': True}
record['passed'] = True
Path('/tmp/postproc-tests/neural-pio-benchmark.json').write_text(json.dumps(record, indent=2) + '\n')
print('NEURAL_PIO_BENCHMARK', json.dumps(record), flush=True)
