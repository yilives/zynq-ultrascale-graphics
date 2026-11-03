"""Actual FPGA pixels after identical, partial, changed and reallocated textures."""
import ctypes as c,hashlib,json,os,sys,time
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
    error=bind(gl,'glGetError',u);proc=bind(gl,'glXGetProcAddressARB',p,c.c_char_p)
    active=c.CFUNCTYPE(None,u)(proc(b'glActiveTextureARB'))
    active(0x84c1);g('Disable',u)(0xde1);active(0x84c0);g('Enable',u)(0xde1)
    for cap in (0xb71,0xbe2,0xb60,0xb50,0xb44,0xc11):g('Disable',u)(cap)
    g('Viewport',i,i,i,i)(0,0,400,240);g('MatrixMode',u)(0x1701);g('LoadIdentity')();g('Ortho',d,d,d,d,d,d)(0,400,0,240,-1,1)
    g('MatrixMode',u)(0x1700);g('LoadIdentity')();g('Color4f',f,f,f,f)(1,1,1,1)
    g('TexEnvi',u,u,i)(0x2300,0x2200,0x1e01)
    texture=u();g('GenTextures',i,c.POINTER(u))(1,c.byref(texture))
    def allocate():
        g('BindTexture',u,u)(0xde1,texture.value)
        for key in (0x2800,0x2801):g('TexParameteri',u,u,i)(0xde1,key,0x2600)
        data=(c.c_ubyte*(256*256*3)).from_buffer_copy(bytes((0,0,255))*65536)
        g('TexImage2D',u,i,i,i,i,i,u,u,p)(0xde1,0,0x1907,256,256,0,0x1907,0x1401,data)
    allocate();results=[];folder=Path(sys.argv[1]).parent
    def update(rgb,size=16):
        data=(c.c_ubyte*(size*size*3)).from_buffer_copy(bytes(rgb)*(size*size));offset=0 if size==256 else 96
        g('TexSubImage2D',u,i,i,i,i,i,u,u,p)(0xde1,0,offset,offset,size,size,0x1907,0x1401,data)
    cases=[('initial-blue',(0,0,255),True),('same-blue',(0,0,255),True),('red-patch',(255,0,0),True),('outside',(0,0,255),False),
           ('same-red',(255,0,0),True),('green-patch',(0,255,0),True),('blue-restore',(0,0,255),True),('reallocated-blue',(0,0,255),True)]
    for index,(label,rgb,inside) in enumerate(cases):
        if index in (1,7):time.sleep(.55)
        if index==1:update((0,0,255),256)
        if index in (2,4,5,6):update(rgb)
        if index==7:
            g('DeleteTextures',i,c.POINTER(u))(1,c.byref(texture));g('GenTextures',i,c.POINTER(u))(1,c.byref(texture));allocate()
        coordinate=(100.5 if inside else 10.5)/256
        g('ClearColor',f,f,f,f)(0,0,0,1);g('Clear',u)(0x4100);g('Begin',u)(7)
        for vx,vy in ((0,0),(400,0),(400,240),(0,240)):
            g('TexCoord2f',f,f)(coordinate,coordinate);g('Vertex2f',f,f)(vx,vy)
        g('End')();g('Finish')();bind(gl,'glXSwapBuffers',None,p,w)(display,window)
        raw=(c.c_ubyte*384000)();g('ReadPixels',i,i,i,i,u,u,p)(0,0,400,240,0x1908,0x1401,raw)
        assert error()==0,label;data=bytes(raw);assert data==bytes((*rgb,255))*96000,(label,data[192000:192004])
        (folder/('shadow-native-'+label+'.rgba')).write_bytes(data);results.append(dict(name=label,sha256=hashlib.sha256(data).hexdigest(),pixels=96000))
    Path(sys.argv[1]).write_text(json.dumps(dict(passed=True,cases=results,dedup_enabled=os.environ.get('RIX_JAVA_TEXTURE_DEDUP')=='1',cpu_pixel_fallback=False),indent=2)+'\n')
    print('JAVA_TEXTURE_SHADOW_NATIVE_PASS cases=8 pixels=768000 identical_partial_reuse=1',flush=True)
    current(display,0,None);bind(gl,'glXDestroyContext',None,p,p)(display,context);bind(x,'XFree',i,p)(visual)
    bind(x,'XDestroyWindow',i,p,w)(display,window);bind(x,'XCloseDisplay',i,p)(display)
if __name__=='__main__':main()
