#!/usr/bin/env python3
"""Existing CPU sampling plus timestamped, read-only display GET_STATUS at 1 Hz."""
import json,os,sys,time
from pathlib import Path

def stat(path):
    text=path.read_text();fields=text.rpartition(')')[2].split()
    return dict(comm=text.partition('(')[2].rpartition(')')[0],utime=int(fields[11]),
                stime=int(fields[12]),cpu=int(fields[36]),starttime=int(fields[19]))

def main(pid,output,device_factory=None):
    folder=Path('/proc')/str(pid);initial=stat(folder/'stat')['starttime']
    if device_factory is None:
        sys.path.insert(0,'/opt/rasterix/experimental')
        from game_runtime_support import DisplayStatus
        device_factory=DisplayStatus
    # Refuse an existing output before opening any device.
    with Path(output).open('x') as stream:
        device=device_factory()
        try:
            stream.write(json.dumps(dict(kind='header',pid=pid,starttime=initial,
                hz=os.sysconf('SC_CLK_TCK'),gpu_status_sampler=True,gpu_interval_seconds=1,
                gpu_operation='GET_STATUS',gpu_get_status_ioctl=0x80405200))+'\n')
            next_gpu=0
            while folder.exists():
                try:
                    if stat(folder/'stat')['starttime']!=initial:break
                    tasks={}
                    for task in (folder/'task').iterdir():
                        try:tasks[task.name]=stat(task/'stat')
                        except (FileNotFoundError,ProcessLookupError):pass
                    row=dict(kind='sample',ns=time.monotonic_ns(),threads=tasks)
                    if row['ns']>=next_gpu:
                        begin=time.monotonic_ns();gpu=device.read();end=time.monotonic_ns()
                        gpu.update(sample_begin_ns=begin,sample_end_ns=end)
                        row['gpu']=gpu;next_gpu=end+1000000000
                    stream.write(json.dumps(row)+'\n');stream.flush()
                except (FileNotFoundError,ProcessLookupError):break
                time.sleep(.5)
        finally:device.close()

if __name__=='__main__':main(int(sys.argv[1]),sys.argv[2])
