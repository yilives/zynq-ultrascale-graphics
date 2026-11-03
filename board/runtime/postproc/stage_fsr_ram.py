#!/usr/bin/env python3
"""Hold the shared idle locks while two JTAG payloads cross reserved PS RAM."""
import fcntl
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import tarfile
import time

BASE=Path('/tmp/rix-fpga-fsr')
parser=argparse.ArgumentParser()
parser.add_argument('--profile',choices=('fixed-v7','fixed-v8','fixed-v10-pipeline'),default='fixed-v7')
args=parser.parse_args()
suffix={'fixed-v7':'v7','fixed-v8':'v8','fixed-v10-pipeline':'v10'}[args.profile]
spec=json.loads(Path('/tmp/fsr-stage-manifest-'+suffix+'.json').read_text())
assert spec['format']=='rix-fsr-stage-v1'
assert not BASE.exists() and not BASE.is_symlink(), 'Preserve previous FSR transaction'
assert shutil.disk_usage('/').free>=32*1024*1024
assert shutil.disk_usage('/media/sd-mmcblk1p1').free>=16*1024*1024
BASE.mkdir(mode=0o700)
modspec=importlib.util.spec_from_file_location('fsr_controller','/tmp/fpga_fsr_control.py')
controller=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(controller)
adapter=controller.LinuxAdapter()
adapter.ram_directory(BASE)
locks=[]
for name in controller.LOCKS:
    fd=os.open('/tmp/'+name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    stream=os.fdopen(fd,'a+');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(stream)
before=adapter.runtime_state();controller.check_idle(before)
assert before['boot_id']==spec['boot_id']
adapter.rollback_proof(before['boot_id'],spec['loader']['images']['old']['sha256'])
assert adapter.cnn()=={'magic':0x4e4e5332,'shape':(96<<16)|160,'capabilities':7,'adapter_abi':0x20001}
old=Path('/tmp/rix-fpga-v4/new.bin')
assert adapter.regular_info(old)['sha256']==spec['loader']['images']['old']['sha256']
sha=lambda b:hashlib.sha256(b).hexdigest()
stopping=[False]
signal.signal(signal.SIGTERM,lambda *_:stopping.__setitem__(0,True))
record={'passed':False,'pid':os.getpid(),'before':before,'payloads':{},'error':None}
(BASE/'ready.json').write_text(json.dumps(record)+'\n')
print('FSR_STAGE_GUARD_READY',os.getpid(),flush=True)
try:
    for kind in ('new','payload'):
        item=spec['compressed'][kind]
        assert 0<item['bytes']<=4194304
        flag=BASE/(kind+'.ready');deadline=time.monotonic()+900
        while not flag.exists():
            assert not stopping[0] and time.monotonic()<deadline,'Staging cancelled or expired'
            time.sleep(.05)
        assert not flag.is_symlink() and flag.read_text().strip()==item['sha256']
        assert adapter.runtime_state()==before,'GPU/boot changed while staging'
        subprocess.run(['/tmp/read-ps-fsr-stage-v2',str(item['bytes']),kind],check=True,timeout=30)
        data=(BASE/(kind+'-staging-read.bin')).read_bytes()
        assert len(data)==item['bytes'] and sha(data)==item['sha256'],'Compressed payload mismatch'
        if kind=='new':
            raw=gzip.decompress(data);wanted=spec['loader']['images']['new']
            assert len(raw)==wanted['bytes'] and sha(raw)==wanted['sha256']
            with open(str(BASE/'new.bin'),'xb') as out:out.write(raw)
        else:
            expected=spec['payload_files']
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
                members=archive.getmembers()
                assert len(members)==len(expected) and len({m.name for m in members})==len(expected)
                assert sum(m.size for m in members)<12*1024*1024
                for member in members:
                    path=PurePosixPath(member.name)
                    assert member.isfile() and not path.is_absolute() and '..' not in path.parts and member.name in expected
                    info=expected[member.name];assert member.size==info['bytes']
                    content=archive.extractfile(member).read();assert sha(content)==info['sha256']
                    target=BASE.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True)
                    with open(str(target),'xb') as out:out.write(content)
                    target.chmod(info['mode'])
        record['payloads'][kind]=item
        (BASE/(kind+'.done')).write_text(item['sha256']+'\n')
        print('FSR_STAGE_PAYLOAD_VERIFIED',kind,item['bytes'],flush=True)
    with open(str(BASE/'old.bin'),'xb') as out:out.write(old.read_bytes())
    assert adapter.regular_info(BASE/'old.bin')['sha256']==spec['loader']['images']['old']['sha256']
    with open(str(BASE/'manifest.json'),'x') as out:json.dump(spec['loader'],out,indent=2);out.write('\n')
    assert adapter.runtime_state()==before
    record['passed']=True
except Exception as error:
    record['error']=repr(error)
finally:
    (BASE/'stage-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print('FSR_STAGE_COMPLETE',record['passed'],record['error'],flush=True)
    for stream in reversed(locks):stream.close()
raise SystemExit(0 if record['passed'] else 1)
