#!/usr/bin/env python3
"""Install only our verified additive runtime and official trial packages."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile

base = Path('/opt/rasterix/touhou')
base.mkdir(parents=True, exist_ok=True)
installed = {}
for name in ('th06-runtime', 'th06-demo'):
    cache = Path('/opt/rasterix/experimental/cache')
    archive = cache / (name + '.tar.gz')
    manifest = json.loads((cache / (name + '.json')).read_text())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert manifest.get('verified') and digest == manifest['sha256']
    with tarfile.open(archive) as source:
        for entry in source.getmembers():
            path = PurePosixPath(entry.name)
            assert path.parts[0] == name and not path.is_absolute() and '..' not in path.parts
            assert not entry.isdev() and not entry.isfifo() and not entry.islnk()
            if entry.issym():
                assert not PurePosixPath(entry.linkname).is_absolute() and '/' not in entry.linkname
        source.extractall(base)
    installed[name] = {'sha256': digest, 'bytes': archive.stat().st_size}
# Quarantine the three unused GLX files left by the first experimental install.
# Other games retain their own runtimes in their existing directories.
legacy = base / 'legacy-glx-unloaded'
for name in ('libGL.so', 'libGL.so.1', 'libGL.so.1.0'):
    old = base / 'th06-runtime/lib' / name
    if old.exists() or old.is_symlink():
        legacy.mkdir(exist_ok=True)
        target = legacy / name
        assert not target.exists() and not target.is_symlink(), 'Unexpected existing legacy GLX backup'
        old.rename(target)
(base / 'installed-packages.json').write_text(json.dumps(installed, indent=2) + '\n')
os.sync()
print('TH06_ADDITIVE_INSTALL_PASS=' + json.dumps(installed), flush=True)
