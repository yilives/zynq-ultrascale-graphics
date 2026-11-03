#!/usr/bin/env python3
"""Exercise ClassiCube through XTEST -> X11 -> SDL; never call engine input APIs."""
import ctypes as c
import hashlib, json, math, os, subprocess, sys, tarfile, time
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/classicube')
from rix_capture_source import capture_source

name=sys.argv[1] if len(sys.argv)>1 else 'cc_keyboard_v5'
assert name.replace('_','').isalnum()
out=Path('/tmp/postproc-tests')/name
events=[];stages={};held=set();child=None

class XInput:
    def __init__(self):
        self.x=c.CDLL('libX11.so.6');self.t=c.CDLL('libXtst.so.6')
        self.D=c.c_void_p;self.W=c.c_ulong
        def bind(lib,n,args,result=c.c_int):
            fn=getattr(lib,n);fn.argtypes=args;fn.restype=result
        bind(self.x,'XOpenDisplay',[c.c_char_p],self.D)
        bind(self.x,'XDefaultRootWindow',[self.D],self.W)
        bind(self.x,'XQueryTree',[self.D,self.W,c.POINTER(self.W),c.POINTER(self.W),c.POINTER(c.POINTER(self.W)),c.POINTER(c.c_uint)])
        bind(self.x,'XFetchName',[self.D,self.W,c.POINTER(c.c_void_p)])
        bind(self.x,'XFree',[c.c_void_p]);bind(self.x,'XStringToKeysym',[c.c_char_p],c.c_ulong)
        bind(self.x,'XKeysymToKeycode',[self.D,c.c_ulong],c.c_ubyte)
        bind(self.x,'XRaiseWindow',[self.D,self.W]);bind(self.x,'XSetInputFocus',[self.D,self.W,c.c_int,c.c_ulong])
        bind(self.x,'XSync',[self.D,c.c_int]);bind(self.x,'XCloseDisplay',[self.D])
        bind(self.x,'XTranslateCoordinates',[self.D,self.W,self.W,c.c_int,c.c_int,c.POINTER(c.c_int),c.POINTER(c.c_int),c.POINTER(self.W)])
        bind(self.t,'XTestQueryExtension',[self.D]+[c.POINTER(c.c_int)]*4)
        bind(self.t,'XTestFakeKeyEvent',[self.D,c.c_uint,c.c_int,c.c_ulong])
        bind(self.t,'XTestFakeButtonEvent',[self.D,c.c_uint,c.c_int,c.c_ulong])
        bind(self.t,'XTestFakeRelativeMotionEvent',[self.D,c.c_int,c.c_int,c.c_ulong])
        bind(self.t,'XTestFakeMotionEvent',[self.D,c.c_int,c.c_int,c.c_int,c.c_ulong])
        self.d=self.x.XOpenDisplay(b':0');assert self.d,'X11 unavailable'
        v=[c.c_int() for _ in range(4)]
        assert self.t.XTestQueryExtension(self.d,*(c.byref(a) for a in v))
        self.root=self.x.XDefaultRootWindow(self.d);self.target=None
    def find(self,w,depth=0):
        p=c.c_void_p()
        if self.x.XFetchName(self.d,w,c.byref(p)) and p.value:
            title=c.string_at(p.value).decode('utf-8','replace');self.x.XFree(p)
            if title.startswith('ClassiCube ') and title.endswith('(Singleplayer)'):
                self.title=title;return w
        if depth>8:return None
        root,parent,count=self.W(),self.W(),c.c_uint();children=c.POINTER(self.W)()
        if not self.x.XQueryTree(self.d,w,c.byref(root),c.byref(parent),c.byref(children),c.byref(count)):return None
        ids=list(children[:count.value])
        if children:self.x.XFree(children)
        for sub in ids:
            got=self.find(sub,depth+1)
            if got:return got
    def sync(self):self.x.XSync(self.d,0)
    def focus(self,target=None):
        dest=self.target if target is None else target
        if dest!=self.root:self.x.XRaiseWindow(self.d,dest)
        self.x.XSetInputFocus(self.d,dest,2,0);self.sync()
    def key(self,key,pressed):
        code=self.x.XKeysymToKeycode(self.d,self.x.XStringToKeysym(key.encode('ascii')));assert code
        assert self.t.XTestFakeKeyEvent(self.d,code,int(pressed),0)
        if pressed:held.add(key)
        else:held.discard(key)
        self.sync();events.append({'type':'key','name':key,'pressed':pressed,'time':time.monotonic()})
    def tap(self,key,delay=.12):
        self.key(key,True);time.sleep(delay);self.key(key,False);time.sleep(.15)
    def button(self,button):
        assert self.t.XTestFakeButtonEvent(self.d,button,1,0);self.sync();time.sleep(.1)
        assert self.t.XTestFakeButtonEvent(self.d,button,0,0);self.sync()
        events.append({'type':'button','number':button,'time':time.monotonic()});time.sleep(.2)
    def relative(self,dx,dy):
        assert self.t.XTestFakeRelativeMotionEvent(self.d,dx,dy,0);self.sync()
        events.append({'type':'relative','dx':dx,'dy':dy,'time':time.monotonic()});time.sleep(.12)
    def point(self,x,y):
        ox,oy=c.c_int(),c.c_int();sub=self.W()
        assert self.x.XTranslateCoordinates(self.d,self.target,self.root,0,0,c.byref(ox),c.byref(oy),c.byref(sub))
        assert self.t.XTestFakeMotionEvent(self.d,0,ox.value+int(x),oy.value+int(y),0);self.sync()
        events.append({'type':'point','x':int(x),'y':int(y),'time':time.monotonic()});time.sleep(.2)

