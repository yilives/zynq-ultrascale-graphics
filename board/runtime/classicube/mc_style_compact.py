"""Compact existing RAM evidence: retain full display via SHA, not UART bytes."""
import hashlib,json,tarfile,sys
from pathlib import Path
root=Path('/tmp/postproc-tests')/sys.argv[1]
assert root.parent.resolve()==Path('/var/volatile/tmp/postproc-tests').resolve()
for style in ('oil','anime'):
    data=(root/(style+'.display.bin')).read_bytes()
    (root/(style+'.display.json')).write_text(json.dumps({'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})+'\n')
    with tarfile.open(root.with_name(root.name+'_'+style+'_compact').with_suffix('.tar.gz'),'w:gz') as tf:
        for file in sorted(root.glob(style+'*')):
            if file.is_file() and file.name!=style+'.display.bin':tf.add(file,arcname=file.name)
