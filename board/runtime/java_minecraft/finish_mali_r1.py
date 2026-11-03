"""Restore original disabled PS GPU after destroying all experimental contexts."""
import hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
root=Path('/tmp/rix-mali-java-r1');out=root/'final-state-r1.json';assert not out.exists()
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
record=dict(passed=False,error=None,sd_changed=False,pl_reprogrammed=False)
with m.LinuxAdapter().locks():
 try:
  GpuRecoveryGuard().check();before=m.LinuxAdapter().snapshot();m.check_idle(before);record['before']=before
  for n in (2,3):assert json.loads((root/('world-r%d/result.json'%n)).read_text())['passed']
  assert Path('/sys/module/mali/refcnt').read_text().strip()=='0'
  subprocess.run(['rmmod','mali'],check=True)
  (Path('/sys/kernel/config/device-tree/overlays')/'rix-mali-r1').rmdir()
  assert not Path('/sys/module/mali').exists() and not Path('/dev/mali').exists()
  assert Path('/sys/firmware/devicetree/base/amba/gpu@fd4b0000/status').read_bytes()==b'disabled\0'
  after=m.LinuxAdapter().snapshot();m.check_idle(after);record['after']=after
  assert before['gpu']==after['gpu'] and before['post']==after['post'] and before['cnn']==after['cnn']
  original=json.loads((root/'driver-result/result.json').read_text())['before']
  for key in ('gpu','post','cnn','bindings','module_inventory'):assert after[key]==original[key],key
  GpuRecoveryGuard().check();record.update(passed=True,gpu_status='disabled',guard_passed=True)
 except BaseException as e:record['error']=repr(e)
 finally:out.write_text(json.dumps(record,indent=2)+'\n')
print('MALI_FINAL_STATE '+json.dumps({k:record[k] for k in ('passed','error','sd_changed','pl_reprogrammed')}),flush=True)
sys.exit(0 if record['passed'] else 2)
