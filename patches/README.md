Kernel patches against `aurora-silicon/linux` `aurora-wip` (this machine:
`linux-aurora` 7.1.12 + the USB4 series in
[asahi-j416s-usb4](https://github.com/oliverlukschander/asahi-j416s-usb4)).

| Patch | What |
| --- | --- |
| `0001-drm-apple-route-DPTX-to-USB4-DP-IN-on-Type-C-USB4.patch` | On `TYPEC_MODE_USB4`, select crossbar **dpin0** (`typecN-usb4`) and start DPTX so DPRX can finish on tunnel `0:5 <-> 1:19`. |
| `0002-drm-apple-borrow-USB4-DP-IN-mux-from-the-same-crossb.patch` | If DT has no `typecN-usb4`, use mux index 1 (or `appledrm.usb4_dpin=2`) on the same chip as `typecN`. No m1n1 DTB rebuild. |

USB4-before-DP and m1n1 aliases stay in the USB4 repo / [aurora-silicon/linux#6](https://github.com/aurora-silicon/linux/pull/6).

`dpin0` vs `dpin1` is still a guess. If the tunnel still dies after this is running, try cell `2` in the DT mux-controls.
