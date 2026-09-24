# 0131: pulse HPD propagation on the DP IN adapter (ported from aurora-silicon/linux#8)

Direct continuation of the 0128-0130 chain. Oliver asked for a comprehensive
comparison against the reference implementation (aurora-silicon/linux#8,
t8103/M1, hardware-tested on three docks and multiple monitors) to find out
why it works there and not here. This note is that comparison, and the fix
it turned up.

## Method

Fetched the actual PR (`git fetch https://github.com/aurora-silicon/linux.git
pull/8/head`) and diffed it against its own merge-base with this project's
tree (`2439016`, a "Merge pull request #2 from maralcbr/fix/drm-apple-stale-
dptx-link" that both trees share -- `aurora-wip` already mirrors the same
upstream). `git diff --stat` : 24 files, +2008/-108. Read every commit
message and the full diff for every file relevant to display: `dcp.c`,
`dptxep.c`, `drivers/thunderbolt/{apple,tb,tunnel,switch}.c`, `atc.c`,
`apple-display-crossbar.c`. (PCIe tunneling, IOMMU and the placeholder-EDID
fix are real parts of the same PR but not relevant to the current blocker;
noted below, not acted on.)

## What's already correctly ported (no new finding here)

`dcp.c`'s `dcp_typec_route_activate/deactivate()`, `dcp_tunnel_crossbar_up/
down()`, `dcp_tunnel_set_rate()`, `dcp_tunnel_dpin_activate()`, and
`apple_dcp_tb_dp_tunnel()` all match the reference closely -- this is what
0127 already ported, and re-reading it against the actual PR source (rather
than the two ephemeral scoping-agent transcripts from that session, which
weren't committed anywhere) turned up nothing missing on the DCP side.
`dptxep.c`'s role-bit attribute and the `WillChange`/`DidChange` ->
`dcp_tunnel_crossbar_down/up()` wiring also match.

## What's missing: HPD never gets told to propagate

The reference's Thunderbolt-side commit (`4a7fd72`, "thunderbolt: DP tunnels
from Apple silicon host DP IN adapters") does four things in **generic**
`drivers/thunderbolt/tb.c`/`tunnel.c`, all gated behind a `tb_port_is_apple_
host_dpin()` check so they're a no-op for any non-Apple host:

1. **Pulse `ADP_DP_CS_3_HPD_PROPAGATE` (bit 10) on the DP IN adapter for
   10ms, then wait up to 2s for `ADP_DP_CS_2_HPD`** (via `tb_dp_port_hpd_
   is_active()`), right after the tunnel's paths are activated. The commit
   message states the reason plainly: *"On Apple silicon the display engine
   is not wired to the host router's DP IN adapters"* -- there's no real
   physical DP connector, so nothing else ever sets that adapter's own HPD
   bit. Every downstream USB4 DP tunnel mechanism (AUX/DPCD negotiation,
   `DPRX`) is gated on it having been told to propagate.
2. Hold the hub-side DP OUT adapter's link training off
   (`ADP_DP_CS_3_NO_AUTO_LT`, bit 8) while the tunnel is up, since the host's
   own DPTX trains the sink through the tunnel instead.
3. Give the DP IN video hop 5 NFC credits specifically for Apple hosts.
4. Skip Titan Ridge's LTTPR-non-transparent workaround for an Apple host's
   own tunnel (not relevant to our hub).

0127's own note already explained, correctly, why this project's port
avoided touching `tb.c`/`tunnel.c`: it reused this project's pre-existing
`dp_tunnel_pre/post_activate/deactivate` hooks instead of the reference's
separate `dp_tunnel_changed` NHI op, specifically to keep `thunderbolt.ko`
byte-identical and touch zero shared connection-manager code. That choice
was right for the *routing trigger* (its own job), but it also meant these
four register-level steps -- which live in the reference's generic code
alongside the trigger, not behind it -- were never carried over. Confirmed
by direct search: zero references anywhere in this tree, before this
commit, to `ADP_DP_CS_3_HPD_PROPAGATE`, `NO_AUTO_LT`, `tb_dp_tunnel_notify`,
or `tb_port_is_apple_host_dpin`.

## Why this is a strong, not merely plausible, match for the current symptom

`apple_dp_aux_work()` (this project's own diagnostic poller, unrelated to
anything from the reference) independently samples the DP IN adapter's
CS0-CS13 registers every 500ms for up to 12s and logs `"DP IN CS changed
..."` on any difference, completely decoupled from DCP/AFK timing. Across
all four dcpext1/right-port failures so far (0128 x2, 0129, 0130 -- 96
samples), it logs **zero** changes. In the one dcpext0/left-port success
(0127), it logs **exactly one** (the DPRX transition itself). An
unpropagated HPD is a direct, mechanistic explanation for registers that
never move at all: if the adapter's own state machine never considers a
display "plugged in" at the protocol level, it has no reason to ever
attempt AUX/DPCD with the sink, and nothing in that register block would
ever change.

