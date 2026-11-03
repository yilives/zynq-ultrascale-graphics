#!/usr/bin/env python3
"""Preserve evidence and accepted RAM runtime before a normal Linux reboot.

Only writes the known no-map DDR staging area; never programs PL or resets CPUs.
The launch locks remain held until the host acknowledges its readback.
"""
import fcntl,hashlib,importlib.util,json,mmap,os,subprocess,sys,tarfile,time
from pathlib import Path
sys.path.insert(0,'/tmp')
from receive_java125_ram import idle
BASE=Path('/tmp/rix-java125');TMP=Path('/tmp');LOCKS=('rasterix-game-launch.lock','rix-superres.lock','rix-mc-style-extract.lock')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
locks=[]
try:
    for name in LOCKS:
        f=open(str(TMP/name),'a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
    idle()
    # Do not remove the recovery guard. A real reboot will change the boot UUID.
    guard=Path('/opt/rasterix/experimental/gpu-quarantine.json')
    assert guard.exists() and json.loads(guard.read_text())['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    evidence=Path('/tmp/postproc-tests/java125-evidence.tar.gz');assert not evidence.exists()
    with tarfile.open(evidence,'w:gz') as t:
        for mode in ('sys','display','client'):t.add(BASE/('result-'+mode),arcname='result-'+mode)
        t.add(guard,arcname='gpu-quarantine-before-reboot.json')
        t.add('/tmp/rix-fpga-fsr/active-receipt.txt',arcname='v23-receipt-before-reboot.txt')
    names=['fpga_ram_control.py','fpga_fsr_control.py','rix-classicube-fsr-v23',
        'rix-fpga-v4/manifest.json','rix-fpga-v4/old.bin','rix-fpga-v4/new.bin',
        'rix-fpga-fsr/manifest.json','rix-fpga-fsr/new.bin','rix-fpga-fsr/ahead/rix-fsr-pl',
        'rasterix-classicube/ffa912210b7c']
    payload=TMP/'java125-restore-runtime.tar.gz';assert not payload.exists()
    with tarfile.open(payload,'w:gz') as t:
        for name in names:
            p=TMP/name;assert p.exists() and not p.is_symlink() and p.stat().st_uid==0
            t.add(p,arcname=name)
    data=payload.read_bytes();assert 0<len(data)<=16*1024*1024
    before=json.loads(subprocess.check_output(['plgpuctl','status']))
    record=dict(payload_bytes=len(data),payload_sha256=sha(payload),evidence_bytes=evidence.stat().st_size,
        evidence_sha256=sha(evidence),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),gpu=before,
        accepted_gl_sha256=sha(TMP/'rasterix-classicube/ffa912210b7c/lib/libGL.so.1'),
        accepted_launcher_sha256=sha(TMP/'rix-classicube-fsr-v23'),native_sha256=sha(BASE/'native/liblwjgl.so'),
        files={n:sha(TMP/n) for n in names if (TMP/n).is_file()})
    (TMP/'java125-recovery-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    padded=data+b'\0'*((-len(data))%64)
    fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
    try:
        with mmap.mmap(fd,(len(padded)+4095)//4096*4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x60800000) as mem:
            mem[:len(padded)]=padded
            assert hashlib.sha256(mem[:len(padded)][:len(data)]).hexdigest()==record['payload_sha256']
    finally:os.close(fd)
    assert json.loads(subprocess.check_output(['plgpuctl','status']))==before
    print('JAVA125_REBOOT_BACKUP_READY '+json.dumps(record),flush=True)
    deadline=time.monotonic()+300
    while not (TMP/'java125-recovery-ack').exists():
        assert time.monotonic()<deadline,'Host readback acknowledgement expired'
        time.sleep(.1)
    assert (TMP/'java125-recovery-ack').read_text().strip()==record['payload_sha256']
    idle();print('JAVA125_REBOOT_BACKUP_RELEASED',flush=True)
finally:
    for f in reversed(locks):f.close()
