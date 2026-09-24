# 0137: complete linkcfg_completion unconditionally on lane count

## What 0136's install confirmed

0136 (stale `usb4_defer_bringup=1` config cleanup) was installed and
rebooted. The fix worked exactly as predicted:
`captures/2026-09-24-0136-boot-kernel.log`, right port, dcpext0 forced via
`usb4_route_prefer_fixed_diag=1`:

- `apple-display-crossbar f0304c000.mux: Switched dpin0 to dispext0,0
  (t602x atc=0x1 mux=0x0)` -- a real ENABLE, not "disconnected". No
  `crossbar up failed` anywhere in the log. **0136's fix is confirmed: the
  `-22` is gone.**
- `thunderbolt-apple-nhi f01f00000.nhi: 0:5: DP IN DPRX_DONE=1 (ACIO AUX
  completed)` -- reached again, real AUX/DPCD hardware completion.
- `apple-dcp 289c00000.dcp: DPTXPort: APCALL 12 (32 bytes)` with payload
  `04 00 00 00...` -> `set_active_lane_count: unexpected lane count:4
  phy: 0` -> `USB4/DPTX: SET_ACTIVE_LANE_COUNT 4` -- firmware negotiated
  and the driver accepted 4 active lanes. ("unexpected" here is just
  `dptx->lane_count(0) < lane_count(4)`, a harmless first-negotiation
  print, not a rejection -- confirmed by reading the code, `case 4:` is a
  valid branch.)
- Still no picture: `dcp_dptx_connect: timed out waiting for port 0 link
  configuration`, 8s after `request_display`, despite every step above
  succeeding. A retry (`call #2`) then fails at the tunnel-clock request
  itself (`rate=0xa result=-114`, EALREADY) -- a secondary symptom of call
  #1 never having cleanly released, not a new independent bug; expected to
  disappear once call #1 stops timing out.

## Root cause (verified directly against source and the hardware-validated reference)

`dptxport_call_set_active_lane_count()` (`drivers/gpu/drm/apple/dptxep.c`)
only completed `dcp->dptxport[port].linkcfg_completion` -- the exact
completion `dcp_dptx_connect()` (`dcp.c:1501`) blocks on for up to 8s --
via:
```c
if (dcp_is_usb4_output(dcp)) {
    complete(&dptx->usb4_lane_completion);
    if (dcp_usb4_drm_allowed())
        complete(&dptx->linkcfg_completion);
} else
    complete(&dptx->linkcfg_completion);
```
`dcp_is_usb4_output(dcp)` is true for any tunnel (`dcp->active_typec_route
&& route->tunnel`) -- true here. `dcp_usb4_drm_allowed()` returns
`usb4_force_dptx`, a `static bool` with **no `module_param` registration
anywhere in the tree** (confirmed by a full-tree grep) -- permanently
false, unconditionally, forever.

`git log -S"usb4_force_dptx"` traces this to commit `0dc9f50` ("port real
Thunderbolt DP tunnel routing from aurora-silicon/linux#8", 2026-09-24,
the same commit that introduced the whole tunnel mechanism candidates
0127 onward have been testing). Before that commit, `usb4_force_dptx` was
a live, writable knob:
```c
-module_param_cb(usb4_dptx_train, &usb4_dptx_train_ops, &usb4_force_dptx, 0644);
```
for a manual-training sysfs workflow (`notes/2026-09-20-unattended-build.md`
and the git log around that era: "USB4 DPTX train via sysfs after lid
close", "USB4 manual train allows DRM hotplug"). `0dc9f50` replaced that
whole manual workflow with automatic tunnel detection
(`apple_dcp_tb_dp_tunnel()`) and removed ~400 lines of the old scaffolding
-- but left `usb4_force_dptx`/`dcp_usb4_drm_allowed()` behind, still
gating this one call site, with the only thing that ever set it true
deleted. `dcp_dptx_connect()` itself was "collapsed from three
USB4-specific branches ... to the same single connect path used for a
direct alt-mode PHY" in the same commit -- so its `linkcfg_completion`
wait is now genuinely shared, and gating one of its two completion sites
behind a dead flag silently broke every USB4-tunneled connect, on both
ports, since the moment this mechanism was introduced (0127 onward). The
other completion site, `FORCE_HOTPLUG_DETECT` (`dptxep.c:764`,
unconditional), is not sent by firmware for a tunnel in any capture on
file.

Checked the reference directly
(`git show refs/aurora-pr8:drivers/gpu/drm/apple/dptxep.c`): its own
`dptxport_call_set_active_lane_count()` has no such gate at all --
```c
if (lane_count > 0)
    complete(&dptx->linkcfg_completion);
```
unconditional, exactly once, no `usb4_lane_completion` field, no
`dcp_usb4_drm_allowed()` equivalent. Also confirmed `usb4_lane_completion`
has no `wait_for_completion()` anywhere in this tree (only its `complete()`
call and two `init_completion()`s) -- a fully dead completion, orphaned by
the same commit.

## The change

`drivers/gpu/drm/apple/dptxep.c`: replaced the branching completion logic
with the reference's unconditional `complete(&dptx->linkcfg_completion)`
for `lane_count > 0`.
`drivers/gpu/drm/apple/dptxep.h`: removed the now-fully-dead
`usb4_lane_completion` field (and its two `init_completion()` calls in
dptxep.c).
`drivers/gpu/drm/apple/dcp.c` / `dcp-internal.h`: removed the now-fully-dead
`usb4_force_dptx` and `dcp_usb4_drm_allowed()`.

Same module set as 0135/0136 otherwise (atc/mux/thunderbolt_apple/thunderbolt
unchanged, only `appledrm.ko` rebuilt);
`usb4_route_prefer_fixed_diag=1` still armed, 0136's stale-config cleanup
still in place (checked as a precondition by `manage-0137.py`, not redone).

## Build verification

`make` in `src/appledrm/` (vermagic `7.1.12-2.5-1-ARCH`): clean build, no
new warnings (confirmed via `grep -i warning` excluding the known
unrelated pahole-version notice). `python3 scripts/manage-0137.py check`
(no sudo) passes: correct kernel/machine, 0136 cleanup confirmed in place,
no unexpected external display connected, all five candidate hashes
match.

## Known uncertainty

This should let `dcp_dptx_connect()`'s wait succeed on the first attempt
instead of always timing out -- but what DCP does immediately *after*
that (crossbar plane/CRTC wiring for a Type-C-tunneled source, which
0127's own notes already flagged as "wrong" for dcpext0 specifically) is
untested. This fix targets the link-configuration handshake, not
necessarily a full picture. Also unconfirmed: whether the retry path
(`call #2`'s `-114` tunnel-clock failure) still exists as an independent
problem, since we expect call #1 to now succeed and no retry to be
needed -- worth checking the next capture regardless.

## Test plan

1. Ask Oliver to run `sudo -n python3 scripts/manage-0137.py check` then
   `sudo -n python3 scripts/manage-0137.py install`.
2. Ask Oliver to reboot with the hub/monitor connected exactly as before.
3. Pull `dmesg --ctime`, save as
   `captures/2026-09-24-0137-boot-kernel.log`. Check: does
   `dcp_dptx_connect: timed out waiting for port 0 link configuration`
   disappear, does call #2 not fire at all (meaning call #1 succeeded),
   and -- the only result that actually counts -- is there a picture on
   the external display. Only Oliver's own visual confirmation counts as
   success.
