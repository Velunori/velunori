"""Read-only prerequisites shared by --check and the actual bundle installation.

Only fixed, read-only Omarchy queries are executed. No installers, package
managers, account providers or configuration writers are invoked here.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PAM_CONFIG = Path('/etc/pam.d/omarchy-lock-password')
COMMANDS = ('git', 'omarchy', 'omarchy-shell', 'quickshell', 'pactl', 'ip',
            'hyprctl', 'systemd-run', 'checkupdates', 'omarchy-update')
PLUGINS = ('core', 'clock', 'control-center', 'notifications', 'menu', 'weather', 'update')


class Report:
    def __init__(self):
        self.failures = 0

    def check(self, condition, success, failure):
        print(('OK   ' if condition else 'FAIL ') + (success if condition else failure),
              file=sys.stdout if condition else sys.stderr)
        if not condition:
            self.failures += 1
        return bool(condition)


def query(*args):
    """Bound the time spent waiting for a desktop IPC response; never echo it."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=4,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def writable_directory(path):
    """Inspect the nearest existing parent without creating a directory."""
    while not path.exists() and not path.is_symlink():
        if path == path.parent:
            return False
        path = path.parent
    return path.is_dir() and os.access(path, os.W_OK | os.X_OK)


def same_link(path, target):
    try:
        return path.is_symlink() and path.resolve(strict=True) == target.resolve(strict=True)
    except (OSError, RuntimeError):
        return False


