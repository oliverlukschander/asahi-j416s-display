#!/usr/bin/env python3
"""Remove stale pre-0127 modprobe.d files that force usb4_defer_bringup=1
on the display crossbar, keeping 0135's own module set and options armed.
File-only (conf removal + initramfs rebuild); never reload/reboot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

VERSION = '7.1.12-2.5-1-ARCH'
MODULES = Path('/usr/lib/modules') / VERSION
IMAGE = Path('/boot/initramfs-linux-aurora.img')
OWN_CONFIG = Path('/etc/modprobe.d/j416s-0135-dpin0-mode-guess.conf')
OWN_OPTIONS = ('options appledrm usb4_protocol_probe=1 usb4_native_dpin=1 usb4_route_prefer_fixed_diag=1\n'
               'options thunderbolt_apple dpin_native=1\n'
               'options phy_apple_atc usb4_tunnel_clock=1\n'
               'options thunderbolt dp_video_counter=1 dp_bw_grant=1\n')

# Stale conf files from the discontinued native-DPIN0 experiment (2026-09-23,
# candidates 0113-0126). Each unconditionally sets
# "options mux_apple_display_crossbar usb4_defer_bringup=1", which makes
# apple_dpxbar_set_t602x() reject any dispext state other than 2 on a
# Type-C port's dpin0/dpin1 crossbar leg -- silently sabotaging every
# usb4_route_prefer_fixed_diag=1 attempt (dcpext0 = state 0) since 0127.
# None of the 0127-0135 candidate scripts manage or remove these; they were
# simply never cleaned up when the project moved on from that experiment.
STALE_CONFIGS = [
    Path(f'/etc/modprobe.d/j416s-{n}-dpin0-mode-guess.conf')
    for n in ('0113', '0115', '0116', '0118', '0119', '0121', '0122', '0123', '0124', '0126')
]
STALE_CONTENT_SHA256 = '104e761eaddb267a173b293f8fe95fe9f584902bf49892a64256bfce07c41b2e'
BACKUP = Path('/var/tmp/j416s-0136-stale-confs-before')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def preflight():
    if os.uname().release != VERSION:
        raise RuntimeError('Wrong running kernel')
    if b'apple,j416s' not in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0'):
        raise RuntimeError('Wrong machine')
    if not OWN_CONFIG.is_file() or OWN_CONFIG.read_text() != OWN_OPTIONS:
        raise RuntimeError('Candidate 0135 options missing or changed; install 0135 first')
    for status in Path('/sys/class/drm').glob('card*-*/status'):
        if '-eDP-' not in status.parent.name and status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {status.parent.name}')


def verify_image(stale_removed):
    with tempfile.TemporaryDirectory(prefix='j416s-0136-initramfs-') as tmp:
        run('lsinitcpio', '-x', str(IMAGE), cwd=tmp, stdout=subprocess.DEVNULL)
        tree = Path(tmp)
        own = tree / str(OWN_CONFIG).lstrip('/')
        if not own.is_file() or own.read_text() != OWN_OPTIONS:
            raise RuntimeError('0135 options missing from initramfs')
        found_stale = [p for p in STALE_CONFIGS if (tree / str(p).lstrip('/')).exists()]
        if stale_removed and found_stale:
            raise RuntimeError(f'Stale configs still in initramfs: {found_stale}')
        if not stale_removed and len(found_stale) != len(STALE_CONFIGS):
            raise RuntimeError('Expected all stale configs present (pre-cleanup state)')
        for base, dirs, files in os.walk(tree):
            for name in files:
                p = Path(base) / name
                if name.endswith('.conf'):
                    try:
                        text = p.read_text()
                    except (UnicodeDecodeError, OSError):
                        continue
                    if 'usb4_defer_bringup' in text and stale_removed:
                        raise RuntimeError(f'usb4_defer_bringup still present in {p}')


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_text())
    if set(manifest) != {str(p) for p in STALE_CONFIGS}:
        raise RuntimeError('Incomplete backup manifest')
    for path_str, expected in manifest.items():
        backup_file = BACKUP / Path(path_str).name
        if digest(backup_file) != expected:
            raise RuntimeError(f'Backup checksum mismatch: {path_str}')
    for path_str in manifest:
        shutil.copy2(BACKUP / Path(path_str).name, Path(path_str))
    run('mkinitcpio', '-p', 'linux-aurora')
    verify_image(stale_removed=False)
    os.sync()
    print('Restored the 10 stale confs and rebuilt initramfs; no live reload/reboot.', flush=True)


def install():
    if BACKUP.exists():
        raise RuntimeError('Backup already exists; refusing to overwrite (already installed?)')
    missing = [p for p in STALE_CONFIGS if not p.is_file()]
    if missing:
        raise RuntimeError(f'Expected stale configs not present: {missing}')
    for p in STALE_CONFIGS:
        if digest(p) != STALE_CONTENT_SHA256:
            raise RuntimeError(f'Unexpected content, refusing to remove: {p}')

    BACKUP.mkdir(mode=0o700)
    manifest = {}
    for p in STALE_CONFIGS:
        shutil.copy2(p, BACKUP / p.name)
        if digest(BACKUP / p.name) != digest(p):
            raise RuntimeError(f'Backup verification failed: {p}')
        manifest[str(p)] = digest(p)
    (BACKUP / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    os.sync()
    print('Verified backup:', BACKUP, flush=True)

    try:
        preflight()
        for p in STALE_CONFIGS:
            p.unlink()
        run('mkinitcpio', '-p', 'linux-aurora')
        verify_image(stale_removed=True)
        os.sync()
    except BaseException:
        print('Cleanup failed; restoring stale confs.', flush=True)
        restore()
        raise
    print('0136 installed: stale confs removed, initramfs verified. No reboot performed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'disarm', 'restore'])
    args = parser.parse_args()
    preflight() if args.action != 'check' else None
    if args.action == 'check':
        if os.uname().release != VERSION:
            raise RuntimeError('Wrong running kernel')
        if not OWN_CONFIG.is_file() or OWN_CONFIG.read_text() != OWN_OPTIONS:
            raise RuntimeError('Candidate 0135 options missing or changed; install 0135 first')
        missing = [p for p in STALE_CONFIGS if not p.is_file()]
        if missing:
            print(f'Stale configs already absent (nothing to clean up): {missing}')
        else:
            bad = [p for p in STALE_CONFIGS if digest(p) != STALE_CONTENT_SHA256]
            if bad:
                raise RuntimeError(f'Stale configs have unexpected content: {bad}')
            print('Correct kernel/machine; 0135 options in place; all 10 stale confs present with expected content.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.action == 'install':
        install()
    elif args.action in ('restore', 'disarm'):
        restore()


if __name__ == '__main__':
    main()
