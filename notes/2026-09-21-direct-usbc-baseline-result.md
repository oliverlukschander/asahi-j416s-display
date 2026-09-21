# Direct VMM7100 works on the right USB-C port

Oliver reports the USB-C adapter works directly and subsequently reports
disconnecting it again. The successful capture was taken before that
disconnect, using the commands logged in ACTION-LOG.md.

Hyprland showed eDP-1 active at 3456x2160@120 and USB-3 active at
2560x1440@59.951, identified as BenQ LCD. The VMM7100 was enumerated at
USB 3-1 and the Keychron Q4 through the hub at 1-1.3. No key events were
sampled. Installed module remained 0090, with no reboot or driver reload.

The physical right port is typec2, crossbar 0xf0304c000. It borrowed
dcpext0 0x289c00000 because the left-side USB4 route held dcpext1
0x315c00000. Do not misreport this as a successful direct test of dcpext1.

Observed sequence:

- 1583.718: right DPPHY crossbar selects dispext0,0; PHY 2 allocated.
- 1584.406: connect dcpext0, borrowed Type-C route, target 0x8020.
- 1584.407: connect payload unknown field 0x100.
- 1584.408: GET_SUPPORTS_HPD=1, usb4=0.
- 1584.461: SET_LINK_RATE=0x1e.
- 1584.474: SET_ACTIVE_LANE_COUNT=4.
- 1584.678: TimingElements accepted, 22 modes.
- 1584.680: firmware connected hotplug callback.

The code for this successful physical-DP path performs connect,
request_display, then set_hpd. The USB4 experimental path does set_hpd
before request_display. This difference remains relevant, but replaying the
old post-request HPD alone is not a new fix: it previously started a device
that timed out. It remains prohibited by the prior notes.

At initial successful DPPHY crossbar selection, the driver logged
0x000=1 and 0x800=0. This was before training; it is not a measurement of
0x800 during active scanout. It does show that zero immediately after mux
selection is not sufficient to declare the connection doomed. No additional
register read was performed to obtain this observation.

The direct test verifies the cable, adapter and monitor under Linux as well
as physical DP discovery on dcpext0. Together with Oliver's confirmation
that the entire hub chain works in macOS, this localizes remaining work to
Linux's USB4-specific routing/firmware discovery and potentially its chosen
dcpext1. It does not validate the experimental 0x9001 target, analog mux
definitions, or dcpext1's complete operation.

The capture also includes intervening physical disconnect/reconnect events
before the final direct connection, including transient USB4 selection on
the right port. These are observed events, not actions issued by the agent.
Do not infer that the hub remained continuously attached throughout all
physical moves merely because the final capture shows it attached.

Remaining evidence gap: a known-working USB4 initialization sequence on
this SoC/firmware. Direct DP success does not establish the USB4 target or
analog routing. No additional hardware experiment was run after this test.
