"""CPU-only baseline/candidate comparisons; run under the trial parent's locks."""
import hashlib,json,re,subprocess,sys
from pathlib import Path
stage=Path('/tmp/rix-fpga-java256');out=Path(sys.argv[1]);results={}
for kind in ('geometry','values'):
    rows=[]
    for name,trivial in (('baseline',0),('candidate',1)):
        target=out/('vector-'+kind+'-'+name+'.bin');assert not target.exists()
        executable=stage/('check-'+kind+'-'+name)
        process=subprocess.run([str(executable),str(target)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=20)
        (out/('vector-'+kind+'-'+name+'.log')).write_text(process.stdout)
        assert process.returncode==0 and 'trivial='+str(trivial) in process.stdout
        if kind=='geometry':assert 'tmu=2' in process.stdout and 'draws=96 vertices=11520' in process.stdout
        else:assert 'VECTOR_VALUES_PASS' in process.stdout and 'nan_payload=1 negative_zero=1 self_move=1' in process.stdout
        rows.append(dict(variant=name,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),log=process.stdout))
    assert rows[0]['bytes']==rows[1]['bytes']>100000 and rows[0]['sha256']==rows[1]['sha256']
    results[kind]=dict(passed=True,records=rows)
data=dict(passed=True,actual_tmu_count=2,CPU_only=True,comparisons=results)
(out/'vector-geometry.json').write_text(json.dumps(data,indent=2)+'\n');print('JAVA_VECTOR_CPU_COMPARE_PASS geometry_and_values_bit_exact=1')
