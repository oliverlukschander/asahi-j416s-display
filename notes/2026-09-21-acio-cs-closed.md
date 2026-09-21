# ACIO/NHI/adapter CS closed — 2026-09-21 0063

0063 is healthy: eDP on, tunnel `0:5↔1:19` VE=AE=HPD=1, `CS0=c0090400`,
hop 9 credits=0, analog `+0x18=0x17`, DPRX=0.

## Closed (do not repeat)

| Try | Result |
| --- | --- |
| Analog MMIO +0x00/+0x18/+0x20 | writes bounce |
| Hands-off analog | +0x18 stays 0x17 |
| CS13 DPTX Discovery | CS9 static |
| CS8 DPME | no DPRX |
| VSE +0x02 | scratch, NHI OK, no DPRX |
| VSE +0x0b | NHI timeout, ffffffff CS |
| Hop 9 credits write | -110, NHI dead, eDP black |
| RTKit ep 0x10–0x1f | none start |
| Unmapped ACIO MMIO | reboot loop |

Analog PHY is waiting. DCP skip-connect never AUXes into it.
lpdptxphy `core+0x10=2` trains but blanks eDP and is not DP IN.

0064: dump-only ACIO (no VSE write, no RTKit start_ep).
