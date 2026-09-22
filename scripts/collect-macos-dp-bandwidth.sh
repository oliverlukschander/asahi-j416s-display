#!/bin/bash
# Collect native macOS DP-tunnel/bandwidth-allocation telemetry for the
# working right-port hub scenario. Read-only: no sudo, no settings changes,
# no kernel tracing/dtrace. Run on the M2 in macOS with the OWC hub already
# connected to the RIGHT USB-C port, VMM7100 + monitor attached and showing
# a real picture.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo "Usage: bash $0 [output-directory]"
  echo 'Run on the M2 in macOS, hub already connected to RIGHT USB-C and video working.'
  exit 0
fi
[[ $# -le 1 ]] || exit 2
[[ $(uname -s) == Darwin ]] || { echo 'Run this collector in macOS on the M2.' >&2; exit 1; }
out=${1:-"$HOME/Desktop/j416s-dp-bandwidth-$(date +%Y%m%dT%H%M%S)"}
# Refuse to overwrite a previous capture.
mkdir -m 0700 "$out"

model=$(/usr/sbin/sysctl -n hw.model)
if [[ $model != Mac14,10 ]]; then
  echo "Wrong machine: expected the Mac14,10 M2, found $model." >&2
  exit 1
fi

/usr/bin/sw_vers > "$out/macos-version.txt"
printf '%s\n' "$model" > "$out/model.txt"

# Full properties (not just the class tree) for the specific IOService
# classes already identified as relevant to DP-IN/tunnel/crossbar state.
for cls in AppleATCDPINAdapterPort IODPPortService AppleT602XATCDPXBAR \
           AppleT602XDisplayCrossbar DCPDPDeviceProxy IOThunderboltPort \
           IOThunderboltSwitch AppleThunderboltIP AppleDPTXDisplayPort; do
  /usr/sbin/ioreg -a -l -r -c "$cls" > "$out/ioreg-$cls.plist" 2>/dev/null || true
done

# Last 5 minutes of unified log for Thunderbolt/DisplayPort subsystems.
# Without root, Apple-private fields may show as <private>; still useful
# for message text, timing and event ordering.
/usr/bin/log show --last 5m \
  --predicate 'subsystem CONTAINS "thunderbolt" OR subsystem CONTAINS "displayport" OR subsystem CONTAINS "DisplayPort" OR eventMessage CONTAINS "bandwidth" OR eventMessage CONTAINS "DPTX" OR eventMessage CONTAINS "DP IN" OR eventMessage CONTAINS "DP OUT"' \
  > "$out/log-thunderbolt-dp.txt" 2>&1 || true

/usr/sbin/system_profiler SPDisplaysDataType SPThunderboltDataType -json > "$out/topology.json"

printf 'captured=%s\nnote=hub connected to RIGHT USB-C, video confirmed working\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$out/capture.txt"

echo "Saved native macOS DP-bandwidth reports: $out"
