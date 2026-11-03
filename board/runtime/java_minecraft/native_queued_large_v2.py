#!/usr/bin/env python3
"""Two actual FPGA samplers: independent bindings, coordinates, matrices and pixels."""
import ctypes as c,hashlib,json,sys
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
    proc=bind(gl,'glXGetProcAddressARB',p,c.c_char_p)
    names=['glActiveTextureARB','glClientActiveTextureARB']+['glMultiTexCoord'+str(n)+t+v+'ARB' for n in range(1,5) for t in ('d','f','i','s') for v in ('','v')]
    assert len(names)==34 and all(proc(name.encode()) for name in names)
    active=c.CFUNCTYPE(None,u)(proc(b'glActiveTextureARB'));client=c.CFUNCTYPE(None,u)(proc(b'glClientActiveTextureARB'))
    coord=c.CFUNCTYPE(None,u,f,f,f,f)(proc(b'glMultiTexCoord4fARB'))
    error=bind(gl,'glGetError',u);integer=bind(gl,'glGetIntegerv',None,u,c.POINTER(i));floats=bind(gl,'glGetFloatv',None,u,c.POINTER(f))
    def get_int(key):out=i();integer(key,c.byref(out));return out.value
    def get_float(key,n):out=(f*n)();floats(key,out);return list(out)
    def good(label):assert error()==0,label
    assert get_int(0x84e2)==2;good('two real units')
    ids=(u*2)();g('GenTextures',i,c.POINTER(u))(2,ids)
    for unit in range(2):
        active(0x84c0+unit);client(0x84c0+unit);g('BindTexture',u,u)(0xde1,ids[unit]);coord(0x84c0+unit,.25+.5*unit,.5,0,1)
        g('MatrixMode',u)(0x1702);g('LoadIdentity')();g('Translatef',f,f,f)(.25 if unit==0 else -.25,0,0)
    for unit in range(2):
        active(0x84c0+unit);assert get_int(0x8069)==ids[unit]
        assert get_float(0xb03,4)==[.25+.5*unit,.5,0,1]
        assert get_float(0xba8,16)[12]==(.25 if unit==0 else -.25)
        g('LoadIdentity')();good('independent state '+str(unit))
    palette0=[(255,255,255),(255,255,0),(0,255,255),(255,0,255)]
    palette1=[(255,0,0),(0,255,0),(0,0,255),(255,255,255)]
    for unit,palette in enumerate((palette0,palette1)):
        active(0x84c0+unit);g('TexParameteri',u,u,i)(0xde1,0x2801,0x2600);g('TexParameteri',u,u,i)(0xde1,0x2800,0x2600)
        row=b''.join(bytes(rgb)*64 for rgb in palette);image=(c.c_ubyte*(256*256*3)).from_buffer_copy(row*256)
        g('TexImage2D',u,i,i,i,i,i,u,u,p)(0xde1,0,0x1907,256,256,0,0x1907,0x1401,image)
        g('TexEnvi',u,u,i)(0x2300,0x2200,0x1e01 if unit==0 else 0x2100)
    g('Viewport',i,i,i,i)(0,0,400,240);g('MatrixMode',u)(0x1701);g('LoadIdentity')();g('Ortho',d,d,d,d,d,d)(0,400,0,240,-1,1)
    g('MatrixMode',u)(0x1700);g('LoadIdentity')();g('Color4f',f,f,f,f)(1,1,1,1)
    for cap in (0xb71,0xbe2,0xb60,0xb50,0xb44,0xc11):g('Disable',u)(cap)
    g('EnableClientState',u)(0x8074);g('DisableClientState',u)(0x8076)
    expected_passes=[('multiply',[(255,0,0),(0,255,0),(0,0,0),(255,255,255)],True,True),
        ('only-unit0',list(reversed(palette0)),True,False),('only-unit1',palette1,False,True)]
    folder=Path(sys.argv[1]).parent;results=[]
    for label,expected,on0,on1 in expected_passes:
        for unit,on in enumerate((on0,on1)):
            active(0x84c0+unit);g('Enable' if on else 'Disable',u)(0xde1)
        g('ClearColor',f,f,f,f)(0,0,0,1);g('Clear',u)(0x4100)
        # Offscreen geometry exercises real command-buffer rollover without
        # adding millions of visible fragments. The source is redefined/deleted
        # while earlier calls can still be awaiting the worker.
        outside=(f*8)(-2000,-2000,-1900,-2000,-1900,-1900,-2000,-1900)
        g('VertexPointer',i,u,i,p)(2,0x1406,0,outside)
        g('DisableClientState',u)(0x8076)
        for unit in range(2):client(0x84c0+unit);g('DisableClientState',u)(0x8078)
        pressure=bind(gl,'glGenLists',u,i)(1);assert pressure
        g('NewList',u,u)(pressure,0x1300);g('DrawArrays',u,i,i)(7,0,4);g('EndList')()
        for repeat in range(8):g('CallList',u)(pressure)
        g('NewList',u,u)(pressure,0x1300);g('DrawArrays',u,i,i)(7,0,4);g('EndList')()
        g('CallList',u)(pressure);g('DeleteLists',u,i)(pressure,1)
        for tile in range(4):
            left=tile*100;vertices=(f*8)(left,0,left+100,0,left+100,240,left,240)
            arrays=[]
            for unit in range(2):
                client(0x84c0+unit);g('EnableClientState',u)(0x8078)
                coordinate=(3-tile+.5)/4 if unit==0 else (tile+.5)/4
                data=(f*8)(*([coordinate,.5]*4));arrays.append(data);g('TexCoordPointer',i,u,i,p)(2,0x1406,0,data)
            # A mixed integer source is decoded at list compile time.
            colors=(c.c_ubyte*12)(*([255,255,255]*4));g('ColorPointer',i,u,i,p)(3,0x1401,0,colors)
            g('EnableClientState',u)(0x8076)
            if label=='only-unit1':
                client(0x84c1);g('DisableClientState',u)(0x8078);coord(0x84c1,.125,.5,0,1)
                g('DisableClientState',u)(0x8076);g('Color4f',f,f,f,f)(0,0,0,1)
            if label=='only-unit0':
                for q in range(0,8,2):vertices[q]-=5
                for q in range(0,8,2):arrays[0][q]-=.25
            g('VertexPointer',i,u,i,p)(2,0x1406,0,vertices)
            identifier=bind(gl,'glGenLists',u,i)(1);assert identifier
            g('NewList',u,u)(identifier,0x1300);g('DrawArrays',u,i,i)(7,0,4);g('EndList')()
            for q in range(8):vertices[q]=-1000
            for channel in arrays:
                for q in range(8):channel[q]=0
            for q in range(12):colors[q]=0
            if label=='only-unit1':coord(0x84c1,(tile+.5)/4,.5,0,1);g('Color4f',f,f,f,f)(1,1,1,1)
            if label=='only-unit0':
                active(0x84c0);g('MatrixMode',u)(0x1702);g('LoadIdentity')();g('Translatef',f,f,f)(.25,0,0)
                g('MatrixMode',u)(0x1700);g('Translatef',f,f,f)(5,0,0)
            g('CallList',u)(identifier)
            # Replace the same ID with the now-offscreen mutated source before
            # the previous visible draw has necessarily reached the worker.
            g('NewList',u,u)(identifier,0x1300);g('DrawArrays',u,i,i)(7,0,4);g('EndList')()
            g('CallList',u)(identifier);g('DeleteLists',u,i)(identifier,1)
            g('MatrixMode',u)(0x1700);g('LoadIdentity')()
            active(0x84c0);g('MatrixMode',u)(0x1702);g('LoadIdentity')();g('MatrixMode',u)(0x1700)

        # Visible geometry fills every GPU band; the last marker proves tail consumption.
        for unit in range(2):
            active(0x84c0+unit);g('Disable',u)(0xde1)
            client(0x84c0+unit);g('DisableClientState',u)(0x8078)
        g('DisableClientState',u)(0x8076)
        big=(f*(65536*2))(*([-2000.0,-2000.0]*65536))
        for quad in range(16383):
            y=20+(quad%3)*80
            for index,value in enumerate((20,y,24,y,24,y+4,20,y+4)):big[quad*8+index]=value
        for index,value in enumerate((2,2,10,2,10,10,2,10)):big[len(big)-8+index]=value
        g('VertexPointer',i,u,i,p)(2,0x1406,0,big)
        large=bind(gl,'glGenLists',u,i)(1);assert large
        g('NewList',u,u)(large,0x1300);g('DrawArrays',u,i,i)(7,0,65536);g('EndList')()
        g('Color4f',f,f,f,f)(1,1,0,1);g('CallList',u)(large);g('DeleteLists',u,i)(large,1)
        g('Color4f',f,f,f,f)(1,1,1,1)
        for n in range(8):big[n]=0
        g('Finish')();bind(gl,'glXSwapBuffers',None,p,w)(display,window)
        raw=(c.c_ubyte*384000)();g('ReadPixels',i,i,i,i,u,u,p)(0,0,400,240,0x1908,0x1401,raw);data=bytes(raw)
        (folder/('prepared-dual-'+label+'.rgba')).write_bytes(data);good('two sampler '+label)
        marker=list(data[(5*400+5)*4:(5*400+5)*4+3]);assert marker==[255,255,0],('final segment marker',label,marker)
        actual=[]
        for tile in range(4):
            offset=(120*400+tile*100+50)*4;actual.append(list(data[offset:offset+3]))
        assert all(all(abs(a-b)<=8 for a,b in zip(observed,wanted)) for observed,wanted in zip(actual,expected)),(label,actual,expected)
        results.append(dict(name=label,expected=expected,actual=actual,sha256=hashlib.sha256(data).hexdigest()))
        print('JAVA_PREPARED_PIXEL_CASE_PASS',label,flush=True)
    active(0x84c0);client(0x84c0);good('unit0 restored')
    Path(sys.argv[1]).write_text(json.dumps(dict(passed=True,actual_tmu_count=2,arb_entrypoints=34,
        independent_bindings=True,independent_coordinates=True,independent_matrices=True,pixel_cases=results,
        cpu_pixel_fallback=False,java_gl13_verified=False,owned_inputs_mutated=True,call_time_constants=True,call_time_matrices=True,delete_and_redefine_pending=True,pressure_calls=8,large_batch_vertices=65536,last_segment_marker=True,visible_gpu_pressure=True),indent=2)+'\n')
    print('JAVA_PREPARED_NATIVE_PASS actual_tmu_count=2 pixel_cases=3 owned_inputs=1 call_time_state=1',flush=True)
    current(display,0,None);bind(gl,'glXDestroyContext',None,p,p)(display,context)
    bind(x,'XFree',i,p)(visual);bind(x,'XDestroyWindow',i,p,w)(display,window);bind(x,'XCloseDisplay',i,p)(display)
if __name__=='__main__':main()
