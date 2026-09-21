# Analog PHY closed — 2026-09-21 0057 boot

Hyprland: eDP-1 only. Tunnel kept, DPRX=0.

Hands-off analog at tunnel-up. Timeout dump at 34 s still:

```
dpin0 +0x18=00001017
```

Same first-read status as 0054/0055/0056. Analog did not progress.
Consuming `+0x18` was not why DPRX failed.

ACIO firmware (`AppleCIOFirmware-475~290`) logs USB4 path setup
(ports 13–16, hopids 8–11) and never mentions AUX/DPTX/HPD/display.

Analog MMIO and adapter CS (Discovery, DPME) are closed. Remaining
ACIO work is firmware IPC: RTKit client messages and Apple VSE.
