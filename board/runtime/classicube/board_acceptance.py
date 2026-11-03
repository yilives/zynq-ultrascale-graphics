#!/usr/bin/env python3
"""Real-map, common-lock, orderly-stop and existing-runtime acceptance on AXU3EG."""
import json, subprocess, time
from pathlib import Path

OUT = Path('/tmp/postproc-tests')
results = {}

def run(name, args):
    with (Path('/tmp') / (name + '.log')).open('w') as log:
        child = subprocess.run(['rix-classicube', '--attempt', name] + args, stdout=log, stderr=subprocess.STDOUT)
    result = json.loads((OUT / name / 'result.json').read_text())
    results[name] = result
    (OUT / 'cc_acceptance_runs_v4.json').write_text(json.dumps(results, indent=2) + '\n')
    assert child.returncode == 0 and result['passed'], result
    print('CLASSICUBE_ACCEPT', name, result['hardware_window'], flush=True)
    return result

# Turn ordinary block physics back on after the earlier diagnostic prototype.
profile = Path('/opt/rasterix/classicube/profile/options.txt')
options = dict(line.split('=', 1) for line in profile.read_text().splitlines() if '=' in line)
options['singleplayerphysics'] = 'True'
profile.write_text(''.join(k + '=' + v + '\n' for k, v in options.items()))
run('cc_gameplay_v4', ['--seconds','14','--world-size','32','--view-distance','16','--flat','--autoplay','--gameplay-qa','--capture'])
assert 'singleplayerphysics=True' in profile.read_text(), 'QA changed normal block physics'
saved = '/opt/rasterix/classicube/profile/maps/cc_gameplay_v4.cw'
run('cc_reload_tri_v4', ['--seconds','10','--map',saved,'--capture','--triangles'])
run('cc_reload_quad_v4', ['--seconds','10','--map',saved,'--capture'])
terrain = ['--seconds','18','--world-size','64','--view-distance','32','--autoplay','--capture']
tri = run('cc_terrain_tri_v4', terrain + ['--triangles'])
quad = run('cc_terrain_quad_v4', terrain)
ratio = quad['hardware_window']['fps'] / tri['hardware_window']['fps']
print('CLASSICUBE_QUAD_SPEED_RATIO', ratio, flush=True)
run('cc_terrain_long_v4', ['--seconds','62','--world-size','64','--view-distance','32','--autoplay'])

name = 'cc_orderly_stop_v4'
with (Path('/tmp') / (name + '.log')).open('w') as log:
    child = subprocess.Popen(['rix-classicube','--seconds','60','--world-size','32','--flat','--attempt',name], stdout=log, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 30
    while True:
        path = OUT / name / 'game.log'
        if path.exists() and 'RIX_MEASURE_BEGIN' in path.read_text():
            break
        assert child.poll() is None and time.monotonic() < deadline, 'Game did not become ready'
        time.sleep(.1)
    conflict = subprocess.run(['rix-games','glx-probe','--seconds','5','--attempt','cc_should_be_locked_v4'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert conflict.returncode != 0 and b'Resource temporarily unavailable' in conflict.stdout, conflict.stdout
    assert not subprocess.run(['pidof','rix-glx-probe'], stdout=subprocess.PIPE).stdout
    child.terminate()
    assert child.wait(timeout=20) == 0
stop = json.loads((OUT / name / 'result.json').read_text())
assert stop['passed'] and stop['exit_code'] == 0
assert not subprocess.run(['pidof','ClassiCube'], stdout=subprocess.PIPE).stdout
results[name] = stop
results['common_lock_rejection'] = {'passed':True, 'returncode':conflict.returncode,'output':conflict.stdout.decode()}
legacy = subprocess.run(['rix-games','glx-probe','--seconds','8','--attempt','cc_legacy_v4'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
assert legacy.returncode == 0, legacy.stdout
results['legacy'] = json.loads((OUT / 'games-cc_legacy_v4.json').read_text())
assert results['legacy']['passed']
results['quads_to_triangles_speed_ratio'] = ratio
(OUT / 'cc_acceptance_runs_v4.json').write_text(json.dumps(results, indent=2) + '\n')
print('CLASSICUBE_BOARD_ACCEPTANCE_PASS', flush=True)
