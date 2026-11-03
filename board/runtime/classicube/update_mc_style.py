#!/usr/bin/env python3
"""Update the verified optional MC style v1 add-on to v2, retaining rollback."""
import argparse
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import time

OLD_SHA = '89c1478f4406a0f98d9862392caea619cde27dc1bc948b4dc1171b763917522b'
OLD_COMMAND_SHA = 'f726754576b35dfe89d93dd77bd386b21ff38f4e8cb72ac05efc76726e0e9f1c'
SD = Path('/media/sd-mmcblk1p1')
OLD_ARCHIVE = SD / 'rasterix-mc-style-v1.tar.gz'
TARGET = SD / 'rasterix-mc-style-v2.tar.gz'
BACKUP = SD / 'rasterix-mc-style-v1-command.py'
COMMAND = Path('/usr/bin/rix-classicube-style')
SOURCE = Path('/tmp/mc-style-v2.tar.gz')
ROOT_GUARD = 32 * 1024 * 1024
SD_GUARD = 16 * 1024 * 1024
CLIENTS = ('ClassiCube', 'tuxracer', 'neverball', 'neverputt', 'quakespasm',
           'quake3e', 'rix-glx-probe', 'rix-smoke', 'th06-rix', 'rix-danmaku',
           'rix-superres', 'rix-neural-style')
ERRORS = ('read_errors', 'write_errors', 'timeouts', 'underflows', 'scan_errors')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None,
            'SHA256 must be exactly 64 lowercase hexadecimal characters')
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON object key')
        result[key] = value
    return result


def canonical_name(name, prefix=False):
    require(isinstance(name, str) and '\\' not in name and '\x00' not in name,
            'Invalid archive path')
    path = PurePosixPath(name)
    require(path.as_posix() == name and not path.is_absolute(), 'Noncanonical archive path')
    parts = path.parts
    require(bool(parts) and all(re.fullmatch('[A-Za-z0-9_.-]+', p) is not None and p not in ('.', '..') for p in parts),
            'Unsafe archive path component')
    if prefix:
        require(parts[0] == 'mc-style' and 2 <= len(parts) <= 3, 'Invalid mc-style member path')
        return '/'.join(parts[1:])
    require(1 <= len(parts) <= 2 and name != 'manifest.json', 'Invalid payload manifest path')
    return name


def validate_archive(data, expected):
    """Validate all payloads before any persistent filesystem mutation."""
    digest(expected)
    require(sha(data) == expected, 'New archive SHA mismatch')
    require(data[:2] == b'\x1f\x8b' and len(data) <= 1536000, 'Expected bounded gzip archive')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as tf:
        members = tf.getmembers()
        require(1 < len(members) <= 64, 'Invalid archive member count')
        names = [m.name for m in members]
        require(len(names) == len(set(names)), 'Duplicate tar member')
        total = 0
        for member in members:
            canonical_name(member.name, prefix=True)
            require(member.isfile() and not member.pax_headers and 0 <= member.size <= 4 * 1024 * 1024,
                    'Only bounded regular files without alternate PAX paths are accepted')
            total += member.size
        require(total <= 8 * 1024 * 1024 and 'mc-style/manifest.json' in names, 'Missing or oversized manifest archive')
        manifest_member = tf.getmember('mc-style/manifest.json')
        require(manifest_member.size <= 65536, 'Oversized manifest')
        manifest = json.loads(tf.extractfile(manifest_member).read().decode('utf-8'), object_pairs_hook=unique_object)
        require(isinstance(manifest, dict) and bool(manifest), 'Manifest must be a nonempty object')
        for name, entry in manifest.items():
            canonical_name(name)
            require(isinstance(entry, dict) and set(entry) == {'bytes', 'sha256'}, 'Invalid payload metadata')
            require(type(entry['bytes']) is int and 0 <= entry['bytes'] <= 4 * 1024 * 1024, 'Invalid payload byte count')
            digest(entry['sha256'])
        require(set(names) == {'mc-style/' + n for n in manifest} | {'mc-style/manifest.json'}, 'Archive/manifest member mismatch')
        required = {'bin/rix-neural-style', 'bin/rix-neural-games', 'bin/rix-classicube-style',
                    'bin/rix-classicube-neural-source', 'models/oil.cnn', 'models/anime.cnn'}
        require(required <= set(manifest), 'Missing runnable add-on payload')
        for name, entry in manifest.items():
            blob = tf.extractfile('mc-style/' + name).read()
            require(len(blob) == entry['bytes'] and sha(blob) == entry['sha256'], 'Payload SHA/size mismatch: ' + name)
    return manifest


