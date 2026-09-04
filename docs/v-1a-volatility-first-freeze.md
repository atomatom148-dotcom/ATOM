# V-1A — Volatility-First Research and Transition Freeze

**Decision ID:** `ATOM-V1A-VOLATILITY-FIRST-FREEZE-1`  
**Status:** PROPOSED CONTROLLING FREEZE — documentation only until Owner merge  
**Program:** ATOM V9  
**Author of record:** ChatGPT Pro  
**Owner authority:** Owner retains final merge, deployment, infrastructure, risk, broker, and capital authority.  
**Implementation owner beneath this freeze:** Codex by default under the controlling governance law.  
**Adoption base:** `main` at `ba702d510a7c9b535c96ab4c8c4325f2920d2eda`.

---

## 1. Objective and supersession

ATOM changes its primary **research evaluation target** from directional hit rate to forecasted movement magnitude / volatility.

The governing research question becomes:

> How large is the coming move, how well calibrated is that magnitude forecast, and does the forecast contain information beyond simple volatility persistence?

Direction is preserved as secondary evidence. Existing directional forecasts, outcomes, receipts, lineage, and immutable evidence are not deleted, rewritten, relabeled, or invalidated.

This freeze supersedes, for V-1 subject matter only, the conflicting metric, phase, dashboard, and V-2-outline choices in `docs/drafts/v-1-volatility-target-program-DRAFT.md` and in the saved pre-adoption `ATOM_V1_VOLATILITY_FIRST_TRANSITION_FREEZE.md`. Those sources remain historical/scouting material and carry no authority after Owner merge of this file.

Nothing in this freeze supersedes production V9 mathematics, SIM mathematics, broker boundaries, immutable evidence law, E-1 evidence-selection law, or the ATOM AI-role/governance freezes.

---

## 2. Scope and horizons

V-1 evaluates exactly six horizons independently:

`30S`, `1M`, `5M`, `15M`, `30M`, `1H`.

No pooling across horizons is permitted for a metric, classification, bootstrap interval, or decision.

V-1 scores exactly two existing forecasters:

1. **FAMILY-VOL** — Q3 `forecast_volatility_bps` from the existing durable volatility forecast/outcome seam.
2. **V9-VOL** — calibrated V9 predictive dispersion derived from existing V9 forecast/outcome evidence and the frozen V4C calibration mathematics.

No new market-data source, forecast family, model fit, production writer, service, broker endpoint, or live-capital path is authorized.

---

## 3. Frozen targets

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

All inputs must be finite. Predicted volatility must be strictly positive. A zero realized move is valid evidence.

### 3.1 Causal kappa — exact access decision

V-1B **must not read a latest/current V4C state and must not add a new V4C-state database privilege** merely to obtain kappa.

For each V9 forecast `f`, V-1B reconstructs `kappa(f)` in memory by reusing the frozen V4C scale-calibration function over only admissible V9 forecast/outcome observations whose resolved evidence is causally available strictly before `f.cutoff_at` under the existing V4 evidence seam.

The implementation must preserve the frozen V4C math unchanged. It may create an incremental in-memory causal state for efficiency, but that state must be numerically equivalent to invoking the frozen calibration on the same strictly-prior eligible observations. No future observation may influence `kappa(f)`.

If no valid causal kappa exists for `f`, that window is excluded from V9-VOL metrics and counted as `n_kappa_unavailable`.

This closes the causal-kappa access question without a new role, new credential, new state table, or look-ahead read.

---

## 4. Evidence population and selection

Reuse E-1 evidence discipline exactly unless this freeze states a volatility-specific override:

- regular XNYS sessions only;
- the entire target interval must lie inside 09:30–16:00 America/New_York;
- deterministic ordering by session, cutoff, then immutable record identity;
- horizon-spaced non-overlapping selected windows;
- selection restarts each session;
- six horizons independent;
- no imputation;
- null/non-finite inputs excluded and counted;
- evidence/proof eligibility must use the existing publication-proof seams;
- session is the bootstrap cluster;
- 200,000 bootstrap resamples;
- deterministic seed `0`;
- report 0.999 and 0.95 percentile intervals.

Volatility-specific override: an exactly zero realized magnitude is valid and is not a directional tie.

FAMILY-VOL uses the existing `VOLATILITY_FORECAST` / `VOLATILITY_OUTCOME` publication-proof seam. V9-VOL uses the existing V4 forecast/outcome proof seam.

---

## 5. Persistence benchmark

Volatility persistence is the frozen baseline.

For each forecaster/horizon cell, selected windows are ordered by cutoff across sessions. For selected window `w`:

