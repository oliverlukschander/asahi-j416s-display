# 0110: explicit-guess test of the two remaining DPIN0 writes

Continuation of notes/2026-09-22-0109-dpin0-connected-bit.md and the
subsequent 3-agent parallel static-analysis workflow (findings and
synthesis relayed in chat; raw per-agent addresses kept private under
~/.local/share/j416s-display/dpin-static-13.5/). Oliver explicitly chose
to test a bounds-based best estimate for the two remaining writes rather
than stop or immediately pursue DCP firmware extraction.

## What the workflow established

Three independent agents (top-down attributes-construction trace,
bottom-up field-setter search across the entire __TEXT_EXEC, and a
crossbar-validation/log-string cross-check) all confirmed, instruction-
for-instruction, the exact bit-packing formula already documented in
0109's note. None could pin a concrete runtime value: `w26` (which
determines both remaining writes) is a byte-for-byte, unmodified copy of
the raw `IODPTXPortAttributes` parameter passed into
`AppleCIODPTX::connectTo` -- there is no further Apple-internal derivation
left to find in this kernelcache. That parameter's value is supplied by a
caller that could not be located in this XNU image, most likely because it
originates in the separate DCP coprocessor firmware, which is not part of
`kernelcache.release.mac14j`.

What they did bound: the rate-class subfield (bits 4-7 of the relevant
word) is a compact enum with exactly 5 valid values, and it matches, bit
position for bit position, the same RBR=0/HBR=1/HBR2=2/HBR3=3 ordinal this
driver already uses (`drivers/thunderbolt/tb_regs.h`
`DP_COMMON_CAP_RATE_*`) -- this link negotiates HBR2, so rate_class=2 with
reasonably high confidence, since it is grounded in an already-established
standard enum rather than a fresh guess. A second subfield (checked via
`w26 & 0xE`) could not be identified; the closest available reading from
a structurally similar 3-valid-value field elsewhere in the same function
family suggested a lane-count-class interpretation that would resolve to
1 for a 4-lane link, but this is meaningfully weaker evidence than the
rate-class reading.

## The value tested

```
w20 = rate_class(2) * lane_count(4) + secondary_bit(1) = 9
```

Applied as:
- `+0x1c`: `old | (9 << 7)` -- pure OR, no bits cleared, matching native's
  confirmed mask=0 for this write.
- `+0x14`: `(old & ~0xff) | (1 << 9)` -- clears the low byte, sets bit9,
  matching native's confirmed mask=0xff/value=1 pattern with shiftAmount=9.

Both writes inserted in native's own call order (HPD, then `+0x1c`, then
`+0x14`, then CONTROL), gated the same way as every prior write on this
resource: only when activating, only on read success (skipped if the
register reads as floating, matching this driver's existing "reject a
floating window before writing" discipline).

## Explicitly not confirmed

This is labeled in the kernel comment, the commit message, and here as an
informed estimate, not a fact. If it does not restore the picture, that
is expected to be inconclusive about whether the *formula* is right (it
is, confirmed threefold) versus whether the *specific numeric guess* is
right (unconfirmed, and the weaker of the two subfields is a real
candidate for being wrong). It does not by itself justify further guessing
at this specific field; see the DCP-firmware-extraction plan (Oliver's
chosen next step regardless of this outcome).

## Safety scope

Same DPIN0 resource (`0xf01e50000`, size `0x4000`) this driver has safely
read and written since 0093; no new addresses, no ACIO analog, no
lpdptxphy, no forbidden register. Read-before-write on both new offsets,
consistent with the rest of this handshake. No rollback is added for
these two registers on a failed handshake (matching the existing
conservative choice already made for HPD in 0109 -- native's teardown path
for either was never traced).

## Validation

`scripts/test-dpin-handshake.c` updated: mock now handles reads/writes on
both new offsets, with assertions that MODE_A only ever changes via the
exact confirmed mask/shift pattern and MODE_B only ever gains the OR'd
bits, never anything else. ASan/UBSan, all9 scenarios pass. checkpatch on
the accumulated header diff:0errors/0warnings. `make` in src/thunderbolt
rebuilds only apple.o/thunderbolt_apple.ko; the other four modules,
including core thunderbolt.ko, are unchanged from0109 (verified by
SHA256). Candidate hashes:

```
thunderbolt_apple  7e1dd94484e5d258696de1032bb9aded75b28195748c3e476c3c0fe69f78e102
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
appledrm           9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3 (unchanged)
```

`scripts/manage-0110.py` follows the same eleven-file backup/verify
discipline as every prior candidate; options unchanged from0109 (this is
unconditional code behind the existing `dpin_native=1` gate).
