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
7. **No broker path** — No account balances, positions, order entry, cancellation,
   replacement, execution, or kill-switch trading stack. The read-only Schwab
   market-data exception below grants no broker authority.
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

## Read-only Schwab market-data amendment

Schwab may replace Massive as the sole live NDX source and may provide genuine
COIN `NASDAQ_BOOK` depth through one isolated ATOM-owned market-data gateway.
This exception authorizes only:

- OAuth authorization and token refresh needed for market-data access;
- `/trader/v1/userPreference` solely to obtain streamer connection metadata;
  account fields unavoidably returned in that envelope may cross the transport
  boundary only and must be discarded without parsing or retention;
- read-only NDX quotes and COIN `NASDAQ_BOOK` fields `0,1,2,3`;
- bounded reconnect, freshness, deduplication, health, and causal timestamp checks;
- transient publication under an `atom:v9:schwab:*` namespace.

It does not authorize any account-data request or use, nor any balance,
position, transaction, order, cancel, replace, execution, or broker-control
read or write. Account fields incidentally returned by `userPreference` must
not be parsed, retained, logged, published, or used. Secrets and tokens are
never published with market data.

NDX may enter only the existing independent NDX benchmark/display seam. Schwab
depth is observer-only and cannot enter Q5, any other family, V2/V3/V4,
eligibility, aggregation, forecasts, outcomes, or Truth credit. Q5 remains
`top-book-imbalance-v1`; any Top-3 mathematical successor requires a later,
explicit freeze amendment and a new evidence lineage. Transient market-data
cache entries are not durable evidence and cannot restore or rewrite history.

The first implementation phase is backend-only, disabled by default, and may
add no UI or Render production change. Only after deterministic tests pass may
a separate operational phase prove a live Schwab connection. No deployment or
mathematical promotion is authorized by this amendment.

## Historical replay H2-D-2 amendment

Historical replay may be considered for future concurrency only at the whole
historical-date boundary. Every frame, family calculation, horizon, and stage
inside one date remains strictly chronological and sequential. The controlling
contract is `docs/h2-d2-freeze.md`.

H2-D-2 is a design freeze only. It does not enable a worker pool, queue,
parallel flag, Render deployment, Supabase schema or compute change, replay
write, or evidence mutation. After this freeze is merged, only a separately
approved two-date read-only Parallel Canary may be implemented. Numerical,
lineage, count, duplicate, or receipt-correlation drift stops promotion.
The canary is limited to two ordinary isolated processes, one complete date per
process, finite timeouts, read-only database access, zero evidence writes, and
exact comparison with a sequential control. H2-D-2 pins behavior, numerical
outputs, evidence identities, lineage, counts, receipt correlation, and the
72-metric encoding—not unrelated runtime or V9 source-file hashes.

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
