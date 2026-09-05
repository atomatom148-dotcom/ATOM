# V-1A readiness — cadence and window-yield measurements

**From:** Claude, at Owner request
**Date:** 2026-09-05
**Status:** read-only measurement supplied to the freeze author. No repository,
database, Render, or Supabase state was changed.

## Preregistration boundary (unchanged)

No `enc_b`, encompassing coefficient, bootstrap interval, QLIKE value or gate
was computed. No E-2 `|mu|/(kappa*sigma)` statistic or outcome was touched.
Only row counts, session counts, timestamps, and inter-arrival gaps were read.

## Why this was measured

The post-adoption audit correctly established that all 12 cells fail the §11
rule-2 minima at the frozen boundary. It did not measure the **rate** at which
the population grows, so the draft Amendment 2A readiness rule has no timeline
attached to it. These measurements supply that rate.

Two prior claims of mine were wrong and are withdrawn here, with evidence:

1. **"37% of publication proofs are being lost."** False. Volatility
   publication proofs did not exist before 2026-08-26. Every session since is
   at 100%. There is no leak and nothing to fix.
2. **"The evidence outbox is dropping records."** False. `EVIDENCE_OUTBOX_FULL`
   does not appear in `srv-da31tfmk1f9s73dsiud0` logs across 2026-09-03 to
   2026-09-05.

### Table 0 — FAMILY volatility-forecast proof coverage by session

| Session | Forecasts | Proofs | Coverage |
|---|---:|---:|---|
| 2026-08-21 | 2,700 | 0 | 0% |
| 2026-08-24 | 75,502 | 0 | 0% |
| 2026-08-25 | 74,180 | 0 | 0% |
| 2026-08-26 | 53,095 | 53,087 | 100% |
| 2026-08-27 | 77,038 | 77,038 | 100% |
| 2026-08-28 | 50,368 | 50,365 | 100% |
| 2026-08-31 | 72,227 | 72,221 | 100% |
| 2026-09-01 | 2,691 | 2,691 | 100% |
| 2026-09-02 | 2,746 | 2,746 | 100% |
| 2026-09-03 | 2,956 | 2,956 | 100% |
| 2026-09-04 | 2,823 | 2,823 | 100% |

Source: `public.volatility_forecasts` LEFT JOIN
`atom_v9_internal.legacy_evidence_publications` on `record_id = forecast_id`
where `evidence_kind = 'VOLATILITY_FORECAST'`.

**Consequence for the funnel:** the three sessions 2026-08-21/24/25 are
permanently inadmissible — a commit that has already happened cannot be
retroactively observed. This accounts for a large share of the audit's
FAMILY `n_inadmissible` and for its 4–7 session regression spans. It is not a
defect and cannot be repaired.

## Table 1 — FAMILY eligible forecasts and inter-arrival spacing

Eligibility applied: outcome present and non-null, `forecast_volatility_bps > 0`,
publication proof present, `cutoff_at` local time >= 09:30, `target_endpoint`
local time <= 16:00. Gap is the median seconds between consecutive eligible
forecasts within the same (horizon, session).

| Horizon | Session range | Eligible / session | Median gap |
|---|---|---:|---:|
| 1H | 2026-08-26 .. 08-31 | 5,222 – 7,414 | 1.5 – 1.9 s |
| 1H | 2026-09-01 .. 09-04 | **4** | **3,600 s** |
| 30S | 2026-08-26 .. 08-31 | 3,828 – 8,275 | 1.5 – 2.0 s |
| 30S | 2026-09-01 .. 09-04 | **714 – 778** | **30.0 s** |

**Interpretation.** The Family Evidence Cadence freeze (deployed 2026-08-31)
did not throttle evidence; it aligned emission to the horizon length. Each
FAMILY forecaster now emits approximately one forecast per horizon interval,
which is the non-overlap spacing. Usable window yield is therefore nearly
unchanged at 30S (~780 -> ~750 per session) and reduced from 6 to 4 at 1H.
The 25x drop in raw row count is a 0–33% drop in usable windows.

**Under-sampling note.** RTH admits six non-overlapping 1H windows per session;
the cadence produces four, because emission is aligned to the wall clock rather
than to the session open. Closing that gap would raise FAMILY 1H yield by 50%
and cut its readiness from roughly 30 sessions to roughly 20. Doing so requires
an amendment to the Family Evidence Cadence freeze. This is an Owner /
freeze-author decision and is raised, not recommended.

## Table 2 — V9 eligible forecasts and inter-arrival spacing

Eligibility applied: outcome present, `proof_eligible` commit proof present in
`atom_v9_internal.forecast_commit_proofs`, RTH containment as above, sessions
from 2026-08-26.

