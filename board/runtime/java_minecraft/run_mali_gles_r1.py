"""Exclusive bounded native Mali check; existing PL must remain unchanged."""
import importlib.util,json,subprocess,sys
from pathlib import Path
root=Path('/tmp/rix-mali-java-r1');sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
record=dict(passed=False,error=None)
with m.LinuxAdapter().locks():
 try:
  GpuRecoveryGuard().check();before=m.LinuxAdapter().snapshot();m.check_idle(before);record['before']=before
  assert not subprocess.run(['pidof','java','ClassiCube','rix-fsr-pl'],stdout=subprocess.PIPE).stdout
  with (root/'gles-headless-r1.log').open('xb') as f:
   run=subprocess.run(['python3','/tmp/mali_gles_probe_r1.py'],stdout=f,stderr=subprocess.STDOUT,timeout=30)
  result=json.loads((root/'gles-headless-r1/result.json').read_text());record['gles']=result
  assert run.returncode==0 and result['passed'],result.get('error')
  after=m.LinuxAdapter().snapshot();m.check_idle(after);record['after']=after
  assert before['gpu']==after['gpu'] and before['post']==after['post'] and before['cnn']==after['cnn']
  record['passed']=True
 except BaseException as e:record['error']=repr(e)
 finally:
  (root/'gles-acceptance-r1.json').write_text(json.dumps(record,indent=2)+'\n')
print('MALI_NATIVE_CHECK '+json.dumps(dict(passed=record['passed'],error=record['error'],gles=record.get('gles',{}))),flush=True)
sys.exit(0 if record['passed'] else 2)
