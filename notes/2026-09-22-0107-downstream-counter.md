# 0107: instrument the downstream hop too

0106 established that the DP video path's DP-IN hop counter (host route0-0
port5) goes nonzero (0x421b) after a full link/frame sequence identical to
0105, while the monitor still shows no picture. That is new evidence traffic
leaves the crossbar/DP IN adapter into the tunnel; it says nothing about
whether that traffic reaches the far end. See notes/2026-09-22-0106-result.md.

## The change

Same gate, same mechanism, one more hop. `tb_dp_init_video_path()` already
sets `in_counter_index=0` on the video path's first hop (DP-IN side) when
`dp_video_counter=1` and the restrictive predicate matches (Apple NHI,
apple,j416s, right-hand USB-C port, DP IN adapter). 0107 additionally sets
`in_counter_index=0` on the path's LAST hop -- the downstream router's
ingress side of the same path (concretely, the hub's upstream link-in port,
not the DP OUT adapter itself: DP OUT is always this path's terminal
out_port, never an in_port, so it has no hop counter of its own in this
model). Both assignments go through the same unmodified
`tb_path_activate()` code that already safely programs a hop's
counter/counter_enable bits; nothing else about routing, credits, priority
or weight changes on either hop.

## Readback and interpretation

Same three files as0106, now all informative:

- `/sys/kernel/debug/thunderbolt/0-0/port5/counters` (DP IN, already
  established nonzero in0106)
- `/sys/kernel/debug/thunderbolt/0-1/port19/counters` -- still not directly
  instrumented (DP OUT has no ingress hop of its own, see above); reading it
  remains uninformative and is kept only for context, as in0106.
- the hub's own upstream-port counters file (path/port to be confirmed from
  this attempt's kernel log -- the exact port number on the route0-1 switch
  that is the video path's last hop `in_port`; capture the log first, then
  read that port's `counters`)

If the downstream hop's counter is zero despite a nonzero DP-IN counter: new
evidence traffic is lost somewhere between the host's egress and the hub's
ingress -- in the tunnel/link itself. If nonzero: traffic is crossing into
the hub, and the fault is further downstream still (the hub's internal
routing to DP OUT, the DP OUT adapter's own programming, or the physical
VMM7100/HDMI chain) -- a different, more localized next question than
anything asked so far.

## Validation

`make` in src/thunderbolt rebuilds only thunderbolt.o/thunderbolt.ko; the
other four modules are unchanged (verified by SHA256, matching0106 exactly).
checkpatch on the full accumulated tunnel.c diff:0errors/0warnings. No live
hardware test performed during development. Candidate hashes:

```
thunderbolt (core) ebbd7a80568be7422d403bc6d05a5d0a577dbf24d4f939c359e0561f69255906
thunderbolt_apple  26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
appledrm           9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3 (unchanged)
```

`scripts/manage-0107.py` is manage-0106.py with only the candidate hash and
0106->0107 paths/config changed (diffed to confirm); same eleven-file
backup/verify discipline, same carried-over0105 options plus
`dp_video_counter=1`.
