# Action log

Write the next hardware action here and commit it before running it.
After a crash, this file is the record of what was in flight.

An action is hardware if it loads a module, writes a module parameter,
ioremaps, writes MMIO, reboots, or runs `load-appledrm.sh`.

## 2026-09-21 21:36 crash

Not a reboot I asked for. The machine reset while this command was
starting, before it returned:

`insmod src/dispclk/apple-dispclk.ko`

Module init (`apply=1`) did this immediately, in order:

1. `ioremap` panel disp-1 `0x389320000` size `0x4000` and read it.
2. `ioremap` dcpext1 disp-1 `0x315320000` size `0x4000` and read it.
3. `ioremap` crossbar `0x70304c000` and read `0x000/0x800/0x020/0x820/0x024/0x81c`.
4. `writel` every panel word that was non-zero onto dcpext1 where that word was zero.

The tool line was "Load dispclk and read crossbar clock". It died at 0.0s.
No kernel panic was logged. eDP-1 came back on the next boot. `dispclk` is
not loaded. Do not insmod it. Do not write `appledrm.usb4_dispclk`. That
parameter does the same copy.

Suspect: the read of the live panel block, or the write into dcpext1
disp-1. The crossbar read alone has been done before from the mux driver
without this instant reset.

## 2026-09-21 21:43 about to run

Not the copy. Read the idle external block only.

Command, after this file is pushed:

`insmod src/dispclk/apple-dispclk.ko read_ext=1`

What it does:

1. Refuse `apply=1`.
2. `ioremap` dcpext1 disp-1 `0x315320000` size `0x4000`.
3. Read every word. Count how many are non-zero.
4. `iounmap`. No write. No panel map. No crossbar map.

If the machine resets during this command, this was the action.

Result: it returned. `dcpext1 disp-1 nonzero words 1065`. eDP stayed on.
Reading this block is safe. The crash was the panel map or the write.

## 2026-09-21 21:44 about to run

Same block, still read-only. Print the first 24 non-zero words.

Commands, after this file is pushed:

`rmmod apple_dispclk`
`insmod src/dispclk/apple-dispclk.ko read_ext=1`

What it does: `ioremap 0x315320000` size `0x4000`, `readl`, `iounmap`.
No panel. No writes. No crossbar.

Result: it returned. 1065 words nonzero. The first words are
`+000 71699e03`, `+004 d3c60930`, `+008 9600df50`, and so on through
`+05c`. That is not a clock-enable block. Do not copy the panel into
it. Do not map `0x389320000`. The 21:36 crash stays closed.

## 2026-09-21 21:46 about to run

Read the other 16 KB external block. Still no panel and no writes.

Command, after this file is pushed:

`insmod src/dispclk/apple-dispclk.ko read_ext2=1`

What it does:

1. `ioremap` dcpext1 disp-2 `0x315344000` size `0x4000`.
2. Read every word. Print the first 24 non-zero words and the count.
3. `iounmap`.

No `0x389320000`. No `0x315320000`. No writes. No crossbar. No reboot.

Result: it returned. disp-2 has 5 nonzero words:
`+02c 00000044`, `+064 3fffffff`, `+068 000003f0`, `+070 00000001`,
`+074 00000001`. This one looks like a control block. eDP stayed on.

## 2026-09-21 21:48 about to run

Read the same control block on the live panel. Read only.

Commands, after this file is pushed:

`rmmod apple_dispclk`
`insmod src/dispclk/apple-dispclk.ko read_panel2=1`

What it does:

1. `ioremap` panel disp-2 `0x389344000` size `0x4000`.
2. Read every word. Print the first 24 non-zero words and the count.
3. `iounmap`.

This is not `0x389320000` (the block in the 21:36 crash). No writes.
No dcpext map. No crossbar. No reboot.

Result: it returned. Panel disp-2 has the same four words as dcpext1
disp-2 (`+02c 00000044`, `+064 3fffffff`, `+068 000003f0`,
`+070 00000001`). dcpext1 also has `+074 00000001`. Not the clock.
eDP stayed on.

## 2026-09-21 21:50 about to run

Read the first 4 KB of dcpext1 disp-0 only.

Command, after this file is pushed:

`rmmod apple_dispclk`
`insmod src/dispclk/apple-dispclk.ko read_ext0=1`

What it does:

1. `ioremap` `0x314000000` size `0x1000`.
2. Read every word. Print the first 24 non-zero words and the count.
3. `iounmap`.

No panel. No disp-1. No disp-2. No writes. No crossbar. No reboot.

Result: it returned. All 1024 words in the first 4 KB are nonzero,
starting `+000 caf9b40c`. Same kind of data as disp-1, not a clock
enable. eDP stayed on. Do not write disp-0. Do not map the panel's
disp-0 or disp-1.

## 2026-09-21 21:55 about to run, then reset

Logged and pushed before the command. The command was:

`insmod src/dispclk/apple-dispclk.ko write_074=1`

Planned steps: map `0x315344000`, read `+074`, write 0, read it back.

The crashed boot's kernel log has no `dispclk: write` and no
`+074 before`. The last dispclk line that did land is the disp-0
read at 21:49:53, which returned (`1024` nonzero words). UFW lines
continue until 21:50:59. The next boot is 21:52. No panic.

So this write is the action that was in flight, and it left no
completion line. Do not run it. Do not repeat `read_ext0`.
`write_074` now refuses to load.

## 2026-09-21 21:56 no hardware

This boot, after the reset, `315c00000.dcp` still logs
`setup_video_limits` with no timing, then `set_run_mode 2 -> 1 -> 0`,
then `set_device_enabled 1 -> 0`. eDP-1 is on. No module was loaded
and no register was written on this step. Disp-block reads and writes
stay closed. `iomfb_poweron` stays closed.

## 2026-09-21 22:05 no hardware

The panel DCP reaches `nr_modes:6` and `set_run_mode 2 -> 4`, then
`set_digital_out_mode(color:1 timing:2)` for 3456x2160. dcpext1 never
gets a timing id, so that call cannot be made for it. No module was
loaded and no register was written.

## 2026-09-21 Codex diagnostic 0090 — prepare physical unplug and capture

No hardware action has occurred in this investigation. Kernel commit
`a0df2ede847714b1de9fd2d0341cb1050c831df6` adds EDT/property logging and
removes the automatic second HPD request. It does not add MMIO or timings.
The old no-timing/clock causal interpretation is unproven; see
`notes/2026-09-21-codex-reassessment.md`.

Next action after this entry is committed and pushed: ask Oliver to save work
and physically unplug the OWC hub from the Mac. The hub keyboard will be
unavailable while physically unplugged; use the MacBook keyboard.
This boot's port is typec0: NHI `0x701f00000`, ACIO `0x701ac0000`, display
crossbar `0x70304c000`. DCP external instance `0x315c00000`; panel
`0x389c00000`. No register mapping, direct MMIO access, parameter write,
module load, or reboot is part of this step.

After Oliver confirms unplugging, exact snapshot command:

`cd /home/oliver/Development/asahi-j416s-display && ./scripts/capture-display.sh captures/2026-09-21-0090-unplugged.txt`

The script reads DRM/USB/Type-C/thunderbolt sysfs attributes and existing
kernel logs, and queries Hyprland. It does not explicitly map or write MMIO.
No new tunnel and no DP alt-mode request. Record installation and reboot
separately before those actions. Do not run load-appledrm.sh at this step.

## 2026-09-21 diagnostic 0090 — planned installation, no reboot

Execute installation only after Oliver confirms the hub is unplugged.
Saving work is required before the separately scheduled reboot, not this
installation-only step. The new loader additionally refuses installation if an external Thunderbolt
router remains in sysfs. No command in this entry has run at commit time.

First preserve the installed appledrm and initramfs (file operations only):

```
sudo -n install -d /var/tmp/j416s-0090-before
sudo -n cp -an /usr/lib/modules/7.1.12-2.5-1-ARCH/kernel/drivers/gpu/drm/apple/appledrm.ko /var/tmp/j416s-0090-before/appledrm-kernel.ko
sudo -n cp -an /usr/lib/modules/7.1.12-2.5-1-ARCH/updates/appledrm.ko /var/tmp/j416s-0090-before/appledrm-updates.ko
sudo -n cp -an /boot/initramfs-linux-aurora.img /var/tmp/j416s-0090-before/initramfs-linux-aurora.img
```

Then the exact installation command, from the repository root:

`sudo -n env -u USB4_GROK_CONTINUE -u USB4_GROK_SESSION /home/oliver/Development/asahi-j416s-display/scripts/load-appledrm.sh --no-reboot`

This installs the built module into both kernel/drivers/gpu/drm/apple and
updates, copies the other five modules (verified identical to installed
versions), runs depmod and mkinitcpio -p linux-aurora, and returns WITHOUT
reboot. No insmod/rmmod, direct MMIO, ioremap, PHY switch, or module-parameter
write. The running display driver is not replaced until a separately logged
reboot. No auto-continue will be armed.

New appledrm SHA256:
`790475c0059aea58b602de5a35f2f2a325ceafcb5e8756946e7e9b5b994704d1`.
Previous kernel-path appledrm SHA256:
`c4d3c30af6c5e820031543302bbbd3da444b8513028877a19487ce7e0b3d90ca`.

Hardware addresses potentially used on the later boot (NOT accessed directly
by this installation): eDP DCP `0x389c00000`, dcpext1 `0x315c00000`, HDMI DCP
`0x289c00000`. Last active hub route: typec0 NHI `0x701f00000`, ACIO
`0x701ac0000`, crossbar `0x70304c000`. Hub must stay unplugged until eDP is up.
All disp-block, lpdptxphy, ACIO analog and /dev/mem prohibitions remain in force.

After successful installation, extract the initramfs into a temporary directory
and verify the embedded updates/appledrm.ko checksum before separately logging
and scheduling a reboot. If installation fails, do not reboot.

Installation prerequisite result: Oliver confirmed physical hub unplugging.
/sys/bus/thunderbolt/devices is empty; Hyprland still shows eDP-1 active.
The unplugged capture completed. Backups were copied successfully to
/var/tmp/j416s-0090-before; both old appledrm copies hash to c4d3c30a…,
and the saved initramfs SHA256 is
1819205a61672ba2b0f30148a175d23b7897b13311b7a0ca78ce9b16e2d5f701.
Next command remains the exact --no-reboot installer above.

## 2026-09-21 diagnostic 0090 — installation completed; reboot pending

The --no-reboot installation returned exit 0 and notes/load-status is OK.
mkinitcpio completed successfully. Extracted the new initramfs with
`lsinitcpio -x /boot/initramfs-linux-aurora.img` in
`/tmp/j416s-0090-initramfs` and compared its embedded
`usr/lib/modules/7.1.12-2.5-1-ARCH/updates/appledrm.ko` with the built module.
Both installed module paths and the embedded module have SHA256
`790475c0059aea58b602de5a35f2f2a325ceafcb5e8756946e7e9b5b994704d1`.
The running module has not been unloaded or replaced.

Pending action, ONLY after Oliver says work is saved and ready for reboot:

`sudo -n systemd-run --unit=j416s-0090-reboot --on-active=30s /usr/bin/systemctl reboot`

Before scheduling, verify /sys/bus/thunderbolt/devices has no external router.
This deliberately reboots the computer 30 seconds after scheduling. It is a
planned diagnostic reboot, not an unexpected reset. No USB4_GROK_CONTINUE,
no live insmod/rmmod, no manual MMIO/ioremap or module-parameter write.

The next boot loads 0090 appledrm from initramfs. Normal DCP initialization
uses panel DCP `0x389c00000`, dcpext1 `0x315c00000`, HDMI DCP `0x289c00000`;
the last hub route was typec0 / NHI `0x701f00000`, ACIO `0x701ac0000`, xbar
`0x70304c000`. Keep hub physically unplugged throughout reboot. No forbidden
panel disp-block or lpdptxphy experiment is requested.

After boot: resume this conversation with hub still unplugged. Read dmesg
for read_edt_data and DCP property logs, confirm eDP in Hyprland, then log and
push a separate hub-replug action before requesting it. Stop/unplug if eDP
blacks out. Do not interpret empty timings at disconnected boot as a fix or
failure until the later discovery sequence has been observed.


## 2026-09-21 0090 boot result — eDP recovery and startup mitigation

Scheduled reboot ran as logged. Oliver reports needing a second boot to see
the internal display. Failed boot: 1c91ba5e60974628a3259c4796f54d30;
successful boot: 320edefca258477d9c882452d1cdb100. Hub stayed unplugged.
The failed boot journal ends with an SMC-triggered forced shutdown.
Both boots loaded 0090. See notes/2026-09-21-0090-boot-result.md and captures.

New diagnostic result: both external read_edt_data callbacks request only
initial-vbi-advance-lines; no timing-table request. The previous boot started
Hyprland before the Apple DRM device registered. A startup gate is prepared.

After this entry is committed and pushed, exact installation commands:

```
sudo -n install -D -m 0755 /home/oliver/Development/asahi-j416s-display/scripts/wait-apple-drm.py /usr/local/libexec/j416s-wait-apple-drm
sudo -n install -D -m 0644 /home/oliver/Development/asahi-j416s-display/systemd/20-apple-drm-ready.conf /etc/systemd/system/sddm.service.d/20-apple-drm-ready.conf
sudo -n systemctl daemon-reload
```

No reboot, SDDM restart, live module action, MMIO, ioremap, PHY operation,
or parameter write. Addresses: none directly accessed. Future SDDM starts
wait for the DRM device that exposes the panel driven by DCP 0x389c00000.
Only sysfs/file metadata are read by the check; no DRM ioctl or modeset.
The check has passed six tests and a real-system read-only check.


## 2026-09-21 0090 — controlled hub reconnect, no reboot

Startup-check installation completed and systemctl cat sddm.service confirms
ExecStartPre=/usr/local/libexec/j416s-wait-apple-drm. No desktop restart or
reboot occurred. eDP-1 is active on the current 0090 boot; monitor JSON saved.
No external Thunderbolt router is currently present.

After this entry is committed and pushed: ask Oliver to physically reconnect
the OWC hub to the SAME Mac socket used before (last recorded typec0).
The Mac-side expected route is NHI 0x701f00000, ACIO 0x701ac0000, crossbar
0x70304c000 to dcpext1 0x315c00000. Confirm the actual live port from dmesg
after connection; do not blindly apply these addresses to any command.

This is a physical reconnect handled by normal drivers. No manual tunnel
creation, DP-alt-mode switch, parameter write, module load, direct MMIO,
ioremap or reboot. The diagnostic 0090 path removes the second HPD request.
The hub was physically absent, so normal connection-manager enumeration may
create its usual tunnel; no separate tunnel-building experiment is requested.
The internal display must remain on. If it blacks out, Oliver must unplug the
hub immediately and testing stops. Keyboard function must be checked by Oliver.

After reconnection, exact capture command:
`/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-21-0090-replugged.txt`

Also read existing dmesg for EDT/property/DPTX/USB4/DP-IN status messages.
No direct register read is requested; use status values the drivers log.

## 2026-09-21 0090 reconnect result — eDP and keyboard work; no external display

Oliver confirms the integrated display stays on and the external hub keyboard
works. External monitor remains black. Capture script completed as logged.
Live route is confirmed typec0 / 701f00000.nhi / 70304c000.mux.
Tunnel 0:5 <-> 1:19 remains VE=1 AE=1 HPD=1 DPRX=0.
No SET_LINK_RATE, no SET_ACTIVE_LANE_COUNT, no external TimingElements.
request_display accepts target 0x9001 and calls GET_SUPPORTS_HPD,
GET_MAX_LANE_COUNT and ACTIVATE. With the second HPD removed, this capture
has no DCPDPDevice start or subsequent five-second device timeout.
That absence is not a fix: discovery has not started/progressed to timings.
Crossbar logged 0x000=4 and 0x800=0; semantics remain unverified for T602x.

No further hardware action at this step. Continuing read-only protocol/source
investigation rather than repeating the prohibited HPD or MMIO experiments.

## 2026-09-21 — prepared HDMI baseline, awaiting Oliver's choice

Oliver confirms the exact monitor/HDMI adapter/cable/OWC hub combination
works perfectly in macOS. A question is pending about a temporary direct
HDMI baseline. This entry does not claim it has been performed.

If Oliver accepts, after this entry is committed and pushed, request this
exact physical action: leave the OWC hub and keyboard attached to their
current ports; disconnect the monitor HDMI cable from the VMM7100 adapter
and connect that HDMI cable to the Mac's built-in HDMI socket. Leave the
VMM7100 adapter itself in the hub. No reboot or driver reload.

Addresses/controllers: normal HDMI hotplug is handled by dcpext0
0x289c00000 (firmware target PHY 3 / internal DP-to-HDMI path). Current hub
route is typec0, NHI 0x701f00000, ACIO 0x701ac0000, crossbar 0x70304c000,
dcpext1 0x315c00000. Panel DCP is 0x389c00000. These identify normal driver
paths, not addresses for manual mapping or MMIO. HDMI driver may perform
its ordinary power/PHY/modeset operations in response to cable hotplug;
no experimental module parameter or direct register operation is requested.
No manual tunnel creation or DP-alt-mode switch on the hub port.

Stop condition: if eDP blacks out, disconnect the newly attached HDMI cable,
unplug the hub as previously instructed, and stop hardware testing.

After Oliver reports connection, capture with these exact commands:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-21-hdmi-baseline.txt
sudo -n dmesg > /home/oliver/Development/asahi-j416s-display/captures/2026-09-21-hdmi-baseline-kernel.log
```

The capture script queries DRM/USB/Thunderbolt sysfs and Hyprland, and reads
existing kernel logs. It issues no direct MMIO, firmware request, or modeset.
Installed kernel remains 0090; 0091 is built but not installed.

## 2026-09-21 — HDMI result and direct USB-C adapter baseline

The HDMI baseline completed: Oliver reports a working monitor, and the
capture shows eDP-1 and HDMI-A-1 both active. SET_LINK_RATE and four active
lanes precede 22 firmware timings and the HDMI connected callback. The hub
keyboard remains enumerated. See notes/2026-09-21-hdmi-baseline-result.md.

After this entry is committed and pushed, ask Oliver to perform this exact
physical action, with no reboot: disconnect the monitor HDMI cable from the
Mac HDMI socket; remove the VMM7100 USB-C-to-HDMI adapter from the OWC hub;
attach the monitor HDMI cable to that adapter; plug the adapter into the
Mac's RIGHT-SIDE USB-C socket. Keep the hub and keyboard connected to their
current left-side socket throughout.

Expected separate right-port path: NHI 0xf01f00000, ACIO 0xf01ac0000,
crossbar 0xf0304c000. Normal Type-C routing may allocate dcpext0 0x289c00000
or dcpext1 0x315c00000; confirm actual allocation from dmesg rather than
assuming it. Panel DCP remains 0x389c00000. The hub's current typec0 path
is NHI 0x701f00000 / ACIO 0x701ac0000 / crossbar 0x70304c000.

Normal drivers negotiate DP alt mode on the separate adapter port and may
perform their ordinary PHY and display initialization. Do not switch the
hub port out of USB4, create a manual tunnel, access registers manually,
load a module, write parameters, or reboot. The existing USB4 tunnel may
be torn down by the connection manager when its downstream adapter is
removed; no manual tunnel operation is requested.

If eDP blacks out, unplug the directly connected adapter, unplug the hub,
and stop hardware testing. Otherwise ask Oliver to report picture and
keyboard function. Capture after the user reports the connection:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-21-direct-usbc-baseline.txt
sudo -n dmesg > /home/oliver/Development/asahi-j416s-display/captures/2026-09-21-direct-usbc-baseline-kernel.log
```

This action is prepared, not yet reported performed. Installed module is
still 0090; 0091 remains an uninstalled build artifact.

## 2026-09-21 — direct adapter success and user-reported disconnect

The prepared direct USB-C test succeeded. Captures show eDP-1 and USB-3
active together, VMM7100 on the right port and Keychron Q4 through the hub.
The right DP route borrowed dcpext0 0x289c00000, using crossbar
0xf0304c000 and target 0x8020. See the direct-usbc-baseline result note.

Oliver then reported disconnecting the direct adapter. This records his
reported physical action; it is not a claim of a new agent-issued command
or a pre-action log for that spontaneous disconnect. No new MMIO, parameter,
module, firmware command or reboot was issued. Keep the adapter disconnected
and hub/keyboard attached while reviewing the evidence.

## 2026-09-21 — 0092 exception approved; prepare hub unplug and backup

Oliver explicitly approved trying the proposed 0092 exception after being
shown its target, ordering, limits and the previous prohibition. This covers
the single HPD-after-request_display probe described in
notes/2026-09-21-0092-protocol-proposal.md, not other prohibited operations.

Preflight: eDP connected/enabled, all external DRM connectors disconnected;
external Thunderbolt router 0-1 is still attached. Do not install yet.
Installed 0090 module SHA256 starts 790475c0059a; candidate 0092 starts
ceb3aea107ee8. New backup directory and experiment config do not yet exist.

After this entry is committed and pushed, ask Oliver to physically unplug
the OWC hub from the Mac. Keep the display adapter disconnected. This
uses the normal disconnect path for typec0, NHI 0x701f00000, ACIO
0x701ac0000, crossbar 0x70304c000 and dcpext1 0x315c00000; no manual MMIO,
PHY reconfiguration, module action or reboot is requested. eDP is driven
by 0x389c00000. Confirm no external router before installation.

While awaiting unplug, preserve regular files with these exact commands
(no hardware access; mkdir must fail if backup directory already exists):

```
sudo -n mkdir -m 0700 /var/tmp/j416s-0092-before
sudo -n cp -a /lib/modules/7.1.12-2.5-1-ARCH/kernel/drivers/gpu/drm/apple/appledrm.ko /var/tmp/j416s-0092-before/appledrm-kernel.ko
sudo -n cp -a /lib/modules/7.1.12-2.5-1-ARCH/updates/appledrm.ko /var/tmp/j416s-0092-before/appledrm-updates.ko
sudo -n cp -a /boot/initramfs-linux-aurora.img /var/tmp/j416s-0092-before/initramfs-linux-aurora.img
```

Installation and reboot remain separate logged steps after physical unplug.

## 2026-09-21 — 0092 installation, no reboot in this step

Oliver reports hub unplugged; sysfs confirms no external Thunderbolt router.
All three 0090 backup copies completed in /var/tmp/j416s-0092-before.
The five other modules copied by the loader match installed files byte-for-
byte by SHA256; only appledrm changes.

After committing and pushing this entry, execute exactly:

```
sudo -n install -m 0644 /home/oliver/Development/asahi-j416s-display/config/0092-usb4-protocol-probe.conf /etc/modprobe.d/j416s-0092-protocol-probe.conf
sudo -n env -u USB4_GROK_CONTINUE -u USB4_GROK_SESSION /home/oliver/Development/asahi-j416s-display/scripts/load-appledrm.sh --no-reboot
```

These install files and rebuild initramfs; they do not replace the live
module or issue the probe. Firmware target after a later approved boot and
reconnect is 0x8001 on dcpext1 0x315c00000, NHI 0x701f00000, ACIO
0x701ac0000, crossbar 0x70304c000. Panel DCP 0x389c00000 is not manually
mapped or written. No direct MMIO or new live hardware request in this step.
Keep hub absent. Verify extracted initramfs module and config before the
separately logged reboot. The config will be removed and initramfs rebuilt
after boot, before the actual hub reconnect, to disarm subsequent boots.

## 2026-09-21 — 0092 installed and verified; hub-absent reboot

Loader --no-reboot completed successfully. Extracted initramfs at
/tmp/j416s-0092-initramfs-q6tlp2sy contains candidate appledrm SHA256
ceb3aea107ee878ca1004098ae23f5b0ab2fdfa929dd244271224919e668e30f
and options appledrm usb4_protocol_probe=1. Both installed module copies
match. Backups of both 0090 module copies match SHA256
790475c0059aea58b602de5a35f2f2a325ceafcb5e8756946e7e9b5b994704d1;
backed-up initramfs SHA256 is
fef9c5d9d3e73ac496dcbca0f946ec8d9ca34aed0d673252cc8e8f8802e3c73d.

After this entry is committed/pushed and absence of external routers is
rechecked, schedule the approved test boot with this exact command:

```
sudo -n systemd-run --unit=j416s-0092-reboot --on-active=30s /usr/bin/systemctl reboot
```

This reboot initializes normal hardware, including panel DCP 0x389c00000
and external DCPs 0x289c00000/0x315c00000. Hub must remain physically absent;
no USB4 protocol probe is expected until later reconnect. No manual MMIO.
The SDDM readiness gate is installed. No unattended reconnect/continue.

After boot, keep hub absent, inspect panel/current module parameter/logs,
and remove the opt-in config plus rebuild initramfs (log commands first)
before the separately logged reconnect. Stop if the panel fails to recover.

Conditional recovery prepared if 0092 boot fails; do not execute during a
successful boot or with hub attached:
`sudo -n bash /home/oliver/Development/asahi-j416s-display/scripts/restore-0090.sh`
This verifies the saved hashes, restores only the two 0090 appledrm files and
the 0090 initramfs, removes only the 0092 config, and runs depmod. No live
driver reload, no direct hardware access, and no automatic reboot. Any
subsequent recovery reboot must be recorded separately before execution.

## 2026-09-21 — 0092 boot successful; disarm future boots

Oliver is back. Boot ID f77dc546-cf01-4d44-bdb6-50ee9aa0b8d8; loaded usb4_protocol_probe=Y; eDP connected
and enabled; no external Thunderbolt routers. Kernel journal shows panel
3456x2160@120 modeset completed. No USB4 protocol probe has run yet.

After committing/pushing this entry, execute these exact commands:
```
sudo -n rm -- /etc/modprobe.d/j416s-0092-protocol-probe.conf
sudo -n mkinitcpio -p linux-aurora
```
Then extract the rebuilt initramfs with lsinitcpio -x into a fresh /tmp
directory and verify the probe config is absent and the 0092 module hash
matches. No live parameter write, module reload, reboot, MMIO or firmware
request. Addresses directly accessed: none. Loaded probe stays enabled for
this boot only; future boots default to disabled. Keep the hub unplugged.


## 2026-09-21 — future boots disarmed; single 0092 reconnect prepared

Config removal and initramfs rebuild succeeded. Extracted image contains
0092 appledrm with the expected ceb3aea107ee8 hash and no experiment config.
Current loaded module still has usb4_protocol_probe=Y. No probe has been
manually issued; no reboot or live parameter write occurred.

After this entry is committed and pushed, ask Oliver to attach the display
adapter and monitor to the OWC hub, then reconnect the hub to the SAME
LEFT-BACK Mac port used before. Keep eDP on. This invokes the one-attempt
0092 path: validate/connect 0x8001, request_display, existing crossbar
reselect, one HPD assertion (eight-second RPC timeout). No early HPD, no
second HPD, no physical PHY assigned, no automatic retry. Confirm actual
live route in the resulting kernel log.

Expected addresses: typec0, NHI 0x701f00000, ACIO 0x701ac0000, crossbar
0x70304c000, dcpext1 0x315c00000; panel DCP 0x389c00000. Normal connection
manager may create its standard tunnel after enumeration; no extra manual
tunnel or DP-alt-mode switch is requested. Existing crossbar driver's normal
MMIO runs as logged for this firmware experiment; no direct userspace MMIO.

If the panel blacks out, unplug the hub immediately and stop. If it stays
on, wait about 15 seconds and report external picture and keyboard function.
Capture after the user reports reconnection, using these exact commands:
```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-21-0092-replugged.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-21-0092-replug-kernel.log
```
No claim that the probe has run or succeeded yet. A reset must not be
followed by booting with the hub attached. 0090 backups and restore script
remain available as documented in the preceding reboot entry.

## 2026-09-21 — 0092 probe completed, external display still black

Oliver confirms eDP and the hub keyboard work; external display stays black.
The two prepared capture commands completed. Exactly one 0x8001 probe is
logged. After accepted validate/connect/request_display and crossbar reselect,
firmware reports APCALL 22 and 24 at about five seconds; HPD returns 0 but
there are no external modes, no link-rate or active-lane callbacks, and
DPRX remains 0. See notes/2026-09-21-0092-result.md.

The final lanes=4 diagnostic is merely the cached maximum set by
GET_MAX_LANE_COUNT, not active-lane training. No success is claimed.
The one-attempt guard is consumed; future-boot opt-in was already removed.
No additional hardware action was performed or scheduled after this result.

## 2026-09-22 — prepared native macOS 26 comparison, user-operated

The M4 is reachable as an SSH host. Oliver confirms both Macs can be cabled
and the M2 also has macOS 26. Native macOS reporting is selected before any
hypervisor setup. The M4 workspace and collector preparation changed only
user-owned files; no hardware connection, reboot or boot configuration change.

After this entry and collector are committed and pushed, provide this exact
user-operated sequence (not an unattended action): unplug the OWC hub and
all display adapters from the M2; shut down the M2 using the desktop power
menu; hold its power button to reach Startup Options and select its existing
macOS installation. Leave the inter-Mac USB cable disconnected for this
native-report step. No new OS install or boot/security setting change.

