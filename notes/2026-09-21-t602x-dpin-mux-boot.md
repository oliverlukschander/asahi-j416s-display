# T602x DPIN mux boot — 2026-09-21 10:35

Patched mux + appledrm loaded from initramfs. Hub still on USB-C Right. Hyprland: eDP-1 only.

## What the mux actually wrote (Right, `f0304c000`)

```
Switched dpin0 to dispext1,0 (t602x atc=0x1 mux=0x2002)
030=00002002 034=00000001 01c=00000001
```

- `atc=0x1` = `ATC_DPIN0` (stock always wrote `0x100` = DPPHY)
- `mux=0x2002` = DPIN0 select fields for dispext1,0 (state 2)
- USB-C `dcpext1` (`315c00000.dcp`), DPTX PHY 2

HDMI `130304c000` still selected dpphy for dispext0 (`atc=0x100`). Laptop panel stayed up.

## DPTX

```
validate target=0x9020 core=0 atc=2 die=0 or=0x0
AppleDCPDPTX.cpp:355: [AFK]powering nub 0x854e10
APCALL 18 GET_SUPPORTS_HPD
APCALL 10 GET_MAX_LANE_COUNT → USB4 DP IN, 4 lanes
APCALL 0 ACTIVATE
DPTXController.cpp:4294: logic error: called with device == NULL
APCALL 20 INACTIVE_SINK   (~3 ms later)
timeout -110
```

Tunnel kept: DP IN/OUT still VE=1 AE=1 HPD=1 DPRX=0.

## Read

Crossbar DPIN analog is no longer a no-op. Firmware accepted `0x9020` (ATC 2 + DPIN field 1) then had no DPTX device on ACTIVATE because `atcphy` was NULL (USB4 ATC must not go to `PHY_MODE_DP`).

HDMI PHY 3 previously had a device and trained the empty jack. ATC 2 in USB4 previously returned 22/24. This is a third failure: firmware lookup for that remote-port has no PHY object.

Each ATC has a separate DP AUX block (`lpdptx`) that USB4 mode currently leaves off (`enable_dp_aux = false`). Next: enable that AUX path without switching the USB4 lanes to DP, or find the firmware remote-port that names DPIN instead of ATC 2.
