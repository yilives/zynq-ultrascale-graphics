#!/usr/bin/env python3
"""Validate actual GPU pixels and the GLX/VBO interface under both private GLs."""
import fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
import rasterix_games as games
from game_runtime_support import GpuRecoveryGuard

OUT=Path('/tmp/postproc-tests/cc-tune-v25-glx')
TUNED_SHA='9b31fd0aa187b05a3df5efae32a764ad56da88bda723d8ed8dc394ff9b692fc1'
BASE_SHA='452bbd3d09c94e4c68906475a3432a03e39e92ebede93bd0e3eb546fbc9bf739'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert os.geteuid()==0
    lock=open('/tmp/rasterix-game-launch.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    guard=GpuRecoveryGuard();guard.check()
    assert not subprocess.run(['pidof',*games.CLIENTS,'ClassiCube','rix-fsr-pl'],stdout=subprocess.PIPE).stdout
    games.prepare(['game-runtime'])
    receipt=json.loads(Path('/opt/rasterix/experimental/cache/classicube.json').read_text())
    work=Path('/tmp/rasterix-classicube')/receipt['sha256'][:12]
    original=work/'lib/libGL.so.1';tuned=Path('/tmp/rix-cc-tune-v25/libGL.so.1')
    assert sha(original)==BASE_SHA and sha(tuned)==TUNED_SHA
    OUT.mkdir(mode=0o700)
    before=games.status();cases=[];child=None;failure=None
    try:
        for mode,lib in (('baseline',original),('tuned',tuned)):
            env=os.environ.copy();env.update(DISPLAY=':0',SDL_VIDEODRIVER='x11',SDL_AUDIODRIVER='dummy',LANG='C',LC_ALL='C',
                SDL_VIDEO_GL_DRIVER=str(lib),LD_LIBRARY_PATH=str(lib.parent)+':'+str(games.WORK/'runtime/lib'),RIX_PRESENT_STRATEGY='async',RIX_PRESENT_SYNC='1')
            for key in ('RIX_FRAME_METRICS','RIX_PACKED_FETCH_VERIFY'):env.pop(key,None)
            exe=games.WORK/'runtime/bin/rix-glx-probe'
            with (OUT/(mode+'.log')).open('x') as log:
                child=subprocess.Popen([str(exe)],stdout=log,stderr=subprocess.STDOUT,env=env)
                try:child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    guard.mark('cc_tune_v25_glx',{'reason':'GLX test retains a live GPU process; no forced kill','pid':child.pid})
                    raise
            text=(OUT/(mode+'.log')).read_text()
            assert child.returncode==0 and 'RIX_GLX_SIX_CLIP_PLANES pixels=9246 failures=0' in text and 'RIX_GLX_PROBE_DRAW_PASS' in text,text
            after=games.status()
            assert all(after[k]==before[k]==0 for k in games.ERRORS)
            assert len({after[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
            cases.append(dict(mode=mode,passed=True,graphics_sha256=sha(lib),probe_sha256=sha(exe),gpu=after,pixels=9246))
            child=None
    except Exception as exc:failure=repr(exc)
    record=dict(passed=failure is None,error=failure,cases=cases,before=before,after=games.status(),script_sha256=sha(Path(__file__)))
    (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    raise SystemExit(0 if record['passed'] else 1)

if __name__=='__main__':main()
