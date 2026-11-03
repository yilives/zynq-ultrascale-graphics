#!/usr/bin/env python3
"""Read only the Goodix ID/config on the new touch bus, never scan PS buses."""
import ctypes as c,fcntl,json,os
from pathlib import Path
adapters=[p for p in Path('/sys/class/i2c-adapter').glob('i2c-*') if 'i2c-touch' in str(p.resolve())]
if len(adapters)!=1:raise SystemExit('Expected one experimental i2c-touch adapter; found '+str(adapters))
class Msg(c.Structure):_fields_=[('addr',c.c_uint16),('flags',c.c_uint16),('length',c.c_uint16),('buf',c.c_void_p)]
class Transfer(c.Structure):_fields_=[('msgs',c.POINTER(Msg)),('count',c.c_uint32)]
fd=os.open('/dev/'+adapters[0].name,os.O_RDWR)
def read(addr,register,length):
 tx=(c.c_ubyte*2)(register>>8,register&255);rx=(c.c_ubyte*length)()
 msgs=(Msg*2)(Msg(addr,0,2,c.addressof(tx)),Msg(addr,1,length,c.addressof(rx)));transfer=Transfer(msgs,2)
 fcntl.ioctl(fd,0x0707,bytes(transfer));return bytes(rx)
found=[]
try:
 for addr in (0x5d,0x14):
  try:
   ident=read(addr,0x8140,6);config=read(addr,0x8047,10)
   entry={'adapter':adapters[0].name,'address':hex(addr),'id_ascii':ident[:4].rstrip(b'\0').decode('ascii','replace'),'firmware':int.from_bytes(ident[4:],'little'),'config_version':config[0],'factory_x':int.from_bytes(config[1:3],'little'),'factory_y':int.from_bytes(config[3:5],'little'),'max_touches':config[5]&15,'interrupt_mode':config[6]&3}
   found.append(entry);print('GOODIX_CONTROLLER '+json.dumps(entry),flush=True)
  except OSError as error:print('GOODIX_ADDRESS_ABSENT '+hex(addr)+' '+str(error),flush=True)
finally:os.close(fd)
if not found:raise SystemExit('No Goodix controller responded on the experimental touch bus')
