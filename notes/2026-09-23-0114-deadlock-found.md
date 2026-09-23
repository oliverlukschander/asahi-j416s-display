# Found it: 0114's resend deadlocks the AFK/EPIC ordered workqueue

This closes the loop opened by
`notes/2026-09-23-0114-0115-left-port-result.md` (both `request_display`
calls returning `-110`/ETIMEDOUT on the first live 0114+0115 test).
Root cause found by decompiling the XNU kernelcache side of the real
macOS DPTX connection sequence and then re-reading our own driver's
AFK/EPIC transport with that sequence in mind. This is a **proven,
code-verified, deterministic bug**, not a new hypothesis to test on
hardware -- no hardware action was needed to find it.

## The XNU-side finding that led here

Set up the Ghidra/qemu decompiler again (rebuilt from scratch, see
below -- `/tmp` does not survive a reboot) and, this time, resolved
every relevant class via `llvm-nm`'s real demangled symbols instead of
Ghidra's broken Mach-O symbol loader (same gotcha as before). Traced
the real chain for a Type-C/dcpext DPTX connection:

- `AppleDCPDPTXRemotePortUFP::displayRequest()` -- the "upstream facing
  port" half of the pair, paired with `AppleDCPDPTXRemotePortProxy`
  (the AP<->DCP AFK/EPIC half; `Proxy::start()` creates and owns the
  UFP as its child) -- calls `_armIOProvider->connectTo(*dfp)` (i.e.
  `Proxy::connectTo()`) **first**, and only calls
  `super::displayRequest()` (which eventually flows through to
  `Proxy::displayRequest()` -> `synchronousChangeDPTXPowerStateTo(1)`
  -> `setPowerState(1)`'s gated handler -> the actual `request_display`
  AFK method-6 IPC) if that connect succeeds. If it fails, the code
  explicitly logs `"_provider->connectTo(*dfp) ret=0x%08x; skipping
  super::displayRequest()"` and does nothing further.
- `Proxy::connectTo()` sends its own distinct IPC (role/supportsHPD
  packed into one field, matching our driver's already-existing
  `dptxport_connect()`, AFK method 11) through the same generic
  IPC-send helper as `setPowerState`/`displayRequest`/`displayRelease`.

This matches our driver's own `dptxport_connect()` (method 11) --
already implemented, already called before `dptxport_request_display()`
in the "analog DPIN" block in `dcp_dptx_connect()`
(`drivers/gpu/drm/apple/dcp.c:1598`/`1611`) -- so this part was **not**
the gap. Re-reading the actual captured log line-by-line
(`captures/2026-09-23-0114-0115-left-kernel.log`) with this in mind is
what surfaced the real bug, below.

## The real bug: a self-deadlocking nested AFK call

Exact timestamps from this boot's capture:

```
[19.217336] USB4: analog DPIN bind port=0 (unit 0)
[19.218034] USB4: analog DPIN validate core=1 atc=0: 0
[19.219009] USB4: analog DPIN connect core=1 atc=0 HPD: 0        (dptxport_connect() succeeds)
[19.219874] USB4: analog DPIN set_hpd: 0
             -- dptxport_request_display() called here (1st, "outer" call) --
[19.222207] native DPIN0: active=1 ...                            (DCP's incoming ACTIVATE APCALL
[19.222359] native DPIN0: DCP active=1 result=0                    handled while the outer call above
                                                                    is still pending)
[20.257023] USB4: resend request_display after native DPIN0 activate: -110   (2nd, "inner" call, ETIMEDOUT)
[20.257508] USB4: analog DPIN request_display core=1 atc=0: -110            (1st/"outer" call, ETIMEDOUT
                                                                              ~1.037s after it was issued)
```

The ~1.037s gap between the outer call being issued (~19.220) and
both calls failing together (~20.257) is exactly
`afk_service_call()`'s default timeout,
`MSEC_PER_SEC` (`drivers/gpu/drm/apple/afk.c:1003`).

The mechanism, read directly from `afk.c`:

