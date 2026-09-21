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
