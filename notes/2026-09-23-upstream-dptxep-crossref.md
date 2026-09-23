# Cross-referencing Asahi community DPTX work against our own driver

Following up on the question of why no official documentation exists for the
DCP/DPTX activation sequence: surveyed every relevant branch in the
`AsahiLinux/linux` GitHub repo for prior art on DisplayPort-over-USB4-tunnel,
and diffed the key commits against our own `drivers/gpu/drm/apple/dcp.c` and
`dptxep.c`.

## What exists upstream

- `dcp/dptx-fixes` (Janne Grunau, Hector Martin): the real, mature AFK/EPIC
  "dptxep" implementation -- `dptxport_connect()`, `dptxport_validate_connection()`,
  `dptxport_request_display()`, `dptxport_set_hpd()`, and DCP-initiated APCALLs
  (`DPTX_APCALL_ACTIVATE`, `set_active_lanes`, drive-settings). This is the
  code that drives DP alt-mode / direct HDMI output today, and one commit is
  explicitly titled "port interface to macOS 13.5 firmware" -- our exact DCP
  firmware version.
- `bits/171-dptxphy`, `bits/270-thunderbolt`, `dp-altmode-WIP`, `tbt-reset-wip`,
  `b4/apple-soc-tbt`, `sven/tbt-wip`: all either superseded historical
  ACIO/NHI/DROM/ATC-PHY bring-up work that is already mainlined (the same
  baseline our `thunderbolt_apple`/`phy_apple_atc` drivers build on), or
  generic (non-Apple) thunderbolt-core plumbing. None contain DPIN-crossbar
  or USB4-DP-tunnel-activation-specific logic beyond what's already in our
  tree.

## What we already have

Our `dcp.c`/`dptxep.c` is not a naive from-scratch reimplementation sitting
beside the AFK/EPIC path -- it *is* the AFK/EPIC path, extended. Confirmed by
direct comparison:

- `dptxport_connect()`'s "unk" field: upstream's `72a5222ba9` replaced a
  hardcoded `0x100` with a variable defaulting to `0` ("seen as 0x100 under
  some conditions") and downgraded the reply mismatch from a hard error to a
  notice. Our version (dptxep.c:178) already went further, deriving it as
  `supports_hpd ? DCPDPTX_REMOTE_PORT_SUPPORTS_HPD : 0` with the same lenient
  `dev_notice` check -- functionally ahead of upstream's fix.
- `DPTX_APCALL_ACTIVATE` handling: upstream's `0bf95b0ffd` adds
  `dptxport_call_activate()` calling `phy_set_mode_ext(dptx->atcphy,
  PHY_MODE_DP, dcp->index)` unconditionally. Ours (dptxep.c:685-706) already
  branches on `usb4_native_dpin && dcp_is_usb4_output(dcp)` to skip the
  physical PHY mode-set entirely for the tunneled case and instead invoke our
  own `dptxport_native_dpin()` -> `apple_usb4_right_dpin0_set_active()` --
  correctly recognizing that DPIN0 is not a PHY the AP should mode-switch.
- `dcp_dptx_connect()` missing-unlock bug: upstream's `86b5c3ad44` fixes a
  `return 0` that skips `mutex_unlock(&dcp->hpd_mutex)` when a port is already
  connected. Our rewritten version (dcp.c:1634-1635) already uses
  `goto out_unlock` on that exact path -- not affected.
- Drive-settings APCALLs (`2271fd976e`): cosmetic completeness for
  get/set link-training drive settings used during real link training. Not
  reached in our case since USB4-native-DPIN mode short-circuits before a
  physical PHY link-training handshake ever starts.

## Conclusion

The upstream "combine findings" request has been done: there is no
undiscovered fix sitting in the Asahi community tree, published or
unpublished, that addresses our specific failure. The project's own core DRM/
DCP maintainers (Janne Grunau, Hector Martin) have, as of the `dcp/dptx-fixes`
branch, matured the *direct* DPTX path (physical ATC PHY / DP alt-mode) to
macOS 13.5 firmware parity, but have not published any USB4-DPIN-crossbar
tunnel-specific work -- consistent with the public v2 patch series marking
DP-over-USB4-tunnel as needing "more reverse engineering." Our own branch has
already independently reached, and in the tunnel-specific bits exceeded, the
most advanced point anyone in the Asahi project has reached publicly.

This does not change the standing conclusion from 0106-0110: the two
DPIN0-offset register values (0x14/0x1c) most likely originate inside the DCP
coprocessor firmware itself (not the XNU host kernelcache, and not anywhere
in Linux prior art), and remain unresolved. No new register value, RPC verb,
or sequencing change is indicated by this cross-reference. No hardware action
taken; nothing to log in ACTION-LOG.md.