1. `afkep->wq` is created with `alloc_ordered_workqueue()`
   (`afk.c:69`) -- an **ordered** workqueue, meaning at most one work
   item runs at a time, strictly in submission order.
2. Every incoming EPIC message (both replies to our own outbound calls,
   and incoming APCALLs like ACTIVATE from DCP) is received via
   `afk_receive_message()` -> `queue_work(ep->wq, ...)` ->
   `afk_receive_message_worker()` (`afk.c:726-738`) -- i.e. **all**
   incoming-message handling, for both directions, runs on this one
   ordered queue.
3. For an incoming APCALL (`EPIC_TYPE_NOTIFY`/`EPIC_CAT_NOTIFY`),
   `afk_recv_handle_std_service()` calls `service->ops->call(...)`
   (`dptxport_call()` -> `dptxport_call_activate()` for ACTIVATE,
   idx 0) **synchronously, inline, on this same worker**, and only
   sends the reply (`afk_send_epic(...)`) *after* that call returns
   (`afk.c:480-489`).
4. For an outbound call's reply, `afk_service_call_timeout()`
   (`afk.c:1006`) blocks the *calling* thread on
   `wait_for_completion_timeout()`; the matching
   `complete(service->cmds[idx].completion)` (`afk.c:422`) is itself
   only ever invoked from inside that same
   `afk_receive_message_worker()`/`ep->wq` path, since it fires when
   the reply message for that command arrives.

0114 added a call to `dptxport_request_display()` (a full, blocking
`afk_service_call()`) **from inside `dptxport_call_activate()`**
(`drivers/gpu/drm/apple/dptxep.c:708-714`) -- i.e. from *inside* a
`service->ops->call()` invocation already running on `ep->wq`. That
inner call blocks the *only* thread that is capable of ever running
the work item that would process DCP's reply and call `complete()` on
it. **This inner call cannot ever succeed -- it is a deterministic,
100%-reproducible deadlock, not a race or a flaky timeout.** It always
returns `-ETIMEDOUT` after exactly one second, no matter what DCP does.

Worse, it collaterally dooms the **original** (outer, pre-existing,
non-0114) `request_display` call too: DCP asked us to ACTIVATE
specifically because it's in the middle of handling that outer
request and needs the AP to bring up the physical link first; it is
almost certainly waiting for our ACTIVATE reply before it will answer
the outer call. Our ACTIVATE reply is delayed by the full second the
inner call wastes deadlocking, and by the time we finally send it,
the outer call's own independent one-second timeout has already (or
is about to have) expired. So both calls fail together, at
essentially the same instant, exactly as observed -- **regardless of
whether DCP itself was ever going to grant the display**. This test
provides no information one way or the other about whether the
*original* single `request_display` call would have succeeded on its
own; 0114's addition made that unobservable.

## What this means for the whole 0114 hypothesis

