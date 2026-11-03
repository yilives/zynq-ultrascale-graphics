#!/usr/bin/env python3
"""Read-only CPU IP sampling of the accepted view32/FPGA-FSR game."""
import hashlib,json,os,subprocess,sys,tarfile,time
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
import rasterix_games as games
OUT=Path('/tmp/postproc-tests/cc-prof-v25')
PROFILE=Path('/opt/rasterix/classicube/profile/options.txt')
SAMPLER=Path('/tmp/rix-perf-sample-v25')
LAUNCHER=Path('/tmp/rix-classicube-fsr-v23')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert os.geteuid()==0
    os.umask(0o077)
    assert sha(SAMPLER)=='39885914b5568a9d5348496d69e9bd5f2678bc5ad3322b9c556d6a9fc94a01d5'
    assert sha(LAUNCHER)=='b33a60e7162ee2b4358ce14fa30a87763c290bad4243be4f5d478dc6045ae65f'
    assert not subprocess.run(['pidof',*games.CLIENTS,'ClassiCube','rix-fsr-pl'],stdout=subprocess.PIPE).stdout
    options=PROFILE.read_bytes();OUT.mkdir(mode=0o700);(OUT/'options.before').write_bytes(options)
    record=dict(passed=False,script_sha256=sha(Path(__file__)),sampler_sha256=sha(SAMPLER),launcher_sha256=sha(LAUNCHER),
                before=games.status(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                measurement_limit='CPU sampling has overhead; FPS during this run is not a performance comparison')
    game=None;sampler=None
    attempt=Path('/tmp/postproc-tests/cc_prof_v25')
    try:
        with (OUT/'launcher.log').open('x') as log:
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            game=subprocess.Popen([str(LAUNCHER),'--seconds','140','--view-distance','32','--autoplay','--attempt',attempt.name],stdout=log,stderr=subprocess.STDOUT,env=env)
            deadline=time.monotonic()+60
            while not ((attempt/'game.log').exists() and 'RIX_MEASURE_BEGIN' in (attempt/'game.log').read_text(errors='replace') and (attempt/'fsr-01.log').exists()):
                assert game.poll() is None and time.monotonic()<deadline,'Game startup failed'
                time.sleep(.1)
            parents=[]
            for folder in Path('/proc').iterdir():
                if not folder.name.isdigit():continue
                try:
                    if folder.joinpath('comm').read_text().strip()!='ClassiCube':continue
                    status=folder.joinpath('status').read_text()
                    ppid=int(next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:')))
                    if ppid==game.pid:parents.append(folder)
                except OSError:continue
            assert len(parents)==1
            process=parents[0];tids=sorted(int(p.name) for p in (process/'task').iterdir())[:3]
            assert len(tids)==3
            record.update(game_pid=int(process.name),tids=tids)
            (OUT/'maps-before.txt').write_bytes((process/'maps').read_bytes())
            with (OUT/'sampler.log').open('x') as log:
                sampler=subprocess.Popen([str(SAMPLER),'120',str(OUT/'ip.json'),*map(str,tids)],stdout=log,stderr=subprocess.STDOUT)
                sampler.wait(timeout=130)
            record['sampler_exit']=sampler.returncode
            record['profile']=json.loads((OUT/'ip.json').read_text())
            record['profile_valid']=record['profile']['passed']
            if process.exists():(OUT/'maps-after.txt').write_bytes((process/'maps').read_bytes())
            game.wait(timeout=45)
            record['game_result']=json.loads((attempt/'result.json').read_text())
            assert game.returncode==0 and record['game_result']['passed']
            assert record['game_result']['graphics_sha256']=='452bbd3d09c94e4c68906475a3432a03e39e92ebede93bd0e3eb546fbc9bf739'
            record['passed']=record['profile_valid']
    except Exception as exc:record['error']=repr(exc)
    finally:
        try:
            if sampler is not None and sampler.poll() is None:
                sampler.terminate();sampler.wait(timeout=10) # CPU-only sampler has no FPGA ownership.
            if game is not None and game.poll() is None:
                game.terminate();game.wait(timeout=35) # Accepted wrapper drains FSR before renderer.
            assert not subprocess.run(['pidof',*games.CLIENTS,'ClassiCube','rix-fsr-pl'],stdout=subprocess.PIPE).stdout
            assert not Path('/tmp/rix-fsr-pl.quarantine').exists()
            PROFILE.write_bytes(options);record['profile_restored']=PROFILE.read_bytes()==options
            record['after']=games.status()
            assert all(record['after'][k]==record['before'][k]==0 for k in games.ERRORS)
            assert len({record['after'][k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
        except Exception as exc:record['passed']=False;record['cleanup_error']=repr(exc)
        (OUT/'helper.py').write_bytes(Path(__file__).read_bytes())
        (OUT/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        archive=OUT.parent/'cc-prof-v25-evidence.tar.gz'
        with archive.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as tar:
            for path in sorted(OUT.iterdir()):
                if path.is_file():tar.add(str(path),arcname=path.name,recursive=False)
            if (attempt/'game.log').exists():tar.add(str(attempt/'game.log'),arcname='game.log',recursive=False)
        print(json.dumps(dict(passed=record['passed'],error=record.get('error'),cleanup_error=record.get('cleanup_error'),
            samples=record.get('profile',{}).get('samples'),archive=str(archive),bytes=archive.stat().st_size,archive_sha256=sha(archive))),flush=True)
    raise SystemExit(0 if record['passed'] else 1)

if __name__=='__main__':main()
