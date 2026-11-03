#!/usr/bin/env python3
"""Unlimited normal play for the five existing ports, with guarded shutdown."""
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

STANDARD = ('tuxracer','neverball','neverputt','quake','quake3')
TITLES = dict(tuxracer='Tuxracer',neverball='Neverball',neverputt='Neverputt',quake='Quakespasm',quake3='Quake3e')
STOP = False
def stop(*_):
    global STOP
    STOP = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('game', choices=STANDARD)
    parser.add_argument('--qa-seconds', type=int, default=0)
    args = parser.parse_args()
    assert os.geteuid() == 0 and (args.qa_seconds == 0 or 5 <= args.qa_seconds <= 120)
    sys.path.insert(0,'/opt/rasterix/experimental')
    import rasterix_games as games
    from game_runtime_support import GpuRecoveryGuard, GameLog
    guard = GpuRecoveryGuard()
    lock = open('/tmp/rasterix-game-launch.lock','a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    guard.check()
    clients = (*games.CLIENTS,'java','ClassiCube','rix-fsr-pl','rix-neural-style')
    assert subprocess.run(['pidof',*clients],stdout=subprocess.PIPE).returncode == 1, 'GPU client active'
    receipt = Path('/tmp/rix-fpga-fsr/active-receipt.txt')
    info = receipt.lstat()
    assert receipt.is_file() and not receipt.is_symlink() and info.st_uid == 0 and not info.st_mode & 0o022
    lines = receipt.read_text().splitlines()
    assert lines[1] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert lines[2] == '035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
    before = games.status()
    assert before['status'] == 3 and not any(before[k] for k in games.ERRORS)
    packages = ['game-runtime']
    if args.game != 'tuxracer':
        packages.append('neverball-data' if args.game.startswith('never') else args.game+'-data')
    games.prepare(packages)
    profile = Path('/opt/rasterix/experimental/profiles') / args.game
    profile.mkdir(parents=True,exist_ok=True)
    command = games.command(args.game,profile)
    attempt = 'menu-'+args.game+'-'+uuid.uuid4().hex[:12]
    out = Path('/tmp/rasterix-launcher-runs') / attempt
    out.mkdir(mode=0o700,parents=True)
    env = {k:v for k,v in os.environ.items() if not k.startswith(('RIX_','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS'))}
    runtime = games.WORK/'runtime'
    env.update(DISPLAY=':0',HOME=str(profile),LANG='C',LC_ALL='C',SDL_VIDEODRIVER='x11',SDL_AUDIODRIVER='dummy',
        LD_LIBRARY_PATH='/usr/lib' if args.game=='tuxracer' else str(runtime/'lib'),
        SDL_VIDEO_GL_DRIVER=str(runtime/'lib/libGL.so.1'))
    if args.game == 'quake3':env['RIX_PRESENT_STRATEGY']='async'
    subprocess.run(['/lib/ld-linux-aarch64.so.1','--list',command[0]],env=env,stdout=subprocess.DEVNULL,check=True)
    post = json.loads(subprocess.check_output([games.POST,'--status'],text=True))['requested']
    assert post & 3 in (0,1), 'Active postprocessor must be stopped by its owning adapter'
    subprocess.run([games.POST,'--pl-mode','nearest','--style','0'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['plgpuctl','enable'],check=True,stdout=subprocess.DEVNULL)
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    began = time.monotonic()
    child = None
    error = None
    shutdown = 'normal-exit'
    after = None
    with GameLog(out/'game.log') as log:
        try:
            child = subprocess.Popen(command,env=env,cwd=games.WORK,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
            log.attach(child.stdout)
            while child.poll() is None and not STOP:
                current = games.status()
                if current['status'] != 3 or any(current[k] != before[k] for k in games.ERRORS):
                    raise RuntimeError('GPU errors changed while playing')
                if log.failure or log.errors['transport_errors']:
                    raise RuntimeError('Game transport/log failure')
                if args.qa_seconds and time.monotonic()-began >= args.qa_seconds:break
                time.sleep(.25)
        except BaseException as exc:
            error = repr(exc)
        finally:
            if child is not None and child.poll() is None:
                helper = Path('/opt/rasterix/experimental/game_x11_control.py')
                try:
                    closed = subprocess.run(['python3',str(helper),'close','--window',TITLES[args.game]],env=env,
                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=5)
                    (out/'shutdown.log').write_bytes(closed.stdout)
                    child.wait(timeout=10)
                    shutdown='WM_DELETE_WINDOW'
                except (subprocess.TimeoutExpired,OSError):
                    child.terminate()
                    shutdown='SIGTERM'
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill();child.wait();shutdown='SIGKILL';error=error or 'Normal shutdown failed'
            code = child.returncode if child else -1
            log.finish()
            # Do not restore POST over active commands or unconfirmed children.
            deadline=time.monotonic()+3
            while True:
                after=games.status()
                ids=[after[k] for k in ('frame_id','swap','copy','presented','last_presented')]
                if len(set(ids))==1 or time.monotonic()>=deadline:break
                time.sleep(.05)
            healthy=after['status']==3 and all(after[k]==before[k] for k in games.ERRORS) and len(set(ids))==1
            passed=code==0 and healthy and not error and not log.errors['transport_errors'] and not log.failure
            if passed:
                subprocess.run([games.POST,'--pl-mode','nearest' if post & 3 == 0 else 'bilinear','--style',str((post>>4)&3)],check=True,stdout=subprocess.DEVNULL)
            else:
                guard.mark(attempt,dict(reason=error or 'Game shutdown/transport failure',exit_code=code,
                    transport_errors=bool(log.errors['transport_errors']),after=after))
            record=dict(passed=passed,game=args.game,attempt=attempt,exit_code=code,error=error,shutdown=shutdown,
                elapsed_seconds=time.monotonic()-began,before=before,after=after,profile=str(profile),qa_seconds=args.qa_seconds)
            (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print('LAUNCHER_GAME_RESULT '+json.dumps(record),flush=True)
    return 0 if passed else 2


if __name__ == '__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('LAUNCHER_GAME_PREFLIGHT_ERROR '+repr(exc),file=sys.stderr,flush=True)
        raise SystemExit(2)
