# Out-of-tree `mux-apple-display-crossbar.ko`

T602x DPIN0/DPIN1 analog routing. Stock t602x `set()` only programmed DPPHY.

```bash
make -C src/mux -j"$(nproc)"
```

Installed by `scripts/load-appledrm.sh` next to appledrm and thunderbolt
(in-tree `drivers/mux/` plus initramfs).
