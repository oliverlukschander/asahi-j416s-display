#!/usr/bin/env python3
"""Stage, disarm or restore the bounded 0100 experiment; never reload/reboot."""
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
CONFIG = Path('/etc/modprobe.d/j416s-0100-native-dpin.conf')
BACKUP = Path('/var/tmp/j416s-0100-before')
OPTIONS = ('options appledrm usb4_protocol_probe=1 usb4_native_dpin=1 usb4_tunnel_clock=1\n'
           'options thunderbolt_apple dpin_native=1\n'
           'options phy_apple_atc usb4_tunnel_clock=1\n')
CANDIDATES = {
    'atc': (ROOT / 'src/phy/phy-apple-atc.ko',
            'bca485f08dd1641d226897f4fd6e03ae5f933bb2d6efcaa3af52bf8d5c9e9b60'),
    'mux': (ROOT / 'src/mux/mux-apple-display-crossbar.ko',
            '228a660c494c5826345a70321c8e4f96e3a564a157836f99fbf71618ebbc7ea1'),
    'appledrm': (ROOT / 'src/appledrm/appledrm.ko',
                '01367aacf57ef5e7c43f2bad5f59446233985d3e5797c73fcfd291fcf26a555c'),
    'thunderbolt_apple': (ROOT / 'src/thunderbolt/thunderbolt_apple.ko',
                        '26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198'),
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
    for router in Path('/sys/bus/thunderbolt/devices').glob('*-*'):
        if ':' not in router.name and not router.name.endswith('-0'):
            raise RuntimeError(f'Unplug hub: external router {router.name}')

    for status in Path('/sys/class/drm').glob('card*-*/status'):
        if '-eDP-' not in status.parent.name and status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {status.parent.name}')


def verify_image(armed):
    with tempfile.TemporaryDirectory(prefix='j416s-0100-initramfs-') as tmp:
        run('lsinitcpio', '-x', str(IMAGE), cwd=tmp, stdout=subprocess.DEVNULL)
        tree = Path(tmp)
        found = list(tree.rglob('appledrm.ko'))
        if not found or any(digest(p) != CANDIDATES['appledrm'][1] for p in found):
            raise RuntimeError('Wrong appledrm in initramfs')
        for p in tree.rglob('thunderbolt_apple.ko'):
            if digest(p) != CANDIDATES['thunderbolt_apple'][1]:
                raise RuntimeError('Wrong thunderbolt_apple in initramfs')
        muxes = list(tree.rglob('mux-apple-display-crossbar.ko'))
        if any(digest(p) != CANDIDATES['mux'][1] for p in muxes):
            raise RuntimeError('Wrong crossbar in initramfs')
        atcs = list(tree.rglob('phy-apple-atc.ko'))
        if not atcs or any(digest(p) != CANDIDATES['atc'][1] for p in atcs):
            raise RuntimeError('Wrong or missing ATC PHY in initramfs')
        cfg = tree / str(CONFIG).lstrip('/')
        if armed and (not cfg.is_file() or cfg.read_text() != OPTIONS):
            raise RuntimeError('Candidate options missing from initramfs')
        if not armed and cfg.exists():
            raise RuntimeError('Candidate options still in initramfs')


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_text())
    if set(manifest) != set(TARGETS):
        raise RuntimeError('Incomplete backup manifest')
    for name in TARGETS:
        if digest(BACKUP / name) != manifest[name]:
            raise RuntimeError(f'Backup checksum mismatch: {name}')
    for name, target in TARGETS.items():
        shutil.copy2(BACKUP / name, target)
    CONFIG.unlink(missing_ok=True)
    run('depmod', '-a', VERSION)
    os.sync()
    print('Restored pre-0100 modules and initramfs; no live reload/reboot.', flush=True)


def install():
    if CONFIG.exists() or BACKUP.exists():
        raise RuntimeError('Candidate config or backup already exists; refusing overwrite')
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
                module = name.split('-')[0]
                source, expected = CANDIDATES[module]
                shutil.copy2(source, target)
                if digest(target) != expected:
                    raise RuntimeError(f'Installed checksum mismatch: {target}')
        CONFIG.write_text(OPTIONS)
        CONFIG.chmod(0o644)
        run('depmod', '-a', VERSION)
        run('mkinitcpio', '-p', 'linux-aurora')
        verify_image(armed=True)
        os.sync()
    except BaseException:
        print('Installation failed; restoring verified originals.', flush=True)
        restore()
        raise
    print('0100 installed and initramfs verified. Hub and direct external display MUST remain unplugged. No reboot performed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'disarm', 'restore'])
    args = parser.parse_args()
    preflight()
    if args.action == 'check':
        for path, expected in CANDIDATES.values():
            if digest(path) != expected:
                raise RuntimeError(f'Candidate checksum mismatch: {path}')
        print('Correct kernel/machine; hub and external display absent; candidate hashes match.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.action == 'install':
        install()
    elif args.action == 'restore':
        restore()
    else:
        if not CONFIG.is_file() or CONFIG.read_text() != OPTIONS:
            raise RuntimeError('Expected candidate config missing or changed')
        CONFIG.unlink()
        run('mkinitcpio', '-p', 'linux-aurora')
        verify_image(armed=False)
        os.sync()
        print('Future boots disarmed; currently loaded read-only parameters unchanged.')


if __name__ == '__main__':
    main()
