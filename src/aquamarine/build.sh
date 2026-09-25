#!/usr/bin/env bash
# Rebuilds libaquamarine.so with 0001-connect-clear-stale-pageflip.patch
# applied, pinned to the exact tag matching the installed package
# (pacman -Qi aquamarine). See notes/2026-09-25-aquamarine-stale-pageflip.md.
set -euo pipefail

TAG=v0.15.1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$ROOT/src"

if [[ ! -d "$WORK" ]]; then
    git clone --branch "$TAG" --depth 1 https://github.com/hyprwm/aquamarine.git "$WORK"
fi

cd "$WORK"
git checkout -- . >/dev/null 2>&1 || true
git apply --check "$ROOT/0001-connect-clear-stale-pageflip.patch"
git apply "$ROOT/0001-connect-clear-stale-pageflip.patch"

cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

echo
echo "Built: $WORK/build/libaquamarine.so.0.15.1"
sha256sum "$WORK/build/libaquamarine.so.0.15.1"
