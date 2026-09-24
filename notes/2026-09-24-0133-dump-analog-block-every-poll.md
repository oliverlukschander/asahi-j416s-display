# 0133: dump the ACIO analog block on every poll (pure diagnostic)

Direct continuation of 0132. Monitor still dark. This candidate is not
another register guess -- it's an honest stop to that line of attack, and
a step toward actually seeing what's happening in the one place nothing
has looked closely at yet: the ACIO analog block itself, moment to moment,
not just in a single post-mortem snapshot.

## 0132's result

`captures/2026-09-24-0132-boot-kernel.log`. `"Apple: HPD propagated"` still
fires correctly (unaffected by 0132, as expected). No `"cannot hold off DP
link training"`/`"cannot restore DP link training"` warnings, so the
`NO_AUTO_LT` write path did not error. But the failure shape is otherwise
identical to every run since 0128: `request_display` succeeds, ~5s of
total apcall silence, `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED`,
`linkcfg_completion` timeout, `DEACTIVATE`, one retry, same again. `DPRX`
never asserted. **Oliver confirmed: monitor still dark.**

## Correction: the "5 credits" fix does not do what I claimed

Re-reading `apple_dp_dump_hop()` (`drivers/thunderbolt/apple.c:739`) after
seeing this boot's capture still show `credits=1`/`credits=0` on hop 8/9
(identical to every prior run, unchanged by 0132): that line prints
`hop.initial_credits`, read directly from the USB4 **hop table entry** via
`TB_CFG_HOPS`. My 0132 change instead set `hop->nfc_credits` in
`tb_dp_init_video_credits()`, which only feeds `tb_port_add_nfc_credits()`
-- **port-level** NFC buffer-pool bookkeeping (`ADP_CS_4`), used to avoid
over-committing a port's shared buffer budget across concurrent tunnels.
These are two different numbers that happen to share the word "credits."
My change was not wrong to make (it's still a harmless, correctly-gated,
no-op-for-non-Apple-hosts change, and I've since found the reference also
touches `drivers/thunderbolt/switch.c` to make an Apple DP IN adapter's
port-level NFC accounting apply at all, which I had not ported either) --
but it was not going to affect `hop.initial_credits`, was never going to
change what's on screen, and I should not have implied otherwise. Filed
away, not worth chasing further: this is video-stream flow control,
downstream of a link actually being trained, and AUX/DPRX -- the thing
actually stuck -- is a control-plane concern that comes first.

## What's actually still true after three fix attempts

DCP's own internal wait before declaring `DEVICE_NOT_RESPONDING`/
`DEVICE_NOT_STARTED` has been ~5 seconds, unchanged, on **every single
dcpext1 attempt** (0128 x2, 0129 x2, 0130 x2, 0131, 0132 -- eight
connect attempts total): before any host-side timeout was widened, after
widening two different host-side timeouts, after fixing HPD propagation,
and after holding off the hub's own link training. Nothing on the host
side that's been changed so far has moved that number by more than
normal jitter. That is the strongest single fact this project has --
DCP is waiting on something that four different host-side interventions,
covering everything the hardware-tested t8103 reference does
differently for an Apple host, have not touched.

`aurora-silicon/linux#8`'s own generic-code Apple-host gate
(`tb_port_is_apple_host_dpin()`, all its use sites) is now fully ported:
HPD propagate (0131), `NO_AUTO_LT` (0132), the video-hop credit constant
(0132, though not fully -- see above), and the Titan Ridge LTTPR skip
(not applicable, this is not a Titan Ridge hub). This specific comparison
is exhausted. Continuing to guess at more register pokes from the same
source without new evidence would repeat exactly the mistake this
project's own standing safety rules exist to prevent (see `dpin_aux`:
tested twice, confirmed genuinely ineffective, "re-verify only with a
fundamentally different mechanism in hand" -- I do not have one).

## What hasn't been looked at yet: the analog block, live