def check_prerequisites(suite, *, theme=True, lockscreen=True, cloud=True):
    report = Report()
    suite = Path(suite).resolve()
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'omarchy'
    omarchy = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    plugins = [*PLUGINS, *(['lockscreen'] if lockscreen else [])]
    components = [*plugins, *(['theme'] if theme else [])]
    print('Read-only prerequisite check (selected installation options):')
    report.check(os.geteuid() != 0, 'Running as a desktop user.',
                 'Run as your desktop user, without sudo.')

    available = {}
    for command in COMMANDS:
        available[command] = bool(shutil.which(command))
        report.check(available[command], f'Command available: {command}',
                     f'Missing required command: {command}')
    manifests = {}
    for component in components:
        folder = suite / 'components' / component
        report.check((folder / 'scripts/install-local.sh').is_file(),
                     f'Installer present: {component}',
                     f'Missing {component} installer. Run: git submodule update --init --recursive')
        if component == 'theme':
            continue
        try:
            manifest = json.loads((folder / 'manifest.json').read_text())
            valid = isinstance(manifest, dict) and manifest.get('id') == f'velunori.{component}'
        except (OSError, ValueError):
            manifest, valid = {}, False
        if report.check(valid, f'Manifest valid: {component}',
                        f'Missing or invalid {component} manifest. Check the component checkout.'):
            manifests[component] = manifest
    if 'core' in manifests:
        try:
            version = tuple(int(part) for part in manifests['core']['version'].split('.'))
            valid = version >= (0, 4, 2)
        except (KeyError, ValueError, AttributeError, TypeError):
            valid = False
        report.check(valid, 'Core meets the components\' minimum version.',
                     'Core 0.4.2 or later is required by the selected components.')

    alias = suite / 'components/velunori.core'
    report.check(not (alias.exists() or alias.is_symlink()) or same_link(alias, suite / 'components/core'),
                 'Shared import alias is available or already correct.',
                 f'Conflicting development alias: {alias}')
    report.check(same_link(alias, suite / 'components/core') or writable_directory(alias.parent),
                 'Shared import alias is ready or its directory allows creation.',
                 'Component directory is not writable; the core installer needs to create its import alias.')

    if cloud:
        report.check((suite / 'components/clock/scripts/setup-deps.sh').is_file(),
                     'Calendar dependency installer is present.', 'Missing calendar dependency installer.')
        requirements = suite / 'components/clock/requirements.txt'
        report.check(requirements.is_file() and os.access(requirements, os.R_OK),
                     'Calendar dependency requirements are readable.', 'Calendar requirements.txt is missing or unreadable.')
        report.check(all(importlib.util.find_spec(module) is not None for module in ('venv', 'ensurepip')),
                     'Python venv and ensurepip modules are available.',
                     'Python venv/ensurepip is unavailable. Install the prerequisites or use --without-cloud.')
        report.check(writable_directory(suite / 'components/clock/.venv'),
                     'Calendar environment path can be created or updated.',
                     'Calendar .venv path is blocked or unwritable; dependency setup needs a private environment.')

    shell_file = config / 'shell.json'
    try:
        shell_config = json.loads(shell_file.read_text())
        valid_config = isinstance(shell_config, dict)
    except (OSError, ValueError):
        valid_config = False
    report.check(valid_config, 'Omarchy shell.json is readable and valid.',
                 'Missing, unreadable or invalid Omarchy shell.json.')
    report.check(shell_file.is_file() and os.access(shell_file, os.W_OK) and writable_directory(config),
                 'Shell configuration can be backed up and updated.',
                 'Omarchy shell.json and its directory must be writable for installation and backups.')
    report.check(writable_directory(config / 'plugins'), 'Plugin directory can accept installation links.',
                 'Omarchy plugin directory or its parent is not writable.')
    runtime = os.environ.get('XDG_RUNTIME_DIR', '')
    runtime_ready = report.check(bool(runtime) and Path(runtime).is_dir() and os.access(runtime, os.W_OK | os.X_OK),
                                 'Desktop runtime directory is available.',
                                 'Run inside your Omarchy desktop session (XDG_RUNTIME_DIR is required and must be usable).')
    for plugin in plugins:
        destination = config / f'plugins/velunori.{plugin}'
        report.check(not (destination.exists() or destination.is_symlink()) or same_link(destination, suite / 'components' / plugin),
                     f'Plugin path available or linked to this checkout: {plugin}',
                     f'Another installation exists at {destination}. Keep using its checkout or deliberately migrate it.')

    shell_ready = False
    if available['omarchy-shell'] and runtime_ready:
        shell_ready = report.check(query('omarchy-shell', 'shell', 'ping') == 'ok',
                                   'Omarchy shell responds.', 'Omarchy shell is not responding; no installation changes were made.')
    if shell_ready:
        try:
            discovered = json.loads(query('omarchy-shell', 'shell', 'listPlugins') or '')
            valid_plugins = isinstance(discovered, list) and all(
                isinstance(item, dict) and isinstance(item.get('id'), str)
                and (item.get('clonedFrom') is None or isinstance(item['clonedFrom'], str))
                for item in discovered)
        except ValueError:
            discovered, valid_plugins = [], False
        if report.check(valid_plugins, 'Shell plugin inventory is readable.',
                        'Could not read the shell plugin inventory; replacement conflicts cannot be checked.'):
            replacements = {manifest['omarchy']['clonedFrom']: manifest['id'] for manifest in manifests.values()
                            if isinstance(manifest.get('omarchy'), dict) and isinstance(manifest['omarchy'].get('clonedFrom'), str)}
            conflicts = [item.get('id', '(unknown)') for item in discovered
                         if item.get('enabled') and item.get('clonedFrom') in replacements
                         and item.get('id') != replacements[item['clonedFrom']]]
            report.check(not conflicts, 'No conflicting replacement plugins are active.',
                         'Other replacement plugins are active: ' + ', '.join(map(str, conflicts)))

    if lockscreen:
        try:
            source = suite / 'components/lockscreen/Service.qml'
            installed = omarchy / 'shell/plugins/lock/Service.qml'
            matching = source.read_bytes() == installed.read_bytes()
        except OSError:
            matching = False
        report.check(matching, 'Lock service matches the installed Omarchy service.',
                     'Lock service differs or is missing. Check the lockscreen README or use --without-lockscreen.')
        report.check(PAM_CONFIG.is_file() and os.access(PAM_CONFIG, os.R_OK),
                     'Omarchy lock PAM configuration is readable.', 'Omarchy lock PAM configuration is missing or unreadable.')
        if shell_ready:
            report.check(query('omarchy-shell', 'lock', 'isLocked') == 'false',
                         'Desktop session is unlocked.', 'Could not confirm an unlocked session. Run from an unlocked desktop.')
    if theme:
        wallpaper = suite / 'components/theme/backgrounds/velunori-dusk.png'
        report.check(wallpaper.is_file() and wallpaper.stat().st_size > 0,
                     'Dusk wallpaper is present.', 'Dusk wallpaper is missing from the theme checkout.')
        if available['omarchy']:
            current = query('omarchy', 'theme', 'current')
            report.check(bool(current) and current != 'Unknown', 'Current theme can be identified for recovery.',
                         'Could not identify the current theme for recovery.')

    if report.failures:
        print(f'Preflight failed: {report.failures} prerequisite(s) need attention. No changes were made.', file=sys.stderr)
        return 1
    print('Preflight passed. No changes were made. Live UI behavior, network access and account authentication were not verified.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', type=Path)
    for option in ('theme', 'lockscreen', 'cloud'):
        parser.add_argument(f'--without-{option}', action='store_true')
    args = parser.parse_args()
    return check_prerequisites(args.suite, theme=not args.without_theme,
                               lockscreen=not args.without_lockscreen, cloud=not args.without_cloud)


if __name__ == '__main__':
    sys.exit(main())
