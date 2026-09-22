# Native macOS DP-bandwidth comparison — 2026-09-22

Four reports collected on the M2 (Mac14,10, macOS26.5.1 build25F80),
hub on the RIGHT USB-C port, transferred via the M4 Desktop. Oliver
identifies them in order: 152852 monitor connected/active, 152908
disconnected, 152917 during plug-in, 152923 connected again (active).
Video worked in all connected states, as always on real macOS.

## DCP-firmware bandwidth-ratio check looks healthy, and Linux already
## feeds it the same inputs

`log-thunderbolt-dp.txt` (all four; the5-minute rolling window overlaps
between captures taken seconds apart, so presence alone doesn't
distinguish connected/disconnected) shows:

```
(DCP0) AppleDCPDPTXController::getBandwidthRatio videoBandwidth=25011120000bps
       linkBandwidth=25574400000bps bandwidthRatio=0.9779
(DCP0) AppleDCPDPTXController::updateBandwidthRatio BW_RATIO=0x7d2e
```

`(DCP0)` marks this as a log line from the DCP coprocessor's own firmware
(the same signed blob Linux drives via RTKit RPC), not host-side kext code.
This looks like an internal admission check comparing the mode's required
bandwidth against the negotiated link bandwidth, well under1.0 here. Linux
already sends the DCP the same link-rate/lane-count/mode RPCs that would
feed this same firmware-internal computation (SET_LINK_RATE0xa,
SET_ACTIVE_LANE_COUNT4, and a completed set_digital_out_mode for
2560x1440@59.951, all already present in every0102-0108 capture), so
there is no evidence Linux drives this computation any differently. The
existing Linux `dcpep_cb_allocate_bandwidth` RPC callback (drivers/gpu/drm/
apple/iomfb_template.c) already unconditionally approves (`ret=1`) for
every display type including this one; it is generic, not DP-tunnel
specific, and already exercised successfully by the working eDP/HDMI/
direct-USB-C paths. This is a healthy sign, not a new lead.

## IOThunderboltPort exposes its own bandwidth accounting on the DP OUT
## adapter — mechanism not yet understood well enough to act on

`ioreg-IOThunderboltPort.plist` (152852,152923; absent/zero in the
disconnected/mid-plug-in captures) shows, on the hub's DP OUT adapter
(port19, "DP or HDMI Adapter", the same port already identified from the
Linux side in0106/0107):

```
Link Bandwidth: 1200
Maximum Bandwidth Allocated: 1
Required Bandwidth Allocated: 1
```

These go from absent/zero (disconnected) to present and nonzero exactly
when video is working, which is suggestive. But this is Apple's own
IOThunderboltFamily.kext-level connection-manager bookkeeping (small
integer values, not raw bps), not a value we have tooling to decode with
confidence: it may be the same USB4-spec granularity-quantized
allocated-bandwidth concept0108 already implements (in which case it is
consistent with, not contradictory to, that change), or it may be an
entirely different Apple-internal accounting unrelated to the on-wire
register. Deciding which would require reverse-engineering
IOThunderboltFamily.kext itself -- a different, undissected XNU kernel
extension, not the DCP coprocessor firmware this project already has
disassembly tooling for. That is a materially larger new undertaking than
anything done in this investigation so far, not a small follow-up.

## Conclusion

This comparison validates that Linux's DP-related DCP RPC sequence
(link rate,lane count,mode) matches what native macOS relies on for the
same firmware-internal bandwidth check, and is consistent with (does not
contradict)0108's bandwidth-allocation-mode fix. It does not reveal an
obvious missing register write translatable into a safe, well-understood
kernel patch. Going further on this specific thread requires either new
XNU kext reverse-engineering tooling, or a different empirical angle.

Raw reports (contain hardware IDs) remain outside Git in
/home/oliver/.local/share/j416s-display/macos-captures/j416s-dp-bandwidth-*.
No module load,parameter change,MMIO mapping/access,cable manipulation or
Linux reboot was performed for this analysis.
