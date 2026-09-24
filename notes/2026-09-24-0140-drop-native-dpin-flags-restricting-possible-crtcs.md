# 0140: drop usb4_protocol_probe/usb4_native_dpin -- they were excluding dcpext0 from possible_crtcs

## What 0139 found

0139's plane-level instrumentation, combined with a live replug test
before it was even installed, nailed down the actual failure precisely:

- Hyprland's own rolling log (from the live pre-0139 replug test,
  `captures/2026-09-24-live-replug-diagnostic/hyprland-rollinglog.txt`)
  showed Aquamarine (its DRM backend) **actively** cascading through
  fallback resolutions (800x600, 720x576, 720x480, 640x480), allocating a
  real GBM buffer and attempting a real `ATOMIC_ALLOW_MODESET |
  ATOMIC_TEST_ONLY` commit for each -- every single one rejected with
  EINVAL.
- With 0139 installed and a fresh boot+replug
  (`captures/2026-09-24-0139-boot-kernel.log`, not yet committed as of
  this note -- see the test log referenced in ACTION-LOG),
  `apple_plane_atomic_check()`'s new instrumentation fired **896 times,
  every single one for `plane=35 crtc=50` (the internal eDP panel) --
  never once for the tunnel connector's own plane**, across the whole
  boot including the plug-in event.
- `dcp_hotplug()`'s new diagnostic showed, for both hotplug events on the
  tunnel DCP instance (`289c00000.dcp`): `crtc=0000000000000000
  active=-1 mode=-1x-1` -- the connector's own DRM state has **no CRTC
  attached at all** when hotplug fires.

Together: Aquamarine's atomic commits for this connector are being
rejected *before* they ever reach per-plane validation -- i.e. at the
generic DRM core's encoder/CRTC pairing check, which runs before
`drm_atomic_helper_check_planes()`.

## Root cause (read directly, not inferred)

`apple_probe_typec_ports()` (`drivers/gpu/drm/apple/apple_drv.c:431-512`)
computes each Type-C port connector's encoder's `possible_crtcs` mask
once, at driver probe time:

```c
for (i = 0; i < num_dcp; i++) {
    struct apple_dcp *candidate = platform_get_drvdata(dcp[i]);

    /*
     * Userspace caches possible_crtcs before the hub is attached.
     * The native test owns dcpext1; advertise only that CRTC
     * from registration, not a wider mask narrowed at hotplug.
     */
    if (dcp_usb4_native_route(idx) && candidate->index != 2)
        continue;
    if (dcp_typec_port_has_candidate(idx, dcp[i]))
        mask |= crtc_mask[i];
}
```

`dcp_usb4_native_route()` (`dcp.c:174-177`):
```c
bool dcp_usb4_native_route(unsigned int typec_index)
{
    return usb4_native_dpin && usb4_protocol_probe && typec_index <= 2;
}
```

Both `usb4_native_dpin` and `usb4_protocol_probe` have been set to `1` in
every candidate's module options since candidate 0129 (`options appledrm
usb4_protocol_probe=1 usb4_native_dpin=1 ...`) -- leftover from the
pre-0127 "native DPIN0" single-purpose proof-of-concept, carried forward
unexamined ever since (the same pattern as 0136's stale config files:
leftover test-environment state from a discontinued experiment silently
sabotaging the current, correct approach).

With both flags set, `dcp_usb4_native_route(idx)` returns true for our
port, so the loop **skips every candidate DCP whose `index != 2`** --
i.e. it explicitly excludes dcpext0 (whatever its index is; dcpext1 is
index 2) from the connector's `possible_crtcs` mask, on the hard-coded
assumption (accurate for the old single-purpose test, wrong for
everything since) that only dcpext1 will ever drive this port.

But candidate 0135 onward has been running with
`usb4_route_prefer_fixed_diag=1`, which forces `apple_dcp_tb_dp_tunnel()`'s
software route-scoring to select **dcpext0** for this exact port. DCP
firmware trains the link successfully on dcpext0 (confirmed repeatedly:
DPRX_DONE=1, 4 lanes, no timeout) -- but the DRM-level `possible_crtcs`
mask computed at probe time never included dcpext0's CRTC bit, so every
atomic commit that tries to attach this connector to dcpext0's CRTC
(exactly what `dcp_typec_route_activate()` registered as this route's
CRTC) fails the generic DRM core's encoder/CRTC compatibility check --
before ever reaching `apple_plane_atomic_check()` or any other
driver-specific validation. This is a direct, mechanistic explanation for
every observed symptom: every mode Aquamarine tries fails identically
(the mode/plane size is irrelevant to a pairing-level rejection); the
plane check never runs for this connector; the connector's own crtc
pointer reads NULL at hotplug time (before any commit has managed to
attach one).

## Why disabling both flags is safe

Grepped every call site of `usb4_native_dpin`/`usb4_protocol_probe`
exhaustively (`drivers/gpu/drm/apple/{dcp,iomfb,iomfb_template,dcp-internal.h}`).
Besides the `possible_crtcs` restriction above and one early-return in
the reconnect-retry work (`dcp_typec_reconnect_work()`, only affects
retry logging after a failed connect, not the main path), **every other
call site is a bare `dev_info`/`dev_info_once()` diagnostic print with no
other effect** (`iomfb.c:596`, and seven call sites in
`iomfb_template.c` covering swap-completion/flush logging, plus
`right_frame_snapshot()` which is itself fully gated off and only takes
a diagnostic crossbar register snapshot). None of this is behavior the
current working path depends on.

## The change

Config-only, no kernel rebuild: dropped `usb4_protocol_probe=1` and
`usb4_native_dpin=1` from the module options. Kept
`usb4_route_prefer_fixed_diag=1` unchanged (still forcing the tunnel onto
dcpext0, the only pipeline that's ever reached a real link). Same
`appledrm.ko`/`thunderbolt.ko` as 0139 (0139's plane/hotplug diagnostics
stay installed and active -- useful to keep for confirmation, and to
catch anything else if this doesn't fully resolve it).

## Build verification

No rebuild needed. `python3 scripts/manage-0140.py check` (no sudo)
passes: correct kernel/machine, 0136 cleanup in place, candidate hashes
match (identical to 0139's already-built modules).

## Known uncertainty

This fixes the specific, confirmed mechanism blocking every atomic
commit for the tunnel connector. It does not by itself guarantee the
~29s autonomous teardown (still open, very likely firmware-internal)
won't recur -- but if this fix is correct, we should finally see
`apple_plane_atomic_check()` fire for the tunnel connector's own plane,
print "OK", and (the only thing that actually matters) put a real
picture on the monitor, at least until any later autonomous teardown.

## Test plan

1. Ask Oliver to run `sudo -n python3 scripts/manage-0140.py check` then
   `sudo -n python3 scripts/manage-0140.py install`.
2. Ask Oliver to reboot with the monitor connected as usual (or unplugged
   then plugged in, either should now work).
3. Pull `dmesg --ctime`, save as `captures/2026-09-24-0140-boot-kernel.log`.
   Check for `apple_plane_atomic_check:` lines mentioning the tunnel
   connector's own crtc/plane (not crtc=50), and whether they say "OK".
   The only result that actually counts: is there a picture on the
   external display. Only Oliver's own visual confirmation counts as
   success.
