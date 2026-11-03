#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verified additive boot update. Original files are backed up and rehashed.

BOOT first: new fabric with the old DTB remains compatible with existing games;
old fabric with an advertised new peripheral would permit an unsafe probe.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

p = argparse.ArgumentParser()
p.add_argument('--apply', action='store_true')
a = p.parse_args()
assert os.geteuid() == 0
cache = Path('/opt/rasterix/experimental/cache')
archive = cache / 'neural-boot.tar.gz'
receipt = json.loads((cache / 'neural-boot.json').read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert receipt['verified'] and sha(archive) == receipt['sha256']
sd = Path('/media/sd-mmcblk1p1')
assert sd.resolve() == sd
mounts = [line.split() for line in Path('/proc/mounts').read_text().splitlines()]
assert any(m[0] == '/dev/mmcblk1p1' and m[1] == str(sd) and 'rw' in m[3].split(',') for m in mounts)
active = subprocess.run(['pidof', 'tuxracer', 'neverball', 'neverputt', 'quakespasm', 'quake3e', 'th06-rix', 'rix-smoke', 'rix-superres', 'rix-neural-style'], stdout=subprocess.PIPE)
assert active.returncode == 1 and not active.stdout, 'Stop graphics/postprocessing clients before boot update'
with tarfile.open(archive) as tf:
    members = tf.getmembers()
    assert len(members) == 3 and {m.name for m in members} == {'neural-boot/' + n for n in ('BOOT.BIN', 'system.dtb', 'manifest.json')}
    assert all(m.isfile() for m in members)
    manifest = json.load(tf.extractfile('neural-boot/manifest.json'))
    data = {name: tf.extractfile('neural-boot/' + name).read() for name in ('BOOT.BIN', 'system.dtb')}
for name, content in data.items():
    meta = manifest['files'][name]
    assert len(content) == meta['bytes'] and hashlib.sha256(content).hexdigest() == meta['sha256']
    assert (sd / name).is_file() and not (sd / name).is_symlink()
before = {name: sha(sd / name) for name in data}
assert before == manifest['expected_previous'] or all(before[n] == manifest['files'][n]['sha256'] for n in data), 'Unknown current boot files; preserve and inspect before updating'
assert manifest['backup_directory'] == 'rasterix-neural-copy-backup-20261020'
backup = sd / manifest['backup_directory']
assert backup.resolve() == backup
record = {'before': before, 'new': manifest['files'], 'apply': a.apply, 'backup': str(backup)}
if a.apply and before == manifest['expected_previous']:
    backup.mkdir(exist_ok=True)
    for name in data:
        saved = backup / name
        if not saved.exists():
            with saved.open('xb') as f:
                f.write((sd / name).read_bytes())
                f.flush(); os.fsync(f.fileno())
        assert sha(saved) == before[name]
    assert shutil.disk_usage(sd).free > sum(len(b) for b in data.values()) + 16*1024*1024
    for name, content in data.items():
        temp = sd / (name + '.neural-incoming')
        assert not temp.is_symlink()
        with temp.open('wb') as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
        assert sha(temp) == manifest['files'][name]['sha256']
    os.sync()
    for name in ('BOOT.BIN', 'system.dtb'):
        (sd / (name + '.neural-incoming')).replace(sd / name)
        os.sync()
        assert sha(sd / name) == manifest['files'][name]['sha256']
record['after'] = {name: sha(sd / name) for name in data}
if a.apply:
    assert all(record['after'][n] == manifest['files'][n]['sha256'] for n in data)
    (backup / 'update.json').write_text(json.dumps(record, indent=2) + '\n')
    os.sync()
Path('/tmp/neural-boot-update.json').write_text(json.dumps(record, indent=2) + '\n')
print('NEURAL_BOOT_UPDATE', json.dumps(record), flush=True)
