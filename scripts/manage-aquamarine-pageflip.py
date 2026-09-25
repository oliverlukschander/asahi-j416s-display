#!/usr/bin/env python3
"""Stage, or restore, both local Aquamarine fixes (one shared library).

Two unrelated fixes are built into the same libaquamarine.so.0.15.1:

1. Stale pending-flip on reconnect (0001-connect-clear-stale-pageflip.patch):
   SDRMConnector::connect() never cleared a CRTC's stale pending-flip
   bookkeeping, unlike disconnect() and setCRTC() (when the CRTC assignment
   changes). A prior commit in flight when a Thunderbolt/USB4-tunneled
   display's tunnel is torn down abruptly at suspend leaves
   crtc->pendingFlip stuck; when the tunnel and connector come back
   (0147's resume auto-recovery reconnects to the *same* CRTC), nothing
   clears it, and every subsequent real commit is silently rejected -- the
   exact "outputs permanently black" failure mode Aquamarine's own
   restoreAfterVT() already guards against for a different trigger (VT
   switch / session reactivation), just reached via a hotplug reconnect
   instead. Fix: call the existing, already-safe invalidateFrame()
   unconditionally at the top of connect() too. Full detail in
   notes/2026-09-25-aquamarine-stale-pageflip.md.

2. Destructor teardown null-deref (0002-fix-destructor-teardown-order.patch):
   CDRMBackend::~CDRMBackend() reset each connector's shared_ptr in the same
   pass that disconnect() transitively re-walks the whole connectors vector,
   so tearing down 2+ connectors dereferenced an already-nulled earlier
   slot. Already confirmed crashing the real, system-installed Hyprland
   twice in one morning before this was even found. Fix: disconnect
   everything first, reset everything only after. Full detail in
   notes/2026-09-25-aquamarine-destructor-teardown-crash.md.

This is a plain shared library (/usr/lib/libaquamarine.so.0.15.1,
symlinked from .so/.so.14), not a kernel module -- no depmod,
initramfs, or reboot. But it's pacman-owned and actively mapped into
the running Hyprland session: install only swaps the file on disk
(safe -- the currently-running process keeps using the already-mapped
old copy regardless). Testing requires a fresh process, i.e. logout
and back in -- do not restart/kill Hyprland live as part of this
script.

The build is not bit-reproducible (no reproducible-build flags in
aquamarine's CMakeLists.txt -- rerunning src/aquamarine/build.sh
produces a different hash each time from identical source). So
`check`/`install` verify the *candidate on disk right now* is a
real ELF shared library with the expected soname and that the patch
source is actually present in the tracked patch file, and `install`
records whatever hash it actually copied for later restore
verification -- rather than comparing against one hard-coded hash
that would spuriously fail on a legitimate rebuild.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'src/aquamarine/src/build/libaquamarine.so.0.15.1'
PATCHES = [
    ROOT / 'src/aquamarine/0001-connect-clear-stale-pageflip.patch',
    ROOT / 'src/aquamarine/0002-fix-destructor-teardown-order.patch',
]
TARGET = Path('/usr/lib/libaquamarine.so.0.15.1')
BACKUP = Path('/var/tmp/j416s-aquamarine-pageflip-before')
PRIOR_BACKUP = Path('/var/tmp/aquamarine-trace-backup/libaquamarine.so.0.15.1.orig')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def preflight():
    if b'apple,j416s' not in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0'):
        raise RuntimeError('Wrong machine')
    if not TARGET.is_file():
        raise RuntimeError(f'Missing original: {TARGET}')


def check_candidate():
    if not CANDIDATE.is_file():
        raise RuntimeError(f'Candidate missing, run src/aquamarine/build.sh first: {CANDIDATE}')
    for patch in PATCHES:
        if not patch.is_file():
            raise RuntimeError(f'Patch file missing: {patch}')
    out = subprocess.run(['file', str(CANDIDATE)], check=True, capture_output=True, text=True).stdout
    if 'ELF' not in out or 'shared object' not in out:
        raise RuntimeError(f'Candidate is not a shared object: {out.strip()}')
    out = subprocess.run(['objdump', '-p', str(CANDIDATE)], check=True, capture_output=True, text=True).stdout
    if 'SONAME' not in out or 'libaquamarine.so.14' not in out:
        raise RuntimeError('Candidate has wrong/missing SONAME')


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_text())
    expected = manifest['sha256']
    if digest(BACKUP / 'libaquamarine.so.0.15.1') != expected:
        raise RuntimeError('Backup checksum mismatch')
    # This file is a shared library that may be actively memory-mapped by a
    # running process (Hyprland). Overwriting it in place (shutil.copy2 onto
    # an existing path) corrupts that process's mapped pages out from under
    # it -- write to a temp file in the same directory and rename() instead,
    # exactly like install() already does, so the swap is atomic and a
    # running process keeps its old, still-valid mapping regardless.
    tmp = TARGET.with_suffix('.tmp')
    shutil.copy2(BACKUP / 'libaquamarine.so.0.15.1', tmp)
    if digest(tmp) != expected:
        raise RuntimeError('Copy verification failed before rename')
    os.rename(tmp, TARGET)
    run('ldconfig')
    if digest(TARGET) != expected:
        raise RuntimeError(f'Restored checksum mismatch: {TARGET}')
    os.sync()
    print('Restored pre-fix libaquamarine.so.0.15.1 (atomic swap). No logout/restart performed.', flush=True)


def install():
    check_candidate()

    if BACKUP.exists():
        # A verified backup from an earlier install this session already
        # captures a legitimate prior state -- reuse it rather than refusing
        # outright (restore() only ever needs one valid fallback, not the
        # single earliest one) or silently clobbering it.
        manifest_path = BACKUP / 'manifest.json'
        if not manifest_path.is_file():
            raise RuntimeError(f'Backup exists but has no manifest, refusing to touch it: {BACKUP}')
        expected_backup = json.loads(manifest_path.read_text())['sha256']
        if digest(BACKUP / 'libaquamarine.so.0.15.1') != expected_backup:
            raise RuntimeError(f'Existing backup failed verification, refusing to touch it: {BACKUP}')
        print('Reusing existing verified backup:', BACKUP, flush=True)
    else:
        BACKUP.mkdir(mode=0o700)
        expected_backup = digest(TARGET)
        shutil.copy2(TARGET, BACKUP / 'libaquamarine.so.0.15.1')
        if digest(BACKUP / 'libaquamarine.so.0.15.1') != expected_backup:
            raise RuntimeError('Backup verification failed')
        if PRIOR_BACKUP.is_file() and digest(PRIOR_BACKUP) != expected_backup:
            print('NOTE: prior trace backup does not match current installed file '
                  '(expected if aquamarine has been updated since); proceeding on the fresh backup.',
                  flush=True)
        (BACKUP / 'manifest.json').write_text(json.dumps({'sha256': expected_backup}, indent=2) + '\n')
        os.sync()
        print('Verified backup:', BACKUP, flush=True)
    try:
        preflight()
        candidate_hash = digest(CANDIDATE)
        # Atomic replace: write to a temp file in the same directory, then rename.
        tmp = TARGET.with_suffix('.tmp')
        shutil.copy2(CANDIDATE, tmp)
        if digest(tmp) != candidate_hash:
            raise RuntimeError('Copy verification failed before rename')
        os.rename(tmp, TARGET)
        run('ldconfig')
        if digest(TARGET) != candidate_hash:
            raise RuntimeError(f'Installed checksum mismatch: {TARGET}')
        os.sync()
    except BaseException:
        print('Installation failed; restoring verified original.', flush=True)
        restore()
        raise
    print(f'Installed (hash {candidate_hash}). Log out and back in to test -- '
          'do not restart Hyprland live.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'restore'])
    args = parser.parse_args()
    preflight()
    if args.action == 'check':
        check_candidate()
        print('Correct machine; candidate is a valid libaquamarine.so.14 build; ready to install.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.action == 'install':
        install()
    else:
        restore()


if __name__ == '__main__':
    main()
