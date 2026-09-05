# Correction 2 — tau measured, and a structural defect in `range_status`

Issued 2026-09-05 by Claude (read-only reviewer). Follows Correction 1.
Nothing here was computed on the frozen ledger. Every figure is either a value
production computed and persisted, or arithmetic on two such values
(`tau = n / N_eff`). No `enc_b`, no coefficients, no intervals, no QLIKE, no
`|mu|/(kappa*sigma)` was computed by me.

## 1. The V4C state is persisted and was readable

`atom_v9_v4_states` carries two state versions. I had only been reading the
first:

| `state_version` | rows | latest |
|---|---|---|
| `ATOM_TRUE_V9_V4B_ACCURACY_1` | 3,783 | 2026-09-05T00:06:08Z |
| `ATOM_TRUE_V9_V4C_PROBABILITY_1` | 3,703 | 2026-09-05T00:06:08Z |

The V4C rows key their horizon array under `horizons`, not `horizon_states`.
Latest V4C state, all six horizons:

| Horizon | calibration pool (`len(sorted_residuals)`) | `scale_status` | `range_status` | kappa set | `threshold_status` |
|---|---|---|---|---|---|
| 30S | 4,773 | **MATURE** | PROVISIONAL | yes | UNAVAILABLE |
| 1M | 2,866 | **MATURE** | PROVISIONAL | yes | UNAVAILABLE |
| 5M | 598 | PROVISIONAL | PROVISIONAL | yes | UNAVAILABLE |
| 15M | 102 | PROVISIONAL | PROVISIONAL | yes | UNAVAILABLE |
| 30M | 0 | UNAVAILABLE | UNAVAILABLE | no | UNAVAILABLE |
| 1H | 0 | UNAVAILABLE | UNAVAILABLE | no | UNAVAILABLE |

Pool sizes reconcile exactly with `split = max(0, len(selected) - 250)` against
the V4B `non_overlapping_n` figures (5023, 3116, 848, 352, 196, 95). The two
state versions are consistent.

## 2. tau, bounded from persisted status

`calibrate_scale` (`quant/v9_v4c_predictive.py:371`):

```python
status = "MATURE" if len(scores)>=250 and neff>=200 and k is not None else ...
```

**5M is the decisive cell.** Its pool is 598 — well past the 250 raw floor — and
`kappa` is set, so `len(scores)>=250` and `k is not None` both hold. The only
condition left to fail is `neff >= 200`. It is PROVISIONAL. Therefore:

> **At 5M, N_eff on the actual V4C score series is below 200 at 598 calibration
> pairs. That bounds tau > 2.99 on the exact series the gate uses.**

The two MATURE cells bound it from the other side: 30S at 4,773 pairs implies
tau <= 23.9; 1M at 2,866 implies tau <= 14.3.

Independent corroboration from the persisted V4B effective-n figures
(`tau = non_overlapping_n / *_effective_n`):

| Horizon | selected | N_eff(abs error) | tau | N_eff(sq error) | tau | N_eff(directional) | tau |
|---|---|---|---|---|---|---|---|
| 30S | 5,023 | 213.9 | 23.48 | 645.6 | 7.78 | 4,576.0 | 1.10 |
| 1M | 3,116 | 148.1 | 21.03 | 419.9 | 7.42 | 2,913.0 | 1.07 |
| 5M | 848 | 152.2 | 5.57 | 488.0 | 1.74 | 735.4 | 1.15 |
| 15M | 352 | 143.4 | 2.46 | 205.0 | 1.72 | 351.0 | 1.00 |
| 30M | 196 | 83.3 | 2.35 | 124.0 | 1.58 | 182.4 | 1.07 |
| 1H | 95 | 44.8 | 2.12 | 46.9 | 2.03 | 35.4 | 2.68 |

**N_eff on the error-magnitude series does not grow with n — it saturates near
150-215.** 30S has 5,023 pairs and gets 213.9 effective; 1M has 3,116 and gets
148.1. tau scales roughly with n. Two consequences:

- My earlier reading of the 1H directional ratio 0.373 as a warning sign was
  wrong. Directional tau is ~1.0-1.1 at every horizon except 1H, where n=95
  makes the Geyer estimator unstable. That figure was noise. Withdrawn.
- The real signal is the magnitude series, and it says the 30S and 1M passes
  were bought by brute pair count against a large tau, not by low dependence.

