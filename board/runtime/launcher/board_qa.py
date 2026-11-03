#!/usr/bin/env python3
"""Board acceptance driver. RAM install, real game cycles and aligned readback."""
import argparse
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tarfile
import time

ROOT=Path('/tmp')
APP=ROOT/'rasterix-launcher-v2e'
OUT=ROOT/'rasterix-launcher-v2e-qa'
PACKAGE=ROOT/'launcher-recovery/launcher.tar.gz'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def frozen():
    spec=importlib.util.spec_from_file_location('qa_frozen',APP/'java/java_dual_loader.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.CLIENTS=(*m.CLIENTS,'java');return m

def install(expected):
    assert platform.machine()=='aarch64' and os.geteuid()==0
    assert sha(PACKAGE)==expected and not PACKAGE.is_symlink()
    assert not APP.exists() and not OUT.exists(),'Keep previous installation and evidence'
    APP.mkdir(mode=0o700);OUT.mkdir(mode=0o700)
    with tarfile.open(PACKAGE) as source:
        names=source.getnames();assert len(names)==len(set(names))
        manifest=json.load(source.extractfile('rasterix-launcher-v2/package-manifest.json'))['files']
        assert set(names)=={'rasterix-launcher-v2/'+n for n in manifest}|{'rasterix-launcher-v2/package-manifest.json'}
        for member in source:
            name=Path(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts and name.parts[0]=='rasterix-launcher-v2'
            relative='/'.join(name.parts[1:]);data=source.extractfile(member).read()
            if relative!='package-manifest.json':
                entry=manifest[relative];assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
            target=APP/relative;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with target.open('xb') as stream:stream.write(data)
            target.chmod(0o700 if relative in ('rix-launcher','java/rix-fsr-pl') else 0o600)
    m=frozen();adapter=m.LinuxAdapter()
    sys.path.insert(0,'/opt/rasterix/experimental')
    from game_runtime_support import GpuRecoveryGuard
    with adapter.locks():
        GpuRecoveryGuard().check();before=adapter.snapshot();m.check_idle(before)
        stage=ROOT/'rix-launcher-java-profile-v2'
        if not stage.exists():stage.mkdir(mode=0o700)
        assert not stage.is_symlink() and not (stage/'active-receipt.txt').exists()
        target_manifest=read(APP/'java/manifest.json')
        for role in ('new','old'):
            source=ROOT/'rix-fpga-java256'/(role+'.bin')
            assert sha(source)==target_manifest['images'][role]['sha256'] and not source.is_symlink()
            if not (stage/source.name).exists():os.link(source,stage/source.name)
            assert sha(stage/source.name)==target_manifest['images'][role]['sha256']
        if not (stage/'manifest.json').exists():
            (stage/'manifest.json').write_bytes((APP/'java/manifest.json').read_bytes());(stage/'manifest.json').chmod(0o600)
        assert read(stage/'manifest.json')==target_manifest
        socket=OUT/'preview.sock'
        with (OUT/'preview-control.log').open('xb') as log:
            server=subprocess.Popen(['python3',str(APP/'launcher_control.py'),'--socket',str(socket),'serve'],stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+10
                while not socket.exists():assert server.poll() is None and time.monotonic()<deadline;time.sleep(.05)
                checks=[]
                for size in ('1920x1080','800x480'):
                    folder=OUT/size;folder.mkdir(mode=0o700)
                    with (folder/'ui.log').open('xb') as output:
                        subprocess.run([str(APP/'rix-launcher'),'--assets',str(APP/'assets'),'--headless','--size',size,
                            '--socket',str(socket),'--state-dir',str(folder/'state'),'--test-ui',str(folder/'result.json'),
                            '--snapshot',str(folder/'frame.bmp')],stdout=output,stderr=subprocess.STDOUT,check=True,timeout=90)
                    result=read(folder/'result.json');assert result['passed'] and len(result['checks'])==16
                    checks.append(result)
            finally:server.terminate();server.wait(timeout=5)
        after=adapter.snapshot();m.check_idle(after)
        assert before['gpu']==after['gpu'] and before['post']==after['post']
        save(OUT/'install.json',dict(passed=True,boot_id=before['boot_id'],package_sha256=expected,ui_checks=checks,
            gpu_and_post_unchanged=True,dp_output_validated=False,before=before,after=after))
    print('LAUNCHER_V2_INSTALLED '+str(APP),flush=True)

def one_game(game, seconds, extra):
    path=OUT/('direct-'+game+'.log')
    with path.open('xb') as log:
        child=subprocess.Popen(['python3',str(APP/'play_game.py'),game,'--fsr','--qa-seconds',str(seconds),*extra],
            stdout=log,stderr=subprocess.STDOUT)
        try:child.wait(timeout=seconds+120)
        except subprocess.TimeoutExpired:
            child.terminate()
            # Do not kill the wrapper while it may be draining an AXI owner.
            try:child.wait(timeout=60)
            except subprocess.TimeoutExpired:raise RuntimeError('Game wrapper still owns hardware: '+str(child.pid))
            raise
    rows=[json.loads(row.split(' ',1)[1]) for row in path.read_text().splitlines() if row.startswith('LAUNCHER_GAME_RESULT ')]
    assert child.returncode==0 and len(rows)==1 and rows[0]['passed'],str(path)
    return rows[0]

def suite():
    sys.path.insert(0,str(APP));import launcher_control as control
    assert read(OUT/'install.json')['passed'] and not (OUT/'suite.json').exists()
    record=dict(passed=False,direct=[],controller=[],error=None)
    try:
        previous=ROOT/'rasterix-launcher-v2b-qa/suite.json'
        if previous.exists():
            old=read(previous)
            assert not old['passed'] and len(old['direct'])==2 and not old['controller']
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            assert [r['game'] for r in old['direct']]==['touhou','classicube']
            assert all(r['passed'] and r['boot_id']==boot for r in old['direct'])
            if all(sha(APP/name)==sha(ROOT/'rasterix-launcher-v2b'/name) for name in ('play_game.py','game_specs.py')):
                record['direct']=old['direct']
                record['reused_direct']=dict(path=str(previous),sha256=sha(previous),reason='Only Java journal directory changed; completed non-Java adapters unchanged.')
        for game,seconds,extra in (('touhou',30,['--qa-autoplay']),('classicube',30,['--qa-autoplay']),
                ('minecraft-java',105,['--qa-autoplay','--qa-golden'])):
            if any(r['game']==game for r in record['direct']):continue
            print('LAUNCHER_SUITE_DIRECT '+game,flush=True)
            result=one_game(game,seconds,extra);record['direct'].append(result)
            save(OUT/'suite-progress.json',record)
        socket=OUT/'board.sock'
        with (OUT/'board-control.log').open('xb') as log:
            server=subprocess.Popen(['python3',str(APP/'launcher_control.py'),'--socket',str(socket),'--board','serve'],stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+10
                while not socket.exists():assert server.poll() is None and time.monotonic()<deadline;time.sleep(.05)
                for game,minimum in (('touhou',15),('classicube',15),('minecraft-java',35)):
                    print('LAUNCHER_SUITE_CONTROL '+game,flush=True)
                    before_logs=set((ROOT/'rasterix-launcher-control').glob('launch-'+game+'-*.log'))
                    initial=control.exchange(socket,'STATUS');assert game in initial['ready'].split(',')
                    started=control.exchange(socket,'START '+game+' fsr');assert started['phase']=='running'
                    until=time.monotonic()+minimum
                    while time.monotonic()<until:
                        assert control.exchange(socket,'STATUS')['phase']=='running','Normal game exited early'
                        time.sleep(.5)
                    sample1=json.loads(subprocess.check_output(['plgpuctl','status'],text=True));time.sleep(2)
                    sample2=json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
                    assert sample2['presented']>sample1['presented'],'No new game frames'
                    assert control.exchange(socket,'STOP')['phase']=='stopping'
                    until=time.monotonic()+90
                    while True:
                        status=control.exchange(socket,'STATUS')
                        if status['phase']=='menu':break
                        assert status['phase']!='error' and time.monotonic()<until,'Control stop/restore failed'
                        time.sleep(.25)
                    fresh=set((ROOT/'rasterix-launcher-control').glob('launch-'+game+'-*.log'))-before_logs
                    assert len(fresh)==1
                    lines=next(iter(fresh)).read_text().splitlines()
                    result=json.loads(next(row.split(' ',1)[1] for row in lines if row.startswith('LAUNCHER_GAME_RESULT ')))
                    assert result['passed'] and result['qa_seconds']==0 and not result['qa_autoplay']
                    result['controller_samples']=[sample1,sample2];record['controller'].append(result)
                    save(OUT/'suite-progress.json',record)
            finally:server.terminate();server.wait(timeout=40)
        assert record['direct'][-1]['java_fsr_golden_384000_pixels']
        record['passed']=True
    except BaseException as exc:record['error']=repr(exc)
    finally:save(OUT/'suite.json',record)
    print('LAUNCHER_SUITE_DONE '+json.dumps(dict(passed=record['passed'],error=record['error'])),flush=True)
    return 0 if record['passed'] else 2

def export():
    m=frozen();adapter=m.LinuxAdapter()
    sys.path.insert(0,'/opt/rasterix/experimental');from game_runtime_support import GpuRecoveryGuard
    with adapter.locks():
        GpuRecoveryGuard().check();snapshot=adapter.snapshot();m.check_idle(snapshot)
        save(OUT/'final-state.json',dict(snapshot=snapshot,receipt=(ROOT/'rix-fpga-fsr/active-receipt.txt').read_text(),
             dp_status=Path('/sys/class/drm/card0-DP-1/status').read_text().strip()))
        paths=[p for p in OUT.rglob('*') if p.is_file() and p.suffix not in ('.sock',) and p.name not in ('evidence.tar.gz','transport.tar','export.json')]
        previous=ROOT/'rasterix-launcher-v2b-qa'
        if previous.exists():paths += [previous/name for name in ('install.json','suite.json','direct-minecraft-java.log')]
        suite_data=read(OUT/'suite.json') if (OUT/'suite.json').exists() else read(OUT/'suite-progress.json')
        for result in suite_data.get('direct',[])+suite_data.get('controller',[]):
            run=ROOT/'rasterix-launcher-runs'/result['attempt']
            paths += [p for p in run.rglob('*') if p.is_file() and p.suffix not in ('.bin',) and p.name not in ('new.bin','old.bin')]
        bundle=OUT/'evidence.tar.gz'
        with tarfile.open(bundle,'w:gz') as target:
            for path in sorted(set(paths)):
                assert not path.is_symlink() and path.stat().st_size<=16*1024*1024
                target.add(path,arcname=path.relative_to(ROOT).as_posix(),recursive=False)
        save(OUT/'export.json',dict(boot_id=snapshot['boot_id'],inner_bytes=bundle.stat().st_size,inner_sha256=sha(bundle)))
        transport=OUT/'transport.tar'
        with tarfile.open(transport,'w') as target:
            target.add(bundle,arcname='evidence.tar.gz',recursive=False);target.add(OUT/'export.json',arcname='export.json',recursive=False)
        data=transport.read_bytes();assert 0<len(data)<=16*1024*1024 and len(data)%512==0
        node=Path('/proc/device-tree/reserved-memory/graphics@60000000')
        assert struct.unpack('>4I',(node/'reg').read_bytes())==(0,0x60000000,0,0x2000000) and (node/'no-map').exists()
        fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        try:
            with mmap.mmap(fd,(len(data)+4095)//4096*4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x60800000) as memory:
                memory[:len(data)]=data;assert hashlib.sha256(memory[:len(data)]).hexdigest()==sha(transport)
        finally:os.close(fd)
        print('LAUNCHER_V2_EVIDENCE_READY '+json.dumps(dict(bytes=len(data),sha256=sha(transport),boot_id=snapshot['boot_id'])),flush=True)
        ack=ROOT/'launcher-v2-evidence-ack';deadline=time.monotonic()+600
        while not ack.exists():assert time.monotonic()<deadline;time.sleep(.2)
        assert ack.read_text().strip()==sha(transport);m.check_idle(adapter.snapshot())
    print('LAUNCHER_V2_EVIDENCE_RELEASED',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=('install','suite','export'))
    parser.add_argument('--sha256');args=parser.parse_args()
    if args.operation=='install':install(args.sha256)
    elif args.operation=='suite':raise SystemExit(suite())
    else:export()
