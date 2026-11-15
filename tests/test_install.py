"""Run only stand-in installers and commands, with isolated configuration."""
import os
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('bundle_preflight', Path(__file__).resolve().parents[1] / 'scripts/preflight.py')
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="velunori-bundle-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.suite = self.root / "suite with spaces"
        (self.suite / "scripts").mkdir(parents=True)
        shutil.copy(Path(__file__).resolve().parents[1] / "scripts/install.sh",
                    self.suite / "scripts/install.sh")
        shutil.copy(Path(__file__).resolve().parents[1] / 'scripts/preflight.py',
                    self.suite / 'scripts/preflight.py')
        for component in ("core", "clock", "control-center", "notifications", "menu",
                          "weather", "update", "lockscreen", "theme"):
            folder = self.suite / "components" / component / "scripts"
            folder.mkdir(parents=True)
            (folder / "install-local.sh").write_text(
                '#!/bin/bash\nset -eu\n'
                f'echo {component} >> "$TEST_LOG"\n'
                f'[[ ${{TEST_FAIL:-}} != {component} ]]\n')
            if component != 'theme':
                manifest = {'id': f'velunori.{component}', 'version': '0.4.4'}
                clones = {'menu': 'omarchy.menu', 'notifications': 'omarchy.notifications', 'lockscreen': 'omarchy.lock'}
                if component in clones:
                    manifest['omarchy'] = {'clonedFrom': clones[component]}
                (folder.parent / 'manifest.json').write_text(json.dumps(manifest))
        backgrounds = self.suite / 'components/theme/backgrounds'
        backgrounds.mkdir()
        (backgrounds / 'velunori-dusk.png').write_bytes(b'wallpaper fixture')
        self.omarchy = self.root / 'omarchy'
        service = self.omarchy / 'shell/plugins/lock/Service.qml'
        service.parent.mkdir(parents=True)
        service.write_text('fixture lock service\n')
        (self.suite / 'components/lockscreen/Service.qml').write_bytes(service.read_bytes())
        self.pam = self.root / 'pam-fixture'
        self.pam.write_text('fixture PAM configuration\n')
        (self.suite / "components/clock/scripts/setup-deps.sh").write_text(
            '#!/bin/bash\necho dependencies >> "$TEST_LOG"\n')
        (self.suite / 'components/clock/requirements.txt').write_text('fixture-package\n')
        self.config = self.root / "config/omarchy"
        self.config.mkdir(parents=True)
        (self.config / "shell.json").write_text('{"bar":{"id":"omarchy.bar"}}\n')
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for executable in ("omarchy", "omarchy-shell", "pactl", "ip", "hyprctl",
                           "systemd-run", "checkupdates", "omarchy-update", "git", "quickshell"):
            path = self.bin / executable
            path.write_text('#!/bin/bash\n'
                            'case "$1 ${2:-}" in\n'
                            '  "shell ping") printf "%s\\n" "${TEST_SHELL_PING:-ok}" ;;\n'
                            '  "shell listPlugins") printf "%s\\n" "${TEST_PLUGINS:-[]}" ;;\n'
                            '  "lock isLocked") printf "%s\\n" "${TEST_IS_LOCKED:-false}" ;;\n'
                            '  "theme current") printf "%s\\n" "${TEST_THEME:-tokyo-night}" ;;\n'
                            '  *) echo "command: $(basename "$0") $*" >> "$TEST_LOG" ;;\n'
                            'esac\n')
            path.chmod(0o755)
        self.log = self.root / "log"
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_RUNTIME_DIR=str(self.root), TEST_LOG=str(self.log),
                        OMARCHY_PATH=str(self.omarchy),
                        PATH=f"{self.bin}:{os.environ['PATH']}")

    def run_install(self, *args):
        return subprocess.run(["bash", str(self.suite / "scripts/install.sh"), *args],
                              env=self.env, text=True, capture_output=True)

    def lines(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def preflight(self, **options):
        output, error = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(PREFLIGHT, 'PAM_CONFIG', self.pam), contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = PREFLIGHT.check_prerequisites(self.suite, **options)
        return code, output.getvalue(), error.getvalue()

    def assert_unchanged(self):
        self.assertFalse(self.log.exists(), 'An installer or modifying command ran')
        self.assertEqual(list(self.config.glob('*.before-*')), [])
        self.assertEqual((self.config / 'shell.json').read_text(), '{"bar":{"id":"omarchy.bar"}}\n')
        self.assertFalse((self.suite / 'components/clock/.venv').exists())
        self.assertFalse((self.suite / 'components/velunori.core').exists())
        self.assertFalse((self.suite / 'scripts/__pycache__').exists())

    def test_full_dry_run_has_no_side_effects(self):
        result = self.run_install("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("lockscreen/scripts/install-local.sh", result.stdout)
        self.assertIn("theme/scripts/install-local.sh", result.stdout)
        self.assertIn("clock/scripts/setup-deps.sh", result.stdout)
        self.assertFalse(self.log.exists())
        self.assertEqual(list(self.config.glob("*.before-*")), [])

    def test_order_backup_and_restart_with_standins(self):
        result = self.run_install("--without-lockscreen")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lines(), ["dependencies", "core", "clock",
                         "command: omarchy restart shell", "control-center",
                         "notifications", "menu", "weather", "update", "theme"])
        backup, = self.config.glob("shell.json.before-velunori-suite.*")
        self.assertEqual(backup.read_bytes(), (self.config / "shell.json").read_bytes())

    def test_options_skip_components(self):
        result = self.run_install("--without-lockscreen", "--without-theme", "--without-cloud")
        self.assertEqual(result.returncode, 0, result.stderr)
        for item in ("dependencies", "theme", "lockscreen"):
            self.assertNotIn(item, self.lines())

    def test_failure_stops_later_components(self):
        self.env["TEST_FAIL"] = "menu"
        result = self.run_install("--without-lockscreen")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Previously completed components remain", result.stderr)
        self.assertIn("menu", self.lines())
        self.assertNotIn("weather", self.lines())
        self.assertNotIn("theme", self.lines())

    def test_conflicting_installation_stops_before_dependencies(self):
        destination = self.config / "plugins/velunori.weather"
        destination.mkdir(parents=True)
        result = self.run_install("--without-lockscreen")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another installation exists", result.stderr)
        self.assertFalse(self.log.exists())
        self.assertEqual(list(self.config.glob("*.before-*")), [])

    def test_missing_submodule_stops_before_execution(self):
        (self.suite / "components/menu/scripts/install-local.sh").unlink()
        result = self.run_install("--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("git submodule update --init --recursive", result.stderr)
        self.assertFalse(self.log.exists())

    def test_unknown_option_is_rejected(self):
        result = self.run_install("--everything")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_check_is_read_only_and_successful(self):
        result = self.run_install('--check', '--without-lockscreen')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Preflight passed', result.stdout)
        self.assertNotIn('Install plan', result.stdout)
        self.assert_unchanged()

    def test_full_preflight_uses_only_fixture_lock_service_and_pam(self):
        code, output, error = self.preflight()
        self.assertEqual(code, 0, error)
        self.assertIn('Lock service matches', output)
        self.assert_unchanged()

    def test_all_optional_prerequisites_are_skipped_when_disabled(self):
        (self.suite / 'components/theme/backgrounds/velunori-dusk.png').unlink()
        (self.suite / 'components/lockscreen/Service.qml').unlink()
        (self.suite / 'components/clock/scripts/setup-deps.sh').unlink()
        self.env['TEST_THEME'] = 'Unknown'
        self.env['TEST_IS_LOCKED'] = 'true'
        result = self.run_install('--check', '--without-theme', '--without-lockscreen', '--without-cloud')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_unchanged()

    def test_multiple_failures_are_reported_together(self):
        self.env['TEST_SHELL_PING'] = 'offline'
        (self.suite / 'components/menu/scripts/install-local.sh').unlink()
        (self.config / 'plugins/velunori.weather').mkdir(parents=True)
        result = self.run_install('--check', '--without-lockscreen')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Missing menu installer', result.stderr)
        self.assertIn('Another installation exists', result.stderr)
        self.assertIn('Omarchy shell is not responding', result.stderr)
        self.assert_unchanged()

    def test_active_replacement_is_detected_before_installation(self):
        self.env['TEST_PLUGINS'] = json.dumps([{'id': 'other.menu', 'enabled': True, 'clonedFrom': 'omarchy.menu'}])
        result = self.run_install('--without-lockscreen')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Other replacement plugins are active: other.menu', result.stderr)
        self.assert_unchanged()

    def test_existing_links_to_this_checkout_are_allowed(self):
        folder = self.config / 'plugins'
        folder.mkdir()
        (folder / 'velunori.core').symlink_to(self.suite / 'components/core')
        result = self.run_install('--check', '--without-lockscreen')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_unchanged()

    def test_missing_command_and_venv_support_are_actionable(self):
        which, find_spec = PREFLIGHT.shutil.which, PREFLIGHT.importlib.util.find_spec
        with mock.patch.object(PREFLIGHT.shutil, 'which', side_effect=lambda name: None if name == 'pactl' else which(name)), mock.patch.object(PREFLIGHT.importlib.util, 'find_spec', side_effect=lambda name: None if name == 'ensurepip' else find_spec(name)):
            code, _, error = self.preflight(lockscreen=False)
        self.assertEqual(code, 1)
        self.assertIn('Missing required command: pactl', error)
        self.assertIn('venv/ensurepip is unavailable', error)
        self.assert_unchanged()

    def test_service_mismatch_and_locked_session_are_detected(self):
        (self.suite / 'components/lockscreen/Service.qml').write_text('different service\n')
        self.env['TEST_IS_LOCKED'] = 'true'
        code, _, error = self.preflight()
        self.assertEqual(code, 1)
        self.assertIn('Lock service differs', error)
        self.assertIn('unlocked session', error)
        self.assert_unchanged()

    def test_invalid_config_and_core_version_are_reported(self):
        (self.config / 'shell.json').write_text('invalid JSON')
        (self.suite / 'components/core/manifest.json').write_text('{"id":"velunori.core","version":"0.1.0"}')
        result = self.run_install('--check', '--without-lockscreen')
        self.assertEqual(result.returncode, 1)
        self.assertIn('invalid Omarchy shell.json', result.stderr)
        self.assertIn('Core 0.4.2 or later', result.stderr)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.config / 'shell.json').read_text(), 'invalid JSON')
        self.assertEqual(list(self.config.glob('*.before-*')), [])

    def test_ipc_timeout_is_reported_without_changes(self):
        with mock.patch.object(PREFLIGHT.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture', 4)):
            code, _, error = self.preflight(lockscreen=False, theme=False)
        self.assertEqual(code, 1)
        self.assertIn('shell is not responding', error)
        self.assert_unchanged()

    def test_invalid_plugin_inventory_is_reported(self):
        self.env['TEST_PLUGINS'] = '[{"id":"fixture","clonedFrom":{}}]'
        result = self.run_install('--check', '--without-lockscreen')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Could not read the shell plugin inventory', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assert_unchanged()

    def test_conflicting_import_alias_is_not_replaced(self):
        alias = self.suite / 'components/velunori.core'
        alias.symlink_to(self.root / 'unrelated-missing-path')
        result = self.run_install('--check', '--without-lockscreen')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Conflicting development alias', result.stderr)
        self.assertEqual(os.readlink(alias), str(self.root / 'unrelated-missing-path'))
        self.assert_unchanged()

    def test_missing_pam_is_reported_without_authentication(self):
        self.pam.unlink()
        code, _, error = self.preflight()
        self.assertEqual(code, 1)
        self.assertIn('PAM configuration is missing or unreadable', error)
        self.assert_unchanged()

    def test_root_and_unwritable_config_are_rejected_without_changes(self):
        access = PREFLIGHT.os.access
        with mock.patch.object(PREFLIGHT.os, 'geteuid', return_value=0), mock.patch.object(PREFLIGHT.os, 'access', side_effect=lambda path, mode: False if Path(path) == self.config / 'shell.json' and mode == os.W_OK else access(path, mode)):
            code, _, error = self.preflight(lockscreen=False)
        self.assertEqual(code, 1)
        self.assertIn('without sudo', error)
        self.assertIn('must be writable', error)
        self.assert_unchanged()

    def test_dry_run_still_skips_runtime_queries(self):
        self.env['TEST_SHELL_PING'] = 'offline'
        self.env['TEST_PLUGINS'] = 'not valid JSON'
        result = self.run_install('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Preflight', result.stdout)
        self.assert_unchanged()

    def test_check_and_dry_run_cannot_be_combined(self):
        result = self.run_install('--check', '--dry-run')
        self.assertEqual(result.returncode, 2)
        self.assertIn('separately', result.stderr)
        self.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
