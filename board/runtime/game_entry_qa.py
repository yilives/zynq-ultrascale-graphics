#!/usr/bin/env python3
"""Exercise the installed launcher, persistent profiles and hardware style selection."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--attempt',default='entry01')
a=p.parse_args()
assert a.attempt.isalnum()
base=Path('/opt/rasterix/experimental')
out=Path('/tmp/postproc-tests')
out.mkdir(exist_ok=True)
public=Path('/usr/bin/rix-games')
assert public.is_symlink() and public.resolve()==base/'rix-games'
before=json.loads(subprocess.check_output(['plgpuctl','status']))
runs={}
sentinels={}
for game,filtering,style in [('neverball','nearest','binary'),('neverputt','bilinear','poster'),('quake','bilinear','sepia'),('quake3','nearest','original'),('tuxracer','bilinear','original')]:
    home=base/'profiles'/game
    home.mkdir(parents=True,exist_ok=True)
    sentinel=home/('optimization-qa-'+a.attempt+'.txt')
    sentinel.write_text('Persistent profile QA '+a.attempt+' '+game+'\n')
    digest=hashlib.sha256(sentinel.read_bytes()).hexdigest()
    trial=a.attempt+'_'+game
    command=[str(public),game,'--attempt',trial,'--seconds','15','--filter',filtering,'--style',style,'--capture']
    if game.startswith('never'):command.append('--autoplay')
    with (out/('games-'+trial+'.log')).open('wb') as log:
        code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
    data=json.loads((base/'results-optimization-20261019'/trial/'result.json').read_text())
    status=json.loads(subprocess.check_output([str(base.parent/'postproc-touch/bin/rix-superres'),'--status']))
    word=(1 if filtering=='bilinear' else 0)|({'original':0,'poster':1,'sepia':2,'binary':3}[style]<<4)
    valid=code==0 and data['passed'] and not data['fresh_profile'] and data['profile']==str(home) and status['requested']==word and status['active']==word
    if style=='binary':
        raw=Path(data['captures']['lcd']['path']).read_bytes()
        pixels=struct.unpack('<6000H',raw)
        valid=valid and set(pixels)=={0,65535}
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==digest
    sentinels[str(sentinel)]=digest
    runs[game]={'passed':valid,'result':data,'postprocess_status':status,'expected_mode':word}
    assert valid,game

# Verify the command builder preserves customized controls on repeated setup,
# using an isolated profile so existing player settings are not changed.
spec=importlib.util.spec_from_file_location('qa_games',str(base/'rasterix_games.py'))
sys.path.insert(0,str(base))
games=importlib.util.module_from_spec(spec)
spec.loader.exec_module(games)
testhome=out/('games-'+a.attempt+'-config')
games.command('neverball',testhome)
config=testhome/'.neverball/neverballrc'
config.write_text(config.read_text()+'mouse_sense 337\n')
games.command('neverball',testhome)
values=dict(line.split(None,1) for line in config.read_text().splitlines())
preserved=values['mouse_sense']=='337'
after=json.loads(subprocess.check_output(['plgpuctl','status']))
profile_files={}
for game in runs:
    home=base/'profiles'/game
    config_names={'neverballrc','config.cfg','q3config.cfg','options'}
    found=[path for path in home.rglob('*') if path.is_file() and not path.is_symlink() and path.name in config_names]
    assert found,'No persistent game config: '+game
    profile_files[game]={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in found}
result={'passed':all(r['passed'] for r in runs.values()) and preserved and after['status']==3,
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'public_entry':str(public),'runs':runs,'profile_sentinels':sentinels,
        'custom_control_preserved':preserved,'profile_config_sha256':profile_files,'before':before,'after':after,
        'scope':'Actual installed entry, five persistent profiles and four styles/two filters; binary LCD pixels checked. Full style formula QA is recorded separately for the unchanged FPGA.'}
encoded=json.dumps(result,indent=2)+'\n'
(out/'games-entry-qa.json').write_text(encoded)
(base/'game-entry-qa.json').write_text(encoded)
print('GAME_ENTRY_QA_PASS' if result['passed'] else 'GAME_ENTRY_QA_FAIL',flush=True)
raise SystemExit(0 if result['passed'] else 2)