This does not, on its own, explain why 0127 worked *without* this pulse.
Two honest possibilities, neither confirmed: residual HPD state left on
the *left* port's specific ACIO instance from earlier, unrelated direct-
connection activity this same boot (this project's own hardware notes
already record that direct HDMI/adapter connections on these same physical
ports work); or a genuine difference between the two ACIO instances --
which would not be new news, since a still-active workaround from an
earlier candidate (`dp_bw_grant`, `notes/ACTION-LOG.md`'s hardware
reference / `tunnel.c`) already documents that *this exact* right-side
adapter "has never been observed to generate a bandwidth request
notification," a different but analogous asymmetry on the same hardware.
Either way, the absence of this specific, hardware-tested mechanism on the
side that fails, and its presence (implicitly, in the reference) on the
side that's known to work, is the most concrete, mechanistically-explained
lead this project has had since 0127's own architectural port.

## The change (kernel commit 63955f6)

Added `ADP_DP_CS_3_HPD_PROPAGATE` (`drivers/thunderbolt/tb_regs.h`, next to
the existing `ADP_DP_CS_3_HPDC`) and `tb_dp_apple_pulse_hpd()`
(`drivers/thunderbolt/tunnel.c`), a close port of the reference's own pulse
logic, reusing this tree's pre-existing `tb_dp_port_hpd_is_active()` and
`tb_nhi_is_apple()`/`tb_port_is_dpin()` helpers rather than reinventing
them. Called from `tb_dp_activate()` right before this project's own
`dp_tunnel_post_activate` hook, so the DCP glue routes a display only after
HPD has actually propagated -- preserving the reference's own ordering
intent even though our hook lives one level deeper in the call stack than
its `dp_tunnel_changed` callsite (reference: tunnel activates -> pulse ->
notify glue, all in `tb.c`; here: tunnel activates -> pulse -> notify glue,
all inside `tb_dp_activate()` itself). Gated on `tb_nhi_is_apple(tunnel->tb-
>nhi) && tb_port_is_dpin(tunnel->src_port)`: zero effect on any non-Apple
host or non-DP-IN tunnel. A failed pulse is logged (`"HPD did not
propagate"` or a read/write error) and the tunnel setup continues
regardless -- not a fatal error -- matching the reference's own
non-blocking handling exactly.

## Known uncertainty / deliberately deferred

- **Not ported this candidate:** `ADP_DP_CS_3_NO_AUTO_LT` (hub-side DP OUT
  hold-off) and the 5-NFC-credit override for the DP IN video hop. Both are
  real parts of the same hardware-tested commit, but they operate on a
  different adapter (dst_port, not src_port) and a different resource
  (video-stream credits, not the control-plane/AUX-adjacent HPD signal)
  respectively -- keeping this candidate to the one variable most directly
  implicated by the CS-register evidence. If HPD now propagates
  (`"Apple: HPD propagated"` in the log) but DPRX still never asserts, these
  two are the next things to port, in that order.
