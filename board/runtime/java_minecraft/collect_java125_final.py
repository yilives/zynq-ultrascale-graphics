#!/usr/bin/env python3
"""Collect real client failure, normal close and restoration evidence."""
import fcntl,hashlib,importlib.util,json,os,subprocess,sys,tarfile
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
BASE=Path('/tmp/rix-java125');OUT=Path('/tmp/postproc-tests')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
with open('/tmp/rasterix-game-launch.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    guard=GpuRecoveryGuard();guard.check()
    clients=('java','ClassiCube','rix-fsr-pl','tuxracer','neverball','neverputt','quakespasm','quake3e','rix-neural-style','rix-superres','th06-rix')
    p=subprocess.run(['pidof',*clients],stdout=subprocess.PIPE);assert p.returncode==1 and not p.stdout
    clean=read(BASE/'result-client-clean/result.json')
    assert clean['exit_code']==0 and not clean['expired'] and clean['normal_close_requested']
    assert clean['texture_too_big'] and not clean['gameplay_verified']
    assert 'Invalid value (1281)' in (BASE/'result-client-clean/stdout.log').read_text()
    v4=read(OUT/'cc_v4_fpga_load.json');fsr=read(OUT/'cc_fsr_fpga_load.json')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    for row in (v4,fsr):assert row['passed'] and row['outcome']=='new-loaded-and-verified' and row['after']['boot_id']==boot
    cc=read(OUT/'java125_restorecheck/result.json')
    assert cc['passed'] and cc['exit_code']==0 and cc['fsr_drained'] and cc['fsr_completed_frames']>0
    assert cc['boot_id']==boot and cc['cpu_pixel_processing_live'] is False and cc['view_distance']==32
    spec=importlib.util.spec_from_file_location('restored_fsr_controller','/tmp/fpga_fsr_control.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    state=mod.LinuxAdapter().runtime_state()
    assert state['boot_id']==boot and state['gpu']['status']==3 and state['gpu']['enabled']==1
    assert all(state['gpu'][k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    assert len({state['gpu'][k] for k in ('frame_id','swap','copy','presented','last_presented')})==1
    assert state['post']['active']==1 and state['post']['snapshot_status']==state['post']['snapshot_expirations']==0
    assert hashlib.sha1((BASE/'libs/client.jar').read_bytes()).hexdigest()=='4a2fac7504182a97dcbcd7560c6392d7c8139928'
    files=dict(gl='/tmp/rasterix-classicube/ffa912210b7c/lib/libGL.so.1',
        launcher='/tmp/rix-classicube-fsr-v23',fsr='/tmp/rix-fpga-fsr/ahead/rix-fsr-pl')
    pins=dict(gl='452bbd3d09c94e4c68906475a3432a03e39e92ebede93bd0e3eb546fbc9bf739',
        launcher='b33a60e7162ee2b4358ce14fa30a87763c290bad4243be4f5d478dc6045ae65f',
        fsr='de86960c07507deabb08e79daf6c1adc99315564e041db772ab8152146d3cb13')
    assert {k:sha(v) for k,v in files.items()}==pins
    record=dict(passed=True,scope='JVM/native support, known initialization failure, clean close and original runtime restoration; gameplay failed',
        java_gameplay_passed=False,java_fps=None,normal_close_seconds=clean['seconds'],normal_close_passed=True,
        boot_id=boot,guard_clear=True,old_quarantine=read(guard.path),state=state,accepted_file_hashes=pins,
        classicube_restoration_test_passed=True,classicube_restoration_fsr_frames=cc['fsr_completed_frames'],
        bit_sha256=fsr['manifest']['images']['new']['sha256'],active_receipt=Path('/tmp/rix-fpga-fsr/active-receipt.txt').read_text())
    target=OUT/'java125-final-state.json';assert not target.exists();target.write_text(json.dumps(record,indent=2)+'\n')
    archive=OUT/'java125-final-evidence.tar.gz';assert not archive.exists()
    with tarfile.open(archive,'w:gz') as t:
        t.add(BASE/'result-client-clean',arcname='result-client-clean')
        for name in ('cc_v4_fpga_load.json','cc_fsr_fpga_load.json','java125-final-state.json'):
            t.add(OUT/name,arcname=name)
        t.add(OUT/'java125_restorecheck',arcname='classicube-restorecheck')
    print('JAVA125_FINAL_EVIDENCE_PASS',archive.stat().st_size,sha(archive),flush=True)
