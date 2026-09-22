# Native macOS working-hub comparison — 2026-09-22

Three reports copied from the M4 Desktop to this Linux machine. They were
collected on the M2, Mac14,10, macOS 26.5.1 build 25F80. Oliver identifies
074227 as right USB-C and 074252 as left-back USB-C; both had working video.

| Capture suffix | Connection | External display | USB4 bus |
| --- | --- | --- | --- |
| disconnected-20260922T074155 | Disconnected | None | None occupied by hub |
| hub-20260922T074227 | Right | BenQ LCD, 2560x1440 at 60 Hz | 2 |
| hub-20260922T074252 | Left-back | BenQ LCD, 2560x1440 at 60 Hz | 0 |

Color LCD is present in all three topology reports. Both working IOService
trees add dispext1:dcpdp-device-epic:0 and its DCPDPDeviceProxy. The
baseline lacks that device service. This supports the current dcpext1
controller choice; it does not expose the numeric firmware target sent by
macOS, or prove the Linux crossbar programming is correct.

## DP-IN resources, distinct from the earlier ACIO RC experiments

The device tree supplies translated absolute IODeviceMemory resources:

| Native node | Physical resource | Size | Crossbar |
| --- | --- | --- | --- |
| atc0-dpin0 | 0x701e50000 | 0x4000 | 0x70304c000 |
| atc0-dpin1 | 0x701e58000 | 0x4000 | 0x70304c000 |
| atc2-dpin0 | 0xf01e50000 | 0x4000 | 0xf0304c000 |
| atc2-dpin1 | 0xf01e58000 | 0x4000 | 0xf0304c000 |

All advertise transport-tunneled=1, transport-type=5; transport-index is
0 or 1. The DP switch downstream endpoint is the ATC number; downstream
port is 1 for dpin0, 2 for dpin1. Their IOService driver is
AppleATCDPINAdapterPort, with IODPPortService children. dcpext1 advertises
upstream endpoint 1, port 0, on the same display-crossbar0 parent.

These selected properties and resources are identical across all captures,
including disconnected. They describe topology, not the active selection.

The old src/thunderbolt/apple.c APPLE_CIO_DPIN0_ANALOG=0x4000 and
DPIN1_ANALOG=0x8000 operate within the ACIO RC window, physically
0x701ac4000/0x701ac8000 on ATC0. Native macOS lists those regions under
acio0 separately from the atc0-dpin resources above. Thus the old RC
experiments did not directly examine these named DP-IN register resources.
This does NOT establish that RC analog blocks are unrelated or unnecessary,
nor that mapping/writing the newly identified regions is safe.

Search of current src/thunderbolt/apple.c, existing notes/docs and t602*
Linux DTS sources found no use of 1e50000/1e58000. Current Linux t602* DTS
sources have no dpin nodes. The macOS driver/resource ownership is a concrete
lead for investigating missing host DP-IN initialization, not proof of a
single missing write or a patch ready to load.

## Limits and next investigation

framebuffers.plist and displays.plist are empty on this macOS release.
service-tree.txt has class names and hierarchy but no service properties.
The IODeviceTree and system_profiler reports parse successfully. They do
not contain a register trace, firmware RPC order, trained lane callbacks,
or a safe initialization recipe. macOS 26 also differs from the Linux
firmware ABI 13.5, so runtime behavior cannot simply be assumed identical.

Next useful evidence is the native AppleATCDPINAdapterPort initialization
and its relationship to DCP ACTIVATE, crossbar and ACIO. A future native
collector should retain targeted IOService properties for that class,
AppleT602XATCDPXBAR, AppleT602XDisplayCrossbar and DCPDPDeviceProxy; those
properties may help but still are not guaranteed to reveal register writes.
Do not repeat timing injection or blind analog/clock writes based on this
static topology. No module load, parameter change, MMIO mapping/access,
cable manipulation or reboot was performed for this analysis.

A sanitized resource extract and SHA-256 manifest are in
notes/2026-09-22-macos-topology.json. Raw reports contain hardware IDs and
remain outside Git in /home/oliver/.local/share/j416s-display/macos-captures/.
Original copies remain on the M4 Desktop. The raw reports are deliberately
not committed.
