# HPD-gated DPTX phy 3 — 2026-09-21 10:12

Sequence worked as coded:

1. `USB4 dpin mux typec2; waiting for DP IN HPD`
2. Dump: DP IN/OUT VE=1 AE=1 **HPD=1** DPRX=0
3. `DP IN HPD=1 typec2, DPTX phy 3 (not ATC)`
4. `target=0:3` (`0x8030`)
5. INACTIVE_SINK, one HPD kick (no storm)
6. SET_LINK_RATE 0x0, 8s timeout
7. Tunnel kept

HDMI DPTX PHY 3 still trains the HDMI analog jack (empty), not USB4 DP IN
`0:5`, even though that adapter already has HPD=1.
