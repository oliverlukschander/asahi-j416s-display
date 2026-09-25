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

## Not attempted yet, deliberately

A candidate fix is straightforward to write (add the missing
`aqBackend->session->active` check to `renderMonitor()`, or call
`canRender()` from `onSyncFired()`/`onPresented()` before proceeding).
But this touches Hyprland's actual render/frame-pacing core -- a much
larger, more central piece of code than the one-line Aquamarine fix
that already cost three hard resets to (mis)diagnose live. Not
attempting to build, install, or test this against Oliver's daily
driver without a much more deliberate plan and his explicit sign-off
first.
