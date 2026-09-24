# 0130: widen DPTX_CONNECT_TIMEOUT to 8s as a diagnostic

Direct continuation of 0129. Oliver confirmed by eye: no picture, no
flicker, nothing at all on the monitor that boot -- consistent with
`DPRX` staying 0 the whole time in the capture.

## What 0129 actually confirmed, and what it left open

Widening `set_hpd`'s own timeout worked exactly as intended: zero
AFK-layer timeouts anywhere in the 0129 capture, `release_display` itself
returned `result=0` instead of `-110` on both connect attempts. That's a
real, positive result -- the 1-second host timeout genuinely was cutting
off a valid (if slow) DCP reply for that one call, confirming the
"cut off, not fundamentally broken" reading for `set_hpd` specifically.

But the failure didn't disappear, it moved: both attempts hit exactly
0127's own failure line, `dcp_dptx_connect: timed out waiting for port %u
link configuration` (`dcp.c`, `wait_for_completion_timeout(&dcp-
>dptxport[port].linkcfg_completion, DPTX_CONNECT_TIMEOUT)`, 2000ms). The
full, precise timing from `captures/2026-09-24-0129-boot-kernel.log`:

- `request_display: call #1 result=0` at 08:18:44.
- Silence on the apcall channel -- not one single `DPTXPort: APCALL ...`
  line of any kind -- for 5 seconds.
- 08:18:49: APCALL 22 (`DEVICE_NOT_RESPONDING`) and APCALL 24
  (`DEVICE_NOT_STARTED`), DCP's own unprompted verdict.
- 08:18:51: `timed out waiting for port 0 link configuration` -- exactly
  2000ms after 08:18:49, which is strong circumstantial evidence that
  `set_hpd`'s own reply (and the `linkcfg_completion` wait's start) landed
  right at 08:18:49, the same moment as the `DEVICE_NOT_RESPONDING`/
  `DEVICE_NOT_STARTED` upcalls. Attempt #2 (08:18:52 onward) reproduces
  the identical pattern, down to the same ~5s silence and the same two
  upcalls, before `USB4 protocol probe finished: -110; no automatic
  retry` ends the boot's retry loop.

Unlike 0127, `SET_LINK_RATE`, `WILL_CHANGE_LINK_CONFIG`, and every other
apcall in that instant post-request_display burst simply never appear --
not even undecoded ones (the dispatcher prints `DPTXPort: APCALL N (X
bytes)` unconditionally for every apcall it receives, decoded or not, so
their total absence means DCP genuinely sent nothing on this channel for
those 5 seconds, not that something is going unlogged).

## Reading this fairly

Two ways to read `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` landing at
the same moment as `set_hpd`'s own (now-successful) reply:

- They could be DCP's **terminal** verdict -- "I tried for 5 seconds, the
  sink never answered, I'm done with this attempt" -- in which case
  widening `DPTX_CONNECT_TIMEOUT` changes nothing, because DCP has
  already decided not to send `WILL_CHANGE_LINK_CONFIG`/`SET_LINK_RATE`
  before our wait for them even starts.
- Or they could be an informational status notification running in
  parallel with DCP *still* internally attempting to train the link on
  its own longer timeline, exactly as `set_hpd` itself turned out to be
  slow rather than broken -- in which case a wider wait could still catch
  a genuine, later `DID_CHANGE_LINK_CONFIG`.

