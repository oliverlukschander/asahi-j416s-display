# Out-of-tree `appledrm.ko`

Build against the Aurora 7.1.12 headers on this machine:

```bash
# sources are the patched tree at linux-aurora-pr (symlinked locally)
make -C src/appledrm -j"$(nproc)"
```

`pahole` is not installed, so the Makefile temporarily hides `vmlinux` to skip BTF.

Load (root, **reboots** — do not `rmmod appledrm` on a live session):

```bash
sudo ./scripts/load-appledrm.sh
```

Override DP IN mux after a failed DPRX: `appledrm.usb4_dpin=2` (dpin1).
