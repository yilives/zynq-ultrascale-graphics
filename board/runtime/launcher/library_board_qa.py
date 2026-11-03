"""Real expansion games on v23: normal player, source/LCD readback, menu return."""
import hashlib,json,mmap,os,signal,struct,subprocess,sys,time,traceback,uuid
from pathlib import Path

BASE=Path('/tmp/rix-library-v4');APP=BASE/'app';OUT=Path('/tmp/postproc-tests')/('library-arcade-'+uuid.uuid4().hex[:12])
sys.path[:0]=[str(APP),'/tmp/rix-cnn-group-r1','/opt/rasterix/experimental']
from board_profile import OLD,LEGACY,load
from game_runtime_support import DisplayStatus
from library_games import ARCADE

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def healthy(r):assert r['status']==3 and all(r[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
def save(r):(OUT/'result.json').write_text(json.dumps(r,indent=2)+'\n')
def gone(pid):
    try:return Path('/proc',str(pid),'stat').read_text().split()[2]=='Z'
    except FileNotFoundError:return True

def main():
    OUT.mkdir(mode=0o700);r=dict(passed=False,error=None,runs={},FPGA_programmed=False)
    oldapp=Path('/tmp/rasterix-launcher-v3-native');m,A=load(Path('/tmp/rix-cnn-group-r1/frozen_loader.py'));adapter=A();child=None;frozen=False;stopped=False;safe=False
    def gpu():
        with_display=DisplayStatus()
        try:value=with_display.read();healthy(value);return value
        finally:with_display.close()
    def idle():
        state=adapter.snapshot();m.check_idle(state);assert state['cnn']==m.java_cnn_contract(OLD);assert LEGACY.read_text().splitlines()[2]==OLD;return state
    try:
        sessions=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:args=(proc/'cmdline').read_bytes().split(b'\0')
            except (FileNotFoundError,ProcessLookupError):continue
            if str(oldapp/'session.py').encode() in args:sessions.append(int(proc.name))
        assert len(sessions)==1;os.kill(sessions[0],signal.SIGTERM);deadline=time.monotonic()+125
        while not gone(sessions[0]):assert time.monotonic()<deadline;time.sleep(.1)
        stopped=True
        with adapter.locks():r['before']=idle()
        for game in ARCADE:
            folder=OUT/game;folder.mkdir();log=folder/'player.log';samples=[];captured=False;before=gpu();began=time.monotonic()
            with log.open('xb') as stream:child=subprocess.Popen([sys.executable,'-B',str(APP/'play_game.py'),game,'--qa-seconds','22','--qa-autoplay'],stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
            while child.poll() is None:
                elapsed=time.monotonic()-began;value=gpu()
                if 4<elapsed<10:samples.append(dict(t=elapsed,frame=value['presented']))
                if elapsed>9 and not captured:
                    pids=subprocess.check_output(['pidof','rix-arcade'],text=True).split();assert len(pids)==1;engine=int(pids[0])
                    os.kill(engine,signal.SIGSTOP);frozen=engine
                    try:
                        deadline=time.monotonic()+5
                        while True:
                            value=gpu()
                            if len({value[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1:break
                            assert time.monotonic()<deadline;time.sleep(.05)
                        post=json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status']))
                        assert post['requested']==post['active']==0 and post['last_source'] in (0x60000000,0x60100000,0x60200000)
                        fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
                        try:
                            with mmap.mmap(fd,0x30000,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=post['last_source']) as mm:
                                raw=mm[:192000];assert raw==mm[:192000]
                        finally:os.close(fd)
                        (folder/'source.rgb565').write_bytes(raw)
                        subprocess.run(['/opt/rasterix/postproc-touch/bin/rix-superres','--capture',str(folder/'lcd.bin')],stdout=subprocess.PIPE,check=True,timeout=5)
                        source=struct.unpack('<96000H',raw);lcd=struct.unpack('<6000H',(folder/'lcd.bin').read_bytes())
                        expected=[source[y*400+x] for y in range(0,240,4) for x in range(0,400,4)]
                        assert expected==list(lcd),'Physical LCD mismatch';assert len(set(source))>4,'Insufficient drawn colors'
                        captured=dict(source_frame=value['frame_id'],source_sha256=sha(folder/'source.rgb565'),lcd_sha256=sha(folder/'lcd.bin'),lcd_points=6000,post=post)
                    finally:os.kill(engine,signal.SIGCONT);frozen=False
                assert time.monotonic()-began<45,'Player did not stop normally';time.sleep(.1)
            assert child.returncode==0,log.read_text()[-3000:]
            text=log.read_text();entries=[json.loads(x.split(' ',1)[1]) for x in text.splitlines() if x.startswith('LAUNCHER_GAME_RESULT ')]
            assert len(entries)==1 and entries[0]['passed'] and entries[0]['profile_restored'] and captured
            player=entries[0];game_result=Path('/tmp/rasterix-launcher-runs')/player['attempt']/'game.log'
            game_text=game_result.read_text();rows=[json.loads(x.split(' ',1)[1]) for x in game_text.splitlines() if x.startswith('ARCADE_RESULT ')]
            assert len(rows)==1 and rows[0]['qa_autoplay'] and rows[0]['updates']>50 and rows[0]['actions']>1 and 'RasterIX' in game_text
            (folder/'game.log').write_text(game_text);assert len(samples)>20
            fps=(samples[-1]['frame']-samples[0]['frame'])/(samples[-1]['t']-samples[0]['t'])
            with adapter.locks():after=idle()
            r['runs'][game]=dict(passed=True,fps=fps,samples=samples,game=rows[0],player=player,capture=captured,after=after);save(r)
            print('LIBRARY_ARCADE_GAME_PASS',game,round(fps,3),flush=True)
        r['source_sha256']=sha(APP/'game_specs.py')
    except BaseException:r['error']=traceback.format_exc()
    finally:
        if frozen:
            try:os.kill(frozen,signal.SIGCONT)
            except ProcessLookupError:pass
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=40)
            except subprocess.TimeoutExpired:r['drain_error']='Player still owns hardware'
        if child is None or child.poll() is not None:
            try:
                with adapter.locks():r['after']=idle();safe=True
            except BaseException:r['restore_error']=traceback.format_exc()
        if stopped and safe:
            try:
                with (OUT/'menu.log').open('xb') as log:menu=subprocess.Popen([sys.executable,'-B',str(oldapp/'session.py'),'--board','--lcd-menu'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL)
                deadline=time.monotonic()+25;ready=None
                while ready is None:
                    assert menu.poll() is None and time.monotonic()<deadline
                    for line in (OUT/'menu.log').read_text().splitlines():
                        if line.startswith('LAUNCHER_SESSION_READY '):ready=json.loads(line.split(' ',1)[1])
                    time.sleep(.1)
                sys.path.insert(0,str(oldapp));from launcher_control import exchange
                while True:
                    status=exchange(Path(ready['socket']),'STATUS');post=adapter.post_state()
                    if status['phase']=='menu' and post['active']==2:break
                    assert time.monotonic()<deadline;time.sleep(.1)
                r['menu']=dict(ready=ready,status=status,post=post)
            except BaseException:r['menu_error']=traceback.format_exc()
        r['passed']=r['error'] is None and len(r['runs'])==len(ARCADE) and safe and 'menu' in r
        save(r);print('LIBRARY_ARCADE_COMPLETE',r['passed'],str(OUT),flush=True)

if __name__=='__main__':main()
