"""Archive the frozen starting world and raw NBT pose/repair evidence, without devices."""
import hashlib,os,tarfile
from pathlib import Path
base=Path('/tmp/rix-java125');results=Path('/tmp/postproc-tests')
files={'world-poses.json':results/'java256-world-poses-r28.json','save-repair.json':results/'java256-world-r24/save-repair.json'}
for path in (base/'profile-baseline-r24').rglob('*'):
    if path.is_file():files['frozen-world/'+path.relative_to(base/'profile-baseline-r24').as_posix()]=path
for revision in ('r25','r26','r27','r28'):
    folder=results/('java256-world-'+revision)/'finished-world-save'
    if not folder.exists():folder=base/'home/.minecraft/saves'/('rixjava-'+revision)
    files[revision+'-level.dat']=folder/'level.dat'
for path in files.values():assert path.is_file() and not path.is_symlink()
target=results/'java256-texture-batch-supplement-r28.tar.gz'
with os.fdopen(os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for name,path in files.items():archive.add(str(path),arcname=name,recursive=False)
print('JAVA_TEXTURE_BATCH_SUPPLEMENT',target.stat().st_size,hashlib.sha256(target.read_bytes()).hexdigest())
