#!/usr/bin/env python3
"""Preserve known superseded launchers on SD, verifying bytes before unlinking."""
import fcntl, gzip, hashlib, io, json, os, shutil, subprocess, tarfile
from pathlib import Path

lock = open('/tmp/rasterix-game-launch.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
assert not subprocess.run(['pidof', 'ClassiCube'], stdout=subprocess.PIPE).stdout
root = Path('/opt/rasterix/classicube')
names = ['rix-classicube-0010ac2846f1.py', 'rix-classicube-7b736321025b.py',
         'rix-classicube-97bec6dbb1ec.py']
payload = {}
for name in names:
    path = root / name
    assert path.resolve() == path and not path.is_symlink()
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest().startswith(name[len('rix-classicube-'):-3])
    payload[name] = data
buffer = io.BytesIO()
with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', mtime=0) as gz:
    with tarfile.open(fileobj=gz, mode='w') as tf:
        for name, data in payload.items():
            member = tarfile.TarInfo(name)
            member.size = len(data); member.mode = 0o644
            tf.addfile(member, io.BytesIO(data))
data = buffer.getvalue()
dest = Path('/media/sd-mmcblk1p1/rasterix-classicube-cache-archive-20261021/launchers-pre-performance.tar.gz')
assert dest.resolve() == dest and not dest.is_symlink()
if dest.exists():
    assert dest.read_bytes() == data
else:
    assert shutil.disk_usage(dest.parent).free > len(data) + 16 * 1024 * 1024
    with dest.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
with tarfile.open(dest) as tf:
    assert {m.name for m in tf.getmembers()} == set(names)
    assert all(tf.extractfile(name).read() == value for name, value in payload.items())
os.sync()
for name, value in payload.items():
    path = root / name
    assert path.read_bytes() == value
    path.unlink()
os.sync()
receipt = {'passed': True, 'archive': str(dest), 'bytes': len(data),
           'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
           'files': {n: hashlib.sha256(d).hexdigest() for n, d in payload.items()},
           'root_free_bytes': shutil.disk_usage('/').free}
Path('/tmp/postproc-tests/cc_perf_storage.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('CLASSICUBE_LAUNCHER_ARCHIVE_PASS', receipt, flush=True)
