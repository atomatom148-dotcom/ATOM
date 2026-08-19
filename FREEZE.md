# ATOM V9 Thin — Architecture Freeze

**Status:** LAW
**Product:** Quant research pipeline only
**Instrument:** COIN

This freeze is short on purpose. If a change needs more surface area, stop and update this file first.

## Permanent laws

1. **Single forecast owner** — Unified Quant only. No second brain.
2. **Exact six horizons** — `30S`, `1M`, `5M`, `15M`, `30M`, `1H`.
3. **Missing ≠ 0** — Missing evidence is never coerced to zero or neutral support.
4. **Commit before horizon** — Exact-six rows are written before horizon maturity.
5. **Honest status** — API/UI never invents READY, probabilities, counts, or COLD_START.
6. **Valid non-trades** — `NO_SETUP`, `UNAVAILABLE`, and `BLOCKED` are healthy outcomes.
7. **No broker path** — No orders, Schwab/account data, execution, or kill-switch trading stack.
8. **Truth credit** — Only from resolved, eligible ledger rows. Activity ≠ learning.
9. **Thin first** — No families UI, Scout/Shadow, Research OS, or SEI/VJE programs until Phase B is stable.
10. **One phase at a time** — Do not scaffold later phases in the same change.

## Allowed pipeline

```
COIN snapshot
  → minimal features
  → Unified Quant
  → exact-six commit
  → resolve when due
  → truthful status JSON
```

## Forbidden until explicit freeze amendment

- Direction Brain or any parallel forecast writer
- Global Lock / V41.7 subsystems
- Broker or live execution
- Invented 50/50 probabilities
- Bulk import of the old 800-file archive
- Research Center / charts as a day-one deliverable
- Merging migration/phase-zero-through-c2 into main

## Win condition (Phase B)

> Snapshot → UQ → exact-six commit → resolve → status tells the truth, every time.
