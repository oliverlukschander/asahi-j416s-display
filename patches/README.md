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
