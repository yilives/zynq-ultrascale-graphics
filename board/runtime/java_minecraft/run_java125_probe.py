#!/usr/bin/env python3
"""Bounded isolated JVM/LWJGL/client attempt using the real private RasterIX GL."""
import fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import DisplayStatus,GameLog,GpuRecoveryGuard
BASE=Path('/tmp/rix-java125');JRE=BASE/'zulu8.98.0.107-ca-jre8.0.512-linux_aarch64'
GL=Path('/tmp/rasterix-classicube/ffa912210b7c/lib')
CLIENTS=('tuxracer','rix-smoke','neverball','neverputt','quake3e','quakespasm','rix-glx-probe',
         'rix-danmaku','rix-superres','rix-neural-style','th06-rix','ClassiCube','rix-fsr-pl','java')
ERRORS=('read_errors','write_errors','timeouts','underflows','scan_errors')
QUEUES=('frame_id','swap','copy','presented','last_presented')
def main():
    mode=sys.argv[1];assert mode in ('sys','display','client','client-clean')
    attempt=BASE/('result-'+mode);attempt.mkdir()
    with open('/tmp/rasterix-game-launch.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        guard=GpuRecoveryGuard();guard.check()
        p=subprocess.run(['pidof',*CLIENTS],stdout=subprocess.PIPE)
        assert p.returncode==1 and not p.stdout,'Another game/Java/postprocessor is active'
        gpu=DisplayStatus();before=gpu.read()
        assert before['status']==3 and all(before[k]==0 for k in ERRORS) and len({before[k] for k in QUEUES})==1
        gl_hash=hashlib.sha256((GL/'libGL.so.1').read_bytes()).hexdigest()
        assert gl_hash=='452bbd3d09c94e4c68906475a3432a03e39e92ebede93bd0e3eb546fbc9bf739'
        env=os.environ.copy()
        env.update(DISPLAY=':0',HOME=str(BASE/'home'),LD_LIBRARY_PATH=':'.join(map(str,[
            GL,BASE/'native',BASE/'native/deps',JRE/'lib/aarch64',JRE/'lib/aarch64/server'])))
        home=BASE/'home';home.mkdir(exist_ok=True)
        game=home/'.minecraft';game.mkdir(exist_ok=True)
        options=game/'options.txt'
        if not options.exists():
            options.write_text('music:0.0\nsound:0.0\nrenderDistance:3\nfancyGraphics:false\nambientOcclusion:false\nadvancedOpengl:false\nviewBobbing:false\nfpsLimit:1\n')
        command=[str(JRE/'bin/java'),'-Xms64m','-Xmx512m','-XX:+UseSerialGC',
            '-Duser.home='+str(home),'-Djava.awt.headless=false','-Dsun.java2d.opengl=false',
            '-Dsun.java2d.xrender=false','-Dorg.lwjgl.util.Debug=true',
            '-Dorg.lwjgl.librarypath='+str(BASE/'native'),
            '-cp',str(BASE/'probe')+':'+str(BASE/'libs/*')]
        if mode=='client':command+=['net.minecraft.client.Minecraft']
        elif mode=='client-clean':command+=['Java125ClientHarness']
        else:command+=['Java125Probe',mode]
        start=time.monotonic();expired=False
        with GameLog(attempt/'stdout.log') as log:
            process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,cwd=game)
            log.attach(process.stdout)
            try:
                code=process.wait(timeout=45 if mode.startswith('client') else 25)
            except subprocess.TimeoutExpired:
                expired=True
                process.terminate()
                try:code=process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill();code=process.wait(timeout=5)
        deadline=time.monotonic()+5
        while True:
            after=gpu.read()
            if len({after[k] for k in QUEUES})==1 or time.monotonic()>=deadline:break
            time.sleep(.1)
        text=(attempt/'stdout.log').read_text(errors='replace')
        unsafe=any(after[k]!=before[k] for k in ERRORS) or len({after[k] for k in QUEUES})!=1 or log.errors['transport_errors']>0
        # An interrupted GPU client also requires explicit recovery even if counters look idle.
        if expired and after['command_beats']!=before['command_beats']:unsafe=True
        result=dict(mode=mode,exit_code=code,expired=expired,seconds=time.monotonic()-start,
            before=before,after=after,gl_sha256=gl_hash,command=command,environment=env,
            transport_errors=log.errors['transport_errors'],reason='unsafe GPU termination/errors' if unsafe else 'clean exit',
            probe_pass='JAVA125_PROBE_PASS' in text,gameplay_verified=False,
            normal_close_requested='JAVA125_NORMAL_CLOSE_REQUEST' in text,
            texture_too_big='glTexImage2D texture is too big.' in text,
            log=log.stats(),scope='Official client 1.2.5, ARM64 JVM, real RasterIX; no FPS claim')
        # Keep only the explicit runtime variables; never capture inherited credentials.
        result['environment']={k:env[k] for k in ('DISPLAY','HOME','LD_LIBRARY_PATH')}
        if unsafe:guard.mark('minecraft-java125-'+mode,result)
        (attempt/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print('JAVA125_RESULT',json.dumps({k:result[k] for k in ('mode','exit_code','expired','seconds','probe_pass','reason')}),flush=True)
        print(text[-6000:],flush=True)
        assert not unsafe,'GPU recovery guard set; stop further tests'
if __name__=='__main__':main()
