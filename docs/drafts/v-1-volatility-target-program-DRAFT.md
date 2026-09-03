# V-1 — Volatility as Primary Target (DRAFT freeze)

**Draft status:** prepared by Claude at Owner direction ("change from chasing direction to volatility") under 1B delegated drafting; zero authority until adopted and Owner-merged.  
**Phase:** V-1 (read-only volatility scorecard), with the V-2 preregistration outline in §7  
**Change type:** documentation only; the implementation that follows is one read-only reader and receipts  
**Relationship to direction:** the directional lineage keeps running untouched. V-1 changes what the program *scores first*, not what the ledger writes.

---

## 0. Why volatility, in one paragraph

Direction at 30S–5M was measured and is a coin flip; its apparent edges were drift. Volatility is a different kind of quantity: it clusters, it persists, and it is the one thing V9 already calibrates successfully (V4C kappa MATURE at 30S). ATOM has been producing **two** volatility forecasts since day one — Q3's `forecast_volatility_bps` (409k rows with 392k realized outcomes) and V9's calibrated dispersion `κ·√σ²` — and neither has ever been scored against a benchmark. Scoring them is cheap, needs no new data, and answers "can this pipeline find a real signal?" on a target where a real signal is expected to exist.

## 1. Scouting evidence (read-only, 2026-09-03, disclosed for preregistration)

Q3 volatility forecasts vs realized absolute move, regular hours, all sessions pooled, **overlapping** windows (so treat as direction-of-investigation only):

| Horizon | n | corr(forecast, realized) | mean forecast bps | mean realized bps | slope realized-on-forecast |
|---|---|---|---|---|---|
| 30S | 30,215 | 0.344 | 106.1 | 10.2 | 0.055 |
| 1M | 30,737 | 0.335 | 107.8 | 14.5 | 0.070 |
| 5M | 33,628 | 0.357 | 107.4 | 30.0 | 0.142 |
| 15M | 33,409 | 0.441 | 105.9 | 52.1 | 0.305 |
| 30M | 31,203 | 0.405 | 105.5 | 70.4 | 0.355 |
| 1H | 29,217 | 0.283 | 107.6 | 102.2 | 0.327 |

Two findings:

1. **Q3 has rank information at every horizon (0.28–0.44)** — the first quantity in the program with a measurable relationship to what it predicts.
2. **Q3's level is wrong and does not scale with horizon.** It emits ~106–108 bps regardless of horizon, against realized moves from 10 bps (30S) to 102 bps (1H). It is ~10× too large at 30S and roughly right at 1H. The ranking is informative; the number is not. That is exactly the defect a calibration layer fixes — V4C already does this for V9's σ — and it is not a math change to Q3.