def render_bootstrap(old_command, from_sha, new_sha):
    require(digest(from_sha) == OLD_SHA, 'This updater accepts only the known v1 package')
    require(digest(new_sha) != OLD_SHA, 'v2 package must differ from v1')
    require(sha(old_command) == OLD_COMMAND_SHA, 'Unknown installed command; preserve it before updating')
    old_path = repr(OLD_ARCHIVE.as_posix()).encode('ascii')
    old_digest = repr(from_sha).encode('ascii')
    require(old_command.count(old_path) == 1 and old_command.count(old_digest) == 1,
            'Old bootstrap literal anchors must occur exactly once')
    path_line = b'\narchive=Path(' + old_path + b')\n'
    hash_line = b'\nexpected=' + old_digest + b'\n'
    require(old_command.count(path_line) == 1 and old_command.count(hash_line) == 1,
            'Old bootstrap assignment anchors changed')
    result = old_command.replace(old_path, repr(TARGET.as_posix()).encode('ascii')).replace(old_digest, repr(new_sha).encode('ascii'))
    compile(result, '<mc-style-v2-bootstrap>', 'exec')
    return result


def regular_bytes(path):
    require(not path.is_symlink() and path.is_file(), 'Expected a regular non-symlink file: ' + str(path))
    return path.read_bytes()


