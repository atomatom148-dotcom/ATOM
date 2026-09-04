# V-1A — Volatility-First Research and Transition Freeze

**Decision ID:** `ATOM-V1A-VOLATILITY-FIRST-FREEZE-1`  
**Status:** PROPOSED CONTROLLING FREEZE — documentation only until Owner merge  
**Program:** ATOM V9  
**Author of record:** ChatGPT Pro  
**Implementation owner beneath this freeze:** Codex by default under controlling governance  
**Owner authority:** Owner retains final merge, infrastructure, risk, broker, order, and capital authority.

---

## 1. Objective, scope, and supersession

ATOM changes its primary **research evaluation target** from directional hit rate to forecasted movement magnitude / volatility.

The governing research question is:

> How large is the coming move, how well calibrated is that magnitude forecast, and does the forecast contain information beyond simple volatility persistence?

Direction remains secondary immutable evidence. Existing directional forecasts, outcomes, receipts, lineage, and history are not deleted, rewritten, relabeled, or invalidated.

This freeze supersedes, for V-1 subject matter only, conflicting choices in `docs/drafts/v-1-volatility-target-program-DRAFT.md` and the saved pre-adoption `ATOM_V1_VOLATILITY_FIRST_TRANSITION_FREEZE.md`.

Nothing here supersedes production V9 mathematics, SIM mathematics, broker/order boundaries, immutable evidence law, E-1 evidence-selection law, or ATOM governance.

V-1 evaluates exactly six horizons independently:

`30S`, `1M`, `5M`, `15M`, `30M`, `1H`.

No pooling across horizons or lineages is permitted.

---

## 2. Frozen targets

### 2.1 FAMILY-VOL

```text
predicted_volatility_bps = forecast_volatility_bps
realized_volatility_bps  = realized_move_bps
```

### 2.2 V9-VOL

```text
predicted_volatility_bps = kappa(f) * sqrt(predictive_variance_bps2)
realized_volatility_bps  = abs(actual_return_bps)
```

All required inputs must be finite. Predicted volatility must be strictly positive. A zero realized move is valid evidence.

---

## 3. Exact lineage identities and twelve-cell multiplicity budget

E-1 lineage boundaries are preserved exactly.

FAMILY identity is:

```text
(quant_id, formula_version, symbol, horizon)
```

V9 identity is:

```text
(v3_model_version, symbol, horizon, cohort_id, cohort_hash)
```

Distinct identities may never be pooled.

### 3.1 FAMILY-VOL lineage

For each horizon, FAMILY-VOL is fixed to:

```text
quant_id        = q3_volatility
formula_version = realized-volatility-v1
symbol          = COIN
horizon         = the cell horizon
```

### 3.2 Deterministic V9-VOL lineage selection

For each horizon, consider every admissible `PRODUCTION` V9 forecast identity for `symbol = COIN` inside the frozen snapshot and as-of boundary. For each identity compute its maximum admissible forecast `cutoff_at` without examining outcomes or any volatility metric.

Select the identity with the greatest such maximum cutoff. If multiple identities tie, sort the complete identity tuple `(v3_model_version, symbol, horizon, cohort_id, cohort_hash)` by UTF-8 code-point order and select the first.

All rows from every non-selected identity are excluded and counted as `n_unselected_lineage_rows`. They are never pooled into the selected lineage.

Therefore the inferential multiplicity budget remains exactly:

```text
6 FAMILY-VOL cells + 6 V9-VOL cells = 12 cells
```

---

## 4. Deterministic official evaluation population

### 4.1 Merge-derived evaluation session and as-of boundary

The official V-1B run is one-shot.

Let `v1a_merge_committed_at` be the UTC commit timestamp of the Owner-merged V-1A merge commit on `main`.

Convert that instant to `America/New_York`.

