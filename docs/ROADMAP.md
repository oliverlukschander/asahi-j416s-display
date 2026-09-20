# Roadmap

## Done (USB4, other repo)

USB3 through the hub: [asahi-j416s-usb4](https://github.com/oliverlukschander/asahi-j416s-usb4)
and [aurora-silicon/linux#6](https://github.com/aurora-silicon/linux/pull/6).

## In progress

1. **Keep this cabling.** Hub TB5 port → VMM7100 → HDMI. Capture and notes
   live under `captures/` and `notes/`.
2. **Explain the teardown.** Confirmed: `tb_dp_tunnel_active()` DPRX timeout
   on `0:5 <-> 1:19`, not a missing hub HDMI jack.
3. **Patch 0001** (not on the running kernel yet): USB4 → dpin0 mux + DPTX
   connect. Needs a kernel rebuild/`update-m1n1` of the j416 DTB.

## Next

3. **Dump DP adapter state** at tunnel time (HPD on `1:19`, DP IN enable on
   `0:5`, AUX). Needs thunderbolt dyndbg (`sudo`).
4. **Route DPTX to USB4 DP IN** — see [`dptx-usb4-hook.md`](dptx-usb4-hook.md).
   DT currently only binds crossbar cell 0 (`dpphy`). USB4 needs cell 1/2
   (`dpin0`/`dpin1`) plus `dptxport_connect()` / `set_hpd()` from
   `dcp_typec_route_set()` when `TYPEC_MODE_USB4`.
5. **HPD into DCP** during the ~12 s DPRX window so the tunnel is not torn
   down.
6. **Hyprland.** Once a DRM USB-C connector shows `connected` with modes,
   existing `monitors.lua` `preferred` / `auto` should pick it up.

## Later / out of scope here

- PCIe-C / m1n1 preinit (enclosures, eGPU)
- DP alt-mode on a *free* Mac USB-C port (useful fallback, different series)
- MST (Apple DPTX has no MST)
