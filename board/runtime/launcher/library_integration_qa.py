"""Final v4 acceptance: all seven new PL-FSR games, menu switches and native pixels."""
import array,ctypes as c,hashlib,json,os,signal,subprocess,sys,time,traceback,uuid
from pathlib import Path

APP=Path('/tmp/rasterix-launcher-v4-library');OLDAPP=Path('/tmp/rasterix-launcher-v3-native')
OUT=Path('/tmp/postproc-tests')/('library-v4-integration-'+uuid.uuid4().hex[:12])
sys.path[:0]=[str(APP),'/tmp/rix-cnn-group-r1','/opt/rasterix/experimental']
from board_profile import OLD,LEGACY,load
from launcher_control import exchange
from library_games import EXPANSION
from game_specs import ALL,TITLES

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gone(pid):
    try:return Path('/proc',str(pid),'stat').read_text().split()[2]=='Z'
    except FileNotFoundError:return True
def save(r):(OUT/'result.json').write_text(json.dumps(r,indent=2)+'\n')
def gpu():
    r=json.loads(subprocess.check_output(['plgpuctl','status']));assert r['status']==3 and all(r[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'));return r

def main():
    OUT.mkdir(mode=0o700);r=dict(passed=False,error=None,fsr_games={},switches=[],menus={},FPGA_programmed=False)
    m,A=load(Path('/tmp/rix-cnn-group-r1/frozen_loader.py'));adapter=A();session=None;player=None;old_stopped=False;ready=None
    def idle():
        state=adapter.snapshot();m.check_idle(state);assert state['cnn']==m.java_cnn_contract(OLD);assert LEGACY.read_text().splitlines()[2]==OLD;return state
    def wait_menu():
        deadline=time.monotonic()+65
        while True:
            assert session.poll() is None,'New menu session exited'
            value=exchange(Path(ready['socket']),'STATUS');post=adapter.post_state()
            if value['phase']=='menu' and post['requested']==post['active'] and post['active']&3==2:return value
            assert value['phase']!='error',value
            assert time.monotonic()<deadline,'Game/menu handoff deadline';time.sleep(.1)
    def inject(operation,key,title):
        if title=='RasterIX · 游戏库':time.sleep(1.2)  # UI observes backend once per second.
        args=[sys.executable,str(APP/'x11_control.py'),operation]+([key] if key else [])+['--window',title]
        q=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=6);assert q.returncode==0,q.stdout
    def latest_game(game,normal=False):
        rows=list(Path('/tmp/rasterix-launcher-runs').glob('menu-'+game+'-*/result.json'));assert rows
        path=max(rows,key=lambda p:p.stat().st_mtime);result=json.loads(path.read_text());assert result['passed'] and result['profile_restored'] and result['exit_code']==0
        assert all(x==0 for x in result['transport_errors'].values())
        if normal:assert result['qa_seconds']==0 and result['qa_autoplay'] is False
        return path,result
    def menu_pixels(label):
        candidates=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:args=(proc/'cmdline').read_bytes().split(b'\0')
            except (FileNotFoundError,ProcessLookupError):continue
            if args and Path(os.fsdecode(args[0])).resolve()==(APP/'rix-launcher').resolve():candidates.append(int(proc.name))
        assert len(candidates)==1
        producer=candidates[0];os.kill(producer,signal.SIGSTOP)
        # Only the software UI producer is frozen. The separate POST owner
        # completes its acknowledged publication and is never interrupted.
        try:capture_menu_pixels(label)
        finally:os.kill(producer,signal.SIGCONT)
    def capture_menu_pixels(label):
        from lcd_native import Device
        frame=Path(ready['work'])/'menu.rgb565';deadline=time.monotonic()+5
        while True:
            raw=frame.read_bytes();time.sleep(.25)
            if raw==frame.read_bytes():break
            assert time.monotonic()<deadline
        assert len(raw)==768000
        device=Device(APP/'menu/librix-menu-native.so')
        try:
            word=device.read(0x58);assert word==device.read(0x54) and word&3==2
            native=(c.c_uint32*384000)();device.library.rix_menu_read_native.argtypes=[c.c_void_p,c.POINTER(c.c_uint32),c.c_size_t];device.library.rix_menu_read_native.restype=c.c_int
            assert device.library.rix_menu_read_native(device.bptr+((word>>9)&1)*0x200000,native,384000)==0
            source=array.array('H');source.frombytes(raw)
            expected=array.array('I',(0xff000000|(((v>>11)<<3)|(v>>13))<<16|((((v>>5)&63)<<2)|(((v>>5)&63)>>4))<<8|((v&31)<<3)|((v&31)>>2) for v in source)).tobytes()
            actual=bytes(native);assert actual==expected,'Native UI full-frame mismatch'
            token=device.read(0x64)&1;assert device.read(0x68)&1==token;device.write(0x64,1);deadline=time.monotonic()+3
            while device.read(0x68)&1==token:assert time.monotonic()<deadline;time.sleep(.001)
            lcd=array.array('H')
            for i in range(6000):device.write(0x6c,i);lcd.append(device.read(0x70)&65535)
            assert lcd.tolist()==[source[y*800+x] for y in range(0,480,8) for x in range(0,800,8)]
            assert word==device.read(0x54)==device.read(0x58) and raw==frame.read_bytes()
            (OUT/(label+'.rgb565')).write_bytes(raw);(OUT/(label+'.display.xrgb')).write_bytes(actual);(OUT/(label+'.lcd')).write_bytes(lcd.tobytes())
            r['menus'][label]=dict(exact_native_pixels=384000,exact_LCD_points=6000,source_sha256=sha(OUT/(label+'.rgb565')),post_word=word)
        finally:device.close()
    try:
        sessions=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:args=(proc/'cmdline').read_bytes().split(b'\0')
            except (FileNotFoundError,ProcessLookupError):continue
            if str(OLDAPP/'session.py').encode() in args:sessions.append(int(proc.name))
        assert len(sessions)==1;os.kill(sessions[0],signal.SIGTERM);deadline=time.monotonic()+125
        while not gone(sessions[0]):assert time.monotonic()<deadline;time.sleep(.1)
        old_stopped=True
        with adapter.locks():r['before']=idle()
        for game in EXPANSION:
            log=OUT/(game+'-fsr.log')
            with log.open('xb') as stream:player=subprocess.Popen([sys.executable,'-B',str(APP/'play_game.py'),game,'--qa-seconds','22','--qa-autoplay','--fsr'],stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
            deadline=time.monotonic()+65
            while player.poll() is None:gpu();assert time.monotonic()<deadline,'FSR game did not stop';time.sleep(.25)
            assert player.returncode==0,log.read_text()[-2500:]
            path,result=latest_game(game);assert result['fsr_requested'] and sum(x['frames'] for x in result['fsr'])>10
            assert all(not x['cpu_pixel_processing_live'] and x['repeated_source_frames']==0 and x['unique_source_frames']==x['frames'] for x in result['fsr'])
            with adapter.locks():idle()
            r['fsr_games'][game]=dict(passed=True,result=result,path=str(path));save(r);print('LIBRARY_V4_FSR_PASS',game,flush=True)
        with (OUT/'session.log').open('xb') as log:session=subprocess.Popen([sys.executable,'-B',str(APP/'session.py'),'--board','--lcd-menu'],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        deadline=time.monotonic()+25
        while ready is None:
            assert session.poll() is None and time.monotonic()<deadline
            for line in (OUT/'session.log').read_text().splitlines():
                if line.startswith('LAUNCHER_SESSION_READY '):ready=json.loads(line.split(' ',1)[1])
            time.sleep(.1)
        status=wait_menu();assert set(status['ready'].split(','))==set(ALL) and len(ALL)==15
        r['ready']=ready;menu_pixels('page1')
        for game,fsr in [('arcade-sokoban',False),('rrootage',True),('neverball',False)]:
            before=gpu();reply=exchange(Path(ready['socket']),'START '+game+(' fsr' if fsr else ''));assert reply['ok']=='1'
            deadline=time.monotonic()+40
            while gpu()['presented']<before['presented']+3:
                assert session.poll() is None and time.monotonic()<deadline
                assert exchange(Path(ready['socket']),'STATUS')['phase']!='error';time.sleep(.1)
            time.sleep(1)
            if game=='arcade-sokoban':inject('key','Return',TITLES[game]);inject('key','Right',TITLES[game])
            elif game=='rrootage':
                for i in range(3):inject('key','z',TITLES[game]);time.sleep(.4)
            else:inject('click',None,TITLES[game])
            time.sleep(3);exchange(Path(ready['socket']),'STOP');wait_menu();path,result=latest_game(game,True)
            if fsr:assert sum(x['frames'] for x in result['fsr'])>0
            r['switches'].append(dict(game=game,FSR=fsr,result=result,path=str(path)));save(r)
        inject('key','Page_Down','RasterIX · 游戏库');time.sleep(.7);menu_pixels('page2')
        r['final_status']=wait_menu();r['final_state']=adapter.snapshot();r['receipt']=LEGACY.read_text()
        sd=Path('/media/sd-mmcblk1p1');r['SD_boot_sha256']={n:sha(sd/n) for n in ('BOOT.BIN','system.dtb')}
        r['library_manifest']=json.loads((APP/'library/manifest.json').read_text())
        r['runtime_sha256']={n:sha(APP/n) for n in json.loads((APP/'runtime-manifest.json').read_text())['files']}
        r['adopted_session_pid']=session.pid
        r['passed']=len(r['fsr_games'])==7 and len(r['switches'])==3 and len(r['menus'])==2
    except BaseException:r['error']=traceback.format_exc()
    finally:
        if not r['passed']:
            if player is not None and player.poll() is None:
                player.terminate()
                try:player.wait(timeout=40)
                except subprocess.TimeoutExpired:r['drain_error']='Player remains live; do not reconfigure'
            if session is not None and session.poll() is None:
                session.terminate()
                try:session.wait(timeout=90)
                except subprocess.TimeoutExpired:r['session_drain_error']='Menu session remains live'
            if old_stopped and (player is None or player.poll() is not None) and (session is None or session.poll() is not None):
                try:
                    with adapter.locks():idle()
                    with (OUT/'old-menu-restored.log').open('xb') as log:subprocess.Popen([sys.executable,'-B',str(OLDAPP/'session.py'),'--board','--lcd-menu'],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
                    r['fallback_old_menu_started']=True
                except BaseException:r['fallback_error']=traceback.format_exc()
        save(r);print('LIBRARY_V4_INTEGRATION_COMPLETE',r['passed'],str(OUT),flush=True)
if __name__=='__main__':main()
