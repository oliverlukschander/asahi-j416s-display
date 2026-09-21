# USB-C Right crossbar clock status stays 0

0085 boot, hub in, eDP on. `DCPDPDevice` still dies at 5 s.

Crossbar `f0304c000` after dpin0 is switched to dispext1:

```
ctl 0x000=00000004  stat 0x800=00000000
ctl 0x020=00000001  stat 0x820=00000000
ctl 0x024=00000110  stat 0x81c=00000110
```

`0x800` is the DPTX write-clock status. The enable bit is set and
the status stays 0, so dcpext1 is not producing a pixel/AUX clock
into the ACIO analog PHY. Restoring `0x024` bit 0 (idle `0x111`),
toggling `0x000` bit 2, and writing the `0x828`/`0x82c` status
(`0x3ffff`) do not make `0x800` leave 0. eDP stayed on.

That is why `DCPDPDevice` start times out: the route is selected
and the source clock never starts.
