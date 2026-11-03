#!/usr/bin/env python3
"""Archive only three identified obsolete candidates, verifying before removal."""
import hashlib
import json
import os
from pathlib import Path
import shutil

cache=Path('/opt/rasterix/experimental/cache')
card=Path('/mnt/sd-mmcblk1p1').resolve()
assert cache.resolve()==cache
assert os.path.ismount(str(card))
target=card/'rasterix-runtime-cache-backup-20261019-round2'
target.mkdir(exist_ok=True)
assert target.resolve().parent==card
hashes=('cad9db2ed081f5b0017af5c6c6a2bef10aa3f690c78453280f36f03ec3e46951',
        '6bc8fc418f8e4f78d1123e052868dc73dd643ada08b7980ea5fa0a4f90d6ec64',
        'e70b9e27f1bd9e24de0ab291871b7fc81a164321d9cf68af7020ae68270cb7b0')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
receipt=json.loads(Path('/opt/rasterix/experimental/optimization-install.json').read_text())
assert receipt['package_sha256'] not in hashes
boot={name:sha(card/name) for name in ('BOOT.BIN','system.dtb','Image')}
manifest=target/'manifest.json'
if manifest.exists():
    previous=json.loads(manifest.read_text())
    assert all(sha(Path(r['destination']))==r['sha256'] for r in previous['files'])
    print('RUNTIME_CANDIDATES_ALREADY_ARCHIVED',flush=True)
    raise SystemExit(0)
records=[]
for digest in hashes:
    prefix='game-runtime-'+digest[:12]
    archive=cache/(prefix+'.tar.gz')
    metadata=cache/(prefix+'.json')
    assert not archive.is_symlink() and sha(archive)==digest
    assert json.loads(metadata.read_text())['sha256']==digest
    for path in (archive,metadata):
        records.append({'source':str(path),'destination':str(target/path.name),
                        'sha256':sha(path),'bytes':path.stat().st_size})
assert shutil.disk_usage(card).free>sum(r['bytes'] for r in records)+8*1024*1024
before=shutil.disk_usage(cache).free
for record in records:
    source=Path(record['source']);destination=Path(record['destination'])
    assert source.parent==cache and destination.parent==target and not destination.is_symlink()
    if destination.exists():assert sha(destination)==record['sha256']
    else:
        temporary=destination.with_name(destination.name+'.copying')
        with source.open('rb') as incoming,temporary.open('wb') as outgoing:
            shutil.copyfileobj(incoming,outgoing);outgoing.flush();os.fsync(outgoing.fileno())
        assert sha(temporary)==record['sha256']
        os.replace(temporary,destination)
    assert sha(destination)==record['sha256']
os.sync()
for record in records:
    source=Path(record['source'])
    assert source.parent==cache and sha(source)==record['sha256']
    source.unlink()
os.sync()
assert all(sha(card/name)==value for name,value in boot.items())
result={'files':records,'bytes_relocated':sum(r['bytes'] for r in records),
        'root_free_before':before,'root_free_after':shutil.disk_usage(cache).free,
        'boot_files_unchanged':True,'retained_package':receipt['package_sha256'],
        'backup_directory':str(target)}
manifest.write_text(json.dumps(result,indent=2)+'\n')
Path('/tmp/postproc-tests/games-opt2-cache-archive.json').write_text(json.dumps(result,indent=2)+'\n')
os.sync()
print('RUNTIME_CANDIDATES_ARCHIVED '+str(result['bytes_relocated']),flush=True)
