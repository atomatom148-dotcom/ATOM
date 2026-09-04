# V-1A — Volatility-First Research and Transition Freeze

**Decision ID:** `ATOM-V1A-VOLATILITY-FIRST-FREEZE-1`  
**Status:** PROPOSED CONTROLLING FREEZE — documentation only until Owner merge  
**Program:** ATOM V9  
**Author of record:** ChatGPT Pro  
**Owner authority:** Owner retains final merge, infrastructure, deployment, risk, broker, order, and capital authority.  
**V-1B implementation owner:** Codex by default under the controlling governance law.  
**V-1B job identity:** `ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1`  
**Adoption base:** `main` at `ba702d510a7c9b535c96ab4c8c4325f2920d2eda`.

---

## 1. Objective, authority, and supersession

ATOM changes its primary **research evaluation target** from directional hit rate to forecasted movement magnitude / volatility.

The governing research question becomes:

> How large is the coming move, how well calibrated is that magnitude forecast, and does the forecast contain information beyond simple volatility persistence?

Direction remains secondary evidence. Existing directional forecasts, outcomes, receipts, lineage, and immutable evidence are not deleted, rewritten, relabeled, or invalidated.

For V-1 subject matter only, this freeze supersedes conflicting metric, phase, dashboard, population, statistics, migration, receipt, and V-2-outline choices in `docs/drafts/v-1-volatility-target-program-DRAFT.md` and the saved pre-adoption `ATOM_V1_VOLATILITY_FIRST_TRANSITION_FREEZE.md`. Those remain historical/scouting material and carry no authority after Owner merge of this file.

Nothing here supersedes production V9 mathematics, SIM mathematics, broker/account/order boundaries, live-capital boundaries, immutable evidence law, or ATOM AI-role/governance law.

Owner merge of V-1A authorizes **V-1B only** within the exact boundary below. It does not authorize V-1C or V-2.

---

## 2. Phase-pointer relationship

V-1 is a read-only research track and **does not take, replace, advance, or edit the repository active phase pointer**.

No `AGENTS.md`, `PHASES.md`, `FREEZE.md`, or `SIMULATION_FREEZE.md` pointer change is authorized by V-1A or V-1B. Whatever active pointer is controlling when V-1B executes remains controlling for production/simulator work.

V-1B may run alongside that pointer only when it does not mutate, delay, contaminate, or reinterpret the V-1 evidence population or any active production/SIM phase.

---

## 3. Exact forecasters, horizons, and lineage law

V-1 evaluates exactly six horizons independently:

```text
30S
1M
5M
15M
30M
1H
```

There are exactly **12 inferential cells**: one FAMILY-VOL lineage and one V9-VOL lineage per horizon. Distinct model/cohort lineages are never pooled.

### 3.1 FAMILY-VOL identity

For each horizon, the only FAMILY-VOL candidate lineage is exactly:

```text
quant_id        = q3_volatility
formula_version = realized-volatility-v1
symbol          = COIN
horizon         = <that canonical horizon>
```

The receipt records the complete tuple `(quant_id, formula_version, symbol, horizon)` verbatim.

Any row with another family identity is outside V-1 and cannot enter counts, persistence, metrics, regression, or bootstrap.

### 3.2 V9-VOL identity

V9 evidence preserves the existing E-1 cell identity exactly:

```text
(v3_model_version, symbol, horizon, cohort_id, cohort_hash)
```

For each horizon, select **one** V9 lineage before reading outcomes or computing any metric:

1. enumerate all `evidence_origin = PRODUCTION` V9 forecast identities at that horizon whose forecast publication/proof is admissible at the frozen as-of boundary in §5;
2. for each identity compute only its greatest admissible forecast `cutoff_at` not later than the frozen as-of boundary;
3. choose the identity with the greatest such cutoff;
4. if tied, choose the lexicographically smallest UTF-8 tuple `(v3_model_version, symbol, horizon, cohort_id, cohort_hash)`.

No outcome value, volatility value, return, metric, classification, sample size, or kappa is permitted in this lineage-selection rule.

The exact selected tuple is receipted. Every other V9 lineage is excluded before inference and counted only in `n_unselected_lineage_rows` for audit.

This deterministic one-lineage-per-horizon rule preserves E-1 lineage separation while retaining the frozen 12-cell multiplicity budget.

---

## 4. Frozen targets and exclusions

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

A usable predicted volatility must be finite and **strictly greater than 0**. A finite zero or finite negative prediction is excluded and counted as `n_nonpositive_prediction_excluded`; it is not folded into null/non-finite accounting.

