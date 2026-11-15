"""Run only stand-in installers and commands, with isolated configuration."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="velunori-bundle-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.suite = self.root / "suite with spaces"
        (self.suite / "scripts").mkdir(parents=True)
        shutil.copy(Path(__file__).resolve().parents[1] / "scripts/install.sh",
                    self.suite / "scripts/install.sh")
        for component in ("core", "clock", "control-center", "notifications", "menu",
                          "weather", "update", "lockscreen", "theme"):
            folder = self.suite / "components" / component / "scripts"
            folder.mkdir(parents=True)
            (folder / "install-local.sh").write_text(
                '#!/bin/bash\nset -eu\n'
                f'echo {component} >> "$TEST_LOG"\n'
                f'[[ ${{TEST_FAIL:-}} != {component} ]]\n')
        (self.suite / "components/clock/scripts/setup-deps.sh").write_text(
            '#!/bin/bash\necho dependencies >> "$TEST_LOG"\n')
        self.config = self.root / "config/omarchy"
        self.config.mkdir(parents=True)
        (self.config / "shell.json").write_text('{"bar":{"id":"omarchy.bar"}}\n')
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for executable in ("omarchy", "omarchy-shell", "pactl", "ip", "hyprctl",
                           "systemd-run", "checkupdates", "omarchy-update"):
            path = self.bin / executable
            path.write_text('#!/bin/bash\n'
                            'if [[ "$1 ${2:-}" == "shell ping" ]]; then echo ok; '
                            'else echo "command: $(basename "$0") $*" >> "$TEST_LOG"; fi\n')
            path.chmod(0o755)
        self.log = self.root / "log"
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_RUNTIME_DIR=str(self.root), TEST_LOG=str(self.log),
                        PATH=f"{self.bin}:{os.environ['PATH']}")

    def run_install(self, *args):
        return subprocess.run(["bash", str(self.suite / "scripts/install.sh"), *args],
                              env=self.env, text=True, capture_output=True)

    def lines(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

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


if __name__ == "__main__":
    unittest.main()
