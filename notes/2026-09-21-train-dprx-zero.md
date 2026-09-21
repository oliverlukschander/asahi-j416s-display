# Full analog train: 4 lanes, DPRX stayed 0 — 2026-09-21 13:57

```
user DPTX train (full analog)
validate 0x9040  atc=4
SET_LINK_RATE 0x1e
SET_ACTIVE_LANE_COUNT 4
set_drive_settings 4:0:14 … 22
unexpected lane count:4 phy: 0
lanes 4 → 2 → 1
DPRX still 0 on 0:5 and 1:19
no cb_hotplug on 315c00000.dcp
~36 s SET_LINK_RATE 0x0
```

lpdptxphy analog is not the USB4 DP IN path. Firmware trained that PHY;
the tunnel never saw AUX (DPRX=0). eDP went black from core+0x10=2.
The VMM7100 staying dark matches DPRX=0.

Do not use lpdptxphy to light the dock while chasing eDP. Auto-restore
DCP index 0 ~10 s after a manual train so the panel comes back without
unplugging.
