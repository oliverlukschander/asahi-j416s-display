# lpdptxphy train blanked eDP with DRM hotplug suppressed — 2026-09-21

```
got lpdptxphy phy
validate 0x9040
SET_LINK_RATE 0x1e
SET_ACTIVE_LANE_COUNT 4
USB4: DPTX trained 4 lanes, DRM hotplug suppressed
cb_hotplug() ignored on USB4 connected:1
~31 s later SET_LINK_RATE 0x0
```

No Linux `set_digital_out_mode` on dcpext. eDP still went black. Blanking
is `phy_set_mode(DP)` on `phy@39c000000` (or DPTX ACTIVATE index 4), not
KMS. Do not phy_set_mode lpdptxphy on this laptop until that is understood.