A realized magnitude must be finite and may equal exactly `0`. Zero realized movement is valid volatility evidence and is not a directional tie.

No imputation is permitted.

---

## 5. Deterministic official evaluation population

V-1B has exactly one official evaluation population under this decision.

### 5.1 Adoption instant and frozen evaluation session

`v1a_adopted_at` is the GitHub committer timestamp of the Owner merge commit that merges this V-1A freeze into `main`.

`evaluation_session` is the most recent **fully completed regular XNYS session** whose official 16:00 America/New_York close is less than or equal to `v1a_adopted_at`.

`evaluation_as_of_at` is exactly that session's 16:00:00 America/New_York close represented in UTC.

If the Owner merge occurs before the current session closes, that in-progress session is excluded. Half-days and non-regular XNYS sessions are excluded. No operator-selected later as-of is permitted.

### 5.2 Database snapshot and publication boundary

The official scorecard runs in one read-only `REPEATABLE READ` database transaction/snapshot for the entire evidence read.

A forecast/outcome/proof is inside the official population only when:

- its immutable forecast cutoff is `<= evaluation_as_of_at`;
- its required outcome is resolved by `evaluation_as_of_at`;
- its required publication/commit-proof observation timestamp is `<= evaluation_as_of_at`;
- it satisfies the existing proof seam and every other frozen admissibility rule.

Evidence or proof published after `evaluation_as_of_at` is excluded even if its market cutoff occurred earlier. This prevents later backfill/publication from changing the official population.

### 5.3 Session-date rule

For each selected lineage, the candidate session set is the sorted unique America/New_York calendar dates present among its admissible forecast rows satisfying §5.2 and ending no later than `evaluation_session`.

Every such date is included. No date may be manually added, removed, skipped, shortened, sampled, or retried based on outcomes or metrics.

Within each date, the full target interval must remain inside regular 09:30–16:00 America/New_York.

The receipt records the exact ordered session-date array for each cell.

### 5.4 Run identity

Before outcomes are scored, build `run_identity_body` from exactly:

```json
{
  "decision_id": "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1",
  "job_id": "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1",
  "v1a_merge_sha": "<40 lowercase hex>",
  "evaluation_session": "YYYY-MM-DD",
  "evaluation_as_of_at": "YYYY-MM-DDTHH:MM:SS.ffffffZ",
  "selected_lineages": "<12 identities in canonical cell order>"
}
```

`run_identity = sha256(canonical_json(run_identity_body))` using the canonical JSON rules in §13.

The selected lineages and run identity may not change on a rerun under this decision.

### 5.5 Rerun and publication policy

Exactly one receipt may become `OFFICIAL` for this `run_identity`.

A local rerun is allowed only for reproducibility. It must use the same V-1A merge SHA, as-of boundary, selected lineages, database/project, code version, and frozen mathematics. A rerun may not expand the population or create a second official attempt.

If a rerun disagrees on any substantive field under `cells`, `authority_proof`, `evaluation_session`, `evaluation_as_of_at`, or `run_identity`, V-1B overall status becomes `INVALID`, no competing receipt may be published, and a documentation-first amendment is required.

Once an Owner-merged official receipt exists for this `run_identity`, no different receipt for the same run identity may be published. Replacing or overwriting an official receipt is forbidden.

---

## 6. Window selection

Reuse E-1 evidence selection exactly unless this freeze states a volatility-specific override:

- deterministic ordering by `(session_date, cutoff_at, immutable_record_identity)`;
- horizon-spaced non-overlapping windows;
- selection restarts each session;
- each horizon and selected lineage independent;
- no imputation;
- exclusions counted;
- proof/admissibility comes only from the existing publication-proof seams.

FAMILY-VOL uses the existing `VOLATILITY_FORECAST` / `VOLATILITY_OUTCOME` publication-proof seam.

V9-VOL uses the existing V4 forecast/outcome proof seam.

---

## 7. Complete causal-kappa reconstruction

V-1B must not read a latest/current V4C state and must not add a V4C-state database privilege merely to obtain kappa.

For each selected V9-VOL forecast `f`, reconstruct kappa from existing V4 forecast/outcome evidence using the frozen V4C calibration functions unchanged.

### 7.1 Exact kappa evidence scope

Only V4 pairs matching `f`'s exact selected V9 identity may contribute:

```text
v3_model_version = f.v3_model_version
symbol           = f.symbol
horizon          = f.horizon
cohort_id         = f.cohort_id
cohort_hash       = f.cohort_hash
```

