# V-1A — Volatility-First Research and Transition Freeze

**Decision ID:** `ATOM-V1A-VOLATILITY-FIRST-FREEZE-1`  
**Status:** PROPOSED CONTROLLING FREEZE — documentation only until Owner merge  
**Program:** ATOM V9  
**Author of record:** ChatGPT Pro  
**Owner authority:** Owner retains final merge, deployment, infrastructure, risk, broker, instrument, order, and capital authority.  
**Implementation owner beneath this freeze:** Codex-class implementation labor under the controlling governance law.  
**Original adoption base:** `main` at `ba702d510a7c9b535c96ab4c8c4325f2920d2eda`.

---

## 1. Objective, authority, and supersession

ATOM changes its primary **research evaluation target** from directional hit rate to future movement magnitude / realized volatility.

The V-1 research question is:

> Does an existing ATOM volatility forecast contain reproducible information about future realized magnitude beyond a frozen volatility-persistence benchmark?

V-1 is **not** an options-pricing, implied-volatility, profitability, trading, or capital-authorization study. A later freeze may compare a surviving volatility model with implied volatility and executable option economics; nothing in V-1 authorizes that work.

Direction remains secondary immutable evidence. Existing directional forecasts, outcomes, receipts, lineage, and evidence are not deleted, rewritten, relabeled, re-scored, or invalidated.

On Owner merge, this document supersedes, for V-1 subject matter only, conflicting metric, causal-kappa, phase, dashboard-source, publication, migration, and V-2 choices in:

- `docs/drafts/v-1-volatility-target-program-DRAFT.md`;
- saved pre-adoption `ATOM_V1_VOLATILITY_FIRST_TRANSITION_FREEZE.md`.

Those sources remain historical/scouting material and carry no controlling authority for V-1 after this merge.

Nothing here supersedes production V9 mathematics, SIM mathematics, broker boundaries, immutable evidence law, E-1 evidence-selection law except the explicit volatility-specific proof-kind overrides below, or ATOM AI-role/governance freezes.

---

## 2. Horizons, forecasters, and multiplicity

V-1 evaluates exactly six horizons independently:

```text
30S
1M
5M
15M
30M
1H
```

No pooling across horizons is permitted.

Exactly two forecasters are evaluated:

1. **FAMILY-VOL** — existing Q3 volatility forecaster.
2. **V9-VOL** — existing V9 predictive variance converted to calibrated dispersion with a causally reconstructed V4C kappa.

The inferential budget is exactly **12 cells = 2 forecasters × 6 horizons**.

No third forecaster, IV benchmark, HAR model, BTC model, Level-II model, event model, market-data source, or production family is silently added to V-1. Such ideas require a separate documentation-first research freeze.

Benchmark strengthening is not the addition of a forecaster. Exactly two additional
comparison benchmarks are authorized, and only these two: `unconditional` (§8.2) and
`seasonal` (§8.3). Both are computed solely from the already-authorized
realized-volatility series of the same cell. Neither is a forecaster, may be
classified, may earn `INFORMATIVE`, may appear on any dashboard, nor introduces a new
data source, instrument, table, credential, or model family. Every other prohibition
in this section is unchanged; in particular no IV, HAR, BTC, Level-II, or event model
enters V-1.

---

## 3. Exact lineage identities and deterministic cell selection

Distinct model/cohort lineages may never be pooled.

### 3.1 FAMILY-VOL identity

The only FAMILY-VOL lineage is:

```text
quant_id        = q3_volatility
formula_version = realized-volatility-v1
symbol          = COIN
horizon         = one canonical horizon
```

A FAMILY-VOL cell identity is exactly:

```text
(quant_id, formula_version, symbol, horizon)
```

For §6.4 `n_input`, the FAMILY-VOL source population is every
`public.volatility_forecasts` row inside the snapshot/as-of boundary with
`quant_id = q3_volatility`, the cell symbol, and the cell horizon, regardless
of `formula_version`. Only `formula_version = realized-volatility-v1` is the
selected lineage. Every source row with another formula version is
`n_unselected_lineage_rows` and cannot affect admissibility, outcomes, or
metrics.

### 3.2 V9-VOL identity

A V9 lineage identity is exactly:

```text
(v3_model_version, symbol, horizon, cohort_id, cohort_hash)
```

with `symbol = COIN` and decoded `evidence_origin = PRODUCTION`.

For each horizon, determine the eligible V9 lineage set inside the frozen official snapshot before scoring outcomes. If that set is nonempty, select exactly one lineage using this outcome-blind rule:

1. maximize the latest admissible forecast `cutoff_at` not later than `evaluation_as_of_at`;
2. tie-break by lexicographically greatest UTF-8 tuple `(v3_model_version, cohort_id, cohort_hash)`;
3. once selected, retain only that exact identity for the cell.

All rows belonging to other V9 lineages are excluded as `n_unselected_lineage_rows`; their outcomes and metric values may not affect selection.

If the eligible set is empty, the V9 cell is still constructed. Its exact reserved lineage identity is:

```text
v3_model_version = "__NO_ADMISSIBLE_V9_LINEAGE__"
symbol           = "COIN"
horizon          = cell horizon
cohort_id        = "__NO_ADMISSIBLE_V9_LINEAGE__"
cohort_hash      = "0000000000000000000000000000000000000000000000000000000000000000"
```

That tuple is a receipt-only sentinel and can never identify a durable V9 row. A durable row using either reserved string together with the reserved hash is a frozen-contract defect. For the sentinel cell, `n_input` is still the §6.4 source-row count; `n_unselected_lineage_rows = 0`; every input row is assigned to `n_inadmissible`; every later §6.4 bucket, `n_sessions`, and every §8/§10.3 population count (including `n_unconditional_unavailable`) are zero. The three evidence-span fields follow the empty behavior in §13.5, all descriptive, coefficient, interval, and loss-summary values are `null`, all three bootstrap counter triplets are zero, and both gates are `UNAVAILABLE`. The cell is `INSUFFICIENT`, not `INVALID`, and emits every failed-minimum reason code required by §11. No outcome is scored for this sentinel cell.

This rule preserves exactly six V9 cells and therefore exactly 12 inferential cells total.

### 3.3 Canonical cell order

Canonical cell order is exactly:

```text
0  FAMILY-VOL 30S
1  FAMILY-VOL 1M
2  FAMILY-VOL 5M
3  FAMILY-VOL 15M
4  FAMILY-VOL 30M
5  FAMILY-VOL 1H
6  V9-VOL    30S
7  V9-VOL    1M
8  V9-VOL    5M
9  V9-VOL    15M
10 V9-VOL    30M
11 V9-VOL    1H
```

---

## 4. Frozen targets

For FAMILY-VOL:

```text
predicted_volatility_bps = forecast_volatility_bps
realized_volatility_bps  = realized_move_bps
```

For V9-VOL:

```text
predicted_volatility_bps = kappa(f) * sqrt(predictive_variance_bps2)
realized_volatility_bps  = abs(actual_return_bps)
```

All required numeric inputs must be finite. Predicted volatility must be strictly positive. An exactly zero realized move is valid evidence.

A finite prediction `<= 0` is excluded and counted in `n_nonpositive_prediction_excluded`, not in a null/non-finite bucket.

---

## 5. V-1A merge identity and deterministic official evaluation population

The V-1B official population is not operator-selected.

### 5.1 Verified V-1A merge identity

After this PR is Owner-merged, V-1B must determine the exact GitHub merge commit that introduced decision `ATOM-V1A-VOLATILITY-FIRST-FREEZE-1` into `main`.

Before any population derivation, V-1B must verify all of the following through repository history available to the execution revision:

- `v1a_merge_sha` is a 40-character lowercase hexadecimal commit reachable from the exact authorized V-1B `main` revision;
- that commit is the Owner-merged main commit for PR #319, not the PR head, a branch-only commit, or a caller-supplied arbitrary SHA;
- that commit contains this contract path with this decision ID;
- the merge commit's committer timestamp is read from that same verified commit object.

Failure to prove this identity before evidence reading is `BLOCKED`. If identity inconsistency is discovered only after evidence evaluation has begun, it is `INVALID` and uses the pre-cell-invalid receipt schema in §14.2 when complete cells cannot truthfully be constructed.

### 5.2 Evaluation session and as-of

Let `T_merge` be the UTC committer timestamp of the verified V-1A merge commit.

Convert `T_merge` to America/New_York. `evaluation_session` is the latest **fully completed regular XNYS session** whose regular close at 16:00 America/New_York is strictly before `T_merge`.

If the merge occurs during a regular session, that in-progress session is excluded. Half-days and non-regular sessions are excluded.

```text
evaluation_as_of_at = regular close of evaluation_session = 16:00:00 America/New_York
```

stored as UTC RFC3339 microseconds.

No operator-selected later or earlier as-of is permitted.

### 5.3 One snapshot

The official scorecard uses one read-only `REPEATABLE READ` transaction/snapshot for all database evidence reads.

A record/proof can enter the official population only when every required durable row and publication proof is present inside that snapshot and its relevant availability timestamp is `<= evaluation_as_of_at`.

Evidence or proof published after `evaluation_as_of_at` is excluded even if its market cutoff refers to an earlier time.

### 5.4 Session set

For each selected cell lineage, candidate session dates are the sorted unique America/New_York dates represented by admissible target forecasts whose target intervals end no later than `evaluation_as_of_at`.

Every qualifying regular XNYS date is included. No operator may manually add, remove, sample, shorten, retry, or choose dates based on outcomes or metrics.

The entire target interval must remain inside 09:30–16:00 America/New_York.

---

## 6. Exact proof seams, non-overlap selection, and mutually exclusive accounting

Reuse E-1 ordering and non-overlap mechanics, but use these **volatility-specific target-row proof seams**.

### 6.1 FAMILY-VOL proof seam

FAMILY-VOL target rows are `public.volatility_forecasts` joined to `public.volatility_forecast_outcomes` by the existing forecast identity.

Admissibility and durable availability use the existing legacy publication-proof reader for these exact proof kinds:

```text
VOLATILITY_FORECAST
VOLATILITY_OUTCOME
```

A directional proof kind may not substitute.

