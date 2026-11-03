#!/usr/bin/env python3
"""Same model/normal scheduler, serialized transient-versus-pool board runs."""
import argparse,hashlib,json,os,resource,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
p=argparse.ArgumentParser();p.add_argument('--phase',choices=('screen','abba'),default='screen');p.add_argument('--candidate',choices=('pipeline','copy','both'),default='both');p.add_argument('--seconds',type=int,default=12);p.add_argument('--prefix',default='cc_v5_pool');a=p.parse_args()
assert 8<=a.seconds<=90
assert a.prefix.replace('_','').isalnum() and len(a.prefix)<25
root=Path('/tmp/rix-mc-style-packages/a45fcf150c4a79b5-0f13b7fbde903a5d')
sys.path.insert(0,str(root/'bin'));from mc_worker_scheduler import adjust_mc_workers
out=Path('/tmp/postproc-tests');name=a.prefix+'_'+a.phase;target=out/(name+'.json');assert not target.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],universal_newlines=True))
post=lambda:json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],universal_newlines=True))
errors=('read_errors','write_errors','timeouts','underflows','scan_errors');rows=[]
order=['baseline','pipeline','copy','both','baseline'] if a.phase=='screen' else ['baseline',a.candidate,a.candidate,'baseline']
for index,kind in enumerate(order):
 attempt=name+'_'+str(index);folder=out/attempt;folder.mkdir();exe=root/'bin/rix-neural-style' if kind=='baseline' else Path('/tmp/rix-neural-'+kind+'-v5')
 assert os.access(str(exe),os.X_OK),'Candidate must be executable before source launch'
 model=root/'models/anime.cnn';before=status();assert all(before[k]==0 for k in errors)
 assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
 source_command=['rix-classicube','--seconds','180','--autoplay','--fps-limit','60','--attempt',attempt+'_game']
 command=[str(exe),'--model',str(model),'--backend','pl-int8','--live','--seconds',str(a.seconds),'--composition','mc-residual','--strength','128','--frame-pipeline','overlap','--snapshot-copy','neon','--snapshot-workers','4','--pio-output','atomic']
 for rect in ('0,0,400,34','0,192,400,48','194,114,12,12'):command+=['--protect-rect',rect]
 row={'kind':kind,'passed':False,'error':None,'runtime_sha256':sha(exe),'model_sha256':sha(model),'before':before,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'clock':{k:Path('/sys/devices/system/cpu/cpu0/cpufreq/'+k).read_text().strip() for k in ('scaling_cur_freq','scaling_governor')},'source_command':source_command,'neural_command':command}
 game=None;nn=None
 try:
  with (folder/'source.log').open('w') as gl:
   game=subprocess.Popen(source_command,stdout=gl,stderr=subprocess.STDOUT)
   source=out/(attempt+'_game')/'game.log';deadline=time.monotonic()+50
   while not source.exists() or 'RIX_MEASURE_BEGIN' not in source.read_text():
    assert game.poll() is None and time.monotonic()<deadline;time.sleep(.05)
   row['scheduler']=adjust_mc_workers(game.pid);assert row['scheduler']['passed']
   cpu_before=resource.getrusage(resource.RUSAGE_CHILDREN)
   with (folder/'neural.log').open('w') as log:
    nn=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);row['neural_exit']=nn.wait(timeout=a.seconds+25)
   cpu_after=resource.getrusage(resource.RUSAGE_CHILDREN)
   row['neural_child_cpu_seconds']={'user':cpu_after.ru_utime-cpu_before.ru_utime,'system':cpu_after.ru_stime-cpu_before.ru_stime}
   assert row['neural_exit']==0,(folder/'neural.log').read_text()
   m=[json.loads(l) for l in (folder/'neural.log').read_text().splitlines() if l.startswith('{')][-1]
   assert m['pio_output']=='atomic' and m['processed_frames']==m['present_submitted_frames']==m['present_completed_frames']>0
   row['metrics']=m
 except Exception as exc:row['error']=repr(exc)
 finally:
  if nn is not None and nn.poll() is None:nn.terminate();nn.wait(timeout=15)
  if game is not None:
   if game.poll() is None:game.terminate()
   row['game_exit']=game.wait(timeout=25)
  source=out/(attempt+'_game')/'result.json';row['source']=json.loads(source.read_text()) if source.exists() else None
  row['after']=status();row['post_after']=post()
  row['passed']=row['error'] is None and row['game_exit']==0 and row['source']['passed'] and all(row['after'][k]==0 for k in errors) and row['post_after']['requested']==row['post_after']['active']==1 and row['post_after']['snapshot_status']==row['post_after']['snapshot_expirations']==0
  rows.append(row);target.write_text(json.dumps(rows,indent=2)+'\n')
 print('MC_V5_POOL_RESULT',kind,row['passed'],row.get('metrics',{}).get('processed_fps'),row.get('error'),flush=True)
 assert row['passed'],row
print('MC_V5_POOL_BENCH_PASS',flush=True)
