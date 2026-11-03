#!/usr/bin/env python3
"""Read the physical Goodix evdev without grabbing it away from Xorg."""
import argparse,fcntl,json,os,select,struct,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=30);p.add_argument('--output',type=Path);a=p.parse_args()
assert 0<a.seconds<=3600
devices=[q for q in Path('/sys/class/input').glob('event*/device/name') if 'goodix' in q.read_text().lower()]
if len(devices)!=1:raise SystemExit('Expected one physical Goodix device; found '+str(len(devices)))
node=Path('/dev/input')/devices[0].parent.parent.name
fd=os.open(node,os.O_RDONLY|os.O_NONBLOCK)
def axis(code):
 data=bytearray(24);fcntl.ioctl(fd,0x80184540+code,data);return dict(zip(('value','min','max','fuzz','flat','resolution'),struct.unpack('6i',data)))
report={'device':str(node),'name':devices[0].read_text().strip(),'x_axis':axis(0x35),'y_axis':axis(0x36),'events':0,'sync_reports':0,'tracking_starts':0,'positions':[],'grabbed':False}
print('TOUCH_MONITOR_READY '+json.dumps(report),flush=True)
event=struct.Struct('llHHi');pending=b'';end=time.monotonic()+a.seconds;xs=[];ys=[];position={}
try:
 while time.monotonic()<end:
  if not select.select([fd],[],[],min(.5,max(0,end-time.monotonic())))[0]:continue
  pending+=os.read(fd,event.size*64)
  while len(pending)>=event.size:
   _,_,kind,code,value=event.unpack(pending[:event.size]);pending=pending[event.size:];report['events']+=1
   if kind==3 and code==0x39 and value>=0:report['tracking_starts']+=1
   if kind==3 and code==0x35:xs.append(value);position['x']=value
   if kind==3 and code==0x36:ys.append(value);position['y']=value
   if kind==0 and code==0:
    report['sync_reports']+=1
    if position and len(report['positions'])<256:report['positions'].append(dict(position))
finally:os.close(fd)
report['observed_x']=[min(xs),max(xs)]if xs else None;report['observed_y']=[min(ys),max(ys)]if ys else None
report['physical_contacts_observed']=report['tracking_starts']>0 and bool(xs)and bool(ys)
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print('TOUCH_MONITOR_RESULT '+json.dumps(report),flush=True)
