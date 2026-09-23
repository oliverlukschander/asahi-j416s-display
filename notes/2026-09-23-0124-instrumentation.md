# 0124: close the silent-failure blind spots instead of guessing another bit

Direct continuation of 0123 after its result ("no picture, DCP still never sends
SET_LINK_RATE"). This candidate makes **no behavioral change at all** -- it only
adds logging. The goal is to get a single hardware test's dmesg to answer several
open questions definitively instead of guessing an eighth signal to flip.

## Why a pure-logging candidate

0118 through 0123 changed a different bit or ordering each time and got the
identical externally-visible outcome every time (DCP reaches `INACTIVE_SINK_DETECTED`,
never sends `SET_LINK_RATE`, 12s DPRX timeout, no picture). That consistency across
genuinely different inputs means we've been guessing blind: we do not actually know
whether DCP is rejecting our `connect`/`validate_connection` calls outright (with a
specific, currently-invisible error code), whether it accepts them but a *different*
downstream precondition is unmet, or whether our own driver is doing something (an
unacked apcall reply, a falsely-timed-out `request_display`, a second untracked
connect) that DCP is reacting to. Continuing to flip bits without that visibility is
not a productive use of another hardware test.

Three parallel investigations (this session, Opus 5.5 agents A/B/C) converged on
concrete, previously-invisible gaps rather than more hypotheses to test blind:

## Finding 1 (Agent A): DCP's actual per-call retcode is captured and thrown away

`afk_service_call_timeout()` (`drivers/gpu/drm/apple/afk.c`) receives DCP's real
per-call `u32 retcode` (the value DCP's firmware itself returns from functions like
`connectTo()`/`validateConnection()` -- confirmed via this session's Ghidra
decompilation of `t602xdcp.bin` to be capable of returning specific, meaningful
codes such as `0xe00002e2`/`0xe00002c2` depending on internal firmware state) but
at the `if (retcode) { ret = -EINVAL; goto out; }` branch it discards the value
entirely with zero logging. A second, adjacent branch (magic/group/command echo
mismatch) does the exact same thing. Every hardware test this whole project has run
has been blind to whatever DCP's firmware actually said when a call failed.

## Finding 2 (Agent B): a failed apcall handler gets **no reply sent to DCP at all**

`afk_recv_handle_std_service()` (`afk.c`): if `dptxport_call()` (the apcall
dispatch handler) returns non-zero for any reason, the driver does
`kfree(reply); return;` -- it sends DCP *nothing back*, not even an error ack.
Concretely, `dptxport_call_did_change_link_config()` returns `-EALREADY` if
`dptx->usb4_link_up_attempted` is already set (`dptxep.c`); if that path is ever
hit a second time in the same connection attempt, DCP's own AFK/EPIC layer is left
waiting on an acknowledgment that will never arrive. This has never been logged, so
we don't know today whether it has been happening on any of our tests.

Agent B also found the analog-DPIN branch of `dcp_dptx_connect()` (`dcp.c`,
"reselect dpin after nub") has no `connected` guard and never sets it, so several
call paths (CRTC enable via `dcp_poweron()`, the cold-boot auto-arm path, the
`usb4_arm`/`usb4_dptx_train` module params, replug) could in principle re-enter
`connect()`/`validate_connection()` without an intervening release. This candidate
does **not** fix that guard (a behavioral change); it only adds the counters needed
to prove or disprove it firing on our actual boots.

## Finding 3 (Agent C + follow-up): the "bit 8" this project has been chasing since 0118 is not what we thought

Agent C's read of the actual per-boot journals for 0118-0123 shows exactly one
`validateConnection`/`connectTo` call per boot on `315c00000.dcp` -- so DCP's
internal "active connection count" (found via this session's decompile of
`connectTo()`, `*(uint*)(*(long*)(this+0x138)+8)`) should have been 0 every time,
ruling out a stale/repeated connection as the reason the count-gated branch never
produced a picture.

Re-reading the decompiled `connectTo()` after Agent C's report surfaced a real
misidentification carried since 0118: `connectTo()`'s "trivial path" test and its
later `(uVar4>>8&1)==0` gate operate on `uVar4`, the *original* 64-bit register
DCP receives -- and since `struct dcpdptx_connection_cmd { u32 target; u32 unk; }`
is passed as one 8-byte value, the low 32 bits are `target` and the high 32 bits
are `unk`. `uVar4>>8&1` is therefore bit 8 **of `target`**, not of `unk`/attrs. Per
`dptxep.h`, `DCPDPTX_REMOTE_PORT_DIE = GENMASK(11,8)` -- bit 8 of `target` is the
low bit of the *die index*, which is constant (0) for our single-die M2 Pro
regardless of anything 0118-0123 changed. The `supportsHPD`/role bit we've spent
six candidates on lives entirely in `unk` (the *high* 32 bits) and was never what
that specific gate in `connectTo()` was checking. It also means we always take
`connectTo()`'s non-trivial branch (target's low byte, core/atc, is never 0 for a
real route; `unk` always carries `0x100`, which falls inside the trivial-path's
`0x83ff00000000` mask), so the un-decompiled `FUN_001a7d40()` deep-validation call
runs, and rejects or accepts us, on every single test we've run. If it rejects us,
Finding 1's fix will show the exact retcode on the next test with zero further
firmware reverse-engineering required.

