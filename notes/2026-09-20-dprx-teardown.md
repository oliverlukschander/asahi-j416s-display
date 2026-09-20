# 2026-09-20 — DP tunnel exists, DPRX does not

Cabling left as-is: OWC TB5 Hub on USB-C Left Back, Keychron on USB-A,
VMM7100 HDMI adapter on a hub TB5 port.

## Evidence

From `captures/2026-09-20-initial.txt`:

- Hub `0-1` authorized, USB4, 2×20 Gb/s.
- VMM7100 `06cb:7100` on USB `1-1.2` (hub USB 2 port 2).
- DRM: only `eDP-1` connected.
- 14 seconds after hub enumerate:

  `thunderbolt-apple-nhi 701f00000.nhi: 0:5 <-> 1:19 (DP): not active, tearing down`

## Code path (aurora-wip `tb.c`)

`tb_tunnel_one_dp()` allocates `tb_tunnel_alloc_dp(..., tb_dp_tunnel_active, ...)`
and `tb_tunnel_activate()`. When activation finishes, `tb_dp_tunnel_active()`
runs:

- If `tb_tunnel_is_active(tunnel)`: DPRX completed, keep the tunnel.
- Else: log `not active, tearing down` and
  `tb_dp_resource_unavailable(..., "DPRX negotiation failed")`.

The 12 s delay matches waiting for DPRX/AUX on DP IN `0:5`.

Nothing in `drivers/thunderbolt/apple.c` connects DPTX to that DP IN.
PCIe-C has `pci_tunnel_pre/post_activate`; DP has no counterpart.

## Implication

Do not chase hub HDMI (this hub has none). Do not chase PCIe-C. Next code is
DPTX + display crossbar → USB4 DP IN `0:5` for the ACIO on Left Back, with
HPD from hub DP OUT `1:19`.
