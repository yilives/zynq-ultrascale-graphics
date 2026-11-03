#!/usr/bin/env python3
"""Observe real X11/SDL keyboard/mouse input while neural styling runs."""
import ast,ctypes as c,hashlib,json,math,os,subprocess,time
from pathlib import Path

root=Path('/tmp/rix-mc-style-v3/mc-style');name='cc_style_v3_input'
out=Path('/tmp/postproc-tests');game_out=out/(name+'_game')
support=Path('/tmp/cc_style_x11_support.py').read_text()
tree=ast.parse(support);node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='XInput')
namespace={'c':c,'time':time,'events':[],'held':set()}
exec(compile(ast.Module(body=[node]),'<verified-project-XInput>','exec'),namespace)
env=os.environ.copy();env['RIX_INPUT_QA']=str(game_out)
command=['python3',str(root/'bin/rix-classicube-style'),'--seconds','60','--attempt',name]
stages={};checks={};child=None;x=None;error=None

def state():return json.loads((game_out/'input.json').read_text())
def wait(predicate,seconds=8):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        assert child.poll() is None,'Game stopped during input test'
        if (game_out/'input.json').exists():
            value=state()
            if predicate(value):return value
        time.sleep(.05)
    raise RuntimeError('Input telemetry timeout')
def mark(stage):stages[stage]=state();return stages[stage]
def check(label,condition):checks[label]=bool(condition);assert condition,label

try:
    with (out/(name+'.log')).open('w') as log:
        child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        wait(lambda s:s['focus'] and s['raw'] and s['size']==[400,240],30)
        deadline=time.monotonic()+25
        while not (out/name/'neural.log').exists() or 'NEURAL_FRAME 1 ' not in (out/name/'neural.log').read_text():
            assert child.poll() is None and time.monotonic()<deadline;time.sleep(.1)
        x=namespace['XInput']();x.target=x.find(x.root);check('exact_classicube_window',bool(x.target));x.focus()
        initial=mark('initial');check('native_focus_raw_size',initial['focus'] and initial['raw'] and initial['size']==[400,240])
        x.key('w',True);time.sleep(.3);x.key('space',True);time.sleep(.2)
        moving=mark('walking_jump');check('keyboard_keydown_received',moving['W'] and moving['Space'] and moving['sdl']['key_down']>=initial['sdl']['key_down']+2)
        check('jump_changes_position',moving['position'][1]>initial['position'][1]+.1)
        x.key('space',False);time.sleep(.2);x.key('w',False);released=wait(lambda s:not s['W'] and not s['Space'])
        stages['released']=released;check('keyboard_keyup_received',released['sdl']['key_up']>=initial['sdl']['key_up']+2)
        check('horizontal_movement',math.hypot(released['position'][0]-initial['position'][0],released['position'][2]-initial['position'][2])>.3)
        for _ in range(3):x.relative(25,20)
        turned=mark('mouse_look');check('mouse_look_received',abs(turned['yaw']-released['yaw'])>1 and abs(turned['pitch']-released['pitch'])>1)
        x.tap('2');number=mark('number_slot');check('number_selects_slot',number['slot']==1)
        x.button(5);wheel=mark('wheel_slot');check('mouse_wheel_selects_slot',wheel['slot']!=number['slot'] and wheel['sdl']['wheel']>number['sdl']['wheel'])
        x.tap('Escape');pause=wait(lambda s:s['gui_grab'] and not s['raw'] and s['cursor_visible']);stages['pause']=pause
        check('pause_menu_enters_gui',bool(pause['widgets']))
        x.point(100,80);pointer=wait(lambda s:abs(s['pointer'][0]-100)<=2 and abs(s['pointer'][1]-80)<=2);stages['pointer']=pointer
        check('menu_mouse_pointer',True)
        x.tap('Escape');resume=wait(lambda s:s['raw'] and not s['gui_grab']);stages['resumed']=resume
        check('menu_resumes_keyboard_mouse',bool(resume['focus']))
except Exception as exc:error=repr(exc)
finally:
    if x is not None:
        for key in list(namespace['held']):x.key(key,False)
        x.x.XCloseDisplay(x.d)
    if child is not None and child.poll() is None:child.terminate()
    code=child.wait(timeout=25) if child is not None else None
    session=json.loads((out/name/'session.json').read_text()) if (out/name/'session.json').exists() else None
    game=json.loads((game_out/'result.json').read_text()) if (game_out/'result.json').exists() else None
    passed=error is None and code==0 and session and session['passed'] and game and game['passed'] and game['fps_limit']==60 and not game['metrics']['autoplay']
    record={'passed':bool(passed),'error':error,'checks':checks,'stages':stages,'events':namespace['events'],'session':session,'game':game,'command':command,'command_exit':code,'support_sha256':hashlib.sha256(support.encode()).hexdigest(),'scope':'Actual XTEST -> X11 -> SDL -> game with FPGA CNN active; no physical USB input claim'}
    (out/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n');print('MC_STYLE_INPUT_PROBE',bool(passed),error,flush=True)
raise SystemExit(0 if record['passed'] else 1)
