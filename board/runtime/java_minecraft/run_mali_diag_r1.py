"""Bounded menu-only attribution run. All timing is explicitly diagnostic."""
import importlib.util,os,subprocess,sys,json
from pathlib import Path
root=Path('/tmp/rix-mali-java-r1');base=Path('/tmp/rix-java125');out=root/'diagnostic-r1';out.mkdir(exist_ok=False)
jre=base/'zulu8.98.0.107-ca-jre8.0.512-linux_aarch64'
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard,GameLog
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
native=out/'native';native.mkdir();(native/'liblwjgl.so').write_bytes((root/'liblwjgl-mali-diag.so').read_bytes())
env=os.environ.copy();env.update(DISPLAY=':0',HOME=str(root/'home'),LD_LIBRARY_PATH=':'.join(map(str,[root/'lib',native,base/'native/deps',jre/'lib/aarch64',jre/'lib/aarch64/server'])),LIBGL_ES='2',LIBGL_FB='3',LIBGL_EGL='/usr/lib/headless/libMali.so.9.0',LIBGL_GLES='/usr/lib/headless/libMali.so.9.0',LIBGL_NOERROR='0',LIBGL_SHRINK='0',LIBGL_SILENTSTUB='0')
cmd=[str(jre/'bin/java'),'-Xms64m','-Xmx512m','-XX:+UseSerialGC','-Duser.home='+str(root/'home'),'-Djava.awt.headless=false','-Dsun.java2d.opengl=false','-Dsun.java2d.xrender=false','-Dorg.lwjgl.librarypath='+str(native),'-Drix.java125.closeSeconds=25','-cp',str(root/'classes')+':'+str(base/'probe')+':'+str(base/'libs/*'),'Java256ClientHarness']
with m.LinuxAdapter().locks():
 GpuRecoveryGuard().check();before=m.LinuxAdapter().snapshot();m.check_idle(before)
 with GameLog(out/'minecraft.log') as log:
  child=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True);log.attach(child.stdout)
  try:code=child.wait(timeout=50)
  except subprocess.TimeoutExpired:child.terminate();code=child.wait(timeout=10)
 after=m.LinuxAdapter().snapshot();m.check_idle(after)
 assert before['gpu']==after['gpu'] and before['post']==after['post'] and before['cnn']==after['cnn']
 (out/'result.json').write_text(json.dumps(dict(diagnostic_only=True,code=code,before=before,after=after,log=log.stats()),indent=2)+'\n')
print('MALI_DIAGNOSTIC_DONE code='+str(code),flush=True)
