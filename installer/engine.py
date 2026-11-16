#!/usr/bin/env python3
"""Velunori selection, prerequisite checks and transactional copied installation."""
import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


def ask(prompt):
    # A piped Bash installer has script bytes on stdin; use its controlling tty
    # for user choices instead of consuming the script or silently choosing all.
    if os.environ.get('VELUNORI_STDIN_IS_SCRIPT') == '1' and not sys.stdin.isatty():
        try:
            descriptor=os.open('/dev/tty',os.O_RDWR)
            try:
                os.write(descriptor,prompt.encode())
                answer=bytearray()
                while True:
                    value=os.read(descriptor,1)
                    if not value:raise EOFError('No answer received from the terminal.')
                    if value==b'\n':break
                    answer.extend(value)
                return answer.decode('utf-8',errors='replace').rstrip('\r')
            finally:
                os.close(descriptor)
        except OSError:
            pass
    try:
        return input(prompt)
    except EOFError as error:
        raise EOFError('No interactive terminal/answer available. Run from a terminal; use --all or --components for selection.') from error


def identity(entry):
    return entry.get('id') if isinstance(entry, dict) else entry


def atomic_write(path, content):
    mode=path.stat().st_mode & 0o777 if path.exists() and not path.is_symlink() else 0o600
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    os.fchmod(descriptor,mode)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def configuration(before, selected):
    """Change only selected components, preserving stock/custom bar otherwise."""
    result = copy.deepcopy(before)
    bar = result.setdefault('bar', {})
    layout = bar.setdefault('layout', {})
    disabled = result.setdefault('disabledPlugins', [])
    restores = result.setdefault('cloneSourceRestores', [])
    plugins = result.setdefault('plugins', [])
    for component in selected:
        name, plugin = component['name'], component.get('id')
        if name == 'theme':
            continue
        if name == 'bar':
            bar['id'] = plugin
            continue
        source = component.get('replaces')
        if source and component.get('clone') and source not in disabled:
            disabled.append(source)
            if plugin not in restores:
                restores.append(plugin)
        if plugin in disabled:
            disabled.remove(plugin)
        if component['section']:
            found = False
            removed = {'omarchy.monitor','omarchy.network','omarchy.audio','omarchy.power','omarchy.indicators'} if name == 'control-center' else set()
            for section, entries in list(layout.items()):
                if not isinstance(entries, list):
                    continue
                output = []
                for entry in entries:
                    entry_id = identity(entry)
                    if entry_id in (source, plugin):
                        if not found:
                            replacement = dict(entry) if isinstance(entry, dict) else {}
                            replacement['id'] = plugin
                            output.append(replacement)
                            found = True
                    elif entry_id not in removed:
                        output.append(entry)
                layout[section] = output
            if not found:
                layout.setdefault(component['section'], []).append({'id':plugin})
            plugins[:] = [entry for entry in plugins if identity(entry) != plugin]
        elif plugin not in [identity(entry) for entry in plugins]:
            plugins.append(plugin)
    if not disabled:
        result.pop('disabledPlugins', None)
    if not restores:
        result.pop('cloneSourceRestores', None)
    return result


