#!/usr/bin/env python3
"""Install verified additive files, or stage the validated boot pair with rollback."""
import argparse,hashlib,json,os,shutil,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--activate-boot',action='store_true');a=p.parse_args()
assert os.geteuid()==0
cache=Path('/opt/rasterix/experimental/cache');archive=cache/'postproc-touch.tar.gz'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
record=json.loads((cache/'postproc-touch.json').read_text());assert record.get('verified')and sha(archive)==record['sha256']
target=Path('/opt/rasterix/postproc-touch');target.mkdir(parents=True,exist_ok=True)
previous=json.loads((target/'manifest.json').read_text())if(target/'manifest.json').exists()else {}
with tarfile.open(archive)as tf:
 members=tf.getmembers()
 for m in members:
  path=Path(m.name);assert m.isfile()and path.parts[0]=='postproc-touch'and '..'not in path.parts and len(path.parts)<=3
 manifest=json.load(tf.extractfile('postproc-touch/manifest.json'))
 for name,meta in manifest.items():
  data=tf.extractfile('postproc-touch/'+name).read();assert len(data)==meta['bytes']and hashlib.sha256(data).hexdigest()==meta['sha256']
 for m in members:
  path=target/Path(*Path(m.name).parts[1:]);assert not path.is_symlink();path.parent.mkdir(parents=True,exist_ok=True)
  data=tf.extractfile(m).read();tmp=path.with_name(path.name+'.incoming');tmp.write_bytes(data);os.chmod(tmp,0o755 if path.parent.name=='bin'else 0o644);os.replace(tmp,path)
os.sync()
for name,file in (('S08rasterix-postproc','rasterix-postproc-start.sh'),('S08rasterix-touch','rasterix-touch-start.sh')):
 hook=Path('/etc/rc5.d')/name;script=target/'bin'/file
 if hook.is_symlink():assert hook.resolve()==script
 elif hook.exists():raise RuntimeError('Refuse to overwrite unrelated boot hook')
 else:hook.symlink_to(script)
print('POSTPROC_TOUCH_SOFTWARE_INSTALLED',flush=True)
if a.activate_boot:
 boot=Path('/mnt/sd-mmcblk1p1');assert boot.resolve()==Path('/media/sd-mmcblk1p1')
 expected={'BOOT.BIN':'8f26ae5abc9360cea233545b8d044d4bb257e1d5159f79ca4a7b5180effed3bc','system.dtb':'854f1b2f87bb35d2bebcc280552f501b5747dabd1edeaffc76397f34f8784d77'}
 assert shutil.disk_usage(boot).free>32*1024*1024
 assert not os.system('pidof tuxracer rix-smoke neverball neverputt quake3e quakespasm rix-superres >/dev/null')==0,'Stop GPU clients before boot update'
 history={name:set()for name in expected}
 # Software may be installed before boot activation. Retain all fully verified
 # feature boot revisions instead of assuming the last software manifest is active.
 for metadata in cache.glob('postproc-touch*.json'):
  saved=cache/(metadata.stem+'.tar.gz')
  info=json.loads(metadata.read_text())
  if not info.get('verified')or not saved.is_file()or sha(saved)!=info['sha256']:continue
  with tarfile.open(saved)as tf:
   old=json.load(tf.extractfile('postproc-touch/manifest.json'))
   for name in expected:
    key='boot/'+name
    if key in old:
     data=tf.extractfile('postproc-touch/'+key).read();digest=hashlib.sha256(data).hexdigest()
     assert digest==old[key]['sha256'];history[name].add(digest)
 for name,digest in expected.items():
  original=boot/name;backup=boot/(name+'.pre-postproc-20261018')
  allowed={digest,manifest['boot/'+name]['sha256']}
  allowed.update(history[name])
  if 'boot/'+name in previous:allowed.add(previous['boot/'+name]['sha256'])
  assert sha(original)in allowed,'Active boot differs from validated baseline or known feature package'
  if backup.exists():assert sha(backup)==digest
  else:
   assert sha(original)==digest,'Baseline backup is required before replacing feature firmware'
   shutil.copyfile(original,backup)
  assert sha(backup)==digest
  incoming=target/'boot'/name;assert sha(incoming)==manifest['boot/'+name]['sha256']
  pending=boot/(name+'.incoming');shutil.copyfile(incoming,pending);assert sha(pending)==sha(incoming)
 os.sync()
 # The new bitstream also runs with the old DT. Activate it first, then DT.
 for name in ('BOOT.BIN','system.dtb'):
  os.replace(boot/(name+'.incoming'),boot/name);os.sync();assert sha(boot/name)==manifest['boot/'+name]['sha256']
 print('POSTPROC_TOUCH_BOOT_STAGED_AND_READBACK_VERIFIED',json.dumps({name:sha(boot/name)for name in expected}),flush=True)
os.sync()
