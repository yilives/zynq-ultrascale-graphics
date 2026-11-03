#!/usr/bin/env python3
"""Collect real, completed optimization tests and their boot-bound evidence."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

ROOT = Path('/tmp/postproc-tests')
BASE = Path('/tmp/rix-fpga-fsr')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', choices=('v14',), required=True)
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('--runtime-sha256', required=True)
    parser.add_argument('--candidate-sha256', required=True)
    args = parser.parse_args()
    helper = BASE / ('test_fsr_pl_board_' + args.version + '.py')
    require(sha(helper.read_bytes()) == args.helper_sha256, 'QA helper identity changed')
    spec = importlib.util.spec_from_file_location('fsr_optimization_archive_helper', str(helper))
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    identity = q.receipt_identity(args.runtime_sha256)
    require(not q.active_clients(), 'A GPU client remains active')
    suffix = args.version + '_' + identity['boot_id'][:4]
    out = ROOT / ('fsr-prefetch-evidence-' + suffix)
    archive_path = ROOT / ('fsr_prefetch_' + suffix + '_evidence.tar.gz')
    require(not out.exists() and not archive_path.exists(), 'Preserve existing optimization archive')
    out.mkdir(mode=0o700)
    q.OUT = out
    before = q.snapshot('before')
    require(before['post']['active'] == before['post']['requested'] == 1 and
            before['post']['snapshot_expirations'] == 0, 'Display was not restored')
    spaces = q.guard_space()
    static_dir = ROOT / ('fsr-pl-' + args.version)
    overlap_dir = ROOT / ('fsr-runtime-prefetch-' + args.version)
    static = json.loads((static_dir / 'result.json').read_text())
    overlap = json.loads((overlap_dir / 'result.json').read_text())
    for result in (static, overlap):
        require(result['passed'] and result['error'] is None and
                result['identity'] == result['identity_after'] == identity,
                'A test failed or used another boot/bitstream/runtime')
    require(overlap['candidate_identity']['sha256'] == args.candidate_sha256 and
            overlap['candidate_identity_after'] == overlap['candidate_identity'],
            'Candidate identity changed')
    candidate = Path(overlap['candidate_identity']['path'])
    q.private_file(candidate)
    require(sha(candidate.read_bytes()) == args.candidate_sha256, 'Candidate ELF changed')
    require(overlap['profile_restored'] and
            sha(Path('/opt/rasterix/classicube/profile/options.txt').read_bytes()) ==
            overlap['profile_sha256_before'], 'Game profile was not restored')
    require(len(overlap['cases']) == 4 and
            [case['mode'] for case in overlap['cases']] == ['baseline', 'candidate', 'candidate', 'baseline'] and
            all(case['passed'] and case['children_drained'] and case['game_result']['world'] ==
                overlap['matching_world'] for case in overlap['cases']), 'Incomplete ABBA comparison')
    require(overlap['static_qa']['sha256'] == sha((static_dir / 'result.json').read_bytes()),
            'ABBA static QA binding differs')
    frames = {}
    for case in static['cases']:
        name = case['scene']
        image = static_dir / (name + '.xrgb')
        q.private_file(image)
        data = image.read_bytes()
        require(len(data) == 1536000 and sha(data) == case['comparison']['output_sha256'] ==
                q.IDENTITIES[name][1] and case['comparison']['mismatches'] == 0,
                'Static output changed: ' + name)
        frames[name] = dict(bytes=len(data), sha256=sha(data))
    require(len(frames) == 3 and static['lcd']['samples'] == 6000 and
            static['lcd']['mismatches'] == 0 and static['lcd']['full_frame']['mismatches'] == 0,
            'Full-frame or LCD QA missing')
    files = {}

    def include(path, name):
        q.private_file(path)
        data = path.read_bytes()
        require(name not in files and len(data) <= 512000, 'Unexpected evidence member')
        files[name] = data

    directories = [static_dir, overlap_dir]
    live_dir = ROOT / ('fsr-pl-live-' + args.version)
    if live_dir.exists():
        live = json.loads((live_dir / 'result.json').read_text())
        require(live['passed'] and live['identity'] == live['identity_after'] == identity,
                'Live test failed or used another load')
        directories.append(live_dir)
    for directory in directories:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and (path.suffix in ('.json', '.log') or
                                   path.name in ('options.before', 'lcd.rgb565')):
                include(path, path.relative_to(ROOT).as_posix())
    for path in (ROOT / 'cc_v4_fpga_stage.json', ROOT / 'cc_v4_fpga_load.json',
                 ROOT / 'cc_fsr_fpga_load.json'):
        require(json.loads(path.read_text())['passed'], 'A staging/load transaction did not pass')
        include(path, 'transactions/' + path.name)
    for name in ('stage-result.json', 'manifest.json', 'active-receipt.txt', 'runtime-manifest.json', 'qa-generation.json'):
        include(BASE / name, 'load/' + name)
    for path in sorted(Path('/tmp').glob('fsr-v14-*.log')):
        include(path, 'stdout/' + path.name)
    for path, name in ((helper, helper.name),
                       (BASE / ('test_fsr_runtime_prefetch_' + args.version + '.py'),
                        'test_fsr_runtime_prefetch_' + args.version + '.py'),
                       (Path(__file__), 'archive_fsr_prefetch_v14.py')):
        include(path, 'scripts/' + name)
    after = q.snapshot('after')
    require(after == before and not q.active_clients() and
            q.receipt_identity(args.runtime_sha256) == identity, 'State changed during collection')
    for path in sorted(out.glob('*.log')):
        include(path, 'collection/' + path.name)
    record = dict(format='rix-fsr-prefetch-collected-evidence', passed=True,
                  version=args.version, identity=identity, candidate_sha256=args.candidate_sha256,
                  before=before, after=after, spaces=spaces, profile_restored=True,
                  static_output_files=frames, aggregate=overlap['aggregate'],
                  files={name: dict(bytes=len(data), sha256=sha(data)) for name, data in sorted(files.items())},
                  script_sha256=sha(Path(__file__).read_bytes()),
                  note='RAM-only; no SD BOOT update. Full static output files rehashed, not included.')
    q.exclusive_json(out / 'result.json', record)
    files['collection/result.json'] = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
    with archive_path.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for name, data in sorted(files.items()):
            require(not name.startswith('/') and '..' not in Path(name).parts, 'Unsafe member name')
            info = tarfile.TarInfo(name)
            info.mode, info.size, info.mtime = 0o600, len(data), 0
            tar.addfile(info, io.BytesIO(data))
    require(archive_path.stat().st_size <= 1536000, 'Archive exceeds serial limit')
    print(json.dumps(dict(passed=True, archive=str(archive_path), bytes=archive_path.stat().st_size,
                          archive_sha256=sha(archive_path.read_bytes()), members=len(files),
                          aggregate=overlap['aggregate'])), flush=True)


if __name__ == '__main__':
    main()
