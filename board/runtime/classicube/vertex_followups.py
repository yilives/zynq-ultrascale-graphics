#!/usr/bin/env python3
"""Exercise packed rendering with menus, persistent maps, fallback and shutdown."""
import json,re,subprocess,sys,time
from pathlib import Path
out=Path('/tmp/postproc-tests');records={}
version=sys.argv[1] if len(sys.argv)>1 else 'v16';assert re.fullmatch('v[0-9]+',version)
name=lambda part:'cc_vertex_'+part+'_'+version
subprocess.run(['rix-classicube','--world-size','64','--view-distance','32','--autoplay','--triangles',
                '--seconds','8','--capture','--attempt',name('triangles')],check=True)
subprocess.run(['python3','/tmp/cc_vertex_stress.py',name('stress')],check=True)
subprocess.run(['python3','/tmp/cc_vertex_input.py',name('input')],check=True)
records['input']=json.loads((out/name('input')/'result.json').read_text())
assert records['input']['passed'] and records['input']['vertex_fetch']=='packed'
profile=Path('/opt/rasterix/classicube/profile/options.txt')
def options():return dict(s.split('=',1) for s in profile.read_text().splitlines() if '=' in s)
values=options();physics=values.get('singleplayerphysics','True');values['singleplayerphysics']='False'
profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
try:
    subprocess.run(['rix-classicube','--map','/opt/rasterix/classicube/profile/maps/'+name('input').replace('_','')+'.cw',
                    '--seconds','10','--capture','--attempt',name('reload')],check=True)
finally:
    values=options();values['singleplayerphysics']=physics;profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
records['reload']=json.loads((out/name('reload')/'result.json').read_text())
with Path('/tmp/'+name('early')+'.log').open('w') as log:
    child=subprocess.Popen(['rix-classicube','--world-size','32','--flat','--input-qa','--attempt',name('early')],stdout=log,stderr=subprocess.STDOUT)
    until=time.monotonic()+30
    while not (out/name('early')/'input.json').exists():
        assert child.poll() is None and time.monotonic()<until;time.sleep(.02)
    child.terminate();assert child.wait(timeout=20)==0
records['early']=json.loads((out/name('early')/'result.json').read_text())
assert records['early']['passed'] and records['early']['metrics']['seconds']<2
subprocess.run(['rix-games','glx-probe','--seconds','8','--attempt',name('legacy')],check=True)
records['legacy']=json.loads((out/('games-'+name('legacy')+'.json')).read_text())
assert records['legacy']['passed'] and records['legacy']['all_errors_zero'] and not records['legacy']['transport_errors']
subprocess.run(['python3','/tmp/cc_collect_state.py'],check=True)
(out/('cc_vertex_followups_'+version+'.json')).write_text(json.dumps(records,indent=2)+'\n')
print('CLASSICUBE_VERTEX_FOLLOWUPS_PASS',flush=True)
