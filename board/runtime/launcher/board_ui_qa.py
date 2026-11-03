#!/usr/bin/env python3
"""Real AArch64 software UI QA; preserves GPU/POST/receipt, no game launch."""
import hashlib
import argparse
import importlib.util
import io
import json
import mmap
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tarfile
import time

ROOT=Path('/tmp')
PACKAGE=ROOT/'rix-java256-swap-transfer/cpu-r137.tar.gz'
parser=argparse.ArgumentParser()
parser.add_argument('--sha256',required=True)
args=parser.parse_args()
EXPECTED=args.sha256
assert len(EXPECTED)==64 and all(c in '0123456789abcdef' for c in EXPECTED)
OUT=ROOT/'rasterix-launcher-ui-qa-v1'
APP=ROOT/'rasterix-launcher-v1'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert os.geteuid()==0 and platform.machine()=='aarch64'
assert sha(PACKAGE)==EXPECTED and not PACKAGE.is_symlink()
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
spec=importlib.util.spec_from_file_location('frozen',ROOT/'fpga_fsr_control.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
adapter=m.LinuxAdapter()
with adapter.locks():
    GpuRecoveryGuard().check();before=adapter.snapshot();m.check_idle(before)
    assert not before['clients']
    receipt_path=ROOT/'rix-fpga-fsr/active-receipt.txt'
    receipt=receipt_path.read_bytes()
    assert receipt.decode().splitlines()[1:3]==[before['boot_id'],'035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9']
    assert not APP.exists() and not OUT.exists()
    APP.mkdir(mode=0o700);OUT.mkdir(mode=0o700)
    with tarfile.open(PACKAGE) as source:
        names=source.getnames()
        assert len(names)==len(set(names))
        manifest=json.load(source.extractfile('rasterix-launcher-v1/package-manifest.json'))['files']
        assert set(names)=={'rasterix-launcher-v1/'+name for name in manifest}|{'rasterix-launcher-v1/package-manifest.json'}
        for member in source:
            relative=Path(member.name)
            assert member.isfile() and not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='rasterix-launcher-v1'
            target=APP.joinpath(*relative.parts[1:]);target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            data=source.extractfile(member).read()
            if relative.name!='package-manifest.json':
                expected=manifest['/'.join(relative.parts[1:])]
                assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256']
            with target.open('xb') as stream:stream.write(data)
            target.chmod(0o700 if relative.name=='rix-launcher' else 0o600)
    socket=OUT/'control.sock'
    with (OUT/'control.log').open('xb') as log:
        server=subprocess.Popen(['python3',str(APP/'launcher_control.py'),'--socket',str(socket),'serve'],stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+10
            while not socket.exists():
                assert server.poll() is None and time.monotonic()<deadline
                time.sleep(.02)
            results=[]
            for size in ('1920x1080','800x480'):
                target=OUT/size;target.mkdir(mode=0o700)
                command=[str(APP/'rix-launcher'),'--assets',str(APP/'assets'),'--headless','--size',size,
                    '--socket',str(socket),'--state-dir',str(target/'state'),'--test-ui',str(target/'result.json'),
                    '--snapshot',str(target/'frame.bmp')]
                with (target/'ui.log').open('xb') as output:
                    subprocess.run(command,check=True,stdout=output,stderr=subprocess.STDOUT,timeout=90)
                result=json.loads((target/'result.json').read_text())
                assert result['passed'] and not result['hardware_access'] and len(result['checks'])==14
                result.update(snapshot_sha256=sha(target/'frame.bmp'),snapshot_bytes=(target/'frame.bmp').stat().st_size)
                results.append(result)
        finally:
            server.terminate();server.wait(timeout=5)
            assert not socket.exists()
    after=adapter.snapshot();m.check_idle(after);GpuRecoveryGuard().check()
    assert before['gpu']==after['gpu'] and before['post']==after['post'] and not after['clients']
    assert receipt_path.read_bytes()==receipt
    record=dict(passed=True,scope='AArch64 software UI and preview protocol only',real_game_launched=False,
        dp_or_lcd_output_validated=False,board_boot_id=before['boot_id'],package_sha256=EXPECTED,results=results,
        gpu_and_post_unchanged=True,receipt_unchanged=True,control_server_stopped=True,before=before,after=after)
    (OUT/'board-result.json').write_text(json.dumps(record,indent=2)+'\n')
    bundle=OUT/'evidence.tar.gz'
    with tarfile.open(bundle,'w:gz') as target:
        for relative in ('board-result.json','control.log','1920x1080/result.json','1920x1080/ui.log','1920x1080/frame.bmp',
                         '800x480/result.json','800x480/ui.log','800x480/frame.bmp'):
            target.add(OUT/relative,arcname=relative,recursive=False)
    transport=OUT/'transport.tar'
    export_path=OUT/'export-v2.json'
    export_path.write_text(json.dumps(dict(passed=True,boot_id=before['boot_id'],before=after,
        inner_sha256=sha(bundle),inner_bytes=bundle.stat().st_size,first_export_failed=False),indent=2))
    with tarfile.open(transport,'w') as target:
        target.add(bundle,arcname='evidence.tar.gz',recursive=False)
        target.add(export_path,arcname='export-v2.json',recursive=False)
    data=transport.read_bytes();assert 0<len(data)<=16*1024*1024 and len(data)%512==0
    node=Path('/proc/device-tree/reserved-memory/graphics@60000000')
    assert struct.unpack('>4I',(node/'reg').read_bytes())==(0,0x60000000,0,0x2000000) and (node/'no-map').exists()
    fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
    try:
        with mmap.mmap(fd,(len(data)+4095)//4096*4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x60800000) as memory:
            memory[:len(data)]=data;assert hashlib.sha256(memory[:len(data)]).hexdigest()==sha(transport)
    finally:os.close(fd)
    print('LAUNCHER_UI_EVIDENCE_READY '+json.dumps(dict(bytes=len(data),sha256=sha(transport),boot_id=before['boot_id'])),flush=True)
    deadline=time.monotonic()+600
    ack=ROOT/'launcher-ui-v1-evidence-ack'
    while not ack.exists():
        assert time.monotonic()<deadline;time.sleep(.2)
    assert ack.read_text().strip()==sha(transport)
    m.check_idle(adapter.snapshot())
print('LAUNCHER_UI_EVIDENCE_RELEASED',flush=True)