The forecast proof and outcome proof must both exist and satisfy the existing integrity/proof-method rules. For target-row eligibility at the official as-of, required commit-observation timestamps must be `<= evaluation_as_of_at`.

### 6.2 V9-VOL target proof seam

V9-VOL target rows use `public.atom_v9_v4_forecasts` and `public.atom_v9_v4_outcomes` under the existing V4 forecast/outcome proof seam and exact E-1 V9 proof eligibility rules.

Decoded `evidence_origin` must be `PRODUCTION`. No simulator or reconstructed evidence may enter.

### 6.3 Non-overlap

Within each cell and session:

- deterministic ordering = `(session_date, cutoff_at, immutable_record_identity)`;
- apply the existing E-1 horizon-spaced non-overlap selector;
- selection restarts each session;
- six horizons and all selected lineages are independent;
- no imputation.

### 6.4 Ordered mutually exclusive row accounting

`n_input` is counted before lineage filtering. For FAMILY-VOL it is exactly
the §3.1 source population. For V9-VOL it is every
`public.atom_v9_v4_forecasts` row inside the snapshot/as-of boundary with the
cell symbol and horizon, before model/cohort filtering.

Each input row enters exactly one first-applicable bucket in this order:

1. `n_unselected_lineage_rows` — for FAMILY-VOL, a source row does not have
   the exact §3.1 selected identity; for a real selected V9 lineage, a source
   row does not have that exact §3.2 identity; for the §3.2 sentinel cell only,
   this bucket is zero.
2. `n_inadmissible` — selected lineage but proof/admissibility/evidence-origin contract fails; in the §3.2 sentinel cell, every input row is assigned here because no admissible lineage exists.
3. `n_non_rth` — admissible but target interval is not wholly inside a regular XNYS RTH session in the official session set.
4. `n_overlap_excluded` — otherwise eligible but excluded by frozen non-overlap selection.
5. `n_null_or_nonfinite_excluded` — selected window has a required null or non-finite target/prediction input.
6. `n_nonpositive_prediction_excluded` — required inputs are finite but the resulting predicted volatility is `<= 0`.
7. `n_kappa_unavailable` — V9 only: otherwise valid target window but causal kappa is unavailable under §7; FAMILY value is zero.
8. `n_windows` — selected valid volatility windows surviving every preceding bucket.

A row satisfying multiple defects is counted only in the earliest applicable bucket.

The first required reconciliation equation is:

```text
n_input
= n_unselected_lineage_rows
+ n_inadmissible
+ n_non_rth
+ n_overlap_excluded
+ n_null_or_nonfinite_excluded
+ n_nonpositive_prediction_excluded
+ n_kappa_unavailable
+ n_windows
```

Failure of this equation is a protocol defect => `INVALID`.

---

## 7. Complete causal-kappa reconstruction

V-1B must not read the latest/current V4C state to assign historical kappa and must not add a V4C-state privilege merely for kappa.

For each selected V9 target forecast `f`, reconstruct kappa in memory from causally prior V4 forecast/outcome evidence using the existing frozen V4C calibration mathematics unchanged.

### 7.1 Exact identity and causal availability

Only V4 pairs matching `f` exactly may contribute:

```text
v3_model_version = f.v3_model_version
symbol           = f.symbol
horizon          = f.horizon
cohort_id         = f.cohort_id
cohort_hash       = f.cohort_hash
```

Every contributing pair must satisfy all of:

- existing V4 proof/admissibility contract;
- finite required inputs;
- forecast `cutoff_at < f.cutoff_at`;
- durable outcome `target_resolved_at < f.cutoff_at`;
- durable outcome `created_at < f.cutoff_at`;
- required forecast publication/proof-observation timestamp `< f.cutoff_at`;
- required outcome publication/proof-observation timestamp `< f.cutoff_at`.

Equality to `f.cutoff_at` is not prior and is excluded.

A delayed/recovered outcome inserted after `f.cutoff_at` cannot back-enter kappa merely because it carries an earlier target-resolution timestamp.

### 7.2 Governed selection, latest-250 withholding, and calibration end

For the strictly prior governed pairs:

1. apply existing V4C governed-evidence filtering unchanged;
2. apply existing V4C `select_non_overlapping(...)` unchanged;
3. order selected pairs by `(forecast.cutoff_at, forecast_record_id)`;
4. `split = max(0, len(selected) - 250)`;
5. `calibration_pairs = selected[:split]`;
6. `validation_pairs = selected[split:]`; the latest 250 selected pairs are withheld and never enter kappa fitting;
7. if `calibration_pairs` is non-empty, set `calibration_end = calibration_pairs[-1].forecast.cutoff_at`;
8. if `calibration_pairs` is empty, set `calibration_end` to the strict causal boundary immediately before `f.cutoff_at`, represented by the greatest timestamp that is strictly less than `f.cutoff_at` at the implementation's timestamp precision;
9. build existing `CalibrationObservation` values from `calibration_pairs` only;
10. call exactly `calibrate_scale(observations, calibration_end=calibration_end)` using the existing implementation unchanged.

The calibration-end argument may not be replaced by `f.cutoff_at`, `evaluation_as_of_at`, outcome resolution time, or current time.

### 7.3 MATURE-only

`kappa(f)` is usable only when reconstructed `ScaleResult.status == "MATURE"` and `kappa` is finite and strictly positive.

`PROVISIONAL`, `UNAVAILABLE`, null, non-finite, zero, or negative kappa is unavailable and the target window enters `n_kappa_unavailable`.

No fallback kappa, current state, cross-cohort state, neighboring horizon, interpolation, or forward fill is allowed.

---

## 8. Benchmarks and regression population

### 8.1 Persistence

For each cell, `n_windows` selected valid windows are ordered by `(session_date, cutoff_at, immutable_record_identity)` across the official session population.

For valid window `w`:

```text
persist_1(w)  = realized_volatility_bps of the immediately prior selected valid window
persist_20(w) = arithmetic mean realized_volatility_bps of the prior 20 selected valid windows
```

Every constituent realized value used in `persist_20(w)` must have its outcome and required proof durably available no later than `w.cutoff_at`.

The first 20 selected valid windows, and any later valid window lacking 20 causal prior realized magnitudes, are excluded from benchmark-relative inference and counted as `n_persist20_unavailable`.

Rows remaining are the **regression population**.

```text
n_regression_windows  = number of regression-population rows
n_regression_sessions = number of distinct regular XNYS dates represented by those rows
```

Second required reconciliation equation:

```text
n_windows = n_persist20_unavailable + n_regression_windows
```

The inferential minimum applies to the regression population only:

```text
n_regression_windows  >= 100
n_regression_sessions >= 10
```

Pre-persistence `n_windows` and `n_sessions` are descriptive and cannot satisfy the inferential minimum.

### 8.2 Unconditional benchmark — the floor

For each regression-population window `w`, define the causal prior set
`C(w)` as every regression-population window `u` of the same cell that:

1. precedes `w` in the frozen §8.1 order; and
2. has its outcome and every required publication proof durably available no
   later than `w.cutoff_at`.

A preceding row that fails condition 2 is omitted from `C(w)`; it may enter
`C(v)` for a later window `v` only when it is durably available by
`v.cutoff_at`. No unavailable constituent, later availability, or snapshot-only
knowledge may enter a benchmark retroactively.

```text
unconditional(w) = arithmetic mean realized_volatility_bps over C(w)
```

`unconditional(w)` is unavailable when `C(w)` is empty or when its arithmetic
mean is not finite and strictly positive. Thus it is unavailable for the first
regression-population window, may also be unavailable for a later window, and is
unavailable when all causal prior realized magnitudes are zero. Every such row is
counted once in `n_unconditional_unavailable`.

This benchmark uses no conditioning information at all. It is the floor: a
forecaster that does not beat it has demonstrated nothing about variation in
volatility.

### 8.3 Seasonal benchmark — the public-structure floor

`seasonal(w)` is unavailable exactly when `unconditional(w)` is unavailable.
Otherwise:

```text
seasonal(w) = unconditional(w) * diurnal_factor(w)
```

For each `w`, define its seasonal profile set `P(w)` as the members of `C(w)`
whose `session_date` is strictly earlier than `w.session_date` and whose
`realized_volatility_bps` is strictly positive, so its logarithm is finite.
Every member of `P(w)` is therefore both from a strictly earlier session and
durably available with its required proof by `w.cutoff_at`.

`diurnal_factor(w)` is computed exactly as follows:

1. bucket each `u` in `P(w)` by
   `floor(minutes since 09:30 America/New_York at u.cutoff_at / 30)`;
   the §5.4 RTH rule gives buckets `0..12`;
2. bucket `w` using the same expression at `w.cutoff_at`;
3. compute `mean(log(realized_volatility_bps))` per bucket and the overall mean
   across all rows in `P(w)`;
4. set
   `diurnal_factor(w) = exp(bucket_mean(bucket(w)) - overall_mean)` only when
   `P(w)` contains at least three distinct strictly-earlier sessions and
   `w`'s bucket contains at least two observations; otherwise set it to exactly
   `1.0`;
5. use no smoothing, interpolation, parametric shape, later-session data, or row
   absent from `P(w)`.

Exactly-zero realized magnitudes remain evaluated outcomes but are excluded from
profile estimation because their logarithm is non-finite. Any other non-finite
profile intermediate or a non-finite/nonpositive diurnal factor is a protocol
defect and makes the cell `INVALID`; it is not replaced or clipped.

Because every available unconditional value and every valid diurnal factor is
strictly positive, the unconditional and seasonal gate populations are identical.
This benchmark contains only the publicly known intraday volatility U-shape.
Beating persistence but not this is not a finding.

---

## 9. Descriptive metrics

For each cell report:

```text
mae_bps
rank_corr
level_ratio
coverage_90
mz_a
mz_b
mz_r2
persist_rank_corr
unconditional_rank_corr
seasonal_rank_corr
```

Definitions over `n_windows` selected valid windows unless stated otherwise:

