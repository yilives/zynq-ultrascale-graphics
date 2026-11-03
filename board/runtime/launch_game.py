#!/usr/bin/env python3
"""Validate hardware identity and readiness before constructing the GL singleton."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
def status():
    return json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--configuration',default='/etc/rasterix/config.json')
    p.add_argument('--seconds',type=int,default=1800)
    p.add_argument('--log',default='/tmp/rasterix-acceptance.jsonl')
    p.add_argument('--asset-manifest',default='/etc/rasterix/assets.json')
    a=p.parse_args();config=json.loads(Path(a.configuration).read_text())
    if a.seconds<=0: p.error('--seconds must be positive')
    if not os.environ.get('DISPLAY'): raise RuntimeError('Set DISPLAY for the BSP SDL2 X11 input window')
    if not Path('/usr/local/share/tuxracer/tuxracer_init.tcl').exists():
        raise RuntimeError('Install the pinned/audited Tux Racer data at /usr/local/share/tuxracer first')
    assets=json.loads(Path(a.asset_manifest).read_text())
    data=Path('/usr/local/share/tuxracer')
    for name,expected in assets['files_sha256'].items():
        file=data/name
        try:
            file.resolve().relative_to(data.resolve())
        except ValueError:
            raise RuntimeError(f'Invalid game asset path: {name}')
        if file.is_file():
            actual=hashlib.sha256(file.read_bytes()).hexdigest()
        else:
            raise RuntimeError(f'Missing or invalid game asset: {name}')
        if actual!=expected: raise RuntimeError(f'Game asset checksum mismatch: {name}')
    options=Path.home()/'.tuxracer/options'
    if not options.exists():
        options.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile('/etc/rasterix/tuxracer-options',options)
    text=options.read_text()
    if not re.search(r'^\s*set\s+data_dir\s+"/usr/local/share/tuxracer"\s*$',text,re.M):
        raise RuntimeError(f'Set data_dir to /usr/local/share/tuxracer in {options}')
    for name in ('dma_proxy_tx','dma_proxy_rx','plgpu_display'):
        if not Path('/dev',name).exists(): raise RuntimeError(f'Missing /dev/{name}')
    deadline=time.monotonic()+30
    while True:
        s=status()
        if s['abi']!=0x52495801 or s['config']!=config['config_hash']:
            raise RuntimeError('Hardware/userspace ABI or configuration mismatch')
        if s['status']&4: raise RuntimeError(f'Hardware fault: {s}')
        if s['status']&3==3: break
        if time.monotonic()>deadline: raise RuntimeError('MIG/pixel clock readiness timed out')
        time.sleep(.1)
    subprocess.run(['plgpuctl','enable'],check=True)
    start=status();baseline={k:start[k] for k in ('read_errors','write_errors','timeouts','underflows','scan_errors')}
    proc=subprocess.Popen(['tuxracer'])
    began=time.monotonic()
    try:
        with open(a.log,'a',buffering=1) as log:
            log.write(json.dumps({'configuration':config,'assets':assets['configuration'],
                                  'started':time.time(),'initial':start})+'\n')
            while proc.poll() is None:
                s=status();s['elapsed_s']=time.monotonic()-began;log.write(json.dumps(s)+'\n')
                if s['status']&4 or any(s[k]!=v for k,v in baseline.items()):
                    raise RuntimeError(f'Display/DMA error counters changed: {s}')
                if s['elapsed_s']>=a.seconds: break
                time.sleep(1)
            if proc.poll() not in (None,0): raise RuntimeError(f'Game exited with {proc.returncode}')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill();proc.wait()
    print(f'Log saved to {a.log}; check menu/input/course and image correctness separately')
if __name__=='__main__':
    try: main()
    except Exception as e: print(str(e),file=sys.stderr);sys.exit(1)
