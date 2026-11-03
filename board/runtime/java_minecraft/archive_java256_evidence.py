"""Archive existing CPU-side evidence before reboot. Never accesses GPU/DDR."""
import argparse,hashlib,io,json,re,subprocess,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--attempt');p.add_argument('--compact',action='store_true');a=p.parse_args()
assert re.fullmatch('java256-[a-z0-9_-]{1,40}',a.name)
if a.attempt:assert re.fullmatch('java256-full-r[0-9]+',a.attempt)
root=Path('/tmp/postproc-tests');output=root/(a.name+'.tar.gz')
assert not output.exists()
q=subprocess.run(['pidof','java'],stdout=subprocess.PIPE);assert q.returncode==1
selected=[root/a.attempt] if a.attempt else [x for x in sorted(root.glob('java256-full-r*')) if x.is_dir()]
if a.compact:
    names=('result.json','texture256.log','mojang256.log','mojang256.ppm','mojang256-source.bin','mojang256-source.json',
        'minecraft.log','minecraft-source.bin','minecraft-source.json','original-fsr-receipt.txt','retired-256-receipt.txt')
    paths=[(x/name,'attempts/'+x.name+'/'+name) for x in selected for name in names if (x/name).exists()]
else:paths=[(x,'attempts/'+x.name) for x in selected]
pattern=(a.attempt+'-*-journal.json') if a.attempt else 'java256-full-r*-journal.json'
paths += [(x,'journals/'+x.name) for x in sorted(root.glob(pattern)) if x.is_file()]
qa=root/('java256_restorecheck_r5' if a.attempt=='java256-full-r5' else 'java256_restorecheck')
if qa.exists():
    for x in sorted(qa.iterdir()):
        if x.is_file() and (x.suffix=='.log' or x.name in ('result.json','dependencies.log')):
            paths.append((x,'baseline-check/'+x.name))
for path,name in (
    ('/opt/rasterix/experimental/gpu-quarantine.json','guard.json'),
    ('/tmp/rix-fpga-fsr/active-receipt.txt','original-active-receipt.txt'),
    ('/tmp/rix-fpga-java256/delivery.json','stage-delivery.json'),
    ('/tmp/rix-fpga-java256/manifest.json','stage-manifest.json'),
    ('/tmp/rix-fpga-java256/run_java256_trial.py','stage-runner.py'),
    ('/tmp/postproc-tests/cc_fsr_fpga_load.json','original-load-proof.json')):
    if Path(path).exists():paths.append((Path(path),name))
for filename in ('cc_v4_fpga_load.json','java256-final-state.json','java256-final-state-r5.json'):
    if (root/filename).exists():paths.append((root/filename,filename))
context=dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    original_receipt_present=Path('/tmp/rix-fpga-fsr/active-receipt.txt').exists(),
    source='existing_files_only_no_GPU_or_DDR_access')
with tarfile.open(output,'w:gz') as t:
    for path,name in paths:t.add(path,arcname=name,recursive=True)
    data=json.dumps(context,indent=2).encode()
    info=tarfile.TarInfo('context.json');info.size=len(data);info.mode=0o600;t.addfile(info,io.BytesIO(data))
print('JAVA256_EVIDENCE_ARCHIVED',output.stat().st_size,hashlib.sha256(output.read_bytes()).hexdigest(),flush=True)
