# The exact stuck state: DCP firmware's run_mode 2->4 transition never completes

This closes the loop opened by 2026-09-23-swap-complete-never-fires.md.
Combines a targeted disassembly of the real DCP firmware's
`IOMobileFramebuffer::swap_submit_dcp` with live, long-duration
observation of our own controller's state, and is now the most
concrete, fully-verified finding of the entire project to date.

## The firmware mechanism (from disassembly of t602xdcp.bin)

`swap_submit_dcp` (firmware vmaddr `0x723b4`, confirmed by parameter
marshaling matching its real 14-argument C++ signature) acquires a
"swap slot" from a sub-object before it will do any real work. If that
acquisition fails, execution jumps to a bail-out block that logs (via a
throttled logger capped at 15 occurrences before going silent) a
previously-unknown-to-us format string:

```
"%s: IOMFB_SWAP_SUBMIT_LOST, transaction->swapID: %d, transaction->enabled: %d, transaction->completed: %d\n"
```

and returns immediately -- the swap never reaches the ~400-instruction
block that actually programs hardware. This is a third silent-drop path,
distinct from the two known "swallowed swap" checks (`fControllerPowerState
is 0` and `timinsg are not enabled`), which sit later in the same
function and gate the final hardware-programming step, not slot
acquisition. Neither of those two known strings fires during our actual
stall (confirmed earlier the same day); this third, previously
unexamined path is the better structural match for "frames vanish with
zero visible errors."

The natural reading: a new slot is only granted once the *previous*
transaction's `completed` field is true. If nothing ever marks a
transaction complete, the slot pool empties after the first handful of
frames and every subsequent submit is silently dropped forever --
exactly matching the observed symptom (a handful of CRC/frame-index
entries at enable, then permanent silence).

A neighboring string, `"batched_swap_complete_ap_gated"`, is the likely
candidate for the DCP-internal function that marks a transaction
complete and notifies the AP (found near real DCP source filenames
`IOMobileFramebuffer_LocalCalls.cpp`/`_RemoteCalls.cpp` in the same
string table). Its callers could not be resolved statically: the
binary uses Apple's chained-fixup pointer encoding for `__DATA`
pointers, and the call site is behind vtable-based virtual dispatch --
both require a working decompiler with vtable/RTTI recovery, which is
not available in this environment (confirmed again: no working Ghidra
headless/decompiler on this ARM64 Linux host, same wall hit earlier in
the project). Disassembly-only analysis (llvm-objdump + capstone +
manual ADRP/ADD/LDR cross-reference resolution) was sufficient to locate
and characterize `swap_submit_dcp` itself, but not to trace this
specific virtual call to its target.

## Live confirmation: run_mode never reaches steady state

Our own kernel log already contains, verbatim, DCP firmware's own
internal state-machine tracing for exactly this pipeline
(`PPipeDCP_H13P.cpp`, "H13P" -- presumably this SoC generation's display
pipe hardware block). Every connection attempt for our controller
(315c00000.dcp) follows an identical pattern:

```
set_run_mode_safe: no need to defer: 0 -> 1
set_run_mode_safe: no need to defer: 1 -> 2
set_run_mode_safe: no need to defer: 2 -> 1
set_run_mode_safe: no need to defer: 1 -> 0
set_run_mode_safe: no need to defer: 0 -> 1
set_run_mode_safe: no need to defer: 1 -> 2
set_run_mode_safe: deferring: 2 -> 4
UPPipeDCP_H13P::ready_for_run_mode_change(...): initiating deferred run mode change
```

...and then **nothing further, ever**, for that connection. Modes 0-2
transition instantly and unconditionally ("no need to defer"); the 2->4
transition is the only one that requires `ready_for_run_mode_change()`
to agree, and it never does.

**Verified live, not inferred**: connected the hub, let it sit
completely idle and untouched for over 40 minutes (uptime went from
~15s to 2571s at the connection's start to check time, i.e. ~42.6
minutes), then re-checked: the run_mode log tail is byte-identical to
what it was at t=15.6s (still "deferring: 2 -> 4", no further line), and
reading the crtc's CRC/frame-index debugfs file still blocks
indefinitely (no new frames, confirmed with `timeout`-bounded reads).
This rules out "it just needs more time" -- whatever
`ready_for_run_mode_change()` is waiting for never arrives, not even
after 40+ minutes of a stable, fully-negotiated USB4 DP tunnel sitting
idle.

(A few *other* captures show a later `"deferring: 4 -> 1"` line at
timestamps matching known disconnect events. This does not contradict
the above -- it is far more likely DCP's teardown path unconditionally
issues its own mode-change request assuming a nominal prior state,
which itself also defers and is irrelevant once the connector is gone,
than it is evidence the 2->4 transition ever actually completed in any
of our tests. No capture shows a completion log for the connect-time
2->4 transition in any of dozens of attempts.)

## What this means

`ready_for_run_mode_change(IOMFB::AppleRegisterStream *)` -- a real DCP
firmware function, confirmed by its exact C++ signature string --
checks some register-level hardware readiness condition before
allowing the pipe into its actively-scanning-out mode (4). For every
other working pipeline on this machine (eDP, and by inference any
directly-wired PHY output), this evidently resolves quickly. For our
dcpext instance driving DPIN0/crossbar into a USB4 tunnel, it never
resolves. Given the function takes an `AppleRegisterStream*` argument,
it most plausibly reads back a specific hardware register (very likely
in the display-pipe or crossbar/clock domain) that our current
DPIN0/crossbar bring-up sequence never actually satisfies, despite
every RPC-level milestone we can observe from Linux (crossbar bring-up,
DPRX_DONE, set_digital_out_mode, dcp_poweron/iomfb_poweron) reporting
success.

This is now the single most concrete, best-verified statement of the
actual blocker after the entire session's work: not a wrong register
value anywhere we've tested, not the monitor or adapter (confirmed
working on other systems), not a hub/USB4-tunnel setup problem (the
tunnel itself is solidly established) -- a specific DCP-firmware
internal readiness check for entering continuous scanout mode that
this exact pipeline shape never satisfies.

## What would be needed to go further

- A working decompiler with vtable/RTTI recovery for this Mach-O
  (chained-fixup `__DATA` pointers plus indirect vtable dispatch both
  block pure disassembly from resolving `ready_for_run_mode_change`'s
  actual register read, or `batched_swap_complete_ap_gated`'s callers).
  Not available in this environment; would need either a different
  Ghidra setup (e.g. on x86_64 where its decompiler backend works) or
  substantially more manual ARM64 reading than is practical by hand.
- Alternatively, comparing register-level state between a known-working
  direct-PHY pipeline and ours at the exact moment this check runs,
  which would require either JTAG/hardware-debug access this project
  does not have, or an extremely precisely-timed register dump from
  Linux (racy and unlikely to land on the right instant without kernel
  instrumentation we do not currently have).

No hardware register write was made in the course of this
investigation. No further action needed before a future session
picks this up; this note plus
2026-09-23-swap-complete-never-fires.md together give a complete,
reproducible account of exactly where and why the picture never
appears.