```text
mae_bps     = mean(abs(predicted_volatility_bps - realized_volatility_bps))
rank_corr   = Spearman(predicted_volatility_bps, realized_volatility_bps)
level_ratio = median(predicted_volatility_bps) / median(realized_volatility_bps)
coverage_90 = mean(realized_volatility_bps <= 1.6448536269514722 * predicted_volatility_bps)
```

If median realized volatility is zero, `level_ratio = null`.

Mincer–Zarnowitz descriptive regression over selected valid windows:

```text
realized_volatility_bps = mz_a + mz_b * predicted_volatility_bps + error
```

Use exactly the `n_windows` row order from §6.3. Let `n` be the
number of selected valid windows. If `n < 2`, set all three MZ fields to
`null` and do not evaluate a division. Otherwise convert `f_i =
predicted_volatility_bps` and `y_i = realized_volatility_bps` to IEEE-754
binary64 Python `float` values, evaluate in the displayed order, and use
`math.fsum` for every displayed sum:

```text
f_bar = math.fsum(f_i) / n
y_bar = math.fsum(y_i) / n
S_ff  = math.fsum((f_i - f_bar) * (f_i - f_bar))
S_fy  = math.fsum((f_i - f_bar) * (y_i - y_bar))
S_yy  = math.fsum((y_i - y_bar) * (y_i - y_bar))
```

The two-column design `[intercept, f]` is descriptively fit-able if and only
if `n >= 2`, every source/intermediate above is finite, and `S_ff > 0`.
Equality fails. When fit-able, compute exactly:

```text
mz_b = S_fy / S_ff
mz_a = y_bar - (mz_b * f_bar)
SSE  = math.fsum((y_i - (mz_a + (mz_b * f_i))) * (y_i - (mz_a + (mz_b * f_i))))
SST  = S_yy
```

Both coefficients must be finite. If the fit criterion, coefficient finiteness,
or any pre-coefficient arithmetic operation fails, `mz_a = null`, `mz_b =
null`, and `mz_r2 = null`. Otherwise retain the finite coefficients and
compute the ordinary unadjusted coefficient of determination exactly as:

```text
mz_r2 = 1.0 - (SSE / SST)
```

when `SST > 0`, `SSE` is finite, and the result is finite; otherwise only
`mz_r2 = null`. No library least-squares/rank default, alternate tolerance,
or fallback fit is permitted. Any MZ null remains descriptive and does not
itself create `INVALID`.

`persist_rank_corr` is exactly:

```text
Spearman(persist_20, realized_volatility_bps)
```

over **regression-population rows only**.

`unconditional_rank_corr` and `seasonal_rank_corr` are exactly:

```text
Spearman(unconditional, realized_volatility_bps)
Spearman(seasonal, realized_volatility_bps)
```

over regression-population rows where that benchmark is defined.

Each benchmark's own rank correlation is reported alongside the candidate's so that a
comparison against a benchmark carrying no information of its own is visible in the
receipt rather than inferred.

### 9.1 Exact Spearman behavior

For `rank_corr`, `persist_rank_corr`, `unconditional_rank_corr`, and `seasonal_rank_corr`:

1. use only the frozen paired finite observations for the stated population;
2. sort values ascending;
3. ties receive arithmetic mean of their one-based rank positions (midrank);
4. calculate ordinary Pearson correlation of rank vectors using binary64 arithmetic;
5. if fewer than two pairs exist or either rank vector has zero variance, return JSON `null`;
6. no jitter, random tie break, epsilon, imputation, or alternate ranking method.

Descriptive metrics never independently create `INFORMATIVE`.

---

## 10. Sole inferential model and deterministic bootstrap

The only V-1 classification statistic is `enc_b` in the regression-population OLS:

```text
realized_volatility_bps
    = intercept
    + persistence_coefficient * persist_20
    + enc_b * predicted_volatility_bps
    + error
```

Every full-sample and bootstrap fit of this §10 encompassing OLS model uses the following sole binary64 algorithm. Let `p_i = persist_20`, `f_i = predicted_volatility_bps`, and `y_i = realized_volatility_bps`. Full-sample row instances are in §6.3 deterministic order. A resample orders row instances by the drawn-session sequence and then by §6.3 order within each occurrence of that session. Convert every scalar to an IEEE-754 binary64 Python `float`; evaluate the displayed operations in the displayed order; and use `math.fsum` for every displayed sum:

```text
n     = number of row instances
p_bar = math.fsum(p_i) / n
f_bar = math.fsum(f_i) / n
y_bar = math.fsum(y_i) / n

S_pp = math.fsum((p_i - p_bar) * (p_i - p_bar))
S_ff = math.fsum((f_i - f_bar) * (f_i - f_bar))
S_pf = math.fsum((p_i - p_bar) * (f_i - f_bar))
S_py = math.fsum((p_i - p_bar) * (y_i - y_bar))
S_fy = math.fsum((f_i - f_bar) * (y_i - y_bar))

Q = S_pp * S_ff
D = Q - (S_pf * S_pf)
```

The three-column design `[intercept, p, f]` is numerically full rank if and only if every source and intermediate value above is finite, `S_pp > 0`, `S_ff > 0`, `Q > 0`, and:

```text
D > (2.0 ** -40) * Q
```

Equality fails the criterion. For a full-rank design, compute exactly:

```text
persistence_coefficient = ((S_py * S_ff) - (S_fy * S_pf)) / D
enc_b                   = ((S_fy * S_pp) - (S_py * S_pf)) / D
intercept               = y_bar - (persistence_coefficient * p_bar) - (enc_b * f_bar)
```

All three coefficients must be finite. A non-finite source, intermediate, coefficient, or arithmetic exception is a non-finite fit. If every value is finite but any rank inequality fails, the fit is rank-deficient. No library rank default, least-squares driver, QR/SVD tolerance, standardization, ridge, pseudoinverse, fallback fit, or algebraic reassociation may replace this algorithm. The same rules determine full-sample validity and whether each bootstrap draw is valid.

### 10.1 Exact session-resampling operation

For each eligible cell:

- canonical `sessions = sorted(unique regression session dates as YYYY-MM-DD strings)` ascending;
- instantiate one `rng = random.Random(0)` once per cell;
- for every bootstrap attempt execute exactly:

```python
drawn_sessions = rng.choices(sessions, k=len(sessions))
```

- for each drawn session identity, duplicate all regression-population rows from that session once for each occurrence in `drawn_sessions`;
- refit the exact OLS model;
- a draw is valid only when the resampled design is full column rank and the fitted `enc_b` is finite.

Invalid attempts consume the RNG state from that exact `choices(...)` call and are counted; they are not rewound.

The implementation must obtain exactly:

```text
bootstrap_valid_draws = 200000
```

with hard cap:

```text
bootstrap_attempted_draws = 1000000
```

If one million attempts are reached before 200,000 valid draws, the cell is `INVALID` and no partial interval is emitted.

```text
bootstrap_invalid_draws = bootstrap_attempted_draws - bootstrap_valid_draws
```

### 10.2 Exact percentile order statistics

After exactly 200,000 valid `enc_b` values exist, sort those 200,000 values **ascending**.

For interval level `L`, `B = 200000`:

```text
lower_index = floor((1 - L) / 2 * (B - 1))
upper_index = ceil((1 + L) / 2 * (B - 1))
```

Use levels exactly `0.999` and `0.95`.

The interval endpoints are direct zero-based selections of the sorted values at those integer indices. No interpolation, quantile library default, standard error, t-test, robust covariance, ridge, pseudoinverse fallback, or alternative bootstrap is permitted.

### 10.3 Mandatory benchmark-loss gates

For a strictly positive forecast `f` and realized magnitude `r >= 0`, the frozen
loss is exactly:

```text
QLIKE(r, f) = log(f^2) + (r^2 / f^2)
```

evaluated with `f = predicted_volatility_bps` or the benchmark value, and
`r = realized_volatility_bps`. This form is finite at `r = 0`, which §4
declares valid evidence, and ranks forecasts identically to the standard QLIKE,
from which it differs only by a term independent of `f`. Lower is better. No
alternative loss, clipping, or epsilon floor may be substituted.

For each benchmark `b` in exactly `{unconditional, seasonal}`, its gate
population `G_b` is the regression-population rows where `b(w)` is available.
By §§4 and 8, both the benchmark and prediction are finite and strictly positive
on every such row. The two gate populations are identical by §8.3.

Report:

```text
n_unconditional_gate_windows  = number of rows in G_unconditional
n_unconditional_gate_sessions = number of distinct session dates in G_unconditional
n_seasonal_gate_windows       = number of rows in G_seasonal
n_seasonal_gate_sessions      = number of distinct session dates in G_seasonal
```

with exact reconciliation:

```text
n_regression_windows
= n_unconditional_unavailable + n_unconditional_gate_windows

n_unconditional_gate_windows  = n_seasonal_gate_windows
n_unconditional_gate_sessions = n_seasonal_gate_sessions
```

Each gate's actual population must independently satisfy:

```text
n_<benchmark>_gate_windows  >= 100
n_<benchmark>_gate_sessions >= 10
```

For each row in `G_b`:

```text
candidate_loss(w) = QLIKE(realized(w), predicted(w))
benchmark_loss_b(w) = QLIKE(realized(w), b(w))
d_b(w) = benchmark_loss_b(w) - candidate_loss(w)
```

`d_b > 0` means the candidate loses less than the benchmark. The singular
receipt summaries are arithmetic means over the common gate population:

```text
qlike_candidate     = mean(candidate_loss)
qlike_unconditional = mean(benchmark_loss_unconditional)
qlike_seasonal      = mean(benchmark_loss_seasonal)
d_unconditional     = mean(d_unconditional(w))
d_seasonal          = mean(d_seasonal(w))
```

For every nonempty gate population and every nonempty resampled gate draw,
`mean(values)` in this section means exactly:

```text
math.fsum(values in the frozen §6.3/drawn-instance order) / len(values)
```

All values and the division use IEEE-754 binary64 Python `float` arithmetic.
This rule governs all five displayed receipt summaries and every bootstrap
`mean(d_b)`; built-in `sum`, `statistics.fmean`, NumPy reductions, and
every other aggregation are forbidden. All five summaries are `null` when
the common gate population is empty. No sum, median, differently filtered
population, or alternate aggregate is permitted.

