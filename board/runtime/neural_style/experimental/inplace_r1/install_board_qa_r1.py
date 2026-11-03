"""Validate the complete transport before starting a detached RAM-only QA job."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

archive=Path('/tmp/rix-cnn-inplace-r1.tar.gz')
stage=Path('/tmp/rix-cnn-inplace-r1')
assert os.geteuid()==0
assert archive.stat().st_size==2608033
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='3eb662a47020781aa87fe28066424c851ba0ce374a3014afb7194eb475b4b19c'
assert not stage.exists() and not stage.is_symlink()
with tarfile.open(archive,'r:gz') as tar:
    members=tar.getmembers()
    assert len(members)<100 and len({m.name for m in members})==len(members)
    assert all(m.isfile() and Path(m.name).name==m.name and m.name not in ('.','..') for m in members)
    assert sum(m.size for m in members)<16*1024*1024
    stage.mkdir(mode=0o700)
    tar.extractall(str(stage),members=members)
index=json.loads((stage/'payload-index.json').read_text())
for name,meta in index.items():
    data=(stage/name).read_bytes()
    assert len(data)==meta['bytes'] and hashlib.sha256(data).hexdigest()==meta['sha256'],name
manifest=json.loads((stage/'manifest.json').read_text())
old=manifest['images']['old']
for candidate in (Path('/tmp/rix-launcher-java-profile-v2/old.bin'),Path('/tmp/rix-fpga-fsr/new.bin')):
    if candidate.is_file() and not candidate.is_symlink():
        if candidate.stat().st_size==old['bytes'] and hashlib.sha256(candidate.read_bytes()).hexdigest()==old['sha256']:
            os.link(candidate,stage/'old.bin');break
else:raise RuntimeError('No verified original rollback image in RAM; FPGA was not touched')
assert hashlib.sha256((stage/'source.json').read_bytes()).hexdigest()==manifest['source_sha256']
with (stage/'job.log').open('xb') as log:
    child=subprocess.Popen([sys.executable,'-B',str(stage/'board_qa_r1.py')],
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
record=dict(pid=child.pid,stage=str(stage),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
(stage/'job.json').write_text(json.dumps(record)+'\n')
print('CNN_INPLACE_BOARD_QA_STARTED',json.dumps(record),flush=True)
