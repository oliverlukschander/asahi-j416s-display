# 0129: widen the tunnel set_hpd timeout to 8s as a diagnostic

Direct continuation of 0128. Both dcpext1 boots since the pipeline fix
landed have failed identically, before ever reaching `DPRX_DONE=1`. This
candidate does not change any routing, crossbar, or PHY logic -- it widens
exactly one existing timeout, as a diagnostic to answer the question
ACTION-LOG has been carrying open: is DCP's multi-second unresponsiveness
after `request_display` a real internal retry our 1-second host timeout is
cutting off, or a genuinely failed AUX negotiation that no timeout would
fix?

## A clean read of both 0128 captures (they are byte-for-byte identical)

Decoding the AFK group/cmd numbers against `dptxep.c`'s actual call sites
(`afk_service_call(service, 0, 12, ...)` = validate,
`afk_service_call(service, 0, 11, ...)` = connect,
`afk_service_call(service, 0, 6, ...)` = request_display,
`afk_service_call(service, 0, 7, ...)` = release_display,
`afk_service_call_timeout(service, 8, 8, ...)` = set_hpd), the timeline in
`captures/2026-09-24-0128-boot-kernel.log` and
`captures/2026-09-24-0128-retry-boot-kernel.log` is, in both runs:

1. `DP IN tunnel routing: tunnel 0:5 <-> 1:19` (Thunderbolt tunnel up;
   `tb_dp_activate()` starts `tb_dp_dprx_start()` right here, independent of
   everything below).
2. validate call #1, connect call #1, request_display call #1 -- all
   succeed silently within the normal 1000ms budget (`request_display: call
   #1 result=0`), identical to every prior successful attempt including
   0127.
3. `dcp_dptx_connect()` calls `dptxport_set_hpd(..., true)` next (group 8
   cmd 8, since `dcp_is_typec_output(dcp)` is true). **This is the first
   call, in this whole project's history, to silently swallow the entire
   1000ms budget with no reply at all**: `AFK[ep:2a]: AppleDCPDPTXRemotePort
   (chan:1) command type 0xc0 tag 0x0300 timed out after 1000 ms`, then
   `dcp_dptx_connect: failed to assert Type-C HPD: -110`.
4. Falls into `out_release`: `dptxport_release_display()` (group 0 cmd 7)
   -- also times out at 1000ms.
