#!/usr/bin/env python3
"""Record actual engine configuration files after the installed-entry trials."""
import hashlib
import json
from pathlib import Path
base=Path('/opt/rasterix/experimental')
record=base/'game-entry-qa.json'
data=json.loads(record.read_text())
assert data['passed'] and len(data['runs'])==5
files={}
for game in data['runs']:
    home=base/'profiles'/game
    paths=[p for p in home.rglob('*') if p.is_file() and not p.is_symlink() and p.name in {'neverballrc','config.cfg','q3config.cfg','options'}]
    assert paths,'No saved game configuration: '+game
    files[game]={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
data['profile_config_sha256']=files
data['profile_audit_source']='game_profile_audit.py: after normal game exit, before reboot'
encoded=json.dumps(data,indent=2)+'\n'
record.write_text(encoded)
Path('/tmp/postproc-tests/games-entry-qa.json').write_text(encoded)
print('GAME_PROFILE_CONFIG_AUDIT_PASS games='+str(len(files)),flush=True)
