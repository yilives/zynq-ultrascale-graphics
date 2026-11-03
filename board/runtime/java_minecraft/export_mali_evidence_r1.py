"""Archive original Mali records including failures; never edit their verdicts."""
import hashlib,json,os,tarfile
from pathlib import Path
root=Path('/tmp/rix-mali-java-r1');out=Path('/tmp/postproc-tests/mali-r1-evidence.tar.gz')
assert not out.exists()
items={}
for name in ('driver-result','gles-headless-r1','compat-r1','compat-r2','compat-r3','compat-r4','world-r1'):
 p=root/name
 if p.exists():
  for f in p.rglob('*'):
   if f.is_file():items[f.relative_to(root).as_posix()]=f
for name in ('driver-manifest.json','world-manifest-r1.json','gles-acceptance-r1.json','compat-manifest.json'):
 p=root/name
 if p.is_file():items[name]=p
for name in ('home/.minecraft/saves/rixmali-r1/level.dat','home/.minecraft/options.txt'):
 p=root/name
 if p.is_file():items[name]=p
meta=root/'export-platform-r1.json';assert not meta.exists()
meta.write_text(json.dumps(dict(clock_ticks=os.sysconf('SC_CLK_TCK'),uname=list(os.uname()),files={n:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in items.items()}),indent=2)+'\n')
items[meta.name]=meta
with tarfile.open(out,'x:gz') as tar:
 for name,p in items.items():tar.add(p,arcname=name,recursive=False)
print('MALI_EVIDENCE '+json.dumps(dict(path=str(out),bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest())),flush=True)
