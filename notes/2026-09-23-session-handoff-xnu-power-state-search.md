# Handoff prompt: find the XNU-side trigger for DCP's power-state gate

This is a ready-to-paste prompt for starting a fresh Claude Code session
on this exact next step, in case the current session needs to end. Copy
everything below the line into a new session's first message.

---

I'm working on getting an external monitor working on my MacBook Pro
16" M2 Pro (apple,j416s / Mac14,10) running Asahi Linux (Omarchy),
through an OWC Thunderbolt 5 hub + Synaptics VMM7100 USB-C-to-HDMI
adapter, to a BenQ 2560x1440 monitor. Direct HDMI and a direct USB-C DP
adapter (no hub) both already work fine on this same machine. Only the
hub-tunneled (USB4 DisplayPort tunnel) path is broken: every observable
milestone succeeds (USB4 tunnel setup, DCP crossbar routing through a
DPIN0 input, AUX/DPRX channel completion, `set_digital_out_mode`), but
the monitor never receives an actual video signal (confirmed on the
monitor's own OSD: correct HDMI input selected, "no signal detected").

## Repos and where everything lives

- `/home/oliver/Development/asahi-j416s-display` -- the project repo
  (git, pushed to a real remote). `notes/` has the full history,
  `notes/ACTION-LOG.md` is the master mandatory-logging chronicle,
  `patches/` has every kernel patch as a numbered series, `scripts/`
  has installer/test tooling.
- `/home/oliver/Development/linux-aurora-pr` -- the actual kernel
  source tree (branch `j416s-usb4-dpin`), symlinked into the display
  repo's `src/` tree. This is where all kernel code changes are made;
  patches get exported from here into the display repo.
- Read `notes/ACTION-LOG.md` (append-only, chronological, and large --
  read the tail first) and these specific notes from earlier the same
  day as this handoff, in order, before doing anything else:
  1. `notes/2026-09-23-mode-value-sweep-exhausted.md` -- an exhaustive
     0-15 hardware sweep of a specific pair of DPIN0 crossbar registers
     (MODE_A/MODE_B) that was hypothesized to gate the picture. All 16
     possible values are clean negatives. **Do not suggest testing more
     values here or revisiting this specific register pair** -- it's
     conclusively ruled out.
  2. `notes/2026-09-23-swap-complete-never-fires.md` -- found, by
     correlating DRM atomic state, per-crtc CRC/frame-index debugfs
     counters, and Hyprland's own compositor log (`atomic drm request:
     failed to commit: Device or resource busy`), that DCP firmware
     accepts a modeset and a handful of initial frames, then never
     calls back to report any further frame as complete. Kernel-side:
     `dcpep_cb_swap_complete()` in
     `drivers/gpu/drm/apple/iomfb_template.c` (RPC index 589) is the
     callback that's supposed to fire and never does past the first
     few frames.
  3. `notes/2026-09-23-run-mode-4-permanently-stuck.md` -- correlated
     the above against DCP firmware's own RTKit syslog state tracing
     (`PPipeDCP_H13P.cpp`) already present in the kernel log: this
     pipe's internal `run_mode` transition from 2 to 4 (continuous
     scanout) is requested, logged as "deferring", and never completes
     -- verified live over 40+ minutes of an idle, fully-negotiated
     connection (state was byte-identical at the start and 40 minutes
     later; ruled out "just needs more time").
  4. `notes/2026-09-23-power-state-gate-traced.md` -- the deepest
     finding. Using a **working ARM64 decompiler for Ghidra** (see
     setup below, since Ghidra ships no native `linux_arm_64` decompile
     binary at all), traced the exact chain in real decompiled DCP
     firmware C code:
     - `IOMobileFramebuffer::swap_submit_dcp` only reuses a swap slot
       once the previous transaction's `completed` field is true.
     - The function that sets that field and notifies the AP,
       `batched_swap_complete_ap_gated` (`FUN_00078ae0` in the
       analyzed binary), is only ever *registered* (inside
       `FUN_000788d0`) when a global, `DAT_0062d975`, is nonzero.
     - That global is set/cleared by exactly one function
       (`FUN_0005d2b0`), which is a **power-state transition handler**:
       entering internal state `0x21` (33) from state `8` sets it true;
       the reverse transition clears it.
     - That handler is registered as part of `FUN_00129574`, which sets
       up the core `"iomfb_ap_link"` AP<->DCP RPC channel -- i.e. this
       is generic DCP firmware infrastructure, not anything specific to
       USB4/DPIN0 routing.
  5. `notes/2026-09-23-upstream-dptxep-crossref.md` and the formula-
     correction note from the same day -- confirms our own kernel
     driver (`drivers/gpu/drm/apple/dptxep.c`, `dcp.c`) already matches
     or exceeds the most advanced known Asahi Linux community work on
     the direct-DP-alt-mode path; nothing there addresses this specific
     USB4-tunnel power-state gap either.

## The actual task

**Find what, on the real macOS/XNU side, triggers this exact power-
state transition (some internal ordinal 8 -> 0x21) for a dcpext-class
display pipe**, so we know what our Linux driver needs to request that
it currently doesn't. This is almost certainly an IOKit
`registerPowerDriver`/`changePowerStateTo`/`setPowerState`-style call
on a `IOMobileFramebufferAP`-adjacent class (possibly
`AppleDCPDPTXRemotePortProxy`, `AppleCIODPTX`, or a class specifically
tied to `dcpext`/Type-C-routed pipes -- these class names are
speculative, confirm them from the actual binary). This requires a
**fresh pass over the XNU kernelcache** (a different binary from the
DCP coprocessor firmware already analyzed above) specifically looking
for host-side power-management calls tied to display pipes, since all
of this session's earlier kernelcache work focused on
`AppleCIODPTX::bringConnectionUp`/`connectTo` (the DPIN0 handshake),
not power state management.

### Getting the kernelcache

```
# DER OCTET STRING at file offset 57, length 25883419, in:
/boot/asahi/kernelcache.release.mac14j
# lzfse-decompress it; verify SHA256:
9615a486511c7a60b141d7f4291361c5212e908546d6568890029bb90b5431e7
```
(This exact extraction was done multiple times earlier in the project;
the offset/length/hash above are already confirmed correct for this
machine's installed kernelcache.)

### Getting the DCP firmware (if you need to re-cross-reference it)

```
mkdir -p /tmp/dcp-fw2 && cd /tmp/dcp-fw2
# build pzb (partialZipBrowser) -- libfragmentzip/libgeneral are
# already installed system-wide from earlier sessions (/usr/local/lib),
# only pzb itself needs rebuilding:
git clone https://github.com/tihmstar/partialZipBrowser.git
cd partialZipBrowser && git fetch --unshallow  # if needed
export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig LD_LIBRARY_PATH=/usr/local/lib
./autogen.sh && make -j4
cd ..
export LD_LIBRARY_PATH=/usr/local/lib
./partialZipBrowser/pzb/pzb -g "Firmware/dcp/t602xdcp.im4p" -o t602xdcp.im4p \
  "https://updates.cdn-apple.com/2023SummerFCS/fullrestores/032-69606/D3E05CDF-E105-434C-A4A1-4E3DC7668DD0/UniversalMac_13.5_22G74_Restore.ipsw"
python3 -c "
from asahi_firmware.img4 import img4p_extract
with open('t602xdcp.im4p','rb') as f: data = f.read()
fourcc, payload = img4p_extract(data)
open('t602xdcp.bin','wb').write(payload)
"
# Verify: sha256sum t602xdcp.bin ->
# f3d919d62979408b5643a0f1e07df3a17e734dc5666ee27a873766a3adb35430
```

### Setting up a working Ghidra decompiler on this ARM64 host

Ghidra 12.1.4 (and likely other versions) ships decompile binaries only
for `linux_x86_64`, `win_x86_64`, `osx_x86_64`, `osx_arm_64` -- **not**
`linux_arm_64`, which silently breaks decompilation (disassembly/xref
analysis still works) on this machine's own architecture. Fixed this
session by running the x86_64 binary under QEMU emulation:

```
sudo pacman -S --noconfirm qemu-user qemu-user-binfmt
mkdir -p /tmp/x86-sysroot && cd /tmp/x86-sysroot
curl -sL -o libc6.deb "http://deb.debian.org/debian/pool/main/g/glibc/libc6_2.44-2_amd64.deb"
curl -sL -o libstdc++6.deb "http://ftp.debian.org/debian/pool/main/g/gcc-12/libstdc++6_12.2.0-14+deb12u1_amd64.deb"
curl -sL -o libgcc-s1.deb "http://ftp.debian.org/debian/pool/main/g/gcc-12/libgcc-s1_12.2.0-14+deb12u1_amd64.deb"
mkdir -p sysroot
for pkg in libc6 libstdc++6 libgcc-s1; do
  mkdir -p extract-$pkg && ar x $pkg.deb --output=extract-$pkg
  tar -xf extract-$pkg/data.tar.* -C sysroot
done
mkdir -p sysroot/lib64
# IMPORTANT: this symlink must be RELATIVE, not absolute -- an absolute
# target isn't correctly re-prefixed by QEMU_LD_PREFIX/-L.
ln -sf ../usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 sysroot/lib64/ld-linux-x86-64.so.2

# download Ghidra (check for a newer release tag first):
mkdir -p /tmp/ghidra-setup && cd /tmp/ghidra-setup
curl -sL -o ghidra.zip "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip"
unzip -q ghidra.zip

GHIDRA=/tmp/ghidra-setup/ghidra_12.1.4_PUBLIC
mkdir -p "$GHIDRA/Ghidra/Features/Decompiler/os/linux_arm_64"
cat > "$GHIDRA/Ghidra/Features/Decompiler/os/linux_arm_64/decompile" << 'WRAPPER'
#!/bin/bash
export QEMU_LD_PREFIX=/tmp/x86-sysroot/sysroot
exec qemu-x86_64 -L /tmp/x86-sysroot/sysroot "$GHIDRA/Ghidra/Features/Decompiler/os/linux_x86_64/decompile" "$@"
WRAPPER
chmod +x "$GHIDRA/Ghidra/Features/Decompiler/os/linux_arm_64/decompile"

python3 -m venv /tmp/ghidra-setup/venv
source /tmp/ghidra-setup/venv/bin/activate
CXX=/usr/bin/g++ CC=/usr/bin/gcc pip install --quiet pyghidra jpype1
```

Then drive it with `pyghidra` (see the worked examples in
`2026-09-23-power-state-gate-traced.md` for the exact Python patterns
that worked: `pyghidra.start()`, `GhidraProject.openProject()` /
`openProgram()` for re-opening an already-analyzed project,
`pyghidra.open_program(..., analyze=True)` for a first-time import,
`DecompInterface` for actual decompilation, and
`mem.findBytes()`-based string search + `getReferencesTo()` for finding
functions by the strings they reference, since there's no symbol table
in either binary). **Run long analyses as detached background
processes and poll for completion** -- full auto-analysis on the DCP
firmware took several minutes; the kernelcache is larger and will take
longer. Note everything under `/tmp` does not survive a reboot; if a
reboot happens mid-session, redo the setup (takes ~10-15 minutes).

## Mandatory safety/process rules for this project (do not skip)

- Never touch anything outside `/home/oliver/Development/asahi-j416s-display`
  and `/home/oliver/Development/linux-aurora-pr` for actual changes.
  Never touch any `omalogimouse`-named project files.
  Never commit `HERDR-PR-BRIEF.md` or raw hardware captures (the
  `captures/` directory in the display repo is intentionally untracked).
- Firmware/kernelcache analysis itself is safe, offline, read-only --
  no confirmation needed to keep researching.
- **Any action that touches real hardware** (installing a new kernel
  module, writing a new register value, requesting a reboot, asking for
  a hub plug/unplug) requires: write a design note first, append to
  `notes/ACTION-LOG.md` with exact commands/addresses, commit and push
  *before* taking the action, then take exactly one hardware action at
  a time with the user physically performing any plug/unplug/reboot
  (never assume or fake a physical action; verify via
  `/sys/bus/thunderbolt/devices/` and
  `/sys/class/drm/card*-*/status` after every claimed action, don't
  just trust a "done" reply).
- **Never claim the monitor works** without the user's own explicit
  visual confirmation of a real picture. Frame completion, DRM "active"
  state, or Hyprland recognizing the monitor are not proof by
  themselves -- this project has been burned by exactly that
  distinction today.
- If a hardware test comes back invalid (e.g. DCP never even detects
  the display -- a real, recurring ~20% intermittent failure mode on
  this hub/adapter combination, confirmed unrelated to code, seen many
  times today), say so and ask to retry rather than treating it as data.
- If several consecutive hotplug attempts on the same long-running boot
  start failing (3+ in a row), that has reliably meant accumulated
  USB4/hub state fatigue this session, not a real regression -- a
  reboot has cleared it every time it happened today.

## What "done" looks like

A confirmed, user-visually-verified picture on the BenQ monitor through
the OWC hub + Synaptics VMM7100 adapter, from the right-hand USB-C port,
with eDP and hub USB still functional. Anything short of that -- however
deep or interesting the intermediate finding -- is not the goal.
