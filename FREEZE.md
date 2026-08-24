# ATOM V9 Thin — Architecture Freeze

**Status:** LAW
**Product:** Quant research pipeline only
**Instrument:** COIN

This freeze is short on purpose. If a change needs more surface area, stop and update this file first.

## Permanent laws

1. **Single runtime owner** — ATOM Quant only. Twelve fixed-equation quant families are approved components; eligible directional families may write exact-six forecasts to the shared evidence ledger. No second brain.
2. **Exact six horizons** — `30S`, `1M`, `5M`, `15M`, `30M`, `1H`.
3. **Missing ≠ 0** — Missing evidence is never coerced to zero or neutral support.
4. **Commit before horizon** — Exact-six rows are written before horizon maturity.
5. **Honest status** — API/UI never invents READY, probabilities, counts, or COLD_START.
6. **Valid non-trades** — `NO_SETUP`, `UNAVAILABLE`, and `BLOCKED` are healthy outcomes.
7. **No broker path** — No orders, Schwab/account data, execution, or kill-switch trading stack.
8. **Truth credit** — Only from resolved, eligible ledger rows. Activity ≠ learning.
9. **Approved numerical surface** — The 12-family and Phase-E evidence UI may expose computed numbers and eligible resolved truth only. Scout/Shadow, Research OS, and SEI/VJE remain excluded.
10. **One phase at a time** — Do not scaffold later phases in the same change.

## Allowed pipeline

```
COIN snapshot
  → 12 fixed-equation quant families
  → eligible exact-six commits to one evidence ledger
  → resolve when due
  → Phase-E truth metrics
  → truthful numerical UI/status
```

The existing Unified Quant implementation and all historical evidence remain preserved. This amendment changes current authority only; it deletes nothing.

## Paper simulator amendment

The production pipeline and Q1–Q12/V1–V4 ownership remain unchanged. The paper simulator is authorized only as a downstream consumer of completed, immutable V4D output. It has no production, forecasting, broker, or truth-credit authority. `SIMULATION_FREEZE.md` is controlling law for all simulator work. Simulator failure, delay, overload, missing data, or complete unavailability cannot affect production.

## Forbidden until explicit freeze amendment

- Direction Brain or any forecast writer outside the approved 12-family ATOM Quant runtime
- Global Lock / V41.7 subsystems
- Broker or live execution
- Invented 50/50 probabilities
- Bulk import of the old 800-file archive
- Research Center / charts as a day-one deliverable
- Merging migration/phase-zero-through-c2 into main

## Win condition (Phase B)

> Snapshot → approved families → exact-six commit → resolve → status tells the truth, every time.
