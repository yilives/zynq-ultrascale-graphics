"""Snapshot the completed RAM QA files into a bounded, indexed transport."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

stage=Path('/tmp/rix-cnn-inplace-r1')
assert 'CNN_INPLACE_BOARD_QA_COMPLETE' in (stage/'job.log').read_text()
result=json.loads((stage/'qa/result.json').read_text())
snapshots={}
for path in sorted((stage/'qa').rglob('*')):
    if path.is_file():
        assert not path.is_symlink()
        snapshots[path.relative_to(stage).as_posix()]=path.read_bytes()
for name in ['source.json','manifest.json','payload-index.json','board_profile.py','board_qa_r1.py','job.json','job.log']:
    snapshots[name]=(stage/name).read_bytes()
index={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in snapshots.items()}
snapshots['evidence-index.json']=(json.dumps(index,indent=2)+'\n').encode()
archive=stage/'evidence.tar.gz'
assert not archive.exists()
with tarfile.open(archive,'w:gz') as tar:
    for name,data in snapshots.items():
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600
        tar.addfile(info,io.BytesIO(data))
assert archive.stat().st_size<4*1024*1024
print('CNN_EVIDENCE_EXPORT',json.dumps(dict(path=str(archive),bytes=archive.stat().st_size,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=len(snapshots),qa_passed=result['passed'])),flush=True)
