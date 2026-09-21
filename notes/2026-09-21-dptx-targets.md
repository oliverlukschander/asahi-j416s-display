# DPTX remote-port experiments — 2026-09-21

Hub on USB-C Right (`f01f00000.nhi`), tunnel `0:5 <-> 1:19` still torn
down as inactive. Keyboard/USB on the hub work.

Firmware APCALL 22 = DEVICE_NOT_RESPONDING, 24 = DEVICE_NOT_STARTED.
APCALL 20 = INACTIVE_SINK_DETECTED (HDMI analog PHY 3, no HDMI jack).
SET_LINK_RATE 0x0 is teardown, not training.

## Targets tried (core=0 die=0 CONNECTED=0x8000)

| target | meaning | result |
| --- | --- | --- |
| 0x8020 | ATC 2 | 22/24 |
| 0x9020 | ATC 2 + bit12 | 22/24 |
| 0xa020 | ATC 2 + bit13 | 22/24 |
| 0xc020 | ATC 2 + bit14 | 22/24 |
| 0x8120 | ATC 2 + bit8 | 22/24 |
| 0x8021 | ATC 2 + core1 | 22/24 |
| 0x8420 | ATC 2 + bit10 | 22/24 |
| 0x8028 | ATC 2 + bit3 | 22/24 |
| 0x8030 | ATC 3 (HDMI DPTX PHY) | APCALL 20 INACTIVE_SINK |
| 0x8010 | ATC 1 (dcpext1 default) | 22/24 |

`dpin0` and `dpin1` on `f0304c000` (Right) both selected at various
times. Crossbar logs `Switched dpin0 to dispext0,0`. USB4 DPTX on ATC 2
never starts. HDMI PHY 3 starts and sees no sink.

HPD kick after APCALL 20 caused a 300+ INACTIVE_SINK storm. Do not repeat.

## Conclusion

DCP firmware will not train DP on the USB4-occupied ATC. Remote-port bit
stuffing does not change that. Next work is the USB4 **DP IN adapter**
(host `0:5`) and how Apple routes DPTX *digital* onto it — not more ATC
indexes.
