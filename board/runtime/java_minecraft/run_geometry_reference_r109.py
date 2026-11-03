"""CPU-only golden reference, under the existing board recovery/idle guards."""
import base64,fcntl,hashlib,importlib.util,io,json,os,subprocess,sys,tarfile
from pathlib import Path

"""Validate the actual v23 report without rewriting atomic-v4 evidence."""
def verify_current_v23_proof(proof, before, receipt):
    bit='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
    cnn=dict(magic=0x4e4e5332,shape=(96<<16)|160,capabilities=7,adapter_abi=0x00020001)
    assert proof['passed'] is True and proof['outcome']=='new-loaded-and-verified'
    assert len(receipt)==4 and receipt[:3]==['RIX_FSR_PL_ACTIVE_V1',before['boot_id'],bit]
    assert proof['after']['boot_id']==before['boot_id']
    assert proof['manifest']['images']['new']['sha256']==bit
    assert proof['manifest']['source_sha256']==receipt[3]
    assert proof['after']['cnn']==before['cnn']==cnn
    assert proof['after']['bindings']==before['bindings']
    assert proof['after']['modules']==before['modules']
    assert proof['after']['fsr']['passed'] is True
    assert before['manager_name']=='Xilinx ZynqMP FPGA Manager' and before['manager_state']=='operating'
    return True

root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in manifest['files'].items():assert sha(root/name)==digest
controller=Path('/tmp/fpga_fsr_control.py')
assert sha(controller)=='6f4f34f440094cde3d858ad14f405f9d600cfd4ded5c5f011e9c00f52d09b92d'
spec=importlib.util.spec_from_file_location('frozen_controller',str(controller))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
locks=[]
try:
 for name in m.LOCKS:
  fd=os.open('/tmp/'+name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  locks.append(fd);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 GpuRecoveryGuard().check()
 assert subprocess.run(['pidof','java'],stdout=subprocess.PIPE).returncode==1
 a=m.LinuxAdapter();before=a.snapshot();m.check_idle(before)
 assert before['boot_id']==manifest['boot_id']
 bit='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
 receipt=Path('/tmp/rix-fpga-fsr/active-receipt.txt').read_text().splitlines()
 assert len(receipt)==4 and receipt[:3]==['RIX_FSR_PL_ACTIVE_V1',before['boot_id'],bit]
 proof_path=Path('/tmp/postproc-tests/cc_fsr_fpga_load.json');a.regular_info(proof_path)
 proof=json.loads(proof_path.read_text(),object_pairs_hook=m.unique_object)
 assert verify_current_v23_proof(proof,before,receipt)
 output=root/'arm-output';assert not output.exists()
 run=subprocess.run([str(root/'geometry-reference-arm'),str(output)],pass_fds=locks,
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
 after=a.snapshot();m.check_idle(after)
 assert before['boot_id']==after['boot_id'] and before['gpu']==after['gpu'] and before['post']==after['post']
 assert before['bindings']==after['bindings'] and before['modules']==after['modules']
 assert Path('/tmp/rix-fpga-fsr/active-receipt.txt').read_text().splitlines()==receipt
 assert run.returncode==0 and 'GEOMETRY_REFERENCE_PASS cases=27 triangles=30 band_commands=78 no_hardware_access=1' in run.stdout,run.stdout
 reference=json.loads((output/'reference.json').read_text())
 assert reference['passed'] and reference['hardware_access'] is False and len(reference['cases'])==27
 report=dict(passed=True,CPU_only=True,PL_programmed=False,geometry_accelerator_present=False,
             manifest=manifest,output=run.stdout,before=before,after=after,
             v23_proof_path=str(proof_path),v23_proof_sha256=sha(proof_path),
             files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in output.iterdir()})
 target=root/'arm-guard.json'
 with target.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
 payload=io.BytesIO()
 with tarfile.open(fileobj=payload,mode='w:gz') as archive:
  archive.add(target,arcname='arm-guard.json',recursive=False)
  for path in sorted(output.iterdir()):archive.add(path,arcname='arm-output/'+path.name,recursive=False)
 data=payload.getvalue();assert len(data)<65536
 print('GEOMETRY_ARM_OUTPUT '+base64.b64encode(data).decode(),flush=True)
 print('GEOMETRY_ARM_GUARDED_PASS',flush=True)
finally:
 for fd in reversed(locks):os.close(fd)
