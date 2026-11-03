#!/usr/bin/env python3
"""Test upstream submission caps without changing models or pixel math."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--phase',choices=('select','abba'),default='select')
p.add_argument('--seconds',type=int,default=12);p.add_argument('--candidate-cap',type=int,choices=(30,60,120),default=60)
p.add_argument('--prefix',default='cc_style_v3_source')
a=p.parse_args();assert a.prefix.replace('_','').isalnum() and len(a.prefix)<35
root=Path('/tmp/rix-mc-style-packages/8c8cd893bd6b7a66');exe=root/'bin/rix-neural-style';model=root/'models/anime.cnn'
out=Path('/tmp/postproc-tests');out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
post='/opt/rasterix/postproc-touch/bin/rix-superres';errors=('read_errors','write_errors','timeouts','underflows','scan_errors')
cases=[120,60,30] if a.phase=='select' else [120,a.candidate_cap,a.candidate_cap,120]
records=[]
for i,cap in enumerate(cases):
    attempt=a.prefix+'_'+a.phase+'_'+str(i);folder=out/attempt;folder.mkdir(exist_ok=False)
    assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
    before=status();assert all(before[k]==0 for k in errors)
    clock={n:Path('/sys/devices/system/cpu/cpu0/cpufreq/'+n).read_text().strip() for n in ('scaling_cur_freq','scaling_governor')}
    nn=None;failure=None;metrics=None
    game_command=['rix-classicube','--seconds','180','--attempt',attempt+'_game','--autoplay','--fps-limit',str(cap)]
    command=[str(exe),'--model',str(model),'--backend','pl-int8','--live','--seconds',str(a.seconds),'--composition','mc-residual','--strength','128',
             '--frame-pipeline','overlap','--snapshot-workers','4','--snapshot-copy','neon']
    for rect in ('0,0,400,34','0,192,400,48','194,114,12,12'):command+=['--protect-rect',rect]
    with (folder/'launcher.log').open('w') as log:
        game=subprocess.Popen(game_command,stdout=log,stderr=subprocess.STDOUT)
        try:
            source_log=out/(attempt+'_game')/'game.log';deadline=time.monotonic()+60
            while not source_log.exists() or 'RIX_MEASURE_BEGIN' not in source_log.read_text():
                assert game.poll() is None and time.monotonic()<deadline,'source startup failed'
                time.sleep(.05)
            with (folder/'neural.log').open('w') as neural_log:
                nn=subprocess.Popen(command,stdout=neural_log,stderr=subprocess.STDOUT);code=nn.wait(timeout=a.seconds+15)
            assert code==0,(folder/'neural.log').read_text()
            metrics=[json.loads(l) for l in (folder/'neural.log').read_text().splitlines() if l.startswith('{')][-1]
            assert metrics['processed_frames']==metrics['present_completed_frames']==metrics['present_submitted_frames']>0
        except Exception as error:failure=repr(error)
        finally:
            if nn is not None and nn.poll() is None:nn.terminate();nn.wait(timeout=10)
            if game.poll() is None:game.terminate()
            game.wait(timeout=25)
    after=status();post_after=json.loads(subprocess.check_output([post,'--status'],text=True))
    source=json.loads((out/(attempt+'_game')/'result.json').read_text())
    row={'cap':cap,'index':i,'before':before,'after':after,'post_after':post_after,'clock':clock,'metrics':metrics,'source':source,
         'runtime_sha256':sha(exe),'model_sha256':sha(model),'command':command,'game_command':game_command,'error':failure}
    row['passed']=failure is None and game.returncode==0 and source['passed'] and all(before[k]==after[k]==0 for k in errors) and post_after['snapshot_status']==0 and post_after['snapshot_expirations']==0
    records.append(row);(out/(a.prefix+'_'+a.phase+'.json')).write_text(json.dumps(records,indent=2)+'\n')
    print('MC_SOURCE_CAP_RESULT',cap,metrics,'source_fps',source.get('hardware_window'),flush=True)
    assert row['passed'],row
print('MC_SOURCE_CAP_BENCH_PASS',flush=True)
