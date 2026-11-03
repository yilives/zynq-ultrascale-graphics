"""Export completed menu trials as data; performs no device operations."""
import argparse,json,os,re,tarfile
from pathlib import Path

ROOT=Path('/tmp/postproc-tests')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--revision',required=True)
    parser.add_argument('--attempt')
    parser.add_argument('--allow-failed',action='store_true')
    args=parser.parse_args();assert re.fullmatch('r[0-9]+',args.revision)
    attempt=args.attempt or 'java256-full-'+args.revision
    assert attempt in ('java256-full-'+args.revision,'java256-singleplayer-'+args.revision,'java256-world-'+args.revision)
    folder=ROOT/attempt
    result=json.loads((folder/'result.json').read_text())
    assert 'after' in result,'Trial has not reached its final state'
    if not args.allow_failed:assert result['passed'] and result['restored'] and result['error'] is None
    names=['result.json','minecraft.log','texture256.log','mojang256.log',
           'minecraft-front-before-reset.bin','minecraft-front-before-reset.bin.json',
           'minecraft-source.bin','minecraft-source.json','original-fsr-receipt.txt','retired-256-receipt.txt']
    files={name:folder/name for name in names if (folder/name).exists()}
    if not args.allow_failed:assert len(files)==len(names)
    for name in ('tmu_bounds.log','swap_stress.log','swap-stress-front-before-reset.bin','swap-stress-front-before-reset.bin.json','display_lists.log','display-lists.json'):
        if (folder/name).exists():files[name]=folder/name
    for path in folder.glob('display-list-*.rgba'):files[path.name]=path
    for name in ('submission.log','submission.json','submit-texture-grid.rgba','arb_api.log'):
        if (folder/name).exists():files[name]=folder/name
    for name in ('dual_texture.log','dual-texture.json'):
        if (folder/name).exists():files[name]=folder/name
    for path in folder.glob('dual-*.rgba'):files[path.name]=path
    for name in ('world-active.bin','world-active.json','original-options.txt'):
        if (folder/name).exists():files[name]=folder/name
    for phase in ('load','restore'):
        name=attempt+'-'+phase+'-journal.json'
        if (ROOT/name).exists():files[name]=ROOT/name
    if args.revision=='r8':
        for name in ('result.json','minecraft.log'):
            files['r7/'+name]=ROOT/'java256-full-r7'/name
    for path in files.values():assert path.is_file() and not path.is_symlink()
    output=ROOT/('java256-'+args.revision+'-menu-evidence.tar.gz')
    fd=os.open(str(output),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        with tarfile.open(fileobj=stream,mode='w:gz') as archive:
            for name,path in files.items():archive.add(str(path),arcname=name,recursive=False)
    import hashlib
    print('JAVA256_MENU_EVIDENCE',str(output),output.stat().st_size,hashlib.sha256(output.read_bytes()).hexdigest())
if __name__=='__main__':main()
