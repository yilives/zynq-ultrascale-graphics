#!/usr/bin/env python3
"""Add a verified optional command/model; never replaces the default entry."""
import argparse,contextlib,fcntl,hashlib,json,os,subprocess
from pathlib import Path
SD=Path('/media/sd-mmcblk1p1');BASE=Path('/usr/bin/rix-classicube-style')
ENTRY=Path('/usr/bin/rix-classicube-style-v5');MODEL=SD/'rasterix-mc-anime-quality-v5.cnn';META=SD/'rasterix-mc-quality-v5.json'
ROOT_GUARD=33554432;SD_GUARD=16777216
PUBLIC_SHA='0932ef7a6c3b0dc5b962dec7829c4a3436b1de83a72a0a9f67f44465da69c652'
ENTRY_SHA='42b5b3656b9289c4610d3e93f47493aa76c2c0e1cb6d84f088c764947fa9d985'
MODEL_SHA='2b3cedee067e24273a2e3f645002dac3af39986cca37178970bff0c2c7234ae5'
REPORT=Path('/tmp/postproc-tests/cc_v5_model_install.json')
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def regular(p):
 require(p.is_file() and not p.is_symlink(),'Expected regular file: '+str(p));return p.read_bytes()
def free(p):
 s=os.statvfs(str(p));return s.f_bavail*s.f_frsize
def sync_dir(p):
 fd=os.open(str(p),os.O_RDONLY|os.O_DIRECTORY)
 try:
  try:os.fsync(fd)
  except OSError:os.sync()
 finally:os.close(fd)
def write_new(p,data,mode):
 require(not p.is_symlink(),'Destination symlink')
 if p.exists():require(regular(p)==data,'Preserve unknown destination: '+str(p));return False
 temp=p.with_name(p.name+'.v5-incoming');require(not temp.exists() and not temp.is_symlink(),'Preserve existing staging file')
 fd=os.open(str(temp),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 require(regular(temp)==data and not p.exists(),'Write/commit changed');temp.chmod(mode);temp.replace(p);sync_dir(p.parent);require(regular(p)==data,'Committed readback mismatch');return True
def commit(entry,model,metadata,entry_bytes,model_bytes,meta_bytes,hook=lambda _:None):
 # Validate every fixed existing target BEFORE any write.
 for p,b in ((entry,entry_bytes),(model,model_bytes),(metadata,meta_bytes)):
  require(not p.is_symlink() and (not p.exists() or regular(p)==b),'Unknown target: '+str(p))
 old_entry=entry.exists()
 try:
  write_new(model,model_bytes,0o644);hook('model')
  write_new(metadata,meta_bytes,0o644);hook('metadata')
  write_new(entry,entry_bytes,0o755);hook('entry')
  require(all(regular(p)==b for p,b in ((entry,entry_bytes),(model,model_bytes),(metadata,meta_bytes))),'Final optional files changed')
 except BaseException:
  if not old_entry and entry.exists() and not entry.is_symlink() and regular(entry)==entry_bytes:entry.unlink();sync_dir(entry.parent)
  raise
def guard(root,sd,e,m,j):
 require(root>=ROOT_GUARD+e+8192,'Keep32MiB root guard');require(sd>=SD_GUARD+2*m+2*j+8192,'Keep16MiB SD guard')
def main():
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args();require(a.execute and os.geteuid()==0,'Explicit root --execute required')
 require(SD.is_mount() and SD.resolve()==SD and not SD.is_symlink(),'Expected mounted SD');require(not REPORT.exists() and not REPORT.is_symlink(),'Preserve existing install report')
 entry=regular(Path('/tmp/rix-classicube-style-v5'));model=regular(Path('/tmp/mc-anime-quality-v5.cnn'));meta_bytes=regular(Path('/tmp/quality-v5-manifest.json'));meta=json.loads(meta_bytes)
 require(meta['format']=='rix-mc-quality-v5-optional' and meta['required_public_sha256']==PUBLIC_SHA,'Manifest format/base')
 for name,data in (('rix-classicube-style-v5',entry),('anime-v5.cnn',model)):
  require(meta['files'][name]=={'bytes':len(data),'sha256':sha(data)},'Payload manifest mismatch')
 require(len(model)==7116 and sha(model)==MODEL_SHA and sha(entry)==ENTRY_SHA and sha(regular(BASE))==PUBLIC_SHA,'Known model/entry/default pins')
 require(ENTRY.parent.resolve()==ENTRY.parent,'Expected real root entry directory')
 guard(free(Path('/')),free(SD),len(entry),len(model),len(meta_bytes))
 record={'passed':False,'format':'rix-mc-quality-v5-installed','default_preserved':False,'model_sha256':MODEL_SHA,'entry_sha256':sha(entry),'manifest_sha256':sha(meta_bytes),'error':None}
 with contextlib.ExitStack() as stack:
  for name in ('rasterix-game-launch.lock','rix-superres.lock','rix-mc-style-extract.lock'):
   path=Path('/tmp')/name;require(not path.is_symlink(),'Lock symlink');f=stack.enter_context(path.open('a+'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  require(not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout,'GPU client running')
  gpu=json.loads(subprocess.check_output(['plgpuctl','status'],universal_newlines=True));post=json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],universal_newlines=True))
  require(gpu['status']==3 and gpu['config']==0x9adb505e and len({gpu[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1 and all(gpu[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors')),'GPU not idle/healthy')
  require(post['requested']==post['active']==1 and post['snapshot_status']==post['snapshot_expirations']==0,'POST not idle')
  require(sha(regular(BASE))==PUBLIC_SHA,'Default changed');guard(free(Path('/')),free(SD),len(entry),len(model),len(meta_bytes))
  record.update(before=gpu,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
  try:
   commit(ENTRY,MODEL,META,entry,model,meta_bytes);os.sync();require(sha(regular(BASE))==PUBLIC_SHA,'Default changed during install')
   require(free(Path('/'))>=ROOT_GUARD and free(SD)>=SD_GUARD,'Storage guard after install')
   record.update(passed=True,default_preserved=True,root_available=free(Path('/')),sd_available=free(SD),model=str(MODEL),entry=str(ENTRY),default_model_replaced=False,oil_model_replaced=False)
  except BaseException as exc:record['error']=repr(exc);raise
  finally:
   with REPORT.open('x') as f:json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 print('V5_OPTIONAL_MODEL_INSTALLED',json.dumps(record),flush=True)
if __name__=='__main__':main()
