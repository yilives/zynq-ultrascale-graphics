#!/usr/bin/env python3
"""Validate the separate RAM FSR launcher, normal exit and keyboard-mode SIGTERM."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

BASE=Path('/tmp/rix-fpga-fsr')
OUT=Path('/tmp/postproc-tests/classicube-fsr-v23-launcher')
LAUNCHER=Path('/tmp/rix-classicube-fsr-v23')
CANDIDATE='de86960c07507deabb08e79daf6c1adc99315564e041db772ab8152146d3cb13'
RUNTIME='94fc82f8e7aa5a123bc15151bfa13adb6362f8196d565132a18abbb61fbc5bb2'
QA_KEYS=('RIX_AUTOPLAY','RIX_GAMEPLAY_QA','RIX_INPUT_QA','RIX_CAPTURE','RIX_HOLD','RIX_SAVE','RIX_FLAT')


def require(ok,message):
    if not ok:raise RuntimeError(message)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def children(pid):
    result=[]
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit():continue
        try:
            status=folder.joinpath('status').read_text()
            parent=int(next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:')))
            if parent==pid:result.append(folder)
        except (OSError,StopIteration):continue
    return result


def game_env(pid):
    for folder in children(pid):
        try:
            if folder.joinpath('comm').read_text().strip()!='ClassiCube':continue
            env=dict(item.split(b'=',1) for item in folder.joinpath('environ').read_bytes().split(b'\0') if b'=' in item)
            return {key:env[key.encode()].decode() for key in QA_KEYS if key.encode() in env}
        except OSError:continue
    return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher-sha256',required=True)
    args=parser.parse_args()
    require(os.geteuid()==0,'Root required')
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    path=BASE/'test_fsr_pl_live_v23.py'
    require(sha(path)=='caa33ede32c9fb9709191fea7774bce99a0a7978679721b4f1ed62efb25a5eb8','Live helper differs')
    spec=importlib.util.spec_from_file_location('launcher_live',str(path));live=importlib.util.module_from_spec(spec);spec.loader.exec_module(live)
    live.OUT=OUT;q=live.helper()
    q.private_file(LAUNCHER)
    require(sha(LAUNCHER)==args.launcher_sha256,'Launcher SHA differs')
    require(sha(BASE/'ahead/rix-fsr-pl')==CANDIDATE,'FSR SHA differs')
    identity=q.receipt_identity(RUNTIME)
    require(not q.active_clients(),'Another GPU client is active')
    q.guard_space();q.private_file(live.PROFILE);options=live.PROFILE.read_bytes()
    OUT.mkdir(mode=0o700);(OUT/'options.before').write_bytes(options)
    record=dict(passed=False,format='rix-classicube-fsr-v23-launcher',identity=identity,
                launcher_sha256=args.launcher_sha256,candidate_sha256=CANDIDATE,
                script_sha256=sha(Path(__file__)),cases=[])
    game=None;log=None
    try:
        record['before']=q.snapshot('before')
        for mode in ('normal','keyboard-stop'):
            attempt='ccfsr23_'+mode.replace('-','_')
            folder=OUT.parent/attempt
            require(not folder.exists(),'Attempt exists')
            q.private_file(LAUNCHER);require(sha(LAUNCHER)==args.launcher_sha256,'Launcher changed')
            env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
            for key in QA_KEYS:env.pop(key,None)
            command=[str(LAUNCHER),'--seconds','22' if mode=='normal' else '30','--attempt',attempt]
            if mode=='normal':command.append('--autoplay')
            else:env.update({key:('1' if key in ('RIX_AUTOPLAY','RIX_GAMEPLAY_QA','RIX_FLAT') else '/tmp/rix-stale-'+key) for key in QA_KEYS})
            case=dict(mode=mode,attempt=attempt,command=command,passed=False);record['cases'].append(case)
            log=(OUT/(mode+'.log')).open('x')
            game=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env)
            case['pid']=game.pid
            def ready():
                require(game.poll() is None,'Launcher ended before FSR started')
                return (folder/'game.log').exists() and 'RIX_MEASURE_BEGIN' in (folder/'game.log').read_text(errors='replace') and (folder/'fsr-01.log').exists()
            live.wait_until(ready,60,'Game/FSR startup timeout')
            case['game_environment']=game_env(game.pid)
            require(case['game_environment']==({'RIX_AUTOPLAY':'1'} if mode=='normal' else {}),'Unexpected actual game QA environment')
            fsr_pids=[int(f.name) for f in children(game.pid) if f.joinpath('comm').read_text().strip()=='rix-fsr-pl']
            require(len(fsr_pids)==1,'Expected one FSR process');case['fsr_pid']=fsr_pids[0]
            if mode=='keyboard-stop':
                time.sleep(5)
                require(Path('/proc/%d'%fsr_pids[0]).exists() and game.poll() is None,'FSR/game ended before interruption')
                case['stop_signal']='SIGTERM';game.terminate()
            live.wait_until(lambda:game.poll() is not None,55,'Launcher failed to exit')
            case['launcher_exit']=game.returncode;log.close();log=None
            result=json.loads((folder/'result.json').read_text());case['game_result']=result
            require(result['fsr_drained'] and result['fsr_error'] is None and result['fsr_runs']>0 and result['fsr_completed_frames']>0,'No completed drained FSR output')
            require(result['fsr_runtime_sha256']==CANDIDATE and result['cpu_pixel_processing_live'] is False,'Wrong FSR runtime/backend')
            require(result['view_distance']==32 and result['world_size']==64,'Wrong default game settings')
            require(all(result['after'][key]==result['before'][key]==0 for key in q.ERRORS),'GPU fault')
            if mode=='normal':require(game.returncode==0 and result['passed'] and result['metrics'],'Normal game did not complete')
            else:
                case['expected_interruption']=True
                if result['metrics']:require(not result['metrics'].get('autoplay',False),'Unexpected autoplay metrics')
            case['after']=q.snapshot(mode+'-after')
            require(case['after']['post']['active']==1 and case['after']['post']['snapshot_status']==0 and case['after']['post']['snapshot_expirations']==0,'Display/lease not restored')
            require(not q.active_clients() and not live.QUARANTINE.exists(),'Client/FSR quarantine remains')
            for path in sorted(folder.iterdir()):
                if path.suffix in ('.log','.json'):(OUT/(mode+'-'+path.name)).write_bytes(path.read_bytes())
            case['passed']=True;game=None
        record['passed']=True
    except Exception as exc:record['error']=repr(exc)
    finally:
        try:
            if game is not None and game.poll() is None:
                game.terminate()
                live.wait_until(lambda:game.poll() is not None,35,'Launcher retains ownership; reset required')
            require(not q.active_clients() and not live.QUARANTINE.exists(),'Live/quarantined client prevents restoration')
            require(q.receipt_identity(RUNTIME)==identity,'Load identity changed')
            q.private_file(live.PROFILE);live.PROFILE.write_bytes(options)
            record['profile_restored']=live.PROFILE.read_bytes()==options
            require(record['profile_restored'],'Profile restoration failed')
            record['after']=q.snapshot('after');record['spaces']=q.guard_space()
            require(record['after']['post']['active']==1 and record['after']['post']['snapshot_status']==0 and record['after']['post']['snapshot_expirations']==0,'Final display/lease state wrong')
        except Exception as exc:record['passed']=False;record['cleanup_error']=repr(exc)
        if log is not None:log.close()
        (OUT/'launcher.py').write_bytes(LAUNCHER.read_bytes())
        (OUT/'helper.py').write_bytes(Path(__file__).read_bytes())
        q.exclusive_json(OUT/'result.json',record)
        archive=OUT.parent/'classicube-fsr-v23-launcher-evidence.tar.gz'
        with archive.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as tar:
            for path in sorted(OUT.iterdir()):
                if path.is_file():tar.add(str(path),arcname=path.name,recursive=False)
        print(json.dumps(dict(passed=record['passed'],error=record.get('error'),cleanup_error=record.get('cleanup_error'),
              archive=str(archive),bytes=archive.stat().st_size,archive_sha256=sha(archive),
              cases=[dict(mode=c['mode'],passed=c['passed'],launcher_exit=c.get('launcher_exit'),
                          fsr_frames=c.get('game_result',{}).get('fsr_completed_frames')) for c in record['cases']])),flush=True)
    raise SystemExit(0 if record['passed'] else 1)


if __name__=='__main__':main()
