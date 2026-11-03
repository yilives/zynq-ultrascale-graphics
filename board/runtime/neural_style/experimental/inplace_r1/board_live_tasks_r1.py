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


def run_live(adapter,stage,out):
    sys.path.insert(0,'/opt/rasterix/experimental')
    import rasterix_games as games
    from game_runtime_support import GpuRecoveryGuard,GameLog
    GpuRecoveryGuard().check();games.prepare(['game-runtime','neverball-data'])
    home=out/'home';home.mkdir(mode=0o700)
    command=games.command('neverball',home)
    runtime=games.WORK/'runtime'
    env={k:v for k,v in os.environ.items() if not k.startswith(('RIX_','TH06_','LD_PRELOAD'))}
    env.update(DISPLAY=':0',HOME=str(home),LANG='C',LC_ALL='C',SDL_VIDEODRIVER='x11',SDL_AUDIODRIVER='dummy',
               LD_LIBRARY_PATH=str(runtime/'lib'),SDL_VIDEO_GL_DRIVER=str(runtime/'lib/libGL.so.1'))
    subprocess.run(['/lib/ld-linux-aarch64.so.1','--list',command[0]],env=env,stdout=subprocess.PIPE,check=True,timeout=10)
    def gpu():return json.loads(subprocess.check_output(['plgpuctl','status'],text=True,timeout=5))
    before=gpu();runs={};game=None;nn=None
    with adapter.lend_post(),GameLog(out/'game.log') as game_log:
        try:
            game=subprocess.Popen(command,cwd=games.WORK,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            adapter.managed.append(game);game_log.attach(game.stdout)
            deadline=time.monotonic()+40
            while gpu()['presented']<before['presented']+3:
                assert game.poll() is None and time.monotonic()<deadline,'No real game source frames'
                assert not game_log.failure and not game_log.errors['transport_errors']
                time.sleep(.1)
            for style in ('anime','oil'):
                prefix=out/style
                with (out/(style+'.log')).open('xb') as log:
                    args=[str(stage/'rix-neural-inplace'),'--backend','pl-int8','--model',str(stage/(style+'.cnn')),
                          '--live','--seconds','3','--hold-last-seconds','10','--dump-prefix',str(prefix),'--dump-last']
                    nn=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                adapter.managed.append(nn)
                deadline=time.monotonic()+30
                while 'NEURAL_OUTPUT_HELD' not in (out/(style+'.log')).read_text():
                    assert nn.poll() is None and time.monotonic()<deadline,'CNN live failed: '+(out/(style+'.log')).read_text()[-1000:]
                    time.sleep(.05)
                text=(out/(style+'.log')).read_text()
                metrics=[json.loads(line) for line in text.splitlines() if line.startswith('{')][-1]
                assert metrics['processed_frames']>0 and metrics['engine_version']==3
                assert metrics['cnn_cycles_per_frame']==462816 and metrics['pio_output']=='atomic'
                assert metrics['display_backend']=='pl-bilinear-5x'
                assert metrics['present_submitted_frames']==metrics['present_completed_frames']==metrics['processed_frames']
                assert 'NEURAL_DISPLAY_READBACK_PASS bytes=61440' in text
                subprocess.run([games.POST,'--capture',str(prefix)+'.lcd.bin'],check=True,stdout=subprocess.PIPE,timeout=5)
                post=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                assert post['active']==3 and post['snapshot_status']==post['snapshot_expirations']==0
                cpu=subprocess.run([str(stage/'rix-neural-inplace'),'--backend','cpu-int8','--model',str(stage/(style+'.cnn')),
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
                runs[style]=dict(metrics=metrics,cpu_integer_bit_exact=True,display_full_readback=True,
                    lcd_samples=6000,lcd_mismatches=mismatches,post=post,
                    output_sha256=hashlib.sha256(Path(str(prefix)+'.output.bin').read_bytes()).hexdigest())
                (out/'live-progress.json').write_text(json.dumps(runs,indent=2)+'\n')
                print('CNN_LIVE_STYLE_PASS',style,metrics['processed_frames'],metrics['processed_fps'],flush=True)
        finally:
            if nn is not None and nn.poll() is None:
                nn.terminate();nn.wait(timeout=15)
            if game is not None and game.poll() is None:
                closed=subprocess.run([sys.executable,'/opt/rasterix/experimental/game_x11_control.py','close','--window','Neverball'],
                    env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=6)
                (out/'game-close.log').write_bytes(closed.stdout)
                assert closed.returncode==0,'Normal game close failed'
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
    return dict(passed=len(runs)==2,game='neverball',before=before,after=after,runs=runs,
                source_presented_frames=after['presented']-before['presented'],game_exit=game.returncode,
                transport_errors=game_log.errors,FSR_enabled=False,
                scope='Real game CNN presentation throughput, not a standalone game-FPS benchmark')
