#!/usr/bin/env python3
"""Preserve the completed v7 RAM transaction after its verified rollback."""
import fcntl
import json
import os
from pathlib import Path
import subprocess

def main():
    locks=[]
    for name in ('rasterix-game-launch.lock','rix-superres.lock','rix-mc-style-extract.lock'):
        fd=os.open('/tmp/'+name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        stream=os.fdopen(fd,'a+');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(stream)
    current=json.loads(subprocess.check_output(['plgpuctl','status'],universal_newlines=True))
    assert current['status']==3 and all(current[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    assert len({current[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
    assert not subprocess.run(['pidof','ClassiCube','rix-neural-style','rix-superres','rix-fsr-pl'],stdout=subprocess.PIPE).stdout
    report=Path('/tmp/postproc-tests/cc_fsr_fpga_recover_v7.json')
    recovery=json.loads(report.read_text())
    assert recovery['rollback']['passed'] and recovery['outcome']=='rolled-back'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==recovery['before']['boot_id']
    base=Path('/tmp/rix-fpga-fsr');target=Path('/tmp/rix-fpga-fsr-v7')
    assert base.is_dir() and not base.is_symlink() and base.resolve()==Path('/tmp').resolve()/'rix-fpga-fsr'
    assert not target.exists() and not target.is_symlink()
    assert not (base/'active-receipt.txt').exists() and not Path('/tmp/rix-fsr-pl.quarantine').exists()
    load=Path('/tmp/postproc-tests/cc_fsr_fpga_load.json')
    old_load=Path('/tmp/postproc-tests/cc_fsr_fpga_load_v7.json')
    assert load.is_file() and not load.is_symlink() and not old_load.exists()
    # Literal sibling renames only; all bytes and previous evidence survive.
    base.rename(target);load.rename(old_load)
    print('FSR_V7_RAM_ARCHIVED',str(target),str(old_load),flush=True)
    for stream in reversed(locks):stream.close()

if __name__=='__main__':main()
