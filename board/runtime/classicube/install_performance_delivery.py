#!/usr/bin/env python3
"""Preserve the performance audit on SD, with fsync and complete SHA readback."""
import hashlib, json, os, shutil, sys, tarfile
from pathlib import Path

kind=sys.argv[1] if len(sys.argv)>1 else 'performance'
assert kind in ('performance','vertex')
archive = Path('/tmp/cc_'+kind+'_delivery.tar.gz')
dest = Path('/media/sd-mmcblk1p1/rasterix-classicube-'+kind+'-20261021.tar.gz')
link = Path('/opt/rasterix/classicube/'+kind+'-delivery-20261021.tar.gz')
assert os.geteuid() == 0 and dest.resolve() == dest and not dest.is_symlink()
with tarfile.open(archive) as tf:
    members = tf.getmembers(); manifest = json.load(tf.extractfile('manifest.json'))
    assert len(members) == len({m.name for m in members})
    assert {m.name for m in members} == set(manifest) | {'manifest.json'}
    for member in members:
        name = Path(member.name)
        assert member.isfile() and not name.is_absolute() and '..' not in name.parts
        data = tf.extractfile(member).read()
        if member.name in manifest:
            assert len(data) == manifest[member.name]['bytes'] and hashlib.sha256(data).hexdigest() == manifest[member.name]['sha256']
data = archive.read_bytes()
if dest.exists():
    assert dest.read_bytes() == data, 'Preserve existing evidence'
else:
    assert shutil.disk_usage(dest.parent).free > 16 * 1024 * 1024 + len(data) + 8192
    with dest.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    dest.chmod(0o644)
assert dest.read_bytes() == data
with tarfile.open(dest) as tf:
    readback = {n: hashlib.sha256(tf.extractfile(n).read()).hexdigest() for n in manifest}
assert all(readback[n] == v['sha256'] for n, v in manifest.items())
if link.is_symlink():
    assert link.resolve() == dest
elif link.exists():
    raise RuntimeError('Unrelated evidence path exists')
else:
    link.symlink_to(dest)
os.sync()
receipt = {'passed': True, 'root': str(link), 'SD': str(dest),
           'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
           'files': readback}
Path('/tmp/postproc-tests/cc_'+('perf' if kind=='performance' else kind)+'_delivery_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('CLASSICUBE_'+kind.upper()+'_DELIVERY_PASS', len(manifest), receipt['archive_sha256'], flush=True)