```text
persist_1(w)  = realized_volatility_bps of the immediately prior selected window
persist_20(w) = arithmetic mean realized_volatility_bps of the prior 20 selected windows
```

Every component of `persist_20(w)` must have resolved causally no later than `w.cutoff_at`.

The first 20 selected windows, and any later window lacking 20 causally available prior realized magnitudes, are excluded from benchmark-relative inference and counted as `n_persist20_unavailable`.

No V-1 research credit is earned merely for repeating persistence.

---

## 6. Frozen metrics

For each `(forecaster, horizon)` cell, report these exact descriptive fields over valid selected windows:

```text
n_input
n_inadmissible
n_non_rth
n_overlap_excluded
n_null_or_nonfinite_excluded
n_kappa_unavailable                  # V9-VOL; 0 for FAMILY-VOL
n_windows
n_sessions
mae_bps
rank_corr
level_ratio
coverage_90
mz_a
mz_b
mz_r2
n_persist20_unavailable
persist_rank_corr
enc_b
enc_b_ci_0999
enc_b_ci_095
```

Definitions:

```text
mae_bps      = mean(abs(predicted_volatility_bps - realized_volatility_bps))
rank_corr    = Spearman(predicted_volatility_bps, realized_volatility_bps)
level_ratio  = median(predicted_volatility_bps) / median(realized_volatility_bps)
coverage_90  = mean(realized_volatility_bps <= 1.6448536269514722 * predicted_volatility_bps)
```

If `median(realized_volatility_bps) == 0`, `level_ratio` is JSON null and the condition is recorded; it is never converted to infinity or zero.

Mincer–Zarnowitz descriptive regression:

```text
realized_volatility_bps = mz_a + mz_b * predicted_volatility_bps + error
```

`mz_r2` is ordinary coefficient of determination for that regression.

Persistence-context field:

```text
persist_rank_corr = Spearman(persist_20, realized_volatility_bps)
```

over benchmark-relative windows only.

### 6.1 Sole inferential model

The only V-1 classification statistic is the forecast coefficient in:

```text
realized_volatility_bps
    = intercept
    + persistence_coefficient * persist_20
    + enc_b * predicted_volatility_bps
    + error
```

For each bootstrap resample, resample complete XNYS sessions with replacement, retain all benchmark-relative windows belonging to sampled sessions, refit the regression, and record `enc_b`.

`enc_b_ci_0999` and `enc_b_ci_095` are percentile intervals from exactly 200,000 such session-clustered refits using deterministic seed `0`.

If the design matrix is rank-deficient, the regression cannot be fit, or a required statistic becomes non-finite, the cell is `INVALID`; the implementation must not silently fall back to another estimator.

No MAE, rank correlation, level ratio, MZ coefficient, coverage value, or persistence correlation may independently create an `INFORMATIVE` classification.

---

## 7. Eligibility, classification, and statistical budget

Minimum evidence per forecaster/horizon cell:

```text
n_windows  >= 100
n_sessions >= 10
```

Classification is exactly:

- `INFORMATIVE` — the cell is valid and the lower endpoint of `enc_b_ci_0999` is strictly greater than `0`.
- `NOISE` — the cell is valid and eligible but the 0.999 interval touches or falls below `0`.
- `INSUFFICIENT` — either minimum evidence condition is not met.
- `INVALID` — protocol defect, causal violation, evidence-continuity defect, proof defect, rank-deficient/non-finite inference, changed frozen statistic, or other research-contract violation.

There are exactly 12 inferential cells: 2 forecasters × 6 horizons. With the one-sided positive screen induced by a two-sided 0.999 percentile interval, the preregistered expected false-`INFORMATIVE` count is `12 * 0.0005 = 0.006` under null calibration assumptions. This is report-only context; no alternate multiplicity correction may be substituted after results are seen.

No V-1 result may be called tradeable, profitable, production-ready, or sufficient to authorize capital.

---

## 8. V-1A phase decision

V-1A is **documentation only**.

Owner merge of this freeze authorizes only the next phase, **V-1B**, subject to the implementation boundary below.

V-1A does not authorize code, migration execution, dashboard edits, production activation, deployment, V-1C, or V-2.

---

## 9. V-1B — authorized next phase after V-1A merge

After V-1A is Owner-merged, Codex may implement the smallest read-only V-1 scorecard.