- If it is at or after 16:00:00 local on a regular full XNYS session, `evaluation_session` is that session date.
- Otherwise `evaluation_session` is the immediately preceding completed regular full XNYS session.
- Half-days, weekends, holidays, and in-progress sessions are excluded.

`evaluation_as_of_at` is exactly `16:00:00.000000 America/New_York` on `evaluation_session`, converted to UTC and serialized as `YYYY-MM-DDTHH:MM:SS.ffffffZ`.

No operator-selected later as-of, session subset, extension, early stop, or outcome-dependent session selection is permitted.

### 4.2 Snapshot

The official evidence read uses one read-only `REPEATABLE READ` transaction/snapshot for the complete run.

Evidence is inside the official snapshot only when all required forecast, outcome, and publication-proof timestamps are at or before `evaluation_as_of_at` under their existing proof contracts.

Evidence published after `evaluation_as_of_at` is excluded even when its market cutoff is earlier.

### 4.3 Session-date population

For each selected lineage, use every sorted unique regular XNYS date present among its admissible forecast rows through `evaluation_session`. No date may be manually added, removed, retried, or sampled.

---

## 5. Exact canonical selected-lineage array and run identity

Before outcome scoring, construct `selected_lineages` as a JSON array of exactly 12 objects in the exact cell order in §12.1.

FAMILY object shape is exactly:

```json
{
  "cell_order": 0,
  "forecaster": "FAMILY-VOL",
  "horizon": "30S",
  "identity": {
    "quant_id": "q3_volatility",
    "formula_version": "realized-volatility-v1",
    "symbol": "COIN",
    "horizon": "30S"
  }
}
```

V9 object shape is exactly:

```json
{
  "cell_order": 6,
  "forecaster": "V9-VOL",
  "horizon": "30S",
  "identity": {
    "v3_model_version": "<string>",
    "symbol": "COIN",
    "horizon": "30S",
    "cohort_id": "<string>",
    "cohort_hash": "<string>"
  }
}
```

Only the values and cell-order/horizon positions vary as frozen. No extra keys are permitted.

`run_identity_body` is exactly:

```json
{
  "decision_id": "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1",
  "job_id": "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1",
  "v1a_merge_sha": "<40 lowercase hex>",
  "evaluation_session": "YYYY-MM-DD",
  "evaluation_as_of_at": "YYYY-MM-DDTHH:MM:SS.ffffffZ",
  "selected_lineages": ["<the exact 12 objects above in §12.1 order>"]
}
```

The bracketed notation above denotes the JSON array itself, not a string serialization.

`run_identity = sha256(canonical_json(run_identity_body))` under §13.3.

Exactly one receipt may become `OFFICIAL` for a run identity. Reruns are reproducibility-only and must use the identical snapshot boundary, lineages, code revision, database identity, and mathematics. Any substantive disagreement makes the study `INVALID`; no favorable rerun may replace the first official result.

---

## 6. Window selection and mutually exclusive row accounting

Reuse E-1 deterministic ordering and horizon-spaced non-overlap selection. Selection restarts per session.

For each forecaster/horizon candidate universe, `n_input` is every raw forecast row for `symbol = COIN` and that horizon visible in the frozen snapshot before lineage filtering.

Each input row is assigned to **exactly one** bucket using this precedence, stopping at the first matching condition:

1. `n_unselected_lineage_rows` — identity is not the selected lineage.
2. `n_inadmissible` — selected lineage but publication/proof/admissibility fails.
3. `n_non_rth` — selected/admissible but complete forecast interval is outside one regular 09:30–16:00 XNYS session.
4. `n_overlap_excluded` — selected/admissible/RTH but excluded by frozen horizon-spacing selection.
5. `n_null_or_nonfinite_excluded` — selected window has a required null or non-finite forecast/outcome/variance input.
6. `n_nonpositive_prediction_excluded` — resulting predicted volatility is finite but `<= 0`.
7. `n_kappa_unavailable` — V9-VOL only: all other inputs qualify but §7 does not produce an accepted causal MATURE kappa. FAMILY-VOL always records `0` here.
8. `n_windows` — row survives all prior buckets and is a valid selected volatility window.

