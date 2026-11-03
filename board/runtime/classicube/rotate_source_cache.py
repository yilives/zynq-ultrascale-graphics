#!/usr/bin/env python3
"""Retain verified old candidates on the host/SD before replacing the active cache."""
import fcntl, hashlib, json, os, shutil, subprocess
from pathlib import Path

lock = open('/tmp/rasterix-game-launch.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
assert not subprocess.run(['pidof', 'ClassiCube'], stdout=subprocess.PIPE).stdout
archive = Path('/media/sd-mmcblk1p1/rasterix-classicube-cache-archive-20261021')
host = json.loads(Path('/tmp/cc_perf_source_host_mirror.json').read_text())
assert len(host) == 1
for record in host:
    digest = record['sha256']; name = 'classicube-' + digest[:12] + '.tar.gz'
    path = archive / name
    assert path.resolve() == path and not path.is_symlink()
    assert path.stat().st_size == record['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    receipt = json.loads(path.with_name(name[:-7] + '.json').read_text())
    assert receipt['verified'] and receipt['sha256'] == digest
    locator = path.with_name(name + '.host.json')
    data = (json.dumps(record, indent=2) + '\n').encode()
    if locator.exists():
        assert locator.read_bytes() == data
    else:
        with locator.open('xb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
    assert locator.read_bytes() == data
os.sync()
for record in host:
    path = archive / ('classicube-' + record['sha256'][:12] + '.tar.gz')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    path.unlink()
os.sync()
cache = Path('/opt/rasterix/experimental/cache')
source = cache / 'classicube.tar.gz'; meta = cache / 'classicube.json'
receipt = json.loads(meta.read_text()); digest = hashlib.sha256(source.read_bytes()).hexdigest()
assert receipt['verified'] and digest == '241f6bd36065b7579b497fd300a22957b8c5646fa51f4c0ec993b500d0d57a95'
assert receipt['sha256'] == digest and source.resolve() == source
dest = archive / ('classicube-' + digest[:12] + '.tar.gz')
if not dest.exists():
    assert shutil.disk_usage(archive).free > source.stat().st_size + 16 * 1024 * 1024
    with dest.open('xb') as f:
        f.write(source.read_bytes()); f.flush(); os.fsync(f.fileno())
assert hashlib.sha256(dest.read_bytes()).hexdigest() == digest
metadata = dest.with_name(dest.name[:-7] + '.json')
if metadata.exists():
    assert metadata.read_bytes() == meta.read_bytes()
else:
    with metadata.open('xb') as f:
        f.write(meta.read_bytes()); f.flush(); os.fsync(f.fileno())
assert metadata.read_bytes() == meta.read_bytes()
os.sync(); source.unlink(); meta.unlink(); os.sync()
result = {'passed': True, 'host_mirrors': host, 'candidate_archived_SD': str(dest),
          'candidate_sha256': digest, 'root_free_bytes': shutil.disk_usage('/').free,
          'SD_free_bytes': shutil.disk_usage(archive).free}
Path('/tmp/postproc-tests/cc_perf_source_cache_storage.json').write_text(json.dumps(result, indent=2) + '\n')
print('CLASSICUBE_PERFORMANCE_CACHE_ROTATION_PASS', result, flush=True)
