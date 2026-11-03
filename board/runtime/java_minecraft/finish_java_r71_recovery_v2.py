"""Supply the byte-verified rollback image; preserve refused preflight journal."""
import hashlib,json,subprocess,sys
from pathlib import Path
root=Path('/tmp');sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
GpuRecoveryGuard().check()
reports=root/'postproc-tests';failed=reports/'cc_fsr_fpga_load.json';r=json.loads(failed.read_text())
assert not r['passed'] and not r['device_mutation_started'] and r['outcome']=='preflight-failed-no-device-change'
manifest=json.loads((root/'rix-fpga-fsr/manifest.json').read_text());source=root/'rix-fpga-v4/new.bin';target=root/'rix-fpga-fsr/old.bin'
data=source.read_bytes();assert len(data)==manifest['images']['old']['bytes'] and hashlib.sha256(data).hexdigest()==manifest['images']['old']['sha256']
proof=json.loads((reports/'cc_v4_fpga_load.json').read_text());assert proof['passed'] and proof['images']['new']['sha256']==manifest['images']['old']['sha256']
assert not target.exists()
with target.open('xb') as f:f.write(data)
target.chmod(0o600)
preserved=reports/'cc_fsr_fpga_load-r71-missing-old-failed.json';assert not preserved.exists();failed.rename(preserved)
with (root/'r71-recovery-fsr-v2.log').open('xb') as f:run=subprocess.run(['python3','/tmp/fpga_fsr_control.py','--manifest','/tmp/rix-fpga-fsr/manifest.json','--execute'],stdout=f,stderr=subprocess.STDOUT)
assert run.returncode==0,run.returncode
GpuRecoveryGuard().check();boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();receipt=(root/'rix-fpga-fsr/active-receipt.txt').read_text().splitlines()
assert receipt[1]==boot and receipt[2]=='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
proofs={}
for n in ('cc_v4_fpga_load.json','cc_fsr_fpga_load.json'):
 item=json.loads((reports/n).read_text());assert item['passed'] and item['after']['boot_id']==boot;proofs[n]=item
record=dict(passed=True,new_boot=boot,old_quarantine=json.loads(Path('/opt/rasterix/experimental/gpu-quarantine.json').read_text()),receipt=receipt,proofs=proofs,refused_preflight=r)
(reports/'r71-normal-reboot-recovery.json').write_text(json.dumps(record,indent=2))
print('JAVA_R71_RUNTIME_RECOVERY_PASS '+boot,flush=True)
