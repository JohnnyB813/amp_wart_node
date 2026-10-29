#!/usr/bin/env python3
"""Build release metadata, publish immutable assets, and promote one AMP channel."""
import argparse,base64,hashlib,json,re,struct,subprocess,tempfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request,urlopen
REPO='JohnnyB813/amp_wart_node'
ROOT=Path(__file__).resolve().parents[1]

def gh(*args,optional=False):
    result=subprocess.run(['gh',*args],capture_output=True,text=True,check=False)
    if result.returncode and not optional:raise RuntimeError(result.stderr.strip())
    return None if result.returncode else result.stdout

def api(path,optional=False):
    output=gh('api',path,optional=optional)
    return json.loads(output) if output else None

def download(url,limit=64<<20):
    if not url.startswith(('https://raw.githubusercontent.com/','https://github.com/')):raise ValueError('Unexpected source URL')
    with urlopen(Request(url,headers={'User-Agent':'amp-wart-publisher/0.1.0'}),timeout=180) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Source download exceeds limit')
    return data

def validate_elf(data):
    if len(data)<64 or data[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',data,18)[0]!=62:raise ValueError('Expected Linux x86-64 ELF')
    offset=struct.unpack_from('<Q',data,32)[0];size,count=struct.unpack_from('<HH',data,54)
    if count and size<56:raise ValueError('Invalid ELF program header size')
    for i in range(count):
        kind,_,pos,_,_,length,_,_=struct.unpack_from('<IIQQQQQQ',data,offset+i*size)
        if kind==3:raise ValueError('Dynamic ELF interpreter is not supported')
        if kind==2:
            if length%16 or pos+length>len(data):raise ValueError('Invalid ELF dynamic segment')
            if any(struct.unpack_from('<qQ',data,j)[0]==1 for j in range(pos,pos+length,16)):raise ValueError('Dynamic libraries are not supported')

def source_info(repository,commit,network):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Use the full source commit SHA')
    base=f'https://raw.githubusercontent.com/{repository}/{commit}/'
    meson=download(base+'meson.build',1<<20).decode()
    version=re.search(r"version\s*:\s*'([0-9]+\.[0-9]+\.[0-9]+)'",meson).group(1)
    params=download(base+'src/shared/src/general/params.hpp',1<<20).decode()
    constant='GENESISSEED_TESTNET' if network=='testnet' else 'GENESISSEED'
    match=re.search(r'\b'+constant+r'\[\]\s*=\s*"([^"\n]+)"',params)
    if not match:raise ValueError('Explicit network genesis constant not found; review the source before publishing')
    return version,hashlib.sha256(match.group(1).encode()).hexdigest()

def timestamp(value):return int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp())

