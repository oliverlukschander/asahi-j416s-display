#!/usr/bin/env bash
# Install patched appledrm into the module tree AND the Aurora initramfs.
# appledrm is loaded from initramfs, so updates/ alone is ignored.
# Do not rmmod the live display driver — that blacks the panel.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(uname -r)"
KO="$ROOT/src/appledrm/appledrm.ko"
TBKO="$ROOT/src/thunderbolt/thunderbolt.ko"
TBAPPLEKO="$ROOT/src/thunderbolt/thunderbolt_apple.ko"
MUXKO="$ROOT/src/mux/mux-apple-display-crossbar.ko"
PHYKO="$ROOT/src/phy/phy-apple-atc.ko"
DPTXPHYKO="$ROOT/src/phy/phy-apple-dptx.ko"
INTREE="/lib/modules/$VER/kernel/drivers/gpu/drm/apple/appledrm.ko"
TBINTREE="/lib/modules/$VER/kernel/drivers/thunderbolt/thunderbolt.ko"
TBAPPLEINTREE="/lib/modules/$VER/kernel/drivers/thunderbolt/thunderbolt_apple.ko"
MUXINTREE="/lib/modules/$VER/kernel/drivers/mux/mux-apple-display-crossbar.ko"
PHYINTREE="/lib/modules/$VER/kernel/drivers/phy/apple/phy-apple-atc.ko"
DPTXPHYINTREE="/lib/modules/$VER/kernel/drivers/phy/apple/phy-apple-dptx.ko"
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
if [[ -f $TBAPPLEKO ]]; then
  if [[ -f $TBAPPLEINTREE && ! -f ${TBAPPLEINTREE}.stock ]]; then
    cp -a "$TBAPPLEINTREE" "${TBAPPLEINTREE}.stock"
  fi
  install -m 0644 "$TBAPPLEKO" "$TBAPPLEINTREE"
  install -m 0644 "$TBAPPLEKO" "$DST/thunderbolt_apple.ko"
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
if [[ -f $DPTXPHYKO ]]; then
  if [[ -f $DPTXPHYINTREE && ! -f ${DPTXPHYINTREE}.stock ]]; then
    cp -a "$DPTXPHYINTREE" "${DPTXPHYINTREE}.stock"
  fi
  install -d "$(dirname "$DPTXPHYINTREE")"
  install -m 0644 "$DPTXPHYKO" "$DPTXPHYINTREE"
  install -m 0644 "$DPTXPHYKO" "$DST/phy-apple-dptx.ko"
fi
depmod -a "$VER"

echo "Rebuilding Aurora initramfs so the patched appledrm is what boots"
mkinitcpio -p linux-aurora

echo OK >"$STATUS"
echo "Installed into $INTREE and initramfs-linux-aurora.img"

# Arm post-boot Grok continue if a session id is present.
if [[ -n ${USB4_GROK_SESSION:-} ]]; then
	printf '%s\n' "$USB4_GROK_SESSION" >"$ROOT/notes/boot-continue.session"
fi
if [[ -s $ROOT/notes/boot-continue.session ]]; then
	touch "$ROOT/notes/boot-continue.armed"
	echo "Armed Grok continue for session $(tr -d '[:space:]' <"$ROOT/notes/boot-continue.session")"
fi

echo "Rebooting in 3s. GRUB default is Aurora."
sync
sleep 3
systemctl reboot
