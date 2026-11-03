#!/usr/bin/env python3
"""Replay the verified v7 transaction's rollback after its first-frame QA fault.

Default is read-only inspection. No counter is cleared in software; --execute
quiesces and reloads the known atomic-v4 rollback through the original controller.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import signal

BASE=Path('/tmp/rix-fpga-fsr')
REPORT=Path('/tmp/postproc-tests/cc_fsr_fpga_recover_v7.json')
CONTROLLER_SHA='6f4f34f440094cde3d858ad14f405f9d600cfd4ded5c5f011e9c00f52d09b92d'
BIT_SHA='10369dbde0953497ed58567b67789c7da0bbb3d8ac61b7f4fc22e7aeb8db9a2c'
SOURCE_SHA='78bc6f1d4ead205de069626d0a89e709319059f4691874e578d2dadaea1d02a3'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    path=BASE/'fpga_fsr_control.py'
    assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==CONTROLLER_SHA
    spec=importlib.util.spec_from_file_location('original_fsr_controller',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.REPORT=REPORT
    a=module.LinuxAdapter()
    assert not REPORT.exists() and not REPORT.is_symlink()
    with a.locks():
        a.ram_directory(BASE);a.ram_directory(REPORT.parent)
        load_path=Path('/tmp/postproc-tests/cc_fsr_fpga_load.json')
        a.regular_info(load_path)
        load=json.loads(load_path.read_text(),object_pairs_hook=module.unique_object)
        assert load['passed'] is True and load['outcome']=='new-loaded-and-verified'
        assert load['manifest']['images']['new']['sha256']==BIT_SHA and load['manifest']['source_sha256']==SOURCE_SHA
        current=a.snapshot();gpu=current['gpu'];post=current['post']
        assert current['boot_id']==load['before']['boot_id'] and not current['clients']
        assert current['manager_state']=='operating' and gpu['status']==3 and gpu['config']==0x9adb505e
        assert all(gpu[key]==0 for key in module.IDS)
        assert gpu['underflows']==1 and all(gpu[key]==0 for key in module.ERRORS if key!='underflows')
        assert post['requested']==post['active']==1 and post['snapshot_status']==post['snapshot_expirations']==0
        assert current['cnn']==load['after']['cnn'] and current['bindings']==load['before']['bindings']
        assert current['module_inventory']==load['before']['module_inventory']
        for name in module.MODULES:
            assert current['modules'][name]['file']==load['before']['modules'][name]['file']
            assert current['modules'][name]['loaded']==load['before']['modules'][name]['loaded']
            assert current['modules'][name]['refcount']==0
        receipt=(BASE/'active-receipt.txt').read_text().splitlines()
        assert receipt==['RIX_FSR_PL_ACTIVE_V1',current['boot_id'],BIT_SHA,SOURCE_SHA]
        qa_path=Path('/tmp/postproc-tests/fsr-pl-v7/result.json')
        qa=json.loads(qa_path.read_text())
        assert qa['passed'] is False and qa['error'] is None and len(qa['cases'])==3
        assert all(case['comparison']['mismatches']==0 for case in qa['cases'])
        assert qa['lcd']['mismatches']==0 and qa['lcd']['samples']==6000
        assert qa['cleanup_error']=="RuntimeError('GPU fault counter is nonzero')"
        assert not Path('/tmp/rix-fsr-pl.quarantine').exists()
        controller=module.Controller(a)
        controller.record=copy.deepcopy(load)
        controller.record.update(passed=False,outcome='recovering-diagnosed-first-frame-underflow',
            previous_load_sha256=hashlib.sha256(load_path.read_bytes()).hexdigest(),
            failing_qa_sha256=hashlib.sha256(qa_path.read_bytes()).hexdigest(),
            recovery_observed_before=current,rollback={'attempted':False,'passed':False},
            controller_sha256=CONTROLLER_SHA,recovery_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        controller.before=load['before']
        controller.verify_images(load['manifest'])
        a.rollback_proof(current['boot_id'],load['manifest']['images']['old']['sha256'])
        if not args.execute:
            print(json.dumps({'inspection_passed':True,'execute':False,'boot_id':current['boot_id'],
                'observed_underflows':1,'reason':'v7 native to LR without an initial presented GPU frame',
                'rollback_sha256':load['manifest']['images']['old']['sha256']}),flush=True)
            return
        a.verify_fsr_protocol() # No DDR command; ensure the current master is idle.
        def interrupted(sig, frame):
            if not controller.recovering:raise RuntimeError('Recovery interrupted before mutation')
        signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
        controller.save()
        controller.recover()
        result=controller.record
        print(json.dumps({'recovery_passed':result['rollback']['passed'],'outcome':result['outcome'],
                          'report':str(REPORT)}),flush=True)
        if not result['rollback']['passed']:raise SystemExit(3)

if __name__=='__main__':main()
