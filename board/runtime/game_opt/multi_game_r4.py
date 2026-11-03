"""RAM-only per-game pacing trials and CNN/PL-FSR integration checks."""
import hashlib,json,os,shutil,struct,subprocess,sys,tarfile,time
from pathlib import Path

from cfs_pipe_r3_tasks import guarded_adapter,run_fixed

STANDARD=('tuxracer','neverball','neverputt','quake','quake3')
GAMES=STANDARD+('touhou','classicube')
TITLES=dict(zip(STANDARD,('Tuxracer','Neverball','Neverputt','Quakespasm','Quake3e')))


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):Path(p).write_text(json.dumps(value,indent=2)+'\n')
def cpu(pid):
    try:
        fields=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
        return (int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
    except FileNotFoundError:return None


def prepare(game,home,variant,games,out):
    home.mkdir(mode=0o700)
    env={k:v for k,v in os.environ.items() if not k.startswith(('RIX_','TH06_','LD_PRELOAD','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS'))}
    env.update(DISPLAY=':0',HOME=str(home),LANG='C',LC_ALL='C',SDL_VIDEODRIVER='x11',SDL_AUDIODRIVER='dummy',RIX_FRAME_METRICS='1')
    runtime=games.WORK/'runtime';env['LD_LIBRARY_PATH']=str(runtime/'lib');env['SDL_VIDEO_GL_DRIVER']=str(runtime/'lib/libGL.so.1')
    if game in STANDARD:
        packages=['game-runtime']+([] if game=='tuxracer' else ['neverball-data' if game.startswith('never') else game+'-data'])
        games.prepare(packages)
        # Only private profiles are changed; user controls and saves are untouched.
        original=Path('/opt/rasterix/experimental/profiles')/game
        for name in ('.neverball/neverballrc','.neverball-dev/neverballrc','.tuxracer/options'):
            source=original/name;target=home/name
            if source.is_file():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        args=games.command(game,home,tuning='legacy' if game=='neverputt' else 'balanced')
        if game=='tuxracer':env['LD_LIBRARY_PATH']='/usr/lib'
        if game=='quake3':env['RIX_PRESENT_STRATEGY']='async'
        if variant=='candidate':
            if game in ('neverball','neverputt','quake'):env['RIX_PRESENT_STRATEGY']='async'
            if game=='tuxracer':env['RIX_PRESENT_STRATEGY']='pipeline'
            if game=='quake3':
                index=args.index('com_maxfps');assert args[index+1]=='30';args[index+1]='60'
        return args,env,games.WORK
    if game=='touhou':
        base=Path('/opt/rasterix/touhou');runtime=base/'th06-runtime'
        contract=json.loads(Path('/tmp/rasterix-launcher-v3-native/game-contracts.json').read_text())['touhou']
        for name,digest in contract.items():assert sha(base/name)==digest,name
        for source in (base/'th06-demo').iterdir():
            if source.is_file():(home/source.name).symlink_to(source)
        env.update(LD_LIBRARY_PATH=str(runtime/'lib'),TH06_TEXTURE_MODE='balanced',TH06_TOUCH='1',TH06_AUTOPLAY='1')
        return [str(runtime/'bin/th06-rix')],env,home
    # Verify the existing isolated ClassiCube payload, never overwrite a user world.
    cache=Path('/opt/rasterix/experimental/cache');receipt=json.loads((cache/'classicube.json').read_text())
    assert receipt['verified'];archive=cache/'classicube.tar.gz';assert sha(archive)==receipt['sha256']
    work=Path('/tmp/rasterix-classicube')/receipt['sha256'][:12]
    if not (work/'manifest.json').is_file():
        work=out/'classicube-assets'
        if not (work/'manifest.json').is_file():
            work.mkdir(mode=0o700)
            with tarfile.open(archive) as source:
                members=source.getmembers();assert len(members)==len({m.name for m in members})
                manifest=json.load(source.extractfile('classicube/manifest.json'))
                assert {m.name for m in members}=={'classicube/'+n for n in manifest}|{'classicube/manifest.json'}
                for member in members:
                    name=Path(member.name);assert member.isfile() and name.parts[0]=='classicube' and '..' not in name.parts and not name.is_absolute()
                    target=work.joinpath(*name.parts[1:]);target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(source.extractfile(member).read());target.chmod(0o700 if name.parts[1]=='bin' else 0o600)
    manifest=json.loads((work/'manifest.json').read_text())
    for name,entry in manifest.items():assert sha(work/name)==entry['sha256'],name
    for name in ('texpacks','maps','home'):(home/name).mkdir()
    (home/'texpacks/default.zip').symlink_to(work/'data/default.zip')
    original=Path('/opt/rasterix/classicube/profile/options.txt')
    values=dict(row.split('=',1) for row in original.read_text().splitlines() if '=' in row) if original.exists() else {}
    values.update({'window-width':'400','window-height':'240','viewdist':'32','musicvolume':'0','soundsvolume':'0',
        'fpslimit':'Limit60FPS' if variant=='candidate' else 'Limit120FPS','auto-pause':'False','usebitmapfont':'True',
        'gfx-mipmaps':'False','gfx-smoothlighting':'False','entityshadow':'None','chat-logging':'False','gfx-maxchunkupdates':'2','win-raw-input':'False'})
    (home/'options.txt').write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    env.update(HOME=str(home/'home'),LD_LIBRARY_PATH=str(work/'lib')+':'+str(runtime/'lib'),SDL_VIDEO_GL_DRIVER=str(work/'lib/libGL.so.1'),
        RIX_SECONDS='0',RIX_WORLD_SIZE='64',RIX_AUTOPLAY='1',RIX_PACKED_FETCH='1',RIX_PRESENT_STRATEGY='async',RIX_PRESENT_SYNC='1')
    return [str(work/'bin/ClassiCube'),'--singleplayer'],env,home


def run_live(adapter,stage,out,selected_style,seconds):
    out.mkdir();sys.path.insert(0,'/opt/rasterix/experimental')
    import rasterix_games as games
    from game_runtime_support import DisplayStatus,GameLog,GpuRecoveryGuard
    GpuRecoveryGuard().check();status=DisplayStatus();result=dict(passed=False,games={},source_only=True)
    nn=None
    def healthy():
        value=status.read();assert value['status']==3 and all(value[k]==0 for k in games.ERRORS),value
        return value
    def pause(duration,game,log):
        until=time.monotonic()+duration
        while time.monotonic()<until:
            assert game.poll() is None,'Game exited during measurement'
            assert not log.failure and not log.errors['transport_errors'],'Game transport/log error'
            healthy();time.sleep(.1)
    def close(game,name,env,log,folder):
        if game.poll() is None:
            if name in TITLES:
                deadline=time.monotonic()+20
                while game.poll() is None:
                    p=subprocess.run([sys.executable,'/opt/rasterix/experimental/game_x11_control.py','close','--window',TITLES[name]],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=5)
                    with (folder/'close.log').open('ab') as stream:stream.write(p.stdout)
                    if p.returncode==0:break
                    assert time.monotonic()<deadline,'Window did not become ready for normal close';time.sleep(.1)
            else:game.terminate()
            game.wait(timeout=20)
        log.finish();assert game.returncode==0,'Game did not drain normally'
        assert not log.failure and not log.errors['transport_errors']
        deadline=time.monotonic()+5
        while True:
            value=healthy()
            if len({value[k] for k in ('frame_id','swap','copy','presented','last_presented')})==1:return value
            assert time.monotonic()<deadline,'GPU did not drain';time.sleep(.05)
    def launch(name,variant,label):
        folder=out/label;folder.mkdir(mode=0o700)
        args,env,cwd=prepare(name,folder/'home',variant,games,out)
        deps=subprocess.run(['/lib/ld-linux-aarch64.so.1','--list',args[0]],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15)
        (folder/'dependencies.log').write_bytes(deps.stdout);assert deps.returncode==0,deps.stdout
        save(folder/'launch.json',dict(command=args,environment=env,cwd=str(cwd),binary_sha256=sha(args[0]),variant=variant))
        log=GameLog(folder/'game.log');before=healthy()
        game=subprocess.Popen(args,env=env,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        adapter.managed.append(game);log.attach(game.stdout)
        try:
            deadline=time.monotonic()+60
            while healthy()['presented']<before['presented']+3:
                assert game.poll() is None and time.monotonic()<deadline,'No source frames'
                assert not log.failure and not log.errors['transport_errors'];time.sleep(.1)
            pause(6 if name=='tuxracer' else (8 if name in ('touhou','classicube') else 2),game,log)
            if name=='tuxracer':
                for key in ('Return','p','Return'):
                    p=subprocess.run([sys.executable,'/opt/rasterix/experimental/game_x11_control.py','key',key,'--window',TITLES[name]],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=5)
                    assert p.returncode==0,p.stdout;pause(.8,game,log)
                pause(2,game,log)
            return game,log,env,folder
        except BaseException:close(game,name,env,log,folder);raise
    def measure(game,log,duration):
        before=healthy();began=time.monotonic();c0=cpu(game.pid);pause(duration,game,log);ended=time.monotonic();after=healthy();c1=cpu(game.pid)
        n=(after['presented']-before['presented'])&0xffffffff;elapsed=ended-began
        return dict(frames=n,seconds=elapsed,fps=n/elapsed,CPU_seconds=c1-c0,CPU_percent=100*(c1-c0)/elapsed,
                    command_beats_per_frame=((after['command_beats']-before['command_beats'])&0xffffffff)/n,
                    GPU_busy_ms_per_frame=((after['gpu_busy_cycles']-before['gpu_busy_cycles'])&0xffffffff)/100000/n,before=before,after=after)
    try:
        with adapter.lend_post():
            for name in GAMES:
                record=dict(source=[],neural={},selected_profile='baseline');result['games'][name]=record
                variants=('baseline','candidate','candidate','baseline') if name!='touhou' else ('baseline',)
                for i,variant in enumerate(variants):
                    game,log,env,folder=launch(name,variant,name+'-source-'+str(i))
                    try:
                        measured=measure(game,log,seconds)
                        record['source'].append(dict(variant=variant,metrics=measured,folder=folder.name))
                        save(folder/'source.json',measured)
                    finally:close(game,name,env,log,folder)
                    save(out/'progress.json',result);print('MULTIGAME_SOURCE',name,variant,measured['fps'],flush=True)
                def average(variant):
                    rows=[r['metrics'] for r in record['source'] if r['variant']==variant]
                    return sum(r['frames'] for r in rows)/sum(r['seconds'] for r in rows)
                record['source_baseline_fps']=average('baseline')
                if name!='touhou':
                    record['source_candidate_fps']=average('candidate')
                    if record['source_candidate_fps']>record['source_baseline_fps']*1.03:record['selected_profile']='candidate'
                # Same game process and source settings for the NN ABBA.
                game,log,env,folder=launch(name,record['selected_profile'],name+'-neural')
                try:
                    record['source_before_neural']=measure(game,log,3)
                    schedule=[('a1','rix-cfs-early'),('b1','rix-cfs-poll'),('b2','rix-cfs-poll'),('a2','rix-cfs-early')]
                    for label,binary in schedule:
                        prefix=folder/label;initial=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                        deadline=time.monotonic()+2
                        while initial['requested']!=initial['active']:
                            assert time.monotonic()<deadline;time.sleep(.01)
                            initial=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                        save(str(prefix)+'.post-initial.json',initial)
                        args=[str(stage/binary),'--backend','pl-int8','--model',str(stage/'cfs-comic.cnn'),
                            '--live','--seconds',str(seconds),'--composition','neural-fsr','--upscaler','pl-fsr','--detail-gain','192',
                            '--pio-output','group','--core-wait','sleep','--frame-pipeline','overlap','--fsr-schedule','pipeline',
                            '--hold-last-seconds','10','--dump-prefix',str(prefix),'--dump-last']
                        if binary=='rix-cfs-poll':args+=['--fsr-notify','cnn-output']
                        with (folder/(label+'.log')).open('xb') as stream:nn=subprocess.Popen(args,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                        adapter.managed.append(nn);deadline=time.monotonic()+seconds+30
                        while 'NEURAL_OUTPUT_HELD' not in (folder/(label+'.log')).read_text():
                            assert nn.poll() is None and time.monotonic()<deadline,(folder/(label+'.log')).read_text()[-1200:]
                            assert not log.failure and not log.errors['transport_errors'];healthy();time.sleep(.05)
                        text=(folder/(label+'.log')).read_text();metrics=[json.loads(row) for row in text.splitlines() if row.startswith('{')][-1]
                        assert metrics['FSR_enabled'] and metrics['engine_version']==4 and metrics['cnn_cycles_per_frame']==462816
                        assert metrics['fsr_launched']==metrics['fsr_completed']==metrics['present_submitted_frames']==metrics['present_completed_frames']==metrics['processed_frames']>0
                        assert 'NEURAL_DISPLAY_READBACK_PASS bytes=1536000' in text
                        subprocess.run([games.POST,'--capture',str(prefix)+'.lcd.bin'],stdout=subprocess.PIPE,check=True,timeout=5)
                        post=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                        deadline=time.monotonic()+2
                        while post['snapshot_status']&3:
                            assert time.monotonic()<deadline and nn.poll() is None;time.sleep(.01)
                            post=json.loads(subprocess.check_output([games.POST,'--status'],text=True,timeout=5))
                        expected=2|(((((initial['active']>>9)&1)^(metrics['processed_frames']&1)))<<9)
                        assert post['requested']==post['active']==expected and post['snapshot_expirations']==0
                        save(str(prefix)+'.post-final.json',post)
                        cpu_run=subprocess.run([str(stage/'rix-cfs-poll'),'--backend','cpu-int8','--model',str(stage/'cfs-comic.cnn'),
                            '--input',str(prefix)+'.input.bin','--output',str(prefix)+'.cpu.bin'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
                        assert cpu_run.returncode==0,cpu_run.stdout
                        assert Path(str(prefix)+'.cpu.bin').read_bytes()==Path(str(prefix)+'.output.bin').read_bytes()
                        words=struct.unpack('<384000I',Path(str(prefix)+'.display.bin').read_bytes());capture=struct.unpack('<6000H',Path(str(prefix)+'.lcd.bin').read_bytes())
                        expected_samples=[((words[y*800+x]>>8)&0xf800)|((words[y*800+x]>>5)&0x7e0)|((words[y*800+x]>>3)&31) for y in range(0,480,8) for x in range(0,800,8)]
                        assert expected_samples==list(capture),'LCD sample mismatch'
                        nn.terminate();assert nn.wait(timeout=15)==0
                        record['neural'][label]=dict(binary=binary,metrics=metrics,prefix=prefix.relative_to(out).as_posix(),LCD_samples=6000,LCD_mismatches=0,CPU_integer_exact=True)
                        save(out/'progress.json',result);print('MULTIGAME_NEURAL',name,label,metrics['processed_fps'],flush=True)
                finally:
                    if nn is not None and nn.poll() is None:nn.terminate();nn.wait(timeout=15)
                    close(game,name,env,log,folder)
                record['passed']=len(record['neural'])==4
                save(out/'progress.json',result)
        result['passed']=len(result['games'])==len(GAMES) and all(r.get('passed') for r in result['games'].values())
        result['source_only']=False;save(out/'result.json',result);return result
    finally:status.close()
