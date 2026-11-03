"""Private RAM Mali experiment: real vanilla GUI/world, completed swaps, no PL writes."""
import hashlib,importlib.util,json,os,re,shutil,signal,struct,subprocess,sys,time
from pathlib import Path

root=Path('/tmp/rix-mali-java-r1');base=Path('/tmp/rix-java125')
out=root/'world-r3';out.mkdir(exist_ok=False)
jre=base/'zulu8.98.0.107-ca-jre8.0.512-linux_aarch64'
sys.path.insert(0,'/opt/rasterix/experimental')
from game_runtime_support import GpuRecoveryGuard,GameLog
spec=importlib.util.spec_from_file_location('frozen','/tmp/fpga_fsr_control.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
hashes=lambda p:{f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()}
manifest=read(root/'world-manifest-r3.json')
record=dict(passed=False,error=None,sd_changed=False,pl_reprogrammed=False,output_scope='Mali GLES2 -> GL4ES pbuffer -> X11; no PL/LCD presentation proof')
child=None;world_source=base/'profile-baseline-r24'
env=os.environ.copy()
env.update(DISPLAY=':0',HOME=str(root/'home-world-r3'),LD_LIBRARY_PATH=':'.join(map(str,[root/'lib',root/'native',base/'native/deps',jre/'lib/aarch64',jre/'lib/aarch64/server'])),
 LIBGL_ES='1',LIBGL_FB='3',LIBGL_EGL='/usr/lib/headless/libMali.so.9.0',LIBGL_GLES='/usr/lib/headless/libMali.so.9.0',LIBGL_NOERROR='0',LIBGL_SHRINK='0',LIBGL_SILENTSTUB='0')
common=[str(jre/'bin/java'),'-Xms64m','-Xmx512m','-XX:+UseSerialGC','-Duser.home='+str(root/'home-world-r3'),'-Djava.awt.headless=false',
 '-Dsun.java2d.opengl=false','-Dsun.java2d.xrender=false','-Dorg.lwjgl.librarypath='+str(root/'native'),
 '-cp',str(root/'classes')+':'+str(base/'probe')+':'+str(base/'libs/*')]
def counter(path):
 for retry in range(100):
  a=path.read_bytes();b=path.read_bytes()
  if len(a)==len(b)==128:
   values=struct.unpack('<16Q',a);other=struct.unpack('<16Q',b)
   if values[0]==0x5249584d414c4931 and values[1]==other[1] and values[1]%2==0:return values
  time.sleep(.001)
 raise RuntimeError('Unstable swap counter')
def launch(name,command,limit):
 global child
 with GameLog(out/(name+'.log')) as log:
  child=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True);log.attach(child.stdout)
  start=time.monotonic();samples=[]
  while child.poll() is None:
   if time.monotonic()-start>limit:
    os.killpg(child.pid,signal.SIGTERM)
    try:child.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
    raise RuntimeError(name+' timed out')
   if name=='minecraft':
    proc=Path('/proc')/str(child.pid)
    try:
     samples.append(dict(monotonic_ns=time.monotonic_ns(),stat=(proc/'stat').read_text(),status=(proc/'status').read_text()))
     if len(samples)==10:
      (out/'process-maps.txt').write_text((proc/'maps').read_text())
      fd={f.name:os.readlink(str(f)) for f in (proc/'fd').iterdir() if f.exists()};(out/'process-fds.json').write_text(json.dumps(fd,indent=2))
    except FileNotFoundError:pass
   time.sleep(.5)
  code=child.returncode;child=None
  if samples:(out/'cpu-samples.json').write_text(json.dumps(samples))
  return dict(code=code,seconds=time.monotonic()-start,log=log.stats())