When §11 permits gate inference, bootstrap `mean(d_b)` from that gate's
population only. For each benchmark `b`, define:

```text
sessions_b = sorted(unique session dates in G_b as YYYY-MM-DD strings)
rng = random.Random(0)
drawn_sessions_b = rng.choices(sessions_b, k=len(sessions_b))
```

Instantiate the RNG once per `(cell, benchmark)`. On every attempt, execute
that exact `choices(...)` call, then duplicate only the `d_b` rows in
`G_b` for each occurrence of their session in `drawn_sessions_b`, in draw
order and §6.3 order within each session occurrence. No regression-population
row outside `G_b` enters a gate draw. Apply the §10.2 order statistics to the
resulting gate-draw means. Exactly 200,000 valid draws are required with a
1,000,000-attempt cap. A draw is valid only when its resampled `mean(d_b)` is
finite. Invalid attempts consume RNG state and are not rewound.

Each benchmark reports its own exact counters:

```text
<benchmark>_bootstrap_attempted_draws
<benchmark>_bootstrap_valid_draws
<benchmark>_bootstrap_invalid_draws
```

where `benchmark` is `unconditional` or `seasonal`, and:

```text
<benchmark>_bootstrap_invalid_draws
= <benchmark>_bootstrap_attempted_draws
- <benchmark>_bootstrap_valid_draws
```

Exhausting the cap without 200,000 valid draws makes the cell `INVALID`.

Each gate status is exactly one of `PASS`, `FAIL`, `UNAVAILABLE`, or
`NOT_RUN`:

- `PASS` only when a completed 0.999 interval has lower endpoint strictly
  greater than zero;
- `FAIL` when a completed 0.999 interval has lower endpoint less than or equal
  to zero;
- `UNAVAILABLE` only when its gate population has zero rows; and
- `NOT_RUN` when its population is nonempty but §11 skips inference, a valid
  interval is not completed, or §13.5 suppresses an INVALID cell's analytic
  result.

`UNAVAILABLE` and `NOT_RUN` are not `PASS`.

---

## 11. Cell eligibility, classification, and precedence

Before applying the precedence below, a conforming implementation completes
all cell-level rule-1 validation and the §17 preinspection check. Those checks
are a mandatory pre-inference checkpoint; no descriptive metric, full-sample
fit, or bootstrap begins first.

Classification and inference precedence is exactly:

1. protocol, identity, causality, proof, accounting-reconciliation, or
   frozen-contract defect => `INVALID` regardless of sample size;
2. otherwise if the regression population or either actual gate population
   fails its own 100-window or 10-session minimum => `INSUFFICIENT`, with no
   bootstrap;
3. otherwise if full-sample OLS is rank-deficient or non-finite => `INVALID`;
4. otherwise run the inferential bootstraps in this exact order:
   `enc_b`, `unconditional`, `seasonal`; if any required bootstrap fails
   its valid-draw requirement, the cell is `INVALID` and every later bootstrap
   is not run;
5. otherwise if all three conditions hold => `INFORMATIVE`:
   a. lower endpoint of `enc_b_ci_0999` is strictly greater than zero;
   b. the unconditional gate is `PASS`;
   c. the seasonal gate is `PASS`;
6. otherwise => `NOISE`.

For `INSUFFICIENT`, all three bootstrap counter triplets are zero. A gate with
zero population is `UNAVAILABLE`; a gate with a nonzero population is
`NOT_RUN`. Every `INVALID` cell serializes analytic values, gate statuses,
and bootstrap counters by the sole §13.5 matrix; no provisional `PASS`,
`FAIL`, coefficient, interval, or metric is optionally retained.

The evaluated-cell `reason_codes` namespace is closed. The array is sorted
unique in ascending UTF-8 order, contains no free text or implementation-specific
strings, and is derived solely from the final classification as follows:

- `INFORMATIVE`: exactly `[]`.
- `NOISE`: include every and only applicable code:
  - `ENC_B_NOT_POSITIVE` iff the lower endpoint of `enc_b_ci_0999` is less
    than or equal to zero;
  - `FAILED_UNCONDITIONAL_GATE` iff `gate_unconditional == FAIL`;
  - `FAILED_SEASONAL_GATE` iff `gate_seasonal == FAIL`.
- `INSUFFICIENT`: include each code whose stated inequality is true:
  - `INSUFFICIENT_REGRESSION_WINDOWS` iff `n_regression_windows < 100`;
  - `INSUFFICIENT_REGRESSION_SESSIONS` iff `n_regression_sessions < 10`;
  - `INSUFFICIENT_UNCONDITIONAL_GATE_WINDOWS` iff
    `n_unconditional_gate_windows < 100`;
  - `INSUFFICIENT_UNCONDITIONAL_GATE_SESSIONS` iff
    `n_unconditional_gate_sessions < 10`;
  - `INSUFFICIENT_SEASONAL_GATE_WINDOWS` iff
    `n_seasonal_gate_windows < 100`;
  - `INSUFFICIENT_SEASONAL_GATE_SESSIONS` iff
    `n_seasonal_gate_sessions < 10`.
- `INVALID`: include every and only applicable code from this list:
  - `CELL_PROTOCOL_DEFECT` iff §11 rule 1 applies, except for the specific
    §17 preinspection condition below;
  - `FULL_SAMPLE_OLS_RANK_DEFICIENT` iff rule 3 has only finite values but
    fails at least one of the positive/rank inequalities in §10;
  - `FULL_SAMPLE_OLS_NONFINITE` iff rule 3 encounters a non-finite source,
    intermediate, coefficient, or arithmetic exception under §10;
  - `ENC_B_BOOTSTRAP_EXHAUSTED` iff the `enc_b` bootstrap reaches its cap
    before 200,000 valid draws;
  - `UNCONDITIONAL_GATE_BOOTSTRAP_EXHAUSTED` iff that gate reaches its cap
    before 200,000 valid draws;
  - `SEASONAL_GATE_BOOTSTRAP_EXHAUSTED` iff that gate reaches its cap before
    200,000 valid draws;
  - `PREINSPECTED_CONFIRMATORY_STATISTIC` iff §17 invalidates the cell.

A condition not reached because an earlier precedence rule stopped evaluation
does not emit a code. Multiple established conditions emit multiple codes; no
first-failure reason-code precedence is used. An unavailable or not-run gate is
classified earlier and never maps to a `NOISE` reason code.

There are exactly 12 inferential cells. Under the nominal one-sided screen
induced by a two-sided 0.999 interval, the report-only nominal expectation is:

```text
12 * 0.0005 = 0.006 nominal expected false INFORMATIVE cells
```

Conjoining the two gates makes `INFORMATIVE` a subset of the original
`enc_b` rejection event and therefore cannot increase that nominal screen
count. The value `0.006` is not asserted as a proven finite-sample
false-positive bound; actual percentile-bootstrap coverage may differ from its
nominal level.

No alternate multiplicity correction may be substituted after results are seen.

No V-1 result may be called tradeable, profitable, production-ready, an options
edge, or sufficient to authorize capital.

---

## 12. V-1B exact implementation boundary

Owner merge of V-1A authorizes **V-1B only**.

V-1B job identity:

```text
ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1
```

### 12.1 Exhaustive file list

