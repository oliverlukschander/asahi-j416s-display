#!/usr/bin/env python3
"""Stage, disarm or restore the final, cleaned-up driver; never reload/reboot.

Full generalization pass: removed every diagnostic-only print added this
session (fires on every atomic commit/frame in some cases -- real log
spam for permanent use) and every module_param gate that was either (a)
confirmed dead/superseded scaffolding from the pre-0127 "native DPIN0"
single-purpose experiment (usb4_native_dpin, usb4_protocol_probe,
dcp_usb4_native_route() and its possible_crtcs exclusion, dpin_native,
apple_usb4_dpin0_set_active(), usb4_defer_bringup and its whole deferred-
bringup/frame-snapshot mechanism in the crossbar driver), or (b) a
redundant opt-in flag layered on top of scoping that's already
hardware-precise (usb4_route_prefer_fixed_diag -- now the unconditional,
permanent route-scoring preference, since dcpext1 has a confirmed
firmware-internal defect for a Type-C tunnel target; usb4_tunnel_clock
and dp_bw_grant -- both already gated on of_machine_is_compatible(
"apple,j416s") plus specific port/PHY checks, so the extra flag added
nothing). dp_video_counter (phy/apple/atc.c... actually
drivers/thunderbolt/tunnel.c) is kept: it is a genuine, self-described,
permanent diagnostic (packet counters via debugfs), not scaffolding, and
stays off by default like any other opt-in diagnostic (show_notch,
hdmi_audio, unstable_edid).

Net effect: NO module options are needed at all any more. This candidate
removes the last remaining j416s conf file entirely, with no replacement.
Requires 0142's stale-config cleanup to already be in place (checked
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
PRIOR_CONFIG = Path('/etc/modprobe.d/j416s-0142-dpin0-mode-guess.conf')
BACKUP = Path('/var/tmp/j416s-0143-before')
PRIOR_CONFIG_BACKUP = BACKUP / 'prior-0142.conf'
OLD_STALE_CONFIGS = [
    Path(f'/etc/modprobe.d/j416s-{n}-dpin0-mode-guess.conf')
    for n in ('0113', '0115', '0116', '0118', '0119', '0121', '0122', '0123', '0124', '0126')
]
NEW_STALE_CONFIGS = [
    Path(f'/etc/modprobe.d/j416s-{n}-dpin0-mode-guess.conf')
    for n in ('0127', '0128', '0129', '0130', '0131', '0132', '0133', '0134')
]
CANDIDATES = {
    'atc': (ROOT / 'src/phy/phy-apple-atc.ko',
            '68139956324f5864de7103b3a7e3dfaf789eaa57e2153a9413e0e95182246aea'),
    'mux': (ROOT / 'src/mux/mux-apple-display-crossbar.ko',
            '0c1e5d3b8cf2d89405226ee9398ffe0a35ac56f0fecbf974f7cb4d2c252b9341'),
    'appledrm': (ROOT / 'src/appledrm/appledrm.ko',
                '6f262fc469200952b7cab5d5ca95a534230922ae6bee40103331e6a8493c31cc'),
    'thunderbolt_apple': (ROOT / 'src/thunderbolt/thunderbolt_apple.ko',
                        '929c9701a975e8b7c6df79313eb152c813fe5f6f9f4599b1188a063100e508c7'),
    'thunderbolt': (ROOT / 'src/thunderbolt/thunderbolt.ko',
                   '5ed6047164978c1506bb8ac8abf8545dd91ccbbaa36b0b7dba8ac89596c85ce7'),
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
REMOVED_FLAGS = (
    'usb4_native_dpin', 'usb4_protocol_probe', 'usb4_route_prefer_fixed_diag',
    'dpin_native', 'usb4_defer_bringup', 'usb4_tunnel_clock', 'dp_bw_grant',
)


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
    present_new_stale = [p for p in NEW_STALE_CONFIGS if p.is_file()]
    if present_new_stale:
        raise RuntimeError(f'0142 stale-config cleanup not in place: {present_new_stale}')
    for status in Path('/sys/class/drm').glob('card*-*/status'):
        name = status.parent.name
        if '-eDP-' in name or name.endswith('-USB-3'):
            continue
        if status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {name}')


def verify_image():
    with tempfile.TemporaryDirectory(prefix='j416s-0143-initramfs-') as tmp:
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
        prior_cfg = tree / str(PRIOR_CONFIG).lstrip('/')
        if prior_cfg.exists():
            raise RuntimeError('Superseded 0142 conf still in initramfs; remove it first')
        for base, dirs, files in os.walk(tree):
            for name in files:
                if not name.endswith('.conf'):
                    continue
                p = Path(base) / name
                try:
                    text = p.read_text()
                except (UnicodeDecodeError, OSError):
                    continue
                for flag in REMOVED_FLAGS:
                    if f'{flag}=1' in text:
                        raise RuntimeError(f'{flag}=1 leaked back into {p}')


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_text())
    if set(manifest) != set(TARGETS):
        raise RuntimeError('Incomplete backup manifest')
    for name in TARGETS:
        if digest(BACKUP / name) != manifest[name]:
            raise RuntimeError(f'Backup checksum mismatch: {name}')
    for name, target in TARGETS.items():
        shutil.copy2(BACKUP / name, target)
    if PRIOR_CONFIG_BACKUP.exists() and not PRIOR_CONFIG.exists():
        shutil.copy2(PRIOR_CONFIG_BACKUP, PRIOR_CONFIG)
    run('depmod', '-a', VERSION)
    run('mkinitcpio', '-p', 'linux-aurora')
    os.sync()
    print('Restored pre-0143 modules, conf, and initramfs; no live reload/reboot.', flush=True)


def install():
    if BACKUP.exists():
        raise RuntimeError('Backup already exists; refusing to overwrite')
    for path, expected in CANDIDATES.values():
        if digest(path) != expected:
            raise RuntimeError(f'Candidate checksum mismatch: {path}')
    for target in TARGETS.values():
        if not target.is_file():
            raise RuntimeError(f'Missing original: {target}')
    if not PRIOR_CONFIG.is_file():
        raise RuntimeError('Expected 0142 conf missing; nothing to supersede')

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
        run('depmod', '-a', VERSION)
        run('mkinitcpio', '-p', 'linux-aurora')
        verify_image()
        os.sync()
    except BaseException:
        print('Installation failed; restoring verified originals.', flush=True)
        restore()
        raise
    print('0143 installed and initramfs verified: no j416s conf file needed any more. '
          'No reboot performed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'restore'])
    args = parser.parse_args()
    preflight()
    if args.action == 'check':
        for path, expected in CANDIDATES.values():
            if digest(path) != expected:
                raise RuntimeError(f'Candidate checksum mismatch: {path}')
        if not PRIOR_CONFIG.is_file():
            raise RuntimeError('Expected 0142 conf missing; nothing to supersede')
        print('Correct kernel/machine; 0136+0142 cleanup in place; candidate hashes match; '
              'ready to install (removes the last j416s conf file entirely).')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.action == 'install':
        install()
    else:
        restore()


if __name__ == '__main__':
    main()
