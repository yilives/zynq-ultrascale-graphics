#!/usr/bin/env python3
"""Exercise real SNP1 ownership while Neverball continues rendering."""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import signal
import struct
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('--output',default='/tmp/postproc-tests/snapshot-check.json')
a=p.parse_args()
assert Path('/proc/device-tree/rasterix-frame-snapshot/rasterix,snapshot-version').exists(),'SNP1 device tree required'
tool='/opt/rasterix/postproc-touch/bin/rix-superres'
folder=Path('/tmp/postproc-tests');folder.mkdir(exist_ok=True)
checks={};records={};child=None;paused=False
game=int(subprocess.check_output(['pidof','neverball']).split()[0])
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
regs=mmap.mmap(fd,65536,offset=0xa0010000)

def reg(offset):return struct.unpack_from('<I',regs,offset)[0]
def state():return reg(0x7c)&3
def status():return json.loads(subprocess.check_output(['plgpuctl','status']))
def wait(predicate,seconds=4):
    until=time.monotonic()+seconds
    while not predicate():
        if time.monotonic()>until:raise RuntimeError('snapshot state wait timeout')
        time.sleep(.005)
def start(name,hold):
    return subprocess.Popen([tool,'--snapshot',str(folder/(name+'.rgb565')),'--snapshot-hold-ms',str(hold)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
def finish(proc):
    out=proc.communicate(timeout=5)[0]
    return {'returncode':proc.returncode,'output':out}

try:
    assert reg(0x74)==0x534e5031
    before=status();records['before']=before
    child=start('immutable',700);wait(lambda:state()==3)
    token=reg(0x80);frame=reg(0x84);first=status()
    time.sleep(.25);second=status()
    checks['game_advances_while_cpu_owns_snapshot']=second['presented']>first['presented']
    checks['same_token_held_while_game_advances']=state()==3 and reg(0x80)==token and reg(0x84)==frame
    result=finish(child);child=None;records['immutable']=result
    checks['two_actual_copies_match_under_lease']=result['returncode']==0 and '"released":true' in result['output']
    records['immutable_source_sha256']=hashlib.sha256((folder/'immutable.rgb565').read_bytes()).hexdigest()
    checks['normal_release_idle']=state()==0

    child=start('terminated',1500);wait(lambda:state()==3);child.terminate()
    records['sigterm']=finish(child);child=None;wait(lambda:state()==0)
    checks['sigterm_releases_lease']=state()==0

    expired=reg(0x8c);child=start('killed',1500);wait(lambda:state()==3)
    first=status();child.kill();records['sigkill']=finish(child);child=None
    time.sleep(.15);checks['sigkill_does_not_prematurely_release']=state()==3
    wait(lambda:state()==0,3);second=status()
    checks['sigkill_watchdog_reclaims']=reg(0x8c)==expired+1
    checks['game_advances_during_abandoned_lease']=second['presented']>first['presented']

    # With the producer stopped, a request must expire instead of publishing
    # previous data as a new frame. Resume even if any assertion fails.
    os.kill(game,signal.SIGSTOP);paused=True;time.sleep(.4)
    first=status();time.sleep(.2);second=status()
    assert first['presented']==second['presented'],'queued GPU frames have not drained'
    expired=reg(0x8c);child=start('no-producer',0);wait(lambda:state()==1)
    result=finish(child);child=None;records['no_producer']=result
    checks['pending_watchdog_rejects_stale_frame']=result['returncode']!=0 and state()==0 and reg(0x8c)==expired+1
    os.kill(game,signal.SIGCONT);paused=False
    child=start('recovered',0);result=finish(child);child=None;records['recovered']=result
    checks['reacquires_after_kill_and_producer_pause']=result['returncode']==0 and state()==0
    after=status();records['after']=after
    checks['gpu_and_display_errors_zero']=after['status']==3 and all(after[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    checks['gpu_frames_continued']=after['presented']>before['presented']
finally:
    if child is not None and child.poll() is None:child.kill();child.communicate()
    if paused:os.kill(game,signal.SIGCONT)
    regs.close();os.close(fd)

result={'passed':all(checks.values()),'checks':checks,'records':records,'physical_touch_tested':False}
Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
print('SNP1_BOARD_CHECKS',sum(checks.values()),'/',len(checks),flush=True)
if not result['passed']:raise SystemExit('Failed: '+str([k for k,v in checks.items()if not v]))
