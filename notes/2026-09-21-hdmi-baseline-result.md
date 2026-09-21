# Direct HDMI works alongside eDP

Oliver confirms the monitor works directly. The logged capture confirms:

- eDP-1: 3456x2160 at 120 Hz, active.
- HDMI-A-1: BenQ LCD, 2560x1440 at 59.951 Hz, active.
- Keychron Q4 remains enumerated through the hub (key events not sampled).
- Running module remains 0090. No reboot, install or parameter write.

Successful firmware sequence on dcpext0 0x289c00000:

| Uptime (s) | Event |
| --- | --- |
| 1413.720 | validate/connect target 0x8030, connect unknown field 0 |
| 1413.721 | GET_SUPPORTS_HPD=0, GET_MAX_LANE_COUNT, ACTIVATE |
| 1414.411 | SET_LINK_RATE=0x1e |
| 1414.423 | SET_ACTIVE_LANE_COUNT=4 |
| 1414.596 | TimingElements accepted, nr_modes=22 |
| 1414.597 | connected hotplug callback, DRM notification |
| 1414.612 | Linux selects color 83 / timing 45, 2560x1440 |
| 1414.840 | modeset completes |

This same external DCP had no timings and transitioned to run mode 0 while
disconnected at boot. Discovery subsequently supplied timings before Linux
selected a mode. Therefore a prior firmware timing ID is not a general
prerequisite for external discovery. The original no-timing/run-mode theory
is not supported by this working counterexample. HDMI success does not prove
that the separate USB4 route or its remote target is correctly initialized.

Next diagnostic separation: test the VMM7100 directly on a free USB-C port,
keeping the hub and keyboard on their current port. This uses ordinary DP
alt mode on the separate port, not on the hub's USB4 port. It is not a claim
of success through the hub. Exact physical action is logged separately.
