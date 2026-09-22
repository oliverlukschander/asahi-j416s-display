# 0108: the DP tunnel has never been granted nonzero bandwidth

0106/0107 established (via a real hardware packet counter, not a status
flag) that video traffic leaves the crossbar/DP IN adapter and reaches the
hub-side hop that forwards directly to the DP OUT adapter. Combined with
0104's DP OUT CS registers already showing 4 lanes/HBR negotiated and DPRX
done, and the fact this exact hub+adapter+monitor combination is confirmed
working under macOS, the crossbar/DCP/USB4-tunnel path built across
0102-0107 is no longer a credible explanation for the missing picture. See
notes/2026-09-22-0107-result.md, "Not yet checked".

## What was found, purely offline

`usb4_dp_port_bandwidth_mode_supported()` (drivers/thunderbolt/usb4.c)
checks bit28 (`DP_COMMON_CAP_BW_MODE`) of the DP IN adapter's `DP_LOCAL_CAP`
field. In every already-captured dump (0104, 0107), the host DP IN
adapter's `LOCAL` field has that bit set (e.g.`LOCAL=15402334`), so
`tb_dp_pre_activate()` always takes the bandwidth-allocation-mode branch
for this tunnel -- this has been happening on every single attempt since
0093, unnoticed until now.

`tb_dp_bandwidth_alloc_mode_enable()` then does, per the USB4 spec: set
group/CM id, compute non-reduced bandwidth, set granularity, set the
*estimated* bandwidth (`tunnel->max_down`/`max_up`, already reserved by the
connection manager), and finally call
`usb4_dp_port_allocate_bandwidth(in, 0)` -- explicitly granting *zero*
bandwidth as the spec-mandated starting point. The design assumes the DP IN
adapter will subsequently raise it itself via a hardware "bandwidth
request" notification, which is handled reactively in
`tb_handle_dp_bandwidth_request()` (drivers/thunderbolt/tb.c), itself only
invoked from the generic USB4 control-channel notification-packet path
(`tb_handle_notification()`).

Decoding the DP IN adapter's own `DP_STATUS` field (offset0x06, "STAT" in
the existing apple.c dumps; bits31:24 are `DP_STATUS_ALLOCATED_BW`) in
every already-captured right-port attempt (0104, 0107) shows it at
`STAT=00000000` -- allocated bandwidth0, exactly matching what the code
above does and never observed to change. Nothing in apple.c (extensively
read across this whole investigation) generates or forwards a bandwidth
request notification for the Apple ACIO NHI; it is plausible this
proprietary host controller never raises USB4 CFG_ERROR-style notification
packets the way the generic Linux CM code expects. If the hub's DP OUT
firmware honestly refuses to drive its physical output while0 Mb/s is
allocated -- a spec-compliant, conservative interpretation, and consistent
with AUX/control traffic (not bandwidth-metered the same way) still
flowing while isochronous video does not -- that fully explains every
observation so far: real packets in the tunnel, full link/frame negotiation
success, and no picture.

## The change

Default-off module parameter `dp_bw_grant`, gated by the same
`tb_dp_is_apple_j416s_right_dpin()` predicate now shared with
`dp_video_counter` (refactored out of `tb_dp_video_counter_wanted`, no
behavior change there). When enabled, `tb_dp_bandwidth_alloc_mode_enable()`
grants `min(non_reduced_bw, estimated_bw)` immediately instead of0:
`non_reduced_bw` is the bandwidth the function already computes from the
negotiated rate/lanes (the same number logged as "non-reduced bandwidth");
`estimated_bw` is `tunnel->max_down`/`max_up`, i.e. exactly what the
connection manager already reserved for this tunnel before it was ever
created. The grant can therefore never exceed a budget that was already
admitted, so this cannot oversubscribe the fabric or affect any other
tunnel. No other DP adapter on any other system is affected -- the
predicate requires this exact machine, NHI vendor, and right-hand port.

This does not touch DP IN hop credits (`nfc_credits`/`initial_credits`,
untouched, out of scope per longstanding instruction), routing, the ACIO
analog block, or any panel register. It writes exactly one field
(`DP_STATUS` allocated-bandwidth) on the DP IN adapter, through the
existing, unmodified `usb4_dp_port_allocate_bandwidth()` helper that the
driver already calls at this exact point for every DP tunnel -- only the
value passed changes, and only for this one route.

## Validation

`make` in src/thunderbolt rebuilds only thunderbolt.o/thunderbolt.ko; the
other four modules are unchanged (verified by SHA256, matching0107).
checkpatch on the full accumulated tunnel.c diff:0errors/0warnings. No live
hardware test performed during development. Candidate hashes:

```
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7
thunderbolt_apple  26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
appledrm           9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3 (unchanged)
```

`scripts/manage-0108.py` follows the same eleven-file backup/verify
discipline as0106/0107, keeps the0105 option set plus
`dp_video_counter=1` (kept enabled for continued observability -- if this
works, both counters should also show nonzero traffic that finally
reaches the monitor; if it does not, the counters remain available to see
whether traffic patterns change at all) and adds `dp_bw_grant=1`.

## If this does not restore the picture

This does not "fix" anything blindly -- it removes one concretely-observed
difference from what a spec-compliant, request-capable DP IN adapter would
do. If the monitor is still dark with a confirmed nonzero allocated
bandwidth, that is new evidence the fault is genuinely inside the hub's own
DP-alt-mode output stage or the physical VMM7100 link, entirely outside
what the Linux host driver can observe or control from here -- a materially
different conclusion than "we have not tried enough software", and worth
being candid about rather than continuing to guess.
