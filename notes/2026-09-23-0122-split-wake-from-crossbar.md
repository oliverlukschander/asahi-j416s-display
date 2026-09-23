# 0122: split the native DPIN0 wake from the crossbar select

Direct correction to 0121 after its first hardware test. 0121 removed the eager
crossbar/DPIN0 activation from `dptxport_call_activate()` entirely, expecting DCP
to naturally continue via `SET_LINK_RATE` once nothing premature blocked it. Result:
DCP did **less** than before -- no `INACTIVE_SINK_DETECTED`, no `SET_LINK_RATE`,
nothing at all until the 12s DPRX timeout. Worse than 0119, which at least reached
`INACTIVE_SINK_DETECTED`.

## Why

Re-reading the reference implementation's (aurora-silicon/linux#8) own comment more
carefully: "The DP IN adapter may only be woken (DPTX_INACTIVE=0) while DCP drives
the DPTX, i.e. from DCP's Activate call; waking it earlier hangs the machine." This
describes the wake as *required* at Activate -- 0121 removed it entirely instead of
just removing the crossbar mux selection that was bundled with it. Without any wake
at all, DCP apparently never even considers this port worth an AUX probe.

`dptxport_native_dpin()` couples the ACIO wake (`apple_usb4_dpin0_set_active()`) and
the crossbar `mux_control_select()` into one call whenever `active=true`, with no
way to do one without the other -- so 0121's only options were "both" (0119's
behavior, premature) or "neither" (0121's actual behavior, worse).

## The fix (kernel commit 047e3e1)

Added a `crossbar` bool parameter to `dptxport_native_dpin()`, gating just the
mux-selection branches (`if (active && crossbar && bring_up)` /
`else if (active && crossbar)`) while the ACIO wake (`set_active()`) always still
runs when `active` is true, independent of `crossbar`. Call sites:
- `dptxport_call_activate()`: `dptxport_native_dpin(service, true, false, false)`
  -- wake only, matching the reference implementation's Activate handler exactly.
- `dptxport_call_did_change_link_config()`: `dptxport_native_dpin(service, true,
  usb4_tunnel_clock, true)` -- unchanged behavior, does both, already correctly
  gated on `dptx->link_rate`.
- `dptxport_call_deactivate()`: `dptxport_native_dpin(service, false, false, true)`
  -- `crossbar` is irrelevant here since `active=false` skips both mux branches
  regardless; passed `true` for no behavior change.

## Build verification

Only `dptxep.o` recompiled. New `appledrm.ko` SHA256:
`ed41d69d6e59debd3906a542f1800f6243705e67fcbb83d6646a578047bf6335`. `phy-apple-atc.ko`
untouched (still byte-identical to 0119's known-good hash). Stale-symlink sweep
clean, `test-dpin-handshake.c` 13/13 still pass.

## Test plan

Same protocol, single boot. Watch for the ACIO wake (`native DPIN0: DCP active=1
result=...`, now logged immediately after `APCALL 0`, matching 0119's timing) but
critically **no** crossbar-related log line (`Switched dpin0 to...`) at that point
-- confirming the split worked. Then watch for whether `INACTIVE_SINK_DETECTED`
still fires (expected, same as 0119) and, this time, whether it's followed by
`SET_LINK_RATE` and a *second*, later `native DPIN0: link-config up rate=...` line
from `DidChangeLinkConfiguration` bringing up the crossbar for the first time --
this is the concrete signal the reordering actually works.