Normal shutdown/boot touches normal system hardware; no manual register
access is requested. Known M2 Linux addresses for context are panel DCP
0x389c00000, external DCPs 0x289c00000/0x315c00000, left-back hub path NHI
0x701f00000 / ACIO 0x701ac0000 / crossbar 0x70304c000. The collector uses
macOS registry APIs, not these physical addresses.

In a native M2 macOS Terminal, download the reviewed collector and take a
disconnected baseline using these exact commands:

```
curl -fL https://raw.githubusercontent.com/oliverlukschander/asahi-j416s-display/main/scripts/collect-macos-display.sh -o /tmp/collect-macos-display.sh
bash /tmp/collect-macos-display.sh disconnected
```

Then reconnect the known-working OWC hub, with keyboard, VMM7100 and monitor,
to the same left-back M2 port, wait for the picture, and run:

```
bash /tmp/collect-macos-display.sh hub
```

This is normal native macOS hotplug on a setup Oliver confirmed works there;
no Linux experimental parameter, manual tunnel or MMIO request. If the panel
blacks out or the system behaves unexpectedly, unplug the hub and stop.
Keep reports on the M2 Desktop for review; no automatic upload/commit.
No return reboot is scheduled or authorized by this log entry. This records
the proposed physical sequence before instructions, not its execution.

## 2026-09-22 — 0093 built offline; next action is user unplug only

Built appledrm and thunderbolt_apple with a default-disabled native DP-IN
handshake candidate, derived from this machine's preserved Apple 13.5
kernel cache. No module installation, reload, parameter write, ioremap,
MMIO operation or reboot has occurred. Evidence, guards, build hashes and
remaining limitations are in notes/2026-09-22-0093-native-dpin.md.

Read-only kernel journal confirms the CURRENT hub is on RIGHT typec2:
NHI 0xf01f00000, ACIO 0xf01ac0000, crossbar 0xf0304c000. Current boot is
d1045ee5-d459-4fa1-8175-76725cee1e07. The candidate refuses that route.

After this entry is committed and pushed, request this exact physical action:
Oliver unplugs the OWC hub cable from the M2's right USB-C port and leaves
it unplugged. There is no shell command and no manual register access for
this action. eDP must remain on. This entry records the requested action,
not a claim it has happened. Do not reconnect, install, reboot or execute
scripts/load-appledrm.sh under this entry.

The later candidate requires its own separate preflight/action entry with
exact commands and backups. Its only new resource would be LEFT-BACK DPIN0
0x701e50000..0x701e53fff, reads at +0,+0x0c,+0x10 and writes only +0x0c
bit0, controlled by the ACIO owner lock. Existing left-back crossbar is
0x70304c000 and external DCP is 0x315c00000. None is accessed in this step.

## 2026-09-22 — 0093 installation with hub unplugged

Oliver confirms the hub is unplugged and asks to proceed. Read-only checks
show no Thunderbolt devices and eDP enabled, kernel 7.1.12-2.5-1-ARCH.
The candidate hashes match the recorded build. Existing SDDM Apple DRM
readiness gate remains installed. No change to that gate is planned.

After committing and pushing this entry and scripts/manage-0093.py,
execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0093.py install
```

The reviewed script backs up and SHA-256-verifies these original files in
/var/tmp/j416s-0093-before, with manifest.json, before changing any target:

- /usr/lib/modules/7.1.12-2.5-1-ARCH/kernel/drivers/gpu/drm/apple/appledrm.ko
- /usr/lib/modules/7.1.12-2.5-1-ARCH/updates/appledrm.ko
- /usr/lib/modules/7.1.12-2.5-1-ARCH/kernel/drivers/thunderbolt/thunderbolt_apple.ko
- /usr/lib/modules/7.1.12-2.5-1-ARCH/updates/thunderbolt_apple.ko
- /boot/initramfs-linux-aurora.img

Installs appledrm SHA256
2e5cb7146f07aa7f23bfb4f03afd2c5e66c0e3efea81b68fc49fdfc2dafdcefc and
thunderbolt_apple SHA256
993526f4fef5b1c2042c5b57a0b6b397e1987893dff89552ee7dbcc184f228ad.
Writes /etc/modprobe.d/j416s-0093-native-dpin.conf with exactly:

```
options appledrm usb4_protocol_probe=1 usb4_native_dpin=1
options thunderbolt_apple dpin_native=1
```

Then runs depmod -a 7.1.12-2.5-1-ARCH and mkinitcpio -p linux-aurora,
extracts the image with lsinitcpio -x into a temporary directory, and checks
candidate module hashes and options. Automatic failure recovery restores
all five originals from the verified manifest, removes only the new config,
runs depmod and syncs. No live module reload, parameter write or reboot.

No physical address is mapped or accessed during this installation. New
candidate access on a later logged left-back hotplug would be DPIN0
0x701e50000..0x701e53fff, reads +0/+0xc/+0x10 and writes +0xc bit0;
ACIO owner 0x701ac0000, NHI 0x701f00000, existing crossbar 0x70304c000,
dcpext1 0x315c00000. Right-port candidate access is refused. Panel DCP
0x389c00000 and panel disp/PHY mappings are not added by the candidate.

Keep the hub unplugged. Reboot and subsequent hotplug require separate
entries, committed and pushed before either action. After candidate boot,
disarm persistent options and verify initramfs before permitting hotplug.

## 2026-09-22 — 0093 installed and verified; hub-absent reboot next

The logged installer completed successfully. All four installed module
files match the candidate hashes. The extracted initramfs contains the
candidate appledrm and exact opt-in configuration. No live driver reload
occurred. Hub absence was rechecked. eDP remains enabled.

Verified backups at /var/tmp/j416s-0093-before/manifest.json:
- Both original appledrm copies: ceb3aea107ee878ca1004098ae23f5b0ab2fdfa929dd244271224919e668e30f
- Both original thunderbolt_apple copies: cd83aafe75264173ba78f466ab88cee42e1ee4b1d1dc63c2f17c8d76fcb9b6b8
- Original initramfs: 73667d5cfb78ba19c4e10910e30f34e842d3debfe8736709ecd5cdaf69c1d2bc
- New verified initramfs: 8b27aa5b1893113e69667606057a0a167258585e0856e2f131893f08814c38bf

After this entry is committed and pushed, execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0093.py check && sudo -n systemctl reboot
```

This is a normal system reboot with the hub unplugged. Kernel boot accesses
normal platform resources, including panel DCP 0x389c00000 and external DCPs
0x289c00000/0x315c00000. The new DPIN0 resource 0x701e50000..0x701e53fff
must NOT be mapped without a later eligible USB4 ACTIVATE on left-back.
Left-back context: ACIO 0x701ac0000, NHI 0x701f00000, xbar 0x70304c000.
No manual register command is run. No alternate port or tunnel is forced.

Oliver has been told to leave the hub disconnected after the desktop
returns and report back. Next agent must verify new boot ID, eDP, module
parameters and logs. Before any requested replug, remove persistent test
options and rebuild/verify initramfs using the reviewed manage-0093.py disarm
operation, separately logged before execution. Current loaded flags remain
active for the bounded test while future boots revert to defaults.

If recovery is required, the prepared operation is
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0093.py restore
with hub absent; log it before execution. It verifies backup hashes,
restores all five originals, removes the candidate config, runs depmod,
and syncs. It does not reload live drivers or reboot. Do not restore only
appledrm: 0093 also changes thunderbolt_apple.

This entry records the imminent reboot, not its successful completion or
any display result. Never reconnect the hub while the panel is black.

## 2026-09-22 — 0093 boot verified; disarm future boots before testing

Oliver reports back after restart. New boot ID:
910bfa0d-a6e8-46b5-b27b-8d67922d7ad6. Running kernel is
7.1.12-2.5-1-ARCH, eDP is enabled, and no Thunderbolt devices are present.
Loaded appledrm usb4_protocol_probe=Y, usb4_native_dpin=Y and
thunderbolt_apple dpin_native=Y. No native DPIN activation/probe log appears.
The candidate has not run its hardware experiment.

After committing and pushing this entry, execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0093.py disarm
```

This removes only /etc/modprobe.d/j416s-0093-native-dpin.conf, executes
mkinitcpio -p linux-aurora, extracts the rebuilt image and verifies candidate
module hashes and absence of that config. It does not modify loaded module
parameters, reload drivers, reboot, map or access MMIO. The currently loaded
flags remain Y for this single-attempt test; subsequent boots default off.

Addresses for the later experiment (not accessed by disarming): left-back
DPIN0 0x701e50000..0x701e53fff, reads +0/+0xc/+0x10 and writes +0xc bit0;
ACIO 0x701ac0000, NHI 0x701f00000, crossbar 0x70304c000,
dcpext1 0x315c00000. Keep hub unplugged until successful image verification
and a separate committed/pushed hotplug entry. No hotplug is authorized by
this entry alone.

## 2026-09-22 — future boots disarmed; one left-back 0093 hotplug next

The logged disarm completed and verified the rebuilt initramfs: candidate
appledrm hash is correct, and j416s-0093-native-dpin.conf is absent from both
/etc/modprobe.d and the extracted image. Disarmed initramfs SHA256:
94a7d8a1e9e58bf0f7f055e43853eeedf97fc27330ca79455a4ec19aea800b75.
Current boot 910bfa0d-a6e8-46b5-b27b-8d67922d7ad6 still has all three loaded
read-only flags Y, no Thunderbolt devices and eDP enabled.

After committing and pushing this entry, request this exact physical action:
connect the existing OWC hub, with monitor adapter and keyboard still on it,
to the M2 LEFT-BACK USB-C port (left-side USB-C nearest the hinge/MagSafe).
Do not use the right port or left-front port. This physical connection is
the trigger; no shell parameter write, insmod, driver reload or reboot.
Wait about 15 seconds and report laptop picture, external picture and hub
keyboard operation. If eDP blacks out, unplug the hub immediately and stop.
Do not repeat the connection or reboot with the hub attached.

The logged candidate automatically handles one eligible request, target
0x8001, dcpext1 0x315c00000 / typec0 / unit0 / mux index2 / DPIN0. The
normal USB4 stack supplies the tunnel; do not build another tunnel. Confirm
live NHI 0x701f00000 and ACIO 0x701ac0000 from the new kernel messages.

During ACTIVATE, existing crossbar selection is repeated at 0x70304c000
(resource size 0x4000, including existing control offsets 0x000..0x034,
0x050/0x070 and status reads including 0x800). The new ACIO-owned operation
reserves and maps exactly 0x701e50000..0x701e53fff once, with nonposted
mapping and the ACIO cable-power lock held. It reads HPD at 0x701e50000,
CONTROL at 0x701e5000c and ACK at 0x701e50010. If HPD is high it clears
CONTROL bit0 and polls ACK bit0 for up to one second. On a failed handshake
it restores only the original CONTROL bit0; on DEACTIVATE it requests bit0=1
and waits for ACK. Other bits are preserved. There is no write to DPIN +8,
panel mapping, RC analog operation added by this candidate, or physical PHY
mode change. No default-on or repeating native test is configured.

After Oliver reports the result, use these exact read-only capture commands:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0093-replugged.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0093-replug-kernel.log
```

The native handshake result alone is not display success. Check actual
SET_LINK_RATE, SET_ACTIVE_LANE_COUNT > 0, DPRX=1, Hyprland monitor list and
Oliver's confirmation of picture and keyboard. This entry schedules the
single physical test; it does not claim the connection or experiment ran.

## 2026-09-22 — 0093 discovery success; modeset mismatch; prepare right-port 0094

Oliver confirms the hub is in the left port but no picture appears, and
requests the RIGHT USB-C port for the next test. The two previously logged
capture commands completed. Preserve full reports privately and commit the
sanitized event excerpt plus notes/2026-09-22-0093-result.md.

The first native handshake completed; firmware requested 0x0a link rate and
four active lanes, delivered 22 TimingElements modes and connected hotplug,
and host DP IN reported DPRX_DONE=1. eDP stays enabled. Hyprland exposes the
BenQ at 0x0 and its ATOMIC_TEST_ONLY requests fail with EINVAL. Read-only
encoder inspection confirms userspace selected CRTC69 while the connector
only permits CRTC88. No new MMIO/probe/retry was performed for this analysis.

Built 0094 offline with a fixed initial right-port CRTC mask and matching
route constraint, native target0x8021 and right DPIN0 resource0xf01e50000.
Both modules compile; nine mock tests pass. Installer/restore helper is
prepared but not executed. 0093 future boot flags remain disarmed.

After this entry is committed and pushed, request exactly this physical
action: Oliver unplugs the hub from LEFT-BACK and leaves it disconnected
before installation. No shell command, reload or reboot is part of this
request. Current left path: ACIO0x701ac0000, NHI0x701f00000,
xbar0x70304c000, dcpext1 0x315c00000. Normal candidate DEACTIVATE, if called
while ACIO is still powered, may set DPIN0 CONTROL0x701e5000c bit0=1 and
read ACK0x701e50010; its ACIO owner lock prevents access after cable power
teardown. This is the same logged 0093 deactivation behavior, not a new probe.

Do not move directly to right while 0093 is loaded: its one-attempt guard is
consumed and its native route is left-only. The next fresh-boot candidate
uses right ACIO0xf01ac0000, NHI0xf01f00000, xbar0xf0304c000 and native
DPIN0 0xf01e50000..0xf01e53fff. Installation, reboot and right hotplug
must each be separately logged and pushed before execution. This entry
records the unplug request only, not execution or a working monitor.

## 2026-09-22 — Install 0094 with hub disconnected

Oliver reports unplug complete. Read-only preflight confirms j416s, running
7.1.12-2.5-1-ARCH, no external Thunderbolt router, and eDP enabled.
After committing and pushing this entry, execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0094.py install
```

This backs up both kernel and updates copies of appledrm.ko and
thunderbolt_apple.ko plus /boot/initramfs-linux-aurora.img into
/var/tmp/j416s-0094-before, with verified SHA256 manifest. Installs matching
0094 modules, writes /etc/modprobe.d/j416s-0094-native-dpin.conf containing
options appledrm usb4_protocol_probe=1 usb4_native_dpin=1 and options
thunderbolt_apple dpin_native=1, runs depmod -a 7.1.12-2.5-1-ARCH and
mkinitcpio -p linux-aurora, then verifies extracted image modules/options.
On installation failure it restores the five backed-up files and removes
that config. No live reload, MMIO, mapping, cable action or reboot here.

Candidate appledrm SHA256:
a6ec3ac3a4bd4a06d0726cdfd0e21f1243cd6d4f58d360d0c7649f9b3c99c449
Candidate thunderbolt_apple SHA256:
26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198

Future right-port test addresses (not accessed by installation): ACIO
0xf01ac0000, NHI 0xf01f00000, xbar 0xf0304c000, dcpext1 0x315c00000,
DPIN0 0xf01e50000..0xf01e53fff; HPD +0, CONTROL +0xc, ACK +0x10.
Reboot and physical connection require separate pre-action log entries.

## 2026-09-22 — Boot verified 0094 with hub absent

Installation completed successfully; extracted initramfs module hashes and
candidate options verified. A second preflight confirms hub absent.
New /boot/initramfs-linux-aurora.img SHA256:
7b22d3cca8a595e3caa619dac3224aa1ea4bf3885836c3edf390046e017b13ac
Backup /var/tmp/j416s-0094-before/manifest.json verifies both original
appledrm copies as 2e5cb7146f07aa7f23bfb4f03afd2c5e66c0e3efea81b68fc49fdfc2dafdcefc,
both thunderbolt_apple copies as 993526f4fef5b1c2042c5b57a0b6b397e1987893dff89552ee7dbcc184f228ad,
and original image as 94a7d8a1e9e58bf0f7f055e43853eeedf97fc27330ca79455a4ec19aea800b75.

After committing and pushing this entry, execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0094.py check && sudo -n systemctl reboot
```

Hub remains unplugged throughout restart and until postboot checks and
future-boot disarm are complete. No native DPIN ACTIVATE is eligible with
hub absent. The armed candidate targets only right typec2, dcpext1
0x315c00000, ACIO 0xf01ac0000, NHI 0xf01f00000, xbar 0xf0304c000,
DPIN0 0xf01e50000..0xf01e53fff (HPD +0, CONTROL +0xc, ACK +0x10).
No manual mapping or register operation accompanies this reboot command.

Recovery if necessary, with hub absent and separately logged before use:
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0094.py restore
This restores all five verified backup files and removes candidate options;
it does not reload or reboot. Postboot next step is verify eDP and module
flags, then log/push and execute manage-0094.py disarm BEFORE asking Oliver
to connect the hub to RIGHT. This entry records planned reboot, not success.

## 2026-09-22 — 0094 boot verified; disarm future boots

Boot 17277113-8b54-4315-87fb-867feccb3faa has eDP enabled at
3456x2160@120, all three experiment flags Y, hub absent, and no native
handshake attempted. Read-only modetest -M apple -e confirms right encoder
97 has initial possible_crtcs=0x4 (other USB encoders 0x6), as intended.

After this entry is committed and pushed execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0094.py disarm
```

Removes /etc/modprobe.d/j416s-0094-native-dpin.conf, rebuilds initramfs via
mkinitcpio -p linux-aurora, verifies candidate hashes and options absent,
and syncs. Loaded flags remain Y for this boot only. No live module reload,
parameter write, mapping, MMIO or reboot. Right path addresses remain
ACIO 0xf01ac0000, NHI 0xf01f00000, crossbar 0xf0304c000, dcpext1
0x315c00000, DPIN0 0xf01e50000..0xf01e53fff; none accessed by this command.

## 2026-09-22 — Schedule one 0094 RIGHT-port hotplug

Future-boot disarm completed with extracted image verification; current
boot retains experiment flags. Disarmed image SHA256: 33c6ed09b72c6357c2a8f902dfdead616a52d22f09e4d1a8c7bc4d9dc1080982.

After committing and pushing this entry, request exactly: Oliver connects
the hub (monitor and keyboard attached) to the RIGHT USB-C port once.
If eDP goes black, unplug the hub and stop. Do not reboot with hub attached.
This is a physical action; no shell command initiates the connection.

Expected live path must be confirmed from kernel messages: typec2,
NHI 0xf01f00000, ACIO 0xf01ac0000, dcpext1 0x315c00000. Candidate
0094 permits one native protocol request target 0x8021, core1/atc2/die0,
unit0/mux index2, using the normal USB4-created tunnel. No second tunnel.
Existing crossbar routing is selected at 0xf0304c000 (resource 0x4000,
existing controls 0x000..0x034, 0x050/0x070 and status including 0x800).
ACIO owner reserves/maps DPIN0 0xf01e50000..0xf01e53fff nonposted while
holding cable-power lock. Reads HPD 0xf01e50000, CONTROL 0xf01e5000c,
ACK 0xf01e50010. With HPD high, clears CONTROL bit0 and polls ACK bit0
for at most one second; failure restores original CONTROL bit0 preserving
other bits. DEACTIVATE requests CONTROL bit0=1 and polls ACK under the
same power lock. No DPIN+8 write, panel mapping, manual PHY mode or added
analog operation. The loaded test is one-attempt; no automatic retest.

After Oliver reports connection, capture with these read-only commands:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0094-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0094-right-kernel.log
modetest -M apple -e
```

Keep raw captures private/untracked. Check nonzero link rate, lane count,
DPRX, TimingElements, dcpext1 digital-out modeset and actual compositor
resolution, plus Oliver's confirmation of picture and keyboard operation.
This entry schedules the test; it does not assert it has run or succeeded.

## 2026-09-22 — 0094 right-port connection reaches active modeset

Oliver reports hub plugged in. Executed the three previously logged
read-only capture commands. Right-port native handshake succeeds, link
rate 0x0a / four lanes, DPRX_DONE=1, and 22 modes arrive. dcpext1 completes
2560x1440 modeset; encoder97 now uses CRTC88. Hyprland USB-3 is enabled
at 2560x1440@59.951 beside enabled eDP-1 at 3456x2160@120. Physical picture
and keyboard confirmation requested, pending. No extra hardware probe.
See notes/2026-09-22-0094-result.md and sanitized result excerpt. Raw logs
remain untracked with private copies. Future boots remain disarmed.

## 2026-09-22 — 0094 physical result correction

Oliver reports external screen inactive, no visible picture. Successful
link training and accepted modeset did not achieve video output. Read-only
DRM state shows CRTC88 active with a Hyprland framebuffer; compositor logs
show pending-page-flip / EBUSY. Investigating frame completion and native
crossbar/link-change implementation offline. No new hardware action.

## 2026-09-22 — Bounded software frame-callback trace

Execute after commit/push: sudo -n python3 /tmp/j416s-0094-trace.py
Script creates isolated tracing instance /sys/kernel/tracing/instances/j416s0094,
enables only dcp iomfb_swap_submit, iomfb_swap_complete,
iomfb_swap_complete_intent_gated and iomfb_abort_swap_ap_gated for 10 seconds,
stops tracing, saves /tmp/j416s-0094-frame-trace.txt, removes the instance.
No global trace modification, modeset, live parameter write, hardware mapping
or MMIO operation is initiated. Current hardware remains right ACIO
0xf01ac0000 / xbar0xf0304c000 / DPIN0 0xf01e50000 / dcpext1 0x315c00000.

## 2026-09-22 — 0095 built; request right-port unplug before installation

0094 picture failure remains. Software trace completed and removed its
isolated instance. Offline native analysis supports testing crossbar bring-up
at DID_CHANGE_LINK_CONFIG, after the first nonzero link rate. 0095 kernel
commit37c69d3 builds and passes checkpatch; patch, notes and pinned installer
are pushed. Nothing installed or loaded. No extra MMIO reads performed.

After committing and pushing this entry, request exactly this physical
action: Oliver unplugs hub from RIGHT USB-C and leaves it disconnected.
No shell command initiates unplug; no install/reboot accompanies it.
The currently loaded 0094 path is dcpext1 0x315c00000, NHI 0xf01f00000,
ACIO 0xf01ac0000 and xbar0xf0304c000. Normal driver teardown may deselect
that crossbar; its previously logged existing register access is unchanged.
0094 native DEACTIVATE, if called while ACIO remains powered, sets DPIN0
CONTROL 0xf01e5000c bit0=1 and polls ACK0xf01e50010, under ACIO owner lock,
using existing mapping0xf01e50000..0xf01e53fff. No manual register command.
Installation/reboot of 0095 must be separately logged/pushed after absence
is verified. Never reboot with hub attached; eDP black means unplug and stop.

## 2026-09-22 — Install 0095 with hub absent

Oliver says proceed. manage-0095.py check confirms correct kernel/machine,
no external Thunderbolt router and matching candidate hashes. eDP enabled.
After this entry is committed/pushed execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0095.py install
```

Installer verifies backups of both kernel/updates copies of appledrm.ko and
thunderbolt_apple.ko and /boot/initramfs-linux-aurora.img under
/var/tmp/j416s-0095-before with SHA256 manifest. Installs matching candidates,
writes /etc/modprobe.d/j416s-0095-native-dpin.conf with options appledrm
usb4_protocol_probe=1 usb4_native_dpin=1 and options thunderbolt_apple
dpin_native=1. Runs depmod -a 7.1.12-2.5-1-ARCH, mkinitcpio -p linux-aurora,
verifies extracted image module hashes/options and syncs. On failure restores
the five original files and removes new config. No live reload or reboot.

appledrm SHA256 eb6122ba4ce9a30d357d02deb237545c8f9d943cf6769fe6f2947f98e13346a2
thunderbolt_apple SHA256 26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198

No MMIO or mapping during installation. Future right-port path remains
ACIO0xf01ac0000, NHI0xf01f00000, xbar0xf0304c000, dcpext1 0x315c00000,
DPIN0 0xf01e50000..0xf01e53fff (HPD+0, CONTROL+0xc, ACK+0x10).
Reboot and physical hotplug require separate pre-action log entries.

## 2026-09-22 — Reboot into verified 0095 with hub absent

Installation succeeded; extracted initramfs module hashes and candidate
options verified. Second preflight confirms hub absent. New image SHA256:
fea06cc3c9ffd25da7e5ea4f9f0d4594b90117bbbfe4fb4d60eebc04987a9d6b

After committing/pushing this entry execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0095.py check && sudo -n systemctl reboot
```

Keep hub unplugged through reboot and postboot checks. No eligible native
DPIN activation occurs without the hub. Candidate only targets right typec2,
dcpext1 0x315c00000, ACIO0xf01ac0000, NHI0xf01f00000,
xbar0xf0304c000, DPIN0 0xf01e50000..0xf01e53fff (HPD+0,
CONTROL+0xc, ACK+0x10). No manual MMIO operation accompanies this command.

Verified originals and manifest are in /var/tmp/j416s-0095-before. Recovery
with hub absent, separately logged before execution:
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0095.py restore
This restores both copies of both modules and original image, removes 0095
options, depmods/syncs, without reload or reboot. After return verify eDP
and loaded flags, then separately log/push/execute manage-0095.py disarm
BEFORE asking for a right-port hotplug. No claim of successful boot or
visible external picture is made by this entry.

## 2026-09-22 — 0095 requires two restarts; hold test and disarm

Oliver reports two restarts before desktop. Current boot
bfac7473-5184-4715-9154-dad36350742a has eDP enabled, all three experiment
flags Y, correct candidate hashes, and hub absent. Journal boot list shows
only prior 0094 boot17277113 and current boot; no intervening failed attempt
is preserved there. Cause and whether failure occurred on shutdown or startup
remain undetermined. Do not schedule hotplug while investigating.

After this entry is committed/pushed execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0095.py disarm
```

Removes /etc/modprobe.d/j416s-0095-native-dpin.conf, runs mkinitcpio -p
linux-aurora, verifies extracted candidate hashes and absence of that config,
then syncs. Current loaded flags remain Y; this only disarms future boots.
No module reload, reboot, live parameter write or MMIO. No addresses accessed;
experimental right path remains ACIO0xf01ac0000, NHI0xf01f00000,
xbar0xf0304c000, dcpext1 0x315c00000, DPIN0 0xf01e50000..0xf01e53fff.

## 2026-09-22 — 0095 future boots disarmed; boot failure cause unresolved

manage-0095.py disarm completed successfully and verified rebuilt image.
Disarmed image SHA256: 1910d07e0f96bdddab3055d2d9aabd63b4f9493112334ce27ac8d68848e0324d
Current bfac7473 boot retains loaded flags Y but hub is absent; no native
DPIN/protocol-probe activity appears. Panel modeset completes at14.502s,
SDDM readiness gate reports eDP modes at14.443s and session starts normally.
Current boot's systemd-pstore reports empty /sys/fs/pstore; archived pstore
directory also empty. Previous persisted boot is17277113 (0094); its journal
ends during orderly filesystem unmount, with no intervening failed-boot
journal. Therefore neither a 0095 kernel regression nor a specific shutdown
or boot failure is established. Oliver's report of two restarts is recorded,
and clarification of screen state and cable state is pending. Hold physical
hub test; no further reboot, module reload or hardware action scheduled.

## 2026-09-22 — Resume with one 0095 right-port hotplug

Oliver confirms hub was unplugged throughout the troublesome restart and
explicitly asks to continue. Current boot bfac7473 remains stable with eDP
enabled, all three loaded flags Y, hub absent, candidate hashes matching,
and no native DPIN/protocol probe activity. Future-boot options remain
absent; disarmed image was verified in the previous entry. The restart
cause is unresolved; this test does not require another reboot.

After this entry is committed/pushed, request exactly: connect hub with
monitor and keyboard attached to RIGHT USB-C once. If eDP goes black,
unplug immediately and stop. Do not reboot with hub attached or retry.
No shell command initiates the physical connection.

Expected live path: typec2, NHI0xf01f00000, ACIO0xf01ac0000,
crossbar0xf0304c000 (size0x4000), dcpext1 0x315c00000, target0x8021.
Normal USB4 stack supplies existing tunnel0:5 to1:19; no manual tunnel or
DP altmode change. ACTIVATE reselects existing right crossbar using existing
register operations at offsets0x000..0x034, 0x050/0x070 and status reads
including0x800. ACIO owner maps/reserves native DPIN0
0xf01e50000..0xf01e53fff nonposted with its cable-power lock held, reads
HPD0xf01e50000, CONTROL0xf01e5000c, ACK0xf01e50010; active handshake
clears CONTROL bit0 and polls ACK for up to1s, restores original bit0 on
failure preserving other bits. DEACTIVATE requests CONTROL bit0=1.
No DPIN+8, panel, PHY-mode or added analog write.

0095 adds ONE additional reselect of that same crossbar on the first
DID_CHANGE_LINK_CONFIG with nonzero cached rate, using the existing guarded
native helper. ACIO should return cached active success without another
handshake. Repeated nonzero link-up callbacks are refused. This is a bounded
sequencing experiment, not a proven video fix or reconnect implementation.

After connection, capture with these exact read-only commands:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0095-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0095-right-kernel.log
modetest -M apple -e
```

Keep raw captures private/untracked. Require Oliver's visible-picture and
keyboard confirmation, plus enabled eDP, link rate/lanes/DPRX/modeset and
frame completion evidence. Hyprland dimensions alone are not success.

