import copy
import contextlib
import io
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('engine',ROOT/'engine.py');engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.temp=tempfile.TemporaryDirectory(prefix='velunori shell test ');self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.package=self.home/'package';self.package.mkdir()
        shutil.copy2(ROOT/'catalog.json',self.package/'catalog.json')
        for name in ['lib',*[x['name'] for x in json.loads((ROOT/'catalog.json').read_text())['components']]]:
            source=self.package/'components'/name;source.mkdir(parents=True)
            (source/'scripts').mkdir();(source/'scripts/install-local.sh').write_text('# fixture\n')
            if name=='lib':(source/'library.json').write_text(json.dumps({'id':'velunori.lib','apiVersion':1,'version':'1.0.0'}))
            elif name!='theme':
                (source/'manifest.json').write_text(json.dumps({'id':'velunori.'+name,'velunori':{'dependencies':{'velunori.lib':{'apiVersion':1}}}}))
            if name=='lockscreen':(source/'Service.qml').write_text('unchanged lock service')
        files={p.relative_to(self.package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.package.rglob('*') if p.is_file()}
        (self.package/'integrity.json').write_text(json.dumps({'build':'fixture-build','files':files}))
        self.env=patch.dict(os.environ,{'HOME':str(self.home),'XDG_CONFIG_HOME':str(self.home/'config'),'XDG_DATA_HOME':str(self.home/'data')})
        self.env.start();self.addCleanup(self.env.stop)
        self.installer=engine.Installer(self.package)
        self.installer.config_dir.mkdir(parents=True)
        self.original={'version':1,'bar':{'id':'omarchy.bar','layout':{'left':['custom.mail'],'center':[{'id':'omarchy.clock','timeFormat':'HH:mm'}],'right':['omarchy.audio','omarchy.weather']}},'plugins':[],'other':{'keep':True}}
        self.before=(json.dumps(self.original)+'\n').encode();self.installer.config.write_bytes(self.before)
        self.calls=[];self.selected=[];self.fail_restart=False;self.fail_cloud=False;self.external_change=False
        self.which=patch.object(engine.shutil,'which',return_value='/fixture/bin/tool');self.which.start();self.addCleanup(self.which.stop)
        self.uid=patch.object(engine.os,'geteuid',return_value=1000);self.uid.start();self.addCleanup(self.uid.stop)
        self.installer.run=self.run_command;self.installer.query=self.query

    def test_existing_component_data_does_not_block_installation(self):
        clock_data=self.home/'data/velunori/clock';clock_data.mkdir(parents=True)
        (clock_data/'calendar.sqlite3').write_text('keep')
        self.assertEqual(self.installer.prefix,self.home/'data/velunori/installation')
        self.assertTrue(self.installer.check(self.select(['clock'])))
        self.assertEqual((clock_data/'calendar.sqlite3').read_text(),'keep')

    def test_slow_rescan_reported_as_unresponsive_still_installs(self):
        # omarchy-shell reports "not responding" while the shell loads new plugins.
        self.slow_rescan=True
        self.installer.install(self.select(['clock']),confirm=lambda _:'INSTALL')
        self.assertEqual(json.loads(self.installer.receipt.read_text())['phase'],'installed')

    def run_command(self,*args,capture=False,timeout=60):
        self.calls.append(tuple(map(str,args)))
        code=0
        if tuple(map(str,args[:3]))==('omarchy','restart','shell') and self.fail_restart:
            self.fail_restart=False;code=1
        if str(args[-1]).endswith('setup-deps.sh') and self.fail_cloud:code=1
        if tuple(map(str,args[:3]))==('omarchy-shell','shell','rescanPlugins'):
            if self.external_change:self.installer.config.write_text('{"version":1,"userChanged":true}')
            if getattr(self,'slow_rescan',False):code=1
        return subprocess.CompletedProcess(args,code,stdout='')

    def query(self,*args):
        if args==('omarchy-shell','shell','ping'):return 'ok'
        if args==('omarchy-shell','lock','isLocked'):return 'false'
        if args==('omarchy','theme','current'):return 'tokyo-night'
        if args==('omarchy-shell','shell','listPlugins'):
            return json.dumps([{'id':p.name,'enabled':True} for p in self.installer.plugins.glob('velunori.*')])
        return None

    def select(self,names,cloud=False):
        self.selected=self.installer.select(names,cloud=cloud);return self.selected

    def install(self,names,cloud=False):
        return self.installer.install(self.select(names,cloud),cloud,confirm=lambda _:'INSTALL')

    def receipt(self):return json.loads(self.installer.receipt.read_text())

    def test_control_center_only_resolves_lib_without_bar(self):
        selected=self.select(['control-center'])
        self.assertTrue(self.installer.needs_library(selected))
        self.assertEqual([x['name'] for x in selected],['control-center'])
        self.assertEqual(self.install(['control-center']),0)
        result=json.loads(self.installer.config.read_text())
        self.assertEqual(result['bar']['id'],'omarchy.bar')
        self.assertTrue((self.installer.plugins/'lib').is_dir())
        self.assertFalse((self.installer.plugins/'velunori.bar').exists())
        self.assertFalse(any(p.is_symlink() for p in self.home.rglob('*')))
        self.assertEqual(result['other'],self.original['other'])

    def test_theme_only_does_not_require_library(self):
        self.assertFalse(self.installer.needs_library(self.select(['theme'])))

    def test_unknown_component_and_cloud_without_clock_are_rejected(self):
        for names in [['core'],['no-such-plugin'],[]]:
            with self.assertRaises(ValueError):self.select(names)
        with self.assertRaisesRegex(ValueError,'requires the clock'):self.select(['control-center'],cloud=True)

    def test_full_selection_contains_all_nine_components(self):
        self.assertEqual(len(self.installer.select(all_components=True)),9)

    def test_plan_and_check_do_not_write(self):
        selected=self.select(['control-center']);before=sorted(str(p) for p in self.home.rglob('*'))
        self.installer.plan(selected);self.assertTrue(self.installer.check(selected))
        self.assertEqual(before,sorted(str(p) for p in self.home.rglob('*')))
        self.assertEqual(self.calls,[])

    def test_install_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError,'cancelled'):
            self.installer.install(self.select(['clock']),confirm=lambda _:'no')
        self.assertFalse(self.installer.prefix.exists());self.assertEqual(self.installer.config.read_bytes(),self.before)

    def test_existing_plugin_and_data_directory_are_preserved(self):
        self.installer.plugins.mkdir();path=self.installer.plugins/'velunori.clock';path.mkdir();(path/'mine').write_text('keep')
        self.assertFalse(self.installer.check(self.select(['clock'])))
        self.assertEqual((path/'mine').read_text(),'keep')
        path.rename(self.installer.plugins/'unrelated')
        self.installer.prefix.mkdir(parents=True);(self.installer.prefix/'mine').write_text('keep')
        self.assertFalse(self.installer.check(self.select(['clock'])))

    def test_existing_symlink_is_not_replaced(self):
        self.installer.plugins.mkdir();target=self.installer.plugins/'velunori.clock';target.symlink_to(self.home/'missing')
        self.assertFalse(self.installer.check(self.select(['clock'])))
        self.assertTrue(target.is_symlink())

    def test_source_tampering_is_rejected_before_writes(self):
        (self.package/'components/clock/manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'integrity'):self.installer.check(self.select(['clock']))
        self.assertFalse(self.installer.prefix.exists())

    def test_root_and_locked_session_are_rejected(self):
        with patch.object(engine.os,'geteuid',return_value=0):self.assertFalse(self.installer.check(self.select(['clock'])))
        self.installer.query=lambda *args:'true' if args[-1]=='isLocked' else self.query(*args)
        self.assertFalse(self.installer.check(self.select(['clock'])))

    def test_receipt_backup_and_existing_library_reuse(self):
        library=self.installer.plugins/'lib';library.mkdir(parents=True)
        (library/'library.json').write_text(json.dumps({'id':'velunori.lib','apiVersion':1,'version':'1.0.0'}))
        (library/'mine').write_text('preserved')
        self.assertEqual(self.install(['clock']),0)
        self.assertNotIn('lib',self.receipt()['owned'])
        self.assertEqual((self.installer.prefix/'backups/shell.before.json').read_bytes(),self.before)
        self.assertEqual((library/'mine').read_text(),'preserved')
        self.assertEqual(self.installer.prefix.stat().st_mode & 0o777,0o700)

    def test_incompatible_library_is_not_overwritten(self):
        library=self.installer.plugins/'lib';library.mkdir(parents=True)
        (library/'library.json').write_text('{"id":"velunori.lib","apiVersion":2,"version":"2.0.0"}')
        self.assertFalse(self.installer.check(self.select(['clock'])))

    def test_failed_restart_restores_config_and_preserves_files_in_recovery(self):
        self.fail_restart=True
        with self.assertRaisesRegex(ValueError,'after the shell restart'):self.install(['clock'])
        self.assertEqual(self.installer.config.read_bytes(),self.before)
        self.assertFalse((self.installer.plugins/'velunori.clock').exists())
        self.assertTrue((self.installer.prefix/'recovery/velunori.clock').is_dir())
        self.assertEqual(self.receipt()['phase'],'failed-restored')

    def test_cloud_setup_failure_does_not_activate_plugins(self):
        self.fail_cloud=True
        with self.assertRaisesRegex(ValueError,'dependency setup failed'):self.install(['clock'],cloud=True)
        self.assertEqual(self.installer.config.read_bytes(),self.before)
        self.assertEqual(self.receipt()['phase'],'failed-restored')

    def test_external_config_change_is_preserved_with_recovery_record(self):
        self.external_change=True
        with self.assertRaisesRegex(ValueError,'changed during preparation'):self.install(['clock'])
        self.assertTrue(json.loads(self.installer.config.read_text())['userChanged'])
        self.assertTrue((self.installer.plugins/'velunori.clock').is_dir())
        self.assertEqual(self.receipt()['phase'],'needs-recovery')

    def test_replacement_conflict_and_bad_inventory_fail_closed(self):
        original=self.installer.query
        self.installer.query=lambda *args:json.dumps([{'id':'other.menu','enabled':True,'clonedFrom':'omarchy.menu'}]) if args[-1]=='listPlugins' else original(*args)
        self.assertFalse(self.installer.check(self.select(['menu'])))
        self.installer.query=lambda *args:'{}' if args[-1]=='listPlugins' else original(*args)
        self.assertFalse(self.installer.check(self.select(['clock'])))

    def test_lock_service_is_compared_without_authentication(self):
        host=self.home/'omarchy';service=host/'shell/plugins/lock/Service.qml';service.parent.mkdir(parents=True);service.write_text('unchanged lock service')
        self.installer.omarchy=host;self.installer.pam=self.home/'pam';self.installer.pam.write_text('fixture')
        self.assertTrue(self.installer.check(self.select(['lockscreen'])))
        service.write_text('different')
        self.assertFalse(self.installer.check(self.select(['lockscreen'])))
        self.assertEqual(self.calls,[])


class ConfigurationTests(unittest.TestCase):
    def setUp(self):self.catalog=json.loads((ROOT/'catalog.json').read_text())['components']
    def selected(self,*names):return [x for x in self.catalog if x['name'] in names]
    def test_clock_replacement_preserves_slot_and_options(self):
        before={'version':1,'bar':{'id':'omarchy.bar','layout':{'center':['custom.before',{'id':'omarchy.clock','showDate':False},'custom.after']}}}
        result=engine.configuration(before,self.selected('clock'))
        self.assertEqual(result['bar']['layout']['center'],['custom.before',{'id':'velunori.clock','showDate':False},'custom.after'])
        self.assertEqual(before['bar']['layout']['center'][1]['id'],'omarchy.clock')
    def test_bar_is_optional_and_selection_is_idempotent(self):
        before={'version':1,'bar':{'id':'custom.bar','layout':{'right':['omarchy.audio','custom.mail']}}}
        result=engine.configuration(before,self.selected('control-center','menu'))
        self.assertEqual(result['bar']['id'],'custom.bar')
        self.assertIn('custom.mail',result['bar']['layout']['right'])
        self.assertEqual(engine.configuration(result,self.selected('control-center','menu')),result)
        self.assertEqual(engine.configuration(before,self.selected('bar'))['bar']['id'],'velunori.bar')
    def test_lock_service_and_prior_disabled_source_are_preserved(self):
        before={'version':1,'bar':{'id':'omarchy.bar'},'disabledPlugins':['omarchy.lock']}
        result=engine.configuration(before,self.selected('lockscreen'))
        self.assertIn({'id':'velunori.lockscreen'},result['plugins'])
        self.assertTrue(all(isinstance(entry,dict) for entry in result['plugins']))
        self.assertNotIn('cloneSourceRestores',result)
    def test_theme_only_does_not_select_a_bar_or_widget(self):
        before={'version':1,'bar':{'id':'omarchy.bar','layout':{}},'plugins':[]}
        self.assertEqual(engine.configuration(before,self.selected('theme')),before)


if __name__=='__main__':unittest.main()
