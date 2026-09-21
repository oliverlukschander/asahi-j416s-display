# 0075 pulse ACIO analog on ACTIVATE

0074 closed: `set_hpd` after `request_display` → `-110`, then 22/24.
0073 order (`set_hpd` before the nub) is the working handshake:
`GET_SUPPORTS_HPD=1`, ACTIVATE, no 22/24, analog `0x1017`.

On ACTIVATE (nub powered, no lpdptxphy), pulse ACIO analog `+0x00`
bit 0. Tunnel-up stays hands-off. Do not write `+0x18`.

Boot: pulse ran. `+0x00` stayed `80000000`. `+0x18` `0x17`→`80000000`
(consumed). `+0x20` stayed 0. No 22/24. DPRX=0.

Closed: analog MMIO on ACTIVATE still bounces. Do not pulse `+0x00`
on ACTIVATE; it only eats `+0x18`.

0076: 0073 handshake with ATC=4 (target `0x9041`), no analog poke,
no `core+0x10`.
