#!/usr/bin/env python3
"""Read-only per-thread CPU samples while one particular Java PID exists."""
import json,os,sys,time
from pathlib import Path
pid=int(sys.argv[1]);folder=Path('/proc')/str(pid)
def stat(path):
    text=path.read_text();fields=text.rpartition(')')[2].split()
    return dict(comm=text.partition('(')[2].rpartition(')')[0],utime=int(fields[11]),stime=int(fields[12]),cpu=int(fields[36]),starttime=int(fields[19]))
initial=stat(folder/'stat')['starttime']
with Path(sys.argv[2]).open('x') as stream:
    stream.write(json.dumps(dict(kind='header',pid=pid,starttime=initial,hz=os.sysconf('SC_CLK_TCK')))+'\n')
    while folder.exists():
        try:
            if stat(folder/'stat')['starttime']!=initial:break
            tasks={}
            for task in (folder/'task').iterdir():
                try:tasks[task.name]=stat(task/'stat')
                except (FileNotFoundError,ProcessLookupError):pass
            stream.write(json.dumps(dict(kind='sample',ns=time.monotonic_ns(),threads=tasks))+'\n');stream.flush()
        except (FileNotFoundError,ProcessLookupError):break
        time.sleep(.5)
