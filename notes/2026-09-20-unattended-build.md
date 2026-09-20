# Unattended overnight — 2026-09-20

Built patched `appledrm.ko` (vermagic `7.1.12-2.5-1-ARCH`) at
`src/appledrm/appledrm.ko`. USB4 DPTX path borrows crossbar **dpin0**
without a DTB change.

**Did not load it.** This session has no passwordless sudo (`sudo -n`
fails). Reloading `appledrm` would drop eDP; installer therefore
copies the `.ko` to `/lib/modules/.../updates` and **reboots**.

When you are at the keyboard:

```bash
cd /home/oliver/Development/asahi-j416s-display
sudo ./scripts/load-appledrm.sh
```

After reboot, hub still on Left Back, VMM7100 still on a TB5 port:

```bash
./scripts/capture-display.sh
dmesg | grep -E 'USB4 DP IN|0:5 <->|allocated Type-C'
hyprctl monitors
```

If the tunnel still tears down, reboot once more with dpin1:

```bash
# after install, before reboot, or via kernel cmdline if you prefer:
# insmod path is updates/; set in a /etc/modprobe.d/appledrm.conf:
# options appledrm usb4_dpin=2
```
