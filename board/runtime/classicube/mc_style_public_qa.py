#!/usr/bin/env python3
"""Verify installed entry restores its RAM cache from the SD package."""
import argparse,fcntl,hashlib,json,subprocess
from pathlib import Path
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--revision',choices=('v1','v2','v3'),default='v1')
p.add_argument('--sha256',default='89c1478f4406a0f98d9862392caea619cde27dc1bc948b4dc1171b763917522b')
p.add_argument('--command-sha256',default='f726754576b35dfe89d93dd77bd386b21ff38f4e8cb72ac05efc76726e0e9f1c')
a=p.parse_args();assert len(a.sha256)==64 and len(a.command_sha256)==64
out=Path('/tmp/postproc-tests');expected=a.sha256;attempt='cc_style_public_'+a.revision
archive=Path('/media/sd-mmcblk1p1/rasterix-mc-style-'+a.revision+'.tar.gz');command=Path('/usr/bin/rix-classicube-style')
assert sha(archive)==expected
assert sha(command)==a.command_sha256
assert not subprocess.run(['pidof','ClassiCube','rix-neural-style'],stdout=subprocess.PIPE).stdout
lock=open('/tmp/rix-mc-style-extract.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
work=Path('/tmp/rix-mc-style-packages')/expected[:16]
assert not work.is_symlink() and work.resolve()==Path('/tmp').resolve()/'rix-mc-style-packages'/expected[:16]
manifest=json.loads((work/'manifest.json').read_text())
assert all(sha(work/n)==v['sha256'] for n,v in manifest.items())
backup=work.with_name(work.name+'.verified-before-restore');assert not backup.exists()
work.rename(backup);assert not work.exists();lock.close()
args=[str(command),'--style','anime','--seconds','15','--autoplay','--attempt',attempt]
with (out/(attempt+'.log')).open('w') as log:r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=50)
assert work.is_dir() and all(sha(work/n)==v['sha256'] for n,v in manifest.items())
record={'command':args,'command_exit':r.returncode,'session':json.loads((out/attempt/'session.json').read_text()),
        'post_after':json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],text=True)),
        'package_sha256':sha(archive),'command_sha256':sha(command),'empty_ram_cache_restored':True,'manifest_verified_files':len(manifest)}
record['game_result']=json.loads((out/(attempt+'_game')/'result.json').read_text())
(out/(attempt+'.json')).write_text(json.dumps(record,indent=2)+'\n')
assert r.returncode==0 and record['session']['passed'] and record['session']['post_restored_after_both_exited']
print('MC_STYLE_INSTALLED_PUBLIC_PASS',flush=True)
