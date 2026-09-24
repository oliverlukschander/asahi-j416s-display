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

## Current state (as of 2026-09-24, candidate 0132 prepared)

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

**Candidate 0131 prepared, awaiting Oliver's install+reboot.** Ports just
this one piece (the HPD-propagate pulse), gated on the same pre-existing
`tb_nhi_is_apple()`/`tb_port_is_dpin()` checks so it's a no-op for any
non-Apple host or non-DP-IN tunnel. Deliberately not ported yet: the
reference's `NO_AUTO_LT` hold-off on the hub's DP OUT adapter, and its
5-NFC-credit override for the DP IN video hop -- both real, both part of
the same commit, held back to keep this one variable at a time.

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

## Recent candidates (0126-0132)

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
  0131. Ports the other two pieces of the same hardware-tested commit,
  held back from 0131 to keep that a single-variable test: `ADP_DP_CS_3_
  NO_AUTO_LT` holding the hub's DP OUT adapter off its own link training
  while the tunnel is up, and a hardcoded 5 NFC credits for the DP IN
  video hop (this project's own captures have shown 1/0 there every run).
  Not yet installed/booted.
  `notes/2026-09-24-0132-no-auto-lt-and-video-credits-apple-host.md`.

Currently installed and booted: candidate 0131
(`thunderbolt.ko` SHA256 `fd5f7196144fc760459f71cac094d19901c554531e96ab6c2c68096c7e9b7465`,
`thunderbolt_apple.ko` SHA256 `4bd921e908a491ddc3ccd2dfd701fb39ae015df2824f0ad9862ca8ca71ef314d`,
`appledrm.ko`/`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko` unchanged
from 0130, hashes in `scripts/manage-0131.py`).

Candidate 0132 built and verified, not yet installed
(`thunderbolt.ko` SHA256 `459250fe65adc5066f64f9b9b91c8f8b291e6e96b648de4d95bb0222afe4a5b9`,
`thunderbolt_apple.ko` SHA256 `91caddc7f37594c6d326b01562656f12d99c8e0b67adc2bde84d3df75645368b`
(source unchanged, rebuilt against the new tb_regs.h/tunnel.o),
`appledrm.ko`/`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko` unchanged
from 0130/0131, hashes in `scripts/manage-0132.py`). To arm and test,
after this commit is pushed:
```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0132.py check
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0132.py install
```
then reboot, and capture `dmesg`/`journalctl -k` from this boot.
