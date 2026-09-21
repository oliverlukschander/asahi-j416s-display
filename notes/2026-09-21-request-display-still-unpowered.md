# request_display then 1080p — still fDisplayPowerState=0

request_display 0, nub power, APCALL 18/10/0 ACTIVATE target 0:4
(dptx_phy=4 from USB4 route, no core+0x10 assign). Modeset ~200 ms
later: setmode failed, fSoftPowerState=0, fDisplayPowerState=0,
80000104. Then 22/24 at +5.5 s.

request_display does not enable the dcpext pipe. Firmware still
needs a DPTX sink. lpdptxphy can be that sink and is not DP IN.
