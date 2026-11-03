#!/usr/bin/env python3
"""Whole 800x480 UI frames through the existing PST1 native double buffer.

No GL context, downsampling, live source reads, or CNN/FSR job is used. The
controller waits for this process to restore POST and exit before any game.
"""
import argparse,ctypes as c,hashlib,json,mmap,os,signal,stat,subprocess,sys,time
from pathlib import Path

WIDTH,HEIGHT=800,480
FRAME_BYTES=WIDTH*HEIGHT*2


class NativeProtocol:
    def __init__(self,io,clock=time.monotonic,sleep=time.sleep):
        self.io,self.clock,self.sleep=io,clock,sleep
        assert io.read(0x50)==0x50535431 and io.read(0x74)==0x534e5031,'PST1/SNP1 identity mismatch'
        assert io.read(0x88)==0xa1400000 and io.read(0x90)==384000,'Unexpected native/snapshot memory layout'
        assert io.read(0x54)==io.read(0x58)==1,'Require restored POST mode 1 before menu'
        self.expected=1
        self.idle()

    def idle(self):
        assert self.io.read(0x7c)==self.io.read(0x8c)==0,'Snapshot lease/expiry must be clear'
        assert self.io.read(0x54)==self.io.read(0x58)==self.expected,'Unexpected POST owner/configuration'

    def switch(self,word):
        self.io.write(0x54,word)
        until=self.clock()+3
        # STOP never interrupts this acknowledgement barrier or lends the bank.
        while self.io.read(0x58)!=word:
            if self.clock()>=until:raise RuntimeError('Native LCD frame acknowledgement timeout')
            self.sleep(.001)
        self.expected=word
        self.idle()

    def present(self,raw):
        if len(raw)!=FRAME_BYTES:raise ValueError('Require one whole 800x480 RGB565 frame')
        self.idle()
        bank=((self.expected>>9)&1)^1
        self.io.copy(bank,raw)  # Ordered stores + dsb sy precede frame publication.
        self.switch(2|(bank<<9))
        return bank

    def restore(self):
        self.idle()
        self.switch(1)


class Device:
    def __init__(self,library):
        self.library=c.CDLL(str(library))
        self.library.rix_menu_read32.argtypes=[c.c_void_p,c.c_uint];self.library.rix_menu_read32.restype=c.c_uint32
        self.library.rix_menu_write32.argtypes=[c.c_void_p,c.c_uint,c.c_uint32];self.library.rix_menu_write32.restype=None
        self.library.rix_menu_write565.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t];self.library.rix_menu_write565.restype=c.c_int
        self.regs=self.banks=None
        fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        try:
            self.regs=mmap.mmap(fd,65536,offset=0xa0010000)
            # Only the two native frame banks. Never map the snapshot at +4MiB.
            self.banks=mmap.mmap(fd,0x400000,offset=0xa1000000)
        except BaseException:
            self.close();raise
        finally:os.close(fd)
        self.rptr=c.addressof(c.c_char.from_buffer(self.regs))
        self.bptr=c.addressof(c.c_char.from_buffer(self.banks))

    def read(self,offset):return self.library.rix_menu_read32(self.rptr,offset)
    def write(self,offset,value):self.library.rix_menu_write32(self.rptr,offset,value)
    def copy(self,bank,raw):
        assert bank in (0,1) and len(raw)==FRAME_BYTES
        source=c.create_string_buffer(raw,len(raw))
        assert self.library.rix_menu_write565(self.bptr+bank*0x200000,source,len(raw))==0,'Native pixel transfer failed'
    def close(self):
        for name in ('banks','regs'):
            value=getattr(self,name,None)
            if value is not None:value.close();setattr(self,name,None)


