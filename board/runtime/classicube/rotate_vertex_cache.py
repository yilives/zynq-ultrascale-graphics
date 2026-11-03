#!/usr/bin/env python3
"""Reclaim only verified ClassiCube backups already preserved on the host."""
import fcntl,hashlib,json,os,shutil,subprocess
from pathlib import Path
lock=open('/tmp/rasterix-game-launch.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert not subprocess.run(['pidof','ClassiCube'],stdout=subprocess.PIPE).stdout
archive=Path('/media/sd-mmcblk1p1/rasterix-classicube-cache-archive-20261021')
host=json.loads(Path('/tmp/cc_vertex_host_mirrors.json').read_text())
assert {r['sha256'][:12] for r in host}=={'241f6bd36065','b21cad39681b'}
for r in host:
    name='classicube-'+r['sha256'][:12]+'.tar.gz';path=archive/name
    assert path.resolve()==path and path.is_file() and not path.is_symlink()
    assert path.stat().st_size==r['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
    receipt=json.loads(path.with_name(name[:-7]+'.json').read_text());assert receipt['verified'] and receipt['sha256']==r['sha256']
    locator=path.with_name(name+'.host.json');assert not locator.exists()
    data=(json.dumps(r,indent=2)+'\n').encode()
    with locator.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    assert locator.read_bytes()==data
os.sync()
for r in host:
    path=archive/('classicube-'+r['sha256'][:12]+'.tar.gz')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256'];path.unlink()
os.sync()
cache=Path('/opt/rasterix/experimental/cache');source=cache/'classicube.tar.gz';meta=cache/'classicube.json'
receipt=json.loads(meta.read_text());digest=hashlib.sha256(source.read_bytes()).hexdigest()
assert receipt['verified'] and digest==receipt['sha256']=='24debcb0c0b68dd244b7a6223a14d9049e041b000f72ed57bfd508cb6eab7bc8'
assert source.resolve()==source
dest=archive/('classicube-'+digest[:12]+'.tar.gz');assert not dest.exists()
assert shutil.disk_usage(archive).free>source.stat().st_size+16*1024*1024
with dest.open('xb') as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
assert hashlib.sha256(dest.read_bytes()).hexdigest()==digest
metadata=dest.with_name(dest.name[:-7]+'.json');assert not metadata.exists()
with metadata.open('xb') as f:f.write(meta.read_bytes());f.flush();os.fsync(f.fileno())
assert metadata.read_bytes()==meta.read_bytes()
os.sync();source.unlink();meta.unlink();os.sync()
result={'passed':True,'host_mirrors':host,'previous_release_SD':str(dest),'previous_sha256':digest,
        'root_free_bytes':shutil.disk_usage('/').free,'SD_free_bytes':shutil.disk_usage(archive).free}
Path('/tmp/postproc-tests/cc_vertex_storage.json').write_text(json.dumps(result,indent=2)+'\n')
print('CLASSICUBE_VERTEX_STORAGE_PASS',result,flush=True)
