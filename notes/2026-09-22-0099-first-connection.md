# 0099 first connection was the hub, not the direct reference

User reports connected, laptop on, no picture. Contrary to the requested
direct reference, both live sysfs and boot journal identify router0-1
as Other World Computing Thunderbolt5 Hub, vendor0x5a/device0xde81;
VMM7100 is USB1-1.2 behind that hub. Typec2 entersUSB4, source2 DPIN0
is selected. Do not infer a direct-DP regression from this connection.

0099 after-frame-dpin0 snapshot succeeds at252.383579s:
000=4,800=0,020=0,820=0,024=0x110,81c=0x110.
Right frame log:usb4=1,result=0. External modeset completes, encoder97
usesCRTC88; eDP3456x2160@120 remains active. No visible signal per user.

The previously logged capture filenames contain right-direct because
that was the intended test, not the observed topology. Private copies
under linux-0099-result use actual-hub names. No direct after-frame
snapshot has run; its separate one-shot latch remains available. Native
USB4 attempt has been consumed: do not reconnect the hub this boot.
