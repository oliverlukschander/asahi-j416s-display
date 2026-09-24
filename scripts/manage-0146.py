#!/usr/bin/env python3
"""Stage, or restore, a bounded retry around the ACIO reset handshake.

apple_cio_start()'s reset_control_deassert(acio->reset) call is a
request/ack handshake with the M3/PMGR firmware (100ms budget per
attempt, no .assert op to fall back on). Confirmed via live dmesg to
time out on resume from suspend with an active USB4 tunnel, right when
every other coprocessor on the SoC is also coming back online at once.
Now retries up to APPLE_CIO_START_RETRIES (5) times, 100ms apart,
before giving up. No new code path, no new suspend/resume hook -- only
the existing call, retried. Full detail in
notes/2026-09-24-0146-acio-reset-retry-suspend.md.

RISK: this touches the Thunderbolt controller bring-up path under a
suspend/resume scenario upstream has never validated
(aurora-silicon/linux#8: "Suspend with an active tunnel has not been
validated"). apple_cio_tbt_switch_set() documents that an invalid
cable-state transition can crash ACIO and trigger an SoC watchdog
reset -- this candidate does NOT touch that code path (no new PM
hooks), but the underlying scenario being tested (resume with a live
tunnel) is exactly where that class of failure could show up. Test
with that in mind.

Only thunderbolt_apple.ko changes; the other four modules are
untouched.
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
BACKUP = Path('/var/tmp/j416s-0146-before')
CANDIDATE = (ROOT / 'src/thunderbolt/thunderbolt_apple.ko',
             'd0ec1d8fd2aeea333f1a50f4e09a62ab5095b8e2c9e1c6ed64933b97425df527')
TARGETS = {
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
    for status in Path('/sys/class/drm').glob('card*-*/status'):
        name = status.parent.name
        if '-eDP-' in name or name.endswith('-USB-3') or name.endswith('-USB-1'):
            continue
        if status.read_text().strip() == 'connected':
            raise RuntimeError(f'Unplug external display: {name}')


def verify_image():
    with tempfile.TemporaryDirectory(prefix='j416s-0146-initramfs-') as tmp:
        run('lsinitcpio', '-x', str(IMAGE), cwd=tmp, stdout=subprocess.DEVNULL)
        tree = Path(tmp)
        found = list(tree.rglob('thunderbolt_apple.ko'))
        if not found or any(digest(p) != CANDIDATE[1] for p in found):
            raise RuntimeError('Wrong or missing thunderbolt_apple in initramfs')


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
    print('Restored pre-0146 thunderbolt_apple module and initramfs; no live reload/reboot.', flush=True)


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
    print('0146 installed and initramfs verified. No reboot performed.', flush=True)


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