## 2026-09-22 — 0095 no picture; 0096 built offline; request unplug

Oliver confirms no external picture; other operation normal, no keyboard
attached. Logged captures complete. New link-config callback ran successfully,
but pending page flip persists. Offline native comparison identifies two
DPIN0 teardown errors; corrected module builds and RAM register tests pass.
See notes/2026-09-22-0096-crossbar-teardown.md. No new live hardware action.

After committing/pushing, request exactly: unplug hub from RIGHT USB-C and
leave it unplugged before installing0096. No shell command initiates unplug.
Loaded0095 teardown may deselect xbar0xf0304c000 and, if powered,
request native inactive CONTROL0xf01e5000c bit0=1 and poll ACK0xf01e50010
under the ACIO0xf01ac0000 power lock. Existing DPIN mapping is
0xf01e50000..0xf01e53fff, NHI0xf01f00000, dcpext1 0x315c00000.
No manual MMIO command or reboot accompanies this request. Installation
and reboot need separate logged/pushed actions after absence is verified.

## 2026-09-22 — Install 0096 after confirmed unplug

Oliver reports unplug complete; preflight verifies hub absent, correct
kernel/machine, matching candidate hashes and eDP enabled. After commit/push:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0096.py install
```

Back up SEVEN originals under /var/tmp/j416s-0096-before with verified
SHA256 manifest: kernel and updates copies of appledrm.ko,
thunderbolt_apple.ko and mux-apple-display-crossbar.ko, plus
/boot/initramfs-linux-aurora.img. Install matching module copies and write
/etc/modprobe.d/j416s-0096-native-dpin.conf: options appledrm
usb4_protocol_probe=1 usb4_native_dpin=1; options thunderbolt_apple
dpin_native=1. Run depmod -a 7.1.12-2.5-1-ARCH and mkinitcpio -p
linux-aurora; verify image hashes/options, sync. Failure restores all seven
originals and removes config. No live reload, MMIO, mapping or reboot.

Crossbar SHA256 4bb0096ac4560f2da103148f7147403d43434ace76caa20c83cb704fa784a930
appledrm SHA256 eb6122ba4ce9a30d357d02deb237545c8f9d943cf6769fe6f2947f98e13346a2
thunderbolt SHA256 26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198

Future right-port addresses (not accessed by installer): ACIO0xf01ac0000,
NHI0xf01f00000, crossbar0xf0304c000, dcpext1 0x315c00000,
DPIN0 0xf01e50000..0xf01e53fff; HPD+0, CONTROL+0xc, ACK+0x10.
0096 DPIN0 crossbar teardown clears source bit at+0x00c and restores
reset at+0x024 instead of setting+0x020. Requires fresh boot, separately
logged and pushed; keep hub unplugged until postboot verification/disarm.

## 2026-09-22 — Reboot into verified 0096 with hub absent

Installation succeeded, seven-file backup manifest verified, extracted boot
image candidate hashes/options verified. Repeat preflight confirms hub absent.
New image SHA256: 7285438374cf5c03b11786abd39f0f5bfaf8ce07e650fa0ac8c94421dc4bd45e

After this entry is committed/pushed, execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0096.py check && sudo -n systemctl reboot
```

Keep hub unplugged throughout reboot and postboot verification/disarm. No
manual MMIO or reload accompanies this command. Normal crossbar module
probe initializes platform muxes; new teardown correction only applies to
DPIN0 with an existing selected source. Hub-absent boot does not qualify
for native DPIN ACTIVATE. Right experimental path: crossbar0xf0304c000,
ACIO0xf01ac0000, NHI0xf01f00000, dcpext1 0x315c00000,
DPIN0 0xf01e50000..0xf01e53fff (HPD+0, CONTROL+0xc, ACK+0x10).

Known uncertainty: prior restart required two attempts; no intervening failed
boot journal persisted, cause unresolved. Oliver subsequently authorized
continuation; report which startup screen appears if this recurs. Do not
connect hub to investigate a boot failure.

Recovery, hub absent and separately logged before use:
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0096.py restore
Restores all seven originals from /var/tmp/j416s-0096-before after hash
verification, removes candidate options, depmods/syncs; no reboot/reload.
After return verify eDP, correct loaded modules/options and no hub activity,
then separately log/push/execute manage-0096.py disarm before right hotplug.
This records a planned reboot, not a successful boot or display fix.

## 2026-09-22 — 0096 boot verified; disarm future boots

Oliver reports back after reboot. Boot c614801c-b80f-439e-8e64-34a519647cd0
has eDP enabled and panel modeset completed at11.801s, all three loaded
experiment flags Y, hub absent, candidate hashes matching. Loaded crossbar
.note.gnu.build-id bytes exactly match the0096 candidate ELF section.
No native DPIN/protocol-probe activity appears. srcversion is unavailable,
so it was not used to identify the loaded module.

After commit/push execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0096.py disarm
```

Removes /etc/modprobe.d/j416s-0096-native-dpin.conf, rebuilds image with
mkinitcpio -p linux-aurora, verifies candidate image hashes and options absent,
syncs. Loaded flags remain Y for this boot only. No MMIO, mapping, live
parameter write, reload or reboot. Right path addresses unchanged and not
accessed: xbar0xf0304c000, ACIO0xf01ac0000, NHI0xf01f00000,
dcpext1 0x315c00000, DPIN0 0xf01e50000..0xf01e53fff.

## 2026-09-22 — Schedule one 0096 RIGHT-port hotplug

Future-boot disarm completed with extracted image verification. Image SHA256:
1910d07e0f96bdddab3055d2d9aabd63b4f9493112334ce27ac8d68848e0324d
Current boot remains armed; no eligible test has run yet.

After commit/push request exactly: Oliver plugs the hub with monitor attached
into RIGHT USB-C once. Keyboard was absent in0095 and may remain absent;
do not claim its functionality tested. If eDP goes black, unplug immediately
and stop. Do not reboot with hub attached or repeat hotplug. No shell command
initiates this physical action.

Expected path to confirm in logs: typec2, NHI0xf01f00000, ACIO0xf01ac0000,
crossbar0xf0304c000 size0x4000, dcpext1 0x315c00000, target0x8021.
Normal USB4 creates tunnel0:5 to1:19. ACTIVATE selects existing crossbar;
first nonzero DID_CHANGE_LINK_CONFIG reselects it once. Existing controls
0x000..0x034,0x050/0x070 and status reads including0x800 are used.
0096 DPIN0 teardown clears source bit2 at0xf0304c00c and restores reset
bit0 at0xf0304c024; it does NOT write the former erroneous+0x020 path.
Normal select again clears reset+0x024 and sets source+0x00c.

ACIO reserves/maps DPIN0 0xf01e50000..0xf01e53fff nonposted under its
cable-power lock, reads HPD0xf01e50000, CONTROL0xf01e5000c and
ACK0xf01e50010. Native active clears CONTROL bit0, polls ACK up to1s,
restores original bit0 on failure preserving other bits. DEACTIVATE requests
CONTROL bit0=1. The link-config callback should find ACIO already active
and return cached success. No DPIN+8, panel mapping, manual PHY mode,
new analog operation or second tunnel.

After Oliver reports connection, exact read-only captures:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0096-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0096-right-kernel.log
modetest -M apple -e
```

Retain raw logs privately/untracked. Require actual visible picture rather
than compositor dimensions alone; inspect lane/rate/DPRX, modeset, page-flip
completion and eDP preservation. This entry schedules a test, not success.

## 2026-09-22 — 0096 no picture; diagnostic0097 built; request unplug

Logged0096 captures completed. Reset+0x024 now restores correctly and
+0x020 remains0, but visible picture absent and page flip remains pending.
Link training/modeset success alone is insufficient. Prepared diagnostics-only
0097 with first-frame milestones; no further hardware behavior change.
Build/checkpatch pass. Nothing installed. See0097 first-frame notes.

After commit/push request: unplug hub from RIGHT USB-C and leave it
unplugged before diagnostic installation. No shell command initiates unplug.
Normal loaded0096 teardown affects xbar0xf0304c000 (including corrected
source+0x00c and reset+0x024); native DEACTIVATE may set DPIN CONTROL
0xf01e5000c bit0=1 and poll ACK0xf01e50010 under ACIO0xf01ac0000
power lock while powered, using existing0xf01e50000..0xf01e53fff mapping.
NHI0xf01f00000, dcpext1 0x315c00000. No manual MMIO or reboot with
this request. Installation/reboot must be separately logged/pushed.

## 2026-09-22 — Correct 0097 installer checksum; install hub absent

Oliver confirms unplug. Initial read-only check refused crossbar checksum:
naive0096-to0097 script rename accidentally changed matching digits inside
its pinned hash. Actual module still matches verified0096 hash4bb0096...;
corrected installer literal and reran check successfully. No installation
or hardware action occurred on the failed check. eDP enabled, hub absent.

After committing/pushing this entry and corrected installer execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0097.py install
```

Back up and verify seven files in /var/tmp/j416s-0097-before: kernel/updates
copies of appledrm.ko, thunderbolt_apple.ko, mux-apple-display-crossbar.ko,
and /boot/initramfs-linux-aurora.img. Install pinned copies, write
/etc/modprobe.d/j416s-0097-native-dpin.conf with options appledrm
usb4_protocol_probe=1 usb4_native_dpin=1 and options thunderbolt_apple
dpin_native=1, depmod -a 7.1.12-2.5-1-ARCH, mkinitcpio -p linux-aurora,
verify extracted image modules/options and sync. Failure restores seven
originals and removes config. No live reload, MMIO or reboot.

appledrm b536c83e9f0e678aa0df3df24d146e5aca3fff5eebac4865bfef4e144af19103
crossbar 4bb0096ac4560f2da103148f7147403d43434ace76caa20c83cb704fa784a930
thunderbolt 26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198

Future right route (not accessed by installation): xbar0xf0304c000,
ACIO0xf01ac0000, NHI0xf01f00000, dcpext1 0x315c00000,
DPIN0 0xf01e50000..0xf01e53fff (HPD+0, CONTROL+0xc, ACK+0x10).
0097 only adds first-frame logs; hardware behavior remains0096.
Reboot and later physical connection require separate logged/pushed entries.

## 2026-09-22 — Reboot verified diagnostic0097 with hub absent

Installer completed successfully; seven original files backed up/verified,
extracted image candidate hashes and options verified. Repeated preflight
confirms hub absent. New image SHA256:
54fbb8e86b79391af0d62961a8a9b2b207bd283d940c4fde50a758e2ccc6f940

After commit/push execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0097.py check && sudo -n systemctl reboot
```

Keep hub unplugged until postboot checks and future-boot disarm complete.
No native ACTIVATE is eligible without hub. No manual MMIO/reload with
this command. Normal crossbar probe is unchanged from0096. Experimental
right path: xbar0xf0304c000, ACIO0xf01ac0000, NHI0xf01f00000,
dcpext1 0x315c00000, DPIN0 0xf01e50000..0xf01e53fff (HPD+0,
CONTROL+0xc, ACK+0x10). 0097 adds first-frame logs only.

Recovery with hub absent, separately logged before use:
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0097.py restore
This verifies/restores all seven originals from /var/tmp/j416s-0097-before,
removes new config, depmods and syncs, without reload/reboot. After return
verify loaded modules and eDP, then log/push/execute manage-0097.py disarm
before asking for right-port connection. This entry is intent, not success.

## 2026-09-22 — Verify diagnostic0097 boot; disarm future boots

Boot fcc1d903-4f1a-445b-a8cc-d4da6f826c9a: hub absent, eDP enabled,
three experiment flags Y, candidate hashes match. Loaded appledrm and
crossbar build-ID notes exactly match candidate ELF sections. Panel modeset
completes11.175s; no native probe or first-frame experiment activity.

After commit/push execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0097.py disarm
```

Remove /etc/modprobe.d/j416s-0097-native-dpin.conf, rebuild with mkinitcpio
-p linux-aurora, verify image module hashes/options absent, sync. Loaded
flags remain Y for this boot. No live reload, MMIO, mapping, parameter write
or reboot. Right addresses unchanged, not accessed by disarm:
xbar0xf0304c000, ACIO0xf01ac0000, NHI0xf01f00000, dcpext1 0x315c00000,
DPIN0 0xf01e50000..0xf01e53fff (HPD+0, CONTROL+0xc, ACK+0x10).

## 2026-09-22 — Schedule one diagnostic0097 right-port connection

Disarm completed and extracted image verified. Disarmed image SHA256:
74fded6167a80366ced0440d30124c49199985089848aacbdd05cbc442feba47
Current boot retains flags; no test performed yet.

After commit/push request exactly: connect hub with monitor attached to
RIGHT USB-C once. If eDP blacks out, unplug immediately and stop. No
reboot with hub attached, no repeated connection. Keyboard may remain
absent; do not claim tested. No shell command initiates physical hotplug.

Same0096 hardware behavior: typec2, NHI0xf01f00000, ACIO0xf01ac0000,
dcpext1 0x315c00000, target0x8021, normal tunnel0:5 to1:19. Existing
crossbar0xf0304c000 size0x4000 is selected at ACTIVATE and reselected
once after first nonzero link configuration. Existing controls offsets
0x000..0x034,0x050/0x070 and status reads including0x800 are used.
DPIN0 teardown clears source bit2 at+0x00c, restores reset bit0 at+0x024;
it does not set the erroneous+0x020 path. Native ACIO reserves/maps
0xf01e50000..0xf01e53fff nonposted with cable-power lock, reads
HPD0xf01e50000, CONTROL0xf01e5000c and ACK0xf01e50010. Activation
clears CONTROL bit0, polls ACK at most1s, restores original bit on failure;
deactivation requests bit0=1. Link-config helper uses cached active state.
No DPIN+8, panel mapping, manual PHY or analog write, or second tunnel.
0097 adds software milestone logs only, not new hardware operations.

After connection capture exactly:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0097-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0097-right-kernel.log
modetest -M apple -e
```

Inspect USB4 frame milestones to locate the stall. Raw captures remain
private/untracked. Visible picture must be confirmed by Oliver; software
mode dimensions and completion logs alone do not prove visible output.

## 2026-09-22 — 0097 first frame completes; bounded software trace

Logged captures complete. Boot fcc1d903 shows external frame2 start,
submit acknowledgement ret0 and actual completion at170.336s. This disproves
the unqualified earlier assertion that the first external frame never
completes. Physical picture confirmation requested, pending. Do not infer
pixel transport from completion alone or stall from transient compositor logs.

After commit/push execute exactly:
sudo -n python3 /tmp/j416s-0097-trace.py
Creates isolated /sys/kernel/tracing/instances/j416s0097; enables only
DCP swap submit, complete, complete intent and abort trace events for10s,
stops tracing, writes /tmp/j416s-0097-frame-trace.txt, removes instance.
No modeset, parameter write, MMIO, mapping, module reload or reboot initiated.
Hardware remains right xbar0xf0304c000, ACIO0xf01ac0000, NHI0xf01f00000,
dcpext1 0x315c00000, DPIN0 0xf01e50000..0xf01e53fff.

## 2026-09-22 — 0097 no signal; prepare0098 and request hub removal

Oliver confirms black/no signal despite external frame2 completion.
Software trace completed; private evidence preserved. No additional live
MMIO or parameter writes were performed. 0098 kernel commit92a9dee adds
a one-shot existing-crossbar snapshot after completion, no register writes.
Both modules build; RAM-only27-cycle teardown checks pass; hashes pinned
in manage-0098.py and notes/2026-09-22-0098-after-frame.md.

After this entry is committed and pushed, request exactly: unplug the hub
from the RIGHT USB-C port and report when unplugged. No shell command
initiates this physical action. Current0097 handles normal disconnect;
0098 is not installed or loaded. No reboot or reload yet.

Disconnect uses the existing right route: typec2, NHI0xf01f00000,
ACIO0xf01ac0000, dcpext1 0x315c00000, crossbar0xf0304c000 size0x4000.
Existing crossbar teardown touches controls+0x000,+0x004,+0x008,+0x00c,
+0x014,+0x018,+0x01c,+0x024,+0x028,+0x02c,+0x030,+0x034,+0x050,+0x070,
and its existing status reads include+0x800,+0x820,+0x81c. Native DPIN0
resource0xf01e50000..0xf01e53fff deactivation requests CONTROL+0xc bit0=1
and uses existing HPD+0 and ACK+0x10 reads. No manual MMIO or panel mapping.
If eDP blacks out, leave hub unplugged and stop. Installation and reboot
require their own committed/pushed entries after hub absence is verified.

## 2026-09-22 — Install0098 with hub verified absent

manage-0098.py check confirms correct kernel/machine, no external router,
and all three candidate hashes match. After commit/push execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0098.py install
```

Back up and checksum seven original files to /var/tmp/j416s-0098-before:
two copies each of appledrm, mux-apple-display-crossbar, thunderbolt_apple,
and /boot/initramfs-linux-aurora.img. Install pinned module copies, create
/etc/modprobe.d/j416s-0098-native-dpin.conf, depmod, mkinitcpio, extract
and verify image hashes/options, sync. Automatic restore on install failure.
No live module reload, MMIO, parameter write or reboot in this command.
Candidate hashes are recorded in notes/2026-09-22-0098-after-frame.md.

Right experiment addresses (not accessed by installer): crossbar
0xf0304c000 size0x4000; NHI0xf01f00000; ACIO0xf01ac0000; dcpext1
0x315c00000; native DPIN0 0xf01e50000..0xf01e53fff, HPD+0, CONTROL+0xc,
ACK+0x10. New diagnostic reuses crossbar reads once after completed frame:
+000,+004,+008,+00c,+014,+018,+01c,+024,+028,+02c,+030,+034,+040,+044,
+048,+04c,+050,+060,+070,+800,+020,+820,+81c. No new register writes.
Keep hub absent through separately logged reboot and postboot validation.

## 2026-09-22 — Reboot verified0098 with hub absent

Installation completed; seven-file backup verified, image module hashes
and experiment options verified. Repeated preflight confirms hub absent.
Installed image SHA256: 02398dd9348b414da9fcc7d5807cfdc200cc1bb9150c2f797debccabe10feeb1

After commit/push execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0098.py check && sudo -n systemctl reboot
```

Keep hub unplugged through postboot checks and future-boot disarm. Normal
crossbar probe remains unchanged. No manual mapping, MMIO or live reload.
Right native route: xbar0xf0304c000 size0x4000, NHI0xf01f00000,
ACIO0xf01ac0000, dcpext1 0x315c00000, DPIN0 0xf01e50000..0xf01e53fff
(HPD+0, CONTROL+0xc, ACK+0x10). With hub absent the native activation
and new one-shot after-frame snapshot are ineligible. Snapshot reads
existing crossbar offsets recorded in the installation entry only after
a later separately logged right-port connection and frame completion.

Recovery, hub absent and separately logged before use:
`sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0098.py restore`
Restores all seven verified originals from /var/tmp/j416s-0098-before,
removes config, depmods and syncs; no live reload/reboot. After boot verify
loaded build IDs, eDP and flags, then log/push/execute disarm before hotplug.
This entry records reboot intent, not successful boot or visible output.

## 2026-09-22 — Verify0098 boot and disarm future boots

Boot4ab4e6cc-59df-4dd9-86ca-5eede410542e: hub absent, all candidate
hashes match; loaded ELF build-ID notes for appledrm, crossbar and
thunderbolt match candidate files. Three live native experiment flags Y.
Hyprland eDP-1 active3456x2160@120, DPMS on, disabled=false.

After commit/push execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0098.py disarm
```

Remove /etc/modprobe.d/j416s-0098-native-dpin.conf, rebuild initramfs,
verify candidate hashes and removed options, sync. Current loaded flags
remain enabled for one test. No live reload, parameter write, MMIO,
mapping or reboot. Right addresses unchanged and not accessed by disarm:
xbar0xf0304c000, NHI0xf01f00000, ACIO0xf01ac0000, dcpext1 0x315c00000,
DPIN0 0xf01e50000..0xf01e53fff (HPD+0, CONTROL+0xc, ACK+0x10).

## 2026-09-22 — Schedule one0098 right-port connection

Disarm completed; extracted boot image verified. Disarmed image SHA256:
08cfa28e6b200972ad25d706816ef4393f8768d7086c666f91330a4851eba483
Live flags remain enabled. Panel modeset completed18.904s; no native DPIN
or USB4 frame experiment appeared before connection.

After commit/push request exactly: connect hub with monitor attached to
RIGHT USB-C once, then report visible output. No shell command initiates
physical hotplug. If eDP blacks out, unplug immediately and stop. Do not
reboot with hub attached or repeat hotplug. Keyboard may remain absent.

Existing path: typec2, NHI0xf01f00000, ACIO0xf01ac0000, dcpext1
0x315c00000, target0x8021, normal tunnel0:5 to1:19; no second tunnel.
Existing crossbar0xf0304c000 size0x4000 selects at ACTIVATE and reselects
once after first nonzero link config. Existing control accesses+0x000
through+0x034, +0x050/+0x070 and status reads are unchanged. DPIN0
teardown clears source bit2 at+0x00c and restores reset bit0 at+0x024.
Native ACIO maps0xf01e50000..0xf01e53fff under cable-power lock, reads
HPD+0, CONTROL+0xc, ACK+0x10; clears CONTROL bit0, polls ACK at most1s,
restores original bit on failure; deactivation requests bit0=1.
No DPIN+8 write, manual PHY/analog/panel access, or new clock selection.

0098 adds one snapshot through the existing right crossbar mapping after
external swap completion and page-flip delivery. Guarded by native opt-in,
right route, DCP index2, DPIN0 source2 selection, hardware address and
one-shot flags. Existing t602x_dump reads base0xf0304c000 plus offsets:
000,004,008,00c,014,018,01c,024,028,02c,030,034,040,044,048,04c,050,060,
070,800,020,820,81c. No new mapping or register writes.

After connection capture exactly:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0098-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0098-right-kernel.log
modetest -M apple -e
```

Raw logs remain private/untracked. Inspect after-frame snapshot and result,
frame completion, link rate/lanes/DPRX and eDP. Physical picture must be
confirmed by Oliver; frame completions alone do not prove signal output.

## 2026-09-22 —0098 result captured; end this connection test

Logged captures completed. Oliver reports no picture. External frame2
completes; successful one-shot snapshot at287.511925s reads right crossbar
+0x800=0, +0x000=4. eDP active, external DRM mode active; no keyboard
test. Offline audit and selected evidence in notes/2026-09-22-0098-result.md.
No new kernel patch, MMIO or parameter change made after capture.

After commit/push request exactly: unplug the hub from RIGHT USB-C and
leave it disconnected; do not reconnect the adapter or reboot yet.
Physical action, no shell command initiates unplug. Existing0098 normal
disconnect uses typec2, NHI0xf01f00000, ACIO0xf01ac0000, dcpext1
0x315c00000, crossbar0xf0304c000 size0x4000; existing teardown controls
+000,+004,+008,+00c,+014,+018,+01c,+024,+028,+02c,+030,+034,+050,+070
and existing status reads. DPIN0 at0xf01e50000..0xf01e53fff requests
CONTROL+0xc bit0=1 and uses existing HPD+0/ACK+0x10 reads. No manual
MMIO, new mapping or panel access. If eDP blacks out, leave unplugged
and stop. Future boots already disarmed. Any subsequent direct-USB-C
test or changed diagnostic must be reviewed and logged separately.

## 2026-09-22 — Hub absent; prepare and install0099 reference diagnostic

User confirms unplugged;0098 preflight verifies hub absent. Existing logs
show source gates cleared and crossbar idle restored after disconnect.
DEACTIVATE returned-ENODEV after cable loss; do not claim DPIN deactivation
handshake completed. eDP remains on.0099 adds bounded direct-reference
snapshot, described in notes/2026-09-22-0099-direct-comparison.md.

After commit/push execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0099.py check
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0099.py install
```

Back up seven current module/image files to /var/tmp/j416s-0099-before,
verify checksums, install pinned candidates in kernel/updates copies,
create /etc/modprobe.d/j416s-0099-native-dpin.conf, depmod, mkinitcpio,
verify extracted boot image/options, sync. Failure restores originals.
No live reload, parameter write, MMIO, new mapping or reboot. Reboot
requires separate logged/pushed entry. Leave all display cables absent.

Unaccessed experiment addresses: right crossbar0xf0304c000 size0x4000,
NHI0xf01f00000, ACIO0xf01ac0000, dcpext1 0x315c00000, native DPIN0
0xf01e50000..0xf01e53fff (HPD+0, CONTROL+0xc, ACK+0x10).0099 adds
only existing-crossbar after-frame reads, once each for source2 DPIN0
and DPPHY: offsets000,004,008,00c,014,018,01c,024,028,02c,030,034,
040,044,048,04c,050,060,070,800,020,820,81c. No register-write changes.
Direct cable attachment and its normal PHY accesses will be logged
separately after reboot verification; nothing initiates them here.

## 2026-09-22 — Reboot verified0099 with no external display connection

Installer succeeded, seven original files backed up/verified in
/var/tmp/j416s-0099-before. Extracted image module hashes/options match.
Repeated preflight confirms hub absent. Image SHA256:
aeccc392aa61e218b188444c0021a0848f3aad2ced6246ad8a79ba317ad6b8fe

After commit/push execute exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0099.py check && sudo -n systemctl reboot
```

Keep hub and direct adapter disconnected through boot verification and
future-boot disarm. Crossbar probe unchanged. No manual MMIO/reload.
No connected route means the new after-frame diagnostic is ineligible.
Relevant right addresses: xbar0xf0304c000 size0x4000, NHI0xf01f00000,
ACIO0xf01ac0000, dcpext1 0x315c00000, DPIN0 0xf01e50000..0xf01e53fff
(HPD+0, CONTROL+0xc, ACK+0x10).0099 snapshot accesses are listed in
the install entry and require a later separately logged connection.

Recovery command, hub absent and separately logged before use:
`sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0099.py restore`
Restores seven checksummed originals, removes config, depmods and syncs;
no reload/reboot. After return verify live build IDs and eDP, then log/push
and execute manage-0099.py disarm before requesting DIRECT right USB-C
adapter connection. No claim of successful boot or visible output yet.

## 2026-09-22 — Verify0099 boot and disarm future boots

Boote7238bcd-c22b-4d8b-ab00-dd5542cf0061: hub absent, candidate hashes
match, all three loaded module build-ID notes match0099. Three experiment
flags Y. Hyprland eDP-1 active3456x2160@120, DPMS on, disabled=false.
Panel modeset completes48.279478s; no native DPIN or frame snapshot yet.

After commit/push execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0099.py disarm
```

Remove /etc/modprobe.d/j416s-0099-native-dpin.conf, rebuild initramfs,
verify candidate hashes/options absent, sync. Live flags remain enabled
for this boot. No live reload, parameter write, mapping, MMIO or reboot.
Right addresses unchanged and unaccessed by disarm: xbar0xf0304c000,
NHI0xf01f00000, ACIO0xf01ac0000, dcpext1 0x315c00000, DPIN0
0xf01e50000..0xf01e53fff (HPD+0, CONTROL+0xc, ACK+0x10).

## 2026-09-22 — Schedule0099 direct right-port reference connection

Future-boot disarm completed, image hashes/options verified. Image SHA256:
23f6dca440382b08a97138f979c49a6b690b756f160a05b8bce24e8172de1fbf
Live experiment flags remain Y; loaded modules/eDP verified. No external
connection or after-frame snapshot yet in boote7238bcd.

After commit/push request exactly: leave OWC hub unplugged; connect the
same USB-C-to-HDMI adapter with monitor attached DIRECTLY to the Mac's
RIGHT USB-C port once. Report actual picture and whether laptop stays on.
No shell command initiates the physical connection. If eDP blacks out,
unplug adapter immediately and stop. Do not reboot or connect hub.

This uses normal existing direct DP-alt-mode driver behavior, not DP mode
on a connected USB4 hub. Right source dcpext1 0x315c00000, crossbar
0xf0304c000 size0x4000, DPPHY output/source2. Existing crossbar controls
+000..+034,+050,+070 and existing status reads unchanged. Right ATC2
PHY resources from t602x DTS: core0xf03000000 size0x4c000, lpdptx
0xf03050000 size0x8000, axi2af0xf00000000 size0x4000, usb2phy
0xf02a90000 size0x4000, pipehandler0xf02a84000 size0x4000. Normal
Type-C orientation/DP configuration is owned by existing driver; no
manual PHY command, panel mapping or forbidden39c000000 assignment.
Associated ACIO0xf01ac0000/NHI0xf01f00000 have no external USB4 router.
Native DPIN0 handshake is ineligible for this direct path.

0099 reads existing crossbar mapping once after first completed frame:
base0xf0304c000 offsets000,004,008,00c,014,018,01c,024,028,02c,030,034,
040,044,048,04c,050,060,070,800,020,820,81c. Provider checks j416s,
T602x, exact right resource, DPPHY selectedsource2 under lock; caller
checks right route/DCP2/opt-in. No new mapping or register writes.

After direct connection capture exactly:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0099-right-direct.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0099-right-direct-kernel.log
modetest -M apple -e
```