A naive persistence baseline (previous window's realized move) correlated at 0.90–0.998 in this pooled query. **That number is an overlap artifact** — consecutive 1H windows share 99.9% of their span — and says nothing about predictability. Any honest benchmark must use non-overlapping windows, which is why V-1 reuses E-1's window selection exactly.

Disclosure: the statistics above (pooled correlation, level ratio, slope) have been examined. **No non-overlapping, session-clustered, benchmark-relative statistic has been examined**, and no V9-layer `κ·√σ²` volatility statistic has been examined. V-2 preregisters against those.

## 2. What V-1 scores

Two forecasters, six horizons, both layers already durable:

- **FAMILY-VOL:** Q3 `forecast_volatility_bps` from `public.volatility_forecasts`, outcome `realized_move_bps = |10⁴·ln(mid_endpoint/mid_cutoff)|` from `public.volatility_forecast_outcomes`, admissible and eligible only through the existing `VOLATILITY_FORECAST` / `VOLATILITY_OUTCOME` publication-proof seam (same timing rules as E-1's FAMILY layer).
- **V9-VOL:** for each admissible V9 forecast, `σ_cal(f) = κ(f)·√(predictive_variance_bps2)` with `κ(f)` the causal V4C kappa (latest state strictly before `cutoff_at`; `UNAVAILABLE` → excluded, counted), outcome `|actual_return_bps|` from the eligible V4 outcome.

Windows, RTH restriction, non-overlap selection by horizon spacing, session counting, abstain/invalid/tie handling, and the 200,000-resample session-clustered bootstrap are **exactly E-1's**. Volatility has no ties; a zero realized move is a valid observation, not a tie.

## 3. Benchmarks (the "drift" of volatility is persistence)

Per horizon, over the same non-overlapping windows in cutoff order (crossing session boundaries):

```text
persist_1(w)   = realized of the previous selected window
persist_20(w)  = mean realized over the previous 20 selected windows   (null for the first 20; those windows are excluded from benchmark-relative metrics)
```

A forecaster earns nothing for merely tracking persistence.

## 4. Frozen per-cell metrics

For each (forecaster, horizon) cell, over windows with all inputs present:

```text
n_windows, n_sessions
rank_corr            = Spearman(forecast, realized)
level_ratio          = median(forecast) / median(realized)
mz_a, mz_b, mz_r2    : realized = a + b·forecast                         (Mincer–Zarnowitz)
enc_b                : realized = a + b·forecast + c·persist_20           (encompassing coefficient on the forecast)
enc_b_ci_0999        : 0.999 session-clustered percentile-bootstrap interval of enc_b
enc_b_ci_095
persist_rank_corr    = Spearman(persist_20, realized)                     (for context only)
```

Descriptive fields are reported for every cell. The only inferential statistic is the encompassing bootstrap.

## 5. Eligibility and classification (mirrors E-1)

Eligible: `n_windows ≥ 100` and `n_sessions ≥ 10`; otherwise `INSUFFICIENT`. Eligible cells: `INFORMATIVE` when `enc_b_ci_0999` lies entirely above 0, else `NOISE`. Budget: 12 cells (2 forecasters × 6 horizons); `expected_false_informative = 0.006`. No label means anything beyond "worth a preregistered V-2 test." No cell may be labeled tradeable.

## 6. Boundaries

Read-only; one process; the E-1 reader pattern. **One migration** on the production project grants `atom_e1_scorecard_reader` `SELECT` on `public.volatility_forecasts` and `public.volatility_forecast_outcomes` and adds the matching permissive full-read `SELECT` policies (the E-1 full-read verification extends to six tables). No new role. No write. No change to Q3, V3, V4C, kappa, thresholds, RANGE, families, evidence, SIM, or trading.

Implementation surface: `quant/volatility_scorecard.py` (new; reuses E-1 window/bootstrap functions unchanged), `tests/test_volatility_scorecard.py` (new), the one migration, one benchmark-worker start command set by the Owner. Receipt: same shape as E-1's, plus the disclosure text from §1 verbatim.

## 7. V-2 outline (preregistration to be finalized as its own document after V-1's receipt)

Hypothesis: "V9-VOL at 5M encompasses persistence on future sessions" — `enc_b > 0` at 0.95 on ≥20 clean sessions collected **after** the V-2 document merges, evaluated once. Secondary: FAMILY-VOL at 15M. Pilot fixes nothing (no free parameters); confirmatory sample = the first 20 clean sessions.

## 8. What a PASS is worth — said plainly

On one share of COIN, a volatility forecast earns nothing by itself. It earns through:

1. **Gating and sizing** — a calibrated σ is the denominator of the E-2 signal-to-noise test and the natural "don't trade now" switch. This is the first consumer and needs only a SIM selection-rule freeze.
2. **Options** — the direct monetization of a volatility edge. Outside every current instrument and broker freeze; would require its own instrument freeze and is not proposed here.
3. **Credibility** — the first demonstrated, benchmark-relative signal in the program, on the target most likely to have one.

FAIL closes volatility as a primary target at that horizon and forecaster, and is preserved.

## 9. Not authorized

No change to Q3's formula or level (the level defect is fixed by calibration downstream, later, under its own freeze if V-1 shows it matters); no promotion, sizing, gating, or trading on this receipt; no options; no new data source; no reweighting of families; no change to the directional lineage.
