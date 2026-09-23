# 0111: lower bound of the bounded DPIN0 mode-value sweep

Continuation of notes/2026-09-22-0110-mode-value-guess.md and
-0110-result.md, and notes/2026-09-23-upstream-dptxep-crossref.md (which
confirmed no unexplored Asahi-community prior art exists for this specific
DCP-firmware-internal value; Oliver explicitly declined outreach to
upstream and asked to brute-force the bounded value space instead).

## What varies, what doesn't

The formula documented in 0109/0110 is unchanged and still independently
confirmed threefold by the 3-agent static-analysis workflow:

```
MODE_VALUE = rate_class(2) * lane_count(4) + secondary_bit
```

`rate_class=2` (HBR2) and `lane_count=4` are both high-confidence, grounded
in an already-established standard enum and this link's known lane count --
neither is varied across this sweep. The only free parameter is
`secondary_bit`, a weak reading of a 3-valid-value enumeration (0, 1, or 2).
0110 tested the middle value (secondary_bit=1, MODE_VALUE=9): ran cleanly,
no error, no picture -- an inconclusive negative on that specific guess, not
on the formula or the general mechanism.

This candidate tests the lower bound: **secondary_bit=0, MODE_VALUE=8**.
0112 (if this is also inconclusive) will test the remaining bound,
secondary_bit=2, MODE_VALUE=10.

## Change

Single-line constant change in
`drivers/thunderbolt/apple-dpin-handshake.h`: `APPLE_DPIN_MODE_VALUE` 9U ->
8U, comment updated to document the sweep plan across 0110/0111/0112. No
other code changed -- same two offsets (+0x14, +0x1c), same call order
(HPD, MODE_B, MODE_A, CONTROL), same masks (pure OR at MODE_B shifted by 7;
clear-low-byte-then-set-bit-at-value at MODE_A), same gating (only on
activate, only after a successful read, no rollback on failure, matching
the existing HPD precedent).

## Validation

`scripts/test-dpin-handshake.c` updated: expected `mode_a`/`mode_b` values
recomputed for MODE_VALUE=8 (`1<<8=0x100`, `8<<7=0x400`, replacing 0110's
`0x200`/`0x480`); assertions themselves are symbolic (reference
`APPLE_DPIN_MODE_VALUE`, not a hardcoded number) so they needed no other
change. Compiled with `-fsanitize=address,undefined`; all 9 scenarios pass.

`make` in `src/thunderbolt` rebuilt only `apple.o`/`thunderbolt_apple.ko`.
SHA256 confirms every other module is byte-identical to 0110's:

```
thunderbolt_apple  e552cbc0bf6abcb22abc9c5d63065f5a668b48de440c6933526ffef526657e51 (changed)
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
appledrm           9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3 (unchanged)
```

`scripts/manage-0111.py` derived from `manage-0110.py` via mechanical `sed`
substitution only (0110->0111, thunderbolt_apple hash); diffed to confirm
no other line changed. Offline `check` action confirms correct kernel/
machine, hub and external display absent, and candidate hashes match.

## Safety scope

Identical resource scope to every candidate since 0093: DPIN0
(`0xf01e50000`, size `0x4000`); no new addresses, no ACIO analog register,
no lpdptxphy, no forbidden register. Same one-attempt-per-boot discipline.
