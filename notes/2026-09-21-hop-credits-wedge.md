# Hop 9 credits write hung NHI and blanked eDP — 2026-09-21 0062

User unplugged the hub; laptop panel went black. After reconnect:

```
DP IN hop 9 credits 0 -> 7 write -110
DP IN hop 9 read failed: -110
1:19 hub DP OUT config space dead ret=-110
```

Do not write DP IN hop registers after the tunnel is up. Credits=0 is
the USB4 video-path default.

0063 removes the credit write.