Keep raw captures private. Require after-frame-dpphy snapshot result0 and
Oliver's visible-picture confirmation before treating this as a known-good
reference. A later hub test requires its own log and review.

## 2026-09-22 —0099 topology correction; request hub removal

Logged capture commands completed. Live sysfs/journal identify OWC
Thunderbolt5 Hub0-1 and VMM7100 behind it, not direct adapter attachment.
0099 records after-frame-dpin0,+800=0,result0; user no picture/eDP on.
Direct diagnostic has not run. See0099-first-connection notes; preserve
raw evidence with corrected private filenames. No further MMIO initiated.

After commit/push request exactly: unplug OWC hub from the Mac and leave
it unplugged; report when disconnected. No shell command initiates this
physical action. Current normal teardown uses typec2, NHI0xf01f00000,
ACIO0xf01ac0000, dcpext1 0x315c00000, xbar0xf0304c000 size0x4000,
existing controls+000,+004,+008,+00c,+014,+018,+01c,+024,+028,+02c,+030,
+034,+050,+070 and existing status reads. Native DPIN0 resource
0xf01e50000..0xf01e53fff uses CONTROL+0xc bit0=1 request, HPD+0/ACK+0x10
reads if cable-powered owner remains available. No manual register write
or mapping. If eDP blacks out, stop with hub unplugged. No reboot or
hub reconnection. Verify unplug before separately proceeding to direct
adapter reference;0099 retains a separate direct snapshot allowance.

## 2026-09-22 — Hub absence verified; proceed to actual direct reference

User confirms unplugged. manage-0099.py check confirms hub absent and
matching candidates; Hyprland shows only eDP-1 active3456x2160@120.
DPIN0 crossbar disconnected381.124177s; DEACTIVATE returned-ENODEV after
cable loss. No after-frame-dpphy has run. No reboot/reload required.

After commit/push request exactly: remove the small USB-C-to-HDMI adapter
from the OWC hub, keep its HDMI monitor cable attached, and plug that
adapter directly into the Mac RIGHT USB-C port once. Leave OWC hub
unplugged. If laptop display goes black, unplug adapter immediately and
stop. No shell command initiates physical connection; no hub retry.

Same direct-path action and guards as prior0099 direct-connection entry:
dcpext1 0x315c00000, right crossbar0xf0304c000 size0x4000, source2/DPPHY.
Normal existing ATC2 PHY resources:0xf03000000 size0x4c000,0xf03050000
size0x8000,0xf00000000 size0x4000,0xf02a90000 size0x4000,0xf02a84000
size0x4000. ACIO0xf01ac0000/NHI0xf01f00000 have no external router.
No manual PHY/MMIO, no forbidden panel mapping or39c000000 assignment,
no native DPIN handshake for direct mode. Existing normal DP operations
plus one after-frame snapshot through existing crossbar mapping only.
Snapshot offsets:000,004,008,00c,014,018,01c,024,028,02c,030,034,040,044,
048,04c,050,060,070,800,020,820,81c. No new mapping/register writes.

Capture after connection with distinct filenames preserving prior evidence:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0099-actual-direct.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0099-actual-direct-kernel.log
modetest -M apple -e
```

Confirm actual topology and visible output before labeling known-good.

## 2026-09-22 —0099 direct picture confirmed; comparison preserved

Logged actual-direct capture commands completed. Oliver confirms picture.
Direct after-frame crossbar+800=4 vs hub0, same dcpext1/right port/source2
and video timing. Details and native tunnel-rate lead preserved in
notes/2026-09-22-0099-working-direct.md. Raw logs/disassembly private.
No live hardware operation after the previously logged diagnostic snapshot.
No candidate0100, parameter write, new mapping, hotplug or reboot scheduled.
Direct adapter remains connected; future boots disarmed.

## 2026-09-22 —0100 built offline; request direct-adapter unplug

User requests the separate Apple USB4 tunnel clock path. Candidate0100
implemented and RAM-tested; kernel commit b433579; see0100-tunnel-clock
notes for provenance, masks, limitations and hashes. No0100 live operation,
installation, parameter write, mapping or reboot has occurred. Future boots
remain disarmed. Only0099 is loaded, direct adapter currently working.

After this entry is committed and pushed, request exactly: unplug the
working USB-C-to-HDMI adapter from the Mac RIGHT USB-C port; keep the OWC
hub unplugged; report when disconnected. No shell command initiates the
physical unplug. This is ordinary0099 direct-DP teardown, not the new0100
clock path. Existing owner resources: ATC2 core0xf03000000 size0x4c000,
lpdptx0xf03050000 size0x8000, axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000, pipehandler0xf02a84000 size0x4000;
right crossbar0xf0304c000 size0x4000; dcpext1 0x315c00000. Crossbar
existing controls+000,+004,+008,+00c,+014,+018,+01c,+024,+028,+02c,
+030,+034,+050,+070 and status reads remain driver-owned. Associated
NHI0xf01f00000/ACIO0xf01ac0000 have no external router. No manual MMIO,
new mapping or forbidden panel/lpdptx assignment. If eDP goes black,
leave all external display cables unplugged and stop.

After unplug, read-only verification command:
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0100.py check

Install/reboot/next hub connection each require their own later log entry
committed and pushed before execution. This entry does not schedule them.

## 2026-09-22 —0100 install with external connections absent

Oliver confirms unplugged. `python3 scripts/manage-0100.py check` passes:
correct kernel/machine, no hub router, no external DRM connection, all
candidate hashes match. After this entry is committed and pushed, execute:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0100.py install
```

The installer backs up and verifies nine files in /var/tmp/j416s-0100-before:
two installed copies each of ATC, appledrm, crossbar mux, thunderbolt_apple,
plus /boot/initramfs-linux-aurora.img. It installs the recorded0100 hashes,
writes /etc/modprobe.d/j416s-0100-native-dpin.conf, runs depmod and mkinitcpio,
and verifies the image's modules/options. On failure it restores the verified
original files. No insmod, live parameter write, MMIO access, driver unload,
or reboot is performed by this command. Currently loaded0099 stays active.

Address scope on the later separately logged boot/test: ATC2 core
0xf03000000 size0x4c000; clock offsets008,1b0,7000,2224,2080,2084,2088,
2208,2220,2214,2200,2000 with the masks in0100 notes; status reads a74/7044.
Existing right crossbar0xf0304c000 size0x4000, dcpext1 0x315c00000,
DPIN0 0xf01e50000 size0x4000, NHI0xf01f00000, ACIO0xf01ac0000 remain
owned by their existing drivers. No additional mappings from installation.
All external display cables remain unplugged. Reboot requires its own
subsequent committed/pushed action entry after install verification.

## 2026-09-22 —0100 installed and verified; unplugged reboot instruction

Installation completed successfully; nine-file backup verified at
/var/tmp/j416s-0100-before. Initramfs module/options verification passed.
Armed image SHA256:
1833c12191f86165a54a6447954869635d9e78774a7aca81df3d6d0d6c0f6adb.
Pre-reboot boot ID e7238bcd-c22b-4d8b-ab00-dd5542cf0061. Post-install
manage-0100.py check passes; hub and external display remain absent.

After this entry is committed and pushed, instruct Oliver to reboot with
BOTH hub and direct adapter left unplugged. Exact user-run command:

```
systemctl reboot
```

No automated reboot is executed in this turn. Normal boot loads0100
appledrm and ATC with usb4_tunnel_clock=1, appledrm native/protocol flags,
and thunderbolt_apple dpin_native=1. With no hub/display connected, the
new clock helper must perform no clock programming. No live unload/reload
or manual MMIO. Ordinary driver-owned resources include right ATC core
0xf03000000 size0x4c000, lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000, usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000; crossbar0xf0304c000 size0x4000;
dcpext1 0x315c00000, NHI0xf01f00000, ACIO0xf01ac0000 and
DPIN0 0xf01e50000 size0x4000. The new optional clock register offsets
and masks are fully listed in0100 notes and the prior installation entry;
no tunnel-rate request is expected while unplugged. No forbidden manual
panel or39c000000 assignment/mapping.

After desktop returns, keep both external connections unplugged. Verify
new boot ID, eDP and loaded0100 flags; log/commit/push future-boot disarm
before executing it. Only then separately log/commit/push one right-port
hub connection. If the integrated display does not return, stop the test;
do not connect the hub. No hub hotplug is authorized by this entry.

## 2026-09-22 — User explicitly requests agent-executed 0100 reboot

Oliver: "reboot please". Rechecked manage-0100.py check successfully:
correct kernel/machine, hub and external display absent, candidate hashes
match. After committing and pushing this entry execute exactly:

```
sudo -n systemctl reboot
```

This replaces the preceding user-run reboot instruction with an agent-run
reboot. Same verified0100 image, backup and address scope: right ATC core
0xf03000000 size0x4c000, lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000, usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000, crossbar0xf0304c000 size0x4000,
dcpext1 0x315c00000, NHI0xf01f00000, ACIO0xf01ac0000,
DPIN0 0xf01e50000 size0x4000. No external connection; no new tunnel
clock programming expected. No manual MMIO or module unload. Keep both
external connections unplugged after boot until loaded-driver verification
and separately logged future-boot disarm. If eDP fails, stop the test.

## 2026-09-22 —0100 boot verified; disarm future boots before hotplug

New boot db25bd04-ac78-4144-96ad-344a8b49757d, kernel7.1.12-2.5-1-ARCH.
Hyprland eDP-1 active3456x2160@120, dpms1, disabledfalse. No external
DRM connector or USB4 hub router; candidate hash check passes. Loaded
appledrm usb4_tunnel_clock/native_dpin/protocol_probe, phy_apple_atc
usb4_tunnel_clock and thunderbolt_apple dpin_native all report Y.

After committing and pushing this entry execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0100.py disarm
```

This removes /etc/modprobe.d/j416s-0100-native-dpin.conf and rebuilds and
verifies /boot/initramfs-linux-aurora.img without the candidate options.
Loaded read-only flags remain unchanged for this boot's bounded test.
No live parameter write, insmod, MMIO, mapping or reboot. Thus no hardware
address is accessed by the disarm command. Later test resource scope remains
ATC2 core0xf03000000 size0x4c000, crossbar0xf0304c000 size0x4000,
dcpext1 0x315c00000, DPIN0 0xf01e50000 size0x4000, NHI0xf01f00000,
ACIO0xf01ac0000; clock offsets/masks unchanged from0100 notes. Hub and
direct adapter stay unplugged. A separate pushed entry will precede hotplug.

## 2026-09-22 —0100 future boots disarmed; one right-port hub test

Disarm completed and initramfs verified without0100 options. Image SHA256
48dcece31ad466e13e8a3faba0ac4c4929dbe5d2ccd59ce10a9085cbae21e7ca.
Current boot db25bd04-ac78-4144-96ad-344a8b49757d retains loaded Y flags.
eDP is active; boot journal shows normal panel mode setup and no tunnel
clock callback while unplugged. No hub/direct adapter currently attached.

After this entry is committed and pushed, request exactly: attach the
USB-C-to-HDMI adapter and its monitor cable to a downstream USB-C port
on the OWC hub, then connect the hub host cable to the Mac RIGHT USB-C
port once. Do not connect the display adapter directly to the Mac. Leave
the laptop display enabled. Report visible external picture and laptop
state; report keyboard behavior if a keyboard is attached. No shell
command initiates this physical hotplug. If eDP goes black, unplug the
hub immediately and stop. Do not reboot or repeatedly reconnect.

This first0100 test invokes the normal USB4 tunnel path; no manual tunnel
creation or DP-alt-mode forcing. Right ATC2 existing core0xf03000000
size0x4c000: new clock writes at offsets/masks 008/0003ffff,
1b0/00000fff,7000/0000207c,2224/00000003,2080/ffffffff,
2084/0fffffff,2088/007fffff,2208/001f0000,2220/00000080,
2214/00000001,2200/00000054,2000/1ffffff9; status reads a74/7044.
The owner checks machine/resource/mode and existing clock clients;
only one programming attempt this boot; command/lock timeouts restore
saved owned fields. Cleanup uses the same addresses, no second mapping.
Normal existing ATC resources also include lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000. No added lane mux or AUX writes.

DCP source dcpext1 0x315c00000; crossbar0xf0304c000 size0x4000,
source2 to DPIN0. Existing crossbar controls+000,+004,+008,+00c,+014,
+018,+01c,+024,+028,+02c,+030,+034,+050,+070 and0099 snapshot offsets
000,004,008,00c,014,018,01c,024,028,02c,030,034,040,044,048,04c,
050,060,070,800,020,820,81c remain unchanged. Existing native DPIN0
resource0xf01e50000 size0x4000 uses CONTROL+0xc request bit0 and HPD+0,
ACK+0x10 reads. NHI0xf01f00000/ACIO0xf01ac0000 owned by normal USB4
drivers. No forbidden ACIO RC analog writes, no panel disp mapping,
no39c000000 assignment, /dev/mem, or live module unload.

After connection capture exactly (read-only OS interfaces; private outputs):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0100-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0100-right-kernel.log
modetest -M apple -e
```

Verify actual right-port topology, tunnel-clock result, link rate/lanes,
DPRX and completed-frame crossbar+800. Success requires Oliver's actual
visible-picture confirmation plus eDP remaining on; keyboard remains
unverified unless attached and checked. Software detection alone is not
success. No further hardware experiment is covered by this entry.

## 2026-09-22 —0100 capture completed; request hub removal for0101

Previously logged capture commands completed. User no picture; eDP active.
Right ATC callback returns-EBUSY on first SET_LINK_RATE0xa, before any new
clock writes. DPRX_DONE1 but no external frame. See0100-result-0101-diagnostics
notes. Built/tested0101 only adds logging to existing clock preflight reads;
it is not installed. Future boots remain disarmed.

After commit/push request exactly: unplug OWC hub from Mac RIGHT USB-C;
keep direct display adapter disconnected from Mac; report when unplugged.
No shell command initiates physical removal. Current0100 clock state was
never saved/programmed, so its restore helper performs no MMIO. Normal
teardown remains driver-owned at right ATC core0xf03000000 size0x4c000,
lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,
NHI0xf01f00000/ACIO0xf01ac0000. Existing crossbar controls+000,+004,
+008,+00c,+014,+018,+01c,+024,+028,+02c,+030,+034,+050,+070;
native DPIN0 base0xf01e50000 size0x4000 CONTROL+0xc request bit0,
HPD+0/ACK+0x10 reads if owner still available. No new mapping, manual
register write, forbidden panel access, or39c000000 assignment. If eDP
blacks out, stop with hub unplugged. No reboot/replug covered by this entry.
After unplug verify with:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0101.py check
```

Installation and reboot require subsequent committed/pushed entries.

## 2026-09-22 —0101 install after verified hub removal

Oliver confirms unplugged. manage-0101.py check passes: kernel/machine
correct, hub/external DRM absent, candidate hashes match. After this entry
is committed and pushed execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0101.py install
```

Back up and verify nine files under /var/tmp/j416s-0101-before: two copies
each of ATC/appledrm/mux/thunderbolt_apple plus initramfs. Install0101
ATC SHA256794b47de6e3b1faab8da51532ca1e264da0cb8eb9513188e2a5ff5ae0b4d86b4;
other modules unchanged from0100. Write0101 modprobe options, depmod,
rebuild initramfs, verify modules/options; restore originals on failure.
No insmod, live parameter change, MMIO, mapping, unload or reboot in this
command. No hardware addresses accessed by installation. Later boot/test
scope unchanged: ATC2 core0xf03000000 size0x4c000; existing preflight
reads+7000,+2200,+2000 gain log messages only. Existing0100 write masks
and guards retained. Crossbar0xf0304c000 size0x4000, dcpext1 0x315c00000,
DPIN0 0xf01e50000 size0x4000, NHI0xf01f00000/ACIO0xf01ac0000.
Both external connections remain unplugged. Reboot logged separately
only after successful installation verification.

## 2026-09-22 —0101 installed/verified; unplugged reboot instruction

Installer completed: nine-file backup verified at /var/tmp/j416s-0101-before,
initramfs module/options verification passed. Armed image SHA256
f508d2524f0d8e010b484db13a0c299d3a304c7ac50c637e0e34f12d82f44b6a.
Boot before reboot db25bd04-ac78-4144-96ad-344a8b49757d. Post-install
check passes; hub and external display absent. No live module reload.

After committing and pushing this entry instruct Oliver to run:

```
systemctl reboot
```

Keep hub and direct adapter unplugged through boot. No agent-executed
reboot this turn. Normal driver-owned resources: right ATC core0xf03000000
size0x4c000,lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. No tunnel clock callback
or its MMIO expected while unplugged.0101 adds only logs of0100 existing
preflight reads; clock masks/guards unchanged. No manual MMIO, forbidden
panel mapping,39c000000 assignment, or live driver unload.

Once desktop returns verify boot/drivers/eDP, then separately log/push
and disarm future test boots before separately logging right-port hub
connection. Keep hub unplugged until that verification. If eDP does not
return, stop the test and do not connect hub.

## 2026-09-22 — Agent-executed0101 reboot after user go-ahead

Oliver says "lets go" following installed0101 reboot instruction. Recheck
passes: correct kernel/machine, hub and external display absent, candidate
hashes match. Current boot db25bd04-ac78-4144-96ad-344a8b49757d. After
committing and pushing this entry execute exactly:

```
sudo -n systemctl reboot
```

This supersedes the prior user-run reboot instruction with agent execution.
Same verified0101 image and nine-file backup. Both external connections
remain unplugged. Normal driver-owned resource scope: ATC2 core0xf03000000
size0x4c000,lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. No tunnel clock callback
or new clock programming expected while unplugged; no manual MMIO, live
module unload, panel mapping or39c000000 assignment. Keep hub disconnected
after boot until verification and separately logged future-boot disarm.
If eDP does not return, stop the test; do not connect hub.

## 2026-09-22 —0101 boot verification and future-boot disarm

New boot0ec84f1a-b57c-455e-9155-bb440f5c0d24. Candidate hash/machine/kernel
check passes, hub and external DRM absent. eDP active3456x2160@120.
All five expected loaded flags report Y. Journal shows normal panel setup
and no USB4 tunnel clock invocation while unplugged.

After commit/push execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0101.py disarm
```

Remove0101 modprobe options, rebuild and verify initramfs without them.
Current loaded flags remain unchanged. No MMIO, mapping, live parameter
write, module reload or reboot; no hardware address accessed by disarm.
Later test scope remains right ATC core0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,DPIN0 0xf01e50000
size0x4000,NHI0xf01f00000,ACIO0xf01ac0000. Keep external cables unplugged
until disarm verification and a separately committed/pushed hotplug entry.

## 2026-09-22 —0101 disarmed; first right-port diagnostic connection

Disarm completed; image verified without0101 options, SHA256
332d63e5d800d71e841c97bc3f721eb54c7ebf8e2d6bac8b6a321e2900b797e7.
Loaded build IDs matched candidate files by read-only ELF/sysfs comparison:
ATC66783a52ae24044656fef15c25a193091128babc,
appledrm890025a11411c927b51a4b014d142d4398b66dc4.
Current boot0ec84f1a-b57c-455e-9155-bb440f5c0d24, eDP active, hub absent.

After commit/push request exactly: monitor/HDMI adapter attached to a
DOWNSTREAM OWC hub USB-C port, connect hub HOST cable to Mac RIGHT USB-C
once. Do not attach adapter directly to Mac. Report external picture and
whether laptop stays on. If eDP goes black, unplug hub immediately and
stop. No shell command initiates physical connection; no reboot/retry.

Normal USB4 tunnel path, no second tunnel or DP-alt-mode forcing. Existing
right ATC core0xf03000000 size0x4c000.0101 logs existing reads+7000,
+2200,+2000 before unchanged busy checks; no additional read or write.
If guards pass, existing0100 writes offsets/masks008/3ffff,1b0/fff,
7000/207c,2224/3,2080/ffffffff,2084/0fffffff,2088/007fffff,
2208/001f0000,2220/80,2214/1,2200/54,2000/1ffffff9; status a74/7044.
Same one-attempt policy, timeout rollback and mode/ownership guards.
Normal other resources:lpdptx0xf03050000 size0x8000,axi2af0xf00000000
size0x4000,usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000.
DCP315c00000, crossbar0xf0304c000 size0x4000/source2 DPIN0; existing
controls+000,+004,+008,+00c,+014,+018,+01c,+024,+028,+02c,+030,+034,
+050,+070 and0099 after-frame snapshot offsets000,004,008,00c,014,018,
01c,024,028,02c,030,034,040,044,048,04c,050,060,070,800,020,820,81c.
NativeDPIN0 base0xf01e50000 size0x4000 CONTROL+0xc requestbit0,
HPD+0/ACK+0x10 reads. NHI0xf01f00000/ACIO0xf01ac0000 driver-owned.
No new mappings, forbidden ACIO RC analog writes, panel mapping,
39c000000 assignment, /dev/mem, or live module unload.

After connection execute the following previously reviewed capture tools:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0101-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0101-right-kernel.log
modetest -M apple -e
```

Keep raw captures private. Identify last preflight register/value and exact
callback result; do not infer clock ownership from enable bits alone.
Visible picture with eDP retained remains required for success. Keyboard
unverified unless attached and tested. Further action requires separate log.

## 2026-09-22 —0101 guard identified; request unplug for0102

Logged captures completed. Right PHY+7000=0000e001 triggered the first
busy guard; no0101 PLL writes. User no picture, eDP active, DPRX1.
Built/RAM-tested0102 exact-state exception contingent on outputs/request/
lock clear; see0101-result-0102-gate-state notes. Not installed. No live
extra register access; future boots still disarmed.

After this entry is committed and pushed request exactly: unplug the OWC
hub from Mac RIGHT USB-C; leave direct adapter disconnected from Mac;
report when unplugged. No shell command initiates physical removal.
Current0101 saved-clock state is false, so its restore does no MMIO.
Normal teardown resources: ATC2 core0xf03000000 size0x4c000,
lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,
NHI0xf01f00000/ACIO0xf01ac0000. Existing crossbar controls+000,+004,
+008,+00c,+014,+018,+01c,+024,+028,+02c,+030,+034,+050,+070;
DPIN0 base0xf01e50000 size0x4000 CONTROL+0xc requestbit0,HPD+0/ACK+0x10
reads if owner remains available. No new mapping/manual MMIO or forbidden
panel/39c000000 access. If eDP blacks out stop with hub unplugged.
After unplug, verification command:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0102.py check
```

Install/reboot/hotplug each require separately committed/pushed entries.

## 2026-09-22 —0102 installation after verified unplug

Oliver confirms unplugged. manage-0102.py check passes: correct kernel/
machine, hub and external DRM absent, candidate hashes match. Current
boot0ec84f1a-b57c-455e-9155-bb440f5c0d24. After commit/push execute:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0102.py install
```

Installer verifies nine-file backup in /var/tmp/j416s-0102-before (two
copies each ATC/appledrm/mux/thunderbolt_apple plus initramfs), installs
0102 ATC SHA256e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9
with other modules unchanged, writes0102 options, runs depmod/mkinitcpio,
and verifies image modules/options. Failure restores verified originals.
No live module reload, MMIO, mapping, parameter write or reboot. No
hardware addresses accessed by this installation command. Later test
scope: ATC2 core0xf03000000 size0x4c000, preflight7000/2200/2000/7044;
existing0100 clock write masks unchanged as documented in0102 notes.
Crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,DPIN0 0xf01e50000
size0x4000,NHI0xf01f00000,ACIO0xf01ac0000. Both external connections
stay unplugged. Reboot separately logged after successful verification.

## 2026-09-22 —0102 installed and verified; unplugged reboot instruction

Nine-file backup verified at /var/tmp/j416s-0102-before. Installer and
initramfs module/options verification succeeded. Armed image SHA256
ba12ab5144b9d0dcc7537d993eb3f527cbec8847936869b75a4d2a4701ddfd15.
Post-install check passes; both external connections absent. Current
boot0ec84f1a-b57c-455e-9155-bb440f5c0d24 still runs0101, no live reload.

After commit/push instruct Oliver to run exactly:

```
systemctl reboot
```

No agent-executed reboot this turn. Keep hub and direct display adapter
unplugged through boot. Normal resource scope: ATC2 core0xf03000000
size0x4c000,lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. No tunnel clock callback
or its register programming expected while unplugged. No manual MMIO,
forbidden panel mapping,39c000000 assignment, or driver unload.

After desktop returns verify boot ID, loaded driver build IDs and eDP;
separately log/push future-boot disarm before executing it, then separately
log/push one right-port hub connection. Keep hub unplugged until those
checks. If eDP does not return, stop the test and do not connect hub.

## 2026-09-22 —0102 user reboot verified; disarm future boots

Oliver reports reboot done; agent had not executed a reboot command.
New boot741e4261-fa77-45f1-a1c6-07d98348fe65. Candidate hash/machine/kernel
check passes; hub and external DRM absent. eDP active3456x2160@120.
All five expected loaded flags Y. Loaded build IDs match candidate ELF:
ATC f4fc4b28eb06cabfd7b88d2fdcf6b8b72c42614e,
appledrm 890025a11411c927b51a4b014d142d4398b66dc4.

After this entry is committed and pushed execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0102.py disarm
```

Remove0102 modprobe options, rebuild/verify initramfs without them.
Current loaded flags remain unchanged. No MMIO, mapping, live parameter
write, reload or reboot; no hardware address accessed by disarm. Future
test scope remains ATC2 core0xf03000000 size0x4c000,crossbar0xf0304c000
size0x4000,dcpext1 0x315c00000,DPIN0 0xf01e50000 size0x4000,
NHI0xf01f00000,ACIO0xf01ac0000. Keep both external cables unplugged
until disarm verification and a separately committed/pushed hotplug entry.

## 2026-09-22 —0102 disarmed; first right-port hub connection

Disarm completed and image verified without0102 options. Image SHA256
ce30d0fb6bc02f9e6d77c561236a5c7b3668381e5ad08a50a7afd678532f53e9.
Current boot741e4261-fa77-45f1-a1c6-07d98348fe65 retains loaded test flags.
eDP active; external connections absent at preflight.

After commit/push request exactly: with monitor/HDMI adapter on a DOWNSTREAM
OWC hub USB-C port, connect hub HOST cable to Mac RIGHT USB-C once.
Do not connect the display adapter directly to Mac. Report actual external
picture and whether eDP stays on; keyboard behavior if attached. No shell
command initiates physical hotplug. If eDP blacks out unplug hub immediately
and stop. No reboot or repeated reconnection.

Normal existing USB4 tunnel only. Right ATC core0xf03000000 size0x4c000:
0102 reads/logs preflight offsets7000,2200,2000,7044. Exact e001 gate state
may proceed only with PLL outputs/request/lock clear; all other enabled-gate
states rejected. Existing0100 writes offsets/masks008/3ffff,1b0/fff,
7000/207c,2224/3,2080/ffffffff,2084/0fffffff,2088/007fffff,
2208/001f0000,2220/80,2214/1,2200/54,2000/1ffffff9; status a74/7044.
Same mode/resource/route guards, one programming attempt, timeout rollback.
No new mapping or lane mux. Other normal ATC resources:lpdptx0xf03050000
size0x8000,axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000. DCP315c00000, crossbar0xf0304c000
size0x4000/source2 DPIN0. Existing crossbar controls+000,+004,+008,+00c,
+014,+018,+01c,+024,+028,+02c,+030,+034,+050,+070;0099 snapshot offsets
000,004,008,00c,014,018,01c,024,028,02c,030,034,040,044,048,04c,050,
060,070,800,020,820,81c. NativeDPIN0 base0xf01e50000 size0x4000,
CONTROL+0xc requestbit0,HPD+0/ACK+0x10 reads. NHI0xf01f00000/
ACIO0xf01ac0000 driver-owned. No manual MMIO, forbidden ACIO RC analog
writes, panel mapping,39c000000 assignment,/dev/mem or live module unload.

After connection execute these read-only capture tools; keep raw outputs private:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0102-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0102-right-kernel.log
modetest -M apple -e
```

Assess all four preflight values, clock callback result, link rate/lanes,
DPRX, completed frame and crossbar+800. Success requires actual visible
picture with eDP retained; keyboard unverified unless checked. Further
hardware action needs its own committed/pushed entry.

## 2026-09-22 —0102 capture: clock setup succeeds and crossbar+800=4

Previously logged capture commands completed after user "connected".
Right ATC preflight7000=e001,2200=2000,2000=10000000,7044=0; rate0xa
clock setup result0. Four lanes,DPRX1,completed external frame,+800=4.
Hyprland BenQ USB-3 active2560x1440 alongside activeeDP3456x2160@120.
See0102-clock-success notes. Actual visible picture confirmation requested
and pending; keyboard not attached in capture, functionality unverified.
No further hardware action, unplug, reboot or persistence change requested.
Current connected state preserved; future boots remain disarmed.

## 2026-09-22 —0102 visual confirmation NEGATIVE

