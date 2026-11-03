#!/usr/bin/env python3
"""Eight fixed game entries, optional FPGA FSR, and fail-closed profile return."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from game_specs import ALL, TITLES, prepare
from java_profile import Profile, LOCK_NAMES, OLD_BIT, sha
from library_games import CLIENTS as EXPANSION_CLIENTS

STOP=False
def stop(*_):
    global STOP
    STOP=True

class LaunchCancelled(Exception):
    pass

def launch_checkpoint():
    if STOP:raise LaunchCancelled()

def close_window(child, app, title, path, seconds=20):
    """A stop during native initialization waits for its real close protocol."""
    deadline=time.monotonic()+seconds
    with path.open('ab') as log:
        while child.poll() is None:
            result=subprocess.run(['python3',str(app/'x11_control.py'),'close','--window',title],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=5)
            log.write(result.stdout);log.flush()
            if result.returncode==0:return 'WM_DELETE_WINDOW'
            if time.monotonic()>=deadline:raise RuntimeError('Named game window never became ready for normal close')
            time.sleep(.2)
    return 'already-exited'

def acquire(name):
    fd=os.open('/tmp/'+name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    stream=os.fdopen(fd,'a+')
    try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BaseException:stream.close();raise
    return stream

def summary(text):
    rows=[json.loads(row) for row in text.splitlines() if row.startswith('{"backend":')]
    assert len(rows)==1,'Expected exactly one FSR completion record'
    result=rows[0]
    assert result['backend']=='FPGA PL EASU12 + RCAS5 fixed point'
    assert result['cpu_pixel_processing_live'] is False
    assert result['frames']>=0 and result['unique_source_frames']==result['frames']
    assert result['repeated_source_frames']==0 and result['prefetch_lease_expirations']==0
    return result

class Fsr:
    def __init__(self, path, out, GameLog):
        self.path,self.out,self.GameLog=Path(path),out,GameLog
        self.child=None;self.protocol_child=None;self.log=None;self.results=[]
    def preflight(self):
        child=subprocess.Popen([str(self.path),'--protocol-check'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.protocol_child=child
        try:
            text,_=child.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                # Never SIGKILL a PL AXI owner's fail-stop process.
                raise RuntimeError('FSR preflight still owns AXI; cold recovery required')
            raise
        (self.out/'fsr-protocol.log').write_bytes(text)
        assert child.returncode==0,'FSR protocol rejected this PL/receipt'
    def golden(self, app):
        self.protocol_child=subprocess.Popen([str(self.path),'--input',str(app/'java/qa/tiles.rgb565'),
            '--output',str(self.out/'fsr-golden.xrgb'),'--no-present','--verify-output',str(app/'java/qa/tiles.xrgb')],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:text,_=self.protocol_child.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            self.protocol_child.terminate()
            try:self.protocol_child.wait(timeout=15)
            except subprocess.TimeoutExpired:raise RuntimeError('FSR golden AXI owner did not drain')
            raise
        (self.out/'fsr-golden.log').write_bytes(text)
        assert self.protocol_child.returncode==0 and b'PASS FSR_PL_FULL_FRAME_GOLDEN 384000 pixels' in text
        assert sha(self.out/'fsr-golden.xrgb')==sha(app/'java/qa/tiles.xrgb')
    def start(self):
        index=len(self.results)
        self.log=self.GameLog(self.out/('fsr-%d.log'%index));self.log.__enter__()
        self.child=subprocess.Popen([str(self.path),'--live','--seconds','3600',
            '--output',str(self.out/('fsr-%d-last.xrgb'%index))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.log.attach(self.child.stdout)
    def finish(self):
        if self.protocol_child is not None and self.protocol_child.poll() is None:
            raise RuntimeError('FSR protocol process retains hardware ownership')
        if self.child is None:return
        if self.child.poll() is None:
            self.child.terminate()
            try:self.child.wait(timeout=15)
            except subprocess.TimeoutExpired:raise RuntimeError('FSR drain timeout; AXI owner remains alive')
        self.log.finish()
        assert self.child.returncode==0,'FPGA FSR failed'
        result=summary(self.log.path.read_text());self.results.append(result)
        self.log.__exit__(None,None,None);self.log=None;self.child=None
    def poll(self):
        if self.child is not None and self.child.poll() is not None:
            self.finish();self.start() # A normal one-hour segment, not a game time limit.
    def owns_hardware(self):
        return any(child is not None and child.poll() is None for child in (self.child,self.protocol_child))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('game',choices=ALL)
    parser.add_argument('--fsr',action='store_true')
    parser.add_argument('--qa-seconds',type=int,default=0)
    parser.add_argument('--qa-autoplay',action='store_true')
    parser.add_argument('--qa-golden',action='store_true')
    args=parser.parse_args()
    assert os.geteuid()==0 and (args.qa_seconds==0 or 5<=args.qa_seconds<=180)
    assert not args.qa_autoplay or args.qa_seconds>=20,'Synthetic input is restricted to bounded QA'
    assert not args.qa_golden or (args.fsr and args.game=='minecraft-java' and args.qa_seconds)
    app=Path(__file__).resolve().parent
    sys.path.insert(0,'/opt/rasterix/experimental')
    import rasterix_games as games
    from game_runtime_support import DisplayStatus,GameLog,GpuRecoveryGuard
    def status():
        # A cached /dev/plgpu_display fd pins its module across whole-PL loads.
        # Every telemetry sample must release the device before any transition.
        device=DisplayStatus()
        try:return device.read()
        finally:device.close()
    locks={};guard=GpuRecoveryGuard();child=None;profile=None;fsr=None;game_log=None
    attempt='menu-'+args.game+'-'+uuid.uuid4().hex[:12]
    out=Path('/tmp/rasterix-launcher-runs')/attempt;out.mkdir(mode=0o700,parents=True)
    record=dict(passed=False,game=args.game,attempt=attempt,fsr_requested=args.fsr,fsr=[],
        qa_seconds=args.qa_seconds,qa_autoplay=args.qa_autoplay,profile_restored=False,error=None)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    unsafe=False;began=time.monotonic();before=None
    def save(): (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    try:
        # Nonblocking locks keep stale/incompatible clients from deadlocking a switch.
        for name in LOCK_NAMES:locks[name]=acquire(name)
        guard.check()
        assert subprocess.run(['pidof',*games.CLIENTS,*EXPANSION_CLIENTS,'java','ClassiCube','th06-rix','rix-fsr-pl','rix-neural-style'],
            stdout=subprocess.PIPE).returncode==1,'GPU client already active'
        receipt=Path('/tmp/rix-fpga-fsr/active-receipt.txt');info=receipt.lstat();rows=receipt.read_text().splitlines()
        assert not receipt.is_symlink() and info.st_uid==0 and not info.st_mode&0o077
        assert len(rows)==4 and rows[0]=='RIX_FSR_PL_ACTIVE_V1' and rows[2]==OLD_BIT
        assert rows[1]==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        before=status()
        assert before['status']==3 and all(before[k]==0 for k in games.ERRORS)
        assert len({before[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
        record.update(boot_id=rows[1],before=before)
        launch_checkpoint()
        command,env,cwd,user_profile=prepare(args.game,app,games,args.qa_autoplay,attempt)
        record['user_profile']=str(user_profile)
        launch_checkpoint()
        if args.game=='minecraft-java':
            profile=Profile(app,out,locks);profile.enter()
        launch_checkpoint()
        # Never hold the POST lock while spawning a child that acquires it.
        locks.pop('rix-superres.lock').close()
        post=json.loads(subprocess.check_output([games.POST,'--status'],text=True))['requested']
        assert post&3 in (0,1),'Stop the owning postprocessor first'
        record['saved_post']=post
        subprocess.run([games.POST,'--pl-mode','nearest','--style','0'],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['plgpuctl','enable'],check=True,stdout=subprocess.DEVNULL)
        if args.fsr:
            path=app/'java/rix-fsr-pl' if profile else Path('/tmp/rix-fpga-fsr/ahead/rix-fsr-pl')
            expected=json.loads((app/'game-contracts.json').read_text())['java_fsr_sha256'] if profile else 'de86960c07507deabb08e79daf6c1adc99315564e041db772ab8152146d3cb13'
            assert sha(path)==expected,'Unapproved FSR executable'
            fsr=Fsr(path,out,GameLog);fsr.preflight()
            if args.qa_golden:fsr.golden(app);record['java_fsr_golden_384000_pixels']=True
        launch_checkpoint()
        dependencies=subprocess.run(['/lib/ld-linux-aarch64.so.1','--list',command[0]],env=env,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15)
        (out/'dependencies.log').write_bytes(dependencies.stdout)
        assert dependencies.returncode==0,'Missing game dependency'
        launch_checkpoint()
        game_before=status();record['game_before']=game_before
        game_log=GameLog(out/'game.log');game_log.__enter__()
        child=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        game_log.attach(child.stdout)
        while child.poll() is None and not STOP:
            current=status()
            if current['status']!=3 or any(current[k] for k in games.ERRORS):raise RuntimeError('GPU error during game')
            if game_log.failure or game_log.errors['transport_errors']:raise RuntimeError('Game transport/log error')
            if fsr:
                if fsr.child is None and not fsr.results and current['presented']>game_before['presented']+1:fsr.start()
                fsr.poll()
            if args.qa_seconds and time.monotonic()-began>=args.qa_seconds:break
            time.sleep(.25)
    except LaunchCancelled:
        record['cancelled_before_launch']=True
    except BaseException as exc:
        record['error']=repr(exc)
    finally:
        # First drain all FSR LOAD/COMPUTE/POST work; only then close the renderer.
        if fsr is not None:
            try:fsr.finish();record['fsr']=fsr.results
            except BaseException as exc:unsafe=True;record['fsr_error']=repr(exc)
            if fsr.owns_hardware():unsafe=True
        if child is not None and child.poll() is None:
            if args.game in ('classicube','touhou'):
                child.terminate();record['shutdown']='engine-SIGTERM'
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:unsafe=True
            else:
                try:
                    record['shutdown']=close_window(child,app,TITLES[args.game],out/'shutdown.log')
                    child.wait(timeout=15)
                except (OSError,RuntimeError,subprocess.TimeoutExpired):
                    child.terminate()
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:unsafe=True
                    record['shutdown']='SIGTERM-fallback';record['error']=record['error'] or 'Normal window close failed'
        if child is not None and child.poll() is None:
            # Renderer only; no active PL master is killed here.
            child.kill();child.wait();unsafe=True
        if game_log is not None:
            game_log.finish()
            record['transport_errors']=game_log.errors
            if game_log.failure or game_log.errors['transport_errors']:unsafe=True
            game_log.__exit__(None,None,None)
        record['exit_code']=child.returncode if child is not None else None
        if child is not None and child.returncode!=0:unsafe=True
        if args.fsr and args.qa_seconds and child is not None and not sum(r['frames'] for r in record['fsr']):
            record['error']=record['error'] or 'No completed FSR frames in bounded QA'
        if before is not None:
            try:
                until=time.monotonic()+5
                while True:
                    after=status()
                    if len({after[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1:break
                    if time.monotonic()>until:raise RuntimeError('GPU queue drain failed')
                    time.sleep(.05)
                record['game_after']=after
                assert after['status']==3 and all(after[k]==0 for k in games.ERRORS)
            except BaseException as exc:unsafe=True;record['drain_error']=repr(exc)
        if not unsafe and before is not None:
            try:
                if 'rix-superres.lock' not in locks:locks['rix-superres.lock']=acquire('rix-superres.lock')
                if profile is not None:profile.leave()
                record['profile_restored']=True
            except BaseException as exc:unsafe=True;record['restore_error']=repr(exc)
        if unsafe:
            if profile is not None:profile.invalidate()
            guard.mark(attempt,dict(reason=record.get('fsr_error') or record.get('restore_error') or record['error'] or 'Unconfirmed game drain',
                exit_code=record['exit_code'],transport_errors=True,after=record.get('game_after')))
        if not unsafe and 'rix-superres.lock' in locks and before is not None:
            # Leave the verified v23 idle convention for the next profile transaction.
            if profile is None:
                locks.pop('rix-superres.lock').close()
                subprocess.run([games.POST,'--pl-mode','bilinear','--style','0'],check=True,stdout=subprocess.DEVNULL)
        record['passed']=((child is not None and child.returncode==0) or record.get('cancelled_before_launch',False)) and not record['error'] and not unsafe
        record['elapsed_seconds']=time.monotonic()-began
        if before is not None:
            try:record['after']=status()
            except Exception as exc:record['after_error']=repr(exc);record['passed']=False
        save()
        for stream in locks.values():stream.close()
    print('LAUNCHER_GAME_RESULT '+json.dumps(record),flush=True)
    return 0 if record['passed'] else 2

if __name__=='__main__':raise SystemExit(main())
