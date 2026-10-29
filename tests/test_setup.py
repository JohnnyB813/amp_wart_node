import copy,hashlib,importlib.util,json,os,shlex,struct,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def elf(label):
    data=bytearray(64);data[:7]=b'\x7fELF\x02\x01\x01';struct.pack_into('<HHI',data,16,2,62,1);struct.pack_into('<HH',data,52,64,56);return bytes(data)+label.encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def snapshot(path):return {p.relative_to(path).as_posix():('link:'+os.readlink(p) if p.is_symlink() else sha(p.read_bytes())) for p in path.rglob('*') if p.is_file() or p.is_symlink()}

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='AMP integration with spaces ');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.inst=module('installer',ROOT/'scripts/install-amp-updates.py')
        self.helper=Path(os.environ.get('AMP_UPDATER_TEST_BINARY',str(ROOT/'dist/amp-wart-update-linux-amd64')))
        self.assertTrue(self.helper.is_file(),'Build the standalone updater before the Python integration tests')
    def fixture(self,network):
        instance=self.base/network;root=instance/('warthog-mainnet' if network=='mainnet' else 'warthog-defi-testnet');root.mkdir(parents=True)
        old=elf('old '+network);digest=sha(old);version='0.8.20' if network=='mainnet' else '0.10.32'
        self.inst.KNOWN[network][digest]=(version,'1'*40)
        if network=='mainnet':
            directory=root/'releases'/digest;directory.mkdir(parents=True);(directory/'wart-node').write_bytes(old);(directory/'wart-node').chmod(0o755)
            (directory/'SHA256SUMS').write_text(digest+'  wart-node\n');(root/'current').symlink_to('releases/'+digest,target_is_directory=True)
            executable='current/wart-node';command='--chain-db="./data/chain.db3" --peers-db="./data/peers.db3"'
        else:
            (root/'wart-node-defi-beta-linux').write_bytes(old);(root/'wart-node-defi-beta-linux').chmod(0o755)
            executable='wart-node-defi-beta-linux';command='--testnet --session="./data"'
        command+=' --bind="{{$ApplicationIPBinding}}:{{$ApplicationPort1}}" --rpc="127.0.0.1:{{$ApplicationPort2}}" --publicrpc="{{PublicAPIIP}}:{{$ApplicationPort3}}" --stratum="{{StratumIP}}:{{$ApplicationPort4}}" {{DebugLogging}} --minfee=0.00009992'
        fields={'Meta.AppConfigId':self.inst.APP_IDS[network],'Meta.ConfigVersion':'1','App.RootDir':'./'+root.name+'/',
            'App.BaseDirectory':'./'+root.name+'/','App.WorkingDir':'.','App.ExecutableLinux':executable,'App.CommandLineArgs':command,
            'App.UpdateSources':'[{"old":"saved in backup"}]','App.PreStartStages':'[{"old":"saved in backup"}]',
            'App.Ports':'assigned ports unchanged','App.AppSettings':'{"PublicAPIIP":"127.0.0.1"}','Unrelated.Custom':'retain this exact value'}
        raw=b'\xef\xbb\xbf'+''.join('GenericModule.'+k+'='+v+'\r\n' for k,v in fields.items()).encode();(instance/'GenericModule.kvp').write_bytes(raw)
        (instance/'AMPConfig.conf').write_text('startup settings stay unchanged\n');(root/'data').mkdir()
        for name in ('chain.db3','chain.db3-wal','chain.db3-shm','peers.db3'):(root/'data'/name).write_bytes(b'KEEP DATABASE BYTES\x00\xff')
        policy=json.loads((ROOT/'channels/policy.json').read_text())[network];new=elf('new '+network)
        remote={'schema':1,'network':network,'platform':'linux-amd64','version':'0.8.20' if network=='mainnet' else '0.10.36',
            'source_commit':'2'*40,'chain_id':policy['chain_id'],'epoch':policy['epoch'],'sequence':2,
            'binary':{'url':'https://github.com/JohnnyB813/amp_wart_node/releases/download/example/node','sha256':sha(new),'size':len(new)}}
        def fetch(url,limit=64<<20):
            if url.endswith('/'+network+'.json'):return json.dumps(remote).encode()
            if url==remote['binary']['url']:return new
            raise AssertionError('Unexpected remote request '+url)
        return instance,root,raw,fields,remote,fetch
    def call(self,instance,network,**kwargs):
        return self.inst.install(instance,network,updater_path=self.helper,updater_sha=sha(self.helper.read_bytes()),**kwargs)
    def test_mainnet_preview_and_integration_preserve_data_and_flags(self):
        instance,root,raw,values,remote,fetch=self.fixture('mainnet');before=snapshot(instance);databases=snapshot(root/'data')
        with patch.object(self.inst,'fetch',fetch):
            result=self.call(instance,'mainnet',check=True);self.assertFalse(result['testnet_reset']);self.assertEqual(snapshot(instance),before)
            result=self.call(instance,'mainnet')
        self.assertEqual(snapshot(root/'data'),databases);self.assertEqual((instance/'AMPConfig.conf').read_text(),'startup settings stay unchanged\n')
        _,after=self.inst.fields((instance/'GenericModule.kvp').read_bytes())
        for key in ('App.CommandLineArgs','App.Ports','App.AppSettings','Unrelated.Custom'):self.assertEqual(after[key][2],values[key])
        self.assertEqual((Path(result['backup_directory'])/'GenericModule.kvp').read_bytes(),raw)
        self.assertTrue((instance/'GenericModule.kvp').read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n',(instance/'GenericModule.kvp').read_bytes())
        self.assertEqual(json.loads((root/'amp-update.json').read_text())['network'],'mainnet')
        stage=json.loads(after['App.PreStartStages'][2])[0]
        args=stage['UpdateSourceArgs'].replace('{{$FullBaseDir}}',str(root)+'/')
        verified=subprocess.run(['/bin/sh',*shlex.split(args)],capture_output=True,text=True)
        self.assertEqual(verified.returncode,0,verified.stderr)
    def test_matching_installed_binary_uses_published_sequence(self):
        instance,root,raw,values,remote,fetch=self.fixture('mainnet')
        old=(root/'current/wart-node').read_bytes()
        remote['binary']['sha256']=sha(old);remote['binary']['size']=len(old);remote['source_commit']='1'*40
        with patch.object(self.inst,'fetch',fetch):self.call(instance,'mainnet')
        metadata=json.loads((root/'current/amp-release.json').read_text())
        self.assertEqual(metadata['sequence'],remote['sequence'])
    def test_testnet_reset_is_explicit_and_keeps_every_old_file(self):
        instance,root,raw,values,remote,fetch=self.fixture('testnet');before=snapshot(instance);databases=snapshot(root/'data');old=(root/'wart-node-defi-beta-linux').read_bytes()
        with patch.object(self.inst,'fetch',fetch):
            with self.assertRaisesRegex(ValueError,'RESET REQUIRED'):self.call(instance,'testnet')
            self.assertEqual(snapshot(instance),before)
            self.call(instance,'testnet',check=True,accept_reset=remote['epoch']);self.assertEqual(snapshot(instance),before)
            result=self.call(instance,'testnet',accept_reset=remote['epoch'])
        self.assertTrue(result['testnet_reset']);self.assertEqual(snapshot(root/'data'),databases);self.assertEqual((root/'wart-node-defi-beta-linux').read_bytes(),old)
        _,after=self.inst.fields((instance/'GenericModule.kvp').read_bytes())
        self.assertEqual(after['App.ExecutableLinux'][2],'current/wart-node')
        self.assertEqual(after['App.CommandLineArgs'][2],values['App.CommandLineArgs'].replace('--session="./data"','--session="./data-testnet-2026-10-24"'))
        self.assertFalse((root/'data-testnet-2026-10-24').exists());self.assertFalse((root/'previous').exists())
    def test_wrong_app_and_mainnet_epoch_are_refused(self):
        instance,root,raw,values,remote,fetch=self.fixture('mainnet')
        (instance/'GenericModule.kvp').write_bytes(raw.replace(self.inst.APP_IDS['mainnet'].encode(),b'wrong-app'))
        with patch.object(self.inst,'fetch',fetch):
            with self.assertRaisesRegex(ValueError,'identity'):self.call(instance,'mainnet')
        (instance/'GenericModule.kvp').write_bytes(raw);remote['epoch']='unapproved';before=snapshot(instance)
        with patch.object(self.inst,'fetch',fetch):
            with self.assertRaisesRegex(ValueError,'RESET REQUIRED'):self.call(instance,'mainnet',accept_reset='unapproved')
        self.assertEqual(snapshot(instance),before)
    def test_failed_bootstrap_verification_restores_existing_selection(self):
        instance,root,raw,values,remote,fetch=self.fixture('mainnet');old_link=os.readlink(root/'current');databases=snapshot(root/'data')
        with patch.object(self.inst,'fetch',fetch),patch.object(self.inst.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'verify')):
            with self.assertRaises(subprocess.CalledProcessError):self.call(instance,'mainnet')
        self.assertEqual(os.readlink(root/'current'),old_link);self.assertEqual((instance/'GenericModule.kvp').read_bytes(),raw)
        self.assertEqual(snapshot(root/'data'),databases);self.assertFalse((root/'amp-wart-update').exists());self.assertFalse((root/'amp-update.json').exists())

