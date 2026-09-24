# Action log

Write the next hardware action here and commit it before running it.
After a crash, this file is the record of what was in flight.

An action is hardware if it loads a module, writes a module parameter,
ioremaps, writes MMIO, reboots, or runs `load-appledrm.sh`.

Full history (candidates 0090-0125, every install/disarm/result entry, every
exact command and hash) lives in
`notes/ACTION-LOG-ARCHIVE-2026-09-21-to-0125.md`, with a condensed
phase-by-phase summary in that file's own prior git history (this file's
content as of commit before this trim). Per-candidate reasoning lives in
`notes/2026-*.md`. This file only carries what's needed to pick up work
right now: safety rules, current state, and the last few actions.

## Hardware reference

M2 Pro (j416s/T602X). Left-back USB-C: NHI `0x701f00000`, ACIO `0x701ac0000`,
crossbar `0x70304c000`, dcpext1 `0x315c00000` (typec0). Right USB-C: NHI
`0xf01f00000`, ACIO `0xf01ac0000`, crossbar `0xf0304c000` (typec2, also
routes through dcpext1 `0x315c00000` at times, or dcpext0 `0x289c00000` for
direct HDMI/adapter routes — confirm the live route from dmesg every time,
never assume). Panel/eDP DCP: `0x389c00000`. DPIN0 (per-port ACIO block):
`{ACIO}+0x50000..+0x53fff`, HPD at `+0`, CONTROL at `+0xc`, ACK at `+0x10`.
Chain under test: OWC Thunderbolt 5 hub → Synaptics VMM7100 USB-C→HDMI →
BenQ 2560×1440. Direct HDMI and direct USB-C-adapter connections to the same
monitor both work; only the hub-tunneled (USB4) path is broken.

## Standing safety rules (never re-test these without new evidence)

- **Never `insmod src/dispclk/apple-dispclk.ko` with `apply=1`, and never
  write `appledrm.usb4_dispclk`.** Caused an instant, silent hard reset
  (2026-09-21 21:36) by copying the live panel clock block onto dcpext1.
  Read-only variants of that module (`read_ext`/`read_ext2`/`read_panel2`/
  `read_ext0`) are safe; the copy/write path is not.
- **Never write `+0x074` in any disp-clock block** (`write_074`) — the one
  attempt left no completion log across a reset; presumed unsafe, permanently
  disabled in the module.
- **`dpin_aux=1` (drivers/thunderbolt/apple.c) does not stick.** Confirmed
  twice, ~2 days apart, under very different driver states: 2026-09-21
  candidates 0054-0056 (`notes/2026-09-21-acio-rc-dpin-analog.md`) and again
  in 2026-09-23 candidate 0125 (`notes/2026-09-23-0125-dpin-aux-retest.md`)
  after crossbar/native-DPIN0/role-bit sequencing were all independently
  fixed. The MMIO pulse to the ACIO DP IN analog block's AUX/DPCD serializer
  genuinely does not take effect on this hardware chain — not a stale/fixed
  finding, re-verify only with a fundamentally different mechanism in hand.
- **`apple_atc_usb4_enable_dp_aux()` (candidate 0120, since fully reverted)
  disconnects the entire Thunderbolt hub** — do not re-add without first
  understanding exactly what register state it shares with the USB4 tunnel's
  own PLL/SERDES config.
- **The full DPIN0 `mode_value` guess space (0-15) is exhausted** (candidates
  0111-0113) — clean negatives across the whole range, do not re-sweep it.

## Current state (as of 2026-09-24, candidate 0139 prepared: diagnostic only)

A third research pass (5 angles + synthesis + 3 adversarial verifiers,
all `refuted: false`) investigated the one remaining lead from 0138: does
enabling `dcp_hotplug()`'s retrain-nudge for USB4 outputs
(`!dcp_is_usb4_output(dcp)` exclusion) help the connector escape its stuck
`0x0` mode? **Conclusion: no code fix proposed.** The exclusion's own
history traces to an unrelated, since-deleted debug shim (not a
documented hazard with the retrain path), but removing it would very
likely be a no-op regardless -- traced through actual DRM atomic-commit
semantics: the retrain path never touches the CRTC's stored mode, so
replaying it just re-triggers the same silently-swallowed `0x0` commit.
Narrowing the gate would also reintroduce a `LINK_STATUS_BAD` marking
that has direct historical precedent for making Hyprland refuse to
commit a mode entirely on this same connector. Confirmed from the log:
`set_digital_out_mode(` (the only thing that ever sets `dcp->valid_mode
= true`) appears twice, both for the internal panel, never once for the
tunnel connector, in either connect cycle this boot.

**0139 (prepared, not yet installed): two additive `dev_info()` lines in
`iomfb.c`, no control-flow change**, to settle whether a real-but-
degenerate atomic commit (`active=1`, `0x0` mode) is landing for the
tunnel connector at all, versus no commit ever reaching it -- before
spending a reboot on a fix that might target the wrong layer (kernel vs.
Hyprland/wlroots) entirely. Full reasoning in
`notes/2026-09-24-0139-log-crtc-active-mode-for-0x0-commit.md`. Same
module set as 0138 except a rebuilt `appledrm.ko`.

