#!/usr/bin/env python3
"""Observe bridge copy/presentation transitions without modifying the hardware."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import DisplayStatus

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--seconds',type=int,default=12)
p.add_argument('--interval-us',type=int,default=500)
p.add_argument('--output',type=Path,default=Path('/tmp/postproc-tests/games-opt2-phases.json'))
a=p.parse_args()
assert 5<=a.seconds<=30
assert 100<=a.interval_us<=10000
device=DisplayStatus()
frames={}
gaps=[]
before=time.monotonic();previous=device.read();previous_begin=before;previous_end=time.monotonic()
assert previous['status']==3 and not any(previous[k] for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
deadline=previous_end+a.seconds
reads=1
missed=0
while time.monotonic()<deadline:
    time.sleep(a.interval_us/1000000)
    began=time.monotonic();current=device.read();ended=time.monotonic();reads+=1
    assert current['status']==3 and not any(current[k] for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    gaps.append(ended-previous_end)
    for counter,event in [('frame_id','swap'),('copy','copy'),('presented','present')]:
        delta=(current[counter]-previous[counter])&0xffffffff
        if delta==1:
            frame=frames.setdefault(current[counter],{})
            frame[event]=[previous_begin,ended]
        elif delta:missed+=delta
    previous=current;previous_begin=began;previous_end=ended

def interval_difference(end,start):
    return {'lower_ms':max(0,(end[0]-start[1])*1000),
            'midpoint_ms':((end[0]+end[1]-start[0]-start[1])/2)*1000,
            'upper_ms':max(0,(end[1]-start[0])*1000)}

rows=[]
for number,events in sorted(frames.items()):
    if set(events)=={'swap','copy','present'}:
        row={'frame_id':number,'copy':interval_difference(events['copy'],events['swap']),
             'present_wait':interval_difference(events['present'],events['copy'])}
        prior=frames.get((number-1)&0xffffffff,{})
        if 'present' in prior:row['between_present_and_next_swap']=interval_difference(events['swap'],prior['present'])
        rows.append(row)
summary={}
for name in ('copy','present_wait','between_present_and_next_swap'):
    selected=[r[name] for r in rows if name in r]
    if selected:summary[name]={key:statistics.median(r[key] for r in selected) for key in ('lower_ms','midpoint_ms','upper_ms')}
result={'passed':len(rows)>=30 and missed==0,'seconds':a.seconds,'reads':reads,'complete_frames':len(rows),
        'requested_poll_interval_us':a.interval_us,
        'missed_counter_transitions':missed,'median_poll_gap_ms':statistics.median(gaps)*1000,
        'max_poll_gap_ms':max(gaps)*1000,'phase_medians':summary,'frames':rows,'after':previous,
        'scope':'Observed counter transition bounds. copy = bridge accepts SWAP to COPY_DONE; present_wait = COPY_DONE to actual LCD flip ACK. Upstream gap includes renderer, CPU and command upload; it is not isolated GPU rasterization time. Profiling was run outside the 12..39 s FPS comparison window.'}
a.output.write_text(json.dumps(result,indent=2)+'\n')
print('FRAME_PHASES_RESULT '+json.dumps({k:v for k,v in result.items() if k!='frames'}),flush=True)
raise SystemExit(0 if result['passed'] else 2)
