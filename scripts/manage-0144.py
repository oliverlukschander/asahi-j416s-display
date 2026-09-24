#!/usr/bin/env python3
"""Stage, or restore, the PR-prep cleanup pass; never reload/reboot.

Same driver behavior as 0143 except one real fix: drivers/phy/apple/atc.c's
tunnel_attempted flag was never cleared on teardown, so the USB4 tunnel
pixel clock could only ever be granted once per boot -- every subsequent
unplug/replug would fail with -EALREADY. atc_tunnel_restore() now clears
it alongside tunnel_saved/tunnel_rate.

Everything else is dead-code removal (exported symbols and struct fields
with zero callers/readers anywhere in the tree, verified by grep), comment
rewrites (dropped this project's own candidate/session-number references,
kept every technical fact), and log-level downgrades (dev_info/dev_warn
diagnostic dumps added while debugging -> dev_dbg, off by default) -- no
other behavior change. Full detail in
notes/2026-09-24-0144-pr-prep-cleanup.md.

No j416s conf file involved (0143 already removed the last one); this is
a pure module-file swap.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

VERSION = '7.1.12-2.5-1-ARCH'
ROOT = Path(__file__).resolve().parents[1]
MODULES = Path('/usr/lib/modules') / VERSION
IMAGE = Path('/boot/initramfs-linux-aurora.img')
BACKUP = Path('/var/tmp/j416s-0144-before')
CANDIDATES = {
    'atc': (ROOT / 'src/phy/phy-apple-atc.ko',
            'd50282ecbcb7e7b38d1be73ede1d4ca6c26bbe538366a2e0c6e8fd610dc9e529'),
    'mux': (ROOT / 'src/mux/mux-apple-display-crossbar.ko',
            'b9c5a4ffccee537780a4f48912bc2aa94c7ea2d19af1b0f4da73dadd3eb4699d'),
    'appledrm': (ROOT / 'src/appledrm/appledrm.ko',
                '8d56c8c01f56ea7463397a68d7451e28af353ad240ad0c903d02aa10b7b8dc33'),
    'thunderbolt_apple': (ROOT / 'src/thunderbolt/thunderbolt_apple.ko',
                        '47138ae05b43137f7ab304bd105b1177c4e9c7f6a1ae45e596a78bca76761a25'),
    'thunderbolt': (ROOT / 'src/thunderbolt/thunderbolt.ko',
                   '8978842bd5154c8fe2c63cb3705f1a47bbd629f44e392f2d48d4271b75ced9e3'),
}
TARGETS = {
    'atc-kernel.ko': MODULES / 'kernel/drivers/phy/apple/phy-apple-atc.ko',
    'atc-updates.ko': MODULES / 'updates/phy-apple-atc.ko',
    'mux-kernel.ko': MODULES / 'kernel/drivers/mux/mux-apple-display-crossbar.ko',
    'mux-updates.ko': MODULES / 'updates/mux-apple-display-crossbar.ko',
    'appledrm-kernel.ko': MODULES / 'kernel/drivers/gpu/drm/apple/appledrm.ko',
    'appledrm-updates.ko': MODULES / 'updates/appledrm.ko',
    'thunderbolt_apple-kernel.ko': MODULES / 'kernel/drivers/thunderbolt/thunderbolt_apple.ko',
    'thunderbolt_apple-updates.ko': MODULES / 'updates/thunderbolt_apple.ko',
    'thunderbolt-kernel.ko': MODULES / 'kernel/drivers/thunderbolt/thunderbolt.ko',
    'thunderbolt-updates.ko': MODULES / 'updates/thunderbolt.ko',
    'initramfs-linux-aurora.img': IMAGE,
}
MODULE_OF = {
    'atc-kernel.ko': 'atc',
    'atc-updates.ko': 'atc',
    'mux-kernel.ko': 'mux',
    'mux-updates.ko': 'mux',
    'appledrm-kernel.ko': 'appledrm',
    'appledrm-updates.ko': 'appledrm',
    'thunderbolt_apple-kernel.ko': 'thunderbolt_apple',
    'thunderbolt_apple-updates.ko': 'thunderbolt_apple',
    'thunderbolt-kernel.ko': 'thunderbolt',
    'thunderbolt-updates.ko': 'thunderbolt',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def preflight():
    if os.uname().release != VERSION:
        raise RuntimeError('Wrong running kernel')
    if b'apple,j416s' not in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0'):
        raise RuntimeError('Wrong machine')
    for status in Path('/sys/class/drm').glob('card*-*/status'):
        name = status.parent.name
        if '-eDP-' in name or name.endswith('-USB-3'):
            continue
        if status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {name}')


def verify_image():
    with tempfile.TemporaryDirectory(prefix='j416s-0144-initramfs-') as tmp:
        run('lsinitcpio', '-x', str(IMAGE), cwd=tmp, stdout=subprocess.DEVNULL)
        tree = Path(tmp)
        found = list(tree.rglob('appledrm.ko'))
        if not found or any(digest(p) != CANDIDATES['appledrm'][1] for p in found):
            raise RuntimeError('Wrong appledrm in initramfs')
        for p in tree.rglob('thunderbolt_apple.ko'):
            if digest(p) != CANDIDATES['thunderbolt_apple'][1]:
                raise RuntimeError('Wrong thunderbolt_apple in initramfs')
        for p in tree.rglob('thunderbolt.ko'):
            if digest(p) != CANDIDATES['thunderbolt'][1]:
                raise RuntimeError('Wrong thunderbolt (core) in initramfs')
        muxes = list(tree.rglob('mux-apple-display-crossbar.ko'))
        if any(digest(p) != CANDIDATES['mux'][1] for p in muxes):
            raise RuntimeError('Wrong crossbar in initramfs')
        atcs = list(tree.rglob('phy-apple-atc.ko'))
        if not atcs or any(digest(p) != CANDIDATES['atc'][1] for p in atcs):
            raise RuntimeError('Wrong or missing ATC PHY in initramfs')


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_text())
    if set(manifest) != set(TARGETS):
        raise RuntimeError('Incomplete backup manifest')
    for name in TARGETS:
        if digest(BACKUP / name) != manifest[name]:
            raise RuntimeError(f'Backup checksum mismatch: {name}')
    for name, target in TARGETS.items():
        shutil.copy2(BACKUP / name, target)
    run('depmod', '-a', VERSION)
    run('mkinitcpio', '-p', 'linux-aurora')
    os.sync()
    print('Restored pre-0144 modules and initramfs; no live reload/reboot.', flush=True)


def install():
    if BACKUP.exists():
        raise RuntimeError('Backup already exists; refusing to overwrite')
    for path, expected in CANDIDATES.values():
        if digest(path) != expected:
            raise RuntimeError(f'Candidate checksum mismatch: {path}')
    for target in TARGETS.values():
        if not target.is_file():
            raise RuntimeError(f'Missing original: {target}')

    BACKUP.mkdir(mode=0o700)
    manifest = {}
    for name, target in TARGETS.items():
        expected = digest(target)
        shutil.copy2(target, BACKUP / name)
        if digest(BACKUP / name) != expected:
            raise RuntimeError(f'Backup verification failed: {name}')
        manifest[name] = expected
    (BACKUP / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    os.sync()
    print('Verified backup:', BACKUP, flush=True)
    try:
        preflight()
        for name, target in TARGETS.items():
            if name.endswith('.ko'):
                module = MODULE_OF[name]
                source, expected = CANDIDATES[module]
                shutil.copy2(source, target)
                if digest(target) != expected:
                    raise RuntimeError(f'Installed checksum mismatch: {target}')
        run('depmod', '-a', VERSION)
        run('mkinitcpio', '-p', 'linux-aurora')
        verify_image()
        os.sync()
    except BaseException:
        print('Installation failed; restoring verified originals.', flush=True)
        restore()
        raise
    print('0144 installed and initramfs verified. No reboot performed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'restore'])
    args = parser.parse_args()
    preflight()
    if args.action == 'check':
        for path, expected in CANDIDATES.values():
            if digest(path) != expected:
                raise RuntimeError(f'Candidate checksum mismatch: {path}')
        print('Correct kernel/machine; candidate hashes match; ready to install.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.action == 'install':
        install()
    else:
        restore()


if __name__ == '__main__':
    main()
