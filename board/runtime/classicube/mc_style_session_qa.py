#!/usr/bin/env python3
"""Exercise actual wrapper duration, early stop and model failure cleanup."""
import argparse,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--command',default='/tmp/rix-mc-style-v2/mc-style/bin/rix-classicube-style');p.add_argument('--prefix',default='cc_style_session_v1')
a=p.parse_args();out=Path('/tmp/postproc-tests');records=[]
post='/opt/rasterix/postproc-touch/bin/rix-superres'
for case in ('bounded','early','invalid-model'):
    attempt=a.prefix+'_'+case.replace('-','_')
    command=['python3',a.command,'--style','anime','--seconds','10' if case=='bounded' else '60','--autoplay','--attempt',attempt]
    if case=='invalid-model':
        model=out/(attempt+'.cnn');model.write_bytes(b'bad-model');command+=['--model-file',str(model)]
    with (out/(attempt+'.log')).open('w') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        if case=='early':
            deadline=time.monotonic()+30
            while not (out/attempt/'neural.log').exists() or 'NEURAL_FRAME 1 ' not in (out/attempt/'neural.log').read_text():
                assert proc.poll() is None and time.monotonic()<deadline,'No actual neural frame before early-stop test'
                time.sleep(.1)
            time.sleep(.3);proc.terminate()
        code=proc.wait(timeout=45)
    record=json.loads((out/attempt/'session.json').read_text())
    status=json.loads(subprocess.check_output([post,'--status'],text=True))
    assert (code==0)==(case!='invalid-model'),record
    assert record['game_exit']==0 and record['post_restored_after_both_exited'] and (status['requested']&0x33)==1
    assert status['snapshot_status']&3==0 and status['snapshot_expirations']==0
    assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
    record['case']=case;record['post_after']=status;records.append(record)
    (out/(a.prefix+'.json')).write_text(json.dumps(records,indent=2)+'\n')
    print('MC_STYLE_SESSION_CASE',case,code,flush=True)
print('MC_STYLE_SESSION_QA_PASS',flush=True)
