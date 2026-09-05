# Correction 1 to V-1A-CADENCE-AND-READINESS-MEASUREMENTS

Issued 2026-09-05 by Claude (read-only reviewer). Supersedes the section titled
"Hard arithmetic floor on V9 1H" in that document. That section was wrong.
Nothing else in the document is changed by this correction.

## 1. What I claimed, and why it was wrong

I wrote, as a hard floor:

> Non-overlap admits at most 6 calibration pairs per session at 1H. The §7.2
> latest-250 withholding therefore consumes at least 42 sessions before
> `calibration_pairs` is non-empty ... V9 1H cannot mature in under
> approximately 15 weeks under any schedule.

ChatGPT's exact-selector check refuted this and its refutation is correct. I
have now confirmed the mechanism by reading merged code rather than reasoning
about it. There are **two different window selectors** in the repository and I
applied the wrong one:

| Selector | Location | RTH filter | Session reset | Governs |
|---|---|---|---|---|
| `CellSelector.feed` | `quant/evidence_scorecard.py:175` | yes — `is_rth_window`, requires `[cutoff, cutoff+h]` inside 09:30–16:00 ET, same date | **yes** — `self._last = None` on each new session | V-1A regression windows; the G-1 gamma study (`gamma_challenger_study.py:107`) |
| `select_non_overlapping` | `quant/v9_v4a_evidence.py:385` | **no** — no RTH predicate anywhere in the function | **no** — one greedy pass over all pairs sorted by `cutoff_at`, continuous across days | §7.2 V4C calibration (`quant/evidence_outbox.py:503`) |

The six-per-session cap is a property of `CellSelector` and is real there: RTH is
6.5 hours, so at 1H the admissible cutoffs are 09:30 through 14:30 and 15:30 is
excluded because its window ends after the close. But §7.2 V4C does not use
`CellSelector`. It uses `select_non_overlapping`, whose only spacing rule is

```python
if not selected or pair[0].cutoff_at >= selected[-1][0].cutoff_at + timedelta(
        seconds=selected[-1][0].horizon_seconds):
    selected.append(pair)
```

with no session boundary and no RTH predicate. I imported a cap from the
selector that does not govern this pool. My "15 weeks" figure is withdrawn.

## 2. The measured rate

`atom_v9_v4_states.state_json -> horizon_states -> non_overlapping_n` is the
output of exactly this selector. Progression for 1H, end-of-day maximum per ET
session, cohort `3e72e914`:

| ET session | `non_overlapping_n` | delta | `raw_resolved_n` |
|---|---|---|---|
| 2026-08-24 | 4 | — | 1,609 |
| 2026-08-25 | 19 | +15 | 13,395 |
| 2026-08-26 | 2 | −17 | 500 |
| 2026-08-27 | 5 | +3 | 2,958 |
| 2026-08-28 | 20 | +15 | 7,938 |
| 2026-08-31 | 35 | +15 | 16,041 |
| 2026-09-01 | 50 | +15 | 25,298 |
| 2026-09-02 | 65 | +15 | 33,867 |
| 2026-09-03 | 80 | +15 | 46,794 |
| 2026-09-04 | **95** | +15 | 57,794 |

The rate is exactly +15 per full trading day on six consecutive full days, and
the pool is cumulative. Fifteen rather than six because the pool is not
RTH-bounded: the 1H `first_cutoff` is 2026-08-24T19:05Z and cutoffs run from
roughly 08:00 to 19:00 ET, a ~15-hour observation day.

This corroborates ChatGPT's figure. Its "91 at the frozen 2026-09-04 close,
advancing by 15" is the same quantity under a slightly different eligibility
cut; the +15/day and the cumulative behaviour are confirmed independently.

## 3. The MATURE thresholds, verified

ChatGPT's upward correction of MATURE is also confirmed in code.
`quant/v9_v4c_predictive.py:371`, `calibrate_scale`:

```python
status = "MATURE" if len(scores)>=250 and neff>=200 and k is not None else ...
```

Both conditions, so the floor is 250 calibration pairs **and** N_eff ≥ 200 on
them. `calibration_pairs = selected[:max(0, len(selected)-250)]`, so 250
calibration pairs requires **500 selected pairs**. 450 was wrong; 500 is right.

`calibrate_range` at line 425 is stricter still and worth the freeze author's
attention:

```python
mature = (quantile is not None and len(scores)>=250 and score_neff>=200
          and len(valid)>=250 and cov is not None and cov[0]>=200 and ...)
```

