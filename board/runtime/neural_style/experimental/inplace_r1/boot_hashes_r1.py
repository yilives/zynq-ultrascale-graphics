import hashlib
import json
from pathlib import Path

base=Path('/media/sd-mmcblk1p1')
record={}
for name in ('BOOT.BIN','system.dtb'):
    path=base/name
    assert path.is_file(),str(path)
    record[name]=dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
print('CNN_BOOT_HASHES',json.dumps(record),flush=True)
