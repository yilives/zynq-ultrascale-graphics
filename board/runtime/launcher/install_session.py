#!/usr/bin/env python3
"""Verify a v3 package, then optionally extract a new private board RAM copy."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import tarfile


def verify(path, expected):
    assert path.stat().st_size <= 16 * 1024 * 1024
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    assert actual == expected, 'Package SHA256 mismatch'
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as source:
        for member in source:
            name = PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and '..' not in name.parts
            assert name.parts[0] == 'rasterix-launcher-v3' and len(name.parts) > 1
            relative = '/'.join(name.parts[1:])
            assert relative not in files and member.name == 'rasterix-launcher-v3/' + relative
            assert 0 <= member.size <= 40 * 1024 * 1024
            total += member.size
            assert total <= 80 * 1024 * 1024 and len(files) < 256
            data = source.extractfile(member).read()
            assert len(data) == member.size
            files[relative] = data
    manifest = json.loads(files['package-manifest.json'])['files']
    assert set(files) == set(manifest) | {'package-manifest.json'}
    for name, entry in manifest.items():
        assert len(files[name]) == entry['bytes'] and hashlib.sha256(files[name]).hexdigest() == entry['sha256']
    return files, dict(passed=True, package_sha256=actual, package_bytes=len(raw), files=len(files),
                       extracted_bytes=total, gpu_access=False, boot_files_changed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--destination', type=Path, default=Path('/tmp/rasterix-launcher-v3'))
    args = parser.parse_args()
    assert len(args.sha256) == 64 and all(char in '0123456789abcdef' for char in args.sha256)
    files, result = verify(args.archive, args.sha256)
    if not args.verify_only:
        assert os.geteuid() == 0 and platform.machine() == 'aarch64'
        target = args.destination
        assert target.is_absolute() and target.parent == Path('/tmp') and target.name.startswith('rasterix-launcher-v3')
        assert target.parent.resolve() in (Path('/tmp'), Path('/var/volatile/tmp'))
        assert not target.exists() and not target.is_symlink(), 'Keep existing installation and evidence'
        os.umask(0o077)
        target.mkdir(mode=0o700)
        for name, data in files.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open('xb') as stream:
                stream.write(data)
            path.chmod(0o700 if name in ('rix-launcher', 'java/rix-fsr-pl') else 0o600)
        result['installed'] = str(target)
        (target / 'install-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print('LAUNCHER_V3_RAM_PACKAGE_VERIFIED ' + json.dumps(result), flush=True)
