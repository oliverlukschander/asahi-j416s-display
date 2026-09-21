# DPTX Discovery before AE — 2026-09-21

Hyprland: eDP-1 only. Tunnel kept.

```
discover before AE: ROUTER_CS_6=01000000 AE=0 VE=0
CS13 try 00000001 stuck=1  CS9 41000553 -> 41000553
CS13 try 00000002 stuck=2  CS9 unchanged
CS13 try 00000100 stuck    CS9 unchanged
CS13 try 00010000 stuck    CS9 unchanged
CS13 try 01000000 stuck    CS9 unchanged
CS13 try 80000000 stuck    CS9 unchanged
then AE/VE/HPD=1 DPRX=0
```

All six CS13 bits are writable. CS9 is a static capability (same on idle 0:6). No `DPTX discovery` notification.

USB4 DPTX Discovery is not implemented on Apple DP IN. Closed.

T602x `070` still 0 (write ignored). Analog remains `01c/034`.

Next: scan ACIO 16MB window / leftover RC / NHI spare pages for a DP analog/AUX block. Do not cycle CS13 again.
