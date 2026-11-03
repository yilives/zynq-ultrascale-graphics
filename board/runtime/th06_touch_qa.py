#!/usr/bin/env python3
"""Inject temporary uinput contacts into the real TH06 evdev path; not a physical touch test."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('--attempt',required=True)
a=p.parse_args()
assert re.fullmatch('[a-z0-9_-]{1,40}',a.attempt)
base=Path('/opt/rasterix/touhou')
result_dir=base/'results'/a.attempt
assert not result_dir.exists()
fd=os.open('/dev/uinput',os.O_WRONLY|os.O_NONBLOCK)
child=None
device_name='TH06 Touch QA '+a.attempt
event=struct.Struct('llHHi')
def send(kind,code,value):
    os.write(fd,event.pack(0,0,kind,code,value))
def contact(slot,x=0,y=0,down=True,move=False):
    send(3,0x2f,slot)
    if not move:send(3,0x39,slot+100 if down else -1)
    if down:
        send(3,0x35,x);send(3,0x36,y)
    send(0,0,0)
def release():
    for slot in range(3):contact(slot,down=False)
def log():
    path=result_dir/'game.log'
    return path.read_text(errors='replace') if path.exists() else ''
created=False
try:
    for kind in (0,1,3):fcntl.ioctl(fd,0x40045564,kind) # UI_SET_EVBIT
    fcntl.ioctl(fd,0x40045565,330) # BTN_TOUCH
    for axis in (0x2f,0x35,0x36,0x39):fcntl.ioctl(fd,0x40045567,axis)
    maximum=[0]*64
    for axis,value in ((0x2f,9),(0x35,799),(0x36,479),(0x39,65535)):maximum[axis]=value
    setup=struct.pack('80sHHHHI',device_name.encode(),3,0x5249,0x5806,1,0)
    setup+=struct.pack('64i',*maximum)+bytes(64*4*3)
    assert len(setup)==1116
    os.write(fd,setup);fcntl.ioctl(fd,0x5501);created=True
    deadline=time.monotonic()+5
    nodes=[]
    while not nodes and time.monotonic()<deadline:
        nodes=[q for q in Path('/sys/class/input').glob('event*/device/name') if q.read_text().strip()==device_name]
        time.sleep(.05)
    assert len(nodes)==1,'Temporary uinput device not found'
    node='/dev/input/'+nodes[0].parent.parent.name
    env=os.environ.copy();env['TH06_TOUCH_DEVICE']=node;env['TH06_TOUCH']='1'
    with (base/('touch-qa-'+a.attempt+'.log')).open('wb') as output:
        child=subprocess.Popen(['python3',str(base/'th06_board_trial.py'),'--attempt',a.attempt,'--seconds','45','--texture-mode','balanced'],env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+20
    while 'TH06_TOUCH_READY' not in log() and time.monotonic()<deadline:
        assert child.poll() is None,'Game trial stopped before touch initialization'
        time.sleep(.1)
    assert 'TH06_TOUCH_READY' in log(),'TH06 evdev reader did not open the virtual device'
    # Confirm through the real title/difficulty/character/shot menus.
    for _ in range(14):
        if re.search(r'TH06_RIX_FRAME .* state=2 ',log()):break
        contact(0,400,240);time.sleep(.12);contact(0,down=False);time.sleep(1)
    assert re.search(r'TH06_RIX_FRAME .* state=2 ',log()),'Touch menu confirmation did not enter a stage'
    contact(0,300,240);time.sleep(.2)
    contact(0,330,210,move=True);time.sleep(.3)
    contact(1,650,400);time.sleep(.2);contact(1,down=False);time.sleep(.2)
    contact(2,650,40);time.sleep(.2);release();time.sleep(.3)
    code=child.wait(timeout=60)
    text=log()
    masks=[int(v) for v in re.findall(r'TH06_TOUCH_BUTTONS state=2 mask=(\d+)',text)]
    trial=json.loads((result_dir/'result.json').read_text())
    checks={
        'virtual_device_opened': 'name='+device_name in text,
        'menu_confirm_entered_stage': bool(re.search(r'TH06_RIX_FRAME .* state=2 ',text)),
        'drag_shoot_focus': 149 in masks,
        'second_finger_bomb': 151 in masks,
        'second_finger_pause': 157 in masks,
        'release_clears_input': bool(masks) and masks[-1]==0,
        'clean_exit_and_no_hw_errors': code==0 and trial['exit_code']==0 and trial['all_errors_zero'],
    }
    result={'passed':all(checks.values()),'checks':checks,'masks':masks,'device':node,'physical_finger_tested':False}
    (result_dir/'touch-qa.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TH06_TOUCH_QA_RESULT='+json.dumps(result),flush=True)
    if not result['passed']:raise SystemExit(1)
finally:
    if child is not None and child.poll() is None:
        os.killpg(child.pid,signal.SIGTERM)
        try:child.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    if created:
        release();fcntl.ioctl(fd,0x5502)
    os.close(fd)
