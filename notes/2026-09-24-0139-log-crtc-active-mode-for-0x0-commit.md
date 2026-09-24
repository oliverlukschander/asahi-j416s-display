# 0139: log every apple_plane_atomic_check() exit point (updated after native macOS comparison)

## Superseded framing

This candidate started as a narrow diagnostic (log `crtc_state->active`
in `dcp_hotplug()`/`dcp_crtc_atomic_modeset()`'s 0x0 bail-out) based on a
research pass that concluded no atomic commit likely ever reaches the
kernel for the tunnel connector at all. **That premise turned out to be
wrong, overturned by direct evidence gathered after that research pass
completed.** This note documents what actually happened and what 0139
now contains.

## What overturned it: native macOS comparison + a live Linux replug test

Oliver ran the macOS capture script (from this session) natively on both
his M4 MacBook Pro and, critically, the actual M2 Pro/T602x machine
booted into macOS with the identical hub+monitor setup
(`captures/macos-2026-09-24/{m2,m4}-logs/`). The M2 capture shows the
entire path from physical tunnel activation to a fully committed,
DCP-acknowledged real video mode taking **~575ms**, automatically:
`hotPlug_notify` (13:08:10.258) -> WindowServer already has the full
EDID/mode list by 13:08:10.284 -> `set_digital_out_mode: Modeset
requested` at 13:08:10.300 (42ms after the hotplug notification) ->
`plug gated: modeset received.` at 13:08:10.503. Confirmed on the M4
(different chip) too, ~10ms end to end. This is a universal WindowServer
behavior, not firmware-specific timing -- see the ACTION-LOG entry for
the full timeline and citations.

Grepping every one of our own Linux captures (0136-0138) for the
equivalent event (`set_digital_out_mode(`) found it never fires once for
the tunnel connector -- consistent with either "no commit ever reaches
the kernel" (the prior research's working assumption) or "a commit
reaches the kernel and is silently rejected" (indistinguishable from
kernel logs alone, as that research pass itself flagged).

**A live, zero-reboot test settled it.** With Oliver's help, did one more
physical replug on the currently-running (0138-confirmed-working) kernel,
capturing `hyprctl rollinglog` and `dmesg` immediately after
(`captures/2026-09-24-live-replug-diagnostic/`). Hyprland's own log
(`hyprland-rollinglog.txt`) shows Aquamarine (Hyprland's DRM backend)
**actively trying**: it allocates a real GBM buffer and attempts a real
`ATOMIC_ALLOW_MODESET | ATOMIC_TEST_ONLY` commit for a cascade of
fallback resolutions -- 800x600, 720x576, 720x480, 640x480 -- and **every
single one fails with "Invalid argument" (EINVAL)**. `dmesg.log` from the
exact same window has zero atomic-related lines at all (confirmed
`drm.debug` is already at its maximum bitmask, `1023`, but this driver's
checks don't route through the dynamic-debug-gated `DRM_DEBUG_ATOMIC`
macros, and dynamic_debug has no matching callsites for
`drm_atomic`/`drm_mode_atomic` in this kernel build).

**So a commit does reach the kernel, repeatedly, and gets silently
rejected.** The prior research's "likely no commit lands" conclusion was
reasonable given what it could see, but is now confirmed wrong by direct
evidence it didn't have access to.

## Where the rejection likely is, and the new diagnostic

Read `apple_plane_atomic_check()` (`drivers/gpu/drm/apple/plane.c`) in
full -- the plane-level atomic-check hook (a different function from
`dcp_crtc_atomic_check()`, which the prior research correctly cleared:
re-verified directly, it only ever returns non-zero on `dcp->crashed`,
confirmed absent from every capture including this new one). Found:
- A 32x32 minimum-plane-size guard that already logs
  (`dev_err_once(..., "Plane operation would have crashed DCP!
  Rejected!"...)`) -- but this string appears **zero times** in any
  capture including the fresh one, so it's confirmed not the cause.
- Two genuinely **silent** `-EINVAL` returns: an unaligned-pitch check
  (`fb->pitches[i] & 63`) and a mismatched-multi-plane-object check.
  Neither logs anything, matching the observed symptom exactly.
- A generic `drm_atomic_helper_check_plane_state()` call whose own
  failure is also not logged by this driver.

Added `dev_info()` at **every** exit point of `apple_plane_atomic_check()`
-- the `crtc_state` error path, the generic check's failure (with mode
and fb dimensions), the not-visible early return, both previously-silent
`-EINVAL`s (now with the actual pitch/plane values that triggered them),
and an explicit "OK" log on success. No control-flow change anywhere. If
even the "OK" line never appears for the tunnel connector's plane, that
would point further up (generic DRM core's own `drm_atomic_helper_check`,
outside this driver -- a different, follow-up question). If a specific
`-EINVAL` line does appear, it tells us exactly which check and why,
directly.

## The change

`drivers/gpu/drm/apple/plane.c`: instrumented, no behavior change.
Combined into the same `appledrm.ko` as the original crtc-mode diagnostic
(`drivers/gpu/drm/apple/iomfb.c`, unchanged from the first version of
this candidate). Same module set as 0138 otherwise.

## Build verification

`make` in `src/appledrm/` (vermagic `7.1.12-2.5-1-ARCH`): only `plane.o`
recompiled this round, clean, no new warnings. `python3
scripts/manage-0139.py check` (no sudo) passes.

## Test plan

1. Ask Oliver to run `sudo -n python3 scripts/manage-0139.py check` then
   `sudo -n python3 scripts/manage-0139.py install`.
2. Ask Oliver to reboot with the monitor unplugged, then plug it in once
   booted.
3. Pull `dmesg --ctime`, save as `captures/2026-09-24-0139-boot-kernel.log`.
   Look for `apple_plane_atomic_check:` lines -- specifically whether the
   final "OK" line ever appears, or which specific rejection fires (and
   with what pitch/dimension values) for the tunnel connector's plane.
   As always, the only result that actually counts is whether there's a
   picture -- only Oliver's own visual confirmation counts as success.
