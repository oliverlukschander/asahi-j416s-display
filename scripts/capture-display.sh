#!/usr/bin/env bash
# Snapshot of USB4 / DRM / Type-C / USB for the OWC hub + VMM7100 path.
# No sudo. Writes captures/capture-<timestamp>.txt
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/captures/capture-$(date +%Y%m%dT%H%M%S).txt}"
mkdir -p "$(dirname "$OUT")"

{
  echo "# asahi-j416s-display capture $(date -Is)"
  echo
  echo '## uname'
  uname -a
  echo
  echo '## cmdline'
  cat /proc/cmdline
  echo
  echo '## hyprctl monitors'
  hyprctl monitors all 2>/dev/null || echo '(hyprctl failed)'
  echo
  echo '## DRM connectors'
  for c in /sys/class/drm/card*-*; do
    [ -f "$c/status" ] || continue
    echo "$(basename "$c") status=$(cat "$c/status") enabled=$(cat "$c/enabled") edid_bytes=$(wc -c < "$c/edid" 2>/dev/null || echo 0)"
    echo "  modes: $(tr '\n' ' ' < "$c/modes" 2>/dev/null)"
  done
  echo
  echo '## thunderbolt'
  python3 - <<'PY'
import pathlib
base = pathlib.Path("/sys/bus/thunderbolt/devices")
if not base.exists():
    print("(no /sys/bus/thunderbolt/devices)")
    raise SystemExit
for d in sorted(base.iterdir()):
    print("====", d.name, "====")
    for p in sorted(d.iterdir()):
        if p.is_file() and p.name not in ("uevent", "remove", "key"):
            try:
                val = p.read_text().strip()
            except OSError as e:
                val = f"ERR {e}"
            if val and len(val) < 240:
                print(f"  {p.name}={val}")
        elif p.is_dir() and p.name.startswith("usb4_port"):
            link = (p / "link").read_text().strip() if (p / "link").exists() else "?"
            print(f"  {p.name} link={link}")
PY
  echo
  echo '## typec'
  for p in /sys/class/typec/port0 /sys/class/typec/port1 /sys/class/typec/port2 /sys/class/typec/port3; do
    [ -d "$p" ] || continue
    name="$(basename "$p")"
    echo "-- $name data_role=$(tr '\n' '/' < "$p/data_role" 2>/dev/null) power_role=$(tr '\n' '/' < "$p/power_role" 2>/dev/null)"
    for a in "$p/$name.0" "$p/$name.1"; do
      [ -f "$a/active" ] || continue
      echo "   $(basename "$a") active=$(cat "$a/active") svid=$(cat "$a/svid") mode=$(cat "$a/mode") vdo=$(cat "$a/vdo")"
    done
    if [ -f "$p/$name-partner/usb_mode" ]; then
      echo "   partner type=$(cat "$p/$name-partner/type") usb_mode=$(cat "$p/$name-partner/usb_mode")"
    fi
  done
  echo 'DT labels:'
  for n in /proc/device-tree/soc/i2c@39b040000/usb-pd@*/connector; do
    [ -f "$n/label" ] || continue
    echo "  $(echo "$n" | sed 's|.*/usb-pd@||;s|/connector||') $(tr -d '\0' < "$n/label")"
  done
  echo
  echo '## USB'
  python3 - <<'PY'
import pathlib
base = pathlib.Path("/sys/bus/usb/devices")
for d in sorted(base.iterdir(), key=lambda p: p.name):
    vid = d / "idVendor"
    if not vid.exists():
        continue
    def r(n):
        p = d / n
        return p.read_text().strip() if p.exists() else ""
    if not r("idVendor"):
        continue
    print(f"{d.name:12} {r('idVendor')}:{r('idProduct')} speed={r('speed'):6} {r('manufacturer')} {r('product')}")
PY
  echo
  echo '## dmesg (DP/TB, no RTKit)'
  dmesg --ctime 2>/dev/null | grep -Ei 'thunderbolt 0-|0:[0-9]+ <->|DP\):|PCIe-C|native ports|VMM7100|06cb|dcp_dptx|dp2hdmi|crossbar|USB4' \
    | grep -v RTKit | grep -v 'dependency cycle' | tail -100 || true
} > "$OUT"

echo "wrote $OUT"
