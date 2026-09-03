# E-1E — Drift-Adjusted Baseline Fields (DRAFT amendment to the E-1 freeze)

**Draft status:** prepared by Claude at Owner request under 1B delegated drafting; zero authority until adopted and Owner-merged.  
**Amends:** `docs/e-1-evidence-scorecard-freeze.md` — "Frozen statistics" §4 (descriptive metrics) and "Receipt and stopping rule" only  
**Change type:** documentation only; the implementation that follows is read-only and receipt-only

## 1. Problem

E-1 classifies against a 50% directional null. On the measured sample that null is wrong: an always-short rule scored 54.5% at 1H and q10's entire "edge" at 5M equals the realized market move. A cell can look skilled while merely being long in an up-drift or short in a down-drift.

## 2. Exact change

Add three **descriptive** per-cell fields, computed over the same economic windows already defined, with no change to window selection, eligibility, bootstrap procedure, budget, labels, or classification:

```text
drift_bps                  = mean(outcome_bps) over economic windows          (sign of the market itself)
drift_baseline_bps         = |drift_bps|                                        (what a constant-direction rule earns)
excess_over_drift_bps      = mean_signed_bps - drift_baseline_bps
majority_direction_hit     = max(share_up, share_down) over decided windows     (the hit-rate null)
excess_hit_over_majority   = hit_rate - majority_direction_hit
```

`share_up`/`share_down` count decided windows with outcome > 0 / < 0. All five fields are `null` under the same conditions that null `hit_rate` and `mean_signed_bps`. None enters the bootstrap, the eligibility minimums, the multiplicity budget, or the `CANDIDATE`/`NOISE` label. The receipt hash covers them.

## 3. Why descriptive only

E-1's classification is preregistered and has already produced a receipt; changing its rule after results are visible is forbidden by the accuracy-and-value law. E-1E adds context, not judgment. E-2 (separate draft) uses `excess_over_drift_bps` as its **primary endpoint** by preregistration before its own data is read.

## 4. Implementation surface (after adoption)

- `quant/evidence_scorecard.py` — compute and emit the five fields; no other change;
- `tests/test_evidence_scorecard.py` — golden vectors for the five fields, including a pure-drift cell whose `excess_over_drift_bps` is exactly 0 and a tie-only cell whose fields are `null`.

No migration, role, grant, or database change. The dedicated `atom_e1_scorecard_reader` credential, RLS full-read verification, identity assertion, and no-`BYPASSRLS` design are unchanged.

## 5. Required tests

Exact formulas on hand-computed vectors; sign conventions (`drift_bps` negative in a down-drift; `drift_baseline_bps` non-negative); null propagation; receipt hash covers the new fields; classification output identical to the pre-E-1E implementation on the preserved 2026-09-03 receipt inputs (byte-identical labels, counts, intervals).

## 6. Not authorized

No reclassification of any existing cell; no change to the 0.999 guard, the 100-cell budget, or the ten-session minimum; no rerun of the preserved receipt as a substitute for the ten-session receipt.
