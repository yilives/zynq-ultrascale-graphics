#!/usr/bin/env python3
"""Preserve QA-created bytecode evidence; never deletes or weakens cache checks."""
import contextlib,fcntl,hashlib,json,os,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
root=Path('/tmp/rix-mc-style-packages/a45fcf150c4a79b5-0f13b7fbde903a5d');backup=root.with_name(root.name+'.qa-bytecode-evidence-v5')
out=Path('/tmp/postproc-tests/cc_v5_cache_repair.json');assert not out.exists() and not backup.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with contextlib.ExitStack() as stack:
 for name in ('rasterix-game-launch.lock','rix-superres.lock','rix-mc-style-extract.lock'):
  f=stack.enter_context((Path('/tmp')/name).open('a+'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
 gpu=json.loads(subprocess.check_output(['plgpuctl','status'],universal_newlines=True));assert gpu['status']==3 and len({gpu[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
 assert root.resolve()==Path('/tmp').resolve()/'rix-mc-style-packages'/root.name and not root.is_symlink()
 manifest=json.loads((root/'manifest.json').read_text());assert len(manifest)==12
 for n,item in manifest.items():
  p=root/n;assert not p.is_symlink() and p.is_file() and p.stat().st_size==item['bytes'] and sha(p)==item['sha256']
 files={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
 extra=files-set(manifest)-{'manifest.json'};assert extra=={'bin/__pycache__/mc_worker_scheduler.cpython-37.pyc'},extra
 assert not any(p.is_symlink() for p in root.rglob('*'))
 record={'passed':False,'reason':'QA imported scheduler without disabling Python bytecode; immutable public cache correctly rejected the extra file','source':str(root),'preserved_as':str(backup),'payload_hashes_intact':True,'extra':{n:{'bytes':(root/n).stat().st_size,'sha256':sha(root/n)} for n in extra},'gpu':gpu,'deleted_files':False}
 root.rename(backup);assert backup.is_dir() and not root.exists();record['passed']=True;out.write_text(json.dumps(record,indent=2)+'\n')
 print('QUALITY_CACHE_EVIDENCE_PRESERVED',str(backup),flush=True)
