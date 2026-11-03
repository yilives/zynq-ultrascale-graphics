"""Real vendor Mali GLES2: shader MVP + two samplers, complete RGBA reference."""
import ctypes as C,hashlib,json,os,sys,time
from pathlib import Path
root=Path('/tmp/rix-mali-java-r1');out=root/'gles-headless-r1';out.mkdir(exist_ok=False)
lib=C.CDLL('/usr/lib/headless/libMali.so.9.0',mode=C.RTLD_GLOBAL)
u=C.c_uint;i=C.c_int;p=C.c_void_p;f=C.c_float
def fn(name,ret,args):
 fun=getattr(lib,name);fun.restype=ret;fun.argtypes=args;return fun
record=dict(passed=False,error=None,backend='/usr/lib/headless/libMali.so.9.0',size=[400,240])
display=context=surface=None
try:
 getDisplay=fn('eglGetDisplay',p,[p]);initialize=fn('eglInitialize',u,[p,C.POINTER(i),C.POINTER(i)])
 display=getDisplay(None);major=i();minor=i();assert initialize(display,C.byref(major),C.byref(minor)),'eglInitialize failed'
 query=fn('eglQueryString',C.c_char_p,[p,i]);record['egl_version']=[major.value,minor.value];record['egl_vendor']=query(display,0x3053).decode()
 attrs=(i*15)(0x3033,1,0x3040,4,0x3024,8,0x3023,8,0x3022,8,0x3021,8,0x3025,16,0x3038)
 config=p();count=i();assert fn('eglChooseConfig',u,[p,C.POINTER(i),C.POINTER(p),i,C.POINTER(i)])(display,attrs,C.byref(config),1,C.byref(count)) and count.value==1
 assert fn('eglBindAPI',u,[u])(0x30a0)
 surface=fn('eglCreatePbufferSurface',p,[p,p,C.POINTER(i)])(display,config,(i*5)(0x3057,400,0x3056,240,0x3038));assert surface
 context=fn('eglCreateContext',p,[p,p,p,C.POINTER(i)])(display,config,None,(i*3)(0x3098,2,0x3038));assert context
 assert fn('eglMakeCurrent',u,[p,p,p,p])(display,surface,surface,context)
 getString=fn('glGetString',C.c_char_p,[u]);record['renderer']=getString(0x1f01).decode();record['vendor']=getString(0x1f00).decode();record['version']=getString(0x1f02).decode();record['extensions']=getString(0x1f03).decode()
 assert 'mali' in record['renderer'].lower() and 'llvmpipe' not in record['renderer'].lower()
 descriptors=[]
 for fd in Path('/proc/self/fd').iterdir():
  try:descriptors.append(os.readlink(str(fd)))
  except OSError:pass
 record['mali_device_open']=any(x=='/dev/mali' for x in descriptors);assert record['mali_device_open']
 def shader(kind,text):
  s=fn('glCreateShader',u,[u])(kind);source=(C.c_char_p*1)(text.encode());fn('glShaderSource',None,[u,i,C.POINTER(C.c_char_p),C.POINTER(i)])(s,1,source,None);fn('glCompileShader',None,[u])(s)
  status=i();fn('glGetShaderiv',None,[u,u,C.POINTER(i)])(s,0x8b81,C.byref(status))
  log=C.create_string_buffer(8192);fn('glGetShaderInfoLog',None,[u,i,C.POINTER(i),C.c_char_p])(s,8192,None,log);assert status.value,log.value
  return s
 vs=shader(0x8b31,'attribute vec2 position;uniform mat4 mvp;varying vec2 uv;void main(){uv=position*0.5+0.5;gl_Position=mvp*vec4(position,0.0,1.0);}')
 fs=shader(0x8b30,'precision mediump float;varying vec2 uv;uniform sampler2D tex0;uniform sampler2D tex1;void main(){gl_FragColor=texture2D(tex0,uv)*texture2D(tex1,uv);}')
 program=fn('glCreateProgram',u,[])();attach=fn('glAttachShader',None,[u,u]);attach(program,vs);attach(program,fs);fn('glBindAttribLocation',None,[u,u,C.c_char_p])(program,0,b'position');fn('glLinkProgram',None,[u])(program)
 status=i();fn('glGetProgramiv',None,[u,u,C.POINTER(i)])(program,0x8b82,C.byref(status));assert status.value,'program link failed';fn('glUseProgram',None,[u])(program)
 uniform=fn('glGetUniformLocation',i,[u,C.c_char_p]);matrix=(f*16)(.5,0,0,0,0,.5,0,0,0,0,1,0,.25,0,0,1);fn('glUniformMatrix4fv',None,[i,i,C.c_ubyte,C.POINTER(f)])(uniform(program,b'mvp'),1,0,matrix)
 textures=(u*2)();fn('glGenTextures',None,[i,C.POINTER(u)])(2,textures)
 colors0=bytes([255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255]);colors1=bytes([255,0,255,255])*4
 for index,data in enumerate((colors0,colors1)):
  fn('glActiveTexture',None,[u])(0x84c0+index);fn('glBindTexture',None,[u,u])(0x0de1,textures[index])
  for key,value in ((0x2801,0x2600),(0x2800,0x2600),(0x2802,0x812f),(0x2803,0x812f)):fn('glTexParameteri',None,[u,u,i])(0x0de1,key,value)
  storage=C.create_string_buffer(data);fn('glTexImage2D',None,[u,i,i,i,i,i,u,u,p])(0x0de1,0,0x1908,2,2,0,0x1908,0x1401,C.cast(storage,p));fn('glUniform1i',None,[i,i])(uniform(program,('tex'+str(index)).encode()),index)
 vertices=(f*12)(-1,-1,1,-1,1,1,-1,-1,1,1,-1,1);fn('glVertexAttribPointer',None,[u,i,u,C.c_ubyte,i,p])(0,2,0x1406,0,0,C.cast(vertices,p));fn('glEnableVertexAttribArray',None,[u])(0)
 fn('glViewport',None,[i,i,i,i])(0,0,400,240);fn('glDisable',None,[u])(0x0bd0);fn('glClearColor',None,[f,f,f,f])(0,0,0,1);fn('glClear',None,[u])(0x4000);fn('glDrawArrays',None,[u,i,i])(4,0,6);fn('glFinish',None,[])()
 data=(C.c_ubyte*(400*240*4))();fn('glReadPixels',None,[i,i,i,i,u,u,p])(0,0,400,240,0x1908,0x1401,C.cast(data,p));raw=bytes(data)
 assert fn('glGetError',u,[])()==0
 expected=bytearray(bytes([0,0,0,255])*(400*240))
 for y in range(60,180):
  for x in range(150,350):
   color=([255,0,0,255] if x<250 else [0,0,0,255]) if y<120 else ([0,0,255,255] if x<250 else [255,0,255,255])
   offset=(y*400+x)*4;expected[offset:offset+4]=bytes(color)
 (out/'actual.rgba').write_bytes(raw);(out/'expected.rgba').write_bytes(expected)
 record.update(rgba_sha256=hashlib.sha256(raw).hexdigest(),expected_sha256=hashlib.sha256(expected).hexdigest(),pixels=96000,mvp_executed_in_shader=True,two_samplers=True,mismatching_bytes=sum(a!=b for a,b in zip(raw,expected)))
 assert raw==bytes(expected),record['mismatching_bytes'];record['passed']=True
except BaseException as e:
 record['error']=repr(e);record['egl_error']=hex(fn('eglGetError',u,[])())
finally:
 if display:
  if context:fn('eglMakeCurrent',u,[p,p,p,p])(display,None,None,None);fn('eglDestroyContext',u,[p,p])(display,context)
  if surface:fn('eglDestroySurface',u,[p,p])(display,surface)
  fn('eglTerminate',u,[p])(display)
 (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
 print('MALI_GLES_RESULT '+json.dumps({k:record.get(k) for k in ('passed','renderer','version','mali_device_open','mismatching_bytes','error')}),flush=True)
sys.exit(0 if record['passed'] else 2)
