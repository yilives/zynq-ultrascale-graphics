"""Validate pacing changes through the real v23 menu player, then retain or undo."""
import hashlib,json,os,signal,subprocess,sys,time,traceback,uuid
from pathlib import Path

S=Path('/tmp/rix-cnn-group-r1');sys.path.insert(0,str(S))
from board_profile import OLD,LEGACY,load


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,r):Path(p).write_text(json.dumps(r,indent=2)+'\n')
def gone(pid):
    try:return Path('/proc',str(pid),'stat').read_text().split()[2]=='Z'
    except FileNotFoundError:return True


def main():
    app=Path('/tmp/rasterix-launcher-v3-native');out=S/('native-r4-'+uuid.uuid4().hex[:12]);out.mkdir(mode=0o700)
    policy=json.loads((S/'native-r4-release.json').read_text())
    assert sha(S/'game_specs_r4.py')==policy['new_sha256'] and sha(app/'game_specs.py')==policy['old_sha256']
    m,Adapter=load(S/'frozen_loader.py');adapter=Adapter();menu_stopped=False;applied=False;child=None
    result=dict(passed=False,error=None,FPGA_programmed=False,SD_written=False,runs={})
    save(out/'result.json',result)
    def idle():
        state=adapter.snapshot();m.check_idle(state);assert state['cnn']==m.java_cnn_contract(OLD)
        assert LEGACY.read_text().splitlines()[:3]==['RIX_FSR_PL_ACTIVE_V1',Path('/proc/sys/kernel/random/boot_id').read_text().strip(),OLD]
        return state
    def replace(raw,expected):
        target=app/'game_specs.py';assert sha(target)==expected and not target.is_symlink()
        incoming=app/('game_specs.py.r4-'+uuid.uuid4().hex)
        fd=os.open(str(incoming),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,target.stat().st_mode&0o777)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(incoming,target)
    def healthy(value):assert value['status']==3 and all(value[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    def run(game,phase,fsr=False):
        nonlocal child
        sys.path.insert(0,'/opt/rasterix/experimental');from game_runtime_support import DisplayStatus
        with adapter.locks():idle()
        label=phase+'-'+game+('-fsr' if fsr else '');folder=out/label;folder.mkdir()
        command=[sys.executable,'-B',str(app/'play_game.py'),game,'--qa-seconds','18']+(['--fsr'] if fsr else [])
        device=DisplayStatus();samples=[];renderer=None;began=time.monotonic()
        try:
            before=device.read();healthy(before)
            with (folder/'player.log').open('xb') as log:
                child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            deadline=time.monotonic()+60
            while child.poll() is None:
                elapsed=time.monotonic()-began;value=device.read();healthy(value)
                if 8<=elapsed<=16:samples.append(dict(seconds=elapsed,presented=value['presented']))
                if renderer is None and value['presented']>before['presented']+2:
                    name='neverball' if game=='neverball' else 'quake3e'
                    pids=subprocess.check_output(['pidof',name],text=True).split();assert len(pids)==1
                    proc=Path('/proc',pids[0]);args=[x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
                    env=dict(x.decode().split('=',1) for x in (proc/'environ').read_bytes().split(b'\0') if b'=' in x)
                    renderer=dict(pid=int(pids[0]),command=args,RIX_environment={k:v for k,v in env.items() if k.startswith('RIX_')},binary_sha256=sha(args[0]))
                if time.monotonic()>deadline:
                    child.terminate();child.wait(timeout=30);raise RuntimeError('Public game exceeded normal stop deadline')
                time.sleep(.1)
            assert child.returncode==0,(folder/'player.log').read_text()[-2000:]
            after=device.read();healthy(after)
        finally:device.close()
        assert len(samples)>=30 and renderer is not None
        first,last=samples[0],samples[-1];elapsed=last['seconds']-first['seconds'];frames=(last['presented']-first['presented'])&0xffffffff
        assert elapsed>=6 and frames>0
        text=(folder/'player.log').read_text();records=[json.loads(row.split(' ',1)[1]) for row in text.splitlines() if row.startswith('LAUNCHER_GAME_RESULT ')]
        assert len(records)==1 and records[0]['passed'] and records[0]['profile_restored']
        if game=='neverball':assert renderer['RIX_environment'].get('RIX_PRESENT_STRATEGY')==('async' if phase=='candidate' else None)
        else:
            args=renderer['command'];assert args[args.index('com_maxfps')+1]==('60' if phase=='candidate' else '30')
        if fsr:
            assert records[0]['fsr'] and sum(r['frames'] for r in records[0]['fsr'])>0
            assert all(r['cpu_pixel_processing_live'] is False and r['repeated_source_frames']==0 for r in records[0]['fsr'])
        with adapter.locks():state=idle()
        r=dict(passed=True,game=game,phase=phase,FSR_enabled=fsr,frames=frames,seconds=elapsed,fps=frames/elapsed,
            samples=samples,renderer=renderer,player=records[0],after=state,source_sha256=sha(app/'game_specs.py'))
        result['runs'][label]=r;save(folder/'result.json',r);save(out/'result.json',result)
        print('NATIVE_R4_RUN_PASS',label,r['fps'],flush=True)
    try:
        sessions=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:args=(proc/'cmdline').read_bytes().split(b'\0')
            except (FileNotFoundError,ProcessLookupError):continue
            if str(app/'session.py').encode() in args:sessions.append(int(proc.name))
        assert len(sessions)==1
        os.kill(sessions[0],signal.SIGTERM);deadline=time.monotonic()+125
        while not gone(sessions[0]):assert time.monotonic()<deadline;time.sleep(.1)
        menu_stopped=True
        with adapter.locks():result['before']=idle()
        for game in ('neverball','quake3'):run(game,'baseline')
        original=(app/'game_specs.py').read_bytes();assert hashlib.sha256(original).hexdigest()==policy['old_sha256']
        (out/'original-game_specs.py').write_bytes(original);(out/'original-game_specs.py').chmod(0o600)
        with adapter.locks():idle();replace((S/'game_specs_r4.py').read_bytes(),policy['old_sha256']);applied=True
        for game in ('neverball','quake3'):run(game,'candidate')
        result['gains_percent']={game:100*(result['runs']['candidate-'+game]['fps']/result['runs']['baseline-'+game]['fps']-1) for game in ('neverball','quake3')}
        assert all(gain>10 for gain in result['gains_percent'].values()),'Public v23 did not reproduce the source gains'
        for game in ('neverball','quake3'):run(game,'candidate',True)
        result['adopted']=True
    except BaseException:result['error']=traceback.format_exc()
    finally:
        safe=False
        try:
            assert child is None or child.poll() is not None,'Public player is still draining; no menu restart'
            with adapter.locks():
                result['after']=idle()
                if applied and not result.get('adopted'):
                    replace((out/'original-game_specs.py').read_bytes(),policy['new_sha256']);result['source_rollback']=True
                result['active_source_sha256']=sha(app/'game_specs.py');safe=True
        except BaseException:result['teardown_error']=traceback.format_exc()
        if menu_stopped and safe:
            try:
                with (out/'menu.log').open('xb') as log:
                    menu=subprocess.Popen([sys.executable,'-B',str(app/'session.py'),'--board','--lcd-menu'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+30;ready=None
                while ready is None:
                    assert menu.poll() is None and time.monotonic()<deadline
                    for line in (out/'menu.log').read_text().splitlines():
                        if line.startswith('LAUNCHER_SESSION_READY '):ready=json.loads(line.split(' ',1)[1])
                    time.sleep(.1)
                sys.path.insert(0,str(app));from launcher_control import exchange
                while True:
                    status=exchange(Path(ready['socket']),'STATUS');post=adapter.post_state()
                    if status.get('phase')=='menu' and post['active']==2:break
                    assert time.monotonic()<deadline;time.sleep(.1)
                result['menu']=dict(ready=ready,status=status,post=post,pid=menu.pid)
            except BaseException:result['menu_error']=traceback.format_exc()
        result['passed']=result.get('adopted') is True and result['error'] is None and safe and 'menu' in result
        save(out/'result.json',result);print('NATIVE_R4_COMPLETE',result['passed'],str(out),flush=True)
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
