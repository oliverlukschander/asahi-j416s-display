# 0115: make the native DPIN0 path work on any Type-C port

Triggered by a real, immediate need: Oliver is now at a different
location where only the left port is physically usable, and the
entire native DPIN0 mechanism built this project turned out to be
hardcoded to the right port only. This candidate removes that
limitation properly rather than working around it.

## What was actually wrong

Every prior candidate (0093-0114) only ever worked with the hub in the
right USB-C port, because five separate call sites across four
drivers each independently hardcoded the right port's specific
physical addresses or index, left over from when this was explicitly
scoped as a single-port proof of concept:

1. `drivers/thunderbolt/apple.c`,
   `apple_usb4_right_dpin0_set_active()`: hardcoded the DPIN0 MMIO
   resource (`0xf01e50000`) and the devicetree lookup path
   (`/soc/cio@f01ac0000`).
2. `drivers/gpu/drm/apple/dcp.c`, `dcp_usb4_native_route()`: required
   `typec_index == 2` exactly.
3. `drivers/mux/apple-display-crossbar.c`: three separate checks
   (`apple_dpxbar_right_frame_snapshot`,
   `apple_dpxbar_right_dpin0_bring_up`, and the crossbar probe's
   `defer_dpin0_bringup` flag) all required the crossbar's MMIO
   resource to start at `0xf0304c000` exactly.
4. `drivers/phy/apple/atc.c`,
   `apple_atc_right_usb4_tunnel_rate()`: required the ATC PHY core
   resource to start at `0xf03000000` exactly -- and this one matters
   in practice, since `usb4_tunnel_clock` is enabled in every
   candidate's options.

None of this was a hardware limitation -- it was never generalized
because the whole project's testing setup only ever used the right
port. Confirmed against this exact machine's own device tree
(`/sys/firmware/devicetree/base/aliases/usb4-<N>-acio` and
`atcphy<N>`): j416s has one ACIO/USB4 controller and one ATC PHY core
per Type-C port, at addresses that differ only in a top-nibble prefix:

| typec_index | ACIO | ATC PHY | Crossbar (inferred, same pattern) |
|---|---|---|---|
| 0 (left) | `0x701ac0000` | `0x703000000` | `0x70304c000` |
| 1 (left) | `0xb01ac0000` | `0xb03000000` | `0xb0304c000` |
| 2 (right) | `0xf01ac0000` | `0xf03000000` | `0xf0304c000` (confirmed all session) |

## The fix

All five call sites now compute or accept the correct per-port address
dynamically instead of a single hardcoded right-port constant:

- `apple_usb4_right_dpin0_set_active()` renamed to
  `apple_usb4_dpin0_set_active(typec_index, active)`; a new
  `apple_usb4_typec_acio_base()` helper maps `typec_index` to the
  correct ACIO base, and the DPIN0 resource and devicetree path are
  both derived from it. The stale cable-info address guard is
  generalized the same way.
- `dcp_usb4_native_route()` now accepts any `typec_index <= 2` (every
  port with a real ACIO instance) instead of `== 2` only.
- `dptxep.c`'s `symbol_get()` call site updated to match the rename and
  pass `route->typec_index` through -- this is what makes the port
  selection automatic: whichever port the DCP route-selection logic
  (already port-generic, since direct connections already worked on
  any port) picks becomes the `typec_index` threaded through to the
  native DPIN0 activation, with no new module parameter needed.
- The three crossbar checks and the ATC PHY check now accept any of
  the three known per-port addresses via small shared helpers
  (`apple_dpxbar_is_typec_crossbar()`, `apple_atc_is_typec_core()`).

## What was deliberately left alone

`dcp_usb4_protocol_connect()` -- a separate, one-shot experimental
probe path (predating this session, module param `usb4_protocol_probe`,
which is enabled in every candidate's options) -- uses its own `atc`
target-address field, computed as `usb4_native_dpin ? 2 : 0`. This
value's actual relationship to `typec_index` for ports other than the
right one is not established (unlike the four fixes above, which are a
confirmed, regular, device-tree-verified per-port pattern): tellingly,
the main native-DPIN0 path's own default `atc` value (via the
`usb4_atc` module param, unset in every candidate so far) is `0`, not
`2`, even though it targets the same right port successfully --
meaning "atc" is not simply an alias for `typec_index`, and guessing at
its generalization risked sending a subtly wrong target address to DCP
for no established benefit.

