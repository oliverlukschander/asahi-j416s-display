#!/usr/bin/env bash
# Rebuilds Hyprland with 0001-fix-session-active-race.patch applied,
# pinned to the exact tag matching the installed package (pacman -Qi
# hyprland). See notes/2026-09-25-hyprland-render-session-active-race.md.
set -euo pipefail

TAG=v0.56.2
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$ROOT/src"

if [[ ! -d "$WORK" ]]; then
    git clone --branch "$TAG" --depth 1 https://github.com/hyprwm/Hyprland.git "$WORK"
fi

cd "$WORK"
git submodule update --init --recursive
git checkout -- . >/dev/null 2>&1 || true
git apply --check "$ROOT/0001-fix-session-active-race.patch"
git apply "$ROOT/0001-fix-session-active-race.patch"

cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

echo
echo "Built: $WORK/build/Hyprland"
sha256sum "$WORK/build/Hyprland"