## The change (this candidate, logging only)

`drivers/gpu/drm/apple/afk.c`:
- Log DCP's actual retcode (hex) plus group/command on the previously-silent
  `retcode != 0` branch in `afk_service_call_timeout()`.
- Log sent-vs-echoed magic/group/command on the previously-silent mismatch branch.
- Log every transport-level failure (`-ENOMEM`/`-ENOSPC`/`-ETIMEDOUT`/ring-full)
  with group/command context, both in `afk_service_call_timeout()` and the
  `-ETIMEDOUT` path inside `afk_send_command_timeout()`.
- `dev_dbg` success line for symmetry (silent unless dynamic debug is enabled).
- Log when an apcall handler returns non-zero right before the previously-silent
  "send DCP nothing back" path in `afk_recv_handle_std_service()`.

`drivers/gpu/drm/apple/dptxep.c` / `.h`:
- Per-port call counters (`validate_calls`, `connect_calls`, `request_calls`,
  `release_calls`) on `struct dptx_port`, logged with `%pS` caller on every call to
  `dptxport_validate_connection()`, `dptxport_connect()`, `dptxport_request_display()`,
  `dptxport_release_display()` (the latter two previously had **no** logging at
  all). A call count greater than 1 on the same boot, or `release_calls == 0` before
  a second `connect_calls`, would directly confirm Agent B's re-entry hypothesis.
- Closed the remaining silent `-EINVAL` blind spots: `validate_connection`'s
  target-mismatch and non-USB4 attrs-mismatch returns, `connect`'s target-mismatch
  return, `set_hpd_timeout`'s unk-mismatch return -- all now `dev_warn` before
  returning.
- Every inbound APCALL's raw payload (up to 64 bytes) is now hex-dumped
  (`print_hex_dump`), not just its length -- covers `INACTIVE_SINK_DETECTED`,
  `ACTIVATE`, `FORCE_HOTPLUG_DETECT`, `SET_TILED_DISPLAY_HINTS`, `DEVICE_NOT_*`,
  none of which log their payload contents today.

No function signature changed, no control flow changed, no behavior changed for
any successful path. `afk_service_call()`/`afk_service_call_timeout()`'s callers
(dptxep.c, av.c, epic/dpavservep.c, afk.c's own debugfs helper) were all checked
(by Agent A) and none needed changes.

## Build verification

Only `afk.o`, `dcp.o` (unchanged content, recompiled only because it's in the same
module), and `dptxep.o` recompiled. New `appledrm.ko` SHA256:
`74e2d3cf57480937efd8b3064d750b9ba9e439007e17c83bed39a80fb5ed048d`. `phy-apple-atc.ko`,
`mux-apple-display-crossbar.ko`, `thunderbolt_apple.ko` and `thunderbolt.ko` all
byte-identical to their 0119/0123 known-good hashes (verified via direct
`sha256sum` comparison, unchanged since neither was touched). Stale-symlink sweep
clean. `test-dpin-handshake.c` 13/13 still pass (this candidate never touches
`drivers/thunderbolt/apple.c`, so this is a pure regression check).

## Test plan

Same protocol, single boot, hub already connected. This time the goal is not "does
the picture come up" (unlikely, since nothing behavioral changed) but "what does
dmesg now show that it never showed before":

1. Exactly how many times do `DPTX validate: call #`/`DPTX connect: call #` appear,
   and from which `caller=`? More than one of either, on this boot, confirms
   Finding 2's re-entry hypothesis.
2. Does any `AFK[ep:...] ... service call group %u cmd %u returned retcode 0x...`
   line appear? If `group 0 cmd 11` (connect) or `group 0 cmd 12`
   (validate_connection) shows a non-zero retcode, DCP is rejecting the connection
   outright and we finally know the real error code instead of a generic -EINVAL.
3. Does any `apcall %u handler returned %d, sending NO reply` line appear? If so,
   which apcall, and does it correlate with the point training stalls?
4. What do the new hex dumps for `INACTIVE_SINK_DETECTED`'s and `ACTIVATE`'s
   payloads actually contain?

Whatever this shows determines the next candidate; no further guessing planned
until this data is in hand.
