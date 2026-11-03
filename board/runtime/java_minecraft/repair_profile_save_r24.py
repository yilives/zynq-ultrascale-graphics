"""Preserve the unintended test save and restore the byte-verified R23 copy."""
import hashlib,importlib.util,json,shutil,sys
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard
base=Path('/tmp/rix-java125');out=Path('/tmp/postproc-tests/java256-world-r24')
data=json.loads((out/'result.json').read_text());assert data['restored'] and not data['world_source_unchanged']
assert data['error'] is None and data['java_gameplay_verified']
def hashes(folder):
    assert folder.is_dir() and not folder.is_symlink() and not any(p.is_symlink() for p in folder.rglob('*'))
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
source=base/'home/.minecraft/saves/rixjava-r24';target=base/'home/.minecraft/saves/rixjava-r23'
baseline=base/'profile-baseline-r24';backup=out/'unintended-r23-save'
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.CLIENTS=(*m.CLIENTS,'java')
with m.LinuxAdapter().locks():
    GpuRecoveryGuard().check();m.check_idle(m.LinuxAdapter().snapshot())
    assert hashes(source)==data['world_source_hashes'],'Preserve failed proof; do not restore from a changed copy'
    assert not baseline.exists() and not backup.exists()
    before=hashes(target);shutil.copytree(source,baseline);assert hashes(baseline)==data['world_source_hashes']
    target.rename(backup);shutil.copytree(source,target);assert hashes(target)==data['world_source_hashes'] and hashes(backup)==before
    report=dict(passed=True,r24_failure_preserved=True,unintended_save_preserved=str(backup),
                baseline=str(baseline),baseline_hashes=hashes(baseline),restored_r23_hashes=hashes(target),unintended_save_hashes=before)
    (out/'save-repair.json').write_text(json.dumps(report,indent=2)+'\n')
print('JAVA_PROFILE_SAVE_REPAIR_PASS original_r23_bytes_restored=1 changed_save_preserved=1')
