"""Execute the actual launcher lifecycle blocks with faulting subprocess fixtures."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'linux/classicube/rix-classicube-fsr-v23'
TREE=ast.parse(SOURCE.read_text())


def run_nodes(nodes, env):
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(SOURCE),'exec'),env)


class Process:
    pid=123
    def __init__(self, waits, active=True):
        self.waits=list(waits);self.returncode=None if active else 0;self.terminated=0
    def poll(self):return self.returncode
    def terminate(self):self.terminated+=1
    def wait(self,timeout):
        value=self.waits.pop(0)
        if value=='timeout':raise subprocess.TimeoutExpired('fixture',timeout)
        self.returncode=value
        return value


class Lifecycle(unittest.TestCase):
    def test_no_forced_kill(self):
        calls=[n for n in ast.walk(TREE) if isinstance(n,ast.Call)]
        self.assertFalse(any(isinstance(n.func,ast.Attribute) and n.func.attr=='kill' for n in calls))
        for n in calls:
            if isinstance(n.func,ast.Attribute) and n.func.attr=='run':
                self.assertFalse(any(k.arg=='timeout' for k in n.keywords))

    def preflight(self, waits):
        child=Process(waits)
        start=next(i for i,n in enumerate(TREE.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='fsr_preflight' for t in n.targets))
        env=dict(subprocess=types.SimpleNamespace(Popen=lambda args:child,TimeoutExpired=subprocess.TimeoutExpired),fsr_path='fixture',sys=types.SimpleNamespace(stderr=None))
        return child,env,TREE.body[start:start+2]

    def test_preflight_success(self):
        child,env,nodes=self.preflight([0]);run_nodes(nodes,env);self.assertEqual(child.terminated,0)

    def test_preflight_nonzero(self):
        child,env,nodes=self.preflight([2])
        with self.assertRaises(AssertionError):run_nodes(nodes,env)
        self.assertEqual(child.terminated,0)

    def test_preflight_timeout_drains(self):
        child,env,nodes=self.preflight(['timeout',0])
        with self.assertRaises(subprocess.TimeoutExpired):run_nodes(nodes,env)
        self.assertEqual(child.terminated,1);self.assertEqual(child.poll(),0)

    def test_preflight_quarantine_retains_process(self):
        child,env,nodes=self.preflight(['timeout','timeout'])
        with self.assertRaises(subprocess.TimeoutExpired):run_nodes(nodes,env)
        self.assertEqual(child.terminated,1);self.assertIsNone(child.poll())

    def stop(self, waits, quarantine=False):
        child=Process(waits)
        log=types.SimpleNamespace(closed=False)
        log.close=lambda:setattr(log,'closed',True)
        env=dict(fsr_child=child,fsr_log=log,fsr_failure=None,Path=lambda p:types.SimpleNamespace(exists=lambda:quarantine))
        node=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='stop_fsr')
        run_nodes([node],env)
        return child,log,env,env['stop_fsr']()

    def test_stop_success(self):
        child,log,env,passed=self.stop([0]);self.assertTrue(passed);self.assertTrue(log.closed)

    def test_stop_failure(self):
        child,log,env,passed=self.stop([2]);self.assertFalse(passed);self.assertTrue(log.closed)

    def test_stop_quarantine(self):
        child,log,env,passed=self.stop([0],True);self.assertFalse(passed);self.assertIn('quarantined',env['fsr_failure'])

    def test_stop_retains_active_log(self):
        child,log,env,passed=self.stop(['timeout']);self.assertFalse(passed);self.assertFalse(log.closed);self.assertIsNone(child.poll())

    def test_inherited_qa_environment_removed(self):
        keys=('RIX_AUTOPLAY','RIX_GAMEPLAY_QA','RIX_INPUT_QA','RIX_CAPTURE','RIX_HOLD','RIX_SAVE','RIX_FLAT')
        node=next(n for n in TREE.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='key')
        env=dict(env={k:'stale' for k in keys});run_nodes([node],env);self.assertEqual(env['env'],{})

    def evidence(self,frames=3,runs=1):
        stats=dict(backend='FPGA PL EASU12 + RCAS5 fixed point',cpu_pixel_processing_live=False,frames=frames,
                   elapsed_seconds=1.0,unique_source_frames=frames,repeated_source_frames=0,prefetch_lease_expirations=0,
                   duplicate_snapshot_retries=0,snapshot_retries=0,ack_timestamps_us=[10,20,30])
        path=types.SimpleNamespace(read_text=lambda:json.dumps(stats),name='fsr-01.log')
        env=dict(fsr_drained=True,fsr_runs=runs,out=types.SimpleNamespace(glob=lambda pattern:[path]),json=json,failure=None)
        start=next(i for i,n in enumerate(TREE.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='fsr_stats' for t in n.targets))
        end=next(i for i in range(start,len(TREE.body)) if isinstance(TREE.body[i],ast.Assign) and any(isinstance(t,ast.Name) and t.id=='after' for t in TREE.body[i].targets))
        run_nodes(TREE.body[start:end],env)
        return env

    def test_completed_fsr_evidence(self):
        env=self.evidence();self.assertIsNone(env['failure']);self.assertEqual(env['fsr_completed_frames'],3)
        self.assertNotIn('ack_timestamps_us',env['fsr_stats'][0])

    def test_no_fsr_frames_rejected(self):
        self.assertIn('FSR evidence',self.evidence(frames=0)['failure'])

    def test_missing_fsr_run_rejected(self):
        self.assertIn('FSR evidence',self.evidence(runs=2)['failure'])


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Lifecycle)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    out=ROOT/'build/fsr-pl/fixed-v23-bufferedread/launcher-host-result.json'
    out.write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,launcher_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest()),indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
