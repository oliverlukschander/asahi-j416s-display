# asahi-j416s-display

Make an external monitor work through an **OWC Thunderbolt 5 Hub** on a
**MacBook Pro 16-inch, M2 Pro, 2023** (`Mac14,10` / `apple,j416s`) running
Omarchy with the Aurora kernel.

USB on the hub already works
([asahi-j416s-usb4](https://github.com/oliverlukschander/asahi-j416s-usb4)).
This repo is the display path: a **Synaptics VMM7100 USB-C to HDMI adapter**
plugged into a hub Thunderbolt 5 port.

> **Unofficial.** Not affiliated with Asahi Linux, Aurora Silicon, OWC, or
> Omarchy. File issues here, not with those projects.

## Topology (do not replug)

```
Mac USB-C Left Back  --USB4-->  OWC Thunderbolt 5 Hub
                                  ├─ USB-A: Keychron Q4          (works)
                                  └─ TB5 USB-C: VMM7100 HDMI     (dark)
                                       └─ HDMI --> monitor
```

The OWC Thunderbolt 5 Hub has **no HDMI jack**. Three downstream Thunderbolt 5
ports plus one USB-A. A USB-C HDMI adapter on a TB5 port is the supported
layout (OWC manual).

The Linux software connection manager already pairs host **DP IN `0:5`** with
hub **DP OUT `1:19`** and builds a DP tunnel. ~12 seconds later it tears it
down:

```
0:5 <-> 1:19 (DP): not active, tearing down
```

That message is `tb_dp_tunnel_active()` in `drivers/thunderbolt/tb.c`. The
comment there is the whole bug: **DPRX negotiation failed** because nothing
on the Apple DPTX side is driving the USB4 DP IN adapter. USB4 did its job;
pixels never showed up.

Hub downstream `usb4_port3/5/7` staying `link=none` is expected: the VMM7100
is a DP-alt-mode sink, not a USB4 router.

## Current machine

| Item | Value |
| --- | --- |
| Host | MacBook Pro 16-inch M2 Pro 2023, `apple,j416s` |
| Kernel | `linux-aurora` `7.1.12-2.5-1-ARCH` (`aurora-silicon/linux` `2439016d`) |
| USB4 | working (CD321x USB4-before-DP + m1n1 aliases) |
| Hub | OWC Thunderbolt 5 Hub `1e91:de81`, authorized, 40 Gb/s |
| Adapter | Synaptics VMM7100 `06cb:7100` HID + Billboard on hub USB 2 |
| Keyboard | Keychron Q4 `3434:0140` on hub USB-A |
| Hyprland | `eDP-1` only |

Live dump: [`captures/2026-09-20-initial.txt`](captures/2026-09-20-initial.txt).

## What has to happen

```
dcpext DPTX  -->  display crossbar  -->  USB4 DP IN 0:5
                                              |
                                         DP tunnel
                                              |
                                         hub DP OUT 1:19
                                              |
                                         VMM7100 DP-to-HDMI
                                              |
                                           monitor
```

Aurora `drivers/thunderbolt/apple.c` already has PCIe-C tunnel callbacks on
the NHI. There are no equivalent DP callbacks. `drm/apple` DPTX talks to USB-C
PHYs for DP alt-mode; it does not route onto ACIO DP IN when the port is in
USB4.

Native DP alt-mode on the **hub** port would turn the Thunderbolt switch off
again (that is why USB4-before-DP exists). Display through the hub must be
**tunneled DP**, not alt-mode on the Mac port.

Hook for the first kernel patch:
[`docs/dptx-usb4-hook.md`](docs/dptx-usb4-hook.md). The display crossbar
already has `dpin0`/`dpin1` outputs; the DT only wires `dpphy` (alt-mode).

PCIe-C (`m1n1 handoff is not initialized`) is unrelated. Skip it.

## Repo layout

```
docs/topology.md     How the bits are wired
docs/ROADMAP.md      Work items
notes/               Dated bring-up notes
captures/            scripts/capture-display.sh output
scripts/             Diagnostics (no sudo required)
patches/             Kernel patches once they exist
```

Kernel tree for patches: `aurora-silicon/linux` `aurora-wip`, same style as
the USB4 series. Do not vendor the kernel here.

## Capture

```bash
./scripts/capture-display.sh
```

Writes `captures/capture-<timestamp>.txt`.
