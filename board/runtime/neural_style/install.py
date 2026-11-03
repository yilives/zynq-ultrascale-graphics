#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import hashlib
import json
import os
from pathlib import Path
import tarfile

assert os.geteuid() == 0
target = Path('/opt/rasterix/neural-style')
assert target.resolve() == target
with tarfile.open('/tmp/neural-style.tar.gz') as tf:
    members = tf.getmembers()
    names = [m.name for m in members]
    assert len(names) == len(set(names))
    for m in members:
        p = Path(m.name)
        assert m.isfile() and p.parts[0] == 'neural-style' and '..' not in p.parts and len(p.parts) <= 3
    manifest = json.load(tf.extractfile('neural-style/manifest.json'))
    assert set(names) == {'neural-style/' + k for k in manifest} | {'neural-style/manifest.json'}
    for name, meta in manifest.items():
        data = tf.extractfile('neural-style/' + name).read()
        assert len(data) == meta['bytes'] and hashlib.sha256(data).hexdigest() == meta['sha256']
    target.mkdir(parents=True, exist_ok=True)
    for m in members:
        p = target / Path(*Path(m.name).parts[1:])
        assert not p.is_symlink() and not p.parent.is_symlink()
        p.parent.mkdir(parents=True, exist_ok=True)
        temp = p.with_name(p.name + '.incoming')
        temp.write_bytes(tf.extractfile(m).read())
        temp.chmod(0o755 if p.parent.name == 'bin' else 0o644)
        temp.replace(p)
command = Path('/usr/bin/rix-neural-games')
expected = target / 'bin/rix-neural-games'
if command.is_symlink():
    assert command.resolve() == expected
elif command.exists():
    raise RuntimeError('Refuse to replace an unrelated rix-neural-games command')
else:
    command.symlink_to(expected)
os.sync()
print('NEURAL_STYLE_EXPERIMENT_INSTALLED', json.dumps(manifest))