Oliver: "nope, still no picture on the external one". Crossbar clock+800=4,
PLL callback0 and external frame are confirmed intermediate progress only;
monitor goal remains unmet. Corrected0102-clock-success notes accordingly.
No further live register access, hotplug, reboot or parameter change.
Current connection preserved, future boots remain disarmed. Investigate
remaining video delivery offline; do not treat Hyprland detection as picture.

## 2026-09-22 — No-signal confirmed;0103 built; request hub removal

Oliver confirms no signal/standby.0102 intermediate clock/frame success
is not monitor success. Built/RAM-tested0103 native post-clock bring-up
without disconnecting selected crossbar; see0103-native-link-up notes.
Not installed. No live register experiments performed. Future boots disarmed.

After commit/push request exactly: unplug OWC hub from Mac RIGHT USB-C,
leave direct adapter disconnected from Mac, report when unplugged. No shell
command initiates physical removal. Unlike0100/0101, current0102 successfully
programmed the clock, so this unplug exercises its existing saved-state
cleanup for the first time. ATC owner stops PCLK1/PLL outputs and restores
saved fields through existing core0xf03000000 size0x4c000:
008/3ffff,1b0/fff,7000/207c,2224/3,2080/ffffffff,2084/0fffffff,
2088/007fffff,2208/001f0000,2220/80,2214/1,2200/54,2000/1ffffff9.
Mode transition performs restoration before existing power-off; if already
restored, later DCP cleanup performs no register access. No live manual MMIO.

Normal teardown also owns lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000,crossbar0xf0304c000 size0x4000,
dcpext1 0x315c00000,NHI0xf01f00000/ACIO0xf01ac0000. Existing crossbar
controls+000,+004,+008,+00c,+014,+018,+01c,+024,+028,+02c,+030,+034,
+050,+070;DPIN0 0xf01e50000 size0x4000 CONTROL+0xc requestbit0,
HPD+0/ACK+0x10 reads if powered owner remains available. No new mapping,
forbidden panel/39c000000 assignment, /dev/mem or module unload.
If eDP goes black, stop with hub unplugged. Do not reboot or reconnect.

After unplug verify with:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0103.py check
sudo -n journalctl -k -b --no-pager -o short-monotonic
hyprctl monitors
```

Install/reboot/next hotplug each require their own committed/pushed entry.

## 2026-09-22 —0102 unplug completed;0103 installation

Oliver confirms unplugged. manage-0103.py check passes; hub/external DRM
absent, candidate hashes match. eDP active3456x2160@120, same boot
741e4261-fa77-45f1-a1c6-07d98348fe65. Journal: SET_LINK_RATE0 at1050.478836s,
clock cleanup callback0; DPIN deactivation-ENODEV after cable loss;
crossbar disconnect completes. No reset observed. This is one successful
unplug observation, not full cleanup/replug validation. Idle snapshot+800
still4 while+000=0; no further live register probing performed.

After committing and pushing this entry execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0103.py install
```

Back up/verify nine files in /var/tmp/j416s-0103-before: two installed
copies each ATC/appledrm/mux/thunderbolt_apple plus initramfs. Install0103
pinned hashes, write0103 options, depmod/mkinitcpio and verify image;
restore verified originals on failure. No live reload, mapping, MMIO,
parameter write or reboot; no hardware addresses accessed by installation.
Later test scope remains right ATC core0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,DPIN0 0xf01e50000
size0x4000,NHI0xf01f00000,ACIO0xf01ac0000.0103 new crossbar bring-up
uses offsets004,014,024,008,018,028,000,00c,01c,034,02c and status
804,810,81c as documented; no such operation during install. Keep both
external connections unplugged. Reboot logged separately after verification.

## 2026-09-22 —0103 installed/verified; unplugged reboot instruction

Installer completed; nine-file backup /var/tmp/j416s-0103-before verified.
Initramfs modules/options verified. Armed image SHA256
04f0572d3348a7d394e3588b06d07b7d6aea2e3bc56a44f332d24a15677e53f6.
Post-install check passes; hub and external display absent. Current boot
741e4261-fa77-45f1-a1c6-07d98348fe65 remains on0102; no live reload.

After this entry is committed and pushed instruct Oliver to run:

```
systemctl reboot
```

No agent-executed reboot this turn. Keep hub and direct adapter unplugged.
Normal resource scope: ATC2 core0xf03000000 size0x4c000,
lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000,
crossbar0xf0304c000 size0x4000,dcpext1 0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. No tunnel clock callback
or new post-clock bring-up expected while unplugged. No manual MMIO,
forbidden panel mapping,39c000000 assignment or driver unload.

After desktop returns verify new boot, loaded build IDs and eDP. Log/push
future-boot disarm before executing it; then separately log/push one
right-port hub test. Keep hub unplugged until verification. If eDP does
not return, stop the test and do not connect hub.

## 2026-09-22 —0103 reboot verified; disarm future boots

New bootfad74e21-836b-45f1-9488-6b5f75a7f4be. Candidate check passes:
correct kernel/machine, hub/external DRM absent, hashes match. eDP active
3456x2160@120. All five expected loaded flags Y. Loaded build IDs match:
ATC f4fc4b28eb06cabfd7b88d2fdcf6b8b72c42614e,
appledrm e55a61a2d1ba1d45ab0bf89a468078d67cfc31dd,
mux 6effcfefd97193d8737d73ba31a56adbb4899a0c.
After committing and pushing this entry execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0103.py disarm
```

Remove0103 modprobe options; rebuild/verify initramfs without them. Loaded
flags remain unchanged. No MMIO, mapping, live parameter write, reload or
reboot; no hardware address accessed by disarm. Later test scope remains
ATC2 core0xf03000000 size0x4c000,crossbar0xf0304c000 size0x4000,
dcpext1 0x315c00000,DPIN0 0xf01e50000 size0x4000,NHI0xf01f00000,
ACIO0xf01ac0000. Keep both external connections unplugged until disarm
verification and a separate committed/pushed hotplug entry.

## 2026-09-22 —0103 disarmed; first right-port sequencing test

Disarm completed; initramfs verified without0103 options. Image SHA256
a920ffb00d0af2fc7d6f8b2f4446501a1bbd20614a6de96d548b16e1e9f13d9a.
Bootfad74e21-836b-45f1-9488-6b5f75a7f4be retains loaded test flags.
eDP active and external connections absent at preflight.

After commit/push request exactly: monitor/HDMI adapter on a DOWNSTREAM
OWC hub USB-C port, connect hub HOST cable to Mac RIGHT USB-C once.
Do not connect adapter directly to Mac. Report visible picture versus
no signal and whether eDP stays on. No shell command initiates hotplug.
If eDP goes black unplug hub immediately and stop. No reboot or retry.

Normal USB4 tunnel only, no DP-alt-mode forcing. ATC2 core0xf03000000
size0x4c000:0102 preflight7000,2200,2000,7044; same guarded writes
008/3ffff,1b0/fff,7000/207c,2224/3,2080/ffffffff,2084/0fffffff,
2088/007fffff,2208/001f0000,2220/80,2214/1,2200/54,2000/1ffffff9;
status a74/7044. Other normal ATC resources:lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000. No lane mux or additional mappings.

DCP315c00000; right crossbar0xf0304c000 size0x4000,source2/DPIN0.
Initial selection/ACTIVATE unchanged controls000,004,008,00c,014,018,
01c,024,028,02c,030,034,050,070. After successful PLL setup,0103
DID_CHANGE now performs one bring-up without disconnect/reselect:
clear004/bit2,014/bit2,024/bit0; wait1us; read804/bit2,810/bit2,
81c/bit0 and refuse if any remain set. Then set008/bit2; masked018/30
value10,028/3 value1; set000/bit2,00c/bit2,01c/bit0,034/bit0,02c/bit2.
This operation does not assert reset, disable source clock, rewrite030,
or write050/070. Existing dump/snapshot offsets000,004,008,00c,014,018,
01c,024,028,02c,030,034,040,044,048,04c,050,060,070,800,020,820,81c.
NativeDPIN0 base0xf01e50000 size0x4000,CONTROL+0xc requestbit0,
HPD+0/ACK+0x10 reads; active result cached by existing owner after bring-up.
NHI0xf01f00000/ACIO0xf01ac0000 driver-owned. No forbidden ACIO RC analog
writes, panel mapping,39c000000 assignment,/dev/mem or module unload.

After connection capture exactly, keeping raw outputs private:

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0103-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0103-right-kernel.log
modetest -M apple -e
```

Require actual picture confirmation, not only clock4/frame/Hyprland.
Check native-link-up result and preserve all failure evidence. Keyboard
untested unless attached/checked. Further hardware action separately logged.

## 2026-09-22 —0103 captured;0104 duplicate-completion fix prepared offline

Previously logged capture commands completed. User no picture,eDP active.
Native PLL and crossbar bring-up succeed; second identical DID_CHANGE hits
one-attempt-EALREADY and AFK transport omits ACK by source inspection.
Modeset times out. Hub disconnect307.207s/reconnect342.864s also recorded;
manual versus spontaneous cause pending user clarification. Second attachment
cannot retrigger the one-attempt experiment. See0103-result-0104-completion.

Built/tested0104 caches successful same-rate completion without another
hardware operation. Kernel fa3f3dd, patch exported; not installed. No live
MMIO, parameter change, new hotplug or reboot requested. Future boots remain
disarmed. Preserve present state pending clarification; next unplug/install/
reboot/hotplug requires a separate committed/pushed action entry.

## 2026-09-22 —0103 reconnection confirmed manual; request unplug for0104

Oliver confirms he unplugged/reconnected the hub. Do not classify that
recorded disconnect as spontaneous hardware failure. Current boot remains
fad74e21-836b-45f1-9488-6b5f75a7f4be; sysfs external router0-1 present.
0104 is built/tested/pushed but not installed. Future boots remain disarmed.

After committing and pushing this entry request exactly: unplug the OWC
hub from the Mac RIGHT USB-C port, leave direct adapter disconnected from
Mac, and report when unplugged. No shell command initiates this physical
removal. Current0103 already returned clock cleanup0 after the first
removal; its saved state should be clear. If any saved state remains, normal
owner cleanup restores the existing ATC core0xf03000000 size0x4c000 fields:
008/3ffff,1b0/fff,7000/207c,2224/3,2080/ffffffff,2084/0fffffff,
2088/007fffff,2208/001f0000,2220/80,2214/1,2200/54,2000/1ffffff9.
No manual register operation or new mapping.

Normal teardown also owns lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000,crossbar0xf0304c000 size0x4000,
dcpext1 0x315c00000,NHI0xf01f00000/ACIO0xf01ac0000. Existing crossbar
controls000,004,008,00c,014,018,01c,024,028,02c,030,034,050,070;
DPIN0 base0xf01e50000 size0x4000 CONTROL+0xc requestbit0,HPD+0/ACK+0x10
reads if owner remains available. No forbidden panel/39c000000 mapping or
assignment, /dev/mem or module unload. If eDP goes black, stop with hub
unplugged. No reboot/reconnection requested by this entry.

After unplug verify exactly:

```
python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0104.py check
hyprctl monitors
```

Install/reboot/next single hotplug require separately committed/pushed entries.

## 2026-09-22 — install0104 after confirmed unplug

Oliver reports done. Preflight passed: correct kernel/j416s, external router
and external display absent; candidate hashes match. eDP-1 active, DPMS1,
disabled false. Boot fad74e21-836b-45f1-9488-6b5f75a7f4be.
After committing and pushing this entry execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0104.py install
```

Back up nine module/image files to /var/tmp/j416s-0104-before, install pinned
0104 modules, set candidate boot options, depmod and rebuild/verify initramfs.
No live module reload, parameter write, mapping, MMIO or reboot in this action.
0104 only acknowledges repeated successful same-rate link completion; no new
hardware operation on the repeated request. First-attempt hardware remains
0103: right ATC core0xf03000000 size0x4c000, crossbar0xf0304c000 size0x4000,
lpdptx0xf03050000 size0x8000, axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000, pipehandler0xf02a84000 size0x4000,
dcpext1 0x315c00000, NHI0xf01f00000, ACIO0xf01ac0000,
DPIN0 0xf01e50000 size0x4000. No access to these addresses during install.
Keep hub/direct adapter disconnected. Reboot/hotplug logged separately.

## 2026-09-22 —0104 installation verified; request unplugged reboot

Installer exited0, verified backup /var/tmp/j416s-0104-before and module
hashes/options inside initramfs. Image SHA256:
603553c7f9761d2533cea352d8068c36c02d3e01a86eaed13a9947500a3bd7c3.
Post-install preflight passes, hub/external display absent. No live reload.
Recurring firmware/font/architecture warnings only; image verification passed.

After committing/pushing this entry ask Oliver to keep hub and direct display
adapter unplugged, reboot with exactly `systemctl reboot`, then report back
before plugging anything in. This is a user-executed reboot instruction;
no agent reboot command executed. New boot arms0104 options. Hardware paths
and addresses remain those recorded in preceding installation entry:
ATC0xf03000000 size0x4c000, crossbar0xf0304c000 size0x4000,
lpdptx0xf03050000 size0x8000, axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000, pipehandler0xf02a84000 size0x4000,
dcpext1 0x315c00000, NHI0xf01f00000, ACIO0xf01ac0000,
DPIN0 0xf01e50000 size0x4000. No new manual address access or mapping;
no forbidden panel mapping, /dev/mem, PHY mode change or module unload.
On return verify loaded modules/eDP and disarm future boots before separately
logged single RIGHT-port attachment. No picture success claimed.

## 2026-09-22 —0104 boot verified; disarm future boots before attachment

Boot c7df4aec-08c9-475c-87c9-58c7de8499b0. Hub/external display absent;
eDP-1 active3456x2160@120, DPMS1, disabledfalse. All four loaded build IDs
match candidates: DRM3bc81d7a70df6a01cdca3b8d1da93df2b8e22ef4,
ATCf4fc4b28eb06cabfd7b88d2fdcf6b8b72c42614e,
mux6effcfefd97193d8737d73ba31a56adbb4899a0c,
TB016770f55ed62a96a882387ca75dafc3887438c5.
NativeDPIN and tunnelclock flags Y. After commit/push execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0104.py disarm
```

Deletes0104 boot options and rebuilds/verifies initramfs. Current loaded
readonly flags remain Y for one attachment. No live parameter/MMIO/mapping,
module reload or reboot. No addresses accessed: test resources remain right
ATC0xf03000000 size0x4c000, crossbar0xf0304c000 size0x4000,
lpdptx0xf03050000,axi2af0xf00000000,usb2phy0xf02a90000,
pipehandler0xf02a84000,dcpext1 0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000. Hotplug separately logged after success.

## 2026-09-22 —0104 disarmed successfully; single RIGHT-port hub test

Disarm exited0 and verified image; SHA256
361dcfd6eb2a4cee098947d22087f21517741e4e64fe878555ce43f3f4c387ee.
Current boot retains loaded experiment; future boots disarmed.
After committing and pushing this entry request exactly: connect OWC hub once
to Mac RIGHT USB-C port with monitor attached to hub, leave connected for
capture, report actual picture/no signal and whether eDP remains on. Do not
replug/reboot. If eDP blacks out, unplug hub and stop. Keyboard untested unless
attached and checked. No shell command initiates physical attachment.

Driver-owned first-attempt scope unchanged from0103. ATC core0xf03000000
size0x4c000 offsets/masks008/3ffff,1b0/fff,7000/207c,2224/3,
2080/ffffffff,2084/0fffffff,2088/007fffff,2208/001f0000,2220/80,
2214/1,2200/54,2000/1ffffff9; preflight7000,2200,2000,7044;
statusa74/7044. Owner-mapped lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000. Crossbar0xf0304c000 size0x4000,
source2 toDPIN0: normalcontrols000,004,008,00c,014,018,01c,024,028,
02c,030,034,050,070. Nativeup clears004bit2,014bit2,024bit0;
reads804bit2,810bit2,81cbit0; sets008bit2,018bits5:4=1,028bits1:0=1,
000bit2,00cbit2,01cbit0,034bit0,02cbit2. No selector rewrite or
clock-disable/reset-assertion in nativeup. Snapshots000,004,008,00c,014,
018,01c,024,028,02c,030,034,040,044,048,04c,050,060,070,800,020,820,81c.
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000;
DPIN0 0xf01e50000 size0x4000 CONTROL+c requestbit0,HPD+0/ACK+10reads.
0104 same-rate repeat returns cached success without another hardware attempt.
No forbidden ACIO analog, panel mappings,39c000000 assignment,/dev/mem,
PHY mode override, manual tunnel or module unload.

After user connects, capture exactly (private raw output, not committed):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0104-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0104-right-kernel.log
modetest -M apple -e
```

Confirm live right port in logs, repeated completion ACK and frame/modeset
outcome; actual visible picture required regardless of Hyprland/clock status.

## 2026-09-22 —0104 no signal; inspect existing DP configuration interfaces

User reports connected, monitor idle/no picture. Capture completed. Right
NHI f01f00000 confirmed, PLL result0, nativeup0,4lanes,DPRX1,crossbar800=4,
mode and frame completed. No repeated DID_CHANGE this attachment, so0104
cache path unexercised. eDP and USB-3 enabled in Hyprland, not proof of video.

After commit/push execute exactly:

```
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/regs > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0104-dpin-regs.txt
sudo -n cat /sys/kernel/debug/thunderbolt/0-1/port19/regs > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0104-dpout-regs.txt
```

Reads USB4 TB_CFG_PORT configuration space on route0 adapter5 and route1
adapter19 using existing tb_port_read transport, not physical MMIO maps.
Reviewed debugfs.c port_regs_show: runtime-PM reference, domain lock, basic
DWORD offsets0..8, then existing capability chain with advertised lengths;
DP v1 capability relative DWORD0..8. Includes any advertised VSE reads,
no VSE writes, no hop credit writes, no counters reset or sideband operation.
Transport owner is right NHI0xf01f00000/ACIO0xf01ac0000. No new physical
mapping/address access; no panel,disp or ATC manual register operations.
Hub remains attached for this read-only snapshot; no replug/reboot requested.
Raw capture files remain private/untracked.

## 2026-09-22 —0104 adapter reads completed; request safe unplug

Both logged debugfs reads completed. Host/hub DP status both4lanes,HBR;
CM handshake clear, VE/AE/HPD set. See notes/2026-09-22-0104-result.md.
No new kernel patch, install or reboot. Monitor still no picture.
After committing/pushing request unplug hub from RIGHT port and leave direct
adapter disconnected. No shell command initiates removal. Normal teardown
can restore saved ATC clock fields at core0xf03000000 size0x4c000:
008/3ffff,1b0/fff,7000/207c,2224/3,2080/ffffffff,2084/0fffffff,
2088/007fffff,2208/001f0000,2220/80,2214/1,2200/54,2000/1ffffff9.
Normal driver-owned resources include lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000,crossbar0xf0304c000 size0x4000,
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000 size0x4000,CONTROL+c requestbit0,HPD+0/ACK+10reads.
Crossbar teardown controls000,004,008,00c,014,018,01c,024,028,02c,030,034,
050,070. No new mapping/manualMMIO/forbidden panel access or module unload.
If eDP blacks out, stop with hub unplugged. No reconnect or reboot requested.

## 2026-09-22 —0105 staged-route candidate; install with hub unplugged

User confirmed unplug. Preflight passes, eDP active,0104 cleanup rate0 result0.
0105 source/test/patch described in notes/2026-09-22-0105-deferred-gates.md.
After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0105.py install
```

Back up nine module/image files to /var/tmp/j416s-0105-before; install pinned
modules/options, depmod, rebuild/verify initramfs. No live module reload,
parameter write, MMIO, mapping or reboot. Future candidate uses existing
right ATC0xf03000000 size0x4c000,crossbar0xf0304c000 size0x4000,
lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000,
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000 size0x4000. None accessed during this install.
Initial crossbar selection writes only030; existing nativeup gates occur
after clock setup. No new address access; prohibited operations remain
prohibited. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-22 —0105 packaging check rollback; corrected installation retry

First install rebuilt image but failed the newly added requirement that mux
be packaged inside initramfs. Crossbar is normally absent there and loads
from rootfs. Installer automatically restored all nine originals and removed
0105 options. Restored image hash matches prior disarmed0104 exactly:
361dcfd6eb2a4cee098947d22087f21517741e4e64fe878555ce43f3f4c387ee.
No live change/reboot. Keep first verified backup untouched.

Corrected0105 image verification to accept absent mux, while validating any
packaged copy and retaining checksum verification of installed rootfs module
copies. This matches prior installers and actual packaging. New backup path
/var/tmp/j416s-0105-retry-before avoids overwriting first backup.
After commit/push retry exact command:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0105.py install
```

File-only install, depmod/initramfs build/verification. No hardware addresses
accessed; resource scope remains preceding0105 entry (ATCf03000000,
crossbarf0304c000,DPINf01e50000,NHIf01f00000,ACIOf01ac0000,DCP315c00000).
No live reload/MMIO/parameter write, no reboot. Hub/direct adapter unplugged.

## 2026-09-22 —0105 installed/verified; request unplugged reboot

Retry succeeded, verified backup /var/tmp/j416s-0105-retry-before and pinned
rootfs modules/initramfs options. New image SHA256
7aadcd5f52258afb7161af973cc2cf59a9d61937b83dd7a7d478446858d6eb3e.
Post-install preflight passes; hub/external display absent. Build/tests and
checkpatch pass (0errors/0warnings). Kernel commitf79519f, display patches
and notes pushed. No live module loaded, no hardware result yet.

After committing/pushing request user command exactly `systemctl reboot`,
with hub and direct display adapter kept unplugged. No agent reboot command.
Boot uses0105 existing owner resources: ATCf03000000 size4c000,
crossbarf0304c000 size4000,lpdptxf03050000 size8000,
axi2aff00000000 size4000,usb2phyf02a90000 size4000,
pipehandlerf02a84000 size4000,DCP315c00000,NHIf01f00000,
ACIOf01ac0000,DPINf01e50000 size4000 (all hexadecimal addresses).
No manual MMIO or new mapping; no panel mapping,39c000000 assignment,
USB4 lane mode override, module unload or forbidden operation.
After reboot verify loaded hashes, eDP and mux readonly flag, then separately
log/push disarm and single right-port attachment. Do not connect yet.

## 2026-09-22 —0105 boot verified; disarm future boots

Boot4198e4ef-c026-41aa-8aa9-9275e358dbc3, preflight passes, hub and external
display absent. eDP active3456x2160@120,DPMS1,disabledfalse. All loaded IDs
match candidates: DRM3bc81d7a70df6a01cdca3b8d1da93df2b8e22ef4,
ATCf4fc4b28eb06cabfd7b88d2fdcf6b8b72c42614e,
muxc37ada7d21313f63257ed02934264d5a044ac376,
TB016770f55ed62a96a882387ca75dafc3887438c5.
Mux usb4_defer_bringup Y; DRM native/clock,ATCclock,TBnative flags Y.
After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0105.py disarm
```

Removes0105 options and rebuilds/verifies initramfs. Current readonly flags
remain Y for this test. No live MMIO,mapping,module reload or parameter write.
No addresses accessed; future/current driver resource scope remains
ATC0xf03000000,crossbar0xf0304c000,lpdptx0xf03050000,
axi2af0xf00000000,usb2phy0xf02a90000,pipehandler0xf02a84000,
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,DPIN0 0xf01e50000.
Hotplug will be logged separately after successful disarm.

## 2026-09-22 —0105 disarmed; single right-port attachment

Disarm exited0, image verified; SHA256
361dcfd6eb2a4cee098947d22087f21517741e4e64fe878555ce43f3f4c387ee.
Current0105 flags remain enabled; future boots disarmed. After committing
and pushing this entry request exactly: connect hub once to RIGHT USB-C port
with monitor on hub; leave connected for capture, report visible picture and
eDP status. If eDP blacks out, unplug hub and stop. No replug/reboot.
No shell command initiates physical connection. Keyboard untested unless
attached and checked.

Scope is existing owner mappings. ATC0xf03000000 size0x4c000 masks
008/3ffff,1b0/fff,7000/207c,2224/3,2080/ffffffff,2084/0fffffff,
2088/007fffff,2208/001f0000,2220/80,2214/1,2200/54,2000/1ffffff9;
preflight7000,2200,2000,7044; statusa74/7044.
Lpdptx0xf03050000 size0x8000,axi2af0xf00000000 size0x4000,
usb2phy0xf02a90000 size0x4000,pipehandler0xf02a84000 size0x4000.
Crossbar0xf0304c000 size0x4000, DPIN0/source2. Initial0105 selection only
030bits15:12/3:0. Existing ACTIVATE teardown can clear000,008,00c,018,01c,
028,02c,034 and030 and assert resets004,014,024. It now omits050/070.
After successful PLL, nativeup releases004bit2,014bit2,024bit0; reads
804bit2,810bit2,81cbit0; sets008bit2,018bits5:4=1,028bits1:0=1,
000bit2,00cbit2,01cbit0,034bit0,02cbit2. No selector rewrite then.
Snapshots000,004,008,00c,014,018,01c,024,028,02c,030,034,040,044,048,
04c,050,060,070,800,020,820,81c. No new addresses added by0105.
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000 size0x4000 CONTROL+c bit0,HPD+0/ACK+10 reads.
No forbidden panel mappings,analog writes,39c000000 assignment,/dev/mem,
manual tunnel,PHY mode override or module unload.

After user connects capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0105-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0105-right-kernel.log
modetest -M apple -e
```

Confirm right port and pre-clock gates off, then PLL/nativeup result,034/800,
lanes/DPRX and actual picture. If sequence stalls, capture and stop without
retrying gates or changing registers. No visible success assumed.

## 2026-09-22 —0105 connection captured, visible outcome pending

Previously logged capture commands completed. Right-port deferred selection
verified with gates0 before PLL, then PLL/nativeup result0,4lanes,DPRX1,
mode/framecomplete,800=4. Crossbar034 still0. eDP and BenQ both enabled in
Hyprland. User physical picture confirmation pending; do not claim success
or failure yet. See notes/2026-09-22-0105-result.md. Future boots disarmed.
No additional hardware action, parameter write or reboot requested.

## 2026-09-22 —0105 user confirms no signal; end this attachment

User confirms external inactive/no picture. Updated0105 result with failed
visible outcome and additional offline crossbar lookup/accessor checks.
No speculative kernel patch, live MMIO or parameter change. Future boots
remain disarmed. After committing/pushing request unplug RIGHT-port hub;
leave direct adapter disconnected. No reboot/reconnection requested.
Physical unplug may invoke existing owner cleanup: ATC0xf03000000 size4c000
saved masks008/3ffff,1b0/fff,7000/207c,2224/3,2080/ffffffff,
2084/0fffffff,2088/007fffff,2208/001f0000,2220/80,2214/1,2200/54,
2000/1ffffff9. Other resources lpdptx0xf03050000 size8000,
axi2af0xf00000000 size4000,usb2phy0xf02a90000 size4000,
pipehandler0xf02a84000 size4000,crossbar0xf0304c000 size4000,
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000 size4000 CONTROL+cbit0,HPD+0/ACK+10reads.
0105 DPIN0 crossbar teardown controls000,004,008,00c,014,018,01c,024,
028,02c,030,034; excludes legacy050/070. Sizes/offsets hexadecimal.
No new mapping/manualMMIO/panelaccess/moduleunload. If eDP blacks out, stop
with hub unplugged. No shell command initiates physical removal.

## 2026-09-22 —0106 built offline; DP-IN packet-counter diagnostic

No speculative crossbar/gate-ordering change. Instead, offline re-decode of
the already-captured, already-logged0104-dpin-regs.txt/0104-dpout-regs.txt
(no new hardware read) shows host DP IN route0port5 and hub DP OUT-side
route1port19 both report TB_CFG_PORT DWORD1 counters_support=1,max_counters=2.
Kernel commitf1640dd adds a default-off readonly module parameter
dp_video_counter on the core thunderbolt module: when set, drivers/
thunderbolt/tunnel.c's tb_dp_init_video_path assigns in_counter_index=0 on
only the DP video path's DP-IN-side hop, gated to Apple NHI+apple,j416s
machine+right-hand USB-C port (tb_apple_nhi_typec_index==2), matching the
existing restrictive-predicate style. This sets only the counter/
counter_enable bits already defined in TB_CFG_HOPS dword1 for that one hop;
it does not touch nfc_credits/initial_credits (hop credits), routing,
priority/weight, ACIO analog, or panel registers, and adds no new
ioremap/MMIO of its own — tb_path_activate already performs this exact write
for every tunnel type that uses a counter. Full design in
notes/2026-09-22-0106-dp-video-counter.md; checkpatch0errors/0warnings;
`make` in src/thunderbolt rebuilds only thunderbolt.ko (thunderbolt_apple,
mux, atc, appledrm are byte-identical to the currently-installed0105 build,
verified by SHA256). Readback after connection will use the existing
debugfs .../port5/counters and .../port19/counters files, not new code.

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0106.py install
```

