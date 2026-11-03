#!/usr/bin/env python3
"""Fixed-tensor old/new PIO protocol checks on idle GPU, all outputs in RAM."""
import argparse,fcntl,hashlib,json,mmap,os,struct,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--name',default='cc_v4_transport_pre');a=p.parse_args()
assert a.name.replace('_','').isalnum() and len(a.name)<32
out=Path('/tmp/postproc-tests');exe=Path('/tmp/rix-neural-transport-v4');base=Path('/opt/rasterix/neural-style')
lock=open('/tmp/rasterix-game-launch.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert not subprocess.run(['pidof','ClassiCube','rix-neural-style','rix-neural-runtime-v4'],stdout=subprocess.PIPE).stdout
assert (Path('/proc/device-tree/neural-style@a0030000/compatible').read_bytes() in (b'rasterix,cnn-int8-v1\0',b'rasterix,cnn-int8-v2\0'))
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC);regs=mmap.mmap(fd,65536,offset=0xa0030000)
read=lambda x:struct.unpack_from('<I',regs,x)[0]
assert read(0)==0x4e4e5332 and read(0x38)==414738
cap=read(0x3c);abi=read(0x44) if cap&4 else None
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
before=status();rows=[];negative=None
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
for style in ('oil','anime'):
 model=base/('models/'+style+'.cnn');input_file=base/('tests/'+style+'-full-input.bin');expected=(base/('tests/'+style+'-full-output.bin')).read_bytes()
 modes=['legacy','atomic','atomic','legacy','auto'] if cap&4 else ['legacy','auto','auto','legacy']
 for index,mode in enumerate(modes):
  target=out/(a.name+'_'+style+'_'+str(index)+'.bin')
  command=[str(exe),'--backend','pl-int8','--model',str(model),'--input',str(input_file),'--output',str(target),'--pio-output',mode]
  run=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=15)
  assert run.returncode==0,(command,run.stdout,run.stderr)
  metrics=json.loads(run.stdout);assert metrics['engine_version']==2 and metrics['cnn_cycles']==414738
  assert metrics['pio_output']==('atomic' if (cap&4 and mode!='legacy') else 'legacy')
  assert target.read_bytes()==expected,'Actual PL tensor differs from independent expected output'
  rows.append({'style':style,'requested':mode,'metrics':metrics,'model_sha256':sha(model),'input_sha256':sha(input_file),'output_sha256':sha(target),'expected_sha256':hashlib.sha256(expected).hexdigest(),'bit_exact':True})
if not cap&4:
 offsets=(0xc,0x28,0x2c,0x30,0x34,0x38,0x3c)
 old=[read(x) for x in offsets]
 r=subprocess.run([str(exe),'--backend','pl-int8','--model',str(model),'--pio-output','atomic'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10)
 current=[read(x) for x in offsets]
 negative={'exit':r.returncode,'stderr':r.stderr,'before':old,'after':current,'passed':r.returncode==1 and 'atomic output capability absent' in r.stderr and current==old}
 assert negative['passed'],negative
after=status();assert before==after,'Idle GPU changed during standalone CNN checks'
post=json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],text=True))
assert post['requested']==post['active']==1 and post['snapshot_status']==post['snapshot_expirations']==0
record={'passed':True,'executable_sha256':sha(exe),'capabilities':cap,'adapter_abi':abi,'runs':rows,'unsupported_atomic_rejected_before_any_writes':negative,'gpu_before':before,'gpu_after':after,'post':post,'scope':'Real idle FPGA inference and exact fixed tensors, no live-game FPS claim'}
(out/(a.name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
print('MC_TRANSPORT_FIXED_PASS',cap,[(r['style'],r['requested'],r['metrics']['seconds']) for r in rows],flush=True)
regs.close();os.close(fd)
