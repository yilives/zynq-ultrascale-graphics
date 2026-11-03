#!/usr/bin/env python3
"""Verify complete v3+overlay archives and stage an isolated merged RAM tree."""
import argparse,fcntl,hashlib,io,json,os,stat,tarfile
from pathlib import Path,PurePosixPath
p=argparse.ArgumentParser();p.add_argument('--sha256',required=True);a=p.parse_args()
assert len(a.sha256)==64 and all(c in '0123456789abcdef' for c in a.sha256)
old_sha='a45fcf150c4a79b5c0014c0667b815fb0f136f1c60760175f48a784b1c521a82'
sha=lambda b:hashlib.sha256(b).hexdigest()
def regular(path):
 assert stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()
 return path.read_bytes()
def archive(path,digest,prefix):
 raw=regular(path);assert sha(raw)==digest
 with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
  ms=tf.getmembers();assert len(ms)==len({m.name for m in ms})<=32
  files={}
  for m in ms:
   assert m.isfile() and m.name.startswith(prefix+'/') and 0<m.size<=200000
   name=m.name[len(prefix)+1:];parts=PurePosixPath(name).parts
   assert name=='/'.join(parts) and all(x not in ('..','.','') for x in parts) and not name.startswith('/') and '\\' not in name
   files[name]=tf.extractfile(m).read()
 return files
def verify(files,manifest):
 assert set(files)==set(manifest)
 for name,data in files.items():assert type(manifest[name]['bytes']) is int and len(data)==manifest[name]['bytes'] and sha(data)==manifest[name]['sha256']
base=archive(Path('/media/sd-mmcblk1p1/rasterix-mc-style-v3.tar.gz'),old_sha,'mc-style')
manifest=json.loads(base.pop('manifest.json'));verify(base,manifest)
overlay=archive(Path('/tmp/mc-style-v4-overlay.tar.gz'),a.sha256,'mc-style-overlay')
spec=json.loads(overlay.pop('overlay.json'));assert spec['format']=='rix-mc-style-v4-overlay' and spec['base_sha256']==old_sha
assert set(overlay)=={'bin/rix-neural-style','bin/rix-neural-games','bin/mc_worker_scheduler.py','provenance.json'}
verify(overlay,spec['files']);base.update(overlay);manifest.update(spec['files']);verify(base,manifest)
lock=open('/tmp/rix-mc-style-extract.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
parent=Path('/tmp/rix-mc-style-v4');assert not parent.exists();parent.mkdir(mode=0o700)
assert parent.resolve()==Path('/tmp').resolve()/parent.name
target=parent/'mc-style';target.mkdir()
for name,data in base.items():
 path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o755 if name.startswith('bin/') else 0o644)
(target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert all(sha(regular(target/n))==v['sha256'] for n,v in manifest.items())
record={'passed':True,'base_sha256':old_sha,'overlay_sha256':a.sha256,'merged_files':len(manifest),'root':str(target),'files':manifest,'persistent_write':False}
Path('/tmp/postproc-tests/cc_v4_overlay_stage.json').write_text(json.dumps(record,indent=2)+'\n')
print('MC_V4_OVERLAY_STAGED',str(target),len(manifest),flush=True)
