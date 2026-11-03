"""Exercise pipe backpressure, log overflow and the kernel ABI independently."""
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'linux'))
from game_runtime_support import DisplayStatus,GameLog,GpuRecoveryGuard

HINT=b'[2020-06-12 11:00:00.000] [warning] [glHint.cpp:23] glHint not implemented\n'
DRAW=b'[2020-06-12 11:00:00.000] [warning] [glDrawBuffer.cpp:23] glDrawBuffer not implemented\n'

class RuntimeSupportTests(unittest.TestCase):
    def test_failure_guard_requires_a_different_boot(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'guard.json'
            guard=GpuRecoveryGuard(path,boot_id='boot-one')
            guard.check()
            result={'reason':'process exited','exit_code':-6,'transport_errors':1,'after':{'status':3,'timeouts':0}}
            guard.mark('caught-timeout',result)
            with self.assertRaisesRegex(RuntimeError,'reboot'):guard.check()
            record=json.loads(path.read_text())
            self.assertEqual(record['transport_errors'],1)
            self.assertEqual(record['after']['status'],3)
            GpuRecoveryGuard(path,boot_id='boot-two').check()
            self.assertEqual(json.loads(path.read_text()),record)
    def test_repeated_advisories_do_not_hide_errors_or_metrics(self):
        source=HINT*20000+DRAW*3000+b'RIX_FRAME_METRICS frames=60 cpu_submit_fps=30\n'+b'dma-proxy ioctl errno=110\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'game.log'
            with GameLog(path) as log:log.attach(io.BytesIO(source))
            self.assertIsNone(log.failure)
            self.assertEqual(log.raw_bytes,len(source))
            self.assertEqual(log.advisories,{'glHint':20000,'glDrawBuffer':3000})
            self.assertEqual(log.errors['transport_errors'],1)
            self.assertEqual(path.read_bytes().count(b'glHint not implemented'),1)
            self.assertIn(b'RIX_FRAME_METRICS',path.read_bytes())
            self.assertLess(path.stat().st_size,512)

    def test_unique_overflow_is_drained_and_errors_crossing_chunks_count(self):
        needle=b'dma-proxy ioctl errno='
        prefix=b'x'*(64*1024-9)
        source=prefix+needle+b'110\n'+b'z\n'*150000+needle+b'5\n'+b'glClipPlane only GL_CLIP_PLANE0\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'game.log'
            with GameLog(path,limit=4096,tail_limit=1024) as log:log.attach(io.BytesIO(source))
            self.assertIsNone(log.failure)
            self.assertEqual(log.raw_bytes,len(source))
            self.assertEqual(log.errors,{'transport_errors':2,'unsupported_clip_warnings':1})
            self.assertEqual(path.stat().st_size,4096)
            self.assertEqual(path.with_name('game-tail.log').read_bytes(),source[-1024:])
            self.assertGreater(log.discarded,300000)

    def test_more_than_old_eight_mib_limit_through_real_pipe(self):
        # The child writes over twice the former abort threshold. An undrained
        # PIPE would deadlock well before exit; errors after overflow must survive.
        code="import sys;line="+repr(HINT)+";sys.stdout.buffer.write(line*250000+b'dma-proxy ioctl errno=110\\n');sys.stdout.flush()"
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'game.log'
            began=time.monotonic()
            with GameLog(path) as log:
                child=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                log.attach(child.stdout)
                self.assertEqual(child.wait(timeout=30),0)
            self.assertIsNone(log.failure)
            self.assertGreater(log.raw_bytes,16*1024*1024)
            self.assertEqual(log.advisories['glHint'],250000)
            self.assertEqual(log.errors['transport_errors'],1)
            self.assertLess(path.stat().st_size,256)
            print('PIPE_FLOOD_QA '+json.dumps({'raw_bytes':log.raw_bytes,'stored_bytes':log.written,'seconds':time.monotonic()-began}))

    def test_status_layout_and_fault_evidence(self):
        # Expected field positions come from the C struct, not the Python map.
        words=[0x52495801,0x9adb505e,7,1,101,102,103,104,105,11,12,13,14,15,106,107]
        raw=struct.pack('<16I',*words)
        status=DisplayStatus.__new__(DisplayStatus)
        status.fd=9;status.buffer=bytearray(64);status.reads=0
        def ioctl(fd,op,buffer,mutate):
            self.assertEqual((fd,op,len(buffer),mutate),(9,0x80405200,64,True))
            buffer[:]=raw
        status._ioctl=ioctl
        result=status.read()
        self.assertEqual(result['frame_id'],101)
        self.assertEqual(result['swap'],102)
        self.assertEqual(result['copy'],103)
        self.assertEqual(result['presented'],104)
        self.assertEqual(result['last_presented'],105)
        self.assertEqual([result[k] for k in ('read_errors','write_errors','timeouts','underflows','scan_errors')],[11,12,13,14,15])
        self.assertEqual(result['status'],7)
        self.assertEqual(result['gpu_busy_cycles'],107)
        raw=bytes(64)
        with self.assertRaises(RuntimeError):status.read()

if __name__=='__main__':unittest.main()
