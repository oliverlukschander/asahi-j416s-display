# 0090 protocol audit after reconnect

External display remains unresolved. Oliver confirms eDP and the hub keyboard
work while the external display stays black. No hardware action was performed
during this audit; installed kernel/module and live display state were unchanged.

Kernel reviewed: a0df2ede847714b1de9fd2d0341cb1050c831df6.
Capture: captures/2026-09-21-0090-replug-firmware.log.

## Separate obstacles

1. Discovery still fails before link training and external TimingElements.
   Removing the repeated HPD prevents the previously observed DCPDPDevice
   start/timeout, not just the error message. It is not a functional fix.
2. The safe USB4 path suppresses IOMFB hotplug callbacks unconditionally:
   dcp_usb4_drm_allowed() returns usb4_force_dptx, which defaults false.
   The flag also controls entry into the dangerous physical-PHY training
   experiment. It must not be enabled to bypass the guard. The comment says
   to wait for real sink EDID, but this predicate contains no EDID check.
   This is a later obstacle to normal hotplug reporting, not evidence for
   the cause of missing firmware link training. Other connector-state writers
   exist (including res_is_main_display), so it is not a universal guarantee
   that every possible path keeps the connector disconnected.
3. The safe USB4 connect branch returns success even if validation/connect/
   request_display fails, does not mark dptxport.connected, and skips the
   normal branch's completion setup. These are lifecycle defects, but the
   current capture shows accepted RPCs. Fixing bookkeeping alone would not
   explain or repair the absent sink discovery.

## Reference comparison and limits

Read official AsahiLinux/m1n1 commit
4184923ffb2dff079b384d6a32cc02142aa14572, cloned to
/tmp/j416s-m1n1-reference. Relevant files:

- src/dcp/dptx_port_ep.h: remote target has CORE bits 3:0, DFP bits 7:4,
  DIE bits 11:8, CONNECTED bit 15. No defined DPIN bits 13:12.
- src/dcp/dptx_port_ep.c: connect request unknown field is zero; validation
  uses 0x100. Both expect response unknown field 0x100. Connect is followed
  by request_display; HPD is a separate entry point.
- proxyclient/hv/trace_dcp.py: target decoder likewise lacks DPIN bits.

These sources describe supported physical DPTX use, not a demonstrated T602x
USB4 connection. They neither validate our experimental target 0x9001 nor
prove its extra bit is wrong. Do not clear that bit or change the connection
sequence on this evidence alone. Prior notes' reference to 2022 USB4 traces
needs the actual trace and hardware/firmware context before being relied on.

Reference:
https://github.com/AsahiLinux/m1n1/tree/4184923ffb2dff079b384d6a32cc02142aa14572

## Next evidence needed

A known-working T602x USB4 DCP/DP-IN initialization trace or documented
equivalent is needed to justify the next hardware-changing candidate. Compare
remote target, request payloads, power/HPD ordering and crossbar selection
before considering any new experiment. Preserve the existing tunnel and
panel restrictions. Do not replay the prohibited post-request HPD experiment,
enable usb4_force_dptx, inject panel timings, or guess clock registers.

Once genuine sink discovery works, replace the coupled hotplug/PHY guard
with a separately reviewed per-output readiness condition backed by that
sink's data, and repair connect/disconnect bookkeeping. Merely seeing
nr_modes > 0 is insufficient protection against the previously observed
panel-mode cloning.

No new kernel candidate or reboot is justified by this audit alone. The SDDM
startup gate installed earlier still awaits validation on a future necessary
boot; it is not yet a proven cure for the internal-display startup failure.
