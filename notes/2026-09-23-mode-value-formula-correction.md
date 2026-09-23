# Major correction: the mode-value formula was reading the wrong field

Supersedes the rate_class/lane_count/secondary_bit model documented in
2026-09-22-0109-dpin0-connected-bit.md, -0110-mode-value-guess.md, and
carried through 0110/0111/0112 (dpin_mode_value 8, 9, 10, all tested
clean with no picture). Triggered by external research (finding the real
`IODPTXPortAttributes` ObjC type-encoding layout from Apple binaries via
the `blacktop/ipsw-diffs` project) that showed our assumed nibble-aligned
bit boundaries ("bits 4-7 rate class", "bits 1-3 secondary") didn't match
the real struct's byte packing (`C b1 b1 b6 b16 {IODPTXPortAddress = b4
b4 b2 b5 b1 b16}`), prompting a focused re-disassembly of
`AppleCIODPTX::connectTo`/`bringConnectionUp` against the corrected
layout.

## What the re-analysis found

`connectTo(nub, attrs)` stores the raw 64-bit `attrs` parameter
unmodified. `bringConnectionUp` later splits it into two 32-bit halves:

- The **lower** 32 bits is the `IODPTXPortAttributes` word itself (`C b1
  b1 b6 b16`) -- never read by the code that computes the two DPIN0
  writes at all. Our old "rate_class"/"secondary" reading was never
  looking at this word to begin with.
- The **upper** 32 bits (what our earlier trace labeled `w26`) is
  actually the nested `IODPTXPortAddress` sub-struct -- a **routing
  address** (core/atc/die/port-like fields), not a display-mode or
  link-rate descriptor at all.

Confirmed by matching bit-for-bit against our own already-shipped
`dptxep.h`: `DCPDPTX_REMOTE_PORT_CORE=GENMASK(3,0)`,
`_ATC=GENMASK(7,4)`, `_DIE=GENMASK(11,8)`, `_DPIN=GENMASK(13,12)`,
`_CONNECTED=BIT(15)` -- an exact match to `IODPTXPortAddress`'s layout.
So the field our old formula called "rate_class" (bits 4-7) is literally
the **ATC field of the routing target we already send as a parameter to
`dptxport_connect()`** -- not something DPIN0's handshake needs to
independently re-derive a rate class from at all.

The actual computation, re-read directly from disassembly:

```
w23 = bits4-7 of w26          // ATC field of IODPTXPortAddress
w11 = (w26 & 0xE != 0) && (this->byte_0x128 >= 2) && (unit == 0)   // 0 or 1
mode_value = w23 * this->byte_0x128 + w11
```

Our own connection uses ATC=0 for this exact route (dcp.c: "USB4 dpin:
ATC=0", confirmed in the kernel log's own "analog DPIN validate
core=%u atc=%u" lines throughout 0093-0112). With ATC=0, `w23=0`,
collapsing the formula to **`mode_value = w11`, which can only be 0 or
1** -- never 8, 9, or 10. The entire prior sweep (0110/0111/0112) tested
outside the real candidate space, because the field it was reading
(interpreted as "rate class") was never rate-related in the first place.

`w11` depends on `w26 & 0xE`, i.e. bits 1-3 of the CORE field:
CORE=1 (0b0001) -> `&0xE=0` -> w11=0 -> **mode_value=0**.
CORE=2 (0b0010) -> `&0xE=2` -> w11=1 (if the other two conditions hold)
-> **mode_value=1**.

Our connect path (`dcp.c` USB4 custom loop) tries `usb4_core` (default
1, i.e. CORE=1) first and only falls back to CORE=2 if validation fails;
every prior successful run's kernel log shows the CORE=1 attempt
succeeding on the first try (no fallback-to-2 log lines), so the real
working connection is CORE=1 -> **predicted mode_value=0** with highest
confidence, mode_value=1 as the immediate fallback if 0 is inconclusive.

## What this does not change

- The write mechanics themselves (MODE_A one-hot-bit-at-shift-amount,
  MODE_B pure-OR-at-bit-7, both native-confirmed patterns) are
  unaffected -- only what numeric value should be written is corrected.
- `this->byte_0x128`'s exact meaning is not resolved (irrelevant while
  ATC=0, since it's multiplied by 0).
- The lower-32-bit attributes word's role elsewhere is not resolved (not
  read by this code path at all).

## Next hardware step

Test `dpin_mode_value=0` first (highest confidence), then `=1` if
inconclusive -- both via the 0112 runtime parameter and unplug/replug,
no reboot needed. This is a much narrower, better-grounded target than
the previous 0-15 sweep, which is now understood to have never been
searching the right space.
