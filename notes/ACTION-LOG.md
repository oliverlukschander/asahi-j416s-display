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

## Current state (as of 2026-09-23, end of candidate 0125)

**Confirmed working, end-to-end, reproducibly:** DCP's AFK/EPIC protocol
handling for the USB4-tunneled connect sequence (`validate` → `connect` →
`set_hpd` → `request_display` → `ACTIVATE`, our native DPIN0 wake) — zero
errors, exactly the calls expected, on two independent clean boots. Crossbar
routing, the native DPIN0 handshake mechanism itself, and the Thunderbolt
DP IN role bit are all correctly implemented.

**Confirmed not working:** the actual DisplayPort AUX/DPRX electrical
negotiation between the USB4 tunnel's DP adapter hardware and the downstream
Synaptics VMM7100/BenQ chain. `DPRX` never asserts; DCP goes silent after
`ACTIVATE` rather than proceeding to `WILL_CHANGE_LINK_CONFIG`/
`SET_LINK_RATE`. The one existing software lever for this (`dpin_aux`) is
confirmed, twice, genuinely ineffective on this hardware. Cross-checked
against aurora-silicon/linux#8 (the M1/t8103 reference): that implementation
has no equivalent AUX-poke mechanism at all — DPRX completes as a natural
side effect of DCP's own link training once told a display is attached, and
never needed forcing. That reframes `dpin_aux` as never having been the
right lever, not just an ineffective one.

**Two live open directions, neither attempted yet:**
1. Further DCP firmware-internal reverse engineering of whatever gates the
   AUX read during that silent window — not reachable from any Linux-side
   instrumentation, since DCP never reports back on it at all.
2. A genuine compatibility limit specific to the OWC hub / Synaptics VMM7100
   adapter chain for a *tunneled* (vs. direct) DP route — direct HDMI and
   direct USB-C to the same monitor both work. Weighed against this: the
   identical cable/hub/adapter chain works instantly under macOS on an M4
   Mac, so the hardware itself is capable of it.

No hardware action is currently pending.

## 2026-09-23 -0126: stop switching the USB4 tunnel PHY to DP mode

Found while scoping a full aurora-silicon/linux#8 port (two parallel Opus
5.5 agents did a full function-by-function comparison; see
notes/2026-09-23-0126-stop-phy-mode-dp-switch.md for the trigger chain).
`dcp_dptx_connect()`'s analog-DPIN branch has unconditionally switched the
tunnel's ATC PHY to `PHY_MODE_DP` at connect time since candidate 0118 --
present in every candidate since. Both the reference PR and our own
tunnel-clock code require the PHY to stay in USB4/TBT mode for a genuine
tunnel. Also traced that DPRX is checked by a generic, non-Apple-specific
mechanism already in our own tunnel.c (`tb_dp_dprx_start`/`tb_dp_wait_dprx`,
polling the real hardware bit `DP_COMMON_CAP_DPRX_DONE`) -- downstream of
DCP's protocol, so forcing the tunnel PHY out of USB4 mode before that can
complete is a plausible direct cause. One-line, low-risk removal, tested
before committing to the much larger PR#8 architectural port (still
scoped and ready to build if this alone isn't sufficient -- see
`/tmp/dcp-fw2/agent-portA-dcp-side.md`/`agent-portB-tb-side.md`, scratch
analysis, not committed to this repo).

