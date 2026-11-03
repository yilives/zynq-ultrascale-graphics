#!/usr/bin/env python3
"""Preserve the v16 candidate and reclaim one independently mirrored backup."""
import fcntl,hashlib,json,os,shutil,subprocess
from pathlib import Path
lock=open('/tmp/rasterix-game-launch.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert not subprocess.run(['pidof','ClassiCube'],stdout=subprocess.PIPE).stdout
archive=Path('/media/sd-mmcblk1p1/rasterix-classicube-cache-archive-20261021')
r=json.loads(Path('/tmp/cc_vertex_final_host_mirror.json').read_text());assert r['sha256'].startswith('52895f4cf627')
name='classicube-'+r['sha256'][:12]+'.tar.gz';path=archive/name
assert path.resolve()==path and not path.is_symlink() and path.stat().st_size==r['bytes']
assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
receipt=json.loads(path.with_name(name[:-7]+'.json').read_text());assert receipt['verified'] and receipt['sha256']==r['sha256']
locator=path.with_name(name+'.host.json');assert not locator.exists()
data=(json.dumps(r,indent=2)+'\n').encode()
with locator.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
assert locator.read_bytes()==data;os.sync();path.unlink();os.sync()
cache=Path('/opt/rasterix/experimental/cache');source=cache/'classicube.tar.gz';meta=cache/'classicube.json'
receipt=json.loads(meta.read_text());digest=hashlib.sha256(source.read_bytes()).hexdigest()
assert receipt['verified'] and digest==receipt['sha256']=='cc755593abf15835f44b98ddd021cbffc77dfa41ba43235f77fe5fdf39fcb20a'
assert source.resolve()==source
dest=archive/('classicube-'+digest[:12]+'.tar.gz');assert not dest.exists()
assert shutil.disk_usage(archive).free>source.stat().st_size+16*1024*1024
with dest.open('xb') as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
assert hashlib.sha256(dest.read_bytes()).hexdigest()==digest
metadata=dest.with_name(dest.name[:-7]+'.json');assert not metadata.exists()
with metadata.open('xb') as f:f.write(meta.read_bytes());f.flush();os.fsync(f.fileno())
assert metadata.read_bytes()==meta.read_bytes();os.sync();source.unlink();meta.unlink();os.sync()
result={'passed':True,'host_mirror':r,'candidate_SD':str(dest),'candidate_sha256':digest,
        'root_free_bytes':shutil.disk_usage('/').free,'SD_free_bytes':shutil.disk_usage(archive).free}
Path('/tmp/postproc-tests/cc_vertex_final_storage.json').write_text(json.dumps(result,indent=2)+'\n')
print('CLASSICUBE_VERTEX_FINAL_STORAGE_PASS',result,flush=True)