`validation_pairs = selected[split:]` is **exactly 250 pairs** by construction
once `len(selected) >= 250`. So `len(valid) >= 250` requires all 250 validation
pairs to be valid — a knife-edge condition with no slack. One inadmissible row
in the trailing 250 holds `range_status` at PROVISIONAL indefinitely. If that is
intended it should be stated; if it is not, it is a defect.

## 4. Corrected readiness for V9 1H — with the assumption named

At 95 selected pairs on 2026-09-04, advancing +15 per full trading day, and a
500-pair floor:

```
(500 - 95) / 15 = 27 trading days  ->  approximately 2026-10-14
```

That is ChatGPT's estimate and I agree with the pair-count arithmetic. **But it
assumes N_eff ≈ raw n, and that assumption is unmeasured.** `effective_n`
(`quant/v9_v2b_calibration.py:167`) is a Geyer initial-positive-sequence
estimator: `N_eff = n / tau`, `tau = 1 + 2*sum((1 - lag/n) * rho_lag)` over the
initial positive sequence. Reaching N_eff ≥ 200 from n = 250 requires
**tau ≤ 1.25** — near-zero positive autocorrelation in the standardised
absolute-error scores.

Observed `directional_effective_n / non_overlapping_n` in the current state, as
a proxy for how tau behaves by horizon:

| Horizon | ratio | implied tau |
|---|---|---|
| 5M | 0.867 | ~1.15 |
| 15M | 0.997 | ~1.00 |
| 30M | 0.931 | ~1.07 |
| **1H** | **0.373** | **~2.68** |

The 1H ratio is the outlier. It is computed on the directional binary series,
not on the V4C score series, and at n = 95 the Geyer estimator is unstable — so
this is a warning, not a result. But the two outcomes differ materially:

- tau settles at or below 1.25 → 500 pairs suffices → ~27 trading days, mid-October.
- tau stays near 2.7 → N_eff ≥ 200 needs n ≈ 540 calibration pairs → ~790 selected → **~46 trading days, mid-November**.

Recommended measurement, which I have not performed because it is a gate input:
compute `effective_n` on the 1H V4C calibration score series at the frozen
boundary and report tau. That single number decides which tier V9 1H lands in,
and it should be measured before the amendment legislates a date.

## 5. A reset risk neither of us has raised

The pool is cumulative but **not durable**. Tracking the 1H `cohort_hash`:

| cohort_hash (1H) | first seen | last seen | n range |
|---|---|---|---|
| `6544fb45…` | 2026-08-24 14:06Z | 2026-08-24 18:43Z | 6 → 10 |
| `ef5ff16d…` | 2026-08-24 19:05Z | 2026-09-05 00:06Z | 0 → 95 |

The cohort rotated once and `non_overlapping_n` **reset to zero and rebuilt from
scratch**. Any change that rotates a horizon's `cohort_hash` therefore restarts
the 500-pair clock: at +15/day that is 34 trading days from zero, roughly seven
weeks, for V9 1H.

This has a direct consequence for the amendment. If the readiness amendment —
or any freeze merged before the first receipt — alters an input that feeds the
cohort hash, every horizon's calibration pool restarts and the readiness date
moves by up to seven weeks with no visible failure. The amendment should either
state that cohort rotation resets readiness and require the rotation to be
recorded, or pin the inputs that feed the cohort hash for the duration of the
readiness window. This strengthens the tiered-boundary recommendation: tiers
that bank the cells which mature early are robust to a later rotation; an
all-cells rule is not.

## 6. Standing of the original document

Everything in `V-1A-CADENCE-AND-READINESS-MEASUREMENTS.md` other than the
"Hard arithmetic floor on V9 1H" section and the "V9 15M, 30M, 1H — months" row
of the readiness table stands as issued. Both are replaced by §4 above. The
methodological caveat in the original document — that its yields are
spacing-derived rather than selector-derived and that the audit's exact selector
counts govern — is what caught this error, and it continues to apply to every
remaining estimate in it.

## 7. Provenance

Code read at `origin/main`, paths and line numbers as cited. Counts from
read-only SQL against production project `afyiydxbjgzaiswnbcyj` on 2026-09-05
against `atom_v9_v4_states` only. No gate statistic was computed: no `enc_b`, no
coefficients, no intervals, no QLIKE, no `|mu|/(kappa*sigma)`. No state changed.