Only dcp.o recompiled. New appledrm.ko SHA256:
a3ea4d4eed1d763fc696f89098d373bbd27b5331382eb6bdf1fe59c2aacac209. Other
four modules unchanged (verified). Stale-symlink sweep clean,
test-dpin-handshake.c 13/13 pass. Patch:
patches/0126-drm-apple-dcp-stop-switching-usb4-tunnel-phy-to-dp-mode.patch.
scripts/manage-0126.py derived from manage-0124.py (candidate number + hash
only).

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0126.py install
```

## 2026-09-23 -0126 result: clean negative, byte-for-byte identical to 0124

Rebooted into 0126 with hub connected. Captured
captures/2026-09-23-0126-boot-kernel.log. User confirmed: no picture.

Trace is byte-for-byte identical to 0124's (and its clean-reboot
re-verification): same call counts (validate/connect/request_display each
#1, zero errors), same APCALL sequence (18, 10, 0), same "USB4: reselect
dpin after nub: 0", same DPRX=0 the whole way through, same 12s-later "DPRX
timeout, keeping DP tunnel" with identical register values. Removing the
PHY_MODE_DP switch alone did not change observable behavior at all.

Conclusion: this fix was a real correctness improvement (the tunnel PHY no
longer gets forced out of USB4/TBT mode) but not, on its own, sufficient to
unstick DPRX. Keeping it -- there is no reason to revert a fix that matches
both the reference implementation and our own tunnel-clock code's stated
requirement, even though it didn't resolve the symptom alone. Consistent
with the working theory: DCP's software protocol is fully clean (0124), and
the remaining gap is either something only the full PR#8 mechanism actually
exercises (real tunnel-established trigger, HPD_PROPAGATE pulse, NO_AUTO_LT
on the dock's DP OUT, proper crossbar-deferred-to-DidChangeLinkConfig
sequencing) or something deeper in DCP firmware/hardware not reachable from
Linux-side changes at all. Next: proceed with the full architectural port
scoped earlier (see /tmp/dcp-fw2/agent-portA-dcp-side.md and
agent-portB-tb-side.md for the complete function-by-function plan).

## 2026-09-24 -0127: full port of Thunderbolt DP tunnel routing from PR#8

0126's quick PHY-mode fix was a clean negative (byte-for-byte identical to
0124). Proceeded to the full architectural port scoped earlier: every
candidate through 0126 relied on faking a USB4 tunnel route through the
Type-C alt-mode mux-state machinery, never a genuine "a Thunderbolt DP
tunnel came up" trigger. Ported the real mechanism from
aurora-silicon/linux#8 (hardware-validated on t8103), adapted to
T602X/j416s. Full reasoning, architecture, and known-uncertainty notes in
notes/2026-09-24-0127-port-thunderbolt-dp-tunnel-routing.md.

Spans four modules for the first time this project: dcp.c/dptxep.c (new
apple_dcp_tb_dp_tunnel() entry point + dcp_tunnel_* helpers, ~400 lines of
superseded scaffolding removed), drivers/thunderbolt/apple.c (new
apple_dpin_ctx mechanism wired into this project's own already-safe
dp_tunnel_pre/post_activate/deactivate hooks -- zero changes to shared
tb.c/tunnel.c, thunderbolt.ko stays byte-identical), atc.c (renamed
tunnel-rate export, kept our T602X implementation), and
apple-display-crossbar.c (generalized the existing dpin0 bring-up helper
to any index). Confirmed before writing code: the device-tree graph link
the mechanism needs already exists on this hardware (walked the live
phandle), no DT change needed.

Only dcp.o/dptxep.o recompiled. New appledrm.ko SHA256:
28c219f2549dfba6a6182b5224588890fd1dc65baa9eb2072d0e31634a095395.
thunderbolt_apple.ko SHA256:
16b18fb9494d4f9b865748276bfb4c2c1df28c65da2598e93d46ed3e18eeb4ad.
mux-apple-display-crossbar.ko SHA256:
813682df2cfa01b0ee83daac9824a37a3290bf234b389035e483da6c5044c3df.
phy-apple-atc.ko SHA256:
31b68d51a454885081406089c99bae00617231c49cb99680586494d3c8a4a49f.
thunderbolt.ko unchanged (verified byte-identical). Module options also
changed: removed usb4_defer_bringup=1 (wrong semantics under the new
crossbar model, see design note) and usb4_tunnel_clock=1 from appledrm's
line (the module param it gated no longer exists). Stale-symlink sweep
clean, test-dpin-handshake.c 13/13 pass. Patch:
patches/0127-port-thunderbolt-dp-tunnel-routing-from-pr8.patch.
scripts/manage-0127.py hand-updated (first candidate changing more than
one module's hash at once, so not purely mechanical this time).

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0127.py install
```

