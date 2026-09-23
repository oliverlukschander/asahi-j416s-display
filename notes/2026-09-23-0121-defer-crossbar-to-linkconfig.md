# 0121: defer crossbar/DPIN0 activation to DidChangeLinkConfiguration

The real fix, found via a real, hardware-tested reference implementation rather than
further guessing. Oliver pointed at aurora-silicon/linux#8, "DisplayPort and PCIe
over Thunderbolt for M1 (t8103)" -- a complete, hardware-validated (CalDigit TS3
Plus, Kensington SD5560T, three different docks) DisplayPort-over-Thunderbolt-tunnel
implementation, explicitly built on Oliver's own earlier t6020 tunnel-clock work for
this exact project. This closes the loop on tonight's 0120 regression and finally
identifies the real, structural bug behind every one of this session's stalls.

## What the reference PR actually does differently

Its `dcp_dptx_connect()` uses the *same* connect path our own driver already has --
`dptxport_validate_connection()`/`dptxport_connect()` with a real PHY attached
(`dptx->atcphy = dcp->phy`) -- just addressed via a `dptx_dfp_port` field (0=dpphy,
1=dpin0, 2=dpin1, matching exactly the "port" bitfield an earlier decompile pass
found in the real XNU IODPTXPortAttributes struct) instead of our "core/atc" scheme.
It never touches DP AUX or any PLL-common-control-style register at all -- confirming
0120's whole approach was built on the wrong mental model.

The actual key difference is **ordering**, laid out explicitly in its own code
comments:
- `Activate` only wakes the DP IN adapter (`dcp_tunnel_dpin_activate()`) -- it does
  **not** select the crossbar mux.
- `SetLinkRate` starts the tunnel pixel clock (`dcp_tunnel_set_rate()` ->
  `apple_atc_dp_tunnel_rate()` -- architecturally identical to, and explicitly
  descended from, our own already-existing `apple_atc_right_usb4_tunnel_rate()` /
  `atc_tunnel_start()`).
- `DidChangeLinkConfiguration` -- **only once `dptx->link_rate` is already set** --
  is where the crossbar mux actually gets selected
  (`mux_control_try_select()` in `dcp_tunnel_crossbar_up()`).
- `WillChangeLinkConfiguration` takes the crossbar back down first, before any
  relink.

## The bug this exposes in our own driver

