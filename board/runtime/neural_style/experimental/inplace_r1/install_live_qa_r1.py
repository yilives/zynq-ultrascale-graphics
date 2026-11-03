import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

stage=Path('/tmp/rix-cnn-inplace-r1')
assert json.loads((stage/'qa/result.json').read_text())['passed']
archive=Path('/tmp/rix-cnn-inplace-live-r1.tar.gz')
assert archive.stat().st_size==5617 and hashlib.sha256(archive.read_bytes()).hexdigest()=='88c4be8f542d16b93e7c5f1d9fd0921d59aeedb0db1f31fde7e2747ae01391b3'
with tarfile.open(archive) as tar:
    members=tar.getmembers()
    assert {m.name for m in members}=={'board_live_r1.py','board_live_tasks_r1.py','live-extension-index.json'}
    assert all(m.isfile() and not (stage/m.name).exists() for m in members)
    tar.extractall(stage)
index=json.loads((stage/'live-extension-index.json').read_text())
for name,digest in index.items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest
with (stage/'live-job.log').open('xb') as log:
    child=subprocess.Popen([sys.executable,'-B',str(stage/'board_live_r1.py')],stdin=subprocess.DEVNULL,
                           stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(stage/'live-job.json').write_text(json.dumps(dict(pid=child.pid))+'\n')
print('CNN_LIVE_QA_STARTED',child.pid,flush=True)
