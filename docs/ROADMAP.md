# Roadmap

## Done (USB4, other repo)

USB3 through the hub: [asahi-j416s-usb4](https://github.com/oliverlukschander/asahi-j416s-usb4)
and [aurora-silicon/linux#6](https://github.com/aurora-silicon/linux/pull/6).

## In progress

1. **Keep this cabling.** Hub TB5 port → VMM7100 → HDMI. Capture and notes
   live under `captures/` and `notes/`.
2. **Explain the teardown.** Confirmed: `tb_dp_tunnel_active()` DPRX timeout
   on `0:5 <-> 1:19`, not a missing hub HDMI jack.

## Next

3. **Dump DP adapter state** at tunnel time (HPD on `1:19`, DP IN enable on
   `0:5`, AUX). Needs thunderbolt dyndbg (`sudo`). Script:
   `scripts/capture-display.sh` (add a `--debug` path once we have a password
   prompt).
4. **Route DPTX to USB4 DP IN** when a DP tunnel activates on this ACIO.
   Hook next to existing `pci_tunnel_*` NHI ops in
   `drivers/thunderbolt/apple.c`, plus `drm/apple` `dptxep.c` / display
   crossbar mux.
5. **HPD into DCP.** Hub DP OUT HPD must reach DPTX so AUX/DPRX can finish
   and the DRM USB-C connector gets an EDID.
6. **Hyprland.** Once `card2-USB-*` (or a new connector) shows `connected`
   with modes, `hyprctl monitors` should pick it up with the existing
   `preferred` / `auto` `monitors.lua`.

## Later / out of scope here

- PCIe-C / m1n1 preinit (enclosures, eGPU)
- DP alt-mode on a *free* Mac USB-C port (useful fallback, different series)
- MST (Apple DPTX has no MST)
