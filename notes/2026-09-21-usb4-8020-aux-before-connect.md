# AUX before connect, target 0x8020 — 2026-09-21

Hyprland: eDP-1 only. Hub NHI still present.

```
USB4: enable DP AUX without lane switch (submode=2)   # at mux arm
USB4: DP AUX enabled before DPTX connect
validate target=0x8020 core=0 atc=2 die=0
powering nub
ACTIVATE (AUX again)
DPTXController.cpp:4294: logic error: called with device == NULL
INACTIVE_SINK
```

DPIN analog still `atc=0x1 mux=0x2002`. Tunnel kept, DPRX=0.

ATC 2 has no firmware DPTX object in USB4. Linux lpdptx MMIO does not
create one. HDMI PHY 3 *does* have an object (earlier boot trained the
empty jack). Next: USB4 on dcpext0 so firmware uses PHY 3 as the DPTX
engine, with USB-C dpin0 analog as the destination (same dispext0
digital into both crossbars) and DPIN bits in the remote-port.