class Installer:
    def __init__(self, package, prefix=None):
        self.package = Path(package).resolve()
        self.catalog = json.loads((self.package / 'catalog.json').read_text())
        self.home = Path.home()
        self.config_dir = Path(os.environ.get('XDG_CONFIG_HOME', str(self.home / '.config'))) / 'omarchy'
        self.config = self.config_dir / 'shell.json'
        self.plugins = self.config_dir / 'plugins'
        # The receipt has its own subdirectory: velunori/ also holds component data such as velunori/clock.
        self.prefix = Path(prefix).expanduser().absolute() if prefix else Path(os.environ.get('XDG_DATA_HOME', str(self.home / '.local/share'))) / 'velunori' / 'installation'
        self.receipt = self.prefix / 'installation.json'
        self.omarchy = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
        self.pam = Path('/etc/pam.d/omarchy-lock-password')

    def select(self, names=None, all_components=False, cloud=False):
        available = {item['name']:item for item in self.catalog['components']}
        names = list(available) if all_components else (names or [])
        if not names:
            raise ValueError('Select --all or --components NAME,NAME. Use plan --all to explore.')
        unknown = set(names) - available.keys()
        if unknown:
            raise ValueError('Unknown components: ' + ', '.join(sorted(unknown)) + '. Core is now named bar; lib is resolved automatically.')
        if cloud and 'clock' not in names:
            raise ValueError('--cloud requires the clock component.')
        return [item for item in self.catalog['components'] if item['name'] in names]

    def needs_library(self, selected):
        return any(item['name'] != 'theme' for item in selected)

    def run(self, *args, capture=False, timeout=60):
        return subprocess.run(list(map(str,args)), capture_output=capture, text=True, timeout=timeout,
                              env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})

    def query(self, *args):
        try:
            result = self.run(*args, capture=True, timeout=5)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def verify(self):
        info = json.loads((self.package / 'integrity.json').read_text())
        actual={p.relative_to(self.package).as_posix() for p in self.package.rglob('*') if p.is_file()}
        if actual != set(info['files']) | {'integrity.json'} or any(p.is_symlink() for p in self.package.rglob('*')):
            raise ValueError('Package inventory contains unexpected or missing files.')
        for name, digest in info['files'].items():
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe package inventory path.')
            path = self.package / relative
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Package integrity failure: ' + name)
        return info['build']

    def plan(self, selected, cloud=False):
        print('Velunori ' + self.catalog['version'] + ' — installation plan')
        print('Components: ' + ', '.join(item['title'] for item in selected))
        print('Shared library: ' + ('API 1, included automatically; no bar activated' if self.needs_library(selected) else 'not required'))
        print('Calendar cloud libraries: ' + ('download into the clock private environment' if cloud else 'not selected'))
        print('Floating Bars: ' + ('will replace the selected bar' if any(x['name']=='bar' for x in selected) else 'not selected; current bar stays in place'))
        print('Plugin location: ' + str(self.plugins))
        print('Receipt and backups: ' + str(self.prefix))
        print('Files are copied; no workspace shortcuts or source links are created.')
        if any(x['name']=='theme' for x in selected):
            print('Dusk: WILL apply theme and wallpaper immediately.')
        if any(x['name']=='lockscreen' for x in selected):
            print('Serene: selected; unchanged Omarchy lock service must match. No locking/authentication test is run.')
        print('Installation may restart the shell. It never runs a system update or connects accounts.')

    def check(self, selected, cloud=False):
        self.verify()
        failures = []
        def require(condition, message):
            print(('OK   ' if condition else 'FAIL ') + message)
            if not condition:
                failures.append(message)
        require(os.geteuid() != 0, 'Run as your desktop user, without sudo.')
        commands = {'bash','omarchy','omarchy-shell'}
        if self.needs_library(selected):
            commands.add('quickshell')
        for item in selected:
            commands.update(item['commands'])
        for command in sorted(commands):
            require(bool(shutil.which(command)), 'Required command: ' + command)
        require(self.config.is_file() and not self.config.is_symlink(), 'A regular Omarchy shell.json is available.')
        if self.config.is_file():
            try:
                value = json.loads(self.config.read_text())
                valid = isinstance(value,dict) and value.get('version') == 1
            except (ValueError,OSError):
                valid = False
            require(valid, 'shell.json is valid and has version 1.')
        require(not self.prefix.exists() and not self.prefix.is_symlink(), 'Installation receipt directory is unused; existing installs are not overwritten.')
        require(os.access(self.config_dir, os.W_OK | os.X_OK), 'Omarchy configuration directory is writable.')
        parent = self.prefix.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        require(parent.is_dir() and os.access(parent,os.W_OK | os.X_OK), 'Installation data parent is writable.')
        require(not self.plugins.is_symlink(), 'Plugin directory is not a redirected directory.')
        require(not self.plugins.exists() or (self.plugins.is_dir() and os.access(self.plugins,os.W_OK | os.X_OK)), 'Plugin directory is writable or can be created.')
        for item in selected:
            if item.get('id'):
                target = self.plugins / item['id']
                require(not target.exists() and not target.is_symlink(), 'No conflicting installation: ' + item['id'])
                manifest = json.loads((self.package/'components'/item['name']/'manifest.json').read_text())
                require(manifest['id'] == item['id'], 'Packaged manifest matches ' + item['id'])
                require(manifest.get('velunori',{}).get('dependencies',{}).get('velunori.lib',{}).get('apiVersion') == 1,
                        'Library API declared by ' + item['id'])
        if self.needs_library(selected):
            library = self.plugins/'lib'
            if library.exists() or library.is_symlink():
                try:
                    metadata=json.loads((library/'library.json').read_text())
                    compatible=not library.is_symlink() and metadata['id']=='velunori.lib' and metadata['apiVersion']==1 and (1,0,0)<=tuple(map(int,metadata['version'].split('.')))<(2,0,0)
                except (OSError,ValueError,KeyError,TypeError):
                    compatible=False
                require(compatible,'Existing shared library is compatible; it will be retained.')
        if 'omarchy-shell' in commands and shutil.which('omarchy-shell'):
            require(self.query('omarchy-shell','shell','ping') == 'ok', 'Omarchy shell responds.')
            require(self.query('omarchy-shell','lock','isLocked') == 'false', 'Desktop is unlocked (read-only query).')
            try:
                inventory=json.loads(self.query('omarchy-shell','shell','listPlugins') or 'null')
                valid=isinstance(inventory,list) and all(isinstance(p,dict) and isinstance(p.get('id'),str) for p in inventory)
            except ValueError:
                inventory=None;valid=False
            require(valid,'Shell plugin inventory is available.')
            if valid:
                for item in selected:
                    source=item.get('replaces')
                    conflicts=[p['id'] for p in inventory if source and p.get('enabled') and p.get('clonedFrom')==source and p['id']!=item['id']]
                    require(not conflicts,'No active replacement conflict for '+item['title'])
        if any(x['name']=='lockscreen' for x in selected):
            host=self.omarchy/'shell/plugins/lock/Service.qml'
            bundled=self.package/'components/lockscreen/Service.qml'
            require(host.is_file() and host.read_bytes()==bundled.read_bytes(),'Serene service matches installed Omarchy byte for byte.')
            require(self.pam.is_file() and os.access(self.pam,os.R_OK),'Omarchy PAM configuration exists; authentication is not invoked.')
        if any(x['name']=='theme' for x in selected):
            previous=self.query('omarchy','theme','current')
            require(bool(previous) and previous!='Unknown','Current theme is identifiable for recovery.')
        if cloud:
            require(importlib.util.find_spec('venv') is not None and importlib.util.find_spec('ensurepip') is not None,'Python venv/pip support is available.')
        return not failures

    @contextmanager
    def lock(self):
        self.config_dir.mkdir(parents=True,exist_ok=True)
        descriptor=os.open(self.config_dir/'.velunori-install.lock',os.O_WRONLY|os.O_CREAT,0o600)
        try:
            try:
                fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError('Another Velunori installation is running.') from error
            yield
        finally:
            os.close(descriptor)

    def save(self, receipt):
        atomic_write(self.receipt,(json.dumps(receipt,indent=2)+'\n').encode())

    def wait_for(self, predicate):
        for _ in range(30):
            if predicate():
                return True
            time.sleep(.2)
        return False

    def inventory_ready(self, selected, enabled=False):
        try:
            inventory=json.loads(self.query('omarchy-shell','shell','listPlugins') or 'null')
            return isinstance(inventory,list) and all(any(p.get('id')==item['id'] and (not enabled or p.get('enabled')) for p in inventory) for item in selected if item.get('id'))
        except (ValueError,TypeError,AttributeError):
            return False

    def install(self, selected, cloud=False, confirm=input, bootstrap=None):
        self.plan(selected,cloud)
        if not self.check(selected,cloud):
            raise ValueError('Prerequisite checks failed. Nothing was installed.')
        if confirm('Type INSTALL to apply this plan: ') != 'INSTALL':
            raise ValueError('Installation cancelled.')
        with self.lock():
            if not self.check(selected,cloud):
                raise ValueError('Prerequisites changed; nothing was installed.')
            before=self.config.read_bytes()
            before_doc=json.loads(before)
            after=(json.dumps(configuration(before_doc,selected),indent=2)+'\n').encode() if any(x.get('id') for x in selected) else before
            previous_theme=self.query('omarchy','theme','current') if any(x['name']=='theme' for x in selected) else None
            self.prefix.mkdir(parents=True,mode=0o700)
            (self.prefix/'backups').mkdir(mode=0o700)
            atomic_write(self.prefix/'backups/shell.before.json',before)
            receipt={'schemaVersion':1,'version':self.catalog['version'],'build':self.verify(),'id':uuid.uuid4().hex,
                     'components':[x['name'] for x in selected],'cloud':cloud,'phase':'preparing',
                     'previousTheme':previous_theme,'owned':[]}
            self.save(receipt)
            if bootstrap:
                shutil.copyfile(bootstrap,self.prefix/'installer.sh')
                (self.prefix/'installer.sh').chmod(0o600)
            created=[]
            config_changed=False
            theme_attempted=False
            try:
                self.plugins.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.velunori-stage-',dir=self.plugins) as temporary:
                    stage=Path(temporary)
                    names=[x['name'] for x in selected if x.get('id')]
                    if self.needs_library(selected) and not (self.plugins/'lib').exists():
                        names.insert(0,'lib')
                    for name in names:
                        target_name='lib' if name=='lib' else next(x['id'] for x in selected if x['name']==name)
                        shutil.copytree(self.package/'components'/name,stage/target_name)
                        atomic_write(stage/target_name/'.velunori-owner.json',json.dumps({'installation':receipt['id'],'build':receipt['build']}).encode())
                        if name!='lib' and self.run('omarchy','plugin','validate',stage/target_name).returncode:
                            raise ValueError('Native manifest validation failed: '+name)
                    for name in names:
                        target_name='lib' if name=='lib' else next(x['id'] for x in selected if x['name']==name)
                        target=self.plugins/target_name
                        if target.exists() or target.is_symlink():
                            raise ValueError('Installation path changed: '+str(target))
                        (stage/target_name).rename(target)
                        created.append(target)
                        receipt['owned'].append(target_name)
                        self.save(receipt)
                if cloud:
                    if self.run('bash',self.plugins/'velunori.clock/scripts/setup-deps.sh',timeout=900).returncode:
                        raise ValueError('Calendar dependency setup failed.')
                if selected and any(x.get('id') for x in selected):
                    if self.run('omarchy-shell','shell','rescanPlugins').returncode or not self.wait_for(lambda:self.inventory_ready(selected)):
                        raise ValueError('Plugin discovery did not complete.')
                if self.config.read_bytes()!=before:
                    raise ValueError('Shell configuration changed during preparation; it was not overwritten.')
                if after != before:
                    atomic_write(self.config,after)
                    config_changed=True
                receipt['phase']='activating';self.save(receipt)
                if any(x.get('id') for x in selected):
                    if self.run('omarchy','restart','shell').returncode or not self.wait_for(lambda:self.query('omarchy-shell','shell','ping')=='ok' and self.inventory_ready(selected,True)):
                        raise ValueError('Selected plugins did not become enabled after shell restart.')
                if any(x['name']=='theme' for x in selected):
                    shutil.copytree(self.package/'components/theme',self.prefix/'theme')
                    theme_attempted=True
                    if self.run('bash',self.prefix/'theme/scripts/install-local.sh',timeout=120).returncode:
                        raise ValueError('Dusk theme activation failed.')
                receipt['phase']='installed';self.save(receipt)
                print('Installed. Receipt and recovery snapshot: '+str(self.prefix))
                print('No account was connected, desktop locked, or system update run.')
                return 0
            except (OSError,ValueError,subprocess.SubprocessError) as error:
                safe=self.config.read_bytes() in (before,after)
                restored=not config_changed
                if safe and config_changed:
                    atomic_write(self.config,before)
                    restored=self.run('omarchy','restart','shell').returncode==0
                if safe and restored:
                    recovery=self.prefix/'recovery';recovery.mkdir(exist_ok=True,mode=0o700)
                    owned_paths=[]
                    for path in created:
                        try:
                            owned=not path.is_symlink() and json.loads((path/'.velunori-owner.json').read_text())['installation']==receipt['id']
                        except (OSError,ValueError,KeyError):
                            owned=False
                        if owned:
                            owned_paths.append(path)
                    if len(owned_paths)==len(created):
                        for path in reversed(created):
                            path.rename(recovery/path.name)
                        receipt['phase']='failed-restored'
                    else:
                        # Keep dependencies together if any new path changed ownership.
                        receipt['phase']='needs-recovery'
                else:
                    receipt['phase']='needs-recovery'
                    print('Configuration changed or restoration failed. Installed files were retained; review the saved snapshot.',file=sys.stderr)
                if theme_attempted and previous_theme and (self.query('omarchy','theme','current') or '').lower()=='velunori':
                    if self.run('omarchy','theme','set',previous_theme).returncode:
                        receipt['phase']='needs-recovery'
                receipt['error']=str(error);self.save(receipt)
                raise ValueError(str(error)+' Recovery information: '+str(self.prefix)) from error

    def status(self):
        if not self.receipt.is_file():
            print('No managed installation at '+str(self.prefix));return 0
        receipt=json.loads(self.receipt.read_text())
        print(json.dumps({key:receipt.get(key) for key in ['version','build','components','cloud','phase']},indent=2))
        return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='install',choices=['plan','check','install','status'])
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--all',action='store_true')
    group.add_argument('--components',help='Comma-separated component names; lib is included automatically')
    parser.add_argument('--cloud',action='store_true',help='Download optional calendar libraries; requires clock')
    parser.add_argument('--prefix',type=Path,help='Permanent installation receipt/backup directory')
    parser.add_argument('--bootstrap-path',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    try:
        installer=Installer(Path(__file__).resolve().parent,args.prefix)
        if args.action=='status':return installer.status()
        names=args.components.split(',') if args.components is not None else None
        if not names and not args.all:
            if args.action!='install':
                parser.error('Select --all or --components NAME,NAME.')
            print('1. Entire suite\n2. Choose components')
            choice=ask('Choose 1 or 2: ').strip()
            if choice not in ('1','2'):raise ValueError('Choose 1 (entire suite) or 2 (individual components).')
            if choice=='1':args.all=True
            else:
                print('Available: '+', '.join(x['name'] for x in installer.catalog['components']))
                names=[value.strip() for value in ask('Components (comma-separated): ').split(',')]
        selected=installer.select(names,args.all,args.cloud)
        installer.verify()
        if args.action=='plan':installer.plan(selected,args.cloud);return 0
        if args.action=='check':return 0 if installer.check(selected,args.cloud) else 1
        return installer.install(selected,args.cloud,confirm=ask,bootstrap=args.bootstrap_path)
    except (OSError,ValueError,KeyError,TypeError,EOFError,subprocess.SubprocessError) as error:
        print('Velunori: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':
    sys.exit(main())
