#!/usr/bin/env python3
"""Build a deterministic, self-contained .sh installer from the pinned component submodules."""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import shutil
import re
import tarfile

BOOTSTRAP = r"""#!/usr/bin/env bash
# Velunori __VERSION__ — self-contained installer preview.
set -euo pipefail
command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/payload.b64" <<'__VELUNORI_DATA__'
__VELUNORI_ENCODED__
__VELUNORI_DATA__
bootstrap=$(cat <<'__VELUNORI_PYTHON__'
import base64,hashlib,io,pathlib,subprocess,sys,tarfile,tempfile
payload_file=pathlib.Path(sys.argv[1])
payload=base64.b64decode(payload_file.read_bytes(),validate=False)
digest=hashlib.sha256(payload).hexdigest()
if digest!='__VELUNORI_SHA256__':
    raise SystemExit('Installer payload checksum mismatch; download a fresh copy.')
with tempfile.TemporaryDirectory(prefix='runtime-',dir=payload_file.parent) as temporary:
    stage=pathlib.Path(temporary)
    root=stage/'package';root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        names=set()
        for member in archive:
            relative=pathlib.PurePosixPath(member.name)
            if not member.isfile() or relative.is_absolute() or '..' in relative.parts or member.name in names:
                raise SystemExit('Unsafe installer archive entry.')
            names.add(member.name)
            path=root/member.name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
            path.chmod(member.mode & 0o777)
    template=(root/'bootstrap.template').read_text()
    retained=stage/'installer.sh'
    retained.write_text(template.replace('__VELUNORI_'+'SHA256__',digest).replace('__VELUNORI_'+'ENCODED__',base64.encodebytes(payload).decode()))
    result=subprocess.run([sys.executable,'-I',str(root/'engine.py'),*sys.argv[2:],'--bootstrap-path',str(retained)])
    raise SystemExit(result.returncode)
__VELUNORI_PYTHON__
)
pipe_mode=0
[[ -n ${BASH_SOURCE[0]:-} && -f ${BASH_SOURCE[0]} ]] || pipe_mode=1
VELUNORI_STDIN_IS_SCRIPT="$pipe_mode" python3 -I -c "$bootstrap" "$work/payload.b64" "$@"
"""

ROOT=Path(__file__).resolve().parent
COMPONENTS=ROOT.parent/'components'


def runtime_files(source):
    for path in sorted(source.rglob('*')):
        relative=path.relative_to(source)
        if any(part in {'.git','.venv','__pycache__','tests','docs','dist'} for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Source symlinks are not packaged: '+str(path))
        allowed_directory=relative.parts[0] in {'scripts','components','kit','design','assets','backgrounds'}
        allowed_top=relative.name in {'README.md','LICENSE','THIRD_PARTY_NOTICES.md','manifest.json','library.json','requirements.txt','qmldir','colors.toml','hyprland.lua','chromium.theme'} or relative.suffix in {'.qml','.js','.py'}
        allowed_suffix=relative.suffix in {'.qml','.js','.mjs','.py','.sh','.svg','.png','.jpg','.jpeg','.webp','.toml','.lua','.theme','.txt'} or relative.name=='qmldir'
        if path.is_file() and not relative.name.startswith('.') and ((len(relative.parts)==1 and allowed_top) or (allowed_directory and allowed_suffix)):
            yield relative,path


def build(destination):
    catalog=json.loads((ROOT/'catalog.json').read_text())
    # Every packaged file comes from a pinned, clean submodule commit.
    sources={'lib':COMPONENTS/'lib'}
    for item in catalog['components']:
        sources.setdefault(item['name'],COMPONENTS/item['name'])
    library=json.loads((sources['lib']/'library.json').read_text())
    if library['id']!='velunori.lib' or library['apiVersion']!=catalog['library']['apiVersion']:
        raise ValueError('Library API mismatch')
    entries={'engine.py':((ROOT/'engine.py').read_bytes(),0o644), 'catalog.json':((ROOT/'catalog.json').read_bytes(),0o644)}
    provenance={}
    for name,source in sources.items():
        if not source.is_dir():raise ValueError('Missing source: '+str(source))
        commit=subprocess.run(['git','-C',str(source),'rev-parse','HEAD'],capture_output=True,text=True)
        dirty=subprocess.run(['git','-C',str(source),'status','--porcelain','--untracked-files=normal'],capture_output=True,text=True)
        if commit.returncode or dirty.returncode:
            raise ValueError('Not an initialized submodule: '+str(source))
        if dirty.stdout.strip():
            raise ValueError('Uncommitted changes in '+str(source)+'; commit them and update the pin first.')
        provenance[name]={'commit':commit.stdout.strip()}
        for relative,path in runtime_files(source):
            entries[f'components/{name}/{relative.as_posix()}']=(path.read_bytes(),path.stat().st_mode & 0o777)
    entries['bootstrap.template']=(BOOTSTRAP.replace('__VERSION__',catalog['version']).encode(),0o644)
    hashes={name:hashlib.sha256(data).hexdigest() for name,(data,_) in entries.items()}
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    info={'build':digest,'version':catalog['version'],'files':hashes,'provenance':provenance,'status':'built from pinned submodule commits'}
    entries['integrity.json']=((json.dumps(info,indent=2)+'\n').encode(),0o644)
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w',format=tarfile.PAX_FORMAT) as archive:
        for name,(data,mode) in sorted(entries.items()):
            member=tarfile.TarInfo(name);member.size=len(data);member.mode=mode;member.mtime=0
            archive.addfile(member,io.BytesIO(data))
    compressed=gzip.compress(raw.getvalue(),mtime=0)
    payload_hash=hashlib.sha256(compressed).hexdigest()
    output=BOOTSTRAP.replace('__VERSION__',catalog['version']).replace('__VELUNORI_SHA256__',payload_hash).replace('__VELUNORI_ENCODED__',base64.encodebytes(compressed).decode()).encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(output);destination.chmod(0o644)
    destination.with_suffix(destination.suffix+'.sha256').write_text(hashlib.sha256(output).hexdigest()+'  '+destination.name+'\n')
    print(f'{destination} ({len(output):,} bytes; build {digest[:12]})')
    return info


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path)
    group.add_argument('--site-dir',type=Path,help='Stage the script/checksums into a local website; never deploys')
    args=parser.parse_args()
    if args.output:
        build(args.output)
    else:
        site=args.site_dir.resolve()
        version=json.loads((ROOT/'catalog.json').read_text())['version']
        relative=f'downloads/velunori-{version}.sh'
        target=site/relative
        build(target)
        shutil.copyfile(target,site/'install.sh')
        (site/'install.sh.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  install.sh\n')
        for name in ['index.html','guide.html']:
            path=site/name
            text=path.read_text()
            text=re.sub(r'downloads/velunori-[0-9A-Za-z.-]+\.sh(?![A-Za-z0-9])',relative,text)
            path.write_text(text)
        print('Staged locally; no GitHub or Pages publication performed.')