Exactly:

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

A row satisfying multiple defects is counted only in the earliest applicable bucket.

Persistence accounting is also exclusive:

```text
n_windows = n_persist20_unavailable + n_regression_windows
```

`n_sessions` is the number of distinct session dates represented by `n_windows`; `n_regression_sessions` is the number represented by `n_regression_windows`.

The receipt must satisfy both equations exactly for every cell or the cell and overall run are `INVALID`.

---

## 7. Complete causal-kappa reconstruction

V-1B must not read a latest/current V4C state merely to obtain kappa. It reconstructs causal kappa from existing V4 forecast/outcome evidence using the frozen V4C functions unchanged.

### 7.1 Exact causal scope

For target V9 forecast `f`, only V4 pairs matching all of:

```text
v3_model_version = f.v3_model_version
symbol           = f.symbol
horizon          = f.horizon
cohort_id         = f.cohort_id
cohort_hash       = f.cohort_hash
```

may contribute.

Every contributing pair must satisfy all existing V4 proof/admissibility requirements plus:

```text
forecast.cutoff_at        < f.cutoff_at
outcome.target_resolved_at < f.cutoff_at
outcome.created_at         < f.cutoff_at
forecast publication proof observed_at < f.cutoff_at
outcome publication proof observed_at  < f.cutoff_at
```

Equality is not prior and is excluded. Delayed recovery or delayed durable insertion may never back-enter a causal kappa state for an earlier target forecast.

### 7.2 Exact non-overlap and latest-250 split

For the strictly prior governed pairs:

1. apply the existing V4C governed-evidence filter unchanged;
2. apply existing `select_non_overlapping(...)` unchanged;
3. sort by `(forecast.cutoff_at, forecast_record_id)`;
4. `split = max(0, len(selected) - 250)`;
5. `calibration_pairs = selected[:split]`;
6. `validation_pairs = selected[split:]`;
7. the latest 250 selected pairs are withheld from fitting;
8. construct existing `CalibrationObservation` values from calibration pairs only;
9. call existing frozen `calibrate_scale(...)` unchanged.

### 7.3 Acceptance

`kappa(f)` is usable only when reconstructed `ScaleResult.status == "MATURE"` and kappa is finite and strictly positive.

`PROVISIONAL`, `UNAVAILABLE`, null, non-finite, zero, or negative values are unavailable and counted in `n_kappa_unavailable`.

No fallback, cross-cohort, neighboring-horizon, interpolated, current-state, or forward-filled kappa is allowed.

---

## 8. Persistence benchmark and inferential minimum

For each cell, valid selected windows are ordered by `(session_date, cutoff_at, immutable_record_identity)` across the frozen population.

```text
persist_20(w) = arithmetic mean realized_volatility_bps of the prior 20 valid selected windows
```

Every component must itself be durably outcome/proof available no later than `w.cutoff_at`.

The first 20 valid windows and any later row without 20 causal prior realized magnitudes are `n_persist20_unavailable`.

Remaining rows are the regression population.

Inferential eligibility applies only to:

```text
n_regression_windows  >= 100
n_regression_sessions >= 10
```

Pre-persistence `n_windows` / `n_sessions` are descriptive only.

---

## 9. Descriptive metrics

For every cell report:

```text
mae_bps      = mean(abs(predicted_volatility_bps - realized_volatility_bps))
level_ratio  = median(predicted_volatility_bps) / median(realized_volatility_bps)
coverage_90  = mean(realized_volatility_bps <= 1.6448536269514722 * predicted_volatility_bps)
```

If median realized volatility is zero, `level_ratio = null`.

Mincer-Zarnowitz descriptive regression is:

```text
realized_volatility_bps = mz_a + mz_b * predicted_volatility_bps + error
```

