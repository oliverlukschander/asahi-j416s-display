# 0142: remove 8 more stale pre-0135 configs still forcing usb4_native_dpin/usb4_protocol_probe

## What 0141 found

0141's probe-time diagnostic in `apple_probe_typec_ports()` showed,
for every Type-C port on this machine:
```
typec port 0 candidate dcp-index=1 native_route=1 has_candidate=1 crtc_mask=0x2
typec port 0 candidate dcp-index=2 native_route=1 has_candidate=1 crtc_mask=0x4
typec port 0 final possible_crtcs mask=0x4
```
`native_route=1` for dcpext0 (`dcp-index=1`) means
`dcp_usb4_native_route()` is **still returning true**, despite 0140/0141
dropping `usb4_protocol_probe=1`/`usb4_native_dpin=1` from our own
candidate's own module options. Since `native_route=1` and
`candidate->index (1) != 2`, the exclusion still fires and dcpext0's
CRTC bit (`0x2`) is still missing from the final mask (`0x4`, only
dcpext1's bit) -- exactly reproducing 0140's non-fix.

Checked the live module parameter values directly:
```
$ sudo cat /sys/module/appledrm/parameters/usb4_native_dpin
Y
$ sudo cat /sys/module/appledrm/parameters/usb4_protocol_probe
Y
```
Both still true, confirming the diagnostic wasn't lying -- something
*other than our own candidate's conf* is still setting them.

## Root cause: a second batch of stale configs, same shape as 0136

`grep -rl "usb4_native_dpin\|usb4_protocol_probe" /etc/modprobe.d/`
turned up eight files -- `j416s-{0127,0128,0129,0130,0131,0132,0133,0134}-dpin0-mode-guess.conf`
-- all byte-identical (`sha256:902cf068...5bc4ed65`), all still containing
`options appledrm usb4_protocol_probe=1 usb4_native_dpin=1`. **0136's
cleanup only removed the older 0113-0126 batch** (from the pre-0127
"native DPIN0" single-purpose experiment); it never touched these eight,
which are from the *first* batch of candidates using the current
tunnel-routing mechanism, predating the point where later candidates'
scripts started reliably unlinking their immediate predecessor's own
conf file. Confirmed these eight are baked into the currently-installed
initramfs alongside 0141's own conf (`lsinitcpio -x` on the live image).
modprobe merges every matching `options appledrm ...` line across every
conf file it finds, so these eight kept overriding what 0140/0141's own
(correct) conf specified.

This is the exact same shape of bug as 0136 -- leftover test-environment
config from an earlier phase of this same investigation, silently
sabotaging the current, correct configuration -- just a different batch
that 0136's own cleanup didn't cover.

## The change

Back up (sha256-verified) and remove these 8 files, same pattern as
0136's script. Keep 0141's module set (all diagnostics from 0139/0141
stay installed and active) and 0140/0141's own options
(`usb4_route_prefer_fixed_diag=1` only) unchanged. `verify_image()` now
also explicitly asserts no `.conf` anywhere in the rebuilt initramfs
contains `usb4_native_dpin=1`/`usb4_protocol_probe=1`, to catch a third
leftover batch immediately if one exists, rather than repeat this same
mistake a third time.

## Build verification

No kernel rebuild needed (same modules as 0141). `python3
scripts/manage-0142.py check` (no sudo) passes: confirms all 8 stale
confs present with the expected checksum, candidate hashes match,
0136's own cleanup still in place.

## Test plan

1. Ask Oliver to run `sudo -n python3 scripts/manage-0142.py check` then
   `sudo -n python3 scripts/manage-0142.py install`.
2. Ask Oliver to reboot with the monitor connected as usual.
3. Immediately after boot, pull `dmesg --ctime`, save as
   `captures/2026-09-24-0142-boot-kernel.log`, and check the `typec port
   ... candidate dcp-index=1 native_route=...` line -- it should now
   read `native_route=0`, and `final possible_crtcs mask=` should
   include dcpext0's bit (`0x2`) alongside dcpext1's (`0x4`), i.e.
   `0x6`. Then check whether `apple_plane_atomic_check()` finally fires
   for the tunnel connector's own plane, and -- the only thing that
   actually counts -- whether there's a picture on the external display.
   Only Oliver's own visual confirmation counts as success.
