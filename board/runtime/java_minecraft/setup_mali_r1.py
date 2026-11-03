"""Enable the disabled PS GPU using a removable overlay and matching RAM module."""
import gzip,hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path('/tmp/rix-mali-java-r1');OUT=ROOT/'driver-result';OUT.mkdir(exist_ok=False)
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
manifest=json.loads((ROOT/'driver-manifest.json').read_text());record=dict(passed=False,sd_changed=False,pl_reprogrammed=False,error=None)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def command(args):
 r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=25)
 record.setdefault('commands',[]).append(dict(args=args,returncode=r.returncode,output=r.stdout));assert r.returncode==0,r.stdout
 return r.stdout
overlay=Path('/sys/kernel/config/device-tree/overlays/rix-mali-r1');created=False;loaded=False
with m.LinuxAdapter().locks():
 try:
  GpuRecoveryGuard().check();before=m.LinuxAdapter().snapshot();m.check_idle(before);record['before']=before
  assert before['boot_id']=='17eb445e-5b38-40ab-9729-9b2dd89a0f12'
  assert hashlib.sha256(gzip.decompress(Path('/proc/config.gz').read_bytes())).hexdigest()==manifest['kernel_config_sha256']
  assert sha(Path('/sys/kernel/notes'))==manifest['kernel_notes_sha256']
  assert not Path('/dev/mali').exists() and not Path('/sys/module/mali').exists()
  dt=Path('/sys/firmware/devicetree/base/amba/gpu@fd4b0000/status');assert dt.read_bytes()==b'disabled\0'
  for name,item in manifest['files'].items():assert sha(ROOT/name)==item
  assert not overlay.exists();overlay.mkdir();created=True
  with (overlay/'dtbo').open('wb') as f:f.write((ROOT/'gpu-enable.dtbo').read_bytes())
  assert dt.read_bytes()==b'okay\0'
  command(['insmod',str(ROOT/'mali.ko'),'mali_max_job_runtime=5000']);loaded=True
  deadline=time.monotonic()+10
  while not Path('/dev/mali').exists() and time.monotonic()<deadline:time.sleep(.1)
  assert Path('/dev/mali').exists(),'Mali character device missing'
  record['driver_bindings']=[str(p) for p in Path('/sys/bus/platform/drivers/mali').glob('*')]
  record['device_mode']=oct(Path('/dev/mali').stat().st_mode)
  after=m.LinuxAdapter().snapshot();m.check_idle(after)
  assert before['gpu']==after['gpu'] and before['post']==after['post'] and before['cnn']==after['cnn']
  record.update(passed=True,after=after,overlay=str(overlay),module_sha256=sha(ROOT/'mali.ko'))
 except BaseException as e:
  record['error']=repr(e)
  if loaded:
   try:command(['rmmod','mali'])
   except BaseException as x:record['rollback_module_error']=repr(x)
  if created and not Path('/sys/module/mali').exists():
   try:overlay.rmdir()
   except BaseException as x:record['rollback_overlay_error']=repr(x)
 finally:
  record['kernel_tail']=subprocess.check_output(['dmesg'],text=True)[-10000:]
  (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('MALI_DRIVER_SETUP_RESULT '+json.dumps({k:record[k] for k in ('passed','sd_changed','pl_reprogrammed','error')}),flush=True)
sys.exit(0 if record['passed'] else 2)
