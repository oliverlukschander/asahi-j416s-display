# ACIO MMIO scan crash loop — 2026-09-21

Dock connected. `0029` `readl` of the ACIO 16MB window (and extra RC/NHI
pages) ran at DP tunnel post_activate.

Boot 11:52:15 reached `analog/AUX serializer` + `ACIO RC:` then host DP
IN dumps. Later boots 11:57–11:59 lasted 1–3 s and looped until the hub
was unplugged. PMU logged boot errors, no Linux panic (SError/hang).

Do not probe unmapped ACIO MMIO. USB4 adapter CS dumps stay.

Reconnect only after a load **without** the hub, once the laptop
desktop is up.
