#!/usr/bin/env python3
"""Compare a full SNP1 frame against independent GPU/PS glReadPixels output."""
import argparse,hashlib,json,mmap,os,struct,subprocess,tarfile,time
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--attempt',required=True)
p.add_argument('--expected-origin',choices=('top-down','bottom-up'))
a=p.parse_args()
assert a.attempt.replace('_','').isalnum() and len(a.attempt)<40
out=Path('/tmp/postproc-tests')/a.attempt
out.mkdir(parents=True,exist_ok=False)
assert not subprocess.run(['pidof','rix-smoke','neverball','neverputt','tuxracer','quakespasm','quake3e','rix-neural-style','rix-superres'],stdout=subprocess.PIPE).stdout
for module in ('rix_dma_proxy','plgpu_display'):
    if module+' ' not in Path('/proc/modules').read_text():
        subprocess.run(['insmod','/opt/rasterix/modules/'+module+'.ko'],check=True)
subprocess.run(['plgpuctl','enable'],check=True,stdout=subprocess.DEVNULL)
status=lambda:json.loads(subprocess.check_output(['plgpuctl','status'],text=True))
tool='/opt/rasterix/postproc-touch/bin/rix-superres'
before=status()
record={'attempt':a.attempt,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'smoke_sha256':hashlib.sha256(Path('/usr/bin/rix-smoke').read_bytes()).hexdigest(),'before':before,'passed':False}
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
regs=mmap.mmap(fd,65536,offset=0xa0010000)
reg=lambda offset:struct.unpack_from('<I',regs,offset)[0]
game_log=(out/'smoke.log').open('w')
game=subprocess.Popen(['/usr/bin/rix-smoke','360'],cwd=str(out),stdout=game_log,stderr=subprocess.STDOUT)
child=None
try:
    deadline=time.monotonic()+15
    while status()['presented']<before['presented']+3:
        assert game.poll() is None and time.monotonic()<deadline,'smoke produced no source frames'
        time.sleep(.02)
    child=subprocess.Popen([tool,'--snapshot',str(out/'source.rgb565'),'--snapshot-hold-ms','700'],
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    copying=None
    deadline=time.monotonic()+5
    while True:
        value=reg(0x7c)&3
        now=time.monotonic()
        if value==2 and copying is None:copying=now
        if value==3:break
        assert child.poll() is None and now<deadline,'snapshot failed before READY'
        time.sleep(.0002)
    record['copying_to_ready_seconds']=None if copying is None else now-copying
    record['sampling_interval_seconds']=.0002
    token,frame=reg(0x80),reg(0x84)
    first=status();time.sleep(.25);second=status()
    record['game_advances_under_lease']=second['presented']>first['presented']
    record['lease_stays_owned']=reg(0x7c)&3==3 and reg(0x80)==token and reg(0x84)==frame
    text=child.communicate(timeout=5)[0]
    assert child.returncode==0 and '"released":true' in text,text
    record['snapshot']=json.loads(text)
    record['normal_release_idle']=reg(0x7c)&3==0
    assert game.wait(timeout=45)==0,(out/'smoke.log').read_text()
    game_log.close()
    assert 'SMOKE_PASS' in (out/'smoke.log').read_text()
    ppm=(out/'rix-smoke.ppm').read_bytes()
    header,width_height,maximum,rgb=ppm.split(b'\n',3)
    assert header==b'P6' and width_height==b'400 240' and maximum==b'255' and len(rgb)==288000
    data=(out/'source.rgb565').read_bytes()
    assert len(data)==192000
    actual=struct.unpack('<96000H',data)
    reference=[((rgb[i]>>3)<<11)|((rgb[i+1]>>2)<<5)|(rgb[i+2]>>3) for i in range(0,len(rgb),3)]
    mismatches={'top-down':sum(x!=y for x,y in zip(actual,reference)),
                'bottom-up':sum(actual[y*400+x]!=reference[(239-y)*400+x] for y in range(240) for x in range(400))}
    origin=a.expected_origin or next((name for name,count in mismatches.items() if count==0),None)
    record.update(pixels=96000,origin=origin,mismatches=mismatches,
                  source_sha256=hashlib.sha256(data).hexdigest(),ps_readback_ppm_sha256=hashlib.sha256(ppm).hexdigest())
    record['after']=status()
    record['passed']=origin is not None and mismatches[origin]==0 and record['game_advances_under_lease'] and record['lease_stays_owned'] and record['normal_release_idle'] and all(record['after'][key]==0 for key in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
finally:
    if child is not None and child.poll() is None:
        child.terminate();child.communicate(timeout=5)
    if game.poll() is None:game.wait(timeout=45)
    game_log.close();regs.close();os.close(fd)
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    with tarfile.open(out.with_suffix('.compact.tar.gz'),'w:gz') as archive:
        for name in ('result.json','source.rgb565','rix-smoke.ppm','smoke.log'):
            if (out/name).is_file():archive.add(out/name,arcname=name)
    print('COPY_STATIC_FULL_FRAME',json.dumps(record),flush=True)
raise SystemExit(0 if record['passed'] else 1)
