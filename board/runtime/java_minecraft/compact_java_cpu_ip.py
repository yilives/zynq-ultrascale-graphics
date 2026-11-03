"""Preserve compact JIT address metadata with hashes of the full raw log/archive."""
import hashlib,json,os,tarfile,xml.etree.ElementTree as E
from pathlib import Path
base=Path('/tmp/postproc-tests');folder=base/'java256-world-r33'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
full=base/'java256-r33-menu-evidence.tar.gz';assert full.is_file()
tree=E.parse(folder/'jit.xml');methods=[dict(node.attrib) for node in tree.iter('nmethod')]
events=[dict(kind=kind,**node.attrib) for kind in ('make_not_entrant','code_cache_full') for node in tree.iter(kind)]
metadata=dict(jit_xml_sha256=sha(folder/'jit.xml'),jit_xml_bytes=(folder/'jit.xml').stat().st_size,
    methods=methods,events=events,full_archive_sha256=sha(full),full_archive_bytes=full.stat().st_size)
(folder/'jit-addresses.json').write_text(json.dumps(metadata,indent=2)+'\n')
target=base/'java256-r33-cpu-compact.tar.gz'
with target.open('xb') as stream,tarfile.open(fileobj=stream,mode='w:gz') as tar:
    for name in ('result.json','ip-counts.json','ip-profile.json','ip-maps-before.txt','ip-maps-after.txt','ip-sampler.log','jit-addresses.json','minecraft.log'):
        tar.add(str(folder/name),arcname=name,recursive=False)
parts=[];data=full.read_bytes()
for index,offset in enumerate(range(0,len(data),240000)):
    path=base/('java256-r33-cpu-part'+str(index)+'.bin')
    with path.open('xb') as output:output.write(data[offset:offset+240000])
    parts.append(dict(name=path.name,bytes=path.stat().st_size,sha256=sha(path)))
(folder/'full-archive-parts.json').write_text(json.dumps(parts,indent=2)+'\n')
print('JAVA_CPU_COMPACT',target.stat().st_size,sha(target),'nmethods',len(methods),'full_bytes',len(data))
print('JAVA_CPU_ARCHIVE_PARTS',json.dumps(parts))
