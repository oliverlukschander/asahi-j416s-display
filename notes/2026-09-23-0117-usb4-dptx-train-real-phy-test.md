# 0117: fire the existing usb4_dptx_train real-PHY test

No new kernel module, patch, or install for this candidate -- an
already-built, already-loaded runtime knob is being exercised for the
first time. Read this note first if anything unexpected happens
(eDP stays blank, the machine hangs, or you have to unplug/reboot):
see "Recovery" at the bottom.

## Why

`notes/2026-09-23-ACTION-LOG.md`'s 0116 entries showed
`request_display` now succeeds (the 0116 deadlock fix worked), but the
DisplayPort receiver never trains (`DPRX timeout, keeping DP tunnel`)
and no picture appears. Comparing against an old *working* baseline
capture (`captures/2026-09-21-hdmi-baseline-kernel.log`) found two
different DCP hardware instances logged there: `315c00000.dcp` (the
one every USB4/hub candidate this whole project has ever targeted),
which only ever gets `APCALL 18/10/0` and stalls -- exactly today's
symptom -- and a completely separate instance, `289c00000.dcp`, which
answered the `GET_SUPPORTS_HPD` query with **0** (ours always answers
1) and then received a full real link-training sequence from DCP
(`SET_LINK_RATE 0x1e`, `SET_ACTIVE_LANE_COUNT 4`, and more).

Our own driver already documents why it answers 1, not 0:
`drivers/gpu/drm/apple/dptxep.c`'s `dptxport_call_get_supports_hpd()`
comment says denying HPD support once made `request_display` lead to
`DEVICE_NOT_STARTED` after ~5.5s -- because at the time (candidate
0079, `notes/2026-09-21-0079-no-lpdptxphy.md`), answering 0 correctly
told DCP to expect a real PHY, but no PHY had been instantiated for
this path: candidate 0078 (the one before it) had instantiated the
shared `lpdptxphy` (`phy@39c000000`, the *same physical PHY engine
eDP uses*) for the USB4 path and found doing so blanks eDP, since
there is only one such engine and configuring it for external output
takes it from the internal panel. 0079 reverted that to protect eDP,
and every candidate since (0080-0116) has run with no real PHY at all
for this path -- exactly why DPRX never trains.

## What already exists, unused

`drivers/gpu/drm/apple/dcp.c` already has a complete, self-reverting
test harness for exactly this, built some time before this session
and never fired (`usb4_force_dptx` is explicitly called "the dangerous
physical-PHY training experiment" / "prohibited" in
`notes/2026-09-21-0090-protocol-audit.md`, with an explicit instruction
not to enable it without new justification -- this note is that new
justification, with Oliver's explicit, informed approval given after
being told the known eDP-blanking risk):

- `usb4_dptx_train` -- a runtime-writable (0644) module parameter on
  the already-loaded `appledrm` module. Writing `1`:
  - Sets `usb4_force_dptx = true`, which makes `dcp_dptx_connect()`
    skip the no-PHY "analog DPIN" branch entirely and take the real
    path: `dcp_usb4_enable_lpdptxphy()` (instantiates `phy@39c000000`
    if not already), then `dptxport_validate_connection()` ->
    `dptxport_connect()` -> `dptxport_request_display()` using
    `dcp->dptxport[port].atcphy = usb4_lpdptx_phy` as a real PHY
    reference, then waits (`usb4_lane_completion`, 8s timeout) for
    DCP to report real lanes trained.
  - Calls `dcp_dptx_connect(usb4_armed_dcp, 0)` directly -- confirmed
    right now that `usb4_armed_dcp` is set (this boot already logged
    `USB4 DP IN armed typec0`), so this will act on the actual live
    hub connection, no replug needed.
  - Schedules `usb4_restore_edp_work()` after exactly 10 seconds
    regardless of outcome: sets `usb4_force_dptx = false` and calls
    `phy_set_mode_ext(usb4_lpdptx_phy, PHY_MODE_DP, 0)` to hand the
    PHY engine back to eDP automatically. No manual action needed to
    restore eDP in the success or failure case.
  - Writing `0` at any time immediately cancels and restores early.
  - The parameter's own description literally says: "Write 1 after
    closing the lid to train USB4 DPTX (blanks eDP)" -- this was
    built with exactly this expected side effect in mind.

One known gap not yet addressed: `dptxport_call_get_supports_hpd()`
still always answers 1 regardless of `usb4_force_dptx`, unlike the
`0` a real-PHY-driven connection needs per the baseline comparison
above. This first test intentionally does not patch that -- it's
cheaper to first see what happens with the existing, unmodified
harness (GET_SUPPORTS_HPD was already answered once, automatically,
before this write, at the initial hotplug/ACTIVATE round logged at
19:41:17; a forced reconnect may not re-ask it at all, in which case
this gap may not matter for this specific test). If this test shows
DCP still balking specifically over the stale HPD answer, that
mismatch becomes the next concrete, well-motivated code fix.

## The test

```
sudo -n sh -c 'echo 1 > /sys/module/appledrm/parameters/usb4_dptx_train'
```

Then, within 10 seconds, capture kernel log and DRM state, and get
Oliver's direct visual read: does the external monitor show anything
different (even briefly) while eDP is blanked, and does eDP correctly
come back after ~10s on its own.

## Recovery (read this if anything unexpected happens)

- **eDP does not come back after ~10s on its own**: write `0` to the
  same parameter to force the restore immediately:
  `sudo -n sh -c 'echo 0 > /sys/module/appledrm/parameters/usb4_dptx_train'`.
  This runs the exact same `phy_set_mode_ext(usb4_lpdptx_phy,
  PHY_MODE_DP, 0)` restore call as the automatic 10s path.
- **That doesn't bring eDP back either, or the machine seems otherwise
  wedged**: unplug the hub, then `systemctl reboot`. The next boot
  loads the same 0116 modules/config already verified working (this
  test writes a runtime parameter only -- it does not change
  `/etc/modprobe.d/j416s-0116-dpin0-mode-guess.conf`,
  `/boot/initramfs-linux-aurora.img`, or any installed `.ko`, so a
  plain reboot returns to exactly the state verified in the "0116
  boot verified" ACTION-LOG entry above, with no candidate-management
  script action needed).
- **If a reboot happens on its own** (crash, hang, forced power-off):
  same as above -- the next boot returns to the already-verified 0116
  state on its own; nothing further needs to be run or reverted first.
  `sudo -n python3 scripts/manage-0116.py check` after any such reboot
  confirms the installed candidate is still 0116 and matches its
  recorded hashes.
- This test does not touch `/etc/modprobe.d/`, the initramfs, or any
  installed module file -- only a live, in-memory module parameter and
  the PHY hardware state it drives. There is nothing to "undo" in the
  installed candidate regardless of how this test ends.

## Safety scope

No new register address, APCALL, or AFK method beyond what
`usb4_dptx_train`'s pre-existing, previously-reviewed implementation
already does. The only thing new here is actually writing `1` to it,
which requires -- and now has -- Oliver's explicit, informed consent
given the specific eDP-blanking risk already documented from 0078.
