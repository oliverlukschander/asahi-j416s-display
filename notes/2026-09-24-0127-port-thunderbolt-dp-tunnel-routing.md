# 0127: port the real Thunderbolt DP tunnel mechanism from aurora-silicon/linux#8

Direct continuation of 0126. The quick PHY-mode fix alone didn't change the
observed behavior (byte-for-byte identical trace to 0124). This candidate is
the full architectural port scoped earlier via two parallel Opus 5.5 agents
(`/tmp/dcp-fw2/agent-portA-dcp-side.md`, `agent-portB-tb-side.md` -- scratch
analysis, not committed to this repo).

## Why the previous six candidates could never have worked

0118 through 0126 all patched a mechanism that fundamentally never had a
real trigger: `dcp_typec_route_set()` (the Type-C alt-mode mux-state
callback) faked a USB4 tunnel route into existence by scoring a
`usb4_xbar` candidate whenever it saw a USB4/TBT-SVID mux notification.
DCP's own AFK/EPIC protocol handling was already confirmed completely clean
end-to-end through ACTIVATE (candidate 0124: zero retcode errors, zero
reply mismatches, exactly the calls expected) -- the six candidates before
this one were all correctly-implemented fixes to a mechanism that was never
going to reach SET_LINK_RATE, because nothing about it resembled how a real
Thunderbolt DP tunnel actually gets routed to a display pipeline.

## What was ported, and what wasn't touched

Full details and the exact PR-vs-ours diff for every function are in the
two scoping documents above (not committed -- they're analysis artifacts,
not part of the project's permanent record; the kernel commit message
covers the same ground). Summary:

- **New cross-module interface** (`include/linux/soc/apple/dp-tunnel.h`):
  `apple_dcp_tb_dp_tunnel()`, `apple_atc_dp_tunnel_rate()`,
  `apple_dpxbar_link_up/down()` -- found via `symbol_get()`, so none of the
  four modules (appledrm, thunderbolt_apple, phy-apple-atc,
  mux-apple-display-crossbar) requires the others loaded.
- **dcp.c**: `dcp_typec_route_activate()`/`deactivate()` rewritten to defer
  a tunnel's crossbar select to `DidChangeLinkConfiguration`;
  `dcp_typec_route_set()` no longer creates tunnel routes at all;
  `apple_dcp_tb_dp_tunnel()` + `dcp_tunnel_crossbar_up/down()`/
  `set_rate()`/`dpin_activate()` added (this side is SoC-agnostic, ported
  close to verbatim); `dcp_dptx_connect()` collapsed from three
  USB4-specific branches to one path shared with direct alt-mode PHYs.
  ~400 lines of superseded experimental scaffolding removed
  (`dcp_usb4_arm_typec`/`auto_arm_work`, `dcp_usb4_protocol_connect`, the
  analog-DPIN bind loop, `lpdptxphy` instantiation, their module params).
