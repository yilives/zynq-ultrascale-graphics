#!/usr/bin/env python3
"""RAM-only JTAG receiver holding the shared game lock throughout."""
import fcntl,hashlib,json,mmap,os,re,shutil,socket,struct,subprocess,sys
from pathlib import Path
BASE=Path('/tmp/rix-java125-transfer');SOCK=BASE/'control.sock'
NAMES=('jre','client','native')
CLIENTS=('tuxracer','rix-smoke','neverball','neverputt','quake3e','quakespasm','rix-glx-probe',
         'rix-danmaku','rix-superres','rix-neural-style','th06-rix','ClassiCube','rix-fsr-pl','java')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def idle():
    p=subprocess.run(['pidof',*CLIENTS],stdout=subprocess.PIPE)
    assert p.returncode==1 and not p.stdout,'PL/Java client active'
    node=Path('/proc/device-tree/reserved-memory/graphics@60000000')
    assert struct.unpack('>4I',(node/'reg').read_bytes())==(0,0x60000000,0,0x2000000)
    assert (node/'no-map').exists()
    d=json.loads(subprocess.check_output(['plgpuctl','status']))
    assert d['status']==3 and d['config']==0x9adb505e
    assert all(d[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    assert len({d[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
def serve():
    assert os.geteuid()==0
    if not BASE.exists():BASE.mkdir(mode=0o700)
    assert not BASE.is_symlink() and BASE.stat().st_uid==0 and not BASE.stat().st_mode&0o077
    assert not SOCK.exists()
    lock=open('/tmp/rasterix-game-launch.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    sys.path.insert(0,'/opt/rasterix/experimental')
    from game_runtime_support import GpuRecoveryGuard
    GpuRecoveryGuard().check();idle()
    server=socket.socket(socket.AF_UNIX);server.bind(str(SOCK));os.chmod(SOCK,0o600);server.listen(1)
    print('JAVA125_RECEIVER_READY',os.getpid(),flush=True)
    try:
        done=False
        while not done:
            conn,_=server.accept()
            with conn:
                try:
                    data=b''
                    while not data.endswith(b'\n'):
                        b=conn.recv(1024);assert b and len(data)+len(b)<4096;data+=b
                    req=json.loads(data);op=req[0]
                    if op=='ping':reply='READY'
                    elif op=='shutdown':reply='STOPPED';done=True
                    else:
                        name=req[1];assert name in NAMES
                        part=BASE/(name+'.part');final=BASE/(name+'.tar.gz');meta=BASE/(name+'.json')
                        idle()
                        if op=='begin':
                            size=int(req[2]);digest=req[3]
                            assert 0<size<100*1024*1024 and re.fullmatch('[0-9a-f]{64}',digest)
                            assert shutil.disk_usage(BASE).free>size*3+64*1024*1024
                            if final.exists():
                                assert not final.is_symlink() and final.stat().st_size==size and sha(final)==digest
                                reply='COMPLETE '+str(size)
                            else:
                                assert not part.exists() and not meta.exists()
                                with part.open('xb'):pass
                                os.chmod(part,0o600)
                                with meta.open('x') as f:json.dump(dict(bytes=size,sha256=digest),f)
                                reply='OFFSET 0'
                        elif op=='chunk':
                            offset,length,digest=int(req[2]),int(req[3]),req[4]
                            m=json.loads(meta.read_text())
                            assert not part.is_symlink() and part.stat().st_size==offset
                            assert 0<length<=2097152 and offset+length<=m['bytes']
                            assert re.fullmatch('[0-9a-f]{64}',digest)
                            fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
                            try:
                                with mmap.mmap(fd,(length+4095)//4096*4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=0x60800000) as mem:
                                    chunk=mem[:(length+63)//64*64][:length]
                            finally:os.close(fd)
                            assert hashlib.sha256(chunk).hexdigest()==digest,'JTAG block SHA mismatch'
                            with part.open('ab') as f:f.write(chunk);f.flush()
                            reply='ACK '+str(offset+length)
                        elif op=='finish':
                            m=json.loads(meta.read_text())
                            assert part.stat().st_size==m['bytes'] and sha(part)==m['sha256'] and not final.exists()
                            part.rename(final);reply='SHA256 '+m['sha256']
                        else:raise ValueError('Unknown operation')
                    conn.sendall(json.dumps(dict(ok=True,reply=reply)).encode()+b'\n')
                except Exception as exc:
                    conn.sendall(json.dumps(dict(ok=False,error=repr(exc))).encode()+b'\n')
    finally:
        server.close();SOCK.unlink();lock.close()
def request():
    c=socket.socket(socket.AF_UNIX);c.settimeout(45);c.connect(str(SOCK))
    c.sendall(json.dumps(sys.argv[2:]).encode()+b'\n');data=b''
    while not data.endswith(b'\n'):
        b=c.recv(4096);assert b;data+=b
    c.close();r=json.loads(data);assert r['ok'],r
    print('JAVA125 '+r['reply'],flush=True)
if __name__=='__main__':
    if sys.argv[1]=='serve':serve()
    elif sys.argv[1]=='request':request()
    else:raise ValueError('Unknown command')
