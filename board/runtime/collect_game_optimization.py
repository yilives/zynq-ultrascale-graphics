#!/usr/bin/env python3
"""Collect the exact completed board trials without replacing their raw records."""
import json
from pathlib import Path
import hashlib
import tarfile
base=Path('/opt/rasterix/experimental/results-optimization-20261019')
selected={
    'baselines':['ball_base02','putt_base02','quake_base02','q3_base02','tux_base02'],
    'finals':['ball_final03','putt_final03','quake_final03','q3_final03','tux_final03'],
    'cycles':['glx_final03','glx_mix02','glx_mix03','glx_mix04'],
}
result={group:{name:json.loads((base/name/'result.json').read_text()) for name in names} for group,names in selected.items()}
result['cache_qa']=json.loads(Path('/tmp/postproc-tests/games-cache-qa.json').read_text())
result['logs']={name:(base/name/'game.log').read_text(errors='replace') for name in selected['cycles']+['putt_final03','tux_final03']}
text=result['logs']['tux_final03']
result['tux_log_summary']={'bytes':len(text.encode()),'ignored_hint_warnings':text.count('glHint not implemented')}
result['logs']['tux_final03']='\n'.join(line for line in text.splitlines() if line.startswith('TUX_'))
result['package']=json.loads(Path('/opt/rasterix/experimental/cache/game-runtime.json').read_text())
archive=Path('/mnt/sd-mmcblk1p1/rasterix-game-cache-backup-20261019/archive-manifest.json')
result['cache_archive']=json.loads(archive.read_text())
bundle=Path('/tmp/postproc-tests/games-final-captures.tar.gz')
with tarfile.open(bundle,'w:gz') as output:
    for run in result['finals'].values():
        for label,capture in run['captures'].items():
            source=Path(capture['path'])
            assert source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest()==capture['sha256']
            name=run['attempt']+('-lcd' if label=='lcd' else '')+'.bin'
            output.add(str(source),arcname=name)
    preview=Path('/tmp/postproc-tests/games-tux-race-preview.bin')
    if preview.exists():
        output.add(str(preview),arcname='tux-race-preview.bin')
        result['race_preview']={'sha256':hashlib.sha256(preview.read_bytes()).hexdigest(),
                                'snapshot_log':Path('/tmp/postproc-tests/games-tux-race-preview.log').read_text()}
result['capture_bundle']={'sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'bytes':bundle.stat().st_size}
path=Path('/tmp/postproc-tests/games-final-evidence.json')
path.write_text(json.dumps(result))
print('GAME_FINAL_EVIDENCE_READY bytes='+str(path.stat().st_size),flush=True)
