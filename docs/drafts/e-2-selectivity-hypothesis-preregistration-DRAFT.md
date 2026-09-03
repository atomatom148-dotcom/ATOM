# E-2 — Preregistered Hypothesis: Calibrated Signal-to-Noise Selectivity (DRAFT freeze)

**Draft status:** prepared by Claude at Owner request under 1B delegated drafting; zero authority until adopted and Owner-merged.  
**Phase:** E-2 (one hypothesis, evaluated once)  
**Prerequisites:** E-1 receipt over ≥10 clean sessions; E-1E fields; E-3 `cost_bps(h)`  
**Change type:** documentation only; implementation is one read-only reader and two receipts (pilot, confirmatory)

## 0. Preregistration statement

This hypothesis is frozen before any data on its test statistic is examined. Disclosure: read-only queries to date have examined raw hit rates, drift decomposition, side splits, time-of-day buckets, and V4C calibration values. **No query has examined `|μ|/(κσ)`, its distribution, tails, or their outcomes.** If the Owner or ChatGPT Pro has examined it, this preregistration is void and must be rewritten by someone who has not.

## 1. Hypothesis (exactly one)

> At horizon 5M, V9 forecasts in the top quintile of calibrated signal-to-noise carry directional information that the remaining forecasts do not, and that information survives cost and drift.

## 2. Definitions (frozen)

For each V9 forecast `f` at horizon `5M` with `expected_return_bps = μ` and `predictive_variance_bps2 = σ²`, both non-null and finite, and `σ² > 0`:

```text
κ(f)   = the kappa of the V4C state for f's cohort whose state_as_of is the latest strictly before f.cutoff_at   (causal; no look-ahead)
snr(f) = |μ| / (κ(f) · sqrt(σ²))
dir(f) = sign(μ)
```

A forecast with no causal V4C state, or with kappa status `UNAVAILABLE`, is excluded from the population (counted as `n_no_kappa`).

Windows, admissibility, eligibility, decided/tie/abstain classification, session clustering, and the 200,000-resample session bootstrap are exactly E-1's. Cost is E-3's `cost_bps(5M)`. Drift fields are E-1E's.

## 3. Design: pilot, then confirmatory, evaluated once

**Pilot window:** the first 10 clean regular sessions after adoption (dates echoed in the pilot receipt). The pilot fixes exactly two numbers and makes no pass/fail claim:

```text
T   = 80th percentile of snr(f) over pilot decided windows        (the tail threshold; frozen thereafter)
s²  = session-clustered variance of per-window net signed return   (for sample-size derivation)
```

**Confirmatory sample size:** derived from `s²` at one-sided α = 0.05, power 0.80, minimum detectable effect δ = `cost_bps(5M)` (i.e., the tail must clear cost by at least one more cost unit over drift). `N_conf = ceil(((1.645 + 0.842)² · s²) / δ²)` tail windows, with a floor of 150 tail windows and 20 sessions. The pilot receipt states `N_conf` and the projected session count.

**Confirmatory window:** the next `N_conf` tail windows after the pilot, in whole sessions, evaluated exactly once. No extension, no early stop, no re-draw of `T`.

## 4. Endpoints (frozen)

Over confirmatory windows, split into `TAIL` (`snr ≥ T`) and `REST` (`snr < T`):

```text
primary:    excess_net_bps(TAIL) = mean(dir·outcome) − cost_bps(5M) − drift_baseline_bps(TAIL)
secondary:  hit_rate(TAIL) − majority_direction_hit(TAIL)
secondary:  excess_net_bps(TAIL) − excess_net_bps(REST)
```

`drift_baseline_bps(TAIL)` is `|mean(outcome)|` over TAIL windows, per E-1E, so a tail that merely selects drift scores zero.

## 5. Pass / fail / invalid

- **PASS:** the 0.95 session-clustered bootstrap interval of the primary endpoint lies entirely above 0, **and** both secondary point estimates are positive.
- **FAIL:** any other valid result. A valid null is a FAIL, not INVALID, and is preserved.
- **INVALID:** protocol defect only — `T` examined or moved after the pilot, confirmatory window extended, cost or drift definition changed, sessions excluded after results, fewer than 20 confirmatory sessions, or evidence-continuity failure (L-1 acceptance not holding across the window).

The 0.95 level is deliberately weaker than E-1's 0.999 screen because this is one preregistered test, not a 72-cell search.

## 6. What PASS authorizes and what it does not

PASS authorizes exactly one next step: a separately frozen paper-simulator selection rule (SIM) that acts only on TAIL forecasts at 5M, with the same `T`, evaluated net of SIM-5 bid/ask exits. It does not authorize a V3 change, a family change, a threshold change in production, sizing, a second horizon, or any capital.

FAIL closes the selectivity hypothesis at 5M. It may be re-posed at another horizon only as a new E-2 with a new preregistration and a new disclosure statement.

## 7. Implementation surface (after adoption)

`quant/e2_selectivity.py` (new reader; reuses E-1's window and bootstrap functions unchanged), `tests/test_e2_selectivity.py` (golden vectors: `T` fixed from pilot only; causal kappa lookup rejects same-timestamp and later states; a pure-drift tail scores primary = −cost), the E-1 reader credential, no write anywhere.

## 8. Why 5M and why the top quintile

5M is the most data-rich horizon that cost does not obviously kill (30S/1M forecasts are single-digit bps; E-3 will say). ~78 windows per clean session gives a ~15-window daily tail at the 80th percentile — enough to reach `N_conf` in weeks, not months. The quintile is a prior, not a fit: it is chosen before any SNR data is seen and frozen by the pilot.

## 9. Not authorized

No examination of SNR data before adoption; no more than one hypothesis; no post-pilot change to `T`, cost, drift, endpoints, or sessions; no promotion on this receipt alone.
