#!/usr/bin/env python3
"""Remove 8 more stale pre-0135 modprobe.d files forcing
usb4_native_dpin=1/usb4_protocol_probe=1, on top of 0141's modules.

0140/0141 dropped these two flags from OUR OWN candidate's own options,
but the live module_param values still read Y: eight leftover conf files
from candidates 0127-0134 (never cleaned up -- 0136 only cleaned up the
older 0113-0126 batch) still set
"options appledrm usb4_protocol_probe=1 usb4_native_dpin=1", and modprobe
merges every matching "options appledrm ..." line across every conf file
it finds. Confirmed directly: /sys/module/appledrm/parameters/
{usb4_native_dpin,usb4_protocol_probe} both read Y despite our own
candidate's conf omitting them, and all 8 stale files are confirmed
baked into the currently-installed initramfs alongside our own. Same
shape of bug as 0136, different batch of leftovers.
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
CONFIG = Path('/etc/modprobe.d/j416s-0142-dpin0-mode-guess.conf')
PRIOR_CONFIG = Path('/etc/modprobe.d/j416s-0141-dpin0-mode-guess.conf')
BACKUP = Path('/var/tmp/j416s-0142-before')
PRIOR_CONFIG_BACKUP = BACKUP / 'prior-0141.conf'
OPTIONS = ('options appledrm usb4_route_prefer_fixed_diag=1\n'
           'options thunderbolt_apple dpin_native=1\n'
           'options phy_apple_atc usb4_tunnel_clock=1\n'
           'options thunderbolt dp_video_counter=1 dp_bw_grant=1\n')
OLD_STALE_CONFIGS = [
    Path(f'/etc/modprobe.d/j416s-{n}-dpin0-mode-guess.conf')
    for n in ('0113', '0115', '0116', '0118', '0119', '0121', '0122', '0123', '0124', '0126')
]
NEW_STALE_CONFIGS = [
    Path(f'/etc/modprobe.d/j416s-{n}-dpin0-mode-guess.conf')
    for n in ('0127', '0128', '0129', '0130', '0131', '0132', '0133', '0134')
]
NEW_STALE_SHA256 = '902cf068b6bd382fc1ff70de0579011351efd0a4849522f41bc599605bc4ed65'
CANDIDATES = {
    'atc': (ROOT / 'src/phy/phy-apple-atc.ko',
            '31b68d51a454885081406089c99bae00617231c49cb99680586494d3c8a4a49f'),
    'mux': (ROOT / 'src/mux/mux-apple-display-crossbar.ko',
            '813682df2cfa01b0ee83daac9824a37a3290bf234b389035e483da6c5044c3df'),
    'appledrm': (ROOT / 'src/appledrm/appledrm.ko',
                '5a478e08bf8688c107681ff2b2cadc4c0a01f4790b75c25cf6aef50950317bd6'),
    'thunderbolt_apple': (ROOT / 'src/thunderbolt/thunderbolt_apple.ko',
                        'cfcd0fce5f999ab0ee082cb2680468996c96c9a143ace01d324aff6ee7268374'),
    'thunderbolt': (ROOT / 'src/thunderbolt/thunderbolt.ko',
                   '8f716975e3e6324c4e2731de937188a338a75887c3506afe61ef983c4aea68e7'),
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
    present_old_stale = [p for p in OLD_STALE_CONFIGS if p.is_file()]
    if present_old_stale:
        raise RuntimeError(f'0136 stale-config cleanup not in place: {present_old_stale}')
    # USB-3 stale "connected" status: same rationale as 0138-0141 -- the
    # only thing that ever clears it lives behind the exact fix chain
    # this candidate is part of, so it can read connected long after the
    # cable was last unplugged. Every other connector keeps the real check.
    for status in Path('/sys/class/drm').glob('card*-*/status'):
        name = status.parent.name
        if '-eDP-' in name or name.endswith('-USB-3'):
            continue
        if status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {name}')


def verify_image(armed):
    with tempfile.TemporaryDirectory(prefix='j416s-0142-initramfs-') as tmp:
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
        cfg = tree / str(CONFIG).lstrip('/')
        if armed and (not cfg.is_file() or cfg.read_text() != OPTIONS):
            raise RuntimeError('Candidate options missing from initramfs')
        if not armed and cfg.exists():
            raise RuntimeError('Candidate options still in initramfs')
        prior_cfg = tree / str(PRIOR_CONFIG).lstrip('/')
        if prior_cfg.exists():
            raise RuntimeError('Superseded 0141 conf still in initramfs; remove it first')
        for p in NEW_STALE_CONFIGS:
            stale_in_image = tree / str(p).lstrip('/')
            if armed and stale_in_image.exists():
                raise RuntimeError(f'Stale conf still in initramfs: {p}')
        for base, dirs, files in os.walk(tree):
            for name in files:
                if not name.endswith('.conf'):
                    continue
                p = Path(base) / name
                try:
                    text = p.read_text()
                except (UnicodeDecodeError, OSError):
                    continue
                if 'usb4_defer_bringup' in text:
                    raise RuntimeError(f'usb4_defer_bringup leaked back into {p}')
                if armed and ('usb4_native_dpin=1' in text or 'usb4_protocol_probe=1' in text):
                    raise RuntimeError(f'usb4_native_dpin/usb4_protocol_probe leaked back into {p}')


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
    if PRIOR_CONFIG_BACKUP.exists():
        shutil.copy2(PRIOR_CONFIG_BACKUP, PRIOR_CONFIG)
    for n in NEW_STALE_CONFIGS:
        backup_file = BACKUP / n.name
        if backup_file.exists():
            shutil.copy2(backup_file, n)
    run('depmod', '-a', VERSION)
    run('mkinitcpio', '-p', 'linux-aurora')
    os.sync()
    print('Restored pre-0142 modules, stale confs, and initramfs; no live reload/reboot.', flush=True)


def install():
    if CONFIG.exists() or BACKUP.exists():
        raise RuntimeError('Candidate config or backup already exists; refusing overwrite')
    for path, expected in CANDIDATES.values():
        if digest(path) != expected:
            raise RuntimeError(f'Candidate checksum mismatch: {path}')
    for target in TARGETS.values():
        if not target.is_file():
            raise RuntimeError(f'Missing original: {target}')
    if not PRIOR_CONFIG.is_file():
        raise RuntimeError('Expected 0141 conf missing; nothing to supersede')
    missing_stale = [p for p in NEW_STALE_CONFIGS if not p.is_file()]
    if missing_stale:
        raise RuntimeError(f'Expected stale configs not present: {missing_stale}')
    for p in NEW_STALE_CONFIGS:
        if digest(p) != NEW_STALE_SHA256:
            raise RuntimeError(f'Unexpected content, refusing to remove: {p}')

    BACKUP.mkdir(mode=0o700)
    manifest = {}
    for name, target in TARGETS.items():
        expected = digest(target)
        shutil.copy2(target, BACKUP / name)
        if digest(BACKUP / name) != expected:
            raise RuntimeError(f'Backup verification failed: {name}')
        manifest[name] = expected
    (BACKUP / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy2(PRIOR_CONFIG, PRIOR_CONFIG_BACKUP)
    for p in NEW_STALE_CONFIGS:
        shutil.copy2(p, BACKUP / p.name)
        if digest(BACKUP / p.name) != digest(p):
            raise RuntimeError(f'Stale-conf backup verification failed: {p}')
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
        PRIOR_CONFIG.unlink()
        for p in NEW_STALE_CONFIGS:
            p.unlink()
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
    print('0142 installed and initramfs verified. No reboot performed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'disarm', 'restore'])
    args = parser.parse_args()
    preflight()
    if args.action == 'check':
        for path, expected in CANDIDATES.values():
            if digest(path) != expected:
                raise RuntimeError(f'Candidate checksum mismatch: {path}')
        if not PRIOR_CONFIG.is_file():
            raise RuntimeError('Expected 0141 conf missing; nothing to supersede')
        missing_stale = [p for p in NEW_STALE_CONFIGS if not p.is_file()]
        if missing_stale:
            print(f'Stale configs already absent (nothing to clean up): {missing_stale}')
        else:
            bad = [p for p in NEW_STALE_CONFIGS if digest(p) != NEW_STALE_SHA256]
            if bad:
                raise RuntimeError(f'Stale configs have unexpected content: {bad}')
            print('Correct kernel/machine; 0136 cleanup in place; candidate hashes match; '
                  'all 8 new stale confs (0127-0134) present with expected content; ready to install.')
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
