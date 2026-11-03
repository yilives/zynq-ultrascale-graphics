"""XTEST injection into an explicitly matched game window."""
import argparse
import ctypes as c
import json
import time


def key(name, hold, window_title):
    title_prefix = 'Quake 3: Arena' if window_title == 'Quake3e' else window_title
    x = c.CDLL('libX11.so.6')
    xt = c.CDLL('libXtst.so.6')
    display = c.c_void_p
    window = c.c_ulong
    x.XOpenDisplay.argtypes = [c.c_char_p]
    x.XOpenDisplay.restype = display
    x.XDefaultRootWindow.argtypes = [display]
    x.XDefaultRootWindow.restype = window
    x.XQueryTree.argtypes = [display, window, c.POINTER(window), c.POINTER(window), c.POINTER(c.POINTER(window)), c.POINTER(c.c_uint)]
    x.XFetchName.argtypes = [display, window, c.POINTER(c.c_void_p)]
    x.XFree.argtypes = [c.c_void_p]
    x.XStringToKeysym.argtypes = [c.c_char_p]
    x.XStringToKeysym.restype = c.c_ulong
    x.XKeysymToKeycode.argtypes = [display, c.c_ulong]
    x.XKeysymToKeycode.restype = c.c_ubyte
    x.XRaiseWindow.argtypes = [display, window]
    x.XSetInputFocus.argtypes = [display, window, c.c_int, c.c_ulong]
    x.XSync.argtypes = [display, c.c_int]
    x.XCloseDisplay.argtypes = [display]
    xt.XTestFakeKeyEvent.argtypes = [display, c.c_uint, c.c_int, c.c_ulong]
    xt.XTestFakeButtonEvent.argtypes = [display, c.c_uint, c.c_int, c.c_ulong]
    xt.XTestQueryExtension.argtypes = [display] + [c.POINTER(c.c_int)] * 4
    d = x.XOpenDisplay(b':0')
    assert d, 'X11 :0 unavailable'
    held = False
    try:
        values = [c.c_int() for _ in range(4)]
        assert xt.XTestQueryExtension(d, *(c.byref(v) for v in values)), 'XTEST unavailable'

        def find(w, depth=0):
            title = c.c_void_p()
            if x.XFetchName(d, w, c.byref(title)) and title.value:
                text = c.string_at(title.value).decode('utf-8', 'replace')
                x.XFree(title)
                if text.lower().startswith(title_prefix.lower()):
                    return w
            if depth >= 8:
                return None
            root, parent, count = window(), window(), c.c_uint()
            children = c.POINTER(window)()
            if not x.XQueryTree(d, w, c.byref(root), c.byref(parent), c.byref(children), c.byref(count)):
                return None
            ids = list(children[:count.value])
            if children:
                x.XFree(children)
            for child in ids:
                found = find(child, depth + 1)
                if found:
                    return found
            return None

        target = find(x.XDefaultRootWindow(d))
        assert target, 'Requested game window not found; no key sent'
        x.XRaiseWindow(d, target)
        x.XSetInputFocus(d, target, 2, 0)
        x.XSync(d, 0)
        if name == 'Close':
            class Data(c.Union):
                _fields_=[('b',c.c_char*20),('s',c.c_short*10),('l',c.c_long*5)]
            class Client(c.Structure):
                _fields_=[('type',c.c_int),('serial',c.c_ulong),('send_event',c.c_int),('display',display),('window',window),('message_type',c.c_ulong),('format',c.c_int),('data',Data)]
            class Event(c.Union):
                _fields_=[('client',Client),('padding',c.c_long*24)]
            x.XInternAtom.argtypes=[display,c.c_char_p,c.c_int]
            x.XInternAtom.restype=c.c_ulong
            x.XSendEvent.argtypes=[display,window,c.c_int,c.c_long,c.POINTER(Event)]
            event=Event()
            event.client.type=33
            event.client.send_event=1
            event.client.display=d
            event.client.window=target
            event.client.message_type=x.XInternAtom(d,b'WM_PROTOCOLS',0)
            event.client.format=32
            event.client.data.l[0]=x.XInternAtom(d,b'WM_DELETE_WINDOW',0)
            assert x.XSendEvent(d,target,0,0,c.byref(event))
            x.XSync(d,0)
            print(json.dumps({'close_window':target,'window_title_prefix':window_title,'protocol':'WM_DELETE_WINDOW'}),flush=True)
            return
        send = xt.XTestFakeButtonEvent if name == 'Button1' else xt.XTestFakeKeyEvent
        code = 1 if name == 'Button1' else x.XKeysymToKeycode(d, x.XStringToKeysym(name.encode('ascii')))
        assert code, 'Unmapped keysym'
        assert send(d, code, 1, 0)
        held = True
        x.XSync(d, 0)
        time.sleep(hold)
        assert send(d, code, 0, 0)
        held = False
        x.XSync(d, 0)
        print(json.dumps({'key': name, 'hold_s': hold, 'window': target, 'window_title_prefix': window_title, 'x11_xtest': True, 'monotonic_s': time.monotonic()}), flush=True)
    finally:
        if held:
            send(d, code, 0, 0)
            x.XSync(d, 0)
        x.XCloseDisplay(d)


p = argparse.ArgumentParser(description="Inject XTEST keys into a named game window only")
p.add_argument("operation", choices=("key", "click", "close"))
p.add_argument("name", nargs="?", default="Return")
p.add_argument("--hold", type=float, default=0.12)
p.add_argument("--window", choices=("Tuxracer", "Neverball", "Neverputt", "Quakespasm", "Quake3e", "Minecraft", "RasterIX Arcade", "rRootage", "RasterIX · 游戏库"), default="Tuxracer")
a=p.parse_args()
assert 0.01 <= a.hold <= 10
key("Close" if a.operation=="close" else "Button1" if a.operation=="click" else a.name, a.hold, a.window)
