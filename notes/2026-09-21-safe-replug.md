# Safe replug after MMIO scan crash — 2026-09-21

Hub on USB-C Right again. No reboot loop. Hyprland eDP-1 only.

```
f0304c000 dpin0 → dispext1,0 atc=0x1 mux=0x2002
315c00000.dcp USB4 DP IN, ACIO AUX, skip DPTX connect
0:5 VE=1 AE=1 HPD=1 DPRX=0
1:19 VE=1 AE=1 HPD=1 DPRX=0
CS13=0  (no discovery cycling)
```

Keyboard/USB up. MMIO scan not present.

Next: one DCP `request_display` + `set_hpd` on the USB-C dpin DCP **without** `dptxport_connect` (no PHY lookup, no ACIO MMIO). One shot; no HPD kick loop.
