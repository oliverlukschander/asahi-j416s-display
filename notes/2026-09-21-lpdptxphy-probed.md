# lpdptxphy probed — 2026-09-21

Hyprland: eDP-1 only. Hub up. `phy_apple_dptx` bound to `phy@39c000000`.

```
instantiated lpdptxphy phy-apple-dptx
validate target=0x9040 atc=4
powering nub
APCALL 18, 10, 0 ACTIVATE
~5.5 s  APCALL 22/24 on target 0:4
timeout, DEACTIVATE
DPRX=0
```

Linux PHY probed. DPTX ACTIVATE did not call `phy_set_mode` because
`dptxport.atcphy` is NULL on USB4. Firmware still DEVICE_NOT_STARTED
on index 4.

Next: set `atcphy` to lpdptxphy so ACTIVATE runs `phy_set_mode(DP)` on
that dedicated PHY (not the USB4 ATC).
