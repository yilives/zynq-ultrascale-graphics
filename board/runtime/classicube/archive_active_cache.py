#!/usr/bin/env python3
"""Archive the known v11 candidate before the capture-fence release replaces it."""
import fcntl, hashlib, json, os, shutil, subprocess
from pathlib import Path

lock = open('/tmp/rasterix-game-launch.lock', 'a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
assert not subprocess.run(['pidof', 'ClassiCube'], stdout=subprocess.PIPE).stdout
cache = Path('/opt/rasterix/experimental/cache')
source = cache / 'classicube.tar.gz'; meta = cache / 'classicube.json'
receipt = json.loads(meta.read_text()); digest = hashlib.sha256(source.read_bytes()).hexdigest()
assert receipt['verified'] and digest == receipt['sha256'] == '52895f4cf6278c0ef4d91edceaf6669259612de4dd72c3bd8eff17d1c329d4fd'
dest = Path('/media/sd-mmcblk1p1/rasterix-classicube-cache-archive-20261021') / ('classicube-' + digest[:12] + '.tar.gz')
assert source.resolve() == source and dest.resolve() == dest
if not dest.exists():
    assert shutil.disk_usage(dest.parent).free > source.stat().st_size + 16 * 1024 * 1024
    with dest.open('xb') as f:
        f.write(source.read_bytes()); f.flush(); os.fsync(f.fileno())
assert hashlib.sha256(dest.read_bytes()).hexdigest() == digest
saved_meta = dest.with_name(dest.name[:-7] + '.json')
if not saved_meta.exists():
    with saved_meta.open('xb') as f:
        f.write(meta.read_bytes()); f.flush(); os.fsync(f.fileno())
assert saved_meta.read_bytes() == meta.read_bytes()
os.sync(); source.unlink(); meta.unlink(); os.sync()
Path('/tmp/postproc-tests/cc_perf_v11_cache_storage.json').write_text(json.dumps(
    {'passed': True, 'archive': str(dest), 'sha256': digest}, indent=2) + '\n')
print('CLASSICUBE_V11_CACHE_ARCHIVED', digest, flush=True)
