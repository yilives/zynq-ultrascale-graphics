"""Export already completed UI QA in aligned TAR blocks, preserving first failure."""
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import struct
import sys
import tarfile
import time

ROOT=Path('/tmp');OUT=ROOT/'rasterix-launcher-ui-qa-v1'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
spec=importlib.util.spec_from_file_location('frozen',ROOT/'fpga_fsr_control.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
adapter=m.LinuxAdapter()
with adapter.locks():
    GpuRecoveryGuard().check();before=adapter.snapshot();m.check_idle(before)
    record=json.loads((OUT/'board-result.json').read_text())
    assert record['passed'] and record['board_boot_id']==before['boot_id'] and not record['real_game_launched']
    assert record['gpu_and_post_unchanged'] and record['receipt_unchanged'] and record['control_server_stopped']
    assert record['after']['gpu']==before['gpu'] and record['after']['post']==before['post'] and not before['clients']
    assert not (OUT/'control.sock').exists()
    for result in record['results']:
        path=OUT/(str(result['width'])+'x'+str(result['height']))/'frame.bmp'
        assert path.stat().st_size==result['snapshot_bytes'] and sha(path)==result['snapshot_sha256']
        assert len(result['checks'])==14 and result['passed']
    archive=OUT/'evidence.tar.gz';assert archive.is_file()
    export=dict(passed=True,scope='Recovery of evidence transport only; original UI QA not rerun',
        boot_id=before['boot_id'],before=before,inner_sha256=sha(archive),inner_bytes=archive.stat().st_size,
        first_export_failed=True,transport='Uncompressed TAR; full 512-byte blocks for Device-memory staging',
        original_qa_source_sha256=sha(ROOT/'launcher_ui_qa_v1.py'))
    manifest=OUT/'export-v2.json'
    with manifest.open('x') as stream:json.dump(export,stream,indent=2)
    transport=OUT/'transport-v2.tar';assert not transport.exists()
    with tarfile.open(transport,'w') as target:
        target.add(archive,arcname='evidence.tar.gz',recursive=False)
        target.add(manifest,arcname='export-v2.json',recursive=False)
    data=transport.read_bytes();assert 0<len(data)<=16*1024*1024 and len(data)%512==0
    node=Path('/proc/device-tree/reserved-memory/graphics@60000000')
    assert struct.unpack('>4I',(node/'reg').read_bytes())==(0,0x60000000,0,0x2000000) and (node/'no-map').exists()
    fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
    try:
        with mmap.mmap(fd,(len(data)+4095)//4096*4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x60800000) as memory:
            memory[:len(data)]=data;assert hashlib.sha256(memory[:len(data)]).hexdigest()==sha(transport)
    finally:os.close(fd)
    print('LAUNCHER_UI_EVIDENCE_READY '+json.dumps(dict(bytes=len(data),sha256=sha(transport),boot_id=before['boot_id'])),flush=True)
    deadline=time.monotonic()+600;ack=ROOT/'launcher-ui-v1-evidence-ack'
    while not ack.exists():
        assert time.monotonic()<deadline;time.sleep(.2)
    assert ack.read_text().strip()==sha(transport)
    after=adapter.snapshot();m.check_idle(after);GpuRecoveryGuard().check()
    assert before['gpu']==after['gpu'] and before['post']==after['post']
print('LAUNCHER_UI_EVIDENCE_RELEASED',flush=True)
