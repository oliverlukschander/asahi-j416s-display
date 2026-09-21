# 0075 pulse ACIO analog on ACTIVATE

0074 closed: `set_hpd` after `request_display` → `-110`, then 22/24.
0073 order (`set_hpd` before the nub) is the working handshake:
`GET_SUPPORTS_HPD=1`, ACTIVATE, no 22/24, analog `0x1017`.

On ACTIVATE (nub powered, no lpdptxphy), pulse ACIO analog `+0x00`
bit 0. Tunnel-up stays hands-off. Do not write `+0x18`.

Look for `USB4: ACTIVATE pulse ACIO analog`, analog before/after
`+0x00`/`+0x18`, then `SET_LINK_RATE` / 22/24 / DPRX.