## 2026-09-24 -0127 result: DPRX_DONE=1 achieved for the first time ever, wrong DCP pipeline found

Rebooted into 0127 with hub connected. Captured
captures/2026-09-24-0127-boot-kernel.log. **`apple_dcp_tb_dp_tunnel()`
fired correctly** ("display routed to Thunderbolt DP tunnel dpin0"), the
full connect sequence succeeded, DCP reached ACTIVATE, and then:
`DP IN CS changed ... DPRX=1`, `DP IN DPRX_DONE=1 (ACIO AUX completed)` --
the exact hardware signal this whole project has chased since it started,
achieved for the first time. DCP then sent SET_TILED_DISPLAY_HINTS and
several more apcalls but ultimately deactivated; the driver's own retry
ran the whole sequence again with the same result. User confirmed: still
dark.

Root cause found immediately from the same capture: every connect call
this boot targeted `apple-dcp 289c00000.dcp` (dcpext0, HDMI-capable, has a
fixed `phy@1303000000` dependency per the boot's own devicetree dump) --
not `315c00000.dcp` (dcpext1, USB-C only), the device every single prior
candidate's own working AFK exchanges always used. The route-scoring
simplification in 0127 dropped a fixed-output penalty
(`dcp_typec_route_score_usb4()`, removed) that used to keep the tunnel off
dcpext0. DPRX completing on dcpext0 anyway makes sense (AUX/DPRX is a
tunnel-layer physical signal, not DCP-instance-specific); dcpext0's
plane/CRTC/scanout wiring being wrong for a Type-C source plausibly
explains why it still gave up. Full reasoning in
notes/2026-09-24-0128-prefer-dcpext1-for-tunnel.md.

## 2026-09-24 -0128: restore the fixed-output route-scoring penalty

Kernel commit 68d4d8f: restored the same bias inline in
`apple_dcp_tb_dp_tunnel()`'s own scoring loop (`if
(candidate->dcp->fixed_phy) score += 100;`). Only dcp.o (and dptxep.o,
rebuilt incidentally, unchanged content) recompiled. New appledrm.ko
SHA256: 0102875210f5fd9aa0a8233e20abdde4894a2588947234e2cc8f2337577597ac.
Other three modules (thunderbolt_apple, mux, atc) unchanged from 0127.
Stale-symlink sweep clean, test-dpin-handshake.c 13/13 pass. Patch:
patches/0128-prefer-non-fixed-output-pipeline-for-tunnel-route.patch.
scripts/manage-0128.py derived from manage-0127.py (candidate number +
appledrm hash only, mechanical).

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0128.py install
```

## Last actions

- **0124** (instrumentation, no behavior change): closed several silent
  failure paths in `afk.c`/`dptxep.c` (DCP's real per-call retcode was
  captured and discarded; a failed apcall got no reply sent back to DCP at
  all; `request_display`/`release_display` had no logging; apcall payloads
  were never logged). Built, installed, tested on two independent clean
  boots — byte-identical result both times (see "current state" above).
  `notes/2026-09-23-0124-instrumentation.md`.
- **0125** (live parameter test, no kernel change): re-tested `dpin_aux=1`
  against the already-active tunnel (its setter fires immediately, no
  reboot needed). Reproduced the 0054-0056 "doesn't stick" result exactly.
  Reverted to 0 immediately after. `notes/2026-09-23-0125-dpin-aux-retest.md`.
- Cross-checked aurora-silicon/linux#8 in detail for any AUX/DPRX-specific
  mechanism we might be missing — found none; folded into "current state"
  above.
- Condensed this file from ~5750 lines to the current form; full verbatim
  history preserved in `notes/ACTION-LOG-ARCHIVE-2026-09-21-to-0125.md`.
