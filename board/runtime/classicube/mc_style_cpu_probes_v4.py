#!/usr/bin/env python3
"""Run isolated A53 pixel and inactive-bank transfer probes in sequence."""
import hashlib,json,subprocess
from pathlib import Path
out=Path('/tmp/postproc-tests');source=out/'cc_style_v3_final';records=[]
for name in ('planar','pairs','write'):
 exe=Path('/tmp/benchmark-'+name)
 assert not subprocess.run(['pidof','ClassiCube','rix-neural-style','rix-neural-runtime-v4'],stdout=subprocess.PIPE).stdout
 command=[str(exe)]
 if name!='write':command += [str(source/('anime.'+s)) for s in ('source565.bin','input.bin','output.bin')]
 result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
 (out/('cc_v4_probe_'+name+'.log')).write_text(result.stdout+result.stderr)
 assert result.returncode==0,(name,result.stdout,result.stderr)
 value=json.loads(result.stdout);assert value['passed'],value
 record={'case':name,'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'result':value}
 records.append(record);(out/'cc_v4_cpu_probes.json').write_text(json.dumps(records,indent=2)+'\n')
 print('MC_V4_CPU_PROBE',name,json.dumps(value),flush=True)
print('MC_V4_CPU_PROBES_PASS',flush=True)
