"""Two processes, same GL image: prove off/on palette pixels and actual fast use."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
stage=Path('/tmp/rix-fpga-java256');out=Path(sys.argv[1]);expected=json.loads((stage/'delivery.json').read_text());records=[]
for mode in (0,1):
    folder=out.parent/('prepared-mode'+str(mode));folder.mkdir()
    env=os.environ.copy();env['RIX_JAVA_PREPARED_ARRAYS']=str(mode);env['RIX_JAVA_PREPARED_STATS']=str(folder/'stats.json')
    result=subprocess.run(['python3',str(stage/'native_prepared_arrays.py'),str(folder/'result.json')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    (folder/'output.log').write_text(result.stdout);assert result.returncode==0,result.stdout
    record=json.loads((folder/'result.json').read_text());assert record['passed'] and record['actual_tmu_count']==2 and record['owned_inputs_mutated'] and record['call_time_constants'] and record['call_time_matrices']
    if expected['prepared_arrays']:
        stats=json.loads((folder/'stats.json').read_text());assert stats['enabled']==bool(mode)
        assert stats['fast_vertices']>0 and stats['fallback_vertices']==0 if mode else stats['fallback_vertices']>0 and stats['fast_vertices']==0
        record['stats']=stats
    records.append(record)
for name in ('multiply','only-unit0','only-unit1'):
    a=out.parent/'prepared-mode0'/('prepared-dual-'+name+'.rgba');b=out.parent/'prepared-mode1'/a.name
    assert a.read_bytes()==b.read_bytes()
data=dict(passed=True,prepared_capable=expected['prepared_arrays'],same_binary_mode_pixels_identical=True,modes=records)
out.write_text(json.dumps(data,indent=2)+'\n');print('JAVA_PREPARED_NATIVE_COMPARE_PASS modes=2 pixel_cases=3 call_time_state=1')