def worker(frame,state,token):
    from java_profile import LOCK_NAMES,OLD_BIT
    from play_game import acquire
    sys.path.insert(0,'/opt/rasterix/experimental')
    from game_runtime_support import DisplayStatus,GpuRecoveryGuard
    assert os.geteuid()==0
    os.umask(0o077);locks={};device=None;protocol=None;stopped=False
    guard=GpuRecoveryGuard()
    record=dict(passed=False,phase='starting',token=token,pid=os.getpid(),frames=0,backend='PST1 native 800x480',
        output='RGB LCD',source=[800,480],render=[800,480],dp_output=False,gpu_touched=False,post_changed=False,post_restored=False)
    def save():
        pending=state.with_name(state.name+'.new');pending.write_text(json.dumps(record,indent=2)+'\n');pending.replace(state)
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def gpu():
        item=DisplayStatus()
        try:result=item.read()
        finally:item.close()
        assert result['status']==3 and all(result[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
        assert len({result[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1,'GPU must already be drained'
        return result
    def post():
        return dict(requested=device.read(0x54),active=device.read(0x58),snapshot_status=device.read(0x7c),snapshot_expirations=device.read(0x8c))
    try:
        for name in LOCK_NAMES:locks[name]=acquire(name)
        guard.check()
        receipt=Path('/tmp/rix-fpga-fsr/active-receipt.txt');info=receipt.lstat();rows=receipt.read_text().splitlines()
        assert not receipt.is_symlink() and info.st_uid==0 and not info.st_mode&0o077
        assert len(rows)==4 and rows[0]=='RIX_FSR_PL_ACTIVE_V1' and rows[2]==OLD_BIT
        assert rows[3]=='b3a546c81676ab63395de0b4be4b5d4c5586d82b7d775e5d6ba4b25cd101d703'
        assert rows[1]==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert Path('/proc/device-tree/touch-gpio@a0020000').is_dir()
        assert subprocess.run(['pidof','tuxracer','neverball','neverputt','quakespasm','quake3e','th06-rix',
            'ClassiCube','java','rix-fsr-pl','rix-neural-style'],stdout=subprocess.PIPE).returncode==1,'Existing game/postprocessor client'
        record.update(boot_id=rows[1],before=gpu())
        device=Device(Path(__file__).resolve().parent/'menu/librix-menu-native.so')
        record['post_before']=post();protocol=NativeProtocol(device)
        last=None;deadline=time.monotonic()+15
        while not stopped:
            try:
                # Open the atomically published inode, then validate this fd.
                fd=os.open(str(frame),os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as stream:
                    info=os.fstat(stream.fileno());stamp=(info.st_ino,info.st_mtime_ns,info.st_size)
                    assert stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_size==FRAME_BYTES
                    raw=stream.read() if stamp!=last else None
                if raw is not None:
                    record.update(gpu_touched=True,post_changed=True);save()
                    bank=protocol.present(raw)
                    record.update(after=gpu(),post_active=post(),frames=record['frames']+1,
                        phase='ready',passed=True,frame_sha256=hashlib.sha256(raw).hexdigest(),bank=bank)
                    save();last=stamp
            except FileNotFoundError:
                if time.monotonic()>deadline:raise RuntimeError('UI did not publish a whole menu frame')
            time.sleep(.05)
        protocol.restore();record.update(after=gpu(),post_after=post(),post_restored=True,passed=True,phase='released')
    except BaseException as exc:
        record.update(passed=False,phase='error',error=repr(exc))
        if record['gpu_touched']:
            guard.mark('lcd-native-'+token,dict(reason=repr(exc),exit_code=2,transport_errors=True,after=record.get('after')))
    finally:
        if device is not None:device.close()
        save()
        for stream in locks.values():stream.close()
    print('LAUNCHER_LCD_MENU_RESULT '+json.dumps(record),flush=True)
    return 0 if record['passed'] else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--frame',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--token',required=True)
    args=parser.parse_args();assert len(args.token)==32 and all(ch in '0123456789abcdef' for ch in args.token)
    raise SystemExit(worker(args.frame,args.state,args.token))
