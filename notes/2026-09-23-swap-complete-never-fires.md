# Root mechanism found: DCP never sends swap_complete for this pipeline

This is the most significant finding of the session and reframes
everything tested in 0093-0113 plus the mode-value sweep: the crossbar,
DPIN0 handshake, USB4 tunnel, AUX/DPRX, link-rate/lane negotiation, and
`set_digital_out_mode()` all genuinely work. The actual break is one
level up, in DCP firmware's frame-completion signaling.

## The mechanism, confirmed precisely

1. `set_digital_out_mode()` succeeds; DRM's atomic state shows `crtc-2`
   (assigned to connector USB-3, our BenQ) as `enable=1 active=1` with
   the correct mode ("2560x1440": 60Hz) and a plane assigned
   (`plane_mask=40`). Hyprland itself fully recognizes the display --
   correct EDID (`BNQ BenQ LCD T4M01233019`), positioned in the desktop
   layout, assigned its own workspace, `disabled: false`, `dpmsStatus: 1`.
2. A handful of initial frames are submitted and produce CRC entries
   (`/sys/kernel/debug/dri/soc:display-subsystem/crtc-2/crc/data`,
   frame indices 0x71-0x75 observed in one boot). CRC values are always
   `0x00000000`, which is normal for this driver -- eDP's working
   crtc-0 shows the same all-zero CRC pattern while its frame index
   climbs continuously (confirmed: ~43 frames counted over a 2-second
   sample), so CRC value is not a meaningful signal here, only the
   frame index advancing is.
3. crtc-2's frame index **never advances past that initial handful**,
   confirmed by two independent checks: (a) reading
   `crtc-2/crc/data` blocks forever (no new frames arrive, ever,
   verified with `timeout`-bounded reads over several minutes and
   after moving the cursor onto that screen's desktop area), while the
   identical read against `crtc-0/crc/data` (eDP) returns immediately
   every time; (b) Hyprland's own log
   (`~/.local/state` equivalent under `/run/user/<uid>/hypr/<sig>/hyprland.log`)
   shows the concrete, literal error:
   ```
   ERR from aquamarine]: atomic drm request: failed to commit: Device or resource busy, flags: ATOMIC_NONBLOCK PAGE_FLIP_EVENT
   ```
   logged once, immediately after the initial modeset succeeds, and
   never again -- meaning the compositor tried exactly once more to
   commit a new frame, got `-EBUSY`, and gave up on this output for
   the rest of the session.
4. `-EBUSY` from an atomic commit means the kernel believes a previous
   commit's page-flip completion is still outstanding. Tracing the
   completion path: DCP calls back into `dcpep_cb_swap_complete()`
   (`drivers/gpu/drm/apple/iomfb_template.c:153`, RPC callback table
   index `[589]`) when *it* considers a submitted swap finished; that
   handler calls `dcp_drm_crtc_page_flip()`
   (`drivers/gpu/drm/apple/dcp.c:1141`), which sends the DRM vblank/
   page-flip event that unblocks the next atomic commit. If DCP never
   sends this RPC callback for a given submitted swap, the kernel-side
   completion never fires, the crtc's pending-commit state never
   clears, and every subsequent commit attempt is rejected with
   `-EBUSY` -- exactly what's observed.
5. This is distinct from the earlier-considered
   `"swallowed swap ID N as fControllerPowerState is 0"` RTKit syslog
   message (see the "fControllerPowerState" investigation earlier the
   same day): that message fires loudly and only at disconnect time,
   for a different, later frame. During the active window, nothing is
   logged at all -- DCP is not loudly rejecting the swap, it is simply
   never acknowledging it as complete.

## What this rules in and out

- Rules out (with much higher confidence than before): DPIN0 MODE_A/
  MODE_B values (already exhaustively 0-15 tested), the crossbar
  route, AUX/DPRX negotiation, and the modeset call itself. All of
  that machinery is doing exactly what it should.
- Rules in: something in DCP firmware's per-swap completion signaling
  for this specific pipeline (dcpext-class controller driving a
  USB4-tunneled DPIN0 target) never fires the swap-complete RPC back
  to the AP, even though it accepted the modeset and the crossbar/link
  training all completed. This could be gated on the same class of
  condition as `fControllerPowerState`/timing-enable (silently, this
  time, rather than loudly), or something else entirely
  DCP-firmware-internal that has no Linux-side equivalent to set.

## Why this wasn't found earlier

This required correlating three separate signal sources that had never
been read together before this session's live investigation: DRM's own
atomic state (debugfs `state` file), the per-crtc CRC frame-index
counter (debugfs `crc/data`), and Hyprland's own compositor log
(previously never checked at all -- everything before this was kernel-
log-only). None of the kernel driver's own `dev_info`/`dev_warn` lines
show any hint of a problem in the active window; the failure is
completely silent from the kernel's own logging.

## Next steps

Not yet resolved: what specifically prevents DCP from sending
swap_complete for this exact pipeline shape. Worth checking:
targeted Asahi Linux history/issue search for "swap_complete" combined
with dcpext/secondary-display context (a much more specific, likely-to
-have-prior-art query than earlier broad "no picture" searches, now that
the exact failure point is known); and re-examining whether our own
`dcp->crtc` assignment (`dcp_link()`, `drivers/gpu/drm/apple/dcp.c`)
is correctly wired for the 315c00000 controller in this Type-C-routed
configuration, since `dcp_drm_crtc_page_flip()` dereferences `dcp->crtc`
directly and a stale/incorrect assignment there could independently
explain a silently-dropped completion even if DCP does send the RPC.

No hardware register write was made in the course of this
investigation -- purely observational (debugfs reads, Hyprland log
inspection, cursor movement). No further action needed before the next
session picks this up.
