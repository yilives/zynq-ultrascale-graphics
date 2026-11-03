#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tarfile

p = argparse.ArgumentParser()
p.add_argument('attempt')
a = p.parse_args()
assert a.attempt.replace('_', '').isalnum()
root = Path('/tmp/postproc-tests') / a.attempt
record = json.loads((root / 'result.json').read_text())
for style in ('oil', 'anime'):
    display = (root / f'{style}.display.bin').read_bytes()
    capture = (root / f'{style}.lcd.bin').read_bytes()
    assert len(display) == 1536000 and len(capture) == 12000
    expected = []
    for y in range(0, 480, 8):
        for x in range(0, 800, 8):
            v = struct.unpack_from('<I', display, (y * 800 + x) * 4)[0]
            expected.append(((v >> 8) & 0xf800) | ((v >> 5) & 0x7e0) | ((v >> 3) & 0x1f))
    actual = struct.unpack('<6000H', capture)
    mismatch = sum(a != b for a, b in zip(actual, expected))
    record['runs'][style]['lcd'] = {'pixels': 6000, 'mismatches': mismatch, 'passed': mismatch == 0,
                                   'display_sha256': hashlib.sha256(display).hexdigest(),
                                   'lcd_sha256': hashlib.sha256(capture).hexdigest()}
record['passed'] = record.get('passed_board', False) and all(r['lcd']['passed'] for r in record['runs'].values())
(root / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
archive = root.with_suffix('.compact.tar.gz')
with tarfile.open(archive, 'w:gz') as tf:
    for item in sorted(root.iterdir()):
        if item.is_file() and not item.name.endswith(('.display.bin', '.cpu.bin')):
            tf.add(item, arcname=item.name)
assert archive.stat().st_size < 1536000
print('NEURAL_COMPACT_EVIDENCE', archive, archive.stat().st_size, hashlib.sha256(archive.read_bytes()).hexdigest(), json.dumps(record), flush=True)
raise SystemExit(0 if record['passed'] else 1)
