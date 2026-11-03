#!/usr/bin/env python3
"""Measure telemetry overhead and audit the bounded-logging game runtime."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import tarfile
import time

BASE=Path('/opt/rasterix/experimental')
OUT=Path('/tmp/postproc-tests')
OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(BASE))
from game_runtime_support import DisplayStatus

ATTEMPTS={'glx-probe':('glx_log01',8),'neverball':('ball_log01',45),'neverputt':('putt_log01',45),
          'quake':('quake_log01',45),'quake3':('q3_log01',45),'tuxracer':('tux_log01',300)}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def idle():
    result=subprocess.run(['pidof','tuxracer','neverball','neverputt','quakespasm','quake3e','rix-glx-probe','cache-qa','th06-rix','rix-superres'],stdout=subprocess.PIPE)
    assert result.returncode==1 and not result.stdout,'GPU client already running'

def benchmark():
    idle()
    device=DisplayStatus()
    expected=device.read()
    assert expected['status']==3
    def cpu():
        own=resource.getrusage(resource.RUSAGE_SELF)
        child=resource.getrusage(resource.RUSAGE_CHILDREN)
        return own.ru_utime+own.ru_stime+child.ru_utime+child.ru_stime
    measurements={}
    for name,read in [('external_cli',lambda:json.loads(subprocess.check_output(['plgpuctl','status']))),('direct_ioctl',device.read)]:
        read()
        start=time.monotonic();used=cpu()
        for _ in range(100):assert read()==expected,'Counter changed while GPU was idle'
        measurements[name]={'calls':100,'wall_ms_per_read':(time.monotonic()-start)*10,
                            'cpu_ms_per_read':(cpu()-used)*10}
    result={'passed':True,'status_fields_identical':True,'fields':len(expected),'measurements':measurements,
            'wall_speedup':measurements['external_cli']['wall_ms_per_read']/measurements['direct_ioctl']['wall_ms_per_read'],
            'status':device.read(),'scope':'Idle board, 100 reads each; CPU time includes reaped CLI children.'}
    (OUT/'games-opt2-telemetry.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TELEMETRY_ABI_AND_COST_PASS '+json.dumps(measurements),flush=True)

def run():
    benchmark()
    for game,(attempt,seconds) in ATTEMPTS.items():
        print('RUNTIME_OPT2_STAGE '+attempt,flush=True)
        command=['rix-games',game,'--attempt',attempt,'--seconds',str(seconds),'--fresh-profile','--filter','nearest']
        if game!='glx-probe':command.append('--capture')
        if game in ('neverball','neverputt','tuxracer'):command.append('--autoplay')
        with (OUT/('games-'+attempt+'.log')).open('wb') as log:
            code=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
        result=json.loads((BASE/'results-optimization-20261019'/attempt/'result.json').read_text())
        assert code==0 and result['passed'],attempt
    collect()
    print('RUNTIME_OPT2_SUITE_PASS',flush=True)

def collect():
    runs={game:json.loads((BASE/'results-optimization-20261019'/attempt/'result.json').read_text()) for game,(attempt,_) in ATTEMPTS.items()}
    logs={game:(BASE/'results-optimization-20261019'/run['attempt']/'game.log').read_text(errors='replace') for game,run in runs.items()}
    bundle=OUT/'games-opt2-captures.tar.gz'
    with tarfile.open(bundle,'w:gz') as archive:
        for game,run in runs.items():
            for label,capture in run['captures'].items():
                path=Path(capture['path'])
                assert sha(path)==capture['sha256']
                archive.add(str(path),arcname=run['attempt']+('-lcd' if label=='lcd' else '')+'.bin')
    result={'runs':runs,'logs':logs,'telemetry':json.loads((OUT/'games-opt2-telemetry.json').read_text()),
            'package':json.loads((BASE/'cache/game-runtime.json').read_text()),
            'capture_bundle':{'sha256':sha(bundle),'bytes':bundle.stat().st_size},
            'runtime_support_sha256':sha(BASE/'game_runtime_support.py'),
            'unit_test_log':(OUT/'games-opt2-unit.log').read_text(),'python_version':sys.version}
    encoded=json.dumps(result)
    (OUT/'games-opt2-evidence.json').write_text(encoded)
    (OUT/'games-opt2-evidence.json.gz').write_bytes(gzip.compress(encoded.encode()))
    destination=BASE/'delivery-runtime2-20261019'
    destination.mkdir(exist_ok=True)
    (destination/'evidence.json').write_text(encoded)
    (destination/'telemetry.json').write_text(json.dumps(result['telemetry'],indent=2)+'\n')
    print('RUNTIME_OPT2_EVIDENCE_READY bytes='+str(len(encoded)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('run','benchmark','collect'))
    globals()[p.parse_args().operation]()
