# 0091: reconsider the USB4 hotplug guard

Oliver asked whether suppressing hotplug is preventing the display from
working and requested a fresh examination of the old assumptions.

The original rationale conflated a PHY assignment, receipt of panel-like
modes on dcpext, a DRM notification and a modeset. Later tests recorded in
2026-09-21-lpdptxphy-blank-no-drm.md and 2026-09-21-status.md reproduced
eDP blanking with hotplug suppressed and no dcpext modeset. Consequently,
blocking firmware hotplug is not an effective safeguard against the PHY
assignment. This corrects the rationale for retaining that particular guard
in the previous audit. The restrictions on the actual PHY operation remain.

## Code change

Kernel commit 65ac2fb0ba9aaefff62a5f091016691e9cfdeab3 removes only the early
USB4 return in dcpep_cb_hotplug and adds nr_modes to its log. Firmware
connect/disconnect callbacks now follow ordinary external-display handling,
including deferral during modesets. No mode is invented or copied.

The usb4_force_dptx flag remains false and the safe connect path remains in
place. The link-completion gate is unchanged; restoring connector callbacks
does not require enabling the dangerous PHY assignment. The existing main
display callback handling and USB4 exclusion from automatic active-CRTC
retraining are unchanged.

This is not proof that every future USB4 callback is safe: wrongly routed
firmware could still supply panel modes. The protection against that known
failure is avoiding the physical PHY reassignment, not the old notification
gate. get_modes uses the selected DCP's modes and mode_valid rejects modes
absent from that list; neither function verifies physical sink identity.

## What the live trace actually says

Read existing kernel messages with:
`sudo -n dmesg | rg 'cb_hotplug|DCP property|DPTXPort|USB4:|is_main_display|DP IN|Switched dpin'`

No external IOMFB hotplug callback is currently being discarded. dcpext1
reports is_main_display=0, so the main-display check is not hiding one.
The tunnel reports HPD=1, and the driver sends firmware HPD before
request_display. Firmware then calls GET_SUPPORTS_HPD, GET_MAX_LANE_COUNT
and ACTIVATE, but supplies neither modes nor a connected callback.

These are distinct stages:

1. USB4 DP IN reports downstream sink presence.
2. DPTX set_hpd communicates that state to firmware.
3. Firmware discovers the sink and supplies display properties/callbacks.
4. IOMFB callback updates DRM; userspace can probe and select modes.

Patch 0091 repairs stage 4's unjustified gate. The present trace stops before
stage 3 completes. A synthetic DRM event cannot provide the missing firmware
mode IDs. The earlier repeated post-request HPD did start DCPDPDevice, which
then timed out; that remains an unresolved firmware-side issue and the
prohibited experiment was not repeated.

av_service_connect was also examined: it opens the audio service. Skipping
it does not itself demonstrate a missing video-discovery call.

## Validation and deployment state

Both IOMFB firmware variants compiled; MODPOST and module link succeeded
against the supplied 7.1.12-2.5-1-ARCH build tree, with module BTF disabled.
git diff --check passed. Existing pahole-version warning remains.

Built module SHA256:
b4edbde88434d187e3cec4b55e21f44eb77abf26feeed61d61fc4724e538207d

Patch: patches/0091-drm-apple-decouple-usb4-hotplug-from-phy-training.patch.
The src/appledrm build artifact is now 0091; installed/running module remains
0090. No installation, module parameter write, firmware request, MMIO access,
hub replug or reboot was performed. Runtime behavior of 0091 is untested.
Do not run the loader without a new logged/pushed action and hub unplugging.
