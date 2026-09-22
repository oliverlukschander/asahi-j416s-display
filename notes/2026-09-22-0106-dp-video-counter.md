# 0106: instrument the DP video path instead of guessing at ordering again

0105 confirmed the deferred-gate ordering ran (route select at030 with gates
off, PLL/nativeup/4-lane/DPRX/mode/frame all report success at175s), but the
user confirmed no picture and034 still reads0 afterward. That is the fourth
consecutive candidate (0102-0105) where every software/firmware success
indicator is met and the monitor stays dark. Repeating another deferred-enable
timing tweak is not justified by any new evidence; see
notes/2026-09-22-0105-result.md follow-up.

The open question stated in the working brief: DCP/crossbar -> DP IN -> USB4
tunnel -> DP OUT -> adapter. Frame completion and DPRX_DONE do not establish
that boundary. 0104 already noted `in_counter_index` is-1 in the existing
debugfs path-counter mechanism, so reading it proves nothing without first
enabling it.

## What is actually available

Offline decode of the already-captured, already-logged private register dumps
from 0104 (captures/2026-09-22-0104-dpin-regs.txt,-dpout-regs.txt; no new
hardware read performed for this) shows both ends of the tunnel support
standard USB4 per-hop packet counters:

- Host DP IN, route0 port5: TB_CFG_PORT DWORD1=0x00080209 ->
  first_cap_offset=9 (matches the already-known DP capability base),
  max_counters=2, counters_support=1.
- Hub DP OUT-side, route1 port19: DWORD1=0x0008020a -> counters_support=1,
  max_counters=2.

Linux's generic `tb_path_activate()` (drivers/thunderbolt/path.c) already
clears and enables a hop's counter whenever
`path->hops[i].in_counter_index != -1`; it programs only the existing
`counter`/`counter_enable` bits in TB_CFG_HOPS dword1, the same write it
already performs for every other tunnel type that uses a counter.
`tb_dp_init_video_path()` (drivers/thunderbolt/tunnel.c) just always leaves it
at-1 for DP tunnels. No new register-poking code is required: only setting
the index.

## The change

New read-only module parameter on the core `thunderbolt` module,
`dp_video_counter` (default false). When true, `tb_dp_init_video_path()`
assigns `in_counter_index=0` on the DP video path's first hop, but only if
all of the following hold (same restrictive predicate style as prior
candidates):

- that hop's `in_port` is a DP IN adapter (`tb_port_is_dpin`)
- the NHI is an Apple NHI (`tb_nhi_is_apple`)
- the machine is `apple,j416s`
- the port is the right-hand USB-C NHI (`tb_apple_nhi_typec_index()==2`,
  matching the `f01f` NHI name substring already used elsewhere in this file)

This only ever changes the `counter`/`counter_enable` bits of that one hop's
existing TB_CFG_HOPS dword1. It does not touch `nfc_credits`/
`initial_credits` (hop credits, explicitly out of scope), routing
(`next_hop`/`out_port`/`enable`), priority/weight, or any ACIO analog/panel
register, and it adds no new ioremap or MMIO path of its own -- it only opts
an already-existing generic code path into a feature this exact hardware
already advertises supporting. Gated off by default; no behavior change
unless `dp_video_counter=1` is set.

## Readback

The existing, already-in-tree debugfs files
`/sys/kernel/debug/thunderbolt/0-0/port5/counters` and
`/sys/kernel/debug/thunderbolt/<hub-route>/port19/counters` (same
`tb_port_read`-mediated mechanism already used for the 0104 regs dumps) read
counter index0 after the right-port attach. Interpretation:

- DP-IN counter stays0 despite a completed frame: new evidence the fault is
  upstream of the tunnel (crossbar/DCP not actually emitting video packets
  despite reporting success) -- redirects focus back to034/crossbar internals.
- DP-IN counter is nonzero: new evidence DP IN is emitting correctly and the
  fault is downstream (tunnel programming, DP OUT adapter, or the physical
  VMM7100/HDMI chain) -- an entirely different next investigation branch.

Only one counter (DP IN side) is enabled in this candidate to keep the diff
and the test minimal; a second checkpoint at the hub-side hop was considered
and deferred rather than combined into this same change.

## Validation

`make` in src/thunderbolt rebuilds only `thunderbolt.o`/`thunderbolt.ko`
(tunnel.c is the only file touched); `thunderbolt_apple.ko`, mux, atc and
appledrm are byte-identical to what is already installed from0105 (verified
by SHA256, not just assumed). checkpatch on the diff:0 errors,0 warnings.
No live hardware test performed during development. Candidate hashes:

```
thunderbolt (core) a70debca0d7fd8a53d8807358a6db922049f321ed24b8a6415ebf4f75b3a8898
thunderbolt_apple  26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198 (unchanged)
mux                38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24 (unchanged)
atc                e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9 (unchanged)
appledrm           9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3 (unchanged)
```

`scripts/manage-0106.py` backs up all five module pairs plus the initramfs
(eleven files total, `/var/tmp/j416s-0106-before`), installs the pinned set,
and keeps the 0105 options (`usb4_protocol_probe`, `usb4_native_dpin`,
`usb4_tunnel_clock`, `dpin_native`, `usb4_defer_bringup`) active alongside the
new `dp_video_counter=1`, so this test replicates the exact 0105 sequencing
already characterized in notes and only adds the counter on top -- it does
not reopen the ordering question.