`dcp_dptx_connect()` unconditionally returns whatever this probe
returns, which would have permanently blocked every other port from
ever reaching the (now-fixed) native DPIN0 path below it. Rather than
touch the probe's own encoding, the call site was scoped to only
invoke it when `route->typec_index == 2`, exactly preserving existing
right-port behavior; any other port now falls straight through to the
fully-generalized native DPIN0 path.

Function, parameter, and log-string names still say "right" in several
places (`apple_dpxbar_right_dpin0_bring_up`,
`apple_dpxbar_right_frame_snapshot`,
`apple_atc_right_usb4_tunnel_rate`, the `usb4_tunnel_clock`
`MODULE_PARM_DESC` strings, etc.). Only the address-comparison logic
needed to change for correctness; renaming these is a separate,
lower-priority cleanup left for later.

## Also fixed: a second stale-symlink build bug

`src/mux/apple-display-crossbar.c` and `src/phy/atc.c` in the display
project's symlink farm turned out to be stale plain file copies, not
symlinks into the kernel tree -- the exact same class of bug found and
fixed for `apple-dpin-handshake.h` earlier in this project (new files
this project added to the kernel tree, missed when the original
symlink farm was set up). Edits to both files were being silently
ignored by `make` until a suspicious zero-rebuild during this exact
change caught it. Fixed the same way: removed the stale copies,
symlinked them properly. Worth checking for a third time this doesn't
recur: `find src -type f -name '*.c' -o -name '*.h' | xargs -I{} sh -c
'test -L "{}" || echo NOT SYMLINK: {}'` (excluding intentionally-local
files like test harnesses).

## Follow-up found while checking for more stale symlinks (deferred, not fixed today)

Running the same check across the whole `src/` tree (excluding
`*.mod.c` build artifacts, which are expected to not be symlinks)
found two more non-symlinked files, both pre-existing and unrelated to
today's change:

- `src/phy/dptx.c`/`dptx.h`: real divergence from the kernel tree, not
  just a missed symlink. The display-repo copy of `dptx.c` contains an
  entire extra feature (an `assign_only` module param/code path) that
  does not exist anywhere in the current `linux-aurora-pr` tree at all,
  and `dptx.h`'s copy is textually old enough to predate its current
  upstream attribution header. This could be orphaned prior work,
  intentionally superseded work, or a genuine regression -- not
  established today, deliberately left untouched pending a real
  investigation of that file's history rather than guessing.
- `src/dispclk/apple-dispclk.c`: no corresponding file exists anywhere
  in the kernel tree (`find` for any `*dispclk*` path returns nothing)
  -- this is a standalone file with nothing to symlink to, not simply a
  missed link like the other two fixed today.

Neither is touched by 0115 and neither affects the port-generalization
change. Flagging here so a future session doesn't have to rediscover
this.

## Validation

`make` in each affected directory (`src/thunderbolt`, `src/appledrm`,
`src/mux`, `src/phy`) rebuilds exactly the expected object files.
`scripts/test-dpin-handshake.c` re-run (13 scenarios, ASan/UBSan) to
confirm `apple-dpin-handshake.h`'s own logic, untouched today, still
passes. New hashes, all four changed as expected:

```
appledrm           a9476d34ed835b9c94a72aa310992f8c82419ae42376484e4e1eb42d9a995f30 (changed: dcp.c, dptxep.c)
thunderbolt_apple  7d20ca29a9589aa5e6b6903d77e094d149e9a2131f7103a4ba44ccfa2955ecd2 (changed: apple.c)
mux                0abc55f24b93afb3ef4b6cf042cf517e9654bfcd8c3d53e7663cd0a36fd2fead (changed: apple-display-crossbar.c)
atc                fb748d4ba55e467dad4eaca6f4045059200aea46eccbd8a1bd2165025a95cf7f (changed: atc.c)
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7 (unchanged)
```

No new module option is needed: the port is now auto-detected from
`route->typec_index` at runtime rather than fixed by a module
parameter, so the exact same `OPTIONS` string arms either port.

## Safety scope

No new register, address range, or mechanism beyond what's already
been exercised safely all project -- this candidate only makes the
existing, already-tested logic apply its per-port address correctly
instead of a single hardcoded one. Includes 0114's resend-
request_display change unmodified underneath.
