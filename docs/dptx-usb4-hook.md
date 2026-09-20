# First kernel hook: DPTX onto USB4 DP IN

Aurora already speaks USB4 on this port and already speaks DPTX for DP
alt-mode. They never meet.

## What happens on hub plug today

1. CD321x reports USB4 (patch: USB4 before native DP).
2. `dcp_typec_route_set()` sees `state->mode == TYPEC_MODE_USB4`, which is
   **not** DP alt-mode (`dcp_typec_route_is_dp()` is false).
3. It **disconnects** DPTX from that Type-C port and returns. The only extra
   call is `dcp_typec_retrain_active_routes()` for *other* ports that already
   own a DP route.
4. ACIO comes up. Software CM builds `0:5 <-> 1:19` (DP).
5. `tb_dp_tunnel_active()` waits for DPRX on DP IN `0:5`.
6. Nothing is driving that adapter, so ~12 s later: `not active, tearing down`.

## Hardware that is already in the DT

Each ATC has a display crossbar (`apple,t6020-display-crossbar`) with three
muxes (`drivers/mux/apple-display-crossbar.c`):

| Mux index | Name    | Where the pixels go |
| --------- | ------- | ------------------- |
| 0         | `dpphy` | USB-C PHY (DP alt-mode) |
| 1         | `dpin0` | USB4 DP IN adapter 0 |
| 2         | `dpin1` | USB4 DP IN adapter 1 |

Left Back (hub) is `mux@70304c000` next to `phy@703000000` / ACIO
`cio@701ac0000`.

`dcpext0` currently takes that chip as `typec0` with **cell 0** (`dpphy`
only):

```
mux-controls = <&mux_70304c000 0 ...>;
mux-control-names = "dp-xbar", "typec0", "typec1", "typec2";
apple,typec-mux-indices = <0 0 0>;   /* crossbar *state* (which dispext) */
```

`dpin0` / `dpin1` are never requested. That is why USB4 cannot feed DP IN
`0:5`.

`dptxport_connect()` / `dptxport_set_hpd()` in `drm/apple/dptxep.c` already
know how to attach DPTX to a target and assert HPD. `dcp_dptx_connect()`
uses them for alt-mode. USB4 never calls them for this port.

## Patch shape

Against `aurora-silicon/linux` `aurora-wip`. Keep USB4-before-DP.

1. **DT (t602x):** for each Type-C route, also wire crossbar cells 1 and 2
   (`dpin0`, `dpin1`), or a single `usb4-dpin` mux-control. Do not steal
   `dpphy`; alt-mode on other ports must keep working.
2. **`dcp_typec_route_set()`:** on `TYPEC_MODE_USB4`, do not only
   disconnect. Select `dpin*` for this DCP, `dptxport_connect()`, then
   `dptxport_set_hpd(true)` once the USB4 DP tunnel is activating (or
   immediately if hub DP OUT already has HPD).
3. **Thunderbolt:** optional NHI callback next to `pci_tunnel_post_activate`
   so DPTX HPD is asserted in the DPRX window (`tb_dp_tunnel_active`), not
   after the tunnel is already dead.
4. **Teardown:** USB4 off / unplug → `dptxport_set_hpd(false)`, release
   display, idle the dpin mux.

Which of `dpin0`/`dpin1` is host adapter `0:5` is still unknown. First
instrumented boot should log both mux selections against
`tb_port` 5.

## What this is not

- Not DP alt-mode on Left Back (kills ACIO).
- Not PCIe-C / m1n1 preinit.
- Not DisplayLink; VMM7100 is a DP-to-HDMI retimer on hub DP OUT `1:19`.
