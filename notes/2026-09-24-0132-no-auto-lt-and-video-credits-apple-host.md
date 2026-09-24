# 0132: hold off hub DP OUT auto-training, grant 5 NFC credits (Apple host)

Direct continuation of 0131. HPD now confirmed propagates -- but it wasn't
enough on its own, so this ports the other two pieces of the same
hardware-tested reference commit that 0131 deliberately held back.

## 0131's result

`captures/2026-09-24-0131-boot-kernel.log`: `thunderbolt-apple-nhi
f01f00000.nhi: 0:5: Apple: HPD propagated` fires right where expected,
before `"DP IN tunnel routing"` --
confirming the pulse and wait loop from 0131 work exactly as designed
(`tb_dp_port_hpd_is_active()` returned true within the 2s budget).

Everything after that is otherwise byte-for-byte the same shape as every
dcpext1 failure since 0128: `request_display` succeeds, 5 seconds of
complete apcall silence, `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`,
`dcp_dptx_connect: timed out waiting for port 0 link configuration`,
`DEACTIVATE`, one retry, same again, `USB4 protocol probe finished: -110;
no automatic retry`. `"DPRX timeout, keeping DP tunnel"` still fires at the
same ~12s-from-tunnel-up mark. `DPRX` never asserted. (`apple_dp_aux_work`'s
`"DP IN CS changed"` line still doesn't appear either, but that's now
explained rather than mysterious: the pulse in 0131 runs *before*
`apple_nhi_dp_tunnel_post_activate()` takes its CS0-13 baseline snapshot,
so HPD is already asserted by the time the baseline is captured -- there's
no delta left for the periodic poller to detect. Not a sign that nothing
happened; a side effect of getting the fix right.)

So: propagating the DP IN adapter's own protocol-level HPD was real and
necessary (a first, confirmed win), but not sufficient by itself. Something
else still keeps the actual AUX/DPCD exchange from ever completing.

## The other two pieces of the same commit

aurora-silicon/linux#8's `4a7fd72` bundles three register-level changes
together as one tested unit (three docks, multiple monitors), all gated
behind the same Apple-host check. 0131 ported only the first:

1. ~~HPD propagate pulse~~ -- done in 0131, confirmed working.
2. **`ADP_DP_CS_3_NO_AUTO_LT` on the DP OUT (hub-side) adapter, held for the
   duration of the tunnel.** The reference's own reasoning: *"the host's
   DPTX trains the sink through the tunnel; the DP OUT adapter must not
   start link training on its own while the tunnel is up."* Without this,
   the hub is free to run its own link-training state machine on the same
   physical link at the same time our host's DCP/DPTX is trying to train
   it through the tunnel. Two independent trainers driving the same link
   is a concrete, mechanistic way for AUX/DPCD to never produce a coherent
   result even after HPD is correctly asserted -- exactly 0131's leftover
   symptom.
3. **5 NFC (non-flow-controlled) credits for the DP IN video hop**,
   overriding the generic per-adapter credit-allocation formula. This
   project's own captures have shown `credits=1`/`credits=0` on this
   adapter's hops every single run (`apple_dp_dump_hop()`,
   `drivers/thunderbolt/apple.c`) -- the reference simply hardcodes 5 for
   any Apple host DP IN adapter.

Neither was ported in 0131, specifically to keep that a clean, single-
variable test of the pulse alone. Now that the pulse is confirmed working
and confirmed insufficient alone, both are added together here: they come
from the same tested-as-one-unit commit, operate on different adapters/
resources than each other (dst_port link-training vs. video-hop credits),
and Oliver asked to move decisively rather than spend another whole boot
attempt isolating which of the two remaining pieces matters most.

## The change (kernel commit ab59673)