- **dptxep.c**: SetLinkRate/Activate/Deactivate wired to the new
  `dcp_tunnel_*()` calls; WillChange/DidChange crossbar hooks moved into
  the apcall dispatcher; the ATC PHY is never switched to `PHY_MODE_DP` for
  a tunnel (0126's fix, folded in); `dptxport_remote_target()` drops the
  DPIN target field.
- **drivers/thunderbolt/apple.c**: a genuinely new decision here --
  **reused this project's own existing, already-safely-integrated
  `dp_tunnel_pre_activate`/`post_activate`/`deactivate` hooks** (already
  wired into `tunnel.c`'s `tb_dp_activate()` at the right lifecycle points)
  instead of porting the reference's separate `dp_tunnel_changed` NHI op.
  Same effect, and it meant **zero changes to shared Thunderbolt
  connection-manager code** -- `drivers/thunderbolt/{tb,tunnel}.c` are
  untouched, confirmed by `thunderbolt.ko` staying byte-identical. The new
  `apple_dpin_ctx`/`apple_dpin_connect()` machinery reuses this file's own
  confirmed-working DPTX_INACTIVE handshake (`apple_dpin_handshake()`,
  unchanged) rather than reinventing it, generalized to whichever DP IN
  adapter (0 or 1) a tunnel actually lands on instead of always dpin0. The
  confirmed-ineffective `dpin_aux` "analog AUX serializer" mechanism
  (2026-09-21 candidates 0054-0056, reconfirmed 2026-09-23 candidate 0125)
  is removed from the hot path; its diagnostic CS-register-change polling
  (`dp_aux_work`) is kept running for visibility.
- **atc.c**: `apple_atc_right_usb4_tunnel_rate()` renamed to
  `apple_atc_dp_tunnel_rate()` (matching the reference's symbol name),
  keeping our own T602X-specific implementation -- the reference's own
  version hard-fails off t8103's fixed AUSPLL descriptor. Now also accepts
  TBT mode, not just USB4.
- **apple-display-crossbar.c**: the existing, working
  `apple_dpxbar_right_dpin0_bring_up()` (kept, unchanged, still exported)
  generalized into `apple_dpxbar_link_up()`/`link_down()`, parameterized on
  whichever index/dispext is actually selected instead of always
  dpin0/source-2.

## Two things found and resolved *before* writing any code

1. **The device-tree graph link the reference needs
   (`of_graph_get_remote_node(acio_np, 1, -1)`, ACIO port@1 -> the Type-C
   connector) does not need adding.** One scoping agent's static `.dtsi`
   grep said it was missing; walked the actual live phandle
   (`/sys/firmware/devicetree/base/soc/cio@701ac0000/ports/port@1/endpoint/remote-endpoint`)
   before trusting that and found it already resolves correctly to
   `usb-pd@38/connector` on this exact hardware. No DT change in this
   candidate.
2. **`usb4_defer_bringup=1` (mux_apple_display_crossbar) must NOT be set
   under the new model.** It changes the T602X crossbar's `.set()` op to
   select the mux *without* enabling any clock gates, deferring that to a
   later explicit call -- which was fine for the old, hand-rolled
   activation sequence, but `dcp_tunnel_crossbar_up()`'s first bring-up
   only ever calls `mux_control_try_select()` (assuming, like the
   reference's own t8103 crossbar, that a fresh select brings everything
   up in one shot) and only calls `apple_dpxbar_link_up()` on a
   *re*-select. With the defer flag on, the gates would never be enabled
   on the very first connection. Removed from this candidate's module
   options entirely (defaults to off).

Also removed `usb4_tunnel_clock=1` from the `appledrm` options line
specifically (it stayed correct for `phy_apple_atc`, a separate module
parameter of the same name) -- `dptxport_tunnel_clock()`, the only thing in
appledrm that read it, no longer exists; leaving it in the options file
would have failed the whole module load with an unknown-parameter error.
`usb4_native_dpin`/`usb4_protocol_probe` are kept set: `usb4_native_dpin`
is still load-bearing in iomfb.c/iomfb_template.c for USB4-tunnel-specific
swap-completion logic outside this port's scope, composing with
`dcp_is_usb4_output()`, which still correctly reflects `route->tunnel`.

## Known uncertainty, flagged rather than hidden

`apple_dpxbar_link_up()`/`link_down()`'s generalization from the
DPIN0-only, source-2-only `t602x_right_dpin0_bring_up()` required guessing
the meaning of one 2-bit field (`T602X_FIFO_RD_N_CLK_EN`'s
`GENMASK(1,0)`-masked write) whose only prior evidence was a single
hardcoded `BIT(0)` value for DPIN0. Interpreted as `FIELD_PREP(GENMASK(1,0),
index)` (matching `MUX_DPPHY=0`/`MUX_DPIN0=1`/`MUX_DPIN1=2`, since `BIT(0)`
== 1 == `MUX_DPIN0`'s own enum value) -- documented inline, not silently
assumed. This code path is very unlikely to even be exercised by the next
hardware test: it only runs on a *re*-link (`WillChange`→`DidChange` after
a link rate is already set), and no candidate has ever gotten DCP past
`ACTIVATE` to begin with. `dcp_tunnel_crossbar_up()`'s *first* bring-up path
(`mux_control_try_select()` alone, exercising `apple_dpxbar_set_t602x()`'s
already-proven immediate-enable behavior) is what actually matters for this
test, and does not depend on this guess at all.

## Build verification

All four touched modules built and verified individually, each a clean
build with no errors (only one pre-existing-pattern unused-function
warning in apple.c, harmless). New SHA256 hashes:
- `appledrm.ko`: `28c219f2549dfba6a6182b5224588890fd1dc65baa9eb2072d0e31634a095395`
- `thunderbolt_apple.ko`: `16b18fb9494d4f9b865748276bfb4c2c1df28c65da2598e93d46ed3e18eeb4ad`
- `mux-apple-display-crossbar.ko`: `813682df2cfa01b0ee83daac9824a37a3290bf234b389035e483da6c5044c3df`
- `phy-apple-atc.ko`: `31b68d51a454885081406089c99bae00617231c49cb99680586494d3c8a4a49f`
- `thunderbolt.ko`: unchanged (`dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7`),
  confirmed byte-identical -- no shared Thunderbolt connection-manager code
  was touched.

Stale-symlink sweep clean. `test-dpin-handshake.c` 13/13 still pass (the
underlying handshake logic in `apple_dpin_handshake()` is unchanged, only
its caller is new). Patch:
`patches/0127-port-thunderbolt-dp-tunnel-routing-from-pr8.patch`.
`scripts/manage-0127.py` derived from `manage-0126.py`, with all four
changed hashes and the corrected `OPTIONS` string (see above) updated by
hand, not mechanically -- this is the first candidate to change more than
one module's hash at once.

## Test plan

Same protocol, single boot, hub already connected. This is a genuinely
different mechanism, not another bit flip, so watch for signals that don't
exist in any prior capture:
1. `dev_info` lines from the new code: `"DP IN tunnel routing: tunnel ..."`,
   `"dpinN: waiting for the display driver"` (if appledrm's symbol isn't
   ready yet), `"display routed to Thunderbolt DP tunnel dpinN"` (from
   `apple_dcp_tb_dp_tunnel()` itself -- this line firing at all is the
   single clearest signal the new trigger path is working).
2. Whether `DPTX validate`/`connect` now show a **different** `target=`
   value than every prior candidate (`core` should now be `dcp->dptx_dfp_port`,
   computed from real crossbar topology, not a hand-picked constant).
3. Whether DCP proceeds *past* `ACTIVATE` this time: `SET_LINK_RATE`,
   `WILL_CHANGE_LINK_CONFIG`, `DID_CHANGE_LINK_CONFIG` apcalls appearing for
   the first time ever.
4. Whether `DPRX` ever reaches 1, and obviously, the monitor itself.
5. If `apple_dcp_tb_dp_tunnel()` never gets called at all (no "display
   routed" line), check for the two warnings that would explain why:
   `"could not map port %u to a dpin index"` or
   `"no Type-C connector for dpinN"` -- the latter would mean the
   `connector_np` graph-walk assumption from this note's point 1 needs
   re-examining after all.
