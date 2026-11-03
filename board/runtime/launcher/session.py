#!/usr/bin/env python3
"""One command starts UI, controller and board keyboard return observer.

LCD presentation is explicitly opt-in until board acceptance. The default
preview never opens GPU, evdev, PL registers or DRM.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from launcher_control import exchange


def run(args):
    app = Path(__file__).resolve().parent
    assert not args.lcd_menu or args.board
    assert not args.qa_sdl_dummy or args.qa_seconds > 0
    if args.board:
        assert os.geteuid() == 0
    os.umask(0o077)
    work = Path('/tmp') / ('rix-menu-session-' + uuid.uuid4().hex)
    work.mkdir(mode=0o700)
    socket = work / 'control.sock'
    frame = work / 'menu.rgb565'
    record = dict(passed=False, board=args.board, lcd_menu=args.lcd_menu, output_validated=False,
                  work=str(work), processes={}, error=None)
    children, logs = {}, []
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    def spawn(name, command, env=None):
        log = (work / (name + '.log')).open('xb')
        logs.append(log)
        children[name] = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    started = time.monotonic()
    try:
        control = [sys.executable, str(app / 'launcher_control.py'), '--socket', str(socket)]
        if args.board:
            control += ['--board']
        if args.lcd_menu:
            control += ['--lcd-menu', '--frame-input', str(frame)]
        spawn('control', control + ['serve'])
        until = time.monotonic() + 10
        while not socket.exists():
            assert children['control'].poll() is None and time.monotonic() < until
            if stopped:
                return 2
            time.sleep(.05)
        env = dict(os.environ, DISPLAY=':0', SDL_VIDEODRIVER='dummy' if args.qa_sdl_dummy else 'x11')
        state = args.state_dir or (Path('/opt/rasterix/experimental/profiles/launcher') if args.board else work / 'ui-state')
        ui = [str(app / 'rix-launcher'), '--assets', str(app / 'assets'), '--socket', str(socket),
              '--size', '800x480' if args.lcd_menu else args.size, '--state-dir', str(state), '--frame-output', str(frame)]
        if args.lcd_menu:
            ui += ['--input-size', '400x240']
        spawn('ui', ui, env)
        if args.board:
            spawn('input', [sys.executable, str(app / 'global_input.py'), '--socket', str(socket)])
        print('LAUNCHER_SESSION_READY ' + json.dumps(dict(work=str(work), socket=str(socket),
              mode='board' if args.board else 'preview', lcd_menu=args.lcd_menu)), flush=True)
        while not stopped:
            for name, child in children.items():
                code = child.poll()
                if code is not None:
                    if name == 'ui' and code == 0:
                        stopped = True
                        break
                    raise RuntimeError(name + ' exited unexpectedly: ' + str(code))
            if args.qa_seconds and time.monotonic() - started >= args.qa_seconds:
                stopped = True
            time.sleep(.1)
        record['last_status'] = exchange(socket, 'STOP')
        if record['last_status'].get('phase') == 'error':
            raise RuntimeError('Controller blocked return after an unconfirmed renderer exit')
        record['passed'] = True
    except BaseException as exc:
        record['error'] = repr(exc)
    finally:
        # The controller owns the normal hardware shutdown ordering. It must
        # finish before the UI/input session is torn down. Never force-kill it.
        control = children.get('control')
        if control is not None and control.poll() is None:
            control.terminate()
            try:
                code = control.wait(timeout=110)
                if code != 0:
                    record.update(passed=False, error='Controller could not confirm normal hardware shutdown')
            except subprocess.TimeoutExpired:
                record.update(passed=False, error='Controller still draining hardware; process left alive')
        for name in ('input', 'ui'):
            child = children.get(name)
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    record.update(passed=False, error=name + ' did not stop; process left alive')
        for name, child in children.items():
            record['processes'][name] = dict(pid=child.pid, exit_code=child.poll())
        for log in logs:
            log.close()
        record['elapsed_seconds'] = time.monotonic() - started
        (work / 'session.json').write_text(json.dumps(record, indent=2) + '\n')
        print('LAUNCHER_SESSION_RESULT ' + json.dumps(record), flush=True)
    return 0 if record['passed'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', action='store_true')
    parser.add_argument('--lcd-menu', action='store_true', help='Experimental PL LCD presenter')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--size', default='1920x1080', choices=('800x480', '1920x1080'))
    parser.add_argument('--qa-seconds', type=float, default=0)
    parser.add_argument('--qa-sdl-dummy', action='store_true')
    args = parser.parse_args()
    assert 0 <= args.qa_seconds <= 3600
    raise SystemExit(run(args))