Only these unconditional repository files are authorized:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
```

Only this conditional third path is authorized:

```text
migrations/033_authorize_v1_volatility_scorecard_reader.sql
```

and only when the pre-implementation privilege check proves the existing reader lacks the exact volatility-table access required in §15.

No modification is authorized to `quant/evidence_scorecard.py`, `quant/v9_v4c_predictive.py`, `quant/evidence_outbox.py`, `quant/web.py`, `AGENTS.md`, `PHASES.md`, `FREEZE.md`, `SIMULATION_FREEZE.md`, or any other path.

The new V-1B module is explicitly authorized to perform the pure in-memory session-resampled OLS-refit loop frozen in §10. It must import/reuse existing E-1/V4C primitives without editing their source files.

If any unlisted path is required, stop `BLOCKED` for documentation-first amendment.

If migration path `033` is no longer collision-free at V-1B implementation time, do not silently renumber; stop `BLOCKED` for an amendment naming the replacement path.

### 12.2 Required tests

At minimum tests must prove:

- canonical six horizons and 12-cell order;
- exact FAMILY and V9 lineage identities and no pooling;
- nonselected FAMILY formula versions enter
  `n_unselected_lineage_rows` and reconcile without affecting the cell;
- deterministic V9 lineage selection is outcome-blind;
- the zero-admissible-V9-lineage sentinel, accounting, run identity, null fields,
  gate statuses, classification, and exact failed-minimum reason codes;
- V-1A merge identity validation and evaluation-session/as-of derivation;
- exact volatility-specific proof kinds and V4 target proof seam;
- E-1 non-overlap parity;
- mutually exclusive accounting order and both reconciliation equations;
- zero realized magnitude valid;
- null/non-finite and finite-nonpositive prediction buckets distinct;
- strict causal kappa requires cutoff, target-resolved, outcome-created, and proof-observation times all prior;
- latest-250 withholding;
- exact `calibration_end` boundary and equivalence to existing V4C calibration behavior;
- MATURE-only kappa acceptance;
- exact causal `persist_20`;
- actual regression-population minima;
- exact MAE/rank/level/coverage/MZ/persistence metrics;
- exact binary64 MZ fit coefficients, rank/null rule, SSE, and `mz_r2`
  behavior;
- exact Spearman ties/null behavior;
- bootstrap exact `random.Random(0).choices(...)` call and canonical session order;
- invalid bootstrap draws consume RNG state and exactly 200,000 valid refits are required;
- ascending order-statistic interval extraction;
- pure persistence cannot become INFORMATIVE merely by descriptive metrics;
- constructed incremental signal positive path;
- the exact §10 binary64 OLS coefficients and finite/rank decisions, including
  fixtures strictly below, exactly equal to, and strictly above the frozen
  determinant threshold;
- constant `predicted_volatility_bps` and constant `persist_20` each fail the
  frozen rank criterion and classify `INVALID`;
- full-sample rank defect => INVALID;
- exact evaluated, BLOCKED, pre-cell-INVALID, and
  post-evaluation-authority-INVALID schemas and canonical hashes;
- effective DSN target/login verification, including rejection of duplicate or
  ambient target/login parameters and every startup `options` value;
- exact six-table read/RLS/no-write authority proof including restrictive policies;
- execution revision and V-1A merge revision binding;
- rollback deployment target derivation from the V-1B merge's exact first
  parent, with intervening main commits preserved;
- no writes, SIM, broker, order, production-math, V-1C, or V-2 behavior;
- unconditional benchmark uses only causally prior regression-population realized
  values and is null for the first such window;
- diurnal factor uses only strictly-earlier sessions, returns exactly `1.0` below the
  three-session / two-observation minimum, and excludes zero-magnitude windows from
  estimation only;
- `QLIKE` is finite when the realized magnitude is exactly zero;
- a constructed full-column-rank fixture with varying `persist_20` and a
  nonconstant candidate has lower point QLIKE than `persist_1` and
  `persist_20` but does not beat `unconditional`; its completed
  unconditional gate is `FAIL`, so the cell is `NOISE`, never
  `INFORMATIVE`;
- constructed heteroskedastic evidence carrying genuine incremental information
  satisfies all three §11 conditions;
- each gate bootstrap derives its session list from that gate's `G_b`, samples
  and duplicates only that gate's rows, uses the §10.2 indices, and has one RNG
  per `(cell, benchmark)`;
- causal benchmark sets exclude rows whose outcomes or proofs were not durable by
  the evaluated window's `cutoff_at`, including delayed earlier-session rows;
- later unconditional unavailability, all-zero causal history, and exact
  unconditional/seasonal gate-population reconciliation;
- seasonal bucketing uses each row's exact `cutoff_at`;
- all four rank correlations use the exact §9.1 Spearman behavior;
- gate-specific 100-window/10-session minima and separate attempted/valid/invalid
  draw counters;
- exact `math.fsum(...)/len(...)` aggregation and populations for every
  `qlike_*`, `d_*`, and resampled gate-draw mean;
- `UNAVAILABLE` and `NOT_RUN` status behavior for skipped or incomplete gate
  inference;
- exact closed cell and overall evaluated reason-code derivation for every
  `INFORMATIVE`, `NOISE`, `INSUFFICIENT`, `INVALID`, `PASS`, and
  `FAIL` status, including multiple simultaneously applicable codes;
- the complete §13.5 INVALID serialization matrix for every INVALID cause,
  including null fields, gate states, and each bootstrap-exhaustion frontier;
- `session_dates` and evidence cutoff extrema derive only from `n_windows`,
  including exact empty behavior;
- runtime rejection of every transaction isolation level other than
  `repeatable read`;
- pre-read and pre-receipt rejection when `session_user` differs from the
  reader, any reader membership exists, or any frozen reader role attribute
  differs, including `rolsuper` or `rolbypassrls`;
- pre-read and pre-receipt rejection when the reader owns the database or has
  effective database `CREATE` or `TEMPORARY` privilege, including through
  `PUBLIC` or implicit `pg_database_owner` authority;
- pre-read and pre-receipt verification of `atom_v9_internal` USAGE and
  EXECUTE on exactly both proof-reader functions;
- deterministic routing of a failed final authority recheck to the exact
  post-evaluation authority-invalid receipt, never the passing evaluated schema;
- if migration is present, migration self-refusal and exact privilege proof.

---

## 13. Exact evaluated receipt schema

A successfully evaluated V-1B run produces one top-level JSON object with **exactly** these keys:

```text
schema_version
decision_id
job_id
contract_path
code_version
verified_main_sha
v1a_merge_sha
run_identity
evaluation_session
evaluation_as_of_at
generated_at_utc
reader_identity
database_identity
authority_proof
bootstrap
cells
overall_status
overall_reason_codes
scouting_disclosure
read_only
forecast_writes
outcome_writes
evidence_writes
receipt_sha256
```

### 13.1 Top-level types/domains

```text
schema_version      string = "ATOM-V1B-RECEIPT-1"
decision_id         string = "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1"
job_id              string = "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1"
contract_path       string = "docs/v-1a-volatility-first-freeze.md"
code_version        string = "ATOM-V1B-1"
verified_main_sha   string, exactly 40 lowercase hex, bound by §16
v1a_merge_sha       string, exactly 40 lowercase hex, verified by §5.1
run_identity        string, exactly 64 lowercase hex
evaluation_session  string YYYY-MM-DD
evaluation_as_of_at string UTC RFC3339 microseconds `YYYY-MM-DDTHH:MM:SS.ffffffZ`
generated_at_utc    string same timestamp format
reader_identity     string = "atom_e1_scorecard_reader"
overall_status      string = PASS | FAIL | INVALID
overall_reason_codes array[string], sorted unique UTF-8 ascending
scouting_disclosure array[string], exact §17 lines in listed order
read_only           boolean = true
forecast_writes     integer = 0
outcome_writes      integer = 0
evidence_writes     integer = 0
receipt_sha256      string, exactly 64 lowercase hex
```

`BLOCKED` is not a valid status in this evaluated schema; pre-evaluation blocked failures use §14.1.

### 13.2 `database_identity` exact object

Exactly two keys:

```text
supabase_project_ref string = "afyiydxbjgzaiswnbcyj"
database_name        string = "postgres"
```

No extra keys.

### 13.3 `authority_proof` exact object

Exactly these keys:

```text
current_user                         string = "atom_e1_scorecard_reader"
session_user                         string = "atom_e1_scorecard_reader"
dsn_login_user                       string, exact conditional value below
dsn_identity_overrides_absent        boolean = true
current_database                     string = "postgres"
database_owner                       string != "atom_e1_scorecard_reader"
database_create                      boolean = false
database_temporary                   boolean = false
effective_host                       string
project_binding_verified             boolean = true
schema_public_usage                  boolean = true
schema_public_create                 boolean = false
schema_atom_v9_internal_usage        boolean = true
proof_functions_execute              object[string function signature -> boolean true]
reader_role_attributes               object exact shape below
reader_role_memberships               array[string] = []
six_tables_select                    object[string table -> boolean true]
six_tables_insert                    object[string table -> boolean false]
six_tables_update                    object[string table -> boolean false]
six_tables_delete                    object[string table -> boolean false]
six_tables_truncate                  object[string table -> boolean false]
six_tables_rls_enabled               object[string table -> boolean]
six_tables_permissive_full_read      object[string table -> boolean true]
six_tables_restrictive_select        object[string table -> boolean false]
transaction_isolation                string = "repeatable read"
read_only_transaction                boolean = true
verification_status                  string = "PASS"
```

Each six-table object contains exactly these six keys in semantic set terms (canonical JSON later sorts object keys):

```text
public.forecasts
public.forecast_outcomes
public.atom_v9_v4_forecasts
public.atom_v9_v4_outcomes
public.volatility_forecasts
public.volatility_forecast_outcomes
```

No extra table keys.

`proof_functions_execute` contains exactly these two keys, both `true`:

```text
atom_v9_internal.read_forecast_commit_proof(text)
atom_v9_internal.read_legacy_evidence_publications_for_records(text,timestamptz,bigint[])
```

No extra function keys. These two object keys are the frozen literal strings
above; the implementation must not derive their receipt spelling from
`regprocedure::text` or any catalog-rendered alias.

`reader_role_attributes` contains exactly:

```text
rolcanlogin     boolean = true
rolinherit      boolean = false
rolsuper        boolean = false
rolcreatedb     boolean = false
rolcreaterole   boolean = false
rolreplication  boolean = false
rolbypassrls    boolean = false
```

No extra role-attribute keys.

`dsn_login_user` is the normalized, percent-decoded username from the
credential itself, before any connection is attempted. Its only permitted
values are:

- direct host: exactly `atom_e1_scorecard_reader`;
- approved Supavisor host: exactly
  `atom_e1_scorecard_reader.afyiydxbjgzaiswnbcyj`, following Supavisor's
  `[DB-USER].[PROJECT-REF]` convention.

It is derived from the credential, never from the mutable PostgreSQL
`current_user` or `session_user`. `dsn_identity_overrides_absent` is
`true` only when every prohibition in §15.1 has passed.

`database_owner` is exactly the single value returned by
`SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_catalog.pg_database WHERE
datname = current_database()`. It must not equal the reader.
`database_create` and
`database_temporary` are the effective
`pg_catalog.has_database_privilege(current_user,current_database(),...)`
results, including privileges inherited from `PUBLIC` and implicit
`pg_database_owner`; both must be `false`.

`reader_role_memberships` is exactly the ascending UTF-8 list of role names
from every `pg_catalog.pg_auth_members` row whose `member` is the OID of
`atom_e1_scorecard_reader`. The only passing value is `[]`; any direct
membership is a pre-read authority failure, regardless of `inherit_option`,
`set_option`, or `admin_option`.

### 13.4 `bootstrap` exact object

Exactly:

```text
resamples_required integer = 200000
max_attempts       integer = 1000000
seed               integer = 0
interval_levels    array[number] = [0.999, 0.95]
cluster            string = "XNYS_SESSION_DATE"
sampling_operation string = "random.Random(0).choices(sessions,k=len(sessions))"
loss_function      string = "QLIKE(r,f)=log(f^2)+r^2/f^2"
gates              array[string] = ["unconditional", "seasonal"]
```

The `sampling_operation` value uses `sessions` as the canonical population
variable: it means §10.1 regression sessions for `enc_b`, and the
benchmark-specific §10.3 `sessions_b` for gate `b`. It never authorizes a
gate draw from the full regression population.

### 13.5 `cells` exact array/object schema

`cells` is an array of exactly 12 objects in §3.3 order. Each cell contains exactly:

```text
cell_order                         integer 0..11
forecaster                         string FAMILY-VOL | V9-VOL
horizon                            string 30S | 1M | 5M | 15M | 30M | 1H
lineage_identity                   object exact shape below
session_dates                      array[string YYYY-MM-DD], ascending unique
evidence_min_cutoff_at             string UTC RFC3339 microseconds | null
evidence_max_cutoff_at             string UTC RFC3339 microseconds | null
n_input                            integer >= 0
n_unselected_lineage_rows          integer >= 0
n_inadmissible                     integer >= 0
n_non_rth                          integer >= 0
n_overlap_excluded                 integer >= 0
n_null_or_nonfinite_excluded       integer >= 0
n_nonpositive_prediction_excluded  integer >= 0
n_kappa_unavailable                integer >= 0
n_windows                          integer >= 0
n_sessions                         integer >= 0
n_persist20_unavailable            integer >= 0
n_regression_windows               integer >= 0
n_regression_sessions              integer >= 0
mae_bps                            finite number | null
rank_corr                          finite number | null
level_ratio                        finite number | null
coverage_90                        finite number | null
mz_a                               finite number | null
mz_b                               finite number | null
mz_r2                              finite number | null
persist_rank_corr                  finite number | null
enc_b                              finite number | null
enc_b_ci_0999                      array[finite number, finite number] | null
enc_b_ci_095                       array[finite number, finite number] | null
bootstrap_attempted_draws          integer >= 0
bootstrap_valid_draws              integer >= 0
bootstrap_invalid_draws            integer >= 0
n_unconditional_unavailable                integer >= 0
n_unconditional_gate_windows              integer >= 0
n_unconditional_gate_sessions             integer >= 0
n_seasonal_gate_windows                   integer >= 0
n_seasonal_gate_sessions                  integer >= 0
unconditional_rank_corr                    finite number | null
seasonal_rank_corr                         finite number | null
qlike_candidate                            finite number | null
qlike_unconditional                        finite number | null
qlike_seasonal                             finite number | null
d_unconditional                            finite number | null
d_unconditional_ci_0999                    array[finite number, finite number] | null
d_unconditional_ci_095                     array[finite number, finite number] | null
d_seasonal                                 finite number | null
d_seasonal_ci_0999                         array[finite number, finite number] | null
d_seasonal_ci_095                          array[finite number, finite number] | null
unconditional_bootstrap_attempted_draws    integer >= 0
unconditional_bootstrap_valid_draws        integer >= 0
unconditional_bootstrap_invalid_draws      integer >= 0
seasonal_bootstrap_attempted_draws         integer >= 0
seasonal_bootstrap_valid_draws             integer >= 0
seasonal_bootstrap_invalid_draws           integer >= 0
gate_unconditional                         string PASS | FAIL | UNAVAILABLE | NOT_RUN
gate_seasonal                              string PASS | FAIL | UNAVAILABLE | NOT_RUN
classification                     string INFORMATIVE | NOISE | INSUFFICIENT | INVALID
reason_codes                       array[string], sorted unique UTF-8 ascending
```

The evidence-span metadata is derived from exactly the selected valid-window
population counted by `n_windows`, before persistence or benchmark
availability can reduce a later population:

- `session_dates` is the ascending unique set of XNYS session-date strings
  among exactly those `n_windows` rows, and `n_sessions =
  len(session_dates)`;
- `evidence_min_cutoff_at` and `evidence_max_cutoff_at` are respectively
  the minimum and maximum forecast `cutoff_at` instants among exactly those
  rows, rendered in the required UTC format;
- when `n_windows == 0`, `session_dates = []` and both cutoff fields are
  `null`.

Membership in a later regression or gate population is irrelevant: every row
counted in `n_windows` contributes even if persistence or a benchmark is later
unavailable, and no row outside `n_windows` contributes.

FAMILY lineage object has exactly:

```text
quant_id        string = "q3_volatility"
formula_version string = "realized-volatility-v1"
symbol          string = "COIN"
horizon         string = cell horizon
```

V9 lineage object has exactly:

```text
v3_model_version string
symbol           string = "COIN"
horizon          string = cell horizon
cohort_id        string
cohort_hash      string
```

No extra lineage keys. A V9 cell with a real selected lineage records that
identity verbatim. A zero-eligible-lineage V9 cell records exactly the §3.2
sentinel values; no other placeholder, omitted cell, `null` lineage member,
or negative receipt is permitted for that condition.

For an `INSUFFICIENT` cell, inferential coefficients/intervals and loss
summaries that were not validly computed are `null`, all three bootstrap
counter triplets are zero, and gate statuses follow §11.

An evaluated `INVALID` cell is permitted only when its identity,
evidence-span metadata, and every population/accounting `n_*` field can be
truthfully constructed; otherwise use §14.2. It serializes deterministically:

1. retain the structural fields through `evidence_max_cutoff_at` and every
   `n_*` field at its exact computed value;
2. set every field in this exact list to `null`:

```text
mae_bps
rank_corr
level_ratio
coverage_90
mz_a
mz_b
mz_r2
persist_rank_corr
enc_b
enc_b_ci_0999
enc_b_ci_095
unconditional_rank_corr
seasonal_rank_corr
qlike_candidate
qlike_unconditional
qlike_seasonal
d_unconditional
d_unconditional_ci_0999
d_unconditional_ci_095
d_seasonal
d_seasonal_ci_0999
d_seasonal_ci_095
```

3. serialize each gate as `UNAVAILABLE` iff its `n_*_gate_windows == 0`;
   otherwise serialize it as `NOT_RUN`, even if a provisional interval was
   completed before a later bootstrap exhausted its cap;
4. serialize bootstrap counter triplets by the first and only possible
   exhaustion point under §11:
   - no `*_BOOTSTRAP_EXHAUSTED` reason code: all three triplets are zero;
   - `ENC_B_BOOTSTRAP_EXHAUSTED`: its attempted count is `1000000`, its
     valid count is the exact attained value below `200000`, its invalid
     count is the difference, and both gate triplets are zero;
   - `UNCONDITIONAL_GATE_BOOTSTRAP_EXHAUSTED`: retain the completed `enc_b`
     triplet; its own attempted count is `1000000`, valid count is the exact
     attained value below `200000`, and invalid count is the difference; the
     seasonal triplet is zero;
   - `SEASONAL_GATE_BOOTSTRAP_EXHAUSTED`: retain the completed `enc_b` and
     unconditional triplets; its attempted count is `1000000`, valid count
     is the exact attained value below `200000`, and invalid count is the
     difference;
5. set `classification = INVALID` and derive `reason_codes` only by §11.

A completed retained triplet has `valid_draws = 200000` and its exact
deterministic attempted/invalid counts. §11 stops at the first exhausted
bootstrap, so an INVALID cell can contain at most one exhaustion code. No other
field may vary with discovery or evaluation order. No NaN/Infinity is ever
serialized.

### 13.6 Exact run identity body

Before outcomes are scored, construct `selected_lineages` as a JSON array of exactly 12 objects in §3.3 order. Each object is exactly:

FAMILY:

```json
{"cell_order":0,"forecaster":"FAMILY-VOL","horizon":"30S","lineage_identity":{"quant_id":"q3_volatility","formula_version":"realized-volatility-v1","symbol":"COIN","horizon":"30S"}}
```

with cell/horizon substituted appropriately.

V9:

```json
{"cell_order":6,"forecaster":"V9-VOL","horizon":"30S","lineage_identity":{"v3_model_version":"<string>","symbol":"COIN","horizon":"30S","cohort_id":"<string>","cohort_hash":"<string>"}}
```

with cell/horizon/identity substituted appropriately. For the §3.2 empty-set
case, the three identity placeholders are substituted with the exact reserved
sentinel strings and hash.

No extra keys are permitted.

`run_identity_body` has exactly:

```text
decision_id       string = decision ID
job_id            string = job ID
v1a_merge_sha     verified 40-hex SHA
evaluation_session YYYY-MM-DD
evaluation_as_of_at UTC RFC3339 microseconds
selected_lineages array = the exact 12-object array above
```

`run_identity = sha256(canonical_json(run_identity_body))`.

### 13.7 Canonical JSON and receipt hash

Canonical JSON:

```text
UTF-8
sort_keys = true
separators = (",", ":")
ensure_ascii = false
allow_nan = false
```

Array order is preserved.

To compute `receipt_sha256`:

1. construct complete receipt without `receipt_sha256`;
2. canonicalize exactly;
3. SHA-256 UTF-8 bytes;
4. lowercase hex digest;
5. add digest field. The digest field is excluded from its own hash boundary.

### 13.8 Official filename

Only:

```text
docs/v-1b-volatility-scorecard-receipt-<evaluation_session>-<run_identity>-<receipt_sha256>.json
```

---

## 14. Negative receipts

Negative receipts preserve failures without fabricating evaluated cells.

### 14.1 BLOCKED receipt

Use only when repository/environment/database/credential/revision authority fails **before evidence evaluation begins**.

Exact top-level keys:

```text
schema_version       string = "ATOM-V1B-BLOCKED-RECEIPT-1"
decision_id          exact decision string
job_id               exact job string
contract_path        exact contract path
generated_at_utc     UTC RFC3339 microseconds
stage                string = "PRE_EVALUATION_AUTHORITY"
reason_codes         array[string], sorted unique
observed_main_sha    40-hex string | null
expected_main_sha    40-hex string | null
observed_v1a_merge_sha 40-hex string | null
observed_user        string | null
observed_database    string | null
observed_effective_host string | null
project_binding_verified boolean | null
read_only            boolean | null
receipt_sha256       64 lowercase hex
```

No `run_identity`, `cells`, metrics, or classifications exist in this schema. It cannot be published as the official evaluated receipt and cannot open V-1C.

### 14.2 PRE-CELL INVALID receipt

Use when evidence evaluation has begun but a protocol/identity/causality/proof/accounting defect prevents truthful construction of all 12 evaluated cell objects or a valid run identity.

Exact top-level keys:

```text
schema_version       string = "ATOM-V1B-PRE-CELL-INVALID-RECEIPT-1"
decision_id          exact decision string
job_id               exact job string
contract_path        exact contract path
verified_main_sha    exact authorized V-1B SHA
v1a_merge_sha        verified V-1A merge SHA | null if the invalid defect is that identity itself
evaluation_session   YYYY-MM-DD | null
evaluation_as_of_at  UTC RFC3339 microseconds | null
generated_at_utc     UTC RFC3339 microseconds
stage                string = "EVALUATION_STARTED"
reason_codes         array[string], sorted unique
reader_identity      string = "atom_e1_scorecard_reader"
database_identity    exact §13.2 object when known | null
authority_proof      exact §13.3 object when authority already passed | null
read_only            boolean = true
forecast_writes      integer = 0
outcome_writes       integer = 0
evidence_writes      integer = 0
receipt_sha256       64 lowercase hex
```

No fabricated `cells` or `run_identity`. Overall semantic status is `INVALID` by schema identity. It cannot become the official evaluated receipt and cannot open V-1C.

### 14.3 POST-EVALUATION AUTHORITY INVALID receipt

Use only when all 12 truthful cell objects and a valid `run_identity` have
been constructed, but the mandatory final §15.3 authority recheck fails. The
passing §13 evaluated schema is forbidden for this condition.

Exact top-level keys:

```text
schema_version          string = "ATOM-V1B-POST-EVALUATION-AUTHORITY-INVALID-RECEIPT-1"
decision_id             exact decision string
job_id                  exact job string
contract_path           exact contract path
verified_main_sha       exact authorized V-1B SHA
v1a_merge_sha           verified V-1A merge SHA
run_identity            string, exactly 64 lowercase hex
evaluation_session      YYYY-MM-DD
evaluation_as_of_at     UTC RFC3339 microseconds
generated_at_utc        UTC RFC3339 microseconds
stage                   string = "POST_EVALUATION_AUTHORITY_RECHECK"
reason_codes            array[string] = ["FINAL_AUTHORITY_RECHECK_FAILED"]
reader_identity         string = "atom_e1_scorecard_reader"
database_identity       exact §13.2 object
initial_authority_proof exact passing §13.3 object from the pre-read check
read_only               boolean = true
forecast_writes         integer = 0
outcome_writes          integer = 0
evidence_writes         integer = 0
receipt_sha256          64 lowercase hex
```

No `cells`, metrics, classifications, evaluated `overall_status`, or final
passing `authority_proof` is serialized. The single exact reason code is used
regardless of which or how many final checks fail, so check/discovery order
cannot change the receipt body. Overall semantic status is `INVALID` by
schema identity. This receipt cannot become official and cannot open V-1C.

All three negative schemas use §13.7 canonicalization/hash rules.

---

## 15. Exact database, migration, effective target, and reader authority

Only authorized database target:

```text
Supabase project ref: afyiydxbjgzaiswnbcyj
Database:             postgres
Reader role:          atom_e1_scorecard_reader
Purpose:              ATOM production evidence database
Credential env:       ATOM_E1_SCORECARD_READONLY_DATABASE_URL
```

No simulator, restore/PITR, development, local, or other project/database is authorized.

### 15.1 Effective DSN target verification — before connect

The implementation must parse the supplied libpq/psycopg connection string and determine the **effective connection target**, not merely the URI authority hostname.

Fail `BLOCKED` before evidence reading unless all conditions hold:

- database name is exactly `postgres`;
- direct-host form is exactly `db.afyiydxbjgzaiswnbcyj.supabase.co` and
  the credential username is exactly `atom_e1_scorecard_reader`, **or** an
  approved Supavisor pooler host is used and the credential username is
  exactly
  `atom_e1_scorecard_reader.afyiydxbjgzaiswnbcyj`;
- the credential itself supplies exactly one unambiguous `user`, `host`,
  and `dbname` value; and
- no URI/query/conninfo, separate connect keyword argument, service file, or
  ambient libpq setting can add, replace, or redirect the verified target,
  login identity, or startup authorization state.

After percent-decoding and libpq normalization, explicitly reject:

```text
duplicate user, host, hostaddr, port, dbname, database, service, or options keys
any hostaddr
any service or servicefile
any options value
any multi-host or multi-port list
any separate connect keyword argument for user, host, hostaddr, port, dbname,
  database, service, servicefile, or options
