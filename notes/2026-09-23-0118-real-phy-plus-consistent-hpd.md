# 0118: attach a real per-port PHY and make supports_hpd consistent

Built via a 4-agent ultracode workflow (3 parallel investigations + 1 synthesis),
followed by additional manual verification of the highest-risk interaction before
building. Full workflow transcript: run id `wf_eaa02ec8-561`,
`/home/oliver/.claude/projects/-home-oliver-Development-omarchy-omalogimouse/5f1ab8f3-ac89-47b2-a5f9-8be67ac3a153/subagents/workflows/wf_eaa02ec8-561/journal.jsonl`.

## The three investigations

1. **Source + project history** (no decompiling): read the full current
   dcp_dptx_connect()/dptxep.c connect sequence and every relevant note
   (0078/0079/0088/0090/0092/0115/0116/0117), and diffed the exact AFK/EPIC
   APCALL sequence and target/core/atc values across three captured logs: the
   old working HDMI baseline, today's analog-DPIN attempt, and tonight's
   force_dptx/real-PHY attempt.
2. **DCP firmware decompile** (t602xdcp.bin, sha256 f3d919d6..., re-verified):
   force-created missing Function objects over connectTo/validateConnection
   (Ghidra's auto-analysis had disassembled but not "functionized" that region)
   and decompiled the real connectTo() handler.
3. **XNU kernelcache decompile** (kernelcache.macho, sha256 9615a486...,
   re-verified): traced AppleDCPDPTXRemotePortUFP::displayRequest() through
   Proxy::connectTo() and the AppleT602XATCDPXBAR/AppleCIODPTX validateConnection
   implementations to find the real IODPTXPortAttributes bit layout.

## What they found, reconciled

**The address was never the bug.** dcp_dptx_connect()'s analog-DPIN branch
(dcp.c:1561-1647) already validates/connects at target 0x8001 (core=1, atc=0,
die=dcp->dptx_die) -- the exact address the native DPIN0 crossbar handshake and
request_display (after the 0116 deadlock fix) already succeed at. DCP firmware's
own validateConnection only range-checks the core index against a hardware-
discovered port count; it doesn't reject a merely-different-but-valid target.

**The real gap, confirmed from two independent binaries:**
- DCP firmware's real connectTo() handler (0x00043e2c) gates its ONE
  first-connection callback (`call(*(this+0x248))`, the strongest available
  candidate for "kick off SET_LINK_RATE") on bit8 of the connect payload:
  bit8==0 fires it, bit8==1 skips it.
- XNU's IODPTXPortAttributes packs the identical bit -- bit8 == supportsHPD --
  at the identical position, in Proxy::connectTo()'s own payload, independently
  confirming this bit's identity rather than being a coincidental match.
- Our driver hardcodes `true` (bit8=1, "AP will supply HPD") for this exact
  connect() call (dcp.c:1599) and separately, unconditionally answers 1 to the
  GET_SUPPORTS_HPD APCALL for every Type-C/USB4 target regardless of
  `dcp_is_usb4_output()` (dptxep.c:600) -- so DCP is told twice, consistently,
  "don't bother training, the AP has this," and never does.
- Separately, `dptxport_call_get_max_lane_count()` short-circuits to a fixed
  4-lane analog answer whenever `dptx->atcphy` is NULL (dptxep.c:338), which it
  always is on this branch -- no path that uses this confirmed-correct address
  has ever attached a real PHY reference.

Both single-lever fixes were already tried in isolation and already failed:
denying HPD alone (without a PHY) regressed to DEVICE_NOT_STARTED at ~5.5s
(the comment above GET_SUPPORTS_HPD documents this); attaching a real PHY alone
(candidate 0088, `usb4_dptx` param) left eDP safe but never told DCP a PHY was
in play, so it still didn't train. `dcp_usb4_protocol_connect()` (the sibling,
right-port-only path) explicitly forbids combining a PHY with this address at
all (`if (dptx->atcphy) return -EBUSY`, dcp.c:1473-1476) -- confirmed in
notes/2026-09-21-0092-result.md as a deliberate, never-revisited choice. The
untried combination is doing all three at once, at the address already proven
correct.

## The fix (kernel commit 09dc764)

1. `dptxep.c` `dptxport_call_get_supports_hpd()`: answer
   `(dcp_is_typec_output(dcp) && !dcp_is_usb4_output(dcp)) ? 1 : 0` instead of
   ignoring `dcp_is_usb4_output()`.
2. `dcp.c`, analog-DPIN block: before validate/connect, if
   `dcp->active_typec_route->phy` is available, assign it to
   `dcp->dptxport[bind].atcphy` and call
   `phy_set_mode_ext(route->phy, PHY_MODE_DP, dcp->index)`.
3. `dcp.c`, the `dptxport_connect()` call in that same block: pass `!have_phy`
   instead of the hardcoded `true`.

`route->phy` is the per-port ATC PHY (`devm_phy_get(dev, "typecN")`, dcp.c:961),
the SAME object candidate 0088's `usb4_dptx` lever already used safely -- a
physically distinct object from the shared `usb4_lpdptx_phy`/`phy@39c000000`
that also drives eDP and that blanked it tonight (0117). This fix does not
touch `usb4_lpdptx_phy`, `usb4_force_dptx`, or `usb4_dptx_train` at all.

## Additional verification done before building (beyond the workflow's own output)

