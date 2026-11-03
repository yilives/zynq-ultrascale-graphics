#!/usr/bin/env python3
"""Read a hardware-selected PS source only while its renderer is explicitly frozen.

This is diagnostic readback, never a live-frame substitute for the SNP1 lease.
The caller has drained CPU/DMA, fenced presentation and stopped new submissions.
"""
import hashlib, json, mmap, os, subprocess, time
from pathlib import Path

def capture_source(prefix, frame_id):
    prefix = Path(prefix)
    assert prefix.is_absolute() and Path('/tmp/postproc-tests') in prefix.parents
    # /tmp is a BSP symlink to /var/volatile/tmp; validate its resolved root.
    assert Path('/tmp/postproc-tests').resolve() in prefix.resolve().parents and not prefix.is_symlink()
    def gpu():
        state = json.loads(subprocess.check_output(['plgpuctl', 'status']))
        assert state['status'] == 3 and state['config'] == 0x9adb505e, ('GPU configuration',state)
        assert all(state[k] == frame_id for k in ('frame_id', 'swap', 'copy', 'presented', 'last_presented')), ('GPU frame changed',frame_id,state)
        assert not any(state[k] for k in ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')), ('GPU fault',state)
        return state
    def post():
        return json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres', '--status']))
    before = gpu(); first = post(); address = first['last_source']
    assert address in (0x60000000, 0x60100000, 0x60200000) and first['requested'] == first['active'] == 0, ('source/mode', first)
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, 0x30000, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ, offset=address) as mem:
            # Full 64-byte-aligned copies, as required by this BSP's Device mapping.
            data = mem[:192000]; time.sleep(.005); verify = mem[:192000]
    finally:
        os.close(fd)
    after = gpu(); last = post()
    assert data == verify and last['last_source'] == address and last['active'] == 0, ('source changed',address,last)
    assert all(before[k]==after[k] for k in ('command_beats','gpu_busy_cycles')), 'GPU was not frozen during source read'
    record = {'reference': 'hardware last completed PS source, frozen and immutable',
              'frame_id': frame_id, 'physical_address': address, 'bytes': len(data),
              'sha256': hashlib.sha256(data).hexdigest(), 'before': before, 'after': after,
              'post_before': first, 'post_after': last}
    Path(str(prefix) + '.bin').write_bytes(data)
    Path(str(prefix) + '.json').write_text(json.dumps(record, indent=2) + '\n')
    return record
