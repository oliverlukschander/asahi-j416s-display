# ACIO DP IN AUX boot — 2026-09-21

Hyprland: eDP-1 only. `card2-USB-*` and HDMI-A-1 disconnected. Hub keyboard up.

## What ran

```
f0304c000 dpin0 → dispext1,0 (t602x atc=0x1 mux=0x2002) 070=0
315c00000.dcp  allocated Type-C DPTX PHY 2 (USB4 DP IN, ACIO AUX)
USB4 DP IN armed typec2; ACIO AUX owns adapter 0:5 (no DPTX PHY)
DP IN analog/AUX serializer: tunnel 0:5 <-> 1:19

0:5 host DP IN  VE=1 AE=1 HPD=1 DPRX=0 LCK=0
    LOCAL=15402334 REMOTE=0547a135 COMMON=15402134 CS9=41000553
    hop 8 AUX enable=1 out=1 next=11 credits=1
    hop 9 VID enable=1 out=1 next=10 credits=0   # USB4 ignores path credits
0:6 host DP IN  VE=0 AE=0 HPD=0 DPRX=0
    LOCAL=15402334 REMOTE=0 COMMON=0 CS9=41000553   # sibling adapter, no tunnel

ACIO RC: 000=3010 004=11 018=40000 01c=1 024=09600258 030=7af 040=c 078=3 0a8=01000000 0ac=04000001 0d0=62
DPRX timeout, tunnel kept. CS did not change.
```

No PS190, no `device == NULL`. Mux is USB-C dcpext1. Analog ATC bit is programmed (`01c=1 034=1`); T602x `070` (t8103 `CROSSBAR_ATC_EN`) stays 0.

CS9 is identical on 0:5 and 0:6 → static capability, not discovery status.

## Read

USB4 Connection Manager Guide 5.4.1.4: **DPTX Discovery** finds which GPU DPTX is wired to a DP IN adapter. Set `ADP_DP_CS_13.DPTX Discovery Mode`, wait for `ADP_DP_CS_9.Discovery Success/Failure`. Linux currently ACKs `TB_CFG_ERROR_DPTX_DISCOVERY` and ignores it.

Next: enable DPTX Discovery on 0:5, dump ROUTER_CS_6 + CS11–16, set T602x `070=ATC_DPIN0`.