- **If the pulse itself fails** (`"cannot read/pulse/end HPD propagation"`,
  or `"HPD did not propagate"` after the full 2s): that's still a real,
  useful result -- it would mean the DP IN adapter's `ADP_DP_CS_3`/`CS_2`
  register space itself is not behaving as the reference expects on this
  port, a harder and more specific problem than "never tried."
- **If HPD propagates and DPRX still stays at 0**: the crossbar/DID_CHANGE_
  LINK_CONFIG path (unexercised on the correct pipeline in every run so
  far) becomes the next live suspect, including the `FIFO_RD_N_CLK_EN`
  field-width guess flagged back in `notes/2026-09-24-0127-*.md`.
- Two other pieces of the same reference PR are real but out of scope
  entirely for the current blocker: the PCIe-tunnel/IOMMU commits (57b3f3a,
  6170818) are for USB device/network tunneling through the same dock, not
  display; the placeholder-EDID retry (14cc7c9) only matters once EDID is
  actually being read, which requires getting past this blocker first.

## Build verification

`tb_regs.h` (+6 lines) and `tunnel.c` (+54/-1 lines) changed; `dcp.c`/
`dptxep.c`/`atc.c`/`apple-display-crossbar.c` untouched. New hashes:
`thunderbolt.ko` `fd5f7196144fc760459f71cac094d19901c554531e96ab6c2c68096c7e9b7465`
(expected -- this is the actual functional change),
`thunderbolt_apple.ko` `4bd921e908a491ddc3ccd2dfd701fb39ae015df2824f0ad9862ca8ca71ef314d`
(source file `apple.c` itself untouched; changed only because it recompiles
against the new `tb_regs.h`/`tunnel.o`, confirmed by a single pre-existing,
unrelated unused-function warning being the only compiler output).
`appledrm.ko` verified byte-identical to 0130
(`2d0b5f5b9d831f0a740a150e47d9774858cf9bf089c97698f32d70dedacced8c`);
`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko` verified byte-identical
to every prior candidate. Stale-symlink sweep clean (same pre-existing,
already-triaged non-symlinks as every candidate since 0115).
`test-dpin-handshake.c` 13/13 pass (regression check only; this candidate
never touches `apple-dpin-handshake.h` or its callers). Patch:
`patches/0131-pulse-hpd-propagation-apple-host-dpin.patch`. `scripts/
manage-0131.py` derived from `manage-0130.py`: `appledrm` hash unchanged,
`thunderbolt`/`thunderbolt_apple` hashes updated, `CONFIG`/`BACKUP` path
suffixes bumped; `OPTIONS` byte-identical (no new module parameters).

## Test plan

Same protocol, single boot, hub already connected, still dcpext1/right-port
(no port change). Watch specifically for:

1. `thunderbolt-apple-nhi ...: Apple: HPD propagated` (new line from this
   candidate) versus a warning (`cannot read/pulse/end HPD propagation
   pulse`, or `HPD did not propagate`) -- the first real new signal.
2. Whether `apple_dp_aux_work()`'s `"DP IN CS changed ..."` line appears at
   all this time (it never has, in any dcpext1 run so far).
3. `DPRX_DONE=1`, and whether `SET_LINK_RATE`/`WILL_CHANGE_LINK_CONFIG`
   finally appear in the post-`request_display` window that's been
   completely silent in every failure so far.
4. If `DPRX` asserts: `dcp_tunnel_crossbar_up()`'s own result on the
   correct pipeline for the first time, and -- the actual goal -- a
   picture, confirmed by Oliver's own eyes.
5. If the pulse succeeds (`"HPD propagated"`) but `DEVICE_NOT_RESPONDING`/
   `DEVICE_NOT_STARTED` and the same silence still follow: port
   `NO_AUTO_LT` and the video-hop credit override next, in that order, per
   "Known uncertainty" above.
