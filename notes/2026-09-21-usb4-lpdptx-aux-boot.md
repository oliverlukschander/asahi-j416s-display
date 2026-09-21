# USB4 lpdptx AUX boot — 2026-09-21

Shutdown did not hang. Hub still on USB-C Right. Hyprland: eDP-1 only.

## What ran

```
Switched dpin0 to dispext1,0 (t602x atc=0x1 mux=0x2002)
validate target=0x9020 core=0 atc=2 die=0
powering nub 0x854e10
APCALL 18, 10, 0 ACTIVATE
phy-apple-atc f03000000.phy: USB4: enable DP AUX without lane switch (submode=2)
DPTXController.cpp:4294: logic error: called with device == NULL
INACTIVE_SINK (~3 ms)
timeout -110
tunnel kept, HPD=1 DPRX=0
```

USB4 lanes stayed (NHI `0-1` still present). Pipehandler still logs the stock
`USB4 not implemented; falling back to USB2` (USB3-via-4 on the Mac PHY).

## Read

Linux AUX enable on ACTIVATE does not create the firmware DPTX object.
Firmware looks up that object from the remote-port target. `0x9020` (ATC 2 +
DPIN field 1) has no matching device. Lookup is at connect, before ACTIVATE.

Next: enable lpdptx at USB4 mux arm (before validate/connect), and use target
`0x8020` (ATC 2, no DPIN bits) now that analog DPIN and AUX are both up.
Previous `0x8020` 22/24 was without those.