def prepare(network,binary_path=None,source_commit=None,from_source=False):
    policy=json.loads((ROOT/'channels/policy.json').read_text())[network]
    repository=policy['source_repository']
    if network=='testnet' and not from_source:
        release=api(f'repos/{repository}/releases/latest')
        asset=next(a for a in release['assets'] if a['name']=='wart-node-defi-beta-linux')
        digest=asset.get('digest','')
        if not re.fullmatch('sha256:[0-9a-f]{64}',digest):raise ValueError('Official asset has no published SHA-256')
        if not source_commit:
            runs=api(f'repos/{repository}/actions/runs?branch=defi&status=success&per_page=100')['workflow_runs']
            matches=[r for r in runs if r['name']=='Release (defi)' and timestamp(r['created_at'])<=timestamp(asset['updated_at'])<=timestamp(r['updated_at'])+60]
            if len(matches)!=1:raise ValueError('Cannot uniquely identify the DeFi build source; supply --source-commit after review')
            source_commit=matches[0]['head_sha']
        version,chain_id=source_info(repository,source_commit,network)
        if release['tag_name'].lstrip('v')!=version:raise ValueError('DeFi source version differs from published asset')
        data=Path(binary_path).read_bytes() if binary_path else download(asset['browser_download_url'])
        if len(data)!=asset['size'] or hashlib.sha256(data).hexdigest()!=digest[7:]:raise ValueError('Official DeFi binary checksum/size mismatch')
        sequence=timestamp(asset['updated_at'])
    else:
        if not binary_path or not source_commit:raise ValueError('Source builds require --binary and --source-commit from the tested source build')
        version,chain_id=source_info(repository,source_commit,network)
        data=Path(binary_path).read_bytes()
        commit=api(f'repos/{repository}/commits/{source_commit}')
        sequence=timestamp(commit['commit']['committer']['date'])
    if chain_id!=policy['chain_id']:raise ValueError('Genesis changed: review channels/policy.json for a new epoch before publishing')
    if not 0<len(data)<=64<<20:raise ValueError('Unexpected binary size')
    validate_elf(data)
    digest=hashlib.sha256(data).hexdigest()
    tag=f'{network}-{version}-{source_commit[:12]}-{digest[:12]}' if network=='mainnet' or from_source else f'{network}-{version}-{digest[:12]}'
    asset_name=f'wart-node-{network}-linux-amd64'
    manifest={'schema':1,'network':network,'platform':'linux-amd64','version':version,'source_commit':source_commit,
        'chain_id':chain_id,'epoch':policy['epoch'],'sequence':sequence,
        'binary':{'url':f'https://github.com/{REPO}/releases/download/{tag}/{asset_name}','sha256':digest,'size':len(data)}}
    destination=ROOT/'dist'/tag;destination.mkdir(parents=True,exist_ok=True)
    (destination/asset_name).write_bytes(data)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    (destination/'SHA256SUMS').write_text(''.join(hashlib.sha256((destination/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in (asset_name,'manifest.json')),encoding='utf-8',newline='\n')
    return tag,destination,manifest

def publish(tag,directory,manifest,source_build=False):
    names=[f'wart-node-{manifest["network"]}-linux-amd64','manifest.json','SHA256SUMS']
    existing=api(f'repos/{REPO}/releases/tags/{tag}',optional=True)
    if existing:
        assets={a['name']:a.get('digest') for a in existing['assets']}
        for name in names:
            if assets.get(name)!='sha256:'+hashlib.sha256((directory/name).read_bytes()).hexdigest():raise ValueError('Existing immutable release differs; assets will not be overwritten')
    else:
        origin='upstream source build' if source_build else ('official upstream asset mirror' if manifest['network']=='testnet' else 'custom mainnet source build')
        notes=directory/'release-notes.txt'
        notes.write_text(f'Origin: {origin}\nWarthog {manifest["network"]} {manifest["version"]}\nSource: {manifest["source_commit"]}\nEpoch: {manifest["epoch"]}\nBinary SHA-256: {manifest["binary"]["sha256"]}\n\nDownloads do not contain databases or wallet keys.\n')
        gh('release','create',tag,*[str(directory/n) for n in names],'--repo',REPO,'--title',f'{manifest["network"]} {manifest["version"]} ({manifest["source_commit"][:12]})','--notes-file',str(notes),'--latest=false')
    channel=f'channels/{manifest["network"]}.json'
    current=api(f'repos/{REPO}/contents/{channel}',optional=True)
    content=(directory/'manifest.json').read_bytes()
    if current:
        previous=base64.b64decode(current['content'])
        if previous==content:return
        old=json.loads(previous)
        if old['network']!=manifest['network']:raise ValueError('Existing channel network differs')
        if old['epoch']==manifest['epoch'] and old['sequence']>manifest['sequence']:raise ValueError('Channel promotion would move backwards; use explicit node rollback')
    body={'message':f'Promote {manifest["network"]} {tag}','content':base64.b64encode(content).decode(),'branch':'main'}
    if current:body['sha']=current['sha']
    with tempfile.TemporaryDirectory() as temporary:
        payload=Path(temporary)/'promotion.json';payload.write_text(json.dumps(body))
        gh('api','--method','PUT',f'repos/{REPO}/contents/{channel}','--input',str(payload))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('network',choices=['mainnet','testnet']);parser.add_argument('--binary',type=Path)
    parser.add_argument('--source-commit');parser.add_argument('--publish',action='store_true')
    parser.add_argument('--from-source',action='store_true',help='Publish a tested testnet source build instead of mirroring an official asset')
    args=parser.parse_args();tag,path,manifest=prepare(args.network,args.binary,args.source_commit,args.from_source)
    if args.publish:publish(tag,path,manifest,args.from_source)
    print(json.dumps({'tag':tag,'path':str(path),'published':args.publish,'manifest':manifest},indent=2))
if __name__=='__main__':main()