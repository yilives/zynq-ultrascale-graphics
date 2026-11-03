"""Named expansion adapters with pinned executables/data; no command strings."""
import hashlib,json,os,struct
from pathlib import Path

ARCADE={'arcade-snake':'snake','arcade-blocks':'blocks','arcade-breakout':'breakout','arcade-2048':'merge2048','arcade-sokoban':'sokoban','arcade-mines':'mines'}
EXPANSION=tuple(ARCADE)+('rrootage',)
CLIENTS=('rix-arcade','rrootage')

def verify(app,game):
    base=Path(app)/'library';manifest=json.loads((base/'manifest.json').read_text())
    assert manifest['schema']==1 and game in manifest['games'],'Expansion game not installed'
    names=manifest['games'][game]['files']
    assert names and len(names)==len(set(names))
    for name in names:
        relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
        path=base/relative;entry=manifest['files'][name]
        assert path.is_file() and not path.is_symlink() and path.stat().st_size==entry['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256'],name
    binary=base/('bin/rix-arcade' if game in ARCADE else 'bin/rrootage')
    header=binary.read_bytes()[:64];assert header[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',header,18)[0]==183
    return base,manifest['games'][game]

def available(app):
    result=[]
    for game in EXPANSION:
        try:verify(app,game);result.append(game)
        except (OSError,ValueError,KeyError,AssertionError):pass
    return tuple(result)

def prepare(game,app,env,qa_autoplay=False,attempt=''):
    assert game in EXPANSION
    base,contract=verify(app,game)
    if qa_autoplay:
        assert attempt.startswith('menu-') and len(attempt)<100
        profile=Path('/tmp/rasterix-library-qa-profiles')/attempt
    else:profile=Path('/opt/rasterix/experimental/profiles/library-v4')/game
    profile.mkdir(mode=0o700,parents=True,exist_ok=True)
    runtime=Path('/tmp/rasterix-games/runtime')
    env.update(HOME=str(profile),LD_LIBRARY_PATH=str(runtime/'lib'),SDL_VIDEO_GL_DRIVER=str(runtime/'lib/libGL.so.1'),RIX_PRESENT_STRATEGY='async',RIX_PRESENT_SYNC='1')
    if game in ARCADE:
        command=[str(base/'bin/rix-arcade'),'--game',ARCADE[game],'--state-dir',str(profile)]
        if qa_autoplay:command+=['--qa-autoplay']
    else:
        for source in (base/'data/rrootage').iterdir():
            target=profile/source.name
            if target.is_symlink():assert target.resolve()==source.resolve()
            elif target.exists():raise RuntimeError('Keep existing profile data: '+str(target))
            else:target.symlink_to(source)
        command=[str(base/'bin/rrootage'),'-nosound']
        if qa_autoplay:env['RIX_AUTOPLAY']='1'
    return command,env,profile,profile
