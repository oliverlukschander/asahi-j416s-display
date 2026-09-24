# 0143: it works -- generalize and clean up

## Confirmed working

Candidate 0142 (removing the second batch of stale
`usb4_native_dpin=1`/`usb4_protocol_probe=1` configs) produced a real,
working picture: 2560x1440 on the BenQ monitor over the OWC Thunderbolt 5
hub + Synaptics VMM7100 adapter. `captures/2026-09-24-0142-boot-kernel.log`
confirms `apple_plane_atomic_check: plane=54 crtc=69 mode=2560x1440
fb=2560x1440 OK` and `hyprctl monitors` showed `2560x1440@59.95100` (not
`0x0`). Oliver confirmed the picture directly.

This is the resolution of the entire session: direct HDMI works (DP
alt-mode), USB-C+HDMI-adapter works (DP alt-mode), and now the OWC hub
(genuine USB4/Thunderbolt DP tunneling, the mechanism that had never
worked at all before today) works too.

## What this candidate does: turn the fix into something permanent

Everything that got this working was staged as opt-in module parameters
and per-session diagnostic `dev_info()` calls, appropriate for iterating
under the mandatory one-hardware-attempt-at-a-time protocol this session
followed, but not appropriate to leave in a driver meant to just work.
This candidate removes all of it and makes the working configuration the
only configuration:

**Removed entirely** (all part of the pre-0127 "native DPIN0"
single-purpose proof of concept, fully superseded by the real
tunnel-routing mechanism from `0dc9f5087`):
- `usb4_native_dpin`, `usb4_protocol_probe`, `dcp_usb4_native_route()`,
  and the `possible_crtcs` exclusion it drove in
  `apple_probe_typec_ports()`. This is the exact mechanism that took two
  full rounds of "find the stale config" (0136, 0140/0142) to defeat --
  removing the code path entirely means it can never again silently
  reappear from a leftover conf file.
- `dpin_native` and `apple_usb4_dpin0_set_active()`
  (`drivers/thunderbolt/apple.c`) -- confirmed via a full-tree grep to
  have zero callers; an orphaned duplicate of the real, generalized
  `apple_dpin_set_active()` a few hundred lines below it in the same
  file.
- `usb4_defer_bringup` and the whole deferred-bringup/frame-snapshot
  mechanism in the crossbar driver (`t602x_right_dpin0_bring_up()`,
  `apple_dpxbar_right_dpin0_bring_up()`,
  `apple_dpxbar_right_frame_snapshot()`,
  `apple_dpxbar_is_typec_crossbar()`, and their struct fields) --
  confirmed dead: the flag's only effect (a `-EINVAL` on any state other
  than dcpext1's) required the same stale-config leftover pattern to
  ever fire.

**Generalized to unconditional, permanent behavior** (kept the logic,
removed the opt-in gate):
- `usb4_route_prefer_fixed_diag` -> `apple_dcp_tb_dp_tunnel()`'s route
  scoring now always prefers a pipeline with a fixed output (dcpext0)
  for a Type-C tunnel route. Extensive hardware testing this session
  (candidates 0128-0135) found dcpext1 (Type-C only, the intuitively
  "correct" pipeline) never completes a real link for a tunnel target --
  DCP firmware accepts `request_display` but never issues another
  apcall, a firmware-internal decision with no driver-source asymmetry
  to explain or fix (confirmed by an independent research pass and its
  own adversarial verification). dcpext0 reaches a full real AUX/DPCD
  link every time, and with 0136-0142's fixes, a working picture.
- `usb4_tunnel_clock` (`drivers/phy/apple/atc.c`) and `dp_bw_grant`
  (`drivers/thunderbolt/tunnel.c`) -- both already gated on
  `of_machine_is_compatible("apple,j416s")` plus specific port/PHY
  compatibility checks (`tb_dp_is_apple_j416s_right_dpin()`,
  T6020 ATC PHY checks); the extra opt-in flag added nothing beyond
  what was already correctly scoped. (`dp_video_counter`, a genuine,
  self-described, permanent debugfs packet-counter diagnostic, is left
  exactly as it was -- not scaffolding, just an ordinary opt-in feature
  like `show_notch`/`hdmi_audio`/`unstable_edid` elsewhere in the same
  driver.)

**Removed** (diagnostic-only additions from this session's own
investigation, no longer needed -- some fired on every single atomic
commit or every frame, which is real log spam in permanent use):
- `apple_plane_atomic_check()`'s per-exit `dev_info()` calls
  (`plane.c` -- confirmed via `git diff` to be byte-identical to its
  pre-session state again).
- `dcp_hotplug()`'s and `dcp_crtc_atomic_modeset()`'s crtc-state
  diagnostics (`iomfb.c`).
- `dcp_crtc_atomic_check()`'s per-commit diagnostic (`dcp.c`).
- `apple_probe_typec_ports()`'s possible_crtcs-computation diagnostic
  (`apple_drv.c`).

Net diff: **-556/+43 lines across 10 files.**

## The result: no module options needed at all

Every module parameter this project ever added specifically for the j416s
USB4 tunnel work is now gone. The driver just works on this hardware with
its plain defaults -- no `/etc/modprobe.d/j416s-*.conf` file needed any
more. `scripts/manage-0143.py` removes the last remaining conf file
(0142's) with no replacement.

## Build verification

All four affected modules rebuilt individually and confirmed clean:
`appledrm.ko`, `mux-apple-display-crossbar.ko`,
`thunderbolt.ko`/`thunderbolt_apple.ko`, `phy-apple-atc.ko` -- no new
warnings in any of them. One pre-existing, unrelated warning
(`apple_dp_set_dpme` defined but not used, in `drivers/thunderbolt/apple.c`)
was confirmed via `git show HEAD` to already exist before this session's
changes; out of scope for this cleanup.

`python3 scripts/manage-0143.py check` (no sudo) passes.

## Test plan

This is a refactor of already-working, hardware-confirmed functionality
-- every removed flag's redundancy was verified by reading the code (not
guessed), and the two behavior-affecting generalizations
(`usb4_route_prefer_fixed_diag`, and the crossbar/possible_crtcs removal)
are exactly what the currently-installed, currently-working 0142
configuration already does at runtime, just without needing the flag any
more. Still, this changes real code paths, so it needs its own real
hardware confirmation before being treated as the final state:

1. Ask Oliver to run `sudo -n python3 scripts/manage-0143.py check` then
   `sudo -n python3 scripts/manage-0143.py install`.
2. Ask Oliver to reboot with the monitor connected as usual.
3. Confirm the picture still comes up correctly (resolution, no
   regressions), and that `cat /etc/modprobe.d/*.conf 2>/dev/null` shows
   no j416s-specific file at all.
