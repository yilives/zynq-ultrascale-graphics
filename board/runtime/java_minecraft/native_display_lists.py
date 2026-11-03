#!/usr/bin/env python3
"""Pixel equivalence of real RasterIX rendering with owned display lists."""
import ctypes as c,hashlib,json,os,sys
from pathlib import Path
def bind(lib,name,result,*args):
    fn=getattr(lib,name);fn.restype=result;fn.argtypes=list(args);return fn
def main():
    p=c.c_void_p;u=c.c_uint;i=c.c_int;f=c.c_float;d=c.c_double;w=c.c_ulong
    x=c.CDLL('libX11.so.6');display=bind(x,'XOpenDisplay',p,c.c_char_p)(b':0');assert display
    screen=bind(x,'XDefaultScreen',i,p)(display);root=bind(x,'XRootWindow',w,p,i)(display,screen)
    window=bind(x,'XCreateSimpleWindow',w,p,w,i,i,u,u,u,w,w)(display,root,0,0,400,240,0,0,0)
    bind(x,'XMapWindow',i,p,w)(display,window);bind(x,'XSync',i,p,i)(display,0)
    gl=c.CDLL('/tmp/rix-fpga-java256/lib/libGL.so.1')
    visual=bind(gl,'glXChooseVisual',p,p,i,c.POINTER(i))(display,screen,(i*11)(4,5,8,5,9,6,10,5,12,16,0))
    context=bind(gl,'glXCreateContext',p,p,p,p,i)(display,visual,None,1);assert context
    current=bind(gl,'glXMakeCurrent',i,p,w,p);assert current(display,window,context)
    def g(name,*args):return bind(gl,'gl'+name,None,*args)
    err=bind(gl,'glGetError',u);gen=bind(gl,'glGenLists',u,i);is_list=bind(gl,'glIsList',c.c_ubyte,u)
    new=g('NewList',u,u);end=g('EndList');call=g('CallList',u);delete=g('DeleteLists',u,i)
    color=g('Color3f',f,f,f);translate=g('Translated',d,d,d)
    vertex=g('VertexPointer',i,u,i,p);colorptr=g('ColorPointer',i,u,i,p)
    on=g('EnableClientState',u);off=g('DisableClientState',u)
    arrays=g('DrawArrays',u,i,i);elements=g('DrawElements',u,i,u,p)
    matrix=g('MatrixMode',u);identity=g('LoadIdentity');clear=g('Clear',u)
    integer=bind(gl,'glGetIntegerv',None,u,c.POINTER(i));floats=bind(gl,'glGetFloatv',None,u,c.POINTER(f))
    swap=bind(gl,'glXSwapBuffers',None,p,w);read=g('ReadPixels',i,i,i,i,u,u,p)
    def good(label):assert err()==0,label
    def get_int(key):v=i();integer(key,c.byref(v));return v.value
    def values(key,n):v=(f*n)();floats(key,v);return list(v)
    def frame():
        for cap in (0xde1,0xb71,0xbe2,0xb60,0xb50,0xb44,0xc11):g('Disable',u)(cap)
        g('Viewport',i,i,i,i)(0,0,400,240);matrix(0x1701);identity();g('Ortho',d,d,d,d,d,d)(0,400,0,240,-1,1)
        matrix(0x1700);identity();off(0x8076);off(0x8075);off(0x8078);on(0x8074)
        g('ClearColor',f,f,f,f)(0,0,0,1);clear(0x4100);color(1,1,1)
    def pixels():
        swap(display,window);raw=(c.c_ubyte*(400*240*4))();read(0,0,400,240,0x1908,0x1401,raw);good('frame read');return bytes(raw)
    def triangle(x=10,y=10):
        data=(f*6)(x,y,x+60,y,x,y+60);vertex(2,0x1406,0,data);arrays(4,0,3);return data
    def equal(name,reference):
        actual=pixels();assert actual==reference,(name,sum(a!=b for a,b in zip(actual,reference)))
        colored=sum(any(reference[k+j]>128 for j in range(3)) for k in range(0,len(reference),4))
        assert colored==0 if name=='deleted_nested_list_is_noop' else 1500<=colored<=2100,(name,colored)
        cases.append(dict(name=name,rgba_bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),different_bytes=0))
        print('DISPLAY_LIST_CASE_PASS',name,flush=True)
    cases=[];base=gen(3000000);assert base==1 and not is_list(base);good('large interval')
    delete(16,16);assert gen(16)==16;good('reuse interval')
    # Arrays must be copied at compile time; scalar state and matrices must not execute then.
    vertices=(f*6)(10,10,70,10,10,70);colors=(f*9)(1,0,0,1,0,0,1,0,0)
    frame();vertex(2,0x1406,0,vertices);colorptr(3,0x1406,0,colors);on(0x8076);arrays(4,0,3);reference=pixels()
    frame();before_color=values(0xb00,4);before_matrix=values(0xba6,16)
    new(base,0x1300);assert get_int(0xb33)==base and get_int(0xb30)==0x1300
    color(1,0,1);vertex(2,0x1406,0,vertices);colorptr(3,0x1406,0,colors);on(0x8076);arrays(4,0,3);end()
    assert is_list(base) and get_int(0xb33)==0
    assert values(0xb00,4)==before_color and values(0xba6,16)==before_matrix;good('compile has no server side effects')
    for n in range(6):vertices[n]=-200
    for n in range(9):colors[n]=0
    frame();call(base);equal('array_snapshot_and_compile_state',reference)
    # Constants and transforms are resolved when calling the list, not frozen with arrays.
    frame();color(0,1,0);translate(100,30,0);triangle();reference=pixels()
    frame();color(1,0,0);new(base+1,0x1300);data=triangle();end()
    for n in range(6):data[n]=-300
    frame();color(0,1,0);translate(100,30,0);call(base+1);equal('call_time_matrix_and_constant',reference)
    # Unsigned-byte indices above 127 and their referenced positions are owned too.
    vertices=(f*(131*2))();vertices[256:262]=[230,20,290,20,230,80];indices=(c.c_ubyte*3)(128,129,130)
    frame();color(0,0,1);vertex(2,0x1406,0,vertices);elements(4,3,0x1401,indices);reference=pixels()
    frame();new(base+2,0x1300);color(0,0,1);vertex(2,0x1406,0,vertices);elements(4,3,0x1401,indices);end()
    for n in range(len(vertices)):vertices[n]=0
    for n in range(3):indices[n]=0
    frame();call(base+2);equal('unsigned_byte_index_snapshot',reference)
    # Compile-and-execute must not double-record internal helper calls.
    frame();translate(40,50,0);color(1,1,0);triangle();reference=pixels()
    frame();new(base+3,0x1301);translate(40,50,0);color(1,1,0);triangle();end();equal('compile_and_execute_once',reference)
    frame();call(base+3);equal('compile_and_execute_replay_once',reference)
    # A parent calls the current definition of its child.
    new(base+4,0x1300);call(base+1);end()
    new(base+1,0x1300);color(0,1,1);triangle(160,120);end()
    frame();color(0,1,1);triangle(160,120);reference=pixels()
    frame();call(base+4);equal('nested_late_binding',reference)
    # List offsets are copied; the base remains a server command executed with the list.
    offsets=(c.c_ubyte*1)(1);new(base+5,0x1300);g('ListBase',u)(base);g('CallLists',i,u,p)(1,0x1401,offsets);end();offsets[0]=2
    frame();call(base+5);equal('call_lists_owned_offsets_and_base',reference)
    # Immediate mode commands are replayed, including copied vector arguments.
    point=(f*2)(320,100)
    def immediate():
        color(1,0,1);g('Begin',u)(4);g('Vertex2fv',c.POINTER(f))(point);g('Vertex2f',f,f)(380,100);g('Vertex2f',f,f)(320,160);g('End')()
    frame();immediate();reference=pixels();frame();new(base+6,0x1300);immediate();end();point[0]=point[1]=-400
    frame();call(base+6);equal('immediate_vector_snapshot',reference)
    delete(base+1,1);assert not is_list(base+1)
    frame();blank=pixels();frame();call(base+4);equal('deleted_nested_list_is_noop',blank)
    good('all display list cases')
    record=dict(passed=True,cases=cases,reserved_names=3000000,max_list_nesting=get_int(0xb31),
        gl_version=bind(gl,'glGetString',c.c_char_p,u)(0x1f02).decode(),java_gl13_verified=False,world_verified=False,
        rendering='real_fpga_rasterix',scope='display_list_geometry_matrix_fixed_state')
    Path(sys.argv[1]).write_text(json.dumps(record,indent=2)+'\n')
    assert len(cases)==9
    print('JAVA256_DISPLAY_LIST_PASS cases=9 byte_exact_pixels=1',flush=True)
    current(display,0,None);bind(gl,'glXDestroyContext',None,p,p)(display,context)
    bind(x,'XFree',i,p)(visual);bind(x,'XDestroyWindow',i,p,w)(display,window);bind(x,'XCloseDisplay',i,p)(display)
if __name__=='__main__':main()
