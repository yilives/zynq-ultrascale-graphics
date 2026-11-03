#!/usr/bin/env python3
"""Run original TH06 trial data on the native RasterIX engine and record evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--attempt', required=True)
parser.add_argument('--seconds', type=int, default=30)
parser.add_argument('--autoplay', action='store_true')
parser.add_argument('--legacy-pacing', action='store_true')
parser.add_argument('--hold', type=int, default=0)
parser.add_argument('--texture-mode', choices=('balanced','native','scaled'), default='balanced')
parser.add_argument('--atlas-qa', action='store_true')
parser.add_argument('--style-qa', action='store_true')
parser.add_argument('--published-entry', action='store_true')
args = parser.parse_args()
assert re.fullmatch('[a-z0-9_-]{1,48}', args.attempt) and 5 <= args.seconds <= 1800
assert 0 <= args.hold <= 10
assert not args.style_qa or args.hold >= 6
base = Path('/opt/rasterix/touhou')
runtime = base / 'th06-runtime'
data = base / 'th06-demo'
output = base / 'results' / args.attempt
assert not output.exists(), 'Use a new trial attempt name'
output.mkdir(parents=True)
home = output / 'home'
home.mkdir()
for source in data.iterdir():
    if source.is_file():
        (home / source.name).symlink_to(source)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def status():
    # plgpuctl deliberately exits 2 on a hardware fault, but its JSON remains
    # valuable evidence and must survive into result.json.
    probe = subprocess.run(['plgpuctl', 'status'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return json.loads(probe.stdout)

active = subprocess.run(['pidof', 'tuxracer', 'neverball', 'neverputt', 'quake3e', 'quakespasm', 'rix-danmaku', 'rix-superres', 'th06-rix'], stdout=subprocess.PIPE)
assert active.returncode == 1 and not active.stdout, 'GPU client already active'
before = status()
assert before['status'] == 3 and before['config'] == 0x9adb505e
errors = ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')
assert not any(before[k] for k in errors)
subprocess.run(['/opt/rasterix/postproc-touch/bin/rix-superres', '--pl-mode', 'nearest', '--style', '0'], check=True)
binary = runtime / 'bin/th06-rix'
capture = Path('/tmp/postproc-tests') / ('th06-' + args.attempt + '.ppm')
capture.parent.mkdir(exist_ok=True)
env = os.environ.copy()
env.update(DISPLAY=':0', SDL_VIDEODRIVER='x11', SDL_AUDIODRIVER='dummy',
           LD_LIBRARY_PATH=str(runtime / 'lib'), LANG='C', LC_ALL='C',
           TH06_RUN_SECONDS=str(args.seconds), TH06_CAPTURE_PATH=str(capture))
env['TH06_HOLD_LAST_SECONDS'] = str(args.hold)
env['TH06_TEXTURE_MODE'] = args.texture_mode
if args.atlas_qa:
    env['TH06_ATLAS_QA'] = str(capture.with_suffix('')) + '-atlas'
else:
    env.pop('TH06_ATLAS_QA', None)
if args.legacy_pacing:
    env['TH06_LEGACY_PACING'] = '1'
else:
    env.pop('TH06_LEGACY_PACING', None)
if args.autoplay:
    env['TH06_AUTOPLAY'] = '1'
else:
    env.pop('TH06_AUTOPLAY', None)
deps = subprocess.run(['/lib/ld-linux-aarch64.so.1', '--list', str(binary)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(output / 'dependencies.log').write_bytes(deps.stdout)
assert deps.returncode == 0, deps.stdout.decode(errors='replace')
samples = []
lcd_code = None
style_codes = {}
began = time.monotonic()
reason = 'process completed'
with (output / 'game.log').open('wb') as log:
    command=[str(binary)]
    if args.published_entry:
        command=[str(runtime/'bin/rix-th06-run'),'--quality',args.texture_mode,'--seconds',str(args.seconds),'--touch']
        if args.autoplay:command.append('--autoplay')
    child = subprocess.Popen(command, cwd=home, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        while child.poll() is None:
            s = status()
            s['elapsed_s'] = time.monotonic() - began
            samples.append(s)
            if args.hold >= 4 and lcd_code is None and capture.exists() and capture.stat().st_size == 288015:
                with (output / 'lcd-capture.log').open('wb') as lcd_log:
                    lcd_code = subprocess.call(['/opt/rasterix/postproc-touch/bin/rix-superres', '--capture', str(output / 'lcd.bin')], stdout=lcd_log, stderr=subprocess.STDOUT)
                    if args.style_qa:
                        tool='/opt/rasterix/postproc-touch/bin/rix-superres'
                        try:
                            for filtering,style in [('nearest',0),('nearest',1),('nearest',2),('nearest',3),('bilinear',0)]:
                                name=filtering+'-style'+str(style)
                                setting=subprocess.call([tool,'--pl-mode',filtering,'--style',str(style)],stdout=lcd_log,stderr=subprocess.STDOUT)
                                captured=subprocess.call([tool,'--capture',str(output/('lcd-'+name+'.bin'))],stdout=lcd_log,stderr=subprocess.STDOUT) if not setting else -1
                                style_codes[name]=[setting,captured]
                        finally:
                            subprocess.call([tool,'--pl-mode','nearest','--style','0'],stdout=lcd_log,stderr=subprocess.STDOUT)
            if s['status'] != 3 or any(s[k] != before[k] for k in errors):
                reason = 'hardware error'
                break
            if s['elapsed_s'] > args.seconds + 15:
                reason = 'trial wall-clock limit'
                break
            if log.tell() > 2 * 1024 * 1024:
                reason = 'diagnostic log limit'
                break
            time.sleep(.5)
    finally:
        if child.poll() is None:
            child.terminate()
        try:
            code = child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            code = child.wait()
            reason = 'forced stop after nonresponsive shutdown'
after = status()
elapsed = time.monotonic() - began
result = {'attempt': args.attempt, 'texture_mode': args.texture_mode, 'autoplay': args.autoplay, 'legacy_pacing': args.legacy_pacing, 'hold_seconds': args.hold, 'lcd_capture_exit_code': lcd_code, 'exit_code': code, 'reason': reason,
          'seconds': elapsed, 'frames_presented': (after['presented'] - before['presented']) & 0xffffffff,
          'before': before, 'after': after, 'all_errors_zero': after['status'] == 3 and not any(after[k] for k in errors),
          'binary_sha256': sha(binary), 'runtime_sha256': {p.name: sha(p) for p in (runtime / 'lib').iterdir() if p.is_file() and not p.is_symlink()},
          'source_data_manifest': json.loads((data / 'source-manifest.json').read_text()),
          'capture_exists': capture.exists(), 'game_log_sha256': sha(output / 'game.log')}
result['boot_sha256'] = sha(Path('/mnt/sd-mmcblk1p1/BOOT.BIN'))
result['dtb_sha256'] = sha(Path('/mnt/sd-mmcblk1p1/system.dtb'))
text = (output / 'game.log').read_text(errors='replace')
frame_metrics = []
for line in text.splitlines():
    if line.startswith('TH06_RIX_FRAME '):
        frame_metrics.append({k: float(v) for k, v in re.findall(r'([a-z_]+)=([-+0-9.]+)', line)})
result['frame_metrics'] = frame_metrics
result['texture_metrics'] = [{k: float(v) for k,v in re.findall(r'([a-z_]+)=([-+0-9.]+)',line)} for line in text.splitlines() if line.startswith('TH06_TEXTURE_STATS ')]
result['style_capture_returncodes'] = style_codes
result['published_entry'] = args.published_entry
result['idle_demo_guard_seen'] = 'TH06_IDLE_DEMO_UNAVAILABLE keep_menu_active=1' in text
result['physical_goodix_opened'] = 'name=Goodix Capacitive TouchScreen' in text
result['surface_cache_creates'] = text.count('TH06_SURFACE_CACHE_CREATE')
result['menu_idle_after_20_seconds'] = [r for r in frame_metrics if r['state']==1 and r['seconds']>=20]
if args.atlas_qa:
    qa_path = Path(env['TH06_ATLAS_QA'] + '.json')
    result['atlas_qa'] = json.loads(qa_path.read_text()) if qa_path.exists() else None
result['gameplay_verified'] = any(s.get('state') == 2 and s.get('bullets', 0) > 0 and s.get('enemies', 0) > 0 for s in frame_metrics)
result['max_sampled_bullets'] = max((s.get('bullets', 0) for s in frame_metrics), default=0)
result['viewport_selftest_pass'] = 'TH06_RIX_VIEWPORT_SELFTEST_PASS' in text
result['texture_allocation_errors'] = text.count('Ran out of memory')
result['logic_catchup_clamps'] = text.count('TH06_LOGIC_CATCHUP_CLAMP')
if len(frame_metrics) > 1 and 'logic_ticks' in frame_metrics[-1]:
    first, last = frame_metrics[0], frame_metrics[-1]
    result['sampled_logic_hz'] = (last['logic_ticks'] - first['logic_ticks']) / (last['seconds'] - first['seconds'])
if capture.exists():
    result['capture_sha256'] = sha(capture)
    (output / 'frame.ppm').write_bytes(capture.read_bytes())
if len(samples) > 3:
    result['sampled_fps'] = (samples[-1]['presented'] - samples[0]['presented']) / (samples[-1]['elapsed_s'] - samples[0]['elapsed_s'])
(output / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n')
(output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print('TH06_BOARD_TRIAL_RESULT=' + json.dumps({k: v for k, v in result.items() if k != 'source_data_manifest'}), flush=True)
if code or not result['all_errors_zero'] or (args.atlas_qa and not (result.get('atlas_qa') or {}).get('passed')):
    raise SystemExit(1)