0129 already falsified the "it's all just host impatience" theory in its
simplest form (if it were, 0129 alone would have reached `DPRX_DONE=1`;
it didn't). But it did not by itself distinguish these two readings for
*this specific* wait, since `DPTX_CONNECT_TIMEOUT` was still only 2000ms
that run. The only way to actually tell them apart, the same way 0129
settled the question for `set_hpd`, is to widen this one too.

## The change (kernel commit 32931b9)

Widened the `DPTX_CONNECT_TIMEOUT` macro (`dcp.c:1379`, was
`msecs_to_jiffies(2000)`) to `msecs_to_jiffies(8000)` -- same value as
0129's `set_hpd` budget, for consistency, and because it is already known
to be a safe order of magnitude for this codebase. Single macro changed;
its only other reference (`dev_dbg` elapsed-time print) is unaffected in
behavior, just prints a bigger number if this wait is what ends up
taking a while. Unlike 0129, `dcp->hpd_mutex` is already released before
this wait begins (`dcp.c:1470`, unchanged) -- this change adds no
additional lock-hold time at all, only lower risk than 0129's already-safe
change.

Deliberately left everything else alone: `validate`/`connect`/
`request_display`/`set_hpd` all already succeed on every run so far
(0129 proved that), and the only unresolved wait left in the direct path
to `DPRX_DONE=1` is this one.

## Known uncertainty

- If `SET_LINK_RATE`/`WILL_CHANGE_LINK_CONFIG` still never appear even
  with 8 seconds of patience, that's a clean, fairly conclusive result:
  DCP's firmware is not merely slow here, it has decided not to train
  this link at all, on this pipeline/port, every time. That would close
  the whole "it's just cascading timeouts" family of hypotheses for this
  candidate chain, and the next place to look is why DCP reaches that
  verdict at all -- e.g. actually decoding what the ACIO `dpin0 analog`
  register's offset `0x18` value is telling us (it has now read `0000100a`
  on the one success, `00001017` on three of four failures, and `00000017`
  on the fourth -- flagged again, still not decoded, but with more data
  points than 0129 had).
- If it does succeed: expect `SET_LINK_RATE`, `DID_CHANGE_LINK_CONFIG`,
  and, for the first time on the *correct* pipeline,
  `dcp_tunnel_crossbar_up()` actually running. A new failure there
  (crossbar-specific, e.g. the `FIFO_RD_N_CLK_EN` field-width guess
  flagged back in `notes/2026-09-24-0127-*.md`) would not be a setback --
  it would mean this candidate's own question was answered yes, and be
  real, new, unexplored territory.

## Build verification

Only `dcp.o` recompiled (single macro value + comment). New
`appledrm.ko` SHA256:
`2d0b5f5b9d831f0a740a150e47d9774858cf9bf089c97698f32d70dedacced8c`.
`thunderbolt_apple.ko`, `mux-apple-display-crossbar.ko`,
`phy-apple-atc.ko`, `thunderbolt.ko` all verified byte-identical to
0128/0129 (none touched this candidate). Stale-symlink sweep clean (same
pre-existing, already-triaged non-symlinks as every candidate since
0115: build-generated `.mod.c` files, `src/phy/dptx.{c,h}`, `src/dispclk/
apple-dispclk.c`). `test-dpin-handshake.c` 13/13 pass (regression check
only). Patch: `patches/0130-widen-linkcfg-timeout-diagnostic.patch`.
`scripts/manage-0130.py` derived from `manage-0129.py`: only the
`appledrm` hash and the `CONFIG`/`BACKUP` path suffixes changed;
`OPTIONS` is byte-identical to 0128/0129's.

## Test plan

Same protocol, single boot, hub already connected, still dcpext1/
right-port. Watch specifically for:

1. `request_display: call #1 result=0` still appearing identically.
2. Whether any apcall at all appears in the 5-second window that was
   previously silent -- `SET_LINK_RATE`, `WILL_CHANGE_LINK_CONFIG`, or
   anything else, decoded or not.
3. Whether `dcp_dptx_connect: timed out waiting for port 0 link
   configuration` disappears (meaning `DID_CHANGE_LINK_CONFIG` arrived in
   time) or reappears (now after ~8s instead of ~2s).
4. If it disappears: `dcp_tunnel_crossbar_up()`'s own result (success or
   a new failure, on the correct pipeline for the first time), `DPRX`,
   and -- the actual goal -- a picture, confirmed by Oliver's own eyes,
   not by log inference.
5. If it reappears at ~8s: do not widen this wait again without new
   evidence; the next candidate should target why DCP declares
   `DEVICE_NOT_RESPONDING`/`DEVICE_NOT_STARTED` in the first place, not
   how long the host waits for it.
