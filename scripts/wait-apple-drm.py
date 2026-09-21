#!/usr/bin/python3
"""Wait for the Apple display device before SDDM starts its compositor."""
import stat
import sys
import time
from pathlib import Path


def ready_card(sysfs=Path('/sys/class/drm'), dev=Path('/dev/dri')):
    for connector in sysfs.glob('card*-eDP-1'):
        card = connector.name.removesuffix('-eDP-1')
        try:
            driver = (sysfs / card / 'device/driver').resolve(strict=True)
            if driver.name != 'apple-drm':
                continue
            if not stat.S_ISCHR((dev / card).stat().st_mode):
                continue
            if (connector / 'status').read_text().strip() != 'connected':
                continue
            if not (connector / 'modes').read_text().strip():
                continue
            return card
        except OSError:
            # Device removal or incomplete registration: check again next poll.
            continue
    return None


def wait_for_display(timeout=30, probe=ready_card):
    deadline = time.monotonic() + timeout
    while True:
        card = probe()
        if card:
            print(f'Apple DRM ready: {card}, eDP-1 connected with modes', flush=True)
            return 0
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print('Apple DRM not ready: refusing to start SDDM before eDP appears',
                  file=sys.stderr, flush=True)
            return 1
        time.sleep(min(0.1, remaining))


if __name__ == '__main__':
    sys.exit(wait_for_display())
