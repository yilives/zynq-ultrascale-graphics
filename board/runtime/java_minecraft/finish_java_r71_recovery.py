"""Verify RAM restoration then perform the two original guarded transactions."""
import hashlib,importlib.util,json,os,subprocess,sys,tarfile
from pathlib import Path
root=Path('/tmp');sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
GpuRecoveryGuard().check()
archive=root/'rix-java125-transfer/native.tar.gz'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(archive)=='0e0547dcb353b9bb702439f909a54e1390c50bf8168aa6ae176119c2a545c533'
with tarfile.open(archive) as t:
 for m in t:
  p=Path(m.name);assert not p.is_absolute() and '..' not in p.parts and (m.isfile() or m.isdir())
  target=root/p;assert not target.is_symlink()
  if m.isdir():target.mkdir(parents=True,exist_ok=True)
  else:
   data=t.extractfile(m).read()
   if target.exists():assert target.read_bytes()==data,m.name
   else:
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f:f.write(data)
    target.chmod(m.mode)
jre=root/'rix-java125-transfer/jre.tar.gz'
assert jre.stat().st_size==42135719 and sha(jre)=='83c531747c90d34a39be9f78d037d6ad38a798762502c202a977582275c99f52'
subprocess.run(['tar','-xzf',str(jre),'-C',str(root/'rix-java125')],check=True)
stage=root/'rix-fpga-java256';delivery=json.loads((stage/'delivery.json').read_text())
for name,item in delivery['files'].items():assert sha(stage/name)==item['sha256'],name
subprocess.run(['plgpuctl','enable'],check=True)
for name,manifest in (('fpga_ram_control.py','rix-fpga-v4/manifest.json'),('fpga_fsr_control.py','rix-fpga-fsr/manifest.json')):
 with (root/('r71-recovery-'+name+'.log')).open('xb') as f:
  run=subprocess.run(['python3',str(root/name),'--manifest',str(root/manifest),'--execute'],stdout=f,stderr=subprocess.STDOUT)
 assert run.returncode==0,(name,run.returncode)
GpuRecoveryGuard().check();boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
receipt=(root/'rix-fpga-fsr/active-receipt.txt').read_text().splitlines()
assert receipt[1]==boot and receipt[2]=='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
proofs={}
for n in ('cc_v4_fpga_load.json','cc_fsr_fpga_load.json'):
 r=json.loads((root/'postproc-tests'/n).read_text());assert r['passed'] and r['after']['boot_id']==boot;proofs[n]=r
record=dict(passed=True,new_boot=boot,old_quarantine=json.loads(Path('/opt/rasterix/experimental/gpu-quarantine.json').read_text()),receipt=receipt,proofs=proofs)
(root/'postproc-tests/r71-normal-reboot-recovery.json').write_text(json.dumps(record,indent=2))
print('JAVA_R71_RUNTIME_RECOVERY_PASS '+boot,flush=True)
