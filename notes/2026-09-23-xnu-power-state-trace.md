# XNU-side trace: what triggers the DCP power-state transition

Continues 2026-09-23-power-state-gate-traced.md (which found, entirely
from DCP firmware disassembly, that continuous frame completion
requires DCP's internal power state to move from 8 to 0x21, and that
nothing our driver calls has been shown to trigger it). This note
traces the corresponding AP/XNU-side mechanism, using the same
decompiler setup rebuilt after today's reboot (see the setup steps
recorded in the prior note; this session's copy lives under `/tmp`
again and will not survive another reboot).

## Source

`/tmp/kernelcache.macho`, SHA256
`9615a486511c7a60b141d7f4291361c5212e908546d6568890029bb90b5431e7`
(same kernelcache extracted and verified multiple times earlier this
project). Unlike the DCP firmware, this binary retains a full mangled
C++ symbol table -- `llvm-nm` resolves real names directly, which made
this trace far more direct than the DCP firmware's string/xref-based
approach.

## The relevant class: AppleDCPDPTXRemotePortProxy

This class (a "remote port" DPTX proxy -- exactly the abstraction for a
Type-C/dcpext-routed DP transmitter, as opposed to a directly-wired
PHY) exposes standard IOKit power management methods plus one
DPTX-specific one:

- `setPowerState(unsigned long, IOService*)` -- the standard IOKit
  power-management callback.
- `powerChangeDone(unsigned long)`, `initialPowerStateForDomainState(unsigned long)`
  -- more standard IOKit power management plumbing.
- `synchronousChangeDPTXPowerStateTo(unsigned long)` -- **not** a
  standard IOKit name; DPTX/DCP-specific.

## The chain, in decompiled C

`synchronousChangeDPTXPowerStateTo(unsigned long targetState)` has
exactly two direct (non-virtual) callers:

1. A "request display" handler: sets a flag at `this+0x618` and calls
   `synchronousChangeDPTXPowerStateTo(this, 1)`.