`apple_dp_dump_analog()` (dumps `dpin0`/`dpin1` analog register ranges,
including the FSM register at offset `+0x18` this project has been
tracking without being able to decode) has only ever been called **once
per boot**, at the very end of `apple_dp_aux_work()`'s 12-second poll
budget -- after DCP has already given up. There is no data anywhere in
this project's captures on whether that block's internal state changes
*during* DCP's own 5-second attempt, only a single snapshot taken well
after the fact. This is a genuine, currently-missing piece of evidence,
not a guess.

## The change (kernel commit 0a297a8)

Pure diagnostic, zero behavior change: `apple_dp_aux_work()` now calls
`apple_dp_dump_analog()` unconditionally on **every** poll (every 500ms,
same cadence it already runs at for up to 12s) instead of only on the
last one. No new writes, no new logic gates, nothing that could change
whether DPRX asserts -- only more reads of registers this driver already
reads safely every boot. `apple.c` is the only file touched;
`thunderbolt.ko` (tunnel.c/tb_regs.h) is unchanged from 0132.

## What this should tell us

1. **If the analog block's registers (especially `+0x18`, the FSM) never
   change across the whole 12-second window, on every poll**: that's
   strong, direct confirmation the AUX engine genuinely never gets kicked
   into motion at all on this pipeline/port -- not a slow negotiation, not
   a partial attempt, nothing happening at the hardware level. That
   redirects the investigation toward *why* DCP firmware itself never
   triggers this on dcpext1/right-port, which is now firmly a DCP-firmware
   -side or physical-signal-path question, not a driver-register one.
2. **If something does change partway through** (the FSM advancing through
   some states then stalling, for example): that is a completely different
   and much more specific problem -- a real attempt that gets partway and
   fails, decodable in principle from which states are reached, even
   without full register documentation, by comparing to whatever 0127's
   own analog dump showed at its moment of success (`0000100a`).
3. Either way, this capture becomes the first real data this project has
   on the analog block's behavior *during* an attempt, rather than after
   one has already failed -- input for an actually-evidenced next
   candidate instead of another guess.

## Build verification

Only `drivers/thunderbolt/apple.c` changed (+14/-4 lines, one function).
`tb_regs.h`/`tunnel.c` untouched this candidate. New hash:
`thunderbolt_apple.ko`
`c8ea01a483ad5ca6d025ec5f29ef83e51ba5e4357698c3e00b4f8f4129ac6493`.
`thunderbolt.ko` verified byte-identical to 0132
(`459250fe65adc5066f64f9b9b91c8f8b291e6e96b648de4d95bb0222afe4a5b9`);
`appledrm.ko`/`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko` verified
byte-identical to every prior candidate since 0130. Stale-symlink sweep
clean (same pre-existing, already-triaged non-symlinks as every candidate
since 0115). `test-dpin-handshake.c` 13/13 pass (regression check only;
unrelated code). Patch: `patches/0133-dump-analog-block-every-poll.patch`.
`scripts/manage-0133.py` derived from `manage-0132.py`: only the
`thunderbolt_apple` hash and `CONFIG`/`BACKUP` path suffixes changed;
`OPTIONS` byte-identical.

## Test plan

Same protocol, single boot, hub already connected, still dcpext1/
right-port. This time the goal is purely to *read* the resulting capture
closely, not to look for a picture changing -- this candidate cannot fix
anything by itself. Specifically:

1. Pull the full boot log and grep every `"dpin0 analog poll"`/`"dpin1
   analog"` line (there should now be up to 24 of each, one per 500ms
   poll, instead of one).
2. Track offset `+0x18` (the FSM register) across every poll: does it
   change at all during the ~5-second window before `DEVICE_NOT_
   RESPONDING`, or is it identical to its boot-time baseline the whole
   12 seconds?
3. Check every other offset in the dump too, not just `+0x18` -- anything
   that moves at all is new information.
4. Use whatever this shows to design the next candidate from evidence,
   not from another guess at the same well the t8103 reference already
   drew dry.
