# Analog MMIO doorbells closed — 2026-09-21 0056 boot

Hyprland: eDP-1 only. Tunnel kept, DPRX=0.

## Writes did not stick

First dump (active `0x4000`): `+0x18=00001017`, `+0x00=80000000`,
`+0x20=0`. After pulse/fill:

```
after start +0x00=80000000 +0x18=80000000 +0x20=00000000
```

`+0x00` bit 0, `+0x18=0x1f`, and `+0x20=0x40` all bounce. Analog PHY
is initialized by `apple,tunable-rc` at ACIO start. Linux cannot
doorbell AUX through these registers.

`+0x18=0x1017` is first-read status (read-to-clear). The tunnel-up
dump already consumes it.

## 0057

Hands off analog at tunnel-up. Dump analog only after DPRX timeout so
`+0x18` can stay latched. If DPRX is still 0 and `+0x18` is still
`0x1017`, analog is waiting for a DPTX AUX source (dcpext via the
crossbar), not an ACIO MMIO poke.
