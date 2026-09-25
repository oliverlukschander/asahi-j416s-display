# Hyprland: renderMonitor() misses Aquamarine's own session-active flag

## Where this picks up

0147's kernel-side auto-recovery is confirmed correct and working
(`notes/2026-09-24-0147-typec-resume-reverify.md`). The Aquamarine
stale-pageflip fix (`notes/2026-09-25-aquamarine-stale-pageflip.md`)
was believed to cause a real input/compositor freeze on logout, and
was reverted after three hard resets total across this investigation.

This note root-causes that freeze for real, via static analysis only
(no further live testing on Oliver's machine, after three hard resets
was judged too costly to keep repeating blindly). **It is not caused
by the Aquamarine `connect()` fix.** It's a genuine, separate bug in
Hyprland's own explicit-sync frame scheduler.

## Evidence trail

1. An incidental VT-switch test (`chvt` away and back, unrelated
   experiment) caught Oliver's own **live, unmodified, pristine**
   session hitting 210 back-to-back `ERR ]: drm: Session inactive`
   failures in its hyprland.log, in a tight loop with no delay, for the
   whole time the VT was switched away -- self-resolved the instant the
   VT switch back reactivated the session. This proved the busy-loop
   mechanism exists independently of any patch.
2. The actual freeze (via a real logout, twice) showed the identical
   shape both times: internal panel loads, external monitor added via
   a hotplug/reload ~800ms later, then total input silence (no
   keyboard, no cursor) for ~20-24s until a forced shutdown. Happened
   on the **left** port at home and the **right** port at work,
   ruling out anything port-specific.

## Root cause (confirmed via source, Hyprland v0.56.2, matching the
installed version exactly)

Two separate "is the session active" flags exist:
- `g_pCompositor->m_sessionActive` -- Hyprland's own flag.
- `g_pCompositor->m_aqBackend->session->active` -- Aquamarine's
  internal flag, backed by libseat (toggled by "Enabling seat"/
  "Disabling seat", and what `CDRMOutput::commitState()` actually
  checks before allowing a real KMS commit).