with m.LinuxAdapter().locks():
 try:
  GpuRecoveryGuard().check();before=m.LinuxAdapter().snapshot();m.check_idle(before);record['before']=before
  assert read(root/'compat-r5/result.json')['passed']
  assert Path('/dev/mali').exists() and Path('/sys/module/mali').exists()
  for name,digest in manifest['files'].items():assert sha(root/name)==digest,name
  assert hashes(world_source)==manifest['world_source_hashes']
  assert sha(base/'libs/client.jar')==manifest['client_sha256']
  native=root/'native';assert sha(native/'liblwjgl.so')==manifest['files']['liblwjgl-mali-probe.so']
  game=root/'home-world-r3/.minecraft'
  game.parent.mkdir(exist_ok=False);game.mkdir(exist_ok=False)
  (game/'saves').mkdir();shutil.copytree(world_source,game/'saves/rixmali-r3')
  resources=base/'home/.minecraft/resources'
  if resources.exists():shutil.copytree(resources,game/'resources')
  options=(root/'baseline-options-r75.txt').read_text().splitlines()
  # Correct vanilla Tiny key; this test reduces visible distance and is not a same-settings speedup.
  changes=dict(viewDistance='3',renderDistance='3',fancyGraphics='false',clouds='false',difficulty='0')
  options=[s for s in options if s.partition(':')[0] not in changes]+[k+':'+v for k,v in changes.items()]
  (game/'options.txt').write_text('\n'.join(options)+'\n');(out/'initial-options.txt').write_bytes((game/'options.txt').read_bytes())
  record['configuration']=dict(size=[400,240],textures='original 256x256 atlas; LIBGL_SHRINK=0',viewDistance=3,effective_distance='Tiny',graphics='Fast',difficulty='peaceful',clouds=False,warmup_seconds=60,measure_seconds=30,stationary=True)
  env['RIX_MALI_SWAP_STATS']=str(out/'probe-stats.bin');env['RIX_MALI_CAPTURE']=str(out/'probe-capture.rgba')
  record['probe']=launch('instrumented-probe',common+['MaliJavaProbeR3',str(out/'probe.rgba')],30)
  text=(out/'instrumented-probe.log').read_text(errors='replace')
  assert record['probe']['code']==0 and 'MALI_JAVA_PROBE_PASS' in text and 'MALI_RENDER_THREAD renderer=GL4ES using Mali-400 MP' in text
  probe=counter(out/'probe-stats.bin');assert probe[2]>=1 and 'MALI_JAVA_SWAP_DELTA 1' in text,probe;record['probe_completed_swaps']=probe[2]
  env['RIX_MALI_SWAP_STATS']=str(out/'swap-stats.bin');env['RIX_MALI_CAPTURE']=str(out/'world.rgba')
  world_command=common[:-2]+['-Drix.world.name=rixmali-r3','-Drix.mali.stats='+str(out/'swap-stats.bin'),'-Drix.mali.viewDistance=3']+common[-2:]+['MaliWorldHarnessR1']
  record['minecraft']=launch('minecraft',world_command,240)
  text=(out/'minecraft.log').read_text(errors='replace')
  assert '########## GL ERROR ##########' not in text,'Client GL errors; reject performance'
  assert record['minecraft']['code']==0 and 'JAVA_WORLD_ACTIVE_INTERVAL_PASS' in text and 'JAVA_WORLD_INPUT_FAILED' not in text
  assert 'MALI_RUNTIME_SETTINGS viewDistance=3' in text
  assert 'MALI_RENDER_THREAD renderer=GL4ES using Mali-400 MP' in text
  a=json.loads(re.search(r'JAVA_WORLD_STATUS_START (\{[^\n]+\})',text).group(1));b=json.loads(re.search(r'JAVA_WORLD_STATUS_END (\{[^\n]+\})',text).group(1))
  frames=b['completed']-a['completed'];seconds=(b['monotonic_ns']-a['monotonic_ns'])/1e9
  assert frames>0 and 29<seconds<35
  record['measurement']=dict(start=a,end=b,completed_swaps=frames,seconds=seconds,fps=frames/seconds,swap_fraction=(b['swap_ns']-a['swap_ns'])/(b['monotonic_ns']-a['monotonic_ns']))
  values=counter(out/'swap-stats.bin');assert values[8]==2 and values[9:13]==(400,240,0,384000),values
  pixels=(out/'world.rgba').read_bytes();assert len(pixels)==384000
  colors=len(set(pixels[n:n+3] for n in range(0,len(pixels),4)));assert colors>16,colors
  record['capture']=dict(bytes=len(pixels),sha256=hashlib.sha256(pixels).hexdigest(),colors=colors,frame=values[7],monotonic_ns=values[6],error=values[11])
  fd=read(out/'process-fds.json');maps=(out/'process-maps.txt').read_text()
  assert '/dev/mali' in fd.values() and '/tmp/rix-mali-java-r1/lib/libGL.so.1' in maps and '/usr/lib/headless/libMali.so.9.0' in maps
  assert 'llvmpipe' not in maps and 'swrast' not in maps and '/tmp/rix-fpga-java256/lib/libGL' not in maps
  record['hardware_device_open']=True;record['world_source_unchanged']=hashes(world_source)==manifest['world_source_hashes'];assert record['world_source_unchanged']
  after=m.LinuxAdapter().snapshot();m.check_idle(after);record['after']=after
  assert before['gpu']==after['gpu'] and before['post']==after['post'] and before['cnn']==after['cnn']
  record['passed']=True
 except BaseException as e:record['error']=repr(e)
 finally:
  if child is not None and child.poll() is None:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
  record['kernel_tail']=subprocess.check_output(['dmesg'],text=True)[-10000:]
  record['environment']={k:v for k,v in env.items() if k.startswith('LIBGL_') or k in ('HOME','DISPLAY','LD_LIBRARY_PATH')}
  (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('MALI_WORLD_RESULT '+json.dumps({k:record.get(k) for k in ('passed','error','measurement','capture')}),flush=True)
sys.exit(0 if record['passed'] else 2)
