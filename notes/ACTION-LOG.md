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
