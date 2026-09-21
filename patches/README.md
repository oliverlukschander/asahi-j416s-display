Kernel patches against `aurora-silicon/linux` `aurora-wip` (this machine:
`linux-aurora` 7.1.12 + the USB4 series in
[asahi-j416s-usb4](https://github.com/oliverlukschander/asahi-j416s-usb4)).

| Patch | What |
| --- | --- |
| `0001-drm-apple-route-DPTX-to-USB4-DP-IN-on-Type-C-USB4.patch` | On `TYPEC_MODE_USB4`, select crossbar **dpin0** (`typecN-usb4`) and start DPTX so DPRX can finish on tunnel `0:5 <-> 1:19`. |
| `0002-drm-apple-borrow-USB4-DP-IN-mux-from-the-same-crossb.patch` | If DT has no `typecN-usb4`, use mux index 1 (or `appledrm.usb4_dpin=2`) on the same chip as `typecN`. No m1n1 DTB rebuild. |
| `0003-drm-apple-delay-USB4-DPTX-connect-until-the-DP-tunne.patch` | Wait 2.5s after USB4 (10 retries) so DPTX AUX runs while tunnel `0:5 <-> 1:19` is up, not before ACIO. |

USB4-before-DP and m1n1 aliases stay in the USB4 repo / [aurora-silicon/linux#6](https://github.com/aurora-silicon/linux/pull/6).

`dpin0` vs `dpin1` is still a guess. If the tunnel still dies after this is running, try cell `2` in the DT mux-controls.
| `0004-drm-apple-auto-arm-USB4-DP-IN-on-the-NHI-that-has-a-.patch` | If the Type-C mux never delivers USB4 to DCP, arm DP IN on the typecN whose NHI has the hub. `usb4_arm=0..2` forces a port. |
| `0019-drm-apple-drive-USB4-DP-IN-instead-of-HDMI-PHY-3.patch` | Prefer USB-C dcpext; DPIN in remote-port bits 13:12; no HDMI PHY 3, no ATC PHY, no HPD kick. |
| `0020-mux-apple-t602x-program-DPIN0-DPIN1.patch` | T602x crossbar actually selects DPIN0/DPIN1 analog (`ATC_DPIN0`) instead of always writing DPPHY bits. Out-of-tree: `src/mux`. |
| `0021-phy-apple-atc-enable-DP-AUX-on-USB4-without-lane-switch.patch` | USB4 ACTIVATE enables `lpdptx` AUX without switching SS lanes to DP. Out-of-tree: `src/phy`. |
| `0022-drm-apple-bind-USB4-DPTX-PHY-for-lpdptx-AUX.patch` | Bind Type-C DP PHY on USB4 so ACTIVATE can enable AUX. Skip ATC DP lane `phy_configure`. |
| `0023-drm-apple-USB4-AUX-before-connect-drop-DPIN-bits.patch` | Enable lpdptx at USB4 mux arm; remote-port ATC only (`0x8020`), no DPIN field. |
| `0024-drm-apple-USB4-DPTX-engine-PHY3-destination-dpin0.patch` | USB4 uses HDMI PHY 3 as DPTX engine; USB-C dpin0 analog; DPIN bits in remote-port. Closed: trains empty HDMI jack. |
| `0025-thunderbolt-Apple-DP-IN-analog-AUX-after-tunnel-up.patch` | After DP VE/AE, dump host DP IN CS/hops/ACIO RC and poll CS on change. Out-of-tree also builds `thunderbolt_apple.ko`. |
| `0026-drm-apple-USB4-DP-IN-is-ACIO-AUX-stop-PHY-3.patch` | USB4 selects USB-C dpin mux only. No DPTX PHY 3, no ATC `phy_set_mode(DP)`. |
| `0027-thunderbolt-enable-USB4-DPTX-Discovery-on-Apple-DP-I.patch` | Set ADP_DP_CS_13 DPTX Discovery Mode on host DP IN; dump CS11–16 and ROUTER_CS_6. |
| `0028-thunderbolt-run-Apple-DPTX-Discovery-before-AE-VE.patch` | DPTX Discovery before AUX enable; try CS13 bits 0,1,8,16,24,31. Closed: CS9 static. |
| `0029-thunderbolt-scan-ACIO-MMIO-for-DP-IN-analog-AUX.patch` | Closed: ACIO window `readl` hung the machine (reboot loop with dock). |
| `0030-thunderbolt-do-not-scan-ACIO-MMIO.patch` | Remove window/RC+/NHI scans. USB4 CS dumps only. |
| `0031-drm-apple-USB4-DPTX-HPD-without-PHY-connect.patch` | Closed: request_display still ACTIVATE ATC 2, then 22/24. |
| `0032-drm-apple-USB4-DPTX-remote-port-is-ATC-0-DPIN-1.patch` | Closed: 0x9000 device == NULL / INACTIVE_SINK. |
| `0033-drm-apple-USB4-DPTX-engine-is-lpdptxphy-index-4.patch` | of_platform_device_create skipped disabled node. Firmware 22/24 on 0:4. |
| `0034-drm-apple-instantiate-disabled-lpdptxphy-platform-de.patch` | PHY probed; ACTIVATE still 22/24 — atcphy was NULL. |
| `0035-drm-apple-USB4-ACTIVATE-phy_set_mode-on-lpdptxphy.patch` | Trained HBR3 4-lane then modeset 3456x2234@120 on dcpext and blanked eDP. |
| `0036-drm-apple-do-not-phy_set_mode-lpdptxphy-on-USB4.patch` | Unbind lpdptxphy atcphy. Do not complete USB4 linkcfg on SET_ACTIVE_LANE. |
| `0037-drm-apple-USB4-train-lpdptxphy-without-DRM-hotplug.patch` | Trained 4 lanes, hotplug ignored, eDP still blanked. phy_set_mode lpdptxphy is unsafe on this laptop. |
| `0038-drm-apple-do-not-phy_set_mode-lpdptxphy.patch` | Unbind lpdptxphy atcphy again. Instantiating the device is OK; DP mode blanks eDP. |
| `0039-drm-apple-skip-USB4-DPTX-connect-lpdptxphy-DP-mode-b.patch` | Skip DPTX connect. Fix false "trained 4 lanes" from GET_MAX_LANE_COUNT. |
| `0040-drm-apple-USB4-assign-lpdptxphy-DCP-index-only.patch` | Closed: second ioremap of lpdptxphy core hung the fabric (~1 s boot). |
| `0041-drm-apple-do-not-ioremap-lpdptxphy.patch` | No lpdptxphy MMIO. Skip DPTX connect. |
| `0042-drm-apple-USB4-lpdptxphy-assign_only-via-phy-driver.patch` | core+0x10=2 trains HBR3/4 lanes and blanks eDP. DCP-index mux is the steal. |
| `0043-drm-apple-skip-USB4-DPTX-lpdptxphy-assign-blanks-eDP.patch` | Skip DPTX connect. Do not write lpdptxphy core+0x10. |
| `0044-drm-apple-USB4-DPTX-train-via-sysfs-after-lid-close.patch` | Train ran; link 4→1 lanes then rate 0. DRM still suppressed (bug). |
| `0045-drm-apple-USB4-manual-train-allows-DRM-hotplug.patch` | Trained 4 lanes, DPRX stayed 0, no 315c hotplug. lpdptxphy is not DP IN analog. |
| `0046-drm-apple-auto-restore-eDP-10s-after-USB4-DPTX-train.patch` | After manual train, assign lpdptxphy back to DCP 0 in 10 s. |
| `0047-drm-apple-USB4-fake-1080p-scanout-without-lpdptxphy.patch` | Hyprland USB-3 0x0@60. LINK_STATUS_BAD blocked a real 1080p commit. |
| `0048-drm-apple-do-not-mark-USB4-link-BAD-on-fake-scanout.patch` | Hyprland still 0x0; never called set_digital_out_mode on 315c. |
| `0049-drm-apple-USB4-kernel-iomfb_modeset-1080p-on-scanout.patch` | Firmware 80000104: setmode failed, fDisplayPowerState=0. |
| `0050-drm-apple-USB4-iomfb-poweron-before-fake-1080p-modes.patch` | Poweron did not set fDisplayPowerState. Next reboot stuck on logo. |
| `0051-drm-apple-do-not-iomfb_poweron-USB4-dcpext.patch` | Remove dcpext iomfb_poweron. |
| `0052-drm-apple-USB4-request_display-then-1080p-modeset.patch` | usb4_scanout: request_display (no PHY) then iomfb_modeset. No poweron. |
