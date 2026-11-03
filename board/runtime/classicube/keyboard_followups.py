#!/usr/bin/env python3
"""After real X11 input completes, check saved-map reload, full viewport and exits."""
import json,subprocess,sys,time
from pathlib import Path

attempt=sys.argv[1] if len(sys.argv)>1 else 'cc_keyboard_v8'
version=attempt.rsplit('_',1)[1];assert version in ('v7','v8','v8b','v9')
out=Path('/tmp/postproc-tests');qa=out/attempt/'input-qa.json'
deadline=time.monotonic()+120
while not qa.exists():
    assert time.monotonic()<deadline,'Keyboard test did not finish';time.sleep(.2)
assert json.loads(qa.read_text())['passed']
assert not subprocess.run(['pidof','ClassiCube'],stdout=subprocess.PIPE).stdout
records={}
def run(name,args):
    with Path('/tmp/'+name+'.log').open('w') as log:
        r=subprocess.run(['rix-classicube','--attempt',name]+args,stdout=log,stderr=subprocess.STDOUT)
    data=json.loads((out/name/'result.json').read_text());assert r.returncode==0 and data['passed'],data
    records[name]=data
    print('CLASSICUBE_FOLLOWUP',name,data['hardware_window'],flush=True)
run('cc_keyboard_terrain_'+version,['--seconds','18','--world-size','64','--view-distance','32','--autoplay','--capture'])
profile=Path('/opt/rasterix/classicube/profile/options.txt')
def options():return dict(s.split('=',1) for s in profile.read_text().splitlines() if '=' in s)
original=options().get('singleplayerphysics','True')
values=options();values['singleplayerphysics']='False';profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
try:
    run('cc_keyboard_reload_'+version,['--seconds','10','--map','/opt/rasterix/classicube/profile/maps/'+attempt.replace('_','')+'.cw','--capture'])
finally:
    values=options();values['singleplayerphysics']=original;profile.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
name='cc_keyboard_early_'+version
with Path('/tmp/'+name+'.log').open('w') as log:
    child=subprocess.Popen(['rix-classicube','--world-size','32','--flat','--input-qa','--attempt',name],stdout=log,stderr=subprocess.STDOUT)
    until=time.monotonic()+30
    while not (out/name/'input.json').exists():
        assert child.poll() is None and time.monotonic()<until;time.sleep(.02)
    child.terminate();assert child.wait(timeout=20)==0
early=json.loads((out/name/'result.json').read_text());assert early['passed'] and early['metrics']['seconds']<2
records[name]=early
old=subprocess.run(['rix-games','glx-probe','--seconds','8','--attempt','cc_keyboard_legacy_'+version],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
assert old.returncode==0,old.stdout
records['legacy']=json.loads((out/('games-cc_keyboard_legacy_'+version+'.json')).read_text())
assert records['legacy']['passed']
assert not subprocess.run(['pidof','ClassiCube'],stdout=subprocess.PIPE).stdout
(out/('cc_keyboard_followups_'+version+'.json')).write_text(json.dumps(records,indent=2)+'\n')
print('CLASSICUBE_KEYBOARD_FOLLOWUPS_PASS',flush=True)
