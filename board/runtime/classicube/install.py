#!/usr/bin/env python3
"""Install only the additive launcher; large binaries run from verified tmpfs."""
import hashlib,json,os,subprocess,tarfile,shutil
from pathlib import Path
assert os.geteuid()==0
assert not subprocess.run(['pidof','ClassiCube'],stdout=subprocess.PIPE).stdout
cache=Path('/opt/rasterix/experimental/cache')
record=json.loads((cache/'classicube.json').read_text())
archive=cache/'classicube.tar.gz'
assert record['verified'] and hashlib.sha256(archive.read_bytes()).hexdigest()==record['sha256']
with tarfile.open(archive) as tf:
    manifest=json.load(tf.extractfile('classicube/manifest.json'))
    payload={n:tf.extractfile('classicube/'+n).read() for n in manifest}
assert all(len(payload[n])==v['bytes'] and hashlib.sha256(payload[n]).hexdigest()==v['sha256'] for n,v in manifest.items())
root=Path('/opt/rasterix/classicube');assert root.resolve()==root
root.mkdir(exist_ok=True)
target=root/'rix-classicube';assert not target.is_symlink()
if target.exists() and target.read_bytes()!=payload['bin/rix-classicube']:
    old=root/('rix-classicube-'+hashlib.sha256(target.read_bytes()).hexdigest()[:12]+'.py')
    if not old.exists():old.write_bytes(target.read_bytes())
temp=root/'rix-classicube.incoming';assert not temp.is_symlink()
with temp.open('wb') as f:f.write(payload['bin/rix-classicube']);f.flush();os.fsync(f.fileno())
temp.chmod(0o755);temp.replace(target)
if 'bin/rix_capture_source.py' in payload:
    helper=root/'rix_capture_source.py';assert not helper.is_symlink()
    if helper.exists():assert helper.read_bytes()==payload['bin/rix_capture_source.py'],'Preserve unrelated capture helper'
    incoming=helper.with_suffix('.py.incoming');assert not incoming.is_symlink()
    with incoming.open('wb') as f:f.write(payload['bin/rix_capture_source.py']);f.flush();os.fsync(f.fileno())
    incoming.chmod(0o644);incoming.replace(helper)
link=Path('/usr/bin/rix-classicube')
if link.is_symlink():assert link.resolve()==target
elif link.exists():raise RuntimeError('Unrelated command already exists')
else:link.symlink_to(target)
(root/'sources.json').write_bytes(payload['sources.json'])
(root/'LICENSE-ClassiCube.txt').write_bytes(payload['licenses/ClassiCube.txt'])
# Keep superseded ClassiCube upload archives on SD after validating receipts.
saved_dir=Path('/media/sd-mmcblk1p1/rasterix-classicube-cache-archive-20261021')
saved_dir.mkdir(exist_ok=True)
for old in cache.glob('classicube-*.tar.gz'):
    assert old.resolve()==old and not old.is_symlink()
    receipt=old.with_name(old.name[:-7]+'.json')
    metadata=json.loads(receipt.read_text())
    digest=hashlib.sha256(old.read_bytes()).hexdigest()
    assert metadata['verified'] and metadata['sha256']==digest
    dst=saved_dir/old.name
    if not dst.exists():
        assert shutil.disk_usage(saved_dir).free>old.stat().st_size+16*1024*1024
        with dst.open('xb') as f:f.write(old.read_bytes());f.flush();os.fsync(f.fileno())
    assert hashlib.sha256(dst.read_bytes()).hexdigest()==digest
    meta_saved=saved_dir/receipt.name
    if not meta_saved.exists():meta_saved.write_bytes(receipt.read_bytes())
    assert meta_saved.read_bytes()==receipt.read_bytes()
    os.sync();old.unlink();receipt.unlink()
os.sync()
print('CLASSICUBE_LAUNCHER_INSTALLED',hashlib.sha256(target.read_bytes()).hexdigest(),flush=True)
