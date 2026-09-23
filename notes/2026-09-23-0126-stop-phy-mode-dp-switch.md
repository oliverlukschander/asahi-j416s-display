# 0126: stop forcing the USB4 tunnel's ATC PHY into DP mode

Direct continuation of the PR#8 port-scoping work. Found this while tracing
the exact mechanism that detects DPRX, before writing any of the larger port.

## What triggered this

Scoping the full aurora-silicon/linux#8 port (two parallel Opus 5.5 agents,
full function-by-function comparison against our tree -- see
`/tmp/dcp-fw2/agent-portA-dcp-side.md` and `agent-portB-tb-side.md`, not
committed here since they're scratch analysis, not project history) surfaced
that the PR **never changes the ATC PHY's mode for a tunnel route** and that
its tunnel-clock function requires the PHY to stay in USB4/TBT mode
(`-EBUSY` otherwise). Our own `apple_atc_right_usb4_tunnel_rate()`
(drivers/phy/apple/atc.c) has the identical gate:
`atcphy->mode == APPLE_ATCPHY_MODE_USB4`.

Separately, while tracing exactly where DPRX gets checked, found that
`tb_dp_activate()`/`tb_dp_dprx_start()`/`tb_dp_wait_dprx()`
(drivers/thunderbolt/tunnel.c) is a **generic, non-Apple-specific** mechanism
that polls the real hardware bit `DP_COMMON_CAP_DPRX_DONE` on the DP IN
adapter -- the exact bit stuck at `DPRX=0` in every capture since this
project started. This bit is set by PHY/ACIO hardware based on genuine AUX
electrical activity, downstream of anything DCP's software protocol does.
`tb_nhi_is_apple()` hardware deliberately doesn't block tunnel activation on
this bit ("DP tunnel paths up, not waiting for DPRX") and polls it
asynchronously, eventually giving up ("DPRX timeout, keeping DP tunnel") --
both are the exact log lines we've seen every single test.

## The bug

`dcp_dptx_connect()`'s analog-DPIN branch (`drivers/gpu/drm/apple/dcp.c`,
the exact branch confirmed active in every recent test via the
"USB4: skip lpdptxphy instantiate" / "USB4: analog DPIN bind" log lines) has
unconditionally called:
```c
phy_set_mode_ext(dp_route->phy, PHY_MODE_DP, dcp->index);
```
at connect time, since candidate 0118 -- before DCP ever gets to
ACTIVATE/SET_LINK_RATE, and present in every single candidate since
(confirmed: candidates 0119-0125 never touched this line). This forces the
tunnel's ATC PHY out of USB4/TBT mode into raw DisplayPort-signaling mode.
For a genuinely tunneled connection (DP-over-USB4-packets through the
Thunderbolt fabric, not direct electrical DP lanes), this is very plausibly
disrupting exactly the AUX/DPRX electrical path this whole project has been
chasing -- independent of anything DCP-protocol-level, which 0124 already
confirmed is completely clean.

## The fix (kernel commit 8dbf1b0)

Removed the `phy_set_mode_ext(dp_route->phy, PHY_MODE_DP, dcp->index)` call.
Kept `dcp->dptxport[bind].atcphy = dp_route->phy` (unrelated: it only tells
DCP firmware which PHY object to answer `GET_MAX_LANE_COUNT` against, per
the existing comment predating this change -- doesn't touch the PHY's
runtime mode). No other code path in our currently-active configuration sets
PHY_MODE_DP for this route: `dptxport_call_activate()`/`_deactivate()` in
dptxep.c take the `usb4_native_dpin && dcp_is_usb4_output(dcp)` branch (true
in our config), which calls `dptxport_native_dpin()` instead and never
touches PHY mode at all. This is a single, surgical, low-risk removal, not
part of the larger architectural port.

## Build verification

Only `dcp.o` recompiled. New `appledrm.ko` SHA256:
`a3ea4d4eed1d763fc696f89098d373bbd27b5331382eb6bdf1fe59c2aacac209`.
`phy-apple-atc.ko`, `mux-apple-display-crossbar.ko`, `thunderbolt_apple.ko`
and `thunderbolt.ko` all byte-identical to their known-good hashes (verified
via direct SHA256 comparison, neither touched). Stale-symlink sweep clean.
`test-dpin-handshake.c` 13/13 pass (this change never touches
`drivers/thunderbolt/apple.c`, pure regression check). Patch:
`patches/0126-drm-apple-dcp-stop-switching-usb4-tunnel-phy-to-dp-mode.patch`.

## Test plan

Same protocol, single boot, hub already connected. Watch specifically for:
1. Whether `DPRX` ever reaches 1 in the CS-register dumps (host DP IN and
   hub DP OUT), instead of staying at 0 through the 12s timeout.
2. Whether DCP proceeds past `ACTIVATE` this time -- `WILL_CHANGE_LINK_CONFIG`
   / `SET_LINK_RATE` apcalls appearing where they never have before.
3. The monitor itself, obviously.
4. If this doesn't produce a picture on its own, it doesn't invalidate the
   fix -- it may still be a necessary (not sufficient) precondition for the
   larger PR#8 port's mechanism to work when that's built. Either way this
   fix stands on its own: forcing a tunnel PHY into direct-DP mode is wrong
   regardless of what else changes.
