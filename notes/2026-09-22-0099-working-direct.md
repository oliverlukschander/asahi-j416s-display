# 0099: known-working direct reference and missing tunnel-rate lead

Oliver confirms actual direct adapter produces a picture. Same boot,
right typec2, dcpext1 0x315c00000, encoder97/CRTC88, BenQ timing50/color88
2560x1440@60 (241500kHz). Internal eDP remains active.

| Observation | Hub (no picture) | Direct (picture confirmed) |
|---|---|---|
| Firmware target | 0x8021 | 0x8020 |
| Link rate | 0x0a | 0x1e |
| Active lanes | 4 | 4 |
| Crossbar source enable +000 | 4 | 4 |
| After-frame status +800 | 0 | 4 |
| Clock selector +018 | 0x10 | 0x10 |
| Destination gate +01c/+028/+034 | 1 | 0x100 |
| Destination reset +024/+81c | 0x110 | 0x11 |
| Route selector +030 | 0x2002 | 0x200200 |

Direct snapshot succeeded620.604524s, Right frame usb4=0/result0. Hub
snapshot252.383579s, usb4=1/result0. Other captured controls match.
This supports investigating clock delivery specific to USB4; it does not
prove whether DCP or the PHY supplies the missing clock. Destination bits
differ normally and must not be blindly copied from DPPHY to DPIN0.

## New offline native-code lead

AppleATCDPPort::setLinkRate block0xfffffe00093a249c obtains the crossbar
clock selector via vtable+0x8c0 and calls PHY interface+0x188 with rate and
selector, BEFORE caching rate at+0x248 (25e4..25e8). Linux dptxep.c
currently skips phy_configure entirely for USB4 and only caches the rate.

AppleTypeCPhyDisplayPortInterface::setLinkRate block9d1e264 dispatches
through owner vtable+0x940 for a tunnel interface (index+0x90 !=-1),
versus+0x948 for the other path. Resolving authenticated chained pointers
using cache base0xfffffe0007004000 in BOTH T8103/T8112 PHY vtables gives:

- +940:9d62238 displayPortTunnelLinkRateChange
- +948:9d62868 displayPortLinkRateChange
- +a08:9d1b3f8 addDisplayPortPclkClient
- +a10:9d1bbe4 removeDisplayPortPclkClient
- +a70:9d58ac8 configureDPTunnelMode
- +a78:9d5c918 unconfigureDPTunnelMode
- +b10:9d80248 adjustLinkRateOwnerDPTunnelMode

Tunnel block9d62610 registers the PCLK client and invokes configureDPTunnelMode
for a nonzero rate. This is concrete evidence of a separate native tunnel
clock setup path, not permission to call normal PHY_MODE_DP on USB4 lanes.
The configure function includes clock/reset operations beyond0088's simple
pixel-clock gates. Its full resource mapping, rate units, selector handling,
shared-clock ownership and teardown are not yet reconstructed.
Do not transplant those stores or ordinary DP PLL programming blindly.

Native configureDPTunnelMode and configureDPTunnelModePLLFrequency
(9d5c440) disassemblies saved privately, along with setter call chain.
Original13.5 Mach-O SHA256 reverified9615a486511c7a60b141d7f4291361c5212e908546d6568890029bb90b5431e7.
A persistent private analysis-env holds capstone5.0.6/lzfse0.4.2 to avoid
rebuilding offline tools on every reboot. No hardware operations added.

Next implementation requires deriving that tunnel-only clock path under
the existing ATC owner and retaining USB4 lane mode. No candidate0100 is
written, installed or hardware-tested. Direct adapter can remain connected;
no further hotplug, MMIO or reboot is requested. Future boots are disarmed.
