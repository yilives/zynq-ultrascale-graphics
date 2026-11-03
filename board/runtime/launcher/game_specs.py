#!/usr/bin/env python3
"""Fixed, local game commands and private profiles; no shell command expansion."""
import json
import os
from pathlib import Path
import shutil
import tarfile
from java_profile import sha
from library_games import EXPANSION,prepare as prepare_expansion

STANDARD=('tuxracer','neverball','neverputt','quake','quake3')
EXTRA=('touhou','classicube','minecraft-java')+EXPANSION
ALL=STANDARD+EXTRA
TITLES=dict(tuxracer='Tuxracer',neverball='Neverball',neverputt='Neverputt',quake='Quakespasm',quake3='Quake3e',
            touhou='Touhou',classicube='ClassiCube',**{'minecraft-java':'Minecraft'})
TITLES.update({game:'rRootage' if game=='rrootage' else 'RasterIX Arcade' for game in EXPANSION})

def prepare(game, app, games, qa_autoplay=False, attempt=''):
    assert game in ALL
    app=Path(app)
    env={k:v for k,v in os.environ.items() if not k.startswith(('RIX_','TH06_','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','LD_PRELOAD'))}
    env.update(DISPLAY=':0',LANG='C',LC_ALL='C',SDL_VIDEODRIVER='x11',SDL_AUDIODRIVER='dummy')
    if game in EXPANSION:
        games.prepare(['game-runtime'])
        return prepare_expansion(game,app,env,qa_autoplay,attempt)
    if game in STANDARD:
        packages=['game-runtime']
        if game!='tuxracer':packages.append('neverball-data' if game.startswith('never') else game+'-data')
        games.prepare(packages)
        profile=Path('/opt/rasterix/experimental/profiles')/game;profile.mkdir(parents=True,exist_ok=True)
        command=games.command(game,profile)
        runtime=games.WORK/'runtime'
        env.update(HOME=str(profile),LD_LIBRARY_PATH='/usr/lib' if game=='tuxracer' else str(runtime/'lib'),
                   SDL_VIDEO_GL_DRIVER=str(runtime/'lib/libGL.so.1'))
        # Per-game v23 board trials: preserve quality and keep independent pacing.
        if game in ('neverball','quake3'):env['RIX_PRESENT_STRATEGY']='async'
        if game=='quake3':
            at=command.index('com_maxfps');assert command[at+1]=='30'
            command[at+1]='60'
        return command,env,games.WORK,profile
    if game=='touhou':
        base=Path('/opt/rasterix/touhou');runtime=base/'th06-runtime';profile=base/'profile'
        contract=json.loads((app/'game-contracts.json').read_text())['touhou']
        for name,digest in contract.items():assert sha(base/name)==digest,'Touhou runtime identity changed: '+name
        profile.mkdir(parents=True,exist_ok=True)
        for source in (base/'th06-demo').iterdir():
            if source.is_file():
                target=profile/source.name
                if not target.exists() and not target.is_symlink():target.symlink_to(source)
        env.update(HOME=str(profile),LD_LIBRARY_PATH=str(runtime/'lib'),TH06_TEXTURE_MODE='balanced',TH06_TOUCH='1')
        if qa_autoplay:env['TH06_AUTOPLAY']='1'
        return [str(runtime/'bin/th06-rix')],env,profile,profile
    if game=='classicube':
        games.prepare(['game-runtime'])
        cache=Path('/opt/rasterix/experimental/cache');archive=cache/'classicube.tar.gz'
        receipt=json.loads((cache/'classicube.json').read_text())
        assert receipt['verified'] and sha(archive)==receipt['sha256']
        work=Path('/tmp/rasterix-classicube')/receipt['sha256'][:12]
        if not (work/'.verified').exists():
            work.mkdir(parents=True,exist_ok=True)
            with tarfile.open(archive) as source:
                members=source.getmembers();assert len(members)==len({m.name for m in members})
                manifest=json.load(source.extractfile('classicube/manifest.json'))
                assert {m.name for m in members}=={'classicube/'+n for n in manifest}|{'classicube/manifest.json'}
                for member in members:
                    name=Path(member.name)
                    assert member.isfile() and name.parts[0]=='classicube' and '..' not in name.parts and not name.is_absolute()
                    target=work.joinpath(*name.parts[1:]);assert not target.is_symlink()
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.extractfile(member).read())
                    target.chmod(0o700 if name.parts[1]=='bin' else 0o600)
        manifest=json.loads((work/'manifest.json').read_text())
        assert all(sha(work/name)==entry['sha256'] for name,entry in manifest.items())
        (work/'.verified').write_text(receipt['sha256']+'\n')
        profile=Path('/opt/rasterix/classicube/profile');profile.mkdir(parents=True,exist_ok=True)
        for folder in ('texpacks','maps','home'):(profile/folder).mkdir(exist_ok=True)
        target=profile/'texpacks/default.zip';assets=work/'data/default.zip'
        if target.is_symlink():assert os.readlink(target).startswith('/tmp/rasterix-classicube/')
        elif target.exists():assert sha(target)==sha(assets),'Keep the user texture pack'
        if not target.exists() and not target.is_symlink():target.symlink_to(assets)
        # Keep the user's controls and world/physics settings.
        options=profile/'options.txt'
        values=dict(row.split('=',1) for row in options.read_text().splitlines() if '=' in row) if options.exists() else {}
        values.update({'window-width':'400','window-height':'240','viewdist':'32','musicvolume':'0','soundsvolume':'0',
            'fpslimit':'Limit120FPS','auto-pause':'False','usebitmapfont':'True','gfx-mipmaps':'False',
            'gfx-smoothlighting':'False','entityshadow':'None','chat-logging':'False','gfx-maxchunkupdates':'2','win-raw-input':'False'})
        values.setdefault('mousesensitivity','30');values.setdefault('invertmouse','False')
        options.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
        runtime=games.WORK/'runtime'
        env.update(HOME=str(profile/'home'),LD_LIBRARY_PATH=str(work/'lib')+':'+str(runtime/'lib'),
            SDL_VIDEO_GL_DRIVER=str(work/'lib/libGL.so.1'),RIX_SECONDS='0',RIX_WORLD_SIZE='64',RIX_FRAME_METRICS='1',
            RIX_PACKED_FETCH='1',RIX_PRESENT_STRATEGY='async',RIX_PRESENT_SYNC='1')
        if qa_autoplay:env['RIX_AUTOPLAY']='1'
        return [str(work/'bin/ClassiCube'),'--singleplayer'],env,profile,profile
    # Mainline ARM geometry / dual-TMU RasterIX, with the chosen 8e89 library.
    base=Path('/tmp/rix-java125');jre=base/'zulu8.98.0.107-ca-jre8.0.512-linux_aarch64'
    contract=json.loads((app/'game-contracts.json').read_text())['java_existing']
    for name,digest in contract.items():assert sha(base/name)==digest,'Java dependency identity changed: '+name
    library=app/'java/lib/libGL.so.1'
    assert sha(library)=='8e89c36f66e497f26044c779551e5703fbbb7a1a02ff938c76315d8c99d4a993'
    profile=Path('/opt/rasterix/experimental/profiles/minecraft-java');profile.mkdir(parents=True,exist_ok=True)
    minecraft=profile/'.minecraft';minecraft.mkdir(exist_ok=True)
    (minecraft/'saves').mkdir(exist_ok=True)
    # A newly created launcher profile gets a playable demo save, never overwriting saves.
    demo=minecraft/'saves/launcher-demo'
    if not demo.exists():shutil.copytree(base/'profile-baseline-r24',demo)
    options=minecraft/'options.txt'
    original_options=base/'home/.minecraft/options.txt'
    option_text=options.read_text() if options.exists() else original_options.read_text()
    values=dict(row.split(':',1) for row in option_text.splitlines() if ':' in row)
    values.setdefault('music','0.0');values.setdefault('sound','0.0')
    quality=json.loads((app/'java/mainline.json').read_text())['visual_settings']
    values.update({key:str(value).lower() for key,value in quality.items()})
    options.write_text(''.join(k+':'+v+'\n' for k,v in values.items()))
    env.update(HOME=str(profile),LD_LIBRARY_PATH=':'.join(map(str,[app/'java/lib',base/'native',jre/'lib/aarch64',jre/'lib/aarch64/server'])),
        RIX_PRESENT_SYNC='1',RIX_PRESENT_STRATEGY='pipeline',RIX_JAVA_TEXTURE_DEDUP='1',RIX_JAVA_BATCH_CACHE_BYPASS='1',
        RIX_JAVA_FPGA_GEOMETRY='0',RIX_JAVA_DEFER_TEXTURE_WAIT='0')
    entry='Java256WorldHarness' if qa_autoplay else 'JavaInteractive'
    command=[str(jre/'bin/java'),'-Xms64m','-Xmx512m','-XX:+UseSerialGC','-Duser.home='+str(profile),
        '-Djava.awt.headless=false','-Dsun.java2d.opengl=false','-Dsun.java2d.xrender=false',
        '-Dorg.lwjgl.librarypath='+str(base/'native')]
    if qa_autoplay:command.append('-Drix.world.name=launcher-demo')
    command+=['-cp',str(app/'java/classes')+':'+str(base/'libs/*'),entry]
    return command,env,profile,profile
