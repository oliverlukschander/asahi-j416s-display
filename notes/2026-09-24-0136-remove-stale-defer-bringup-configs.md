# 0136: remove 10 stale pre-0127 modprobe.d configs forcing usb4_defer_bringup=1

## What prior candidates found

0135's deep-research workflow (10 agents: 6 independent investigation
angles, 1 synthesis, 3 adversarial verifiers) conclusively separated two
previously-tangled mysteries:

1. **dcpext1 (the Type-C-only pipeline, `315c00000.dcp`) goes silent for
   ~5s after accepting `request_display`, then times out.** All ten agents
   converged, and I independently re-verified their key citations myself:
   no driver-source asymmetry exists anywhere in the connect path (dcp.c,
   dptxep.c, afk.c) between dcpext0 and dcpext1 — the driver-issued connect
   parameters (`target=0x8021 core=1 atc=2 die=0 attrs=0x101`) are
   byte-identical. The clean, 100%-consistent fingerprint across all 10
   available boot captures (0127-0135): a firmware-initiated EPIC service,
   `DCPDP13Service`/`AFK[ep:28]`, gets announced by DCP firmware immediately
   after every dcpext0-hosted `request_display`, and never once after a
   dcpext1-hosted one. This is a firmware-internal decision, not something
   this driver's source can currently control or fix. Left as an open,
   unsolved question — not addressed by this candidate.

2. **`DP tunnel crossbar up failed: -22` (EINVAL), hit by both 0127 (left
   port) and 0135 (right port), both times with dcpext0 hosting the
   tunnel.** This candidate identifies and fixes the actual cause, and it
   is not a code bug at all.

## Root cause (verified directly, not inferred)

`dcp_tunnel_crossbar_up()` (`drivers/gpu/drm/apple/dcp.c:458`) calls
`mux_control_try_select(route->active_xbar, route->mux_index)`, where
`route->active_xbar` is the connecting port's own crossbar's `dpin0`/`dpin1`
leg and `route->mux_index` is read straight from the hosting DCP's
`apple,typec-mux-indices` devicetree property (dcpext0 = 0, dcpext1 = 2 —
each DCP's own "dispext" self-identity, established and ruled out as a bug
in 0135's writeup).

`apple_dpxbar_set_t602x()` (`drivers/mux/apple-display-crossbar.c:211`)
has:
```c
bool deferred = dpxbar->defer_dpin0_bringup && index == MUX_DPIN0;
...
if (deferred && enable && state != 2)
    return -EINVAL;
```
`dpxbar->defer_dpin0_bringup` is set at probe time
(`apple_dpxbar_probe()`, line 722) from the module parameter
`usb4_defer_bringup` (declared in the same file, for an earlier "native
DPIN0" experiment, still present/exported for that experiment's own
diagnostic entry points). When true, it makes the crossbar refuse to
select *anything but* state 2 (dcpext1) on a Type-C port's dpin0 leg — by
design, for that now-discontinued experiment, which only ever expected
dcpext1 to be the one selecting it.

Traced the actual value of that parameter on the machine actually used for
0127-0135: it was never explicitly set by any of the 0127-0135 candidate
configs. But `usb4_defer_bringup` is `0444` (boot-parameter only, combined
across every `options mux_apple_display_crossbar ...` line modprobe finds),
and ten leftover conf files from the discontinued pre-0127 "native DPIN0"
experiment (dated 2026-09-23, candidates 0113/0115/0116/0118/0119/0121/
0122/0123/0124/0126 — all byte-identical,
`sha256:104e761e...c41b2e`) are still sitting in `/etc/modprobe.d/` and
were never removed when the project moved on to the current dcp.c-based
tunnel work on 2026-09-24. I extracted the actual initramfs used for the
0135 boot (`lsinitcpio -x /boot/initramfs-linux-aurora.img`) and confirmed
directly: all ten stale files are baked in alongside 0135's own conf, and
one of them sets `options mux_apple_display_crossbar usb4_defer_bringup=1`
— so every boot since 0127 has silently loaded the crossbar module with
that flag on, without any 0127-0135 candidate script ever touching it
(each only manages its own numbered conf file).

This fully and specifically explains the observed `-22`: forcing dcpext0
(`route->mux_index = 0`) onto either port's dpin0 leg while
`defer_dpin0_bringup` is (unintentionally) true always fails the
`state != 2` check, on both the left port (0127) and the right port
(0135) — a single root cause for both prior "successes-that-still-failed",
and unrelated to dcpext1's own separate firmware-silence problem (dcpext1's
own `mux_index = 2` always satisfies `state != 2` as false, so it was never
affected by this).

## The change

No kernel code changes. Remove the ten stale, superseded conf files
(after verifying their content matches the known-stale checksum, so this
can't accidentally delete something else), rebuild the initramfs, and
verify the resulting image contains 0135's own options
(`usb4_route_prefer_fixed_diag=1` still armed, so the tunnel continues to
be forced onto dcpext0 — the only pipeline that has ever reached
`DPRX_DONE=1`) with no `usb4_defer_bringup` string anywhere. Backed up
(sha256-verified) to `/var/tmp/j416s-0136-stale-confs-before/` first, fully
reversible via `restore`/`disarm`.

`scripts/manage-0136.py` — `check` (already run, no sudo needed, confirms
preconditions) / `install` (backs up + removes the 10 files + rebuilds +
verifies) / `disarm` / `restore` (both put the 10 files back + rebuild).

## Build verification

Ran `python3 scripts/manage-0136.py check` (no sudo): confirms the running
kernel/machine, confirms 0135's own conf is still in place, confirms all
ten stale files are present with the expected checksum. No `install` run
yet — needs `sudo`, must be requested from Oliver per the standing
protocol.

## Known uncertainty

Fixing this `-22` does not guarantee a full picture. It only removes one
specific, now-understood obstacle from the dcpext0-forced-tunnel path.
What happens after the crossbar select actually succeeds (whether the
tunnel clock stays up long enough, whether the earlier "no DP tunnel pixel
clock, crossbar left down" warning at the later `WillChangeLinkConfig`
recurs, whether DPRX_DONE=1 is reached again and this time holds) is
unknown until tested. This is a real, verified bug fix, not a guaranteed
final answer.

## Test plan

1. Ask Oliver to run `sudo -n python3 scripts/manage-0136.py check` then
   `sudo -n python3 scripts/manage-0136.py install`.
2. Ask Oliver to reboot with the hub/monitor connected exactly as before
   (right port, through the OWC hub + Synaptics adapter).
3. Pull `dmesg --ctime`, save as
   `captures/2026-09-24-0136-boot-kernel.log`, check specifically: does
   `apple-display-crossbar f0304c000.mux: Switched dpin0 to dispext0,0`
   (an ENABLE, not "disconnected") now appear, does "DP tunnel crossbar up
   failed" disappear, and — the real goal — is there a picture on the
   external display. Only Oliver's own visual confirmation counts as
   success.
