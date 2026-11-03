"""Adopt the verified original quality in RAM options only, while the GPU is idle."""
import base64,hashlib,importlib.util,json,os,sys,zlib
from pathlib import Path

EXPECTED=dict(viewDistance=3,fpsLimit=1,fancyGraphics=False,clouds=False,difficulty=0,
              ao=True,particles=0,bobView=True,advancedOpengl=False,anaglyph3d=False,fov=0.0,gamma=0.0)
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
adapter=m.LinuxAdapter()
sha=lambda data:hashlib.sha256(data).hexdigest()
with adapter.locks():
    GpuRecoveryGuard().check();before=adapter.snapshot();m.check_idle(before)
    assert not before['clients']
    receipt_path=Path('/tmp/rix-fpga-fsr/active-receipt.txt')
    receipt=receipt_path.read_text().splitlines()
    assert receipt[1]==before['boot_id'] and receipt[2]=='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
    folder=Path('/tmp/java-quality-selection-r133');folder.mkdir(mode=0o700)
    path=Path('/tmp/rix-java125/home/.minecraft/options.txt');assert path.is_file() and not path.is_symlink()
    original=path.read_bytes()
    with (folder/'original-options.txt').open('xb') as stream:stream.write(original)
    changes={key:str(value).lower() for key,value in EXPECTED.items()}
    lines=[line for line in original.decode('utf-8').splitlines() if line.partition(':')[0] not in changes]
    lines.extend(key+':'+value for key,value in changes.items())
    selected=('\n'.join(lines)+'\n').encode()
    if selected!=original:
        temporary=path.with_name('options.txt.quality-r133.new')
        with temporary.open('xb') as stream:
            stream.write(selected);stream.flush();os.fsync(stream.fileno())
        temporary.chmod(0o600);os.replace(temporary,path)
    assert path.read_bytes()==selected
    parsed=dict(line.split(':',1) for line in path.read_text().splitlines() if ':' in line)
    assert all(parsed[key]==value for key,value in changes.items())
    after=adapter.snapshot();m.check_idle(after);GpuRecoveryGuard().check()
    assert not after['clients'] and before['boot_id']==after['boot_id']
    assert before['gpu']==after['gpu'] and before['post']==after['post']
    assert receipt_path.read_text().splitlines()==receipt
    record=dict(passed=True,quality_profile='original',expected_visual_settings=EXPECTED,
        actual_options={key:parsed[key] for key in changes},options_path=str(path),
        backup_path=str(folder/'original-options.txt'),changed=selected!=original,
        original_sha256=sha(original),selected_sha256=sha(selected),gpu_unchanged=True,
        before=before,after=after,receipt=receipt,board_boot_id=before['boot_id'],
        sd_or_autostart_updated=False,game_started=False)
record['locks_released']=True
raw=(json.dumps(record,indent=2)+'\n').encode()
with (folder/'adoption.json').open('xb') as stream:stream.write(raw)
print('QUALITY_SELECTED_ZLIB '+sha(raw)+' '+base64.b64encode(zlib.compress(raw)).decode(),flush=True)
