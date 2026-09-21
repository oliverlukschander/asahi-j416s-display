# lpdptxphy instantiate failed — 2026-09-21

Hyprland: eDP-1 only. Hub up.

```
allocated Type-C DPTX PHY 4
USB4: failed to instantiate lpdptxphy
validate target=0x9040 core=0 atc=4 die=0
powering nub
APCALL 18, 10, 0 ACTIVATE
~5.5 s later APCALL 22/24 on target 0:4
timeout, DEACTIVATE
tunnel kept, DPRX=0
```

No `device == NULL` (unlike ATC 0/2). Firmware waited on index 4.

`of_platform_device_create()` returns NULL for `status = "disabled"`.
`phy@39c000000` is in the live DT. Next: `of_device_alloc` + `of_device_add`
(skips the available check).
