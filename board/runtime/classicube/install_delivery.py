#!/usr/bin/env python3
"""Install review evidence only, verifying every written file before receipt."""
import hashlib, json, os, tarfile
from pathlib import Path

assert os.geteuid() == 0
archive = Path('/tmp/cc_delivery.tar.gz')
root = Path('/opt/rasterix/classicube/delivery-20261021')
assert root.resolve() == root and not root.is_symlink()
with tarfile.open(archive) as tf:
    manifest = json.load(tf.extractfile('manifest.json'))
    members = tf.getmembers()
    assert len(members) == len({m.name for m in members})
    assert {m.name for m in members} == set(manifest) | {'manifest.json'}
    for member in members:
        name = Path(member.name)
        assert member.isfile() and not name.is_absolute() and '..' not in name.parts
        target = root/name
        assert target.resolve() == target and root in target.parents
        data = tf.extractfile(member).read()
        if member.name in manifest:
            meta = manifest[member.name]
            assert len(data) == meta['bytes'] and hashlib.sha256(data).hexdigest() == meta['sha256']
        if target.exists():
            assert target.read_bytes() == data, 'Preserve existing delivery file'
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            target.chmod(0o644)
    assert all(hashlib.sha256((root/n).read_bytes()).hexdigest() == v['sha256'] for n,v in manifest.items())
os.sync()
receipt = {'passed':True,'root':str(root),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
           'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in manifest}}
Path('/tmp/postproc-tests/cc_delivery_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('CLASSICUBE_DELIVERY_INSTALLED',len(manifest),receipt['archive_sha256'],flush=True)
