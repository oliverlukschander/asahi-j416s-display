# DPTX Discovery boot — 2026-09-21

Hyprland: eDP-1 only. Tunnel kept, DPRX=0.

```
f0304c000 dpin0 → dispext1,0 atc=0x1 mux=0x2002 070=0
ROUTER_CS_6=01000000   # bit 24 only
CS13 00000000 -> 00000001   # bit 0 writable
CS9 stays 41000553 on 0:5 and 0:6
no DPTX discovery notification, no CS change after that
```

T602x `070` write is ignored (new mux loaded; readback 0). Analog enable stays `01c/034`.

CS13 bit 0 was set **after** AE/VE=1. USB4 CM Guide requires DPTX Discovery **before** AE. Next boot: discover before `tb_dp_port_enable`, try CS13 bits 0,1,8,16,24,31.
