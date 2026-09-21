# ACIO RC DP IN analog PHY — 2026-09-21

Tunnel `0:5 <-> 1:19` is still VE=AE=HPD=1, DPRX=0. Hyprland eDP-1 only.

`apple,tunable-rc` (already mapped, 0xc000) programs two analog
blocks that the 0x00–0xff RC dump never showed:

| Offset | What |
| --- | --- |
| `rc+0x4000` | DP IN analog 0 (host adapter 0:5) |
| `rc+0x8000` | DP IN analog 1 (host adapter 0:6) |

Same 0x801f-mask PHY tunable pattern as NHI USB4 analog. Two blocks,
two host DP IN adapters. This is inside `acio->rc_base` — not the
unmapped 16MB window that hung in 0029.

## 0054 (`thunderbolt_apple.dpin_aux`)

After VE/AE:

1. Dump RC ctrl + both analog blocks.
2. Re-apply analog tunables on the active adapter’s block.
3. Set `ADP_DP_CS_8.DPME` on DP IN.
4. `echo 2 > /sys/module/thunderbolt_apple/parameters/dpin_aux`
   pulses analog ctrl bit 0 (PCIe-C Intr2AXI equivalent). Default is
   1 (no pulse) so the first boot is dump + DPME only.

Do not `readl` unmapped ACIO ranges.

## After reboot

```
hyprctl monitors
dmesg | grep -E 'DP IN |DP OUT |keeping DP|INACTIVE|HPD=|SET_ACTIVE_LANE|SET_LINK_RATE|target=|PS190|device == NULL|Switched dpin|fDisplayPowerState|80000104|DPRX=|analog|DPME|dpin_aux'
```

Success: analog ctrl changes, then `DPRX_DONE=1`, then Hyprland sees
the VMM7100 besides eDP-1. Hub keyboard stays up. No replug.
