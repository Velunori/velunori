import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_engine


class UpdateTests(unittest.TestCase):
    setUp = test_engine.InstallerTests.setUp
    run_command = test_engine.InstallerTests.run_command
    query = test_engine.InstallerTests.query
    select = test_engine.InstallerTests.select
    install = test_engine.InstallerTests.install
    receipt = test_engine.InstallerTests.receipt

    def seal(self):
        files={p.relative_to(self.package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.package.rglob('*') if p.is_file() and p.name!='integrity.json'}
        build=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
        (self.package/'integrity.json').write_text(json.dumps({'build':build,'files':files}))

    def prepare(self, cloud=False):
        for name in ('clock','control-center'):
            (self.package/'components'/name/'Widget.qml').write_text('old '+name)
        (self.package/'components/clock/requirements.txt').write_text('fixture requirements\n')
        self.seal()
        self.install(['clock','control-center'],cloud=cloud)
        self.clock=self.installer.plugins/'velunori.clock'
        self.environment=self.clock/'.venv';(self.environment/'bin').mkdir(parents=True)
        (self.environment/'bin/python').write_text('keep existing private environment')
        (self.clock/'google-oauth.json').write_text('{"fixture":"keep client"}')
        self.calendar_data=self.home/'data/velunori/clock';(self.calendar_data/'accounts').mkdir(parents=True)
        self.database=self.calendar_data/'calendar.sqlite3';self.database.write_bytes(b'fixture persistent calendar')
        self.credentials=self.calendar_data/'accounts/fixture.json';self.credentials.write_text('{"token":"fixture-only"}')
        self.original_receipt=self.receipt()
        self.installer.catalog['version']='9.9.9-test'
        (self.package/'catalog.json').write_text(json.dumps(self.installer.catalog))
        (self.package/'components/clock/Widget.qml').write_text('new clock')
        self.seal();self.calls=[]

    def update(self, **kwargs):
        return self.installer.update(self.select(['clock']),confirm=lambda _:'yes',**kwargs)

    def test_update_preserves_config_accounts_data_and_environment(self):
        self.prepare(cloud=True)
        config=self.installer.config.read_bytes()
        control=(self.installer.plugins/'velunori.control-center/Widget.qml').read_bytes()
        self.assertEqual(self.update(),0)
        self.assertEqual((self.clock/'Widget.qml').read_text(),'new clock')
        self.assertEqual(self.installer.config.read_bytes(),config)
        self.assertEqual((self.environment/'bin/python').read_text(),'keep existing private environment')
        self.assertEqual(self.database.read_bytes(),b'fixture persistent calendar')
        self.assertEqual(self.credentials.read_text(),'{"token":"fixture-only"}')
        self.assertEqual((self.clock/'google-oauth.json').read_text(),'{"fixture":"keep client"}')
        self.assertEqual((self.installer.plugins/'velunori.control-center/Widget.qml').read_bytes(),control)
        self.assertFalse(any(str(call[-1]).endswith('setup-deps.sh') for call in self.calls))
        receipt=self.receipt();self.assertTrue(receipt['cloud'])
        self.assertEqual(receipt['componentVersions']['clock']['version'],'9.9.9-test')
        self.assertEqual(receipt['componentVersions']['control-center']['version'],self.original_receipt['version'])
        backup=Path(receipt['updates'][-1]['backup'])
        self.assertEqual((backup/'velunori.clock/Widget.qml').read_text(),'old clock')
        self.assertEqual(json.loads((backup/'installation.before.json').read_text()),self.original_receipt)
        self.assertEqual(receipt['id'],self.original_receipt['id'])

    def test_dry_run_and_refused_confirmation_do_not_change_files(self):
        self.prepare()
        before={str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(self.installer.update(self.select(['clock']),dry_run=True,confirm=lambda _:self.fail('Unexpected prompt')),0)
        with self.assertRaisesRegex(ValueError,'cancelled'):
            self.installer.update(self.select(['clock']),confirm=lambda _:'')
        after={str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(after,before)
        self.assertFalse(self.calls)

    def test_unowned_installation_is_refused(self):
        self.prepare();(self.clock/'.velunori-owner.json').write_text('{"installation":"foreign"}')
        with self.assertRaisesRegex(ValueError,'prerequisite checks failed'):self.update()
        self.assertEqual((self.clock/'Widget.qml').read_text(),'old clock')

    def test_git_checkout_is_not_replaced(self):
        self.prepare();(self.clock/'.git').mkdir()
        with self.assertRaisesRegex(ValueError,'prerequisite checks failed'):self.update()
        self.assertEqual((self.clock/'Widget.qml').read_text(),'old clock')

    def test_source_symlink_is_not_replaced(self):
        self.prepare();moved=self.home/'linked-clock';self.clock.rename(moved);self.clock.symlink_to(moved,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'prerequisite checks failed'):self.update()
        self.assertTrue(self.clock.is_symlink())

    def test_failed_activation_restores_code_and_private_environment(self):
        self.prepare();self.fail_restart=True
        with self.assertRaisesRegex(ValueError,'previous plugin folders restored'):self.update()
        self.assertEqual((self.clock/'Widget.qml').read_text(),'old clock')
        self.assertTrue((self.environment/'bin/python').is_file())
        self.assertEqual(self.receipt()['version'],self.original_receipt['version'])
        self.assertEqual(self.receipt()['phase'],'installed')
        self.assertEqual(self.credentials.read_text(),'{"token":"fixture-only"}')
        backup=Path(self.receipt()['lastUpdateBackup'])
        self.assertEqual((backup/'failed/velunori.clock/Widget.qml').read_text(),'new clock')

    def test_dependency_failure_restores_original_environment(self):
        self.prepare(cloud=True);self.fail_cloud=True
        with self.assertRaisesRegex(ValueError,'dependency setup failed'):self.update(cloud=True)
        self.assertEqual((self.environment/'bin/python').read_text(),'keep existing private environment')
        self.assertEqual((self.clock/'Widget.qml').read_text(),'old clock')

    def test_changed_requirements_require_explicit_cloud_refresh(self):
        self.prepare(cloud=True)
        (self.package/'components/clock/requirements.txt').write_text('new requirements\n');self.seal()
        with self.assertRaisesRegex(ValueError,'prerequisite checks failed'):self.update()
        self.assertEqual((self.clock/'Widget.qml').read_text(),'old clock')

    def test_preserves_concurrent_shell_config_changes(self):
        self.prepare();self.external_change=True
        self.assertEqual(self.update(),0)
        self.assertTrue(json.loads(self.installer.config.read_text())['userChanged'])

    def test_no_receipt_and_uninstalled_components_are_refused(self):
        with self.assertRaisesRegex(ValueError,'No managed copied installation'):self.update()
        self.prepare()
        with self.assertRaisesRegex(ValueError,'installed plugin components only'):
            self.installer.update(self.select(['menu']),confirm=lambda _:'yes')
        with self.assertRaisesRegex(ValueError,'installed plugin components only'):
            self.installer.update(self.select(['theme']),confirm=lambda _:'yes')

    def test_recovery_state_blocks_further_updates(self):
        self.prepare();receipt=self.receipt();receipt['phase']='needs-recovery';self.installer.save(receipt)
        with self.assertRaisesRegex(ValueError,'needs recovery'):self.update()

    def test_retained_installer_changes_only_on_success(self):
        self.prepare();retained=self.installer.prefix/'installer.sh';retained.write_text('old installer')
        new=self.home/'new.sh';new.write_text('new installer')
        self.fail_restart=True
        with self.assertRaises(ValueError):self.update(bootstrap=new)
        self.assertEqual(retained.read_text(),'old installer')
        self.assertEqual(self.update(bootstrap=new),0)
        self.assertEqual(retained.read_text(),'new installer')

    def test_partial_folder_swap_failure_restores_every_original(self):
        self.prepare()
        rename=Path.rename
        def fail_stage(path,destination):
            if path.name=='velunori.clock' and path.parent.name.startswith('.velunori-update-'):
                raise OSError('fixture rename failure')
            return rename(path,destination)
        with patch.object(Path,'rename',fail_stage):
            with self.assertRaisesRegex(ValueError,'previous plugin folders restored'):self.update()
        self.assertEqual((self.clock/'Widget.qml').read_text(),'old clock')
        self.assertTrue((self.environment/'bin/python').exists())
        self.assertEqual(self.receipt()['phase'],'installed')

    def test_rollback_does_not_overwrite_a_changed_owner(self):
        self.prepare();run=self.installer.run
        def change_owner(*args,**kwargs):
            result=run(*args,**kwargs)
            if args[:3]==('omarchy','restart','shell'):
                (self.clock/'.velunori-owner.json').write_text('{"installation":"foreign"}')
                result.returncode=1
            return result
        self.installer.run=change_owner
        with self.assertRaisesRegex(ValueError,'review update backups'):self.update()
        self.assertEqual(json.loads((self.clock/'.velunori-owner.json').read_text())['installation'],'foreign')
        self.assertEqual(self.receipt()['phase'],'needs-recovery')
        backup=Path(self.receipt()['lastUpdateBackup'])
        self.assertEqual((backup/'velunori.clock/Widget.qml').read_text(),'old clock')

    def test_receipt_failure_also_restores_retained_installer(self):
        self.prepare();retained=self.installer.prefix/'installer.sh';retained.write_text('old installer')
        new=self.home/'new.sh';new.write_text('new installer')
        save=self.installer.save
        def fail_new_receipt(receipt):
            if receipt.get('phase')=='installed' and receipt['version']=='9.9.9-test':
                raise OSError('fixture receipt failure')
            return save(receipt)
        self.installer.save=fail_new_receipt
        with self.assertRaisesRegex(ValueError,'previous plugin folders restored'):self.update(bootstrap=new)
        self.assertEqual(retained.read_text(),'old installer')
