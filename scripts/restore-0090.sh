#!/usr/bin/env bash
# Restore the verified pre-0092 boot files. Does not reload drivers or reboot.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
for router in /sys/bus/thunderbolt/devices/*-*; do
  [[ -e $router ]] || continue
  name=${router##*/}
  [[ $name == *:* || $name == *-0 ]] && continue
  echo "Unplug the hub before recovery: $name is attached." >&2
  exit 1
done
backup=/var/tmp/j416s-0092-before
version=7.1.12-2.5-1-ARCH
cd "$backup"
sha256sum --check <<'HASHES'
790475c0059aea58b602de5a35f2f2a325ceafcb5e8756946e7e9b5b994704d1  appledrm-kernel.ko
790475c0059aea58b602de5a35f2f2a325ceafcb5e8756946e7e9b5b994704d1  appledrm-updates.ko
fef9c5d9d3e73ac496dcbca0f946ec8d9ca34aed0d673252cc8e8f8802e3c73d  initramfs-linux-aurora.img
HASHES
install -m 0644 appledrm-kernel.ko "/lib/modules/$version/kernel/drivers/gpu/drm/apple/appledrm.ko"
install -m 0644 appledrm-updates.ko "/lib/modules/$version/updates/appledrm.ko"
rm -f /etc/modprobe.d/j416s-0092-protocol-probe.conf
depmod -a "$version"
cp -a initramfs-linux-aurora.img /boot/initramfs-linux-aurora.img
sync
echo '0090 boot files restored. No live driver change or reboot performed.'
