"""Read RAM journals only; never probe PL registers during reconfiguration."""
import json
from pathlib import Path

stage=Path('/tmp/rix-cnn-inplace-r1')
record={}
for name in ('job.json','qa/result.json'):
    path=stage/name
    if path.exists():
        value=json.loads(path.read_text())
        if name.endswith('result.json'):
            value={k:v for k,v in value.items() if k not in ('source','before','restoration','phases')}
            value['phases']=list(json.loads(path.read_text()).get('phases',{}))
        record[name]=value
log=stage/'job.log'
if log.exists():record['job_tail']=log.read_text()[-4000:]
controller=Path('/tmp/postproc-tests/cnn-inplace-r1-load.json')
if controller.exists():
    c=json.loads(controller.read_text())
    record['controller']={k:c.get(k) for k in ('passed','outcome','error','rollback')}
    record['controller']['last_events']=c['events'][-3:]
print('CNN_QA_POLL',json.dumps(record),flush=True)
