#!/usr/bin/env python3
"""Explicit ABBA comparison of baseline and POST/LOAD-overlap runtimes on v8.

Importing is device-free. The original v8 executables, static/live QA helpers,
bitstream receipt and passing static QA remain unchanged. Both runtimes use
the same basename, so the existing pidof client inventory detects either one.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import time

BASE = Path('/tmp/rix-fpga-fsr')
OUT = Path('/tmp/postproc-tests/fsr-runtime-overlap-v8')
CANDIDATE = Path('/tmp/rix-fsr-overlap/rix-fsr-pl')
LIVE_HELPER_SHA256 = '07f2e46b28e92aee5c877102a692bd5c1cee59371aa32bfb4938079585476b53'
STATIC_HELPER_SHA256 = '05c6a091ff6c84eab350f39737b451c60db367b3b352c556de12b5940c81c31b'
RUNTIME_SHA256 = '45309bfe1f5867b47e8bb01b2de40ce529d0f80ef35f2df4861680e82e018611'
BIT_SHA256 = 'c071227653622f3c17fc8e8947aa3d4557a5283c33878925c303e92b7e1128b4'
SOURCE_SHA256 = 'f63180133e8afbcf65bbb205290209112d0743820a535bcdbfb983fd73c9ee70'
SEQUENCE = ('baseline', 'candidate', 'candidate', 'baseline')
BACKEND = 'FPGA PL EASU12 + RCAS5 fixed point'
SCHEDULE = 'POST wait overlaps next SNP1/LOAD'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def helpers():
    path = BASE / 'test_fsr_pl_live_v8.py'
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'Live QA helper must be a root-owned regular file without group/other writes')
    require(sha(path) == LIVE_HELPER_SHA256, 'Reviewed live QA helper has changed')
    spec = importlib.util.spec_from_file_location('original_v8_live_qa', str(path))
    live = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(live)
    require(live.RUNTIME_SHA256 == RUNTIME_SHA256 and
            live.STATIC_HELPER_SHA256 == STATIC_HELPER_SHA256, 'QA constants differ')
    live.OUT = OUT
    q = live.helper()
    require(q.BIT_SHA256 == BIT_SHA256 and q.SOURCE_SHA256 == SOURCE_SHA256 and
            q.RUNTIME_SHA256 == RUNTIME_SHA256 and 'rix-fsr-pl' in q.CLIENTS,
            'Static QA identities or runtime basename inventory differ')
    return live, q


def candidate_identity(q, expected_sha):
    info = CANDIDATE.parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'Candidate directory must be a root-owned directory without group/other writes')
    q.private_file(CANDIDATE)
    info = CANDIDATE.lstat()
    require(info.st_mode & stat.S_IXUSR, 'Candidate is not executable by root')
    require(sha(CANDIDATE) == expected_sha, 'Candidate ELF SHA256 differs from the explicitly reviewed build')
    header = CANDIDATE.read_bytes()[:20]
    require(len(header) == 20 and header[:6] == b'\x7fELF\x02\x01' and
            int.from_bytes(header[18:20], 'little') == 183, 'Candidate is not an AArch64 ELF64 executable')
    return dict(path=str(CANDIDATE), sha256=expected_sha, uid=info.st_uid,
                mode=oct(stat.S_IMODE(info.st_mode)), size=info.st_size)


def validate_runtime(live, stats, mode):
    numbers = ('frames', 'elapsed_seconds', 'processed_fps', 'input_load_us', 'compute_us',
               'snapshot_retries', 'last_source_frame', 'last_bank')
    require(all(isinstance(stats.get(name), (int, float)) and not isinstance(stats[name], bool) and
                math.isfinite(stats[name]) for name in numbers), 'Non-finite or invalid runtime statistics')
    live.validate_runtime(stats)
    require(stats.get('backend') == BACKEND and stats.get('last_bank') in (0, 1),
            'Wrong FSR backend or output bank')
    require(isinstance(stats.get('frames'), int) and not isinstance(stats['frames'], bool),
            'Invalid completed-frame count')
    if mode == 'candidate':
        require(stats.get('schedule') == SCHEDULE, 'Candidate did not report the reviewed overlap schedule')
        names = ('loaded_frames', 'all_input_load_us', 'prepared_input_unused',
                 'snapshot_wait_us', 'post_remaining_wait_us', 'post_ack_observed_us')
        require(all(isinstance(stats.get(name), int) and not isinstance(stats[name], bool) and
                    stats[name] >= 0 for name in names), 'Invalid overlap timing/accounting fields')
        require(stats['prepared_input_unused'] in (0, 1) and
                stats['loaded_frames'] == stats['frames'] + stats['prepared_input_unused'],
                'Completed LOAD count does not match processed and unused inputs')
        require(stats['all_input_load_us'] >= stats['input_load_us'] and
                stats['post_ack_observed_us'] >= stats['post_remaining_wait_us'],
                'Overlap timing/accounting counters are inconsistent')
    else:
        require('schedule' not in stats, 'Baseline unexpectedly reports a candidate schedule')
    return stats


def run_case(live, q, mode, index, record, expected_sha):
    label = '%02d-%s' % (index, mode)
    attempt = OUT.name + '_' + label.replace('-', '_')
    attempt_path = Path('/tmp/postproc-tests') / attempt
    require(not attempt_path.exists() and not attempt_path.with_suffix('.tar.gz').exists(),
            'Launcher attempt already exists: ' + attempt)
    require(q.receipt_identity(RUNTIME_SHA256) == record['identity'], 'Load identity changed')
    require(candidate_identity(q, expected_sha) == record['candidate_identity'], 'Candidate file changed')
    require(not q.active_clients(), 'Another GPU client is active before this case')
    q.guard_space()
    command = ['rix-classicube', '--seconds', '32', '--world-size', '64', '--view-distance', '32',
               '--fps-limit', '120', '--autoplay', '--attempt', attempt]
    binary = q.RUNTIME if mode == 'baseline' else CANDIDATE
    case = dict(mode=mode, run=label, sequence_index=index, attempt=attempt,
                command=command, passed=False, source_size=[400, 240], display_size=[800, 480], style=0,
                runtime_path=str(binary), runtime_sha256=RUNTIME_SHA256 if mode == 'baseline' else expected_sha)
    record['cases'].append(case)
    game = runtime = None
    runtime_log = None
    try:
        with (OUT / (label + '-launcher.log')).open('x') as log:
            env = os.environ.copy()
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            game = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
            case['game_pid'] = game.pid
            game_log = attempt_path / 'game.log'

            def measured():
                require(game.poll() is None, 'MC launcher exited before measurement began')
                return game_log.exists() and 'RIX_MEASURE_BEGIN' in game_log.read_text(errors='replace')

            live.wait_until(measured, 50, 'MC startup did not reach RIX_MEASURE_BEGIN')
            time.sleep(1)
            require(game.poll() is None, 'MC ended before the source measurement window')
            ready = live.post_state(q, label + '-launcher-ready')
            require(ready['active'] == 0 and ready['snapshot_expirations'] == 0,
                    'Expected nearest/style0 with no expired snapshot lease before FSR')
            case['window_before'] = live.gpu_state(q, label + '-window-before')
            started = time.monotonic()
            runtime_command = [str(binary), '--live', '--seconds', '20']
            case['runtime_command'] = runtime_command
            runtime_path = OUT / (label + '-runtime.log')
            runtime_log = runtime_path.open('x')
            runtime = subprocess.Popen(runtime_command, stdout=runtime_log, stderr=subprocess.STDOUT, env=env)
            case['runtime_pid'] = runtime.pid

            def have_stats():
                text = runtime_path.read_text()
                if any(line.startswith('{') for line in text.splitlines()):
                    return True
                require(runtime.poll() is None, 'FSR runtime exited without statistics')
                require(game.poll() is None, 'MC stopped during the FSR output window')
                return False

            live.wait_until(have_stats, 35, 'FSR runtime exceeded its bounded output window')
            case['runtime'] = validate_runtime(live, q.json_line(runtime_path.read_text()), mode)
            case['window_after'] = live.gpu_state(q, label + '-window-after')
            elapsed = time.monotonic() - started
            frames = (case['window_after']['presented'] - case['window_before']['presented']) & 0xffffffff
            require(0 < frames < 10000, 'No new source frames or an implausible counter discontinuity')
            case['source_window_seconds'] = elapsed
            case['source_frames'] = frames
            case['source_fps'] = frames / elapsed
            stats = case['runtime']
            case['new_output_fps'] = stats['processed_fps']
            case['new_output_frames'] = stats['frames']
            case['new_output_window_seconds'] = stats['elapsed_seconds']
            case['average_input_load_ms'] = stats['input_load_us'] / stats['frames'] / 1000
            case['average_compute_ms'] = stats['compute_us'] / stats['frames'] / 1000
            case['new_output_basis'] = 'Completed and POST-acknowledged PL EASU12+RCAS5 output frames'
            if mode == 'candidate':
                case['average_snapshot_wait_ms'] = stats['snapshot_wait_us'] / stats['loaded_frames'] / 1000
                case['average_unhidden_post_wait_ms'] = stats['post_remaining_wait_us'] / stats['frames'] / 1000
                case['average_post_ack_observed_upper_bound_ms'] = stats['post_ack_observed_us'] / stats['frames'] / 1000
            live.wait_until(lambda: runtime.poll() is not None, 10, 'FSR runtime did not restore POST after measurement')
            require(runtime.returncode == 0, 'FSR runtime did not exit cleanly')
            require(live.post_state(q, label + '-runtime-after')['active'] == 0,
                    'FSR did not restore nearest/style0')
            live.wait_until(lambda: game.poll() is not None, 45, 'MC launcher did not finish its bounded run')
            case['game_exit'] = game.returncode
            result_path = attempt_path / 'result.json'
            require(result_path.is_file(), 'MC launcher result is missing')
            game_result = case['game_result'] = json.loads(result_path.read_text())
            require(game.returncode == 0 and game_result.get('passed') is True and
                    game_result.get('exit_code') == 0 and game_result.get('world'),
                    'Game or launcher validation failed')
            require(game_result['boot_id'] == record['identity']['boot_id'] and
                    game_result['world_size'] == 64 and game_result['view_distance'] == 32 and
                    game_result['fps_limit'] == 120, 'Game scene or boot settings differ')
            case['after'] = q.snapshot(label + '-case-after')
            require(case['after']['post']['active'] == 1 and
                    case['after']['post']['snapshot_expirations'] == 0,
                    'Launcher did not restore POST or the snapshot lease expired')
            require(q.receipt_identity(RUNTIME_SHA256) == record['identity'] and
                    candidate_identity(q, expected_sha) == record['candidate_identity'],
                    'Original or candidate identity changed during the game')
            case['passed'] = True
    finally:
        game_drained = live.drain(game, 'game', case)
        runtime_drained = live.drain(runtime, 'runtime', case)
        case['children_drained'] = game_drained and runtime_drained
        if runtime_log is not None:
            runtime_log.close()
        if attempt_path.is_dir():
            case['evidence'] = live.copy_game_evidence(attempt, label)


def aggregate(cases):
    result = {}
    for mode in ('baseline', 'candidate'):
        rows = [case for case in cases if case['mode'] == mode]
        result[mode] = dict(runs=len(rows),
            source_fps=sum(row['source_frames'] for row in rows) / sum(row['source_window_seconds'] for row in rows),
            new_output_fps=sum(row['new_output_frames'] for row in rows) / sum(row['new_output_window_seconds'] for row in rows),
            new_output_frames=sum(row['new_output_frames'] for row in rows))
    result['candidate_output_speedup'] = result['candidate']['new_output_fps'] / result['baseline']['new_output_fps']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-sha256', required=True, help='SHA256 of the separately reviewed AArch64 candidate ELF')
    arguments = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{64}', arguments.candidate_sha256), 'Invalid explicit candidate SHA256')
    require(arguments.candidate_sha256 != RUNTIME_SHA256, 'Candidate SHA equals the original executable')
    require(os.geteuid() == 0, 'Root is required')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    live, q = helpers()
    identity = q.receipt_identity(RUNTIME_SHA256)
    candidate = candidate_identity(q, arguments.candidate_sha256)
    static = live.validate_static(q, identity)
    spaces = q.guard_space()
    require(not q.active_clients(), 'A GPU client is already active')
    q.private_file(live.PROFILE)
    options = live.PROFILE.read_bytes()
    OUT.mkdir(mode=0o700)
    with (OUT / 'options.before').open('xb') as stream:
        stream.write(options)
    record = dict(format='rix-fsr-runtime-overlap-v8-abba', passed=False, error=None,
                  identity=identity, candidate_identity=candidate, static_qa=static,
                  spaces_before=spaces, sequence=list(SEQUENCE), cases=[],
                  source_size=[400, 240], display_size=[800, 480], style=0,
                  script_sha256=sha(__file__), live_helper_sha256=LIVE_HELPER_SHA256,
                  static_helper_sha256=STATIC_HELPER_SHA256,
                  profile_sha256_before=sha(live.PROFILE),
                  note='ABBA schedule; source FPS and completed postprocessed FPS use separate recorded intervals; no captures in timed windows',
                  post_timing_note='post_ack_observed_us is submission-to-observation after input preparation, an upper bound; post_remaining_wait_us is the unhidden CPU wait')
    failure = None
    try:
        record['before'] = q.snapshot('before')
        require(record['before']['post']['active'] == 1 and
                record['before']['post']['snapshot_expirations'] == 0,
                'Expected idle bilinear/style0 without snapshot expirations')
        for index, mode in enumerate(SEQUENCE, 1):
            run_case(live, q, mode, index, record, arguments.candidate_sha256)
        worlds = [case['game_result']['world'] for case in record['cases']]
        require(all(world == worlds[0] for world in worlds), 'Generated MC world identities differ')
        record['matching_world'] = worlds[0]
        record['aggregate'] = aggregate(record['cases'])
        record['passed'] = all(case['passed'] for case in record['cases'])
    except Exception as exc:
        record['error'] = repr(exc)
        failure = exc
    finally:
        try:
            require(all(case.get('children_drained', False) for case in record['cases']),
                    'A child remains alive; no display/profile restoration was attempted')
            require(not live.QUARANTINE.exists() and not q.active_clients(),
                    'Quarantine or a live GPU client prevents restoration')
            require(q.receipt_identity(RUNTIME_SHA256) == identity and
                    candidate_identity(q, arguments.candidate_sha256) == candidate,
                    'Original or candidate identity changed; no restoration was attempted')
            current = live.post_state(q, 'restore-check')
            live.gpu_state(q, 'restore-check', drained=True)
            if current['active'] != 1:
                q.run_logged([q.POST, '--pl-mode', 'bilinear', '--style', '0'], OUT / 'restore-post.log')
            q.private_file(live.PROFILE)
            live.PROFILE.write_bytes(options)
            record['profile_restored'] = live.PROFILE.read_bytes() == options
            require(record['profile_restored'], 'Profile bytes could not be restored')
            record['after'] = q.snapshot('after')
            require(record['after']['post']['active'] == 1 and
                    record['after']['post']['snapshot_expirations'] == 0,
                    'Final POST/lease state differs from the original idle state')
            record['identity_after'] = q.receipt_identity(RUNTIME_SHA256)
            record['candidate_identity_after'] = candidate_identity(q, arguments.candidate_sha256)
            record['spaces_after'] = q.guard_space()
        except Exception as exc:
            record['passed'] = False
            record['cleanup_error'] = repr(exc)
            failure = failure or exc
        q.exclusive_json(OUT / 'result.json', record)
        archive = OUT / 'evidence.tar.gz'
        archive_error = None
        try:
            with archive.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as tar:
                for path in sorted(OUT.rglob('*')):
                    if path.is_file() and not path.is_symlink() and path != archive:
                        tar.add(str(path), arcname=str(path.relative_to(OUT)), recursive=False)
            archive_sha = sha(archive)
        except Exception as exc:
            failure = failure or exc
            archive_sha = None
            archive_error = repr(exc)
        print(json.dumps(dict(passed=record['passed'] and failure is None,
            report=str(OUT / 'result.json'), archive=str(archive), archive_sha256=archive_sha,
            error=record['error'], archive_error=archive_error, cleanup_error=record.get('cleanup_error'),
            aggregate=record.get('aggregate'),
            cases=[dict(run=case['run'], mode=case['mode'], source_fps=case.get('source_fps'),
                        new_output_fps=case.get('new_output_fps')) for case in record['cases']])), flush=True)
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(passed=False, report=None, error=repr(exc))), flush=True)
        raise SystemExit(1)
