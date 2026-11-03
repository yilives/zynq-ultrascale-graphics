#!/usr/bin/env python3
"""Move verified superseded neural runtime archives to the SD backup partition."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

src = Path('/opt/rasterix/experimental/cache')
dest = Path('/media/sd-mmcblk1p1/rasterix-neural-cache-archive-20261020')
assert os.geteuid() == 0 and src.resolve() == src and dest.resolve() == dest
mounts = [line.split() for line in Path('/proc/mounts').read_text().splitlines()]
assert any(m[0] == '/dev/mmcblk1p1' and m[1] == str(dest.parent) and 'rw' in m[3].split(',') for m in mounts)
archives = sorted(p for p in src.iterdir() if re.fullmatch(r'neural-style-[0-9a-f]{12}\.tar\.gz', p.name))
assert shutil.disk_usage(dest.parent).free > sum(p.stat().st_size for p in archives) + 16*1024*1024
dest.mkdir(exist_ok=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
record = []
for archive in archives:
    # PetaLinux Python 3.8: remove the explicit fixed suffix.
    receipt = archive.with_name(archive.name[:-7] + '.json')
    meta = json.loads(receipt.read_text())
    assert archive.is_file() and not archive.is_symlink() and receipt.is_file() and not receipt.is_symlink()
    assert meta['verified'] and sha(archive) == meta['sha256'] and archive.stat().st_size == meta['bytes']
    for path in (archive, receipt):
        target = dest / path.name
        assert not target.is_symlink()
        if not target.exists():
            with target.open('xb') as f:
                f.write(path.read_bytes()); f.flush(); os.fsync(f.fileno())
        assert sha(target) == sha(path)
    os.sync()
    archive.unlink(); receipt.unlink()
    record.append({'archive': archive.name, 'sha256': meta['sha256'], 'bytes': meta['bytes']})
os.sync()
print('NEURAL_OLD_CACHE_ARCHIVED', json.dumps({'destination': str(dest), 'files': record,
      'root_free': shutil.disk_usage(src).free}), flush=True)
