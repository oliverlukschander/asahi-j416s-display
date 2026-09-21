# HPD without connect — 2026-09-21

Hyprland: eDP-1 only. Hub up. No reboot loop.

```
USB4 DP IN armed; DPTX HPD in 200 ms (no PHY connect)
AppleDCPDPTX: powering nub 0x854e10
APCALL 18 GET_SUPPORTS_HPD
APCALL 10 GET_MAX_LANE_COUNT → USB4 DP IN, 4 lanes
APCALL 0 ACTIVATE
set_hpd (no connect): -110
APCALL 22/24 link fault on target 0:2
APCALL 1 DEACTIVATE
tunnel kept, DPRX=0
```

`request_display` still makes firmware ACTIVATE the allocated Type-C PHY (**ATC 2**). USB4 has no DPTX object there. HPD-only is closed.

Next: `dptxport_connect` with remote-port **ATC=0, DPIN=1** (`0x9000`). Not PHY 3, not ATC 2. Digital still on USB-C dpin0 mux. No `phy_set_mode(DP)`, no ACIO MMIO.
