"""Temporary A/B/A CNN inference, verified restoration, then native menu restart."""
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
import traceback
import argparse,uuid

from board_profile import STAGE,LEGACY,OLD,NEW,load


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def gone(pid):
    try:return Path('/proc',str(pid),'stat').read_text().split()[2]=='Z'
    except FileNotFoundError:return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--style',choices=('comic','oil','both'),default='comic');parser.add_argument('--seconds',type=float,default=30);parser.add_argument('--upscaler',choices=('pl-fsr','bilinear'),default='pl-fsr');parser.add_argument('--game',choices=('tuxracer','neverball','neverputt','quake','quake3','touhou','classicube'),default='neverputt');parser.add_argument('--frame-pipeline',choices=('serial','overlap'),default='overlap');demo_options=parser.parse_args();assert 1<=demo_options.seconds<=300
    out=STAGE/('multigame-play-r4-'+uuid.uuid4().hex[:12]);out.mkdir(mode=0o700)
    result=dict(passed=False,FPGA_programming_included=True,SD_modified=False,
                game_fps_measured=False,artistic_quality_accepted=False,phases={},error=None)
    save(out/'result.json',result)
    from multigame_play_r4_tasks import guarded_adapter,run_live,run_fixed
    m,Adapter=load(STAGE/'frozen_loader.py');m.CLIENTS=(*m.CLIENTS,'rix-neural-detail','rix-cnn-fsr','test-cnn-fsr','rix-cfs-poly','rix-cfs-round','rix-cfs-pipe','rix-cfs-early','rix-cfs-poll','test-fsr-pipe','test-fsr-poll');adapter=guarded_adapter(Adapter)()
    m.REPORT=Path('/tmp/postproc-tests')/(out.name+'-cnn-group-load.json')
    extension=json.loads((STAGE/'multigame-play-r4-index.json').read_text())
    for name,digest in extension.items():assert sha(STAGE/name)==digest,name
    for name,digest in json.loads((STAGE/'cfs-fast-r1-micro-index.json').read_text()).items():assert sha(STAGE/name)==digest,name
    for name,digest in json.loads((STAGE/'cfs-pipe-r2-index.json').read_text()).items():assert sha(STAGE/name)==digest,name
    for name,digest in json.loads((STAGE/'cfs-pipe-r3-index.json').read_text()).items():assert sha(STAGE/name)==digest,name
    for name,digest in json.loads((STAGE/'multigame-r4-index.json').read_text()).items():assert sha(STAGE/name)==digest,name
    fsr_index=json.loads((STAGE/'cnn-fsr-index.json').read_text())
    for name,digest in fsr_index.items():assert sha(STAGE/name)==digest,name
    required=json.loads((STAGE/'detail-r1-index.json').read_text())
    for name,digest in required.items():assert sha(STAGE/name)==digest,name
    index=json.loads((STAGE/'payload-index.json').read_text())
    for name,meta in index.items():
        p=STAGE/name;assert p.is_file() and not p.is_symlink()
        assert p.stat().st_size==meta['bytes'] and sha(p)==meta['sha256'],name
    assert sha(STAGE/'old.bin')==OLD and sha(STAGE/'new.bin')==NEW
    result['source']=json.loads((STAGE/'source.json').read_text())
    result['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    cases=json.loads((STAGE/'cases.json').read_text())
    app=Path('/tmp/rasterix-launcher-v3-native')
    menu_stopped=False;can_restart=False;controller=None;retired=False;original=None

    def infer(phase,cycles):
        folder=out/phase;folder.mkdir()
        runs=[]
        with adapter.lend_post():
            for case in cases:
                for pass_index,mode in enumerate(('atomic','group','group','atomic') if cycles==462816 else ('atomic','legacy')):
                    name=case['name']+'-'+mode+'-'+str(pass_index)
                    target=folder/(name+'.bin')
                    args=[str(STAGE/'rix-neural-group'),'--backend','pl-int8',
                          '--model',str(STAGE/case['model']),'--input',str(STAGE/case['input']),
                          '--output',str(target),'--pio-output',mode]
                    began=time.monotonic()
                    run=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=25)
                    (folder/(name+'.log')).write_text(run.stdout)
                    assert run.returncode==0,run.stdout
                    metrics=json.loads(run.stdout)
                    assert metrics['backend']=='pl-int8' and metrics['cnn_cycles']==cycles
                    assert metrics['engine_version']==(4 if cycles==462816 else 2)
                    assert metrics['pio_output']==mode
                    assert target.read_bytes()==(STAGE/case['expected']).read_bytes(),name
                    runs.append(dict(case=case['name'],mode=mode,metrics=metrics,
                                     process_seconds=time.monotonic()-began,bit_exact=True,
                                     output_bytes=target.stat().st_size,output_sha256=sha(target),
                                     output=target.relative_to(STAGE).as_posix()))
        phase_result=dict(runs=runs,median_inference_seconds=statistics.median(r['metrics']['seconds'] for r in runs))
        result['phases'][phase]=phase_result;save(out/'result.json',result)
        print('CNN_PHASE_DONE',phase,phase_result['median_inference_seconds'],flush=True)

    try:
        sessions=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:args=(proc/'cmdline').read_bytes().split(b'\0')
            except (FileNotFoundError,ProcessLookupError):continue
            if any(arg==str(app/'session.py').encode() for arg in args):sessions.append(int(proc.name))
        assert len(sessions)==1,'Expected exactly the existing native menu session'
        pid=sessions[0]
        # Normal session shutdown drains the presenter and restores POST mode 1.
        os.kill(pid,signal.SIGTERM)
        until=time.monotonic()+125
        while not gone(pid):
            assert time.monotonic()<until,'Menu is still draining; no FPGA load attempted'
            time.sleep(.1)
        menu_stopped=True
        with adapter.locks():
            before=adapter.snapshot();m.check_idle(before)
            assert before['cnn']==m.java_cnn_contract(OLD)
            result['before']=before;can_restart=True
            original=LEGACY.read_bytes()
            assert not LEGACY.is_symlink() and LEGACY.stat().st_uid==0 and not LEGACY.stat().st_mode&0o077
            assert original.decode().splitlines()[:3]==['RIX_FSR_PL_ACTIVE_V1',result['boot_id'],OLD]
            (out/'original-receipt.txt').write_bytes(original);(out/'original-receipt.txt').chmod(0o600)
            result['original_before']=adapter.snapshot()
            LEGACY.unlink();retired=True;can_restart=False
            controller=m.Controller(adapter)
            loaded=controller.run(adapter.read_manifest)
            save(out/'candidate-load-complete.json',loaded)
            assert loaded['passed'] and loaded['after']['cnn']==m.java_cnn_contract(NEW),loaded.get('error')
            result['candidate_load_passed']=True
            result['fixed']=run_fixed(adapter,STAGE,out/'fixed')
            result['live']=run_live(adapter,STAGE,out/'live',demo_options.style,demo_options.seconds,demo_options.upscaler,demo_options.game,demo_options.frame_pipeline)
    except BaseException:
        result['error']=traceback.format_exc()
    finally:
        if retired:
            try:
                with adapter.locks():
                    if controller is not None and controller.record['device_mutation_started']:
                        if not controller.record['rollback']['attempted']:
                            controller.record['restore_reason']='normal-test-teardown'
                            controller.recover()
                        assert controller.record['rollback']['passed'],'Original FPGA restore failed'
                        result['restoration']=controller.record['rollback']
                    else:
                        state=adapter.snapshot();m.check_idle(state)
                        assert state['cnn']==m.java_cnn_contract(OLD)
                    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==result['boot_id']
                    assert not LEGACY.exists()
                    fd=os.open(str(LEGACY),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'wb') as stream:
                        stream.write(original);stream.flush();os.fsync(stream.fileno())
                    assert LEGACY.read_bytes()==original
                    retired=False;can_restart=True;result['original_restore_passed']=True
                    if result['error'] is None:result['original_after']=adapter.snapshot()
            except BaseException:
                can_restart=False;result['restore_error']=traceback.format_exc()
        if menu_stopped and can_restart:
            try:
                with (out/'restored-menu.log').open('xb') as log:
                    child=subprocess.Popen([sys.executable,'-B',str(app/'session.py'),'--board','--lcd-menu'],
                                           stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL)
                until=time.monotonic()+20;ready=None
                while ready is None:
                    assert child.poll() is None and time.monotonic()<until,'Native menu did not restart'
                    for line in (out/'restored-menu.log').read_text().splitlines():
                        if line.startswith('LAUNCHER_SESSION_READY '):ready=json.loads(line.split(' ',1)[1])
                    time.sleep(.1)
                sys.path.insert(0,str(app));from launcher_control import exchange
                until=time.monotonic()+20
                while True:
                    status=exchange(Path(ready['socket']),'STATUS')
                    if status.get('phase')=='menu' and adapter.post_state()['active']==2:break
                    assert time.monotonic()<until,'Native menu presenter not ready'
                    time.sleep(.1)
                result['restored_menu']=dict(pid=child.pid,ready=ready,status=status,post=adapter.post_state())
            except BaseException:result['menu_restore_error']=traceback.format_exc()
        result['passed']=(result['error'] is None and result.get('fixed',{}).get('passed') is True
                          and result.get('live',{}).get('passed') is True and result.get('original_restore_passed') is True and 'restored_menu' in result)
        save(out/'result.json',result)
        print('MULTIGAME_PLAY_R4_COMPLETE',result['passed'],str(out),flush=True)
    return 0 if result['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
