# 0139: log crtc active/mode state for the stuck 0x0 tunnel commit (diagnostic only)

## What 0138 confirmed on hardware

0138's reconnect fix is definitively proven: `"DP IN tunnel routing:
tunnel down"` (never seen once before, in any capture this whole
project) fired on unplug, and a genuine second connect cycle
(`dcp_dptx_connect`/`request_display: call #2`/"display routed to
Thunderbolt DP tunnel") fired on replug and reached `DPRX_DONE=1` again.
See `captures/2026-09-24-0138-boot-and-replug-kernel.log` and the
ACTION-LOG entry for full detail.

Still no picture. The ~29s autonomous teardown recurred, on **both**
connects this boot, with exact, reproducible timing: `DPRX_DONE=1` at
12:26:32 -> teardown at 12:27:01 (29s); `DPRX_DONE=1` at 12:27:32 ->
teardown at 12:28:01 (29s again). This rules out randomness and confirms
a fixed firmware-internal deadline, consistent with the prior research's
conclusion that this specific figure isn't visible or fixable from this
source tree.

## The lead investigated this candidate, and why it's NOT being turned into a fix

A third deep-research pass (5 angles + synthesis + 3 adversarial
verifiers, all `refuted: false`) investigated the one real, previously
un-applied lead: `drivers/gpu/drm/apple/iomfb.c`'s `dcp_hotplug()` has a
retrain-nudge (`dcp_retrain_active_crtc()`) explicitly excluded for USB4
outputs (`!dcp_is_usb4_output(dcp)`).

**Git archaeology (confirmed, not guessed):** the retrain-nudge itself
was introduced unconditionally by commit `5c29016e3` ("recover Type-C
displays across link interruptions"). The USB4 exclusion was bolted on
three weeks later by commit `8fb643a0e` ("do not mark USB4 link BAD on
fake scanout"), whose own message reads: *"Hyprland saw USB-3 1920x1080
but stayed at 0x0@60. dcp_hotplug set LINK_STATUS_BAD because valid_mode
was 0, so userspace never committed the mode. Skip that on USB4."* That
commit was silencing a **debug shim that injected a fake 1920x1080 mode**
(`e75d67fe9`, from the same day, written before AUX/DPRX ever worked on
this fork). The big tunnel-routing port (`0dc9f5087`, which everything
this session's fixes build on) deleted that fake-scanout scaffolding
entirely but never touched `iomfb.c` or reconsidered this exclusion.

**So the exclusion's history is an unrevisited leftover, not a
documented hazard with the retrain mechanism itself** -- but two
independent problems make removing it unlikely to help regardless,
both traced through actual DRM atomic-commit semantics, not guessed:

1. **`dcp_retrain_active_crtc()` never touches the mode.**
   `drm_atomic_helper_reset_crtc()` (generic DRM core) only sets
   `crtc_state->connectors_changed = true` and re-commits -- it never
   resets `crtc_state->mode`. Traced the full chain:
   `connectors_changed=true` forces `drm_atomic_crtc_needs_modeset()`
   true, which re-invokes `apple_crtc_atomic_enable()` even though
   `active` didn't change, which unconditionally calls
   `dcp_crtc_atomic_modeset()` on `crtc_state->active` -- but that
   function only replays whatever mode is **already stored**. If that
   stored mode is the same 0x0 blob Hyprland is currently showing, the
   replay lands right back on `iomfb.c`'s own silent 0x0 bail-out
   (confirmed: `if (crtc_state->mode.hdisplay == 0 && ... vdisplay == 0)
   return 0;`, no log, `dcp->valid_mode` never becomes true). Removing
   the gate would very likely just replay the same nothing.
2. **The gate wraps `DRM_MODE_LINK_STATUS_BAD` too, not just the
   retrain call** -- confirmed by reading the diff of the commit that
   added it. Narrowing the gate to only skip the retrain (keeping
   `LINK_STATUS_BAD`) would reintroduce exactly the regression that
   commit's own message documents happening on this same connector type.

**Confirmed from the log (grep over the whole 1872-line capture):**
`set_digital_out_mode(` -- the only string `iomfb_modeset()` ever prints,
and the only place `dcp->valid_mode` is ever set true -- appears exactly
twice, both for `389c00000.dcp` (the internal panel). It never appears
once for `289c00000.dcp` (the tunnel), in either connect cycle. Whatever
decides this connector gets 0x0 has left no trace in the kernel log
either way -- consistent with either "no atomic commit ever lands for
this connector" or "one lands but is silently swallowed by the existing
0x0 bail-out," which are indistinguishable from the log as it stands
today.

Also corrected, for the record: my own framing of the teardown apcall
sequence as literally "WILL_CHANGE_LINK_CONFIG -> SET_ACTIVE_LANE_COUNT(0)
-> SET_LINK_RATE(0x0) -> DID_CHANGE_LINK_CONFIG" doesn't match the log's
actual printed strings -- `WILL_CHANGE_LINK_CONFIG` and
`DID_CHANGE_LINK_CONFIG` never appear as literal text anywhere in the
capture (the log only prints bare `APCALL 5`/`APCALL 12`/`APCALL 9`/
`APCALL 6` numbers plus the named `SET_LINK_RATE 0x0`). The apcall-number
mapping (from `dptxep.h`'s enum) is still the correct interpretation, but
the research caught that I'd stated it as if those exact strings were
logged, which they aren't.

## The change (diagnostic only, no fix)

`drivers/gpu/drm/apple/iomfb.c`, two additive `dev_info()` lines, no
control-flow change:

- In `dcp_crtc_atomic_modeset()`'s existing 0x0 bail-out: log
  `crtc_state->active` and `dcp_is_usb4_output(dcp)` right before the
  early return. This fires synchronously with ANY atomic commit Hyprland
  ever issues for this CRTC that reaches this function at all.
- In `dcp_hotplug()`: log the connector's bound crtc pointer,
  `crtc->state->active`, and the crtc's currently-stored mode dimensions,
  unconditionally (not gated on USB4), right after the function's
  existing entry log line.

Same module set as 0138 otherwise (atc/mux/thunderbolt/thunderbolt_apple
unchanged, only `appledrm.ko` rebuilt: `iomfb.o` recompiled).

## Build verification

`make` in `src/appledrm/` (vermagic `7.1.12-2.5-1-ARCH`): only `iomfb.o`
recompiled, clean relink, no new warnings. `python3 scripts/manage-0139.py
check` (no sudo) passes cleanly.

## What this should tell us on the next capture

If, after a fresh boot+replug, the new "0x0 commit for crtc active=%d
(usb4=%d)" line **never appears** for `289c00000.dcp` even after
manually forcing a mode via `hyprctl keyword monitor ...`, that
confirms Hyprland genuinely never submits an atomic commit for this
connector at all -- a userspace/wlroots-side problem, outside anything
fixable in this kernel driver, and the next step would be investigating
Hyprland/wlroots's own DRM backend rather than this tree. If it **does**
fire, with `active=1`, that proves a real commit is landing with a
degenerate mode, and the question becomes why Hyprland (or wlroots)
picked 0x0 in the first place -- still likely a userspace question, but
a more specific one. Either outcome is strictly more useful than
guessing at a kernel-side fix on the current evidence.

## Test plan

1. Ask Oliver to run `sudo -n python3 scripts/manage-0139.py check` then
   `sudo -n python3 scripts/manage-0139.py install`.
2. Ask Oliver to reboot with the monitor unplugged, then plug it in once
   booted (matching 0138's own successful test sequence).
3. Pull `dmesg --ctime`, save as `captures/2026-09-24-0139-boot-kernel.log`.
   Check for the new "0x0 commit for crtc active=%d (usb4=%d)" and
   "dcp_hotplug: crtc=... active=... mode=..." lines for `289c00000.dcp`,
   both right after connect and (if convenient) after a manual
   `hyprctl keyword monitor "USB-3,2560x1440@59.95,1728x0,1"` attempt
   like the one tried earlier this session. As always, the only result
   that actually counts is whether there's a picture -- only Oliver's own
   visual confirmation counts as success.
