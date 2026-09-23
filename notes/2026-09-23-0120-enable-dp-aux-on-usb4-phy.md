# 0120: enable the DP AUX sub-block on the USB4 tunnel PHY

Direct continuation of 0119. Oliver confirmed the exact same hub + cable +
Synaptics adapter + BenQ monitor chain works immediately on a real Mac
running macOS -- conclusively ruling out hardware/cable/adapter
compatibility as the remaining blocker. This is the piece of evidence that
justified going back into decompilation and, this time, back into the
project's own oldest notes (2026-09-21, before the "analog DPIN"/crossbar
mechanism existed) for anything previously identified and not yet revisited.

## What 0119 actually showed

0119 got DCP firmware to send `APCALL 20` (`DPTX_APCALL_INACTIVE_SINK_DETECTED`)
for the first time this session -- our own driver's comment already calls
this "the normal prelude to link training on USB4." DCP is actively trying
to AUX-probe the sink. But it never got a response and 12s later `DPRX
timeout` fired, exactly as every prior candidate. No amount of waiting
changed this (confirmed: checked the log 10+ minutes after the timeout,
nothing further happened).

## The missing piece, found in this project's own history

`notes/2026-09-21-t602x-dpin-mux.md` (written before the analog-DPIN
mechanism existed, using a different addressing scheme): "Each ATC has a
separate DP AUX block (`lpdptx`) that USB4 mode currently leaves off
(`enable_dp_aux = false`)." That exact gap is still present today, on the
*current* addressing scheme, confirmed by reading `drivers/phy/apple/atc.c`
directly: `atcphy_modes[APPLE_ATCPHY_MODE_USB4].enable_dp_aux = false`
(atc.c:811), and the only caller of `atcphy_enable_dp_aux()` is
`atcphy_set_mode()`, gated on that per-mode table entry
(`if (atcphy_modes[mode].enable_dp_aux) atcphy_enable_dp_aux(atcphy);`,
atc.c:2157-2158). Since 0118's PHY attachment never triggers a mode
transition (`phy_set_mode_ext(route->phy, PHY_MODE_DP, ...)` dispatches to
`atcphy_dpphy_set_mode()`, a documented no-op -- verified in 0118's own
design note), `atcphy_enable_dp_aux()` has never been called for this PHY
while it's in USB4 mode, in any candidate to date.

`atcphy_enable_dp_aux()` (atc.c:1377) is real, already-proven register
programming -- it's the same function the working direct-DP-alt-mode path
already uses via a full mode transition to `APPLE_ATCPHY_MODE_USB3_DP`/
`APPLE_ATCPHY_MODE_DP` (both have `enable_dp_aux = true`). It powers up the
`lpdptx` AUX transceiver sub-block: clears power-down bits, sequences
sleep/clamp bits with real delays, sets calibration values. Without it, the
AUX electrical path is powered down -- consistent with DCP's probe getting
no response (`INACTIVE_SINK_DETECTED`) rather than any higher-level
protocol failure.

## Why this doesn't just do a full mode switch to DP

Switching `atcphy->mode` away from `APPLE_ATCPHY_MODE_USB4` would
reprogram the crossbar/lane_mode/dp_lane fields that the *entire* USB4
tunnel (not just DP) depends on -- including the hub's USB3/USB2 fabric
carrying Oliver's keyboard and other peripherals. That's a much larger,
harder-to-reason-about change with a correspondingly larger blast radius.
`atcphy_enable_dp_aux()` itself only touches the separate `lpdptx` register
region (a permanently-mapped resource, confirmed via
`{ "lpdptx", &atcphy->regs.lpdptx, NULL }` in the probe-time resource
table) plus a `DP_CFG_BLK_TX_DP_CTRL0`/`PLL_COMMON_CTRL` register pair
whose naming is DP-specific, not shared USB4 SERDES state. Explicit,
informed risk accepted by Oliver before building this: if this interaction
is wrong in some undocumented way, the worst case is disrupting the ATC
PHY's USB4 tunnel state entirely, which could take down the hub's USB
peripherals along with DP, not just fail to produce a picture.

## The fix (kernel commit 7435260)

- `drivers/phy/apple/atc.c`: new exported `apple_atc_usb4_enable_dp_aux(struct
  phy *phy)`. Same validation pattern as the existing
  `apple_atc_right_usb4_tunnel_rate()` (phy ops match, machine/PHY
  compatible, correct core address via `apple_atc_is_typec_core()`), plus a
  new `atcphy->mode == APPLE_ATCPHY_MODE_USB4` guard (refuses if the PHY
  isn't actually in USB4 mode, since this call is meaningless/unsafe
  otherwise). Calls `atcphy_enable_dp_aux(atcphy)` directly under the
  existing `atcphy->lock` mutex -- no mode-table lookup, no crossbar/
  lane_mode/dp_lane reprogramming.
- `drivers/gpu/drm/apple/dptxep.c`/`.h`: new `dptxport_usb4_enable_dp_aux()`
  wrapper using the same `symbol_get()`/`symbol_put()` cross-module pattern
  already established for `apple_atc_right_usb4_tunnel_rate`.
- `drivers/gpu/drm/apple/dcp.c`: call it in the analog-DPIN block, right
  after 0118's PHY attachment (`dcp->dptxport[bind].atcphy = dp_route->phy;
  phy_set_mode_ext(...)`), logging the result.

## Build verification

`phy-apple-atc.ko` and `appledrm.ko` both changed (this is the first
candidate since the port-generalization work to touch two modules at
once). New hashes: atc
`2feeec3f8501ce51e51b4a85f22a91e7fea3f0a57037d9dfdabed257e2249d8b`,
appledrm `b401f2913e55206c7b2dc2249e804c29d92e19b5af35baca6f1f1d91f00d9cf5`.
Stale-symlink sweep clean, `test-dpin-handshake.c` 13/13 still pass. Patch:
`patches/0120-phy-apple-drm-apple-enable-DP-AUX-on-the-USB4-tunnel.patch`.

## Test plan

Same protocol as every candidate: single boot, hub reconnect on the left
port, watch dmesg for `USB4: enable DP AUX on route->phy: 0` (confirming
the new call succeeded, not `-EBUSY`/`-EINVAL`/`-EOPNOTSUPP`), then whether
`INACTIVE_SINK_DETECTED` either doesn't fire at all this time or is
followed by `SET_LINK_RATE`/`SET_ACTIVE_LANE_COUNT`, and finally whether
`DP IN ... DPRX=1` ever appears and `DPRX timeout` stops firing. Watch
`lsusb`/hub-connected peripherals (keyboard) immediately after this boot
to confirm the USB4 tunnel's other traffic is genuinely unaffected, per
the risk accepted above.
