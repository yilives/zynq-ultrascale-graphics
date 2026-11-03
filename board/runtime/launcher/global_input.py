#!/usr/bin/env python3
"""Observe keyboard evdev events without grabbing them; Ctrl+Alt+M requests STOP.

No keys or pointer events are injected. Game shutdown and GPU drain stay in the
existing controller/runner. Devices may appear after the menu has started.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import selectors
import signal
import struct
import time

from launcher_control import exchange

EV_SYN, EV_KEY = 0, 1
SYN_REPORT, SYN_DROPPED = 0, 3
KEY_A, KEY_M = 30, 50
CTRL, ALT = {29, 97}, {56, 100}
EVENT = struct.Struct('@llHHi')
KEY_BYTES = 96
EVIOCGKEY = 0x80000000 | (KEY_BYTES << 16) | (ord('E') << 8) | 0x18


def bitmap_keys(raw):
    return {index * 8 + bit for index, value in enumerate(raw)
            for bit in range(8) if value & (1 << bit)}


def keyboard_capability(text, word_bits=struct.calcsize('L') * 8):
    """sysfs prints native-word bitmaps most-significant word first."""
    try:
        mask = 0
        for word in text.split():
            mask = (mask << word_bits) | int(word, 16)
        return all(mask & (1 << key) for key in (KEY_A, KEY_M, 28, 57))
    except ValueError:
        return False


class Chord:
    def __init__(self):
        self.devices = {}
        self.dropped = set()
        self.presses = 0

    def attach(self, device, held=()):
        self.devices[device] = set(held)
        self.dropped.discard(device)

    def remove(self, device):
        self.devices.pop(device, None)
        self.dropped.discard(device)

    def feed(self, device, kind, code, value):
        if device not in self.devices:
            return False
        if kind == EV_SYN and code == SYN_DROPPED:
            self.devices[device].clear()
            self.dropped.add(device)
            return False
        if device in self.dropped or kind != EV_KEY:
            return False
        held = self.devices[device]
        previous = code in held
        if value == 0:
            held.discard(code)
        elif value in (1, 2):
            held.add(code)
        # A fresh M down is required. Neither typematic nor reconnecting with
        # an already-held chord may close another game.
        all_held = set().union(*self.devices.values())
        if code == KEY_M and value == 1 and not previous and all_held & CTRL and all_held & ALT:
            self.presses += 1
            return True
        return False


class EventStream:
    def __init__(self):
        self.pending = b''

    def feed(self, raw):
        self.pending += raw
        count = len(self.pending) // EVENT.size
        ready, self.pending = self.pending[:count * EVENT.size], self.pending[count * EVENT.size:]
        return [EVENT.unpack_from(ready, i)[2:] for i in range(0, len(ready), EVENT.size)]


def held_keys(fd):
    raw = bytearray(KEY_BYTES)
    fcntl.ioctl(fd, EVIOCGKEY, raw, True)
    return bitmap_keys(raw)


def run(socket_path, input_dir=Path('/dev/input'), sys_dir=Path('/sys/class/input')):
    assert os.geteuid() == 0, 'evdev monitor requires board root'
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    chord = Chord()
    devices = {}
    selector = selectors.DefaultSelector()
    next_scan = 0
    def remove(path):
        fd, _ = devices.pop(path)
        selector.unregister(fd)
        os.close(fd)
        chord.remove(path)
    print('LAUNCHER_GLOBAL_INPUT_READY no-grab Ctrl+Alt+M', flush=True)
    try:
        while not stopped:
            if time.monotonic() >= next_scan:
                candidates = set(input_dir.glob('event*'))
                for path in list(devices):
                    if path not in candidates:
                        remove(path)
                for path in sorted(candidates - devices.keys()):
                    fd = None
                    try:
                        caps = (sys_dir / path.name / 'device/capabilities/key').read_text()
                        if not keyboard_capability(caps):
                            continue
                        fd = os.open(str(path), os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                        chord.attach(path, held_keys(fd))
                        selector.register(fd, selectors.EVENT_READ, path)
                        devices[path] = (fd, EventStream())
                        print('LAUNCHER_KEYBOARD_ATTACHED ' + str(path), flush=True)
                    except (OSError, ValueError):
                        chord.remove(path)
                        if fd is not None:
                            os.close(fd)
                next_scan = time.monotonic() + 1
            for key, _ in selector.select(.2):
                path = key.data
                fd, stream = devices[path]
                try:
                    raw = os.read(fd, EVENT.size * 64)
                    if not raw:
                        remove(path)
                        continue
                    for kind, code, value in stream.feed(raw):
                        if kind == EV_SYN and code == SYN_REPORT and path in chord.dropped:
                            chord.attach(path, held_keys(fd))
                            continue
                        if chord.feed(path, kind, code, value):
                            try:
                                reply = exchange(socket_path, 'STOP')
                                print('LAUNCHER_GLOBAL_RETURN ' + json.dumps(reply), flush=True)
                            except (OSError, RuntimeError):
                                print('LAUNCHER_GLOBAL_RETURN_SERVICE_UNAVAILABLE', flush=True)
                except BlockingIOError:
                    continue
                except OSError:
                    remove(path)
    finally:
        for path in list(devices):
            remove(path)
        selector.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--socket', required=True, type=Path)
    args = parser.parse_args()
    run(args.socket)
