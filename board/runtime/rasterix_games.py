#!/usr/bin/env python3
"""Prepare and run the isolated AXU3EG game-port trials from verified SD cache."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import uuid
from game_runtime_support import DisplayStatus

CACHE = Path('/opt/rasterix/experimental/cache')
WORK = Path('/tmp/rasterix-games')
ERRORS = ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')
PACKAGES = {'game-runtime': 'runtime', 'neverball-data': 'neverball', 'quake-data': 'quake', 'quake3-data': 'quake3'}
GAMES = ('glx-probe', 'neverball', 'neverputt', 'quake', 'quake3', 'tuxracer')
CLIENTS = ('tuxracer', 'rix-smoke', 'neverball', 'neverputt', 'quake3e', 'quakespasm',
           'rix-glx-probe', 'rix-danmaku', 'rix-superres', 'th06-rix')
POST = '/opt/rasterix/postproc-touch/bin/rix-superres'
STYLES = {'original': 0, 'poster': 1, 'sepia': 2, 'binary': 3}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


_display_status=None
def status():
    global _display_status
    if _display_status is None:_display_status=DisplayStatus()
    return _display_status.read()


def prepare(packages):
    WORK.mkdir(parents=True, exist_ok=True)
    assert WORK.resolve().parent in (Path('/tmp'), Path('/var/volatile/tmp'))
    for name in packages:
        expected = json.loads((CACHE / (name + '.json')).read_text())
        archive = CACHE / (name + '.tar.gz')
        assert expected.get('verified') is True and sha(archive) == expected['sha256']
        stamp = WORK / ('.' + name + '.sha256')
        if stamp.exists() and stamp.read_text().strip() == expected['sha256']:
            continue
        prefix = PACKAGES[name]
        with tarfile.open(archive) as incoming:
            members = incoming.getmembers()
            for member in members:
                relative = Path(member.name)
                assert not relative.is_absolute() and '..' not in relative.parts and relative.parts[0] == prefix
                assert member.isfile() or member.isdir() or member.issym()
                if member.issym():
                    link = Path(member.linkname)
                    assert not link.is_absolute() and '..' not in link.parts
                target = WORK / relative
                assert not target.is_symlink() or (member.issym() and os.readlink(target) == member.linkname), 'Refuse to overwrite an unrelated link'
            incoming.extractall(WORK)
        stamp.write_text(expected['sha256'] + '\n')
        print('PORT_PACKAGE_PREPARED', name, flush=True)


def command(game, home, tuning='balanced', runtime=None):
    exe = (runtime or WORK / 'runtime') / 'bin'
    if game == 'tuxracer':
        config = home / '.tuxracer/options'
        config.parent.mkdir(parents=True, exist_ok=True)
        if not config.exists():
            shutil.copyfile('/etc/rasterix/tuxracer-options', config)
        return [str(exe / 'tuxracer') if (exe / 'tuxracer').exists() else '/usr/bin/tuxracer']
    if game == 'glx-probe':
        return [str(exe / 'rix-glx-probe')]
    if game in ('neverball', 'neverputt'):
        for folder in ('.neverball', '.neverball-dev'):
            profile = home / folder
            profile.mkdir(parents=True, exist_ok=True)
            config = profile / 'neverballrc'
            # Preserve controls, scores and preferences. Only enforce constraints
            # required by the physical renderer; seed other defaults once.
            values = dict(line.split(None, 1) for line in config.read_text().splitlines() if line.strip() and len(line.split(None, 1)) == 2) if config.exists() else {'sound_volume':'0', 'music_volume':'0'}
            values.update(fullscreen='0', width='400', height='240', reflection='0', shadow='0', mipmap='0', multisample='0', aniso='0', highdpi='0')
            config.write_text(''.join(k+' '+v+'\n' for k,v in values.items()))
        args = [str(exe / game), '--data', str(WORK / 'neverball/data')]
        if game == 'neverball':
            args += ['--level', 'map-easy/easy.sol']
        else:
            args += ['--hole','map-putt/01_easy.sol'] if tuning=='legacy' else ['--course','holes-putt.txt']
        return args
    if game == 'quake':
        basedir=home/'quake'
        (basedir/'id1').mkdir(parents=True,exist_ok=True)
        for pak in (WORK/'quake/id1').glob('*.pak'):
            target=basedir/'id1'/pak.name
            if not target.exists():target.symlink_to(pak)
        # This build has DO_USERDIRS=0. A writable per-profile basedir keeps
        # saves/configs persistent while the original PAK stays read-only.
        return [str(exe / 'quakespasm'), '-basedir', str(basedir),
                '-window', '-width', '400', '-height', '240', '-nosound', '-nocdaudio',
                '-noglsl', '-novbo', '-nomtex', '+gl_max_size', '128',
                '+gl_texturemode', 'GL_LINEAR', '+host_maxfps', '30' if tuning == 'legacy' else '60', '+map', 'e1m1']
    # Native modules match the current engine API; the original 1.11 demo
    # contains an older UI VM. Keep the asset archive intact.
    for name in ('cgameaarch64.so', 'qagameaarch64.so', 'uiaarch64.so'):
        shutil.copyfile(WORK / 'runtime/share/quake3/demoq3' / name, WORK / 'quake3/demoq3' / name)
    return [str(exe / 'quake3e'), '+set', 'fs_basepath', str(WORK / 'quake3'),
            '+set', 'fs_homepath', str(home / 'quake3'), '+set', 'fs_basegame', 'demoq3',
            '+set', 'r_mode', '-1', '+set', 'r_customwidth', '400', '+set', 'r_customheight', '240',
            '+set', 'r_fullscreen', '0', '+set', 'r_stencilbits', '0', '+set', 'r_colorbits', '16',
            '+set', 'r_depthbits', '16', '+set', 'r_ext_multitexture', '0', '+set', 'r_picmip', '2',
            # 60 increases GPU work enough to miss additional LCD refreshes
            # on this scene. Keep the measured 30 Hz budget for Quake III.
            '+set', 's_initsound', '0', '+set', 'com_hunkMegs', '128', '+set', 'com_maxfps', '30',
            '+set', 'vm_ui', '0', '+set', 'vm_cgame', '0', '+set', 'vm_game', '0',
            '+set', 'sv_pure', '0', '+set', 'r_fastsky', '1', '+set', 'r_subdivisions', '20', '+map', 'q3dm1']


if __name__ == '__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='run':
        import game_optimization_trial
        sys.argv=[sys.argv[0],*sys.argv[2:]]
        raise SystemExit(game_optimization_trial.main())
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('prepare',))
    p.add_argument('game',choices=GAMES)
    a=p.parse_args()
    names=['game-runtime']
    if a.game not in ('glx-probe','tuxracer'):
        names.append('neverball-data' if a.game.startswith('never') else a.game+'-data')
    prepare(names)
