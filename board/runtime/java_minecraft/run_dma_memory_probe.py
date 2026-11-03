"""Guarded idle-only CPU bandwidth measurement; never sends a GPU packet."""
import fcntl,hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
root=Path(__file__).resolve().parent;manifest=json.loads((root/'manifest.json').read_text())
for name,h in manifest['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
locks=[]
try:
 for name in m.LOCKS:
  fd=os.open('/tmp/'+name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);locks.append(fd);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 GpuRecoveryGuard().check();a=m.LinuxAdapter();before=a.snapshot();m.check_idle(before)
 receipt=Path('/tmp/rix-fpga-fsr/active-receipt.txt').read_text().splitlines();assert receipt[1]==before['boot_id'] and receipt[2]=='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
 p=root/'result.json';assert not p.exists()
 run=subprocess.run([str(root/'dma-memory-probe'),*map(str,locks)],pass_fds=locks,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
 after=a.snapshot();m.check_idle(after)
 assert before['gpu']==after['gpu'] and before['post']==after['post'] and before['boot_id']==after['boot_id']
 assert run.returncode==0 and 'DMA_MEMORY_PROBE_PASS no_dma_started=1 slot=6 original_bytes_restored=1' in run.stdout
 rows=[json.loads(x) for x in run.stdout.splitlines() if x.startswith('{')];assert len(rows)==8 and all(r['seconds']>0 for r in rows)
 report=dict(passed=True,no_dma_started=True,slot=6,original_slot_restored=True,cached_heap_excludes_dma_cache_maintenance=True,rows=rows,output=run.stdout,before=before,after=after)
 p.write_text(json.dumps(report,indent=2)+'\n');print('DMA_MEMORY_PROBE_RESULT '+json.dumps(rows));print('DMA_MEMORY_PROBE_GUARDED_PASS')
finally:
 for fd in reversed(locks):os.close(fd)