2. A "display release" handler (explicitly logs "Redundant
   DisplayRelease detected!" if already released -- confirming this
   flag tracks "has a display session been requested and not yet
   released"): sends a `DisplayRelease` IPC and calls
   `synchronousChangeDPTXPowerStateTo(this, 0)`.

`synchronousChangeDPTXPowerStateTo` itself just calls the generic
IOKit `changePowerStateTo`-style primitive and synchronously waits
(via a condition on `this+0x619`) for the resulting `setPowerState`
callback to complete -- standard IOKit power-domain machinery, nothing
DPTX-specific happens here directly.

The real work is in `setPowerState`'s gated (work-loop-serialized)
implementation, `setPowerState_block_invoke`:

```c
// powerstate == 1 (activate) branch:
if (lVar7 == 1) {
    cVar9 = '\0';
    if ((char)*plVar1 != '\0') {           // *plVar1 = "_displayRequested" flag
        // ...builds an IPC message using constant 0x1000000006...
        uVar5 = FUN_fffffe0009f41840(plVar3, &local_100);   // sends it
        ...
    }
    // else: flag not set -- no IPC sent, falls through untouched
}
```

The two IPC-message constants used here and in the release path:

```
setPowerState(powerstate=1) message constant: 0x1000000006
displayRelease message constant:              0x1000000007
```

Both are `0x1_00000000 | N` shaped -- a version/type tag in the high
32 bits, and a plain method index in the low 32 bits. **The low-32-bit
values, 6 and 7, are exactly the same AFK/EPIC method indices our own
driver already uses**:

```c
// drivers/gpu/drm/apple/dptxep.c
int dptxport_request_display(struct apple_epic_service *service)
{
	return afk_service_call(service, 0, 6, NULL, 0, 16, NULL, 0, 16);
}
int dptxport_release_display(struct apple_epic_service *service)
{
	return afk_service_call(service, 0, 7, NULL, 0, 16, NULL, 0, 16);
}
```

## What this means

On real macOS, `request_display` (method 6) is not simply sent once,
unconditionally, at connect time the way our driver does it. It is
sent from inside the `setPowerState(1)` handler -- i.e. specifically
at the moment the AP's own IOKit power-management framework transitions
this DPTX remote port proxy's power domain to "on" -- and only when a
display session has already been flagged as wanted. Put differently:
**macOS re-sends (or, depending on ordering, first sends) `request_display`
at the exact moment the power domain goes active, not merely once at
initial connection setup.**

Our driver's `dcp_dptx_connect()` sends `dptxport_request_display()`
unconditionally as one step in a linear connect sequence, with no
equivalent "power domain went active" gating or re-send. This is a
structural difference: it does not yet prove causality (it's equally
possible our existing single call already lands at a state DCP
considers valid, and the real gap is elsewhere), but it is now the
single most concrete, mechanically-grounded, and cheaply testable
difference found between our sequence and real macOS's.

## Additional context gathered (for completeness)

- `initialPowerStateForDomainState` (the IOKit hook that determines
  what power state to assume when a parent power domain changes)
  unconditionally `return 0` for this class -- the resting/default
  assumption is always "off", never "already on".
- `AppleCIODPTX::handlePowerOn`/`handlePowerOff` (the class used for
  the *direct*-PHY DPTX path, not the Type-C remote-port-proxy path)
  use a completely different, unrelated mechanism: both call the same
  helper (`FUN_fffffe00093327e4`) with fixed arguments
  `(this, 0, *(this+0x110), 0x34, 2, 4, <1 or 0>)` -- not
  `synchronousChangeDPTXPowerStateTo` at all. This confirms the two
  classes (`AppleCIODPTX` for direct/fixed ports,
  `AppleDCPDPTXRemotePortProxy` for Type-C/dcpext-routed ports) use
  entirely separate power-management implementations, which is
  consistent with -- and helps explain -- why nothing found earlier
  this session while studying `AppleCIODPTX::bringConnectionUp`
  (the function this whole project's original DPIN0/MODE_A/MODE_B
  investigation was built around) ever touched this mechanism: it's
  simply the wrong class for it. The DPTX remote-port-proxy's own
  connection-establishment code (not yet identified/decompiled) would
  be the right place to look for whatever sets `_displayRequested` or
  otherwise triggers the initial `changePowerStateTo(1)`.
- The `requestDisplay`/`releaseDisplay` wrapper functions
  (`FUN_fffffe000930adb0`/`FUN_fffffe000930aed0`) are each referenced
  by exactly two small trampolines that only differ in how they
  compute the object pointer (`param_1` directly vs. `param_1 - 0x600`)
  before dispatching onto the work loop -- consistent with one being
  the plain C++-method entry and the other being the `IOUserClient`
  external-method (`IOConnectCallMethod`) trampoline for the same
  logical operation. This confirms `requestDisplay`/`releaseDisplay`
  are genuinely top-level, externally-invokable methods (called by
  macOS's window server / graphics stack -- the functional counterpart
  of our own Hyprland atomic-commit "enable" step), not something
  reached via another kernel-internal call chain worth tracing further
  down from this direction.
- Ghidra's own Mach-O loader does **not** apply this kernelcache's
  real (mangled) symbol names to functions or its own symbol table,
  despite `getNumSymbols()` reporting 815825 present -- confirmed by
  an exact-name lookup (`getSymbols(name)`) and a wildcard search
  (`getSymbolIterator("*DPTXRemotePortProxy*", true)`) both returning
  zero matches, while `llvm-nm` reads the same names from the raw file
  instantly. **For any future kernelcache work, resolve addresses with
  `llvm-nm /tmp/kernelcache.macho | grep <mangled-or-partial-name>`
  first, then feed the resulting hex address straight into Ghidra's
  `AddressFactory.getAddress()`/`FunctionManager.getFunctionContaining()`**
  -- do not rely on Ghidra's own name search for this binary.

## Suggested next hardware test (not yet run)

Add a second `dptxport_request_display()` call after the native DPIN0
crossbar handshake completes (i.e. after crossbar bring-up succeeds,
mirroring "resend request_display once the power domain/crossbar is
actually up"), rather than relying solely on the single call already
issued earlier in the connect sequence. This uses only an already-
existing, already-safe AFK/EPIC method (method 6, already sent once
every successful test this project has ever run) -- no new register,
no new APCALL, no new address. Low risk, directly motivated by a
decompiled real-macOS code path, and has not been tried in any
candidate to date.

If this doesn't produce a picture, the next place to look is
`setPowerState`'s `powerstate == 0` (deactivate) path and
`initialPowerStateForDomainState`, neither decompiled yet this session,
plus what actually flips the `_displayRequested` flag itself (not yet
traced -- it may be set by a different, earlier connect-path function
that hasn't been identified).

No hardware register write was made in the course of this
investigation -- purely offline kernelcache decompilation.
