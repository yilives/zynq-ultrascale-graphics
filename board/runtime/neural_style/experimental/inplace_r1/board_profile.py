"""Explicit NIP1 contract extension of the frozen, journaled PL loader.

Importing is inert. Hardware snapshots retain their actual identities.
"""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path

OLD='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
NEW='37fe0a87465e6a4de9c0516530d8acabdfd415bbf48e8c971af76a477f4f6dde'
LOADER='8c3d0ae9f665bc4365f4ff0bd15b57ff1e933b071b12fdb1f68c08111f117f80'
STAGE=Path('/tmp/rix-cnn-inplace-r1')
LEGACY=Path('/tmp/rix-fpga-fsr/active-receipt.txt')


def contract(digest):
    if digest==OLD:
        return dict(magic=0x4e4e5332,shape=(96<<16)|160,capabilities=7,adapter_abi=0x20001)
    if digest==NEW:
        return dict(magic=0x4e495031,shape=(96<<16)|160,capabilities=15,adapter_abi=0x30001,expected_cycles=462816)
    raise RuntimeError('Unregistered CNN bitstream: '+digest)


def load(loader):
    assert hashlib.sha256(Path(loader).read_bytes()).hexdigest()==LOADER
    spec=importlib.util.spec_from_file_location('cnn_inplace_frozen_loader',loader)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.BASE=STAGE;m.MANIFEST=STAGE/'manifest.json'
    m.REPORT=Path('/tmp/postproc-tests/cnn-inplace-r1-load.json')
    m.java_cnn_contract=contract
    m.CLIENTS=(*m.CLIENTS,'java','rix-launcher','rix-neural-inplace')

    class Adapter(m.LinuxAdapter):
        def __init__(self):
            super().__init__();self.owned={};self.lent=set()

        def require_locks(self):
            assert set(self.owned)==set(m.LOCKS) and not self.lent
            for name,stream in self.owned.items():
                assert not stream.closed
                assert os.fstat(stream.fileno()).st_ino==Path('/tmp',name).stat().st_ino

        @contextlib.contextmanager
        def locks(self):
            import fcntl
            if self.owned:
                self.require_locks();yield;return
            with contextlib.ExitStack() as stack:
                try:
                    for name in m.LOCKS:
                        path=Path('/tmp',name)
                        assert not path.is_symlink()
                        fd=os.open(str(path),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
                        stream=stack.enter_context(os.fdopen(fd,'a+'))
                        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        self.owned[name]=stream
                    self.require_locks();yield
                finally:self.owned={}

        @contextlib.contextmanager
        def lend_post(self):
            import fcntl
            self.require_locks();name='rix-superres.lock';stream=self.owned[name]
            fcntl.flock(stream.fileno(),fcntl.LOCK_UN);self.lent.add(name)
            try:yield
            finally:
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                self.lent.remove(name);self.require_locks()

        def rollback_proof(self,boot,bit):
            proof=json.loads(Path('/tmp/postproc-tests/cc_fsr_fpga_load.json').read_text())
            assert proof['passed'] and proof['outcome']=='new-loaded-and-verified'
            assert bit==OLD and proof['after']['boot_id']==boot
            assert proof['manifest']['images']['new']['sha256']==bit

        def cnn(self):
            with self.mmio(0xa0030000) as mm:
                magic=self.read32(mm,0)
                m.require(magic in (0x4e4e5332,0x4e495031),'Unknown CNN MMIO layout')
                caps=self.read32(mm,0x3c)
                result=dict(magic=magic,shape=self.read32(mm,4),capabilities=caps,
                            adapter_abi=self.read32(mm,0x44) if caps&4 else None)
                if magic==0x4e495031:result['expected_cycles']=self.read32(mm,0x38)
                return result

        def activate_receipt(self,boot,bit,source):
            assert bit==NEW
            path=STAGE/'active-receipt.txt'
            fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as out:
                out.write('\n'.join(('RIX_CNN_INPLACE_ACTIVE_V1',boot,bit,source))+'\n')
                out.flush();os.fsync(out.fileno())

    return m,Adapter
