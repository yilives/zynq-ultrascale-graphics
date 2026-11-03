#!/usr/bin/env python3
"""Same-UID Unix control service; preview mode never starts a game process."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import time
import uuid
from library_games import EXPANSION,CLIENTS as EXPANSION_CLIENTS,available as expansion_available

STANDARD = ('tuxracer','neverball','neverputt','quake','quake3')
EXTRA = ('touhou','classicube','minecraft-java')+EXPANSION
ALL = STANDARD + EXTRA


class MenuProcess:
    """A menu renderer owns the locks until it exits successfully."""
    def __init__(self, frame, folder):
        self.token = uuid.uuid4().hex
        self.state = folder / ('lcd-' + self.token + '.json')
        self.log = (folder / ('lcd-' + self.token + '.log')).open('xb')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('RIX_', 'LD_PRELOAD'))}
        env.update(DISPLAY=':0', LANG='C', LC_ALL='C', LD_LIBRARY_PATH=str(Path(__file__).resolve().parent/'menu')+':/usr/lib')
        self.child = subprocess.Popen([sys.executable, str(Path(__file__).with_name('lcd_native.py')),
            '--frame', str(frame), '--state', str(self.state), '--token', self.token],
            stdout=self.log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        self.quarantined=False

    def check_exit(self, result):
        if result not in (None,0) and not self.quarantined:
            try:
                info=json.loads(self.state.read_text())
                preflight=(result==2 and info['phase']=='error' and info['token']==self.token and info['pid']==self.pid
                    and info['gpu_touched'] is False and (info['post_changed'] is False or info['post_restored'] is True))
            except (OSError,ValueError,KeyError):preflight=False
            if preflight:return
            sys.path.insert(0,'/opt/rasterix/experimental')
            from game_runtime_support import GpuRecoveryGuard
            GpuRecoveryGuard().mark('lcd-menu-'+self.token,dict(reason='LCD presenter exited without confirmed GPU release',
                exit_code=result,transport_errors=True,after=None))
            self.quarantined=True

    @property
    def pid(self): return self.child.pid

    @property
    def returncode(self): return self.child.returncode

    def poll(self):
        result = self.child.poll()
        self.check_exit(result)
        if result is not None and not self.log.closed: self.log.close()
        return result

    def terminate(self): self.child.terminate()

    def wait(self, timeout):
        result = self.child.wait(timeout=timeout)
        self.check_exit(result)
        self.log.close()
        return result

    def ready(self):
        try:
            record = json.loads(self.state.read_text())
            return record['phase'] == 'ready' and record['passed'] and record['token'] == self.token and record['pid'] == self.pid
        except (OSError, ValueError, KeyError): return False


def control_folder():
    folder=Path('/tmp/rasterix-launcher-control');folder.mkdir(mode=0o700,exist_ok=True)
    assert not folder.is_symlink() and folder.stat().st_uid==os.geteuid() and not folder.stat().st_mode & 0o077
    return folder


def board_ready():
    try:
        sys.path.insert(0,'/opt/rasterix/experimental')
        from game_runtime_support import GpuRecoveryGuard
        GpuRecoveryGuard().check()
    except Exception:
        return (), 'quarantined'
    try:
        p=Path('/tmp/rix-fpga-fsr/active-receipt.txt');info=p.lstat()
        rows=p.read_text().splitlines()
        assert p.is_file() and not p.is_symlink() and info.st_uid==0 and not info.st_mode & 0o022
        assert rows[1]==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert rows[2]=='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
        gpu=json.loads(subprocess.check_output(['plgpuctl','status'],timeout=2,text=True))
        assert gpu['status']==3 and all(gpu[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    except Exception:
        return (), 'requires-v23'
    clients=('tuxracer','neverball','neverputt','quake3e','quakespasm','th06-rix','ClassiCube','java','rix-fsr-pl','rix-neural-style')+EXPANSION_CLIENTS
    try:
        if subprocess.run(['pidof',*clients],stdout=subprocess.PIPE,timeout=2).returncode==0:
            return (), 'gpu-busy'
    except Exception:
        return (), 'gpu-busy'
    names={'tuxracer':'game-runtime','neverball':'neverball-data','neverputt':'neverball-data','quake':'quake-data','quake3':'quake3-data'}
    cache=Path('/opt/rasterix/experimental/cache')
    ready=[game for game in STANDARD if all((cache/(n+suffix)).is_file() for n in {'game-runtime',names[game]} for suffix in ('.json','.tar.gz'))]
    app=Path(__file__).resolve().parent
    if (app/'game-contracts.json').is_file() and Path('/opt/rasterix/touhou/th06-runtime/bin/th06-rix').is_file():ready.append('touhou')
    if all((cache/('classicube'+suffix)).is_file() for suffix in ('.json','.tar.gz')):ready.append('classicube')
    if all(path.is_file() for path in (app/'java/lib/libGL.so.1',app/'java/java_dual_loader.py',
            Path('/tmp/rix-launcher-java-profile-v2/manifest.json'),
            Path('/tmp/rix-java125/zulu8.98.0.107-ca-jre8.0.512-linux_aarch64/bin/java'))):ready.append('minecraft-java')
    ready.extend(expansion_available(app))
    return tuple(ready), 'ready' if ready else 'missing-runtime'


class Controller:
    def __init__(self,mode='preview',game_factory=None,menu_factory=None):
        assert mode in ('preview','board')
        assert menu_factory is None or mode=='board'
        self.mode=mode
        self.phase='menu'
        self.game=''
        self.child=None
        self.log=None
        self.game_factory=game_factory
        self.error=False
        self.fsr=False
        self.menu_factory=menu_factory
        self.menu=None
        self.pending=None
        self.closing=False
        self.menu_stop_requested=False
        if menu_factory:self.phase='returning'

    def launch(self, game, fsr):
        self.phase='starting';self.game=game
        try:
            if self.game_factory:self.child=self.game_factory(game,fsr)
            else:
                folder=control_folder()
                self.log=(folder/('launch-'+game+'-'+str(time.monotonic_ns())+'.log')).open('xb')
                self.child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('play_game.py')),game]+(['--fsr'] if fsr else []),
                    stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
            self.phase='running'
        except Exception:
            self.phase='error';self.error=True
            if self.log:self.log.close();self.log=None

    def release_menu(self):
        if self.menu is not None and not self.menu_stop_requested:
            try:self.menu.terminate();self.menu_stop_requested=True
            except ProcessLookupError:pass

    def poll(self):
        if self.child is not None and self.child.poll() is not None:
            self.error=self.child.returncode!=0
            self.phase='error' if self.error else ('returning' if self.menu_factory and not self.closing else 'menu')
            self.child=None
            self.game=''
            if self.log:self.log.close();self.log=None
        if self.menu is not None:
            code=self.menu.poll()
            if code is not None:
                requested=self.menu_stop_requested
                self.menu=None;self.menu_stop_requested=False
                if code!=0 or not requested:
                    self.error=True;self.phase='error';self.pending=None
                elif self.phase=='preparing' and self.pending and not self.closing:
                    game,fsr=self.pending;self.pending=None;self.launch(game,fsr)
                elif not self.closing:self.phase='returning'
            elif self.phase=='returning' and not self.menu_stop_requested and self.menu.ready():self.phase='menu'
        if self.menu_factory and not self.closing and not self.error and self.phase=='returning' and self.menu is None:
            try:self.menu=self.menu_factory()
            except Exception:self.error=True;self.phase='error'

    def shutdown(self):
        self.closing=True;self.pending=None
        if self.child is not None:
            try:self.child.terminate();self.phase='stopping'
            except ProcessLookupError:pass
        self.release_menu()

    def status(self):
        self.poll()
        ready,reason=ALL,'preview'
        if self.error:ready,reason=(),'game-error'
        elif self.phase not in ('menu','preview'):ready,reason=(),self.phase
        elif self.mode=='board':ready,reason=board_ready()
        return dict(ok='1',mode=self.mode,phase=self.phase,game=self.game,fsr='1' if self.fsr else '0',reason=reason,ready=','.join(ready),
            menu_output='lcd-experimental' if self.menu_factory else 'software',menu_active='1' if self.menu is not None else '0')

    def dispatch(self,line):
        self.poll()
        words=line.split()
        if words==['STATUS']:return self.status()
        if words==['STOP']:
            if self.phase=='preview':self.phase='menu';self.game=''
            elif self.phase=='preparing':self.pending=None;self.phase='returning';self.game=''
            elif self.child is not None:
                try:self.child.terminate();self.phase='stopping'
                except ProcessLookupError:self.poll()
            return self.status()
        if len(words) in (2,3) and words[0]=='START':
            game=words[1]
            if len(words)==3 and words[2]!='fsr':return dict(ok='0',reason='invalid-request')
            fsr=len(words)==3
            if game not in ALL:return dict(ok='0',reason='invalid-game')
            if self.phase!='menu' or self.error:return dict(ok='0',reason='gpu-busy' if not self.error else 'game-error')
            status=self.status()
            if game not in status['ready'].split(','):return dict(ok='0',reason=status['reason'])
            self.fsr=fsr
            if self.mode=='preview':self.game=game;self.phase='preview';return self.status()
            if self.menu_factory:
                self.pending=(game,fsr);self.game=game;self.phase='preparing';self.release_menu()
            else:self.launch(game,fsr)
            return dict(ok='0',reason='game-error') if self.error else self.status()
        return dict(ok='0',reason='invalid-request')


def exchange(path,line):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(3);client.connect(str(path));client.sendall(line.encode('ascii')+b'\n')
        raw=b''
        while b'\n.\n' not in raw:
            data=client.recv(4096)
            if not data:raise RuntimeError('Incomplete control response')
            raw+=data
            assert len(raw)<16384
    return dict(row.split('=',1) for row in raw.decode('ascii').splitlines() if '=' in row)


def serve(path,controller):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=path.parent.lstat()
    assert not path.parent.is_symlink() and info.st_uid==os.geteuid() and not info.st_mode & 0o077
    assert not path.exists() and not path.is_symlink(),'Existing control socket must be inspected, not removed blindly'
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    exit_code=0
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(path));os.chmod(path,0o600);server.listen(4);server.settimeout(.25)
        print('LAUNCHER_CONTROL_READY '+str(path)+' '+controller.mode,flush=True)
        try:
            while not stopping:
                controller.poll()
                try:connection,_=server.accept()
                except socket.timeout:continue
                with connection:
                    connection.settimeout(.5)
                    try:
                        _,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                        assert uid==os.geteuid()
                        raw=b''
                        while not raw.endswith(b'\n'):
                            data=connection.recv(64)
                            if not data:raise ValueError('Incomplete request')
                            raw+=data
                            assert len(raw)<=80
                        assert raw.count(b'\n')==1
                        result=controller.dispatch(raw[:-1].decode('ascii'))
                        response=''.join(k+'='+str(v)+'\n' for k,v in result.items())+'.\n'
                        connection.sendall(response.encode('ascii'))
                    except (ValueError,AssertionError,socket.timeout,UnicodeError,OSError):
                        try:connection.sendall(b'ok=0\nreason=invalid-request\n.\n')
                        except OSError:pass
        finally:
            controller.shutdown()
            for child in (controller.child,controller.menu):
                if child is not None:
                    try:
                        child.wait(timeout=90)
                        if child.returncode!=0:exit_code=2
                    except subprocess.TimeoutExpired:
                        exit_code=2
                        print('LAUNCHER_CONTROL_CHILD_STILL_OWNS_GPU '+str(child.pid),file=sys.stderr,flush=True)
            controller.poll()
            path.unlink()
    return exit_code


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--socket',type=Path,required=True)
    parser.add_argument('--board',action='store_true')
    parser.add_argument('--fsr',action='store_true')
    parser.add_argument('--lcd-menu',action='store_true',help='Experimental exclusive PL menu presenter; requires --board')
    parser.add_argument('--frame-input',type=Path)
    parser.add_argument('operation',choices=('serve','status','start','stop'))
    parser.add_argument('game',nargs='?')
    args=parser.parse_args()
    if args.board:assert os.geteuid()==0
    if args.lcd_menu:assert args.board and args.operation=='serve' and args.frame_input
    if args.operation=='serve':
        factory=(lambda:MenuProcess(args.frame_input,control_folder())) if args.lcd_menu else None
        raise SystemExit(serve(args.socket,Controller('board' if args.board else 'preview',menu_factory=factory)))
    else:
        command=dict(status='STATUS',start='START',stop='STOP')[args.operation]
        if args.operation=='start':
            assert args.game in (*STANDARD,*EXTRA)
            command+=' '+args.game
            if args.fsr:command+=' fsr'
        print(json.dumps(exchange(args.socket,command)),flush=True)