any nonempty PGUSER, PGHOST, PGHOSTADDR, PGPORT, PGDATABASE, PGSERVICE,
  PGSERVICEFILE, or PGOPTIONS process environment variable
```

The V-1B implementation must never issue `SET ROLE`, `RESET ROLE`, `SET
SESSION AUTHORIZATION`, or `RESET SESSION AUTHORIZATION`. In particular,
startup `options=-c role=...`, `options=-c session_authorization=...`, and
Supabase temporary-access `options=-c jit=true` are all forbidden, regardless
of encoding or spelling.

The parsed credential login is recorded as `dsn_login_user`; it is not
inferred from post-connect role state. If the implementation cannot prove the
effective target and login from the pinned parser/libpq semantics, stop
`BLOCKED`; do not connect first and infer later.

### 15.2 Conditional migration 033

If and only if FAMILY volatility tables lack required reader access, V-1B may include:

```text
migrations/033_authorize_v1_volatility_scorecard_reader.sql
```

It may be applied only to project `afyiydxbjgzaiswnbcyj`, database `postgres`, through an Owner-controlled SQL/migration session.

The migration file itself must fail closed **before any GRANT/POLICY mutation** unless SQL runtime proves:

```text
current_user = 'postgres'
current_database() = 'postgres'
```

The migration must self-verify these assertions in an initial `DO` block or equivalent fail-before-mutation mechanism.

It may grant only the exact minimum existing-reader authority needed for:

```text
public.volatility_forecasts
public.volatility_forecast_outcomes
```

including schema `USAGE` only if required and exact SELECT policies only if required.

No new role, password, membership, writer, function, service, source, broad table grant, default privilege, or application elsewhere. Migration 033 may not alter database ownership or any database-level privilege; failure of the database-owner/`CREATE`/`TEMPORARY` checks requires a documentation-first amendment.

### 15.3 Six-table runtime full-read and zero-write proof

Before evidence reads, and again immediately before evaluated receipt construction in the same read-only run, verify:

- `session_user = current_user = atom_e1_scorecard_reader`;
- zero `pg_catalog.pg_auth_members` rows have the reader's role OID as
  `member`;
- the `pg_catalog.pg_roles` row for that user is exactly `LOGIN NOINHERIT
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, matching
  every boolean in §13.3;
