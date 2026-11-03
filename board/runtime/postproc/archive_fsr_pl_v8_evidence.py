#!/usr/bin/env python3
"""Collect completed fixed-v8 RAM tests without changing FPGA or game state."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tarfile


BASE = Path('/tmp/rix-fpga-fsr')
ROOT = Path('/tmp/postproc-tests')
OUT = ROOT / 'fsr-pl-v8-evidence'
ARCHIVE = ROOT / 'fsr_pl_v8_evidence.tar.gz'
HELPER_SHA256 = '05c6a091ff6c84eab350f39737b451c60db367b3b352c556de12b5940c81c31b'
RUNTIME_SHA256 = '45309bfe1f5867b47e8bb01b2de40ce529d0f80ef35f2df4861680e82e018611'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    helper_path = BASE / 'test_fsr_pl_board_v8.py'
    require(sha(helper_path.read_bytes()) == HELPER_SHA256, 'Changed static QA helper')
    spec = importlib.util.spec_from_file_location('fixed_v8_archive_helper', str(helper_path))
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    identity = q.receipt_identity(RUNTIME_SHA256)
    require(not q.active_clients(), 'A GPU client is still running')
    require(not OUT.exists() and not ARCHIVE.exists(), 'Evidence destination already exists')
    OUT.mkdir(mode=0o700)
    q.OUT = OUT
    before = q.snapshot('before')
    require(before['post']['requested'] == 1 and before['post']['snapshot_expirations'] == 0,
            'Display was not fully restored')
    spaces = q.guard_space()
    static_path = ROOT / 'fsr-pl-v8/result.json'
    live_path = ROOT / 'fsr-pl-live-v8/result.json'
    static_result = json.loads(static_path.read_text())
    live_result = json.loads(live_path.read_text())
    for result in (static_result, live_result):
        require(result.get('passed') is True and result.get('error') is None,
                'A board test did not pass')
        require(result['identity'] == result['identity_after'] == identity,
                'Board test identities changed')
    require(live_result['static_qa']['sha256'] == sha(static_path.read_bytes()),
            'Live test used another static report')
    require(live_result['profile_restored'] is True,
            'Game profile was not restored')
    profile = Path('/opt/rasterix/classicube/profile/options.txt')
    require(sha(profile.read_bytes()) == live_result['profile_sha256_before'],
            'Game profile changed since the live test')
    require(len(static_result['cases']) == 3, 'Incomplete static QA')
    frames = {}
    for case in static_result['cases']:
        name = case['scene']
        output = ROOT / 'fsr-pl-v8' / (name + '.xrgb')
        q.private_file(output)
        raw = output.read_bytes()
        require(len(raw) == 1536000 and sha(raw) == q.IDENTITIES[name][1] ==
                case['comparison']['output_sha256'], 'Static output changed: ' + name)
        require(case['comparison']['mismatches'] == 0 and
                case['comparison']['pixels'] == 384000, 'Static pixels did not pass')
        frames[name] = dict(bytes=len(raw), sha256=sha(raw))
    lcd_path = ROOT / 'fsr-pl-v8/lcd.rgb565'
    require(sha(lcd_path.read_bytes()) == static_result['lcd']['lcd_sha256'] and
            static_result['lcd']['samples'] == 6000 and
            static_result['lcd']['mismatches'] == 0, 'LCD evidence changed')
    cases = {case['mode']: case for case in live_result['cases']}
    require(set(cases) == {'bilinear', 'fsr-pl'} and
            all(case['passed'] and case['children_drained'] for case in cases.values()),
            'Incomplete live QA or undrained children')
    require(cases['bilinear']['game_result']['world'] ==
            cases['fsr-pl']['game_result']['world'] == live_result['matching_world'],
            'The live comparison used different worlds')
    files = {}

    def include(path, name):
        q.private_file(path)
        data = path.read_bytes()
        require(len(data) <= 512000 and name not in files, 'Unexpected evidence member')
        files[name] = data

    for directory in ('fsr-pl-v8', 'fsr-pl-live-v8'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and (path.suffix in ('.json', '.log') or
                                   path.name in ('lcd.rgb565', 'options.before')):
                include(path, str(path.relative_to(ROOT)))
    for path, name in (
        (ROOT / 'cc_fsr_fpga_load.json', 'load/result.json'),
        (BASE / 'stage-result.json', 'stage/result.json'),
        (BASE / 'manifest.json', 'load/manifest.json'),
        (BASE / 'active-receipt.txt', 'load/active-receipt.txt'),
        (BASE / 'qa-generation.json', 'load/qa-generation.json'),
        (Path('/tmp/fsr-stage-v8.log'), 'stage/stdout.log'),
        (Path('/tmp/fsr-load-v8.log'), 'load/stdout.log'),
        (Path('/tmp/fsr-static-qa-v8.log'), 'fsr-pl-v8/stdout.log'),
        (Path('/tmp/fsr-live-qa-v8.log'), 'fsr-pl-live-v8/stdout.log'),
        (BASE / 'test_fsr_pl_board_v8.py', 'scripts/test_fsr_pl_board_v8.py'),
        (BASE / 'test_fsr_pl_live_v8.py', 'scripts/test_fsr_pl_live_v8.py'),
        (Path(__file__), 'scripts/archive_fsr_pl_v8_evidence.py'),
    ):
        include(path, name)
    for name in ('load/result.json', 'stage/result.json'):
        require(json.loads(files[name])['passed'] is True, 'Load or stage did not pass')
    after = q.snapshot('after')
    require(after == before and not q.active_clients(), 'State changed during collection')
    require(q.receipt_identity(RUNTIME_SHA256) == identity, 'Load identity changed')
    for path in sorted(OUT.glob('*.log')):
        include(path, 'collection/' + path.name)
    record = dict(format='rix-fsr-pl-fixed-v8-collected-evidence', passed=True,
                  identity=identity, before=before, after=after, spaces=spaces,
                  profile_restored=True, static_output_files=frames,
                  source_fps=cases['fsr-pl']['source_fps'],
                  fsr_new_output_fps=cases['fsr-pl']['new_output_fps'],
                  bilinear_new_output_fps=cases['bilinear']['new_output_fps'],
                  script_sha256=sha(Path(__file__).read_bytes()),
                  files={name: dict(bytes=len(data), sha256=sha(data))
                         for name, data in sorted(files.items())},
                  note='RAM-only; no SD/BOOT writes. Full static outputs remain in board RAM; '
                       'their hashes were checked again during collection.')
    encoded = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
    q.exclusive_json(OUT / 'result.json', record)
    files['collection/result.json'] = encoded
    with ARCHIVE.open('xb') as stream:
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name, data in sorted(files.items()):
                require(not name.startswith('/') and '..' not in Path(name).parts,
                        'Unsafe member name')
                info = tarfile.TarInfo(name)
                info.mode = 0o600
                info.size = len(data)
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
    require(ARCHIVE.stat().st_size <= 1536000, 'Archive exceeds serial readback limit')
    print(json.dumps(dict(passed=True, archive=str(ARCHIVE), bytes=ARCHIVE.stat().st_size,
                          archive_sha256=sha(ARCHIVE.read_bytes()),
                          members=len(files), identity=identity), sort_keys=True))


if __name__ == '__main__':
    main()