Each contributing pair must be admissible under the existing V4 proof seam, have finite required inputs, have forecast `cutoff_at < f.cutoff_at`, and have outcome `target_resolved_at < f.cutoff_at`.

Equality to `f.cutoff_at` is not prior and is excluded.

### 7.2 Exact non-overlap and validation split

For the strictly-prior governed pairs:

1. apply the existing V4C governed-evidence filter unchanged;
2. apply the existing V4C `select_non_overlapping(...)` selection unchanged;
3. order selected pairs by `(forecast.cutoff_at, forecast_record_id)`;
4. set `split = max(0, len(selected) - 250)`;
5. `calibration_pairs = selected[:split]`;
6. `validation_pairs = selected[split:]` — the latest 250 selected pairs are withheld exactly as in the existing V4C pipeline;
7. set `calibration_end` to the last calibration-pair cutoff when calibration pairs exist, otherwise to the strict causal boundary immediately before `f.cutoff_at`;
8. build the existing `CalibrationObservation` values from `calibration_pairs` only;
9. call the existing frozen `calibrate_scale(...)` mathematics unchanged.

The withheld latest 250 validation pairs never enter kappa fitting.

### 7.3 MATURE-only rule

`kappa(f)` is usable only when the reconstructed `ScaleResult.status` is exactly `MATURE` and `kappa` is finite and strictly positive.

`PROVISIONAL`, `UNAVAILABLE`, null, non-finite, zero, or negative kappa is treated as unavailable. The target V9 window is excluded and counted as `n_kappa_unavailable`.

No fallback kappa, current state, cross-cohort state, neighboring horizon, interpolation, or forward-filled scale is permitted.

---

## 8. Persistence benchmark and regression population

For each inferential cell, selected valid volatility windows are ordered by cutoff across the frozen session population.

```text
persist_1(w)  = realized_volatility_bps of the immediately prior selected valid window
persist_20(w) = arithmetic mean realized_volatility_bps of the prior 20 selected valid windows
```

Every component of `persist_20(w)` must have outcome resolution/proof available no later than `w.cutoff_at`.

The first 20 selected valid windows and any later window lacking 20 causally available prior realized magnitudes are excluded from benchmark-relative inference and counted as `n_persist20_unavailable`.

The rows remaining after that exclusion are the **regression population**.

Receipt exactly:

```text
n_regression_windows
n_regression_sessions
```

where `n_regression_sessions` is the number of distinct XNYS session dates represented by regression-population rows.

The evidence minimum applies **only to this actual regression population**:

```text
n_regression_windows  >= 100
n_regression_sessions >= 10
```

`n_windows` / `n_sessions` over pre-persistence valid windows remain descriptive and cannot satisfy the inferential minimum.

---

## 9. Frozen metrics and deterministic descriptive behavior

For each selected cell report exactly:

```text
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
```

Definitions:

```text
mae_bps     = mean(abs(predicted_volatility_bps - realized_volatility_bps))
level_ratio = median(predicted_volatility_bps) / median(realized_volatility_bps)
coverage_90 = mean(realized_volatility_bps <= 1.6448536269514722 * predicted_volatility_bps)
```

If `median(realized_volatility_bps) == 0`, `level_ratio = null`.

Mincer-Zarnowitz descriptive regression:

```text
realized_volatility_bps = mz_a + mz_b * predicted_volatility_bps + error
```

`mz_r2` is ordinary coefficient of determination.

### 9.1 Spearman rule

For `rank_corr` and `persist_rank_corr`:

1. use only paired finite observations in the metric's frozen population;
2. sort numeric values ascending;
3. tied values receive the arithmetic mean of their one-based rank positions (midrank);
4. compute ordinary Pearson correlation of the two rank vectors using binary64 arithmetic;
5. if fewer than two pairs exist, or either rank vector has zero variance, return JSON `null`;
6. no random tie-breaking, jitter, epsilon, imputation, or alternate rank method is allowed.

A null descriptive rank correlation does not itself create `INVALID` and cannot create `INFORMATIVE`.

---

## 10. Sole inferential model and bootstrap

The only V-1 classification statistic is `enc_b` in:

```text
realized_volatility_bps
    = intercept
    + persistence_coefficient * persist_20
    + enc_b * predicted_volatility_bps
    + error
```

Fit ordinary least squares with an intercept over the full regression population.

### 10.1 Session-resampled OLS-refit loop

V-1B explicitly authorizes the new `quant/volatility_scorecard.py` module to perform this pure in-memory loop; this is not a modification of E-1 or V4C code:

