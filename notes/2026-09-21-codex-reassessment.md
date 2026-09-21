# j416s USB4 display investigation — 2026-09-21

External display remains unresolved. No hardware actions, module loads,
parameter writes, MMIO access, installation, or reboot were performed.
The initial investigation ran in /tmp under a restricted sandbox. After the
user enabled full access, the diagnostic patch was committed to the original
kernel branch and formatted into patches/. This note preserves the initial
assessment; runtime testing is recorded separately in ACTION-LOG.md.

## Current evidence

Source baseline: linux-aurora-pr branch j416s-usb4-dpin,
commit efb4376e8d59e0a2fe16293a8825d4ef12335b60.
Filtered current-boot kernel messages are in boot-display.log.

- Running kernel: 7.1.12-2.5-1-ARCH.
- Hub route in this boot: typec0, NHI 0x701f00000, ACIO 0x701ac0000,
  crossbar 0x70304c000. Do not substitute the right-port addresses.
- Existing tunnel 0:5 <-> 1:19: VE=1 AE=1 HPD=1 DPRX=0.
- DRM reports eDP-1 connected/enabled; HDMI-A-1 and USB-1/2/3 disconnected.
- Keychron Q4 remains registered in /proc/bus/input/devices. Enumeration
  does not by itself prove that key events work; no input events were read.
- Hyprland IPC query failed with "Couldn't set socket timeout (2)".
  No claim of a successful compositor query is made.

## Reassessment of the handoff

1. Missing timing is not established as the initiating fault. The empty HDMI
   controller 0x289c00000 logs the same no-timing warning at 14.063 s, followed
   by run mode 2 -> 1 -> 0. dcpext1 does so at 15.088 s. Its USB4 connection
   attempt only starts around 17.232 s. This is consistent with disconnected
   external controllers shutting down before display discovery; it does not
   prove that interpretation. The working panel itself briefly transitions
   to run mode 0 during its successful modeset.

2. TimingElements flows from firmware to Linux. iomfb_template.c receives
   a chunked dictionary and enumerate_modes() extracts firmware mode IDs.
   set_digital_out_mode selects those IDs; inventing a Linux mode or borrowing
   panel IDs does not install a timing in the external firmware instance.
   The read_edt_data callback is a boot-property query, and its name alone is
   not evidence of an EDID or timing-upload interface. The existing 1080p
   injection experiment already failed; do not repeat it.

3. Crossbar 0x800 semantics on T602x are not established by the cited driver.
   The upstream T602x header warns that most register names may be wrong.
   Its explicitly identified status offsets include 0x804, 0x810 and 0x81c.
   The 0x800 name used by the experiment comes from the older-generation
   register block. Zero is an observation, not proof of a missing pixel/AUX
   clock or of causality for the firmware timeout. A "Switched dpin0" log
   likewise proves that software ran, not successful physical routing.

4. Current code still automatically repeats set_hpd after request_display,
   despite the latest notes prohibiting it. The live boot confirms that retry
   and the subsequent five-second DCPDPDevice timeout. Its removal is included
   in the diagnostic candidate.

## Prepared candidate

The patch logs bounded EDT request keys/count/default0, received property
keys/length/parse result/mode count for external controllers, and mode state
just before the USB4 request_display. It preserves callback replies and adds
no timing injection or MMIO. It removes only the second HPD call from the
normal USB4 connection path; the pre-request HPD remains.

This is diagnostic preparation, not a proven display fix. Other old experimental
parameter handlers and crossbar code remain in the baseline. Do not treat this
candidate as a reviewed replacement for all prior hardware experiments.

The isolated kernel/ repository contains a source snapshot and a candidate
commit. It is NOT the user's full kernel git history. The format-patch is for
application to the original baseline after permissions allow it. The candidate has now been applied to the original kernel history; use the
0090 patch in this repository rather than the temporary snapshot commit.

Build uses the supplied kernel build tree and an out-of-tree directory here.
CONFIG_DEBUG_INFO_BTF_MODULES= disables module BTF generation for this build,
avoiding both pahole and renaming vmlinux in the read-only build tree.
Build logs and the uninstalled module remain in this directory.

## Next decision

A runtime diagnostic test requires the prescribed action-log commit and push,
hub unplugging before installation/boot, and a session permitted to modify the
actual development repositories and system module/initramfs files. The user has now enabled full access. The required log-before-action sequence
and physical hub-unplug prerequisite still apply.
Do not run scripts/load-appledrm.sh casually: it installs several modules,
rebuilds initramfs, and automatically reboots after three seconds.

Before any test, audit its exact effective hardware actions against the user's
prohibitions, log the exact commands/addresses, commit and push that log, and
retain the requirement to stop/unplug if eDP goes black. No next hardware action
has been recorded as approved or executed by this investigation.

The useful remaining question is which connection/AUX/firmware initialization
step prevents sink discovery. Firmware EDT requests can test the handoff's
property hypothesis. Validating T602x USB4 routing still needs authoritative
register/protocol evidence or a known-working trace; random clock/register
writes are not justified by the current evidence.

References:
- https://raw.githubusercontent.com/AsahiLinux/linux/fairydust/drivers/mux/apple-display-crossbar.c
- https://asahilinux.org/docs/hw/soc/display-controllers/
- local kernel drivers/gpu/drm/apple/iomfb_template.c and dptxep.c
- original notes/ACTION-LOG.md and notes/2026-09-21-0086-keep-run-mode.md

Validation: final module build succeeded (including MODPOST and link), vermagic
matches 7.1.12-2.5-1-ARCH, and git apply --check passed against the original
kernel tree. Initial diagnostic printf format warning was fixed (%zu for
chunk length). The remaining build warning reports the unavailable pahole
version; module BTF was explicitly disabled. No runtime validation occurred.
Patch: patches/0090-drm-apple-trace-timing-discovery-drop-repeated-hpd.patch.

## Full-access continuation

The patch is now kernel commit `a0df2ede847714b1de9fd2d0341cb1050c831df6`.
The build in the normal src/appledrm directory succeeds with the supplied
headers, MODPOST and module link. Existing unused-function warnings remain.
Candidate appledrm.ko SHA256:
`790475c0059aea58b602de5a35f2f2a325ceafcb5e8756946e7e9b5b994704d1`.

Hyprland IPC now succeeds with full access: eDP-1 is active at
3456x2160@120, and no external monitor is active.

All five other modules copied by load-appledrm.sh have hashes identical to
the files currently installed under the kernel module tree. Only appledrm
changes. The loader now refuses installation while any external Thunderbolt
router is present and accepts --no-reboot, so initramfs can be checked before
reboot is logged and scheduled separately. bash -n and git diff --check pass.
The loader has not yet been executed.
