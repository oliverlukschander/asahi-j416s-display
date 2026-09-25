# Aquamarine: null-deref crash in CDRMBackend's destructor with 2+ connectors

Found by accident while validating the Hyprland session-active-race fix
(`notes/2026-09-25-hyprland-render-session-active-race.md`): the isolated
test session's `Hyprland` process (real login on tty2, patched binary run
directly by path) disappeared partway through its `timeout 120` run. A
`hyprctl monitors` query moments earlier had shown a perfectly healthy
three-monitor state (`eDP-1`, `USB-3`, the simulated `testmon1` headless
output all present with sane geometry), so this isn't the session-active
race -- it's a separate, previously-unknown bug in Aquamarine itself.

## The crash

`coredumpctl` showed three identical crashes today, all in the isolated
test binary (`src/hyprland/src/build/Hyprland`, PIDs 71296/81690/86975,
10:10-10:14) -- and, critically, **the same exact signature already hit
the real, system-installed `/usr/bin/Hyprland` twice this morning**
(09:46:55 and 09:47:35, PIDs 63397/67048), well before this test session
even started. This is not a test artifact; it was already happening to
Oliver's real system.

```
Program terminated with signal SIGSEGV, Segmentation fault.
#0 Aquamarine::CDRMBackend::flushAsyncCommitEvents() () from libaquamarine.so.14
#1 Aquamarine::CDRMBackend::cancelAsyncOutput(Aquamarine::CDRMOutput*, bool) ()
#2 Aquamarine::SDRMConnector::disconnect() ()
#3 Aquamarine::CDRMBackend::~CDRMBackend() ()
#4 Hyprutils::Memory::CSharedPointer<Aquamarine::CDRMBackend>::_delete(void*) ()
#5 Aquamarine::CBackend::~CBackend() ()
#6 Hyprutils::Memory::CSharedPointer<Aquamarine::CBackend>::_delete(void*) ()
#7 Hyprutils::Memory::CSharedPointer<Aquamarine::CBackend>::~CSharedPointer() ()
#8 __cxa_finalize ()
#9 __do_global_dtors_aux ()
...
#13 exit ()
```

Always at process exit, during global/static destruction of Hyprland's
`CBackend` (which owns the `CDRMBackend`).

## Root cause

`src/backend/drm/DRM.cpp`, `CDRMBackend::~CDRMBackend()` (pristine
v0.15.1, line 381):

```cpp
Aquamarine::CDRMBackend::~CDRMBackend() {
    stopCommitThread();

    for (auto& conn : connectors) {
        conn->disconnect();
        conn.reset();
    }
    ...
}
```

`conn.reset()` nulls that vector slot's `shared_ptr` in place, immediately,
inside the same loop that's still calling `disconnect()` on later entries.
`SDRMConnector::disconnect()` (line 2143) calls
`backend->cancelAsyncOutput(output.get())`, which (line 473) unconditionally
calls `flushAsyncCommitEvents()`:

```cpp
void Aquamarine::CDRMBackend::flushAsyncCommitEvents() {
    for (const auto& connector : connectors) {
        if (connector->output && connector->output->asyncCommitEventPending)
            emitAsyncCommitEvent(connector->output);
    }
}
```

This walks the **entire** `connectors` vector again -- including earlier
slots the destructor's own loop has *already* `.reset()`'d to null on a
prior iteration. `connector->output` on a null `connector` is a null-pointer
dereference. With exactly one connector this is unreachable (nothing has
been reset yet when the only entry disconnects); **with 2 or more
connectors ever registered, disconnecting the second one always walks into
the first one's freshly-nulled slot.** Any normal system with an internal
panel plus one external monitor qualifies -- which is exactly why it was
already hitting the real session.

`cancelAsyncOutput()` only reaches `flushAsyncCommitEvents()` when
`output->asyncOwnerID` is set (line 474), i.e. the connector has had at
least one async commit submitted -- true for any connector that's actually
been driving a real picture, which both `eDP-1` and `USB-3` had been on
every crash observed.

Checked every other iteration of `connectors` in this file (14 call sites,
lines 71/610/920/1158/1327/1555/etc.) -- **none of them null-guard the
element itself**, only `->output`. The destructor's in-place reset is the
sole place that violates the "every entry is always a valid, non-null
`SDRMConnector`" invariant every other reader of this vector already
assumes. That's the actual bug: not a missing null check to sprinkle
everywhere, but one function creating a state (null entries mid-container)
that nothing else expects and that only itself is responsible for tearing
down safely.

## Fix

Split the destructor's single loop into two passes -- disconnect
everything first (every entry stays valid and non-null for the full
duration of every `disconnect()` call, so `flushAsyncCommitEvents()`
re-entering the same vector from a later connector's teardown only ever
sees valid pointers whose `->output` is correctly null if already
disconnected), then reset everything once no code is iterating the vector
anymore:

```cpp
for (auto& conn : connectors)
    conn->disconnect();
for (auto& conn : connectors)
    conn.reset();
```

Two extra lines, zero new state, matches the invariant every other call
site already relies on. Patch: `0002-fix-destructor-teardown-order.patch`.
Rebuilt: `libaquamarine.so.0.15.1` SHA256
`77914a9ff0d5aaae94e194cfe527517e1197de1cd689b71fe4080b3daf61fc0b`.

## Status

Built, not yet tested or installed system-wide. Oliver's tty2 test-login
session from the earlier headless-hotplug test is still alive (`who`
confirms it, idle since 10:09) -- next step is having him re-run
`bash /tmp/run-test.sh` (now pointed at the fixed `.so` via
`LD_LIBRARY_PATH`, no fresh login needed) and confirming no crash on the
`timeout`-triggered exit this time, via the same `coredumpctl`-based check
that found this in the first place.

Once confirmed, this ships as its own PR to `hyprwm/aquamarine`, same
pattern as #422 -- unrelated to the stale-pageflip fix (different
function, different bug class: a genuine reconnect data-staleness issue
there, a destructor iteration-order bug here), and unrelated to the
Hyprland session-active-race fix that was actually under test when this
surfaced.
