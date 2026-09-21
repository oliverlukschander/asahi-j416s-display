#!/usr/bin/env bash
# One-time: passwordless sudo + post-boot USB4 continue hook.
# Run: sudo ./scripts/install-unattended.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUDOERS_SRC="$ROOT/scripts/oliver-dev.sudoers"
HOOK_WRAPPER="$ROOT/scripts/omarchy-post-boot-usb4.sh"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
	echo "Re-running as root"
	exec sudo "$0" "$@"
fi

[[ -f $SUDOERS_SRC ]] || { echo "missing $SUDOERS_SRC"; exit 1; }
install -m 0440 "$SUDOERS_SRC" /etc/sudoers.d/oliver-dev
visudo -cf /etc/sudoers.d/oliver-dev

loginctl enable-linger oliver || true

chmod 0755 "$ROOT/scripts/boot-check.sh" "$HOOK_WRAPPER"
chown oliver:oliver "$HOOK_WRAPPER" || true
if [[ ! -e /home/oliver/.config/omarchy/hooks/post-boot.d/omarchy-post-boot-usb4.sh ]]; then
	sudo -u oliver -H /usr/share/omarchy/bin/omarchy hook install post-boot "$HOOK_WRAPPER"
fi

echo "OK: passwordless sudo for oliver, post-boot USB4 check installed"
echo "Test: sudo -n -u oliver true && echo nopasswd-ok"
echo "Next: sudo -n $ROOT/scripts/load-appledrm.sh"