- cluster = complete XNYS session date;
- RNG = CPython `random.Random(0)`, seeded once per cell;
- draw `n_regression_sessions` session identities with replacement per attempt;
- duplicate all rows belonging to a session each time that session is drawn;
- refit the exact OLS model on the resulting rows;
- a draw is valid only if the refit design matrix has full column rank and `enc_b` is finite.

The implementation must obtain exactly **200,000 valid bootstrap refits**.

Rank-deficient or non-finite attempts are discarded, counted as `bootstrap_invalid_draws`, and still consume RNG state. Continue drawing until either:

```text
bootstrap_valid_draws = 200000
```

or

```text
bootstrap_attempted_draws = 1000000
```

If one million attempts are reached before 200,000 valid draws, the cell is `INVALID`. No partial interval is permitted.

Percentile intervals use the existing E-1 percentile rule over the 200,000 valid `enc_b` values, sorted ascending:

```text
lower_index = floor((1 - level) / 2 * (B - 1))
upper_index = ceil((1 + level) / 2 * (B - 1))
B           = 200000
levels      = 0.999 and 0.95
```

No alternate bootstrap, standard error, t test, robust covariance, ridge fallback, pseudoinverse fallback, or model substitution is authorized.

---

## 11. Cell classification and precedence

Classification precedence is exact:

1. **Protocol/identity/causality/proof defect:** `INVALID`, regardless of sample size.
2. Otherwise, if `n_regression_windows < 100` or `n_regression_sessions < 10`: `INSUFFICIENT`; do not bootstrap.
3. Otherwise, if the full-sample OLS is rank-deficient/non-finite or the valid-bootstrap requirement in §10.1 fails: `INVALID`.
4. Otherwise, if the lower endpoint of `enc_b_ci_0999` is strictly greater than `0`: `INFORMATIVE`.
5. Otherwise: `NOISE`.

No MAE, rank correlation, level ratio, coverage, MZ coefficient, or persistence correlation may independently change classification.

There are exactly 12 inferential cells. With the one-sided positive screen induced by a two-sided 0.999 interval, report-only null expectation is:

```text
12 * 0.0005 = 0.006 expected false INFORMATIVE cells
```

No post-result multiplicity substitute is permitted.

No cell may be called tradeable, profitable, production-ready, or sufficient for capital.

---

## 12. V-1B exact implementation boundary

After Owner merge of V-1A, V-1B implementation is authorized only under job `ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1`.

### 12.1 Exhaustive repository file list

