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

## First attempt: regression, reverted

Installed and tested (lid-close/s2idle/lid-open, hub never touched).
Result: worse than 0146 alone. The ACIO reset handshake exhausted all
5 of 0146's retry attempts and failed completely
(`ACIO block failed to start: -110`, repeated `CIO 0 still busy before
reconfigure request`), whereas 0146 alone succeeds on the first
attempt with zero retries. Reverted via `manage-0147.py restore`,
verified against the pre-install backup. Full writeup in
`notes/ACTION-LOG.md`.

At the time, the log also showed `typec mux set typec0 ... usb4=0`
immediately followed by `usb4=1`, apparently firing microseconds after
`PM: suspend exit` -- too fast to be this fix's own 500ms-debounced
`cd321x_resume_reverify()`. This looked like it might be an
independent second trigger contending for the same M3/PMGR firmware,
but that was never confirmed and turned out to be the wrong framing.

## Corrected root cause: reconnect fires too early, not a second trigger

`cd321x_typec_update_mode()` (the function that ultimately calls
`apple_cio_tbt_switch_set()`) has exactly one call site in the entire
file: inside `cd321x_update_work()`, the same debounced work item both
a real replug and this fix's `cd321x_resume_reverify()` go through.
There is no other, independent path into it -- confirmed by grep, no
second trigger exists.

`PM: suspend exit` is printed at the very tail of the *entire*
suspend/resume transaction, from `suspend_finish()`, strictly after
every device (ACIO, thunderbolt, DCP, the crossbar) has already run
its own `.resume()`. `tipd_resume()`, by contrast, is just one
individual device's `.resume()` callback -- there's no guarantee it
runs anywhere near that tail point, and this driver's device (I2C,
comparatively simple) plausibly resumes well before ACIO/thunderbolt's
own, more involved resume work finishes settling.

The original fix called `cd321x_resume_reverify()` directly from
`tipd_resume()`. That schedules the debounced work ~500ms after
*this device's own* resume runs -- which can easily land while
ACIO/thunderbolt's resume work (and the shared M3/PMGR firmware behind
`apple_cio_start()`'s reset-deassert handshake) is still in progress,
well before the rest of the system, and `PM: suspend exit`, has
actually settled. A real physical replug never hits this, because a
human always does it seconds after the whole system has visibly come
back -- long after any such contention would have cleared on its own.
So the "microseconds after `PM: suspend exit`" observation wasn't a
mystery second trigger -- it was this fix's own reconnect, coincidentally
finishing around the same wall-clock moment as the late-printed
`PM: suspend exit` line, while still overlapping the tail of the
system's broader resume work.

## Corrected fix: trigger from PM_POST_SUSPEND, not tipd_resume()

`register_pm_notifier()`/`PM_POST_SUSPEND` is delivered strictly after
`dpm_resume_end()` -- i.e. after every device in the system, including
ACIO/thunderbolt, has completed its own ordinary resume. Moving the
trigger there removes the race entirely, without any arbitrary added
delay: `cd321x_resume_reverify()` itself is unchanged, only *when* it
gets called changes.

`drivers/usb/typec/tipd/tps6598x.h`: added `struct notifier_block pm_nb;`
to `struct tps6598x`.

`drivers/usb/typec/tipd/core.c`:
- `tipd_resume()`: removed the direct `resume_reverify()` call.
- New `tipd_pm_notify()`, registered via `register_pm_notifier()` at
  the end of `tipd_init()` and unregistered in `tipd_remove()`, gated
  the same way as before (only when `tps->data->resume_reverify` is
  non-NULL, i.e. only the two Apple-specific vtables) -- calls
  `tps->data->resume_reverify(tps)` on `PM_POST_SUSPEND`.

Same watchdog-reset safety argument as before still holds unchanged:
the synthetic disconnect always drives through zero first. Nothing
about *what* the fix does changed, only *when* it's allowed to run.

## Build verification (corrected version)

Clean rebuild from scratch: zero errors, zero warnings (aside from the
pre-existing, unrelated `pahole` version-mismatch notice seen on every
module in this project).
Hash: `c0a9cfe7257141052479cd3365780cb0520df32a8672d95c62aa7bc659bf0b48`

## Updated test plan

Same as before -- install, reboot-with-hub regression check, then the
real lid-close/s2idle/lid-open test with the hub never touched. This
time also watch specifically for zero ACIO start retries (matching the
0146-only baseline), not just whether the picture comes back, since
that retry count is exactly the signal the first attempt got wrong.

## v2's own bug: struct ABI mismatch across separately-built modules, caused a real hang

The v2 install (PM_POST_SUSPEND notifier) was tested with a cold boot,
hub connected. Result: the machine genuinely hung -- required holding
the power button multiple times to recover, not just a slow boot.
Confirmed via `journalctl -b -1`: the external/hub-side DCP
(`289c00000.dcp`) never ran its Thunderbolt DP tunnel connect sequence
at all (compare to the confirmed-good 0146 baseline boot, where that
same sequence completes in under 300ms), and the whole boot stalled
~19s waiting on deferred probes/genpd sync tied to the CIO devices
before the shutdown.

