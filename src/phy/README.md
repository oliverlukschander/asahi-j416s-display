# Out-of-tree `phy-apple-atc.ko`

USB4 DPTX ACTIVATE enables `lpdptx` AUX without switching SS lanes to DP.

```bash
make -C src/phy -j"$(nproc)"
```

Installed by `scripts/load-appledrm.sh`.
