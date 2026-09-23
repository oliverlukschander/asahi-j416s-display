# DPIN0 MODE_A/MODE_B: full 0-15 value space exhausted, all clean negatives

Consolidates 0110, 0111, 0112 (values 9, 8, 10), the 0113 mv0 retest
(value 0), and the `scripts/sweep-mode-value.sh` run covering values 1,
2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15 (notes/mode-value-sweep-results.md).

## Result

Every value from 0 to 15 -- the entire range `APPLE_DPIN_MODE_A`/
`APPLE_DPIN_MODE_B`'s write formulas can express (MODE_A sets one bit at
position `mode_value`; MODE_B ORs a field of that width at bit 7; both
bounded by `APPLE_DPIN_MODE_VALUE_MAX=15`) -- has now been tested on
real hardware. All 16 are clean negatives: the native DPIN0 handshake
completes without error, crossbar bring-up and link-config both report
success, DPRX_DONE=1 (AUX/DPCD read completes), and no picture ever
appears on the external monitor.

Each sweep-script attempt was independently verified (not just "no
crash") to have genuinely run: native DPIN0 handshake logged, DCP's own
hotplug detection fired, `dcp_dptx_connect()` was actually called. This
guards against the two known failure modes that silently invalidated
earlier attempts (the 0112 `dpin_attempted` latch bug, fixed in 0113;
and a one-off AUX/DPRX detection failure on a single mv1 attempt,
unrelated to our code, that the script caught and retried).

## What this changes

This is a materially stronger conclusion than any single candidate:
combined with the formula correction in
2026-09-23-mode-value-formula-correction.md (external research plus a
focused re-disassembly found that what we thought was a "rate class /
lane count" field is actually the ATC field of the *already-known*
`IODPTXPortAddress` routing target we pass into `dptxport_connect()`
ourselves -- not something requiring independent derivation at all), the
balance of evidence now points to **MODE_A/MODE_B not being the
mechanism that turns on the picture, regardless of what value is
written there**. We are not just out of good guesses for this field; we
have exhausted its entire possible value space and found no effect.

This does not mean the two writes are useless or wrong to make (they
still match a confirmed native bit-packing pattern), only that they are
very unlikely to be the specific missing piece standing between the
current state (DPRX_DONE=1, i.e. the monitor's DPCD/AUX channel reads
back successfully) and an actual lit picture.

## Where the real bottleneck likely is

DPRX_DONE=1 means the *AUX/management* channel training completed --
the monitor is being talked to and responds. The absence of a picture
despite that means the gap is somewhere between AUX completion and
actual video (main-link) pixel data reaching the display: main-link
symbol lock/training, video timing generation into the tunnel, or a
DCP-firmware-internal state transition we have not yet identified that
gates "start sending frames" independently of the AUX handshake. This
is a different question than "what value goes in this register" and
likely needs a different investigative angle -- most plausibly, tracing
what native macOS does *after* DPRX/AUX completes and *before* it
starts video, rather than further permutations of MODE_A/MODE_B.

## Housekeeping

No further speculative writes to MODE_A/MODE_B are planned. The 0112
runtime-parameter infrastructure and `scripts/sweep-mode-value.sh`
remain useful general-purpose tools for testing any future bounded
hypothesis without a reboot per value.
