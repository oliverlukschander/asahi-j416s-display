#!/usr/bin/env python3
"""Stage, or restore, the AUSPLL_LOCK retry-loop fix; never reload/reboot.

atc_tunnel_restore() now polls for ACIOPHY_AUSPLL_LOCK to clear before
returning, instead of returning immediately after writing the teardown
registers. Without this, a fast retry (DCP firmware retries a failed
tunnel clock request roughly once a second) can land inside the PLL's
own unlock settling window and see a stale "still locked" reading from
its own just-torn-down state, refusing itself with -EBUSY forever --
this is what produced the continuous SET_LINK_RATE 0xa/0x0 retrain loop
on the left-back port tonight, and is very likely the actual mechanism
behind "doesn't reactivate after standby" too. Full detail in
notes/2026-09-24-0145-auspll-lock-retry-loop.md.

Only phy-apple-atc.ko changes; the other four modules are untouched.
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
BACKUP = Path('/var/tmp/j416s-0145-before')
CANDIDATE = (ROOT / 'src/phy/phy-apple-atc.ko',
             '5525c3e7c66fc8f882084fa53741b36aebbf5ec5b00f5d348893108cd2d92b73')
TARGETS = {
    'atc-kernel.ko': MODULES / 'kernel/drivers/phy/apple/phy-apple-atc.ko',
    'atc-updates.ko': MODULES / 'updates/phy-apple-atc.ko',
    'initramfs-linux-aurora.img': IMAGE,
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
        if '-eDP-' in name or name.endswith('-USB-3') or name.endswith('-USB-1'):
            continue
        if status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {name}')


def verify_image():
    with tempfile.TemporaryDirectory(prefix='j416s-0145-initramfs-') as tmp:
        run('lsinitcpio', '-x', str(IMAGE), cwd=tmp, stdout=subprocess.DEVNULL)
        tree = Path(tmp)
        atcs = list(tree.rglob('phy-apple-atc.ko'))
        if not atcs or any(digest(p) != CANDIDATE[1] for p in atcs):
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
    print('Restored pre-0145 ATC module and initramfs; no live reload/reboot.', flush=True)


def install():
    if BACKUP.exists():
        raise RuntimeError('Backup already exists; refusing to overwrite')
    source, expected = CANDIDATE
    if digest(source) != expected:
        raise RuntimeError(f'Candidate checksum mismatch: {source}')
    for target in TARGETS.values():
        if not target.is_file():
            raise RuntimeError(f'Missing original: {target}')

    BACKUP.mkdir(mode=0o700)
    manifest = {}
    for name, target in TARGETS.items():
        expected_backup = digest(target)
        shutil.copy2(target, BACKUP / name)
        if digest(BACKUP / name) != expected_backup:
            raise RuntimeError(f'Backup verification failed: {name}')
        manifest[name] = expected_backup
    (BACKUP / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    os.sync()
    print('Verified backup:', BACKUP, flush=True)
    try:
        preflight()
        for name, target in TARGETS.items():
            if name.endswith('.ko'):
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
    print('0145 installed and initramfs verified. No reboot performed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'restore'])
    args = parser.parse_args()
    preflight()
    if args.action == 'check':
        source, expected = CANDIDATE
        if digest(source) != expected:
            raise RuntimeError(f'Candidate checksum mismatch: {source}')
        print('Correct kernel/machine; candidate hash matches; ready to install.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.action == 'install':
        install()
    else:
        restore()


if __name__ == '__main__':
    main()
