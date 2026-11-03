#!/usr/bin/env python3
"""Compare the legacy and packed readers with identical game/native settings."""
import argparse,json,os,re,resource,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('prefix');p.add_argument('seconds',type=int);p.add_argument('cases',nargs='+',choices=('legacy','generic','packed','verify'))
p.add_argument('--flat',action='store_true')
p.add_argument('--view-distance',type=int,choices=(16,24,32,48,64),default=32)
a=p.parse_args();assert re.fullmatch('cc_vertex_[a-z0-9_]+',a.prefix)
out=Path('/tmp/postproc-tests');records=[]
for i,case in enumerate(a.cases):
    name='%s_%d_%s'%(a.prefix,i,case)
    env=os.environ.copy();env.pop('RIX_PACKED_FETCH_VERIFY',None);env['RIX_VERTEX_CACHE']='1'
    if case=='verify':env['RIX_PACKED_FETCH_VERIFY']='1'
    command=['rix-classicube','--attempt',name,'--seconds',str(a.seconds),'--world-size','64',
             '--view-distance',str(a.view_distance),'--autoplay','--capture','--fps-limit','120','--present-strategy','async',
             '--vertex-fetch','packed' if case=='verify' else case]
    if a.flat:command.append('--flat')
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    with Path('/tmp/'+name+'.log').open('w') as f:r=subprocess.run(command,env=env,stdout=f,stderr=subprocess.STDOUT)
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    data=json.loads((out/name/'result.json').read_text());data['case']=case
    log=(out/name/'game.log').read_text()
    data['verified_vertices']=sum(int(v) for v in re.findall(r'verified_vertices=(\d+)',log))
    data['packed_vertices']=sum(int(v) for v in re.findall(r'packed_vertices=(\d+)',log))
    data['process_cpu_seconds']={'user':after.ru_utime-before.ru_utime,'system':after.ru_stime-before.ru_stime,
                                 'scope':'launcher plus reaped child processes; includes startup and capture'}
    records.append(data)
    report=out/(a.prefix+'.json');tmp=report.with_suffix('.incoming');tmp.write_text(json.dumps(records,indent=2)+'\n');tmp.replace(report)
    assert r.returncode==0 and data['passed'],data
    if case=='verify':assert data['verified_vertices']>100000,data
    print('CLASSICUBE_VERTEX_RESULT',name,data['hardware_window'],'verified',data['verified_vertices'],flush=True)
assert len({r['native_sha256'] for r in records})==1
assert len({r['package_sha256'] for r in records})==1
assert not subprocess.run(['pidof','ClassiCube'],stdout=subprocess.PIPE).stdout
print('CLASSICUBE_VERTEX_PASS',a.prefix,flush=True)
