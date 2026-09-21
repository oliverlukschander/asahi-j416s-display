# ACIO DP IN AUX — 2026-09-21

PHY 3 + DPIN trained the empty HDMI jack (Parade PS190). ATC 2 in USB4
has no firmware DPTX object. Next path is ACIO-side AUX into host DP IN
`0:5`.

## What this boot loads

- `thunderbolt.ko` + `thunderbolt_apple.ko` (the ACIO driver is a
  separate module; previous out-of-tree builds never replaced it).
- After DP tunnel VE/AE/HPD, `apple.c` dumps every host DP IN adapter
  (CS 0–16, hops 8/9, ADP_CS_4 lock), ACIO RC 0x00–0xff, and hub DP OUT.
  A worker dumps DP IN CS whenever VE/AE/HPD/DPRX/LOCAL/REMOTE change.
- appledrm selects USB-C `dcpext1` dpin0 and does **not** call
  `dcp_dptx_connect` / HDMI PHY 3 / ATC `phy_set_mode(DP)`.

## Success

```
DP IN analog/AUX serializer: tunnel 0:5 <-> 1:19
DP IN DPRX_DONE=1
SET_ACTIVE_LANE_COUNT lanes>0
hyprctl monitors  → VMM7100 besides eDP-1
```

Hub keyboard must stay up. Do not replug.

## After reboot

```
hyprctl monitors
dmesg | grep -E 'DP IN |DP OUT |keeping DP|INACTIVE|HPD=|SET_ACTIVE_LANE|SET_LINK_RATE|target=|PS190|device == NULL|Switched dpin|enable DP AUX|analog/AUX|DPRX_DONE|skip DPTX|ACIO RC'
```