Added `ADP_DP_CS_3_NO_AUTO_LT` (`tb_regs.h`, next to `HPD_PROPAGATE`).  In
`tb_dp_activate()`'s existing `tb_port_is_dpout(tunnel->dst_port)` branch:
set the bit on `tunnel->dst_port` before enabling it (active) and clear it
after disabling (deactivate, even if the disable itself failed -- matching
the reference's "hand link training back regardless" behavior exactly), gated
on `tb_nhi_is_apple(tunnel->tb->nhi) && tb_port_is_dpin(tunnel->src_port) &&
dst_port->cap_adap`. In `tb_dp_init_video_credits()`: return `nfc_credits =
5` immediately for any hop whose `in_port` is an Apple host's own DP IN
adapter (`tb_nhi_is_apple() && !tb_route() && tb_port_is_dpin()` -- the
extra `!tb_route()` check, absent from 0131's simpler tunnel-endpoint-only
gates, guards this one specifically because it iterates every hop in the
path, not just the tunnel's own two fixed endpoints, so it's the one place
a downstream port could theoretically satisfy `tb_port_is_dpin()` by
coincidence).

Both changes are complete no-ops for any non-Apple host or non-DP-IN
tunnel, same as 0131.

## Known uncertainty

- If DPRX still never asserts with both of these in place: all three
  pieces of the reference's generic-code commit are now ported, and the
  "missing register-level step" hypothesis from this comparison is fully
  exhausted. The next place to look would shift to the DCP/firmware side
  again -- specifically the still-unexercised `dcp_tunnel_crossbar_up()`
  path (never reached in any dcpext1 run so far, since the sequence has
  never survived past this point to reach `SET_LINK_RATE`), or decoding
  what `SET_TILED_DISPLAY_HINTS`/other apcall payloads actually mean, since
  they've been logged but never inspected byte-for-byte.
- If `DPRX` does assert: expect `SET_LINK_RATE`, `DID_CHANGE_LINK_CONFIG`,
  and `dcp_tunnel_crossbar_up()` finally running on the correct pipeline
  for the first time ever -- a new failure there (e.g. the `FIFO_RD_N_
  CLK_EN` field-width guess flagged in `notes/2026-09-24-0127-*.md`) would
  not be a setback, it would mean this whole HPD/training/credits line of
  investigation is closed out, successfully.
- The reference's fourth piece (skip Titan Ridge's LTTPR-non-transparent
  workaround) is still deliberately not ported: the OWC hub is a
  Thunderbolt 5 device, not a Titan Ridge controller, so that specific
  workaround's condition (`tb_switch_is_titan_ridge(out->sw)`) should never
  be true here regardless; confirmed not worth touching.

## Build verification

`tb_regs.h` (+7 lines) and `tunnel.c` (+39/-1 lines, on top of 0131's own
changes to the same two files) changed; `dcp.c`/`dptxep.c`/`atc.c`/
`apple-display-crossbar.c` untouched. New hashes: `thunderbolt.ko`
`459250fe65adc5066f64f9b9b91c8f8b291e6e96b648de4d95bb0222afe4a5b9`,
`thunderbolt_apple.ko`
`91caddc7f37594c6d326b01562656f12d99c8e0b67adc2bde84d3df75645368b` (source
`apple.c` itself still untouched, changed only by rebuilding against the
new `tunnel.o`/`tb_regs.h`, same as 0131). `appledrm.ko` verified
byte-identical to 0130/0131
(`2d0b5f5b9d831f0a740a150e47d9774858cf9bf089c97698f32d70dedacced8c`);
`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko` verified byte-identical
to every prior candidate. Stale-symlink sweep clean (same pre-existing,
already-triaged non-symlinks as every candidate since 0115).
`test-dpin-handshake.c` 13/13 pass (regression check only). Patch:
`patches/0132-no-auto-lt-and-video-credits-apple-host.patch`.
`scripts/manage-0132.py` derived from `manage-0131.py`: `thunderbolt`/
`thunderbolt_apple` hashes updated, `appledrm`/`mux`/`atc` unchanged,
`CONFIG`/`BACKUP` path suffixes bumped; `OPTIONS` byte-identical.

## Test plan

Same protocol, single boot, hub already connected, still dcpext1/right-port.
Watch specifically for:

1. `"Apple: HPD propagated"` still appearing (should be unaffected by
   this candidate).
2. Whether `"Apple: cannot hold off DP link training"` or `"cannot restore
   DP link training"` appear (would mean the DP OUT adapter's `ADP_DP_CS_3`
   register isn't accessible the way the reference expects on this hub) --
   versus no such warning, meaning the hold-off applied cleanly.
3. Whether the DP IN hop's credits now read `5` instead of `1`/`0` in
   `apple_dp_dump_hop()`'s existing diagnostic output.
4. Whether `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` and the silent
   5-second window finally change shape -- any apcall at all appearing
   where there's only ever been silence before.
5. `DPRX_DONE=1`, and -- the actual goal -- a picture, confirmed by
   Oliver's own eyes, not log inference.
6. If this still doesn't produce `DPRX=1`: per "Known uncertainty" above,
   the next step shifts away from this reference-comparison line entirely
   and back toward the DCP/firmware side.