The only unconditional V-1B implementation files are:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
```

The only conditional third file is:

```text
migrations/033_authorize_v1_volatility_scorecard_reader.sql
```

and it is authorized only if the pre-implementation privilege check proves `atom_e1_scorecard_reader` lacks the exact FAMILY-VOL access required by §14.

No modification is authorized to:

```text
quant/evidence_scorecard.py
quant/v9_v4c_predictive.py
quant/evidence_outbox.py
quant/web.py
AGENTS.md
PHASES.md
FREEZE.md
SIMULATION_FREEZE.md
```

or any other unlisted path.

V-1B must import/reuse existing E-1 and V4C primitives without editing them. If implementation requires any unlisted repository path, stop `BLOCKED` and return for a documentation-first amendment.

If migration ordinal `033` is no longer collision-free at V-1B implementation time, do not renumber or create another migration under this freeze; stop `BLOCKED` for an amendment that names the replacement path.

---

## 13. Exact receipt schema, canonicalization, and publication

V-1B produces one top-level JSON object with **exactly** these keys and types:

```text
schema_version                 string = "ATOM-V1B-RECEIPT-1"
decision_id                    string = "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1"
job_id                         string = "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1"
contract_path                  string = "docs/v-1a-volatility-first-freeze.md"
code_version                   string
verified_main_sha              string, exactly 40 lowercase hex
v1a_merge_sha                  string, exactly 40 lowercase hex
run_identity                   string, exactly 64 lowercase hex
evaluation_session             string, YYYY-MM-DD
evaluation_as_of_at            string, UTC RFC3339 microseconds: YYYY-MM-DDTHH:MM:SS.ffffffZ
generated_at_utc               string, UTC RFC3339 microseconds: YYYY-MM-DDTHH:MM:SS.ffffffZ
reader_identity                string = "atom_e1_scorecard_reader"
database_identity              object defined below
authority_proof                object defined below
bootstrap                      object defined below
cells                          array of exactly 12 cell objects defined below
overall_status                 string: PASS | FAIL | INVALID | BLOCKED
overall_reason_codes           array[string], sorted unique UTF-8 ascending
scouting_disclosure            array[string], exact §16 disclosure lines in listed order
read_only                      boolean = true
forecast_writes                integer = 0
outcome_writes                 integer = 0
evidence_writes                integer = 0
receipt_sha256                 string, exactly 64 lowercase hex
```

`database_identity` has exactly:

```text
supabase_project_ref           string = "afyiydxbjgzaiswnbcyj"
database_name                  string = "postgres"
```

`authority_proof` has exactly:

```text
current_user                   string
schema_public_usage            boolean
schema_public_create           boolean
six_tables_select              object[table_name -> boolean]
six_tables_insert              object[table_name -> boolean]
six_tables_update              object[table_name -> boolean]
six_tables_delete              object[table_name -> boolean]
six_tables_truncate            object[table_name -> boolean]
six_tables_rls_enabled         object[table_name -> boolean]
six_tables_reader_policy_ok    object[table_name -> boolean]
read_only_transaction          boolean
verification_status            string = PASS | FAIL
```

`bootstrap` has exactly:

```text
resamples_required             integer = 200000
max_attempts                   integer = 1000000
seed                           integer = 0
interval_levels                array[number] = [0.999, 0.95]
cluster                        string = "XNYS_SESSION_DATE"
```

Each `cells` object has exactly:

```text
cell_order                     integer 0..11
forecaster                     string = FAMILY-VOL | V9-VOL
horizon                        string = one canonical horizon
lineage_identity               object
session_dates                  array[string YYYY-MM-DD], ascending unique
evidence_min_cutoff_at         string RFC3339 microseconds UTC | null
evidence_max_cutoff_at         string RFC3339 microseconds UTC | null
n_input                        integer >= 0
n_unselected_lineage_rows      integer >= 0
n_inadmissible                 integer >= 0
n_non_rth                      integer >= 0
n_overlap_excluded             integer >= 0
n_null_or_nonfinite_excluded   integer >= 0
n_nonpositive_prediction_excluded integer >= 0
n_kappa_unavailable            integer >= 0
n_windows                      integer >= 0
n_sessions                     integer >= 0
n_persist20_unavailable        integer >= 0
n_regression_windows           integer >= 0
n_regression_sessions          integer >= 0
mae_bps                        number | null
rank_corr                      number | null
level_ratio                    number | null
coverage_90                    number | null
mz_a                           number | null
mz_b                           number | null
mz_r2                          number | null
persist_rank_corr              number | null
enc_b                          number | null
enc_b_ci_0999                  array[number, number] | null
enc_b_ci_095                   array[number, number] | null
bootstrap_attempted_draws      integer >= 0
bootstrap_valid_draws          integer >= 0
bootstrap_invalid_draws        integer >= 0
classification                 string = INFORMATIVE | NOISE | INSUFFICIENT | INVALID
reason_codes                   array[string], sorted unique UTF-8 ascending
```

FAMILY-VOL `lineage_identity` has exactly string keys `quant_id`, `formula_version`, `symbol`, `horizon`.

V9-VOL `lineage_identity` has exactly string keys `v3_model_version`, `symbol`, `horizon`, `cohort_id`, `cohort_hash`.

### 13.1 Canonical cell ordering

`cells` order is exactly:

```text
0 FAMILY-VOL 30S
1 FAMILY-VOL 1M
2 FAMILY-VOL 5M
3 FAMILY-VOL 15M
4 FAMILY-VOL 30M
5 FAMILY-VOL 1H
6 V9-VOL    30S
7 V9-VOL    1M
8 V9-VOL    5M
9 V9-VOL    15M
10 V9-VOL   30M
11 V9-VOL   1H
```

### 13.2 Canonical JSON and digest boundary

All JSON numbers must be finite; NaN and Infinity are forbidden.

Canonical JSON is UTF-8 JSON with:

```text
sort_keys = true
separators = (",", ":")
ensure_ascii = false
allow_nan = false
```

Array order is preserved exactly as frozen above.

To compute `receipt_sha256`:

1. construct the complete receipt **without** the `receipt_sha256` key;
2. canonicalize that object exactly as above;
3. SHA-256 the UTF-8 bytes;
4. lowercase hexadecimal digest becomes `receipt_sha256`;
5. add `receipt_sha256` as the final logical field; the digest field is not inside its own hash boundary.

### 13.3 Filename grammar

The only publishable filename is:

```text
docs/v-1b-volatility-scorecard-receipt-<evaluation_session>-<run_identity>-<receipt_sha256>.json
```

where both hashes are exactly 64 lowercase hexadecimal characters and `evaluation_session` is `YYYY-MM-DD`.

### 13.4 Publication and latest-receipt selection

Runtime/local generation is not publication.

Publication is a separate documentation-only PR adding exactly one immutable receipt file matching §13.3. Owner merge of that receipt PR is the publication event.

For this decision/run identity, the first Owner-merged SHA-valid receipt is the unique `OFFICIAL` receipt. A second different receipt for the same run identity is forbidden and makes selection ambiguous/fail-closed until a documentation-first amendment resolves it.

Any later consumer searching the deployed repository must:

1. match the exact filename grammar;
2. parse against this exact schema;
3. recompute and verify `receipt_sha256`;
4. require the exact decision/job/run identity;
5. require exactly one Owner-merged valid receipt for that run identity.

Zero matches => `NO DATA`. More than one different valid receipt for the same run identity => fail closed as `NO DATA` plus an audit error; it must not choose by filesystem order, mtime, lexicographic hash, or metric value.

---

## 14. Exact database, migration, and runtime authority

The only database/project authorized for V-1B is:

```text
Supabase project ref: afyiydxbjgzaiswnbcyj
Database:             postgres
Purpose:              ATOM production evidence database
Reader role:          atom_e1_scorecard_reader
```

No V-1B migration or scorecard query may be applied to the isolated simulator project, a restore/PITR project, development database, local database as authority evidence, or any other Supabase project.

### 14.1 Conditional migration executor

If and only if the two volatility tables lack exact reader access, `migrations/033_authorize_v1_volatility_scorecard_reader.sql` may be applied once to project `afyiydxbjgzaiswnbcyj`, database `postgres`, by an Owner-controlled Supabase migration/SQL session whose `current_user` is exactly `postgres`.

The migration must refuse execution unless `current_user = 'postgres'` and `current_database() = 'postgres'`.

It may grant only the minimum existing-reader authority necessary for:

```text
public.volatility_forecasts
public.volatility_forecast_outcomes
```

No new role, password, membership, writer, function, service, source, database, broad grant, default privilege, or application elsewhere is authorized.

### 14.2 Six-table runtime verification

Before reading evidence, and again immediately before receipt construction in the same read-only run, V-1B must verify exact reader identity and full-read authority for all six evidence tables:

```text
public.forecasts
public.forecast_outcomes
public.atom_v9_v4_forecasts
public.atom_v9_v4_outcomes
public.volatility_forecasts
public.volatility_forecast_outcomes
```

Required proof:

- `current_user == 'atom_e1_scorecard_reader'`;
- `USAGE` on schema `public` is true;
- `CREATE` on schema `public` is false;
- `SELECT` is true on each of the six tables;
- `INSERT`, `UPDATE`, `DELETE`, and `TRUNCATE` are false on each of the six tables;
- RLS is enabled on each table where repository law requires RLS;
- an exact reader SELECT policy permits full read on each of the six tables;
- the connection/transaction is read only;
- no fallback credential is attempted.

Any failed authority check => overall `BLOCKED` before evidence inference. The exact proof booleans are included in `authority_proof` in the official receipt when the run succeeds far enough to construct a receipt.

---

## 15. V-1B accountable job, environment, rollback, and overall verdict

### 15.1 Accountability

```text
Job ID:                   ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1
Architecture/final audit: ChatGPT Pro
Implementation owner:     Codex by default under governance
Merge/infra owner:        Owner
```

No implementation agent may self-promote V-1B, V-1C, or V-2.

### 15.2 Execution environment

The authorized one-shot execution environment is the existing Render benchmark worker:

```text
service:        atom-h2d3-benchmark
credential env: ATOM_E1_SCORECARD_READONLY_DATABASE_URL
reader:         atom_e1_scorecard_reader
project:        afyiydxbjgzaiswnbcyj
database:       postgres
```

The Owner may set the one-shot worker start command after the V-1B implementation PR is merged and any required migration is applied/verified.

No production web-service deploy, new worker, new service, new credential, second database connection identity, or V9/SIM runtime activation is authorized.

### 15.3 Rollback target

The V-1B repository rollback target is the exact Owner-merged V-1A `main` SHA immediately before the V-1B implementation merge.

Operational rollback is:

1. stop/suspend the V-1B one-shot benchmark command;
2. restore `atom-h2d3-benchmark` to its pre-V-1B start-command/environment state;
3. preserve every generated/published receipt as immutable evidence;
4. do not delete or rewrite evidence;
5. do not revoke database grants through ad hoc SQL. Any privilege rollback requires its own reviewed migration/amendment.

### 15.4 Overall status

Overall V-1B status is exactly one of:

- `BLOCKED` — required repository/database/environment authority is missing or a required boundary cannot be satisfied; no inferential conclusion.
- `INVALID` — the run executes but any selected cell has a protocol/identity/causality/proof/statistical-contract `INVALID`, or reproducibility under §5.5 fails.
- `PASS` — not BLOCKED/INVALID and at least one of the 12 cells is `INFORMATIVE`.
- `FAIL` — not BLOCKED/INVALID and zero cells are `INFORMATIVE`; this includes all-NOISE, mixed NOISE/INSUFFICIENT, or all-INSUFFICIENT outcomes. Reason codes must distinguish `NO_INCREMENTAL_INFORMATION` from `INSUFFICIENT_EVIDENCE`.

PASS does not authorize production use. FAIL does not delete evidence. INVALID/BLOCKED requires correction or amendment before any downstream phase.

---

## 16. Preregistration disclosure

The official receipt includes these exact disclosure strings in this order:

1. `2026-09-03 pooled overlapping-window Q3 volatility correlations, level ratios, and slopes were inspected.`
2. `Q3 appeared to carry rank information while its absolute level was horizon-miscalibrated.`
3. `An overlapping previous-window persistence calculation was inspected and recognized as overlap-contaminated.`
4. `No E-1-selected non-overlapping session-clustered enc_b statistic under this exact contract had been adopted as controlling evidence before V-1A.`
5. `No V9-VOL causal-kappa enc_b statistic under this exact contract had been adopted as controlling evidence before V-1A.`

If independent review establishes that the exact inferential statistic on the exact frozen population was inspected before adoption, the affected cell is `INVALID` for confirmatory claims and is preserved only as exploratory evidence.

---

## 17. Frozen future dashboard source and freshness — V-1C still unauthorized

This section freezes a future source contract only. It does **not** authorize V-1C.

If V-1C is later separately opened, the visible card title is exactly:

```text
V9 VOLATILITY ACCURACY
```

It may source only V9-VOL values from the unique Owner-merged, SHA-valid official V-1B receipt selected under §13.4. It may not query live evidence tables, recompute scorecard statistics in the web process, use FAMILY-VOL values under a V9 label, or reuse directional accuracy fields.

Rows are exactly:

```text
MAE BPS
RANK CORR
LEVEL RATIO
90% COVERAGE
STATUS
```

Columns remain exactly:

```text
30S 1M 5M 15M 30M 1H
```

### 17.1 STATUS precedence and freshness

For each V9-VOL horizon:

1. if no unique valid official receipt exists: `NO DATA`;
2. if the receipted cell classification is `INVALID`: display `INVALID` — staleness may never hide it;
3. otherwise compute the most recent fully completed regular XNYS session before render time;
4. if receipt `evaluation_session` is earlier than that completed session: display `STALE`;
5. otherwise display the receipted classification exactly: `INFORMATIVE`, `NOISE`, or `INSUFFICIENT`.

Freshness is based on the receipt's **evaluation session**, not `evidence_max_cutoff_at`. A positive horizon naturally has its last eligible cutoff before session close; that fact alone never makes the receipt stale.

Metric cells are blank for `NO DATA`. For `STALE`, receipted metric values remain visible and are not replaced with zeroes.

Directional wins/losses/accuracy percentages may never populate this card.

---

## 18. V-1C gate — explicitly BLOCKED now

V-1C remains `BLOCKED` until all of the following occur in order:

1. V-1A Owner merge;
2. V-1B implementation PR on the exact §12 surface independently reviewed, green, and Owner-merged;
3. conditional migration 033, if required, applied only to the exact §14 database and verified;
4. V-1B one-shot scorecard run under the exact §15 environment;
5. official immutable receipt publication PR independently reviewed, green, and Owner-merged;
6. ChatGPT Pro audits the published receipt against this freeze and explicitly authors/opens V-1C authority.

No implementation agent may infer V-1C authority from V-1A or a V-1B PASS.

---

## 19. V-2 — explicitly not authorized

The V-2 hypothesis and 20-session outline in the prior draft are not adopted.

V-2 requires its own future protected-boundary freeze after V-1B evidence is published and audited.

A V-1B PASS buys only the right for ChatGPT Pro and the Owner to decide whether to author V-2. It does not authorize:

- production volatility-primary synthesis;
- Q3 insertion into signed family synthesis;
- family reweighting;
- volatility gating or sizing;
- options trading;
- broker/account/order changes;
- production Gamma activation;
- any change to `final_bps`;
- any live-capital action.

---

## 20. Production, simulator, directional-evidence, and deployment boundary

V-1A/V-1B do not change or authorize changes to:

- `final_bps`;
- current V9 signed synthesis;
- family signs or production weights;
- Q3 production formula;
- V4C production state;
- production Gamma activation;
- SIM entry rules;
- SIM exit/resolution rules;
- SIM P&L mathematics;
- broker/account/order endpoints;
- live capital;
- options execution;
- Level II mathematical use;
- existing immutable directional forecasts/outcomes/receipts;
- production web deployment;
- any market-data source.

Directional forecasting may continue running unchanged during V-1 so lineage is preserved.

---

## 21. Minimum V-1B tests

Within `tests/test_volatility_scorecard.py`, V-1B must at minimum prove:

1. exactly six canonical horizons;
2. exact FAMILY and V9 lineage separation and deterministic lineage selection;
3. no distinct lineage pooling;
4. frozen merge-time evaluation-session/as-of derivation;
5. late-published evidence after `evaluation_as_of_at` is excluded;
6. E-1 non-overlap/session restart parity;
7. finite zero/negative predictions increment `n_nonpositive_prediction_excluded`;
8. zero realized movement remains valid;
9. exact causal-kappa cohort/horizon scope;
10. strict `< f.cutoff_at` kappa boundary;
11. latest-250 validation withholding;
12. MATURE-only kappa acceptance; PROVISIONAL/UNAVAILABLE excluded;
13. persistence uses only causal prior realized magnitudes;
14. 100-window/10-session minimum applies to `n_regression_windows`/`n_regression_sessions`;
15. deterministic Spearman midranks and null behavior;
16. full-sample rank-deficiency path;
17. rank-deficient bootstrap attempts are discarded/counted while RNG advances;
18. exactly 200,000 valid refits or INVALID at one million attempts;
19. deterministic seed 0 and frozen percentile indices;
20. pure persistence with no incremental forecast information cannot classify INFORMATIVE;
21. constructed incremental information exercises the positive classification path;
22. exact receipt schema/type rejection for extra/missing/wrong-type fields;
23. RFC3339 timestamp grammar;
24. canonical JSON/hash excludes only `receipt_sha256`;
25. filename grammar and unique-official selection;
26. all six evidence tables SELECT yes and write privileges no;
27. exact reader identity required; fallback credential refused;
28. migration 033 text, if present, names only project/database boundary and exact two-table grant/policies;
29. no write, SIM, broker, order, production-math, web, pointer, or deployment path is introduced.

No test requirement authorizes a path outside §12.

---

## 22. V-1B sequence and stop conditions

Execute only in this order after V-1A Owner merge:

```text
V-1B Codex implementation on exhaustive §12 surface
-> independent exact-head review
-> all required checks green
-> zero material findings/threads
-> Owner merge
-> if and only if required, apply migration 033 to §14 target as postgres
-> verify six-table runtime authority
-> Owner sets one-shot atom-h2d3-benchmark command
-> run official frozen population once
-> construct local canonical receipt
-> verify receipt/hash/reproducibility
-> separate documentation-only receipt publication PR
-> independent exact-head review + green checks
-> Owner merge receipt
-> ChatGPT Pro receipt audit
-> only then decide whether to author V-1C
-> V-2 remains a separate future decision
```

Stop `BLOCKED` if V-1B requires:

- any unlisted repository path;
- migration ordinal other than the exact conditional 033 path;
- a database/project other than §14;
- a database executor other than the Owner-controlled `postgres` session;
- new role/credential/service/source;
- broader reader authority;
- production V9 or SIM mathematics;
- broker/account/order/capital authority;
- dashboard implementation;
- changed target/metric/bootstrap/population/lineage law;
- evidence deletion, rewrite, backfill, or relabeling.

Any such requirement needs a new documentation-first amendment.

---

## 23. Merge gate for this V-1A PR

This PR remains documentation-only.

Before Owner merge of V-1A:

- final diff must remain exactly `docs/v-1a-volatility-first-freeze.md`;
- independent review must cover the exact final head;
- all required checks must be green;
- zero unresolved material P1/P2 findings or material threads may remain;
- no V-1B implementation, migration execution, environment change, scorecard run, receipt publication, V-1C, or V-2 work may precede Owner merge.

**Frozen conclusion:** volatility/magnitude becomes ATOM's primary research evaluation target. Direction is preserved as secondary immutable evidence. V-1B is the only next phase authorized by Owner merge of V-1A. V-1C remains blocked behind implementation, official receipt publication, and ChatGPT Pro receipt audit. V-2 requires its own future freeze.
