"""Same binary and visible pressure geometry; cache on versus sequential bypass."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
stage=Path('/tmp/rix-fpga-java256');out=Path(sys.argv[1]);records=[]
for mode in (0,1):
 folder=out.parent/('batch-cache-mode'+str(mode));folder.mkdir()
 env=os.environ.copy();env.update(RIX_JAVA_PREPARED_ARRAYS='1',RIX_JAVA_QUEUED_ARRAYS='1',RIX_JAVA_BATCH_CACHE_BYPASS=str(mode),RIX_JAVA_BATCH_CACHE_STATS=str(folder/'cache-stats.json'),RIX_JAVA_QUEUED_STATS=str(folder/'queued-stats.json'))
 run=subprocess.run(['python3',str(stage/'native_queued_large.py'),str(folder/'result.json')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
 (folder/'output.log').write_text(run.stdout);assert run.returncode==0,run.stdout
 record=json.loads((folder/'result.json').read_text());stats=json.loads((folder/'cache-stats.json').read_text());queued=json.loads((folder/'queued-stats.json').read_text());final=json.loads((folder/'queued-stats.json.final.json').read_text())
 assert record['passed'] and record['visible_gpu_pressure'] and record['last_segment_marker']
 assert stats['phase']==final['phase']=='after_renderer_destroy' and stats['bypass_enabled']==bool(mode)
 assert stats['cached_vertices']+stats['bypass_vertices']==queued['submitted_vertices']==queued['consumed_vertices']>196000
 assert stats['cached_batches']+stats['bypass_batches']==queued['submitted_batches']==queued['consumed_batches']>20
 assert stats['cached_vertices']==0 if mode else stats['bypass_vertices']==0
 assert run.stdout.count('JAVA_GPU_BAND_SPILL complete=1')>0
 record.update(cache_statistics=stats,queued_statistics=queued,final_statistics=final);records.append(record)
for label in ('multiply','only-unit0','only-unit1'):
 a=out.parent/'batch-cache-mode0'/('prepared-dual-'+label+'.rgba');b=out.parent/'batch-cache-mode1'/a.name
 assert a.read_bytes()==b.read_bytes()
out.write_text(json.dumps(dict(passed=True,same_binary=True,cache_modes_identical=True,modes=records),indent=2)+'\n')
print('JAVA_BATCH_CACHE_NATIVE_PASS modes=2 pixel_cases=3 large_batch=65536 final_counters=1')
