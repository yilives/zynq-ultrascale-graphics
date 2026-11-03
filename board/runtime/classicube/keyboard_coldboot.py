#!/usr/bin/env python3
"""From a fresh boot, restore a map written through the actual keyboard menu."""
import json,subprocess
from pathlib import Path

out=Path('/tmp/postproc-tests');out.mkdir(exist_ok=True)
assert not Path('/tmp/rasterix-classicube').exists() and not Path('/tmp/rasterix-games').exists()
saved=Path('/opt/rasterix/classicube/profile/maps/cckeyboardv9.cw');assert saved.is_file()
pre={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
     'classicube_tmp_present':False,'shared_runtime_tmp_present':False,
     'postproc':json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],universal_newlines=True))}
(out/'cc_keyboard_cold_pre.json').write_text(json.dumps(pre,indent=2)+'\n')
profile=Path('/opt/rasterix/classicube/profile/options.txt')
def options():return dict(line.split('=',1) for line in profile.read_text().splitlines() if '=' in line)
values=options();physics=values.get('singleplayerphysics','True');values['singleplayerphysics']='False'
profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
try:
    subprocess.run(['rix-classicube','--map',str(saved),'--seconds','8','--capture','--input-qa','--attempt','cc_keyboard_cold_v9'],check=True)
finally:
    values=options();values['singleplayerphysics']=physics;profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
state=json.loads((out/'cc_keyboard_cold_v9/input.json').read_text())
assert state['size']==[400,240] and state['focus'] and state['raw'] and not state['gui_grab']
(out/'cc_keyboard_cold_input.json').write_text(json.dumps(state,indent=2)+'\n')
subprocess.run(['python3','/tmp/cc_collect_state.py'],check=True)
print('CLASSICUBE_KEYBOARD_COLD_BOOT_PASS',pre['boot_id'],flush=True)