### 9.1 Spearman

For `rank_corr` and `persist_rank_corr`:

- paired finite observations only;
- ascending numeric order;
- ties receive arithmetic mean of one-based rank positions;
- Pearson correlation of rank vectors using binary64 arithmetic;
- fewer than two pairs or zero variance in either rank vector => JSON `null`;
- no jitter, random tie-breaking, epsilon, imputation, or alternate rank method.

---

## 10. Sole inferential model and exact bootstrap

The sole classification statistic is `enc_b` in:

```text
realized_volatility_bps
  = intercept
  + persistence_coefficient * persist_20
  + enc_b * predicted_volatility_bps
  + error
```

Fit ordinary least squares with intercept on the full regression population.

### 10.1 Exact session-resampled OLS-refit algorithm

`quant/volatility_scorecard.py` is explicitly authorized to run this pure in-memory loop.

For each cell:

1. construct `sessions = tuple(sorted(unique regression session YYYY-MM-DD dates))` in ascending ISO date order;
2. instantiate exactly `rng = random.Random(0)` once for that cell;
3. for every attempt execute exactly `drawn = rng.choices(sessions, k=len(sessions))`;
4. for each identity in `drawn`, append all regression rows from that session in original deterministic row order; repeated session identities duplicate all their rows;
5. refit the exact OLS model;
6. valid draw requires full column rank and finite `enc_b`;
7. rank-deficient/non-finite draws are discarded, counted, and still consume the RNG state created by the exact `choices` call.

Require exactly `200000` valid draws. Stop after `1000000` attempted draws. If fewer than `200000` valid draws exist then, classification is `INVALID` and no partial interval is permitted.

Percentile indices are exactly:

```text
lower = floor((1 - level) / 2 * (B - 1))
upper = ceil((1 + level) / 2 * (B - 1))
B = 200000
levels = 0.999, 0.95
```

No alternate RNG call, bootstrap, robust covariance, t test, ridge, pseudoinverse, or model fallback is authorized.

---

## 11. Classification and precedence

1. Protocol/identity/causality/proof/accounting defect => `INVALID` regardless of sample size.
2. Else regression population below 100 windows or 10 sessions => `INSUFFICIENT`; do not bootstrap.
3. Else full-sample OLS invalid or bootstrap-valid-draw requirement fails => `INVALID`.
4. Else lower endpoint of `enc_b_ci_0999` strictly greater than zero => `INFORMATIVE`.
5. Else => `NOISE`.

There are exactly 12 inferential cells; report-only expected false-`INFORMATIVE` count is `12 * 0.0005 = 0.006`.

No V-1 result is tradeable, profitable, production-ready, or capital authority.

---

## 12. Exact V-1B implementation boundary and cell ordering

Owner merge of V-1A authorizes only job:

```text
ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1
```

