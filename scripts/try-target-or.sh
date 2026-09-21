#!/usr/bin/env bash
# Cycle USB4 DPTX target extra bits without rebuilding. Requires root.
# Does not reboot. Watch dmesg for SET_ACTIVE_LANE_COUNT with lanes>0.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
modprobe -n appledrm
for or in 0x2000 0x4000 0x200 0x100 0x1 0x800 0x400 0x8; do
  echo "=== try usb4_target_or=$or usb4_atc=2 ==="
  echo "$or" > /sys/module/appledrm/parameters/usb4_target_or
  echo 2 > /sys/module/appledrm/parameters/usb4_atc
  echo 2 > /sys/module/appledrm/parameters/usb4_arm
  sleep 6
  dmesg | tail -15 | grep -E 'validate target=|link fault|SET_LINK_RATE|SET_ACTIVE|INACTIVE|kick' || true
done
echo "done. full log: dmesg | grep 'validate target='"
