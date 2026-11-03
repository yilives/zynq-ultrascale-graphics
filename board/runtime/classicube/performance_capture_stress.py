#!/usr/bin/env python3
"""Vary real SDL mouse input while requesting multiple asynchronous frame captures."""
import ctypes as c
import json, subprocess, sys, tarfile, time
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/classicube')
from rix_capture_source import capture_source

name = sys.argv[1] if len(sys.argv)>1 else 'cc_perf_capture_stress_v15'
import re
assert re.fullmatch('[a-z0-9_]{1,48}',name)
out = Path('/tmp/postproc-tests') / name
x = c.CDLL('libX11.so.6'); t = c.CDLL('libXtst.so.6')
x.XOpenDisplay.argtypes = [c.c_char_p]; x.XOpenDisplay.restype = c.c_void_p
x.XSync.argtypes = [c.c_void_p, c.c_int]
x.XCloseDisplay.argtypes = [c.c_void_p]
t.XTestFakeRelativeMotionEvent.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_ulong]
d = x.XOpenDisplay(b':0'); assert d
def motion(dx):
    t.XTestFakeRelativeMotionEvent(d, dx, 0, 0); x.XSync(d, 0)
def fence():
    until = time.monotonic() + 5; previous = None; stable = None
    while time.monotonic() < until:
        gpu = json.loads(subprocess.check_output(['plgpuctl', 'status']))
        assert not any(gpu[k] for k in ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors'))
        idle = len({gpu[k] for k in ('frame_id', 'swap', 'copy', 'presented', 'last_presented')}) == 1
        if idle and gpu['frame_id'] == previous and stable is not None and time.monotonic() - stable >= .03:
            return gpu
        if not idle or gpu['frame_id'] != previous or stable is None:
            previous = gpu['frame_id']; stable = time.monotonic() if idle else None
        time.sleep(.002)
    raise RuntimeError('LCD capture fence timeout')
records = []; error = None
with Path('/tmp/' + name + '.log').open('w') as log:
    child = subprocess.Popen(['rix-classicube', '--world-size', '64', '--view-distance', '32',
                              '--input-qa', '--attempt', name], stdout=log, stderr=subprocess.STDOUT)
    try:
        until = time.monotonic() + 30
        while not (out / 'input.json').exists():
            assert child.poll() is None and time.monotonic() < until; time.sleep(.02)
        time.sleep(2)
        for i in range(8):
            token = 'stress_%02d' % i
            motion(60)
            (out / 'request.txt').write_text(token + '\n')
            until = time.monotonic() + 7
            while not (out / (token + '.done')).exists():
                assert child.poll() is None and time.monotonic() < until
                motion(5); time.sleep(.01)
            assert (out / (token + '.done')).read_text().strip() == '1'
            try:
                gpu = fence()
                capture_source(out / (token + '.gpu'),gpu['frame_id'])
                subprocess.run(['/opt/rasterix/postproc-touch/bin/rix-superres', '--capture',
                                str(out / (token + '.lcd.bin'))], check=True, stdout=subprocess.DEVNULL)
                assert json.loads(subprocess.check_output(['plgpuctl', 'status']))['frame_id'] == gpu['frame_id']
                records.append({'token': token, 'fence': gpu, 'input': json.loads((out / 'input.json').read_text())})
            finally:
                (out / (token + '.release')).write_text('release\n')
            time.sleep(.05)
    except Exception as exc:
        error = repr(exc)
    finally:
        child.terminate(); assert child.wait(timeout=20) == 0
        x.XCloseDisplay(d)
result = {'passed': error is None, 'error': error, 'captures': records, 'path': 'XTEST relative mouse -> SDL -> real terrain'}
(out / 'capture-qa.json').write_text(json.dumps(result, indent=2) + '\n')
with tarfile.open(out.with_suffix('.tar.gz'), 'w:gz') as tf:
    for p in out.iterdir():
        if p.is_file() and p.suffix in ('.json', '.log', '.ppm', '.bin'):
            tf.add(p, arcname=p.name)
print('CLASSICUBE_CAPTURE_STRESS', result['passed'], len(records), error, flush=True)
if error: raise SystemExit(2)
