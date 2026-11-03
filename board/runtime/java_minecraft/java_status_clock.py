#!/usr/bin/env python3
"""Read-only counter/time pair; startup and output costs lie outside timestamps."""
import json,sys,time
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import DisplayStatus
device=DisplayStatus()
try:
    begin=time.monotonic_ns();result=device.read();end=time.monotonic_ns()
finally:device.close()
result.update(sample_begin_ns=begin,sample_end_ns=end)
print(json.dumps(result,separators=(',',':')))
