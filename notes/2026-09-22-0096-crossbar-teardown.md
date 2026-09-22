# 0095 failure and 0096 DPIN0 teardown correction

0095 right-port test, boot bfac7473: Oliver confirms no picture, everything
else working; keyboard not attached, so untested. At377.389s the new
link-config up rate=0xa callback returns0. Four lanes, DPRX_DONE=1 and22
modes follow; 2560x1440 modeset finishes377.831s. USB-3 uses CRTC88 and
eDP remains enabled. Compositor again reports pending page flip / EBUSY.
The added link-config reselect did not fix visible output. No automatic
retest is warranted. Future-boot flags remain disarmed.

Native 13.5 AppleT602XATCDPXBAR teardown, block0xfffffe000938c2fc,
clears the source bit at+0x00c for DPIN0's clock1 path (c618..c624), then
sets read reset+0x024 using the downstream bit (c7bc..c7c4). The experimental
Linux baseline instead clears 1<<(2*source) at+0x00c despite enabling
1<<source, and sets+0x020. For source2 the former clears bit4 instead of2;
the latter enables a different clock gate rather than restoring reset.
Native read/AND helper938a210 and read/OR helper938a260 were independently
decoded. DPIN0 is downstream role1; pclkForConnection returns clock1.

0096 corrects ONLY these two DPIN0 teardown operations. DPIN1 and DPPHY
behavior is preserved. Source+0x00c and read reset+0x024 use matching
single-bit masks. No cleanup write to+0x020 is added: fresh boot is required
to avoid the stale bit left by0095. The current live driver is untouched.

The kernel sparse checkout lacked drivers/mux; expanded it and imported the
existing out-of-tree baseline while committing the correction as67385ab.
Therefore patch0096 includes prior experimental routing changes already
present on this machine. The new delta relative to display/src/mux is only
the two DPIN0 conditionals and explanatory comments; it is not an upstream
ready crossbar driver. appledrm0095 and thunderbolt0094 stay unchanged.

scripts/test-t602x-dpin0.py compiles the actual driver set function with
RAM-backed readl/writel and tests27 select/disconnect cycles across9 source
indices, including preservation of an unrelated clock bit. With ASan/UBSan,
corrected source passes. Old baseline fails the reset invariant. The first
negative control used assert/SIGABRT intentionally; the harness now exits1
instead. No hardware is accessed by this harness.

Crossbar module builds; new delta checkpatch0errors/0warnings, whitespace
clean. Crossbar SHA256:
4bb0096ac4560f2da103148f7147403d43434ace76caa20c83cb704fa784a930
appledrm SHA256:
eb6122ba4ce9a30d357d02deb237545c8f9d943cf6769fe6f2947f98e13346a2
thunderbolt_apple SHA256:
26703573febf2ceb4898b0cbc8faf8ac119fb2974e218b4d6edc90872d0ee198

manage-0096.py backs up SEVEN files: kernel/updates copies of all three
modules plus initramfs, verifies them, installs and verifies candidate hashes,
arms the same bounded options and validates the rebuilt image. Crossbar and
thunderbolt hashes are checked if packaged in the image; current image does
not package crossbar, so verified root module copies are used. Restore covers
all seven files. Helper syntax checked; not run or installed yet.

This is a register-sequence correction supported by offline evidence, not
proof of working video. No additional live MMIO read, write, reload or reboot
has occurred. Hub must be unplugged before installation; log/push each action.
