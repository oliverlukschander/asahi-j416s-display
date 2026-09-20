# Contributing

This is a single-machine bring-up: Apple `j416s` + OWC Thunderbolt 5 Hub +
USB-C HDMI adapter. Patches should still be written so they can go to
`aurora-silicon/linux` `aurora-wip` (then Asahi if they carry the same code).

- Do not vendor the kernel, `boot.bin`, or out-of-tree `.ko` blobs.
- Reviewable work is patches under `patches/` plus notes that cite a capture.
- Keep USB4 on the hub port. Do not "fix" display by forcing DP alt-mode on
  Left Back.
- Git author for this tree: Oliver Lukschander `<oliver.lukschander@golf.at>`.

Run `./scripts/capture-display.sh` after any plug/unplug or kernel change and
commit the new file under `captures/`.
