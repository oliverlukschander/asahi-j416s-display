#!/usr/bin/env python3
"""Stage, disarm or restore the bounded 0139 experiment; never reload/reboot.

Diagnostic only, no behavior change. Same module set as 0138 except
appledrm.ko: two additive dev_info() lines in iomfb.c --
(A) in dcp_crtc_atomic_modeset()'s existing silent 0x0-mode bail-out,
logging crtc_state->active and dcp_is_usb4_output(); (B) in dcp_hotplug(),
logging the connector's bound crtc/active/mode unconditionally. Neither
changes control flow. Purpose: settle whether the USB4 tunnel connector's
stuck-at-0x0 picture (independent of the confirmed-fixed 0136/0137/0138
bugs and the still-open ~29s firmware teardown) comes from a real but
degenerate atomic commit landing (crtc active with a 0x0 mode) or no
atomic commit ever reaching this connector at all -- a prior research
pass concluded removing dcp_hotplug()'s !dcp_is_usb4_output(dcp) gate
would very likely be a no-op either way, so no gate change is proposed
here. Requires 0138's reconnect fix to already be in place (checked
below); does not redo it.
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
CONFIG = Path('/etc/modprobe.d/j416s-0139-dpin0-mode-guess.conf')
PRIOR_CONFIG = Path('/etc/modprobe.d/j416s-0138-dpin0-mode-guess.conf')
BACKUP = Path('/var/tmp/j416s-0139-before')
PRIOR_CONFIG_BACKUP = BACKUP / 'prior-0138.conf'
OPTIONS = ('options appledrm usb4_protocol_probe=1 usb4_native_dpin=1 usb4_route_prefer_fixed_diag=1\n'
           'options thunderbolt_apple dpin_native=1\n'
           'options phy_apple_atc usb4_tunnel_clock=1\n'
           'options thunderbolt dp_video_counter=1 dp_bw_grant=1\n')
STALE_CONFIGS = [
    Path(f'/etc/modprobe.d/j416s-{n}-dpin0-mode-guess.conf')
    for n in ('0113', '0115', '0116', '0118', '0119', '0121', '0122', '0123', '0124', '0126')
]
CANDIDATES = {
    'atc': (ROOT / 'src/phy/phy-apple-atc.ko',
            '31b68d51a454885081406089c99bae00617231c49cb99680586494d3c8a4a49f'),
    'mux': (ROOT / 'src/mux/mux-apple-display-crossbar.ko',
            '813682df2cfa01b0ee83daac9824a37a3290bf234b389035e483da6c5044c3df'),
    'appledrm': (ROOT / 'src/appledrm/appledrm.ko',
                '00586d9911053147882b9981dcc4f2fdf60f126b47bdf6e0030bd78c5ec30345'),
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
    present_stale = [p for p in STALE_CONFIGS if p.is_file()]
    if present_stale:
        raise RuntimeError(f'0136 stale-config cleanup not in place: {present_stale}')
    # USB-3 (the Type-C tunnel connector this whole candidate is about) is
    # exempted here: disconnected_hpd_event() -- the only thing that ever
    # clears its "connected" status -- lives inside
    # apple_dcp_tb_dp_tunnel(active=false), which is exactly the call this
    # candidate's own fix (tb_dp_activate's early return) is needed to
    # reach. So on the *currently running, unpatched* kernel, this status
    # is permanently stuck at "connected" from the original boot connect
    # no matter how thoroughly the cable is unplugged -- confirmed stale
    # by Oliver physically unplugging it and the status not changing.
    # Every other connector keeps the real check.
    for status in Path('/sys/class/drm').glob('card*-*/status'):
        name = status.parent.name
        if '-eDP-' in name or name.endswith('-USB-3'):
            continue
        if status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {name}')


def verify_image(armed):
    with tempfile.TemporaryDirectory(prefix='j416s-0139-initramfs-') as tmp:
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
            raise RuntimeError('Superseded 0138 conf still in initramfs; remove it first')
        for base, dirs, files in os.walk(tree):
            for name in files:
                if name.endswith('.conf'):
                    p = Path(base) / name
                    try:
                        text = p.read_text()
                    except (UnicodeDecodeError, OSError):
                        continue
                    if 'usb4_defer_bringup' in text:
                        raise RuntimeError(f'usb4_defer_bringup leaked back into {p}')


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
    run('depmod', '-a', VERSION)
    run('mkinitcpio', '-p', 'linux-aurora')
    os.sync()
    print('Restored pre-0139 modules and initramfs; no live reload/reboot.', flush=True)


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
        raise RuntimeError('Expected 0138 conf missing; nothing to supersede')

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
    print('0139 installed and initramfs verified. No reboot performed.', flush=True)


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
            raise RuntimeError('Expected 0138 conf missing; nothing to supersede')
        print('Correct kernel/machine; 0136 cleanup in place; no unexpected external '
              'display route; candidate hashes match; ready to install.')
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
