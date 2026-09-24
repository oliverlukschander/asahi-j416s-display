# 0135: isolate the port/pipeline confound; revert the FSM misreading

Direct continuation of 0134. At Oliver's request, ran a full parallel
research sweep (8 independent agents, ~1.1M tokens, 267 tool calls) across
this project's own 314KB historical archive, the reference PR's remaining
files, live web/GitHub research for prior art, and an exhaustive re-audit
of every capture this project has. This note is the synthesis and the one
concrete, well-motivated action it produced.

## Corrections to this session's own recent work

**The "stuck FSM" framing (0133/0134) was wrong.** This project's own
source, at the exact lines defining the offset in question, already
documents the real behavior -- from candidates 0054-0056, well before this
session began:

```
#define APPLE_CIO_DPIN_ANALOG_FSM	0x18
#define APPLE_CIO_DPIN_ANALOG_HOLE	0x20
#define APPLE_CIO_DPIN_ANALOG_EMPTY	0x80000000
...
/*
 * Analog MMIO writes are closed: +0x00 / +0x18 / +0x20 do not stick
 * (0054-0056). +0x18 is first-read status 0x1017 (read-to-clear).
 */
```

`0x80000000` isn't an error latch -- it's the register's own documented
*empty* sentinel. Offset `+0x18` is an ordinary one-shot, read-to-clear
status register: it holds a real value (`0x1017`-family) exactly once,
and reads as `EMPTY` on every read after that. Confirmed independently by
re-examining the earlier captures with fresh eyes: 0128 through 0132 (which
read this register only once, at the 12-second give-up) *never* see
`0x80000000` at all -- they still read `~0x1016/0x1017` at that point.
It only ever reads as `EMPTY` starting on the *second* time the driver
reads it -- which only 0133's every-500ms instrumentation ever did. The
"freeze" 0133 found wasn't the hardware getting stuck; it was 0133's own
polling consuming a one-shot status value that had already served its
purpose after the first read.

This also means candidate 0134's write-1-to-clear ack ("had zero effect")
was never going to do anything: there was nothing latched to clear.
`0x80000000` read back after the write is exactly the expected, correct
result for an already-empty one-shot register -- not evidence the write
mechanism failed.

There's a sharper edge to this than just "wasted a candidate": this
project's own `dpin_aux` module parameter has carried a comment, since
before this session, explaining *why* the default behavior only dumps
this block once, at the very end: `"0 = do not touch analog at tunnel-up;
dump it only after DPRX timeout (default). Tests whether consuming +0x18
aborted a handshake."` That is a documented caution against exactly what
0133 did. Reverted 0133/0134 back to that original, deliberately cautious
design (single post-mortem dump only); removed the now-premised-on-nothing
`apple_dp_ack_analog_fsm()`. Kernel commit 07dc4c1, part 1.

## The other, harder correction: the confound

Independently, two of the eight research agents (the exhaustive
register-table differ and the crossbar/port-symmetry audit) converged on
the same finding: **the one success (0127) and every failure since
(0128-0134) differ in both the physical Type-C port and the DCP pipeline
at the same time, never in isolation.** 0127 ran left-port
(`701ac0000.cio`) through the dcpext0 pipeline; every failure since has
run right-port (`f01ac0000.cio`) through dcpext1. This project's own
`notes/ACTION-LOG.md` already records that *port choice* was ruled out as
a variable by Oliver -- but that ruling was about not re-testing "does the
right port work at all," never extended to "therefore an undocumented,
per-instance ACIO register reads identically regardless of which physical
block you're reading." No data anywhere in this project supports that
second, stronger claim, and the offset `+0x18` first-read-value contrast
that motivated 0133/0134 in the first place (`0x100a` on the one success
vs. `~0x1016/0x1017` clustered on every right-port failure) is exactly the
kind of thing a confound like this could produce on its own, with nothing
to do with tunnel success -- it could just as easily be a fixed
per-ACIO-instance calibration constant.

An exhaustive, offset-by-offset diff across all 9 captures (both `dpin0`
and `dpin1`, every offset `0x00`-`0x7c`, first-read and last/settled
value) confirms just how narrow the real signal is: of 32 offsets per
0x80-byte block, only three ever differ across *any* capture at all --
`dpin0 +0x18`, and `dpin1 +0x0c`/`+0x1c`. Every other offset, including
the four (`+0x00`/`+0x0c`/`+0x28`/`+0x34`) 0133's own note flagged as
"sharing the pattern," is bit-for-bit identical in literally every
capture, the one success included -- confirmed against 0127's own dump
directly. Those four are dropped from the suspect list entirely. `dpin1`
(completely unused, unconnected) transitioning at the same poll boundary
as `dpin0`'s `+0x18` in both 0133 and 0134 also argues this is a
shared, block-wide hardware event, not something specific to the actively
-tunneled lane's own AUX/DPCD state -- further weakening `+0x18`'s
candidacy as "the" blocker even before the port confound is considered.

