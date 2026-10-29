#!/usr/bin/env python3
"""One-time connection of an existing, stopped AMP instance to its public update channel."""
import argparse,fcntl,hashlib,json,os,re,shlex,shutil,sqlite3,stat,struct,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
REPO='JohnnyB813/amp_wart_node'
UPDATER_TAG='updater-v0.1.0'
MAIN_SEED="The New York Times International Edition 29/06/2023: 'Water troubles: A preview'"
MAIN_ID=hashlib.sha256(MAIN_SEED.encode()).hexdigest()
RESET_ID=hashlib.sha256(b'DeFi Testnet restart 24/10/26').hexdigest()
APP_IDS={'mainnet':'066fd803-3641-4c26-b3df-5531650bcf17','testnet':'f0778ac4-a7fd-49a3-b89c-d9bc8bd68f50'}
KNOWN={
 'mainnet':{'45f3d8c4d799056f636afcff65485248245466348bc11ff335ee337a89f58db2':('0.8.20','6e9dbf602b5b889159c9f3910a0de40d159bd13d'),
            '55ca417110629fafd180f6a2d71ca16eb67a76df805e50c9d332da20bbba9fc1':('0.8.20','51d5d1d789dd03c876967f6a51676f940ae6690a')},
 'testnet':{'7adaad57112cce460038234d1aee173a4cf6515d9897e46d801e26cc4e457120':('0.10.32','75fd125771fb2a09be076907f68c5b4edbd4e692'),
            'e810ccd5a2ee095618b20d0e67f21c0fb704e06d1a3d9ed65ba3132db6064bef':('0.10.33','7b5a317aad5b104533a7eda944d4d7f5f2f7e1d0'),
            '71a53d4b0b623a255647ec5cc377edcc47f3afb321fb0e22cbe1689c500c2d5d':('0.10.34','b208583fbc17d936f347730792abdd54748658d8'),
            '0421a0c6900a84ba51df43a960ac91a5a73f674cf85d90bfeb6d9b0c4d2768d8':('0.10.35','9b8fca3183a81fc6dbeda97b594980ef4a734452'),
            '2ab6d501efbf81b6804669e2d867b891cb718e5a6d5f0a384319b2256e94cf03':('0.10.36','56b66986a0ea04808a924f81923e664c5009a39f')}}

def sha(data):return hashlib.sha256(data).hexdigest()
def plain(path,kind):
    if path.is_symlink() or not (path.is_file() if kind=='file' else path.is_dir()):raise ValueError('Expected a non-symlink '+kind+': '+str(path))
def fetch(url,limit=64<<20):
    allowed=(f'https://raw.githubusercontent.com/{REPO}/main/channels/',f'https://github.com/{REPO}/releases/download/')
    if not url.startswith(allowed):raise ValueError('Download URL is outside the AMP repository')
    with urlopen(Request(url,headers={'User-Agent':'amp-wart-bootstrap/0.1.0'}),timeout=180) as response:data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Download exceeds limit')
    return data

