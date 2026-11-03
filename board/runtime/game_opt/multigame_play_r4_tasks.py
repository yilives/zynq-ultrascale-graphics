"""Real Neverball -> owned snapshot -> original CNN -> LCD, with guarded owners."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time


def guarded_adapter(base):
    class Guarded(base):
        def __init__(self):super().__init__();self.managed=[]
        def require_locks(self):
            super().require_locks()
            assert not any(p.poll() is None for p in self.managed),'A live renderer/postprocessor still owns hardware'
    return Guarded


def run_live(adapter,stage,out,selected_style,seconds,selected_upscaler,game_name,pipeline):
    out.mkdir()
    sys.path.insert(0,'/opt/rasterix/experimental')
    import rasterix_games as games
    from game_runtime_support import GpuRecoveryGuard,GameLog
    GpuRecoveryGuard().check()
    from multi_game_r4 import prepare as prepare_game,TITLES
    policies=json.loads((stage/'multigame-play-r4-policy.json').read_text())
    policy=policies[game_name];binary=policy['neural_binary'];assert binary in ('rix-cfs-early','rix-cfs-poll')
    home=out/'home'
    command,env,cwd=prepare_game(game_name,home,policy['source_profile'],games,out)
    if game_name=='quake':
        import uuid
        at=command.index('-basedir')+1;alias=Path('/tmp')/('gq4-'+uuid.uuid4().hex[:12])
        assert not alias.exists() and not alias.is_symlink();alias.symlink_to(Path(command[at]));command[at]=str(alias)
        assert len(' '.join(command).encode())<255,'Quake startup command limit'
    if game_name=='neverputt':
        at=command.index('--hole');assert command[at+1]=='map-putt/01_easy.sol'
        command[at:at+2]=['--course','holes-putt.txt']
    env.pop('RIX_AUTOPLAY',None);env.pop('TH06_AUTOPLAY',None)
    subprocess.run(['/lib/ld-linux-aarch64.so.1','--list',command[0]],env=env,stdout=subprocess.PIPE,check=True,timeout=10)
    def gpu():return json.loads(subprocess.check_output(['plgpuctl','status'],text=True,timeout=5))
    before=gpu();runs={};game=None;nn=None
    with adapter.lend_post(),GameLog(out/'game.log') as game_log:
        try:
            game=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            adapter.managed.append(game);game_log.attach(game.stdout)
            deadline=time.monotonic()+40
            while gpu()['presented']<before['presented']+3:
                assert game.poll() is None and time.monotonic()<deadline,'No real game source frames'
                assert not game_log.failure and not game_log.errors['transport_errors']
                time.sleep(.1)
            source_a=gpu();probe_start=time.monotonic();time.sleep(3);source_b=gpu()
            source_probe=dict(seconds=time.monotonic()-probe_start,frames=source_b['presented']-source_a['presented'],CNN_enabled=False,FSR_enabled=False)
            source_probe['source_presented_fps']=source_probe['frames']/source_probe['seconds']
            (out/'source-baseline.json').write_text(json.dumps(source_probe,indent=2)+'\n')
            schedule=[('comic-demo','cfs-comic','group',selected_upscaler),('oil-demo','cfs-oil','group',selected_upscaler)]
            schedule=[item for item in schedule if selected_style=='both' or item[1]=='cfs-'+selected_style]
            for label,style,mode,upscaler in schedule:
                prefix=out/label
                initial_post=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                until_settled=time.monotonic()+2
                while initial_post['requested']!=initial_post['active']:
                    assert time.monotonic()<until_settled,'Previous display restore did not settle'
                    time.sleep(.01)
                    initial_post=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                Path(str(prefix)+'.post-initial.json').write_text(json.dumps(initial_post,indent=2)+'\n')
                with (out/(label+'.log')).open('xb') as log:
                    args=[str(stage/binary),'--fsr-schedule','pipeline' if upscaler=='pl-fsr' else 'serial','--frame-pipeline',pipeline,'--backend','pl-int8','--model',str(stage/(style+'.cnn')),
                          '--live','--seconds',str(seconds),'--composition','neural-fsr','--upscaler',upscaler,'--pio-output',mode,'--core-wait','sleep','--hold-last-seconds','10','--dump-prefix',str(prefix),'--dump-last']
                    args+=['--detail-gain','192']
                    if binary=='rix-cfs-poll':args+=['--fsr-notify','cnn-output' if upscaler=='pl-fsr' else 'end']
                    nn=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                adapter.managed.append(nn)
                deadline=time.monotonic()+seconds+30
                while 'NEURAL_OUTPUT_HELD' not in (out/(label+'.log')).read_text():
                    assert nn.poll() is None and time.monotonic()<deadline,'CNN live failed: '+(out/(label+'.log')).read_text()[-1000:]
                    time.sleep(.05)
                text=(out/(label+'.log')).read_text()
                metrics=[json.loads(line) for line in text.splitlines() if line.startswith('{')][-1]
                assert metrics['processed_frames']>0 and metrics['engine_version']==4
                assert metrics['cnn_cycles_per_frame']==462816 and metrics['pio_output']==mode
                assert metrics['display_backend']==('pl-fsr-after-cnn-detail400' if upscaler=='pl-fsr' else 'arm-bilinear-after-cnn-detail400')
                assert metrics['FSR_enabled']==(upscaler=='pl-fsr')
                assert metrics['present_submitted_frames']==metrics['present_completed_frames']==metrics['processed_frames']
                assert 'NEURAL_DISPLAY_READBACK_PASS bytes=1536000' in text
                subprocess.run([games.POST,'--capture',str(prefix)+'.lcd.bin'],check=True,stdout=subprocess.PIPE,timeout=5)
                post=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                Path(str(prefix)+'.post-before.json').write_text(json.dumps(post,indent=2)+'\n')
                # A canceled snapshot copy may still be draining its AXI writes.
                # Wait for idle; never hide an expiry, mode change or NN exit.
                until_idle=time.monotonic()+2
                while post['snapshot_status']&3:
                    assert nn.poll() is None and time.monotonic()<until_idle,'Snapshot cancellation did not drain'
                    assert post['snapshot_expirations']==0,'Snapshot lease expired'
                    time.sleep(.01)
                    post=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                Path(str(prefix)+'.post-final.json').write_text(json.dumps(post,indent=2)+'\n')
                expected_bank=((initial_post['active']>>9)&1)^(metrics['processed_frames']&1)
                expected_word=2|(expected_bank<<9)
                assert post['requested']==post['active']==expected_word,dict(actual=post,expected=expected_word)
                assert post['snapshot_status']==post['snapshot_expirations']==0,post
                cpu=subprocess.run([str(stage/'rix-cnn-fsr'),'--backend','cpu-int8','--model',str(stage/(style+'.cnn')),
                    '--input',str(prefix)+'.input.bin','--output',str(prefix)+'.cpu.bin'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
                assert cpu.returncode==0,cpu.stdout
                assert Path(str(prefix)+'.output.bin').read_bytes()==Path(str(prefix)+'.cpu.bin').read_bytes()
                display=Path(str(prefix)+'.display.bin').read_bytes();capture=Path(str(prefix)+'.lcd.bin').read_bytes()
                assert len(display)==1536000 and len(capture)==12000
                expected=[]
                for y in range(0,480,8):
                    for x in range(0,800,8):
                        value=struct.unpack_from('<I',display,(y*800+x)*4)[0]
                        expected.append(((value>>8)&0xf800)|((value>>5)&0x7e0)|((value>>3)&0x1f))
                mismatches=sum(a!=b for a,b in zip(expected,struct.unpack('<6000H',capture)))
                assert mismatches==0,'Physical LCD sample mismatch: '+str(mismatches)
                nn.terminate();assert nn.wait(timeout=15)==0
                runs[label]=dict(metrics=metrics,cpu_integer_bit_exact=True,display_full_readback=True,
                    lcd_samples=6000,lcd_mismatches=mismatches,post=post,
                    output_sha256=hashlib.sha256(Path(str(prefix)+'.output.bin').read_bytes()).hexdigest())
                (out/'live-progress.json').write_text(json.dumps(runs,indent=2)+'\n')
                print('CNN_GROUP_LIVE_PASS',label,metrics['processed_frames'],metrics['processed_fps'],flush=True)
        finally:
            if nn is not None and nn.poll() is None:
                nn.terminate();nn.wait(timeout=15)
            if game is not None and game.poll() is None:
                if game_name in TITLES:
                    closed=subprocess.run([sys.executable,'/opt/rasterix/experimental/game_x11_control.py','close','--window',TITLES[game_name]],
                        env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=6)
                    (out/'game-close.log').write_bytes(closed.stdout)
                    assert closed.returncode==0,'Normal game close failed'
                else:game.terminate()
                game.wait(timeout=15)
            game_log.finish()
            assert game is not None and game.returncode==0,'Renderer did not exit cleanly'
            assert not game_log.failure and not game_log.errors['transport_errors']
            deadline=time.monotonic()+5
            while True:
                after=gpu()
                assert after['status']==3 and all(after[k]==0 for k in games.ERRORS)
                if len({after[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1:break
                assert time.monotonic()<deadline,'GPU queue did not drain'
                time.sleep(.05)
    return dict(passed=len(runs)==(2 if selected_style=='both' else 1),game=game_name,binary=binary,source_profile=policy['source_profile'],frame_pipeline=pipeline,before=before,after=after,runs=runs,
                source_presented_frames=after['presented']-before['presented'],game_exit=game.returncode,
                transport_errors=game_log.errors,FSR_modes_tested=[selected_upscaler],
                source_without_CNN=source_probe,scope='Real game CNN presentation throughput, not a standalone game-FPS benchmark')





def run_fixed(adapter,stage,out):
    out.mkdir();records=list(stage.glob('multigame-r4-*/result.json'))
    passed=[p for p in records if json.loads(p.read_text()).get('candidate_load_passed') is True and json.loads(p.read_text()).get('passed') is True]
    assert passed,'Complete static CNN+FSR proof must exist before using the demo'
    proof=max(passed,key=lambda p:p.stat().st_mtime);result=json.loads(proof.read_text())
    assert result['fixed']['passed'] and result['original_restore_passed']
    record=dict(passed=True,scope='Reuse prior complete static proof, not a new static pixel run',
        proof_path=str(proof),proof_sha256=hashlib.sha256(proof.read_bytes()).hexdigest())
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    return record
