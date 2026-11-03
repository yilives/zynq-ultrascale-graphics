"""Preserve RAM inputs/evidence, never program PL or clear quarantine."""
import fcntl,hashlib,json,mmap,os,struct,sys,tarfile,time
from pathlib import Path
sys.path.insert(0,'/tmp')
from receive_java256_swap_ram_v3 import idle
root=Path('/tmp');locks=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
try:
 for n in ('rasterix-game-launch.lock','rix-superres.lock','rix-mc-style-extract.lock'):
  f=open(root/n,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
 idle();guard=Path('/opt/rasterix/experimental/gpu-quarantine.json')
 boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 assert json.loads(guard.read_text())['boot_id']==boot
 archive=root/'java-r71-reboot-extra.tar.gz';assert not archive.exists()
 names=['rix-fpga-java256','rix-java125/libs','rix-java125/native','rix-java125/probe','rix-java125/home','rix-java125/profile-baseline-r24','postproc-tests/java256-world-r24/save-repair.json','postproc-tests/java256-world-r71/result.json','postproc-tests/java256-world-r71/original-fsr-receipt.txt','postproc-tests/java256-r71-menu-evidence.tar.gz','receive_java125_ram.py','receive_java256_swap_ram_v3.py','launch_java_profile_vec_v2.py','bundle_java_cache_parts_v7.py','collect_java_cache_export_v7.py']
 with tarfile.open(archive,'w:gz') as t:
  for name in names:
   p=root/name;assert p.exists() and not p.is_symlink(),name
   def filt(info):
    if '__pycache__' in Path(info.name).parts:return None
    assert not info.issym() and not info.islnk(),info.name
    if info.name.startswith('rix-java125/home/.minecraft/saves/rixjava-r71'):
     info.name=info.name.replace('rix-java125/home/.minecraft/saves/rixjava-r71','postproc-tests/java256-world-r71/failed-unopened-world-save',1)
    return info
   t.add(p,arcname=name,filter=filt)
  t.add(guard,arcname='recovery-r71/quarantine-before-reboot.json')
 data=archive.read_bytes();assert 0<len(data)<=16*1024*1024
 fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
 try:
  with mmap.mmap(fd,(len(data)+4095)//4096*4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x60800000) as mem:
   mem[:len(data)]=data;assert hashlib.sha256(mem[:len(data)]).hexdigest()==sha(archive)
 finally:os.close(fd)
 record=dict(bytes=len(data),sha256=sha(archive),boot_id=boot,names=names)
 (root/'java-r71-reboot-extra.json').write_text(json.dumps(record))
 print('JAVA_R71_BACKUP_READY '+json.dumps(record),flush=True)
 deadline=time.monotonic()+600
 while not (root/'java-r71-reboot-ack').exists():
  assert time.monotonic()<deadline;time.sleep(.2)
 assert (root/'java-r71-reboot-ack').read_text().strip()==record['sha256']
 idle();print('JAVA_R71_BACKUP_RELEASED',flush=True)
finally:
 for f in reversed(locks):f.close()
