#!/usr/bin/env python3
"""Retain an idle boot-bound RAM experiment before staging its successor."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--bit-sha256', required=True)
    parser.add_argument('--source-sha256', required=True)
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9_-]{1,48}', args.label)
    assert re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.boot_id)
    assert all(re.fullmatch(r'[0-9a-f]{64}', s) for s in (args.bit_sha256, args.source_sha256))
    assert os.geteuid() == 0
    assert shutil.disk_usage('/').free >= 32 * 1024**2
    assert shutil.disk_usage('/media/sd-mmcblk1p1').free >= 16 * 1024**2
    spec = importlib.util.spec_from_file_location('fsr_controller', '/tmp/fpga_fsr_control.py')
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    adapter = controller.LinuxAdapter()
    base = Path('/tmp/rix-fpga-fsr')
    report = Path('/tmp/postproc-tests/cc_fsr_fpga_load.json')
    retained = Path('/tmp/rix-fpga-fsr-' + args.label + '-retained')
    retained_report = report.with_name('cc_fsr_fpga_load_' + args.label + '.json')
    receipt = Path('/tmp/postproc-tests/fsr-retention-' + args.label + '.json')
    assert base.is_dir() and not base.is_symlink()
    assert all(not p.exists() and not p.is_symlink() for p in (retained, retained_report, receipt))
    locks = []
    try:
        for name in controller.LOCKS:
            fd = os.open('/tmp/' + name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            stream = os.fdopen(fd, 'a+')
            locks.append(stream)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = adapter.runtime_state()
        controller.check_idle(before)
        assert before['boot_id'] == args.boot_id
        identities = {name: adapter.regular_info(base / name) for name in ('new.bin', 'active-receipt.txt', 'manifest.json')}
        assert identities['new.bin']['sha256'] == args.bit_sha256
        assert (base / 'active-receipt.txt').read_text().splitlines() == [
            'RIX_FSR_PL_ACTIVE_V1', args.boot_id, args.bit_sha256, args.source_sha256]
        report_identity = adapter.regular_info(report)
        assert json.loads(report.read_text())['passed'] is True
        assert adapter.runtime_state() == before
        os.rename(report, retained_report)
        try:
            os.rename(base, retained)
        except Exception:
            os.rename(retained_report, report)
            raise
        assert adapter.runtime_state() == before
        for name, info in identities.items():
            actual = adapter.regular_info(retained / name)
            assert (actual['bytes'], actual['sha256']) == (info['bytes'], info['sha256'])
        actual = adapter.regular_info(retained_report)
        assert (actual['bytes'], actual['sha256']) == (report_identity['bytes'], report_identity['sha256'])
        record = dict(passed=True, label=args.label, boot_id=args.boot_id, before=before,
                      retained=str(retained), retained_report=str(retained_report),
                      files=identities, report_identity=report_identity, FPGA_reconfigured=False)
        with receipt.open('x') as stream:
            json.dump(record, stream, indent=2)
            stream.write('\n')
        print(json.dumps(dict(passed=True, retained=str(retained), receipt=str(receipt))), flush=True)
    finally:
        for stream in reversed(locks):
            stream.close()


if __name__ == '__main__':
    main()
