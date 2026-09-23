# Action log

Write the next hardware action here and commit it before running it.
After a crash, this file is the record of what was in flight.

An action is hardware if it loads a module, writes a module parameter,
ioremaps, writes MMIO, reboots, or runs `load-appledrm.sh`.

Full history (candidates 0090-0125, every install/disarm/result entry, every
exact command and hash) lives in
`notes/ACTION-LOG-ARCHIVE-2026-09-21-to-0125.md`, with a condensed
phase-by-phase summary in that file's own prior git history (this file's
content as of commit before this trim). Per-candidate reasoning lives in
`notes/2026-*.md`. This file only carries what's needed to pick up work
right now: safety rules, current state, and the last few actions.

## Hardware reference

M2 Pro (j416s/T602X). Left-back USB-C: NHI `0x701f00000`, ACIO `0x701ac0000`,
crossbar `0x70304c000`, dcpext1 `0x315c00000` (typec0). Right USB-C: NHI
`0xf01f00000`, ACIO `0xf01ac0000`, crossbar `0xf0304c000` (typec2, also
routes through dcpext1 `0x315c00000` at times, or dcpext0 `0x289c00000` for
direct HDMI/adapter routes — confirm the live route from dmesg every time,
never assume). Panel/eDP DCP: `0x389c00000`. DPIN0 (per-port ACIO block):
`{ACIO}+0x50000..+0x53fff`, HPD at `+0`, CONTROL at `+0xc`, ACK at `+0x10`.
Chain under test: OWC Thunderbolt 5 hub → Synaptics VMM7100 USB-C→HDMI →
BenQ 2560×1440. Direct HDMI and direct USB-C-adapter connections to the same
monitor both work; only the hub-tunneled (USB4) path is broken.

## Standing safety rules (never re-test these without new evidence)

- **Never `insmod src/dispclk/apple-dispclk.ko` with `apply=1`, and never
  write `appledrm.usb4_dispclk`.** Caused an instant, silent hard reset
  (2026-09-21 21:36) by copying the live panel clock block onto dcpext1.
  Read-only variants of that module (`read_ext`/`read_ext2`/`read_panel2`/
  `read_ext0`) are safe; the copy/write path is not.
- **Never write `+0x074` in any disp-clock block** (`write_074`) — the one
  attempt left no completion log across a reset; presumed unsafe, permanently
  disabled in the module.
- **`dpin_aux=1` (drivers/thunderbolt/apple.c) does not stick.** Confirmed
  twice, ~2 days apart, under very different driver states: 2026-09-21
  candidates 0054-0056 (`notes/2026-09-21-acio-rc-dpin-analog.md`) and again
  in 2026-09-23 candidate 0125 (`notes/2026-09-23-0125-dpin-aux-retest.md`)
  after crossbar/native-DPIN0/role-bit sequencing were all independently
  fixed. The MMIO pulse to the ACIO DP IN analog block's AUX/DPCD serializer
  genuinely does not take effect on this hardware chain — not a stale/fixed
  finding, re-verify only with a fundamentally different mechanism in hand.
- **`apple_atc_usb4_enable_dp_aux()` (candidate 0120, since fully reverted)
  disconnects the entire Thunderbolt hub** — do not re-add without first
  understanding exactly what register state it shares with the USB4 tunnel's
  own PLL/SERDES config.
- **The full DPIN0 `mode_value` guess space (0-15) is exhausted** (candidates
  0111-0113) — clean negatives across the whole range, do not re-sweep it.

## Current state (as of 2026-09-23, end of candidate 0125)

**Confirmed working, end-to-end, reproducibly:** DCP's AFK/EPIC protocol
handling for the USB4-tunneled connect sequence (`validate` → `connect` →
`set_hpd` → `request_display` → `ACTIVATE`, our native DPIN0 wake) — zero
errors, exactly the calls expected, on two independent clean boots. Crossbar
routing, the native DPIN0 handshake mechanism itself, and the Thunderbolt
DP IN role bit are all correctly implemented.

