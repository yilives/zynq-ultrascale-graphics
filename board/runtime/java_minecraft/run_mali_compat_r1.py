"""Exclusive GL4ES desktop pixel test then real LWJGL context/list test."""
import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
root=Path('/tmp/rix-mali-java-r1');base=Path('/tmp/rix-java125');jre=base/'zulu8.98.0.107-ca-jre8.0.512-linux_aarch64';out=root/'compat-r1';out.mkdir(exist_ok=False)
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard,GameLog
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
record=dict(passed=False,error=None,tests={});env=os.environ.copy();(root/'home').mkdir(exist_ok=True)
env.update(DISPLAY=':0',HOME=str(root/'home'),LD_LIBRARY_PATH=':'.join(map(str,[root/'lib',base/'native',base/'native/deps',jre/'lib/aarch64',jre/'lib/aarch64/server'])),LIBGL_ES='2',LIBGL_FB='3',LIBGL_EGL='/usr/lib/headless/libMali.so.9.0',LIBGL_GLES='/usr/lib/headless/libMali.so.9.0',LIBGL_NOERROR='0',LIBGL_SHRINK='0',LIBGL_SILENTSTUB='0')
with m.LinuxAdapter().locks():
 try:
  GpuRecoveryGuard().check();before=m.LinuxAdapter().snapshot();m.check_idle(before);record['before']=before
  for name,command,marker in [
   ('native',['python3',str(root/'mali_gl4es_dual_r1.py'),str(out/'native.json')],'JAVA_DUAL_TEXTURE_PASS'),
   ('java',[str(jre/'bin/java'),'-Xms64m','-Xmx512m','-XX:+UseSerialGC','-Djava.awt.headless=false','-Dsun.java2d.opengl=false','-Dsun.java2d.xrender=false','-Dorg.lwjgl.librarypath='+str(base/'native'),'-cp',str(root/'classes')+':'+str(base/'libs/*'),'MaliJavaProbe',str(out/'java.rgba')],'MALI_JAVA_PROBE_PASS')]:
   start=time.monotonic()
   with GameLog(out/(name+'.log')) as log:
    process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True);log.attach(process.stdout)
    try:code=process.wait(timeout=45)
    except subprocess.TimeoutExpired:
     process.terminate();code=process.wait(timeout=10);raise RuntimeError('Mali compatibility probe timeout: '+name)
   text=(out/(name+'.log')).read_text(errors='replace');record['tests'][name]=dict(code=code,seconds=time.monotonic()-start,marker=marker in text,log=log.stats());assert code==0 and marker in text,(name,text[-3000:])
  after=m.LinuxAdapter().snapshot();m.check_idle(after);record['after']=after
  assert before['gpu']==after['gpu'] and before['post']==after['post'] and before['cnn']==after['cnn']
  record['passed']=True
 except BaseException as e:record['error']=repr(e)
 finally:
  record['environment']={k:env[k] for k in ('DISPLAY','HOME','LD_LIBRARY_PATH','LIBGL_ES','LIBGL_FB','LIBGL_EGL','LIBGL_GLES','LIBGL_NOERROR','LIBGL_SHRINK')}
  (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('MALI_COMPAT_RESULT '+json.dumps({k:record[k] for k in ('passed','error','tests')}),flush=True)
sys.exit(0 if record['passed'] else 2)
