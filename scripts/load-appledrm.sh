#!/usr/bin/env bash
# Install patched appledrm into the module tree AND the Aurora initramfs.
# appledrm is loaded from initramfs, so updates/ alone is ignored.
# Do not rmmod the live display driver — that blacks the panel.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(uname -r)"
KO="$ROOT/src/appledrm/appledrm.ko"
TBKO="$ROOT/src/thunderbolt/thunderbolt.ko"
MUXKO="$ROOT/src/mux/mux-apple-display-crossbar.ko"
PHYKO="$ROOT/src/phy/phy-apple-atc.ko"
INTREE="/lib/modules/$VER/kernel/drivers/gpu/drm/apple/appledrm.ko"
TBINTREE="/lib/modules/$VER/kernel/drivers/thunderbolt/thunderbolt.ko"
MUXINTREE="/lib/modules/$VER/kernel/drivers/mux/mux-apple-display-crossbar.ko"
PHYINTREE="/lib/modules/$VER/kernel/drivers/phy/apple/phy-apple-atc.ko"
DST="/lib/modules/$VER/updates"
STATUS="$ROOT/notes/load-status"

echo RUNNING >"$STATUS"
[[ $EUID -eq 0 ]] || { echo FAILED:root >"$STATUS"; exit 1; }
[[ -f $KO ]] || { echo "FAILED:missing $KO" >"$STATUS"; exit 1; }
[[ $(uname -r) == 7.1.12-2.5-1-ARCH ]] || {
  echo "FAILED:not-aurora $(uname -r)" >"$STATUS"
  exit 1
}

install -d "$DST" "$(dirname "$INTREE")" "$(dirname "$TBINTREE")"
if [[ -f $INTREE && ! -f ${INTREE}.stock ]]; then
  cp -a "$INTREE" "${INTREE}.stock"
fi
install -m 0644 "$KO" "$INTREE"
install -m 0644 "$KO" "$DST/appledrm.ko"
if [[ -f $TBKO ]]; then
  if [[ -f $TBINTREE && ! -f ${TBINTREE}.stock ]]; then
    cp -a "$TBINTREE" "${TBINTREE}.stock"
  fi
  install -m 0644 "$TBKO" "$TBINTREE"
  install -m 0644 "$TBKO" "$DST/thunderbolt.ko"
fi
if [[ -f $MUXKO ]]; then
  if [[ -f $MUXINTREE && ! -f ${MUXINTREE}.stock ]]; then
    cp -a "$MUXINTREE" "${MUXINTREE}.stock"
  fi
  install -d "$(dirname "$MUXINTREE")"
  install -m 0644 "$MUXKO" "$MUXINTREE"
  install -m 0644 "$MUXKO" "$DST/mux-apple-display-crossbar.ko"
fi
if [[ -f $PHYKO ]]; then
  if [[ -f $PHYINTREE && ! -f ${PHYINTREE}.stock ]]; then
    cp -a "$PHYINTREE" "${PHYINTREE}.stock"
  fi
  install -d "$(dirname "$PHYINTREE")"
  install -m 0644 "$PHYKO" "$PHYINTREE"
  install -m 0644 "$PHYKO" "$DST/phy-apple-atc.ko"
fi
depmod -a "$VER"

echo "Rebuilding Aurora initramfs so the patched appledrm is what boots"
mkinitcpio -p linux-aurora

echo OK >"$STATUS"
echo "Installed into $INTREE and initramfs-linux-aurora.img"
echo "Rebooting in 3s. GRUB default is Aurora."
sync
sleep 3
systemctl reboot
