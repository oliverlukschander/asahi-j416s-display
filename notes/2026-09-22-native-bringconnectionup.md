# Native AppleCIODPTX::bringConnectionUp: what it writes on DPIN0, and what we can't statically resolve

Continuation of notes/2026-09-22-native-bandwidth-ratio.md. That thread
(AppleDPTXController bandwidth-ratio) is a dead end for us:
`AppleCIODPTX::bringConnectionUp`/`prepareLink` -- the real native tunnel
bring-up code for our exact ACIO/crossbar path -- never call it. It operates
on the separate, shared `lpdptxphy@0x39c000000` block (Linux DTS:
`t602x-dieX.dtsi`, `reg-names = "core","dptx"`, `status = "disabled"` on
this non-desktop machine), not anything in our working tunnel path.

## Where bringConnectionUp actually writes

`AppleCIODPTX::bringConnectionUp(AppleDPTXNub const*)` (0xfffffe0009368d4c)
calls `AppleDPTX::setBitsInReg(this, nub=NULL, memmap, offset, shiftAmount,
mask, value)` (0xfffffe00093327e4, confirmed by symbol and by reading the
callee's own body: `new = (old & ~mask) | (value << shiftAmount)`) against
`memmap = *(this + 0xd8)`. That memory map is the DPIN0-side one (the same
`0xf01e50000` size`0x4000` resource this project already safely maps and
uses via `apple_usb4_right_dpin0_set_active`), not lpdptxphy. Four calls:

| Offset | shiftAmount | mask | value | Status |
| --- | --- | --- | --- | --- |
| `0x0` (our existing HPD-read register) | 1 | 0 | `(w27==1) ? 1 : 0` | depends on a per-side byte at `nub_or_this+0x118` |
| `0xc` **or** `0x10` (our existing CONTROL/ACK registers, selected by a nub flag at `+0xe0`) | 0 | 2 | 2 | **unconditional** -- always sets bit1, no runtime dependency |
| `0x14` | `w20` (computed) | 0xff | 1 | depends on `w20` |
| `0x1c` | 7 | 0 | `w20` (computed) | depends on `w20` |

`w20 = (w23 * lane_count + w11) & 0xFF`, where `lane_count = *(this+0x128)`
(known: 4, from our own already-successful SET_ACTIVE_LANE_COUNT
negotiation), `w23 = (w26>>4)&0xF`, and `w11` is a boolean gated by
`lane_count>=2` and a nub flag at `+0xe0`, with `w26 = *(this_or_this+8 +
0x11c)`.

## Why w20 and the offset-0x0 value are not resolvable from this binary alone

Traced back into `AppleCIODPTX::validateConnection` (0xfffffe0009368084),
which is what actually populates these fields from the caller-supplied
`IODPTXPortAttributes` (a packed 64-bit value) before `bringConnectionUp`
runs. That function's branches on lane count and a rate-class subfield
determine which of several IOReturn/log paths execute and what gets stored
-- but the actual field values depend on the packed attributes value
supplied by the CALLER of `validateConnection`, which is itself computed
elsewhere from live DPCD/EDID negotiation. There is no static default to
read off; further static tracing would mean pattern-matching branch
conditions without the data that actually flows through them at runtime,
which is guessing, not evidence.

## What is actionable now

Only the `+0xc`/`+0x10` bit1 write is confirmed unconditional and
independent of any unresolved field. It is a small, well-understood,
single-variable change in territory this project already safely uses
(DPIN0, not lpdptxphy), unlike the bandwidth-ratio thread. The `+0x0`,
`+0x14` and `+0x1c` writes are real (native macOS does write them) but
their exact values for our specific configuration cannot be established
without either live tracing on real hardware (not available to this
project) or accepting a documented, unverified assumption about lane-count
mode encoding.

No module load, parameter change, MMIO mapping/access, cable manipulation,
or reboot was performed for this analysis. Raw disassembly stays private
under
~/.local/share/j416s-display/dpin-static-13.5/j416s-dptx-bandwidth-ratio.asm
(bandwidth-ratio functions) and is not yet separately saved for
bringConnectionUp/validateConnection pending a decision on how to proceed.
