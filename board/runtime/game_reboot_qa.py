#!/usr/bin/env python3
"""Verify the installed package and profiles after an ordinary Linux reboot."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess

base=Path('/opt/rasterix/experimental')
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--attempt',default='glx_reboot01')
a=p.parse_args()
out=Path('/tmp/postproc-tests')
out.mkdir(exist_ok=True)
entry=json.loads((base/'game-entry-qa.json').read_text())
installed=json.loads((base/'optimization-install.json').read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
checks={'new_boot':boot_id!=entry['boot_id'],'entry_qa_passed':entry['passed'],
        'public_entry':Path('/usr/bin/rix-games').resolve()==base/'rix-games',
        'tux_promoted':installed['tux_promoted'],
        'package_verified':sha(base/'cache/game-runtime.tar.gz')==installed['package_sha256']}
for name,digest in installed['installed_sha256'].items():
    target=Path(name) if name.startswith('/') else base/name
    checks['installed_'+name]=sha(target)==digest
for name,digest in entry['profile_sentinels'].items():
    checks['persistent_'+name]=sha(Path(name))==digest
for game,files in entry['profile_config_sha256'].items():
    checks['config_'+game]=bool(files) and all(sha(Path(name))==digest for name,digest in files.items())
code=subprocess.call(['/usr/bin/rix-games','glx-probe','--attempt',a.attempt,'--seconds','8','--fresh-profile','--filter','bilinear'])
probe=json.loads((base/'results-optimization-20261019'/a.attempt/'result.json').read_text())
checks['glx_after_reboot']=code==0 and probe['passed']
result={'passed':all(checks.values()),'checks':checks,'package_sha256':installed['package_sha256'],
        'tux_sha256':sha(Path('/usr/bin/tuxracer')),'boot_id_before':entry['boot_id'],'boot_id_after':boot_id,
        'glx_probe':probe}
encoded=json.dumps(result,indent=2)+'\n'
(out/'games-reboot-qa.json').write_text(encoded)
(base/'game-reboot-qa.json').write_text(encoded)
print('GAME_REBOOT_QA_PASS' if result['passed'] else 'GAME_REBOOT_QA_FAIL',flush=True)
raise SystemExit(0 if result['passed'] else 2)
