#!/usr/bin/env python3
"""Real ClassiCube -> leased snapshot -> FPGA CNN -> full-detail LCD QA."""
import argparse, hashlib, json, os, subprocess, tarfile, time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,default=Path('/tmp/rix-mc-style'))
p.add_argument('--attempt',default='cc_style_v1')
p.add_argument('--model-dir',type=Path,default=Path('/opt/rasterix/neural-style/models'))
p.add_argument('--models',nargs='+',default=['oil','anime'])
p.add_argument('--seconds',type=int,default=12)
p.add_argument('--frame-pipeline',choices=('serial','overlap'))
p.add_argument('--snapshot-workers',type=int,choices=(1,2,4))
p.add_argument('--snapshot-copy',choices=('paired','neon'))
p.add_argument('--source-fps-limit',type=int,choices=(30,60,120),default=120)
a=p.parse_args()
assert a.attempt.replace('_','').isalnum() and len(a.attempt)<32
assert all(n.replace('-','').isalnum() for n in a.models)
out=Path('/tmp/postproc-tests')/a.attempt;out.mkdir(parents=True,exist_ok=False)
exe=a.root/'bin/rix-neural-style'
post='/opt/rasterix/postproc-touch/bin/rix-superres'
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
post_status=lambda:json.loads(subprocess.check_output([post,'--status'],text=True))
errors=('read_errors','write_errors','timeouts','underflows','scan_errors')
assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
record={'before':status(),'post_before':post_status(),'runtime_sha256':sha(exe),'source_fps_limit':a.source_fps_limit,'runs':{},'error':None}
game_log=open(out/'launcher.log','w')
game=subprocess.Popen(['rix-classicube','--seconds','180','--attempt',a.attempt+'_game','--autoplay','--fps-limit',str(a.source_fps_limit)],stdout=game_log,stderr=subprocess.STDOUT)
nn=None
try:
    native_log=Path('/tmp/postproc-tests')/(a.attempt+'_game')/'game.log'
    deadline=time.monotonic()+60
    while not native_log.exists() or 'RIX_MEASURE_BEGIN' not in native_log.read_text():
        assert game.poll() is None and time.monotonic()<deadline,'MC startup failed'
        time.sleep(.2)
    # Each style has an uninstrumented throughput pass and a separate frozen
    # diagnostic pass. Dump/readback time must not be sold as throughput.
    for style in a.models:
        model=a.model_dir/(style+'.cnn');prefix=out/style
        base=[str(exe),'--model',str(model),'--backend','pl-int8','--live','--composition','mc-residual','--strength','128']
        for rect in ('0,0,400,34','0,192,400,48','194,114,12,12'):base+=['--protect-rect',rect]
        for flag,value in (('--frame-pipeline',a.frame_pipeline),('--snapshot-workers',a.snapshot_workers),('--snapshot-copy',a.snapshot_copy)):
            if value is not None:base+=[flag,str(value)]
        with (out/(style+'-performance.log')).open('w') as log:
            result=subprocess.run(base+['--seconds',str(a.seconds)],stdout=log,stderr=subprocess.STDOUT,timeout=a.seconds+20)
        assert result.returncode==0,(out/(style+'-performance.log')).read_text()
        perf=[json.loads(l) for l in (out/(style+'-performance.log')).read_text().splitlines() if l.startswith('{')][-1]
        with (out/(style+'.log')).open('w') as log:
            nn=subprocess.Popen(base+['--seconds','2','--dump-prefix',str(prefix),'--dump-last','--hold-last-seconds','20'],stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+20
            while 'NEURAL_OUTPUT_HELD' not in (out/(style+'.log')).read_text():
                assert nn.poll() is None and time.monotonic()<deadline,(out/(style+'.log')).read_text()
                time.sleep(.1)
            subprocess.run([post,'--capture',str(prefix)+'.lcd.bin'],check=True,stdout=subprocess.DEVNULL)
            observed=post_status()
            nn.terminate();assert nn.wait(timeout=10)==0
        nn=None
        text=(out/(style+'.log')).read_text()
        metrics=[json.loads(l) for l in text.splitlines() if l.startswith('{')][-1]
        assert 'NEURAL_DISPLAY_READBACK_PASS bytes=1536000' in text
        assert metrics['processed_frames']==metrics['present_submitted_frames']==metrics['present_completed_frames']
        assert metrics['cnn_cycles_per_frame']==414738 and metrics['engine_version']==2
        assert observed['active']&0x33==2 and observed['snapshot_status']&3==0 and observed['snapshot_expirations']==0
        data={'performance':perf,'diagnostic':metrics,'post':observed,'model_sha256':sha(model),'full_bank_readback':True}
        record['runs'][style]=data
        (out/(style+'.display.json')).write_text(json.dumps({'bytes':1536000,'sha256':sha(Path(str(prefix)+'.display.bin'))})+'\n')
        # Single-file artifacts remain small enough for the existing UART pull.
        with tarfile.open(out.with_name(a.attempt+'_'+style).with_suffix('.tar.gz'),'w:gz') as tf:
            for name in (style+'.input.bin',style+'.output.bin',style+'.source565.bin',style+'.display.json',style+'.frame.json',style+'.lcd.bin',style+'.log',style+'-performance.log'):
                tf.add(out/name,arcname=name)
        print('MC_STYLE_QA_RUN',style,json.dumps(data),flush=True)
except Exception as error:
    record['error']=repr(error)
finally:
    if nn is not None and nn.poll() is None:nn.terminate();nn.wait(timeout=10)
    # Existing launcher propagates SIGTERM to native, which drains GPU/DMA.
    if game.poll() is None:game.terminate()
    record['game_exit']=game.wait(timeout=25);game_log.close()
    record['after']=status();record['post_after']=post_status()
    native_result=Path('/tmp/postproc-tests')/(a.attempt+'_game')/'result.json'
    record['game_result']=json.loads(native_result.read_text()) if native_result.exists() else None
    record['passed']=record['error'] is None and record['game_exit']==0 and len(record['runs'])==len(a.models) and all(record['before'][k]==record['after'][k]==0 for k in errors)
    record['runtime_unchanged']=sha(exe)==record['runtime_sha256']
    (out.with_suffix('.json')).write_text(json.dumps(record,indent=2)+'\n')
    print('MC_STYLE_QA_RESULT',json.dumps(record),flush=True)
raise SystemExit(0 if record['passed'] and record['runtime_unchanged'] else 1)
