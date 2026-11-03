#!/usr/bin/env python3
"""Isolated, serialized source/NN CPU-affinity and transfer profiling study."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--phase',choices=('affinity','profile','runtime','protocol','release','abba'),default='affinity')
p.add_argument('--seconds',type=int,default=10)
p.add_argument('--candidate',default='split3')
p.add_argument('--executable',default='/tmp/rix-neural-profile-v4')
p.add_argument('--prefix',default='cc_v4_explore')
a=p.parse_args();assert 6<=a.seconds<=90 and a.prefix.replace('_','').isalnum() and len(a.prefix)<25
root=Path('/tmp/rix-mc-style-packages/a45fcf150c4a79b5/mc-style')
# Public bootstrap extracts the payload directly, without the archive prefix.
if not (root/'bin/rix-neural-style').exists():root=root.parent
runtime=root/'bin/rix-neural-style';model=root/'models/anime.cnn'
out=Path('/tmp/postproc-tests');out.mkdir(exist_ok=True)
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
post='/opt/rasterix/postproc-touch/bin/rix-superres'
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
errors=('read_errors','write_errors','timeouts','underflows','scan_errors')
cases={
 'baseline':([0,1,2,3],[0,1,2,3],4),
 'split3':([3],[0,1,2],4),
 'split3b':([0],[1,2,3],4),
 'gamepin':([3],[0,1,2,3],4),
 'split2':([2,3],[0,1],4),
 'workers2':([0,1,2,3],[0,1,2,3],2),
 'other':([0,1,2,3],[0,1,2,3],4),
}
runtime_extras={
 'rt-original':['--fusion-mode','original','--display-writers','1','--pio-output','legacy'],
 'planar':['--fusion-mode','planar','--display-writers','1','--pio-output','legacy'],
 'pairs':['--fusion-mode','pairs','--display-writers','1','--pio-output','legacy'],
 'pairs128':['--fusion-mode','pairs128','--display-writers','1','--pio-output','legacy'],
 'write2':['--fusion-mode','original','--display-writers','2','--pio-output','legacy'],
 'write4':['--fusion-mode','original','--display-writers','4','--pio-output','legacy'],
 'transport-legacy':['--pio-output','legacy'],
 'atomic':['--pio-output','atomic'],
 'atomic-normal':['--pio-output','atomic'],
 'atomic-write2':['--fusion-mode','original','--display-writers','2','--pio-output','atomic'],
 'atomic-write4':['--fusion-mode','original','--display-writers','4','--pio-output','atomic'],
}
if a.phase=='affinity':order=['baseline','other','split3','split3b','gamepin','split2','workers2','baseline']
elif a.phase=='profile':order=['baseline','profile','profile','baseline']
elif a.phase=='runtime':order=['baseline','rt-original','planar','pairs','pairs128','write2','write4','baseline']
elif a.phase=='protocol':order=['transport-legacy','atomic','atomic','transport-legacy']
elif a.phase=='release':order=['baseline','atomic-normal','atomic-normal','baseline']
else:
 assert a.candidate in set(cases)|set(runtime_extras) and a.candidate!='baseline'
 order=['baseline',a.candidate,a.candidate,'baseline']
records=[]
def thread_state(name):
 value=subprocess.run(['pidof',name],stdout=subprocess.PIPE,text=True).stdout.split()
 rows=[]
 for pid in value:
  for path in sorted((Path('/proc')/pid/'task').iterdir()):
   tid=int(path.name)
   try:rows.append({'pid':int(pid),'tid':tid,'name':(path/'comm').read_text().strip(),'scheduler':os.sched_getscheduler(tid),'rt_priority':os.sched_getparam(tid).sched_priority,'cpus':sorted(os.sched_getaffinity(tid))})
   except ProcessLookupError:pass
 return rows

for index,case in enumerate(order):
 label=a.prefix+'_'+str(index);folder=out/label;folder.mkdir(exist_ok=False)
 game_cpus,nn_cpus,workers=cases.get(case,cases['baseline'])
 exe=Path(a.executable) if case=='profile' or case in runtime_extras else runtime
 assert not subprocess.run(['pidof','ClassiCube','rix-neural-style','rix-neural-profile-v4'],stdout=subprocess.PIPE).stdout
 before=status();assert all(before[k]==0 for k in errors)
 clock={k:Path('/sys/devices/system/cpu/cpu0/cpufreq/'+k).read_text().strip() for k in ('scaling_cur_freq','scaling_governor')}
 source_command=['rix-classicube','--seconds','180','--autoplay','--attempt',label+'_game','--fps-limit','60']
 command=[str(exe),'--model',str(model),'--backend','pl-int8','--live','--seconds',str(a.seconds),'--composition','mc-residual','--strength','128','--frame-pipeline','overlap','--snapshot-copy','neon','--snapshot-workers',str(workers)]
 for r in ('0,0,400,34','0,192,400,48','194,114,12,12'):command+=['--protect-rect',r]
 command+=runtime_extras.get(case,[])
 failure=None;nn=None;metrics=None;code=None;cpu_before=None;cpu_after=None;threads_before=[];threads_adjusted=[];nn_threads=[];worker_audit=None
 with (folder/'game-launch.log').open('w') as game_log:
  game=subprocess.Popen(source_command,preexec_fn=lambda:os.sched_setaffinity(0,game_cpus),stdout=game_log,stderr=subprocess.STDOUT)
  try:
   source_log=out/(label+'_game')/'game.log';end=time.monotonic()+60
   while not source_log.exists() or 'RIX_MEASURE_BEGIN' not in source_log.read_text():
    assert game.poll() is None and time.monotonic()<end,'MC startup failed';time.sleep(.05)
   threads_before=thread_state('ClassiCube')
   assert threads_before,'Native game threads not found'
   if case=='atomic-normal':
    import sys
    sys.path.insert(0,'/tmp/rix-mc-style-v4/mc-style/bin')
    from mc_worker_scheduler import adjust_mc_workers
    worker_audit=adjust_mc_workers(game.pid)
    assert worker_audit['passed']
   elif case=='other':
    native_pid=threads_before[0]['pid'];ancestor=native_pid
    while ancestor not in (1,game.pid):
     ancestor=int(next(l.split()[1] for l in (Path('/proc')/str(ancestor)/'status').read_text().splitlines() if l.startswith('PPid:')))
    assert ancestor==game.pid,'Refuse scheduling adjustment outside this game child tree'
    for r in threads_before:os.sched_setscheduler(r['tid'],os.SCHED_OTHER,os.sched_param(0))
   threads_adjusted=thread_state('ClassiCube')
   cpu_before=Path('/proc/stat').read_text().splitlines()[:5]
   with (folder/'neural.log').open('w') as neural_log:
    nn=subprocess.Popen(command,preexec_fn=lambda:os.sched_setaffinity(0,nn_cpus),stdout=neural_log,stderr=subprocess.STDOUT)
    time.sleep(.2);nn_threads=thread_state(exe.name)
    code=nn.wait(timeout=a.seconds+20)
   cpu_after=Path('/proc/stat').read_text().splitlines()[:5]
   assert code==0,(folder/'neural.log').read_text()
   metrics=[json.loads(l) for l in (folder/'neural.log').read_text().splitlines() if l.startswith('{')][-1]
   assert metrics['processed_frames']==metrics['present_submitted_frames']==metrics['present_completed_frames']>0
  except Exception as exc:failure=repr(exc)
  finally:
   if nn is not None and nn.poll() is None:nn.terminate();nn.wait(timeout=15)
   if game.poll() is None:game.terminate()
   game.wait(timeout=25)
 source=json.loads((out/(label+'_game')/'result.json').read_text())
 after=status();post_after=json.loads(subprocess.check_output([post,'--status'],text=True))
 row={'case':case,'index':index,'command':command,'source_command':source_command,'game_cpus':game_cpus,'neural_cpus':nn_cpus,'workers':workers,'clock':clock,'runtime_sha256':sha(exe),'model_sha256':sha(model),'before':before,'after':after,'post_after':post_after,'metrics':metrics,'source':source,'error':failure,'game_exit':game.returncode,'neural_exit':code,'cpu_before':cpu_before,'cpu_after':cpu_after,'game_threads_before':threads_before,'game_threads_adjusted':threads_adjusted,'neural_threads':nn_threads,'worker_policy_audit':worker_audit}
 row['passed']=failure is None and game.returncode==0 and source['passed'] and all(before[k]==after[k]==0 for k in errors) and post_after['snapshot_status']==post_after['snapshot_expirations']==0 and post_after['requested']==post_after['active']==1
 records.append(row);(out/(a.prefix+'.json')).write_text(json.dumps(records,indent=2)+'\n')
 print('MC_V4_EXPLORE',case,row['passed'],'style',metrics and metrics['processed_fps'],'source',source.get('hardware_window'),flush=True)
 assert row['passed'],row
print('MC_V4_EXPLORE_PASS',flush=True)
