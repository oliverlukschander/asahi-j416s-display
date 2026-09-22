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
