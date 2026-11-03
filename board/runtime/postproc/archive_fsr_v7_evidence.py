#!/usr/bin/env python3
"""Preserve the failed v7 first-frame case and its verified rollback in RAM."""
import hashlib
import json
from pathlib import Path
import tarfile

root=Path('/tmp/postproc-tests')
out=root/'fsr_pl_v7_evidence.tar.gz'
assert not out.exists() and not out.is_symlink()
qa=root/'fsr-pl-v7'
recovery=json.loads((root/'cc_fsr_fpga_recover_v7.json').read_text())
assert recovery['rollback']['passed'] and recovery['outcome']=='rolled-back'
assert recovery['rollback']['final']['gpu']['underflows']==0
result=json.loads((qa/'result.json').read_text())
assert result['passed'] is False and result['lcd']['mismatches']==0
files={
    'load.json':root/'cc_fsr_fpga_load.json',
    'recovery.json':root/'cc_fsr_fpga_recover_v7.json',
    'stage.json':Path('/tmp/rix-fpga-fsr/stage-result.json'),
    'static/result.json':qa/'result.json',
    'static/lcd.rgb565':qa/'lcd.rgb565',
    'stage.log':Path('/tmp/fsr-stage-v7.log'),
    'load.log':Path('/tmp/fsr-load-v7.log'),
    'recovery.log':Path('/tmp/fsr-recover-v7.log'),
}
for path in qa.glob('*.log'):files['static/'+path.name]=path
with tarfile.open(str(out),'x:gz') as archive:
    for name,path in sorted(files.items()):
        assert path.is_file() and not path.is_symlink()
        archive.add(str(path),arcname=name,recursive=False)
print('FSR_V7_EVIDENCE',out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