def elf(data):
    if len(data)<64 or data[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',data,18)[0]!=62:raise ValueError('Expected Linux x86-64 executable')

def manifest(value,network):
    required={'schema','network','platform','version','source_commit','chain_id','epoch','sequence','binary'}
    if set(value)!=required or value['schema']!=1 or value['network']!=network or value['platform']!='linux-amd64':raise ValueError('Wrong network/platform manifest')
    for key,size in (('source_commit',40),('chain_id',64)):
        if not re.fullmatch('[0-9a-f]{'+str(size)+'}',value[key]):raise ValueError('Invalid '+key)
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',value['epoch']):raise ValueError('Invalid network epoch')
    if not re.fullmatch('[0-9a-f]{64}',value['binary']['sha256']) or not 0<value['binary']['size']<=64<<20:raise ValueError('Invalid binary manifest')
    if not value['binary']['url'].startswith(f'https://github.com/{REPO}/releases/download/'):raise ValueError('Unexpected asset origin')
    return value

def fields(original):
    lines=original.decode('utf-8-sig').splitlines(keepends=True);values={}
    for i,line in enumerate(lines):
        key,sep,value=line.rstrip('\r\n').partition('=')
        if sep:
            normalized=key.removeprefix('GenericModule.')
            if normalized in values:raise ValueError('Duplicate key: '+normalized)
            values[normalized]=(i,key,value)
    return lines,values

def patch(original,changes):
    lines,values=fields(original)
    for key,value in changes.items():
        if key not in values:raise ValueError('Missing supported AMP key: '+key)
        i,literal,old=values[key]
        if old!=value:lines[i]=literal+'='+value+('\r\n' if lines[i].endswith('\r\n') else '\n')
    data=''.join(lines).encode()
    return (b'\xef\xbb\xbf'+data) if original.startswith(b'\xef\xbb\xbf') else data

def stage(network,action):
    script='exec "$1/amp-wart-update" '+action+' --root "$1" --network '+network
    args='-c "'+script.replace('"','\\"')+'" amp-wart-updater "{{$FullBaseDir}}"'
    return [{'UpdateStageName':('Download and select approved '+network+' release') if action=='update' else 'Verify selected '+network+' release (offline)',
        'UpdateSourcePlatform':2,'UpdateSource':8,'UpdateSourceArch':3,'UpdateSourceData':'/bin/sh','UpdateSourceArgs':args,
        'RunInBackground':False,'SkipOnFailure':False,'OverwriteExistingFiles':False}]

def stopped(instance,binary):
    if not Path('/proc').is_dir():raise ValueError('Run installation on the Linux AMP host')
    target,root=binary.stat(),instance.stat()
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid():continue
        try:
            exe=(process/'exe').stat();name=Path(os.readlink(process/'exe')).name
            cwd=(process/'cwd').stat() if name.startswith('AMP_') else None
        except OSError:continue
        if ((exe.st_dev,exe.st_ino)==(target.st_dev,target.st_ino) or (cwd and (cwd.st_dev,cwd.st_ino)==(root.st_dev,root.st_ino))):raise ValueError('Stop this node and its managed AMP instance for the one-time integration; leave ADS running')

def session(command):
    matches=[token.split('=',1)[1] for token in shlex.split(command) if token.startswith('--session=')]
    if len(matches)!=1:raise ValueError('Expected exactly one testnet session flag')
    if not re.fullmatch(r'\./data(?:-[a-z0-9-]+)?',matches[0]):raise ValueError('Unexpected testnet session directory')
    return matches[0]

def check_genesis(path,chain_id):
    if not path.exists() or not any(path.iterdir()):return
    plain(path,'directory');db=path/'chain.db3';plain(db,'file')
    wal=path/'chain.db3-wal'
    if wal.exists() and wal.stat().st_size:raise ValueError('Nonempty chain WAL: stop/checkpoint cleanly before retaining this session')
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as connection:
        row=connection.execute('SELECT b.header FROM Blocks b JOIN Consensus c ON b.ROWID=c.block_id WHERE c.height=1').fetchone()
    if not row or not isinstance(row[0],bytes) or len(row[0])!=80 or row[0][:32].hex()!=chain_id:raise ValueError('Existing session genesis is not the approved reset chain')

def atomic(path,data,mode):
    descriptor,name=tempfile.mkstemp(prefix='.amp-bootstrap-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as output:os.fchmod(output.fileno(),mode);output.write(data);output.flush();os.fsync(output.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)

def link(path,target):
    temporary=path.with_name('.amp-current-'+os.urandom(8).hex())
    try:temporary.symlink_to(target,target_is_directory=True);os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def install(instance,network,check=False,accept_reset=None,updater_path=None,updater_sha=None):
    if not instance.is_absolute() or instance.is_symlink():raise ValueError('Use the absolute non-symlink instance directory')
    instance=instance.resolve(strict=True);config=instance/'GenericModule.kvp';plain(config,'file')
    root=instance/('warthog-mainnet' if network=='mainnet' else 'warthog-defi-testnet');plain(root,'directory')
    original=config.read_bytes();_,values=fields(original);get=lambda k:values.get(k,(None,None,''))[2]
    if get('Meta.AppConfigId')!=APP_IDS[network]:raise ValueError('Wrong AMP application identity')
    for key in ('App.RootDir','App.BaseDirectory'):
        if get(key)!='./'+root.name+'/':raise ValueError('Unexpected '+key)
    if get('App.WorkingDir')!='.':raise ValueError('Unexpected working directory')
    command=get('App.CommandLineArgs');tokens=shlex.split(command)
    if any(t.startswith(('--config','--session')) for t in tokens) and network=='mainnet':raise ValueError('Unexpected mainnet config/session flags')
    if any(t.startswith('--testnet') for t in tokens)!=(network=='testnet'):raise ValueError('Wrong network launch flags')
    if network=='mainnet':
        for flag,path in (('--chain-db=','./data/chain.db3'),('--peers-db=','./data/peers.db3')):
            if [t[len(flag):] for t in tokens if t.startswith(flag)]!=[path]:raise ValueError('Unexpected database path')
    executable=get('App.ExecutableLinux')
    if executable not in (('current/wart-node',) if network=='mainnet' else ('wart-node-defi-beta-linux','current/wart-node')):raise ValueError('Unexpected executable path')
    binary=root/executable
    if executable=='current/wart-node':
        current=root/'current'
        resolved=current.resolve(strict=True)
        if current.is_symlink() and resolved.parent!=root/'releases':raise ValueError('Current link leaves the application releases directory')
        plain(resolved,'directory');plain(binary.resolve(),'file')
    else:plain(binary,'file')
    old_data=binary.read_bytes();old_sha=sha(old_data);elf(old_data)
    prior_binding=None;old_manifest=None
    if (root/'amp-update.json').exists():
        plain(root/'amp-update.json','file');prior_binding=json.loads((root/'amp-update.json').read_text())
        if prior_binding['network']!=network:raise ValueError('Wrong existing updater binding')
        old_manifest=json.loads((binary.resolve().parent/'amp-release.json').read_text())
        if old_manifest['binary']['sha256']!=old_sha:raise ValueError('Existing managed binary checksum mismatch')
        old_epoch=prior_binding['epoch'];old_chain=prior_binding['chain_id']
    elif old_sha in KNOWN[network]:
        version,commit=KNOWN[network][old_sha]
        legacy=network=='testnet' and version in ('0.10.32','0.10.33')
        old_epoch='pre-reset' if legacy else ('mainnet-v1' if network=='mainnet' else 'testnet-2026-10-24')
        old_chain=MAIN_ID if legacy or network=='mainnet' else RESET_ID
        old_manifest={'schema':1,'network':network,'platform':'linux-amd64','version':version,'source_commit':commit,'chain_id':old_chain,'epoch':old_epoch,'sequence':0,'binary':{'url':'','sha256':old_sha,'size':len(old_data)}}
    else:raise ValueError('Unrecognized existing binary; select a verified build before integration')
    channel=f'https://raw.githubusercontent.com/{REPO}/main/channels/{network}.json'
    remote=manifest(json.loads(fetch(channel,1<<20)),network)
    reset=old_epoch!=remote['epoch'] or old_chain!=remote['chain_id']
    if reset and (network!='testnet' or accept_reset!=remote['epoch']):raise ValueError('RESET REQUIRED: after a full cold backup, rerun with --accept-testnet-reset '+remote['epoch'])
    selected=remote if reset or old_sha==remote["binary"]["sha256"] else old_manifest
    selected_data=fetch(remote['binary']['url']) if reset else old_data
    if sha(selected_data)!=selected['binary']['sha256'] or len(selected_data)!=selected['binary']['size']:raise ValueError('Selected node binary checksum/size mismatch')
    elf(selected_data)
    if network=='testnet':
        old_session=session(command)
        if reset:
            new_session='./data-'+remote['epoch'];target=root/new_session
            if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):raise ValueError('Fresh reset session destination must be absent or empty')
            command=re.sub(r'''(?<!\S)--session=(?:"[^"]*"|'[^']*'|\S+)''','--session="'+new_session+'"',command,count=1)
        else:check_genesis(root/old_session,selected['chain_id'])
    if updater_path:
        if not updater_sha:raise ValueError('--updater-sha256 is required with a local updater')
        helper=updater_path.read_bytes();expected=updater_sha
    else:
        base=f'https://github.com/{REPO}/releases/download/{UPDATER_TAG}/'
        sums=fetch(base+'SHA256SUMS',1<<20).decode()
        matches=[line.split('  ',1)[0] for line in sums.splitlines() if line.endswith('  amp-wart-update-linux-amd64')]
        if len(matches)!=1:raise ValueError('Updater checksum not found')
        expected=matches[0];helper=fetch(base+'amp-wart-update-linux-amd64')
    if sha(helper)!=expected:raise ValueError('Standalone updater checksum mismatch')
    elf(helper)
    binding={'schema':1,'network':network,'chain_id':selected['chain_id'],'epoch':selected['epoch'],'channel_url':channel}
    changes={'App.ExecutableLinux':'current/wart-node','App.CommandLineArgs':command,
        'App.UpdateSources':json.dumps(stage(network,'update'),separators=(',',':')),
        'App.PreStartStages':json.dumps(stage(network,'verify'),separators=(',',':'))}
    changed=any(get(k)!=v for k,v in changes.items())
    if changed and 'Meta.ConfigVersion' in values:changes['Meta.ConfigVersion']=str(max(10,int(get('Meta.ConfigVersion'))+1))
    updated=patch(original,changes)
    report={'network':network,'instance':str(instance),'check_only':check,'testnet_reset':reset,'epoch':selected['epoch'],
        'selected_node_sha256':selected['binary']['sha256'],'data_files_modified':False,'launch_flags_preserved':not reset,'node_processes_started':0}
    if check:return report
    stopped(instance,binary)
    for p in (root/'releases',instance/'amp-update-backups'):
        if p.is_symlink():raise ValueError('Unexpected directory symlink')
    root.joinpath('releases').mkdir(exist_ok=True)
    lock_path=root/'.amp-update.lock'
    fd=os.open(lock_path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if config.read_bytes()!=original or binary.read_bytes()!=old_data:raise ValueError('Instance changed during preparation')
        backup_root=instance/'amp-update-backups';backup_root.mkdir(mode=0o700,exist_ok=True)
        backup=Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),dir=backup_root))
        shutil.copy2(config,backup/'GenericModule.kvp');(backup/'previous-wart-node').write_bytes(old_data)
        (backup/'integration.json').write_text(json.dumps({**report,'old_sha256':old_sha,'old_executable':executable,'previous_current':os.readlink(root/'current') if (root/'current').is_symlink() else None},indent=2)+'\n')
        destination=root/'releases'/selected['binary']['sha256']
        if destination.exists():
            plain(destination,'directory');plain(destination/'wart-node','file')
            if sha((destination/'wart-node').read_bytes())!=selected['binary']['sha256']:raise ValueError('Occupied release directory has a different executable')
        else:
            destination.mkdir();atomic(destination/'wart-node',selected_data,0o755)
        metadata=destination/'amp-release.json'
        if metadata.is_symlink():raise ValueError('Release metadata is a symlink')
        if metadata.exists() and json.loads(metadata.read_text())!=selected:raise ValueError('Existing managed metadata differs')
        if not metadata.exists():atomic(metadata,(json.dumps(selected,indent=2)+'\n').encode(),0o644)
        sums=destination/'SHA256SUMS';expected_sums=selected['binary']['sha256']+'  wart-node\n'
        if sums.is_symlink() or (sums.exists() and sums.read_text()!=expected_sums):raise ValueError('Existing release checksum file differs')
        if not sums.exists():atomic(sums,expected_sums.encode(),0o644)
        if config.read_bytes()!=original or binary.read_bytes()!=old_data:raise ValueError('Instance changed before integration')
        stopped(instance,binary)
        saved=[];previous=os.readlink(root/"current") if (root/"current").is_symlink() else None;physical=None
        try:
            for target,data,mode in ((root/'amp-wart-update',helper,0o755),(root/'amp-update.json',(json.dumps(binding,indent=2)+'\n').encode(),0o644)):
                if target.is_symlink():raise ValueError('Refusing a helper/binding symlink')
                old=(target.read_bytes(),stat.S_IMODE(target.stat().st_mode)) if target.exists() else None
                saved.append((target,old));atomic(target,data,mode)
            current=root/'current'
            if current.is_symlink():previous=os.readlink(current)
            elif current.exists():
                if executable!='current/wart-node':raise ValueError('Unexpected occupied current directory')
                physical=backup/'previous-current';os.rename(current,physical)
            link(current,'releases/'+selected['binary']['sha256'])
            subprocess.run([str(root/'amp-wart-update'),'verify','--root',str(root),'--network',network],check=True,capture_output=True,text=True)
            atomic(config,updated,stat.S_IMODE(config.stat().st_mode))
        except BaseException:
            if previous is not None:link(root/'current',previous)
            elif physical is not None:
                if (root/'current').is_symlink():(root/'current').unlink()
                os.rename(physical,root/'current')
            elif (root/'current').is_symlink():(root/'current').unlink()
            for path,old in reversed(saved):
                if old is None:path.unlink(missing_ok=True)
                else:atomic(path,*old)
            raise
        report['backup_directory']=str(backup)
        return report
    finally:os.close(fd)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance',type=Path,required=True);parser.add_argument('--network',choices=['mainnet','testnet'],required=True)
    parser.add_argument('--check',action='store_true');parser.add_argument('--accept-testnet-reset')
    parser.add_argument('--updater',type=Path);parser.add_argument('--updater-sha256')
    args=parser.parse_args();print(json.dumps(install(args.instance,args.network,args.check,args.accept_testnet_reset,args.updater,args.updater_sha256),indent=2))
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,sqlite3.Error,subprocess.CalledProcessError) as error:raise SystemExit('AMP integration stopped: '+str(error))