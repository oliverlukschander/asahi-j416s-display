# 0147: auto-recover the display after standby, no replug needed

## Where this picks up

0145 fixed the AUSPLL_LOCK retry loop. 0146 fixed the ACIO/Thunderbolt
controller itself failing to restart after suspend (confirmed on
hardware: a full lid-close/s2idle/lid-open cycle now succeeds, zero
`ACIO block failed to start` failures, `boltctl` shows a genuine
40Gb/s authorized connection afterward).

But even with both fixes, the *display* didn't come back on its own --
a physical unplug/replug of the hub was still needed. This candidate
targets that last piece.

## Root cause

Live kernel log at resume, hub never physically removed:

```
thunderbolt-apple-acio: dpin0: inactive handshake=0
apple-display-crossbar: dpin0: crossbar link down (dispext=0 atc=0x1)
apple-dcp: DPTXPort: SET_LINK_RATE 0x0
thunderbolt-apple-nhi: DP IN tunnel routing: tunnel down
apple-display-crossbar: Switched dpin0 to disconnected state
```

Nothing after this re-established the tunnel. Traced the actual call
chain (`drivers/usb/typec/tipd/core.c`, `drivers/thunderbolt/apple.c`,
`drivers/thunderbolt/tb.c`, `drivers/thunderbolt/tunnel.c`) end to end:

- A physical cable attach/detach is what drives
  `apple_cio_start()`/`apple_cio_stop()` (which bring up/tear down the
  M3 RTKit, ACIO PHY, and the NHI child device that owns the actual
  tunnel) -- via `apple_cio_tbt_switch_set()`, itself driven by the
  Type-C PD controller (CD321x/`tipd`) chip's own attach detection:
  `cd321x_interrupt()` -> debounced `cd321x_update_work()` ->
  `cd321x_typec_update_mode()` -> `typec_thunderbolt_switch_set()` ->
  `apple_cio_tbt_switch_set()`.
- `tipd_resume()` (the PD controller driver's own resume hook) never
  re-verifies the port's actual attach/mode state at all -- confirmed
  by reading it in full. It checks firmware is alive, re-arms the IRQ,
  restarts polling if IRQ-less. Nothing more. It never calls
  `tps->data->connect()` or anything that reaches
  `cd321x_typec_update_mode()`.
- Separately, at the thunderbolt-core level: `tb_resume_noirq()` runs
  in the noirq resume phase, before any device's ordinary `.resume`,
  and calls `tb_free_invalid_tunnels()`, which destroys any tunnel
  whose downstream link no longer validates -- which the hub's own
  link training does not survive a real system sleep, even though the
  *host* side (ACIO/M3) is deliberately kept powered throughout
  (`dev_pm_syscore_device(..., true)`, explicit comment: "must not
  independently cycle them during system sleep"). This is what
  produces the "tunnel down" log lines above, and it is generic
  thunderbolt-core behavior, not a bug by itself. Its own
  tunnel-recreation loop only re-activates tunnels still in its list --
  the just-invalidated one isn't, so nothing there brings it back
  either.

So: the cable was never physically removed, so the PD controller's own
cached attach state never changes, so `tipd`'s edge-triggered IRQ
handling never fires again on resume, so nothing ever re-drives
`apple_cio_tbt_switch_set()` -- even though the tunnel underneath it
was silently torn down. **A physical replug works purely because it
generates a genuine hardware attach event that re-drives this whole
chain from scratch; nothing today reproduces that on resume.**

A naive "just re-verify and re-assert the same state" fix would
actually be a no-op: `apple_cio_tbt_switch_set()`'s very first check is
`if (acio->target_cable_info == acio->current_cable_info) return 0;`,
and `current_cable_info` is untouched by anything in the resume path
(confirmed by grep -- it's only ever written inside
`apple_cio_start()`/`apple_cio_stop()` themselves). Re-detecting the
*same, unchanged* cable would compute the *same* target and hit that
early return immediately.

## The fix

`drivers/usb/typec/tipd/core.c`: added `cd321x_resume_reverify()`,
called from `tipd_resume()` if a chip-specific hook is registered.
Rather than inventing new logic, it reproduces a genuine
unplug-then-replug entirely through the already-existing, already-
hardware-validated code path: reads the real current port status, and
if a cable is present, calls the existing `.connect()` callback
(`cd321x_connect()`) **twice** -- once with the real status but
`TPS_STATUS_PLUG_PRESENT` cleared (a synthetic disconnect), then again
with the real, unmodified status. Both updates land on the same
500ms-debounced work item (`cd321x_update_work()`), which coalesces
them into a single run with `was_disconnected=true` and the correct
final connected state -- exactly the same code path, same
`typec_thunderbolt_switch_set()` OFF-then-back-on sequence, and same
`apple_cio_tbt_switch_set()` guard a real replug already exercises
every time someone does it by hand tonight.

Wired only into the two CD321x/Apple-specific vtables
(`tipd_cd321x_data`, `tipd_sn201202x_data`) via a new optional
`resume_reverify` hook on `struct tipd_data` -- the plain TI
TPS6598x/TPS25750 chip variants (non-Apple hardware, used elsewhere by
this same upstream driver) get a `NULL` hook and are completely
unaffected.

## Why this stays clear of the watchdog-reset landmine

`apple_cio_tbt_switch_set()` warns explicitly: a direct transition
between two different *nonzero* cable-info states (no shutdown in
between) can crash ACIO and trigger an SoC watchdog reset. This fix
never does that -- the synthetic disconnect call always drives
`target_cable_info` to 0 first (going through `apple_cio_stop()`,
which properly zeroes `current_cable_info` and releases the NHI child)
before the second call asserts a nonzero target again. This is the
exact same "clean start from zero" shape the guard already treats as
safe, because it's the *same mechanism* a real unplug/replug uses --
not a new one.

## What's NOT changed

No new suspend/resume PM hook on `apple_cio_driver` itself (the more
invasive option considered and rejected for 0146, for the same
watchdog-reset reasoning) -- this only adds a resume-time re-verify
inside the PD controller driver, which then drives the *existing*,
unchanged `apple_cio_tbt_switch_set()`/`apple_cio_start()`/`apple_cio_stop()`
chain the exact way a real cable event already does.

## Residual risk, flagged rather than hidden

`apple_cio_stop()` destroys the NHI child platform device
(`of_platform_device_destroy()`) and `apple_cio_start()` recreates it.
That's the same thing that happens on every real replug tonight, so
it's not a *new* risk -- but the timing here is different (fired from
inside a debounced work item during ordinary resume, not from a live
IRQ during normal operation), and that specific timing hasn't been
exercised on this hardware before. This needs an actual
lid-close/s2idle/lid-open hardware test before being trusted, the same
way 0145 and 0146 were.

## Build verification

New module directory `src/typec/` (only `tps6598x-core.ko` needs
rebuilding -- the I2C/SPMI bus-glue modules, `tps6598x.ko`/
`sn201202x.ko`, are unchanged since only `core.c` was touched).
Rebuilt clean from scratch: zero errors, zero warnings.
Hash: `25a843beba6585d18c6a8af6f3a73ea862ec1d99ddb1f91a5606bf05302f5669`

## Test plan

1. Install (module swap, no reboot).
2. Reboot with the hub connected, confirm the picture (regression
   check).
3. Real test: lid close -> wait -> lid open, hub never touched. Watch
   `dmesg` for the same chain a real replug produces (`DP IN tunnel
   routing`, `USB4 tunnel clock preflight`, `set_digital_out_mode`) --
   this time without any physical replug at all.
