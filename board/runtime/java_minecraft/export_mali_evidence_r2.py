"""Archive GLES1 results, diagnostics and final state without modifying records."""
import hashlib,json,os,tarfile
from pathlib import Path
root=Path('/tmp/rix-mali-java-r1');out=Path('/tmp/postproc-tests/mali-r2-evidence.tar.gz');assert not out.exists()
items={}
for name in ('compat-r5','diagnostic-r1','world-r2','world-r3'):
 for f in (root/name).rglob('*'):
  if f.is_file() and f.suffix!='.so':items[f.relative_to(root).as_posix()]=f
for name in ('world-manifest-r2.json','world-manifest-r3.json','final-state-r1.json'):
 p=root/name
 if p.is_file():items[name]=p
for number in (2,3):
 for name in ('level.dat','level.dat_old'):
  p=root/('home-world-r%d/.minecraft/saves/rixmali-r%d/'%(number,number))/name
  if p.is_file():items[p.relative_to(root).as_posix()]=p
 p=root/('home-world-r%d/.minecraft/options.txt'%number)
 if p.is_file():items[p.relative_to(root).as_posix()]=p
meta=root/'export-platform-r2.json';assert not meta.exists()
meta.write_text(json.dumps(dict(clock_ticks=os.sysconf('SC_CLK_TCK'),files={n:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in items.items()}),indent=2)+'\n')
items[meta.name]=meta
with tarfile.open(out,'x:gz') as tar:
 for name,p in items.items():tar.add(p,arcname=name,recursive=False)
print('MALI_EVIDENCE '+json.dumps(dict(path=str(out),bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest())),flush=True)
