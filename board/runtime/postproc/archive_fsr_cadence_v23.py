#!/usr/bin/env python3
"""Collect completed cadence runs without including captures in timed windows."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile

BASE = Path('/tmp/rix-fpga-fsr')
ROOT = Path('/tmp/postproc-tests')
OUT = ROOT / 'fsr-runtime-cadence-v23'
sha = lambda data: hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    for name in ('helper-sha256', 'runtime-sha256', 'candidate-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    require(all(re.fullmatch('[0-9a-f]{64}', value) for value in vars(args).values()), 'Invalid explicit SHA')
    helper = BASE / 'test_fsr_pl_board_v23.py'
    require(sha(helper.read_bytes()) == args.helper_sha256, 'Static helper changed')
    spec = importlib.util.spec_from_file_location('fsr_cadence_archive_helper', str(helper))
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    identity = q.receipt_identity(args.runtime_sha256)
    require(not q.active_clients(), 'A GPU client remains active')
    spaces = q.guard_space()
    folder = ROOT / ('fsr-cadence-evidence-v23_' + identity['boot_id'][:4])
    folder.mkdir(mode=0o700)
    q.OUT = folder
    before = q.snapshot('before')
    record = json.loads((OUT / 'result.json').read_text())
    require(record['format'] == 'rix-fsr-runtime-cadence-v23' and record['passed'] and
            record['error'] is None and record.get('cleanup_error') is None and
            record['identity'] == record['identity_after'] == identity and record['profile_restored'],
            'Long-run workflow/cleanup or identity failed')
    require(record['candidate_identity'] == record['candidate_identity_after'] and
            record['candidate_identity']['sha256'] == args.candidate_sha256 and
            sha((BASE / 'cadence/rix-fsr-pl').read_bytes()) == args.candidate_sha256,
            'Cadence executable identity changed')
    require(len(record['cases']) == 2 and record['sequence'] == ['candidate', 'candidate'] and
            all(case['passed'] and case['children_drained'] and case['game_result']['world'] == record['matching_world']
                for case in record['cases']), 'Two complete matching-world runs are required')
    files = {}

    def include(path, name):
        q.private_file(path)
        data = path.read_bytes()
        require(name not in files and len(data) <= 512000, 'Invalid or oversized member')
        files[name] = data

    for path in sorted(OUT.rglob('*')):
        if path.is_file() and (path.suffix in ('.json', '.log') or path.name == 'options.before'):
            include(path, 'long/' + path.relative_to(OUT).as_posix())
    for name in ('manifest.json', 'cadence-delivery.json'):
        include(BASE / 'cadence' / name, 'load/' + name)
    for name in ('test_fsr_runtime_cadence_v23.py', 'test_fsr_pl_board_v23.py'):
        include(BASE / name, 'scripts/' + name)
    include(Path(__file__), 'scripts/archive_fsr_cadence_v23.py')
    after = q.snapshot('after')
    require(after == before and not q.active_clients() and q.receipt_identity(args.runtime_sha256) == identity,
            'State or identity changed during collection')
    for path in sorted(folder.glob('*.log')):
        include(path, 'collection/' + path.name)
    collection = dict(format='rix-fsr-cadence-collected-evidence', passed=True, version='v23',
                      identity=identity, candidate_sha256=args.candidate_sha256,
                      before=before, after=after, spaces=spaces, aggregate=record['aggregate'],
                      script_sha256=sha(Path(__file__).read_bytes()),
                      files={name: dict(bytes=len(data), sha256=sha(data)) for name, data in sorted(files.items())})
    files['collection/result.json'] = (json.dumps(collection, indent=2, sort_keys=True) + '\n').encode()
    q.exclusive_json(folder / 'result.json', collection)
    archive = ROOT / ('fsr-cadence-v23_' + identity['boot_id'][:4] + '-evidence.tar.gz')
    with archive.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.mode, info.size, info.mtime = 0o600, len(data), 0
            tar.addfile(info, io.BytesIO(data))
    require(archive.stat().st_size <= 1536000, 'Archive exceeds UART limit')
    print(json.dumps(dict(passed=True, archive=str(archive), bytes=archive.stat().st_size,
                          archive_sha256=sha(archive.read_bytes()), aggregate=record['aggregate'])), flush=True)


if __name__ == '__main__':
    main()
