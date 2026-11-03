#!/usr/bin/env python3
"""Run an image-bound offline scanout ABBA probe, then verify restoration."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import stat

BASE = Path('/tmp/rix-fpga-fsr')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True, choices=('v19', 'v22'))
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    import hashlib
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    for value in (args.helper_sha256, args.manifest_sha256):
        require(re.fullmatch('[0-9a-f]{64}', value), 'Invalid explicit identity')
    helper = BASE / ('test_fsr_pl_board_' + args.version + '.py')
    info = helper.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022 and
            sha(helper) == args.helper_sha256, 'Unreviewed static helper')
    spec = importlib.util.spec_from_file_location('fsr_offline_load_qa', str(helper))
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    q.CLIENTS += ('rix-fsr-load-probe',)
    binary = Path('/tmp/rix-fsr-load-probe')
    manifest_path = Path('/tmp/fsr-load-probe-' + args.version + '-manifest.json')
    for path in (binary, manifest_path):
        q.private_file(path)
    require(sha(manifest_path) == args.manifest_sha256, 'Build manifest changed')
    manifest = json.loads(manifest_path.read_text())
    require(manifest['passed'] and manifest['FPGA_execution_included'] is False and
            sha(binary) == manifest['files']['rix-fsr-load-probe'] and binary.stat().st_mode & stat.S_IXUSR,
            'Diagnostic executable differs from reviewed build')
    identity = q.receipt_identity(manifest['baseline_runtime_sha256'])
    require(identity['bit_sha256'] == manifest['bit_sha256'] and
            identity['source_sha256'] == manifest['source_sha256'], 'Diagnostic uses another image')
    require(not q.active_clients(), 'Another GPU client is active')
    spaces_before = q.guard_space()
    folder = Path('/tmp/postproc-tests/fsr-load-probe-' + args.version)
    folder.mkdir(mode=0o700)
    q.OUT = folder
    before = q.snapshot('before')
    require(before['post']['requested'] == before['post']['active'] == 1 and
            before['post']['snapshot_expirations'] == 0, 'Probe requires idle bilinear/style0')
    source, golden = q.vectors()['mc-live64']
    command = [str(binary), str(source), str(golden)]
    text = q.run_logged(command, folder / 'runtime.log', timeout=30)
    stats = q.json_line(text)
    require(stats['passed'] and stats['offline_only'] and stats['checked_frames'] == 21 and
            stats['restored_post'] == 1 and stats['scratch_source'] == '0x21500000' and
            len(stats['samples']) == 21, 'Diagnostic did not complete its full sequence')
    rows = stats['samples']
    require(rows[0]['run'] == rows[0]['sample'] == 0 and rows[0]['post'] == 1, 'Missing verified warmup')
    for index, mode in enumerate((1, 514, 514, 1), 1):
        group = rows[1 + (index - 1) * 5:1 + index * 5]
        require([r['sample'] for r in group] == list(range(1, 6)) and
                all(r['run'] == index and r['post'] == mode for r in group), 'Scanout ABBA sequence differs')
    require(all(r['pixels'] == 384000 and r['mismatches'] == 0 and
                type(r['load_us']) is int and r['load_us'] > 0 and
                type(r['compute_us']) is int and r['compute_us'] > 0 for r in rows),
            'Full golden comparison or timings failed')
    after = q.snapshot('after')
    require(after['gpu'] == before['gpu'] and after['post']['requested'] == after['post']['active'] == 1 and
            after['post']['snapshot_status'] == after['post']['snapshot_expirations'] == 0 and
            q.receipt_identity(manifest['baseline_runtime_sha256']) == identity and not q.active_clients(),
            'GPU, lease, display or executable identity changed')
    summary = {}
    for mode in (1, 514):
        chosen = [r for r in rows if r['run'] and r['post'] == mode]
        summary[str(mode)] = dict(samples=len(chosen), mean_load_us=sum(r['load_us'] for r in chosen)/len(chosen),
                                  mean_compute_us=sum(r['compute_us'] for r in chosen)/len(chosen))
    result = dict(passed=True, offline_only=True, identity=identity, before=before, after=after,
                  spaces_before=spaces_before, spaces_after=q.guard_space(), command=command,
                  runtime=stats, aggregate=summary, files={str(p): sha(p) for p in
                      (helper, manifest_path, binary, source, golden, Path(__file__), folder / 'runtime.log')},
                  measurement_limit='No game; independent scratch source, CPU conversion outside timed LOAD/COMPUTE; not a live-FPS benchmark')
    q.exclusive_json(folder / 'result.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
