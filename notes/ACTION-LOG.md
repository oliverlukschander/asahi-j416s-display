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

## Current state (as of 2026-09-24, candidate 0129 prepared)

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

## Recent candidates (0126-0129)

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
  "DCP replies late and the host already stopped listening." Not yet
  installed/booted. `notes/2026-09-24-0129-widen-set-hpd-timeout-diagnostic.md`.

Currently installed and booted: candidate 0128
(`appledrm.ko` SHA256 `0102875210f5fd9aa0a8233e20abdde4894a2588947234e2cc8f2337577597ac`,
`thunderbolt_apple.ko`/`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko`
unchanged from 0127, hashes in `scripts/manage-0128.py`).

Candidate 0129 built and verified, not yet installed
(`appledrm.ko` SHA256 `131f3d85cad626e5387df05b55016f80dac60196cb5d555c4dc73503ab96a6a9`,
other four modules byte-identical to 0128, hashes in
`scripts/manage-0129.py`). To arm and test, after this commit is pushed:
```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0129.py check
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0129.py install
```
then reboot, reconnect if needed (hub may already be connected), and
capture `dmesg`/`journalctl -k` from this boot.
