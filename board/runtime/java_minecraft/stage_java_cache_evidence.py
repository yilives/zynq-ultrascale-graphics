"""Stage completed evidence for read-only JTAG retrieval under all runtime locks."""
import hashlib,importlib.util,json,mmap,os,subprocess,sys,tarfile,time
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
root=Path('/tmp');spec=importlib.util.spec_from_file_location('frozen',root/'fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
with m.LinuxAdapter().locks():
 GpuRecoveryGuard().check();m.check_idle(m.LinuxAdapter().snapshot())
 metadata=[]
 for rev in ('r75','r76','r77','r78'):
  subprocess.run(['python3','/tmp/collect_java_cache_export_v8.py','--revision',rev],check=True,stdout=subprocess.DEVNULL)
  p=root/'postproc-tests'/('java256-'+rev+'-evidence-parts.json');entry=json.loads(p.read_text())
  archive=p.with_name('java256-'+rev+'-menu-evidence.tar.gz');assert sha(archive)==entry['sha256'] and archive.stat().st_size==entry['bytes']
  metadata.append(entry)
 state=m.LinuxAdapter().snapshot();m.check_idle(state)
 state.update(stage_delivery_sha256=sha(root/'rix-fpga-java256/delivery.json'),stage_graphics_sha256=sha(root/'rix-fpga-java256/lib/libGL.so.1'),quarantine_guard_passed=True)
 state_path=root/'java-cache-r78-final-state.json';assert not state_path.exists();state_path.write_text(json.dumps(state,indent=2))
 meta=root/'java-cache-r75-r78-metadata.json';assert not meta.exists();meta.write_text(json.dumps(metadata))
 bundle=root/'java-cache-r75-r78-evidence.tar';assert not bundle.exists()
 with tarfile.open(bundle,'w') as t:
  t.add(meta,arcname='metadata.json',recursive=False)
  for entry in metadata:
   t.add(root/'postproc-tests'/('java256-'+entry['revision']+'-menu-evidence.tar.gz'),arcname=entry['revision']+'.tar.gz',recursive=False)
  for path in (root/'postproc-tests/r71-normal-reboot-recovery.json',root/'postproc-tests/cc_fsr_fpga_load-r71-missing-old-failed.json',state_path):
   t.add(path,arcname=path.name,recursive=False)
 data=bundle.read_bytes();assert 0<len(data)<=16*1024*1024
 fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
 try:
  with mmap.mmap(fd,(len(data)+4095)//4096*4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x60800000) as mem:
   mem[:len(data)]=data;assert hashlib.sha256(mem[:len(data)]).hexdigest()==sha(bundle)
 finally:os.close(fd)
 print('JAVA_CACHE_EVIDENCE_READY '+json.dumps(dict(bytes=len(data),sha256=sha(bundle),rounds=metadata)),flush=True)
 deadline=time.monotonic()+600
 while not (root/'java-cache-evidence-ack').exists():
  assert time.monotonic()<deadline;time.sleep(.2)
 assert (root/'java-cache-evidence-ack').read_text().strip()==sha(bundle)
 m.check_idle(m.LinuxAdapter().snapshot());print('JAVA_CACHE_EVIDENCE_RELEASED',flush=True)
