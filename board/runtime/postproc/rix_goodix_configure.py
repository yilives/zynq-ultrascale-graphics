#!/usr/bin/env python3
"""Adapt the verified GT911 IRQ polarity to Xilinx 2020.1 rising-only GPIO."""
import ctypes as c,fcntl,hashlib,json,os,time
from pathlib import Path
assert os.geteuid()==0
adapters=[p for p in Path('/sys/class/i2c-adapter').glob('i2c-*')if 'i2c-touch'in str(p.resolve())]
assert len(adapters)==1,'Expected one experimental touch adapter'
bus=adapters[0].name;address=0x5d
class Msg(c.Structure):_fields_=[('addr',c.c_uint16),('flags',c.c_uint16),('length',c.c_uint16),('buf',c.c_void_p)]
class Transfer(c.Structure):_fields_=[('msgs',c.POINTER(Msg)),('count',c.c_uint32)]
fd=os.open('/dev/'+bus,os.O_RDWR)
def transaction(messages):
 msgs=(Msg*len(messages))(*messages);fcntl.ioctl(fd,0x0707,bytes(Transfer(msgs,len(msgs))))
def read(register,length):
 tx=(c.c_ubyte*2)(register>>8,register&255);rx=(c.c_ubyte*length)()
 transaction([Msg(address,0,2,c.addressof(tx)),Msg(address,1,length,c.addressof(rx))]);return bytes(rx)
def write(config):
 data=bytes([0x80,0x47])+config;buf=(c.c_ubyte*len(data)).from_buffer_copy(data)
 transaction([Msg(address,0,len(data),c.addressof(buf))]);time.sleep(.05)
def digest(data):return hashlib.sha256(data).hexdigest()
try:
 ident=read(0x8140,6);assert ident[:4].rstrip(b'\0')==b'911','Only verified GT911 configuration layout is supported'
 current=read(0x8047,186);assert sum(current[:-1])&255==0,'Invalid existing GT911 configuration checksum; refusing changes'
 assert int.from_bytes(current[1:3],'little')==800 and int.from_bytes(current[3:5],'little')==480,'Unexpected panel resolution'
 base=Path('/opt/rasterix/postproc-touch');base.mkdir(parents=True,exist_ok=True);backup=base/'gt911-factory-config.bin'
 if not backup.exists():
  with backup.open('xb')as f:f.write(current);f.flush();os.fsync(f.fileno())
  (base/'gt911-factory-config.json').write_text(json.dumps({'id_hex':ident.hex(),'sha256':digest(current),'bytes':186,'original_interrupt_mode':current[6]&3})+'\n');os.sync()
 else:
  previous=backup.read_bytes();meta=json.loads((base/'gt911-factory-config.json').read_text());assert len(previous)==186 and digest(previous)==meta['sha256']and meta['id_hex']==ident.hex()
 if current[6]&3:
  node=Path('/sys/bus/i2c/devices')/(bus[4:]+'-005d')
  assert not(node/'driver').exists(),'Unbind Goodix before changing controller configuration'
  updated=bytearray(current);updated[6]&=~3;updated[-2]=(-sum(updated[:-2]))&255;updated[-1]=1
  try:
   write(bytes(updated));actual=read(0x8047,186)
   assert actual[:-1]==bytes(updated[:-1]),'GT911 rising-edge configuration readback mismatch'
  except BaseException:
   restore=bytearray(current);restore[-1]=1;write(bytes(restore));raise
  print('GOODIX_IRQ_RISING_CONFIGURED '+json.dumps({'backup_sha256':digest(backup.read_bytes()),'active_sha256':digest(actual),'changed_offsets':[i for i in range(186)if current[i]!=actual[i]],'width':800,'height':480}),flush=True)
 else:print('GOODIX_IRQ_RISING_ALREADY_ACTIVE',flush=True)
finally:os.close(fd)
