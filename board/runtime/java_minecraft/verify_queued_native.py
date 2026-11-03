"""Two processes, same GL image: prove off/on palette pixels and actual fast use."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
stage=Path('/tmp/rix-fpga-java256');out=Path(sys.argv[1]);expected=json.loads((stage/'delivery.json').read_text());records=[]
for mode in (0,1):
    folder=out.parent/('queued-mode'+str(mode));folder.mkdir()
    env=os.environ.copy();env['RIX_JAVA_PREPARED_ARRAYS']='1';env['RIX_JAVA_QUEUED_ARRAYS']=str(mode);env['RIX_JAVA_QUEUED_STATS']=str(folder/'queued-stats.json')
    result=subprocess.run(['python3',str(stage/'native_queued_arrays.py'),str(folder/'result.json')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
    (folder/'output.log').write_text(result.stdout);assert result.returncode==0,result.stdout
    record=json.loads((folder/'result.json').read_text());assert record['passed'] and record['actual_tmu_count']==2 and record['owned_inputs_mutated'] and record['call_time_constants'] and record['call_time_matrices']
    assert record['delete_and_redefine_pending'] and record['pressure_calls']==4100
    if expected.get('final_stats_after_destroy'):
        final=json.loads((folder/'queued-stats.json.final.json').read_text())
        counters=json.loads((folder/'queued-stats.json').read_text())
        assert final['phase']=='after_renderer_destroy'
        for field in ('submitted_batches','consumed_batches','submitted_vertices','consumed_vertices'):assert final[field]==counters[field]
        assert counters['submitted_batches']==counters['consumed_batches'] and counters['submitted_vertices']==counters['consumed_vertices']
        record['final_statistics_verified']=True
    if expected['queued_arrays'] and mode:
        stats=json.loads((folder/'queued-stats.json').read_text());assert stats['enabled']
        assert stats['submitted_vertices']==stats['consumed_vertices']>49000
        assert stats['submitted_batches']==stats['consumed_batches']>12300 and stats['retention_drains']>=3
        record['stats']=stats
    records.append(record)
for name in ('multiply','only-unit0','only-unit1'):
    a=out.parent/'queued-mode0'/('prepared-dual-'+name+'.rgba');b=out.parent/'queued-mode1'/a.name
    assert a.read_bytes()==b.read_bytes()
data=dict(passed=True,queued_capable=expected['queued_arrays'],same_binary_mode_pixels_identical=True,modes=records)
out.write_text(json.dumps(data,indent=2)+'\n');print('JAVA_QUEUED_NATIVE_COMPARE_PASS modes=2 pixel_cases=3 pending_delete_redefine=1 pressure=4100')
