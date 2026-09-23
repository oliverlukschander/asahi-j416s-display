# 0125: re-test dpin_aux=1 live, now that everything upstream of it is confirmed clean

Direct continuation of 0124. No kernel source change, no rebuild -- this is a
single runtime module-parameter write, done live against the tunnel that is
already up from the current boot.

## Why re-test something already marked ineffective

Candidates 0054-0056 (notes/2026-09-21-acio-rc-dpin-analog.md) found that
writing `dpin_aux=1` "does not stick" -- direct MMIO pokes to the ACIO DP IN
analog block did not survive readback. That finding predates almost
everything this project has since fixed: crossbar routing sequencing, the
native DPIN0 ACIO wake handshake, the Thunderbolt DP IN role bit, and (as of
0124) confirmation that every AFK/DCP protocol call up through ACTIVATE now
succeeds cleanly with zero errors. It is possible the 0054-0056 "doesn't
stick" result was itself a symptom of one of those since-fixed problems
(e.g. the crossbar not actually being selected onto the right path yet, or
the PHY not being in the state `apple_dp_start_analog()` expects), not
evidence that this mechanism is fundamentally incapable of driving DPRX.
Oliver asked to re-test given that possibility, rather than assume the old
characterization still holds.

## What the write actually does

`dpin_aux` (`drivers/thunderbolt/apple.c`) is `module_param_cb` with mode
0644 (runtime-writable) and a custom setter, `apple_dpin_aux_set()`:

```c
static int apple_dpin_aux_set(const char *val, const struct kernel_param *kp)
{
	...
	apple_dpin_aux = v;
	anhi = READ_ONCE(apple_dpin_anhi);
	if (v >= 1 && anhi)
		apple_dp_start_analog(anhi, true);
	return 0;
}
```

`apple_dpin_anhi` is set by `apple_nhi_dp_tunnel_post_activate()` when the DP
tunnel comes up and cleared by `apple_nhi_dp_tunnel_deactivate()` when it goes
down. The 0124 boot log shows `Apple: DPRX timeout, keeping DP tunnel` (not
"tunnel down"), and a read-only check just now confirms the hub (`0-1`) is
still enumerated on the Thunderbolt bus. So the tunnel from this exact boot
should still be up and `apple_dpin_anhi` still set -- meaning writing
`dpin_aux=1` now should immediately call `apple_dp_start_analog(anhi, true)`
against the live, already-activated tunnel, no unplug/replug or reboot
required.

## The exact action

```
cat /sys/module/thunderbolt_apple/parameters/dpin_aux   # confirm current value (0), read-only
echo 1 | sudo tee /sys/module/thunderbolt_apple/parameters/dpin_aux
```

This is classified as a hardware action per this log's own header (writes a
module parameter). It is fully reversible: `echo 0 | sudo tee ...` restores
the hands-off default, and per `apple_nhi_dp_tunnel_deactivate()`, an unplug
already clears `dp_aux_armed`/`apple_dpin_anhi` independent of this value.
No kernel module is reloaded, no other module parameter changes, nothing
else about the current boot's state is touched.

## What to watch for

After the write:
1. `dmesg`/`journalctl -k` for any new "DP IN analog" / ACIO RC dump lines
   from `apple_dp_start_analog()`/`apple_dp_aux_work()` (the delayed-work poll
   loop logs "DP IN CS changed ..." whenever the adapter's capability
   registers change, including `DPRX=1` if it ever asserts).
2. Whether DCP itself reacts -- a fresh `SET_ACTIVE_LANE_COUNT`/
   `SET_LINK_RATE`/`WILL_CHANGE_LINK_CONFIG` apcall appearing that didn't
   during the original boot sequence would mean DCP was, in fact, waiting on
   exactly this signal.
3. The monitor itself -- Oliver watching for any picture, even a brief
   flicker, immediately after the write.
4. If nothing happens within ~15s, write `dpin_aux=0` to restore the
   documented-safe default and note the result -- this does not disprove the
   idea if the tunnel has already been sitting past its DPRX timeout for too
   long (its own state machine may need a fresh activation, i.e. an
   unplug/replug, to accept a late AUX start). That would be the next,
   separate candidate if this live attempt is inconclusive rather than a
   clean negative.

## Blast radius / rollback

Confirmed by 0054-0056's own history and by `apple_nhi_dp_tunnel_deactivate()`
existing specifically to undo this state on unplug: this is a narrow,
single-purpose, already-shipped-and-tested-safe knob (the original concern
was "ineffective", never "destabilizes the hub" the way candidate 0120's
`apple_atc_usb4_enable_dp_aux()` did). Worst case is no change in behavior.
If anything else on the hub is affected (unlikely, given 0120's actual
"shares the PLL" mechanism doesn't apply here -- this touches ACIO's DP IN
analog block, not AUSPLL), the fallback is `dpin_aux=0` followed by a full
unplug/replug or reboot to fully reset state.