## 3. What this does to the V9 1H estimate

Correction 1 gave ~27 trading days to 500 selected pairs, which I said was
conditional on tau <= 1.25. That condition is now measured and it fails. 500
pairs is necessary and demonstrably **not sufficient**: 5M sits at 598 and has
not achieved `neff >= 200`.

Projections for 1H at the measured +15 selected pairs per full trading day from
95 on 2026-09-04:

| Milestone | selected needed | trading days | approx date |
|---|---|---|---|
| Leaves UNAVAILABLE (pool > 0) | 251 | 11 | 2026-09-21 |
| Clears the 250 raw floor -> PROVISIONAL | 500 | 27 | 2026-10-14 |
| Reaches 5M's pool, still insufficient there | 848 | 50 | 2026-11-16 |
| Reaches 1M's pool, sufficient there | 3,116 | 201 | ~2027-06 |

So mid-October is when V9 1H stops being UNAVAILABLE. `scale_status` MATURE at
1H is plausibly three quarters out, and is not guaranteed at any horizon — it
depends on whether tau keeps scaling with n. **Nobody should write an October
maturity date for V9 1H into the amendment.** My 15-week claim was wrong on
mechanism; the corrected mechanism makes 1H farther away, not nearer.

## 4. A structural defect: `range_status` cannot mature by accumulation

`range_status` is PROVISIONAL at **every** horizon, including 30S with 4,773
calibration pairs and `scale_status` already MATURE. That is not a data
shortage. `calibrate_range` (`quant/v9_v4c_predictive.py:425`) requires, among
other conditions:

```python
mature = (... len(valid)>=250 and cov is not None and cov[0]>=200 and ...
          and roll is not None and roll[0]>=100 and ...)
```

where `cov[0] = effective_n(covered)` over `valid`, and `valid` derives from
`validation_pairs = selected[split:]`.

Because `split = max(0, len(selected) - 250)`, **`validation_pairs` is exactly
250 once 250 pairs exist, forever.** Every additional pair moves into
calibration; the validation half never grows. So:

- `len(valid) >= 250` requires all 250 validation pairs to be valid. No slack.
- `cov[0] >= 200` requires N_eff >= 200 on a coverage indicator over at most 250
  observations — that is **tau <= 1.25 on a fixed 250-observation window**.
- `roll[0] >= 100` requires N_eff >= 100 on the last-20-sessions subset of those
  250.
- `effmiss >= 20` with `cov[0] <= 250` forces coverage <= ~0.92, while
  `cov[1]` must simultaneously contain 0.90 and have half-width <= 0.05.

Accumulating data cannot relieve any of these, because the population they are
computed on is pinned at 250. Given measured tau of 2.99 or higher on the score
series and 2.1-23.5 on the magnitude series, tau <= 1.25 on a 250-window is not
a threshold this system reaches by running longer.

**Conclusion: `range_status` MATURE appears unreachable at all six horizons
regardless of runtime.** Two horizons with 19x and 11x the raw floor, both
stuck, is the evidence.

This is now the single most important item for the readiness amendment. If READY
requires V4C `range_status` MATURE at any horizon, **the amendment legislates a
receipt that can never be issued.** The amendment must either exclude
`range_status` from READY, or the split must be changed so the validation
population grows (a proportional split, or a floor above 250), which is an
implementation change requiring its own freeze and its own phase.

`threshold_status` is UNAVAILABLE at all six horizons and needs the same
scrutiny; I have not traced `build_thresholds` far enough to say whether it has
the same shape.

## 5. Standing

Correction 1 stands except for its §4 tau discussion, which is superseded here:
the tau assumption there is now measured and it fails, and the 1H directional
ratio I cited as a warning sign was small-sample noise. The +15/day rate, the
500-pair floor, the two-selector finding and the cohort-rotation reset risk in
Correction 1 all stand unchanged.

## 6. Provenance

Code at `origin/main`: `quant/v9_v4c_predictive.py` lines 371 and 408-430,
`quant/evidence_outbox.py` line 509, `quant/v9_v2b_calibration.py` line 167.
Counts from read-only SQL against production project `afyiydxbjgzaiswnbcyj` on
2026-09-05, `atom_v9_v4_states` only, both state versions. No state changed. No
preregistered statistic was computed: the tau bounds in §2 are inferred from
persisted MATURE/PROVISIONAL statuses and persisted effective-n values, not from
any series I built.
