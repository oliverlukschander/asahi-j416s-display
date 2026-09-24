# 0144: PR-prep cleanup -- one real bug fix, no other behavior change

## Why

0143 made the driver's working configuration permanent (no module
flags needed). Before turning that branch into a public PR against
`aurora-silicon/linux`, it needed a pass to remove debugging-session
scaffolding that has no place upstream: dead code left over from
abandoned attempts, comments referencing this project's own session
notes by candidate number, and unconditional diagnostic logging added
to chase specific bugs. That pass (parallel review across all seven
touched subsystems, then parallel cleanup edits, this session) found
one genuine behavioral bug along the way, which this candidate fixes.

## The real bug: PHY tunnel clock was one-shot per boot

`drivers/phy/apple/atc.c`: `atcphy->tunnel_attempted` was set true the
first time `atc_tunnel_start()` successfully programmed the tunnel
pixel clock, and never reset anywhere -- not in `atc_tunnel_restore()`,
not anywhere else. Since `atc_tunnel_start()` refuses with `-EALREADY`
whenever `tunnel_attempted` is true and the tunnel isn't currently
active, this meant `apple_atc_dp_tunnel_rate()` -- the entry point DCP
calls to request the tunnel's pixel clock -- could only ever succeed
**once per boot**. Unplug and replug the Thunderbolt hub, and every
subsequent request would fail silently until the module reloaded.

Fix: `atc_tunnel_restore()` now also clears `tunnel_attempted`,
alongside the `tunnel_saved`/`tunnel_rate` resets it already did. This
is a plausible contributor to (not necessarily the whole story behind)
tonight's separate "doesn't recover after standby/replug" symptom --
see the Aquamarine writeup in ACTION-LOG.md for the other, confirmed
half of that story (Hyprland's DRM backend never issuing a real commit
on a live hotplug). Both can be true at once; this fix is independent
and worth having regardless.

## Everything else: no behavior change

- Removed confirmed-dead code across `dcp.c`, `dcp-internal.h`,
  `dptxep.c`, `dptxep.h`, `iomfb_template.c/.h`, `systemep.c`,
  `apple.c`, `tunnel.c`, `tb.c`, `tb_regs.h` -- exported symbols and
  struct fields with zero callers/readers anywhere in the tree,
  verified by grep across the whole repo (not just the touched files)
  before removal, and by full-file reads to confirm nothing was
  missed. Also one genuinely unreachable branch in `tb.c` (superseded
  by an unconditional path added earlier in `tunnel.c`).
- Rewrote every comment across all touched files that referenced this
  project's own debugging-session artifacts (candidate numbers,
  `notes/2026-*.md` paths) into plain descriptions of the actual
  hardware/firmware behavior being documented -- every technical fact
  and finding was preserved, only the session-log framing was removed.
  Two honesty caveats were deliberately *kept* explicit rather than
  smoothed over: the DPIN0 link-rate register value is an empirically
  determined estimate, not a spec-confirmed constant; and DPIN1 (the
  second tunnel port) was never independently hardware-tested, only
  DPIN0 was.
- Downgraded unconditional `dev_info`/`dev_warn`-level diagnostic dumps
  (register/config-space dumps, per-AFK-call hex dumps, per-call
  counters) added while chasing specific bugs to `dev_dbg`, so they no
  longer appear in dmesg during normal operation by default.
- Fixed a stale comment in `apple.c` that contradicted the code
  directly below it (claimed a fixed ADT resource, the code computes
  an RC-window offset -- the code is the working, confirmed part; the
  comment was stale).
- In `apple-display-crossbar.c`, replaced two hand-written forward
  declarations with `#include <linux/soc/apple/dp-tunnel.h>` (the
  header those functions are actually declared in for the DCP driver's
  `symbol_get()` callers), for compiler-enforced signature matching.
- In `atc.c`, replaced several raw bit literals in the new tunnel
  sequence with this file's own existing named macros where they
  matched, and added short comments on the few that don't correspond
  to any named macro, rather than leaving unexplained numbers.

Full methodology: independent parallel review of all seven touched
subsystems (each given the actual diff plus full current file content,
asked to describe the final behavior and flag anything dead,
unconfirmed, or leftover), then parallel cleanup edits grounded in
those specific, verified findings -- not free-ranging edits. Every
agent grepped the whole repository (not just its assigned files)
before deleting anything, and reviewed its own final diff before
finishing.

## Build verification

All four affected modules (`appledrm`, `mux-apple-display-crossbar`,
`thunderbolt`, `thunderbolt_apple`, `phy-apple-atc`) rebuilt clean from
scratch: zero errors, zero warnings.

## Test plan

Same driver behavior as 0143 except the PHY fix, so the primary check
is a straightforward regression test: boot with the monitor connected,
confirm the picture still comes up. The PHY fix specifically needs a
second check the driver has never had a clean chance to demonstrate
before: **unplug and replug the hub multiple times within the same
boot**, and confirm via `dmesg` that `apple_atc_dp_tunnel_rate()` (the
"USB4 tunnel clock preflight" log line) does not report `-EALREADY` on
the second or later attempt. (A full Hyprland-side recovery on replug
is not expected regardless -- that's the separate, unrelated Aquamarine
bug documented earlier in ACTION-LOG.md.)
