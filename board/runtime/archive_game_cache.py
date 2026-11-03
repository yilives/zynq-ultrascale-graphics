#!/usr/bin/env python3
"""Move only superseded game runtime backups to SD's spare FAT space, with readback hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args()
cache=Path('/opt/rasterix/experimental/cache')
boot=Path('/mnt/sd-mmcblk1p1')
target=boot/'rasterix-game-cache-backup-20261019'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def free(path):return shutil.disk_usage(path).free
boot_hashes={name:sha(boot/name) for name in ('BOOT.BIN','system.dtb')}
for name in ('game-runtime',):
    meta=json.loads((cache/(name+'.json')).read_text())
    assert meta['verified'] and sha(cache/(name+'.tar.gz'))==meta['sha256']
records=[]
for archive in sorted(cache.iterdir()):
    match=re.fullmatch(r'(game-runtime-([a-f0-9]{12}))\.tar\.gz',archive.name)
    if not match or match[2] in ("9936c1d0a08d","a28c51bd32bf"):continue
    assert not archive.is_symlink() and archive.is_file()
    metadata=cache/(match[1]+'.json')
    assert metadata.is_file() and not metadata.is_symlink()
    manifest=json.loads(metadata.read_text())
    digest=sha(archive)
    assert manifest['verified'] and digest==manifest['sha256'] and digest.startswith(match[2])
    for source in (archive,metadata):
        records.append({'source':str(source),'destination':str(target/source.name),'bytes':source.stat().st_size,'sha256':sha(source)})
before=free(cache)
assert free(boot)>sum(r['bytes'] for r in records)+8*1024*1024
if a.apply and not records and (target/'archive-manifest.json').exists():
    old=json.loads((target/'archive-manifest.json').read_text())
    assert all(sha(Path(r['destination']))==r['sha256'] for r in old['files'])
    print(json.dumps({'already_archived':True,'bytes_relocated':old['bytes_relocated']}),flush=True)
    raise SystemExit(0)
if a.apply:
    target.mkdir(exist_ok=True)
    # Retain all sources until every destination has passed readback validation.
    for record in records:
        source=Path(record['source']);destination=Path(record['destination'])
        if not destination.exists():
            with source.open('rb') as incoming,destination.open('xb') as outgoing:
                shutil.copyfileobj(incoming,outgoing);outgoing.flush();os.fsync(outgoing.fileno())
        assert destination.is_file() and not destination.is_symlink() and sha(destination)==record['sha256']
    os.sync()
    for record in records:
        source=Path(record['source'])
        assert source.parent==cache and sha(source)==record['sha256']
        source.unlink()
    os.sync()
assert all(sha(boot/name)==digest for name,digest in boot_hashes.items())
result={'applied':a.apply,'files':records,'bytes_relocated':sum(r['bytes'] for r in records),'root_free_before':before,'root_free_after':free(cache),'boot_files_unchanged':True,'backup_directory':str(target),'rollback':'Copy the archived files back into /opt/rasterix/experimental/cache; current packages were not moved.'}
if a.apply:
    (target/'archive-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    Path('/tmp/postproc-tests/games-cache-archive.json').write_text(json.dumps(result,indent=2)+'\n')
    os.sync()
print(json.dumps({k:v for k,v in result.items() if k!='files'}),flush=True)
