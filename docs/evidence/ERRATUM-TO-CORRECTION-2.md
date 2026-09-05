# Erratum to Correction 2 — downgrade the `range_status` claim, plus one finding that matters more

Issued 2026-09-05 by Claude (read-only reviewer). Read this before acting on
Correction 2 §4.

## 1. Downgrade

Correction 2 §4 concluded: "`range_status` MATURE appears unreachable at all six
horizons regardless of runtime," and called it a structural defect. **That is
stated more strongly than the evidence supports. Treat it as a hypothesis, not a
measurement.**

What is measured and solid:

- `validation_pairs = selected[split:]` with `split = max(0, len(selected)-250)`
  is **exactly 250 forever** once 250 pairs exist. Growth moves pairs into
  calibration only. That is arithmetic on merged code and it stands.
- `range_status` is PROVISIONAL at all six horizons, including 30S (4,773
  calibration pairs, `scale_status` already MATURE) and 1M (2,866).

What is **not** measured: which of the roughly eight ANDed conditions in
`calibrate_range` is failing. I checked whether the diagnostics are recoverable
without touching the ledger. They are not. `CompactHorizonState` persists only
`range_status` and `range_quantile`; every `RangeResult` diagnostic
(`validation_effective_n`, `coverage`, `coverage_interval`, `effective_misses`,
`rolling_effective_n`) is discarded before persistence, and
`atom_v9_v2_build_receipts` is a V2 build receipt
(`V9-V2-BUILD-RECEIPT-2`) carrying no V4C range fields.

There is a competing explanation I cannot rule out. `effmiss >= 20` requires
`cov[0]*(1-coverage) >= 20`, so with `cov[0] <= 250` it needs coverage <= ~0.92,
while `cov[1]` must simultaneously contain 0.90. If the intervals are
conservative — too wide — coverage goes to ~1.0 and both conditions fail for
**calibration-quality** reasons, which better intervals would fix. That is a
completely different disposition from the pinned-250 structural reading, and it
is equally consistent with everything I can observe.

So the honest statement is: the validation population is provably pinned at 250,
and that *would* make `cov[0] >= 200` require tau <= 1.25 on a fixed window,
which measured tau does not support. But I have not shown that `cov[0]` is the
condition actually failing. **Do not write either reading into the amendment.**

Discriminating measurement, for whoever holds the authority to run it: emit the
`RangeResult` diagnostics into the state or a receipt — they are already computed
and then thrown away — and read which condition fails at 30S. That is an
observability change, not a statistics change, and it costs one field.

## 2. What I should have led with

`atom_v9_v2_build_receipts.receipt_json.per_family_horizon_effective_n` persists
N_eff per family per horizon. For `q3_volatility` against its admitted counts:

| Horizon | admitted | N_eff | implied tau |
|---|---|---|---|
| 30S | 1,457 | **12.4** | ~117 |
| 1M | 959 | **16.2** | ~59 |
| 5M | 263 | 56.1 | ~4.7 |
| 15M | 114 | 114.0 | 1.00 |
| 30M | 67 | 67.0 | 1.00 |
| 1H | 36 | 36.0 | 1.00 |

Two readings, and the second is the one that matters.

**The volatility family has severe serial dependence.** At 30S, 1,457 admitted
rows yield 12.4 effective. That is the family the owner is pivoting the system
toward. Any gate stated in effective-n terms will be far harder to satisfy for
q3_volatility than for q1_momentum (1,459 admitted, 1,459.0 effective at 30S).

**The tau = 1.00 entries at 15M, 30M and 1H are almost certainly "not
detectable at this n," not "no dependence."** `effective_n` returns `float(n)`
exactly in two branches: `SERIAL_DEPENDENCE_UNIDENTIFIABLE`, or `retained = 0`
giving tau = 1.0. The progression 117 -> 59 -> 4.7 -> 1.0 -> 1.0 -> 1.0 tracks
n monotonically, which is what detectability scaling looks like, not a real
change in dependence structure. Other families do register tau > 1 at n = 31
(q1_momentum 1.48, q2_mean_reversion 1.36), so small n does not force 1.0 — but
the q3_volatility pattern across six horizons is hard to read any other way.

**Consequence: N_eff-based gates are optimistic at long horizons with small n,
and get harder as data accumulates.** A cell can look adequate now and regress
as tau becomes estimable. This is the mechanism behind the N_eff saturation in
Correction 2 §2, and it means every readiness projection in Corrections 1-3 —
mine and ChatGPT's alike — is an upper bound on progress, not an estimate.

## 3. Provenance

Code at `origin/main`: `quant/v9_v4c_predictive.py:408-430` and `:517-535`,
`quant/v9_v2b_calibration.py:167-195`. Counts from read-only SQL on 2026-09-05
against `atom_v9_v4_states` and `atom_v9_v2_build_receipts`. tau figures are
`admitted / effective_n` on values production computed and persisted. No
preregistered statistic computed. No state changed.
