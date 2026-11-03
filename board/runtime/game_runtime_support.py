"""Low-overhead display telemetry and bounded, continuously drained game logs."""
import atexit
from collections import deque
from pathlib import Path
import re
import struct
import threading
import json
import os


class GpuRecoveryGuard:
    """A DMA timeout can leave the GPU stalled while display status stays ready."""
    def __init__(self,path=Path('/opt/rasterix/experimental/gpu-quarantine.json'),boot_id=None):
        self.path=Path(path)
        self.boot_id=boot_id or Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def check(self):
        if self.path.exists():
            previous=json.loads(self.path.read_text())
            if previous['boot_id']==self.boot_id:
                raise RuntimeError('Previous GPU/DMA failure in this boot; reboot the board before starting another game. Evidence: '+str(self.path))

    def mark(self,attempt,result):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_name(self.path.name+'.new')
        data={'boot_id':self.boot_id,'attempt':attempt,'reason':result['reason'],
              'exit_code':result['exit_code'],'transport_errors':result['transport_errors'],
              'after':result['after'],'recovery':'Normal full board reboot required before another GPU client.'}
        with temporary.open('w') as stream:
            json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,self.path)
        if hasattr(os,'O_DIRECTORY'):
            directory=os.open(str(self.path.parent),os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        return data


class DisplayStatus:
    # linux/include/plgpu-display.h: _IOR('R', 0, sixteen __u32 fields).
    FORMAT=struct.Struct('<16I')
    GET_STATUS=0x80405200
    FIELDS=('abi','config','status','enabled','frame_id','swap','copy','presented',
            'last_presented','read_errors','write_errors','timeouts','underflows',
            'scan_errors','command_beats','gpu_busy_cycles')

    def __init__(self):
        import fcntl
        import os
        self._ioctl=fcntl.ioctl
        self._close=os.close
        self.fd=os.open('/dev/plgpu_display',os.O_RDWR|os.O_CLOEXEC)
        self.buffer=bytearray(self.FORMAT.size)
        self.reads=0
        atexit.register(self.close)

    def read(self):
        self._ioctl(self.fd,self.GET_STATUS,self.buffer,True)
        result=dict(zip(self.FIELDS,self.FORMAT.unpack(self.buffer)))
        if result['abi']!=0x52495801 or result['config']!=0x9adb505e:
            raise RuntimeError('Display telemetry ABI/configuration mismatch')
        self.reads+=1
        # Fault bits are returned, so callers can save evidence before stopping.
        return result

    def close(self):
        if self.fd>=0:
            self._close(self.fd)
            self.fd=-1


class GameLog:
    """Drain stdout even after the disk limit; count errors over the entire stream.

    Keep the first occurrence of two already-known advisory messages. Bound
    the primary log and retain a separate tail if unique output exceeds it.
    Repeated advisory text never terminates a running game.
    """
    ADVISORIES={
        'glHint':re.compile(rb'^.*\[warning\] \[glHint\.cpp:[0-9]+\] glHint not implemented\r?\n$'),
        'glDrawBuffer':re.compile(rb'^.*\[warning\] \[glDrawBuffer\.cpp:[0-9]+\] glDrawBuffer not implemented\r?\n$'),
    }
    ERRORS={'transport_errors':b'dma-proxy ioctl errno=',
            'unsupported_clip_warnings':b'glClipPlane only GL_CLIP_PLANE0'}

    def __init__(self,path,limit=8*1024*1024,tail_limit=64*1024):
        assert limit>0 and tail_limit>0
        self.path=Path(path)
        self.limit=limit
        self.tail_limit=tail_limit
        self.file=self.path.open('wb')
        self.source=None
        self.thread=None
        self.failure=None
        self.raw_bytes=self.written=self.discarded=0
        self.lines=0
        self.advisories={key:0 for key in self.ADVISORIES}
        self.errors={key:0 for key in self.ERRORS}
        self._error_tails={key:b'' for key in self.ERRORS}
        self._tail=deque()
        self._tail_bytes=0

    def attach(self,source):
        assert self.thread is None
        self.source=source
        self.thread=threading.Thread(target=self._consume,name='game-log-drain',daemon=True)
        self.thread.start()

    def _accept(self,line):
        self.raw_bytes+=len(line)
        self.lines+=1
        for name,needle in self.ERRORS.items():
            combined=self._error_tails[name]+line
            self.errors[name]+=combined.count(needle)
            self._error_tails[name]=combined[-(len(needle)-1):]
        for name,pattern in self.ADVISORIES.items():
            if pattern.fullmatch(line):
                self.advisories[name]+=1
                if self.advisories[name]>1:return
                break
        count=min(len(line),max(0,self.limit-self.written))
        if count:
            self.file.write(line[:count])
            self.written+=count
            if line.startswith((b'RIX_FRAME_METRICS ',b'TUX_RIX_FRAME ')):
                self.file.flush()
        remainder=line[count:]
        if remainder:
            self.discarded+=len(remainder)
            self._tail.append(remainder)
            self._tail_bytes+=len(remainder)
            while self._tail_bytes>self.tail_limit:
                extra=self._tail_bytes-self.tail_limit
                first=self._tail.popleft()
                if len(first)>extra:
                    self._tail.appendleft(first[extra:])
                    self._tail_bytes-=extra
                else:self._tail_bytes-=len(first)

    def _consume(self):
        try:
            while True:
                # Also bound memory when a process emits a line without LF.
                line=self.source.readline(64*1024)
                if not line:break
                self._accept(line)
        except Exception as error:
            self.failure=repr(error)

    def finish(self):
        if self.thread:
            # The A53 takes >5 s to drain a synthetic 150k-short-line burst.
            # Keep a finite timeout without truncating a healthy consumer.
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                self.failure='Game stdout remained open after process exit'
                return
        if self.source:self.source.close()
        if not self.file.closed:
            self.file.flush()
            self.file.close()
        if self._tail:
            self.path.with_name('game-tail.log').write_bytes(b''.join(self._tail))

    def stats(self):
        return {'raw_bytes':self.raw_bytes,'stored_bytes':self.written,'line_chunks':self.lines,
                'advisory_occurrences':dict(self.advisories),
                'suppressed_advisories':sum(max(0,n-1) for n in self.advisories.values()),
                'overflow_bytes':self.discarded,'tail_bytes':self._tail_bytes,
                'primary_limit':self.limit,'tail_limit':self.tail_limit,
                'errors':dict(self.errors),'capture_failure':self.failure}

    def __enter__(self):return self
    def __exit__(self,*args):self.finish()
