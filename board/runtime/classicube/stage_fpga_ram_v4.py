#!/usr/bin/env python3
"""Keep GPU idle while two checked JTAG payloads cross reserved PS RAM."""
import fcntl,gzip,hashlib,json,os,signal,subprocess,time
from pathlib import Path
parent=Path('/tmp/rix-fpga-v4');assert not parent.exists();parent.mkdir(mode=0o700)
assert parent.resolve()==Path('/tmp').resolve()/parent.name
spec=json.loads(Path('/tmp/stage-manifest-v4.json').read_text());assert spec['format']=='rix-fpga-stage-v4'
locks=[]
for name in ('rasterix-game-launch.lock','rix-superres.lock','rix-mc-style-extract.lock'):
 f=open('/tmp/'+name,'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
assert not subprocess.run(['pidof','ClassiCube','rix-neural-style','rix-neural-runtime-v4'],stdout=subprocess.PIPE).stdout
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
before=status();assert before['status']==3 and all(before[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
assert len({before[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
post=json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],text=True))
assert post['requested']==post['active']==1 and post['snapshot_status']==post['snapshot_expirations']==0
sha=lambda b:hashlib.sha256(b).hexdigest()
stopping=[False];signal.signal(signal.SIGTERM,lambda *_:stopping.__setitem__(0,True))
record={'passed':False,'pid':os.getpid(),'before':before,'images':{},'error':None}
(parent/'ready.json').write_text(json.dumps(record)+'\n');print('FPGA_STAGE_GUARD_READY',os.getpid(),flush=True)
try:
 for kind in ('old','new'):
  item=spec['compressed'][kind];raw=spec['raw']['images'][kind]
  assert item['filename']==kind+'.bin.gz' and raw['filename']==kind+'.bin' and 0<item['bytes']<=2097152 and 0<raw['bytes']<=8388608
  flag=parent/(kind+'.ready');deadline=time.monotonic()+900
  while not flag.exists():
   assert not stopping[0] and time.monotonic()<deadline,'Staging cancelled or expired'
   time.sleep(.05)
  assert not flag.is_symlink() and status()==before,'GPU changed while holding staging ownership'
  subprocess.run(['/tmp/read-ps-stage-v4',str(item['bytes'])],check=True,timeout=30)
  compressed=(parent/'staging-read.bin').read_bytes();assert len(compressed)==item['bytes'] and sha(compressed)==item['sha256'],'JTAG compressed payload mismatch'
  data=gzip.decompress(compressed);assert len(data)==raw['bytes'] and sha(data)==raw['sha256'],'Raw FPGA image mismatch'
  target=parent/raw['filename'];assert not target.exists();target.write_bytes(data)
  assert sha(target.read_bytes())==raw['sha256']
  record['images'][kind]=raw;(parent/(kind+'.done')).write_text(raw['sha256']+'\n')
  print('FPGA_STAGE_IMAGE_VERIFIED',kind,len(data),raw['sha256'],flush=True)
 (parent/'manifest.json').write_text(json.dumps(spec['raw'],indent=2)+'\n')
 assert status()==before
 record['passed']=True;record['after']=status()
except Exception as error:record['error']=repr(error)
finally:
 Path('/tmp/postproc-tests/cc_v4_fpga_stage.json').write_text(json.dumps(record,indent=2)+'\n')
 print('FPGA_STAGE_COMPLETE',record['passed'],record['error'],flush=True)
 for f in reversed(locks):f.close()
raise SystemExit(0 if record['passed'] else 1)
