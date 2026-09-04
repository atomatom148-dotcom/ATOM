# G-1 — V4C Gamma Challenger Research Freeze

**Owner sequence:** 12  
**Decision ID:** G-1  
**Status:** RESEARCH AUTHORIZED  
**Authority:** ChatGPT Pro, as freeze author under ATOM AI governance; Owner retains final merge and capital authority.  
**Effective:** on merge of the PR containing this file.  
**Scope:** offline, read-only falsification only. No production activation, no V9 mathematics change, no SIM change, no broker/account/order authority, no live-capital authority.

## 1. Purpose

Authorize one preregistered, out-of-sample test of the already-coded but production-inactive V4C Gamma Challenger. The challenger may be evaluated only as a variance/calibration mechanism. A PASS is not directional-edge proof and does not authorize shipping or wiring.

The detailed pre-adoption research and code-state audit is preserved in PR #312 history at head `97053f2e6b00c0faf8637549c36a653c22b0c4c1`; the current draft path is only a supersession marker so no discarded alternative can be mistaken for law. This freeze is the sole controlling G-1 research contract.

## 2. Frozen hypothesis

For each horizon independently, test whether rescaling predictive variance by the coded Gamma Challenger improves out-of-sample per-window log score relative to today's baseline `eta = 0`, `phi = 1`, without significant degradation in any Q3-magnitude quartile.

Instrument: COIN.  
Horizons: 30S, 1M, 5M, 15M, 30M, 1H, independently.  
No pooling across horizons.

## 3. Frozen baseline and data population

Baseline is today's V4C scale model with `eta = 0`, `phi = 1`, and baseline kappa-squared fitted on the calibration set.

Admissible pairs are production V9 V4 forecast/outcome pairs with the existing proof and cohort requirements intact. Window selection uses the E-1 admissibility discipline: regular XNYS sessions, interval inside 09:30–16:00 America/New_York, horizon-spaced non-overlapping windows, restart per session.

The study may use only fields already stored in the V9 evidence ledger that are required by the coded challenger: expected return, predictive variance, Q3 diagnostic magnitude, and realized return. Nulls are excluded and counted; never imputed.

## 4. Frozen split

Pilot: pre-adoption sessions only.  
Confirmatory: the first 20 eligible post-adoption sessions for each horizon, subject to the minimum sample rules below.

The confirmatory holdout is sealed before its results are inspected. It may not be extended, truncated, swapped, or refit after outcome visibility.

## 5. Frozen fitting and score

Fit `eta`, `m2`, challenger kappa-squared, and baseline kappa-squared on calibration data only. Holdout data must not move any fitted parameter.

For each holdout window `w`:

```text
d_w = log_score_baseline_w - log_score_challenger_w
Delta_h = mean(d_w) over holdout windows
```

Positive `Delta_h` means the challenger improved log score.

In-sample optimizer improvement is descriptive only and is never promotion evidence.

## 6. Frozen inference

Primary inference uses the E-1 session-clustered percentile bootstrap exactly: 200,000 resamples, deterministic seed 0, cluster = session.

Report both 0.999 and 0.95 intervals. The 0.999 interval is the primary PASS screen for each horizon.

No alternative primary test may be substituted after results are visible.

## 7. Frozen secondary gates

Both are mandatory PASS requirements:

1. Q3 quartile non-degradation must return PASS using the existing coded quartile gate, with `d_gamma` defined here as the per-observation log-score gain `d_w` above.
2. 0.90 coverage under the challenger must be no farther from 0.90 than baseline coverage.

Eta stability across expanding pilot calibration snapshots is report-only and cannot independently PASS or FAIL the study.

## 8. Minimum evidence

Per horizon:

- calibration `n_windows >= 250` and effective `n >= 200`;
- confirmatory holdout `n_sessions >= 20` and `n_windows >= 500`.

A horizon below a minimum is INSUFFICIENT, preserved as such, and is neither PASS nor FAIL.

## 9. Frozen verdicts

**PASS_h** requires all of the following: calibration fit CONVERGED; 0.999 interval of `Delta_h` entirely above zero; Q3 quartile gate PASS; coverage condition met.

**FAIL_h** is any other valid result, including `eta_hat = 0`, an interval touching or below zero, quartile degradation, or failed coverage.