5. `dcp_typec_reconnect_work()` fires once (`DPTX_RECONNECT_DELAY` =
   1000ms later): a fresh `dcp_dptx_connect()`, and this time even
   *validate* (call #2, group 0 cmd 12) times out at 1000ms -- the same
   call that succeeded instantly 3 seconds earlier in the same boot.
6. `usb4_protocol_probe`'s pre-existing "no automatic retry" gate
   (`dcp.c:1504-1506`, this project's own deliberate throttle, not a bug)
   stops the driver's own retry loop right there: `USB4 protocol probe
   finished: -110; no automatic retry`.
7. About a second later, DCP's *firmware* independently sends three
   upcalls the driver never asked for: APCALL 22 (`DEVICE_NOT_RESPONDING`),
   APCALL 24 (`DEVICE_NOT_STARTED`), then APCALL 1 (`DEACTIVATE`). These
   are not replies to any of the three timed-out calls above (the reply
   path for those was already reaped, see below) -- they are DCP's own,
   unprompted verdict.
8. About 7 seconds after that (12 seconds after step 1), a completely
   separate mechanism gives up too: `tb_dp_wait_dprx()` in
   `drivers/thunderbolt/tunnel.c` -- generic, upstream, non-Apple code,
   polling the raw `DP_COMMON_CAP_DPRX_DONE` hardware bit every 25ms
   (`TB_DPRX_WAIT_TIMEOUT`) for up to 12000ms (`TB_DPRX_TIMEOUT`), started
   at step 1 and running the whole time regardless of what DCP/AFK are
   doing -- `Apple: DPRX timeout, keeping DP tunnel`. DPRX read 0 for the
   entire window.

## Why 0127 is not informative for this specific failure

0127 (dcpext0, the pipeline the 0128 fix moved *away* from, left port) ran
the identical validate/connect/request_display/set_hpd sequence with zero
timeouts anywhere -- `dptxport_set_hpd()` has no `dev_info` at send time,
so a fast, silent success there is invisible in the log; this is not 0127
skipping the call (`dcp_is_typec_output()` is true for both pipelines,
since both have `active_typec_route` set). It went on to a burst of
firmware-driven upcalls (`GET_MAX_LINK_RATE`, `GET_SUPPORTS_DOWN_SPREAD`,
`SET_DOWN_SPREAD`, `WILL_CHANGE_LINK_CONFIG`, `SET_LINK_RATE 0xa`, all
answered instantly), real EDID data (a 205757-byte `TimingElements`
property, 22 decoded modes), and `DPRX_DONE=1` -- then failed about 2
seconds later at a structurally later, different point: `dcp_dptx_connect:
timed out waiting for port 0 link configuration`
(`wait_for_completion_timeout(linkcfg_completion, DPTX_CONNECT_TIMEOUT)`,
2000ms), immediately downstream of a logged `DP tunnel crossbar up failed:
-22` inside the new `DID_CHANGE_LINK_CONFIG` handler
(`dcp_tunnel_crossbar_up()`, `dcp.c:439`, this project's own new code from
0127, exercised for the only time so far). Grepping both 0128 captures for
every crossbar-driver log line (`apple-display-crossbar ...: Switched
dpinN ...`) shows nothing at all near the connect attempt -- confirming
`dcp_tunnel_crossbar_up()` is never even reached in 0128, because the
sequence dies at set_hpd, well before `SET_LINK_RATE`/
`DID_CHANGE_LINK_CONFIG` would run. Since 0127 ran on dcpext0 -- a pipeline
this project's own 0128 fix already established has the wrong
plane/CRTC/scanout wiring for a real tunnel route -- a `-22` (EINVAL) from
`mux_control_try_select()` on that route is well explained by a bad
`mux_index` for a pipeline that was never supposed to carry this tunnel:
the same already-diagnosed wrong-pipeline bug, not a new one. 0127's
failure point and 0128's are two different bugs in two different, mutually
unreachable code paths; only 0128's is still open.

## The open question, read as even-handedly as the evidence allows

Two readings are both consistent with everything logged so far:

- **Genuine AUX/DPCD failure.** `tb_dp_wait_dprx()`'s 12-second budget does
  not depend on DCP/AFK at all -- it reads the ACIO capability register
  directly, on a separate workqueue, started at tunnel-up. It is already
  far more patient than the 1-second AFK timeout, and it never sees success
  either. DCP's own eventual verdict (`DEVICE_NOT_RESPONDING`/
  `DEVICE_NOT_STARTED`) is sink-level language, not RPC-transport language,
  suggesting DCP itself concluded the downstream device isn't answering
  rather than merely being slow to reply to the host.
- **Host gave up too early, and that's exactly what's cutting off a real
  retry.** `afk_service_call_timeout()` (`afk.c:968-984`) discards a late
  reply with no log trace at all on timeout: `service->cmds[idx].completion
  = NULL; service->cmds[idx].free_on_ack = true;` then returns -ETIMEDOUT.
  If DCP's firmware answers set_hpd at, say, t+3s, today's captures cannot
  distinguish that from DCP never answering -- the driver has already
  stopped listening and the reply (if any) is silently freed. This also
  means DCP's own `DEVICE_NOT_RESPONDING` a few seconds later is not
  provably independent of the host's silence either; it could be DCP's own
  reaction to *not hearing back from the host* rather than to the sink.

The tunnel-layer evidence leans toward genuine failure, but is not
conclusive, because it's possible DCP's internal handling of set_hpd is
itself the precondition for the ACIO analog block to attempt AUX at all --
if DCP's internal process needed the full budget and we cut *it* off
indirectly some other way, the raw DPRX bit would never assert either, for
reasons that still trace back to timing rather than a hard failure. The
only way to actually tell the two apart is to give the host side enough
patience to either see a reply or definitively not.

## The change (kernel commit d4d8abe)

`dptxport_set_hpd_timeout()` already exists
(`drivers/gpu/drm/apple/dptxep.c:229`) and takes an explicit `timeout_ms`
-- it is the exact knob needed, already proven to work mechanically (it's
literally what produces the "timed out after 1000 ms" messages today,
via `dptxport_set_hpd()`'s plain wrapper passing `MSEC_PER_SEC`). Changed
the single call site in `dcp_dptx_connect()` (`dcp.c:1448`) to call
`dptxport_set_hpd_timeout(..., true, 8000)` directly instead. 8000ms is
comfortably past DCP's own apparent ~5 second internal give-up (request_
display success to DEACTIVATE spans about 5 seconds in both captures), and
still short of the tunnel layer's independent 12-second budget, so a
success at 8s would land before the tunnel layer would have torn anything
down on its own.

`dcp->hpd_mutex` is held for the extra duration (it's released only after
this call returns, `dcp.c:1458`), but it is scoped to this one `struct
apple_dcp` instance (`315c00000.dcp`, dcpext1) and is a separate lock from
the panel's own instance (`389c00000.dcp`) -- so this cannot stall the
internal display, only this one external-monitor connect attempt.

Deliberately left validate/connect/request_display untouched: all three
already succeed within 1000ms on every run so far (including call #1 in
both 0128 runs), so there's no evidence they need more time, and touching
only the one implicated call keeps this a single-variable test.

## Known uncertainty

- If DPRX still never asserts even at 8s, that cleanly rules out "the host
  was too impatient" for this specific call, and the next candidate should
  look for something actually different about the physical AUX path on
  dcpext1/right-port rather than re-guessing timeouts again. One
  unexplained, not-yet-decoded data point worth returning to then: the
  ACIO `dpin0 analog` register dump's offset `0x18` value differs across
  all three runs so far (0127 success: `0000100a`; 0128: `00001017`;
  0128-retry: `00000017`) -- flagging this, not concluding anything from it,
  since I have not identified what that offset encodes.
- If it does succeed, expect the sequence to continue into `SET_LINK_RATE`
  and, for the first time ever on the *correct* pipeline,
  `dcp_tunnel_crossbar_up()` -- itself unexercised/unverified code as of
  this candidate. A second, brand-new failure there would not be
  surprising and should not be read as a setback; it would still mean this
  candidate's question was answered (yes, it was a timeout) and the
  crossbar generalization's own "known uncertainty" (flagged in
  `notes/2026-09-24-0127-*.md`, the `FIFO_RD_N_CLK_EN` field-width guess)
  would become the live suspect.

## Build verification

Only `dcp.o` recompiled (single call site + comment). New `appledrm.ko`
SHA256: `131f3d85cad626e5387df05b55016f80dac60196cb5d555c4dc73503ab96a6a9`.
`thunderbolt_apple.ko`, `mux-apple-display-crossbar.ko`,
`phy-apple-atc.ko`, and `thunderbolt.ko` all verified byte-identical to
0128 (direct SHA256 comparison, none touched this candidate). Stale-symlink
sweep clean (the only non-symlinked files under `src/` are build-generated
`.mod.c` files and the two pre-existing, already-triaged divergences from
`notes/ACTION-LOG-ARCHIVE-2026-09-21-to-0125.md` -- `src/phy/dptx.{c,h}`
and `src/dispclk/apple-dispclk.c` -- neither touched today).
`test-dpin-handshake.c` 13/13 pass (regression check only; this candidate
never touches `apple-dpin-handshake.h` or its caller). Patch:
`patches/0129-widen-set-hpd-timeout-diagnostic.patch`. `scripts/manage-
0129.py` derived from `manage-0128.py`: only the `appledrm` hash and the
`CONFIG`/`BACKUP` path suffixes changed; `OPTIONS` is byte-identical to
0128's since no module parameter changes.

## Test plan

Same protocol, single boot, hub already connected (no port change; still
dcpext1/right-port, per Oliver's standing instruction not to re-litigate
port choice). Watch specifically for:

1. Whether `request_display: call #1 result=0` still appears identically
   (it should -- nothing upstream of set_hpd changed).
2. Whether the `AFK[ep:2a]: ... tag 0x0300 ... timed out after 1000 ms`
   line disappears (meaning DCP answered within the new 8s window) or
   reappears as `timed out after 8000 ms` (meaning it never answers even
   given 8x the patience).
3. If it answers: `SET_LINK_RATE`, APCALL 6 (`DID_CHANGE_LINK_CONFIG`),
   `DP tunnel crossbar up` (this is the first time this code runs on the
   *correct* pipeline), `DPRX_DONE=1`, and -- the actual goal -- a picture.
4. If it times out again at 8000ms: this closes the "1-second timeout is
   the whole problem" hypothesis for `set_hpd` specifically. Do not
   re-test a longer timeout on this same call again without new evidence;
   look at the physical path instead.