Root cause: `struct notifier_block pm_nb;` was added to `struct
tps6598x` in the *shared* header `tps6598x.h`, right before the `data`
vtable pointer. Only `tps6598x-core.ko` (core.c + trace.c) was rebuilt
and reinstalled. The I2C and SPMI bus-glue drivers (`i2c.c`/`spmi.c`)
also include this header and are built into their **own, separately
loaded** kernel modules (`tps6598x.ko`, `sn201202x.ko`) -- those were
never rebuilt, so their compiled code still wrote `tps->data` at the
*old* byte offset while the freshly-built core module read it from the
*new*, shifted offset. That desyncs the vtable pointer every
operation on the chip goes through (`connect()`, `read_data_status()`,
etc.) -- exactly the kind of corruption that can silently misbehave or
hang depending on what ends up at that offset. A field added to a
struct in a header shared across independently-loaded modules requires
rebuilding *every* module that includes it, not just the one whose
`.c` file changed.

**Fix**: extended `src/typec/Makefile` to also build `tps6598x.o`
(from `i2c.c`) and `sn201202x.o` (from `spmi.c`) as separate module
targets in the same directory, matching upstream's own module
boundaries (`drivers/usb/typec/tipd/Makefile`) and the pattern already
used by this project's `thunderbolt`/`phy` module dirs (multiple
`obj-m` targets sharing one directory). All three typec modules are
now rebuilt together from the same header on every change, and
`manage-0147.py` now checks/installs/restores all three as one unit
instead of just `tps6598x-core.ko`.

## Separate, unrelated incident found during recovery: the module tree itself was wiped

While investigating the hang, found `/usr/lib/modules/7.1.12-2.5-1-ARCH`
did not exist at all -- renamed to `/usr/lib/modules/.old` and then
emptied by a stock tmpfiles rule (`R! /usr/lib/modules/.old/* - - -
4w`, which unconditionally removes on every boot regardless of the age
field) during the fallback boot. This is unrelated to the code change
above -- `linux-aurora` was never registered with pacman (`pacman -Q
linux-aurora` returns not found), by original design
(`install-aurora-second-entry.sh` explicitly avoids `pacman -U`
because the package Conflicts with `linux-asahi`), which is exactly
what let the system's kernel-management tooling treat it as an
orphaned, unowned directory and prune it.

Recovered by: verifying the archived package
(`pkg/linux-aurora-7.1.12.aurora2.5-1-aarch64.pkg.tar.xz`) against its
recorded SHA256SUMS and GPG signature (good signature, matches the
Omarchy ARM Repository signing key), extracting it fresh as the
pristine base, then rebuilding and reinstalling every custom-touched
module family (appledrm, mux, thunderbolt + thunderbolt_apple,
phy-apple-atc, and now all three typec modules) from the current
`linux-aurora-pr` git HEAD (`db7b1c019`) into both the `kernel/...` and
`updates/...` locations, followed by `depmod` and `mkinitcpio -p
linux-aurora`. Verified the rebuilt initramfs's module hashes match the
live tree exactly, and that `/boot/vmlinuz-linux-aurora`,
`/boot/grub/custom.cfg`, and the `linux-asahi` boot files were all
untouched throughout. Full detail in `notes/ACTION-LOG.md`.

**Not a recurrence risk for pacman**: this doesn't fix *why* the
directory was orphaned (it's still not pacman-registered, by design,
same as before) -- if the same tmpfiles-driven cleanup mechanism
triggers again after another `.old`-renaming event, this could repeat.
Worth a follow-up outside this session's scope: either register the
package properly under a non-conflicting name, or find and neutralize
whatever renames the aurora module directory to `.old` in the first
place.

## Confirmed on hardware: the kernel-side fix works

Real test after the recovery above (reboot into `linux-aurora`, hub
connected, cold boot succeeded cleanly -- tunnel auto-connected in
~4s, zero ACIO retries, `boltctl` authorized). Then the actual test:
lid close -> s2idle -> lid open, hub never touched.

`dmesg` showed the full automatic chain working exactly as designed:
`PM: suspend exit` -> ~1s later `cd321x_resume_reverify()`'s synthetic
disconnect/reconnect (`typec mux set typec0 ... usb4=0` immediately
followed by `usb4=1`) -> `dcp_dptx_connect()` -> tunnel clock preflight
-> `set_digital_out_mode` all completing successfully, **zero ACIO
start retries** (matching the 0146-only baseline). Oliver confirmed
the picture came back on its own, no replug needed -- this candidate's
actual goal.

**Separate finding, not a regression here**: the picture went black
again a short time later. Checked every layer at that point: DRM
connector `card2-USB-1: connected`, `boltctl` still authorized, no
further kernel-level tunnel/DCP errors, and `hyprctl monitors` showed
Hyprland's own object for `USB-1` as fully healthy (`disabled: false`,
`dpmsStatus: 1`, correct mode/position). Every layer below the
compositor's actual frame output reported correct state. A physical
unplug/replug (no suspend/resume involved) brought the picture back
*immediately* -- this is the exact signature of the already-documented
Aquamarine async-commit-queue bug from earlier in this project (fails
to complete a real, non-test atomic commit on a live hotplug), not a
new problem in this fix. That bug was already investigated and
explicitly set aside as out of scope before 0147 was ever started; a
risky live-instrumentation attempt to root-cause it further was
already tried and abandoned earlier in this project.

**Net result**: 0147's kernel/driver-side auto-recovery is confirmed
correct and working. On this specific compositor (Aquamarine/
Hyprland, as currently built), the end-to-end user-visible outcome
still needs one of: a physical replug, a DPMS toggle, or an eventual
upstream Aquamarine fix, until that separate bug is fixed. On any
compositor without that specific bug -- or once it's fixed -- this
kernel fix makes the recovery fully seamless with no replug at all.
