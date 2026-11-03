#!/usr/bin/env python3
"""Verify the public command actually rebuilds both RAM caches after reboot."""
import json, subprocess
from pathlib import Path

assert not Path('/tmp/rasterix-classicube').exists()
assert not Path('/tmp/rasterix-games').exists()
before = {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'classicube_tmp_present':False,'shared_runtime_tmp_present':False,
          'saved_map_present':Path('/opt/rasterix/classicube/profile/maps/cc_gameplay_v4.cw').is_file(),
          'postproc':json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'],universal_newlines=True))}
out = Path('/tmp/postproc-tests');out.mkdir(exist_ok=True)
(out/'cc_coldboot_pre.json').write_text(json.dumps(before,indent=2)+'\n')
result = subprocess.run(['rix-classicube','--seconds','12','--world-size','64','--view-distance','32','--capture','--attempt','cc_coldboot_v4'])
assert result.returncode == 0
assert Path('/tmp/rasterix-classicube').is_dir() and Path('/tmp/rasterix-games/runtime').is_dir()
subprocess.run(['python3','/tmp/cc_collect_state.py'],check=True)
after=json.loads((out/'cc_board_state.json').read_text())
assert after['postproc']['requested'] == before['postproc']['requested']
print('CLASSICUBE_COLD_BOOT_PASS',before['boot_id'],flush=True)
