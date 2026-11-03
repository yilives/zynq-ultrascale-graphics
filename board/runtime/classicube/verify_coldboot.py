#!/usr/bin/env python3
"""Verify public defaults and saved-map restore with empty volatile caches."""
import argparse,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('attempt');p.add_argument('saved_map');a=p.parse_args()
assert re.fullmatch('[a-z0-9_]{1,48}',a.attempt)
saved=Path(a.saved_map);assert saved.is_file() and saved.resolve().parent==Path('/opt/rasterix/classicube/profile/maps')
out=Path('/tmp/postproc-tests');out.mkdir(exist_ok=True)
assert not Path('/tmp/rasterix-classicube').exists() and not Path('/tmp/rasterix-games').exists()
pre={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
     'classicube_tmp_present':False,'shared_runtime_tmp_present':False,
     'postproc':json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],universal_newlines=True))}
(out/(a.attempt+'_pre.json')).write_text(json.dumps(pre,indent=2)+'\n')
profile=Path('/opt/rasterix/classicube/profile/options.txt')
def options():return dict(s.split('=',1) for s in profile.read_text().splitlines() if '=' in s)
values=options();physics=values.get('singleplayerphysics','True');values['singleplayerphysics']='False'
profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
try:subprocess.run(['rix-classicube','--map',str(saved),'--seconds','8','--capture','--input-qa','--attempt',a.attempt],check=True)
finally:
    values=options();values['singleplayerphysics']=physics;profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
state=json.loads((out/a.attempt/'input.json').read_text())
(out/(a.attempt+'_input.json')).write_bytes((out/a.attempt/'input.json').read_bytes())
assert state['size']==[400,240] and state['focus'] and state['raw'] and not state['gui_grab']
run=json.loads((out/a.attempt/'result.json').read_text())
assert run['passed'] and run['vertex_fetch']=='packed' and run['presentation_strategy']=='async' and run['presentation_sync'] and run['fps_limit']==120
subprocess.run(['python3','/tmp/cc_collect_state.py'],check=True)
print('CLASSICUBE_COLD_BOOT_PASS',a.attempt,pre['boot_id'],flush=True)
