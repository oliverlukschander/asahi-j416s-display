# M4 host preparation and macOS 26 constraint

Oliver confirms an M4 Mac is reachable over Headscale/Tailscale, both Macs
can be physically connected, and the M2 also has macOS 26 installed.

SSH alias m4 works. Host reports macOS 27.0 build 26A428, arm64, Xcode,
Homebrew and Python 3.14.7 (system Python is 3.9.6).

Created an isolated host workspace:
/Users/oliverlukschander/Development/asahi-j416s-tracing

Cloned official m1n1 at 4184923ffb2dff079b384d6a32cc02142aa14572 with its
artwork submodule. Created a venv alongside the clone and installed the
repository requirements (construct 2.10.70, pyserial 3.5); pip check passes.
No global packages, boot configuration or firmware were changed. No tracer
or m1n1 proxy was started, and no serial device was opened.

After cloning, discovered m1n1's AGENTS.md prohibits AI/LLM use. No further
modification or instrumentation of that checkout is planned. The user was
informed of the exact instruction. Reference:
https://github.com/AsahiLinux/m1n1/blob/4184923ffb2dff079b384d6a32cc02142aa14572/AGENTS.md

The official hypervisor guide lists supported macOS guests 13.5 and 14.8.3,
not the user's installed macOS 26. The M4 host OS version is distinct from
the M2 guest compatibility requirement. No attempted boot under a hypervisor
is justified by this setup. Source:
https://asahilinux.org/docs/sw/m1n1-hypervisor/

Prepared scripts/collect-macos-display.sh independently in Oliver's repo.
It uses native macOS ioreg and system_profiler, refuses any machine other
than Mac14,10, creates a fresh private output directory, and writes no system
settings. No sudo or automatic upload. Captures may contain hardware IDs;
retain them locally and review before deciding what belongs in the repository.

This can give device properties and routing topology from working native
macOS 26. It does not capture the initialization sequence or register writes,
and macOS 26 firmware may differ from Linux's firmware ABI 13.5. Do not
present these reports as equivalent to the missing low-level working trace.

Validation: bash syntax checked locally; --help tested on the M4. No actual
collection was run on the M4 or the M2. No reboot, hub manipulation or
USB cable connection was requested/performed in this preparation step.
