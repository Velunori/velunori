#!/usr/bin/env python3
"""Export a committed bundle and its pinned submodules, without workspace data."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def package(repo, ref, output):
    repo, output = Path(repo), Path(output)
    commit = git(repo, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    version = git(repo, 'show', commit + ':VERSION').decode().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?', version):
        raise ValueError('Invalid VERSION in release commit')
    if ref != 'v' + version:
        raise ValueError('Release ref must be v' + version)
    pins = {}
    for line in git(repo, 'ls-tree', '-rz', commit).split(b'\0'):
        if not line:
            continue
        metadata, path = line.split(b'\t', 1)
        mode, _, revision = metadata.split()
        if mode == b'160000':
            pins[path.decode()] = revision.decode()
    if not pins:
        raise ValueError('Release has no pinned components')
    entries = {}

    def collect(source, revision, prefix=''):
        archive = git(source, 'archive', '--format=tar', revision)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source_tar:
            for member in source_tar:
                if member.isdir():
                    continue
                if not (member.isfile() or member.issym()):
                    raise ValueError('Unsupported archive entry: ' + member.name)
                data = source_tar.extractfile(member).read() if member.isfile() else None
                member.name = prefix + member.name
                member.uid = member.gid = 0
                member.uname = member.gname = ''
                member.mtime = 0
                member.pax_headers = {}
                entries[member.name] = (member, data)

    collect(repo, commit)
    for path, revision in sorted(pins.items()):
        if not path.startswith('components/') or '..' in Path(path).parts:
            raise ValueError('Unexpected submodule path: ' + path)
        collect(repo / path, revision, path + '/')
    manifest = {'version': version, 'tag': ref, 'bundle': commit, 'components': dict(sorted(pins.items()))}
    output.mkdir(parents=True, exist_ok=True)
    base = 'velunori-' + version
    archive_path = output / (base + '.tar.gz')
    with archive_path.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as target:
                for name in sorted(entries):
                    member, data = entries[name]
                    member.name = base + '/' + name
                    target.addfile(member, io.BytesIO(data) if data is not None else None)
    manifest_path = output / (base + '.json')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    checksum = output / 'SHA256SUMS'
    checksum.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
                               for path in (archive_path, manifest_path)))
    return archive_path, manifest_path, checksum


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('--output', type=Path, default=Path('dist'))
    args = parser.parse_args()
    for artifact in package(Path(__file__).resolve().parents[1], args.tag, args.output):
        print(artifact)
