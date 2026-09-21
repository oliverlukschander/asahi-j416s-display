#!/usr/bin/env bash
# Omarchy post-boot: capture USB4 DP live-check; optionally resume Grok.
set -u
ROOT=/home/oliver/Development/asahi-j416s-display
OUT="$ROOT/notes/last-boot-check.txt"
ARMED="$ROOT/notes/boot-continue.armed"
SESSION_FILE="$ROOT/notes/boot-continue.session"
LOG="$ROOT/notes/boot-continue.log"
GREP='DP IN |DP OUT |keeping DP|INACTIVE|HPD=|SET_ACTIVE_LANE|SET_LINK_RATE|target=|PS190|device == NULL|Switched dpin|fDisplayPowerState|80000104|DPRX=|analog|validate|connect atc=|set_hpd|request_display|config space dead|core=|GET_SUPPORTS_HPD|APCALL|DEVICE_NOT|bind port|DEACTIVATE|ACTIVATE pulse'

for _ in $(seq 1 60); do
	hyprctl monitors >/dev/null 2>&1 && break
	sleep 1
done

for _ in $(seq 1 40); do
	dmesg | grep -q 'keeping DP tunnel' && break
	sleep 1
done
sleep 2

{
	echo "=== $(date -Iseconds) $(uname -r) ==="
	hyprctl monitors 2>/dev/null || echo 'hyprctl monitors failed'
	echo '--- dmesg ---'
	dmesg | grep -E "$GREP" || true
} >"$OUT"

[[ -f $ARMED && -f $SESSION_FILE ]] || exit 0

SID=$(tr -d '[:space:]' <"$SESSION_FILE")
GROK=$(command -v grok) || GROK=/home/oliver/.local/share/mise/installs/node/latest/bin/grok
PROMPT="$ROOT/scripts/boot-continue.prompt"
[[ -n $SID && -x $GROK && -f $PROMPT ]] || exit 0

systemctl --user stop usb4-grok-continue.service 2>/dev/null || true
systemctl --user reset-failed usb4-grok-continue.service 2>/dev/null || true

systemd-run --user --unit=usb4-grok-continue --collect \
	--working-directory="$ROOT" \
	--setenv=HOME="$HOME" \
	--setenv=PATH="$PATH" \
	--property=TimeoutStartSec=infinity \
	bash -lc "exec \"$GROK\" -r \"$SID\" --prompt-file \"$PROMPT\" --always-approve --permission-mode bypassPermissions --no-auto-update --max-turns 40 >>\"$LOG\" 2>&1"
exit 0
