# 0109: set the CONNECTED bit native firmware also sets on DPIN0

Continuation of notes/2026-09-22-native-bringconnectionup.md. That note
identified four register writes native `AppleCIODPTX::bringConnectionUp`
performs on DPIN0 (`0xf01e50000`, the resource this driver already safely
maps and uses) that this driver never performed. Of those four, one is
fully confirmed and unconditional; the other three depend on runtime
DisplayPort negotiation data not present in the static kernelcache.

## The confirmed, unconditional write

`AppleDPTX::setBitsInReg(nub, memmap, offset, shiftAmount, mask, value)`
(0xfffffe00093327e4, confirmed by symbol; body confirmed to compute
`new = (old & ~mask) | (value << shiftAmount)`) is called from
`bringConnectionUp` against the DPIN0-side memory map with
`offset=0xc-or-0x10 (this port's single-lane-group case resolves to 0xc,
our existing CONTROL register), shiftAmount=0, mask=2, value=2` --
i.e. unconditionally sets bit1, independent of lane count, rate, or any
other runtime value. It also calls the same helper on HPD
(`offset=0x0, shiftAmount=1, mask=0, value=(single-stream ? 1 : 0)`);
every topology this driver drives through DPIN0 is one external monitor
(SST, never DP MST), so that value is 1 here with the same confidence as
the CONTROL write.

## The change

`drivers/thunderbolt/apple-dpin-handshake.h`: add `APPLE_DPIN_CONNECTED
(1U << 1)`. When activating, OR it into both the HPD and CONTROL writes
(HPD was previously read-only in this driver; CONTROL already had bit0
written). On a failed handshake, the existing "restore only our bit"
rollback now restores both INACTIVE and CONNECTED on CONTROL to their
pre-handshake values (previously only INACTIVE), so a failed activation
does not leave CONNECTED stuck set; HPD is not rolled back, since native's
teardown path for it was never traced and this driver did not touch that
register at all before this change. `scripts/test-dpin-handshake.c`
updated to match (ASan/UBSan, 9 scenarios); two scenarios needed their
expected values updated for the new bit, the rest were unaffected --
including a useful confirmation that the two-bit rollback formula reduces
exactly to the original one whenever the saved CONTROL value's bit1 was
already 0, which is the case in every existing scenario.

This only ever touches DPIN0 (0xf01e50000), already safely used by this
driver via `apple_usb4_right_dpin0_set_active`; it does not touch the
crossbar, ACIO analog block, lpdptxphy, or any register this project has
flagged as forbidden.

## Build-system fix found in passing

`src/thunderbolt/apple-dpin-handshake.h` was a stale plain copy, not a
symlink like every other file in `src/thunderbolt/` -- it is a file this
project added on top of stock Thunderbolt sources, and was missed when the
symlink farm was set up. Editing the kernel-repo copy alone silently built
against the stale copy (apple.c's `#include "apple-dpin-handshake.h"`
resolves relative to the symlink's apparent path). Replaced it with a
symlink to the kernel-repo file; rebuild now correctly picks up changes
(verified: thunderbolt_apple.ko hash changed only after the fix).

## Plan for the remaining `+0x14`/`+0x1c` values

Oliver's question -- if this exact monitor can already be driven directly,
these negotiation values must be known somehow -- is right, with one
caveat: the direct/HDMI path in this project does not go through
`AppleCIODPTX::bringConnectionUp` at all (that class is specifically the
ACIO/CIO tunnel path; direct connections use a different concrete class,
per the native class hierarchy: `AppleLPDPTX`/lpdptxphy-based or a plain
`AppleATCDPTX`-style direct path). So there is no existing direct-path
trace of *this* function to read the values off of.

What direct and tunneled paths do share is the underlying
`IODPTXPortAttributes` value itself: `validateConnection` receives it as a
parameter, it is not specific to the tunnel bring-up class, and it is very
likely built by mode/negotiation code common to any DP output for a given
monitor and timing -- lane count, link rate, color depth, DSC on/off,
stream count. Since 0099 (direct connection) and this candidate use the
*same* monitor and timing, if that shared attributes-computation function
can be found and its formula read, the exact value for our known,
already-negotiated configuration (4 lanes, HBR2, 2560x1440@59.951, no DSC)
could be computed without runtime tracing. Concrete next steps, both
offline/zero-risk:

1. Find where `IODPTXPortAttributes` gets constructed (likely a generic
   `AppleDPTXPort`/`IODPTXPort`-level function, not class-specific) and
   read its field-packing logic against known mode parameters.
2. Cross-check against the `AppleDPTXPort::setActiveLaneCount` /
   `AppleATCDPINAdapterPort::validateConnection` family already touched in
   this and prior notes, since lane count is one of the packed fields and
   is already confirmed (4).

Not started in this session; a distinct, bounded follow-up.

## Validation

`make` in src/thunderbolt rebuilds only `apple.o`/`thunderbolt_apple.ko`
(after the symlink fix); the other four modules (including core
`thunderbolt.ko`) are unchanged from0108 (verified by SHA256). checkpatch
on the header diff:0errors/0warnings. Candidate hashes:

```
thunderbolt_apple  74d8250de35ab42a0ef58690887eb3a21cf463663d226aa769a177c0f3743b64
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
appledrm           9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3 (unchanged)
```

`scripts/manage-0109.py` follows the same eleven-file backup/verify
discipline as0106-0108; the option string is unchanged from0108
(this change is unconditional code behind the existing `dpin_native=1`
gate, not a new module parameter).
