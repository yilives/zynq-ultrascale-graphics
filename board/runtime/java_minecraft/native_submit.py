#!/usr/bin/env python3
"""Real FPGA back-buffer completion and >4MiB texture upload regression."""
import ctypes as c,hashlib,json,mmap,os,subprocess,sys
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
    error=bind(gl,'glGetError',u);finish=g('Finish');flush=g('Flush')
    def good(label):assert error()==0,label
    def status():return json.loads(subprocess.check_output(['plgpuctl','status']))
    g('Viewport',i,i,i,i)(0,0,400,240)
    for cap in (0xde1,0xb71,0xbe2,0xb60,0xb50,0xb44,0xc11):g('Disable',u)(cap)
    g('MatrixMode',u)(0x1701);g('LoadIdentity')();g('Ortho',d,d,d,d,d,d)(0,400,0,240,-1,1)
    g('MatrixMode',u)(0x1700);g('LoadIdentity')()
    prior=status();checks=[]
    fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
    try:
        for rgb,word in (((1,0,0),0xf800),((0,1,0),0x07e0),((0,0,1),0x001f)):
            g('ClearColor',f,f,f,f)(*rgb,1);g('Clear',u)(0x4100);flush();finish();good('clear finish')
            snapshot=status();assert snapshot['presented']==prior['presented'],'Finish unexpectedly presented'
            expected=word.to_bytes(2,'little')*96000;matches=[]
            for address in (0x60100000,0x60200000):
                with mmap.mmap(fd,192000,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=address) as mem:
                    if mem[:]==expected:matches.append(hex(address))
            assert matches,('Finish returned before complete back buffer',rgb)
            checks.append(dict(rgb=rgb,word=word,matching_buffers=matches,pixels=96000))
    finally:os.close(fd)
    # Each full 256x256 RGB565 texture consumes 128KiB on the device.
    # Forty distinct textures overflow the 4MiB staging list before any drawing.
    count=40;textures=(u*count)();g('GenTextures',i,c.POINTER(u))(count,textures)
    palette=[]
    for n in range(count):
        rgb=((n*53+17)%256,(n*97+31)%256,(n*151+47)%256);palette.append(rgb)
        image=(c.c_ubyte*(256*256*4)).from_buffer_copy(bytes((*rgb,255))*65536)
        g('BindTexture',u,u)(0xde1,textures[n]);g('TexParameteri',u,u,i)(0xde1,0x2801,0x2600);g('TexParameteri',u,u,i)(0xde1,0x2800,0x2600)
        g('TexImage2D',u,i,i,i,i,i,u,u,p)(0xde1,0,0x1908,256,256,0,0x1908,0x1401,image)
    finish();good('large texture upload')
    g('Enable',u)(0xde1);g('Color4f',f,f,f,f)(1,1,1,1)
    g('EnableClientState',u)(0x8074);g('EnableClientState',u)(0x8078);g('DisableClientState',u)(0x8076)
    tex=(f*8)(0,0,1,0,1,1,0,1);g('TexCoordPointer',i,u,i,p)(2,0x1406,0,tex)
    for n in range(count):
        left=(n%8)*50;bottom=(n//8)*48;vertices=(f*8)(left,bottom,left+50,bottom,left+50,bottom+48,left,bottom+48)
        g('BindTexture',u,u)(0xde1,textures[n]);g('VertexPointer',i,u,i,p)(2,0x1406,0,vertices);g('DrawArrays',u,i,i)(7,0,4)
    finish();good('texture grid finish');assert status()['presented']==prior['presented']
    bind(gl,'glXSwapBuffers',None,p,w)(display,window)
    raw=(c.c_ubyte*384000)();g('ReadPixels',i,i,i,i,u,u,p)(0,0,400,240,0x1908,0x1401,raw);good('grid readback');data=bytes(raw)
    def sample(n,flip):
        x=(n%8)*50+25;y=(n//8)*48+24;y=239-y if flip else y
        offset=(y*400+x)*4;return tuple(data[offset:offset+3])
    def near(actual,expected):return all(abs(a-b)<=8 for a,b in zip(actual,expected))
    flip=not near(sample(0,False),palette[0]);observed=[sample(n,flip) for n in range(count)]
    assert all(near(a,b) for a,b in zip(observed,palette)),list(zip(observed,palette))
    folder=Path(sys.argv[1]).parent;(folder/'submit-texture-grid.rgba').write_bytes(data)
    record=dict(passed=True,finish_without_swap=True,finish_back_pixels_verified=288000,finish_checks=checks,
        texture_count=count,device_texture_bytes=count*131072,staging_budget_bytes=4194304,
        palette=palette,observed=observed,readback_y_flip=flip,grid_sha256=hashlib.sha256(data).hexdigest(),
        gl_error=error(),scope='actual_fpga_back_buffer_and_bounded_upload_queue')
    Path(sys.argv[1]).write_text(json.dumps(record,indent=2)+'\n')
    print('JAVA_SUBMIT_PASS textures=40 finish_no_swap=1 back_pixels=288000',flush=True)
    current(display,0,None);bind(gl,'glXDestroyContext',None,p,p)(display,context)
    bind(x,'XFree',i,p)(visual);bind(x,'XDestroyWindow',i,p,w)(display,window);bind(x,'XCloseDisplay',i,p)(display)
if __name__=='__main__':main()