The synthesis flagged as an open risk that `dptxport_call_set_link_rate()` and
`dptxport_call_set_active_lane_count()` both skip `phy_configure()` whenever
`dcp_is_usb4_output(dcp)` is true, regardless of `dptx->atcphy` -- i.e. even if
this fix gets DCP to send SET_LINK_RATE/SET_ACTIVE_LANE_COUNT, would the driver
actually apply them to real hardware? Traced this manually before deciding
whether to patch it too:
- `set_link_rate` already has a complete, parallel, already-port-generic USB4
  mechanism instead: `dptxport_tunnel_clock()` -> `apple_atc_right_usb4_tunnel_rate()`
  (drivers/phy/apple/atc.c:2355), which despite its "right"-only name already
  uses `apple_atc_is_typec_core()` (the same port-generic helper 0115 added) to
  accept any of the three per-port ATC PHY addresses. Its own precondition
  (`atcphy->mode == APPLE_ATCPHY_MODE_USB4`) should already hold, since the
  hub's ordinary USB4/USB3 traffic (keyboard, etc.) already works through this
  same PHY all session.
- Checked whether `phy_set_mode_ext(route->phy, PHY_MODE_DP, ...)` (fix #2,
  above) could itself break that precondition by changing `atcphy->mode` away
  from USB4: `apple_atc_dp_phy_ops.set_mode` (`atcphy_dpphy_set_mode`,
  atc.c:2262) is a documented no-op ("nothing to do here since the setup
  already happened in mux_set") -- it does not touch `atcphy->mode` at all.
  So attaching this PHY cannot disturb the USB4 tunnel mode the hub's other
  traffic and the tunnel-clock mechanism both depend on.
- `get_max_lane_count()`'s `phy_validate()` call already has a graceful
  fallback for exactly this transitional state (`phy_ops.dp.lanes < 2` ->
  defaults to 4 lanes, dptxep.c:353-359, with its own comment anticipating
  "atc phy is not yet switched to DP mode") -- it cannot itself fail this
  attempt regardless of `atcphy->mode`.
- `set_active_lane_count`'s bare skip (no parallel mechanism, unlike rate) is
  most likely correct as-is: USB4 DisplayPort tunneling negotiates lane count
  as a logical/tunnel-bandwidth property, not a literal per-lane PHY register
  write the way a direct DP connection needs -- there is no evidence this is a
  gap, and patching it without evidence repeats a mistake this project's own
  history has flagged before (0092: "if it fails, do not infer which change
  was wrong"). Left untouched.

Conclusion: no fourth code change is warranted before testing. If SET_LINK_RATE
does fire and `dptxport_tunnel_clock()` itself fails or is skipped for a reason
not covered above, that is the next concrete, evidence-backed lever (not this
one, which is deliberately left alone for lack of evidence it's needed).

## Build verification

Only `dcp.o` and `dptxep.o` recompiled. New `appledrm.ko` SHA256:
`69ef18690a67d277ffaa0eac63bc3126fd3e2b41cdfb0e109373ec72122b4469`. No other
module changed. Stale-symlink sweep clean (same two pre-existing deferred
files as every candidate since 0115). `scripts/test-dpin-handshake.c` re-run,
13/13 scenarios still pass (untouched logic, regression check only). Patch:
`patches/0118-drm-apple-dptx-attach-a-real-per-port-PHY-and-match-.patch`.

## Test plan (single boot, no eDP-risk PHY touched)

`usb4_dptx_train` and `usb4_force_dptx` stay at their defaults (0/off) --
`usb4_lpdptx_phy`/the shared eDP PHY is never touched by this candidate at all.
Reconnect the hub (left port) after install+reboot and watch dmesg for, in
order:
1. The already-working lines unchanged: `DPTX validate/connect target=0x8001`,
   `native DPIN0: ... result=0`, `analog DPIN request_display core=1 atc=0: 0`.
2. The new line: `GET_SUPPORTS_HPD 0 usb4=1` (flipped from 1).
3. Whether `DPTXPort: SET_LINK_RATE` and a `get_max_lane_count` NOT logged as
   the old "USB4 DP IN, 4 lanes" shortcut actually appear.
4. Whether `DP IN ... DPRX=1` (the tunnel's real receiver-capability bit) ever
   sets, and whether `DPRX timeout, keeping DP tunnel` stops firing.
5. Oliver's own visual confirmation -- the only thing that actually counts.

Branches if inconclusive: (a) trained and DPRX locks -- done, pending visual
confirmation. (b) SET_LINK_RATE fires but DPRX still times out -- read
`dptxport_tunnel_clock()`'s own result log line first before any further
change. (c) GET_SUPPORTS_HPD/connect never progress past today's behavior, or
validate/connect itself now fails -- DCP firmware's own unresolved deeper
validation trampoline (found but not fully traced this session,
`FUN_001a7d40` inside connectTo()) may be rejecting this combination at a
level neither of tonight's fixes can reach; do not guess at further register
or target changes without a live firmware trace. (d) `get_max_lane_count`
logs a real `phy_validate` error -- read `atc.c`'s DP-mode validate path
before any further hardware attempt.

## Safety scope

No register address, APCALL method, or crossbar/ACIO mechanism beyond what's
already been exercised safely all project. The one new hardware action
(`phy_set_mode_ext` on `route->phy`) is the exact call already hardware-tested
safe for eDP in isolation by candidate 0088, now traced to also be provably a
no-op with respect to the USB4 tunnel mode state the rest of the hub's
functionality depends on.
