# 0145: the "doesn't reactivate after standby/replug" bug -- found and fixed

## What actually happened tonight

After 0144 was confirmed working (0143's cleanup plus the
tunnel_attempted one-shot fix), Oliver moved the OWC hub from the
right-back USB-C port to the left-back one and connected the BenQ
through it. This is a different physical route than everything else
tonight targeted (right-back's NHI `0xf01f00000` vs left-back's
`0x701f00000`, a different ATC PHY instance entirely: `f03000000.phy`
vs `703000000.phy`). The monitor stayed dark.

Live `dmesg` showed a completely different symptom from anything found
earlier tonight: not a single silent stuck-at-0x0 (the Aquamarine
commit-path bug), but a continuous retrain loop --
`DPTXPort: SET_LINK_RATE 0xa` immediately followed by `SET_LINK_RATE
0x0`, repeating every ~6-7 seconds, for minutes on end. The detailed
sequence around one cycle:

```
phy-apple-atc 703000000.phy: USB4 tunnel clock preflight: +7000=0000e001 +2200=00002000 +2000=10000000 +7044=00000008
phy-apple-atc 703000000.phy: DP tunnel clock: rate=0xa result=-16
apple-dcp 289c00000.dcp: DP tunnel pixel clock (rate 0xa) failed: -16
apple-dcp 289c00000.dcp: no DP tunnel pixel clock, crossbar left down
```

`result=-16` is `-EBUSY`. `+7044=00000008` is `ACIOPHY_DP_PCLK_STAT`
reading `ACIOPHY_AUSPLL_LOCK` (`BIT(3)`) still set.

## Root cause

`atc_tunnel_start()`'s preflight (added in the original tunnel-clock
commit, candidate work from earlier this project) refuses with
`-EBUSY` while `ACIOPHY_AUSPLL_LOCK` reads set, specifically to avoid
clobbering a PLL some other client has genuinely locked. Sound
guard -- but `atc_tunnel_restore()`, which tears the PLL back down on
disconnect/re-link, never waited for that same lock bit to actually
clear. It just wrote the restore registers and returned immediately.

DCP firmware retries a failed tunnel clock request roughly once a
second. On the right-back port earlier tonight, that was slower than
the PLL's real unlock settling time, so every replug test happened to
see a clean `status=0`. On the left-back port's PHY instance, the
retry landed inside that settling window every single time, so the
preflight perpetually saw its own just-torn-down lock as "still busy"
and refused itself -- forever, until the cable was physically removed.

This is very likely the actual mechanism behind "doesn't reactivate
after standby" too: standby/wake and a live replug both go through the
same disconnect -> reconnect -> `atc_tunnel_restore()` ->
`atc_tunnel_start()` sequence: if the reconnect attempt (or DCP's own
retry) lands soon enough after the teardown, it hits this exact race
regardless of what triggered the reconnect.

## The fix

`atc_tunnel_restore()` now polls for `ACIOPHY_AUSPLL_LOCK` to clear
(10us interval, 10ms timeout, the same convention already used by
`atc_tunnel_command()` elsewhere in this file) before returning,
logging a `dev_warn()` if it somehow doesn't clear in time rather than
hanging forever. A request landing right after `atc_tunnel_restore()`
returns now sees a genuinely idle PLL instead of racing its own
teardown.

## Build verification

`phy-apple-atc.ko` rebuilt clean: zero errors, zero warnings.
Hash: `5525c3e7c66fc8f882084fa53741b36aebbf5ec5b00f5d348893108cd2d92b73`

## Test plan

1. Install (module swap only, no reboot).
2. Reboot with the hub connected to the left-back port as it is now.
3. Confirm the picture comes up (regression check -- same as every
   prior candidate).
4. The actual test for this fix: unplug and replug the hub on the
   left-back port a few times in quick succession (faster than the
   ~6-7s retrain interval that was failing before), and confirm via
   `dmesg` that `DP tunnel clock: rate=... result=` never shows a
   nonzero result, and no `SET_LINK_RATE 0xa`/`0x0` retrain loop
   appears.
5. If real hardware confirms this, also fast-forward the standby
   hypothesis: try an actual suspend/resume cycle with the monitor
   connected, since this fix targets exactly the teardown/retry race
   that would also occur on wake.