class PublisherTests(unittest.TestCase):
    def setUp(self):self.pub=module('publisher',ROOT/'scripts/publish.py')
    def test_static_elf_and_dynamic_interpreter_refusal(self):
        self.pub.validate_elf(elf('valid'))
        bad=bytearray(elf(''));struct.pack_into('<Q',bad,32,64);struct.pack_into('<H',bad,56,1);bad+=struct.pack('<IIQQQQQQ',3,0,0,0,0,0,0,0)
        with self.assertRaisesRegex(ValueError,'interpreter'):self.pub.validate_elf(bytes(bad))
    def test_immutable_release_collision_never_overwrites_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);(path/'wart-node-mainnet-linux-amd64').write_bytes(elf('node'));(path/'manifest.json').write_text('{}');(path/'SHA256SUMS').write_text('hash')
            manifest={'network':'mainnet'}
            with patch.object(self.pub,'api',return_value={'assets':[]}),patch.object(self.pub,'gh') as gh:
                with self.assertRaisesRegex(ValueError,'will not be overwritten'):self.pub.publish('example',path,manifest)
                gh.assert_not_called()
    def test_channel_promotion_cannot_move_backwards(self):
        import base64
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            for name in ('wart-node-mainnet-linux-amd64','manifest.json','SHA256SUMS'):(path/name).write_bytes(b'asset '+name.encode())
            assets={'assets':[{'name':p.name,'digest':'sha256:'+sha(p.read_bytes())} for p in path.iterdir()]}
            old={'network':'mainnet','epoch':'mainnet-v1','sequence':3}
            channel={'content':base64.b64encode(json.dumps(old).encode()).decode(),'sha':'abc'}
            current={'network':'mainnet','epoch':'mainnet-v1','sequence':2}
            with patch.object(self.pub,'api',side_effect=[assets,channel]),patch.object(self.pub,'gh') as gh:
                with self.assertRaisesRegex(ValueError,'move backwards'):self.pub.publish('example',path,current)
                gh.assert_not_called()
    def test_new_genesis_requires_policy_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);(path/'channels').mkdir();(path/'channels/policy.json').write_bytes((ROOT/'channels/policy.json').read_bytes());node=path/'node';node.write_bytes(elf('new'))
            with patch.object(self.pub,'ROOT',path),patch.object(self.pub,'source_info',return_value=('0.8.20','0'*64)),patch.object(self.pub,'api',return_value={'commit':{'committer':{'date':'2026-10-29T00:00:00Z'}}}):
                with self.assertRaisesRegex(ValueError,'Genesis changed'):self.pub.prepare('mainnet',node,'1'*40)
            self.assertFalse((path/'dist').exists())
if __name__=='__main__':unittest.main()