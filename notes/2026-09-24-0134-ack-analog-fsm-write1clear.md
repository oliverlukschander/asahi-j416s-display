# 0134: try a write-1-to-clear ack on the stuck analog FSM bit

Direct continuation of 0133. Discussed with Oliver before writing anything
here, since this means an actual write into the address range two
standing safety rules already flag -- he chose to try it.

## What 0133 found, precisely

`captures/2026-09-24-0133-boot-kernel.log`, all 24 polls (500ms apart, the
full 12s budget), dpin0's `APPLE_CIO_DPIN_ANALOG_FSM` (offset `+0x18`):

- Poll 1 (~1s after tunnel-up): `0x00001017`.
- Poll 2 through 24 (~1.5s through ~12s after tunnel-up): `0x80000000`,
  bit-for-bit identical every single time.

Every other word in both the dpin0 dump (`+0x00` through `+0x7c`) and the
dpin1 dump (the *other*, unused adapter) is also bit-for-bit identical
across all 24 polls, with one exception: dpin1 shows a matching one-time
transition at the same poll boundary (`+0x0c`: `00040004`->`80010000`,
`+0x1c`: `00000000`->`80000000`) -- consistent with a real, shared
hardware event at tunnel-up rippling across the whole ACIO analog
subsystem, not sampling noise. The transition happens well before
`DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` (~5s) and stays frozen
through the entire remaining ~11 seconds, including the final give-up.

## Why this looks like a status latch, not a dead end

Two things point at "status/latch bit, needs acknowledging" rather than
"engine reset to idle and never restarted":

1. The value is a single bit (31) with nothing else set -- the classic
   shape of a status/event flag, not an arbitrary counter or a fully
   reset-to-zero state.
2. This driver family already has exactly this pattern elsewhere, working
   correctly: `apple_dpin_up()` (this same file) reads
   `APPLE_DPIN_IRQ_STATUS`, and if bit 0 is set, writes the read value
   straight back to clear it (`"a plug event (bit 0) also latches status
   bits in +0x0 that are cleared by writing it back"`, per that function's
   own comment) -- a real, hardware-tested, write-1-to-clear register on
   an adjacent block in the very same driver. This is not a novel
   invention; it's the existing idiom, aimed at a different register that
   is a strong, concrete candidate for the same behavior.

## The change (kernel commit cb06532)

Added `apple_dp_ack_analog_fsm()`: the first time `+0x18`'s bit 31 is
observed set (checked on every poll, same cadence as 0133's dump, but
only acts once), read the register and write the exact same value
straight back, then read again and log the result. If it's a
write-1-to-clear latch, this clears only the bits that were set and
touches nothing else -- the least presumptuous possible write, not a
guessed constant, not a different offset, not the already-tested
control/start pulse at `+0x00`. Latches via `anhi->dp_aux_fsm_acked`
(new field) so it never fires more than once per tunnel-up, and only
runs while `DPRX` has not already asserted (nothing to unstick once AUX
has already completed).

## Known uncertainty, stated plainly

- This is a guess at register semantics without a datasheet. If `+0x18`
  is not a write-1-to-clear latch (e.g. it's genuinely read-only, or the
  bit means something else), writing the same value back should be a
  no-op at worst on ordinary MMIO status registers -- but "should" is not
  "guaranteed," and this is exactly why the plan is one boot, one clean
  attempt, full capture, not a repeated hammering.
- If the ack succeeds (FSM moves to something other than `0x80000000`
  after the write) but `DPRX` still never asserts: real, useful
  information about the shape of the block's state machine, not a
  wasted attempt.
- If the ack has no effect (FSM reads back `0x80000000` again
  immediately): that's also informative -- either the bit isn't W1C, or
  clearing it isn't sufficient by itself to unstick whatever's actually
  blocking the AUX transaction, and this specific hypothesis is closed.
- Either way, this stays within "one hardware attempt" discipline: a
  single write, once, gated behind confirming the exact stuck condition
  0133 already characterized precisely -- not a new blind guess at an
  unrelated register.

## Build verification

Only `drivers/thunderbolt/apple.c` changed (+47 lines: one new struct
field, one new function, one new call site). `tb_regs.h`/`tunnel.c`
untouched since 0132. New hash: `thunderbolt_apple.ko`
`fa245b8411f4ab85db5143c2111a8cd423ac763aa471c289300ca4f56da46a08`.
`thunderbolt.ko` verified byte-identical to 0132/0133
(`459250fe65adc5066f64f9b9b91c8f8b291e6e96b648de4d95bb0222afe4a5b9`);
`appledrm.ko`/`mux-apple-display-crossbar.ko`/`phy-apple-atc.ko` verified
byte-identical to every prior candidate since 0130. Stale-symlink sweep
clean (same pre-existing, already-triaged non-symlinks as every candidate
since 0115). `test-dpin-handshake.c` 13/13 pass (regression check only;
unrelated code). Patch: `patches/0134-ack-analog-fsm-write1clear.patch`.
`scripts/manage-0134.py` derived from `manage-0133.py`: only the
`thunderbolt_apple` hash and `CONFIG`/`BACKUP` path suffixes changed;
`OPTIONS` byte-identical.

## Test plan

Same protocol, single boot, hub already connected, still dcpext1/
right-port. Watch specifically for:

1. `"Apple: FSM stuck at 0x80000000, attempting write-1-to-clear ack"` --
   confirms the condition fired and the write happened.
2. `"Apple: FSM after ack: 0x........"` -- the actual result. `0x80000000`
   again means the bit did not clear (or was already set again by the
   time of the read-back); anything else means it moved.
3. Whether `"DP IN CS changed ..."` (the separate CS0-13 poller, unrelated
   register space) fires at all afterward -- the first sign the AUX layer
   itself reacted, not just this one status register.
4. `DPRX_DONE=1`, and -- the actual goal -- a picture, confirmed by
   Oliver's own eyes.
5. If the ack has no effect and DPRX still never asserts: this specific
   hypothesis (stuck-latch-needs-clearing) is closed. Do not retry a
   write to this same offset without new evidence; the next place to look
   would be a different register in the same block, or accept that this
   requires DCP-firmware-side or physical-layer investigation beyond what
   the host driver can influence.
