"""Verify bounded GET_STATUS samples inside the independently measured world window."""
import json
from pathlib import Path

def verify(folder):
    folder=Path(folder);record=json.loads((folder/'result.json').read_text())
    rows=[json.loads(line) for line in (folder/'cpu-profile.jsonl').read_text().splitlines()]
    header=rows[0]
    assert header['kind']=='header' and header['gpu_status_sampler']
    assert header['gpu_operation']=='GET_STATUS' and header['gpu_get_status_ioctl']==0x80405200
    assert header['gpu_interval_seconds']==1 and header['hz']>0
    measurement=record['world_measurement']
    midpoint=lambda r:(r['sample_begin_ns']+r['sample_end_ns'])/2
    begin,end=midpoint(measurement['start']),midpoint(measurement['end'])
    samples=[r['gpu'] for r in rows[1:] if 'gpu' in r and begin<=midpoint(r['gpu'])<=end]
    assert len(samples)>=20
    for sample in samples:
        assert sample['abi']==0x52495801 and sample['config']==0x9adb505e
        assert sample['status']==3 and sample['enabled']==1
        assert 0<=sample['sample_end_ns']-sample['sample_begin_ns']<50000000
        assert all(sample[k]==0 for k in ('read_errors','write_errors','timeouts','underflows','scan_errors'))
    intervals=[]
    for a,b in zip(samples,samples[1:]):
        seconds=(midpoint(b)-midpoint(a))/1e9;assert 0<seconds<3
        frames=b['presented']-a['presented'];assert frames>0
        beats=(b['command_beats']-a['command_beats'])&0xffffffff
        intervals.append(dict(seconds_from_measurement_start=(midpoint(a)-begin)/1e9,
            seconds=seconds,completed_frames=frames,command_beats=beats,
            fps=frames/seconds,command_beats_per_frame=beats/frames))
    elapsed=(midpoint(samples[-1])-midpoint(samples[0]))/1e9
    frames=samples[-1]['presented']-samples[0]['presented']
    return dict(passed=True,sample_count=len(samples),intervals=intervals,
        sampled_seconds=elapsed,sampled_completed_frames=frames,sampled_fps=frames/elapsed,
        max_get_status_span_ns=max(s['sample_end_ns']-s['sample_begin_ns'] for s in samples),
        total_get_status_span_ns=sum(s['sample_end_ns']-s['sample_begin_ns'] for s in samples),
        official_fps=record['java_fps'],
        scope='Interior GET_STATUS/time pairs, not a replacement for the official full-window FPS; no input-idle/raster-stall counters exist here')
