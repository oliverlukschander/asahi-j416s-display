# 0138: don't let a departing dpout port skip dp_tunnel_deactivate

## What 0137's install confirmed, and the new mysteries

0137 was installed and confirmed working: the crossbar enables cleanly
(0136), `DPRX_DONE=1` is reached, `SET_ACTIVE_LANE_COUNT 4` is accepted,
and `dcp_dptx_connect()` no longer times out (0137). Hyprland picked up
the real monitor live ("BNQ BenQ LCD T4M01233019", correct EDID). Still
no picture (Oliver confirmed directly: nothing at all). Two new problems
surfaced, both root-caused by a second deep-research workflow (5
investigation angles + synthesis + 3 adversarial verifiers, all
`refuted: false`):

1. **~29s after the successful connect, DCP autonomously tears the link
   back down** (WILL_CHANGE_LINK_CONFIG -> lanes/rate to 0 ->
   DID_CHANGE_LINK_CONFIG, nothing logged as an error). Traced this as
   far as it goes from source: `dptxport_call()`
   (`drivers/gpu/drm/apple/dptxep.c:691`) is reachable *only* from
   firmware-initiated AFK/EPIC notify messages (`afk.c:441-482`) -- there
   is no kernel-side timer, workqueue, or delayed_work anywhere in this
   tree with a ~20-40s period (the one candidate, `usb4_hpd_wq`, is
   confirmed dead code -- `INIT_DELAYED_WORK`'d but never scheduled
   anywhere). The driver's reaction to WILL_CHANGE/DID_CHANGE
   (`dptxep.c:705-720`) is byte-for-byte equivalent to the
   hardware-validated reference (`refs/aurora-pr8`). **Conclusion: this
   specific ~29s figure and its trigger live in the closed-source IOMFB
   firmware and are not visible or fixable from this source tree.** A
   real, separate lead was found though: `iomfb.c:296-297`'s
   `dcp_retrain_active_crtc()` nudge (for a connected-but-unmodeset
   output) is explicitly gated `!dcp_is_usb4_output(dcp)` -- skipped for
   exactly this output type -- meaning the driver never tries to force a
   real modeset onto the tunnel connector while it's up. Not fixed this
   candidate (no proposed change survived as confidently as #2 below);
   see "Diagnostic not yet applied" below.

2. **A live physical unplug/replug of the monitor cable does not re-arm
   DCP's software connect flow**, even though the Thunderbolt/ACIO tunnel
   itself physically reforms (new device enumeration, "DP tunnel paths
   up" at the NHI level). This candidate fixes it. See below.

## Root cause for #2 (verified directly, and independently confirmed by 3 adversarial skeptics)

The chain, traced hop by hop and re-verified against the real files (not
inferred from log absence alone):

1. `apple_nhi_dp_tunnel_deactivate()` (`drivers/thunderbolt/apple.c:1171`)
   is the *only* place that clears `apple_dpin_ctx.alive` (line 1198) and
   unconditionally logs `"DP IN tunnel routing: tunnel down"` (line 1201).
   This string appears **zero times** in the full boot+replug capture
   (`captures/2026-09-24-0137-boot-and-replug-kernel.log`, 1724 lines),
   while its sibling activate-side string appears exactly twice (the
   original boot connect and the replug's own tunnel-up).
2. Since `c->alive` never flips false, `apple_dpin_work_fn()`
   (`apple.c:2226`) never reaches `apple_dpin_down()`
   (`apple.c:2199-2210`), so `c->handed` (set true on the original
   successful connect, `apple.c:2195`) is **never cleared**.
3. The replug's fresh `apple_nhi_dp_tunnel_post_activate()` genuinely
   fires again (confirmed: a real, distinct log line at the replug
   timestamp) and queues `c->work` -- but `apple_dpin_work_fn()` hits
   `if (c->handed) return;` (`apple.c:2243-2244`) and returns immediately,
   never calling `apple_dpin_up()` -> `apple_dcp_tb_dp_tunnel(active=true)`
   -> `dcp_dptx_connect()`. This is exactly why `dcp_dptx_connect(port`,
   `DPTX request_display`, and `display routed to Thunderbolt DP tunnel`
   each appear exactly once in the whole capture, only at the original
   connect, never again after the replug -- confirmed by direct grep.

**Why `apple_nhi_dp_tunnel_deactivate()` itself is never reached on a
real physical unplug** (this is the part that turns "plausible" into
"proven," and turns out to be generic Thunderbolt core code, not
Apple-specific):

- `tb_handle_hotplug()`'s unplug branch (`drivers/thunderbolt/tb.c:2466`)
  calls, in order: `tb_sw_set_unplugged(port->remote->sw)` (line 2471),
  then `tb_free_invalid_tunnels(tb)` (line 2472).
- `tb_free_invalid_tunnels()` (`tb.c:1778`) calls
  `tb_deactivate_and_free_tunnel()` (`tb.c:1725`), which calls
  `tb_tunnel_deactivate()` (`drivers/thunderbolt/tunnel.c:2769`), which
  **unconditionally calls `tunnel->activate(tunnel, false)` and discards
  its return value** (no `ret =` capture at all, line 2776).
- Inside `tb_dp_activate(tunnel, false)`
  (`drivers/thunderbolt/tunnel.c:1278`): `tb_dp_port_enable(src_port,
  false)` succeeds (the host's own adapter, never unplugged). But
  `tb_dp_port_enable(dst_port, false)` -- the hub's DP OUT adapter, which
  *is* on the switch just marked unplugged -- calls `tb_port_read()`/
  `tb_port_write()` (`drivers/thunderbolt/tb.h:705,719`), which have `if
  (port->sw->is_unplugged) return -ENODEV;` **with zero register I/O**.
  This is a deterministic, guaranteed software short-circuit, not a
  hardware-timing race.
- Back in `tb_dp_activate()`, `if (ret) return ret;` at what was line
  1350 fires on that guaranteed `-ENODEV`, returning **before** the
  function ever reaches `ops->dp_tunnel_deactivate(...)` (what was lines
  1373-1376) -- so `apple_nhi_dp_tunnel_deactivate()` is skipped on
  *every* ordinary physical unplug, not an edge case.
- Confirmed this is a structural gap versus the reference: `refs/aurora-pr8`
  doesn't fold this notification into the generic activate/deactivate
  register-programming path at all -- it has a dedicated
  `tb_dp_tunnel_notify()` (reference `tb.c:1729`), idempotent, called
  **unconditionally, first, and independent of any register I/O**, right
  at the top of `tb_deactivate_and_free_tunnel()` (reference `tb.c:1791`).

## The change

`drivers/thunderbolt/tunnel.c`, `tb_dp_activate()`: both `if (ret) return
ret;` checks (guarding `tb_dp_port_enable(src_port, ...)` and
`tb_dp_port_enable(dst_port, ...)`) changed to `if (ret && active) return
ret;`. `tunnel->activate` has exactly two call sites in the whole tree
(`tunnel.c:2748` for activate, `tunnel.c:2776` for deactivate, confirmed
by grep); the deactivate caller already discards the return value
entirely, so this is a no-op on that path's caller-visible behavior and
guarantees `ops->dp_tunnel_deactivate(...)` always runs on deactivation.
The activate (`active=true`) path is byte-for-byte unchanged (the
condition reduces to the original `if (ret)` whenever `active` is true) --
cannot regress the now-confirmed-working boot connect (0136+0137).

This is generic `drivers/thunderbolt/` core code, used by every DP
tunnel regardless of NHI vendor -- not an Apple-specific file. All three
adversarial verifiers independently confirmed this and found the fix
mathematically incapable of touching the activate path.

Same module set as 0137 otherwise (appledrm/atc/mux/thunderbolt_apple
unchanged, only `thunderbolt.ko` rebuilt: `tunnel.o` recompiled,
`thunderbolt.ko` relinked, `thunderbolt_apple.ko`'s hash is unchanged
since `apple.c` wasn't touched).

## Build verification

`make` in `src/thunderbolt/` (vermagic `7.1.12-2.5-1-ARCH`): only
`tunnel.o` recompiled, clean relink, no new warnings (confirmed via
`grep -i warning` excluding the known unrelated pahole-version notice).
`thunderbolt_apple.ko`'s sha256 confirmed unchanged
(`cfcd0fce...`). `python3 scripts/manage-0138.py check` (no sudo)
correctly refused while the external connector still reports
`connected` (a stale HPD/link status left over from the earlier connect
and replug attempts, not a real picture) -- this is the same safety
check every prior candidate's script has always had, working as
intended. Needs the monitor cable physically unplugged (not just
replugged -- HPD reasserts as soon as the ACIO tunnel reforms, even
without a full picture) before `check`/`install` will proceed.

## Known uncertainty

This fixes a real, confirmed, generic-Thunderbolt-core bug that
independently explains why a live replug never worked -- but it does not
address problem #1 (the ~29s autonomous teardown), which the research
concluded is very likely firmware-internal. Even with this fix, the
*original* boot-time connect may still hit the same ~29s teardown it hit
in 0137's own capture. What this candidate should make different: a
*replug after* that teardown should now genuinely re-arm DCP's connect
flow (a fresh `dcp_dptx_connect(port=0)`/`request_display`/"display
routed to Thunderbolt DP tunnel" should appear in the log after a replug,
which never happened in 0137's capture) -- worth testing with a replug
specifically, not just a fresh boot, to isolate whether this fix alone is
enough to reach a stable picture on a *second* attempt even if the first
still degrades after ~29s.

## Diagnostic not yet applied (problem #1, for a future candidate if needed)

The research proposed a single `dev_info` in
`dptxep.c`'s `DPTX_APCALL_WILL_CHANGE_LINKG_CONFIG` case, logging
`dcp->valid_mode`, `dptx->link_rate`, and `dptxport[0].connected` at the
moment of the autonomous teardown, to directly test whether
`valid_mode` was still false (i.e. no atomic modeset ever claimed the
connector) when firmware decided to retract the link. Not applied this
candidate -- keeping this candidate to the one confirmed, high-confidence
fix. Worth adding in a follow-up if problem #1 persists after this fix
and a stable connect via replug.

## Test plan

1. Ask Oliver to physically unplug the monitor cable from the hub
   (leave it unplugged for now).
2. Ask Oliver to run `sudo -n python3 scripts/manage-0138.py check` then
   `sudo -n python3 scripts/manage-0138.py install`.
3. Ask Oliver to reboot with the monitor cable still unplugged, then
   plug it back in once booted (to exercise the exact replug path this
   fix targets, and to see whether the first-ever connect attempt on this
   boot behaves the same as before).
4. Pull `dmesg --ctime`, save as `captures/2026-09-24-0138-boot-kernel.log`.
   Check: does a fresh `dcp_dptx_connect(port=0)`/`request_display`/
   "display routed to Thunderbolt DP tunnel" appear after the plug-in
   event (not just once at some earlier point), and does
   `"DP IN tunnel routing: tunnel down"` now appear if the link is ever
   torn down again. The only result that actually counts: is there a
   picture on the external display. Only Oliver's own visual confirmation
   counts as success.
