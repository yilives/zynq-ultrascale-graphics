"""Receive checked JTAG blocks from unused no-map GPU memory into additive SD cache."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import struct
import subprocess

BASE = Path('/opt/rasterix/experimental/cache')
ALLOWED = ('quake-data', 'quake3-data', 'neverball-data', 'game-runtime', 'postproc-touch', 'th06-runtime', 'th06-demo', 'neural-boot', 'neural-style','classicube')
p = argparse.ArgumentParser()
p.add_argument('operation', choices=('begin', 'chunk', 'finish'))
p.add_argument('name', choices=ALLOWED)
p.add_argument('numbers', nargs='*')
a = p.parse_args()
assert os.geteuid() == 0
assert BASE.resolve() == BASE
BASE.mkdir(parents=True, exist_ok=True)
part = BASE / (a.name + '.tar.gz.part')
final = BASE / (a.name + '.tar.gz')
manifest = BASE / (a.name + '.json')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def idle():
    result = subprocess.run(['pidof', 'tuxracer', 'rix-smoke', 'neverball', 'neverputt', 'quake3e', 'quakespasm', 'rix-glx-probe', 'rix-danmaku', 'rix-superres', 'rix-neural-style', 'th06-rix', 'ClassiCube'], stdout=subprocess.PIPE)
    assert result.returncode == 1 and not result.stdout, 'GPU client active'
    node = Path('/proc/device-tree/reserved-memory/graphics@60000000')
    assert struct.unpack('>4I', (node / 'reg').read_bytes()) == (0, 0x60000000, 0, 0x2000000)
    assert (node / 'no-map').exists()
    status = json.loads(subprocess.check_output(['plgpuctl', 'status']).decode())
    assert status['config'] == 0x9adb505e and status['status'] == 3


if a.operation == 'begin':
    total, sha = int(a.numbers[0]), a.numbers[1]
    assert 0 < total < 100 * 1024 * 1024 and len(sha) == 64
    if final.exists():
        old = json.loads(manifest.read_text())
        actual = digest(final)
        assert actual == old['sha256'], 'Existing cache differs from its verified manifest'
        if final.stat().st_size == total and actual == sha:
            print('RIX_PORT_CACHE_COMPLETE', total, flush=True)
            raise SystemExit(0)
        # Reject insufficient space before moving the active cache away.
        assert not part.exists(), 'Unexpected partial upload beside active cache'
        assert shutil.disk_usage(BASE).free > total + 32 * 1024 * 1024
        idle()
        saved = BASE / (a.name + '-' + actual[:12] + '.tar.gz')
        assert not saved.exists()
        os.replace(final, saved)
        os.replace(manifest, BASE / (a.name + '-' + actual[:12] + '.json'))
    if not final.exists():
        idle()
        current = part.stat().st_size if part.exists() else 0
        assert current <= total
        if manifest.exists():
            previous = json.loads(manifest.read_text())
            assert previous['sha256'] == sha and previous['bytes'] == total
        assert shutil.disk_usage(BASE).free > total - current + 32 * 1024 * 1024
        manifest.write_text(json.dumps({'bytes': total, 'sha256': sha, 'method': 'JTAG no-map GPU resource staging, per-block SHA256 and full-file SHA256'}) + '\n')
        if not part.exists():
            part.touch(exist_ok=False)
        print('RIX_PORT_CACHE_OFFSET', current, flush=True)
elif a.operation == 'chunk':
    idle()
    offset, length, expected = int(a.numbers[0]), int(a.numbers[1]), a.numbers[2]
    assert 0 < length <= 2 * 1024 * 1024 and offset == part.stat().st_size
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, (length + 4095) // 4096 * 4096, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ, offset=0x60800000) as mem:
            # /dev/mem maps no-map RAM as Device memory on this BSP. Keep the
            # libc memcpy against that mapping aligned; trim only after copying
            # into ordinary process RAM to avoid an unaligned tail bus fault.
            data = mem[:(length + 63) // 64 * 64][:length]
    finally:
        os.close(fd)
    assert hashlib.sha256(data).hexdigest() == expected, 'JTAG block hash differs'
    with part.open('ab') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    print('RIX_PORT_CHUNK_ACK', offset + length, flush=True)
else:
    record = json.loads(manifest.read_text())
    assert part.stat().st_size == record['bytes'] and digest(part) == record['sha256']
    os.replace(part, final)
    record['verified'] = True
    manifest.write_text(json.dumps(record) + '\n')
    os.sync()
    print('RIX_PORT_FILE_SHA256_PASS', record['sha256'], flush=True)
