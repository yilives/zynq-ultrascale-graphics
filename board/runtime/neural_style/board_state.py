#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import hashlib
import gzip
import json
import mmap
import os
from pathlib import Path
import struct
import subprocess

assert os.geteuid() == 0
root = Path('/opt/rasterix/neural-style')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def backup_hashes(directory):
    result = {}
    for name in ('BOOT.BIN', 'system.dtb'):
        path = directory / name
        if path.is_file():
            result[name] = sha(path)
        elif path.with_name(name + '.gz').is_file():
            result[name] = hashlib.sha256(gzip.decompress(path.with_name(name + '.gz').read_bytes())).hexdigest()
    return result
manifest = json.loads((root / 'manifest.json').read_text())
files = {name: {'bytes': (root / name).stat().st_size, 'sha256': sha(root / name),
                'matches_manifest': sha(root / name) == meta['sha256']} for name, meta in manifest.items()}
sd = Path('/media/sd-mmcblk1p1')
record = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
          'uname': subprocess.check_output(['uname', '-a'], text=True).strip(),
          'gpu': json.loads(subprocess.check_output(['plgpuctl', 'status'], text=True)),
          'files': files, 'boot': {name: sha(sd / name) for name in ('BOOT.BIN', 'system.dtb')},
          'command_symlink': str(Path('/usr/bin/rix-neural-games').resolve())}
node = Path('/proc/device-tree/neural-style@a0030000/compatible')
record['cnn'] = None
if node.exists():
    assert node.read_bytes() in (b'rasterix,cnn-int8-v1\0', b'rasterix,cnn-int8-v2\0')
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    with mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0xa0030000) as regs:
        record['cnn'] = {hex(offset): struct.unpack_from('<I', regs, offset)[0] for offset in (0, 4, 0xc, 0x28, 0x2c, 0x30, 0x34)}
        if record['cnn']['0x0'] == 0x4e4e5332:
            record['cnn'].update({hex(offset): struct.unpack_from('<I', regs, offset)[0] for offset in (0x38, 0x3c)})
    os.close(fd)
backup = sd / 'rasterix-neural-backup-20261020'
record['backup'] = backup_hashes(backup)
backup = sd / 'rasterix-neural-fast-backup-20261020'
record['previous_nns1_backup'] = backup_hashes(backup)
backup = sd / 'rasterix-neural-buffer-backup-20261020'
record['previous_nns2_backup'] = backup_hashes(backup)
backup = sd / 'rasterix-neural-copy-backup-20261020'
record['previous_buffered_nns2_backup'] = backup_hashes(backup)
record['all_installed_files_match'] = all(v['matches_manifest'] for v in files.values())
print(json.dumps(record), flush=True)
