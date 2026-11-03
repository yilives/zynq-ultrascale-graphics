#!/usr/bin/env python3
"""Bounded MC bilinear / FPGA FSR comparison, after fixed-v23 static QA passes.

Importing is device-free. Run explicitly as root on the board; all device
control uses reviewed command-line programs, never Python register access.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import time

OUT = Path('/tmp/postproc-tests/fsr-pl-live-v23')
STATIC_RESULT = Path('/tmp/postproc-tests/fsr-pl-v23/result.json')
STATIC_HELPER_SHA256 = '3f8ea9d72d2e158d82844a026db9566dbdc10735c3d5eabfc83cecf306cd9aab'
RUNTIME_SHA256 = '94fc82f8e7aa5a123bc15151bfa13adb6362f8196d565132a18abbb61fbc5bb2'
PROFILE = Path('/opt/rasterix/classicube/profile/options.txt')
QUARANTINE = Path('/tmp/rix-fsr-pl.quarantine')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def helper():
    path = Path(__file__).with_name('test_fsr_pl_board_v23.py')
    require(sha(path) == STATIC_HELPER_SHA256, 'Static QA helper is missing or changed')
    spec = importlib.util.spec_from_file_location('fixed_v23_static_qa', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    return module


def wait_until(predicate, seconds, message):
    deadline = time.monotonic() + seconds
    while not predicate():
        require(not QUARANTINE.exists(), 'FSR quarantine detected; no further GPU task is allowed')
        require(time.monotonic() < deadline, message)
        time.sleep(.1)


def gpu_state(q, label, drained=False):
    value = json.loads(q.run_logged(['plgpuctl', 'status'], OUT / (label + '-gpu.log')))
    require(value['status'] == 3 and value['config'] == 0x9adb505e,
            'GPU/MIG status or configuration mismatch')
    require(all(value[key] == 0 for key in q.ERRORS), 'GPU fault counter is nonzero')
    if drained:
        q.check_gpu(value)
    return value


def post_state(q, label):
    value = q.json_line(q.run_logged([q.POST, '--status'], OUT / (label + '-post.log')))
    require(value['requested'] == value['active'] and value['snapshot_status'] == 0,
            'POST switch or snapshot lease remains active')
    return value


def validate_static(q, identity):
    q.private_file(STATIC_RESULT)
    result = json.loads(STATIC_RESULT.read_text())
    require(result.get('format') == 'rix-fsr-pl-fixed-v23-board-qa' and result.get('passed') is True,
            'A genuinely passing fixed-v23 static QA result is required')
    require(result.get('script_sha256') == STATIC_HELPER_SHA256 and
            result.get('identity') == identity and result.get('identity_after') == identity,
            'Static QA identities do not match this boot / runtime / bitstream')
    cases = result.get('cases', [])
    require(len(cases) == 3 and {row['scene'] for row in cases} == set(q.IDENTITIES),
            'Static QA did not validate all three MC scenes')
    require(all(row['comparison']['pixels'] == 384000 and row['comparison']['mismatches'] == 0
                for row in cases), 'Static full-frame QA did not pass')
    lcd = result.get('lcd') or {}
    require(lcd.get('samples') == 6000 and lcd.get('mismatches') == 0 and
            lcd.get('full_frame', {}).get('mismatches') == 0, 'Static LCD QA did not pass')
    return dict(path=str(STATIC_RESULT), sha256=sha(STATIC_RESULT), identity=identity)


def drain(process, role, record):
    """Never turn an uncertain AXI owner into an unlocked, reusable resource."""
    if process is None:
        return True
    if process.poll() is None:
        if role == 'runtime' and QUARANTINE.exists():
            record['preserved_runtime_pid'] = process.pid
            return False
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            record['preserved_' + role + '_pid'] = process.pid
            return False
    record[role + '_exit'] = process.returncode
    return True


def copy_game_evidence(attempt, mode):
    source = Path('/tmp/postproc-tests') / attempt
    target = OUT / (mode + '-game')
    target.mkdir(mode=0o700)
    copied = {}
    for name in ('result.json', 'game.log', 'dependencies.log'):
        path = source / name
        if path.is_file() and not path.is_symlink():
            with (target / name).open('xb') as stream:
                stream.write(path.read_bytes())
            copied[name] = sha(target / name)
    return dict(original_directory=str(source), copied_directory=str(target), files=copied)


def validate_runtime(stats):
    require(stats['frames'] > 0 and 19.9 <= stats['elapsed_seconds'] <= 30 and
            stats['processed_fps'] > 0 and stats['input_load_us'] > 0 and
            stats['compute_us'] > 0 and stats['snapshot_retries'] == 0 and
            stats['cpu_pixel_processing_live'] is False, 'Unexpected FPGA FSR live statistics')
    require(abs(stats['frames'] / stats['elapsed_seconds'] - stats['processed_fps']) < .01,
            'Runtime output FPS is inconsistent with frame count and duration')
    return stats


def run_case(q, mode, record, hold_seconds):
    # The launcher has a fixed /tmp/postproc-tests/<attempt> log root and forbids
    # slashes. Preserve its unique directory and copy its evidence into OUT.
    attempt = OUT.name + '_' + mode.replace('-', '_')
    attempt_path = Path('/tmp/postproc-tests') / attempt
    require(not attempt_path.exists() and not attempt_path.with_suffix('.tar.gz').exists(),
            'Launcher attempt already exists: ' + attempt)
    require(q.receipt_identity(RUNTIME_SHA256) == record['identity'], 'Load identity changed')
    require(not q.active_clients(), 'Another GPU client is active before this case')
    q.guard_space()
    command = ['rix-classicube', '--seconds', '32', '--world-size', '64', '--view-distance', '32',
               '--fps-limit', '120', '--autoplay', '--attempt', attempt]
    case = dict(mode=mode, attempt=attempt, command=command, passed=False,
                source_size=[400, 240], display_size=[800, 480], style=0)
    record['cases'].append(case)
    game = runtime = None
    runtime_log = None
    try:
        with (OUT / (mode + '-launcher.log')).open('x') as log:
            env = os.environ.copy()
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            game = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
            case['game_pid'] = game.pid
            game_log = attempt_path / 'game.log'

            def measured():
                require(game.poll() is None, 'MC launcher exited before measurement began')
                return game_log.exists() and 'RIX_MEASURE_BEGIN' in game_log.read_text(errors='replace')

            wait_until(measured, 50, 'MC startup did not reach RIX_MEASURE_BEGIN')
            time.sleep(1)
            require(game.poll() is None, 'MC ended before the source measurement window')
            if mode == 'bilinear':
                # The public launcher initially requests nearest/style0. Use
                # its existing ownership-aware CLI before starting the window.
                q.run_logged([q.POST, '--pl-mode', 'bilinear', '--style', '0'],
                             OUT / 'bilinear-select.log')
                require(post_state(q, 'bilinear-selected')['active'] == 1,
                        'Bilinear baseline was not activated')
            else:
                require(post_state(q, 'fsr-pl-launcher-ready')['active'] == 0,
                        'Expected the launcher nearest/style0 mode before FSR takes ownership')
            case['window_before'] = gpu_state(q, mode + '-window-before')
            started = time.monotonic()
            if mode == 'bilinear':
                deadline = started + 20
                while time.monotonic() < deadline:
                    require(game.poll() is None and not QUARANTINE.exists(),
                            'Game ended or FSR was quarantined during baseline measurement')
                    time.sleep(min(.1, max(0, deadline - time.monotonic())))
            else:
                runtime_command = [str(q.RUNTIME), '--live', '--seconds', '20']
                if hold_seconds:
                    runtime_command += ['--hold-seconds', str(hold_seconds)]
                case['runtime_command'] = runtime_command
                runtime_path = OUT / 'fsr-pl-runtime.log'
                runtime_log = runtime_path.open('x')
                runtime = subprocess.Popen(runtime_command, stdout=runtime_log,
                                           stderr=subprocess.STDOUT, env=env)
                case['runtime_pid'] = runtime.pid

                def have_stats():
                    text = runtime_path.read_text()
                    if any(line.startswith('{') for line in text.splitlines()):
                        return True
                    require(runtime.poll() is None, 'FSR runtime exited without statistics')
                    require(game.poll() is None, 'MC stopped during the FSR output window')
                    return False

                wait_until(have_stats, 35, 'FSR runtime exceeded its bounded output window')
                case['runtime'] = validate_runtime(q.json_line(runtime_path.read_text()))
            case['window_after'] = gpu_state(q, mode + '-window-after')
            elapsed = time.monotonic() - started
            case['source_window_seconds'] = elapsed
            case['source_frames'] = (case['window_after']['presented'] -
                                     case['window_before']['presented']) & 0xffffffff
            require(case['source_frames'] > 0, 'No new RasterIX source frames')
            require(case['source_frames'] < 10000,
                    'Implausible source counter delta; reset/wrap discontinuity suspected')
            case['source_fps'] = case['source_frames'] / elapsed
            if mode == 'bilinear':
                case['new_output_fps'] = case['source_fps']
                case['new_output_frames'] = case['source_frames']
                case['new_output_window_seconds'] = elapsed
                case['new_output_basis'] = 'Every new source is scaled by streaming PL bilinear'
            else:
                stats = case['runtime']
                case['new_output_fps'] = stats['processed_fps']
                case['new_output_frames'] = stats['frames']
                case['new_output_window_seconds'] = stats['elapsed_seconds']
                case['average_input_load_ms'] = stats['input_load_us'] / stats['frames'] / 1000
                case['average_compute_ms'] = stats['compute_us'] / stats['frames'] / 1000
                case['new_output_basis'] = 'Completed and presented PL EASU12+RCAS5 frames'
                wait_until(lambda: runtime.poll() is not None, hold_seconds + 10,
                           'FSR runtime did not restore POST after measurement')
                require(runtime.returncode == 0, 'FSR runtime did not exit cleanly')
                require(post_state(q, 'fsr-pl-runtime-after')['active'] == 0,
                        'FSR did not restore the launcher nearest/style0 mode')
            wait_until(lambda: game.poll() is not None, 45, 'MC launcher did not finish its bounded run')
            case['game_exit'] = game.returncode
            result_path = attempt_path / 'result.json'
            require(result_path.is_file(), 'MC launcher result is missing')
            game_result = case['game_result'] = json.loads(result_path.read_text())
            require(game.returncode == 0 and game_result.get('passed') is True and
                    game_result.get('exit_code') == 0 and game_result.get('world'),
                    'The game or launcher validation failed')
            require(game_result['boot_id'] == record['identity']['boot_id'] and
                    game_result['world_size'] == 64 and game_result['view_distance'] == 32 and
                    game_result['fps_limit'] == 120, 'Game scene or boot settings differ')
            case['after'] = q.snapshot(mode + '-case-after')
            require(case['after']['post']['active'] == 1 and
                    case['after']['post']['snapshot_expirations'] == record['before']['post']['snapshot_expirations'],
                    'Launcher did not restore POST or the snapshot lease expired')
            require(q.receipt_identity(RUNTIME_SHA256) == record['identity'],
                    'Load identity changed during the game')
            case['passed'] = True
    finally:
        # Stop the renderer promptly if anything goes wrong; an uncertain FSR
        # master keeps its own flock and must never be killed to release it.
        game_drained = drain(game, 'game', case)
        runtime_drained = drain(runtime, 'runtime', case)
        case['children_drained'] = game_drained and runtime_drained
        if runtime_log is not None:
            runtime_log.close()
        if attempt_path.is_dir():
            case['evidence'] = copy_game_evidence(attempt, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hold-seconds', type=float, default=0,
                        help='Optional FSR last-frame hold after its measured 20-second window (0..5)')
    arguments = parser.parse_args()
    require(0 <= arguments.hold_seconds <= 5, 'Invalid optional last-frame hold')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    q = helper()
    identity = q.receipt_identity(RUNTIME_SHA256)
    static = validate_static(q, identity)
    spaces = q.guard_space()
    require(not q.active_clients(), 'A GPU client is already active')
    q.private_file(PROFILE)
    options = PROFILE.read_bytes()
    OUT.mkdir(mode=0o700)
    with (OUT / 'options.before').open('xb') as stream:
        stream.write(options)
    record = dict(format='rix-fsr-pl-fixed-v23-live-comparison', passed=False, error=None,
                  identity=identity, static_qa=static, spaces_before=spaces, cases=[],
                  source_size=[400, 240], display_size=[800, 480], style=0,
                  script_sha256=sha(__file__), static_helper_sha256=STATIC_HELPER_SHA256,
                  profile_sha256_before=sha(PROFILE), hold_seconds=arguments.hold_seconds,
                  note='Source render FPS and new postprocessed output FPS use separately recorded intervals; no capture in the timed window')
    failure = None
    try:
        record['before'] = q.snapshot('before')
        require(record['before']['post']['active'] == 1 and
                record['before']['post']['snapshot_expirations'] == 0,
                'Expected idle bilinear/style0 without snapshot expirations')
        for mode in ('bilinear', 'fsr-pl'):
            run_case(q, mode, record, arguments.hold_seconds)
        worlds = [case['game_result']['world'] for case in record['cases']]
        require(worlds[0] == worlds[1], 'The two generated MC world identities differ')
        record['matching_world'] = worlds[0]
        record['passed'] = all(case['passed'] for case in record['cases'])
    except Exception as exc:
        record['error'] = repr(exc)
        failure = exc
    finally:
        try:
            require(all(case.get('children_drained', False) for case in record['cases']),
                    'A child remains alive; no display/profile restoration was attempted')
            require(not QUARANTINE.exists() and not q.active_clients(),
                    'Quarantine or a live GPU client prevents restoration')
            require(q.receipt_identity(RUNTIME_SHA256) == identity,
                    'Load identity changed; no restoration was attempted')
            # The launcher normally restores bilinear itself. Only ask its
            # existing lock-aware CLI to restore if that mode is not active.
            current = post_state(q, 'restore-check')
            gpu_state(q, 'restore-check', drained=True)
            if current['active'] != 1:
                q.run_logged([q.POST, '--pl-mode', 'bilinear', '--style', '0'],
                             OUT / 'restore-post.log')
            q.private_file(PROFILE)
            PROFILE.write_bytes(options)
            record['profile_restored'] = PROFILE.read_bytes() == options
            require(record['profile_restored'], 'Profile bytes could not be restored')
            record['after'] = q.snapshot('after')
            require(record['after']['post']['active'] == 1 and
                    record['after']['post']['snapshot_expirations'] == record['before']['post']['snapshot_expirations'],
                    'Final POST/lease state differs from the original idle state')
            record['identity_after'] = q.receipt_identity(RUNTIME_SHA256)
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
        summary = dict(passed=record['passed'] and failure is None,
                       report=str(OUT / 'result.json'), archive=str(archive),
                       archive_sha256=archive_sha, error=record['error'],
                       archive_error=archive_error,
                       cleanup_error=record.get('cleanup_error'),
                       cases=[dict(mode=case['mode'], source_fps=case.get('source_fps'),
                                   new_output_fps=case.get('new_output_fps')) for case in record['cases']])
        print(json.dumps(summary), flush=True)
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps(dict(passed=False, report=None, error=repr(exc))), flush=True)
        raise SystemExit(1)
