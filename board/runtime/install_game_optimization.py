#!/usr/bin/env python3
"""Install the validated game launcher and optionally promote the tested Tux Racer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--expected-package',required=True)
p.add_argument('--promote-tux',action='store_true')
p.add_argument('--acceptance',type=Path)
a=p.parse_args()
assert re.fullmatch('[a-f0-9]{64}',a.expected_package)
assert os.geteuid()==0
active=subprocess.run(['pidof','tuxracer','neverball','neverputt','quakespasm','quake3e','rix-glx-probe','cache-qa','th06-rix','rix-danmaku','rix-superres'],stdout=subprocess.PIPE)
assert active.returncode==1 and not active.stdout,'Stop GPU clients before installing'
base=Path('/opt/rasterix/experimental')
cache=base/'cache'
work=Path('/tmp/rasterix-games/runtime')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
archive=cache/'game-runtime.tar.gz'
meta=json.loads((cache/'game-runtime.json').read_text())
assert meta['verified'] and meta['sha256']==a.expected_package and sha(archive)==a.expected_package
names=('rasterix_games.py','game_optimization_trial.py','game_x11_control.py','game_runtime_support.py','rix-games')
with tarfile.open(archive) as source:
    for name in (*names,'tuxracer'):
        data=source.extractfile('runtime/bin/'+name).read()
        assert hashlib.sha256(data).hexdigest()==sha(work/'bin'/name),name
    data=source.extractfile('runtime/lib/libGL.so.1.0').read()
    assert hashlib.sha256(data).hexdigest()==sha(work/'lib/libGL.so.1.0')
backup=base/'backups-optimization-20261019'
backup.mkdir(exist_ok=True)
def install(source,target):
    expected=sha(source)
    if target.exists() and sha(target)==expected:return expected
    if target.exists():
        saved=backup/(target.name+'-'+sha(target)[:12])
        if not saved.exists():shutil.copyfile(target,saved)
        assert sha(saved)==sha(target)
    temporary=target.with_name(target.name+'.optimization-new')
    with source.open('rb') as src,temporary.open('wb') as dst:
        shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
    temporary.chmod(0o755)
    assert sha(temporary)==expected
    os.replace(temporary,target)
    assert sha(target)==expected
    return expected
installed={name:install(work/'bin'/name,base/name) for name in names}
link=Path('/usr/bin/rix-games')
if link.is_symlink():assert link.resolve()==(base/'rix-games').resolve()
elif link.exists():raise RuntimeError('Unrelated /usr/bin/rix-games exists')
else:link.symlink_to(base/'rix-games')
if a.promote_tux:
    assert a.acceptance and a.acceptance.is_file(),'Pass the completed acceptance report'
    validated=json.loads(a.acceptance.read_text())
    assert validated['all_checks_passed'] and validated['package_sha256']==a.expected_package
    installed['/usr/bin/tuxracer']=install(work/'bin/tuxracer',Path('/usr/bin/tuxracer'))
os.sync()
tux_matches=Path('/usr/bin/tuxracer').exists() and sha(Path('/usr/bin/tuxracer'))==sha(work/'bin/tuxracer')
if tux_matches:installed['/usr/bin/tuxracer']=sha(work/'bin/tuxracer')
result={'package_sha256':a.expected_package,'installed_sha256':installed,'tux_promoted':tux_matches,'promote_tux_requested':a.promote_tux,
        'backup_directory':str(backup),'root_free_bytes':shutil.disk_usage('/').free,
        'public_command':'rix-games <tuxracer|neverball|neverputt|quake|quake3> --seconds 1800',
        'profiles':'/opt/rasterix/experimental/profiles/<game>','boot_files_modified':False}
(base/'optimization-install.json').write_text(json.dumps(result,indent=2)+'\n')
Path('/tmp/postproc-tests').mkdir(exist_ok=True)
Path('/tmp/postproc-tests/games-install.json').write_text(json.dumps(result,indent=2)+'\n')
os.sync()
print(json.dumps(result),flush=True)
