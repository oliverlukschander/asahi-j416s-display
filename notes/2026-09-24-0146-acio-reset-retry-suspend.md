# 0146: retry the ACIO reset handshake on resume-time contention

## Background: what's actually broken

After a genuine s2idle suspend/resume with the OWC hub connected
(left-back port), the hub never comes back. This is a *different*,
deeper bug than 0145's AUSPLL_LOCK race -- it's not the display tunnel
failing to light up, it's the Thunderbolt controller itself failing to
restart:

```
thunderbolt-apple-acio 701ac0000.cio: ACIO block failed to start: -110
```

`-110` is `-ETIMEDOUT`, from `reset_control_deassert(acio->reset)` in
`apple_cio_start()` (`drivers/thunderbolt/apple.c`). Confirmed via live
`journalctl`/`boltctl`/`dmesg` from tonight's actual incident (not
guessed):

```
20:27:35  systemd-logind: Lid closed.
20:27:35  thunderbolt-apple-acio: Gen2/3 link error / SBX disconnected / path teardown
20:27:36  kernel: PM: suspend entry (s2idle)                    <- the real suspend
20:27:37  apple-dcp: typec mux set typec0 ... usb4=0            <- cable driven off mid-resume
20:27:37  kernel: PM: suspend exit
20:27:37  kernel: PM: suspend entry (s2idle)                    <- systemd-sleep retrying
20:27:38  systemd-sleep: Failed to put system to sleep. System resumed again: Invalid argument
20:27:38  kernel: PM: suspend exit
   ... 6s quiet ...
20:27:44  systemd-logind: Lid opened.
20:27:44  apple-dcp: typec mux set typec0 ... usb4=1            <- cable re-enabled
20:27:44  thunderbolt-apple-acio: ACIO block failed to start: -110
```

The "double suspend" is `systemd-sleep` retrying after the kernel's
first `/sys/power/state` write returned `EINVAL` (its own log line says
so verbatim) -- a known systemd/kernel race, unrelated to this bug and
not caused by any omarchy/Hyprland lid-close script (checked
`omarchy-system-lid-close`, `omarchy-toggle-suspend`,
`logind.conf(.d)` -- none of them fire a second suspend).

## Root cause

