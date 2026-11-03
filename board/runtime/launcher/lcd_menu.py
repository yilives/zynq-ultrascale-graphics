#!/usr/bin/env python3
"""Exclusive, opt-in RasterIX LCD menu presenter.

The producer publishes a whole 800x480 RGB565 file with atomic rename. We own
that CPU copy; no live PL framebuffer is read here. The established v23 render
size is 400x240, so the LCD menu uses a 2x nearest presentation. This is separate
from the future PS DRM/miniDP backend.
"""
import argparse
from array import array
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

LIBRARY_SHA = 'f042f8a4f7f2751557a48ebcf66d9d6abe20981168de32ee8067ffe3c0678bc1'
RUNTIME_ARCHIVE_SHA = '6d35f2b7bafbf054b1a32c44cd4a3c9d71add5010bb91702db3be60d1f428269'
WIDTH, HEIGHT, TILE = 400, 240, 128


def check_post(value, mode):
    assert value['requested'] == value['active'] == mode, 'Unexpected POST mode/style'
    assert value['snapshot_status'] == value['snapshot_expirations'] == 0, 'Snapshot lease/expiry must be clear'


def source_rgb(raw):
    if len(raw) != 800 * 480 * 2:
        raise ValueError('LCD menu requires one complete 800x480 RGB565 frame')
    pixels = array('H')
    pixels.frombytes(raw)
    if sys.byteorder != 'little':
        pixels.byteswap()
    rgb = bytearray(WIDTH * HEIGHT * 3)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            value = pixels[(y * 2 + 1) * 800 + x * 2 + 1]
            offset = (y * WIDTH + x) * 3
            # Replicate component high bits when expanding 565 to RGB8.
            r, g, b = (value >> 11) & 31, (value >> 5) & 63, value & 31
            rgb[offset:offset + 3] = bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
    return rgb


def tiles(rgb):
    assert len(rgb) == WIDTH * HEIGHT * 3
    for y in range(0, HEIGHT, TILE):
        for x in range(0, WIDTH, TILE):
            width, height = min(TILE, WIDTH - x), min(TILE, HEIGHT - y)
            data = bytearray(TILE * TILE * 3)
            for row in range(height):
                start = ((y + row) * WIDTH + x) * 3
                data[row * TILE * 3:row * TILE * 3 + width * 3] = rgb[start:start + width * 3]
            yield x, y, width, height, data


