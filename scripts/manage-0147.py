#!/usr/bin/env python3
"""Stage, or restore, resume-time auto-recovery for the DP tunnel.

drivers/usb/typec/tipd/core.c: tipd_resume() never re-verified the
port's actual attach/mode state on resume, so a cable that was already
connected before suspend generated no fresh attach event -- nothing
re-drove apple_cio_tbt_switch_set()/apple_cio_start(), even though
thunderbolt-core's own resume handling had already torn down the live
DP tunnel underneath it. A physical unplug/replug was the only thing
that worked, because it generates a genuine hardware attach event.

Added cd321x_resume_reverify(), wired only into the Apple-specific
CD321x/sn201202x vtables (tipd_cd321x_data, tipd_sn201202x_data; the
plain TI TPS6598x/TPS25750 variants get a NULL hook, unaffected). It
reproduces a genuine unplug-then-replug entirely through the existing,
already-validated connect()/cd321x_update_work() path: calls the
existing connect() callback twice (once with PLUG_PRESENT cleared, a
synthetic disconnect, then once with the real status) rather than
inventing new logic. No new suspend/resume PM hook was added to
apple_cio_driver itself -- that more invasive option was considered
and rejected for 0146, for the same reason it's rejected here: an
independent second trigger for apple_cio_start()/stop() around the
same window as the Type-C mux's own decisions risks the SoC
watchdog-reset scenario apple_cio_tbt_switch_set() documents. This
fix stays within the single, already-serialized switch-driven path.
Full detail in notes/2026-09-24-0147-typec-resume-reverify.md.

Only tps6598x-core.ko changes (built from drivers/usb/typec/tipd/core.c
-- the I2C/SPMI bus-glue modules are untouched since only core.c was
edited).
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
BACKUP = Path('/var/tmp/j416s-0147-before')
CANDIDATE = (ROOT / 'src/typec/tps6598x-core.ko',
             '25a843beba6585d18c6a8af6f3a73ea862ec1d99ddb1f91a5606bf05302f5669')
TARGETS = {
    'tps6598x-core-kernel.ko': MODULES / 'kernel/drivers/usb/typec/tipd/tps6598x-core.ko',
    'tps6598x-core-updates.ko': MODULES / 'updates/tps6598x-core.ko',
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
    with tempfile.TemporaryDirectory(prefix='j416s-0147-initramfs-') as tmp:
        run('lsinitcpio', '-x', str(IMAGE), cwd=tmp, stdout=subprocess.DEVNULL)
        tree = Path(tmp)
        for p in tree.rglob('tps6598x-core.ko'):
            if digest(p) != CANDIDATE[1]:
                raise RuntimeError('Wrong tps6598x-core in initramfs')


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
    print('Restored pre-0147 tps6598x-core module and initramfs; no live reload/reboot.', flush=True)


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
    print('0147 installed and initramfs verified. No reboot performed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'restore'])
    args = parser.parse_args()
    preflight()
    if args.action == 'check':
        source, expected = CANDIDATE
        if digest(source) != expected:
            raise RuntimeError(f'Candidate checksum mismatch: {source}')
        for name, target in TARGETS.items():
            if name.endswith('.ko') and not target.is_file():
                raise RuntimeError(f'Missing original: {target}')
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
