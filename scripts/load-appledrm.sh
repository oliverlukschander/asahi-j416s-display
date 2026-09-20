#!/usr/bin/env bash
# Install patched appledrm and reboot into Aurora. Do not rmmod the live
# display driver — that blacks the panel. Requires root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(uname -r)"
KO="$ROOT/src/appledrm/appledrm.ko"
DST="/lib/modules/$VER/updates"
STATUS="$ROOT/notes/load-status"

echo RUNNING >"$STATUS"
[[ $EUID -eq 0 ]] || { echo FAILED:root >"$STATUS"; exit 1; }
[[ -f $KO ]] || { echo "FAILED:missing $KO" >"$STATUS"; exit 1; }
[[ $(uname -r) == 7.1.12-2.5-1-ARCH ]] || {
  echo "FAILED:not-aurora $(uname -r)" >"$STATUS"
  exit 1
}

install -d "$DST"
cp -a --backup=numbered /lib/modules/$VER/kernel/drivers/gpu/drm/apple/appledrm.ko \
  "$DST/appledrm.ko.stock" 2>/dev/null || true
install -m 0644 "$KO" "$DST/appledrm.ko"
depmod -a "$VER"
echo OK >"$STATUS"
echo "Installed $DST/appledrm.ko — reboot to load it (do not rmmod appledrm)."
echo "Rebooting in 3s. GRUB default is Aurora."
sync
sleep 3
systemctl reboot
