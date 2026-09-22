# 0105: select the right DPIN route before enabling its clocks

0104 unplug confirmed: hub/external display absent, eDP active. Rate0
cleanup returned0. FIFO error occurred at cable removal; it does not prove
an error while attached. DEACTIVATE returned-ENODEV after ACIO cable teardown.

Native 13.5 AppleT602XATCDPXBAR::connect block938b7d8..938b888 writes only
route selectors030. DPIN0 case938b854..938b884 selects bits15:12 and3:0.
The native bringConnectionUp block938bc80..938bdf8 separately releases
resets and enables clocks. Existing0103 implemented that later bring-up,
but initial Linux mux selection still enabled gates before SET_LINK_RATE.
This remained a concrete difference despite0104's completed frame.

0105 adds default-off readonly mux parameter usb4_defer_bringup, scoped at
probe to j416s/T6020 right resourcef0304c000. Only DPIN0 source2 selections
use deferred behavior. Initial selection writes030 only; later guarded
DID_CHANGE after successful PLL configuration uses existing nativeup.
The preceding ACTIVATE deselect/select still performs existing quiescent
teardown/reset writes, then selects030 with gates off. No claim of a full
native lifecycle port. Direct DPPHY and other ports retain prior behavior.
The deferred path also omits old T8103-style050/070 accesses on teardown;
its select path skips those automatically. Existing one-attempt guards
and0104 cached completion remain. No new addresses/mappings or driver APIs.

Source-gate enable before PLL is eliminated. Whether this explains the
observed034=0 and absent video is unproven; do not claim a fix until actual
monitor picture. If firmware cannot progress with gates deferred, capture
that failure and stop rather than automatically enabling/retrying.

Validation: mux module build succeeded (known pahole/BTF environment warning).
ASan/UBSan RAM tests exercise actual C: initial route-only write; ACTIVATE
reselection leaves gates off; subsequent nativeup enables them; teardown
avoids050/070; invalid source and conflicting direct route refused. Existing
27 select/disconnect cycles and3 reset-failure cases pass. No live hardware
tests performed during development. Installer0105 pins all candidates,
verifies installed mux and any image copy, sets readonly flag, and backs up
nine files. Crossbar normally loads from rootfs, not the initramfs.
Mux SHA256 38e0756e986d236eddb458e2480f62f45eed1b3c2baeb5e61aa2e55a522f8b24.
