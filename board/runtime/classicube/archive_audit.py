#!/usr/bin/env python3
"""Relocate the already-verified v4 audit tree to SD, preserving its public path."""
import hashlib,json,os,shutil
from pathlib import Path

root=Path('/opt/rasterix/classicube/delivery-20261021')
dest=Path('/media/sd-mmcblk1p1/rasterix-classicube-cache-archive-20261021/delivery-v4')
assert os.geteuid()==0 and not root.is_symlink() and root.resolve()==root
manifest=json.loads((root/'manifest.json').read_text())
files=set(manifest)|{'manifest.json'}
assert {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}==files
assert not any(p.is_symlink() for p in root.rglob('*'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(root/n)==v['sha256'] for n,v in manifest.items())
before=shutil.disk_usage(root).free
assert shutil.disk_usage(dest.parent).free>16*1024*1024+sum((root/n).stat().st_size for n in files)
dest.mkdir(exist_ok=False)
for name in files:
    src=root/name;dst=dest/name;dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open('xb') as f:f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
assert all(sha(root/n)==sha(dest/n) for n in files)
os.sync()
# Remove only the exact manifest-verified files, then empty directories.
for name in files:(root/name).unlink()
for directory in sorted((p for p in root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
root.rmdir();root.symlink_to(dest)
os.sync()
assert all(sha(root/n)==v['sha256'] for n,v in manifest.items())
record={'passed':True,'root':str(root),'archive':str(dest),'files':len(files),
        'free_before':before,'free_after':shutil.disk_usage(root.parent).free}
out=Path('/tmp/postproc-tests/cc_keyboard_storage.json');out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(record,indent=2)+'\n')
print('CLASSICUBE_AUDIT_RELOCATED',json.dumps(record),flush=True)
