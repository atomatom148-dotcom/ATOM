# E-1 read-only evidence scorecard freeze

**Status:** PROPOSED — documentation-only freeze; read-only implementation authorized only after merge  
**Current runtime:** V9 thin, V4 worker, and SIM-4 worker on `main`; Family Evidence Cadence active since August 31  
**Next gate:** E-2 pre-registered single-hypothesis evaluation (separate amendment, not authorized here)

## Decision

**Evidence scoring before strategy change — September 2, 2026:** ATOM has
roughly two weeks of live COIN evidence and no canonical, reproducible
scorecard over it. Informal read-only queries on September 2 (not evidence; not
receipted) showed every family and the V9 synthesis at coin-flip hit rates
below 15M once midpoint ties are excluded, faint and unproven direction at
15M–1H, and no relationship between forecast magnitude and accuracy. Those
numbers are motivation only. Nothing in them changes V9, and this phase does
not act on them.

E-1 authorizes one read-only, single-process scorecard reader over existing
evidence. It produces a receipt. It changes nothing. Its purpose is to make the
ledger answer "is any cell worth a pre-registered test" with fixed statistics
that cannot be tuned after looking.

## Scope

The reader scores two layers over one explicit set of regular XNYS sessions:

- **FAMILY** — `public.forecasts` joined to `public.forecast_outcomes` on
  `forecast_id`; one cell per `(quant_id, formula_version, symbol, horizon)`.
- **V9** — `public.atom_v9_v4_forecasts` joined to `public.atom_v9_v4_outcomes`
  on `forecast_record_id`, outcomes restricted to
  `target_timing_status = VERIFIED`; one cell per
  `(v3_model_version, symbol, horizon)`. Values are decoded only through the
  existing `deserialize_forecast_record` and `deserialize_outcome_record`
  seams. No new float parser.

Sessions are supplied as explicit UTC dates and echoed in the receipt. The
default is the most recent completed regular sessions, count supplied as an
input. Partial sessions are excluded.

## Frozen statistics

These rules are fixed before any receipt is produced and may not be changed in
E-1.

1. **Independent windows.** Horizon seconds are exactly
   `30S=30, 1M=60, 5M=300, 15M=900, 30M=1800, 1H=3600`. Within a cell, keep only
   the earliest-cutoff forecast per epoch-aligned interval
   `floor(cutoff_epoch / horizon_seconds)`. All other forecasts in that interval
   are discarded from the sample. Overlapping cycles are never counted twice.
2. **Ties and abstentions.** An outcome of exactly `0` bps is a **tie**: counted,
   reported, and excluded from every directional and signed metric. A forecast
   of exactly `0` bps, `NULL`, or non-finite is an **abstention**: counted,
   reported, and excluded. `n_decided` is windows minus ties minus abstentions.
3. **Per-cell metrics** (computed only over decided windows unless stated):
   `n_windows`, `n_ties`, `n_abstain`, `n_decided`, `hit_rate`,
   `z_hit = (hit_rate - 0.5) * sqrt(n_decided) / 0.5`,
   `mean_signed_bps = mean(sign(forecast) * outcome)`,
   `t_signed = mean_signed_bps / (stdev / sqrt(n_decided))`,
   `corr_forecast_outcome` (Pearson),
   `calibration_corr = corr(|forecast|, |outcome|)`, and
   `hit_rate_by_magnitude_quartile` (four within-cell quartiles of |forecast|).
4. **Cost line.** `cost_bps` is a required numeric input echoed in the receipt.
   `cost_adjusted_mean_bps = mean_signed_bps - cost_bps`. E-1 defines no cost
   model; a cost model is a separate phase.
5. **Classification.** Each cell receives exactly one label:
   - `INSUFFICIENT` if `n_decided < 100`;
   - `CANDIDATE` if `n_decided >= 100`, `|z_hit| >= 3.0`, and `t_signed` has the
     same sign as `z_hit`;
   - `NOISE` otherwise.
   The `3.0` threshold is the fixed multiple-comparison guard for the
   approximately 66 family-by-horizon cells; it is not tunable per run. No cell
   may be labeled `EDGE`, `TRADEABLE`, or any positive claim. `CANDIDATE` means
   only "eligible for a pre-registered E-2 test."
6. **No selection after looking.** The reader scores every cell in the layer.
   It has no family, horizon, or date filter other than the session set.

## Frozen boundaries

E-1 is read-only and single-process. It adds no migration, table, role, grant,
index, queue, scheduler, service, endpoint, UI, or compute change. It changes
no V9 mathematics, thresholds, weights, family code, synthesis, evidence,
outcome, Truth credit, simulator behavior, SIM-4 entry rule, broker, account,
order, execution, or trading authority. It adds no dependency beyond the
Python standard library and the already-pinned `psycopg`.

Database access is one explicitly read-only transaction per query with a
statement timeout of at most `60s`, using an existing credential. The reader
must not be run during regular XNYS session hours. Forecast, outcome,
manifest, persistence, receipt, and every other write must remain `0`.
Existing evidence may not be deleted, rewritten, repaired, or backfilled.

Implementation is limited to one module (`quant/evidence_scorecard.py`), one
command-line entry point, and tests. Statistics are pure functions over
in-memory rows and are unit-tested on synthetic data with hand-computed
expected values. The database read is a thin, separately tested seam.

## Receipt and stopping rule

Each run emits one JSON receipt to standard output containing:

- the exact session dates scored, `cost_bps`, and the reader's code version;
- rows read from each of the four tables and the query wall time;
- every cell in both layers with all metrics in "Frozen statistics" and its
  label;
- `forecast_writes=0`, `outcome_writes=0`, `evidence_writes=0`,
  `read_only=true`;
- a SHA-256 over the canonical JSON of everything above.

The receipt is evidence about evidence. It is not itself stored in the ledger
and it authorizes nothing. E-1 is complete after the first receipt over at
least ten regular sessions is produced and reviewed.

## What E-1 does not authorize

- No E-2 hypothesis test. E-2 must freeze, before looking at any further
  data, exactly one hypothesis (family set, combination rule, horizon,
  evaluation sessions, pass/fail thresholds), and the E-1 receipt is its
  baseline.
- No cost model, spread measurement, or slippage assumption beyond the echoed
  `cost_bps` input.
- No SIM-4 tradeability floor, position sizing by magnitude, or entry-rule
  change.
- No new market-data driver, symbol, family, or Parent-Child expansion.
- No retirement, reweighting, or sign-flip of any existing family.
