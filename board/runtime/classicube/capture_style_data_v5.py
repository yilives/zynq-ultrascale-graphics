#!/usr/bin/env python3
"""Bounded real terrain sequences, kept in RAM; never replaces game payloads."""
import argparse,hashlib,json,os,subprocess,tarfile,time
from pathlib import Path
out=Path('/tmp/postproc-tests')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
errors=('read_errors','write_errors','timeouts','underflows','scan_errors')
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],universal_newlines=True))
assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
parser=argparse.ArgumentParser();parser.add_argument('--fresh-test',action='store_true');args=parser.parse_args()
for size,count,flat in (((128,8,True),) if args.fresh_test else ((32,18,False),(128,8,False))):
 name='cc_v5_data_'+str(size)+('_flat' if flat else '');folder=out/name;folder.mkdir(mode=0o700)
 env=os.environ.copy();env['RIX_INPUT_QA']=str(folder)
 command=['rix-classicube','--seconds','40','--world-size',str(size),'--autoplay','--fps-limit','60','--attempt',name+'_game']
 if flat:command+=['--flat']
 before=status();game=None;record={'passed':False,'error':None,'source_command':command,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'sequence_id':name,'before':before}
 try:
  with (folder/'launcher.log').open('x') as log:
   game=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env)
   source=out/(name+'_game')/'game.log';deadline=time.monotonic()+50
   while not source.exists() or 'RIX_MEASURE_BEGIN' not in source.read_text():
    assert game.poll() is None and time.monotonic()<deadline,'Source not ready';time.sleep(.05)
   result=subprocess.run(['/tmp/capture-style-sequence-v5',str(folder),str(count),'500'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True,timeout=count+15)
   record['capture_log']=result.stdout;assert result.returncode==0,result.stdout
   frames=json.loads((folder/'captures.json').read_text());assert len(frames)==count
   for row in frames:
    f=folder/row['file'];assert f.stat().st_size==192000 and row['lease_verified_after_copy'];row['sha256']=sha(f)
   record.update(captures=frames,telemetry_last=json.loads((folder/'input.json').read_text()),capture_binary_sha256=sha(Path('/tmp/capture-style-sequence-v5')))
 except Exception as exc:record['error']=repr(exc)
 finally:
  if game is not None:
   if game.poll() is None:game.terminate()
   record['game_exit']=game.wait(timeout=25)
  record['after']=status()
  r=out/(name+'_game')/'result.json';record['source_result']=json.loads(r.read_text()) if r.exists() else None
  record['passed']=record['error'] is None and record.get('game_exit')==0 and record['source_result']['passed'] and all(record['after'][k]==0 for k in errors)
  (folder/'sequence.json').write_text(json.dumps(record,indent=2)+'\n')
 assert record['passed'],record
 archive=out/(name+'.tar.gz');assert not archive.exists()
 with tarfile.open(archive,'w:gz') as tf:
  for row in record['captures']:tf.add(folder/row['file'],arcname=row['file'])
  tf.add(folder/'sequence.json',arcname='sequence.json')
 assert archive.stat().st_size<=1536000
 print('MC_V5_DATA_CAPTURE_PASS',size,count,archive.stat().st_size,flush=True)
