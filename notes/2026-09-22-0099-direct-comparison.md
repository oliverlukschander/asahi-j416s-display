# 0099: right direct-USB-C reference snapshot

0098 showed+0x800=0 after external frame completion with no visible signal.
A known-working direct path is needed to test the meaning of that status
on this chip, using the same source and right crossbar.

0099 extends the existing read-only after-frame snapshot to right DPPHY
as well as DPIN0, with separate one-shot flags per path in DCP and provider.
Caller remains gated by native/protocol opt-in, right typec2, dcpext1
index2 and source2. Provider still requires j416s/T602x, exact resource
0xf0304c000, selected source2 under its lock. DPIN1, other sources, other
ports and panel mappings remain excluded. No new register writes, mapping
or physical PHY operations are introduced by this diagnostic. Direct
adapter attachment will use the existing normal DP-alt-mode path, with
no hub attached; it is not forcing a connected USB4 hub into DP mode.

Both modules built; delta checkpatch0 errors/0 warnings, whitespace clean;
existing RAM-only27-cycle crossbar teardown checks pass. New snapshot
guards reviewed; no hardware test performed. Existing exported-prototype
style warning in0098 is unchanged outside this delta.

First test after boot verification/disarm: direct USB-C adapter in RIGHT
port, hub absent. Require Oliver to confirm actual visible picture. Read
its after-frame-dpphy snapshot and compare with0098 before deciding on
any later hub test. Do not infer working video from DRM modes alone.

Installer manages the same seven files with verified backup/restore and
image verification. No live reload; hub absent for install/reboot.

Pinned candidate SHA256:
mux: 228a660c494c5826345a70321c8e4f96e3a564a157836f99fbf71618ebbc7ea1
appledrm: 65ae9be244ba6475ff1d65ae2db069167ebbddd0edaa994bb798753d88173514
thunderbolt_apple: 26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198
