#!/usr/bin/env python3
"""Comparable game trials, persistent profiles and measured FPGA presentation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import time

import rasterix_games as games
from game_runtime_support import GameLog,GpuRecoveryGuard


def run(a):
    assert os.geteuid() == 0
    assert re.fullmatch(r'[a-z0-9_-]{1,48}', a.attempt)
    lock = open('/tmp/rasterix-game-launch.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    recovery=GpuRecoveryGuard()
    recovery.check()
    active = subprocess.run(['pidof', *games.CLIENTS], stdout=subprocess.PIPE)
    assert active.returncode == 1 and not active.stdout, 'Another GPU client is running'
    for name in ('rix_dma_proxy', 'plgpu_display'):
        if name + ' ' not in Path('/proc/modules').read_text():
            subprocess.run(['insmod', '/opt/rasterix/modules/'+name+'.ko'], check=True)
    before = games.status()
    assert before['status'] == 3 and before['config'] == 0x9adb505e
    assert not any(before[k] for k in games.ERRORS)
    packages = ['game-runtime']
    if a.game not in ('glx-probe', 'tuxracer'):
        packages.append('neverball-data' if a.game.startswith('never') else a.game+'-data')
    games.prepare(packages)
    output = games.WORK / 'results' / a.attempt
    output.mkdir(parents=True, exist_ok=False)
    home = output / 'home' if a.fresh_profile else Path('/opt/rasterix/experimental/profiles') / a.game
    home.mkdir(parents=True, exist_ok=True)
    runtime = games.WORK / ('runtime-baseline' if a.baseline_runtime else 'runtime')
    command = games.command(a.game, home, a.tuning, runtime)
    env = os.environ.copy()
    library = '/usr/lib' if a.game == 'tuxracer' else str(runtime / 'lib')
    env.update(DISPLAY=':0', SDL_VIDEODRIVER='x11', SDL_AUDIODRIVER='dummy',
               SDL_VIDEO_GL_DRIVER=str(runtime / 'lib/libGL.so.1'),
               LD_LIBRARY_PATH=library, HOME=str(home), LANG='C', LC_ALL='C', RIX_FRAME_METRICS='1')
    if a.game=='quake3':
        # This engine benefits from overlap with the threaded uploader.
        # Teardown still drains DMA before freeing command storage.
        env['RIX_PRESENT_STRATEGY']='async'
    if a.no_vertex_cache:
        env['RIX_VERTEX_CACHE'] = '0'
    else:
        env.pop('RIX_VERTEX_CACHE', None)
    deps = subprocess.run(['/lib/ld-linux-aarch64.so.1', '--list', command[0]], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / 'dependencies.log').write_bytes(deps.stdout)
    assert deps.returncode == 0, deps.stdout.decode(errors='replace')
    runtime_hashes = {command[0]: games.sha(Path(command[0]))}
    if a.game != 'tuxracer':
        runtime_hashes[str(runtime / 'lib/libGL.so.1')] = games.sha(runtime / 'lib/libGL.so.1')
    subprocess.run([games.POST, '--pl-mode', a.filter, '--style', str(games.STYLES[a.style])], check=True)
    subprocess.run(['plgpuctl', 'enable'], check=True)
    samples, input_results, captures = [], [], {}
    began = time.monotonic()
    reason = 'process exited'
    shutdown_method = 'already exited'
    clicked = False
    with GameLog(output / 'game.log') as log:
        child = subprocess.Popen(command, env=env, cwd=games.WORK, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log.attach(child.stdout)
        stopped = False
        try:
            while child.poll() is None:
                sample = games.status()
                sample['elapsed_s'] = time.monotonic() - began
                samples.append(sample)
                if sample['status'] != 3 or any(sample[k] != before[k] for k in games.ERRORS):
                    reason = 'hardware error'
                    break
                if a.autoplay and a.game in ('neverball','neverputt') and not clicked and sample['elapsed_s'] >= 6:
                    title = 'Neverball' if a.game == 'neverball' else 'Neverputt'
                    helper=Path(__file__).with_name('game_x11_control.py')
                    if not helper.exists():helper=games.WORK/'runtime/bin/game_x11_control.py'
                    injected = subprocess.run(['python3', str(helper), 'click', '--window', title], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    input_results.append({'returncode':injected.returncode, 'output':injected.stdout.decode(errors='replace')})
                    if injected.returncode:
                        reason='input injection failed'
                        break
                    clicked = True
                if a.autoplay and a.game=='tuxracer' and not clicked and sample['elapsed_s']>=6:
                    helper=Path(__file__).with_name('game_x11_control.py')
                    if not helper.exists():helper=games.WORK/'runtime/bin/game_x11_control.py'
                    for key in ('Return','p','Return'):
                        injected=subprocess.run(['python3',str(helper),'key',key,'--window','Tuxracer'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                        input_results.append({'key':key,'returncode':injected.returncode,'output':injected.stdout.decode(errors='replace')})
                        if injected.returncode:
                            reason='input injection failed'
                            break
                        time.sleep(.8)
                    clicked=True
                    if reason=='input injection failed':break
                if sample['elapsed_s'] >= a.seconds:
                    reason = 'duration limit'
                    break
                if log.failure:
                    reason = 'diagnostic capture failure'
                    break
                time.sleep(.5)
            # Performance samples end BEFORE pausing or taking screenshots.
            if a.capture and child.poll() is None and reason == 'duration limit':
                target = Path('/tmp/postproc-tests') / ('games-'+a.attempt)
                target.parent.mkdir(exist_ok=True)
                # A leased PL snapshot needs a new completed GPU frame. Acquire
                # while the game runs; its pixels remain owned throughout read.
                with (output/'capture.log').open('wb') as caplog:
                    code=subprocess.call([games.POST,'--snapshot',str(target)+'.bin'],stdout=caplog,stderr=subprocess.STDOUT)
                path=Path(str(target)+'.bin')
                captures['frame']={'returncode':code,'path':str(path),'sha256':games.sha(path) if path.exists() else None,'source':'leased PL snapshot while rendering; LCD below may show a later frame'}
                child.send_signal(signal.SIGSTOP)
                stopped = True
                # Drain commands that were already submitted by worker threads.
                previous = games.status()['presented']
                for _ in range(12):
                    time.sleep(.1)
                    current = games.status()['presented']
                    if current == previous:
                        break
                    previous = current
                with (output/'capture.log').open('ab') as caplog:
                    for label,arguments in [('lcd',['--capture',str(target)+'-lcd.bin'])]:
                        code = subprocess.call([games.POST,*arguments],stdout=caplog,stderr=subprocess.STDOUT)
                        path = Path(str(target)+('.bin' if label=='frame' else '-lcd.bin'))
                        captures[label] = {'returncode':code, 'path':str(path), 'sha256':games.sha(path) if path.exists() else None}
        finally:
            if stopped:
                child.send_signal(signal.SIGCONT)
            if child.poll() is None:
                titles={'neverball':'Neverball','neverputt':'Neverputt','quake':'Quakespasm','quake3':'Quake3e','tuxracer':'Tuxracer'}
                helper=Path(__file__).with_name('game_x11_control.py')
                if not helper.exists():helper=games.WORK/'runtime/bin/game_x11_control.py'
                if a.game in titles and reason=='duration limit':
                    close=subprocess.run(['python3',str(helper),'close','--window',titles[a.game]],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                    (output/'shutdown.log').write_bytes(close.stdout)
                    if close.returncode==0:
                        try:
                            child.wait(timeout=4)
                            shutdown_method='WM_DELETE_WINDOW'
                        except subprocess.TimeoutExpired:
                            pass
                if child.poll() is None:
                    shutdown_method='SIGTERM fallback'
                    child.terminate()
            try:
                exit_code = child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                exit_code = child.wait()
                reason = 'forced shutdown'
    after = games.status()
    # Warm-up and asset loading are excluded explicitly, with identical windows
    # for before/after runs. Keep every original sample for independent audit.
    steady = [s for s in samples if 12 <= s['elapsed_s'] <= a.seconds]
    windows = []
    for first,last in zip(steady,steady[1:]):
        seconds = last['elapsed_s']-first['elapsed_s']
        frames = (last['presented']-first['presented']) & 0xffffffff
        windows.append({'seconds':seconds, 'fps':frames/seconds,
                        'gpu_ms_per_frame':((last['gpu_busy_cycles']-first['gpu_busy_cycles'])&0xffffffff)/100000/frames if frames else None,
                        'command_beats_per_frame':((last['command_beats']-first['command_beats'])&0xffffffff)/frames if frames else None})
    diagnostics = (output/'game.log').read_text(errors='replace')
    metrics = []
    for line in diagnostics.splitlines():
        if line.startswith('RIX_FRAME_METRICS '):
            metrics.append({k:float(v) for k,v in re.findall(r'([a-z_]+)=([-+0-9.]+)',line)})
    result = {'game':a.game, 'attempt':a.attempt, 'command':command, 'tuning':a.tuning,
              'baseline_runtime':a.baseline_runtime, 'fresh_profile':a.fresh_profile, 'profile':str(home),
              'filter':a.filter, 'style':a.style, 'vertex_cache_disabled':a.no_vertex_cache,
              'present_strategy':env.get('RIX_PRESENT_STRATEGY','native-async' if a.game=='tuxracer' else 'pipeline'),
              'runtime_sha256':runtime_hashes, 'exit_code':exit_code, 'reason':reason,
              'shutdown_method':shutdown_method,
              'before':before, 'after':after, 'samples':samples, 'windows':windows, 'metrics':metrics,
              'input_results':input_results, 'captures':captures, 'game_log_bytes':(output/'game.log').stat().st_size,
              'diagnostic_stream':log.stats(),'telemetry_backend':'persistent PLGPU_GET_STATUS ioctl',
              'game_log_sha256':games.sha(output/'game.log'), 'all_errors_zero':after['status']==3 and all(s['status']==3 and not any(s[k] for k in games.ERRORS) for s in [*samples,after]),
              'transport_errors':log.errors['transport_errors'],
              'unsupported_clip_warnings':log.errors['unsupported_clip_warnings'],
              'boot_sha256':games.sha(Path('/mnt/sd-mmcblk1p1/BOOT.BIN')), 'dtb_sha256':games.sha(Path('/mnt/sd-mmcblk1p1/system.dtb'))}
    result['tux_state_metrics']=[{k:float(v) for k,v in re.findall(r'([a-z_]+)=([-+0-9.]+)',line)} for line in diagnostics.splitlines() if line.startswith('TUX_RIX_FRAME ')]
    if len(steady)>1:
        result['steady_seconds'] = steady[-1]['elapsed_s']-steady[0]['elapsed_s']
        result['steady_fps'] = ((steady[-1]['presented']-steady[0]['presented'])&0xffffffff)/result['steady_seconds']
        result['median_gpu_ms'] = statistics.median(w['gpu_ms_per_frame'] for w in windows if w['gpu_ms_per_frame'] is not None)
    result['passed'] = exit_code==0 and result['all_errors_zero'] and not result['transport_errors'] and not log.failure and reason in ('duration limit','process exited') and all(v['returncode']==0 for v in captures.values())
    result['gpu_recovery_required']=bool(result['transport_errors'] or not result['all_errors_zero'] or exit_code!=0)
    if result['gpu_recovery_required']:
        result['gpu_recovery_record']=recovery.mark(a.attempt,result)
    encoded = json.dumps(result,indent=2)+'\n'
    (output/'result.json').write_text(encoded)
    Path('/tmp/postproc-tests').mkdir(exist_ok=True)
    (Path('/tmp/postproc-tests')/('games-'+a.attempt+'.json')).write_text(encoded)
    saved = Path('/opt/rasterix/experimental/results-optimization-20261019')/a.attempt
    saved.mkdir(parents=True,exist_ok=False)
    for name in ('result.json','game.log','game-tail.log','dependencies.log','capture.log','shutdown.log'):
        path=output/name
        if path.exists():
            (saved/name).write_bytes(path.read_bytes())
    print('RIX_OPT_TRIAL_RESULT='+json.dumps({k:v for k,v in result.items() if k not in ('samples','metrics','windows')}),flush=True)
    return 0 if result['passed'] else 2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('game',choices=games.GAMES)
    p.add_argument('--attempt',default=None)
    p.add_argument('--seconds',type=int,default=1800)
    p.add_argument('--filter',choices=('nearest','bilinear'),default='bilinear')
    p.add_argument('--style',choices=games.STYLES,default='original')
    p.add_argument('--tuning',choices=('balanced','legacy'),default='balanced')
    p.add_argument('--fresh-profile',action='store_true')
    p.add_argument('--baseline-runtime',action='store_true')
    p.add_argument('--no-vertex-cache',action='store_true')
    p.add_argument('--autoplay',action='store_true')
    p.add_argument('--capture',action='store_true')
    a=p.parse_args()
    if not 5<=a.seconds<=1800:p.error('--seconds must be 5..1800')
    a.attempt=a.attempt or a.game+'-'+games.uuid.uuid4().hex[:12]
    return run(a)


if __name__=='__main__':
    raise SystemExit(main())
