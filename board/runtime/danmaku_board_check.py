#!/usr/bin/env python3
"""Run exclusive process-lifetime and larger-sprite checks on the real board."""
import hashlib
import json
from pathlib import Path
import subprocess

home = Path('/opt/rasterix/danmaku')
binary = home / 'rix-danmaku'
results = home / 'results-20261019'
results.mkdir(parents=True, exist_ok=True)
def status():
    return json.loads(subprocess.check_output(['plgpuctl', 'status']))
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

initial = status()
subprocess.run(['/opt/rasterix/postproc-touch/bin/rix-superres', '--pl-mode', 'nearest', '--style', '0'], check=True)
matrix_code = None
capture_code = None
command = [str(binary), '--seconds', '8', '--output', str(results / 'final.json'),
           '--image', str(results / 'final.ppm'), '--qa-image', str(results / 'alpha-qa.ppm'), '--hold-last-seconds', '60']
with (results / 'matrix.log').open('w', buffering=1) as log:
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    for line in child.stdout:
        log.write(line)
        if line.startswith('DANMAKU_FRAME_HELD '):
            capture_code = subprocess.call(['/opt/rasterix/postproc-touch/bin/rix-superres', '--capture', str(results / 'lcd.bin')])
            child.terminate()
    matrix_code = child.wait()
print('DANMAKU_MATRIX_CAPTURE', matrix_code, capture_code, flush=True)
restart_codes = []
for index, count in enumerate((256, 512, 1024)):
    command = [str(binary), '--count', str(count), '--mode', 'alpha', '--seconds', '1',
               '--output', str(results / ('restart-%d.json' % index))]
    with (results / ('restart-%d.log' % index)).open('wb') as log:
        code = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT)
    restart_codes.append(code)
    print('DANMAKU_RESTART', index, code, flush=True)
    if code:
        break
stress_codes = {}
if restart_codes == [0, 0, 0]:
    for name, args in [('rotated', ['--count', '1024', '--sprite-size', '16', '--rotate']),
                       ('4096', ['--count', '4096'])]:
        command = [str(binary), '--mode', 'alpha', '--seconds', '8', '--output', str(results / (name + '.json'))] + args
        with (results / (name + '.log')).open('wb') as log:
            code = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT)
        stress_codes[name] = code
        print('DANMAKU_STRESS', name, code, flush=True)
        if code:
            break
proof = {'restart_exit_codes': restart_codes, 'stress_exit_codes': stress_codes,
         'matrix_exit_code': matrix_code, 'lcd_capture_exit_code': capture_code,
         'initial_status': initial, 'status': status(), 'binary_sha256': sha(binary),
         'boot_sha256': sha(Path('/mnt/sd-mmcblk1p1/BOOT.BIN')),
         'dtb_sha256': sha(Path('/mnt/sd-mmcblk1p1/system.dtb')),
         'physical_touch_tested': False}
(results / 'board-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
print('DANMAKU_BOARD_PROOF=' + json.dumps(proof), flush=True)
if restart_codes != [0, 0, 0] or any(stress_codes.values()):
    raise SystemExit(1)