The XNU trace that motivated 0114 (real macOS resends `request_display`
from `setPowerState`'s gated handler when the power domain activates)
is still accurate as a description of real macOS. But 0114's
*implementation* of that idea -- calling it synchronously from inside
the inbound ACTIVATE handler -- was structurally unable to ever work
on this transport, independent of whether the underlying idea has
merit. It also means every one of today's log lines showing "-110"
is fully explained by this software bug; none of it is evidence about
DCP firmware's own internal state or about the port-target encoding
question left open in 0115. Both of those remain open, but this bug
was actively preventing us from observing whether they matter.

## Proposed fix (0116, not yet built/tested)

Stop calling `dptxport_request_display()` synchronously from within
`dptxport_call_activate()`. Two parts:

1. **Immediate, safe change**: revert to the pre-0114 behavior in
   `dptxport_call_activate()` -- do the native DPIN0 hardware
   activation and return immediately (no inner AFK call), so the
   ACTIVATE reply goes out promptly and the *original*, outer
   `request_display` call (already issued from ordinary process
   context in `dcp_dptx_connect()`, not from `ep->wq`) gets an
   uncontended chance to receive DCP's real reply within its own
   one-second window. This isolates and directly tests: does the
   pre-existing single call succeed once it's not starved by our own
   deadlock?
2. **If (1) still doesn't produce a picture** and a genuine resend is
   still wanted per the XNU `setPowerState`-activation-triggered
   pattern, issue it from a deferred work item (a plain
   `INIT_WORK`/`schedule_work()`, on the default system workqueue, not
   `ep->wq`) queued from within `dptxport_call_activate()` rather than
   called inline -- so it runs after the ACTIVATE reply has actually
   gone out and the ordered queue is free again to process a real
   reply.

Only (1) is proposed for the next hardware test: it is a pure revert
of already-tested-safe code (the native DPIN0 activation itself, from
0113, is untouched), changes no register, address, or protocol beyond
removing the deadlocking call, and directly isolates the one new
variable worth testing next.

## Candidate 0116: built and verified offline

Kernel commit `c554afe` (`drivers/gpu/drm/apple/dptxep.c` only --
`dptxport_call_activate()` reverted to do just the native DPIN0
activation and return, per fix (1) above). Patch:
`patches/0116-drm-apple-dptx-stop-deadlocking-the-AFK-ordered-work.patch`.
Only `dptxep.o` recompiled (confirmed from the `make` output); new
`appledrm.ko` SHA256:
`ec1a940a3482a804f08ea8f59a7062cb948b7047acaa5cc7eab4b7c3120b14ce`.
No other module changed (mux/atc/thunderbolt/thunderbolt_apple hashes
identical to 0115). Re-ran the project-wide stale-symlink check
(`find src -type f \( -name '*.c' -o -name '*.h' \) ! -name '*.mod.c'
... test -L`); only the two already-known, already-deferred files from
0115 (`src/phy/dptx.c`/`dptx.h`, `src/dispclk/apple-dispclk.c`) are
still plain copies -- no new regression.

`scripts/manage-0116.py` derived mechanically from `manage-0115.py`
(candidate number and the one changed hash only; syntax-checked).
Same `OPTIONS` string as every candidate since 0109 (this fix changes
behavior, not module parameters, so nothing new needs arming).

Per Oliver's standing preference, the hub may stay connected for the
install and reboot. Deployment plan, identical shape to every prior
candidate:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0116.py install
```

Backs up the currently-installed 0115 modules/initramfs to
`/var/tmp/j416s-0116-before`, installs the new `appledrm.ko`, rebuilds
and verifies the initramfs. No live module reload, register write, or
reboot. After install is logged/committed/pushed, request a
`systemctl reboot`, then verify via `manage-0116.py check` and the
module parameters before asking Oliver to reconnect the hub (currently
on the left port) and report what the monitor shows -- the actual
test of whether removing the deadlock lets the pre-existing
`request_display` call succeed.

## Decompiler infrastructure (rebuilt this session, again under /tmp)

Same setup as documented in `2026-09-23-power-state-gate-traced.md`
and `2026-09-23-xnu-power-state-trace.md` (qemu-user x86_64
`decompile` wrapper for Ghidra 12.1.4's missing `linux_arm_64`
binary), rebuilt from scratch since `/tmp` was wiped by the 0115
reboot. Kernelcache re-extracted and re-verified
(`/tmp/kc-extract/kernelcache.macho`, SHA256
`9615a486511c7a60b141d7f4291361c5212e908546d6568890029bb90b5431e7`,
same as every prior extraction). New this pass: resolved every
address via `llvm-nm kernelcache.macho`'s real demangled C++ symbols
first (`AppleDCPDPTXRemotePortProxy::*`, `AppleDCPDPTXRemotePortUFP::*`,
`IODPTXPort::*`), then fed hex addresses straight to
`FunctionManager.getFunctionContaining()` -- much faster and more
reliable than the string/xref-based approach needed for the
DCP-firmware side (which has no symbol table at all).

No hardware register write, MMIO access, or physical action was
performed to reach this finding -- purely kernelcache decompilation
and re-reading our own already-written driver source and captured log
against it.