def fsync_directory(directory):
    # The Windows host test exercises byte-level transaction behavior only.
    # Production is root Linux; vfat may reject directory fsync, so sync there.
    if os.name != 'posix':
        return
    fd = os.open(str(directory), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        try:
            os.fsync(fd)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
            os.sync()
    finally:
        os.close(fd)


def write_new_or_match(path, data, mode=0o644):
    """Never overwrite an unknown path; a completed identical retry is safe."""
    require(not path.is_symlink(), 'Refuse a symlink destination: ' + str(path))
    if path.exists():
        require(regular_bytes(path) == data, 'Existing destination has unknown contents: ' + str(path))
        return False
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(str(path), flags, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    require(regular_bytes(path) == data, 'Persistent readback mismatch: ' + str(path))
    fsync_directory(path.parent)
    return True


def commit_files(target, backup, command, old_command, package, bootstrap):
    """Stage/verify SD files, then use one atomic command replacement."""
    require(regular_bytes(command) == old_command, 'Installed command changed before staging')
    write_new_or_match(target, package)
    write_new_or_match(backup, old_command)
    require(regular_bytes(target) == package and regular_bytes(backup) == old_command,
            'SD package/rollback backup readback failed before command commit')
    temp = command.with_name(command.name + '.v2-incoming')
    require(not temp.exists() and not temp.is_symlink(), 'Unknown root command staging file')
    created = False
    try:
        created = write_new_or_match(temp, bootstrap, 0o755)
        temp.chmod(0o755)
        with temp.open('r+b') as stream:
            os.fsync(stream.fileno())
        require(regular_bytes(command) == old_command, 'Installed command changed before atomic commit')
        temp.replace(command)
        fsync_directory(command.parent)
        require(regular_bytes(command) == bootstrap, 'Committed command readback failed')
    finally:
        # This name was required absent and created by us, never an old file.
        if created and temp.exists() and not temp.is_symlink() and temp.read_bytes() == bootstrap:
            temp.unlink()


def verify_idle(gpu, post):
    require(gpu['status'] == 3 and gpu['config'] == 0x9adb505e, 'Unexpected GPU state/configuration')
    require(all(type(gpu[k]) is int and gpu[k] == 0 for k in ERRORS), 'GPU fault counters must be present and zero')
    require(len({gpu[k] for k in ('frame_id', 'swap', 'copy', 'presented', 'last_presented')}) == 1,
            'GPU queues have not drained')
    require(post['requested'] == post['active'] and (post['requested'] & 3) in (0, 1), 'Postprocessor scanout must be idle')
    require(post['snapshot_status'] == 0 and post['snapshot_expirations'] == 0, 'Snapshot lease/expiration counters must be clear')


@contextlib.contextmanager
def idle_locks():
    import fcntl
    with contextlib.ExitStack() as stack:
        for name in ('rasterix-game-launch.lock', 'rix-superres.lock', 'rix-mc-style-extract.lock'):
            path = Path('/tmp') / name
            require(not path.is_symlink(), 'Refuse a symlink lock path')
            fd = os.open(str(path), os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            stream = stack.enter_context(os.fdopen(fd, 'a+'))
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = subprocess.run(['pidof'] + list(CLIENTS), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        require(active.returncode == 1 and not active.stdout.strip(), 'An active GPU/postprocess client prevents updating')
        gpu = json.loads(subprocess.check_output(['plgpuctl', 'status'], universal_newlines=True))
        post = json.loads(subprocess.check_output(['/opt/rasterix/postproc-touch/bin/rix-superres', '--status'], universal_newlines=True))
        verify_idle(gpu, post)
        time.sleep(.03)
        stable = json.loads(subprocess.check_output(['plgpuctl', 'status'], universal_newlines=True))
        verify_idle(stable, post)
        require(all(stable[k] == gpu[k] for k in ('frame_id', 'command_beats', 'gpu_busy_cycles')), 'GPU activity changed while updater holds locks')
        yield {'gpu': stable, 'post': post}


def available(path):
    vfs = os.statvfs(str(path))
    return vfs.f_bavail * vfs.f_frsize


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--from-sha256', default=OLD_SHA)
    args = parser.parse_args(argv)
    require(os.name == 'posix' and os.geteuid() == 0, 'Root Linux is required')
    require(args.archive == SOURCE and not SOURCE.is_symlink() and SOURCE.resolve() == Path('/tmp').resolve() / SOURCE.name,
            'New archive must be the regular /tmp/mc-style-v2.tar.gz RAM file')
    require(SD.is_mount() and not SD.is_symlink() and SD.resolve() == SD, 'Expected mounted SD boot partition')
    require(not COMMAND.parent.is_symlink() and COMMAND.parent.resolve() == COMMAND.parent
            and os.stat(str(COMMAND.parent)).st_dev == os.stat('/').st_dev,
            'Command directory must remain on the measured root filesystem')
    require(not Path('/opt/rasterix/experimental/gpu-quarantine.json').exists(), 'GPU quarantine must be resolved before updating')
    package = regular_bytes(SOURCE)
    manifest = validate_archive(package, args.sha256)
    old_package = regular_bytes(OLD_ARCHIVE)
    require(digest(args.from_sha256) == OLD_SHA and sha(old_package) == OLD_SHA, 'Known complete v1 rollback archive is required')
    old_command = regular_bytes(COMMAND)
    bootstrap = render_bootstrap(old_command, args.from_sha256, args.sha256)
    # The conservative guards reserve both staging copies and rollback bytes,
    # even though the unique SD archive is written once with O_EXCL.
    require(available(Path('/')) >= ROOT_GUARD + len(bootstrap) + 8192, 'Keep 32 MiB root guard plus temporary bootstrap')
    require(available(SD) >= SD_GUARD + 2 * len(package) + 2 * len(old_command) + 8192,
            'Keep 16 MiB SD guard including new package and rollback staging')
    with idle_locks() as idle:
        require(sha(regular_bytes(OLD_ARCHIVE)) == OLD_SHA and sha(regular_bytes(COMMAND)) == OLD_COMMAND_SHA,
                'v1 package/command changed while obtaining ownership locks')
        require(available(Path('/')) >= ROOT_GUARD + len(bootstrap) + 8192,
                'Root space changed while obtaining ownership locks')
        require(available(SD) >= SD_GUARD + 2 * len(package) + 2 * len(old_command) + 8192,
                'SD space changed while obtaining ownership locks')
        commit_files(TARGET, BACKUP, COMMAND, old_command, package, bootstrap)
        os.sync()
        require(sha(regular_bytes(OLD_ARCHIVE)) == OLD_SHA and regular_bytes(BACKUP) == old_command,
                'v1 rollback archive/command bytes were not preserved')
        require(regular_bytes(TARGET) == package and regular_bytes(COMMAND) == bootstrap, 'Final v2 readback mismatch')
        record = {'verified': True, 'package_sha256': args.sha256, 'bytes': len(package), 'archive': str(TARGET),
                  'command': str(COMMAND), 'command_sha256': sha(bootstrap), 'from_package_sha256': OLD_SHA,
                  'rollback_archive': str(OLD_ARCHIVE), 'rollback_command': str(BACKUP), 'rollback_command_sha256': sha(old_command),
                  'manifest_verified_files': len(manifest), 'root_free': available(Path('/')), 'sd_free': available(SD),
                  'guard_root': ROOT_GUARD, 'guard_sd': SD_GUARD, 'ownership_before': idle}
        require(record['root_free'] >= ROOT_GUARD and record['sd_free'] >= SD_GUARD, 'Final storage guard failed')
        out = Path('/tmp/postproc-tests')
        require(not out.is_symlink(), 'Report output must remain in RAM')
        out.mkdir(exist_ok=True)
        require(out.resolve() == Path('/tmp').resolve() / out.name, 'Report output escaped RAM')
        report = out / 'cc_style_update_v2.json'
        require(not report.is_symlink(), 'Refuse symlink update report')
        report.write_text(json.dumps(record, indent=2) + '\n')
    print('MC_STYLE_V2_UPDATED', json.dumps(record), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
