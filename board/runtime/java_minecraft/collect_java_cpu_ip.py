"""Sample the busiest live Java threads; never opens a GPU device or sends signals."""
import json,os,subprocess,sys,time
from pathlib import Path
pid=int(sys.argv[1]);out=Path(sys.argv[2]);stage=Path(__file__).resolve().parent;proc=Path('/proc')/str(pid)
def tasks():
    found={}
    for task in (proc/'task').iterdir():
        try:
            text=(task/'stat').read_text();fields=text.rpartition(')')[2].split()
            found[int(task.name)]=dict(name=(task/'comm').read_text().strip(),ticks=int(fields[11])+int(fields[12]),start=int(fields[19]))
        except (FileNotFoundError,ProcessLookupError):pass
    return found
first=tasks();time.sleep(.35);last=tasks()
ranked=sorted((dict(tid=tid,comm=row['name'],ticks=row['ticks']-first[tid]['ticks']) for tid,row in last.items() if tid in first and row['start']==first[tid]['start']),key=lambda r:r['ticks'],reverse=True)
selected=[row for row in ranked if row['ticks']>0][:8];assert len(selected)>=2
(out/'ip-maps-before.txt').write_bytes((proc/'maps').read_bytes())
record=dict(pid=pid,selected=selected,all_threads=ranked,clock_hz=os.sysconf('SC_CLK_TCK'),begin_ns=time.monotonic_ns(),
    measurement_limit='IP sampling and JVM compilation logging add overhead; FPS is diagnostic only')
with (out/'ip-sampler.log').open('x') as log:
    result=subprocess.run([str(stage/'cpu-ip-sampler'),'17',str(out/'ip-counts.json'),*[str(row['tid']) for row in selected]],stdout=log,stderr=subprocess.STDOUT,timeout=22)
record.update(exit_code=result.returncode,end_ns=time.monotonic_ns(),profile=json.loads((out/'ip-counts.json').read_text()))
(out/'ip-maps-after.txt').write_bytes((proc/'maps').read_bytes())
record['passed']=result.returncode==0 and record['profile']['passed']
(out/'ip-profile.json').write_text(json.dumps(record,indent=2)+'\n');print('JAVA_CPU_IP_PROFILE',record['passed'],record['profile']['samples'])
raise SystemExit(0 if record['passed'] else 1)