Unconditional implementation files:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
```

Conditional third file only when exact FAMILY-VOL reader access is absent:

```text
migrations/033_authorize_v1_volatility_scorecard_reader.sql
```

Every other repository path is blocked. Existing E-1/V4C functions may be imported but not edited. If another file or a different migration ordinal is required, stop `BLOCKED` for a documentation-first amendment.

### 12.1 Canonical cell order

```text
0  FAMILY-VOL 30S
1  FAMILY-VOL 1M
2  FAMILY-VOL 5M
3  FAMILY-VOL 15M
4  FAMILY-VOL 30M
5  FAMILY-VOL 1H
6  V9-VOL     30S
7  V9-VOL     1M
8  V9-VOL     5M
9  V9-VOL     15M
10 V9-VOL     30M
11 V9-VOL     1H
```

---

## 13. Exact evaluated receipt schema

A run that passes authority verification far enough to evaluate cells emits exactly one `ATOM-V1B-RECEIPT-1` JSON object.

Top-level keys/types are exactly:

```text
schema_version       string = "ATOM-V1B-RECEIPT-1"
decision_id          string = "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1"
job_id               string = "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1"
contract_path        string = "docs/v-1a-volatility-first-freeze.md"
code_version         string
verified_main_sha    string, 40 lowercase hex
v1a_merge_sha        string, 40 lowercase hex
run_identity         string, 64 lowercase hex
evaluation_session   string YYYY-MM-DD
evaluation_as_of_at  string RFC3339 UTC microseconds
generated_at_utc     string RFC3339 UTC microseconds
reader_identity      string = "atom_e1_scorecard_reader"
database_identity    object
authority_proof      object
bootstrap            object
cells                array exactly 12
overall_status       PASS | FAIL | INVALID
overall_reason_codes array[string], sorted unique
scouting_disclosure  array[string]
read_only            boolean = true
forecast_writes      integer = 0
outcome_writes       integer = 0
evidence_writes      integer = 0
receipt_sha256       string, 64 lowercase hex
```

### 13.1 Cell object

Each cell object has exactly:

```text
cell_order
forecaster
horizon
lineage_identity
session_dates
evidence_min_cutoff_at
evidence_max_cutoff_at
n_input
n_unselected_lineage_rows
n_inadmissible
n_non_rth
n_overlap_excluded
n_null_or_nonfinite_excluded
n_nonpositive_prediction_excluded
n_kappa_unavailable
n_windows
n_sessions
n_persist20_unavailable
n_regression_windows
n_regression_sessions
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
bootstrap_attempted_draws
bootstrap_valid_draws
bootstrap_invalid_draws
classification
reason_codes
```

Counts are nonnegative integers. Metric values are finite JSON numbers or null where explicitly allowed. Reason codes are sorted unique strings.

### 13.2 Authority proof object

Exact keys:

```text
current_user
observed_database_name
observed_supabase_project_ref
project_identity_method
schema_public_usage
schema_public_create
six_tables_select
six_tables_insert
six_tables_update
six_tables_delete
six_tables_truncate
six_tables_rls_enabled
six_tables_permissive_full_read_policy
six_tables_restrictive_policy_absent
read_only_transaction
verification_status
```

### 13.3 Canonical JSON and digest

Canonical JSON is UTF-8 with exactly:

```text
sort_keys=true
separators=(",", ":")
ensure_ascii=false
allow_nan=false
```

To compute `receipt_sha256`, remove the digest key, canonicalize the complete remaining object, SHA-256 the UTF-8 bytes, lowercase-hex encode, then add the digest field. The digest never hashes itself.

### 13.4 Evaluated receipt filename/publication

Exact filename:

```text
docs/v-1b-volatility-scorecard-receipt-<evaluation_session>-<run_identity>-<receipt_sha256>.json
```

Runtime generation is not publication. Publication is a separate documentation-only PR adding one immutable file. The first Owner-merged SHA-valid receipt for the run identity is uniquely official. A second distinct receipt for the same run identity is forbidden and causes fail-closed ambiguity until amendment.

---

## 14. Exact BLOCKED receipt schema

A failure before the full evaluation population/cells/run identity can be constructed must not fabricate those values.

Such a run emits a distinct JSON object with exactly:

```text
schema_version              string = "ATOM-V1B-BLOCKED-RECEIPT-1"
decision_id                 string = "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1"
job_id                      string = "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1"
contract_path               string = "docs/v-1a-volatility-first-freeze.md"
code_version                string
v1a_merge_sha               string, 40 lowercase hex
generated_at_utc            string RFC3339 UTC microseconds
failure_stage               string = ENVIRONMENT | REVISION | DATABASE_IDENTITY | READER_IDENTITY | AUTHORITY | MIGRATION_REQUIRED | BOUNDARY
reason_codes                array[string], sorted unique
declared_project_ref        string = "afyiydxbjgzaiswnbcyj"
declared_database_name      string = "postgres"
observed_project_ref        string | null
observed_database_name      string | null
observed_current_user       string | null
execution_revision_sha      string | null
expected_v1b_main_sha       string | null
read_only                   boolean = true
forecast_writes             integer = 0
outcome_writes              integer = 0
evidence_writes             integer = 0
overall_status              string = "BLOCKED"
receipt_sha256              string, 64 lowercase hex
```

Same canonical JSON/digest rule as §13.3.

A BLOCKED receipt has no `run_identity`, `cells`, metrics, classification, or official-scorecard authority. It is negative operational evidence only.

Optional publication, if the Owner chooses to preserve it in-repo, uses exactly:

```text
docs/v-1b-volatility-scorecard-blocked-<YYYY-MM-DD>-<receipt_sha256>.json
```

It can never satisfy the V-1B official evaluated-receipt gate.

---

## 15. Exact database/project and runtime authority proof

The only authorized evidence database is:

```text
Supabase project ref: afyiydxbjgzaiswnbcyj
Database:             postgres
Reader:               atom_e1_scorecard_reader
```

### 15.1 Runtime project binding

Before opening evidence queries, parse `ATOM_E1_SCORECARD_READONLY_DATABASE_URL` without logging its secret material.

It must prove project ref `afyiydxbjgzaiswnbcyj` by one of these exact Supabase DSN forms:

1. direct host: hostname exactly `db.afyiydxbjgzaiswnbcyj.supabase.co`; or
2. Supavisor/pooler form: database username exactly ends with `.afyiydxbjgzaiswnbcyj` and the host ends with `.pooler.supabase.com`.

The database path/name must be exactly `postgres`. Any DSN that does not cryptographically/structurally bind the connection target to that project ref under one of these forms is `BLOCKED`; do not infer identity from table names or receipt constants.

After connecting, require `current_database() = 'postgres'` and `current_user = 'atom_e1_scorecard_reader'`.

Record the observed project ref and the method (`DIRECT_HOST` or `POOLER_USERNAME`) in `authority_proof`.

No restore, PITR, simulator, development, local, or other project may be used for the official run.

### 15.2 Conditional migration

Only if the two volatility tables lack exact reader access, migration `033_authorize_v1_volatility_scorecard_reader.sql` may be applied once to project `afyiydxbjgzaiswnbcyj`, database `postgres`, by an Owner-controlled session with `current_user = 'postgres'`.

Application anywhere else is forbidden.

The migration may grant only the minimum SELECT/RLS policy authority on:

```text
public.volatility_forecasts
public.volatility_forecast_outcomes
```

No new role, password, membership, writer, source, service, function, broad grant, or default privilege is authorized.

### 15.3 Six-table full-read/no-write proof

Before evidence reads and again before evaluated receipt construction, verify all six:

```text
public.forecasts
public.forecast_outcomes
public.atom_v9_v4_forecasts
public.atom_v9_v4_outcomes
public.volatility_forecasts
public.volatility_forecast_outcomes
```

Require:

- exact reader identity;
- schema `public` USAGE true and CREATE false;
- SELECT true on every table;
- INSERT/UPDATE/DELETE/TRUNCATE false on every table;
- required RLS enabled;
- at least one applicable **PERMISSIVE** SELECT policy whose effective predicate is full-read/true for the reader;
- **zero applicable RESTRICTIVE SELECT policies**, including policies applying through `PUBLIC`, for the reader on every table;
- transaction read-only true;
- no fallback credential.

Any restrictive applicable policy fails full-read proof even if a permissive `USING (true)` policy also exists.

Failure => `BLOCKED` before inference and use §14 receipt shape.

---

## 16. Execution revision binding

The V-1B implementation PR must be independently reviewed, green, and Owner-merged before execution.

Let `authorized_v1b_main_sha` be the exact `main` commit SHA produced by that Owner merge.

Before the one-shot run, the Owner sets non-secret environment variable:

```text
ATOM_V1B_AUTHORIZED_MAIN_SHA=<authorized_v1b_main_sha>
```

At execution time the worker must require all of:

```text
ATOM_V1B_AUTHORIZED_MAIN_SHA == authorized_v1b_main_sha
RENDER_GIT_COMMIT            == authorized_v1b_main_sha
git rev-parse HEAD           == authorized_v1b_main_sha
```

Each must be exactly 40 lowercase hexadecimal characters. If repository checkout metadata is unavailable or any value differs, emit `BLOCKED` receipt with `failure_stage = REVISION` and do not read evidence.

For an evaluated receipt:

```text
verified_main_sha = authorized_v1b_main_sha
```

No caller-supplied arbitrary SHA may populate `verified_main_sha`.

---

## 17. Accountable environment, rollback, and overall result

```text
Job ID:                   ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1
Architecture/final audit: ChatGPT Pro
Implementation owner:     Codex by default
Merge/infra owner:        Owner
Execution service:        atom-h2d3-benchmark
Credential env:           ATOM_E1_SCORECARD_READONLY_DATABASE_URL
Authorized revision env:  ATOM_V1B_AUTHORIZED_MAIN_SHA
```

No new worker, service, credential, production web deploy, V9 runtime activation, or SIM activation is authorized.

Repository rollback target is the exact Owner-merged V-1A `main` SHA immediately before V-1B implementation merge. Operational rollback stops the one-shot command and restores the benchmark worker’s pre-V-1B start-command/environment state. Evidence and receipts are preserved; ad hoc privilege rollback is forbidden.

Overall evaluated status:

- `INVALID` if any cell is `INVALID` or reproducibility/accounting/protocol integrity fails after evaluation begins.
- `PASS` if at least one valid cell is `INFORMATIVE` and no cell is `INVALID`.
- `FAIL` if no cell is `INFORMATIVE`, no cell is `INVALID`, and evaluation completed.
- `BLOCKED` is represented only by §14 and means required authority/environment/boundary was unavailable before a valid evaluation.

PASS authorizes no production promotion.

---

## 18. Preregistration disclosure

The official receipt must disclose:

1. pooled overlapping-window Q3 volatility correlations, level ratios, and slopes were inspected before adoption;
2. Q3 appeared to carry rank information while absolute level was horizon-miscalibrated;
3. an overlapping previous-window persistence calculation was inspected and recognized as overlap-contaminated;
4. no exact E-1-selected, persistence-adjusted, session-bootstrap `enc_b` result under this contract was adopted before V-1A;
5. no exact V9-VOL causal-kappa `enc_b` result under this contract was adopted before V-1A.

If evidence proves an exact confirmatory statistic/population was inspected before adoption, the affected claim is `INVALID` for confirmatory use and preserved only as exploratory evidence.

---

## 19. Future dashboard contract — V-1C still blocked

This freezes source semantics only; it does **not** authorize dashboard code.

A future V-1C may source `V9 VOLATILITY ACCURACY` only from the unique Owner-merged SHA-valid official V-1B evaluated receipt and only its V9-VOL cells.

Rows remain exactly:

```text
MAE BPS
RANK CORR
LEVEL RATIO
90% COVERAGE
STATUS
```

`INVALID` has precedence and may never be hidden by freshness.

For non-INVALID valid positive-horizon receipts, freshness is based on `evaluation_session`, not `evidence_max_cutoff_at`: a receipt is `STALE` only when a later fully completed regular XNYS session exists after `evaluation_session`. On the evaluation session itself and before the next completed regular session, it is not automatically stale merely because the last eligible cutoff precedes 16:00 by the horizon length.

No live evidence recomputation or directional percentage reuse is permitted.

V-1C remains `BLOCKED` until V-1B implementation is Owner-merged, the official evaluated receipt is published by Owner merge, ChatGPT Pro audits that receipt, and ChatGPT Pro explicitly opens V-1C.

---

## 20. V-2 remains separate

No V-2 hypothesis, production volatility-primary synthesis, Q3 family insertion, reweighting, opportunity gating, sizing, options work, broker/order change, `final_bps` change, Gamma activation, or live-capital action is authorized.

An `INFORMATIVE` V-1 result buys only the right for ChatGPT Pro and the Owner to decide whether to author a later V-2 freeze.

---

## 21. Production / SIM / broker boundary

V-1 does not authorize changes to:

- `final_bps` or signed V9 synthesis;
- existing family signs/weights or Q3 formula;
- V4C production state;
- production Gamma activation;
- SIM entry, exit, resolution, or P&L mathematics;
- broker/account/order endpoints;
- live capital or options execution;
- Level II mathematical use;
- existing immutable directional evidence;
- production deployment.

Directional forecasting may continue unchanged.

---

## 22. Phase-pointer relationship

V-1A and V-1B are read-only documentation/research work and take **no active-phase pointer**.

They may run alongside the current active program only while they do not mutate or delay it. This document does not edit `AGENTS.md` or move its active pointer.

Owner merge of V-1A authorizes **V-1B only** under the exact boundary above.

V-1C remains blocked. V-2 remains blocked.

---

## 23. Required V-1B tests

At minimum test:

1. six canonical horizons and twelve exact cells;
2. exact FAMILY and deterministic V9 lineage selection, no pooling;
3. canonical `selected_lineages` JSON array/object shape and run-identity stability;
4. merge-derived evaluation session/as-of and no operator session selection;
5. mutually exclusive row bucket precedence and both reconciliation equations;
6. zero prediction accounting and zero realized move validity;
7. strict causal kappa including `outcome.created_at < f.cutoff_at` and both publication-proof timestamps;
8. latest-250 withholding and MATURE-only kappa;
9. 100-window/10-session minimum on regression population;
10. deterministic Spearman midranks/null behavior;
11. exact `random.Random(0).choices(sessions, k=len(sessions))` sampling and invalid-draw continuation;
12. 200,000 valid-draw requirement / 1,000,000 attempt cap;
13. rank-deficient full sample and bootstrap paths;
14. direct-host and pooler project-ref verification plus rejection of wrong project/restore/local DSNs;
15. exact reader identity, six-table SELECT, zero writes, permissive full-read policy, and zero applicable restrictive policies;
16. evaluated receipt exact schema/canonical hash/filename;
17. BLOCKED receipt exact schema without fabricated cells/run identity;
18. exact execution revision equality across authorized env, `RENDER_GIT_COMMIT`, and `git rev-parse HEAD`;
19. dashboard freshness rule and `INVALID` precedence as a pure contract test if represented in V-1B utilities;
20. no imports/write paths that create production/SIM/broker authority.

---

## 24. Sequencing and merge gate

Order only:

```text
V-1A documentation PR
-> fresh independent exact-head review
-> all required checks green
-> zero unresolved material findings
-> Owner merge
-> V-1B implementation under exact file boundary
-> independent final-head review / green checks
-> Owner merge
-> conditional migration 033 only if required, production project only
-> runtime project/revision/reader/full-read proof
-> one-shot official evaluation
-> evaluated or BLOCKED immutable receipt
-> separate documentation-only receipt publication PR if evaluated
-> Owner merge of official evaluated receipt
-> ChatGPT Pro receipt audit
-> only then possible V-1C decision
-> separate future V-2 decision if warranted
```

Do not merge V-1A while any required check is not green or any P1/P2/material review finding remains unresolved on the exact final head.

---

## 25. Frozen conclusion

Volatility becomes ATOM’s primary **research evaluation target** without relabeling directional evidence or altering production mathematics.

V-1B is a deterministic, read-only, lineage-preserving, persistence-adjusted falsification scorecard.

Owner merge of V-1A authorizes V-1B only.

**V-1C: BLOCKED.**  
**V-2: BLOCKED.**