Re-reading our own `dptxep.c` with this in hand: `dptxport_call_did_change_link_config()`
**already has** this exact mechanism, already correctly gated on `dptx->link_rate`,
with a comment that already states the right idea ("Native ATCDP brings the
connection up after setting a nonzero link rate. ACTIVATE alone precedes that clock
configuration.") -- but `dptxport_call_activate()` **also**, unconditionally, calls
`dptxport_native_dpin(service, true, false)`, which does the crossbar mux selection
*and* the ACIO DPIN0 wake handshake immediately, before DCP has ever set a link rate.

This means our driver has been routing a real analog signal path through the
crossbar before any pixel clock exists to drive it, every single time, all session.
DCP's own AUX probe of the sink over that prematurely-routed, clockless path finds
nothing coherent (`INACTIVE_SINK_DETECTED`, confirmed in the 0119 test), and since
nothing about the connection state changes afterward, DCP has no reason to retry --
it never proceeds to `SET_LINK_RATE`, so `dptxport_tunnel_clock()` (already
correctly wired into `dptxport_call_set_link_rate()` for exactly this case) never
even gets a chance to run, and `dptxport_call_did_change_link_config()`'s own
already-correct crossbar bring-up is never reached either.

## The fix (kernel changes, net diff below)

1. **Remove** the eager `dptxport_native_dpin(service, true, false)` call from
   `dptxport_call_activate()`. Activate now does nothing hardware-related for the
   native-DPIN0/USB4 case -- it just replies success immediately, exactly matching
   the reference implementation's own division of labor (their Activate handler
   doesn't select the crossbar either).
2. **Revert** 0118's `GET_SUPPORTS_HPD`/`dptxport_connect()` `supports_hpd` changes
   back to their original, pre-0118 values. The reference PR's own `attrs`/`unk`
   field for a tunnel route keeps `supportsHPD` (bit 8) set exactly like a direct
   connection -- what actually distinguishes a tunnel route is a *separate* new
   "role" bit (bit 0: 0=direct PHY, 1=Thunderbolt DP IN) that has no equivalent in
   our driver yet. Flipping supportsHPD was based on a plausible-but-wrong theory;
   the working baseline's own GET_SUPPORTS_HPD=0 was for an unrelated, genuinely
   direct (non-tunneled) connection, not evidence about the tunnel case at all.
3. **Fully remove** 0120's `apple_atc_usb4_enable_dp_aux()` (atc.c),
   `dptxport_usb4_enable_dp_aux()` (dptxep.c/.h), and its call site (dcp.c). Verified
   byte-for-byte: the rebuilt `phy-apple-atc.ko` hash now exactly matches 0119's
   already-known-good hash (`fb748d4b...`), confirming atc.c is fully, cleanly
   reverted -- zero risk of a repeat of tonight's tunnel-disconnect regression, since
   the code touching that PHY is now byte-identical to the last state that never
   caused it.
4. **Keep** 0118's PHY attachment (`dcp->dptxport[bind].atcphy = dp_route->phy;
   phy_set_mode_ext(dp_route->phy, PHY_MODE_DP, dcp->index);`) and 0119's guard
   relaxation in `dptxport_native_dpin()` (removing the `dptx->atcphy` check) --
   both match the reference implementation's own pattern (`dptx->atcphy = dcp->phy`,
   `phy_set_mode_ext()` called unconditionally in their Activate handler) and remain
   necessary once the crossbar activation itself is correctly deferred.

Net diff: 26 insertions, 98 deletions across dcp.c/dptxep.c/dptxep.h/atc.c -- this
candidate is smaller than 0118 by itself, because it removes far more than it adds.

## Known pre-existing issue, deliberately not touched

`dptxport_call_did_change_link_config()`'s `usb4_link_up_attempted` latch is never
reset (only `usb4_link_up_rate` is, on deactivate/rate-zero). If this test succeeds
once and then a *second* connect attempt happens later (unplug/replug, or a second
hotplug on the same boot), that second attempt would hit `return -EALREADY` instead
of re-running the crossbar bring-up -- the same class of stale-latch bug 0113 already
found and fixed once for `dpin_attempted`. Not fixed here since it cannot affect
tonight's test (this is the first time this code path will ever execute on a fresh
boot); flagged for a follow-up if a replug scenario is ever needed.

## Build verification

Only `dcp.o`/`dptxep.o` (appledrm) and `atc.o` (phy-apple-atc, pure revert)
recompiled. New `appledrm.ko` SHA256:
`15dd9b2346879b3b771200a45362ad81e281fde158d3fae7632369073c5b6ca8`. `phy-apple-atc.ko`
SHA256 `fb748d4ba55e467dad4eaca6f4045059200aea46eccbd8a1bd2165025a95cf7f` -- identical
to 0119's, confirmed via direct hash comparison. Stale-symlink sweep clean,
`test-dpin-handshake.c` 13/13 still pass.

## Test plan

Single boot, hub reconnect on the left port. Watch dmesg for, in order: the
already-working `DPTX validate/connect target=0x8001`, `analog DPIN request_display
core=1 atc=0: 0` (unchanged), then whether `native DPIN0: active=1 ...` /
`native DPIN0: DCP active=1 result=...` now appear **later**, tagged from
`dptxport_call_did_change_link_config()` ("native DPIN0: link-config up rate=0x%x
result=%d") rather than immediately after `APCALL 0`, and specifically whether
`DPTXPort: SET_LINK_RATE` appears at all before that -- this is the concrete signal
that the reordering worked. Then whether `DP IN ... DPRX=1` ever sets and `DPRX
timeout` stops firing. This does not touch the shared eDP PHY or the AUX/PLL
register that caused tonight's disconnect at all, so hub USB functionality should be
completely unaffected regardless of outcome.
