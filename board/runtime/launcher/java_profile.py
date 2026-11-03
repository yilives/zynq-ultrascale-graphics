#!/usr/bin/env python3
"""Journaled Java dual-TMU profile lease. Original v23 is restored on clean exit.

The frozen controller does all reconfiguration. Its three locks are held during
each transition; only the POST lock is lent to the FSR process while playing.
No other game/loader can enter because the game launch lock remains held.
"""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path

OLD_BIT = '035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
JAVA_BIT = '14fd58da8a1a0348b0033f7efef35dc5498c2f4bd1f2a3c43b77404adc9cd961'
JAVA_SOURCE = 'f864fda53db14f4851cb4a109defffa65b6a39abc633048da81c9d3ab76574cc'
LOADER_SHA = '8c3d0ae9f665bc4365f4ff0bd15b57ff1e933b071b12fdb1f68c08111f117f80'
LEGACY = Path('/tmp/rix-fpga-fsr/active-receipt.txt')
CANONICAL = Path('/tmp/rix-fpga-java256/active-receipt.txt')
LOCK_NAMES = ('rasterix-game-launch.lock','rix-superres.lock','rix-mc-style-extract.lock')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def save(path, value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')

def receipt(path, magic, boot, bit, source):
    with Path(path).open('x') as stream:
        os.fchmod(stream.fileno(),0o600)
        stream.write('\n'.join((magic,boot,bit,source))+'\n')
        stream.flush();os.fsync(stream.fileno())

class Profile:
    def __init__(self, app, out, locks):
        self.app,self.out,self.locks = Path(app),Path(out),locks
        # The frozen loader deliberately accepts direct children of /tmp only.
        self.stage=Path('/tmp/rix-launcher-java-profile-v2')
        self.restore=Path('/tmp')/(self.out.name+'-restore-images')
        self.active=False
        self.retired=False
        self.controller_started=False
        self.results={}
        self.loaded=False
        loader=self.app/'java/java_dual_loader.py'
        assert sha(loader)==LOADER_SHA,'Unapproved PL loader'
        spec=importlib.util.spec_from_file_location('launcher_frozen_java_loader',loader)
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.m.CLIENTS=(*self.m.CLIENTS,'java')

    def require_locks(self):
        assert set(self.locks)==set(LOCK_NAMES)
        for name,stream in self.locks.items():
            assert not stream.closed and os.fstat(stream.fileno()).st_ino==Path('/tmp',name).stat().st_ino

    def transition(self, restoring):
        self.require_locks()
        m=self.m;owner=self
        m.BASE=self.restore if restoring else self.stage
        m.MANIFEST=m.BASE/'manifest.json'
        # Frozen adapter accepts journals directly under /tmp only.
        journal=Path('/tmp/postproc-tests')/(self.out.name+('-restore' if restoring else '-load')+'.json')
        assert not journal.exists() and not journal.is_symlink()
        m.REPORT=journal
        class Adapter(m.LinuxAdapter):
            @contextlib.contextmanager
            def locks(self):
                owner.require_locks();yield
            def rollback_proof(self,boot,bit):
                proof=owner.results['load'] if restoring else owner.original_proof
                assert proof['passed'] and proof['outcome']=='new-loaded-and-verified'
                assert proof['after']['boot_id']==boot and proof['manifest']['images']['new']['sha256']==bit
            def activate_receipt(self,boot,bit,source):
                if restoring:
                    assert owner.original_receipt.decode().splitlines()==['RIX_FSR_PL_ACTIVE_V1',boot,bit,source]
                    receipt(LEGACY,'RIX_FSR_PL_ACTIVE_V1',boot,bit,source)
                else:
                    assert bit==JAVA_BIT and source==JAVA_SOURCE
                    receipt(owner.stage/'active-receipt.txt','RIX_TEX256_DUAL_ACTIVE_V1',boot,bit,source)
                    # The accepted 8e89 driver has this fixed receipt path. Both
                    # consumers see one inode, issued only after verified load.
                    os.link(owner.stage/'active-receipt.txt',CANONICAL)
            def deactivate_receipt(self):
                paths=(LEGACY,) if restoring else (owner.stage/'active-receipt.txt',CANONICAL)
                for path in paths:
                    if path.exists():path.unlink()
        controller=m.Controller(Adapter())
        self.controller_started=True
        result=controller.run(controller.a.read_manifest)
        # Record fabric state before any fallible evidence writes.
        if not restoring and result['passed']:self.active=True;self.loaded=True
        if restoring and result['passed']:self.active=False
        self.results['restore' if restoring else 'load']=result
        save(self.out/'profile.json',self.results)
        return result

    def enter(self):
        self.require_locks()
        assert not (self.stage/'active-receipt.txt').exists()
        assert not CANONICAL.exists() and not CANONICAL.is_symlink()
        manifest=read(self.stage/'manifest.json')
        assert manifest['source_sha256']==JAVA_SOURCE
        assert manifest['images']['new']['sha256']==JAVA_BIT and manifest['images']['old']['sha256']==OLD_BIT
        self.original_proof=read('/tmp/postproc-tests/cc_fsr_fpga_load.json')
        initial=self.m.LinuxAdapter().snapshot();self.m.check_idle(initial)
        info=LEGACY.lstat()
        assert not LEGACY.is_symlink() and info.st_uid==0 and not info.st_mode&0o077
        self.original_receipt=LEGACY.read_bytes()
        assert self.original_receipt.decode().splitlines()[1:3]==[initial['boot_id'],OLD_BIT]
        (self.out/'original-receipt.txt').write_bytes(self.original_receipt)
        (self.out/'original-receipt.txt').chmod(0o600)
        self.restore.mkdir(mode=0o700)
        inverse=dict(format='rix-fpga-ram-fsr1',source_sha256=self.original_receipt.decode().splitlines()[3],images={})
        for role,other in (('new','old'),('old','new')):
            source=self.stage/(other+'.bin');target=self.restore/(role+'.bin')
            # Private hard links avoid duplicating two large RAM images per run.
            assert not source.is_symlink() and sha(source)==manifest['images'][other]['sha256']
            os.link(source,target)
            inverse['images'][role]=dict(filename=target.name,bytes=target.stat().st_size,sha256=sha(target))
        save(self.restore/'manifest.json',inverse)
        LEGACY.unlink();self.retired=True
        result=self.transition(False)
        if not result['passed']:
            if (not result['device_mutation_started'] or result['rollback']['passed']) and not LEGACY.exists():
                rows=self.original_receipt.decode().splitlines();receipt(LEGACY,*rows)
                self.retired=False
            raise RuntimeError('Java PL load failed; inspect journal')
        assert CANONICAL.read_bytes()==(self.stage/'active-receipt.txt').read_bytes()
        assert CANONICAL.stat().st_ino==(self.stage/'active-receipt.txt').stat().st_ino

    def leave(self):
        self.require_locks()
        if self.active:
            control=self.m.LinuxAdapter()
            control.set_post_mode1();control.wait_post_mode1()
            result=self.transition(True)
            assert result['passed'],'Original PL restore failed'
            (self.stage/'active-receipt.txt').rename(self.out/'retired-java-receipt.txt')
            CANONICAL.rename(self.out/'retired-java-canonical-receipt.txt')
            self.retired=False
        elif self.retired:
            # An interrupted controller without verified rollback cannot mint a receipt.
            assert not self.controller_started,'Unknown PL state; cold recovery required'
            rows=self.original_receipt.decode().splitlines();receipt(LEGACY,*rows)
            self.retired=False

    def invalidate(self):
        for path in (LEGACY,self.stage/'active-receipt.txt',CANONICAL):
            if path.exists():path.rename(self.out/('invalidated-'+path.parent.name+'-receipt.txt'))