Back up eleven module/image files to /var/tmp/j416s-0106-before (five module
pairs — atc,mux,appledrm,thunderbolt_apple,thunderbolt — plus initramfs);
install pinned modules/options, depmod, rebuild/verify initramfs. No live
module reload, parameter write, MMIO, mapping or reboot. Options keep the
0105 set active (appledrm usb4_protocol_probe=1 usb4_native_dpin=1
usb4_tunnel_clock=1; thunderbolt_apple dpin_native=1; phy_apple_atc
usb4_tunnel_clock=1; mux_apple_display_crossbar usb4_defer_bringup=1) and add
thunderbolt dp_video_counter=1. Candidate hashes: thunderbolt(core)
a70debca0d7fd8a53d8807358a6db922049f321ed24b8a6415ebf4f75b3a8898; atc
e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9; mux
38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24; appledrm
9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3;
thunderbolt_apple26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198
(last four unchanged from0105, reinstalled only for manifest symmetry).
Future candidate uses existing right ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-22 —0106 installed and verified; request unplugged reboot

Installer exited0, verified backup /var/tmp/j416s-0106-before (eleven files;
manifest confirms all four unchanged modules match0105 exactly and
thunderbolt(core) backup is the prior7842204c… build) and installed/initramfs
module hashes/options. New image SHA256
57ad3b1b1ad51ed0d7465a960ad7c0d5f5ceb0b6939b122191e366f9cab91c1c. Post-install
preflight passes, hub/external display absent. Recurring firmware/font/
architecture mkinitcpio warnings only; image verification passed. No live
reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct display
adapter unplugged, reboot with exactly `systemctl reboot`, then report back
before plugging anything in. This is a user-executed reboot instruction; no
agent reboot command executed. New boot arms0106 options (the0105 set plus
thunderbolt dp_video_counter=1). Hardware paths/addresses remain those
recorded in the preceding installation entry: ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. No new manual address access or
mapping; no forbidden panel mapping,/dev/mem,PHY mode change or module
unload. On return verify loaded modules/eDP and disarm future boots before
separately logged single RIGHT-port attachment. No picture success claimed.

## 2026-09-22 —0106 boot verified; disarm future boots

Boota5e4aebd-d270-4224-9857-9b2e0da6a07b, preflight passes, hub and external
display absent. eDP-1 connected,DPMSOn,enabled. Installed thunderbolt(core)
matches candidatea70debca0d7fd8a53d8807358a6db922049f321ed24b8a6415ebf4f75b3a8898.
Loaded readonly flags: thunderbolt dp_video_counter=Y,thunderbolt_apple
dpin_native=Y,mux_apple_display_crossbar usb4_defer_bringup=Y,phy_apple_atc
usb4_tunnel_clock=Y,appledrm usb4_protocol_probe/usb4_native_dpin/
usb4_tunnel_clock=Y. No DP tunnel exists yet so dp_video_counter has not
applied to any hop.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0106.py disarm
```

Removes0106 options and rebuilds/verifies initramfs. Current readonly flags
remain Y for this test. No live MMIO,mapping,module reload or parameter
write. No addresses accessed; resource scope remains ATC0xf03000000,
crossbar0xf0304c000,DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000. Hotplug will be logged separately after successful disarm.

## 2026-09-22 —0106 disarmed; single right-port attachment with counter readback

Disarm exited0, image verified; new SHA256
1c391b656ff49f1ce1c9019a42998d458d62f91747e7c6b6bea74928e4366f55. Current
0106 flags (including dp_video_counter) remain enabled for this boot only;
future boots disarmed. After committing and pushing this entry request
exactly: connect hub once to RIGHT USB-C port with monitor on hub; leave
connected for capture; report visible picture and eDP status. If eDP blacks
out, unplug hub and stop. No replug/reboot. No shell command initiates
physical connection. Keyboard untested unless attached and checked.

Scope is the existing0105 owner mappings (ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000 CONTROL+cbit0,HPD+0/ACK+10reads)
plus the new0106 addition: when the video path's DP-IN hop is created on
this exact route, tb_dp_init_video_path sets in_counter_index=0, and
tb_path_activate (existing generic code, unmodified) writes only the
counter/counter_enable bits of that hop's existing TB_CFG_HOPS dword1 via
the normal tb_port_write control-plane path — no new ioremap/MMIO, no
change to nfc_credits/initial_credits/routing/priority/weight, no ACIO
analog or panel access. No forbidden operation is added by this candidate.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0106-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0106-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0106-dpin-counters.txt
sudo -n cat /sys/kernel/debug/thunderbolt/0-1/port19/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0106-dpout-counters.txt
```

The last two are the new read-only diagnostic reads (existing debugfs
mechanism, TB_CFG_COUNTERS via tb_port_read; no write to either file).
Confirm right port and pre-clock gates off, then PLL/nativeup result,
034/800, lanes/DPRX, both counter reads, and actual picture. If sequence
stalls, capture and stop without retrying gates or changing registers. No
visible success assumed regardless of counter values.

## 2026-09-22 —0106 connection captured; DP-IN counter nonzero; request unplug

Previously logged capture commands completed. Sequence reproduces0105
exactly (route select030=2002gates deferred,PLL/nativeup result0,4lanes,
DPRX_DONE1,frame complete id=2,034 still0,800=4). User confirms "nothing new
to see" — no external picture, same outcome as0102-0105. eDP stayed
connected throughout and after capture.

New: DP-IN hop counter (route0-0 port5,counter index0, enabled for the first
time this boot by0106) reads0x0000421b — nonzero, where tb_path_activate
clears it to0 at every activation. This is new hardware evidence that video
traffic left the crossbar/DP IN adapter into the USB4 tunnel on this attempt.
Hub-side read (route0-1 port19,counter index0) reads0, but that hop's
counter was never enabled by0106 (only the DP-IN hop was instrumented, by
design); an unenabled counter reading zero is uninformative and no
conclusion is drawn from it. Full analysis in
notes/2026-09-22-0106-result.md. No speculative register write or reboot
performed. Future boots remain disarmed.

After committing/pushing request unplug RIGHT-port hub; leave direct adapter
disconnected. No reboot/reconnection requested. Physical unplug may invoke
existing owner cleanup identical in scope to every prior0102-0105 unplug:
ATC0xf03000000 size4c000 saved masks008/3ffff,1b0/fff,7000/207c,2224/3,
2080/ffffffff,2084/0fffffff,2088/007fffff,2208/001f0000,2220/80,2214/1,
2200/54,2000/1ffffff9. Other resources lpdptx0xf03050000 size8000,
axi2af0xf00000000 size4000,usb2phy0xf02a90000 size4000,
pipehandler0xf02a84000 size4000,crossbar0xf0304c000 size4000,
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000 size4000 CONTROL+cbit0,HPD+0/ACK+10reads. No new
mapping/manualMMIO/panelaccess/moduleunload. If eDP blacks out, stop with
hub unplugged. No shell command initiates physical removal.

## 2026-09-22 -0107 built offline; downstream (hub-side) hop counter

Oliver confirmed the0106 unplug. Extending the same0106 mechanism rather
than opening a new question: kernel commit8c472cb adds to the existing
dp_video_counter gate in tb_dp_init_video_path (drivers/thunderbolt/
tunnel.c) - when it already matches (Apple NHI,apple,j416s,right-hand
USB-C port,DP IN adapter) - also set in_counter_index=0 on the video path's
LAST hop (the downstream router's ingress side of the same path; concretely
the hub's upstream link-in port, not the DP OUT adapter itself, which is
always this path's terminal out_port and has no hop counter of its own in
this model). Uses the same unmodified tb_path_activate() write as0106; no
change to credits/routing/priority/weight on either hop, no new ioremap/
MMIO. Design and interpretation in
notes/2026-09-22-0107-downstream-counter.md. checkpatch on the full
accumulated tunnel.c diff:0errors/0warnings. `make` in src/thunderbolt
rebuilds only thunderbolt.ko; the other four modules are unchanged from
0106 (verified by SHA256).

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0107.py install
```

Back up eleven module/image files to /var/tmp/j416s-0107-before (same five
module pairs as0106 plus initramfs); install pinned modules/options,
depmod, rebuild/verify initramfs. No live module reload, parameter write,
MMIO, mapping or reboot. Options keep the0105 set active plus thunderbolt
dp_video_counter=1 (unchanged option string from0106 - the new hop is
enabled in code, not by a new option). Candidate hashes: thunderbolt(core)
ebbd7a80568be7422d403bc6d05a5d0a577dbf24d4f939c359e0561f69255906; atc
e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9; mux
38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24; appledrm
9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3;
thunderbolt_apple26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-22 -0107 installed and verified; request unplugged reboot

Installer exited0, verified backup /var/tmp/j416s-0107-before (eleven files;
manifest confirms all four unchanged modules match0106 exactly and
thunderbolt(core) backup is the prior0106 buildstarting a70debca...). New
image SHA256 f92184cb059b0479a254de4d1f407b84557a06d2fe391846860f0cd5a2563949.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms0107 options
(same0105+dp_video_counter=1 option string as0106; the new downstream-hop
counter is enabled in code, not by a new option). Hardware paths/addresses
remain those recorded in the preceding installation entry: ATC0xf03000000
size0x4c000,crossbar0xf0304c000 size0x4000,DCP0x315c00000,
NHI0xf01f00000,ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. No new manual
address access or mapping; no forbidden panel mapping,/dev/mem,PHY mode
change or module unload. On return verify loaded modules/eDP and disarm
future boots before separately logged single RIGHT-port attachment. No
picture success claimed.

## 2026-09-22 -0107 boot verified; disarm future boots

Boot1b4327ec-5e93-45cc-a6eb-b6d88a907edd, preflight passes, hub and external
display absent. eDP-1 connected,DPMSOn. Installed thunderbolt(core) matches
candidate ebbd7a80568be7422d403bc6d05a5d0a577dbf24d4f939c359e0561f69255906.
Loaded readonly flags: thunderbolt dp_video_counter=Y,thunderbolt_apple
dpin_native=Y,mux_apple_display_crossbar usb4_defer_bringup=Y,phy_apple_atc
usb4_tunnel_clock=Y,appledrm usb4_protocol_probe/usb4_native_dpin/
usb4_tunnel_clock=Y. No DP tunnel exists yet so dp_video_counter has not
applied to any hop.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0107.py disarm
```

Removes0107 options and rebuilds/verifies initramfs. Current readonly flags
remain Y for this test. No live MMIO,mapping,module reload or parameter
write. No addresses accessed; resource scope remains ATC0xf03000000,
crossbar0xf0304c000,DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000. Hotplug will be logged separately after successful disarm.

## 2026-09-22 -0107 disarmed; single right-port attachment with two-hop counter readback

Disarm exited0, image verified; new SHA256
4d77bf2db9ccd8b694aeeeee5ff762f84881e1ff1e48b94455f919de329a8993. Current
0107 flags (including dp_video_counter) remain enabled for this boot only;
future boots disarmed. After committing and pushing this entry request
exactly: connect hub once to RIGHT USB-C port with monitor on hub; leave
connected for capture; report visible picture and eDP status. If eDP blacks
out, unplug hub and stop. No replug/reboot. No shell command initiates
physical connection. Keyboard untested unless attached and checked.

