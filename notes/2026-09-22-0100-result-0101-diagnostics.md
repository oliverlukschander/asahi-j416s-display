# 0100 result; 0101 identifies the existing-clock conflict

Boot db25bd04-ac78-4144-96ad-344a8b49757d, right port confirmed by
f01f00000.nhi/f01ac0000.cio/f03000000.phy journal. User reports no picture.
eDP-1 remains active3456x2160@120. External DRM connectors disconnected,
encoder97 has no CRTC. Keyboard functionality not checked.

At245.171077s DCP315c00000 requests SET_LINK_RATE0xa. At245.171363s
ATC tunnel callback returns-16(-EBUSY), propagated to DCP. No earlier
clock call in this boot. Thus atc_tunnel_start refused one of the three
preflight conditions before setting tunnel_attempted/saving state or
performing any new0100 clock write:

- core+7000: PCLK1/PCLK2/DPRX enable bits13/14/15;
- core+2200: PLL output-enable mask0x54;
- core+2000: APB command request bit0.

The active-rate-conflict branch cannot be the first callback. The mode
check cannot account for this line: its return precedes the PHY result
log. Which register caused the refusal is not logged in0100.

Native DPIN0 activate handshake succeeds245.118125s, DPRX_DONE1 at
245.216328s. This confirms AUX negotiation, not video success. There is
no completed external frame or after-frame snapshot; no fresh crossbar
+800 conclusion can be made. Unlike0099, rate success is not falsely
cached when the new clock operation fails. The earlier working-frame
stage is not reached. This is a blocked clock attempt, not evidence the
native PLL sequence failed after programming.

Read-only review of DT firmware tunable tuples finds no explicit entries
for7000,2200,2000. Current source has a legacy USB4 gate helper, but the
capture contains no "USB4 DPTX clocks on" invocation. These checks do
not establish actual runtime ownership or justify bypassing the guards.

## 0101 ready, not installed

Add log lines for the existing preflight reads, preserving their exact
order, conditions and early returns. The last logged register identifies
the refusal. Log active-rate conflicts too. No additional MMIO read,
write, mapping, register-mask or guard change. Candidate retains all0100
restrictions and one-attempt behavior. A reboot is needed to load it;
no live replacement/unload of the active ATC/display stack.

PHY SHA256794b47de6e3b1faab8da51532ca1e264da0cb8eb9513188e2a5ff5ae0b4d86b4.
Other three module hashes unchanged from0100. Installermanage-0101.py
has distinct config and nine-file backup. Hashes/target existence/helper
parity verified. PHY builds; existing missing-pahole warning only.
RAM helper tests still pass with logging stubbed; checkpatch0errors0warnings.
Kernel commit exported as patch0101. No raw captures committed.

Current hub remains connected; future boots already disarmed with image
SHA25648dcece31ad466e13e8a3faba0ac4c4929dbe5d2ccd59ce10a9085cbae21e7ca.
Next: logged hub unplug before any install/reboot. Do not force past the
busy guard, issue live register probes, or repeatedly hotplug this build.
