# Native XNU AppleDPTXController bandwidth-ratio mechanism (offline, no hardware)

Re-derived the exact same decoded macOS13.5 kernelcache Mach-O already
analyzed for0093-0105 (SHA256
9615a486511c7a60b141d7f4291361c5212e908546d6568890029bb90b5431e7,
byte-identical, re-extracted from the same private
/boot/asahi/kernelcache.release.mac14j via the same IM4P/lzfse recipe
recorded in notes/2026-09-22-0093-native-dpin.md). No new hardware read,
write, or macOS-side extraction was needed: this is XNU host-kernel code
(Darwin22.6.0/xnu-8796.141.3~6), already present in that same cache.

## What triggered this

The native macOS DP-bandwidth capture (0106-0108 follow-up) showed
`(DCP0) AppleDCPDPTXController::getBandwidthRatio ... bandwidthRatio=0.9779`
and `updateBandwidthRatio BW_RATIO=0x7d2e` on the WORKING right-port hub
connection (notes/2026-09-22-macos-dp-bandwidth-result.md). The `(DCP0)`
prefix is the driver instance's registered name, not proof the code runs
on the coprocessor; the symbol table confirms `AppleDPTXController` is
ordinary XNU host-kext C++ code.

## Functions found and disassembled (offline, addresses only, no raw
## assembly committed here)

| Method | Address |
| --- | --- |
| `AppleDPTXController::getLinkBandwidth(unsigned int, unsigned long long) const` | 0xfffffe0009365384 |
| `AppleDPTXController::getUsableLinkBandwidth(unsigned int, unsigned long long) const` | 0xfffffe00093646a4 |
| `AppleDPTXController::updateBandwidthRatio(IODPDevice*, unsigned long long, IOAVVideoLinkData const*)` | 0xfffffe0009362708 |
| `AppleDPTXController::setBandwidthRatio(unsigned int)` | 0xfffffe0009364524 |

## What they do

`getUsableLinkBandwidth` reads a capability/mode value via
`AppleDPTXNub::readReg(0x1c)` (confirmed by symbol, not guessed -- this is
a real register read on the DPTX nub, not a generic property getter) and,
if a specific bit is set, derates the raw link bandwidth by a fixed-point
factor of 64000/65536 (~0.9766) before returning it as "usable" bandwidth.

`updateBandwidthRatio` computes a ratio from the requested video bandwidth
against that usable link bandwidth, then calls `setBandwidthRatio`, which
packs the ratio into a fixed-point value and calls
`AppleDPTXNub::setBitsInReg(0x6e4, mask, shift, value)` -- again a
confirmed real register write on the DPTX nub, not a property-table
write. Register `0x6e4` receiving a computed bandwidth-ratio value on
every DP link establishment, gated by a capability check at register
`0x1c`, is a genuinely new, concrete finding: this is a real hardware
register write native macOS performs as part of bringing up this exact
DPTX hardware block, distinct from anything already inspected in this
investigation (crossbar 0x000-0x070/0x800 series, USB4 tunnel hop
counters, USB4 DP_STATUS allocated-bandwidth).

## What is NOT yet established

- Which physical resource `AppleDPTXNub`'s register space maps to on this
  machine/route (the existing Linux driver owns two separate named
  regions, "core" and "dptx", under the `lpdptx 0xf03050000` size`0x8000`
  resource already listed as owner-mapped in every0102-0108 entry;
  offset0x6e4 has not yet been confirmed against either sub-region's
  actual base, and the historically dangerous `core+0x10` DCP-index mux
  is a different, much smaller offset in the same general PHY hardware --
  they are not confirmed unrelated, only not confirmed the same).
- Whether Linux's existing src/phy/dptx.c ever reads or writes register
  0x6e4 or0x1c: grepped, no match. This is consistent with the register
  being genuinely untouched by the current Linux driver, not proof that
  writing it is safe or would restore video.
- Whether this register actually gates DPTX output at all, versus being
  informational/logging-only in the firmware's own accounting.

Given this PHY block's documented history in this investigation (hard
resets, blackouts requiring two boots to recover, several explicitly
forbidden operations already recorded for exactly this hardware), no
register read or write is proposed here without first confirming the
exact physical address this offset corresponds to and cross-checking it
against every existing prohibition. No module load, parameter change,
MMIO mapping/access, cable manipulation, or reboot was performed for this
analysis. Raw disassembly is kept private under
~/.local/share/j416s-display/dpin-static-13.5/j416s-dptx-bandwidth-ratio.asm.
