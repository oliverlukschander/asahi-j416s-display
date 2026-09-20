# Topology

## Hardware

OWC Thunderbolt 5 Hub (`OWCTB5HUB5P`):

- 1× Thunderbolt 5 host (to the Mac)
- 3× Thunderbolt 5 downstream USB-C
- 1× USB-A 10 Gb/s
- **No HDMI, no DisplayPort jack**

Video is a USB-C to HDMI adapter on a downstream TB5 port. OWC documents
that: HDMI/DP displays attach with a USB-C adapter on a Thunderbolt 5 port.

On this machine:

| End | Device |
| --- | --- |
| Mac port | USB-C Left Back (`port1`, CD321x `0-0038`, ACIO `701ac0000`) |
| Hub | `thunderbolt 0-1` vendor `0x5a` device `0xde81` |
| Keyboard | USB-A → Keychron Q4 `3434:0140` |
| Display | TB5 USB-C → Synaptics VMM7100 `06cb:7100` → HDMI → monitor |

VMM7100 USB interfaces: HID (`03`) + Billboard (`11`). That is the adapter's
USB side. Pixels are DP alt-mode on the same plug, then HDMI out.

## USB4 view

Host router `0-0` port 1 is up (`link=usb4`). Hub `0-1` upstream is USB4.
Hub `usb4_port3`, `usb4_port5`, `usb4_port7` are `link=none` because the
HDMI adapter is not a USB4 device.

The hub still exposes a **DP OUT protocol adapter**. Software CM paired it:

| Adapter | Role |
| --- | --- |
| `0:5` | host DP IN (ACIO, should be fed by DPTX via the display crossbar) |
| `1:19` | hub DP OUT (the TB5 port that has the VMM7100) |

## Why the tunnel dies

`drivers/thunderbolt/tb.c` `tb_dp_tunnel_active()`:

1. CM allocates and activates a DP tunnel `0:5 <-> 1:19`.
2. It waits for DPRX (AUX) to complete.
3. If the tunnel is still not active, it logs `not active, tearing down`
   and marks the DP IN resource unavailable (`DPRX negotiation failed`).

The in-tree comment says this happens when **no graphics driver is talking
to DP IN**, or the sink is not actually connected. The VMM7100 is enumerated,
so the sink is there. DPTX is not routed onto `0:5`.

## Apple path that is missing

From the comment diagram in `drivers/thunderbolt/apple.c`:

```
dcpext  -->  display crossbar  -->  USB4 DP IN adapter  -->  tunnel
```

Today:

- ACIO + NHI + USB3 tunnel: working
- PCIe-C tunnel: coded, blocked on m1n1 preinit (not needed here)
- DP IN `0:5`: exists, tunnel attempted
- DPTX / crossbar: used for DP alt-mode toward the ATC PHY, **not** toward
  ACIO DP IN while the port is in USB4

`dcpext0` (`289c00000.dcp`) is labelled HDMI-A. This chassis has no HDMI
jack. `dcpext1` (`315c00000.dcp`) is USB-C. Boot logged
`typec-routes/route@0: failed to get display crossbar` on that DCP, then it
still bound. Crossbar routing is the next place to look.

## What not to do

- Do not force DP alt-mode on Left Back. That turns the Thunderbolt switch
  off and USB on the hub dies.
- Do not treat the VMM7100 USB device as a DisplayLink GPU. It is a DP-to-HDMI
  retimer.
- Do not wait on PCIe-C / m1n1 handoff for this monitor.
