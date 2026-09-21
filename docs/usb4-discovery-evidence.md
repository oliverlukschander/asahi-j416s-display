# T6020 USB4 DisplayPort discovery: evidence and remaining gap

This is a local investigation brief, not a submitted bug report. No message
has been sent to upstream developers. This machine uses a heavily modified
experimental driver stack; the observations must not be presented as an
upstream regression.

## Current scope of upstream support

Sven Peter's September 6, 2026 v2 USB4 series explicitly limits supported
tunneling to XDomain and USB3; PCIe and DisplayPort still require further
implementation and reverse engineering:
https://lists.openwall.net/linux-kernel/2026/09/06/840

The inspected AsahiLinux bits/270-thunderbolt apple.c describes a physical
connection from display crossbar to the host DP IN adapters, but the presence
of that diagram does not implement display initialization. Source:
https://github.com/AsahiLinux/linux/blob/bits/270-thunderbolt/drivers/thunderbolt/apple.c

## Machine and controlled comparisons

- MacBook Pro M2 Pro, j416s / Mac14,10; firmware ABI 13.5; m1n1 v1.6.1.
- Kernel 7.1.12-2.5-1-ARCH, custom branch j416s-usb4-dpin.
- OWC Thunderbolt 5 Hub, VMM7100 USB-C-to-HDMI adapter, BenQ 2560x1440.
- Oliver confirms this exact hub/adapter/monitor chain works in macOS.
- Linux direct HDMI and direct USB-C adapter both work with eDP active.
- Both successful Linux baselines used dcpext0 0x289c00000; the hub route
  reserved dcpext1 0x315c00000. We have not separately proved that dcpext1
  completes direct physical-DP discovery in this session.
- Hub keyboard works. USB4 tunnel 0:5 to 1:19 reaches VE=AE=HPD=1, DPRX=0.

## Latest failed experiment

0092, kernel commit d8ffe9b, removed the guessed target bit 12 for its opt-in
path and tested 0x8001 with connect, request_display, existing crossbar
reselect, then one HPD assertion. No physical PHY is assigned. The test was
restricted to typec0 / dcpext1 and one attempt per loaded module.

Validate/connect/request_display return success. Firmware asks
GET_SUPPORTS_HPD, GET_MAX_LANE_COUNT and ACTIVATE, then reports DEVICE_NOT_
RESPONDING (22) and DEVICE_NOT_STARTED (24) about five seconds later.
No SET_LINK_RATE, SET_ACTIVE_LANE_COUNT, external TimingElements or connected
callback follows. eDP and the hub keyboard continue working.

The HPD RPC returning zero and cached lane_count=4 are not evidence of
training: GET_MAX_LANE_COUNT itself sets that cached field. The fault logger
prints old route metadata 0:4, while the actual sent target is 0x8001.

## Source-level gap, not a proven register-level cause

In dptxport_call_activate, the only initialization call is conditional
phy_set_mode_ext(dptx->atcphy, ...). When atcphy is NULL, the handler simply
acknowledges success. The current experiment deliberately takes that branch
because the older physical-PHY assignment stole the panel engine. There is
no alternative host DP-IN activation implementation in this handler.

This establishes an unimplemented host-side action at this point, but does
not prove that macOS performs it here or that it is the sole cause: firmware
could handle part of it, and the selected USB4 target or crossbar setup may
also be wrong. An ACTIVATE acknowledgement alone proves no hardware state.
Do not restore the known-bad physical-PHY assignment as a substitute.

## Evidence needed for the next implementation

Capture a working macOS USB4 sink attachment on T6020 with firmware context:

1. DCP remote-port target and connect payload, power and HPD ordering.
2. Host actions between ACTIVATE request and reply, including the actual
   DP-IN initialization and clock/reset ownership.
3. Crossbar state and writes associated specifically with DP IN, distinguished
   from the physical ATC DP output and panel LPDPTX engine.
4. The first successful AUX/DPCD/EDID activity, link-rate/lane callbacks and
   firmware TimingElements delivery.

Compare the working trace with the same events in 0092. Only then map the
necessary operations to Linux lifecycle/ownership and review register writes.
Do not infer T602x meanings solely from similarly placed T8103 registers.

## Tracing feasibility, not a runnable setup instruction

Official m1n1 documentation lists macOS 13.5 and 14.8.3 targets and describes
using a separate macOS test installation with a host computer over USB. A
compatible macOS installation, host, cable and matching m1n1 build must be
checked before planning a capture. The current Linux firmware ABI is 13.5;
that does not tell us the installed macOS version.
https://asahilinux.org/docs/sw/m1n1-hypervisor/
https://asahilinux.org/docs/sw/m1n1-user-guide/

This setup can involve a separate macOS volume and boot/security changes;
none has been performed or authorized as part of the current test. Do not
run generic install/boot commands from this brief. A reviewed, machine-specific
plan and the user's decision are required before such changes.

The DCP tracer exists in official m1n1 at proxyclient/hv/trace_dcp.py. Its
ability to decode remote-port messages does not itself provide a known-good
USB4 trace. Prior notes referring to 2022 traces still lack the original
capture and its firmware/hardware context.

## Preserved artifacts

- captures/2026-09-21-hdmi-baseline-kernel.log
- captures/2026-09-21-direct-usbc-baseline-kernel.log
- captures/2026-09-21-0092-replug-kernel.log
- notes/2026-09-21-0092-result.md
- notes/ACTION-LOG.md and patches/0090 through 0092

0092 is running with its single attempt consumed; future-boot opt-in is
removed. No further hardware action is scheduled. Keep all recorded panel,
PHY, MMIO and hub-absent reboot restrictions in force.
