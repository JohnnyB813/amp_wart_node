#!/usr/bin/env python3
"""Publish a pinned updater/installer pair; never replace an existing release."""
import argparse,hashlib,shutil
from pathlib import Path
from publish import REPO,ROOT,api,gh,validate_elf

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    binary=ROOT/'dist/amp-wart-update-linux-amd64';validate_elf(binary.read_bytes())
    directory=ROOT/'dist/updater-v0.1.0';directory.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(binary,directory/binary.name)
    shutil.copyfile(ROOT/'scripts/install-amp-updates.py',directory/'install-amp-updates.py')
    names=['amp-wart-update-linux-amd64','install-amp-updates.py']
    (directory/'SHA256SUMS').write_text(''.join(hashlib.sha256((directory/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in names),encoding='utf-8',newline='\n')
    if args.publish:
        existing=api(f'repos/{REPO}/releases/tags/updater-v0.1.0',optional=True)
        if existing:
            assets={a['name']:a.get('digest') for a in existing['assets']}
            for name in [*names,'SHA256SUMS']:
                if assets.get(name)!='sha256:'+hashlib.sha256((directory/name).read_bytes()).hexdigest():raise ValueError('Updater release is immutable; bump its version instead of overwriting it')
        else:
            notes=directory/'notes.txt';notes.write_text('One-time AMP channel integration for Linux x86-64.\n\nStandalone updater, installer and SHA-256 checksums. No runtime Python dependency inside AMP containers.\n\nFollow the repository setup guide before running the installer. Stop and back up only the target node/managed instance. Testnet resets require explicit acceptance.\n')
            gh('release','create','updater-v0.1.0',*[str(directory/n) for n in [*names,'SHA256SUMS']],'--repo',REPO,'--title','AMP updater 0.1.0','--notes-file',str(notes),'--latest=false')
    print(directory)
if __name__=='__main__':main()