## What the research sweep otherwise ruled in and out

- **Crossbar gap, real but currently unreachable.** The reference PR's
  `apple_dpxbar_link_up()`/`link_down()` gate an ATC-facing output-clock
  register (`OUT_PCLK1_EN`/`OUT_N_CLK_EN`) that this project's T602x port
  of those same two functions never touches; `link_down()` also never
  clears `CROSSBAR_DISPEXT_EN`, contradicting both the reference and this
  driver's own comment claiming parity with it. Real, confirmed
  discrepancies -- but T602x's actual register layout has clearly
  diverged from the generic/t8103 one it was compared against (extra,
  unnamed registers -- `T602X_REG_00C`/`01C`/`034`/`018` -- with no
  established 1:1 mapping to the generic names), and this code
  (`dcp_tunnel_crossbar_up()`/`down()`) only ever runs after
  `SET_LINK_RATE`/`DID_CHANGE_LINK_CONFIG`, which never fire on any
  failing run to date. Fixing it now would be guessing at unfamiliar
  registers to patch code that isn't even reached yet. Deliberately
  deferred to a future candidate, once we're past the current blocker --
  noted here so it isn't lost.
- **PHY analog wake / AUSPLL descriptor sequence: confirmed correct.**
  Every raw hex constant in this project's `atc_tunnel_start()` was
  manually decoded against the reference's own named macros and matches
  exactly. Not the defect.
- **Crossbar/mux routing and device-tree wiring: confirmed symmetric.**
  Live device-tree data for both ports' crossbar and ACIO nodes is
  structurally identical; the of_graph connector pairing is correctly
  distinct per port; the mux-index computation is generic, not
  hardcoded. No bug found in this layer for either port.
- **DCP apcall dispatch (`DEVICE_NOT_RESPONDING`/`BUSY_TIMEOUT`/
  `NOT_STARTED` handling): confirmed not the defect.** Byte-identical
  across this project's tree, the shared merge-base, and the
  hardware-validated reference -- it predates all three. The real,
  load-bearing fact this audit surfaced: on every failing run, DCP issues
  *zero* apcalls of any kind for ~5 seconds after `request_display`
  succeeds, where the one successful run immediately launches a dense,
  real link-training burst (`GET_MAX_LINK_RATE`, `WILL_CHANGE_LINK_CONFIG`,
  `SET_ACTIVE_LANE_COUNT`, `SET_LINK_RATE`, `DID_CHANGE_LINK_CONFIG`,
  drive-settings cycles) in the very same second. The fault happens
  upstream of anything the driver's apcall dispatcher ever gets called
  for -- confirming, from a completely different angle, that this isn't a
  driver-response-logic problem.
- **No external prior art exists to lean on.** Live GitHub/web research
  (not from training-data memory) confirms: no public source documents
  this ACIO "analog" block under any name; the one parallel community
  effort on the same SoC family (`ice3186/linux` PR #1, a 14" M2 Max) is
  explicitly pre-hardware-test and behind this project's own state; the
  reference PR (`aurora-silicon/linux#8`) received only cosmetic fixes
  since the merge-base, nothing T602x-specific; and Sven Peter's actual,
  currently-landing upstream Asahi Thunderbolt series confirms
  DisplayPort tunneling remains unimplemented for every Apple Silicon
  generation. This project's own state -- DCP tunnel comes up, connects,
  requests the display, then five seconds of silence before giving up,
  with a (now correctly understood, not a bug) one-shot status register
  as the only observed hardware signal in that window -- is very likely
  the most advanced public reference point for DP-over-USB4-tunnel on
  T602x specifically, for anyone.

## The change (kernel commit 07dc4c1)

Two parts, one commit:

1. **Revert** 0133/0134's per-poll analog-block reads and the ack
   function, back to the original single-dump design (see "Corrections"
   above). `drivers/thunderbolt/apple.c` is now source-identical to its
   0132 state except for one added explanatory comment (confirmed via
   `git diff` against the 0132 commit directly) -- the `.ko` hash differs
   from 0132's only because of that comment text, not any logic change.
2. **New diagnostic**: `usb4_route_prefer_fixed_diag` (default off,
   `drivers/gpu/drm/apple/dcp.c`). When set, skips 0128's fixed-output
   route-scoring penalty for this boot, so whichever port actually
   tunnels lands on the dcpext0 pipeline instead of dcpext1 --
   reproducing 0127's exact pipeline choice, but on the port genuinely
   under test (right port, the actual target hardware). This does **not**
   test "does the right port work" in the sense already ruled out by
   Oliver -- it tests whether the specific things 0127 reached (the
   apcall burst, `DPRX_DONE=1`) are gated by the *port* or by the
   *pipeline*, which the existing data cannot distinguish. Armed for
   this candidate's own test (`scripts/manage-0135.py`'s `OPTIONS`
   includes `usb4_route_prefer_fixed_diag=1`).