- `current_database() = postgres`;
- the `pg_catalog.pg_database` owner of `current_database()`, resolved with
  `pg_catalog.pg_get_userbyid(datdba)`, is not
  `atom_e1_scorecard_reader`;
- `pg_catalog.has_database_privilege(current_user,current_database(),'CREATE')`
  is exactly `false`;
- `pg_catalog.has_database_privilege(current_user,current_database(),'TEMPORARY')`
  is exactly `false`;
- effective target, parsed credential login, and absence of every identity
  override already passed §15.1;
- schema `public` USAGE true;
- schema `public` CREATE false;
- schema `atom_v9_internal` USAGE true;
- EXECUTE true on exactly the two required proof-reader signatures
  `atom_v9_internal.read_forecast_commit_proof(text)` and
  `atom_v9_internal.read_legacy_evidence_publications_for_records(text,timestamptz,bigint[])`;
- SELECT true on all six tables;
- INSERT/UPDATE/DELETE/TRUNCATE false on all six;
- RLS enabled wherever repository law requires it;
- at least one applicable PERMISSIVE SELECT policy gives full read (`USING (true)` semantically) for the reader on each RLS table;
- **zero applicable RESTRICTIVE SELECT policies** for the reader, including policies applying through `PUBLIC` or any role membership;
- `SHOW transaction_isolation`, normalized to lowercase, equals exactly
  `repeatable read`;
- transaction read-only true;
- no fallback credential attempted.

Six tables:

```text
public.forecasts
public.forecast_outcomes
public.atom_v9_v4_forecasts
public.atom_v9_v4_outcomes
public.volatility_forecasts
public.volatility_forecast_outcomes
```

The routing is exact:

- any failure of the first, pre-read check => §14.1 BLOCKED;
- any authority failure after evaluation begins but before all 12 truthful
  cells and a valid `run_identity` exist => §14.2 PRE-CELL INVALID;
- when all 12 truthful cells and a valid `run_identity` exist, any failure of
  the final check => §14.3 POST-EVALUATION AUTHORITY INVALID.

A final authority failure may never be represented by the passing §13
evaluated schema, even as evaluated `overall_status = INVALID`. Only when
both complete §15.3 checks pass may their identical passing values populate
the evaluated `authority_proof`.

---

## 16. V-1B job environment, revision binding, rollback, and overall verdict

### 16.1 Accountability

```text
Job ID:                   ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1
Architecture/final audit: ChatGPT Pro
Implementation owner:     Codex-class implementation labor
Merge/infra owner:        Owner
```

### 16.2 Authorized execution environment

Existing Render benchmark worker only:

```text
service:        atom-h2d3-benchmark
credential env: ATOM_E1_SCORECARD_READONLY_DATABASE_URL
reader:         atom_e1_scorecard_reader
project:        afyiydxbjgzaiswnbcyj
database:       postgres
```

No new worker/service/credential/database identity or production web deploy.

### 16.3 Exact V-1B execution revision

After the V-1B implementation PR itself is independently reviewed, all required checks are green, zero material findings remain, and Owner merges it, define that exact main merge commit as `V1B_AUTHORIZED_MAIN_SHA`.

Before database evidence reads, the one-shot environment must provide:

```text
ATOM_V1B_AUTHORIZED_MAIN_SHA=<exact 40-hex Owner-merged V-1B main commit>
```

and verify:

```text
RENDER_GIT_COMMIT == ATOM_V1B_AUTHORIZED_MAIN_SHA
git rev-parse HEAD == ATOM_V1B_AUTHORIZED_MAIN_SHA
```

The authorized SHA must be a main commit containing this V-1A decision and the reviewed V-1B implementation. Failure => BLOCKED.

`verified_main_sha` in any evaluated receipt is exactly this observed authorized SHA, never a caller-supplied claim.

The verified `v1a_merge_sha` under §5.1 must also be reachable from this authorized main revision and proven to be the PR #319 Owner-merge commit.

### 16.4 Rollback

Let `V1B_PREMERGE_MAIN_SHA` be the exact first parent of
`V1B_AUTHORIZED_MAIN_SHA`. Verify the direct parent relationship from the
repository commit object. That first parent—not the V-1A merge SHA—is the sole
deployment rollback target, so every main commit that landed between V-1A and
V-1B is preserved.

