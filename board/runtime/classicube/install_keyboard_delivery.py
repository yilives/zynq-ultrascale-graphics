#!/usr/bin/env python3
"""Store the new audit on SD and preserve a stable link from the installed port."""
import hashlib,json,os,shutil,tarfile
from pathlib import Path
archive=Path('/tmp/cc_keyboard_delivery.tar.gz')
dest=Path('/media/sd-mmcblk1p1/rasterix-classicube-keyboard-20261021')
link=Path('/opt/rasterix/classicube/keyboard-delivery-20261021')
assert os.geteuid()==0 and dest.resolve()==dest and not dest.is_symlink()
with tarfile.open(archive) as tf:
    manifest=json.load(tf.extractfile('manifest.json'));members=tf.getmembers()
    assert len(members)==len({m.name for m in members})
    assert {m.name for m in members}==set(manifest)|{'manifest.json'}
    assert shutil.disk_usage(dest.parent).free>16*1024*1024+sum(m.size for m in members)
    for m in members:
        name=Path(m.name);assert m.isfile() and not name.is_absolute() and '..' not in name.parts
        target=dest/name;assert target.resolve()==target and dest in target.parents
        data=tf.extractfile(m).read()
        if m.name in manifest:assert len(data)==manifest[m.name]['bytes'] and hashlib.sha256(data).hexdigest()==manifest[m.name]['sha256']
        if target.exists():assert target.read_bytes()==data,'Preserve existing evidence'
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            target.chmod(0o644)
    assert all(hashlib.sha256((dest/n).read_bytes()).hexdigest()==v['sha256'] for n,v in manifest.items())
if link.is_symlink():assert link.resolve()==dest
elif link.exists():raise RuntimeError('Unrelated evidence path exists')
else:link.symlink_to(dest)
os.sync()
receipt={'passed':True,'root':str(link),'SD':str(dest),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
         'files':{n:hashlib.sha256((dest/n).read_bytes()).hexdigest() for n in manifest}}
Path('/tmp/postproc-tests/cc_keyboard_delivery_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('CLASSICUBE_KEYBOARD_DELIVERY_PASS',len(manifest),receipt['archive_sha256'],flush=True)
