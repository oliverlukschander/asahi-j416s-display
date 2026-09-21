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