Scope is identical to0106 (existing0105 owner mappings: ATC0xf03000000
size0x4c000,crossbar0xf0304c000 size0x4000,lpdptx0xf03050000 size0x8000,
axi2af0xf00000000 size0x4000,usb2phy0xf02a90000 size0x4000,
pipehandler0xf02a84000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000 CONTROL+cbit0,HPD+0/ACK+10reads)
plus0107's addition: the video path's LAST hop (downstream router's ingress
side, i.e. the hub's upstream link-in port) also gets in_counter_index=0 via
the same unmodified tb_path_activate() write. No new ioremap/MMIO, no
change to credits/routing/priority/weight, no ACIO analog or panel access.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0107-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0107-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0107-dpin-counters.txt
```

The kernel log determines the hub's route and the video path's actual last
hop `in_port` number (read from the crossbar/tunnel activation messages,
same way route/port were confirmed for every prior right-port attempt); the
matching debugfs counters file for that exact route/port is read separately
once identified, rather than guessed in advance. Confirm right port,
pre-clock gates off, PLL/nativeup result,034/800, lanes/DPRX, both counter
reads, and actual picture. If sequence stalls, capture and stop without
retrying gates or changing registers. No visible success assumed regardless
of counter values.

## 2026-09-22 -0107 connection captured; both hops nonzero; unplug confirmed

Previously logged capture commands completed. Sequence reproduces0105/0106
exactly (route select gates deferred,PLL/nativeup result0,4lanes,DPRX_DONE1,
frame complete id=2). User confirms "connected, no external display / still
standby - no other problems" - same outcome as0102-0106. eDP stayed
connected throughout.

DP-IN hop counter (route0-0 port5,idx0): 0x0000a465. To find the downstream
hop actually carrying our marker, all hub ports1-23 under route0-1 were
scanned read-only (cat .../pathfor each, no writes) and decoded; hub port1
hop10 (out_port=19,counter=0,counter_enable=1) uniquely matches what0107's
gate sets - confirmed as the video path's downstream hop, not assumed.
Reading its counter (route0-1 port1,idx0): 0x0001765b. Both nonzero, where
tb_path_activate clears each to0 at every activation. New evidence: video
traffic reaches the hub-side hop that forwards directly to the DP OUT
adapter (out_port=19). Combined with0104's DP OUT CS registers already
showing4lanes/HBR negotiated and DPRX done, and the standing fact this
exact hub+adapter+monitor combo works under macOS, the crossbar/DCP/tunnel
path built across0102-0107 is no longer a credible explanation. Remaining
suspects are outside Linux driver control (hub firmware/physical DP-alt-mode
training) or unexplored (DP tunnel bandwidth allocation mode - not yet
checked either way). Full analysis in notes/2026-09-22-0107-result.md.

Oliver confirmed the hub is unplugged from the right port; sysfs shows no
thunderbolt devices, eDP remained connected before and after. No further
hardware action performed this boot (one-attempt guard). No speculative
register write or reboot performed.

## 2026-09-22 -0108 built offline; grant DP bandwidth immediately

Purely offline review of already-captured data (0104/0107 dumps, no new
hardware read): the host DP IN adapter's LOCAL field has DP_COMMON_CAP_BW_MODE
(bit28) set, so tb_dp_pre_activate always enters bandwidth-allocation-mode
for this tunnel; tb_dp_bandwidth_alloc_mode_enable then explicitly grants0
Mb/s initially per spec, relying on the DP IN adapter to request more via a
hardware notification later. The DP IN adapter's own DP_STATUS field
(offset0x06,"STAT" in existing dumps,bits31:24) reads STAT=00000000 -
allocated bandwidth0 - in every already-captured right-port attempt
(0104,0107), and nothing in apple.c has ever been shown to generate or
forward the notification that would raise it. Kernel commit9e122f5 adds a
default-off module parameter dp_bw_grant that, gated by the same restrictive
predicate as dp_video_counter (now factored into a shared
tb_dp_is_apple_j416s_right_dpin helper, no behavior change to the existing
counter), grants min(non_reduced_bw,estimated_bw) immediately instead of0.
estimated_bw is tunnel->max_down/max_up - bandwidth the connection manager
already reserved for this tunnel before it existed - so the grant can never
exceed an already-admitted budget and cannot oversubscribe the fabric or
affect any other tunnel; no other DP adapter on any other system is
affected. Writes exactly one field (DP_STATUS allocated-bandwidth) via the
existing unmodified usb4_dp_port_allocate_bandwidth() helper the driver
already calls at this point for every DP tunnel; does not touch DP IN hop
credits, routing, ACIO analog or panel registers. Full analysis in
notes/2026-09-22-0108-bandwidth-grant.md. checkpatch on the full
accumulated tunnel.c diff:0errors/0warnings. `make` in src/thunderbolt
rebuilds only thunderbolt.ko; the other four modules are unchanged from
0107 (verified by SHA256).

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0108.py install
```

Back up eleven module/image files to /var/tmp/j416s-0108-before (same five
module pairs as0106/0107 plus initramfs); install pinned modules/options,
depmod, rebuild/verify initramfs. No live module reload, parameter write,
MMIO, mapping or reboot. Options keep the0105 set plus
dp_video_counter=1 (kept enabled for continued observability) and the new
dp_bw_grant=1. Candidate hashes: thunderbolt(core)
dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7; atc
e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9; mux
38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24; appledrm
9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3;
thunderbolt_apple26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-22 -0108 installed and verified; request unplugged reboot

Installer exited0, verified backup /var/tmp/j416s-0108-before (eleven files;
manifest confirms all four unchanged modules match0107 exactly and
thunderbolt(core) backup is the prior0107 build starting ebbd7a80...). New
image SHA256 59e08935c6163bee6ec61811676216bfda6c7b4371ac3ceabe17f7028b777f1e.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms0108 options
(0105 set plus dp_video_counter=1 and the new dp_bw_grant=1). Hardware
paths/addresses remain those recorded in the preceding installation entry:
ATC0xf03000000 size0x4c000,crossbar0xf0304c000 size0x4000,
DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000.
No new manual address access or mapping; no forbidden panel mapping,
/dev/mem,PHY mode change or module unload. On return verify loaded
modules/eDP and disarm future boots before separately logged single
RIGHT-port attachment. No picture success claimed.

## 2026-09-22 -0108 boot verified; disarm future boots

Boote330ca2f-5a47-4bd9-af81-d8ac70e6d06e, preflight passes, hub and external
display absent. eDP-1 connected. Installed thunderbolt(core) matches
candidate dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7.
Loaded readonly flags: thunderbolt dp_video_counter=Y,dp_bw_grant=Y,
thunderbolt_apple dpin_native=Y,mux_apple_display_crossbar
usb4_defer_bringup=Y,phy_apple_atc usb4_tunnel_clock=Y,appledrm
usb4_protocol_probe/usb4_native_dpin/usb4_tunnel_clock=Y. No DP tunnel
exists yet so neither new flag has applied to any hop/adapter.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0108.py disarm
```

Removes0108 options and rebuilds/verifies initramfs. Current readonly flags
remain Y for this test. No live MMIO,mapping,module reload or parameter
write. No addresses accessed; resource scope remains ATC0xf03000000,
crossbar0xf0304c000,DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000. Hotplug will be logged separately after successful disarm.

## 2026-09-22 -0108 disarmed; single right-port attachment with bandwidth-grant test

Disarm exited0, image verified; new SHA256
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4. Current
0108 flags (dp_video_counter,dp_bw_grant) remain enabled for this boot only;
future boots disarmed. After committing and pushing this entry request
exactly: connect hub once to RIGHT USB-C port with monitor on hub; leave
connected for capture; report visible picture and eDP status. If eDP blacks
out, unplug hub and stop. No replug/reboot. No shell command initiates
physical connection. Keyboard untested unless attached and checked.

Scope is identical to0107 (existing0105 owner mappings unchanged) plus
0108's addition: when tb_dp_bandwidth_alloc_mode_enable runs for this exact
route, it grants min(non_reduced_bw,estimated_bw) instead of0 via the
existing unmodified usb4_dp_port_allocate_bandwidth() helper - one field
(DP_STATUS allocated-bandwidth) on the DP IN adapter, bounded by what the
connection manager already reserved for this tunnel. No new ioremap/MMIO,
no change to hop credits/routing/priority/weight, no ACIO analog or panel
access.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0108-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0108-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0108-dpin-counters.txt
```

The downstream-hop counter and the DP IN/DP OUT STAT (allocated-bandwidth)
registers are read the same way0107 identified them (scan/decode, not
assumed) once the actual route/port is confirmed from this attempt's log.
Confirm right port, pre-clock gates off, PLL/nativeup result,034/800,
lanes/DPRX, counter/bandwidth readback, and actual picture - the last of
these decided only by Oliver's visual confirmation, not by any register or
log line. If sequence stalls, capture and stop without retrying gates or
changing registers.

## 2026-09-22 -0108 connection captured; bandwidth grant confirmed; unplug confirmed

Previously logged capture commands completed. Sequence reproduces
0105-0107 exactly. User confirms "connected... external monitor still idle
/ standby" - same outcome as0102-0107. eDP stayed connected throughout.

Host DP IN adapter STAT (DP_STATUS,bits31:24=allocated bandwidth) read
0x24000000 at101.115s, before DPRX_DONE - nonzero, where every prior
capture (0104,0107) showed STAT=00000000. This is exactly the field
dp_bw_grant's usb4_dp_port_allocate_bandwidth() writes; it changed exactly
as designed, confirming real nonzero bandwidth was granted for the first
time in this investigation. DP-IN packet counter also nonzero (0x3740).
Hub DP OUT's own local STAT=04000000 unchanged (expected - this patch only
ever writes the DP IN side's field). Full analysis in
notes/2026-09-22-0108-result.md.

This rules out the zero-bandwidth-allocation hypothesis as the (sole)
explanation. Combined with0106/0107, three separate independently-verified
USB4/tunnel-level hypotheses (crossbar not emitting;tunnel not carrying
traffic to the hub;zero allocated bandwidth) are now ruled out with hard
evidence each time. Remaining likely causes are outside Linux driver
observation/control (hub firmware,physical DP-alt-mode link training) or
require native macOS comparison.

Oliver confirmed the hub is unplugged from the right port; sysfs shows no
thunderbolt devices, eDP remained connected before and after. No further
hardware action performed this boot (one-attempt guard). No speculative
register write or reboot performed.

Oliver chose to compare against real macOS on this Mac next (boot into
macOS, plug the same hub+adapter+monitor, capture IORegistry/log telemetry)
rather than continue guessing at further Linux-side USB4/tunnel theories.
That is a separate investigation track requiring its own preflight and
action entries before any macOS-side capture or reboot.

## 2026-09-22 -prepared native macOS DP-bandwidth comparison, user-operated

Oliver chose to compare against real macOS on this M2 rather than continue
guessing at further Linux-side USB4/tunnel theories, after0106-0108 ruled
out three separate, independently-verified hypotheses with hard evidence
(crossbar not emitting;tunnel not reaching the hub;zero allocated
bandwidth). The existing macos-captures (disconnected-074155,
hub-074227 right,hub-074252 left-back, all working video) only contain
generic topology (ioreg service tree without properties,system_profiler);
per notes/2026-09-22-macos-working-hub.md's own stated limits they contain
no register trace,firmware RPC order or bandwidth-allocation detail, so
they cannot answer whether native macOS uses the same0-then-request
bandwidth-allocation-mode dance our0108 evidence shows Linux stuck in.

New read-only collector scripts/collect-macos-dp-bandwidth.sh (committed
below) targets that gap: full ioreg properties (not just class tree) for
AppleATCDPINAdapterPort,IODPPortService,AppleT602XATCDPXBAR,
AppleT602XDisplayCrossbar,DCPDPDeviceProxy,IOThunderboltPort,
IOThunderboltSwitch,AppleThunderboltIP,AppleDPTXDisplayPort; a5-minute
unified-log window filtered to thunderbolt/displayport-related messages
(no sudo,no private-data unlock,no dtrace/settings change); and a
Thunderbolt/Displays topology snapshot. No sudo required by any command in
this script. Machine-checked (Mac14,10) before writing.

After this entry and the script are committed and pushed, this is a
user-operated sequence (not an unattended action), matching the earlier
0090 native-comparison precedent: unplug the OWC hub and all display
adapters from the M2; shut down the M2 using the desktop power menu; hold
its power button to reach Startup Options and select its existing macOS
installation. No new OS install or boot/security setting change. Normal
shutdown/boot touches normal system hardware; no manual register access is
requested. Known M2 Linux addresses for context only (not accessed by this
step): panel DCP0x389c00000,external DCPs0x289c00000/0x315c00000,right hub
path NHI0xf01f00000/ACIO0xf01ac0000/crossbar0xf0304c000.

In macOS, reconnect the known-working OWC hub with keyboard,VMM7100 and
monitor to the SAME RIGHT USB-C port used throughout0102-0108, confirm the
picture appears (as it has every time before), then in Terminal run:

```
curl -fL https://raw.githubusercontent.com/oliverlukschander/asahi-j416s-display/main/scripts/collect-macos-dp-bandwidth.sh -o /tmp/collect-macos-dp-bandwidth.sh
bash /tmp/collect-macos-dp-bandwidth.sh
```

This is normal native macOS hotplug on a setup already confirmed working
there; no Linux experimental parameter,manual tunnel or MMIO request. If
anything behaves unexpectedly, stop and report before continuing. Reports
save to the Desktop; no automatic upload/commit. Bring the resulting
directory back to this Linux session for review (as with the earlier M4
handoff) before drawing conclusions. No return reboot into Linux is
scheduled or authorized by this log entry.

## 2026-09-22 -0108 hub unplug confirmed (belated)

Oliver confirmed the hub is unplugged from the right port following the
0108 result and the subsequent native-analysis research (0106-0108's
counters/registers, bandwidth-ratio dead end, bringConnectionUp DPIN0
findings - all offline, no hardware). sysfs shows no thunderbolt devices;
eDP remained connected before and after. No hardware action was performed
during that research interval.

## 2026-09-22 -0109 built offline; set native CONNECTED bit on DPIN0

Continuing offline native analysis (no hardware access): traced the real
tunnel bring-up code AppleCIODPTX::bringConnectionUp (not the bandwidth-
ratio dead end) to four DPIN0 register writes native macOS performs that
this driver never has. One is fully confirmed unconditional (verified by
reading the callee AppleDPTX::setBitsInReg directly: mask=0/2,value=2, no
runtime dependency): sets bit1 on both HPD(+0x0) and CONTROL(+0xc) -
CONTROL's write is pure/unconditional; HPD's is gated in native code on a
single-stream check that is unconditionally true for every DPIN0 topology
this driver drives (one external monitor, never DP MST). Kernel commit
15045d6 adds APPLE_DPIN_CONNECTED(bit1) to drivers/thunderbolt/apple-dpin-
handshake.h, set on both registers when activating; failure rollback now
restores both INACTIVE and CONNECTED on CONTROL (previously only
INACTIVE) so a failed attempt does not leave CONNECTED stuck; HPD is not
rolled back (native teardown for it untraced, and this driver never wrote
HPD before this change). scripts/test-dpin-handshake.c updated and passes
(ASan/UBSan,9 scenarios). This touches only DPIN0 (0xf01e50000), already
safely used via apple_usb4_right_dpin0_set_active; no crossbar, ACIO
analog, lpdptxphy or other forbidden-register access. Full design,
confidence breakdown for each of the four found writes, and the plan for
resolving the remaining two (+0x14,+0x1c, which depend on runtime
DisplayPort negotiation data not present in the static kernelcache) are in
notes/2026-09-22-0109-dpin0-connected-bit.md.

Also fixed in passing: src/thunderbolt/apple-dpin-handshake.h was a stale
plain copy (not a symlink like every other file there), so the kernel-repo
edit was silently ignored by the module build until this was found and
fixed; verified the rebuilt thunderbolt_apple.ko hash only changed after
symlinking it. checkpatch on the header diff:0errors/0warnings. `make` in
src/thunderbolt rebuilds only apple.o/thunderbolt_apple.ko; the other four
modules, including core thunderbolt.ko, are unchanged from0108 (verified
by SHA256).

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0109.py install
```

Back up eleven module/image files to /var/tmp/j416s-0109-before (same five
module pairs as0106-0108 plus initramfs); install pinned modules/options,
depmod, rebuild/verify initramfs. No live module reload, parameter write,
MMIO, mapping or reboot. Options unchanged from0108 (this is unconditional
code behind the existing dpin_native=1 gate, not a new module parameter).
Candidate hashes: thunderbolt_apple
74d8250de35ab42a0ef58690887eb3a21cf463663d226aa769a177c0f3743b64;
thunderbolt(core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7;
mux38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24;
atce47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9;
appledrm9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-22 -0109 installed and verified; request unplugged reboot

Installer exited0, verified backup /var/tmp/j416s-0109-before (eleven
files; manifest confirms all four unchanged modules match0108 exactly and
thunderbolt_apple backup is the prior0108 build starting26703573...). New
image SHA256 6eee0c0fda4670a34188702a5f50652e32b53512d9b7d47b3ac8ec2b687ffa29.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms0109 (same
options as0108 - this candidate is unconditional code behind the existing
dpin_native=1 gate). Hardware paths/addresses remain those recorded in the
preceding installation entry: ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. No new manual address access
or mapping; no forbidden panel mapping,/dev/mem,PHY mode change or module
unload. On return verify loaded modules/eDP and disarm future boots before
separately logged single RIGHT-port attachment. No picture success claimed.

## 2026-09-22 -0109 boot verified; disarm future boots

Boot55780c37-7c7d-47e4-9e0a-27aaaacd8200, preflight passes, hub and
external display absent. eDP-1 connected. Installed thunderbolt_apple
matches candidate74d8250de35ab42a0ef58690887eb3a21cf463663d226aa769a177c0f3743b64.
Loaded readonly flags: thunderbolt_apple dpin_native=Y,
mux_apple_display_crossbar usb4_defer_bringup=Y,phy_apple_atc
usb4_tunnel_clock=Y,thunderbolt dp_video_counter=Y,dp_bw_grant=Y,appledrm
usb4_protocol_probe/usb4_native_dpin/usb4_tunnel_clock=Y. No DP tunnel
exists yet so the new CONNECTED-bit code has not run.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0109.py disarm
```

Removes0109 options and rebuilds/verifies initramfs. Current readonly flags
remain Y for this test. No live MMIO,mapping,module reload or parameter
write. No addresses accessed; resource scope remains ATC0xf03000000,
crossbar0xf0304c000,DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000. Hotplug will be logged separately after successful disarm.

## 2026-09-22 -0109 disarmed; single right-port attachment (native CONNECTED bit test)

Disarm exited0, image verified; new SHA256
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4 (matches
0108's disarmed image exactly, as expected since options are unchanged).
Current0109 flags remain enabled for this boot only; future boots
disarmed. After committing and pushing this entry request exactly: connect
hub once to RIGHT USB-C port with monitor on hub; leave connected for
capture; report visible picture and eDP status. If eDP blacks out, unplug
hub and stop. No replug/reboot. No shell command initiates physical
connection. Keyboard untested unless attached and checked.

Scope is identical to0108 (existing owner mappings unchanged) plus0109's
addition: apple_dpin_handshake now sets bit1 (APPLE_DPIN_CONNECTED) on
DPIN0 HPD(+0x0) and CONTROL(+0xc) when activating - confirmed-unconditional
native behavior, no new addresses, no forbidden register access.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0109-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0109-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0109-dpin-counters.txt
```

Confirm right port, pre-clock gates off, PLL/nativeup result,034/800,
lanes/DPRX, counter readback, and actual picture - the last decided only
by Oliver's visual confirmation. If sequence stalls, capture and stop
without retrying gates or changing registers.

## 2026-09-22 -0109 connection captured; CONNECTED bit confirmed clean; unplug confirmed

Previously logged capture commands completed. Sequence reproduces
0105-0108 exactly, plus the new handshake line: "native DPIN0: active=1
handshake=0" - the CONNECTED-bit writes on HPD/CONTROL ran and returned
success (no -EIO/-ENOLINK/-ETIMEDOUT). User confirms "connected, nothing
happened" - same no-signal outcome as0102-0108. eDP stayed connected
throughout. DP-IN packet counter again nonzero (0x5d34).

This rules out the CONNECTED-bit hypothesis - the one fully-confirmed,
unconditional native register write found so far - as a sole explanation.
Combined with0106-0108, four separate, independently-verified, non-
speculative hypotheses at the USB4/tunnel/DPIN0 level are now ruled out
with hard evidence each time. Full analysis in
notes/2026-09-22-0109-result.md. Remaining leads: the two runtime-
dependent DPIN0 fields (+0x14,+0x1c) whose exact values this project
cannot determine from the static kernelcache alone (plan in
notes/2026-09-22-0109-dpin0-connected-bit.md); or causes outside Linux
driver observation/control entirely.

Oliver confirmed the hub is unplugged from the right port; sysfs shows no
thunderbolt devices, eDP remained connected before and after. No further
hardware action performed this boot (one-attempt guard). No speculative
register write or reboot performed.

## 2026-09-22 -0110 built offline; explicit-guess test of remaining DPIN0 writes

Oliver chose to test a bounds-based estimate for the two remaining DPIN0
writes (+0x14,+0x1c) before pursuing DCP firmware extraction. A 3-agent
parallel static-analysis pass (top-down attributes-construction trace,
bottom-up field-setter search across the full __TEXT_EXEC, crossbar-
validation/log-string cross-check) confirmed the exact bit-packing formula
instruction-for-instruction from three independent traces, but could not
pin the underlying runtime value: it is a verbatim copy of a packed
attributes value supplied by a caller not locatable in this XNU
kernelcache, most likely the separate DCP coprocessor firmware. Bounded
finding used for this test: the rate-class subfield matches, bit-for-bit,
the same RBR=0/HBR=1/HBR2=2/HBR3=3 ordinal already used in this driver
(drivers/thunderbolt/tb_regs.h) - this link negotiates HBR2, giving
rate_class=2 with reasonable confidence; a second subfield's meaning is
weaker evidence, resolving to1 for a4-lane link. Kernel commit4b1450f
writes the resulting value (w20=9) to+0x1c(pure OR,shift7) and
+0x14(clears low byte,sets bit9), in native's own call order (HPD,+0x1c,
+0x14,CONTROL), explicitly labeled in code/commit/notes as an informed
estimate, not a confirmed constant. Same DPIN0 resource(0xf01e50000)
already safely used by this driver; no new addresses,no forbidden register
access; read-before-write on both new offsets matching existing discipline;
no rollback added (matching the existing HPD precedent - native teardown
for either was never traced). scripts/test-dpin-handshake.c updated and
passes (ASan/UBSan,9 scenarios). checkpatch on the accumulated header
diff:0errors/0warnings. `make` in src/thunderbolt rebuilds only
apple.o/thunderbolt_apple.ko; the other four modules, including core
thunderbolt.ko, are unchanged from0109 (verified by SHA256). Full design
in notes/2026-09-22-0110-mode-value-guess.md.

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0110.py install
```

Back up eleven module/image files to /var/tmp/j416s-0110-before (same five
module pairs as prior candidates plus initramfs); install pinned
modules/options, depmod, rebuild/verify initramfs. No live module reload,
parameter write, MMIO, mapping or reboot. Options unchanged from0109.
Candidate hashes: thunderbolt_apple
7e1dd94484e5d258696de1032bb9aded75b28195748c3e476c3c0fe69f78e102;
thunderbolt(core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7;
mux38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24;
atce47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9;
appledrm9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC0xf03000000 size0x4c000,
crossbar0xf0304c000 size0x4000,DCP0x315c00000,NHI0xf01f00000,
ACIO0xf01ac0000,DPIN0 0xf01e50000 size0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-22 -0110 installed and verified; request unplugged reboot

Installer exited0, verified backup /var/tmp/j416s-0110-before (eleven
files; manifest confirms all four unchanged modules match0109 exactly and
thunderbolt_apple backup is the prior0109 build starting74d8250d...). New
image SHA256 d9e55e3510b4ce182135b9be44371487f43d53c024566080f4ce11de26b9d0be.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms0110 (same
options as0109 - unconditional code behind the existing dpin_native=1
gate). Hardware paths/addresses remain those recorded in the preceding
installation entry: ATC0xf03000000 size0x4c000,crossbar0xf0304c000
size0x4000,DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000 size0x4000. No new manual address access or mapping; no
forbidden panel mapping,/dev/mem,PHY mode change or module unload. On
return verify loaded modules/eDP and disarm future boots before separately
logged single RIGHT-port attachment. No picture success claimed.

## 2026-09-22 -0110 boot verified; disarm future boots

Boot8d5c055e-b2f0-4195-bdfe-b224236fc09a, preflight passes, hub and
external display absent. eDP-1 connected. Installed thunderbolt_apple
matches candidate7e1dd94484e5d258696de1032bb9aded75b28195748c3e476c3c0fe69f78e102.
Loaded readonly flags: thunderbolt_apple dpin_native=Y,
mux_apple_display_crossbar usb4_defer_bringup=Y,thunderbolt
dp_video_counter=Y,dp_bw_grant=Y. No DP tunnel exists yet so the new
guessed-value code has not run.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0110.py disarm
```

Removes0110 options and rebuilds/verifies initramfs. Current readonly flags
remain Y for this test. No live MMIO,mapping,module reload or parameter
write. No addresses accessed; resource scope remains ATC0xf03000000,
crossbar0xf0304c000,DCP0x315c00000,NHI0xf01f00000,ACIO0xf01ac0000,
DPIN0 0xf01e50000. Hotplug will be logged separately after successful disarm.

## 2026-09-22 -0110 disarmed; single right-port attachment (explicit-guess test)

Disarm exited0, image verified; new SHA256
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4 (matches
0108/0109's disarmed image, as expected since options are unchanged).
Current0110 flags remain enabled for this boot only; future boots
disarmed. After committing and pushing this entry request exactly: connect
hub once to RIGHT USB-C port with monitor on hub; leave connected for
capture; report visible picture and eDP status. If eDP blacks out, unplug
hub and stop. No replug/reboot. No shell command initiates physical
connection. Keyboard untested unless attached and checked.

Scope is identical to0109 (existing owner mappings unchanged) plus0110's
addition: apple_dpin_handshake now also writes an explicit-guess value(9)
to DPIN0+0x1c and+0x14 when activating, in native's own call order. Same
DPIN0 resource already safely used; no new addresses, no forbidden
register access. This value is NOT confirmed - see
notes/2026-09-22-0110-mode-value-guess.md.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0110-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0110-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-22-0110-dpin-counters.txt
```

Confirm right port, pre-clock gates off, PLL/nativeup result,034/800,
lanes/DPRX, counter readback, and actual picture - the last decided only
by Oliver's visual confirmation. If sequence stalls, capture and stop
without retrying gates or changing registers.

## 2026-09-22 -0110 hub unplug confirmed

Oliver confirmed the hub is unplugged from the right port following the
0110 result (explicit-guess value ran cleanly, no error, still no
picture). sysfs shows no thunderbolt devices; eDP remained connected
before and after. No further hardware action performed this boot
(one-attempt guard already used). Per the agreed plan, next step is
pursuing the actual DCP coprocessor firmware (separate from the XNU
kernelcache used for all static analysis so far) - a new research effort,
not a hardware action; will be logged separately if/when it leads to any
hardware-touching step.

## 2026-09-23 -0111 built offline; lower bound of the bounded mode-value sweep

Oliver declined outreach to Asahi Linux upstream and asked to brute-force
the bounded DPIN0 mode-value space instead. First cross-referenced every
relevant AsahiLinux/linux branch (dcp/dptx-fixes and four others) against
our own dcp.c/dptxep.c: confirmed our tree already incorporates or exceeds
every upstream DPTX fix in this area (unk-field handling, activate-time
PHY-mode-set skip for the tunneled case, a missing-unlock bug we don't
have) and that no USB4-DPIN-tunnel-specific prior art exists anywhere,
published or unpublished (notes/2026-09-23-upstream-dptxep-crossref.md,
no hardware action, nothing to log).

0110 tested MODE_VALUE=9 (secondary_bit=1, the middle of a 3-valid-value
enumeration) cleanly with no picture -- inconclusive on that specific
guess, not on the formula (independently confirmed threefold by the prior
3-agent static-analysis workflow). rate_class=2 and lane_count=4 remain
high-confidence and unchanged. This candidate sweeps the lower bound:
secondary_bit=0, MODE_VALUE=8. Kernel commit 1627035 changes exactly one
constant in drivers/thunderbolt/apple-dpin-handshake.h; same two offsets
(+0x14,+0x1c), same call order, masks and gating as 0109/0110. Same DPIN0
resource (0xf01e50000) already safely used; no new addresses, no forbidden
register access. scripts/test-dpin-handshake.c updated (recomputed
expected mode_a/mode_b for MODE_VALUE=8; assertions are symbolic and
needed no change) and passes (ASan/UBSan, 9 scenarios). `make` in
src/thunderbolt rebuilds only apple.o/thunderbolt_apple.ko; the other four
modules are byte-identical to 0110 (verified by SHA256). Full design in
notes/2026-09-23-0111-mode-value-lower-bound.md.

Before this entry, verified via sysfs that the hub Oliver reported
unplugged is in fact absent from /sys/bus/thunderbolt/devices and no
external DRM connector is active; eDP-1 remains connected. Offline
`manage-0111.py check` (preflight only, no install) confirms correct
kernel/machine and matching candidate hashes.

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0111.py install
```

Back up eleven module/image files to /var/tmp/j416s-0111-before (same five
module pairs as prior candidates plus initramfs); install pinned
modules/options, depmod, rebuild/verify initramfs. No live module reload,
parameter write, MMIO, mapping or reboot. Options unchanged from 0109/0110
(unconditional code behind the existing dpin_native=1 gate). Candidate
hashes: thunderbolt_apple
e552cbc0bf6abcb22abc9c5d63065f5a668b48de440c6933526ffef526657e51;
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7;
mux 38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24;
atc e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9;
appledrm 9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC 0xf03000000 size 0x4c000, crossbar
0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000, ACIO
0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-23 -0111 installed and verified; request unplugged reboot

Installer exited 0, verified backup /var/tmp/j416s-0111-before (eleven
files; manifest confirms all four unchanged modules and thunderbolt_apple
backup match the prior disarmed-0110 state exactly, hash
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4 for the
backed-up image). New image SHA256
8eaecc264519dabdb1e3c1f387b4d1eba430a983cffa862457d499873bfefab7.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms 0111 (same
options as 0109/0110 - unconditional code behind the existing
dpin_native=1 gate). Hardware paths/addresses remain those recorded in the
preceding installation entry: ATC 0xf03000000 size 0x4c000, crossbar
0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000, ACIO
0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. No new manual address access
or mapping; no forbidden panel mapping, /dev/mem, PHY mode change or
module unload. On return verify loaded modules/eDP and disarm future
boots before separately logged single RIGHT-port attachment. No picture
success claimed.

## 2026-09-23 -0111 boot verified; disarm future boots

Boot c986c4aa-a46b-415e-995f-aeff2ee30e7b, preflight passes, hub and
external display absent. eDP-1 connected. Installed thunderbolt_apple
matches candidate e552cbc0bf6abcb22abc9c5d63065f5a668b48de440c6933526ffef526657e51.
Loaded readonly flags: thunderbolt_apple dpin_native=Y,
mux_apple_display_crossbar usb4_defer_bringup=Y, thunderbolt
dp_video_counter=Y, dp_bw_grant=Y, phy_apple_atc usb4_tunnel_clock=Y. No
DP tunnel exists yet so the new lower-bound mode-value code has not run.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0111.py disarm
```

Removes 0111 options and rebuilds/verifies initramfs. Current readonly
flags remain Y for this test. No live MMIO, mapping, module reload or
parameter write. No addresses accessed; resource scope remains ATC
0xf03000000, crossbar 0xf0304c000, DCP 0x315c00000, NHI 0xf01f00000, ACIO
0xf01ac0000, DPIN0 0xf01e50000. Hotplug will be logged separately after
successful disarm.

## 2026-09-23 -0111 disarmed; single right-port attachment (lower-bound test)

Disarm exited 0, image verified; new SHA256
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4 (matches
0108/0109/0110's disarmed image, as expected since options are unchanged).
Current 0111 flags remain enabled for this boot only; future boots
disarmed. After committing and pushing this entry request exactly: connect
hub once to RIGHT USB-C port with monitor on hub; leave connected for
capture; report visible picture and eDP status. If eDP blacks out, unplug
hub and stop. No replug/reboot. No shell command initiates physical
connection. Keyboard untested unless attached and checked.

Scope is identical to 0110 (existing owner mappings unchanged) plus
0111's change: apple_dpin_handshake now writes MODE_VALUE=8
(secondary_bit=0, the lower bound of the bounded sweep) instead of
0110's 9 to DPIN0+0x1c and +0x14 when activating, in native's own call
order. Same DPIN0 resource already safely used; no new addresses, no
forbidden register access. This value is NOT confirmed - see
notes/2026-09-23-0111-mode-value-lower-bound.md.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0111-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0111-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0111-dpin-counters.txt
```

Confirm right port, pre-clock gates off, PLL/nativeup result, 034/800,
lanes/DPRX, counter readback, and actual picture - the last decided only
by Oliver's visual confirmation. If sequence stalls, capture and stop
without retrying gates or changing registers.

## 2026-09-23 -0111 result: lower-bound guess ran cleanly, no picture

Oliver confirms "connected, nothing happening on the external monitor" --
same no-signal outcome as 0102-0110. eDP-1 remained connected throughout
(verified via sysfs immediately after). Captured
scripts/capture-display.sh output, kernel log, and DPIN counters (private,
untracked). Kernel log shows the identical clean sequence as 0110: native
DPIN0 handshake succeeds (active=1 handshake=0), crossbar bring-up
result=0, link-config up rate=0xa result=0, DP IN DPRX_DONE=1. DP-IN
packet counter nonzero (0x5b78). One unrelated log line ("ACIO RC dpin0
analog DPRX done") was checked and confirmed to dump a numerically
coincidental but physically different register window
(apple_dp_dump_analog() at acio->rc_base+APPLE_CIO_DPIN0_ANALOG, not our
0xf01e50000-based MODE_A/MODE_B block) -- does not bear on this result.
Full write-up in notes/2026-09-23-0111-result.md.

This is the second of three bounded mode-value candidates to run cleanly
with no picture (0110=9, 0111=8). One value remains: secondary_bit=2
(MODE_VALUE=10), planned as 0112.

Requested Oliver unplug the hub from the right port; awaiting
confirmation before any further hardware action (one-attempt-per-boot
guard already used this boot).

## 2026-09-23 -0112 built offline; reboot-free infrastructure for the mode-value sweep

Oliver flagged reboot cycles as the real cost blocking progress and
asked for a reboot-free way to sweep the bounded DPIN0 mode-value space.
Root causes: (1) the value was a compile-time constant, and (2) even if
runtime-adjustable, MODE_B's pure-OR write and MODE_A's set-one-bit
write would contaminate a second activate without a genuine register
reset in between, and a latent one-shot latch (dpin_attempted) would
have silently blocked any activate after the first for the rest of the
boot anyway. Kernel commit 8fa45e4 fixes both: dpin_mode_value becomes
a 0644 module parameter read fresh on each activate (out-of-range
values rejected with -EINVAL before any register access), and a new
deactivate-path clear (bounded to exactly the bits any in-range value
could have set: MODE_A bits 0-15, MODE_B bits 7-10) leaves clean state
for the next activate; dpin_attempted is reset on a successful
deactivate so that next activate is actually reachable. This is new
behavior invented for our own test isolation, explicitly not a claim
about native teardown (never traced, same caveat already applied to
HPD). Same DPIN0 resource already safely used; no new addresses, no
forbidden register access.

scripts/test-dpin-handshake.c updated for the new function signature;
added out-of-range rejection, the core round-trip (activate 9, clean
deactivate, activate 10, assert no contamination -- this is the
scenario the whole change exists to make valid), and confirmation the
deactivate clear never touches bits outside its documented range.
ASan/UBSan, 13 scenarios, all passing. `make` in src/thunderbolt
rebuilds only apple.o/thunderbolt_apple.ko; the other four modules are
byte-identical to 0111 (verified by SHA256). Full design in
notes/2026-09-23-0112-runtime-sweep.md.

This candidate itself still needs one reboot to load (module params and
code paths can't be hot-patched into an already-loaded module). Every
value sweep after that should not: testing becomes `echo N | sudo tee
/sys/module/thunderbolt_apple/parameters/dpin_mode_value`, unplug/replug,
capture -- no reinstall, no reboot.

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0112.py install
```

Back up eleven module/image files to /var/tmp/j416s-0112-before (same
five module pairs as prior candidates plus initramfs); install pinned
modules/options, depmod, rebuild/verify initramfs. No live module
reload, parameter write, MMIO, mapping or reboot. Options unchanged
from 0109-0111 (unconditional code behind the existing dpin_native=1
gate). Candidate hashes: thunderbolt_apple
f25986e265c84cf3a51c4b5901a3ae9672cbc60013cd8c1445a6dd87259979a6;
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7;
mux 38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24;
atc e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9;
appledrm 9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC 0xf03000000 size 0x4c000, crossbar
0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000, ACIO
0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-23 -0112 installed and verified; request unplugged reboot

Note: Oliver reported "rebooted" once before this install ran; boot_id
check showed no actual reboot had occurred (unchanged from the prior
0111 boot), and the hub was still present on the bus. A second report
("restarted now") checked out (boot_id changed to
ad86f858-6719-4244-92bc-fbfc24a526ba); hub was then confirmed unplugged
via sysfs before this install. That earlier boot ran on the still-
installed 0111 image, not 0112 -- 0112 had not been installed yet at
that point, so it does not count as this candidate's boot.

Installer exited 0, verified backup /var/tmp/j416s-0112-before (eleven
files; manifest confirms all four unchanged modules and
thunderbolt_apple backup match the prior disarmed-0111 state exactly,
hash 411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4
for the backed-up image). New image SHA256
2dc4436524eef7c22fff3a358d483a380a794a89367ba96083b5bc5c1ce6bfb1.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms 0112 (same
options as 0109-0111 - unconditional code behind the existing
dpin_native=1 gate; dpin_mode_value defaults to 8 at load, writable at
runtime after boot). Hardware paths/addresses remain those recorded in
the preceding installation entry: ATC 0xf03000000 size 0x4c000,
crossbar 0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000,
ACIO 0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. No new manual address
access or mapping; no forbidden panel mapping, /dev/mem, PHY mode
change or module unload. On return verify loaded modules/eDP, confirm
the new dpin_mode_value sysfs parameter exists, and disarm future boots
before separately logged single RIGHT-port attachment testing
dpin_mode_value=10. No picture success claimed.

## 2026-09-23 -0112 boot verified; disarm future boots

Boot d203e463-23ef-4dd8-8e5f-15dd4bd10550, preflight passes, hub and
external display absent. eDP-1 connected. Installed thunderbolt_apple
matches candidate f25986e265c84cf3a51c4b5901a3ae9672cbc60013cd8c1445a6dd87259979a6.
Loaded readonly flags: thunderbolt_apple dpin_native=Y. New writable
parameter confirmed present and at its compiled-in default:
/sys/module/thunderbolt_apple/parameters/dpin_mode_value=8. No DP
tunnel exists yet so no handshake code has run this boot.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0112.py disarm
```

Removes 0112 options and rebuilds/verifies initramfs. Current readonly
flags remain Y for this boot; dpin_mode_value stays live-writable
regardless (0644, not gated by the modprobe.d options file). No live
MMIO, mapping, module reload. No addresses accessed; resource scope
remains ATC 0xf03000000, crossbar 0xf0304c000, DCP 0x315c00000, NHI
0xf01f00000, ACIO 0xf01ac0000, DPIN0 0xf01e50000. Hotplug will be
logged separately after successful disarm.

## 2026-09-23 -0112 disarmed; dpin_mode_value=10 set; single right-port attachment

Disarm exited 0, image verified; new SHA256
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4 (matches
0108-0111's disarmed image, as expected since options are unchanged).
Current 0112 flags remain enabled for this boot only; future boots
disarmed.

Set the remaining untested bound via the new runtime parameter:
`echo 10 | sudo tee /sys/module/thunderbolt_apple/parameters/dpin_mode_value`,
read back and confirmed =10 (secondary_bit=2, the upper bound of the
bounded 3-value sweep; 0110=9/secondary_bit=1 and 0111=8/secondary_bit=0
both already ran clean with no picture). No MMIO, mapping, or hardware
access occurred from this parameter write alone -- it only takes effect
on the next DPIN0 activate.

After committing and pushing this entry request exactly: connect hub
once to RIGHT USB-C port with monitor on hub; leave connected for
capture; report visible picture and eDP status. If eDP blacks out,
unplug hub and stop. No replug/reboot. No shell command initiates
physical connection. Keyboard untested unless attached and checked.

Scope is identical to 0111 (existing owner mappings unchanged) plus
0112's infrastructure change: apple_dpin_handshake now reads
mode_value from a runtime parameter (currently 10) instead of a
compile-time constant, and a deactivate-path clear (new in 0112, not a
native-teardown claim) keeps state clean for any further same-boot
retest. This value is NOT confirmed - see
notes/2026-09-23-0112-runtime-sweep.md.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0112-mv10-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0112-mv10-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0112-mv10-dpin-counters.txt
```

Confirm right port, pre-clock gates off, PLL/nativeup result, 034/800,
lanes/DPRX, counter readback, and actual picture - the last decided
only by Oliver's visual confirmation. If sequence stalls, capture and
stop without retrying gates or changing registers. If this is also
inconclusive, the plan is to unplug, then (thanks to 0112) sweep
further values without another reboot rather than stopping here.

## 2026-09-23 -0112 result: full bounded sweep (8,9,10) complete, all clean, no picture

Oliver confirms "nothing" on the external monitor with dpin_mode_value=10.
eDP-1 remained connected throughout (verified via sysfs immediately
after). Captured scripts/capture-display.sh output, kernel log, and
DPIN counters (private, untracked). Kernel log shows the identical
clean sequence as 0110/0111: "native DPIN0: active=1 handshake=0
mode_value=10", crossbar bring-up result=0, link-config up rate=0xa
result=0, DP IN DPRX_DONE=1. No reboot was needed to reach this test --
ran via the 0112 sysfs parameter write plus a single unplug/replug on
the same disarmed boot. Full write-up in notes/2026-09-23-0112-result.md.

All three values in the bounded formula's only free parameter
(secondary_bit=0/1/2, mode_value=8/9/10) have now been tested; all ran
cleanly with no picture. This exhausts the bounded sweep as originally
scoped. Balance of evidence shifts toward this MODE_A/MODE_B write pair,
as currently formulated, not being the missing piece -- not a certainty,
since the underlying enumeration/formula could itself be wrong in a way
not covered by this 3-value sweep.

Requested Oliver unplug the hub from the right port. Given 0112's
reboot-free infrastructure, next steps (if any) can be evaluated and,
if warranted, tested without a reboot cycle.

## 2026-09-23 -0112 widened sweep started (full 0-15 range)

Oliver asked to widen the search beyond the original 3-value bounded
sweep (8,9,10, all clean/no picture) and to look up external
documentation in parallel (background research task, no hardware
access, will be reported separately when it returns). Reframing: MODE_A/
MODE_B are 4-bit-wide fields (APPLE_DPIN_MODE_VALUE_MAX=15), so the full
0-15 range has a principled reading as every combination of a 2-bit
rate_class field (0=RBR,1=HBR,2=HBR2,3=HBR3) and a 2-bit secondary field
(0-3), not just arbitrary brute force. Already covered: rate_class=2
(HBR2) x secondary={0,1,2} = {8,9,10}. Remaining, to be tested via the
0112 runtime parameter and unplug/replug (no further reboots): 0,1,2,3
(RBR), 4,5,6,7 (HBR), 11 (HBR2/secondary=3), 12,13,14,15 (HBR3). Same
DPIN0 resource, same one-value-per-attach discipline, hub confirmed
unplugged via sysfs before starting.

## 2026-09-23 -0112 widened-sweep plan superseded; formula correction found

Background research (no hardware access) located the real
IODPTXPortAttributes ObjC type-encoding layout from Apple binaries
(blacktop/ipsw-diffs), showing our assumed bit boundaries didn't match
the real struct packing. A focused re-disassembly of
AppleCIODPTX::connectTo/bringConnectionUp against the corrected layout
found the entire prior formula was reading the wrong field: what we
called "rate_class" (bits 4-7 of "w26") is actually the ATC field of the
IODPTXPortAddress routing struct already sent to dptxport_connect() --
not a display-mode/rate descriptor at all. With ATC=0 (confirmed: our
own connection always uses ATC=0), the real formula collapses to
mode_value = w11, a single 0-or-1 boolean derived from the CORE field
(CORE=1 -> 0, CORE=2 -> 1). The dpin_mode_value=8/9/10 sweep (0110-0112)
and the planned 0-15 widening were both testing outside the real
candidate space. Full write-up in
notes/2026-09-23-mode-value-formula-correction.md. This does not change
the MODE_A/MODE_B write mechanics (already native-confirmed), only the
numeric value to pass. No hardware action in this entry; hub remains
unplugged (verified via sysfs). Withdrawing the 0-15 widened-sweep plan
logged in the previous entry -- superseded by this narrower, better-
grounded target.

Next: set dpin_mode_value=0 (CORE=1, our connection's actual first-try
route, highest confidence) via the existing 0112 runtime parameter and
request a single right-port attachment. mode_value=1 (CORE=2 case) is
the immediate fallback if 0 is inconclusive. No reboot needed.

## 2026-09-23 -0113 built offline; fix dpin_attempted latch bug found in 0112

Investigation of the dpin_mode_value=0 test's kernel log (requested in
the prior entry) showed it never actually ran the native DPIN0
handshake: no "native DPIN0: active=1 handshake=..." line appears at
all for that attempt, only route-selection/crossbar messages from
other code, followed by "DPRX timeout, keeping DP tunnel". Root cause
found by direct code inspection, confirmed by the exact -19 (-ENODEV)
result already logged for the prior (mode_value=10) deactivate: a real
physical unplug clears acio->current_cable_info before the DCP-issued
DEACTIVATE APCALL reaches apple_usb4_right_dpin0_set_active(), tripping
its very first guard and returning -ENODEV before ever calling
apple_dpin_handshake(). This means the entire 0112 same-boot re-test
mechanism (register clear + dpin_attempted reset) never actually
executed on real hardware across any of the 0112 tests (8,9,10) -- only
in the offline mock, which has no notion of current_cable_info and
could not catch this. Consequence: dpin_attempted stayed latched true
from the boot's first activate, silently blocking the mode_value=0
attempt via -EALREADY before it ever reached the handshake. That test
is invalidated, not a real data point about mode_value=0.

Kernel commit 4240ae7 fixes this: when the early cable-state guard
trips on a deactivate request and acio->dpin_base is already mapped
(real state of ours to clean up), fall through to the same
handshake/cleanup path instead of bailing out with state stuck; still
bail immediately when there is genuinely nothing to do. Same DPIN0
resource, same guard structure; only widens which paths reach the
already-reviewed handshake call. Full design in
notes/2026-09-23-0113-fix-dpin-attempted-latch.md.

`make` in src/thunderbolt rebuilds only apple.o/thunderbolt_apple.ko;
the other four modules are byte-identical to 0112 (verified by SHA256).
No offline mock test added: this bug lives in apple.c's cable-state
wrapper, a layer scripts/test-dpin-handshake.c does not model.

This candidate needs one more reboot to load (module code path change).
After that: retest dpin_mode_value=0, then =1 if inconclusive, and
confirm via kernel log that a post-unplug deactivate now reaches
"native DPIN0: active=0 handshake=..." instead of silently returning
-19.

After committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0113.py install
```

Back up eleven module/image files to /var/tmp/j416s-0113-before (same
five module pairs as prior candidates plus initramfs); install pinned
modules/options, depmod, rebuild/verify initramfs. No live module
reload, parameter write, MMIO, mapping or reboot. Options unchanged
from 0109-0112 (unconditional code behind the existing dpin_native=1
gate). Candidate hashes: thunderbolt_apple
cb636968b5f50919fae72cb7c304b4f92f666d04a727de683266240e95dc8096;
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7;
mux 38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24;
atc e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9;
appledrm 9894035809e17b72d82d9f823d40bf115621539bebc74a5b7448f21f31f392e3
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC 0xf03000000 size 0x4c000, crossbar
0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000, ACIO
0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-23 -0113 installed and verified; request unplugged reboot

Installer exited 0, verified backup /var/tmp/j416s-0113-before (eleven
files; manifest confirms all four unchanged modules and
thunderbolt_apple backup match the prior 0112 state exactly, hash
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4 for the
backed-up image). New image SHA256
2f1e4b85e067e05cabe8204d0cbed81876fdba82c0e25b8b623b64ecd9cd8536.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms 0113 (same
options as 0109-0112 - unconditional code behind the existing
dpin_native=1 gate; dpin_mode_value defaults to 8 at load, writable at
runtime). Hardware paths/addresses remain those recorded in the
preceding installation entry: ATC 0xf03000000 size 0x4c000, crossbar
0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000, ACIO
0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. No new manual address
access or mapping; no forbidden panel mapping, /dev/mem, PHY mode
change or module unload. On return verify loaded modules/eDP and disarm
future boots before separately logged single RIGHT-port attachment
testing dpin_mode_value=0. No picture success claimed.

## 2026-09-23 -0113 boot verified; disarm future boots

Boot 393854ae-59a9-4c26-abaa-ad5dc20ce507, preflight passes, hub and
external display absent. eDP-1 connected. Installed thunderbolt_apple
matches candidate cb636968b5f50919fae72cb7c304b4f92f666d04a727de683266240e95dc8096.
Loaded readonly flags: thunderbolt_apple dpin_native=Y.
dpin_mode_value present at its compiled-in default (8). No DP tunnel
exists yet so no handshake code has run this boot.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0113.py disarm
```

Removes 0113 options and rebuilds/verifies initramfs. Current readonly
flags remain Y for this boot; dpin_mode_value stays live-writable
regardless. No live MMIO, mapping, module reload. No addresses
accessed; resource scope remains ATC 0xf03000000, crossbar 0xf0304c000,
DCP 0x315c00000, NHI 0xf01f00000, ACIO 0xf01ac0000, DPIN0 0xf01e50000.
Hotplug will be logged separately after successful disarm.

## 2026-09-23 -0113 disarmed; dpin_mode_value=0 set; single right-port attachment (retest)

Disarm exited 0, image verified; new SHA256
411e2701e019dc4d15c15043a12adab5f44a4a6051579bea0e7a2854121115f4 (matches
0108-0112's disarmed image). Current 0113 flags remain enabled for this
boot only; future boots disarmed.

Set dpin_mode_value=0 via the runtime parameter (the corrected
highest-confidence value from
notes/2026-09-23-mode-value-formula-correction.md -- CORE=1, our
connection's actual first-try route). This is the genuine retest of the
attempt invalidated by the 0112 latch bug fixed in 0113.

After committing and pushing this entry request exactly: connect hub
once to RIGHT USB-C port with monitor on hub; leave connected for
capture; report visible picture and eDP status. If eDP blacks out,
unplug hub and stop. No replug/reboot. No shell command initiates
physical connection.

Scope is identical to prior candidates plus 0113's fix (cable-state
guard now falls through to the existing handshake/cleanup path instead
of latching). This value is NOT confirmed - see
notes/2026-09-23-mode-value-formula-correction.md.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0113-mv0-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0113-mv0-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0113-mv0-dpin-counters.txt
```

Confirm right port, native DPIN0 handshake actually runs this time
(active=1 handshake=... log line present), crossbar/link-config result,
DPRX completion, and actual picture - the last decided only by Oliver's
visual confirmation. If this is also inconclusive, unplug, verify via
kernel log that the deactivate this time reaches "active=0 handshake=..."
(not -19), then proceed to mode_value=1.

## 2026-09-23 -0113 mv0 result: real test, clean, no picture; unplug requested

Oliver confirms no picture with dpin_mode_value=0 (the genuine retest,
now confirmed to have actually run the handshake -- see kernel log
excerpt in notes/2026-09-23-0113-mv0-result.md). eDP-1 remained
connected. Full write-up in that note.

Requested Oliver unplug the hub. Once confirmed, verify via kernel log
that the deactivate this time reaches "native DPIN0: active=0
handshake=..." (not the -19 early-return the 0113 fix addresses), then
set dpin_mode_value=1 (CORE=2 case) and request the next single
right-port attachment.

## 2026-09-23 -0113 unplug confirmed, deactivate verified fixed; dpin_mode_value=1 set

Hub unplug confirmed via sysfs (no Thunderbolt devices; eDP-1 remains
connected). Kernel log confirms the 0113 fix works end-to-end: "native
DPIN0: DCP active=0 result=0" (success), not the -19 early-return seen
before the fix. dpin_attempted and the MODE_A/MODE_B registers are now
genuinely reset, making the next activate a valid isolated test.

Set dpin_mode_value=1 via the runtime parameter (CORE=2 case, the
second and final candidate from the corrected formula). After
committing and pushing this entry request exactly: connect hub once to
RIGHT USB-C port with monitor on hub; leave connected for capture;
report visible picture and eDP status. Capture the same set as before
under a 2026-09-23-0113-mv1-* prefix.

## 2026-09-23 -0113 mv1 attempt invalid (DCP never detected the display); sweep script added

Investigation of the dpin_mode_value=1 attempt's kernel log found it
invalid for a reason unrelated to the 0113 latch fix (confirmed working
for mv0's deactivate, result=0): DCP's own hotplug detection never
fired ("cb_hotplug() connected:1" absent) and dcp_dptx_connect() was
never called at all -- our own DPIN0 code never got a chance to run.
Only "DP IN analog: leaving PHY alone until DPRX timeout" appears, with
no follow-up, suggesting AUX/DPRX-level flakiness upstream of our code
on this specific physical replug. Not a data point for mode_value=1;
needs a clean retry. eDP and hub bus state were otherwise fine
throughout (checked live, ~100s after the attempt with no further
activity).

Oliver asked for a shell script to automate the remaining sweep
(set value, wait for connect, capture, ask about the picture, log) so
this doesn't require a manual round trip per value. Added
scripts/sweep-mode-value.sh: walks a list of dpin_mode_value candidates
(default: 1,2,3,4,5,6,7,11,12,13,14,15 -- the values not yet cleanly
tested), and for each one verifies via kernel log grep that the native
DPIN0 handshake actually ran, DCP's hotplug detection fired, and
dcp_dptx_connect() was called before accepting a "no picture" answer as
real data -- exactly the validity check this mv1 attempt and the
earlier 0112 latch bug both would have failed, so an invalid attempt
now prompts a retry instead of silently being logged as a clean
negative. Each result is appended to
notes/mode-value-sweep-results.md and committed+pushed automatically.
The script stops immediately and asks for confirmation, without further
writes, if a picture is ever reported. No hardware action from adding
the script itself; it must be run by Oliver interactively (physical
plug/unplug and the picture question cannot be automated).

## 2026-09-23 -0113 sweep complete: full 0-15 value space exhausted, all clean negatives

scripts/sweep-mode-value.sh completed a full run over values 1,2,3,4,5,
6,7,11,12,13,14,15 (results in notes/mode-value-sweep-results.md, each
auto-committed/pushed by the script). Every attempt verified valid
(handshake ran, hotplug detected, dcp_dptx_connect called); all report
no picture. Combined with 0110/0111/0112/0113's mv0 (values 9,8,10,0),
every value 0-15 -- the full range these registers' write formulas can
express -- has now been tested. All 16 are clean negatives. Consolidated
conclusion in notes/2026-09-23-mode-value-sweep-exhausted.md: combined
with the formula correction (MODE_A/MODE_B's driving value is actually
an already-known routing-address field, not an independently-derived
rate/mode descriptor), the balance of evidence now points to these two
writes not being the mechanism that turns on the picture at all,
regardless of value. No further speculative MODE_A/MODE_B writes
planned. Hub remains connected from the value=15 attempt; unplug to be
confirmed separately.

## 2026-09-23 -0113 re-armed for frame/vblank investigation (no new module build)

After the mode-value sweep concluded (all 16 values clean negatives),
investigation shifted to what happens after DPRX_DONE/set_digital_out_mode
succeed -- specifically, whether any real frame/vblank activity reaches
the external connector once a mode is set, since that layer has not been
checked this session. Grepping DCP's own RTKit syslog messages across all
captures found "swap_submit_dcp: swallowed swap ID N as
fControllerPowerState is 0"/"timings are not enabled" for our exact
controller (315c00000.dcp) -- initially promising, but verified (by
checking every instance's timing relative to hotplug connect/disconnect)
to occur exclusively immediately after a disconnect event, never during
the active connected window. This is a harmless teardown artifact, not
the active blocker; ruled out.

Oliver rebooted and reconnected to continue investigating live frame/
vblank activity, but that boot came up with 0113 disarmed (dpin_native=N,
the safe default from the prior disarm), so the native DPIN0 path never
ran at all -- that attempt's DPRX timeout is expected baseline behavior
with the gate off, not new data. My mistake for not flagging this before
the attempt was made.

Re-arming without a new module build: verified the currently-installed
thunderbolt_apple.ko still matches the 0113 candidate hash
(cb636968b5f50919fae72cb7c304b4f92f666d04a727de683266240e95dc8096) on
both kernel/ and updates/ paths (unaffected by disarm, which only removes
the modprobe.d options file). dpin_native is 0444 (load-time only), so
re-enabling it requires a fresh boot; no live module reload/unload
performed (forbidden). Hub confirmed unplugged via sysfs before this
change. After committing/pushing execute exactly:

```
sudo -n install -m 0644 /dev/stdin /etc/modprobe.d/j416s-0113-dpin0-mode-guess.conf << 'CONF'
options appledrm usb4_protocol_probe=1 usb4_native_dpin=1 usb4_tunnel_clock=1
options thunderbolt_apple dpin_native=1
options phy_apple_atc usb4_tunnel_clock=1
options mux_apple_display_crossbar usb4_defer_bringup=1
options thunderbolt dp_video_counter=1 dp_bw_grant=1
CONF
sudo -n mkinitcpio -p linux-aurora
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0113.py check
```

This recreates byte-for-byte the same options file manage-0113.py's
install() would write (verified identical via direct import), then
rebuilds/verifies the initramfs. No module files touched (already
correct), no MMIO, no live reload. After verification, ask Oliver to
reboot with `systemctl reboot`, hub still unplugged, then disarm again
after boot verification per the usual discipline before the next
attachment.

## 2026-09-23 -0113 re-armed and verified; request unplugged reboot

Config file recreated byte-for-byte, initramfs rebuilt, manage-0113.py
check confirms correct kernel/machine, hub/display absent, and matching
candidate hashes. New image SHA256
$(sha256sum /boot/initramfs-linux-aurora.img | cut -d' ' -f1).
No module files touched, no live reload, no MMIO. Hub remains unplugged.

After committing/pushing this entry ask Oliver to reboot with exactly
\`systemctl reboot\`, hub still unplugged, then report back.

## 2026-09-23 root mechanism found: DCP never sends swap_complete for this pipeline

Purely observational investigation (no register writes) while the hub
was live-connected with a genuinely successful modeset (crtc-2/USB-3,
mode "2560x1440" 60Hz, enable=1 active=1, plane assigned). Correlated
three signal sources never read together before this session: DRM's
atomic state (debugfs), the per-crtc CRC frame-index counter (debugfs),
and Hyprland's own compositor log (never checked before -- everything
prior was kernel-log-only).

Found: crtc-2's frame index advances a handful of times at initial
enable then never again (confirmed via blocking debugfs reads over
several minutes and after moving the cursor onto that screen's area),
while eDP's crtc-0 continuously advances as expected. Hyprland's log
shows exactly why: "ERR from aquamarine]: atomic drm request: failed
to commit: Device or resource busy, flags: ATOMIC_NONBLOCK
PAGE_FLIP_EVENT", logged once right after the successful modeset and
never again -- the compositor tried once more, got -EBUSY, and gave up
on this output. Traced -EBUSY to its source: our driver's
dcp_drm_crtc_page_flip() (which unblocks the next atomic commit) is
only called from dcpep_cb_swap_complete(), which only runs when DCP
firmware itself sends a swap-complete RPC callback. That callback
never arrives for this pipeline, so the crtc's pending-commit state
never clears.

This reframes the entire session: crossbar, DPIN0 handshake, USB4
tunnel, AUX/DPRX, link-rate/lane negotiation, and set_digital_out_mode
all genuinely work (much higher confidence than before). The break is
specifically in DCP firmware's per-swap completion signaling for this
dcpext+USB4-tunnel pipeline shape, not in any register value tested to
date (0093-0113, mode-value sweep 0-15 all now understood to be
investigating the wrong layer for this specific symptom). Full writeup
in notes/2026-09-23-swap-complete-never-fires.md.

No hardware register write in the course of this investigation. Hub
still connected at time of writing.

## 2026-09-23 exact stuck mechanism identified: DCP run_mode 2->4 never completes

Targeted disassembly of the real DCP firmware (re-extracted via pzb,
SHA256 f3d919d62979408b5643a0f1e07df3a17e734dc5666ee27a873766a3adb35430,
matches earlier session's extraction) located
IOMobileFramebuffer::swap_submit_dcp (vmaddr 0x723b4, confirmed by
14-argument parameter marshaling matching its real C++ signature).
Found a third, previously unknown silent-drop path distinct from the
two known "swallowed swap" checks: slot acquisition from a
sub-object fails, jumping to a bail-out that logs (via a logger
throttled to 15 occurrences then silent) "IOMFB_SWAP_SUBMIT_LOST,
transaction->swapID/enabled/completed" and returns without programming
hardware. Neither of the two known "swallowed" strings fires during our
actual stall; this one structurally matches "frames vanish, zero
visible errors" far better. Callers of the likely completion-marking
function ("batched_swap_complete_ap_gated") could not be resolved
statically -- blocked by chained-fixup DATA pointers and vtable/RTTI
recovery needs, both requiring a working decompiler this environment
does not have (confirmed absent again).

Correlated directly against our own kernel log's own DCP-firmware
run_mode state tracing (PPipeDCP_H13P.cpp): every connection attempt
for our controller (315c00000.dcp) reaches "set_run_mode_safe:
deferring: 2 -> 4" / "ready_for_run_mode_change(...): initiating
deferred run mode change" and then NOTHING FURTHER, ever, in dozens of
captured attempts. Verified LIVE, not inferred: left the hub connected
and completely untouched for over 40 minutes (connection start ~t=15.6s
this boot, rechecked at uptime 2571s); the run_mode log tail is
byte-identical to its state at t=15.6s, and the crtc's CRC/frame-index
debugfs read still blocks indefinitely (no new frames). This rules out
"just needs more time" -- the transition is permanently stuck, not
slow. Full writeup in
notes/2026-09-23-run-mode-4-permanently-stuck.md.

This is now the best-verified statement of the actual blocker: not any
register value tested this session (0093-0113, full mode-value sweep),
not the monitor/adapter (confirmed working elsewhere), not the USB4
tunnel itself (solidly established) -- a specific DCP-firmware
readiness check for entering continuous-scanout run mode 4 that this
exact dcpext+USB4-tunnel pipeline shape never satisfies. Going further
requires either a working decompiler with vtable/RTTI recovery (not
available in this environment) or hardware-level register comparison
against a known-working pipeline, which this project cannot currently
do. No hardware register write in the course of this investigation.
Hub still connected; no picture.

## 2026-09-23 decompiler working; full chain traced to a power-state gate

Set up a working ARM64 decompiler for Ghidra 12.1.4 (which ships no
linux_arm_64 decompile binary at all): installed qemu-user/qemu-user-
binfmt, built a minimal x86_64 sysroot from four Debian .deb packages
(libc6, libstdc++6, libgcc-s1, their bundled ld-linux-x86-64.so.2),
and wired the real linux_x86_64 decompile binary in as a wrapper script
at the linux_arm_64 path Ghidra expects. Confirmed working with real
decompiled C output (not just disassembly) against t602xdcp.bin.

Traced the full chain from swap_submit_dcp (0x723b4) through to its
ultimate gate, entirely in decompiled firmware C:
swap_submit_dcp's per-transaction "completed" flag is only ever set by
batched_swap_complete_ap_gated (FUN_00078ae0); that function's
registration (not just its invocation) is gated on three conditions in
FUN_000788d0, the load-bearing one being a global (DAT_0062d975, not
per-pipe); that global is set/cleared by exactly one function
(FUN_0005d2b0), which is a power-state transition handler: entering
internal state 0x21 from state 8 sets it true, the reverse clears it;
that handler is registered as part of FUN_00129574, which sets up the
core "iomfb_ap_link" AP<->DCP RPC channel -- confirming this is generic
firmware infrastructure, not anything specific to DPIN0/USB4-tunnel
routing.

Conclusion: continuous frame completion requires DCP's own internal
power-state machine to transition this pipe from state 8 to state 0x21
(33), and nothing this project has ever called (dcp_set_display_device
handle 0 or 2 -- both already tried, 0087 predating this session --
any DPTX APCALL, any DPIN0/crossbar write) has been shown to trigger
it. This is an IOKit-style numbered power-state ordinal, a concept
Linux's own power-management model has no direct equivalent request
for. This precisely explains, at the mechanism level, 0087's older
empirical finding ("handle 0 does not power this dcpext"). Full trace
with decompiled code in notes/2026-09-23-power-state-gate-traced.md,
including the decompiler setup steps for reuse in future sessions
(built under /tmp, will not survive a reboot).

No hardware register write in the course of this investigation --
purely offline firmware decompilation. Hub still connected; no picture.

## 2026-09-23 monitor-side confirmation: "no signal detected" on correct HDMI input

After a genuine reboot (boot a15dbce5-94d9-4232-828b-18818830c0cf; the
/tmp decompiler setup was lost as expected, module came up already
armed since the modprobe.d config was never removed after the last
re-arm), the hub was already connected at boot and went through a
completely clean sequence (native DPIN0 handshake, crossbar bring-up,
DPRX_DONE=1, set_digital_out_mode success) -- identical in every
observable respect to every other "successful-looking" attempt this
project has ever logged.

Oliver checked the monitor's own input selection directly: it is on
the correct HDMI input (the one the Synaptics VMM7100 output feeds),
and the monitor's own OSD explicitly reports "no signal detected" on
that input. This rules out a mundane wrong-input-selected explanation
and positively confirms the mechanism traced earlier today
(notes/2026-09-23-power-state-gate-traced.md): no real video clock/
data signal ever reaches the physical output, consistent with DCP's
internal power state never completing its transition to the fully-
active ordinal (0x21) this pipe's swap-completion path depends on.
Not a new finding -- direct physical confirmation of the existing one.

No hardware register write in the course of this entry.

## 2026-09-23 XNU-side power-state trace: request_display resend pattern found

Rebuilt the decompiler infrastructure after the reboot (same steps as
notes/2026-09-23-power-state-gate-traced.md) and re-extracted the
kernelcache (same SHA256 as every prior extraction:
9615a486511c7a60b141d7f4291361c5212e908546d6568890029bb90b5431e7).
Unlike the DCP firmware, this binary retains full mangled C++ symbols,
resolvable directly via llvm-nm (Ghidra's own Mach-O loader does not
apply them -- confirmed by both exact and wildcard symbol lookups
returning zero matches while llvm-nm reads them instantly; noted for
future reference).

Traced AppleDCPDPTXRemotePortProxy (the Type-C/dcpext-routed DPTX proxy
class -- confirmed the right class for our scenario, as opposed to
AppleCIODPTX which is used for direct/fixed-PHY ports and uses an
entirely different, unrelated power mechanism). Found:
synchronousChangeDPTXPowerStateTo(1) is called by a "requestDisplay"
handler (sets a _displayRequested flag), and (0) by a "displayRelease"
handler; both are top-level externally-invokable methods (work-loop
trampolines matching both a plain C++ entry and an IOUserClient
external-method entry), i.e. invoked by macOS's window server/graphics
stack, the functional counterpart of our own Hyprland atomic-commit
step. The actual work happens in setPowerState's gated implementation:
when powerstate transitions to 1 AND _displayRequested is already set,
it sends an IPC message using AFK/EPIC method index 6 -- the exact
same method our own dptxport_request_display() already uses. The
release path uses method index 7, matching dptxport_release_display().

This means real macOS (re-)sends request_display specifically at the
moment the IOKit power domain transitions to active, not merely once,
unconditionally, at initial connect time the way our
dcp_dptx_connect() does it -- a concrete, mechanically-grounded,
cheaply-testable structural difference (does not yet prove causality).
initialPowerStateForDomainState unconditionally returns 0 (no special
"already on" assumption). Full trace, including the additional context
gathered (AppleCIODPTX's separate mechanism, the dispatch-trampoline
confirmation, and the llvm-nm-over-Ghidra-symbols lesson), in
notes/2026-09-23-xnu-power-state-trace.md.

Suggested next hardware test (not yet run, no design note/candidate
built yet): add a second dptxport_request_display() call after the
native DPIN0 crossbar handshake completes, mirroring this exact
resend-on-power-up pattern. Uses only an already-safe, already-used
AFK/EPIC method; no new register or address.

No hardware register write in the course of this investigation --
purely offline kernelcache decompilation. Hub remains connected from
earlier; no picture.

## 2026-09-23 -0114 built offline; resend request_display after native DPIN0 activate

First candidate built from XNU/kernelcache tracing rather than DPIN0
register guessing (notes/2026-09-23-xnu-power-state-trace.md). Real
macOS's AppleDCPDPTXRemotePortProxy::setPowerState resends
request_display (AFK/EPIC method 6, the exact method
dptxport_request_display() already uses) specifically when the IOKit
power domain confirms active, not merely once unconditionally at
connect time. Kernel commit f7a9a7b adds exactly that: in
dptxport_call_activate() (drivers/gpu/drm/apple/dptxep.c), once
dptxport_native_dpin()'s activate call succeeds (our closest
equivalent of "this tunneled target's power domain is up"), call
dptxport_request_display(service) again. Uses only the existing,
already-safe AFK/EPIC method already sent once in every prior
candidate; no new register, address, or APCALL. Full design in
notes/2026-09-23-0114-resend-request-display.md.

`make` in src/appledrm rebuilds only dptxep.o/appledrm.ko; the other
four modules are byte-identical to 0113 (verified by SHA256). No
offline mock test added -- this is a single additional call to an
already-used function, not new register-level state-machine logic.

Hub confirmed unplugged via sysfs before this entry. After
committing/pushing these changes execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0114.py install
```

Back up eleven module/image files to /var/tmp/j416s-0114-before (same
five module pairs as prior candidates plus initramfs); install pinned
modules/options, depmod, rebuild/verify initramfs. No live module
reload, parameter write, MMIO, mapping or reboot. Options unchanged
from 0109-0113 (unconditional code behind the existing dpin_native=1
gate). Candidate hashes: appledrm
c29b0cb13c4bc6415a7299b3970582fb8043af1692c9710b94eca4321256e504;
thunderbolt_apple cb636968b5f50919fae72cb7c304b4f92f666d04a727de683266240e95dc8096;
thunderbolt (core) dd99ee948f23549ccd16e188db9a6b7c1452f9389ce60a5ecdec34a1126032f7;
mux 38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24;
atc e47f03cef54c44c816c85a7565f41cde046a9a364b9db9857653c5fbaad0b0c9
(last four unchanged, reinstalled only for manifest symmetry). Future
candidate uses existing right ATC 0xf03000000 size 0x4c000, crossbar
0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000, ACIO
0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. None accessed during this
install. Hub/direct display stay unplugged; reboot separately logged.

## 2026-09-23 -0114 installed and verified; request unplugged reboot

Installer exited 0, verified backup /var/tmp/j416s-0114-before (eleven
files; manifest confirms all four unchanged modules and old appledrm
backup match the prior 0113 state exactly, hash
2f1e4b85e067e05cabe8204d0cbed81876fdba82c0e25b8b623b64ecd9cd8536 for
the backed-up image). New image SHA256
b97594af1842d08c00ec056f2b8eac60b403c2cd4b81fa10b9312e79a20ac5e5.
Post-install preflight passes, hub/external display absent. Recurring
firmware/font/architecture mkinitcpio warnings only; image verification
passed. No live reload/MMIO/parameter write occurred.

After committing/pushing this entry ask Oliver to keep hub and direct
display adapter unplugged, reboot with exactly `systemctl reboot`, then
report back before plugging anything in. This is a user-executed reboot
instruction; no agent reboot command executed. New boot arms 0114 (same
options as 0109-0113 - unconditional code behind the existing
dpin_native=1 gate). Hardware paths/addresses remain those recorded in
the preceding installation entry: ATC 0xf03000000 size 0x4c000,
crossbar 0xf0304c000 size 0x4000, DCP 0x315c00000, NHI 0xf01f00000,
ACIO 0xf01ac0000, DPIN0 0xf01e50000 size 0x4000. No new manual address
access or mapping; no forbidden panel mapping, /dev/mem, PHY mode
change or module unload. On return verify loaded modules/eDP and
disarm future boots before separately logged single RIGHT-port
attachment. No picture success claimed.

## 2026-09-23 -0114 boot verified; disarm future boots

Boot 97561110-378c-4bfd-9a1a-beacdf2128aa, preflight passes, hub and
external display absent. eDP-1 connected. Installed candidate matches:
appledrm c29b0cb13c4bc6415a7299b3970582fb8043af1692c9710b94eca4321256e504.
Loaded readonly flags: thunderbolt_apple dpin_native=Y. No DP tunnel
exists yet so the resend-request_display code has not run.

After committing/pushing execute exactly:

```
sudo -n python3 /home/oliver/Development/asahi-j416s-display/scripts/manage-0114.py disarm
```

Removes 0114 options and rebuilds/verifies initramfs. Current readonly
flags remain Y for this boot. No live MMIO, mapping, module reload or
parameter write. No addresses accessed; resource scope remains ATC
0xf03000000, crossbar 0xf0304c000, DCP 0x315c00000, NHI 0xf01f00000,
ACIO 0xf01ac0000, DPIN0 0xf01e50000. Hotplug will be logged separately
after successful disarm.

## 2026-09-23 -0114 disarmed; single right-port attachment

Disarm exited 0, image verified; new SHA256
20cd0e9dc3f298a0f6ea887ff0f6810303d54952931cdc78266e7e0a7d6a8170.
This differs from the 411e2701... baseline seen for every 0108-0113
disarmed image, as expected: 0114 is the first candidate to change
appledrm.ko itself (not just thunderbolt_apple.ko), so the disarmed
initramfs now embeds the new appledrm.ko even with options removed.
Current 0114 flags remain enabled for this boot only; future boots
disarmed.

After committing and pushing this entry request exactly: connect hub
once to RIGHT USB-C port with monitor on hub; leave connected for
capture; report visible picture and eDP status. If eDP blacks out,
unplug hub and stop. No replug/reboot. No shell command initiates
physical connection.

Scope is identical to 0113 plus 0114's change: dptxport_call_activate()
now resends dptxport_request_display() once the native DPIN0 activate
succeeds, mirroring real macOS's setPowerState resend pattern (see
notes/2026-09-23-0114-resend-request-display.md). No new register,
address, or APCALL -- only an additional call to an already-used,
already-safe AFK/EPIC method.

After user connects, capture exactly (private raw files remain untracked):

```
/home/oliver/Development/asahi-j416s-display/scripts/capture-display.sh /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0114-right-connected.txt
sudo -n journalctl -k -b --no-pager -o short-monotonic > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0114-right-kernel.log
modetest -M apple -e
sudo -n cat /sys/kernel/debug/thunderbolt/0-0/port5/counters > /home/oliver/Development/asahi-j416s-display/captures/2026-09-23-0114-dpin-counters.txt
```

Confirm right port, native DPIN0 handshake result, the new "resend
request_display" log line and its return code, crossbar/link-config
result, DPRX completion, and actual picture - the last decided only by
Oliver's visual confirmation. If sequence stalls, capture and stop
without retrying gates or changing registers.
