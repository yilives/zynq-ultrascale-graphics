#!/usr/bin/env python3
"""Install an opt-in RAM-expanded MC style add-on with strict storage guards."""
import argparse,hashlib,json,os,tarfile
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--sha256',required=True)
a=p.parse_args();assert os.geteuid()==0 and len(a.sha256)==64 and set(a.sha256)<=set('0123456789abcdef')
sha=lambda d:hashlib.sha256(d).hexdigest()
data=a.archive.read_bytes();assert sha(data)==a.sha256
with tarfile.open(a.archive) as tf:
    members=tf.getmembers();assert len(members)==len({m.name for m in members})
    assert all(m.isfile() and m.name.startswith('mc-style/') and '..' not in Path(m.name).parts and len(Path(m.name).parts)<=3 for m in members)
    manifest=json.load(tf.extractfile('mc-style/manifest.json'))
    assert {m.name for m in members}=={'mc-style/'+n for n in manifest}|{'mc-style/manifest.json'}
    assert all(len(tf.extractfile('mc-style/'+n).read())==v['bytes'] and sha(tf.extractfile('mc-style/'+n).read())==v['sha256'] for n,v in manifest.items())
sd=Path('/media/sd-mmcblk1p1');assert sd.is_mount() and not sd.is_symlink()
target=sd/'rasterix-mc-style-v1.tar.gz';command=Path('/usr/bin/rix-classicube-style')
assert not command.exists() and not command.is_symlink(),'Preserve existing command before replacing an add-on'
assert not target.exists() and not target.is_symlink(),'Preserve existing add-on archive'
bootstrap='''#!/usr/bin/env python3
# RasterIX isolated MC neural add-on v1; original game/runtime remain separate.
import fcntl,hashlib,json,os,sys,tarfile
from pathlib import Path
archive=Path(ARCHIVE)
expected=EXPECTED
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(archive.read_bytes())==expected,'MC add-on package SHA mismatch'
base=Path('/tmp/rix-mc-style-packages');work=base/expected[:16]
lock=open('/tmp/rix-mc-style-extract.lock','a');fcntl.flock(lock,fcntl.LOCK_EX)
assert not base.is_symlink() and not work.is_symlink(),'Add-on must expand into owned RAM paths'
work.mkdir(parents=True,exist_ok=True)
assert work.resolve()==Path('/tmp').resolve()/'rix-mc-style-packages'/expected[:16]
with tarfile.open(archive) as tf:
    ms=tf.getmembers();assert len(ms)==len({m.name for m in ms})
    manifest=json.load(tf.extractfile('mc-style/manifest.json'))
    assert {m.name for m in ms}=={'mc-style/'+n for n in manifest}|{'mc-style/manifest.json'}
    for m in ms:
        name=Path(m.name);assert m.isfile() and name.parts[0]=='mc-style' and '..' not in name.parts and len(name.parts)<=3
        dst=work.joinpath(*name.parts[1:]);assert not dst.is_symlink()
        dst.parent.mkdir(parents=True,exist_ok=True);assert os.path.commonpath([str(work.resolve()),str(dst.parent.resolve())])==str(work.resolve())
        blob=tf.extractfile(m).read()
        if m.name!='mc-style/manifest.json':assert len(blob)==manifest[str(Path(*name.parts[1:]))]['bytes'] and sha(blob)==manifest[str(Path(*name.parts[1:]))]['sha256']
        if not dst.exists() or sha(dst.read_bytes())!=sha(blob):
            temp=dst.with_name(dst.name+'.incoming');assert not temp.is_symlink();temp.write_bytes(blob);temp.chmod(0o755 if name.parts[1]=='bin' else 0o644);temp.replace(dst)
fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
os.execv(sys.executable,[sys.executable,str(work/'bin/rix-classicube-style')]+sys.argv[1:])
'''.replace('ARCHIVE',repr(str(target))).replace('EXPECTED',repr(a.sha256)).encode()
free=lambda p:os.statvfs(str(p)).f_bavail*os.statvfs(str(p)).f_frsize
assert free(Path('/'))>=32*1024*1024+len(bootstrap)+8192,'Keep 32 MiB root guard'
assert free(sd)>=16*1024*1024+len(data)*2+8192,'Keep 16 MiB SD guard including temporary archive'
temp=target.with_name(target.name+'.incoming');assert not temp.exists() and not temp.is_symlink()
temp.write_bytes(data)
with temp.open('rb') as f:os.fsync(f.fileno())
assert sha(temp.read_bytes())==a.sha256;temp.replace(target)
temp=command.with_name(command.name+'.incoming');assert not temp.exists() and not temp.is_symlink()
temp.write_bytes(bootstrap);temp.chmod(0o755);temp.replace(command);os.sync()
assert sha(target.read_bytes())==a.sha256 and command.read_bytes()==bootstrap
record={'package_sha256':a.sha256,'archive':str(target),'command':str(command),'command_sha256':sha(bootstrap),'bytes':len(data),'root_free':free(Path('/')),'sd_free':free(sd),'guard_root':32*1024*1024,'guard_sd':16*1024*1024,'verified':True}
assert record['root_free']>=record['guard_root'] and record['sd_free']>=record['guard_sd']
Path('/tmp/postproc-tests/cc_style_install.json').write_text(json.dumps(record,indent=2)+'\n')
print('MC_STYLE_ADDON_INSTALLED',json.dumps(record),flush=True)
