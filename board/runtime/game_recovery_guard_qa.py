#!/usr/bin/env python3
"""Verify the public command rejects a same-boot fault before touching the GPU."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import DisplayStatus,GpuRecoveryGuard

base=Path('/opt/rasterix/experimental')
out=Path('/tmp/postproc-tests')
out.mkdir(exist_ok=True)
active=subprocess.run(['pidof','tuxracer','neverball','neverputt','quakespasm','quake3e','rix-glx-probe','th06-rix'],stdout=subprocess.PIPE)
assert active.returncode==1 and not active.stdout
guard=GpuRecoveryGuard()
guard.check()  # Never replace a real fault from the current boot.
saved=guard.path.read_bytes() if guard.path.exists() else None
device=DisplayStatus()
before=device.read()
attempt='guardqa-'+uuid.uuid4().hex
record=guard.mark(attempt,{'reason':'Synthetic launcher guard test; no DMA fault injected',
                          'exit_code':-6,'transport_errors':1,'after':before})
try:
    child=subprocess.run(['rix-games','glx-probe','--attempt',attempt,'--seconds','5','--fresh-profile'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    after=device.read()
    blocked=child.returncode!=0 and b'reboot the board' in child.stdout
    unchanged=before==after
    no_run_directory=not (Path('/tmp/rasterix-games/results')/attempt).exists()
    assert blocked and unchanged and no_run_directory
finally:
    current=json.loads(guard.path.read_text())
    # Preserve any unrelated real failure instead of clearing it accidentally.
    assert current['attempt']==attempt and current['boot_id']==guard.boot_id
    if saved is None:guard.path.unlink()
    else:
        temporary=guard.path.with_name(guard.path.name+'.restore')
        temporary.write_bytes(saved)
        os.replace(temporary,guard.path)
    os.sync()
restored=(not guard.path.exists()) if saved is None else guard.path.read_bytes()==saved
result={'passed':blocked and unchanged and no_run_directory and restored,
        'synthetic':True,'no_hardware_fault_injected':True,'blocked_before_gpu_changes':unchanged,
        'no_game_directory_created':no_run_directory,'previous_marker_restored':restored,
        'command_returncode':child.returncode,'output':child.stdout.decode(errors='replace'),
        'before':before,'after':after,'synthetic_record':record,
        'support_sha256':hashlib.sha256((base/'game_runtime_support.py').read_bytes()).hexdigest(),
        'package':json.loads((base/'cache/game-runtime.json').read_text())}
encoded=json.dumps(result,indent=2)+'\n'
(out/'games-opt2-guard.json').write_text(encoded)
(base/'delivery-runtime2-20261019/guard-qa.json').write_text(encoded)
print('GPU_RECOVERY_GUARD_QA_PASS',flush=True)
