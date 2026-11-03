"""Read-only inventory before an isolated NIP1 RAM test."""
import json
from pathlib import Path
import subprocess

def command(args):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=6)
    return dict(exit=result.returncode,stdout=result.stdout)

processes=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        args=(proc/'cmdline').read_bytes().split(b'\0')
        text=b' '.join(args).decode(errors='replace')
        if any(key in text for key in ('session.py','launcher_control.py','rix-launcher','rix-neural','rix-fsr','java_dual_loader')):
            processes.append(dict(pid=int(proc.name),command=text[:400]))
    except (FileNotFoundError,PermissionError,ProcessLookupError):pass
paths=['/tmp/rasterix-launcher-v3-native','/tmp/rix-fpga-fsr/active-receipt.txt',
       '/tmp/postproc-tests/cc_fsr_fpga_load.json','/tmp/rix-launcher-java-profile-v2/manifest.json',
       '/proc/device-tree/neural-style@a0030000/compatible']
record=dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            uptime=Path('/proc/uptime').read_text().strip(),
            gpu=command(['plgpuctl','status']),processes=processes,
            paths={name:Path(name).exists() for name in paths},
            memory=Path('/proc/meminfo').read_text().splitlines()[:4])
for name in paths[1:]:
    path=Path(name)
    if path.is_file():record[name]=path.read_text(errors='replace')[:2500]
print(json.dumps(record),flush=True)