**INVALID_h** is reserved for protocol defects, including holdout contamination, parameter refit after holdout visibility, changed windows or thresholds, null imputation, use of a non-converged/boundary fit, evidence-continuity failure, or any forbidden E-2 statistic described below.

**INSUFFICIENT_h** means the minimum evidence rule is unmet.

## 10. Frozen research-protection rule

This study must not compute, report, bucket, optimize, or inspect `|mu|/(kappa*sigma)` or its tails. Doing so invalidates the affected G-1 result and violates the E-2 preregistration boundary.

## 11. Credential decision

Reuse `atom_e1_scorecard_reader` for this study only because the study reads the same already-authorized evidence tables and requires no broader privilege. No new role, grant, schema, service, credential class, or database write is authorized.

The reader must assert `current_user = atom_e1_scorecard_reader` and fail closed on mismatch. No fallback credential is permitted.

This reuse does not broaden E-1 authority and does not authorize the credential for unrelated research.

## 12. Implementation boundary

Implementation owner: Codex.  
ChatGPT Pro remains architecture/freeze/final-audit authority.

Codex may create only the smallest study surface required:

- `quant/gamma_challenger_study.py`
- `tests/test_gamma_challenger_study.py`
- immutable pilot and confirmatory receipts under `docs/`

Existing Gamma Challenger mathematics, E-1 window selection, and E-1 bootstrap logic must be reused unchanged where applicable. No production module may be modified for G-1.

No migrations, Render changes, Supabase writes, broker paths, SIM modules, `web.py`, V9 family mathematics, `final_bps`, range/probability production wiring, or deployment are authorized.

## 13. Required tests

At minimum:

- `eta = 0` reproduces baseline scale mathematics;
- perturbing holdout data cannot move calibration-fitted parameters;
- nulls are excluded and counted, never imputed;
- pure-noise magnitude yields a valid null/FAIL path;
- constructed heteroskedastic evidence exercises the positive path;
- quartile gate is unavailable below its effective-size minimum;
- bootstrap output is deterministic under seed 0;
- receipt canonical JSON and SHA-256 are stable;
- no write path, broker path, SIM module, or production web path is imported.

## 14. Receipt requirements

Each receipt must record at least: verified main SHA, reader identity, horizon, cohort identity, calibration sessions, holdout sessions, row counts and exclusions, `eta_hat`, gamma, `m2`, both kappa-squared values, in-sample optimizer improvement, `Delta_h`, both bootstrap intervals, quartile verdict, coverage values, final verdict, and protocol-disclosure statement.

Receipts are append-only evidence. Results may not be overwritten.

## 15. Sequencing decision

G-1 may run alongside SIM-5, L-2, V-1, E-2, and E-3 because it is read-only and takes no active-phase pointer. It must not delay or mutate those programs.

## 16. What PASS authorizes

A PASS authorizes only ChatGPT Pro to consider a separate protected-boundary G-2 wiring freeze for the PASS horizon(s).

No G-2 phase opens automatically. A separate Owner objective is required. No implementation, production activation, state change, forecast-lineage change, V9 change, or trading authority follows from G-1 PASS alone.

## 17. What this freeze does not authorize

No production Gamma activation. No Q3 formula change. No family weighting change. No change to `final_bps`, direction, range, live probabilities, V4C production state, efficacy admission rules, SIM mathematics, Level II, broker/account/order APIs, execution, or capital.

No result may be described as trading profitability evidence unless a later separately frozen program measures that claim directly.

## 18. Final frozen decisions D1-D9

D1: RESEARCH AUTHORIZED; parallel, no pointer.  
D2: pre-adoption pilot + first 20 eligible post-adoption sessions confirmatory.  
D3: E-1 admissibility/window population.  
D4: 0.999 per-horizon E-1 bootstrap interval is primary.  
D5: reuse `atom_e1_scorecard_reader` narrowly; no new grant.  
D6: eta stability report-only.  
D7: quartile and coverage are both PASS gates.  
D8: Codex implementation owner beneath this freeze.  
D9: no automatic G-2; separate Owner objective required.

## 19. Stop condition

G-1 stops when the confirmatory receipt is emitted for all horizons that are not INSUFFICIENT, or immediately for any affected horizon on an INVALID trigger. Nothing beyond receipt generation is authorized.

**Freeze decision:** G-1 / Owner sequence 12 is authorized exactly as written above. Nothing above this freeze may be inferred, widened, or implemented.