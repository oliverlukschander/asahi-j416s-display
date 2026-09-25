#!/usr/bin/env python3
"""Stage, or restore, the Hyprland render-session-active-race fix.

An earlier version of this fix (renderMonitor()/onSyncFired()/
onPresented()) turned out to be dead code on this system --
`hyprctl getoption render:new_render_scheduling` returns false, so
onSyncFired()/onPresented() never run at all here, and renderMonitor()
was already covered by canRender() at its only reachable call site.
Reverted; not shipped. Four isolated-session live tests afterward
(a real login on a spare VT, each a clean run with an explicit VT
switch away and back) all came back with zero "Session inactive"
occurrences -- confirming a plain VT switch alone doesn't reproduce
this. Every real incident involved a monitor hotplug landing at the
same time as a session transition, not the transition alone.

Root cause, found by checking every m_state.commit()/m_state.test()/
m_output->commit() call site in Monitor.cpp and Renderer.cpp (13 sites
across 6 functions): CMonitor::onConnect() (runs on every monitor
hotplug -- exactly 0147's resume-triggered reconnect, and exactly what
a fresh greeter session's startup does when it detects the external
monitor) and CMonitor::applyMonitorRule() (called from onConnect())
both commit/test monitor state directly with zero session-active
checks anywhere in either function. Every commit/test path in this
file relies on its *caller* remembering to check canRender() first --
several plainly don't, and that's inherently fragile: a single missed
call site (existing or future) is enough to reach a real hardware
commit attempt during exactly the window commitState()'s own guard and
Aquamarine's restoreAfterVT() comment already treat as unsafe.

Fix: gate CMonitorState::commit() and ::test() themselves -- the one
place every one of these call sites ultimately funnels through -- with
the identical two-flag check canRender() already uses. Closes the gap
categorically rather than patching call sites one at a time. Full
detail in notes/2026-09-25-hyprland-render-session-active-race.md.

This is the main system Hyprland binary (/usr/bin/Hyprland), not a
kernel module or a library -- no depmod, initramfs, or reboot. Same
discipline as every other live-system change this session: verified
backup before install, verified checksum after, atomic temp-file-then-
rename swap (a currently-running Hyprland process keeps its own
already-loaded image regardless of what's on disk -- this only affects
the next fresh launch, i.e. the next logout/login).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'src/hyprland/src/build/Hyprland'
PATCH = ROOT / 'src/hyprland/0001-fix-session-active-race.patch'
TARGET = Path('/usr/bin/Hyprland')
BACKUP = Path('/var/tmp/j416s-hyprland-session-race-before')


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
        raise RuntimeError(f'Candidate missing, run src/hyprland/build.sh first: {CANDIDATE}')
    if not PATCH.is_file():
        raise RuntimeError(f'Patch file missing: {PATCH}')
    out = subprocess.run(['file', str(CANDIDATE)], check=True, capture_output=True, text=True).stdout
    # PIE binaries get reported by file(1) as either "pie executable" or
    # "shared object" depending on subtle ELF header details -- both are
    # legitimate; what actually matters is that it's a real dynamically
    # linked aarch64 ELF, which the CMake build log already confirmed by
    # explicitly linking a CXX executable named Hyprland.
    if 'ELF' not in out or 'aarch64' not in out or not os.access(CANDIDATE, os.X_OK):
        raise RuntimeError(f'Candidate is not a valid executable: {out.strip()}')


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_text())
    expected = manifest['sha256']
    if digest(BACKUP / 'Hyprland') != expected:
        raise RuntimeError('Backup checksum mismatch')
    tmp = TARGET.with_suffix('.tmp')
    shutil.copy2(BACKUP / 'Hyprland', tmp)
    if digest(tmp) != expected:
        raise RuntimeError('Copy verification failed before rename')
    os.rename(tmp, TARGET)
    os.chmod(TARGET, 0o755)
    if digest(TARGET) != expected:
        raise RuntimeError(f'Restored checksum mismatch: {TARGET}')
    os.sync()
    print('Restored pre-fix Hyprland binary (atomic swap). No logout/restart performed.', flush=True)


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
        if digest(BACKUP / 'Hyprland') != expected_backup:
            raise RuntimeError(f'Existing backup failed verification, refusing to touch it: {BACKUP}')
        print('Reusing existing verified backup:', BACKUP, flush=True)
    else:
        BACKUP.mkdir(mode=0o700)
        expected_backup = digest(TARGET)
        shutil.copy2(TARGET, BACKUP / 'Hyprland')
        if digest(BACKUP / 'Hyprland') != expected_backup:
            raise RuntimeError('Backup verification failed')
        (BACKUP / 'manifest.json').write_text(json.dumps({'sha256': expected_backup}, indent=2) + '\n')
        os.sync()
        print('Verified backup:', BACKUP, flush=True)
    try:
        preflight()
        candidate_hash = digest(CANDIDATE)
        tmp = TARGET.with_suffix('.tmp')
        shutil.copy2(CANDIDATE, tmp)
        if digest(tmp) != candidate_hash:
            raise RuntimeError('Copy verification failed before rename')
        os.rename(tmp, TARGET)
        os.chmod(TARGET, 0o755)
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
        print('Correct machine; candidate is a valid Hyprland executable; ready to install.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    if args.action == 'install':
        install()
    else:
        restore()


if __name__ == '__main__':
    main()