Repository history is never reset to either SHA. If repository reversal is
needed, use a separately reviewed revert commit that reverses exactly the V-1B
merge diff on top of then-current `main`; do not discard intervening or later
work.

Operational rollback:

1. stop/suspend the one-shot V-1B command;
2. restore the benchmark worker to the command/environment at
   `V1B_PREMERGE_MAIN_SHA` or the exact reviewed V-1B revert;
3. preserve all generated receipts/evidence;
4. no deletion/rewrite;
5. no ad-hoc privilege rollback; privilege rollback requires reviewed
   migration/amendment.

### 16.5 Overall evaluated status

Evaluated receipt `overall_status`:

- `INVALID` if any cell is INVALID or any run-level protocol/evidence/reproducibility defect exists;
- otherwise `PASS` if at least one cell is INFORMATIVE;
- otherwise `FAIL` when all evaluated cells are NOISE and/or INSUFFICIENT with no INVALID cell.

The evaluated `overall_reason_codes` derivation is exact:

- `PASS` => exactly `[]`;
- `FAIL` => exactly `["NO_INFORMATIVE_CELL"]`;
- `INVALID` => include `INVALID_CELL_PRESENT` iff at least one cell is
  `INVALID`, and include `RUN_PROTOCOL_DEFECT` iff a run-level
  protocol/evidence/reproducibility defect exists. Include every applicable
  code, sort unique in ascending UTF-8 order, and include no other code.

A BLOCKED, PRE-CELL INVALID, or POST-EVALUATION AUTHORITY INVALID run uses its
separate §14 schema and has no evaluated overall status.

PASS means only that at least one frozen existing ATOM volatility forecaster carries
incremental realized-volatility information beyond `persist_20`, beyond an
unconditional level, and beyond the public intraday seasonal shape, on the frozen
population. It does **not** establish an options edge, an advantage over implied
volatility, or economic profitability.

---

## 17. Preregistration disclosure

The evaluated receipt includes these strings in exactly this order:

1. `2026-09-03 pooled overlapping-window Q3 volatility correlations, level ratios, and slopes were inspected before V-1A adoption.`
2. `Q3 appeared to carry rank information while its absolute level was horizon-miscalibrated.`
3. `An overlapping previous-window persistence calculation was inspected and recognized as overlap-contaminated.`
4. `No exact E-1-selected non-overlapping session-clustered V-1 enc_b statistic under this frozen population was adopted as controlling evidence before V-1A.`
5. `No exact V9-VOL causal-kappa enc_b statistic under this frozen population was adopted as controlling evidence before V-1A.`

If independent review establishes that the exact inferential statistic for an exact confirmatory cell/population was already inspected before adoption, that affected cell is `INVALID` for confirmatory claims and preserved as exploratory evidence.

---

## 18. Receipt generation, publication, and review gate

A local/runtime evaluated or negative receipt is not publication.

Only an **evaluated** `ATOM-V1B-RECEIPT-1` receipt can become the official V-1B evidence receipt.

Publication is a separate documentation-only PR adding exactly one immutable JSON file matching §13.8.

Before Owner merge of that receipt PR, all of these are mandatory:

1. independent review of the exact final receipt-PR head;
2. every required check green on that exact head;
3. zero unresolved P1/P2/material review threads;
4. SHA/schema/run-identity recomputation confirms the file is exactly the generated evaluated receipt;
5. no other repository path is changed.

Only after those gates may the Owner merge the receipt PR. That Owner merge is the publication event.

For a given run identity, the first Owner-merged SHA-valid evaluated receipt is the unique `OFFICIAL` receipt. A second different evaluated receipt for the same run identity is forbidden and causes fail-closed ambiguity until documentation-first amendment.

A BLOCKED, PRE-CELL INVALID, or POST-EVALUATION AUTHORITY INVALID receipt may
be preserved in an audit PR if desired, but it is never an official evaluated
receipt and never opens V-1C.

---

## 19. Rerun policy

Exactly one evaluated receipt may become OFFICIAL for the frozen `run_identity`.

A local rerun is allowed only for reproducibility and must use the same:

- verified V-1A merge SHA;
- evaluation session/as-of;
- selected lineages;
- project/database/reader;
- authorized V-1B main SHA;
- frozen mathematics and implementation.

If two otherwise valid reruns disagree on any substantive `cells`, `authority_proof`, evaluation identity, run identity, or receipt body field other than `generated_at_utc` and corresponding digest, the run is `INVALID`; no competing official receipt may be selected until documentation-first amendment.

No operator may rerun with a new session population to seek a favorable result.

---

## 20. Frozen future dashboard source — V-1C remains blocked

This section freezes only a possible future source contract. It grants no V-1C implementation authority.

If ChatGPT Pro later explicitly opens V-1C after official receipt audit, `V9 VOLATILITY ACCURACY` must read only the six V9-VOL cells from the unique Owner-merged SHA-valid OFFICIAL receipt bundled in the deployed repository.

The web process may not query live evidence tables or recompute V-1 statistics.

Visible rows exactly:

```text
MAE BPS
RANK CORR
LEVEL RATIO
90% COVERAGE
STATUS
```

Columns exactly:

```text
30S 1M 5M 15M 30M 1H
```

Directional wins/losses/accuracy may not populate the volatility card.

### 20.1 Dashboard status precedence and freshness

For a V9 horizon:

1. if no unique Owner-merged SHA-valid OFFICIAL evaluated receipt exists => `NO DATA`;
2. if the receipted cell classification is `INVALID` => `INVALID` regardless of freshness;
3. otherwise determine freshness by `evaluation_session`, **not** by positive-horizon `evidence_max_cutoff_at`;
4. `STALE` only when receipt `evaluation_session` is earlier than the most recent fully completed regular XNYS session before render time;
5. otherwise show exact receipt classification `INFORMATIVE`, `NOISE`, or `INSUFFICIENT`.

A valid positive-horizon receipt is therefore not automatically stale merely because its final admissible forecast cutoff precedes the session close.

`NO DATA` metric cells blank. `STALE` retains receipted metrics. Never fabricate zeroes.

---

## 21. V-1C and V-2 gates

### V-1C

`BLOCKED` until, in order:

1. V-1A Owner merge;
2. V-1B implementation exact-head independent review, green checks, zero material findings, Owner merge;
3. any authorized migration 033 applied and verified if required;
4. one-shot scorecard run from exact authorized V-1B merged SHA;
5. evaluated receipt generated;
6. receipt publication PR exact-head independent review, all required checks green, zero material findings;
7. Owner merge of unique evaluated receipt;
8. ChatGPT Pro audits the published receipt and explicitly opens V-1C.

No implementation agent may infer V-1C authority.

### V-2

The draft's prior 20-session V-2 hypothesis is **not adopted**.

V-2 remains a separate future protected-boundary freeze. Even a V-1B PASS buys only the right to decide what to research next.

No production volatility-primary synthesis, Q3 insertion, family reweighting, IV comparison, options monetization, gating, sizing, broker/order change, Gamma production activation, `final_bps` change, or live-capital action is authorized by V-1.

---

## 22. Active-phase pointer relationship

V-1A and V-1B are read-only research work and **take no active-phase pointer**.

This decision does not modify `AGENTS.md`, `PHASES.md`, or the current active-phase pointer. Existing SIM and other separately authorized work may continue only if it does not mutate V-1 definitions, evidence, or execution environment.

No pointer change is implied by Owner merge of V-1A, V-1B implementation, or receipt publication.

---

## 23. Production, SIM, broker, and immutable-evidence boundaries

V-1 authorizes no changes to:

- `final_bps`;
- current V9 signed synthesis;
- family signs/weights;
- Q3 production formula;
- V4C production mathematics/state contract;
- V4D production contract;
- Gamma production activation;
- SIM entry/exit/resolution/P&L mathematics;
- SIM database/service boundaries;
- broker/account/position/order/execution endpoints;
- live capital;
- options execution;
- Level-II mathematical use;
- immutable directional evidence;
- directional accuracy lineage.

All V-1 database reads are read-only. No evidence backfill, correction, rewrite, deletion, or conversion is authorized.

---

## 24. Stop conditions

Stop `BLOCKED` before evaluation if implementation requires or discovers:

- any unlisted repository path;
- a new market-data source;
- a new database/role/credential/service;
- broader database authority than §15;
- target DSN/project cannot be proven;
- migration ordinal 033 collision;
- authorized execution SHA cannot be proven;
- V-1A merge identity cannot be proven before evaluation;
- production V9/SIM/broker/order/capital changes;
- dashboard implementation;
- V-1C or V-2 work.

After evaluation begins, any protocol/identity/causality/proof/accounting defect is `INVALID`, not BLOCKED. Use evaluated INVALID receipt when complete truthful cells can be constructed; otherwise PRE-CELL INVALID receipt.

Any required widening needs documentation-first amendment and independent exact-head review before implementation.

---

## 25. Exact sequence

```text
V-1A documentation PR #319
-> exact-head independent review
-> all required checks green
-> zero unresolved material findings
-> Owner merge
-> record verified V-1A merge SHA
-> V-1B implementation PR only
-> exact-head independent review
-> tests / all required checks green
-> zero unresolved material findings
-> Owner merge
-> record exact V1B_AUTHORIZED_MAIN_SHA
-> conditional migration 033 only if privilege check requires it
-> migration self-check + post-apply reader authority verification
-> configure one-shot benchmark worker with exact authorized SHA
-> run V-1B read-only scorecard
-> evaluated receipt OR truthful negative receipt
-> if evaluated receipt: documentation-only publication PR containing exactly one receipt file
-> exact-head independent receipt review
-> all required receipt-PR checks green
-> zero unresolved material receipt findings
-> Owner merge official evaluated receipt
-> ChatGPT Pro receipt audit
-> separate V-1C decision
-> later separate V-2 decision
```

V-1C and V-2 are not authorized early.

---

## 26. Adoption statement

Owner merge of this exact final-head document makes `ATOM-V1A-VOLATILITY-FIRST-FREEZE-1` controlling for V-1 subject matter and authorizes **V-1B implementation only** under the exhaustive boundaries above.

Until Owner merge, it remains proposed documentation.
