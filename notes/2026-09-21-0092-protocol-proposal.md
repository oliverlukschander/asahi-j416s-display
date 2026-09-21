# 0092 single-attempt protocol candidate — not installed

Kernel commit: d8ffe9b, following 0091 hotplug handling.
Patch: patches/0092-drm-apple-single-attempt-usb4-protocol-probe.patch.

## Hypothesis, not an established USB4 protocol

The successful direct Type-C path calls connect, request_display, then HPD.
The experimental USB4 path sends HPD first, then request_display; the latter
powers/resets a firmware nub, after which discovery stalls. Its target 0x9001
also includes a guessed DPIN field absent from the official m1n1 definitions.

Test target 0x8001 (CONNECTED, CORE 1, ATC 0, DIE 0), connect unknown field
0x100, request_display, existing crossbar reselect, and one HPD assertion.
There is no early HPD and no second HPD. The HPD RPC timeout is eight seconds
so a five-second firmware failure can return rather than being obscured by
the usual one-second RPC timeout. This does not ensure firmware will respond.

This changes both the target's guessed bit and the ordering. If it succeeds,
it will not by itself tell us which change was necessary. If it fails, do
not infer which change was wrong. The actual USB4 core mapping and T602x
analog mux programming remain unverified; standard physical-DP definitions
are supporting evidence for the experiment, not proof of USB4 correctness.

Primary source inspected:
https://github.com/AsahiLinux/m1n1/blob/4184923ffb2dff079b384d6a32cc02142aa14572/src/dcp/dptx_port_ep.h

## Boundaries

- Disabled by default; read-only module parameter usb4_protocol_probe.
- Restricted to typec0, port/unit 0, DP IN mux 1, DCP index 2, die 0.
- Refuses an attached physical PHY or usb4_force_dptx.
- One attempt per module lifetime, including after errors/unplug; no automatic
  retries or second-core fallback. A later normal call for an already-owned
  connected port returns without another probe.
- Existing crossbar reselect retained; no new manual register mappings.
- Marks the display request owned so normal unplug releases it.
- Includes 0091's normal firmware hotplug callback handling. No injected modes.

The experiment still sends firmware requests that can affect hardware, and
uses the existing experimental crossbar code. These bounds cannot guarantee
against firmware hangs, a black panel or a reset.

## Explicit exception needed before hardware testing

notes/2026-09-21-status.md says: "Do not `set_hpd` after request_display."
The candidate intentionally does that once, using 0x8001 rather than the
previous failed 0x9001 experiment. Ask Oliver to approve this specific
exception; general encouragement is not being treated as that approval.
No other prohibited PHY/MMIO operation is requested or authorized by it.

## Proposed deployment after approval and hub unplug

1. Confirm no external Thunderbolt router, eDP active, and no directly
   connected monitor. Log exact deployment commands and addresses, commit
   and push before installing anything.
2. Back up the currently installed 0090 module and initramfs into a new
   /var/tmp/j416s-0092-before directory (refuse to overwrite a prior backup).
3. Install config/0092-usb4-protocol-probe.conf to
   /etc/modprobe.d/j416s-0092-protocol-probe.conf. Run the existing loader
   with --no-reboot and USB4_GROK_CONTINUE/SESSION unset. Verify module hash
   and config in the rebuilt initramfs. Log/push the reboot separately.
4. Boot with hub absent. Confirm eDP and usb4_protocol_probe=Y. If eDP does
   not recover, no hub test; restore 0090 through recovery using the backup.
5. Before reconnecting the hub, remove the experimental modprobe config and
   rebuild/verify initramfs without it, so a subsequent boot defaults to
   probe disabled. This does not change the already-loaded read-only flag.
6. Log/push the reconnect: hub in the confirmed left-back port, VMM7100 and
   monitor on the hub. Capture firmware RPC results, lane/rate/modes, DRM and
   user confirmation of picture, eDP and keyboard. Do not claim success from
   a zero RPC return. If eDP blacks out, unplug hub and stop immediately.

Controllers: dcpext1 0x315c00000, crossbar 0x70304c000, NHI 0x701f00000,
ACIO 0x701ac0000; firmware target 0x8001. No panel block mapping/writing,
no /dev/mem, no lpdptxphy assignment and no hub-port DP-alt-mode switch.

## Validation

Both firmware variants compile, MODPOST and module link pass against the
supplied build tree. git diff --check passes. Existing unused-function,
const-qualifier and missing-pahole-version warnings remain. No runtime test.

Candidate module SHA256:
ceb3aea107ee878ca1004098ae23f5b0ab2fdfa929dd244271224919e668e30f

src/appledrm/appledrm.ko is now 0092. Installed and running module remain
0090. The config file above is only in this repository, not /etc.
