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

1. **Non-overlapping RTH windows.** Horizon seconds are exactly
   `30S=30, 1M=60, 5M=300, 15M=900, 30M=1800, 1H=3600`. Within a cell, keep only
   the earliest-cutoff forecast per epoch-aligned interval
   `floor(cutoff_epoch / horizon_seconds)`; all other forecasts in that interval
   are discarded from the sample. A window is included only when its full
   interval `[cutoff, cutoff + horizon_seconds]` lies inside regular trading
   hours (09:30–16:00 America/New_York) of a scored session. Pre-market and
   after-hours windows are counted and reported as excluded, not scored.
2. **Ties and abstentions.** An outcome of exactly `0` bps is a **tie**. A
   forecast of exactly `0` bps, `NULL`, or non-finite is an **abstention**.
   Both are counted and reported. Abstentions are excluded from every metric.
   Ties are excluded from **directional** metrics (hit rate) because they are
   neither hit nor miss, and are **included as zero** in every **economic**
   metric, because a flat outcome is zero return before cost, not a missing
   observation. `n_decided` is windows minus abstentions minus ties;
   `n_economic` is windows minus abstentions.
3. **Per-cell descriptive metrics.**
   `n_windows`, `n_excluded_non_rth`, `n_ties`, `n_abstain`, `n_decided`,
   `n_economic`, `n_sessions`;
   `hit_rate` (over decided windows) and `z_hit = (hit_rate - 0.5) * sqrt(n_decided) / 0.5`;
   `mean_signed_bps = mean(sign(forecast) * outcome)` over economic windows;
   `mean_cost_adjusted_bps = mean_signed_bps - cost_bps`;
   `corr_forecast_outcome` (Pearson, economic windows);
   `calibration_corr = corr(|forecast|, |outcome|)` and
   `hit_rate_by_magnitude_quartile` (four within-cell quartiles of |forecast|,
   decided windows).
   `z_hit` and any plain-standard-error statistic are descriptive only. They
   are reported but never used for classification, because windows are serially
   dependent even when non-overlapping.
4. **Inference.** The only inferential statistic is a session-clustered
   bootstrap: resample scored sessions with replacement, recompute
   `mean_cost_adjusted_bps` over all economic windows in the resampled
   sessions, repeat exactly `2000` times with a fixed seed of `0`, and report
   the percentile interval at `99.9%` (two-sided) and at `95%`. The same
   procedure reports a `95%` interval for `hit_rate`. Bootstrap parameters are
   fixed in this document and echoed in the receipt.
5. **Cost line.** `cost_bps` is a required numeric input echoed in the receipt.
   It is an executable-cost **assumption** — the declared round-trip cost of
   crossing the quoted spread plus slippage — not a measurement. E-1 defines no
   cost model and measures no spread; bid/ask alone is quoted spread and must
   not be labeled realized or effective spread. A cost model is a separate
   phase.
6. **Classification.** Each cell receives exactly one label:
   - `INSUFFICIENT` if `n_economic < 100` or `n_sessions < 10`;
   - `CANDIDATE` if not insufficient and the `99.9%` session-clustered bootstrap
     interval for `mean_cost_adjusted_bps` lies entirely above `0`;
   - `NOISE` otherwise.
   The `99.9%` interval is the fixed multiple-comparison guard for the
   approximately 66 family-by-horizon cells; it is not tunable per run. No cell
   may be labeled `EDGE`, `TRADEABLE`, or any positive claim. `CANDIDATE` means
   only "eligible for a pre-registered E-2 test." Negative intervals confer no
   label and authorize no sign-flip.
7. **No selection after looking.** The reader scores every cell in the layer.
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
command-line entry point, and tests. Statistics, including the bootstrap, are
pure functions over in-memory rows and are unit-tested on synthetic data with
hand-computed expected values and a fixed seed. The database read is a thin,
separately tested seam.

## Receipt and stopping rule

Each run emits one JSON receipt to standard output containing:

- the exact session dates scored, `cost_bps`, bootstrap parameters, and the
  reader's code version;
- rows read from each of the four tables and the query wall time;
- every cell in both layers with all metrics in "Frozen statistics", both
  bootstrap intervals, and its label;
- `forecast_writes=0`, `outcome_writes=0`, `evidence_writes=0`,
  `read_only=true`;
- a SHA-256 over the canonical JSON of everything above.

The receipt is evidence about evidence. It is not itself stored in the ledger
and it authorizes nothing. E-1 is complete after the first receipt over at
least ten regular sessions is produced and reviewed. That receipt is the
baseline for E-2.

## What E-1 does not authorize

- No E-2 hypothesis test. E-2 must freeze, before any further data is read,
  exactly one hypothesis: family set, equal weights, fixed signs, combination
  rule, horizon, evaluation sessions, primary endpoint, and pass/fail
  thresholds. The first evaluation window is a locked pilot for variance and
  cost estimation, not proof; the confirmatory sample size must be derived
  from the pilot's variance of net signed bps at a stated power, not from a
  binomial approximation.
- No cost model, spread measurement, or slippage assumption beyond the echoed
  `cost_bps` input.
- No SIM-4 tradeability floor, position sizing by magnitude, or entry-rule
  change.
- No new market-data driver, symbol, family, or Parent-Child expansion.
- No retirement, reweighting, or sign-flip of any existing family.