def state():return json.loads((out/'input.json').read_text())
def wait(predicate,seconds=5):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        assert child.poll() is None,'Game ended before input test completed'
        if (out/'input.json').exists():
            current=state()
            if predicate(current):return current
        time.sleep(.05)
    raise AssertionError('Input state timeout: '+str(state() if (out/'input.json').exists() else None))
def mark(stage,observed=None):
    stages[stage]=state() if observed is None else observed
    (out/'input-stages.json').write_text(json.dumps(stages,indent=2)+'\n')
    print('CLASSICUBE_INPUT_STAGE',stage,flush=True);return stages[stage]
def capture(token):
    assert token.replace('_','').isalnum()
    (out/'request.txt').write_text(token+'\n');deadline=time.monotonic()+7
    while not (out/(token+'.done')).exists():
        assert child.poll() is None and time.monotonic()<deadline
        time.sleep(.03)
    assert (out/(token+'.done')).read_text().strip()=='1'
    try:
        # Independently wait for the actual LCD flip, not only DMA readback.
        deadline=time.monotonic()+5;previous=None;stable=None
        while True:
            gpu=json.loads(subprocess.check_output(['plgpuctl','status']))
            assert not any(gpu[k] for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
            idle=len({gpu[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
            if idle and gpu['frame_id']==previous and stable is not None and time.monotonic()-stable>=.03:break
            if not idle or gpu['frame_id']!=previous or stable is None:
                stable=time.monotonic() if idle else None;previous=gpu['frame_id']
            assert time.monotonic()<deadline,'LCD capture fence timed out'
            time.sleep(.002)
        (out/(token+'.fence.json')).write_text(json.dumps(gpu,indent=2)+'\n')
        capture_source(out/(token+'.gpu'),gpu['frame_id'])
        subprocess.run(['/opt/rasterix/postproc-touch/bin/rix-superres','--capture',str(out/(token+'.lcd.bin'))],check=True,stdout=subprocess.DEVNULL)
        assert json.loads(subprocess.check_output(['plgpuctl','status']))['frame_id']==gpu['frame_id']
    finally:(out/(token+'.release')).write_text('release\n')
    time.sleep(.2)
def resume():
    for _ in range(4):
        if not state()['gui_grab']:break
        x.tap('Escape');time.sleep(.15)
    wait(lambda s:s['raw'] and not s['gui_grab'])
def click_nearest(px,py):
    widgets=[w for w in state()['widgets'] if w['w']>=40 and w['h']>=10]
    assert widgets
    w=min(widgets,key=lambda v:(v['x']+v['w']/2-px)**2+(v['y']+v['h']/2-py)**2)
    x.point(w['x']+w['w']/2,w['y']+w['h']/2);x.button(1);return w

error=None;started=time.monotonic();x=XInput()
try:
    log=open('/tmp/'+name+'-launch.log','w')
    child=subprocess.Popen(['rix-classicube','--seconds','0','--world-size','32','--flat','--input-qa','--attempt',name],stdout=log,stderr=subprocess.STDOUT)
    wait(lambda s:s['size']==[400,240],30);time.sleep(2)
    initial=mark('initial');assert initial['focus'] and initial['raw'] and not initial['gui_grab']
    x.target=x.find(x.root);assert x.target,'No ClassiCube window'
    x.focus();x.key('w',True);time.sleep(.25);x.key('space',True);time.sleep(.22)
    moving=mark('walking_jump');assert moving['W'] and moving['Space'] and moving['position'][1]>initial['position'][1]+.1
    x.key('space',False);time.sleep(.5);x.key('w',False);time.sleep(.5)
    moved=mark('released');assert not moved['W'] and not moved['Space']
    assert math.sqrt(sum((a-b)**2 for a,b in zip(moved['position'],initial['position'])))>1
    for _ in range(4):x.relative(30,60)
    turned=mark('mouse_look');assert abs(turned['yaw']-moved['yaw'])>2 and turned['pitch']>moved['pitch']+2
    for _ in range(8):
        if state()['pitch']>=45:break
        x.relative(0,50)
    wait(lambda s:s['picked_valid']);x.tap('2');number=mark('number_slot');assert number['slot']==1
    x.button(5);wheel=mark('wheel_slot');assert wheel['slot']!=number['slot'] and wheel['sdl']['wheel']>0
    x.button(2);picked=mark('middle_pick');assert picked['block']==picked['picked_block']
    x.button(1);wait(lambda s:s['deleted']>0);mark('left_delete')
    x.tap('1');x.button(3);wait(lambda s:s['placed']>0);mark('right_place');capture('world')
    x.tap('Escape');menu=wait(lambda s:s['gui_grab'] and not s['raw'] and s['cursor_visible']);mark('pause')
    assert menu['widgets'] and all(w['x']>=0 and w['y']>=0 and w['x']+w['w']<=400 and w['y']+w['h']<=240 for w in menu['widgets'])
    x.point(35,35);capture('pause')
    click_nearest(120,95);wait(lambda s:s['gui_grab']);mark('options');capture('options');resume()
    x.tap('b');wait(lambda s:s['gui_grab'] and not s['raw']);inventory=mark('inventory');capture('inventory')
    table=max(inventory['widgets'],key=lambda w:w['w']*w['h'])
    x.point(table['x']+table['w']*.375,table['y']+12);x.button(1);time.sleep(.2);mark('inventory_selection');resume()
    x.tap('Escape');wait(lambda s:s['gui_grab']);click_nearest(280,145);time.sleep(.25)
    mark('save_dialog');x.key('Control_L',True);x.tap('a');x.key('Control_L',False)
    save_name=name.replace('_','')
    for letter in save_name:x.tap(letter,.03)
    capture('save');x.tap('Return')
    saved=Path('/opt/rasterix/classicube/profile/maps')/(save_name+'.cw');deadline=time.monotonic()+5
    while not saved.is_file():
        assert child.poll() is None and time.monotonic()<deadline,'Menu save did not create requested map'
        time.sleep(.05)
    (out/'saved.cw').write_bytes(saved.read_bytes());mark('menu_saved');resume()
    x.key('w',True);wait(lambda s:s['W']);x.focus(x.root);lost=wait(lambda s:not s['focus'] and not s['W']);time.sleep(.5)
    mark('focus_lost',lost);later=mark('focus_lost_held')
    assert not later['focus'] and not later['W'],'Key autorepeat reactivated input after focus loss'
    x.key('w',False);x.focus();wait(lambda s:s['focus']);time.sleep(.25);mark('focus_restored')
    x.tap('F11');assert state()['size']==[400,240];mark('fixed_fullscreen')
    # The default interactive command must survive the former 65-second watchdog.
    while time.monotonic()-started<70:
        assert child.poll() is None;time.sleep(.2)
    mark('unlimited_70s');x.tap('Escape');wait(lambda s:s['gui_grab']);click_nearest(370,228)
    assert child.wait(timeout=20)==0
    result=json.loads((out/'result.json').read_text());assert result['passed'] and result['exit_code']==0
except Exception as exc:
    error=repr(exc)
finally:
    for key in list(held):x.key(key,False)
    if child is not None and child.poll() is None:
        child.terminate()
        try:child.wait(timeout=20)
        except subprocess.TimeoutExpired:error=(error or '')+'; normal shutdown timeout'
    x.x.XCloseDisplay(x.d)
    if child is not None:log.close()
    record={'passed':error is None,'error':error,'elapsed':time.monotonic()-started,
            'path':'XTEST -> X11 -> SDL2 -> ClassiCube input handler','no_internal_autoplay':True,
            'physical_USB_tested':False,'stages':stages,'events':events,
            'menu_save_sha256':hashlib.sha256((out/'saved.cw').read_bytes()).hexdigest() if (out/'saved.cw').exists() else None}
    if out.exists():
        (out/'input-qa.json').write_text(json.dumps(record,indent=2)+'\n')
        (out/'physical-input-devices.txt').write_text(Path('/proc/bus/input/devices').read_text())
        with tarfile.open(out.with_suffix('.tar.gz'),'w:gz') as tf:
            for p in out.iterdir():
                if p.is_file() and p.suffix in ('.json','.log','.ppm','.bin','.txt','.cw'):tf.add(p,arcname=p.name)
    print('CLASSICUBE_X11_INPUT_QA',json.dumps({k:v for k,v in record.items() if k not in ('events','stages')}),flush=True)
if error:raise SystemExit(2)
