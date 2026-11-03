#!/usr/bin/env python3
"""Read installed package, original image/runtime hashes and idle ownership."""
import fcntl, hashlib, json, os, shutil, subprocess
from pathlib import Path

sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
lock = open('/tmp/rasterix-game-launch.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
state = json.loads(subprocess.check_output(['python3','/opt/rasterix/neural-style/bin/neural-board-state.py'], universal_newlines=True))
state['postproc'] = json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'], universal_newlines=True))
state['active_gpu_clients'] = subprocess.run(['pidof','ClassiCube','tuxracer','neverball','neverputt','quakespasm','quake3e',
    'rix-glx-probe','rix-smoke','th06-rix','rix-superres','rix-neural-style'], stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
assert not state['active_gpu_clients']
state['quarantine_exists'] = Path('/opt/rasterix/experimental/gpu-quarantine.json').exists()
cache = Path('/opt/rasterix/experimental/cache')
receipt = json.loads((cache/'classicube.json').read_text())
state['classicube_cache'] = dict(receipt, actual_sha256=sha(cache/'classicube.tar.gz'))
work = Path('/tmp/rasterix-classicube') / receipt['sha256'][:12]
manifest = json.loads((work/'manifest.json').read_text())
state['classicube_files'] = {n:{'bytes':(work/n).stat().st_size,'sha256':sha(work/n),
    'matches_manifest':sha(work/n)==v['sha256']} for n,v in manifest.items()}
state['classicube_command_target'] = str(Path('/usr/bin/rix-classicube').resolve())
state['classicube_launcher_sha256'] = sha(Path('/usr/bin/rix-classicube'))
state['classicube_capture_helper_sha256'] = sha(Path('/opt/rasterix/classicube/rix_capture_source.py'))
state['classicube_asset_target'] = str(Path('/opt/rasterix/classicube/profile/texpacks/default.zip').resolve())
state['tmp_target'] = str(Path('/tmp').resolve())
state['classicube_profile_physics'] = next((x.split('=',1)[1] for x in Path('/opt/rasterix/classicube/profile/options.txt').read_text().splitlines() if x.startswith('singleplayerphysics=')),None)
state['private_gl_sha256'] = sha(Path('/tmp/rasterix-games/runtime/lib/libGL.so.1'))
state['root_free_bytes'] = shutil.disk_usage('/').free
out = Path('/tmp/postproc-tests/cc_board_state.json')
out.write_text(json.dumps(state,indent=2)+'\n')
print('CLASSICUBE_IDLE_STATE',state['boot_id'],state['gpu'],flush=True)
