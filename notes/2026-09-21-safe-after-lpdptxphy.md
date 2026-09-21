# Safe boot after lpdptxphy blank — 2026-09-21

eDP up, hub up. No phy_set_mode. 22/24 on 0:4. False
"trained 4 lanes" was GET_MAX_LANE_COUNT setting lane_count=4
then an 8s wait timeout.

lpdptxphy DP mode trains HBR3/4 lanes and blanks eDP at the PHY,
not via DRM. Skip DPTX connect until that sharing is understood.
