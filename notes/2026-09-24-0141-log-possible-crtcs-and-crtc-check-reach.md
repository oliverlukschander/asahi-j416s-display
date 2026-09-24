# 0141: 0140 did NOT fix it -- more diagnostics before guessing again

## Being honest about 0140

0140 (drop `usb4_protocol_probe`/`usb4_native_dpin`, believed to be
excluding dcpext0's CRTC bit from the right port's `possible_crtcs`) was
installed and tested on real hardware. **It did not fix the problem.**
Oliver rebooted with it installed, connected the monitor, and it stayed
dark, exactly as before.

Direct comparison, both from the same live-replug-diagnostic technique
used before installing 0140:

- Pre-0140 (`captures/2026-09-24-live-replug-diagnostic/`): Aquamarine
  cascades through 800x600 -> 720x576 -> 720x480 -> 640x480, every
  `ATOMIC_ALLOW_MODESET | ATOMIC_TEST_ONLY` commit failing with EINVAL.
- Post-0140 (`captures/2026-09-24-0140-replug-diagnostic/`): **byte-for-byte
  identical** -- same four resolutions in the same order, same failure.
- `captures/2026-09-24-0140-boot-kernel.log`: `apple_plane_atomic_check()`
  (0139's instrumentation, still installed) fired 883 times, every single
  one for the internal panel's `plane=35 crtc=50` -- never once for the
  tunnel connector's plane, exactly as before 0140.

So 0140 had **zero observable effect** on this symptom. Either the
`possible_crtcs` theory itself was wrong, or something else besides the
specific exclusion 0140 removed is also keeping dcpext0's CRTC bit out of
the mask (or out of the eventual connector/CRTC pairing some other way).
Rather than propose another guess, this candidate adds direct
instrumentation to see the actual computed values instead of inferring
them.

## The change (diagnostic only)

Two additions to `drivers/gpu/drm/apple/apple_drv.c` and `dcp.c`, no
control-flow change:

1. `apple_probe_typec_ports()`: logs each candidate DCP's
   `dcp-index`/`native_route`/`has_candidate`/`crtc_mask` contribution,
   and the final computed `possible_crtcs` mask for the port, at probe
   time (very early boot, no replug needed to observe -- available in
   the very first capture after a reboot). This will show directly
   whether `dcp_usb4_native_route()` now reads false as expected, whether
   `dcp_typec_port_has_candidate()` returns true for dcpext0 at all, and
   the exact resulting bitmask (decodable against each DCP's own CRTC
   bit).
2. `dcp_crtc_atomic_check()`: logs every reach of this per-CRTC hook
   (crtc id, mode, active, enable). If this never fires for dcpext0's
   CRTC during a failed commit attempt, that confirms the rejection
   happens even before any driver-level per-CRTC code runs -- i.e.
   squarely in generic DRM core's encoder/CRTC pairing validation. If it
   *does* fire, the rejection must be coming from somewhere else
   entirely (not the pairing, not the already-instrumented plane check),
   which would point the next round of investigation at a completely
   different mechanism.

Same module set as 0140 otherwise (only `appledrm.ko` rebuilt: `apple_drv.o`
and `dcp.o` recompiled).

## Build verification

`make` in `src/appledrm/` (vermagic `7.1.12-2.5-1-ARCH`): clean, no new
warnings. `python3 scripts/manage-0141.py check` (no sudo) passes.

## Test plan

1. Ask Oliver to run `sudo -n python3 scripts/manage-0141.py check` then
   `sudo -n python3 scripts/manage-0141.py install`.
2. Ask Oliver to reboot (no need to unplug first this time -- 0138's
   reconnect fix and 0140's config are both already confirmed/kept in
   place, and this round is purely about reading the new log lines).
3. Pull `dmesg --ctime` immediately after boot, save as
   `captures/2026-09-24-0141-boot-kernel.log`, and check the
   `typec port ... candidate dcp-index=...`/`final possible_crtcs
   mask=...` lines from probe time. If the monitor is connected and
   attempts a commit, also check for `dcp_crtc_atomic_check: crtc=...`
   lines. As always, the only result that actually counts is whether
   there's a picture -- but this round is explicitly about gathering the
   data needed to get the NEXT fix right, not another guess.