Preferred surface:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
```

The implementation must reuse, not fork, the existing E-1 window-selection/bootstrap primitives and frozen V4C calibration mathematics.

### 9.1 Database-access and migration decision

The existing `atom_e1_scorecard_reader` remains the only permitted database identity.

V9-VOL requires no new database grant beyond the existing V4 forecast/outcome evidence access because causal kappa is reconstructed from that evidence under §3.1.

FAMILY-VOL requires read access to exactly:

```text
public.volatility_forecasts
public.volatility_forecast_outcomes
```

If, at V-1B implementation time, `atom_e1_scorecard_reader` does not already have exact read/policy access to both tables, V-1B may include **one and only one** least-privilege migration using the next collision-free migration ordinal on current main. That migration may grant only schema `USAGE` if not already held, table `SELECT` on those two tables, and the exact permissive reader policies required for those two tables. It may not create a role, password, writer, function, service, source, broad table grant, or membership.

The migration must self-verify final authority and fail closed. If a collision-free ordinal or exact least-privilege grant cannot be achieved without broader authority, stop `BLOCKED` for a documentation-first amendment.

No migration is authorized merely for convenience if existing access is already sufficient.

---

## 10. Receipt construction and publication

Each V-1B run produces one canonical immutable receipt containing all 12 cells and at minimum:

- decision ID and contract path;
- code version;
- verified merged main SHA used by the scorecard;
- reader identity;
- run timestamp UTC;
- forecaster and horizon identities;
- all counts and exclusions from §6;
- all frozen descriptive metrics;
- both bootstrap intervals;
- classification;
- exact bootstrap resamples/seed/interval levels;
- evidence minimum/maximum cutoff timestamps per cell;
- scouting disclosure from §11;
- `read_only: true`;
- zero forecast/outcome/evidence writes;
- canonical JSON SHA-256 over the receipt body.

Canonical JSON uses sorted keys, compact separators, UTF-8, and forbids NaN/Infinity.

Runtime generation of a local receipt is not publication.

**Publication is a separate documentation-only receipt PR** adding the immutable JSON under `docs/` with a content-addressed filename containing its SHA-256. The receipt file is append-only and may never overwrite a prior receipt. Owner merge of that receipt PR is the publication event.

A V-1B result has no downstream authority before its receipt is Owner-merged.

---

## 11. Preregistration disclosure

The following pre-adoption scouting is disclosed and may not be concealed:

- pooled overlapping-window Q3 volatility correlations, level ratios, and slopes were inspected on 2026-09-03;
- Q3 appeared to carry rank information while its absolute level was horizon-miscalibrated;
- an overlapping previous-window persistence calculation was inspected and recognized as overlap-contaminated;
- no E-1-selected non-overlapping session-clustered `enc_b` statistic under this exact contract had been adopted as controlling evidence before this freeze;
- no V9-VOL causal-kappa `enc_b` statistic under this exact contract had been adopted as controlling evidence before this freeze.

If review establishes that the exact V-1 inferential statistic on the exact selected population was already inspected before adoption, the affected cell is not silently treated as preregistered; it must be marked `INVALID` for confirmatory claims and preserved as exploratory evidence.

---

## 12. Frozen future dashboard-source decision — no V-1C authority yet

This section freezes the data contract for a possible later V-1C so implementation cannot choose a different source after seeing results. It **does not authorize V-1C**.

If V-1C is later separately authorized, the visible `V9 VOLATILITY ACCURACY` card must source **only V9-VOL values from the latest Owner-merged, SHA-valid V-1B receipt bundled in the deployed repository**. It may not query live evidence tables, recompute statistics in the web process, use FAMILY-VOL values under a V9 label, or reuse directional-accuracy fields.

The five visible rows are exactly:

```text
MAE BPS
RANK CORR
LEVEL RATIO
90% COVERAGE
STATUS
```

The six columns remain exactly `30S`, `1M`, `5M`, `15M`, `30M`, `1H`.

### 12.1 Dashboard STATUS semantics

For each V9-VOL horizon:

1. `NO DATA` — no Owner-merged, SHA-valid V-1B receipt contains that horizon.
2. `STALE` — a valid receipt exists, but its `evidence_max_cutoff_at` is earlier than the close of the most recent fully completed regular XNYS session before render time.
3. Otherwise display the receipt classification exactly: `INFORMATIVE`, `NOISE`, `INSUFFICIENT`, or `INVALID`.

Metric cells are blank for `NO DATA`. They remain the receipted values for `STALE`; staleness must never fabricate zeroes.

Directional wins/losses/accuracy percentages may not populate the volatility card.

---

## 13. V-1C gate — explicitly blocked now

V-1C dashboard work remains `BLOCKED` until all of the following occur in order:

1. V-1A Owner merge;
2. V-1B implementation PR independently reviewed, green, and Owner-merged;
3. any authorized V-1B migration applied and privilege receipt verified;
4. V-1B scorecard run from the merged implementation SHA;
5. immutable V-1B receipt publication PR independently reviewed, green, and Owner-merged;
6. ChatGPT Pro audits the published receipt and explicitly opens V-1C.

No implementation agent may infer V-1C authority from this freeze alone.

---

## 14. V-2 — no preregistration or authority in V-1A

The V-2 hypothesis and 20-session outline in the draft are **not adopted** by this freeze.

V-2 is a separate protected-boundary architecture/research decision that may be authored only after V-1B evidence is published and audited.

A V-1 `INFORMATIVE` result buys only the right for ChatGPT Pro and the Owner to decide whether to author a V-2 freeze. It does not authorize:

- production volatility-primary synthesis;
- Q3 insertion into signed family synthesis;
- family reweighting;
- signal gating or sizing;
- options trading;
- broker/order changes;
- production Gamma activation;
- any change to `final_bps`;
- any live-capital action.

---

## 15. Production, simulator, and evidence boundary

V-1 does not change or authorize changes to:

- `final_bps`;
- current V9 signed synthesis;
- family signs or weights;
- Q3 formula;
- V4C production math;
- production Gamma activation;
- V4C/V4D production state contracts;
- SIM entry/exit/resolution/P&L mathematics;
- SIM services or databases;
- broker/account/order endpoints;
- live capital;
- options execution;
- Level II mathematical use;
- existing immutable directional evidence.

Directional forecasting may continue during V-1.

---

## 16. Required V-1B tests

At minimum, V-1B implementation must prove:

1. exactly six canonical horizons;
2. FAMILY-VOL target mapping exactly as §3;
3. V9-VOL target mapping exactly as §3;
4. causal kappa uses only evidence strictly available before each forecast cutoff;
5. causal-kappa reconstruction is numerically equivalent to frozen V4C calibration on the same prior observations;
6. kappa unavailable is excluded and counted;
7. E-1 RTH and non-overlap selection parity;
8. zero realized magnitude remains valid;
9. null/non-finite values excluded and counted, never imputed;
10. `persist_20` uses exactly 20 causally available prior selected realized magnitudes;
11. unavailable persistence windows excluded and counted;
12. exact MAE, Spearman, level ratio, 90% coverage, MZ, and persistence-correlation definitions;
13. session bootstrap refits the encompassing regression at each resample;
14. bootstrap is deterministic at 200,000 resamples, seed 0;
15. pure persistence with no incremental forecast information cannot classify `INFORMATIVE`;
16. constructed incremental magnitude information exercises the positive classification path;
17. rank-deficient/non-finite inference returns `INVALID` rather than fallback math;
18. canonical receipt JSON and SHA-256 are stable;
19. reader is exactly `atom_e1_scorecard_reader`, read-only, fail-closed, with no fallback credential;
20. no production write, SIM, broker, order, or production-math path is introduced.

If the optional narrow migration is required, add a database-backed proof of its exact final privileges/policies and absence of broader authority.

---

## 17. Sequence

Execute only in this order:

```text
V-1A documentation PR
-> independent final-head review
-> required checks green
-> Owner merge
-> V-1B implementation PR only
-> independent final-head review / tests / green checks
-> Owner merge
-> apply optional already-authorized narrow migration only if required
-> verify exact reader authority
-> run read-only V-1B scorecard from merged SHA
-> create immutable receipt
-> receipt-publication documentation-only PR
-> independent final-head review / green checks
-> Owner merge of receipt
-> ChatGPT Pro receipt audit
-> separate decision whether to open V-1C
-> later, separate decision whether to author V-2
```

Parallel SIM/G/L work may continue if it does not mutate V-1 definitions, contaminate evidence, or claim authority from V-1.

---

## 18. Stop conditions

Stop `BLOCKED` and return for a documentation-first amendment if execution requires any of the following:

- changing a frozen metric or regression;
- changing E-1 selection/bootstrap semantics;
- changing frozen V4C calibration math;
- reading future/current state to manufacture causal kappa;
- a new market-data source;
- a new database role or credential;
- broader table access than §9.1;
- production V9 mathematics;
- SIM mathematics;
- broker/order authority;
- silently relabeling directional data;
- dashboard recomputation from live evidence;
- V-1C before the published-receipt gate;
- V-2 before a separate later freeze.

---

## 19. Frozen conclusion

V-1A establishes volatility/magnitude as ATOM's primary **research evaluation target** while preserving direction as secondary evidence.

V-1B is the only next phase authorized after Owner merge: a read-only, persistence-adjusted, causally calibrated scorecard with immutable receipt publication.

V-1C and V-2 remain explicitly unauthorized until their later gates are satisfied.

**END — ATOM-V1A-VOLATILITY-FIRST-FREEZE-1**