`reset_control_deassert()` for this hardware (`t6000_cio_deassert()` in
`drivers/reset/reset-apple-cio.c`) is a request/ack handshake with the
M3/PMGR coprocessor firmware, not a self-clearing hardware flop: write
`INIT_REQ`, poll the shared `INIT_BUSY` bit for up to
`APPLE_CIO_RESET_TIMEOUT_US` = 100ms. **There is no `.assert` op at
all** ("a request to assert returns immediately on every SoC" per that
driver's own comment) -- once deassert fails, there is no way to
re-arm the reset controller in software short of an actual power
cycle.

Neither `apple_cio_driver` (the ACIO platform driver) nor
`reset-apple-cio.c` register any suspend/resume PM callbacks at all.
The only PM-aware code in this path is `apple_nhi_pm_ops`, bound to
the *dynamically-populated NHI child* device, and it only forwards
into software-level Thunderbolt-topology quiescing
(`tb_domain_suspend/resume_noirq`) -- nothing touches the M3 or the
reset controller.

`apple_cio_start()`/`apple_cio_stop()` are driven exclusively by
`apple_cio_tbt_switch_set()`, itself driven by the Type-C/PD
subsystem's own cable-state machine, whenever `target_cable_info !=
current_cable_info`. Per the live timeline above: the Type-C mux
itself drove the cable to `usb4=0` in the middle of the *first*
(genuine) resume, which runs `apple_cio_stop()` and, critically,
*removes* the `dev_pm_syscore_device()` protection that exists
specifically so genpd doesn't independently power-cycle the ACIO power
domains during system sleep. The second, redundant s2idle cycle
(systemd-sleep's retry) then puts those domains through an *ordinary*,
unprotected genpd sleep transition -- something this code path has
never been exercised against, since a cold boot only ever calls
`apple_cio_start()` once, long before any sleep cycle exists. Six
seconds later the cable comes back (`usb4=1`), triggering
`apple_cio_start()`'s reset handshake, which times out.

**This is a known, already-flagged upstream limitation, not something
this project broke**: aurora-silicon/linux#8 explicitly lists under
"Known limitations": *"Suspend with an active tunnel has not been
validated. Tunnels are released at suspend and set up again on
replug."* The original upstream Sven Peter USB4/Thunderbolt series is
separately on record as not supporting suspend with an active
connection at all (would hit an SError on resume upstream; this fork
times out instead).

## What this candidate does, and what it deliberately does NOT do

The obvious-looking fix -- give `apple_cio_driver` its own explicit
suspend/resume PM hooks that call `apple_cio_stop()`/`apple_cio_start()`
-- was considered and rejected for tonight. `apple_cio_tbt_switch_set()`
has its own explicit warning comment: an invalid direct transition
between two different non-zero `current_cable_info`/`target_cable_info`
states can crash the ACIO coprocessor and **trigger an SoC watchdog
reset a few seconds later**. Adding a second, independent code path
that also calls `apple_cio_stop()`/`apple_cio_start()` around the same
suspend/resume window -- sharing the same `acio->lock` and cable-info
state, but triggered by system PM rather than the Type-C mux -- risks
exactly that class of double-transition, for real hardware-reset
stakes. Confirming a PM-hook redesign is actually safe (rather than
just moving the same failure, or worse, colliding with the Type-C
mux's own independent decision) needs live register tracing this
project doesn't have set up, not something to attempt for the first
time at the end of a long session.

Instead: `apple_cio_start()`'s existing `reset_control_deassert()` call
now retries up to `APPLE_CIO_START_RETRIES` (5) times, `100ms` apart,
before giving up -- no new code path, no new suspend/resume hook, no
change to *when* or *whether* `apple_cio_start()` is called, only how
persistently it waits for the M3/PMGR firmware to answer once it is.
This directly tests the two possibilities the investigation could not
distinguish from code reading alone: if the coprocessor just needed
more time to answer during a resume where every other coprocessor on
the SoC is also coming back online at once, this fixes it outright; if
the block is genuinely wedged (needs a real power cycle, impossible in
software since `.assert` doesn't exist), a bounded retry fails exactly
the same way the single attempt does today -- strictly no worse than
the current baseline, and it tells us cleanly which case we're in.

## Build verification

`thunderbolt_apple.ko` rebuilt clean: zero errors, zero warnings.
Hash: `d0ec1d8fd2aeea333f1a50f4e09a62ab5095b8e2c9e1c6ed64933b97425df527`
(`thunderbolt.ko` unchanged from 0145:
`8978842bd5154c8fe2c63cb3705f1a47bbd629f44e392f2d48d4271b75ced9e3`)

## Test plan and risk

This changes real code in the Thunderbolt controller bring-up path,
tested against a scenario (suspend with an active USB4 tunnel) that
upstream itself has never validated. Oliver was explicit: this could
plausibly trigger the SoC watchdog reset described above, i.e. an
unexpected reboot, if some interaction wasn't caught by the reasoning
above -- **this whole document, plus everything below, is committed
and pushed to both repos before the module is installed, specifically
so the record survives if that happens.**

1. Install (module swap, no reboot).
2. Reboot with the hub connected on the left-back port, confirm the
   picture (regression check, same as every prior candidate).
3. Real test: lid close -> wait -> lid open, with the hub connected.
   Check `dmesg` for the retry log line
   (`ACIO block failed to start (attempt N/5): ..., retrying`) and
   whether it eventually succeeds, versus exhausting all 5 attempts.
4. If the machine reboots unexpectedly instead of resuming cleanly,
   that itself is the answer (retry alone doesn't touch it, or the
   watchdog-reset scenario triggered some other way) -- this document
   and the ACTION-LOG entry already describe exactly what was being
   attempted and why, so the next step doesn't start from zero.
