# lpdptxphy phy_set_mode trained, then blanked eDP — 2026-09-21

Hub plugged. Internal panel went black. Unplugged hub to recover.

```
instantiated lpdptxphy / got phy (0035)
validate 0x9040 atc=4
SET_LINK_RATE 0x1e          # HBR3
SET_ACTIVE_LANE_COUNT 4
set_drive_settings 4:0:28 then 4:0:32
set_digital_out_mode on 315c00000.dcp
mode_set_gated: 3456x2234@120 Hz   # laptop-like timing on dcpext1
Ext XPan M3 pixel_clock 1042130000
```

First real DPTX train on the USB-C dcpext (not HDMI PS190). Linux
`complete(linkcfg)` then KMS modeset the panel timing onto dcpext and
the laptop display went black.

Do not phy_set_mode lpdptxphy until USB4 skips that complete() and does
not hotplug a DRM connector with eDP modes. Hub unplugged for the
safe load.