| Horizon | Session | Eligible | Median gap |
|---|---|---:|---:|
| 30S | 2026-09-01 | 5,318 | 2.0 s |
| 30S | 2026-09-02 | 4,416 | 2.2 s |
| 30S | 2026-09-03 | 8,234 | 1.7 s |
| 30S | 2026-09-04 | 8,715 | 1.8 s |
| 5M | 2026-09-01 | 8,241 | 1.8 s |
| 5M | 2026-09-02 | 5,470 | 2.1 s |
| 5M | 2026-09-03 | 10,749 | 1.6 s |
| 5M | 2026-09-04 | 8,997 | 1.8 s |
| 1H | 2026-09-01 | 7,510 | 1.8 s |
| 1H | 2026-09-02 | 6,847 | 1.9 s |
| 1H | 2026-09-03 | 9,306 | 1.6 s |
| 1H | 2026-09-04 | 7,723 | 1.8 s |

**Interpretation.** The Family Evidence Cadence freeze applies to the Q3 family
path only and did **not** affect V9. V9 continues to emit at ~1.8 s spacing at
every horizon. Its non-overlap yield is therefore capacity-bound, not
supply-bound: approximately 780 windows/session at 30S, 78 at 5M, 6 at 1H.

**This means every V9 zero in the audit funnel is kappa, not evidence.** The
audit's own numbers confirm it: V9 1H reached the kappa stage with 39 rows and
all 39 failed, yielding `n_windows = 0`.

## Methodological caveat

These yield figures are derived from inter-arrival spacing, not from running
the frozen `select_non_overlapping` selector. Where spacing is approximately
equal to the horizon (the post-cadence FAMILY rows) the two coincide by
construction. Where spacing is far below the horizon (all V9 rows, pre-cadence
FAMILY) the greedy selector is capacity-bound and the capacity figure is the
correct bound. **The audit's exact selector counts govern; these are rates, not
replacements.** Please re-derive with the real selector before freezing any
number into an amendment.

## Derived readiness estimates — NOT measured

Estimates only, from the accumulation rates above plus the audit's kappa
findings. They should be recomputed by the readiness rule itself.

| Cell | Binding constraint | Estimated readiness |
|---|---|---|
| V9 30S | MATURE since 2026-09-03; needs 10 post-maturity sessions | ~2 weeks |
| V9 1M | MATURE since 2026-09-03 15:36 ET; same | ~2 weeks |
| FAMILY 30S | 10 regression sessions at ~750 windows/session | ~2 weeks |
| FAMILY 1M | 10 regression sessions | ~2 weeks |
| V9 5M | calibration N_eff 129.6 -> 200 | ~1 month |
| FAMILY 5M, 15M | window accumulation | ~1 month |
| FAMILY 1H | 4 windows/session x (100 + 20 warmup) = 120 | ~30 sessions |
| V9 15M, 30M, 1H | 500 selected pairs then MATURE | ~27 trading days at +15/day (see Correction 1) |

**WITHDRAWN 2026-09-05 — see CORRECTION-1-V9-1H-CALIBRATION-ARITHMETIC.md.**
This section claimed a 6-calibration-pair-per-session cap at 1H and a ~15-week
floor for V9 1H. Both are wrong. The six-per-session RTH cap belongs to
`CellSelector` (`quant/evidence_scorecard.py:175`), which governs V-1A
regression windows. The §7.2 V4C calibration pool uses `select_non_overlapping`
(`quant/v9_v4a_evidence.py:385`), which has no RTH filter and no session reset,
and its measured rate is **+15 selected pairs per full trading day, cumulative**,
standing at 95 at the 2026-09-04 close. The floor is 500 selected pairs
(250 calibration + 250 withheld, both `n >= 250` and `N_eff >= 200` required),
giving **~27 trading days, approximately 2026-10-14**, conditional on tau <= 1.25
in the effective-n estimator. Read Correction 1 for the verified thresholds, the
unmeasured tau assumption, and the cohort-rotation reset risk.

## Implication for the amendment

Draft Amendment 2A requires **every** frozen cell to satisfy all six minima
before `readiness_status` becomes READY. Given the table above, that chains the
first official receipt to V9 1H, which is structurally months away, while four
cells plausibly qualify within two to three weeks.

Recommend the freeze author consider a **tiered boundary**: a first receipt
scoped to the cells that mature, under its own `run_identity`, with later
receipts for the remaining cells under their own boundaries and identities.
This preserves one-official-receipt-per-run-identity, keeps every threshold
prospective and outcome-blind, and returns a real V-1 result this month rather
than after the longest-maturing cell.

If instead the all-cells rule is retained, the Owner should be told plainly
that the first V-1B receipt is roughly a quarter away, and that the V9 1H
withholding arithmetic above is the reason.

## Provenance

All figures from read-only SQL against production project
`afyiydxbjgzaiswnbcyj` on 2026-09-05, and from Render log queries against
`srv-da31tfmk1f9s73dsiud0`. Queries are reproducible from the eligibility
descriptions in each section. No state changed.
