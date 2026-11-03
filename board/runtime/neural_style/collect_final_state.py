#!/usr/bin/env python3
"""Collect installed hashes plus postprocessing ownership after all QA clients exit."""
import json
import hashlib
from pathlib import Path
import subprocess

record = json.loads(subprocess.check_output(['python3', '/opt/rasterix/neural-style/bin/neural-board-state.py'], text=True))
record['postproc'] = json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres', '--status'], text=True))
clients = subprocess.run(['pidof', 'tuxracer', 'neverball', 'neverputt', 'quakespasm', 'quake3e',
                          'rix-glx-probe', 'rix-smoke', 'th06-rix', 'rix-superres', 'rix-neural-style'],
                         stdout=subprocess.PIPE, text=True)
record['active_gpu_clients'] = clients.stdout.strip()
record['experimental_frame_mapping_loaded'] = any(line.startswith('rix_frame_memory ') for line in Path('/proc/modules').read_text().splitlines())
path = Path('/tmp/postproc-tests/neural-final.json')
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(record, indent=2) + '\n')
print('NEURAL_FINAL_STATE', json.dumps({k: record[k] for k in ('boot_id', 'all_installed_files_match', 'active_gpu_clients', 'experimental_frame_mapping_loaded')}), flush=True)