`CMonitorFrameScheduler::canRender()` (`src/output/MonitorFrameScheduler.cpp`)
-- the gate on the *normal* frame path (`onFrame()` when explicit-sync
scheduling is off, or the throttled path when it's on) -- correctly
checks **both**:
```cpp
bool CMonitorFrameScheduler::canRender() {
    if ((g_pCompositor->m_aqBackend->hasSession() && !g_pCompositor->m_aqBackend->session->active) || !g_pCompositor->m_sessionActive) {
        Log::logger->log(Log::WARN, "Attempted to render frame on inactive session!");
        return false;
    }
    ...
}
```

But `IHyprRenderer::renderMonitor()` (`src/render/Renderer.cpp`) --
called **directly and unconditionally** from `onSyncFired()` in the
explicit-sync ("missed frame") path, bypassing `canRender()` entirely
-- only checks one of the two:
```cpp
if (!g_pCompositor->m_sessionActive)
    return;
```
No check of `aqBackend->session->active` at all.

`CMonitorFrameScheduler::onSyncFired()` and `::onPresented()`
(`src/output/MonitorFrameScheduler.cpp`) call `renderMonitor()` /
`commitPendingAndDoExplicitSync()` directly, with **no session-active
check of their own either** -- they rely entirely on `renderMonitor()`
to catch it, which it only half-does.

## The loop

1. A frame is detected as "missed" (rendering took too long -- easy to
   trigger amid the extra processing during a hotplug/reconnect
   flurry). `onSyncFired()` sets `m_pendingThird`, calls
   `renderMonitor()` unconditionally, and arms a new GPU explicit-sync
   fd wait via `onFinishRender()`.
2. If `g_pCompositor->m_aqBackend->session->active` is false at this
   moment (but `m_sessionActive` hasn't caught up yet -- exactly the
   kind of momentary desync a fresh greeter session's own startup, or
   a hotplug-heavy reconnect, can produce) `renderMonitor()`'s own
   check passes, so it renders anyway. The GPU render itself succeeds
   (it doesn't need the display session). The **display commit**, deep
   inside Aquamarine's `commitState()`, correctly fails with `Session
   inactive` -- but only after the expensive render already happened.
3. The GPU render's completion still fires the explicit-sync fd,
   re-triggering `onSyncFired()`/`onPresented()` again -- neither
   checks session-active either. `onPresented()`, after a failed
   commit, may also call `scheduleFrame()` (which *is* properly gated
   and would no-op) -- but that's beside the point, because the
   `onSyncFired()`-driven render-and-rearm cycle keeps itself going on
   its own regardless, purely from GPU-side sync-fd timing, completely
   decoupled from the real display hardware's frame cadence.
4. This repeats as fast as the GPU can render, saturating the main
   event loop thread with doomed renders and failed commits -- input
   processing (keyboard, cursor) never gets a turn. Matches the
   symptom exactly: a live picture (the last real commit before the
   loop started), zero responsiveness, for as long as the desync
   between the two flags persists.

## Why the SDDM greeter is especially prone to this

A brand-new greeter session, right at startup, is exactly the moment
`m_sessionActive` and `aqBackend->session->active` are most likely to
be set at slightly different times (different subsystems initializing
in a slightly different order than an already-running session's
occasional VT switch, which the code was more obviously
tested/designed around). A monitor hotplugging during that same window
(as 0147's resume auto-recovery -- or, at work, the right port's own
reconnect -- both do) is enough to trigger a "missed frame" and start
the loop before the two flags ever agree.

## What this means for 0147 and the Aquamarine fix

- **0147 (kernel/driver-side auto-recovery) is unaffected and
  confirmed working.** Nothing in this trace involves the kernel at
  all once the tunnel/DCP layer has already succeeded (which dmesg
  already confirmed it does, cleanly, every time).
- **The Aquamarine `connect()`/`invalidateFrame()` fix is not
  implicated either.** The busy loop reproduces on a completely
  unpatched, pristine Aquamarine build (proven directly, via the VT-
  switch incident on Oliver's own live session). It's a Hyprland-side
  bug, in code that has nothing to do with `SDRMConnector::connect()`.
- **The real, separate bug**: `renderMonitor()` needs the same
  session-active check `canRender()` already has (both flags, not
  just one), and/or `onSyncFired()`/`onPresented()` should check
  `canRender()` themselves before doing anything, the same way the
  plain `onFrame()` path already correctly does.

## Update: fix written, built, and staged -- Oliver's explicit sign-off

Oliver: *"what we want to do is develop a proper fix, test it and file
a PR for it like always"* -- proceeding with the same rigor as every
kernel candidate this session.

### The fix

Two changes, `src/render/Renderer.cpp` and
`src/output/MonitorFrameScheduler.cpp` (Hyprland v0.56.2, matching the
installed package exactly):

1. `IHyprRenderer::renderMonitor()`: the existing
   `if (!g_pCompositor->m_sessionActive) return;` now also checks
   `g_pCompositor->m_aqBackend->session->active`, matching
   `canRender()`'s condition exactly.
2. `CMonitorFrameScheduler::onSyncFired()` and `::onPresented()`: both
   now call the existing `canRender()` (already correctly checks both
   flags) right at the top, before doing anything else -- these are
   the two functions that call `renderMonitor()`/commit directly,
   bypassing `canRender()`'s gate entirely, which is the actual root
   of the loop (fix #1 alone stops the wasted GPU render, but
   `onSyncFired()` would still unconditionally call `onFinishRender()`
   afterward and re-arm another sync wait regardless -- a lighter but
   still potentially tight loop). `onPresented()` deliberately does
   *not* clear `m_pendingThird` when bailing early -- the frame it
   refers to may have already been rendered by an earlier, successful
   `onSyncFired()`; leaving it set means it gets committed properly
   once the session is active again, matching the existing "if it
   didn't fire yet it doesn't matter, syncs will wait" comment already
   in that code path.

Patch and rebuild script tracked at `src/hyprland/` (patch +
`build.sh`, source itself gitignored, not vendored, same pattern as
`src/aquamarine/`).

### Build verification

Clean build against the exact installed version (cloned at tag
`v0.56.2` + submodules, matching `pacman -Qi hyprland` exactly): zero
errors, one warning (`MiscFunctions.cpp:97`, pre-existing, unrelated
to any touched file). Hash:
`4535df320536e0a1081be41652a040b342c684450859d4ec07765b7db8959b32`.

### Deployment plan and safety preparation

Same discipline as every live-system change this session, plus new
safety measures specifically motivated by the three hard resets on the
*other* fix this session:

- **SysRq fully enabled** (`kernel.sysrq`, both live and persisted via
  `/etc/sysctl.d/99-sysrq-emergency.conf`) -- Wayland compositors take
  an exclusive `EVIOCGRAB` on input devices, which is why Ctrl+Alt+F2
  didn't respond during the earlier freezes (a normal key combo goes
  through that grab). SysRq is intercepted by the kernel *before* any
  userspace grab, specifically for exactly this class of emergency.
- **The real plan, though**: Claude's own shell access to this machine
  is a separate channel entirely from Hyprland's input handling -- a
  frozen compositor shouldn't affect it at all. If this freezes again,
  Oliver should say so *before* reaching for the power button, so
  Claude can check whether that access is still responsive and, if so,
  find and kill the stuck process directly -- no reboot, logs intact.
  SysRq is the fallback if that channel is *also* unresponsive (which
  would suggest a much deeper problem than this specific bug).
- **Log mirroring, fixed**: the earlier `~/aqfix-log-mirror/watch.sh`
  never captured anything because it ran as `oliver`, and
  `/run/user/963` (the sddm system user) is mode `0700` -- silently
  unreadable. Now runs under `sudo`. Needs re-arming after every
  reboot (it's a plain background process with no persistence of its
  own); this was already missed once this session.
- `scripts/manage-hyprland-session-race.py` handles check/install/
  restore for `/usr/bin/Hyprland` with the same atomic
  temp-file-then-rename swap used for the Aquamarine library, verified
  backup before, verified checksum after. A running Hyprland process
  keeps its own already-loaded image regardless of what changes on
  disk -- this only affects the next fresh launch (next logout/login).

### That fix was wrong: confirmed dead code, reverted

`hyprctl getoption render:new_render_scheduling` on this machine
returns `false`. `onSyncFired()`/`onPresented()` both return
immediately at their very first line whenever that's off -- the
`canRender()` calls added to them never executed at all. The
`renderMonitor()` change was reachable, but redundant: its only
caller in the disabled config (`onFrame()`'s plain branch) is already
preceded by `canRender()`'s own check. This patch could not have had
any effect on this system, in either direction. Reverted; not shipped.

Four isolated-session tests afterward (real `login` on a spare VT via
`systemd-run`/`openvt` attempts and, eventually, a proper text login,
each running `timeout 20 Hyprland` with a persistent log path) all
came back completely clean -- zero `Session inactive` occurrences,
even with an explicit VT-switch-away-and-back during the window. This
was the actual useful signal: **a plain VT switch alone, with no
monitor activity, does not reproduce this.** Every real incident
involved an external monitor hotplug (0147's own resume-triggered
reconnect, or a fresh SDDM greeter session detecting the monitor
during its own startup) landing at the same time as a session
transition -- not the transition alone.

Given the cost of live-testing this by then (several hard resets,
none reproducing anything new), Oliver: *"i'd be fine with that, i'd
love to have a full resolution of that issue than in the end"* --
agreed to ship the two already-confirmed fixes (aurora-silicon/linux#25,
hyprwm/aquamarine#422) now and continue this investigation via static
analysis only, no more live resets, until there's a specific,
well-reasoned hypothesis and a safe way to test it.

## The real fix: gate CMonitorState::commit()/test() themselves

Re-examined every `m_state.commit()`/`m_state.test()`/`m_output->commit()`
call site in `Monitor.cpp` and `Renderer.cpp` systematically (13 sites
across 6 functions), checking each one's enclosing function for any
session-active gating at all:

- **`CMonitor::onConnect()`** -- runs whenever a monitor connects (a
  hotplug event; exactly 0147's resume-triggered reconnect, and
  exactly what a fresh greeter session's own startup does when it
  detects the external monitor). Calls `m_state.commit()` three times
  (lines ~270, 280, 313). **Zero session-active checks anywhere in
  the entire function.**
- **`CMonitor::applyMonitorRule()`** -- called from `onConnect()`
  (and elsewhere). Loops over up to ~8 candidate modes, calling
  `m_state.test()` for each, then `m_state.commit()` for the winner
  (lines ~738, 1055). **Also zero session-active checks.** If every
  test fails (which `commitState(true)` guarantees while the session
  is inactive, since it checks `session->active` before anything
  else), `success` never becomes true and `scheduleModeRetry()` fires
  -- a *bounded* retry (max 3, 1s apart) that still isn't
  session-aware, so it wastes all three attempts if the session is
  still inactive.
- Two more call sites (`onDisconnect()`, `commitDPMSState()`) --
  same pattern, no gating.
- `attemptDirectScanout()`'s raw `m_output->commit()` calls are the
  only exception, but reaching them requires an actively-fullscreen
  solitary client (`isDSBlocked()` returns early otherwise) -- not
  reachable from a login screen or an ordinary hotplug reconnect, so
  left alone.

None of this individually creates the *tight*, unbounded loop seen in
the original 210-occurrence evidence -- that entry point is still not
fully pinned down. But the underlying design flaw is real and larger
than any one call site: **every commit/test path across this file
relies on its *caller* remembering to check `canRender()` first**, and
several plainly don't. That's inherently fragile -- a single missed
site (existing or future) is enough to reach a real hardware commit
attempt during the exact window `commitState()`'s own guard and
`restoreAfterVT()`'s comment already treat as unsafe.

**Fix**: gate `CMonitorState::commit()` and `::test()` themselves --
the one place every one of these call sites ultimately funnels
through, in `Monitor.cpp` right next to their existing implementation
-- with the identical two-flag check `canRender()` already uses
(`aqBackend->session->active` and `m_sessionActive`). This closes the
gap categorically rather than patching call sites one at a time.

### Build verification

Clean rebuild against the exact installed v0.56.2 (fresh submodule
init, fresh CMake configure after a stale cache pointed at a since-
removed build directory from an earlier attempt): zero errors, one
pre-existing unrelated warning (`MiscFunctions.cpp:97`, untouched by
this change). Hash:
`3dbb5ee7b40897d2b7926743fe40ecb8b7bb60f3dc9547daa6f3dbae18032a2a`.

### Updated test plan

Given the confirmed finding that a plain VT switch doesn't reproduce
this, testing now needs an actual monitor connect event during a
session-inactive window -- without touching Oliver's real external
display/hub again. Plan: use Hyprland's own headless virtual-output
support (`hyprctl output create headless`) against the isolated test
session's own socket, timed to fire *while* that session's VT is
switched away (fully scripted by Claude; Oliver only needs to do the
initial login, same as the last several attempts). This exercises
`onConnect()` during a real session-inactive window with zero real
hardware involved, directly targeting the exact mechanism this fix
addresses.
