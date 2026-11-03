#!/usr/bin/env python3
"""One locked RAM-only full-256 trial, followed by verified original-v23 restore."""
import argparse,contextlib,fcntl,hashlib,importlib.util,json,os,re,shutil,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import DisplayStatus,GameLog,GpuRecoveryGuard
STAGE=Path('/tmp/rix-fpga-java256');RESTORE=Path('/tmp/rix-fpga-java256-restore')
LEGACY=Path('/tmp/rix-fpga-fsr/active-receipt.txt')
JBASE=Path('/tmp/rix-java125');JRE=JBASE/'zulu8.98.0.107-ca-jre8.0.512-linux_aarch64'
RESULT_ROOT=Path('/tmp/postproc-tests')
LOCK_ROOT=Path('/tmp')
LOADER_PATH=Path('/tmp/fpga_fsr_control.py')
PROOF_PATH=RESULT_ROOT/'cc_fsr_fpga_load.json'
ERRORS=('read_errors','write_errors','timeouts','underflows','scan_errors')
IDS=('frame_id','swap','copy','presented','last_presented')
OLD_BIT='035c30597ce7ed94dff24a733dbbb81fa68998e8d3fba52ef45902d23ccb01d9'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,d):Path(p).write_text(json.dumps(d,indent=2)+'\n')
def new_copy(src,dst):
    if dst.exists():assert not dst.is_symlink() and sha(src)==sha(dst);return
    with dst.open('xb') as f:f.write(src.read_bytes())
    dst.chmod(0o600)