def bind(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, list(args)
    return fn


class Renderer:
    def __init__(self, library):
        self.x = self.gl = None
        self.display = self.window = self.visual = self.context = None
        p, i, u, w = c.c_void_p, c.c_int, c.c_uint, c.c_ulong
        self.x = c.CDLL('libX11.so.6')
        self.display = bind(self.x, 'XOpenDisplay', p, c.c_char_p)(b':0')
        assert self.display, 'X11 :0 is unavailable'
        screen = bind(self.x, 'XDefaultScreen', i, p)(self.display)
        root = bind(self.x, 'XRootWindow', w, p, i)(self.display, screen)
        # An unmapped drawable keeps the real SDL menu as the input-focus owner.
        self.window = bind(self.x, 'XCreateSimpleWindow', w, p, w, i, i, u, u, u, w, w)(self.display, root, 0, 0, WIDTH, HEIGHT, 0, 0, 0)
        assert self.window
        self.gl = c.CDLL(str(library))
        attributes = (i * 11)(4, 5, 8, 5, 9, 6, 10, 5, 12, 16, 0)
        self.visual = bind(self.gl, 'glXChooseVisual', p, p, i, c.POINTER(i))(self.display, screen, attributes)
        assert self.visual, 'No accepted RasterIX visual'
        self.context = bind(self.gl, 'glXCreateContext', p, p, p, p, i)(self.display, self.visual, None, 1)
        assert self.context
        assert bind(self.gl, 'glXMakeCurrent', i, p, w, p)(self.display, self.window, self.context)
        self.textures = (u * 8)()
        self.call('GenTextures', None, [i, c.POINTER(u)], 8, self.textures)

    def call(self, name, result, args, *values):
        return bind(self.gl, 'gl' + name, result, *args)(*values)

    def draw(self, rgb, present=True):
        i, u, f, d, p = c.c_int, c.c_uint, c.c_float, c.c_double, c.c_void_p
        for cap in (0xb71, 0xbe2, 0xb60, 0xb50, 0xb44, 0xc11):
            self.call('Disable', None, [u], cap)
        self.call('Viewport', None, [i] * 4, 0, 0, WIDTH, HEIGHT)
        self.call('MatrixMode', None, [u], 0x1701)
        self.call('LoadIdentity', None, [])
        self.call('Ortho', None, [d] * 6, 0, WIDTH, HEIGHT, 0, -1, 1)
        self.call('MatrixMode', None, [u], 0x1700)
        self.call('LoadIdentity', None, [])
        self.call('ClearColor', None, [f] * 4, 0, 0, 0, 1)
        self.call('Clear', None, [u], 0x4100)
        self.call('Enable', None, [u], 0xde1)
        self.call('Color4f', None, [f] * 4, 1, 1, 1, 1)
        self.call('TexEnvi', None, [u, u, i], 0x2300, 0x2200, 0x1e01)
        self.call('PixelStorei', None, [u, i], 0xcf5, 1)
        for index, (x, y, width, height, data) in enumerate(tiles(rgb)):
            self.call('BindTexture', None, [u, u], 0xde1, self.textures[index])
            for setting in (0x2800, 0x2801):
                self.call('TexParameteri', None, [u, u, i], 0xde1, setting, 0x2600)
            storage = (c.c_ubyte * len(data)).from_buffer(data)
            self.call('TexImage2D', None, [u, i, i, i, i, i, u, u, p], 0xde1, 0, 0x1907, TILE, TILE, 0, 0x1907, 0x1401, storage)
            self.call('Begin', None, [u], 7)
            for vx, vy, tx, ty in ((x, y, 0, 0), (x + width, y, width / TILE, 0),
                                   (x + width, y + height, width / TILE, height / TILE), (x, y + height, 0, height / TILE)):
                self.call('TexCoord2f', None, [f, f], tx, ty)
                self.call('Vertex2f', None, [f, f], vx, vy)
            self.call('End', None, [])
        self.call('Finish', None, [])
        assert self.call('GetError', u, []) == 0, 'RasterIX menu GL error'
        if present:
            bind(self.gl, 'glXSwapBuffers', None, p, c.c_ulong)(self.display, self.window)
            self.call('Finish', None, [])

    def close(self):
        p, i, w = c.c_void_p, c.c_int, c.c_ulong
        if self.context:
            self.call('Finish', None, [])
            bind(self.gl, 'glXMakeCurrent', i, p, w, p)(self.display, 0, None)
            bind(self.gl, 'glXDestroyContext', None, p, p)(self.display, self.context)
            self.context = None
        if self.visual:
            bind(self.x, 'XFree', i, p)(self.visual)
        if self.window:
            bind(self.x, 'XDestroyWindow', i, p, w)(self.display, self.window)
        if self.display:
            bind(self.x, 'XCloseDisplay', i, p)(self.display)
        if self.gl:
            # The GLX library owns the global renderer; unload it while all
            # hardware locks are still held, including its normal destructor.
            from _ctypes import dlclose
            dlclose(self.gl._handle)
            self.gl = None


def worker(frame, state, token):
    from java_profile import LOCK_NAMES, OLD_BIT, sha
    from play_game import acquire
    sys.path.insert(0, '/opt/rasterix/experimental')
    import rasterix_games as games
    from game_runtime_support import DisplayStatus, GpuRecoveryGuard
    assert os.geteuid() == 0
    os.umask(0o077)
    guard = GpuRecoveryGuard()
    locks = {}
    renderer = None
    stopped = False
    touched = False
    record = dict(passed=False, phase='starting', token=token, pid=os.getpid(), frames=0,
                  output='RGB LCD', source=[800, 480], render=[WIDTH, HEIGHT], dp_output=False,
                  gpu_touched=False, post_changed=False, post_restored=False)
    def save():
        pending = state.with_name(state.name + '.new')
        pending.write_text(json.dumps(record, indent=2) + '\n')
        pending.replace(state)
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    def status():
        item = DisplayStatus()
        try:
            value = item.read()
            assert value['status'] == 3 and all(value[k] == 0 for k in games.ERRORS)
            return value
        finally:
            item.close()
    def drain():
        until = time.monotonic() + 5
        while True:
            value = status()
            if len({value[k] for k in ('frame_id', 'swap', 'copy', 'presented', 'last_presented')}) == 1:
                return value
            if time.monotonic() >= until:
                raise RuntimeError('LCD menu GPU queue did not drain')
            time.sleep(.05)
    def post_status():
        return json.loads(subprocess.check_output([games.POST, '--status'], text=True, timeout=5))
    def set_post(mode):
        locks.pop('rix-superres.lock').close()
        try:
            subprocess.run([games.POST, '--pl-mode', 'nearest' if mode == 0 else 'bilinear', '--style', '0'],
                           check=True, stdout=subprocess.DEVNULL, timeout=5)
        finally:
            locks['rix-superres.lock'] = acquire('rix-superres.lock')
        value = post_status()
        check_post(value, mode)
        return value
    try:
        for name in LOCK_NAMES:
            locks[name] = acquire(name)
        guard.check()
        rows = Path('/tmp/rix-fpga-fsr/active-receipt.txt').read_text().splitlines()
        assert rows[0] == 'RIX_FSR_PL_ACTIVE_V1' and rows[2] == OLD_BIT
        assert rows[1] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        record['boot_id'] = rows[1]
        record['before'] = drain()
        record['post_before'] = post_status()
        check_post(record['post_before'], 1)
        assert subprocess.run(['pidof', *games.CLIENTS, 'java', 'ClassiCube', 'rix-fsr-pl', 'rix-neural-style'], stdout=subprocess.PIPE).returncode == 1
        library = Path(__file__).resolve().parent / 'menu/libGL.so.1'
        assert sha(library) == LIBRARY_SHA, 'Unapproved menu GL library'
        record['menu_library_sha256'] = LIBRARY_SHA
        # POST controller acquires its own lock. Keep both profile locks while
        # lending POST, then reclaim it before any menu rendering begins.
        record['post_changed'] = True
        set_post(0)
        subprocess.run(['plgpuctl', 'enable'], check=True, stdout=subprocess.DEVNULL)
        last = None
        deadline = time.monotonic() + 15
        while not stopped:
            try:
                info = frame.stat()
                stamp = (info.st_ino, info.st_mtime_ns, info.st_size)
                if stamp != last:
                    assert not frame.is_symlink() and info.st_uid == os.geteuid()
                    rgb = source_rgb(frame.read_bytes())
                    if renderer is None:
                        touched = True
                        record['gpu_touched'] = True
                        save()
                        renderer = Renderer(library)
                    renderer.draw(rgb)
                    record['after'] = drain()
                    record['frames'] += 1
                    record.update(phase='ready', passed=True, frame_sha256=hashlib.sha256(rgb).hexdigest())
                    save()
                    last = stamp
            except FileNotFoundError:
                if time.monotonic() > deadline:
                    raise RuntimeError('UI did not publish a menu frame')
            time.sleep(.1)
        if renderer is not None:
            renderer.close()
            renderer = None
        record['after'] = drain()
        record['post_after'] = set_post(1)
        record['post_restored'] = True
        record.update(passed=True, phase='released')
    except BaseException as exc:
        record.update(passed=False, phase='error', error=repr(exc))
        if touched:
            guard.mark('lcd-menu-' + token, dict(reason=repr(exc), exit_code=2, transport_errors=True, after=record.get('after')))
        elif record['post_changed'] and set(locks) == set(LOCK_NAMES):
            try:
                record['post_after'] = set_post(1)
                record['post_restored'] = True
            except BaseException as restore:
                record['restore_error'] = repr(restore)
    finally:
        if renderer is not None:
            try:
                renderer.close()
            except BaseException as exc:
                record.update(passed=False, phase='error', close_error=repr(exc))
        save()
        # The parent must observe process exit, never just a ready-file update,
        # before starting the game. Do not SIGKILL this graphics owner.
        for stream in locks.values():
            stream.close()
    print('LAUNCHER_LCD_MENU_RESULT ' + json.dumps(record), flush=True)
    return 0 if record['passed'] else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--frame', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    assert len(args.token) == 32 and all(c in '0123456789abcdef' for c in args.token)
    raise SystemExit(worker(args.frame, args.state, args.token))
