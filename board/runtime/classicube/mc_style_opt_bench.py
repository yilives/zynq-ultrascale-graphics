#!/usr/bin/env python3
"""Same MC model/world/settings, fresh game per case, serialized device QA."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/tmp/rix-mc-style-opt-v2'))
p.add_argument('--phase',choices=('select','abba'),default='select');p.add_argument('--seconds',type=int,default=8)
p.add_argument('--workers',type=int,choices=(1,2,4),default=4);p.add_argument('--copy',choices=('paired','neon'),default='neon')
a=p.parse_args();out=Path('/tmp/postproc-tests');oldroot=Path('/tmp/rix-mc-style-packages/89c1478f4406a0f9')
oldexe=oldroot/'bin/rix-neural-style';exe=a.root/'bin/rix-neural-style';model=oldroot/'models/anime.cnn'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
post='/opt/rasterix/postproc-touch/bin/rix-superres';errors=('read_errors','write_errors','timeouts','underflows','scan_errors')
if a.phase=='select':cases=[('v1',None,4,'paired'),('serial-paired4','serial',4,'paired'),('serial-neon4','serial',4,'neon'),('overlap-neon4','overlap',4,'neon'),('overlap-neon2','overlap',2,'neon'),('overlap-neon1','overlap',1,'neon')]
else:cases=[('v1',None,4,'paired'),('v2','overlap',a.workers,a.copy),('v2','overlap',a.workers,a.copy),('v1',None,4,'paired')]
records=[];prefix='cc_style_opt_'+a.phase
for i,(name,pipeline,workers,copier) in enumerate(cases):
    attempt=prefix+'_'+str(i);folder=out/attempt;folder.mkdir(exist_ok=False)
    before=status();assert all(before[k]==0 for k in errors)
    assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
    nn=None;failure=None
    clock={n:Path('/sys/devices/system/cpu/cpu0/cpufreq/'+n).read_text().strip() for n in ('scaling_cur_freq','scaling_governor')}
    with (folder/'game-launcher.log').open('w') as game_log:
        game=subprocess.Popen(['rix-classicube','--seconds','120','--attempt',attempt+'_game','--autoplay'],stdout=game_log,stderr=subprocess.STDOUT)
        try:
            log=out/(attempt+'_game')/'game.log';deadline=time.monotonic()+60
            while not log.exists() or 'RIX_MEASURE_BEGIN' not in log.read_text():
                assert game.poll() is None and time.monotonic()<deadline,'MC failed to produce measured frames'
                time.sleep(.05)
            command=[str(oldexe if pipeline is None else exe),'--model',str(model),'--backend','pl-int8','--live','--seconds',str(a.seconds),'--composition','mc-residual','--strength','128']
            for rect in ('0,0,400,34','0,192,400,48','194,114,12,12'):command+=['--protect-rect',rect]
            if pipeline is not None:command+=['--frame-pipeline',pipeline,'--snapshot-workers',str(workers),'--snapshot-copy',copier]
            with (folder/'neural.log').open('w') as nn_log:
                nn=subprocess.Popen(command,stdout=nn_log,stderr=subprocess.STDOUT);code=nn.wait(timeout=a.seconds+15)
            assert code==0,(folder/'neural.log').read_text()
            metrics=[json.loads(l) for l in (folder/'neural.log').read_text().splitlines() if l.startswith('{')][-1]
            assert metrics['processed_frames']==metrics['present_submitted_frames']==metrics['present_completed_frames']>0
            assert metrics['cnn_cycles_per_frame']==414738
        except Exception as error:failure=repr(error)
        finally:
            if nn is not None and nn.poll() is None:nn.terminate();nn.wait(timeout=10)
            if game.poll() is None:game.terminate()
            code=game.wait(timeout=25)
    after=status();post_after=json.loads(subprocess.check_output([post,'--status'],text=True))
    result={'case':name,'index':i,'command':command,'model_sha256':sha(model),'runtime_sha256':sha(oldexe if pipeline is None else exe),'metrics':metrics if failure is None else None,
            'clock':clock,'before':before,'after':after,'game_exit':code,'error':failure,'post_after':post_after}
    result['passed']=failure is None and code==0 and all(before[k]==after[k]==0 for k in errors) and post_after['snapshot_status']==0 and post_after['snapshot_expirations']==0
    records.append(result);(out/(prefix+'.json')).write_text(json.dumps(records,indent=2)+'\n')
    print('MC_STYLE_OPT_CASE',name,result['metrics'],flush=True)
    assert result['passed'],result
print('MC_STYLE_OPT_BENCH_PASS',prefix,flush=True)
