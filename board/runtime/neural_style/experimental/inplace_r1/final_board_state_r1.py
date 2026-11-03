import hashlib
import json
from pathlib import Path
import subprocess

def command(args):return subprocess.check_output(args,text=True,timeout=6)
base=Path('/media/sd-mmcblk1p1')
boot={name:dict(bytes=(base/name).stat().st_size,sha256=hashlib.sha256((base/name).read_bytes()).hexdigest())
      for name in ('BOOT.BIN','system.dtb')}
record=dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),boot=boot,
            firmware_path=Path('/sys/module/firmware_class/parameters/path').read_text().rstrip('\n'),
            flags=Path('/sys/class/fpga_manager/fpga0/flags').read_text().strip(),
            manager_state=Path('/sys/class/fpga_manager/fpga0/state').read_text().strip(),
            receipt=Path('/tmp/rix-fpga-fsr/active-receipt.txt').read_text(),
            gpu=json.loads(command(['plgpuctl','status'])),
            post=json.loads(command(['/opt/rasterix/postproc-touch/bin/rix-superres','--status'])))
print('CNN_FINAL_STATE',json.dumps(record),flush=True)
