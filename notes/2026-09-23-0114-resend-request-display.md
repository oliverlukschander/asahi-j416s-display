# 0114: resend request_display after the native DPIN0 handshake completes

Direct follow-up to notes/2026-09-23-xnu-power-state-trace.md. This is
the first candidate to come from XNU/kernelcache tracing rather than
DPIN0 register guessing, and the first change to `dptxep.c` this
project has made all session (every prior candidate touched
`apple-dpin-handshake.h` or `apple.c` in the thunderbolt driver).

## What real macOS does differently

Disassembly of `AppleDCPDPTXRemotePortProxy` (the class confirmed to
be the real macOS driver for a Type-C/dcpext-routed DPTX target --
distinct from `AppleCIODPTX`, used for direct/fixed ports, which uses
an entirely unrelated power mechanism) found:
`setPowerState`'s gated implementation resends `request_display`
(AFK/EPIC method 6 -- the exact method our own
`dptxport_request_display()` already calls) specifically at the moment
the IOKit power domain transitions to state 1 ("active"), gated on a
`_displayRequested` flag already being set. It is not sent
unconditionally, once, at initial connect time -- it is (re-)sent when
the power domain confirms active.

## The change

Our own `dcp_dptx_connect()`'s custom USB4 branch already calls
`dptxport_request_display()` once, early, before the native DPIN0
crossbar handshake even runs. There is no equivalent "power domain
confirmed active, resend" step anywhere in our driver.

`dptxport_call_activate()` in `drivers/gpu/drm/apple/dptxep.c` is
where `dptxport_native_dpin(service, true, false)` runs -- our closest
equivalent of "the tunneled target's power domain is up" (crossbar
bring-up and the native DPIN0 register handshake both succeed here).
Added: on `dptxport_native_dpin()` returning success, call
`dptxport_request_display(service)` again, logging the result.

```c
if (usb4_native_dpin && dcp_is_usb4_output(dcp)) {
	ret = dptxport_native_dpin(service, true, false);
	if (!ret) {
		int r = dptxport_request_display(service);
		dev_info(dcp->dev,
			 "USB4: resend request_display after native DPIN0 activate: %d\n",
			 r);
	}
} else if (...) { ... }
```

This uses only the existing, already-safe AFK/EPIC method (index 6),
already sent once successfully in every prior candidate this project
has run; no new register, address, or APCALL is introduced.

## Validation

`make` in `src/appledrm` rebuilds only `dptxep.o`/`appledrm.ko`.
SHA256 confirms every other module unchanged:

```
appledrm           c29b0cb13c4bc6415a7299b3970582fb8043af1692c9710b94eca4321256e504 (changed)
thunderbolt_apple  cb636968b5f50919fae72cb7c304b4f92f666d04a727de683266240e95dc8096 (unchanged, matches 0113)
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
```

No offline mock test was added: this change is a single additional
AFK/EPIC call inside a callback, not new register-level logic like
`apple-dpin-handshake.h`'s state machine, which is what
`scripts/test-dpin-handshake.c` exists to cover. Correctness here rests
on the direct code read (an existing, already-used function, called an
extra time under a new, narrow, well-understood condition) rather than
an offline test.

## Safety scope

No new register, address, or MMIO access. The added call is the exact
same `dptxport_request_display()` already called successfully once per
connection attempt in every candidate since this project began; this
just calls it a second time, later, gated on the native DPIN0 activate
having already succeeded. Scope otherwise identical to 0113.

## What "inconclusive" would mean here

If this does not produce a picture, it does not disprove the broader
XNU-trace finding -- it would mean either resending `request_display`
alone isn't sufficient (real macOS's `setPowerState` handler does more
work around it we haven't replicated, e.g. via
`initialPowerStateForDomainState`/`powerChangeDone` or whatever sets
`_displayRequested` in the first place, neither traced yet), or the
timing point chosen (right after `dptxport_native_dpin()` succeeds)
isn't the correct equivalent of "power domain confirmed active." Both
remain open per notes/2026-09-23-xnu-power-state-trace.md's own
"suggested next hardware test" section.