**Oliver raised a sharp, likely-load-bearing observation not yet
followed up on**: the monitor works direct via HDMI, and works via a
plain USB-C-to-HDMI adapter, but not through the OWC hub. The
HDMI/adapter cases are almost certainly **DP alt-mode** (direct pin
reassignment), not USB4/Thunderbolt DP tunneling at all -- an entirely
different mechanism in the spec (tunneling requires a real USB4 fabric
bandwidth-negotiation handshake between routers; alt-mode doesn't). If
so, every "it works" case this whole project has is on a code path
unrelated to the one actually failing, and offers no evidence about it.
Proposed next step, not yet acted on: boot into macOS with the identical
physical setup (hub + BenQ) and capture the unified log (`log
stream`/`log show`, filtered to DCP/AVService/Thunderbolt subsystems) to
see what apcall sequence and mode-commit timing macOS's own driver stack
produces for the same real tunnel -- since the DCP firmware itself
(`AppleCIOFirmware`) is the same closed Apple blob under both OSes, this
could reveal whether macOS's WindowServer simply commits a real mode
fast enough to beat the ~29s firmware deadline, which would reframe the
open problem as a Linux/Hyprland/DRM hotplug-timing issue rather than a
kernel driver bug.

## Prior state (candidate 0138 CONFIRMED on hardware: reconnect fix works)

**0138 installed and definitively confirmed: the reconnect-after-replug bug is fixed.**
`captures/2026-09-24-0138-boot-and-replug-kernel.log`. Sequence: monitor
plugged in fresh after boot -> connects normally, `DPRX_DONE=1` at
12:26:32 -> the (unrelated, see below) autonomous teardown hits at
12:27:01 (exactly 29s later) -> Oliver unplugged and replugged the cable
-> **`"DP IN tunnel routing: tunnel down"` appears for the first time in
any capture this whole project** (12:27:22, apple.c's
`apple_nhi_dp_tunnel_deactivate()` finally runs) -> a genuine second
connect cycle fires on replug: `dcp_dptx_disconnect(port=0)`, `allocated
Type-C DPTX PHY 2`, `display routed to Thunderbolt DP tunnel dpin0`,
`dcp_dptx_connect(port=0)`, `DPTX request_display: call #2` (12:27:31) --
**this never happened even once in 0136/0137's own replug test** -- and
it reaches `DPRX_DONE=1` again at 12:27:32. The fix is proven, not just
theorized.

**Problem #1 (the autonomous teardown) recurred, on both connects, and
is now much more precisely characterized: exactly 29 seconds after
DPRX_DONE, to the second, both times** (12:26:32->12:27:01, and
12:27:32->12:28:01). This rules out "random/environmental" and
strengthens the firmware-fixed-timeout theory from the research: DCP
firmware appears to give up on a link nobody has claimed with a real
video mode after a fixed ~29s internal deadline. Still no picture
(status quo unchanged there).

**New, sharper lead for problem #1, not yet applied:** read
`drivers/gpu/drm/apple/iomfb.c:230-316` in full. `dcp_hotplug()`'s
comment (lines 291-295) states outright: "DCP defers link training until
we set a display mode. But we set display modes from atomic_flush, so
userspace needs to trigger a flush, or the CRTC gets no signal." The
`dcp_retrain_active_crtc()` nudge exists specifically to force that
flush for an already-active CRTC after a hotplug -- and is explicitly
skipped for USB4/tunnel outputs (`!dcp_is_usb4_output(dcp)` at line 297).
Untested complication found while reading this, not yet resolved:
`dcp_retrain_active_crtc()` itself only acts `if (crtc->state->active)`
(line 247) -- and Hyprland currently shows this connector's CRTC applying
a `0x0` mode, so it's not yet confirmed whether that CRTC actually reads
as "active" in DRM's own terms; simply removing the `dcp_is_usb4_output`
gate might not be sufficient on its own. Needs verification before being
turned into a candidate -- not done yet, pending research given this
touches core atomic-modeset logic and deserves the same rigor as the
last two fixes before spending another reboot cycle.

## Prior state (candidate 0138 prepared: reconnect-after-replug fix)

The second research workflow (5 angles + synthesis + 3 adversarial
verifiers, all `refuted: false`) resolved both mysteries from 0137:

- **Problem #1 (autonomous ~29s teardown): traced as far as this source
  tree allows.** `dptxport_call()` is reachable only from
  firmware-initiated AFK/EPIC messages -- no kernel-side timer,
  workqueue, or delayed_work anywhere in the tree has a matching ~20-40s
  period (the one candidate, `usb4_hpd_wq`, is confirmed dead code). The
  driver's WILL_CHANGE/DID_CHANGE_LINK_CONFIG handling is byte-for-byte
  equivalent to the hardware-validated reference. Conclusion: this is
  very likely firmware-internal, not fixable from this tree. Not fixed
  this candidate. A real, separate, un-applied lead: `iomfb.c:296-297`'s
  retrain-nudge for a connected-but-unmodeset output is explicitly
  skipped for USB4/tunnel outputs specifically.
- **Problem #2 (replug doesn't re-arm the connect flow): root-caused and
  fixed, high confidence.** A physical unplug marks the departing switch
  unplugged *before* the generic Thunderbolt tunnel-teardown path runs,
  so `tb_dp_port_enable()` on the departing DP OUT port deterministically
  short-circuits to `-ENODEV` (zero I/O, `tb.h`'s
  `is_unplugged` check) -- which trips `tb_dp_activate()`'s early return
  *before* `ops->dp_tunnel_deactivate()` (apple.c's only way to clear its
  own reconnect latch) ever runs. This is **generic
  `drivers/thunderbolt/` core code**, not Apple-specific -- the reference
  avoids it entirely with a dedicated, always-fires notification hook
  this tree folded into the register-programming path instead. Confirmed
  by a direct, hop-by-hop trace (not log-absence inference) and
  independently re-traced by all three verifiers.

**0138 (prepared, not yet installed): fixes problem #2.**
`drivers/thunderbolt/tunnel.c`'s `tb_dp_activate()`: both `if (ret) return
ret;` guards changed to `if (ret && active) return ret;` -- the
deactivate-path caller already discards the return value entirely (so
this is a no-op there), and the activate path is byte-for-byte
unchanged. Full trace and reasoning in
`notes/2026-09-24-0138-dp-tunnel-deactivate-departing-port.md`. Same
module set as 0137 except a rebuilt `thunderbolt.ko` (only `tunnel.o`
recompiled; `thunderbolt_apple.ko` unchanged). `check` correctly refused
while the external connector still shows a stale `connected` status (not
a real picture) -- needs the monitor cable physically unplugged first,
same safety check every candidate has always had.

Problem #1 remains open and is very likely not fixable from this source
tree. This candidate's own boot-time connect may still hit the same ~29s
teardown -- what it should change is whether a *replug afterward*
actually reforms a working connection, which is the specific thing to
test next.

## Prior state (candidate 0137 installed: two new mysteries)

**0137 installed and confirmed on hardware: both the crossbar fix (0136)
and the linkcfg_completion fix (0137) work.** Right port, dcpext0 forced.
`captures/2026-09-24-0137-boot-and-replug-kernel.log`: crossbar cleanly
enables ("Switched dpin0 to dispext0,0", no `-22`), `SET_ACTIVE_LANE_COUNT
4` accepted, **`DP IN DPRX_DONE=1` reached, and `dcp_dptx_connect` does
NOT time out this time** -- `dcp_hotplug() connected:1 valid_mode:0
nr_modes:22` logged normally, no timeout anywhere in the log. Hyprland
picked up the connector live: `hyprctl monitors all` shows **"Monitor
USB-3 (ID 1): description: BNQ BenQ LCD T4M01233019"** with the correct
full EDID mode list (2560x1440@59.95 etc.) -- the real monitor, identified
by name, for the first time this whole project.

Still no picture (Oliver confirmed: nothing at all on the physical
screen), and two new problems surfaced:

1. **~29s after the successful connect (11:40:24-25), DCP autonomously
   tears the link back down** -- a WILL_CHANGE_LINK_CONFIG /
   SET_ACTIVE_LANE_COUNT(0) / SET_LINK_RATE(0x0) / DID_CHANGE_LINK_CONFIG
   apcall sequence at 11:40:54, with **no error, warning, or timeout
   logged anywhere**. This is why Hyprland's USB-3 monitor is stuck at a
   placeholder `0x0` mode: the connector is known (EDID cached from the
   original hotplug), but the underlying link isn't live any more.
2. **A physical unplug/replug of the monitor cable (done live, no
   reboot) does not re-arm DCP's software connect flow.** The Thunderbolt/
   ACIO tunnel physically reforms after replug (new device enumeration,
   "DP tunnel paths up" at 11:46:14) but this time hits "DPRX timeout,
   keeping DP tunnel" at 11:46:26 -- and critically, `grep`ing the whole
   log for `dcp_dptx_connect(port`, `DPTX request_display`, and `display
   routed to Thunderbolt DP tunnel` shows each exactly once, only at the
   original 11:40:24 connect, never again after the replug. DCP's own
   connect flow (`apple_dcp_tb_dp_tunnel()` -> `dcp_typec_route_activate()`
   -> `dcp_dptx_connect()`) was not re-entered despite the tunnel
   reforming at the hardware level.

A second research workflow (5 investigation angles + synthesis + 3
adversarial verifiers, same methodology as 0135/0136/0137's own research)
is running now to root-cause both. `manage-0137.py` stays installed and
armed; no new candidate config change made yet pending that result.

## Prior state (candidate 0137 prepared: linkcfg_completion fix)

**0136 installed and confirmed on hardware: the `-22` crossbar failure is
gone.** `captures/2026-09-24-0136-boot-kernel.log`: `f0304c000.mux:
Switched dpin0 to dispext0,0` (a real enable), no crossbar-up failure
anywhere, `DPRX_DONE=1` reached again, and `SET_ACTIVE_LANE_COUNT 4`
accepted. Still no picture -- `dcp_dptx_connect` still timed out waiting
for link configuration.

**0137 (prepared, not yet installed): found and fixed why, even with 0136
in place, the link-config wait still times out.**
`dptxport_call_set_active_lane_count()` (`dptxep.c`) only completed
`linkcfg_completion` -- the exact completion `dcp_dptx_connect()` blocks
on -- for a USB4 tunnel if `dcp_usb4_drm_allowed()` (`usb4_force_dptx`)
was true. That flag has had **no way to ever be set true since commit
0dc9f50** (2026-09-24, the same commit that introduced the whole tunnel
mechanism 0127 onward has been testing) removed the old manual-training
sysfs knob (`module_param_cb usb4_dptx_train`) that used to set it,
without removing this now-dead gate. The hardware-validated reference
(aurora-silicon/linux#8) completes `linkcfg_completion` here
unconditionally, with no such gate. This means **every USB4-tunneled
connect attempt on this project, on both ports, since 0127, has been
structurally unable to complete the link-configuration wait** -- unrelated
to the port/pipeline confound, the crossbar `-22`, or dcpext1's own
firmware-silence problem; a fourth, independent, now-fixed defect.
`drivers/gpu/drm/apple/dptxep.c`/`.h`, `dcp.c`/`dcp-internal.h` in
`linux-aurora-pr` (branch `j416s-usb4-dpin`, commit `992ff65b5`, not
pushed -- this branch has no `origin` tracking ref, matching every prior
candidate). Full trace, reference diff, and build verification in
`notes/2026-09-24-0137-complete-linkcfg-unconditionally.md`.
`scripts/manage-0137.py`: same module set as 0135/0136 except a rebuilt
`appledrm.ko`; `check` already run (no sudo); `install` needs sudo and a
reboot to test, not yet run.

## Prior state (candidate 0136 prepared: stale-config -22 fix)

**0136: the `-22` crossbar-up failure hit by both 0127 and 0135 is a
leftover test-environment misconfiguration, not a code bug -- fix
prepared, not yet installed.** Ten stale `modprobe.d` conf files from the
discontinued pre-0127 "native DPIN0" experiment
(2026-09-23, candidates 0113/0115/0116/0118/0119/0121/0122/0123/0124/0126)
were never removed and are still baked into the initramfs used for every
boot since 0127 (confirmed by extracting the actual installed image).
One of them sets `options mux_apple_display_crossbar
usb4_defer_bringup=1`, which makes `apple_dpxbar_set_t602x()` refuse to
select any dispext state other than 2 (dcpext1's own state) on a Type-C
port's dpin0/dpin1 crossbar leg -- exactly matching the `-22` seen when
0127 (left port) and 0135 (right port) both forced dcpext0 (state 0) onto
that leg. `scripts/manage-0136.py` backs up and removes the ten stale
files, rebuilds the initramfs, and verifies the result (0135's own
`usb4_route_prefer_fixed_diag=1` still armed, `usb4_defer_bringup` string
gone). `check` already run (no sudo, confirms preconditions); `install`
needs sudo, not yet run. See
`notes/2026-09-24-0136-remove-stale-defer-bringup-configs.md` for the full
trace (mux_control_try_select -> apple_dpxbar_set_t602x's deferred-state
gate -> module param -> stale conf files -> confirmed present in the
actual installed initramfs).

This does not by itself guarantee a picture -- it removes one specific,
now-understood obstacle from the dcpext0-forced tunnel path. What happens
once the crossbar select actually succeeds is untested.

## Prior state (candidate 0135 result: port confound resolved)

**0135 result: the port/pipeline confound is resolved, decisively. The
right port's ACIO hardware is confirmed fine -- the defect is specific to
the dcpext1 pipeline instance, not the physical port.** Forcing the right
port's tunnel onto dcpext0 (0127's own pipeline) reproduced 0127's result
almost exactly: the full rich link-training apcall burst fired
immediately after `request_display` succeeded (`SET_LINK_RATE`,
`WILL_CHANGE_LINK_CONFIG`, `DID_CHANGE_LINK_CONFIG`, drive-settings
cycles), and **`DPRX_DONE=1` was reached** -- a genuine AUX/DPCD hardware
completion, on the right port, for the first time ever. It then hit the
exact same `DP tunnel crossbar up failed: -22` 0127 hit and eventually
gave up with the same `timed out waiting for port 0 link configuration`
(twice, both connect attempts, same shape both times) -- consistent,
reproducible, and matching 0127's own failure point precisely.
`captures/2026-09-24-0135-boot-kernel.log`.

This conclusively answers what 0135 set out to test: **it is not the
right ACIO instance's hardware.** The same physical port that has never
once produced an apcall past `request_display` on dcpext1 (0128-0134)
produces a full, real AUX handshake on dcpext0 (this run). The defect is
tied to the dcpext1 pipeline/DCP-instance specifically.

Chased two follow-up hypotheses from this same capture, both closed by
direct verification rather than left open:
- **dcpext0 runs an explicit `dcp_poweroff()` cycle at boot; dcpext1
  never does.** Checked the code (`dcp_enable_dp2hdmi_hpd()`,
  `dcp.c:1797`): this is gated on `dcp->hdmi_hpd` (a GPIO only dcpext0
  has, for its fixed HDMI output) vs. `dcp_is_typec_output()` (which does
  nothing at boot for either instance, since no cable is connected yet).
  Fully expected, symmetric, correct behavior -- not a lead.
- **`apple,typec-mux-indices` differs in the live device tree: `[0,0,0]`
  for dcpext0 vs `[2,2,0]`... `[2,2,2]` for dcpext1.** Traced
  `route->mux_index`'s only use in the tunnel path
  (`dcp_tunnel_crossbar_up()`, `dcc.c:473`,
  `mux_control_try_select(route->active_xbar, route->mux_index)`): this
  is the crossbar *state* (which dispext a selected control routes to),
  not which control is selected -- dcpext0 routing to state 0 (itself)
  and dcpext1 to state 2 (itself) is exactly the expected, correct,
  symmetric per-instance identity. Also not a lead.

**Open question, now much sharper than before**: why does DCP's dcpext1
instance never issue a single apcall for ~5 seconds after accepting
`request_display`, while dcpext0 -- receiving the identical
target/core/atc/die values, on either port -- immediately launches a
real link-training burst every single time? Nothing checked so far
(devicetree symmetry, apcall dispatch code, crossbar routing code, PHY
sequencing) explains this; it looks like it comes down to something
about the dcpext1 firmware instance itself, or some remaining
driver-side difference in how it specifically gets initialized/talked
to, not yet found.


**Full parallel research sweep run at Oliver's request (8 independent
agents, ~1.1M tokens): overturns the 0133/0134 "stuck FSM" premise, and
finds the confound that has undermined every register comparison since
0127.** Full writeup in `notes/2026-09-24-0135-isolate-port-pipeline-confound-revert-fsm.md`;
summary:

- **The "stuck FSM" was a misreading.** This project's own source
  already documents offset `+0x18` as an ordinary one-shot, read-to-clear
  status register (`APPLE_CIO_DPIN_ANALOG_EMPTY = 0x80000000`, comment
  "+0x18 is first-read status 0x1017 (read-to-clear)") -- from candidates
  0054-0056, before this session. 0133's every-500ms polling was reading
  past the one meaningful value into the documented "empty" sentinel;
  0134's write-1-to-clear ack had nothing to acknowledge. Reverted both
  back to the original, deliberately cautious single-post-mortem-dump
  design.
- **The real, load-bearing gap: 0127 (success) and every failure since
  differ in BOTH physical port AND DCP pipeline at once, never in
  isolation.** Every register-level comparison drawn from this data,
  including the +0x18 first-read contrast that motivated 0133/0134, is
  confounded and cannot be trusted without a same-port data point.
  Offsets +0x00/+0x0c/+0x28/+0x34 (flagged after 0133) are confirmed
  *not* diagnostic -- identical across all 9 captures, the success
  included.
- **Crossbar gap found, deliberately deferred**: the reference's
  `apple_dpxbar_link_up()`/`link_down()` gate a register
  (`OUT_PCLK1_EN`/`OUT_N_CLK_EN`) this project's T602x port never
  touches, and `link_down()` never clears `CROSSBAR_DISPEXT_EN` despite
  a comment claiming parity with the reference. Real, but T602x's
  register layout has clearly diverged from the generic one compared
  against (extra unnamed registers, no established 1:1 mapping), and this
  code is unreachable on the current failure regardless (never gets past
  the ~5s silence to reach `SET_LINK_RATE`). Left for later.
- **Confirmed correct/ruled out**: PHY analog wake/AUSPLL sequence
  (bit-for-bit matches reference); crossbar routing code and live
  device-tree wiring (symmetric between both ports); DCP apcall dispatch
  for `DEVICE_NOT_RESPONDING`/etc. (byte-identical across this project's
  tree, the merge-base, and the working reference -- predates all three,
  not the defect). The real fact from that last audit: DCP issues *zero*
  apcalls for ~5s on every failure, versus an immediate real
  link-training burst on the one success -- the fault is upstream of
  anything the driver's apcall dispatcher ever sees.
- **No external prior art exists.** Confirmed via live GitHub/web
  research: no public source documents this ACIO block; the one parallel
  community effort on the same SoC family is pre-hardware-test and behind
  this project; Sven Peter's real upstream series confirms DP tunneling
  unimplemented for every Apple Silicon generation. This project's own
  state is very likely the most advanced public reference point for this
  exact problem.

**Candidate 0135 prepared, awaiting Oliver's install+reboot**: reverts
0133/0134 (above), and adds `usb4_route_prefer_fixed_diag` (armed for
this boot) to force the right port's tunnel onto the dcpext0 pipeline
(0127's own pipeline), isolating whether the right ACIO's own hardware or
the dcpext1 pairing is the actual discriminator. Full reasoning and test
plan in the note above.


**0134 result: the write-1-to-clear hypothesis is cleanly closed.** Log
showed exactly the designed sequence: `"Apple: FSM stuck at 0x80000000,
attempting write-1-to-clear ack"` then `"Apple: FSM after ack:
0x80000000"` -- identical before and after, no effect at all. Failure
shape otherwise unchanged (`DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`
at ~5s, `DPRX` never asserts, final give-up at ~12s). **Oliver confirmed:
still no picture.** `captures/2026-09-24-0134-boot-kernel.log`. Do not
retry a write to this offset without new evidence.

**Major context finding (web research, not previously done): DisplayPort
tunneling over USB4/Thunderbolt is not yet solved upstream for *any*
Apple Silicon chip.** Sven Peter -- the actual upstream Asahi Linux
Thunderbolt maintainer, currently landing the real "Initial USB4/
Thunderbolt support" series for M1/M2/M3 (t8103/t600x/t8112/t602x, i.e.
this exact machine's SoC family) -- states explicitly in that series
that PCIe and DisplayPort tunneling are deliberately not implemented yet
("require additional work and reverse engineering that is not done
yet"). The *only* place DP tunneling has ever been demonstrated working
on real Apple Silicon hardware is aurora-silicon/linux#8, an unofficial,
third-party PR, for **t8103 (M1) specifically** -- a different, better
-understood, one-generation-older SoC than this machine's t602x (M2
Pro). Ruled out along the way: `CONFIG_RESET_APPLE_CIO` is enabled in
the running kernel (confirmed directly from `/proc/config.gz`); this
project's own `drivers/thunderbolt/apple.c` already correctly requests
and deasserts the ACIO's reset controller
(`devm_reset_control_get_exclusive`/`reset_control_deassert`); the
ACIO's own Cortex-M3 coprocessor is confirmed alive and running firmware
(RTKit syslog messages flow correctly, the same mechanism DCP itself
uses); the "Gen2/3 link error" firmware messages seen at boot are benign
noise, present identically on both the one success (0127) and every
failure. None of this points to a missing foundational piece this
project overlooked -- it points at DP tunneling on t602x specifically
being genuinely unsolved territory, one step ahead of what even the
hardware's most qualified upstream developer has published working code
for. This does not mean it is unsolvable, but it changes the odds on
continuing to guess at undocumented registers without a new, strong
hypothesis. No candidate proposed yet; discussing next steps with
Oliver (continue targeted guessing vs. engage the actual upstream
community with this project's own findings vs. wait for Sven Peter's
work to reach DP tunneling).


**Oliver's direction on the FSM finding: try the targeted write.** Asked
before building anything that writes into the address range the two
standing safety rules flag; he chose "try the targeted write" over
holding off. Candidate 0134 (below) is that attempt: a write-1-to-clear
acknowledge on `+0x18` alone, once, gated on the exact stuck condition
0133 characterized -- not a new blind guess, and not a retry of anything
already confirmed ineffective (`dpin_aux` pulsed a different offset,
`+0x00`).


**0133 result: the clearest, most specific finding this project has had.**
Dumping the ACIO analog block on all 24 polls (500ms apart, full 12s
budget) instead of once at the end shows: `APPLE_CIO_DPIN_ANALOG_FSM`
(offset `+0x18`, literally named "FSM" in this driver's own code) reads
`0x00001017` on poll #1 (~1s after tunnel-up) and `0x80000000` on every
single poll after that (#2 through #24) -- one clean transition, then
**frozen solid for 11+ seconds**, spanning right through
`DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` (~5s) and the final give-up
(~12s). Every other word in both the dpin0 and dpin1 dumps (offsets
0x00-0x58 and 0x5c-0x7c) is bit-for-bit identical across all 24 polls,
*except* dpin1 (the unused adapter) also shows one matching transition at
the same poll boundary (`+0x0c`: `00040004`->`80010000`, `+0x1c`:
`00000000`->`80000000`) -- consistent with a real, shared hardware event
rippling across the ACIO block at tunnel-up, not measurement noise.
`captures/2026-09-24-0133-boot-kernel.log`.

This is not "the AUX engine never tries" (0131/0132's working theory) --
it's "the AUX engine's own FSM takes one real step and then gets stuck,"
a meaningfully different and more specific claim. `dpin_aux`'s standing
safety rule ("does not stick") tested pulsing a *different* register
(`+0x00` bit 0, the control/start pulse, via `apple_dp_start_analog()`)
-- never this status/FSM register specifically, and never with this kind
of moment-to-moment visibility. Whether a targeted read-modify-write on
`+0x18` (e.g. acknowledging what may be a write-1-to-clear latch, a
pattern this same driver family already uses elsewhere -- the DPIN IRQ
status register) would unstick it is a real, evidence-based hypothesis,
not a blind guess -- but it means writing into the exact address range
two standing safety rules already flag, on a register neither has
actually tested. Checking with Oliver before building anything that
writes there.


**0132 result: the full aurora-silicon/linux#8 Apple-host register
comparison is now exhausted, without a picture.** `NO_AUTO_LT` applied
with no error logged; the video-hop credit override was also added but
turned out to target the wrong "credits" field entirely (`hop->nfc_
credits`, port-level NFC buffer bookkeeping, not `hop.initial_credits`,
what `apple_dp_dump_hop()` actually prints and what the reference's own
fix meant -- correction recorded in `notes/2026-09-24-0133-*.md`; harmless,
but not load-bearing for video, and irrelevant to AUX/DPRX regardless).
Failure shape unchanged: ~5s of apcall silence, `DEVICE_NOT_RESPONDING`/
`DEVICE_NOT_STARTED`, `linkcfg_completion` timeout, `DEACTIVATE`, retry,
same again, `DPRX` never asserted. **Oliver confirmed: monitor still
dark.** `captures/2026-09-24-0132-boot-kernel.log`.

**The single strongest fact after eight dcpext1 connect attempts across
five candidates (0128-0132): DCP's own internal wait before declaring
`DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` has stayed ~5 seconds,
unmoved, through every host-side change tried** -- two different widened
timeouts, HPD propagation, and the hub auto-training hold-off. Every
Apple-host-specific piece of the hardware-tested reference's generic
Thunderbolt code is now ported (the Titan Ridge LTTPR skip excepted, not
applicable to this non-Titan-Ridge hub). Continuing to guess at more
register pokes from the same source without new evidence would repeat
exactly what this project's own standing safety rules exist to prevent.


**0131 result: HPD propagation confirmed working, but not sufficient
alone.** `"Apple: HPD propagated"` fired exactly where expected, before
`"DP IN tunnel routing"` -- the pulse and wait loop work correctly on this
hardware. But everything after that reproduced the identical failure
shape as every dcpext1 run since 0128: 5s of apcall silence, `DEVICE_NOT_
RESPONDING`/`DEVICE_NOT_STARTED`, the `linkcfg_completion` timeout,
`DEACTIVATE`, one retry, same again. `DPRX` never asserted; `"DPRX
timeout, keeping DP tunnel"` still fired at ~12s. **Oliver confirmed:
monitor still dark.** `captures/2026-09-24-0131-boot-kernel.log`.
Real, confirmed progress (HPD-propagate was a real, necessary gap, now
closed) but not the whole answer -- see 0132 below for the other two
pieces of the same reference commit, ported next.


**0129 result: the timeout hypothesis was partially right, but a deeper
issue remains.** With `set_hpd` widened to 8000ms, it (and everything
before it) now succeeds cleanly in both connect attempts this boot --
zero AFK-layer timeouts anywhere in the capture, `release_display` itself
now returns `result=0` instead of `-110`. This confirms the 1-second host
timeout genuinely was cutting off a real, slower-but-valid reply from DCP
for this one call. But the failure point simply moved later, to exactly
0127's own failure signature: `dcp_dptx_connect: timed out waiting for
port 0 link configuration` (the separate, pre-existing 2000ms
`DPTX_CONNECT_TIMEOUT` wait for `linkcfg_completion`). DCP's firmware
still independently sends `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`
around 5 seconds in, on **both** connect attempts this boot, exactly as
in every prior dcpext1 failure -- and, unlike 0127, the firmware-driven
link-training burst (`SET_LINK_RATE`, `WILL_CHANGE_LINK_CONFIG`, etc.)
never fires at all this time, so `dcp_tunnel_crossbar_up()` is still
unexercised on the correct pipeline. `DPRX` stayed 0 for the whole boot
(`captures/2026-09-24-0129-boot-kernel.log`). **Oliver confirmed by eye:
no picture, no flicker, nothing at all** -- consistent with the logs.

**0130 result: the "it's just cascading timeouts" hypothesis is now
closed.** Both connect attempts this boot ran the full widened 8000ms
`linkcfg_completion` wait (confirmed from timestamps: attempt #1's
timeout fires ~9s after `request_display` succeeded, attempt #2's fires
at exactly 8s after its own `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`
-- both far past the old 2000ms wall). Nothing changed: still zero
`SET_LINK_RATE`/`WILL_CHANGE_LINK_CONFIG`/any other apcall in the 5-second
window after `request_display`, still `DEVICE_NOT_RESPONDING`/
`DEVICE_NOT_STARTED` at ~5s on both attempts, still `DPRX` at 0 for the
entire boot. **Oliver confirmed by eye: no picture on the external
display.** Widening host-side timeouts got real, confirmed mileage out of
`set_hpd` (0129) but has now run out of road at `linkcfg_completion`
(0130) -- DCP's firmware is not merely slow here, it is not going to train
this link at all on this pipeline/port, however long the host waits.
Do not widen another timeout in this chain without new evidence; the
open question is now *why* DCP reaches
`DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`, not how long anything
waits for it. `captures/2026-09-24-0130-boot-kernel.log`.
`notes/2026-09-24-0130-widen-linkcfg-timeout-diagnostic.md`.

**New lead found while reading the 0130 capture (not yet acted on):** the
generic `apple_dp_aux_work()` poller (`drivers/thunderbolt/apple.c:997`)
independently samples the DP IN adapter's CS0-CS13 registers every 500ms
for up to 12s and logs `"DP IN CS changed ..."` on *any* difference. That
line appears **zero times** across all four dcpext1 failures (0128 x2,
0129, 0130) -- 96 samples total, nothing ever moves -- and exactly **once**
in the one dcpext0 success (0127, the DPRX transition itself). Meanwhile
`dpin%u: active handshake=%d` (`apple_dpin_set_active()`,
`drivers/thunderbolt/apple.c:2081`) logs `handshake=0` (success) at the
same point in *every* run, success or failure alike, so the software-side
DPTX_INACTIVE handshake (HPD/CONTROL/ACK/MODE_A/MODE_B registers) reports
completing cleanly regardless of outcome. Put together: the handshake
that's supposed to wake the ACIO analog block reports success every time,
but the separate CS0-CS13 status registers it should cause to move never
move at all on dcpext1/right-port -- this looks less like a slow retry
and more like the physical AUX engine never actually gets kicked into
motion on this pipeline/port, for a reason not yet identified. Note
0127's own `DPRX_DONE=1` happened *after* its own `dcp_tunnel_crossbar_up()`
already failed with `-22` that run, so crossbar selection does not look
load-bearing for this either -- ruled out as the likely explanation, not
just unexamined. No next candidate proposed yet; wanted Oliver's read on
this before picking the next single-variable thing to try.

**Comprehensive comparison against aurora-silicon/linux#8 done at Oliver's
request; a concrete, hardware-tested candidate found.** Fetched the actual
PR (t8103/M1, hardware-tested on three docks/multiple monitors) and diffed
it against the shared merge-base with this tree. The DCP-side port (0127)
already matches the reference closely. But the reference's Thunderbolt-side
commit (`4a7fd72`) does something in **generic** `tb.c`/`tunnel.c`, gated
behind an Apple-host check, that this project's port never carried over:
right after tunnel activation, it pulses `ADP_DP_CS_3_HPD_PROPAGATE` on the
DP IN adapter and waits up to 2s for `ADP_DP_CS_2_HPD` -- because an Apple
host's DP IN adapter has no real physical DP connector wired to it, so
nothing else would ever set that bit. 0127's port deliberately avoided
touching `tb.c`/`tunnel.c` (to keep `thunderbolt.ko` byte-identical, the
right call for the *routing trigger*), but this specific register-level
step lived in that same generic code and was simply never ported.
Confirmed absent by direct search: zero references anywhere in this tree
to `ADP_DP_CS_3_HPD_PROPAGATE`, `tb_dp_tunnel_notify`, or
`tb_port_is_apple_host_dpin` before this. This lines up exactly with the
CS0-13-never-changes finding above -- an unpropagated HPD is a direct,
mechanistic explanation for registers that never move. Full comparison
and reasoning in
`notes/2026-09-24-0131-pulse-hpd-propagation-apple-host-dpin.md`.

**No next candidate built yet.** See "Current state" above -- the FSM-stuck
finding points at a specific register, but writing to it means entering
the exact address range two standing safety rules already flag, on an
offset neither one actually tested. Checking with Oliver on the
risk/reward before building it.

**Architecture confirmed correct and sufficient.** Candidate 0127 achieved
`DPRX_DONE=1` -- a genuine AUX/DPCD hardware handshake completing over the
USB4 tunnel -- the first and only time this has happened in this project's
full history. This was on a route that turned out to be the wrong DCP
pipeline (see below), so it is not yet a working picture, but it is direct,
unambiguous proof that the crossbar routing, the real tunnel-trigger
mechanism (`apple_dcp_tb_dp_tunnel()`, ported from aurora-silicon/linux#8),
the ATC PHY staying in USB4 mode, and the native DPIN0 wake are all
correct and physically sufficient on this exact hub/adapter/monitor chain.

**Two data points on DPRX, one success and two failures, cause not yet
isolated:**
- 0127 (dcpext0/HDMI-capable pipeline, due to a route-scoring bug):
  `DPRX_DONE=1`, then DCP still deactivated without a picture.
- 0128 x2 (dcpext1/USB-C-only pipeline, the scoring bug fixed): `DPRX`
  stayed 0 both times, identical failure pattern down to the millisecond:
  validate/connect/request_display succeed, DCP calls
  GET_SUPPORTS_HPD/GET_MAX_LANE_COUNT/ACTIVATE, then the driver's own
  outbound `set_hpd` and `release_display` calls each time out at their
  1000ms default, a retried `validate` also times out, and only ~4-5
  seconds after `request_display` succeeded does DCP send
  `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` apcalls and `DEACTIVATE`.

The two 0128 runs used the same pipeline (dcpext1) but a different
physical port than 0127's success (left port for 0127, right port for
both 0128 runs, since Oliver had relocated) -- **explicitly ruled out by
Oliver as the relevant variable, do not re-investigate port choice.** What
actually differs between the one success and the two failures is not yet
established. Concretely unexamined so far: whether DCP's own multi-second
unresponsiveness after `request_display` in the failing runs reflects a
real internal AUX retry that our host-side calls' 1-second timeouts
(`dptxport_set_hpd()`'s default, `afk_service_call()`'s default) are too
short to survive, versus a genuinely failed AUX negotiation that no
timeout value would fix.

**Candidate 0129 prepared, awaiting Oliver's install+reboot** (see below).
Full boot captures for all of this: `captures/2026-09-24-0127-boot-kernel.log`,
`captures/2026-09-24-0128-boot-kernel.log`,
`captures/2026-09-24-0128-retry-boot-kernel.log`.

## Recent candidates (0126-0135)

- **0126** (drm/apple/dcp.c, one-line): stopped forcing the USB4 tunnel's
  ATC PHY into `PHY_MODE_DP` (both the reference PR and our own
  tunnel-clock code require it stay in USB4/TBT mode). Correct fix, kept,
  but alone produced a byte-for-byte identical trace to every prior
  candidate -- confirmed insufficient on its own.
  `notes/2026-09-23-0126-stop-phy-mode-dp-switch.md`.
- **0127** (full architectural port, 4 modules): replaced the
  fake-Type-C-alt-mode tunnel trigger every prior candidate relied on with
  the real mechanism from aurora-silicon/linux#8's hardware-validated
  t8103 implementation -- a new `apple_dcp_tb_dp_tunnel()` DCP-side entry
  point, and a new Thunderbolt-side `apple_dpin_ctx` mechanism wired into
  this project's own pre-existing, already-safe
  `dp_tunnel_pre/post_activate/deactivate` hooks (zero changes to shared
  `tb.c`/`tunnel.c`). Result: `DPRX_DONE=1` (see "Current state").
  `notes/2026-09-24-0127-port-thunderbolt-dp-tunnel-routing.md`.
- **0128** (drm/apple/dcp.c, one-line): restored a fixed-output
  route-scoring penalty the 0127 port had dropped, so the tunnel prefers
  dcpext1 (no fixed output) over dcpext0 (HDMI-capable) -- confirmed
  fixed (connect calls now correctly target `315c00000.dcp`), but `DPRX`
  did not reassert in the two runs since. `notes/2026-09-24-0128-prefer-dcpext1-for-tunnel.md`.
- **0129** (drm/apple/dptxep.c call site in dcp.c, one-line): both 0128
  runs stall identically at the first `dptxport_set_hpd()` call after
  `request_display` succeeds -- every outbound AFK call after it times out
  at the normal 1000ms budget, while the fully independent
  `tb_dp_wait_dprx()` poll (generic, non-Apple, 12000ms budget, started at
  tunnel-up) also never sees DPRX assert. Widened only this one call's
  timeout to 8000ms as a diagnostic: `afk_service_call_timeout()` silently
  discards a late reply with no log trace on the current 1000ms timeout,
  so today's captures cannot actually distinguish "DCP never replies" from
  "DCP replies late and the host already stopped listening." Installed
  and booted same day: confirmed `set_hpd` now succeeds (no AFK timeout
  anywhere in the capture), but the failure point just moved to 0127's own
  `linkcfg_completion` timeout instead -- see "Current state" above.
  `notes/2026-09-24-0129-widen-set-hpd-timeout-diagnostic.md`.
- **0130** (drm/apple/dcp.c, one-line): direct follow-up to 0129. Widened
  `DPTX_CONNECT_TIMEOUT` (2000ms -> 8000ms) the same way. Installed and
  booted same day: both connect attempts ran the full 8000ms wait with no
  change (still no `SET_LINK_RATE`/`WILL_CHANGE_LINK_CONFIG`, still
  `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` at ~5s, `DPRX` stayed 0) --
  Oliver confirmed by eye, no picture. Closed the "it's just cascading
  timeouts" hypothesis. `notes/2026-09-24-0130-widen-linkcfg-timeout-diagnostic.md`.
- **0131** (drivers/thunderbolt/tunnel.c + tb_regs.h): found by a
  comprehensive comparison against aurora-silicon/linux#8 at Oliver's
  request. Ports one specific register-level step from that hardware-
  tested reference -- pulsing `ADP_DP_CS_3_HPD_PROPAGATE` on the DP IN
  adapter and waiting for `ADP_DP_CS_2_HPD` -- that 0127's port never
  carried over when it deliberately avoided touching shared `tb.c`/
  `tunnel.c`. Installed and booted same day: `"Apple: HPD propagated"`
  confirmed firing correctly, but `DPRX` still never asserted -- see
  "Current state" above. `notes/2026-09-24-0131-pulse-hpd-propagation-apple-host-dpin.md`.
- **0132** (drivers/thunderbolt/tunnel.c + tb_regs.h): direct follow-up to
  0131. Ported the other two pieces of the same hardware-tested commit,
  held back from 0131 to keep that a single-variable test: `ADP_DP_CS_3_
  NO_AUTO_LT` holding the hub's DP OUT adapter off its own link training
  while the tunnel is up, and a video-hop credit override that turned out
  to target the wrong "credits" field (see "Current state" above).
  Installed and booted same day: `NO_AUTO_LT` applied cleanly, failure
  shape unchanged, `DPRX` never asserted -- Oliver confirmed, monitor
  still dark. Closes out the full aurora-silicon/linux#8 Apple-host
  register comparison. `notes/2026-09-24-0132-no-auto-lt-and-video-credits-apple-host.md`.
- **0133** (drivers/thunderbolt/apple.c, one function): pure diagnostic,
  zero behavior change. Dumped the ACIO analog block on every 500ms poll
  instead of only the last one. Installed and booted same day: found
  `APPLE_CIO_DPIN_ANALOG_FSM` (`+0x18`) transition once, early
  (`0x00001017` -> `0x80000000`), then freeze solid for the remaining 11+
  seconds straight through `DEVICE_NOT_RESPONDING` and the final give-up
  -- see "Current state" above for the full finding.
  `notes/2026-09-24-0133-dump-analog-block-every-poll.md`.

- **0134** (drivers/thunderbolt/apple.c, one new function): the targeted
  write 0133's finding pointed at, discussed with and approved by Oliver
  before building. `apple_dp_ack_analog_fsm()`: the first time `+0x18`
  (`APPLE_CIO_DPIN_ANALOG_FSM`) is observed stuck at `0x80000000`, read it
  and write the same value straight back -- the exact write-1-to-clear
  idiom this driver family already uses successfully on
  `APPLE_DPIN_IRQ_STATUS` elsewhere in the same file. Installed and
  booted same day: fired exactly as designed, zero effect (`0x80000000`
  before and after), failure shape unchanged -- Oliver confirmed, still
  no picture. Closes this specific hypothesis; see "Current state" above
  for the bigger-picture finding that followed.
  `notes/2026-09-24-0134-ack-analog-fsm-write1clear.md`.
- **0135** (drivers/thunderbolt/apple.c revert + drivers/gpu/drm/apple/dcp.c,
  new diagnostic): found via a full 8-agent parallel research sweep at
  Oliver's request. Reverts 0133/0134 (the "stuck FSM" was a misreading of
  an already-documented, pre-session read-to-clear status register) and
  adds `usb4_route_prefer_fixed_diag` to isolate the port/pipeline confound
  that has undermined every register-level comparison since 0127 -- forces
  the right port's tunnel onto 0127's own dcpext0 pipeline, for one boot,
  to test whether the port or the pipeline gates the rich apcall burst and
  `DPRX_DONE=1`. Not yet installed/booted.
  `notes/2026-09-24-0135-isolate-port-pipeline-confound-revert-fsm.md`.

Currently installed and booted: candidate 0134
(`thunderbolt_apple.ko` SHA256 `fa245b8411f4ab85db5143c2111a8cd423ac763aa471c289300ca4f56da46a08`,
`thunderbolt.ko` unchanged from 0132/0133
(`459250fe65adc5066f64f9b9b91c8f8b291e6e96b648de4d95bb0222afe4a5b9`),
`appledrm.ko`/`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko` unchanged
from 0130-0133, hashes in `scripts/manage-0134.py`).

Candidate 0135 built and verified, not yet installed
(`appledrm.ko` SHA256 `62fea148ce8ab047ad96301ca4b6c977668edb7affc85e4cf35e91b9676fd27f`,
`thunderbolt_apple.ko` SHA256 `cfcd0fce5f999ab0ee082cb2680468996c96c9a143ace01d324aff6ee7268374`
(source-identical to 0132 except one comment, confirmed via `git diff`),
`thunderbolt.ko`/`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko`
unchanged, hashes in `scripts/manage-0135.py`). `OPTIONS` for this
candidate includes `usb4_route_prefer_fixed_diag=1` (armed for this
boot's own test). To arm and test, after this commit is pushed:
```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0135.py check
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0135.py install
```
then reboot, and capture `dmesg`/`journalctl -k` from this boot.
