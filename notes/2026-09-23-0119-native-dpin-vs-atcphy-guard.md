# 0119: let native DPIN0 activation run with a real PHY attached

Direct continuation of 0118 after its first hardware test. 0118 flipped
GET_SUPPORTS_HPD to 0 as intended (confirmed in the log: `GET_SUPPORTS_HPD 0
usb4=1`), and request_display still returned 0 -- but the connection still
went straight to `DPRX timeout, keeping DP tunnel`, with the monitor still on
standby.

## What the log actually showed

```
DPTXPort: APCALL 18 (32 bytes)
DPTXPort: GET_SUPPORTS_HPD 0 usb4=1        <- 0118's fix #1, working
DPTXPort: APCALL 10 (32 bytes)
DPTXPort: APCALL 0 (16 bytes)              <- ACTIVATE
DPTXPort: APCALL 1 (16 bytes)              <- DEACTIVATE, immediately after
DPTXPort: DEACTIVATE
USB4: analog DPIN request_display core=1 atc=0: 0
```

Compare against every prior successful activation (0113 onward), which always
logged `thunderbolt-apple-acio ...: native DPIN0: active=1 ...` and
`apple-dcp ...: native DPIN0: DCP active=1 result=...` right after `APCALL 0`.
Those lines are completely absent here, and DCP sent DEACTIVATE within the
same log timestamp as ACTIVATE -- far too fast for a real hardware handshake
to have even attempted and failed; this is what a synchronous, immediate
-EINVAL from the ACTIVATE handler itself looks like.

## Root cause

`dptxport_native_dpin()` (dptxep.c:643, called from `dptxport_call_activate()`)
had its own guard, separate from and in addition to the one 0118's own design
note already knew about (`dcp_usb4_protocol_connect()`'s `if (dptx->atcphy)
return -EBUSY`, dcp.c:1473): `|| dptx->atcphy) return -EINVAL;` at the end of
its own precondition list (dptxep.c:657, pre-fix). 0118 attaches
`dcp->active_typec_route->phy` to `dptx->atcphy` in `dcp_dptx_connect()`
*before* request_display is even called -- so by the time DCP's incoming
ACTIVATE APCALL reaches this function, `dptx->atcphy` is already non-NULL,
and this guard rejects immediately, before ever calling
`apple_usb4_dpin0_set_active()` or touching the crossbar. `dptxport_call_activate()`
then reports the ACTIVATE reply as failed (`ret ? 1 : 0` with `ret == -EINVAL`),
and DCP -- seeing its own activation request declined -- immediately
deactivates, exactly as observed.

This is a second, previously-unnoticed instance of the exact same "native
DPIN0 activation and a real PHY are mutually exclusive" assumption that
0118's own design note already found and reasoned around once (in
`dcp_usb4_protocol_connect()`). The 4-agent workflow's investigation cited the
`dcp_usb4_protocol_connect()` guard specifically but did not surface this
second one inside `dptxport_native_dpin()` -- found only by reading tonight's
actual post-test log line-by-line and noticing the missing native-DPIN0 log
lines, then re-reading the function's full guard list.

## The fix (kernel commit 7e3fc1a)

Remove `|| dptx->atcphy` from `dptxport_native_dpin()`'s guard. Verified this
carries no double-configuration risk: everything below that guard
(`mux_control_select`/`mux_control_deselect` on `route->usb4_xbar`,
`apple_usb4_dpin0_set_active()` via `symbol_get`) operates on the crossbar and
ACIO -- a physically separate hardware block from `route->phy`'s own
SERDES/lane logic. Nothing in this function calls `phy_configure()`,
`phy_validate()`, or any other PHY-touching API, so there is nothing here to
race or conflict with 0118's earlier `phy_set_mode_ext()` call.

## Build verification

Only `dptxep.o` recompiled. New `appledrm.ko` SHA256:
`8713ea27613c61ab1c32936744327fdf1d7ee6d393aa37883a7c62977f9dac83`.
Stale-symlink sweep clean. `test-dpin-handshake.c`: 13/13 still pass. Patch:
`patches/0119-drm-apple-dptx-let-native-DPIN0-activation-run-with-.patch`.

## Test plan

Same as 0118's own test plan (single boot, `usb4_dptx_train`/`usb4_force_dptx`
untouched, shared eDP PHY never exercised). This time watch specifically for
the native DPIN0 activation lines to reappear (`native DPIN0: active=1 ...`,
`native DPIN0: DCP active=1 result=...`) alongside the already-working
GET_SUPPORTS_HPD=0/request_display=0 lines, confirming both mechanisms now
run together for the first time, before checking whether DCP proceeds to
SET_LINK_RATE/lane training this time.
