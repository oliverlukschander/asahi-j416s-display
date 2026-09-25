#!/usr/bin/env bash
# Rebuilds libaquamarine.so with both local patches applied, pinned to the
# exact tag matching the installed package (pacman -Qi aquamarine):
#   0001-connect-clear-stale-pageflip.patch -- stale pendingFlip on hotplug
#     reconnect (notes/2026-09-25-aquamarine-stale-pageflip.md)
#   0002-fix-destructor-teardown-order.patch -- null-deref crash tearing
#     down 2+ connectors on exit (notes/2026-09-25-aquamarine-destructor-teardown-crash.md)
set -euo pipefail

TAG=v0.15.1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$ROOT/src"

if [[ ! -d "$WORK" ]]; then
    git clone --branch "$TAG" --depth 1 https://github.com/hyprwm/aquamarine.git "$WORK"
fi

cd "$WORK"
git checkout -- . >/dev/null 2>&1 || true
for p in 0001-connect-clear-stale-pageflip.patch 0002-fix-destructor-teardown-order.patch; do
    git apply --check "$ROOT/$p"
    git apply "$ROOT/$p"
done

cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

echo
echo "Built: $WORK/build/libaquamarine.so.0.15.1"
sha256sum "$WORK/build/libaquamarine.so.0.15.1"
