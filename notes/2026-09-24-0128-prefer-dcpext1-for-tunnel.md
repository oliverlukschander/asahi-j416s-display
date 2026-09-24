# 0128: prefer dcpext1 (no fixed output) over dcpext0 for a DP tunnel route

Direct continuation of 0127's first boot. **DPRX_DONE=1 was achieved for
the first time in this entire project's history** -- the fix that matters
here is small, but the result it's fixing is the biggest single data point
this project has produced.

## What 0127's first boot actually showed

`apple_dcp_tb_dp_tunnel()` fired correctly: `"display routed to
Thunderbolt DP tunnel dpin0"`. The full connect sequence ran
(validate/connect/request_display, all `result=0`), DCP proceeded through
`ACTIVATE`, and then:

```
0:5: DP IN CS changed ... DPRX=1 disc=0
0:5: DP IN DPRX_DONE=1 (ACIO AUX completed)
```

DPRX asserting is the exact hardware-level signal this whole project has
been chasing since it started -- confirmed via the generic,
non-Apple-specific `tb_dp_wait_dprx()` polling this project traced back to
while investigating 0126. This is direct, hardware-level confirmation that
the architecture (crossbar routing via a real tunnel trigger, the ATC PHY
staying in USB4 mode, the native DPIN0 wake) is fundamentally correct and
sufficient for a genuine AUX/DPCD handshake to complete over this exact
hub/adapter chain.

DCP then sent `SET_TILED_DISPLAY_HINTS` (APCALL 21) and several other
apcalls, but ultimately `DEACTIVATE`d, and the driver's own retry logic
(`dcp_typec_reconnect_work`, pre-existing, not touched this candidate) ran
the entire connect sequence a second time -- same result, second
`release_display`. No picture.

## The bug: wrong DCP pipeline

`apple_dcp_tb_dp_tunnel()`'s route scoring used the reference PR's plain
`dcp_typec_route_score()` (CRTC index only). The function it replaced,
`dcp_typec_route_score_usb4()` (removed in 0127), also penalized a
pipeline with its own fixed output. The reference has no such bias because
t8103 has a single `dcpext`; j416s has two (`dcpext0`, HDMI-hybrid;
`dcpext1`, USB-C only), a difference the porting scoping already flagged
as project-specific (`notes/2026-09-24-0127-...md`, "known uncertainty").

Confirmed directly in the capture: this boot's connect calls all show
`apple-dcp 289c00000.dcp` -- **not** `315c00000.dcp`, the device every
single prior candidate's own working AFK exchanges used. The devicetree
dependency dump in the same boot log confirms `dcp@289c00000` carries a
fixed `phy@1303000000` (HDMI analog) dependency that `dcp@315c00000` does
not -- `289c00000` is dcpext0, `315c00000` is dcpext1. With HDMI
unplugged, `dcp_typec_route_available()` doesn't exclude dcpext0, and a
bare CRTC-index comparison let it win over dcpext1.

DPRX completing on dcpext0 anyway makes sense: DPRX/AUX is a
Thunderbolt-tunnel-layer, physical-signal concern, largely independent of
which DCP firmware instance is issuing the higher-level connect commands.
But dcpext0's plane/CRTC/scanout wiring is built around its fixed HDMI
output, not a Type-C-tunneled source -- plausibly why DCP still gave up
and never produced a picture despite the AUX handshake itself succeeding.

## The fix (kernel commit 68d4d8f)

Restored the same fixed-output penalty inline in
`apple_dcp_tb_dp_tunnel()`'s own scoring loop: `if
(candidate->dcp->fixed_phy) score += 100;`, matching what
`dcp_typec_route_score_usb4()` used to do. This should make dcpext1 win
the route whenever it's available, exactly as every prior candidate's
(protocol-level, pre-tunnel-mechanism) connect calls always used.

## Build verification

Only `dcp.o` (and `dptxep.o`, rebuilt incidentally, unchanged content)
recompiled. New `appledrm.ko` SHA256:
`0102875210f5fd9aa0a8233e20abdde4894a2588947234e2cc8f2337577597ac`.
`thunderbolt_apple.ko`, `mux-apple-display-crossbar.ko` and
`phy-apple-atc.ko` all unchanged from 0127 (verified). Stale-symlink sweep
clean, `test-dpin-handshake.c` 13/13 pass. Patch:
`patches/0128-prefer-non-fixed-output-pipeline-for-tunnel-route.patch`.

## Test plan

Same protocol, single boot, hub already connected. Watch specifically for:
1. Whether the connect calls now show `apple-dcp 315c00000.dcp` instead of
   `289c00000.dcp`.
2. Whether `DPRX_DONE=1` is reached again (it should be, since this fix
   doesn't touch anything AUX/DPRX-related directly -- it only changes
   which DCP instance handles the connection).
3. Whether DCP proceeds past `ACTIVATE`/the tiled-display-hints exchange
   this time without deactivating -- `SET_LINK_RATE` actually being
   accepted, and critically, the monitor itself.
4. If this still doesn't produce a picture, the next thing to check is
   whatever `SET_TILED_DISPLAY_HINTS` (APCALL 21, 144 bytes) actually
   contains -- new signal never seen before 0127, not yet examined in
   detail.