def set_trial_nearest(adapter):
    # Parent owns rix-superres.lock; do not reacquire it through a child CLI.
    with adapter.mmio(0xa0010000) as mm:
        post=adapter.post_from_mmio(mm)
        assert post['requested']==post['active']==1
        assert post['snapshot_status']==post['snapshot_expirations']==0
        assert adapter.read32(mm,8)==3
        adapter.write32(mm,0x54,0)
        until=time.monotonic()+2
        while adapter.read32(mm,0x58)!=0:
            if time.monotonic()>until:raise RuntimeError('Nearest mode acknowledgement timeout')
            time.sleep(.01)

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--attempt',required=True)
    p.add_argument('--interaction',choices=('none','singleplayer'),default='none')
    p.add_argument('--presentation',choices=('pipeline','serial'),default='pipeline')
    args=p.parse_args();assert args.execute and re.fullmatch('[a-z0-9_-]{1,40}',args.attempt)
    out=RESULT_ROOT/args.attempt;out.mkdir(mode=0o700)
    journals={key:RESULT_ROOT/(args.attempt+'-'+key+'-journal.json') for key in ('load','restore')}
    assert all(not f.exists() and not f.is_symlink() for f in journals.values())
    expected=read(STAGE/'delivery.json')
    restore_dir=RESTORE
    if expected.get('swap_fence'):
        assert expected['swap_fence']==dict(offset=0xa8,magic=0x53574631)
        restore_dir=RESTORE.with_name(RESTORE.name+'-'+expected['files']['new.bin']['sha256'][:12])
    for name,item in expected['files'].items():assert sha(STAGE/name)==item['sha256'],name
    for name,item in expected.get('existing_java_files',{}).items():assert sha(JBASE/name)==item['sha256'],name
    base_path=LOADER_PATH
    assert sha(base_path)=='6f4f34f440094cde3d858ad14f405f9d600cfd4ded5c5f011e9c00f52d09b92d'
    spec=importlib.util.spec_from_file_location('java256_frozen_loader',base_path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.CLIENTS=(*m.CLIENTS,'java')
    locks=[]
    record=dict(passed=False,pass_scope='full_texture256_rgba_mojang_and_original_restore',
        java_gameplay_verified=False,java_fps=None,loads={},tests={},restored=False,error=None)
    process=None;device=None;unsafe=False;switched=False;initial=None;legacy_bytes=None;retired=False;controller_started=False
    guard=GpuRecoveryGuard()
    def interrupted(*_):raise RuntimeError('Trial interrupted')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        for name in m.LOCKS:
            fd=os.open(str(LOCK_ROOT/name),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            f=os.fdopen(fd,'a+');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(f)
        guard.check()
        initial=m.LinuxAdapter().snapshot();m.check_idle(initial)
        boot=initial['boot_id'];proof=read(PROOF_PATH)
        assert proof['passed'] and proof['after']['boot_id']==boot and proof['manifest']['images']['new']['sha256']==OLD_BIT
        legacy_bytes=LEGACY.read_bytes()
        assert legacy_bytes.decode().splitlines()[1:3]==[boot,OLD_BIT]
        assert sha(STAGE/'old.bin')==OLD_BIT
        backup=out/'original-fsr-receipt.txt';backup.write_bytes(legacy_bytes);backup.chmod(0o600)
        # Prepare both directions before retiring the original receipt or touching PL.
        restore_dir.mkdir(mode=0o700,exist_ok=True)
        new_copy(STAGE/'old.bin',restore_dir/'new.bin');new_copy(STAGE/'new.bin',restore_dir/'old.bin')
        inverse=dict(format='rix-fpga-ram-fsr1',source_sha256=legacy_bytes.decode().splitlines()[3],images={})
        for role in ('new','old'):
            f=restore_dir/(role+'.bin');inverse['images'][role]=dict(filename=f.name,bytes=f.stat().st_size,sha256=sha(f))
        manifest=restore_dir/'manifest.json'
        if manifest.exists():assert read(manifest)==inverse
        else:save(manifest,inverse);manifest.chmod(0o600)
        record.update(boot_id=boot,before=initial,delivery=expected,restore_directory=str(restore_dir))
        save(out/'result.json',record)
        # The old global receipt is retired while the alternative bitstream is active.
        LEGACY.unlink();retired=True
        def transaction(restoring):
            nonlocal switched,controller_started
            m.BASE=restore_dir if restoring else STAGE
            m.MANIFEST=m.BASE/'manifest.json'
            # Frozen loader requires the journal directory to be directly under /tmp.
            m.REPORT=journals['restore' if restoring else 'load']
            class Adapter(m.LinuxAdapter):
                @contextlib.contextmanager
                def locks(self):
                    # All three exact launch/POST locks are already owned by this parent.
                    assert len(locks)==len(m.LOCKS) and all(not f.closed for f in locks)
                    for f,name in zip(locks,m.LOCKS):
                        assert os.fstat(f.fileno()).st_ino==os.stat(LOCK_ROOT/name).st_ino
                    yield
                def rollback_proof(self,b,bit):
                    source=read(journals['load']) if restoring else proof
                    assert source['passed'] and source['outcome']=='new-loaded-and-verified'
                    assert source['after']['boot_id']==b and source['manifest']['images']['new']['sha256']==bit
                def activate_receipt(self,b,bit,source):
                    if restoring:
                        assert bit==OLD_BIT and legacy_bytes.decode().splitlines()[1:]==[b,bit,source]
                        assert not LEGACY.exists()
                        with LEGACY.open('xb') as f:f.write(legacy_bytes);f.flush();os.fsync(f.fileno())
                        LEGACY.chmod(0o600)
                    else:
                        path=STAGE/'active-receipt.txt';assert not path.exists()
                        with path.open('x') as f:
                            f.write('RIX_TEX256_CACHE_ACTIVE_V1\n'+b+'\n'+bit+'\n'+source+'\n');f.flush();os.fsync(f.fileno())
                        path.chmod(0o600)
                def verify_fsr_protocol(self):
                    result=super().verify_fsr_protocol()
                    if not restoring:
                        with self.mmio(0xa0010000) as mm:
                            values=[self.read32(mm,n) for n in (0x98,0x9c,0xa0,0xa4)]
                        assert values==[0x54584331,0x01000100,1024,7]
                        result['texture_profile']=values
                        if expected.get('swap_fence'):
                            with self.mmio(0xa0010000) as mm:
                                fence=self.read32(mm,expected['swap_fence']['offset'])
                            assert fence==expected['swap_fence']['magic']
                            result['swap_fence_magic']=fence
                    return result
            adapter=Adapter();controller=m.Controller(adapter)
            controller_started=True
            result=controller.run(adapter.read_manifest)
            # Set the fabric state before any fallible CPU-side evidence writes.
            if not restoring and result['passed']:switched=True
            record['loads']['restore' if restoring else 'candidate']=result
            record['journal_paths']={k:str(v) for k,v in journals.items()}
            save(out/'result.json',record)
            return result
        load=transaction(False)
        if not load['passed']:
            if not load['device_mutation_started'] or load['rollback']['passed']:
                assert not LEGACY.exists()
                LEGACY.write_bytes(legacy_bytes);LEGACY.chmod(0o600)
                record['restored']=True
            else:unsafe=True
            raise RuntimeError('Candidate transaction failed: '+str(load.get('error')))
        switched=True
        control=m.LinuxAdapter();control.set_enabled(1);set_trial_nearest(control)
        device=DisplayStatus()
        env=os.environ.copy()
        env.update(DISPLAY=':0',HOME=str(JBASE/'home'),LD_LIBRARY_PATH=':'.join(map(str,[
            STAGE/'lib',JBASE/'native',JRE/'lib/aarch64',JRE/'lib/aarch64/server'])))
        # The Java launcher must not inherit another game's presentation policy.
        env.update(RIX_PRESENT_SYNC='1',RIX_PRESENT_STRATEGY=args.presentation)
        record['presentation_env']={key:env[key] for key in ('RIX_PRESENT_SYNC','RIX_PRESENT_STRATEGY')}
        common=[str(JRE/'bin/java'),'-Xms64m','-Xmx512m','-XX:+UseSerialGC',
            '-Duser.home='+str(JBASE/'home'),'-Djava.awt.headless=false','-Dsun.java2d.opengl=false',
            '-Dsun.java2d.xrender=false','-Dorg.lwjgl.librarypath='+str(JBASE/'native'),
            '-Drix.java125.closeSeconds=25','-cp',str(STAGE/'classes')+':'+str(JBASE/'probe')+':'+str(JBASE/'libs/*')]
        tests=[('texture256',['Java256TextureProbe',str(out/'texture256.ppm')]),
               ('mojang256',['Java256MojangProbe',str(out/'mojang256.ppm')]),
               ('minecraft',['Java256ClientHarness'])]
        if expected.get('tmu_guard'):tests.insert(0,('tmu_bounds',['Java256TmuProbe']))
        if expected.get('swap_fence'):tests.insert(0,('swap_stress',['Java256SwapProbe']))
        for name,tail in tests:
            before=device.read();start=time.monotonic();expired=False
            test_env=dict(env)
            if name=='swap_stress':test_env['RIX_JAVA_LAST_FRONT']=str(out/'swap-stress-front-before-reset.bin')
            if name=='minecraft':
                test_env['RIX_JAVA_LAST_FRONT']=str(out/'minecraft-front-before-reset.bin')
                # Keep probes and the default menu trial independent of input automation.
                test_env.pop('RIX_JAVA_MENU_CLICK',None)
                if args.interaction=='singleplayer':test_env['RIX_JAVA_MENU_CLICK']='singleplayer'
            with GameLog(out/(name+'.log')) as log:
                command=common+tail
                if name=='tmu_bounds' and expected['tmu_guard'].get('probe_backend')=='native':
                    command=['python3',str(STAGE/'native_tmu_bounds.py')]
                process=subprocess.Popen(command,env=test_env,cwd=str(JBASE/'home/.minecraft'),
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
                log.attach(process.stdout)
                try:code=process.wait(timeout=45)
                except BaseException:
                    expired=True;process.terminate()
                    try:code=process.wait(timeout=8)
                    except subprocess.TimeoutExpired:process.kill();code=process.wait(timeout=5)
            process=None
            deadline=time.monotonic()+5
            while True:
                after=device.read()
                if len({after[k] for k in IDS})==1 or time.monotonic()>deadline:break
                time.sleep(.05)
            unsafe=expired or code<0 or any(after[k]!=before[k] for k in ERRORS) or len({after[k] for k in IDS})!=1 or log.errors['transport_errors']>0
            text=(out/(name+'.log')).read_text(errors='replace')
            record['tests'][name]=dict(exit_code=code,expired=expired,seconds=time.monotonic()-start,
                before=before,after=after,log=log.stats(),texture_pass='JAVA256_TEXTURE_PASS' in text,
                mojang_pass='JAVA256_MOJANG_PASS' in text,
                normal_close='JAVA125_NORMAL_CLOSE_REQUEST' in text,
                gl_failure_lines=[line for line in text.splitlines() if any(s in line.lower() for s in (
                    'openglexception','gl error','texture is too big','invalid enum','invalid value'))])
            save(out/'result.json',record)
            if unsafe:raise RuntimeError('Unsafe Java termination or GPU failure')
            if name=='texture256' and (code!=0 or 'JAVA256_TEXTURE_PASS' not in text):
                raise RuntimeError('Full-resolution texture validation failed')
            if name=='tmu_bounds':
                backend=expected['tmu_guard'].get('probe_backend','java')
                marker='JAVA256_TMU_NATIVE_PASS' if backend=='native' else 'JAVA256_TMU_PASS'
                record['tests'][name]['probe_backend']=backend
                record['tests'][name]['bounds_pass']=marker+' cases=12 state_preserved=1 real_tmu_count=1' in text
                save(out/'result.json',record)
                if code!=0 or not record['tests'][name]['bounds_pass']:
                    raise RuntimeError('Texture-unit error/state validation failed')
            if name=='swap_stress':
                front=out/'swap-stress-front-before-reset.bin';metadata=read(str(front)+'.json')
                a,b=metadata['before'],metadata['after']
                assert metadata['before_default_buffer_reset'] and metadata['format']=='RGB565'
                assert (metadata['width'],metadata['height'],metadata['bytes'])==(400,240,192000)
                assert len(a)==len(b)==16 and a[:3]==b[:3]==[0x52495801,0x9adb505e,3]
                assert len(set(a[4:9]+b[4:9]))==1 and not any(a[9:14]+b[9:14])
                assert front.read_bytes()==b'\x00\xf8'*(400*240),'Full red front buffer mismatch'
                # LWJGL also swaps when creating its window. Count actual GLX calls.
                calls=metadata['renderer_swaps']
                matched=(calls>=121 and a[4]-before['presented']==calls and after['presented']==a[4]+1)
                record['tests'][name]['front_before_reset']=dict(metadata,sha256=sha(front),final_presented_after_destroy=after['presented'])
                record['tests'][name]['swap_stress_pass']=code==0 and matched and 'JAVA256_SWAP_PASS frames=121' in text
                save(out/'result.json',record)
                if not record['tests'][name]['swap_stress_pass']:
                    raise RuntimeError('121-swap stress pixel/frame accounting failed')
            if name=='mojang256' and (code!=0 or 'JAVA256_MOJANG_PASS' not in text):
                raise RuntimeError('Original 256 RGBA PNG validation failed')
            if name=='minecraft':
                front=out/'minecraft-front-before-reset.bin'
                metadata=read(str(front)+'.json')
                assert metadata['before_default_buffer_reset'] and metadata['format']=='RGB565'
                assert (metadata['width'],metadata['height'],metadata['bytes'])==(400,240,192000)
                assert front.stat().st_size==192000 and metadata['renderer_swaps']>0
                a,b=metadata['before'],metadata['after']
                assert len(a)==len(b)==16 and a[:3]==b[:3]==[0x52495801,0x9adb505e,3]
                assert len(set(a[4:9]+b[4:9]))==1 and a[4]>0
                assert not any(a[9:14]+b[9:14])
                record['tests'][name]['front_before_reset']=dict(metadata,sha256=sha(front),
                    final_presented_after_destroy=after['presented'])
                save(out/'result.json',record)
                if code!=0 or not record['tests'][name]['normal_close'] or record['tests'][name]['gl_failure_lines']:
                    raise RuntimeError('Original client GL/normal-close validation failed')
                matched=metadata['before'][4]-before['presented']==metadata['renderer_swaps']
                record['tests'][name]['swap_accounting_matched']=matched
                save(out/'result.json',record)
                if expected.get('swap_fence') and not matched:
                    raise RuntimeError('Fenced original client swap accounting failed')
            if code==0 and not unsafe and after['presented']>before['presented']:
                sys.path.insert(0,'/tmp/rasterix-classicube/ffa912210b7c/bin')
                from rix_capture_source import capture_source
                record['tests'][name]['source_capture']=capture_source(out/(name+'-source'),after['frame_id'])
                save(out/'result.json',record)
            if name=='minecraft' and args.interaction=='singleplayer':
                observed=('JAVA256_INPUT_SINGLEPLAYER_CLICK 200,118' in text and
                          'JAVA256_GUI mw 400x240' in text and 'JAVA256_INPUT_FAILED' not in text)
                record['tests'][name]['interaction']=dict(requested='singleplayer',observed=observed)
                save(out/'result.json',record)
                if not observed:raise RuntimeError('Singleplayer mouse input was not observed')
    except BaseException as exc:
        record['error']=repr(exc)
    finally:
        if process is not None and process.poll() is None:unsafe=True
        if device is not None:device.close();device=None
        if retired and not switched and not LEGACY.exists() and not unsafe:
            if not controller_started:
                LEGACY.write_bytes(legacy_bytes);LEGACY.chmod(0o600);record['restored']=True
            else:
                # An unexpected controller exception has no verified rollback receipt.
                unsafe=True
        if switched and not unsafe:
            try:
                control=m.LinuxAdapter();control.set_post_mode1();control.wait_post_mode1()
                restore=transaction(True)
                if restore['passed']:
                    record['restored']=True
                    (STAGE/'active-receipt.txt').rename(out/'retired-256-receipt.txt')
                else:
                    unsafe=True
                    if LEGACY.exists():LEGACY.unlink()
            except BaseException as exc:
                unsafe=True;record['restore_error']=repr(exc)
        if initial is not None:
            try:record['after']=m.LinuxAdapter().snapshot()
            except BaseException as exc:record['after_error']=repr(exc)
        if unsafe:
            guard.mark(args.attempt,dict(reason=record.get('error') or record.get('restore_error') or 'Unsafe profile trial',
                exit_code=record.get('tests',{}).get('minecraft',{}).get('exit_code'),transport_errors=True,
                after=record.get('after')))
            try:
                active=STAGE/'active-receipt.txt'
                if active.exists():active.rename(out/'invalidated-256-receipt.txt')
                if LEGACY.exists() and not record['restored']:LEGACY.unlink()
            except BaseException as exc:record['receipt_retirement_error']=repr(exc)
        record['passed']=bool(record['restored'] and not unsafe and record.get('tests',{}).get('texture256',{}).get('texture_pass')
            and record.get('tests',{}).get('mojang256',{}).get('mojang_pass'))
        save(out/'result.json',record)
        for f in reversed(locks):f.close()
    print('JAVA256_TRIAL_RESULT',json.dumps({k:record[k] for k in ('passed','restored','error','java_gameplay_verified','java_fps')}),flush=True)
    return 0 if record['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
