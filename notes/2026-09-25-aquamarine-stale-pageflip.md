# Aquamarine: stale pending-flip blocks every commit after an abrupt reconnect

## Where this picks up

0147 (`notes/2026-09-24-0147-typec-resume-reverify.md`) confirmed the
kernel/driver-side auto-recovery works correctly: after a real
lid-close/s2idle/lid-open cycle, the Thunderbolt DP tunnel reconnects
automatically with zero replug and zero ACIO retries. But the picture
still went black again shortly after, even though every layer below
the compositor's actual frame output reported healthy state (DRM
connector `connected`, `boltctl` authorized, `hyprctl monitors` showing
the output enabled with a correct mode). A physical unplug/replug (no
suspend/resume involved) fixed it immediately.

Oliver was explicit that a timing delay to dodge this wasn't
acceptable ("i want the correct solution ... not just guess and wait
X seconds"). This note is that correct solution: a real, confirmed
defect in Aquamarine (Hyprland's DRM backend library,
github.com/hyprwm/aquamarine), not a race to paper over.

## Root cause

Confirmed by reading Aquamarine's actual source
(`src/backend/drm/DRM.cpp`, checked out at the exact installed tag
`v0.15.1`, matching `pacman -Qi aquamarine`):

- `SDRMConnector::disconnect()` calls `invalidateFrame()`, which clears
  any stale pending-flip state on the connector's CRTC
  (`crtc->pendingFlip`, disarmed via `crtc->disarmPageFlip()`).
- `SDRMConnector::setCRTC()` also calls `invalidateFrame()` -- but only
  when the CRTC assignment actually *changes* (`if (crtc == newCRTC)
  return;` short-circuits otherwise).
- `SDRMConnector::connect()` -- the code path a hotplug reconnect goes
  through -- calls neither. It allocates a fresh `CDRMOutput` and
  proceeds straight to scheduling a frame, with no equivalent clearing
  of any pending-flip state left on the CRTC from before.
- Aquamarine's own `CDRMBackend::restoreAfterVT()` has an explicit
  comment describing this exact failure class for a different trigger
  (VT switch / session reactivation): "During S3 suspend the display
  hardware powers off, so any pending page-flip completion events are
  lost ... Without this reset, commitState() rejects every frame with
  'Cannot commit when a page-flip is awaiting' ... leaving outputs
  permanently black after resume." It fixes that path by clearing
  `invalidateFrame()` for every currently-known connector on session
  reactivation.

Our case reaches the identical failure mode through a path that
mitigation doesn't cover: the Thunderbolt/USB4 tunnel is torn down
abruptly during suspend (confirmed in earlier work -- generic
thunderbolt-core's `tb_free_invalid_tunnels()` runs in the noirq
resume phase and silently invalidates the tunnel). If a real commit
happened to be in flight on this CRTC at that moment, its page-flip
completion event can never arrive -- the hardware it was targeting is
gone. When the tunnel and connector come back (via 0147's resume
auto-recovery), the connector goes through `connect()`, not
`disconnect()`/`setCRTC()` with a changed CRTC (a USB4 dock reconnects
to the *same* CRTC it had before), so nothing clears the stale
`pendingFlip`. Every subsequent real commit on that CRTC is then
silently rejected forever by the guard the `restoreAfterVT()` comment
describes -- the picture never returns until something else
(`disconnect()`+`connect()` from an actual physical replug, which
*does* clear it via `disconnect()`) resets it.

This is a real, upstream-confirmed defect (Aquamarine already treats
this exact failure class as a bug worth guarding against -- it just
missed this second trigger path), not a timing race specific to this
machine.

## The fix

One call, in `SDRMConnector::connect()` (`src/backend/drm/DRM.cpp`),
right after the "already connected" early-return guard:

```cpp
invalidateFrame();
```

`invalidateFrame()` is already safe to call unconditionally --
it no-ops if there's no CRTC yet or no pending flip
(`if (crtc && crtc->pendingFlip.connector == self)`). This guarantees
that regardless of *how* the previous output went away (a graceful
disconnect, or an abrupt tunnel teardown mid-commit), a fresh
`connect()` always starts from a clean slate before any real commit is
attempted -- the same guarantee `restoreAfterVT()` already provides for
its own trigger, extended to cover this one.

## Verification (no live changes yet)

- Diff is 14 lines: 13 comment, 1 functional (`invalidateFrame();`).
  `git diff` shows nothing else touched.
- Full clean rebuild against the exact installed version (cloned at
  tag `v0.15.1`, matching `pacman -Qi aquamarine` exactly): zero
  errors, zero warnings.
- Exported dynamic symbol set (`nm -D --defined-only`) compared against
  the currently-installed `/usr/lib/libaquamarine.so.0.15.1`: identical
  except for 3 incidental libstdc++/template-instantiation weak
  symbols (`_M_replace_cold`, `__to_chars_8`, a `CWeakPointer<CGLTex>`
  destructor variant) -- normal compiler-instantiation-order noise, not
  a real API/ABI change. No public header, struct layout, or function
  signature was touched.
- New build hash:
  `6e84b0138e6a80bb6d13494d0a85f2d48be153c60c2c351499498c8fd0297316`
- Current installed (pristine) hash:
  `82dd57588764273995c5faa913c9198f9d6e25d78da9ca830acd43f2591c2e24`
  (matches the existing backup at
  `/var/tmp/aquamarine-trace-backup/libaquamarine.so.0.15.1.orig`,
  left over from an earlier, abandoned live-instrumentation attempt on
  this same library -- confirmed byte-identical, so that backup is
  trustworthy).

## Deployment plan

This is a plain shared library (`/usr/lib/libaquamarine.so.0.15.1`,
symlinked from `.so`/`.so.14`), not a kernel module -- no depmod,
initramfs, or reboot involved. But it's pacman-owned and actively
mapped into the running Hyprland session, so the same discipline
applies: verified backup before install, verified checksum after, and
-- per the earlier crash history swapping an instrumented build into
this exact library live -- **no hot-swap while the session is active.**
Oliver chose: write the patch now, install the file, then test by
logging out and back in (a fresh Hyprland process is what will
actually load the new code; the currently-running one keeps using
the already-mapped old one regardless of what's on disk).

`scripts/manage-aquamarine-pageflip.py` (check/install/restore, same
pattern as the kernel candidates) handles this.

## Test plan

1. Install (file swap only, verified backup, no logout yet).
2. Oliver logs out and back in at a moment of his choosing.
3. Real test: lid close -> s2idle -> lid open, hub never touched --
   the same test 0147 was validated with. This time watch for the
   picture staying up on its own, no replug and no DPMS toggle needed.