**Confirmed not working:** the actual DisplayPort AUX/DPRX electrical
negotiation between the USB4 tunnel's DP adapter hardware and the downstream
Synaptics VMM7100/BenQ chain. `DPRX` never asserts; DCP goes silent after
`ACTIVATE` rather than proceeding to `WILL_CHANGE_LINK_CONFIG`/
`SET_LINK_RATE`. The one existing software lever for this (`dpin_aux`) is
confirmed, twice, genuinely ineffective on this hardware. Cross-checked
against aurora-silicon/linux#8 (the M1/t8103 reference): that implementation
has no equivalent AUX-poke mechanism at all — DPRX completes as a natural
side effect of DCP's own link training once told a display is attached, and
never needed forcing. That reframes `dpin_aux` as never having been the
right lever, not just an ineffective one.

**Two live open directions, neither attempted yet:**
1. Further DCP firmware-internal reverse engineering of whatever gates the
   AUX read during that silent window — not reachable from any Linux-side
   instrumentation, since DCP never reports back on it at all.
2. A genuine compatibility limit specific to the OWC hub / Synaptics VMM7100
   adapter chain for a *tunneled* (vs. direct) DP route — direct HDMI and
   direct USB-C to the same monitor both work. Weighed against this: the
   identical cable/hub/adapter chain works instantly under macOS on an M4
   Mac, so the hardware itself is capable of it.

No hardware action is currently pending.

## 2026-09-23 -0126: stop switching the USB4 tunnel PHY to DP mode

Found while scoping a full aurora-silicon/linux#8 port (two parallel Opus
5.5 agents did a full function-by-function comparison; see
notes/2026-09-23-0126-stop-phy-mode-dp-switch.md for the trigger chain).
`dcp_dptx_connect()`'s analog-DPIN branch has unconditionally switched the
tunnel's ATC PHY to `PHY_MODE_DP` at connect time since candidate 0118 --
present in every candidate since. Both the reference PR and our own
tunnel-clock code require the PHY to stay in USB4/TBT mode for a genuine
tunnel. Also traced that DPRX is checked by a generic, non-Apple-specific
mechanism already in our own tunnel.c (`tb_dp_dprx_start`/`tb_dp_wait_dprx`,
polling the real hardware bit `DP_COMMON_CAP_DPRX_DONE`) -- downstream of
DCP's protocol, so forcing the tunnel PHY out of USB4 mode before that can
complete is a plausible direct cause. One-line, low-risk removal, tested
before committing to the much larger PR#8 architectural port (still
scoped and ready to build if this alone isn't sufficient -- see
`/tmp/dcp-fw2/agent-portA-dcp-side.md`/`agent-portB-tb-side.md`, scratch
analysis, not committed to this repo).

Only dcp.o recompiled. New appledrm.ko SHA256:
a3ea4d4eed1d763fc696f89098d373bbd27b5331382eb6bdf1fe59c2aacac209. Other
four modules unchanged (verified). Stale-symlink sweep clean,
test-dpin-handshake.c 13/13 pass. Patch:
patches/0126-drm-apple-dcp-stop-switching-usb4-tunnel-phy-to-dp-mode.patch.
scripts/manage-0126.py derived from manage-0124.py (candidate number + hash
only).

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0126.py install
```

## Last actions

- **0124** (instrumentation, no behavior change): closed several silent
  failure paths in `afk.c`/`dptxep.c` (DCP's real per-call retcode was
  captured and discarded; a failed apcall got no reply sent back to DCP at
  all; `request_display`/`release_display` had no logging; apcall payloads
  were never logged). Built, installed, tested on two independent clean
  boots — byte-identical result both times (see "current state" above).
  `notes/2026-09-23-0124-instrumentation.md`.
- **0125** (live parameter test, no kernel change): re-tested `dpin_aux=1`
  against the already-active tunnel (its setter fires immediately, no
  reboot needed). Reproduced the 0054-0056 "doesn't stick" result exactly.
  Reverted to 0 immediately after. `notes/2026-09-23-0125-dpin-aux-retest.md`.
- Cross-checked aurora-silicon/linux#8 in detail for any AUX/DPRX-specific
  mechanism we might be missing — found none; folded into "current state"
  above.
- Condensed this file from ~5750 lines to the current form; full verbatim
  history preserved in `notes/ACTION-LOG-ARCHIVE-2026-09-21-to-0125.md`.
