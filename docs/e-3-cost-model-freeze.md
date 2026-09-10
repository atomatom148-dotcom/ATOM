# E-3 read-only executable-cost measurement freeze

**Status:** PROPOSED — documentation-only freeze; read-only implementation authorized only after merge  
**Depends on:** `docs/e-1-evidence-scorecard-freeze.md` merged  
**Consumer:** `docs/e-2-composite-preregistration.md` confirmatory cost line  
**Next gate:** none authorized by E-3

## Decision

**Measure the cost line instead of declaring it — September 2, 2026:** E-1
and the E-2 pilot echo a declared `cost_bps` assumption. The evidence ledger
stores midpoints, not bid and ask, so the assumption cannot be measured from
the ledger. E-3 measures COIN's **quoted** spread from raw historical quotes
through the existing read-only historical quote retrieval seam used by the
H2-D-8 raw Alpaca quote audit, and derives one executable-cost value from it.

Terminology is frozen: bid and ask give the **quoted** spread. **Effective**
and **realized** spread require trade or fill prices relative to the midpoint
and are not measured here. Nothing produced by E-3 may be labelled effective or
realized.

## Scope

- **Input:** raw COIN NBBO quotes for the exact E-2 pilot sessions, retrieved
  read-only through the existing seam. If that seam does not expose bid and
  ask, E-3 stops and reports `SEAM_INSUFFICIENT`; it adds no fetcher.
- **Windows:** regular trading hours only, exactly as E-1 defines RTH.
- **Per quote:** `quoted_spread_bps = 10000 × (ask − bid) / midpoint`, midpoint
  `= (ask + bid) / 2`. Quotes with `bid <= 0`, `ask <= 0`, or `ask < bid` are
  counted as invalid and excluded.

## Frozen statistics

1. Per session and per time-of-day bucket — `09:30–10:00`, `10:00–15:30`,
   `15:30–16:00` America/New_York — report quote count, invalid count, and the
   `50th`, `75th`, and `90th` percentiles of `quoted_spread_bps` using the E-1
   linear-interpolation quantile.
2. Across all pilot sessions: the same percentiles over all valid RTH quotes,
   and the per-session median list.
3. **Executable-cost value:**
   `cost_bps_measured = quoted_spread_p50_all_rth + slippage_bps`, where
   `slippage_bps = 2.0` is a declared constant echoed in the receipt. Crossing
   the full quoted spread once per round trip is the assumption; it is stated as
   such.
4. **Sensitivity (descriptive only):** the same value using the `75th` and
   `90th` percentiles. Only `cost_bps_measured` may be consumed by E-2.

## Frozen boundaries

E-3 is read-only and single-process. It adds no migration, table, role, grant,
index, queue, scheduler, service, endpoint, UI, dependency, or compute change.
It changes no V9 mathematics, family code, synthesis, evidence, outcome, Truth
credit, simulator, SIM-4, broker, account, order, execution, or trading
authority. It writes nothing. It must not run during regular XNYS hours.
Provider requests are bounded to the pilot sessions and use the seam's
existing credentials, pagination, and rate handling without modification.

Implementation is limited to one module and its tests; the statistics are
pure functions over in-memory quotes and are unit-tested with hand-computed
values. The retrieval call is a thin, separately tested seam.

## Receipt and stopping rule

One JSON receipt to standard output with: exact sessions, quote and invalid
counts per session and bucket, every percentile above, `slippage_bps`,
`cost_bps_measured`, the sensitivity values, the seam identity and version,
`evidence_writes=0`, `read_only=true`, and a SHA-256 over the canonical JSON.

E-3 is complete after one receipt over all E-2 pilot sessions is produced
and reviewed. That value, and only that value, may replace the E-2 pilot
assumption for the E-2 confirmatory evaluation.

## What E-3 does not authorize

- No fill simulation, effective or realized spread, market-impact model, or
  latency model.
- No change to E-1 statistics or to the E-2 pilot cost line.
- No SIM-4 cost gate, sizing, or entry-rule change.
- No new market-data source, symbol, or driver.
