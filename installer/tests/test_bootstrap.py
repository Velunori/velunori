import hashlib
import importlib.util
import json
import os
import pty
import select
import time
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'build.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

SHELL_SHIM='''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
if args==['shell','ping']:print('ok')
elif args==['lock','isLocked']:print('false')
elif args==['shell','rescanPlugins']:print('ok')
elif args==['shell','listPlugins']:
 root=Path(os.environ['XDG_CONFIG_HOME'])/'omarchy'
 config=json.loads((root/'shell.json').read_text())
 def ids(value):
  if isinstance(value,str):return [value]
  if isinstance(value,list):return sum((ids(v) for v in value),[])
  if isinstance(value,dict):return sum((ids(v) for v in value.values()),[])
  return []
 active=ids(config);rows=[]
 for path in (root/'plugins').glob('*/manifest.json'):
  if path.parent.name.startswith('.'):continue
  data=json.loads(path.read_text());rows.append(dict(id=data['id'],enabled=data['id'] in active,clonedFrom=data.get('omarchy',{}).get('clonedFrom','')))
 print(json.dumps(rows))
else:raise SystemExit(99)
'''
OMARCHY_SHIM='''#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
args=sys.argv[1:]
with open(Path(os.environ['HOME'])/'commands.log','a') as log:log.write(' '.join(args)+'\\n')
if args[:2]==['plugin','validate']:
 raise SystemExit(subprocess.run(['/usr/share/omarchy/bin/omarchy-plugin-validate',args[2]]).returncode)
if args==['restart','shell']:raise SystemExit(0)
raise SystemExit(99)
'''


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='velunori bootstrap ')
        cls.script=Path(cls.temp.name)/'installer with spaces.sh'
        builder.build(cls.script)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def environment(self,home):
        config=home/'config/omarchy';config.mkdir(parents=True)
        (config/'shell.json').write_text(json.dumps({'version':1,'bar':{'id':'omarchy.bar','layout':{'left':['custom.mail'],'center':['omarchy.clock'],'right':['omarchy.audio']}},'plugins':[]}))
        binary=home/'bin';binary.mkdir()
        for name,text in [('omarchy-shell',SHELL_SHIM),('omarchy',OMARCHY_SHIM),*[(name,'#!/bin/sh\nexit 99\n') for name in ['quickshell','pactl','ip','hyprctl']]]:
            path=binary/name;path.write_text(text);path.chmod(0o755)
        return {**os.environ,'HOME':str(home),'XDG_CONFIG_HOME':str(home/'config'),'XDG_DATA_HOME':str(home/'data'),'PATH':str(binary)+os.pathsep+os.environ['PATH']}

    def test_built_script_is_repeatable_and_has_matching_checksum(self):
        repeated=Path(self.temp.name)/'repeat.sh';builder.build(repeated)
        self.assertEqual(repeated.read_bytes(),self.script.read_bytes())
        digest=self.script.with_suffix('.sh.sha256').read_text().split()[0]
        self.assertEqual(digest,hashlib.sha256(self.script.read_bytes()).hexdigest())
        self.assertEqual(subprocess.run(['bash','-n',str(self.script)]).returncode,0)

    def test_plan_and_help_work_without_omarchy_or_desktop_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);env={**os.environ,'HOME':str(home),'XDG_CONFIG_HOME':str(home/'config'),'XDG_DATA_HOME':str(home/'data')}
            result=subprocess.run(['bash',str(self.script),'plan','--components','control-center'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('current bar stays in place',result.stdout)
            self.assertEqual(list(home.iterdir()),[])
            result=subprocess.run(['bash',str(self.script),'--help'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_real_payload_installs_copies_using_standin_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);env=self.environment(home)
            result=subprocess.run(['bash',str(self.script),'install','--components','clock,control-center'],input='yes\n',env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            plugins=home/'config/omarchy/plugins'
            self.assertTrue((plugins/'lib/kit/Theme.qml').is_file())
            self.assertTrue((plugins/'velunori.control-center/Widget.qml').is_file())
            self.assertTrue((plugins/'velunori.clock/Widget.qml').is_file())
            self.assertFalse((plugins/'velunori.bar').exists())
            self.assertFalse(any(p.is_symlink() for p in home.rglob('*')))
            config=json.loads((home/'config/omarchy/shell.json').read_text())
            self.assertEqual(config['bar']['id'],'omarchy.bar')
            self.assertIn('custom.mail',config['bar']['layout']['left'])
            receipt=json.loads((home/'data/velunori/installation/installation.json').read_text())
            self.assertEqual(receipt['components'],['clock','control-center'])
            self.assertEqual(receipt['phase'],'installed')
            self.assertNotIn('update ',(home/'commands.log').read_text())
            retained=home/'data/velunori/installation/installer.sh'
            status=subprocess.run(['bash',str(retained),'status'],env=env,capture_output=True,text=True)
            self.assertEqual(status.returncode,0,status.stderr)
            self.assertIn('installed',status.stdout)

    def test_piped_script_without_flags_asks_for_selection_on_tty(self):
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);env=self.environment(home)
            pid,fd=pty.fork()
            if pid==0:
                os.execvpe('bash',['bash','-c','cat "$1" | bash -s --','_',str(self.script)],env)
            output=b'';sent=set();status=None
            try:
                deadline=time.monotonic()+30
                answers=[(b'Choose 1 or 2',b'2\n'),(b'comma-separated',b'control-center\n'),(b'[y/N]',b'y\n')]
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.1)[0]:
                        try:data=os.read(fd,65536)
                        except OSError:data=b''
                        output+=data
                        for prompt,answer in answers:
                            if prompt in output and prompt not in sent:
                                os.write(fd,answer);sent.add(prompt)
                    done,code=os.waitpid(pid,os.WNOHANG)
                    if done:status=os.waitstatus_to_exitcode(code);break
                self.assertEqual(status,0,output.decode(errors='replace'))
                self.assertEqual(len(sent),3)
                receipt=json.loads((home/'data/velunori/installation/installation.json').read_text())
                self.assertEqual(receipt['components'],['control-center'])
                self.assertFalse((home/'config/omarchy/plugins/velunori.bar').exists())
            finally:
                if status is None:
                    os.kill(pid,9);os.waitpid(pid,0)
                os.close(fd)

    def test_piped_plan_accepts_arguments_without_a_terminal(self):
        result=subprocess.run(['bash','-s','--','plan','--all'],input=self.script.read_text(),capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('applied immediately',result.stdout)

    def test_corrupted_payload_is_rejected(self):
        bad=Path(self.temp.name)/'corrupt.sh';data=self.script.read_bytes();index=data.index(b"<<'__VELUNORI_DATA__'\n")+len(b"<<'__VELUNORI_DATA__'\n")
        changed=bytearray(data);changed[index]=ord('A') if data[index]!=ord('A') else ord('B');bad.write_bytes(changed)
        result=subprocess.run(['bash',str(bad),'plan','--all'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('checksum mismatch',result.stderr+result.stdout)


if __name__=='__main__':unittest.main()
