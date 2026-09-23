# 0113: fix a real bug that silently invalidated the mode_value=0 test

The dpin_mode_value=0 hardware attempt right after the formula
correction (see 2026-09-23-mode-value-formula-correction.md) produced no
picture, but investigation of the kernel log showed the test never
actually ran the native DPIN0 handshake at all -- it was silently
blocked. This candidate fixes the root cause before that value is
retested.

## What happened

The dpin_mode_value=10 test (0112) was unplugged normally. Its deactivate
call logged:

```
apple-dcp 315c00000.dcp: native DPIN0: DCP active=0 result=-19
```

-19 is -ENODEV, `apple_usb4_right_dpin0_set_active()`'s default `ret`
value -- meaning the function returned via its very first guard,
*before* ever calling `apple_dpin_handshake()`:

```c
if (!acio->current_cable_info || !acio->nhi_pdev ||
    acio->rc_res->start != 0xf01ac0000ULL)
	goto unlock_cio;
```

A real physical unplug clears `acio->current_cable_info` (and often
`nhi_pdev`) essentially immediately, before the DCP-issued DEACTIVATE
APCALL reaches this function through its own asynchronous RPC path. So
this guard trips on every ordinary disconnect, not just some edge case
-- meaning the entire 0112 same-boot re-test mechanism (the deactivate-
time MODE_A/MODE_B register clear, and resetting the `dpin_attempted`
one-shot latch) had never actually executed on real hardware, across
any of the 0112 tests (8, 9, 10). It only ever ran in
`scripts/test-dpin-handshake.c`'s mock, which has no notion of
`current_cable_info` at all and so could not have caught this.

The consequence: `dpin_attempted` stayed latched `true` from the very
first activate of the boot. The next activate request (mode_value=0)
hit `if (active && acio->dpin_attempted) { ret = -EALREADY; ... }`
before ever reaching the handshake or its `dev_info` log line --
consistent with the kernel log showing route-selection and crossbar
messages (driven by other code) but no "native DPIN0: active=1
handshake=..." line at all for that attempt. The observed "DPRX timeout,
keeping DP tunnel" was an expected consequence of the native handshake
never running, not evidence about mode_value=0 itself. That test is
invalidated and needs to be redone.

## Fix

DPIN0's registers are on-die SoC hardware; they are not torn down by
cable removal, only the higher-level `current_cable_info` bookkeeping
is. When the early guard trips on a deactivate request (`!active`) and
we previously activated (`acio->dpin_base` already mapped, meaning
there is real state of ours to clean up), fall through to the same
handshake/cleanup path used for a normal deactivate, instead of bailing
out and leaving `dpin_attempted` and the MODE_A/MODE_B registers stuck.
Still bail out immediately for the two cases where there is genuinely
nothing to do: activating with no real cable/session at all, or
deactivating when nothing was ever mapped.

## Validation

`make` in `src/thunderbolt` rebuilds only `apple.o`/`thunderbolt_apple.ko`.
SHA256 confirms every other module unchanged from 0112:

```
thunderbolt_apple  cb636968b5f50919fae72cb7c304b4f92f666d04a727de683266240e95dc8096 (changed)
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
appledrm           9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3 (unchanged)
```

`scripts/test-dpin-handshake.c` is unchanged: this bug lives entirely in
`apple.c`'s cable-state wrapper around `apple_dpin_handshake()`, a layer
the mock harness does not model. No new test was added for this specific
guard interaction since it depends on real ACIO/Thunderbolt cable-state
bookkeeping that isn't meaningfully mockable outside the kernel; the
correctness argument here rests on the direct code read plus the
matching -19 evidence from the actual failure, not an offline test.

## Safety scope

Same DPIN0 resource (`0xf01e50000`) and same guard structure as before;
the change only widens which paths reach the existing, already-reviewed
handshake call, it does not touch the handshake itself or add any new
register access.

## Next hardware step

This requires one more reboot (module code path change, can't be
hot-patched into an already-loaded module). After that, retest
dpin_mode_value=0, then =1 if inconclusive, exactly as planned before
this bug was found -- and confirm via the kernel log that a deactivate
after a real unplug now actually reaches "native DPIN0: active=0
handshake=..." instead of silently returning -19.
