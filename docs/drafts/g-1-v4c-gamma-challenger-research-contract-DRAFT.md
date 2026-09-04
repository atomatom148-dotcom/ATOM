# G-1 — V4C Gamma Challenger: Research Contract Proposal (DRAFT, zero authority)

**Draft status:** prepared by Claude at Owner request under `AGENTS.md` § "Freeze-author continuity and delegated drafting" and `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B` §2. This text has zero controlling authority. It becomes law only if ChatGPT Pro adopts it as author of record (or the Owner adopts it directly under 1B §2.1), it receives independent final-head review, every required check is green, and the Owner merges it as its own documentation-only PR.  
**Proposed label:** G-1 — offline, read-only falsification of the V4C Gamma Challenger. ChatGPT Pro assigns the real decision and phase IDs on adoption.  
**Change type:** documentation only. If adopted, the implementation that follows is one read-only reader and one receipt. No production, V9, family, simulator, schema, role, credential, Render, or broker change.  
**Requested disposition (Freeze-1 §11):** `RESEARCH AUTHORIZED`, `HOLD`, or `REJECT` — ChatGPT Pro decides.  
**Verified against:** `main` `c622296e7f9e020cf772b5f32c04073a61984cdb` (2026-09-04). Every file:line below is at that commit. Re-checked at `d794a85a2a7273df2317027e04adcb8f3022f2b8` (merge of #310, SIM-5W): the only files that changed are `AGENTS.md` (pointer text) and the new `docs/sim-5w-read-only-sim-web-card-freeze.md`; no cited file moved.

---

## 0. What this asks, in one paragraph

V9 synthesizes `final_bps` from 11 of its 12 families; `q3_volatility` is computed every cycle but is carried only as a diagnostic (`q3_diagnostic_magnitude_bps`, `q3_used = False`). The repository already contains a fully coded, unit-tested, never-run "Gamma Challenger" (`quant/v9_v4c_predictive.py`) that would use that diagnostic to rescale V9's predictive variance per observation. It is quarantined behind hard invariants in five places and has no production caller. This document asks ChatGPT Pro to decide whether to authorize one read-only, preregistered, out-of-sample falsification of that challenger — and nothing else. It does not propose shipping anything.

## 1. Verified current state

### 1.1 Q3 today

- `QUANT_IDS` lists twelve families including `q3_volatility` (`quant/v9_v1_contract.py:23–27`); q3 is the only family typed `MAGNITUDE_BPS` (`:36`).
- Q3 is realized log-return volatility over a fixed `LOOKBACK_SECONDS = 3600` (`quant/q3_volatility.py:14`, `:36–41`). **The same value is emitted for all six horizons of a cycle** (`:41`); it is not horizon-scaled. The V-1 draft's scouting (`docs/drafts/v-1-volatility-target-program-DRAFT.md` §1) found exactly this: rank information at every horizon, wrong level.
- V3 synthesis weights only `CANONICAL_FAMILIES` — eleven families, q3 absent (`quant/v9_v3_synthesis.py:26–30`). Per horizon it copies the fresh q3 value into `q3_diagnostic_magnitude_bps` and leaves `q3_used = False`, `gamma = 0.0`, `phi = 1.0` (`:34–48`, `:293–295`, `:304–308`).
- The diagnostic is durable: `ForecastRecord.q3_diagnostic_magnitude_bps` (`quant/v9_v4a_evidence.py:149`, populated at `:204`) is persisted with every forecast inside `record_json` of `public.atom_v9_v4_forecasts` (`:561`).

### 1.2 The challenger code (exact mathematics as coded)

For one observation `w`: `e_w = actual_return_bps − expected_return_bps`, `q0_w = predictive_variance_bps2`, `m_w = q3_diagnostic_magnitude_bps` (`GammaInput(error, q0, magnitude)`, `quant/v9_v4c_predictive.py:436–438`).

```text
m2        = mean(m_w²) over the fit set                                   (:477)
phi_w(η)  = (1 − η) + η · m_w² / m2                                       (:453)
κ²(η)     = mean(e_w² / (q0_w · phi_w(η)))          — profiled, refit per η (:456)
ℓ_w(η)    = log(κ²(η) · q0_w · phi_w(η)) + e_w² / (κ²(η) · q0_w · phi_w(η))   (:458)
objective(η) = Σ_w ℓ_w(η)                                                 (:459)
```

`optimize_gamma` minimizes `objective(η)` over `η ∈ [0, 1)` by golden-section search (`:486–493`, interval tolerance `1e-12`, `maximum_iterations = 256`), refuses an optimum on the upper boundary (`GAMMA_FINITE_OPTIMUM_UNAVAILABLE`, `:506–507`), and reports `gamma = η / (m2 · (1 − η))` (`:508`), so equivalently `phi_w = (1 − η)(1 + gamma · m_w²)`. `η = 0` reproduces today's model exactly (`phi ≡ 1`, `κ²` = the `calibrate_scale` estimator at `:369`). The result carries `baseline_objective = objective(0)`, `challenger_objective = objective(η̂)`, `objective_improvement = baseline − challenger` (`:511–513`). **On a converged run the returned `status` is the literal `"INACTIVE"`** (`:512`).

Method identities already frozen in code: `GAMMA_STATE_VERSION = ATOM_TRUE_V9_V4C_GAMMA_CHALLENGER_1` (`:29`, defined, never used), `GAMMA_METHOD = ATOM_TRUE_V9_V4_GAMMA_ETA_GOLDEN_SECTION_1` (`:37`).

A companion non-degradation gate is also coded and never run: `build_q3_quartile_gate` (`:258–292`) partitions observations into magnitude quartiles (tie-merge, `:268–274`), requires effective `n ≥ 50` per quartile (`:280–283`), tests each quartile's mean `d_gamma` with Newey–West Bartlett HAC (`hac`, `:81–98`, lag `floor(4·(n/100)^(2/9))`) and Holm at `α = 0.05` across the four quartiles (`:284`), and returns `FAIL` if any quartile degrades significantly (`:290`). **No document in the repository defines `d_gamma`.** The natural reading — the per-observation log-score gain `ℓ_w(0) − ℓ_w(η̂)` — is adopted below as a proposal, not a fact.

### 1.3 No production caller

`optimize_gamma`, `gamma_objective`, `GammaInput`, `build_q3_quartile_gate`, and `Q3QuartileObservation` are referenced only by `tests/test_v9_v4c_predictive.py`. The production V4C state builder `_build_state` (`quant/evidence_outbox.py:487–552`) builds thresholds, scale, and range from `CalibrationObservation` pairs (`:513–518`) and never calls the optimizer. The challenger is dormant research code, not a running shadow.

### 1.4 Five enforcement points that keep it inactive, plus lineage

1. `V4CState` defaults `gamma = 0.0, phi = 1.0, gamma_status = "INACTIVE"` and `__post_init__` raises `"V4C production gamma is frozen inactive"` for any other value (`quant/v9_v4c_predictive.py:537–548`). A dataclass invariant, not a flag.
2. `V4CStateStore.latest_json` reconstructs `V4CState` from the stored row (`:695–700`); a stored gamma-active state would therefore fail closed as `STATE_DESERIALIZATION_INVALID` (`:707–708`).
3. `final_numbers` — the live transformation — computes `predictive_scale_bps = κ · √predictive_variance_bps2` with no `phi` anywhere (`:596–597`) and hardcodes `gamma = 0.0, phi = 1.0, gamma_status = "INACTIVE"` into every `FinalNumbers` (`:628`).
4. The Phase-E efficacy evaluator admits a forecast only when `q3_used is False`, `gamma == 0.0`, `phi == 1.0` (`_valid_verified`, `quant/v9_efficacy.py:383–385`).
5. V4D integration emits the metric literal `v4.<horizon>.gamma.INACTIVE` unconditionally (`quant/v9_v4d_integration.py:323`).

Lineage: `gamma` and `phi` are inside the forecast hash (`_forecast_math` excludes only identity and persistence fields, `quant/v9_v4a_evidence.py:174–177`; fields at `:165–167`) and inside the V4C state hash (`build_v4c_state`, `quant/v9_v4c_predictive.py:562–566`). Any activation changes forecast and state identity and starts a new evidence lineage.

### 1.5 Where `V4CState` / `V4CStateStore` is consumed

`quant/v9_v4d_integration.py:30–32`, `quant/evidence_outbox.py:40–44`, `quant/v4_state_worker.py:16–24` (via the builders), `quant/web.py:1096`, and `quant/v9_production.py:55`. This is the live production forecasting path — which is why the active-phase pointer's "V9/family changes … not authorized" applies and a later wiring phase would be a Class-4 protected-boundary change (Freeze-1 §13).

### 1.6 The data for a real run already exists and is already readable

Every `GammaInput` field is durable per (forecast, outcome) pair, inside `record_json`: the forecast's `expected_return_bps`, `predictive_variance_bps2`, and `q3_diagnostic_magnitude_bps` in `public.atom_v9_v4_forecasts` (`quant/v9_v4a_evidence.py:561`), and the outcome's `actual_return_bps` in `public.atom_v9_v4_outcomes` (`:603`) — the same records the E-1 reader already selects and deserializes (`quant/evidence_scorecard.py:627–642`, `:718`). The E-1 reader role `atom_e1_scorecard_reader` already holds `SELECT` on both tables with permissive full-read policies (`migrations/030_authorize_e1_scorecard_reader.sql:110–112`, `:119–122`). No new table, grant, source, or service is needed to run the study. Whether that credential may be reused for a non-E-1 study is an Owner decision (§5, D5).

### 1.7 No real-data evidence exists

The only executed inputs are synthetic (`tests/test_v9_v4c_predictive.py:77–85`, `:89–92`, `:296`). No receipt, note, or fixture anywhere in the repository records an `optimize_gamma` result on market data. No number is claimed here. The module's 42 unit tests pass at the verified commit.

### 1.8 Correction to the previous draft: which statistical discipline exists

The earlier draft said E-1's discipline is "HAC + Holm". It is not. E-1's only inferential statistic is a session-clustered percentile bootstrap — 200,000 resamples, seed 0, intervals 0.999 and 0.95 — with `INSUFFICIENT` / `NOISE` / `CANDIDATE` labels (`docs/e-1-evidence-scorecard-freeze.md` "Frozen statistics" items 5 and 7; `quant/evidence_scorecard.py:44–52`, `:248`). HAC + Holm is the V4C module's own internal discipline, used by its probability calibrator, its Q3 quartile gate, and the Phase-E efficacy evaluator (`quant/v9_efficacy.py:52`, `:525`, `:603`). Both exist; the contract must name one for its primary test (§4.7).

### 1.9 In-sample improvement is not evidence

Because `η = 0` is inside the search set, `objective_improvement ≥ 0` on every converged run by construction. The earlier draft's question "what minimum `objective_improvement` justifies promotion" is therefore the wrong question. The only admissible evidence is out-of-sample log-score gain with `η̂`, `m2`, and both `κ²` values fixed on data the holdout never touched.

## 2. What this explicitly does not propose

- No change to `quant/`, `tests/`, migrations, `AGENTS.md`, `FREEZE.md`, `SIMULATION_FREEZE.md`, `PHASES.md`, or any freeze. No pointer change.
- No change to Q3's formula, level, or lookback; no reweighting; no family enters or leaves `CANONICAL_FAMILIES`.
- No change to `final_bps` or direction. `phi` cannot touch them even if promoted: it rescales variance only, and SIM-4/SIM-5 direction is a function of `final_bps` alone (`SIMULATION_FREEZE.md` "Direction rule").
- No SIM change, no Level-II use, no E-2 / E-3 / E-4 change, no broker, account, order, or live-capital authority, no new service, role, credential, or data source.
- No claim that the challenger should ship. A PASS below buys exactly one thing: the right for ChatGPT Pro to triage a separate Class-4 wiring freeze (§7).

## 3. Why this is the strongest available research candidate — and its limit

For it: (a) implemented and unit-tested; (b) already quarantined so it cannot silently activate; (c) consumes a diagnostic the ledger has been storing on every forecast since V4A began, so no new data; (d) has a principled, parameter-light objective (one parameter `η`, profiled likelihood) rather than an invented metric; (e) `phi` normalizes by `m2`, so it exploits Q3's *ranking* and is indifferent to Q3's *level* — which is precisely the defect V-1 scouting found in Q3 and precisely what a calibration layer should absorb without touching Q3.

Against it, stated plainly: the challenger cannot create directional edge. Its ceiling is better-calibrated scale, range, and probability outputs. Those matter — a calibrated σ is the denominator of the E-2 selectivity statistic and the natural "don't trade now" switch — but a PASS here is a calibration result, not a trading-value result, and must not be described as one. Q3 is one hour of realized volatility, identical across horizons; at 30S–1M it is a slow feature, and the fit may legitimately find `η̂ ≈ 0` there. That is a cheap, honest FAIL, which is the point of running it.

## 4. Proposed research contract (preregistration fields per Freeze-1 §12)

Every item is a **proposed default**. ChatGPT Pro fixes or replaces each one on adoption; nothing below is fixed by this draft.

### 4.1 Hypothesis (one per horizon, six total)

> H_h: for horizon `h`, rescaling V9's predictive variance by `phi_w(η̂_h)` improves out-of-sample per-window log score relative to today's `phi ≡ 1` model, and does so without significant degradation in any Q3-magnitude quartile.

### 4.2 Instrument, horizons, baseline identity

COIN; all six horizons independently. Baseline = today's model: `η = 0`, `phi ≡ 1`, `κ²` = `calibrate_scale`'s estimator (`quant/v9_v4c_predictive.py:369`) fitted on the calibration set. Baseline identity is recorded as the exact V9 cohort (`cohort_id`, `cohort_hash`) and the forecast/outcome contract versions of the pairs scored.

### 4.3 Population, admissibility, features, labels

- Pairs: `atom_v9_v4_forecasts` joined to `atom_v9_v4_outcomes` on `forecast_record_id`, restricted to `evidence_origin = PRODUCTION`, `persistence_proof_eligible`, outcome `proof_eligible` and `target_timing_status = VERIFIED`, exact cohort match — i.e. the same governance the V4C builder applies (`_governed_v4c_evidence`, `quant/evidence_outbox.py:312`).
- Windows: E-1's rule — regular XNYS sessions, interval inside 09:30–16:00 America/New_York, non-overlapping by horizon spacing, restart per session (`docs/e-1-evidence-scorecard-freeze.md` "Frozen statistics" item 1; `quant/evidence_scorecard.py:126`, `:149`). Alternative in §5 D3.
- Features: `m_w = q3_diagnostic_magnitude_bps` exactly as stored; no transformation.
- Labels: `e_w = actual_return_bps − expected_return_bps`; `q0_w = predictive_variance_bps2`.
- Missing data: a pair with null, non-finite, or negative `m_w` is excluded and counted as `n_no_magnitude`; a pair with `q0_w ≤ 0` or non-finite `e_w` is excluded and counted. Nothing is imputed. Missing ≠ 0.

### 4.4 Estimator and fixed hyperparameters

`optimize_gamma` exactly as coded (golden section, tolerance `1e-12`, `maximum_iterations = 256`, boundary refusal). `m2_h` from the calibration set. `κ²_0` and `κ²_η̂` profiled on the calibration set and then frozen. A calibration fit that is not `CONVERGED` makes the horizon `INVALID`, not `FAIL`.

### 4.5 Split — pilot then confirmatory, evaluated once (mirrors E-2 / V-2)

- **Pilot / calibration set:** every admissible session before the adoption merge date. It fixes, per horizon: `η̂_h`, `gamma_h`, `m2_h`, `κ²_0,h`, `κ²_η̂,h`, and the 0.90 empirical quantile of standardized `|e|` under each model. The pilot receipt publishes these and the in-sample `objective_improvement` (reported, never used) and makes no pass/fail claim.
- **Confirmatory holdout:** the first 20 clean regular sessions after adoption, in whole sessions, evaluated exactly once. No extension, no early stop, no refit.
- Why not walk-forward on existing sessions only: V-1 scouting has already examined Q3's rank relationship to realized magnitude on those sessions; the hypothesis was formed after seeing it. A test on the same sessions is partially contaminated and may be reported only as informal. See §5 D2.

### 4.6 Per-window statistic and primary metric

```text
d_w    = ℓ_w(0) − ℓ_w(η̂_h)      with κ²_0, κ²_η̂, η̂, m2 fixed from calibration
Δ_h    = mean(d_w) over holdout windows        (mean log-score gain, nats per window)
```

### 4.7 Inference

Session-clustered percentile bootstrap exactly as E-1 (`quant/evidence_scorecard.py:248`): 200,000 resamples, `random.Random(0)`, ratio of sums, cluster = session. Report the 0.999 and 0.95 intervals of `Δ_h`. Six cells; at 0.999 the expected false PASS count is 0.003. Alternative in §5 D4.

### 4.8 Secondary metrics (all reported; gating per §5 D7)

1. Q3 quartile non-degradation: `build_q3_quartile_gate` over holdout `(m_w, d_w)` must return `PASS` (not `UNAVAILABLE`, not `FAIL`).
2. Coverage: share of holdout windows with standardized `|e|` inside the calibration-set 0.90 quantile, under baseline and challenger; the challenger's coverage must not be further from 0.90 than the baseline's.
3. Stability: refit `η` on each expanding calibration snapshot at session boundaries during the pilot; publish the path. Report-only unless D6 makes it a gate.
4. Descriptives per horizon: `n_rows`, `n_population`, `n_no_magnitude`, `n_q0_invalid`, `n_windows_cal`, `n_windows_hold`, `n_sessions_hold`, `η̂`, `gamma`, `m2`, `κ²_0`, `κ²_η̂`, in-sample `objective_improvement`.

### 4.9 Sample requirements

Per horizon: calibration `n_windows ≥ 250` with effective `n ≥ 200` (the V4C `MATURE` scale thresholds, `quant/v9_v4c_predictive.py:371`); holdout `n_sessions ≥ 20` and `n_windows ≥ 500`. A horizon that misses a minimum is `INSUFFICIENT`, preserved, and neither PASS nor FAIL.

### 4.10 Verdict rules

- **PASS_h:** 0.999 interval of `Δ_h` entirely above 0, quartile gate `PASS`, coverage condition met, calibration fit `CONVERGED`.
- **FAIL_h:** any other valid result, including `η̂_h = 0`. A valid null is FAIL, not INVALID, and is preserved.
- **INVALID_h:** protocol defect only — `η̂`, `m2`, `κ²`, windows, sessions, or thresholds changed after holdout results were visible; holdout extended or truncated; nulls imputed; a non-converged or boundary fit used; any statistic conditioned on `|μ|/(κσ)` computed inside the study (§8); evidence-continuity failure across the holdout.
- **INSUFFICIENT_h:** §4.9 minimums unmet.
- Multi-horizon logic: horizons are independent; no pooling across horizons; a PASS at one horizon says nothing about another.

### 4.11 Friction, regressions, rollback

Friction: not applicable — log score is friction-free and no trading decision changes. This is why a PASS is not a trading-value claim. Acceptable regressions: none to `final_bps` or direction (structurally impossible); range width may change. Rollback for the study: none required, it writes nothing. Rollback target for any later wiring: the merged SHA before it, with `INACTIVE` as the defined safe state (§7).

### 4.12 What PASS authorizes

Only that ChatGPT Pro may open triage for a separate protected-boundary freeze (§7), restricted to the PASS horizons. It authorizes no implementation, no state change, no consumer, no promotion.

## 5. Open decisions for ChatGPT Pro / the Owner

| # | Decision | Proposed default | Alternative |
|---|---|---|---|
| D1 | Disposition and sequencing against SIM-5, L-2, V-1, E-2, E-3 | `RESEARCH AUTHORIZED`; runs alongside, takes no pointer | `HOLD` behind V-1's receipt (both read Q3) |
| D2 | Split | pilot on pre-adoption sessions, confirmatory on the first 20 post-adoption sessions | expanding walk-forward on existing sessions, results labeled informal |
| D3 | Window population | E-1 admissibility (RTH, horizon-spaced, per-session restart) | the V4C builder's own `select_non_overlapping` set — the consumer's population, but not the program's scoring standard |
| D4 | Primary interval | 0.999 per horizon, E-1's screen | 0.95 with Holm across six horizons |
| D5 | Credential | reuse `atom_e1_scorecard_reader`; no new grant needed | a dedicated read-only role via its own migration (the Owner previously refused reuse of `atom_historical_score_reader` for E-1; this is the same class of decision) |
| D6 | `η̂` stability | report-only | gate: every pilot refit within a fixed band of the final `η̂_h` |
| D7 | Quartile gate and coverage condition (§4.8 items 1–2) | both are PASS requirements (the coded gate's evident purpose) | report-only until `d_gamma` is defined in law |
| D8 | Implementation owner and run mechanism | Codex default; Claude may assume under 1D once a job card exists; one-shot run through the existing E-1 reader pattern and receipt path | — |
| D9 | Does any PASS open G-2 triage automatically | no — a separate Owner objective is required | yes, restricted to PASS horizons |

## 6. Implementation surface if `RESEARCH AUTHORIZED`

Create only: `quant/gamma_challenger_study.py` (read-only reader; reuses `quant/evidence_scorecard.py` window selection and `session_bootstrap` unchanged and `quant/v9_v4c_predictive.py` `optimize_gamma`, `gamma_objective`, `build_q3_quartile_gate` unchanged) and `tests/test_gamma_challenger_study.py`. No modification to any existing module. No write anywhere. Connection only as the role fixed by D5, with `current_user` asserted and no fallback, exactly as E-1's reader does.

Required tests (golden vectors): baseline `η = 0` reproduces `calibrate_scale`'s `κ²` to binary64 equality; `d_w` uses only calibration-fixed parameters (a test that perturbs holdout data must not move `η̂`, `m2`, or either `κ²`); nulls excluded and counted, never imputed; a pure-noise magnitude yields `η̂ = 0` and `FAIL`; a constructed heteroskedastic set yields `PASS`; quartile gate `UNAVAILABLE` below 50 effective per quartile; bootstrap determinism under seed 0; receipt canonical JSON and SHA-256 stable; no import of any write path, broker path, SIM module, or `web.py`.

Receipt: same shape as E-1's, with every §4.8 field per horizon, the session lists for pilot and holdout, the verified `main` SHA, the reader identity, and the §8 disclosure verbatim.

## 7. The wiring phase this does *not* propose (blast radius, so it is explicit now)

If any horizon ever PASSes, activation would be a Class-4 change requiring its own ChatGPT Pro freeze. Verified surface it would have to touch: `final_numbers` mathematics (`phi` applied to `predictive_scale_bps`, and therefore to range and probabilities — never to `final_bps`); the `V4CState` invariant and a new state version (`GAMMA_STATE_VERSION` already exists for this); the state builder computing and storing `(η, m2, gamma)` per horizon; per-cycle `phi` derived from the cycle's own `q3_diagnostic_magnitude_bps`; `V3HorizonResult` / `ForecastRecord` `gamma`/`phi` population — a new forecast lineage; the efficacy evaluator's `phi == 1.0` assertion; the `gamma.INACTIVE` metric; and E-2's frozen `κσ` denominator, which must not silently change under an adopted E-2. Shadow with zero authority, non-influence proof, and rollback would be mandatory (Freeze-1 §14 steps 9–15).

## 8. Disclosure (preregistration honesty)

Examined to date, read-only: Q3 pooled, overlapping correlations with realized absolute move (V-1 draft §1); family and V9 hit rates, drift decomposition, side splits, time-of-day buckets, V4C calibration values (E-1 receipt, edge-program overview §5). **Not examined by anyone, as far as the repository and this session show:** any `optimize_gamma` result on market data, any `η̂`, any `d_w`, any Q3-quartile degradation statistic. Preparing this draft ran no query and no optimizer on real data. If ChatGPT Pro or the Owner has examined any of those, this preregistration is void for that horizon and must be rewritten by someone who has not.

Protection of E-2: the study must never compute, report, or bucket by `|μ|/(κσ)` or its tails; doing so voids E-2's preregistration and is `INVALID` here.

## 9. Appendix B — Mandatory Innovation Proposal (Freeze-1)

```text
Innovation ID:                    G-1 (proposed; ChatGPT Pro assigns)
Problem observed:                 q3_volatility is computed every cycle and used by nothing; V9's
                                  predictive variance ignores current realized volatility.
Current evidence:                 code only — a coded, tested, never-run challenger; zero market-data
                                  results; V-1 scouting shows Q3 ranks realized magnitude (overlapping,
                                  informal).
Proposed improvement:             one read-only, preregistered, out-of-sample falsification of
                                  phi_w = (1−η) + η·m_w²/m2 against phi ≡ 1, per horizon.
Expected measurable benefit:      mean out-of-sample log-score gain Δ_h > 0 at 0.999; better 0.90 coverage.
Affected instrument and horizons: COIN; 30S, 1M, 5M, 15M, 30M, 1H, independently.
Affected system and boundary:     none in G-1 (read-only). A later G-2 would touch V4C state, final_numbers,
                                  forecast lineage, efficacy evaluator — Class 4.
Affected freeze or phase:         none now; active pointer unaffected; FREEZE.md unaffected.
Cheapest valid falsification:     fit η̂_h on pre-adoption sessions; if η̂_h = 0 the idea is dead at that
                                  horizon before any holdout is spent.
Baseline:                         today's model, η = 0, phi ≡ 1, calibrate_scale κ².
Primary metrics:                  Δ_h with session-clustered bootstrap; quartile non-degradation; coverage.
Estimated implementation size:    one reader module + tests, ~E-1 reader scale; one receipt.
Infrastructure or vendor cost:    none new; one-shot read on the existing production project.
Failure risks:                    η̂ ≈ 0 at short horizons (honest FAIL); credential-reuse decision;
                                  contamination if walk-forward on scouted sessions is chosen.
Rollback:                         none needed (no write). G-2 rollback = prior SHA, INACTIVE.
Recommended disposition:          RESEARCH AUTHORIZED — or HOLD behind V-1's receipt.
```

## 10. Appendix A — proposed job card skeleton (for ChatGPT Pro to complete)

```text
Job ID:                                     G-1-STUDY-1 (proposed)
Controlling freeze:                         this document once adopted; FREEZE.md; ATOM-AI-ROLE-AUTHORITY-FREEZE-1 + 1A–1D
Controlling phase:                          G-1 (does not take the active-phase pointer)
Objective:                                  produce the pilot receipt, then the single confirmatory receipt
Named job owner:                            ChatGPT Pro
Named implementation owner:                 Codex (Claude may assume under 1D)
Repository/service/database/instrument scope: ATOM repo; production Supabase project, read-only; COIN
Permitted actions:                          create the two files in §6; read the four evidence tables; emit receipts
Prohibited actions:                         any write; any production/V9/SIM/family change; any credential beyond D5;
                                            any |μ|/(κσ) statistic; any refit after holdout visibility
Permitted files or resources:               quant/gamma_challenger_study.py, tests/test_gamma_challenger_study.py
Required tests:                             §6
Required evidence:                          §4.8 fields per horizon, session lists, SHA, reader identity, disclosure
PASS rule / FAIL rule / INVALID rule:       §4.10
BLOCKED rule:                               D2–D7 unresolved; credential unavailable; evidence-continuity failure
Rollback target:                            n/a (read-only)
Stop condition:                             confirmatory receipt emitted, or any INVALID trigger
Required receipt path:                      docs/g-1-gamma-challenger-pilot-receipt-<date>.json,
                                            docs/g-1-gamma-challenger-confirmatory-receipt-<date>.json
```

## 11. Not authorized by this document

Anything. It is a draft. In particular: no implementation, no query, no optimizer run on market data, no credential use, no change to Q3, V3, V4C, `final_numbers`, thresholds, RANGE, probabilities, families, evidence, SIM, E-2/E-3/E-4, Level II, broker, account, order, or capital; no deployment; no pointer change.

*Prepared by Claude · zero controlling authority per `AGENTS.md` and Amendment 1B §2 · author of record: none until adoption.*
