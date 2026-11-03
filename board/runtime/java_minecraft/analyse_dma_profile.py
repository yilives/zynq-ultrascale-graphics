"""Summarize only samples inside the actual stationary Java world interval."""
import argparse,json,re
from pathlib import Path
def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args();folder=Path(args.folder)
    log=(folder/'minecraft.log').read_text(errors='replace')
    begin=int(re.search(r'JAVA_WORLD_MONO_START (\d+)',log)[1]);end=int(re.search(r'JAVA_WORLD_MONO_END (\d+)',log)[1]);assert end>begin
    def rows(name):return [json.loads(line) for line in (folder/name).read_text().splitlines()]
    dma=rows('dma-profile.jsonl');window=[r for r in dma if r['kind']=='cumulative' and begin<=r['ns']<=end];assert len(window)>=10
    left,right=window[0],window[-1];seconds=(right['ns']-left['ns'])/1e9
    delta={key:right[key]-left[key] for key in left if key not in ('kind','ns')};assert min(delta.values())>=0
    total=sum(delta[key] for key in ('stream_bytes','store_bytes','load_bytes','other_bytes'))
    cpu=rows('cpu-profile.jsonl');hz=cpu[0]['hz'];samples=[r for r in cpu[1:] if begin<=r['ns']<=end];assert len(samples)>=10
    first,last=samples[0],samples[-1];cpu_seconds=(last['ns']-first['ns'])/1e9;threads=[]
    for tid in set(first['threads'])&set(last['threads']):
        a,b=first['threads'][tid],last['threads'][tid];assert a['starttime']==b['starttime']
        used=(b['utime']+b['stime']-a['utime']-a['stime'])/hz
        if used:threads.append(dict(tid=int(tid),comm=b['comm'],cpu_percent=used/cpu_seconds*100,cpu_seconds=used))
    threads.sort(key=lambda x:x['cpu_percent'],reverse=True)
    result=dict(java_world_begin_ns=begin,java_world_end_ns=end,dma_window_seconds=seconds,dma_delta=delta,
        dma_mib_per_second=total/seconds/1048576,texture_store_fraction=delta['store_bytes']/total,
        dma_finish_wait_fraction=delta['wait_ns']/(seconds*1e9),dma_start_ioctl_fraction=delta['tx_ns']/(seconds*1e9),
        cpu_window_seconds=cpu_seconds,threads=threads,diagnostic_scope='cumulative endpoints inside active interval; instrumentation overhead not corrected')
    shadow=folder/'minecraft-texture-dedup.jsonl'
    if shadow.exists():
        window=[r for r in rows(shadow.name) if begin<=r['ns']<=end];assert len(window)>=10
        for row in window:assert row['failures']==0 and row['input_bytes']==row['skipped_bytes']+row['written_bytes']
        first,last=window[0],window[-1];duration=(last['ns']-first['ns'])/1e9
        delta={key:last[key]-first[key] for key in first if key!='ns'};assert min(delta.values())>=0 and delta['input_bytes']>0
        result['texture_dedup']=dict(seconds=duration,delta=delta,skipped_fraction=delta['skipped_bytes']/delta['input_bytes'],
            input_mib_per_second=delta['input_bytes']/duration/1048576,written_mib_per_second=delta['written_bytes']/duration/1048576)
    (folder/'profile-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
