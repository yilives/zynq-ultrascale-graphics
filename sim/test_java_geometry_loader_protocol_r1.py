"""Test-only CSR layout exercises generation; never a hardware CSR source."""
import contextlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from prepare_java_geometry_loader_r1 import generate
layout=dict(CONTROL=0,RETURN=16,MEM=28,MODE=40,COUNT=52,SEQUENCE=64)
class Fake:
 def __init__(self,mem_bits):self.reg={0:4};self.writes=[];self.bits=mem_bits;self.bad=False;self.busy=False
 @contextlib.contextmanager
 def mmio(self,address):assert address==0xa0040000;yield self
 def read32(self,mm,offset):
  value=self.reg.get(offset,0)
  if offset==0 and value&2:self.reg[0]&=~2
  return value
 def write32(self,mm,offset,value):
  self.writes.append((offset,value));self.reg[offset]=value
  if offset==0 and value==1:
   result=0x47454f31 if self.reg[layout['MODE']]==0 else 1<<32
   if self.bad:result+=1
   self.reg[layout['RETURN']]=result&0xffffffff;self.reg[layout['RETURN']+4]=result>>32
   self.reg[0]=0 if self.busy else 6
count=0
for bits in (32,64):
 namespace={'__name__':'geometry_loader_test','__file__':__file__}
 exec(compile(generate((ROOT/'linux/postproc/fpga_fsr_control.py').read_bytes(),'a'*64,layout,bits),'loader-mock','exec'),namespace)
 fake=Fake(bits);result=namespace['verify_geometry_protocol'](fake)
 assert result['passed'] and [c['mode'] for c in result['commands']]==[0,99]
 assert ((layout['MEM']+4,0) in fake.writes)==(bits==64);count+=1
 fake=Fake(bits);fake.bad=True
 try:namespace['verify_geometry_protocol'](fake)
 except RuntimeError as error:assert 'response mismatch' in str(error);count+=1
 else:raise AssertionError('bad return accepted')
 fake=Fake(bits);fake.reg[0]=0
 try:namespace['verify_geometry_protocol'](fake)
 except RuntimeError as error:assert 'not idle' in str(error);count+=1
 else:raise AssertionError('busy core accepted')
 assert not fake.writes
 text=generate((ROOT/'linux/postproc/fpga_fsr_control.py').read_bytes(),'a'*64,layout,bits)
 assert "require(not self.a.module_loaded('rix_geometry')" in text
 assert 'RIX_JAVA_GEOMETRY_ACTIVE_V1' in text and "final['geometry']=verify_geometry_protocol" in text
 count+=1
print('GEOMETRY_LOADER_MOCK_PROTOCOL_PASS cases='+str(count)+' hardware_executed=0')
