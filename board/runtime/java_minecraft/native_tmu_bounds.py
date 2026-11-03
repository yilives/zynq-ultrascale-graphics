#!/usr/bin/env python3
"""Direct C-ABI diagnostic; it does not advertise GL13 capability to Java."""
import ctypes as c,json,os
from pathlib import Path

def bind(library,name,result,*arguments):
    fn=getattr(library,name);fn.restype=result;fn.argtypes=list(arguments);return fn

def main():
    p=c.c_void_p;u=c.c_uint;i=c.c_int;f=c.c_float;window=c.c_ulong
    x=c.CDLL('libX11.so.6')
    open_display=bind(x,'XOpenDisplay',p,c.c_char_p)
    display=open_display(os.environ.get('DISPLAY',':0').encode());assert display
    screen=bind(x,'XDefaultScreen',i,p)(display)
    root=bind(x,'XRootWindow',window,p,i)(display,screen)
    create=bind(x,'XCreateSimpleWindow',window,p,window,i,i,u,u,u,window,window)
    drawable=create(display,root,0,0,400,240,0,0,0);assert drawable
    bind(x,'XMapWindow',i,p,window)(display,drawable)
    bind(x,'XSync',i,p,i)(display,0)
    # Active receipt is installed by the locked parent before this dlopen.
    gl=c.CDLL('/tmp/rix-fpga-java256/lib/libGL.so.1')
    attributes=(i*11)(4,5,8,5,9,6,10,5,12,16,0)
    visual=bind(gl,'glXChooseVisual',p,p,i,c.POINTER(i))(display,screen,attributes);assert visual
    context=bind(gl,'glXCreateContext',p,p,p,p,i)(display,visual,None,1);assert context
    make_current=bind(gl,'glXMakeCurrent',i,p,window,p)
    assert make_current(display,drawable,context)
    error=bind(gl,'glGetError',u)
    integer=bind(gl,'glGetIntegerv',None,u,c.POINTER(i))
    floats=bind(gl,'glGetFloatv',None,u,c.POINTER(f))
    active=bind(gl,'glActiveTexture',None,u)
    client=bind(gl,'glClientActiveTexture',None,u)
    coord4=bind(gl,'glMultiTexCoord4f',None,u,f,f,f,f)
    coord2=bind(gl,'glMultiTexCoord2f',None,u,f,f)
    def get_int(name):
        result=i();integer(name,c.byref(result));return result.value
    def coordinates():
        result=(f*4)();floats(0x0b03,result);return list(result)
    def expect_error(value,label):
        actual=error();assert actual==value,(label,actual,value)
    assert get_int(0x84e2)==1;expect_error(0,'context')
    active(0x84c0);client(0x84c0)
    texture=u();bind(gl,'glGenTextures',None,i,c.POINTER(u))(1,c.byref(texture))
    bind(gl,'glBindTexture',None,u,u)(0x0de1,texture.value)
    coord4(0x84c0,.125,.25,.5,1);expect_error(0,'unit0')
    before=coordinates();assert before==[.125,.25,.5,1.0];expect_error(0,'coordinates')
    cases=[]
    for invalid in (0x84bf,0x84c1,0xffffffff):
        active(invalid);expect_error(0x500,'active invalid')
        assert get_int(0x84e0)==0x84c0 and get_int(0x8069)==texture.value
        expect_error(0,'active state');cases.append([invalid,'active'])
        client(invalid);expect_error(0x500,'client invalid')
        assert get_int(0x84e1)==0x84c0;expect_error(0,'client state');cases.append([invalid,'client'])
        coord4(invalid,.9,.8,.7,.6);expect_error(0x500,'coord4 invalid')
        assert coordinates()==before;expect_error(0,'coord4 state');cases.append([invalid,'coord4'])
        coord2(invalid,.7,.6);expect_error(0x500,'coord2 invalid')
        assert coordinates()==before;expect_error(0,'coord2 state');cases.append([invalid,'coord2'])
    strings=bind(gl,'glGetString',c.c_char_p,u)
    version=strings(0x1f02).decode();renderer=strings(0x1f01).decode();expect_error(0,'implementation identity')
    print('JAVA256_TMU_NATIVE_PASS cases=12 state_preserved=1 real_tmu_count=1',flush=True)
    print(json.dumps(dict(cases=cases,java_gl13_verified=False,scope='direct_native_driver_entrypoints',
                         gl_version=version,gl_renderer=renderer)),flush=True)
    make_current(display,0,None)
    bind(gl,'glXDestroyContext',None,p,p)(display,context)
    bind(x,'XFree',i,p)(visual)
    bind(x,'XDestroyWindow',i,p,window)(display,drawable)
    bind(x,'XCloseDisplay',i,p)(display)
if __name__=='__main__':main()
