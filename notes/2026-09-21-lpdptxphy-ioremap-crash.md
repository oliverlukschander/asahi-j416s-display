# lpdptxphy second ioremap crash — 2026-09-21

0040 `ioremap`'d `phy@39c000000` core while `phy-apple-dptx` already
had it mapped, then `writel` DCP index at +0x10.

Boot 13:22 lasted ~1 s (same class as the ACIO window scan). No
`core+0x10` log: the overlapping map/write hung the fabric before
`dev_info`.

`phy_set_mode(DP)` through the driver's mapping (0035/0037) trains
HBR3/4 lanes and blanks eDP; it does not 1 s-crash.

Do not second-ioremap lpdptxphy. Do not phy_set_mode(DP) on it while
eDP is on.