## What a result either way means

- **If the right port + dcpext0 reaches the same rich apcall burst and
  `DPRX_DONE=1` that 0127 reached**: the right port's ACIO hardware itself
  is not the problem -- the defect is specific to dcpext1 (the pipeline
  actually needed for a real picture), and the crossbar `OUT_PCLK1_EN` gap
  found above becomes directly relevant again, on the correct port this
  time, since this run would exercise `dcp_tunnel_crossbar_up()` for the
  first time on the right port.
- **If it doesn't** (same ~5s silence, same give-up, on dcpext0 this
  time): the right port's ACIO instance itself behaves differently from
  the left's, independent of pipeline -- a genuine hardware/SoC-instance
  difference, not a pipeline-selection bug, and the next investigation
  should focus on what's different about the right ACIO/DP-IN-adapter
  instance specifically (not more register archaeology on the "analog"
  block, which this sweep found to be mostly a dead end regardless).
- Either way, this closes the port/pipeline confound that has quietly
  undermined every register-level comparison this project has drawn since
  0127, and the result is genuine new evidence, not a guess.

## Build verification

`drivers/thunderbolt/apple.c`: -60/+21 lines net (revert of 0133/0134).
`drivers/gpu/drm/apple/dcp.c`: +21/-1 lines (new diagnostic param).
`tb_regs.h`/`tunnel.c`/`atc.c`/`apple-display-crossbar.c` untouched.
New hashes: `appledrm.ko`
`62fea148ce8ab047ad96301ca4b6c977668edb7affc85e4cf35e91b9676fd27f`,
`thunderbolt_apple.ko`
`cfcd0fce5f999ab0ee082cb2680468996c96c9a143ace01d324aff6ee7268374`
(confirmed via `git diff` to be source-identical to 0132 except one
comment). `thunderbolt.ko`/`mux-apple-display-crossbar.ko`/
`phy-apple-atc.ko` verified byte-identical to every prior candidate since
0130/0132. Stale-symlink sweep clean (same pre-existing, already-triaged
non-symlinks as every candidate since 0115). `test-dpin-handshake.c`
13/13 pass (regression check only; unrelated code). Patch:
`patches/0135-isolate-port-pipeline-confound-revert-fsm.patch`.
`scripts/manage-0135.py` derived from `manage-0134.py`: `appledrm`/
`thunderbolt_apple` hashes updated, `thunderbolt`/`mux`/`atc` unchanged;
`OPTIONS` adds `usb4_route_prefer_fixed_diag=1` (the only options-string
change across this whole session) so this diagnostic is armed by default
for this one candidate's own test.

## Test plan

Same protocol, single boot, hub already connected, right port (no
physical change -- this test's whole point is running the diagnostic
pipeline-forcing flag on the port already in use). Watch for:

1. `display routed to Thunderbolt DP tunnel dpin0` followed by
   `dcp_dptx_connect(port=0) target=...` against `289c00000.dcp`
   (dcpext0) instead of `315c00000.dcp` (dcpext1) -- confirms the
   diagnostic routing actually took effect.
2. Whether the ~5-second apcall silence still happens, or whether a real
   link-training burst (`SET_LINK_RATE`, `WILL_CHANGE_LINK_CONFIG`,
   `DID_CHANGE_LINK_CONFIG`, drive-settings cycles) fires immediately
   after `request_display` succeeds, matching 0127.
3. `DPRX_DONE=1` / `"ACIO AUX completed"`.
4. If `DPRX_DONE=1` is reached: `DP tunnel crossbar up` (success or a new
   `-22`-style failure, this time actually informative since it would be
   the right port exercising this code for the first time).
5. No picture is expected regardless (dcpext0 is confirmed the wrong
   pipeline for a real Type-C-tunneled source) -- Oliver's own eyes
   confirm that either way, but the actual goal of this boot is the log,
   not the screen.
