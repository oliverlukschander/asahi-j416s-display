# USB4 lpdptx AUX without lane switch — 2026-09-21

Previous boot: T602x DPIN analog programmed (`atc=0x1`, `030=0x2002`) but
DCP firmware logged `DPTXController.cpp:4294: logic error: called with
device == NULL` on ACTIVATE because `atcphy` was NULL.

USB4 mode in phy-apple-atc leaves `enable_dp_aux = false`. Each ATC has a
separate DP AUX block (`lpdptx`) from the SS lanes. This change:

- Binds the Type-C DP PHY for USB4 DPTX.
- `atcphy_dpphy_set_mode(PHY_MODE_DP)` while `mode==USB4` calls
  `atcphy_enable_dp_aux()` only. It does **not** `mux_set` to
  `APPLE_ATCPHY_MODE_DP` (that would take USB4 down).
- SET_LINK_RATE / SET_ACTIVE_LANE_COUNT do not `phy_configure` the ATC
  DP lane analog.

Boot result: `notes/2026-09-21-usb4-lpdptx-aux-boot.md`. AUX ran on ACTIVATE;
firmware still `device == NULL` for target `0x9020`. Follow-up: AUX at mux
arm, target `0x8020` (no DPIN field).

Success after `sudo ./scripts/load-appledrm.sh`:

- `phy-apple-atc f03000000.phy: USB4: enable DP AUX without lane switch`
- no `device == NULL`
- `SET_ACTIVE_LANE_COUNT` lanes>0
- DP IN `DPRX=1`
- Hyprland sees the VMM7100 besides eDP-1
- hub USB/keyboard still up (USB4 lanes stayed)
