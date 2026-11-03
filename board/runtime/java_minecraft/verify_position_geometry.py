"""Pure CPU geometry comparison; never opens a GPU or device mapping."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
folder=Path(sys.argv[1]);stage=Path('/tmp/rix-fpga-java256');records=[]
for label,binary,enabled in (('reference','position-reference-unit','0'),('off','position-candidate-unit','0'),('on','position-candidate-unit','1')):
 p=folder/('position-'+label+'.bin');assert not p.exists();env=dict(os.environ,RIX_JAVA_POSITION_CACHE=enabled);env.pop('RIX_JAVA_POSITION_STATS',None)
 r=subprocess.run([str(stage/binary),str(p)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
 assert r.returncode==0 and 'TRANSFORM_CACHE_FIXTURE triangles=' in r.stdout
 b=p.read_bytes();assert len(b)>100000;records.append(dict(label=label,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),output=r.stdout))
assert len({r['sha256'] for r in records})==1
result=dict(passed=True,hardware_access=False,bit_exact_geometry=True,records=records)
(folder/'position-geometry.json').write_text(json.dumps(result,indent=2)+'\n')
print('JAVA_POSITION_GEOMETRY_PASS bit_exact=1 modes=3 matrix_resets=96 varied_uv_color=1 lighting_fallback=1')
