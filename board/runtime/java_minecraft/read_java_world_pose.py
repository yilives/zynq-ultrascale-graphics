"""Read saved vanilla NBT player pose; no Java/native dependencies or device writes."""
import argparse,gzip,io,json,struct
from pathlib import Path
def read_world(path):
    stream=io.BytesIO(gzip.decompress(path.read_bytes()))
    def unpack(fmt):return struct.unpack('>'+fmt,stream.read(struct.calcsize('>'+fmt)))[0]
    def string():return stream.read(unpack('H')).decode('utf-8')
    def payload(kind):
        if kind in (1,2,3,4,5,6):return unpack({1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}[kind])
        if kind==8:return string()
        if kind==9:
            element,count=unpack('B'),unpack('i');assert 0<=count<=1000000;return [payload(element) for _ in range(count)]
        if kind==10:
            value={}
            while True:
                child=unpack('B')
                if child==0:return value
                name=string();value[name]=payload(child)
        if kind in (7,11,12):
            count=unpack('i');assert 0<=count<=1000000
            if kind==7:return stream.read(count)
            return [unpack('i' if kind==11 else 'q') for _ in range(count)]
        raise ValueError(kind)
    assert unpack('B')==10;string();world=payload(10)['Data'];player=world['Player']
    return dict(position=player['Pos'],rotation=player['Rotation'],world_type=world.get('generatorName'),time=world.get('Time'))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rounds',nargs='+',default=['r25','r26','r27','r28']);parser.add_argument('--output',default='java256-world-poses-r28.json');args=parser.parse_args()
    assert all(revision.startswith('r') and revision[1:].isdigit() for revision in args.rounds) and Path(args.output).name==args.output
    base=Path('/tmp/rix-java125');results=Path('/tmp/postproc-tests');poses={'baseline':read_world(base/'profile-baseline-r24/level.dat')}
    for revision in args.rounds:
        folder=results/('java256-world-'+revision)/'finished-world-save'
        if not folder.exists():folder=base/'home/.minecraft/saves'/('rixjava-'+revision)
        poses[revision]=read_world(folder/'level.dat')
    target=results/args.output;assert not target.exists();target.write_text(json.dumps(poses,indent=2)+'\n');print(json.dumps(poses))
if __name__=='__main__':main()
