"""Independent binary-command, counter/time and exact-pixel replay gate."""
import hashlib,json,struct,sys
from pathlib import Path

def verify(folder):
    folder=Path(folder);document=json.loads((folder/'result.json').read_text());r=document.get('result',document)
    for field in ('passed','diagnostic_only','ordered_texture_stores_included','group_completion_fence','snapshot_excluded_from_benchmark'):assert r[field] is True,field
    assert r['game_fps'] is False and r['source_frames']==3 and r['validation_cycles']==2
    raw=(folder/'trace.bin').read_bytes();assert raw[:8] in (b'RIXRPL1\0',b'RIXRPL2\0') and struct.unpack_from('<I',raw,8)[0]==3
    pos=12;bytes_total=0;frames=[]
    for frame in range(3):
        count=struct.unpack_from('<I',raw,pos)[0];pos+=4;assert 0<count<=8192
        types=[];swaps=triangles=stores=commits=0
        for _ in range(count):
            kind,index,address,size=struct.unpack_from('<4I',raw,pos);pos+=16
            data=raw[pos:pos+size];pos+=size;assert len(data)==size and size>0;bytes_total+=size
            assert kind in (1,2);types.append(kind)
            if kind==2:
                assert index==0 and 0x00800000<=address and address+size<=0x02000000;stores+=size;continue
            assert index<7 and address==0 and size%4==0
            offset=0
            while offset<size:
                w=struct.unpack_from('<I',data,offset)[0];offset+=4;op=w>>28
                if op in (0,2):
                    n=0
                    if op==2:swaps+=bool((w&0x14)==0x14);commits+=bool(w&1)
                elif op==1:n=4
                elif op==3:
                    n=w&0x0fffffff;assert n==192;triangles+=1
                elif op==4:n=w&0x0fffffff;assert n==256
                elif op==5:
                    assert ((w>>19)&3)<2;n=(w&0x7ffff)*4
                    assert offset+n<=size
                    pages=struct.unpack_from('<'+str(n//4)+'I',data,offset)
                    assert all(0x60800000<=a<0x62000000 and a%2048==0 for a in pages)
                else:raise AssertionError('CPU virtual/unknown opcode in GPU replay')
                assert offset+n<=size;offset+=n
            assert offset==size
        assert swaps==1 and triangles>0 and commits>=3
        frames.append(dict(events=count,swaps=swaps,triangles=triangles,commits=commits,texture_store_bytes=stores))
    restored=0
    if raw[:8]==b'RIXRPL2\0':
        count=struct.unpack_from('<I',raw,pos)[0];pos+=4;assert count<=12288
        for _ in range(count):
            kind,index,address,size=struct.unpack_from('<4I',raw,pos);pos+=16
            assert kind==2 and index==0 and 0x800000<=address and address+size<=0x2000000
            assert 0<size<=65536 and size%2048==0 and address%2048==0
            assert len(raw[pos:pos+size])==size;pos+=size;restored+=size
        assert document['resource_restore_included_in_benchmark'] is True
        assert document['resource_restore_bytes_per_cycle']==restored
    assert pos==len(raw) and bytes_total==r['captured_bytes']<=64*1024*1024
    a,b=r['before'],r['after']
    for p in (a,b):
        assert p['end_ns']>=p['begin_ns'] and p['end_ns']-p['begin_ns']<10_000_000
        s=p['status'];assert len(s)==16 and s[:4]==[0x52495801,0x9adb505e,3,1]
        assert len(set(s[4:9]))==1 and not any(s[9:14])
    completed=b['status'][7]-a['status'][7]
    seconds=((b['begin_ns']+b['end_ns'])-(a['begin_ns']+a['end_ns']))/2e9
    assert completed==r['cycles']*3==r['completed_frames'] and seconds>=3
    assert abs(seconds-r['seconds'])<1e-9 and abs(completed/seconds-r['backend_fps'])<1e-9
    files={};compared=0
    for i in range(3):
        ref=(folder/('reference-'+str(i)+'.bin')).read_bytes();assert len(ref)==192000
        for c in range(2):
            name='validation-'+str(c)+'-'+str(i)+'.bin';assert (folder/name).read_bytes()==ref;compared+=len(ref)
    assert (folder/'final.bin').read_bytes()==(folder/'reference-2.bin').read_bytes();compared+=192000
    for p in folder.iterdir():
        if p.is_file() and p.name!='verified.json':files[p.name]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return dict(passed=True,diagnostic_only=True,game_fps=False,backend_fps=r['backend_fps'],frames=frames,compared_pixel_bytes=compared,files=files,resource_restore_bytes_per_cycle=restored,trace_version=raw[6]-ord('0'))

if __name__=='__main__':
    p=Path(sys.argv[1]);result=verify(p);(p/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    print('JAVA_REPLAY_INDEPENDENT_PASS '+json.dumps({k:v for k,v in result.items() if k not in ('files','frames')}))
