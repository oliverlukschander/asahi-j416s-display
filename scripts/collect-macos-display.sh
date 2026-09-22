#!/bin/bash
# Collect native macOS display topology. No sudo, settings changes or tracing.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo "Usage: bash $0 disconnected|hub|direct [output-directory]"
  echo 'Run on the M2 in macOS. Reports stay local; no upload is performed.'
  exit 0
fi
case ${1:-} in
  disconnected|hub|direct) label=$1 ;;
  *) echo 'Expected label: disconnected, hub, or direct.' >&2; exit 2 ;;
esac
[[ $# -le 2 ]] || exit 2
[[ $(uname -s) == Darwin ]] || { echo 'Run this collector in macOS on the M2.' >&2; exit 1; }
out=${2:-"$HOME/Desktop/j416s-display-$label-$(date +%Y%m%dT%H%M%S)"}
# Refuse to overwrite a previous capture.
mkdir -m 0700 "$out"
/usr/bin/sw_vers > "$out/macos-version.txt"
/usr/sbin/sysctl -n hw.model > "$out/model.txt"
if [[ $(cat "$out/model.txt") != Mac14,10 ]]; then
  echo "Wrong machine: expected the Mac14,10 M2, found $(cat "$out/model.txt")." >&2
  exit 1
fi
/usr/sbin/ioreg -p IOService -w 0 > "$out/service-tree.txt"
/usr/sbin/ioreg -a -l -p IODeviceTree > "$out/device-tree.plist"
/usr/sbin/ioreg -a -l -r -c IOFramebuffer > "$out/framebuffers.plist"
/usr/sbin/ioreg -a -l -r -c IODisplayConnect > "$out/displays.plist"
/usr/sbin/system_profiler SPDisplaysDataType SPThunderboltDataType SPUSBDataType -json > "$out/topology.json"
printf 'label=%s\ncaptured=%s\n' "$label" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$out/capture.txt"
echo "Saved native macOS reports: $out"
