import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('release', Path(__file__).resolve().parents[1] / 'scripts/package-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def init(self, root):
        root.mkdir(parents=True)
        self.git(root, 'init', '-q')
        self.git(root, 'config', 'user.email', 'fixture@example.invalid')
        self.git(root, 'config', 'user.name', 'Release test')

    def test_complete_pinned_reproducible_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / 'bundle'
            component = repo / 'components/core'
            self.init(repo)
            self.init(component)
            (component / 'source.qml').write_text('pinned source\n')
            (component / 'link.qml').symlink_to('source.qml')
            self.git(component, 'add', '.')
            self.git(component, 'commit', '-qm', 'component')
            pin = self.git(component, 'rev-parse', 'HEAD')
            (repo / 'VERSION').write_text('0.1.0-rc.1\n')
            self.git(repo, 'add', '.')
            self.git(repo, 'commit', '-qm', 'bundle')
            self.git(repo, 'tag', 'v0.1.0-rc.1')
            # A different component HEAD and dirty/untracked files must never leak.
            (component / 'source.qml').write_text('new source\n')
            self.git(component, 'commit', '-qam', 'later component')
            (component / 'source.qml').write_text('dirty source\n')
            (repo / 'private-token').write_text('not for release')
            first = release.package(repo, 'v0.1.0-rc.1', base / 'first')
            second = release.package(repo, 'v0.1.0-rc.1', base / 'second')
            self.assertEqual([p.read_bytes() for p in first], [p.read_bytes() for p in second])
            manifest = json.loads(first[1].read_text())
            self.assertEqual(manifest['components'], {'components/core': pin})
            with tarfile.open(first[0]) as archive:
                prefix = 'velunori-0.1.0-rc.1/'
                self.assertEqual(archive.extractfile(prefix + 'components/core/source.qml').read(), b'pinned source\n')
                self.assertTrue(archive.getmember(prefix + 'components/core/link.qml').issym())
                self.assertFalse(any('private-token' in name or '.git/' in name for name in archive.getnames()))
            for line in first[2].read_text().splitlines():
                digest, name = line.split('  ')
                self.assertEqual(digest, hashlib.sha256((first[2].parent / name).read_bytes()).hexdigest())
            self.git(repo, 'tag', 'v9.0.0')
            with self.assertRaisesRegex(ValueError, 'Release ref must'):
                release.package(repo, 'v9.0.0', base / 'wrong')


if __name__ == '__main__':
    unittest.main()
