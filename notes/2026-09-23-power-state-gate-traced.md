# Full trace: swap completion is gated by an internal power-state transition

This closes the loop opened by 2026-09-23-run-mode-4-permanently-stuck.md,
using a working decompiler set up specifically for this investigation
(see "Decompiler infrastructure" below). All addresses/decompiled code
below are from `/tmp/dcp-fw2/t602xdcp.bin`, SHA256
`f3d919d62979408b5643a0f1e07df3a17e734dc5666ee27a873766a3adb35430`
(same firmware extracted and verified earlier this session).

## The full chain, in real decompiled C

1. `IOMobileFramebuffer::swap_submit_dcp` (vmaddr `0x723b4`) only hands
   out a new swap slot once the previous transaction's `completed` field
   is set; otherwise it silently drops the swap via the
   `IOMFB_SWAP_SUBMIT_LOST` path (see the prior note).

2. The function that marks a transaction complete and notifies the AP,
   `batched_swap_complete_ap_gated` (`FUN_00078ae0`, Ghidra address
   `0x78ae0`), is only ever *registered* -- not just called -- inside
   `FUN_000788d0`, and only when three conditions all hold:
   ```c
   void FUN_000788d0(long *param_1)
   {
     uVar3 = (uint)DAT_0062d975;
     *(uint *)((long)param_1 + 0x38dc) = uVar3;
     if (*(char *)((long)param_1 + 0x3902) != '\0') {      // per-pipe flag
       if (uVar3 != 0) {                                    // <-- the gate
         ...
         iVar1 = (**(code **)(*param_1 + 0x340))(param_1);  // vtable check
         if (iVar1 != 0) {
           ...
           (**(code **)(*(long *)param_1[0x4ed] + 0x68))
                     (..., FUN_00078ae0, param_1, 0, 0, 0);  // <-- registration
           ...
         }
       }
       else {
         /* uVar3 == 0: takes a completely different, non-batched path
            and never registers the completion callback at all */
       }
     }
   }
   ```
   `DAT_0062d975` is the load-bearing one: a global, not per-pipe.

3. `DAT_0062d975` is set/cleared by exactly one function,
   `FUN_0005d2b0`, and by nothing else:
   ```c
   void FUN_0005d2b0(undefined8 param_1,int param_2,int param_3)
   {
     if ((param_2 == 0x21) && (param_3 == 8)) {
       DAT_0062d975 = '\0';                 // 0x21 -> 8: clear
     } else {
       if (param_2 != 8) return;
       if (param_3 != 0x21) return;
       DAT_0062d975 = '\x01';               // 8 -> 0x21: set
     }
     ...
   }
   ```
   This is a state-transition handler: entering state `0x21` from state
   `8` sets the gate true; the reverse transition clears it. The
   argument shape (`old_state, new_state`) and the two-endpoint
   enable/disable pairing is the classic signature of an IOKit-style
   numbered power-state transition callback.

4. `FUN_0005d2b0`'s address is registered (not called directly -- found
   via `PARAM`-type cross-references, consistent with the same
   "install this as a callback" pattern as step 2) inside
   `FUN_00129574`, which is the function that sets up the entire
   `"iomfb_ap_link"` RPC channel between the AP and DCP -- the same
   core caller/callee dispatch-table plumbing (`iomfb_ap_caller_0`,
   `iomfb_ap_callee_0`) used for every RPC this whole project has ever
   exercised (`A410`/`dcp_set_display_device`, the DPTX APCALLs, etc.).
   This confirms the power-state handler is core DCP infrastructure,
   not something specific to any one pipe or connection type.

## What this means

Continuous frame completion for a pipe requires DCP's own internal
power-state machine to transition that pipe from state 8 to state
`0x21` (33) at some point after connection setup. Nothing in this
project's own driver -- not `dcp_set_display_device` (handle 0 or 2,
both already tried and found insufficient in candidate 0087, predating
this session), not any DPTX APCALL, not any DPIN0/crossbar register
write -- has ever been shown to trigger this specific transition. The
registration path traced above confirms this is generic, shared
firmware plumbing (the same RPC link used for everything), not a
DPIN0/USB4-tunnel-specific mechanism, which fits: a directly-wired PHY
pipeline (eDP, or a direct external port) presumably reaches this
power state through some other, more standard path our driver doesn't
need to replicate because macOS's boot firmware or the PHY's own power
domain already puts it there; a dynamically-routed Type-C/dcpext pipe
apparently does not get there automatically.

This also reframes 0087's finding precisely: "handle 0 does not power
this dcpext" was empirically correct, and we now know *why* at the
mechanism level -- neither `dcp_set_display_device` handle means "IOKit
power state 8 -> 0x21" to this firmware. The real trigger is a numbered
IOKit power-state ordinal transition, a concept our Linux driver has no
equivalent request for at all (Linux's own power management model --
runtime PM/autosuspend -- has no notion of "IOKit power state 33"
to ask DCP for).

## What would be needed to go further

Finding what *should* request this specific transition would mean
either: locating and decompiling DCP's own power-management state
table (the concrete vtable/class behind `param_1` in `FUN_0005d2b0`
and `FUN_000788d0`, blocked by the same chained-fixup + vtable/RTTI
wall as before), or finding the equivalent call in the XNU host
kernelcache side (a `setPowerState`/`changePowerStateTo`-style call on
an `IOMobileFramebufferAP`/`AppleDCPDPTXRemotePortProxy`-adjacent
class, which was not part of this session's earlier
AppleCIODPTX-focused kernelcache trace and would need a fresh pass).

## Decompiler infrastructure (reusable for future sessions)

Ghidra 12.1.4 ships no `linux_arm_64` decompile binary at all (only
`linux_x86_64`, `win_x86_64`, `osx_x86_64/arm_64`), which blocked
decompilation earlier this project on this ARM64 Linux host. Fixed by:

1. `sudo pacman -S qemu-user qemu-user-binfmt` (registers x86_64 ELF
   binaries to run transparently under `qemu-x86_64`).
2. Built a minimal x86_64 sysroot by downloading just the four .deb
   packages the `decompile` binary needs (`libc6`, `libstdc++6`,
   `libgcc-s1`, plus the `ld-linux-x86-64.so.2` interpreter they carry)
   from `deb.debian.org`, extracting with `ar x` + `tar`, and adding a
   `lib64 -> usr/lib/x86_64-linux-gnu` relative symlink (the interpreter
   path lookup needs a relative symlink here, not absolute -- an
   absolute symlink target isn't correctly re-prefixed by
   `QEMU_LD_PREFIX`/`-L`).
3. Created `Ghidra/Features/Decompiler/os/linux_arm_64/decompile` as a
   wrapper script invoking
   `qemu-x86_64 -L <sysroot> <real linux_x86_64/decompile binary> "$@"`.
   Ghidra picks this up automatically since it only checks for the
   binary's existence for the host-detected OS/arch directory.

This makes `pyghidra`-driven headless decompilation (not just
disassembly/xref analysis, which was already possible before) fully
functional on this ARM64 host for any future firmware analysis.
Sysroot at `/tmp/x86-sysroot/sysroot`, Ghidra install at
`/tmp/ghidra-setup/ghidra_12.1.4_PUBLIC` -- both under `/tmp`, so they
will not survive a reboot; re-running the three steps above takes a
few minutes if needed again.

No hardware register write was made in the course of this
investigation -- purely firmware disassembly/decompilation performed
offline against an already-extracted firmware image.
