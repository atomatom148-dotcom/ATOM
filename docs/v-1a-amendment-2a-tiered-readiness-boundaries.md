# V-1A Amendment 2A — Tiered Readiness Boundaries

**Decision ID:** `ATOM-V1A-AMENDMENT-2A-TIERED-READINESS-1`  
**Amends:** `ATOM-V1A-VOLATILITY-FIRST-FREEZE-1`  
**Adoption base inspected:** `main` at `ac85cc9e99ccc499789f3ef79b186768d99fb0d6`  
**Intended repository path:** `docs/v-1a-amendment-2a-tiered-readiness-boundaries.md`  
**Bound measurement artifact:** `docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS.md`  
**Bound measurement SHA-256:** `0b21fc0f9e2aec42939fcd74a91debbba916639cb84e95fe96c2bfcd55e41627`  
**Bound measurement size:** 8,662 bytes  
**Bound original measurement:** `docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS-ORIGINAL.md`  
**Bound original SHA-256:** `aaa58a0a36f8921bde54f0215f2a189da79a6a5c25b6e9db5d2d4f2b562cf913`  
**Bound original size:** 8,314 bytes  
**Bound correction artifact:** `docs/evidence/CORRECTION-1-V9-1H-CALIBRATION-ARITHMETIC.md`  
**Bound correction SHA-256:** `06c993a6cd3290e306e75feb73f0facf52fd4ce6f2c04dd1357452cfc26ef3fd`  
**Bound correction size:** 8,267 bytes  
**Bound correction cover note:** `docs/evidence/CORRECTION-1-COVER-NOTE.txt`  
**Bound cover-note SHA-256:** `9e85f3cfcfe7a0629cf014a218847738793d72d0deb7814329471b9ab5621611`  
**Bound cover-note size:** 3,149 bytes  
**Bound second correction:** `docs/evidence/CORRECTION-2-N-EFF-SATURATION-AND-RANGE-STATUS-DEFECT.md`  
**Bound second-correction SHA-256:** `24bfda809cc55acb26d46ccdd8a3f741b3b06dccfc064ef00568a714090dc6a5`  
**Bound second-correction size:** 7,795 bytes  
**Bound third correction:** `docs/evidence/CORRECTION-3-THRESHOLD-STATUS.md`  
**Bound third-correction SHA-256:** `717c4057229a9109803e05e0eb4647e9c4648c2a272e36918f1697552157eeb8`  
**Bound third-correction size:** 5,370 bytes  
**Bound erratum:** `docs/evidence/ERRATUM-TO-CORRECTION-2.md`  
**Bound erratum SHA-256:** `37a248d8a29fb258048c27549f06305ab2f5f886c38380d12cebe51da3ef33d4`  
**Bound erratum size:** 4,761 bytes  
**Bound scope note:** `docs/evidence/SCOPE-NOTE-V1A-READINESS-DEPENDS-ON-SCALE-STATUS-ONLY.md`  
**Bound scope-note SHA-256:** `8c8079b428e39fee8f41e64af384c540fbb363013dee00ad3e31a285adf8109b`  
**Bound scope-note size:** 4,915 bytes  
**Status:** PROPOSED CONTROLLING AMENDMENT — documentation only until Owner merge  
**Freeze author:** ChatGPT Pro  
**Owner authority:** Owner retains final approval, merge, deployment, infrastructure, risk, broker, instrument, order, and capital authority.  
**Population-evidence boundary:** counts, identities, timestamps, selector metadata, and availability only through `2026-09-04T20:00:00.000000Z`. The separate correction-only Render-log search, SQL/session-count checks, and persisted selector-state history queried on 2026-09-05 are excluded from every V-1 population and readiness decision. No protected V-1 coefficient, interval, QLIKE value or summary, gate result, classification, or E-2 statistic was computed or inspected.

---

## 1. Controlling decision

The original one-boundary, all-12-cell V-1B design is replaced by nine fixed
manifests with deterministic, manifest-scoped readiness boundaries:

1. one first short-horizon manifest containing exactly four cells; and
2. eight deferred manifests containing exactly one remaining cell each.

Each manifest has its own exact boundary, selected lineages, `run_identity`,
and one terminal confirmatory record. Readiness and evaluation occur in one
deterministic invocation and one database snapshot. There is no separately
published READY receipt.

The first short-horizon terminal receipt is published first. Every deferred
manifest uses the same boundary rule from the same amendment anchor and must
later proceed independently; no deferred cell waits for another deferred cell
and no earlier result may alter continuation.

This amendment changes only evaluation timing and manifest scope; the
readiness, run, seal, and receipt identities needed to bind that partition; and
the recovery, publication, and rollback mechanics needed to preserve one look.
It does **not** change any V-1A forecast, target, proof seam, lineage rule,
selector, kappa reconstruction, benchmark, regression, QLIKE, bootstrap,
threshold, classification, multiplicity, read-only, or Owner-authority rule.

There remain exactly 12 inferential cells. Each cell may receive exactly one
confirmatory evaluation.

---

## 2. Corrections that govern before any amendment premise

### 2.1 The “37% publication-proof loss” claim is withdrawn

For FAMILY volatility forecasts from 2026-08-26 through 2026-09-04, the
measurement supplied these exact totals:

```text
forecasts = 263,944
proofs    = 263,927
unmatched = 17
coverage  = 263,927 / 263,944
          ≈ 99.993559240%  (rounded to nine decimal places)
```

The session table displayed whole-percent coverage, so small misses appeared
as `100%`. The exact result is the fraction above, not literal 100%, and it
cannot prove that no publication leak of any kind exists. It decisively
refutes a 37% post-installation proof-loss claim.

The pre-installation sessions 2026-08-21, 2026-08-24, and 2026-08-25 had no
volatility publication proofs. They remain inadmissible under frozen proof
law; a proof cannot be retroactively observed.

No publication-proof repair, evidence rewrite, backfill, or proof-law change
is authorized by this amendment.

### 2.2 The “evidence outbox is dropping records” claim is withdrawn

The literal marker `EVIDENCE_OUTBOX_FULL` was absent from service
`srv-da31tfmk1f9s73dsiud0` logs inspected for 2026-09-03 through 2026-09-05.
That establishes only marker absence in that service and interval. It does not
prove that no record could be absent for another reason or outside that scope.
The log result does not enter any V-1 population or manifest choice.

No outbox repair, service change, logging change, or drop-rate conclusion is
authorized by this amendment.

### 2.3 Inter-arrival rates are not selector results

The supplied FAMILY and V9 yield figures were derived from inter-arrival
spacing. They were not produced by running the frozen
`select_non_overlapping(...)` implementation. They are planning rates only.

For every readiness decision:

- exact V-1A population and selector counts govern;
- an inter-arrival estimate may not satisfy a minimum;
- a capacity calculation may not replace a selector count; and
- no estimated yield or date in the source measurement is frozen as an
  observed result.

### 2.4 The six-pair calibration arithmetic is withdrawn

Two different selectors must not be conflated:

1. V-1A §6.3 selects target windows within each cell and session and restarts
   selection each session. At 1H, a full 09:30–16:00 RTH session can contribute
   at most six wholly contained target windows.
2. V-1A §7.2 reconstructs V4C calibration by calling the existing V4C
   `select_non_overlapping(...)` unchanged. That selector is globally ordered
   for the governed lineage and does **not** restart at an XNYS session
   boundary. Its calibration domain is not the §6.3 RTH target-window
   population.

The exact §7.2 and `calibrate_scale(...)` arithmetic is:

```text
split = max(0, len(selected) - 250)
calibration_pairs = selected[:split]

first nonempty calibration_pairs: len(selected) >= 251
MATURE raw-score minimum:          len(calibration_scores) >= 250
necessary selected-pair minimum:   len(selected) >= 500
additional MATURE condition:       effective_n >= 200 and finite positive kappa
```

The thresholds 251 and 500 are exact necessary conditions. The 500-pair
condition is not sufficient because filtering, effective N, and finite
positive kappa must also pass. Dividing either threshold by six is invalid for
the calibration pool.

A correction-only, read-only cross-check of persisted
`ATOM_TRUE_V9_V4B_ACCURACY_1` state produced by that selector showed V9 1H
`non_overlapping_n = 91` at `2026-09-04T19:59:26.869009Z` under the frozen
cutoff. The independent correction artifact reported an end-of-session maximum
of 95 and a `+15` change on each of six consecutive full sessions. The bound
materials do not contain the exact queries, complete predicates, snapshot
identities, and full cohort identity needed to reconcile 91 and 95; they are
therefore treated as non-comparable correction-only observations. Neither is a
V-1A readiness count or may replace strict per-target causal reconstruction.

At a planning rate of 15 selected pairs per full session, moving from 95 to the
500-pair necessary floor takes 27 sessions arithmetically. Correction 2 shows
why that is not a maturity date. In persisted V4C state, the 5M scale remained
`PROVISIONAL` with a 598-pair calibration pool and a set kappa; therefore its
actual calibration-score `effective_n` was below 200 and its `tau` was greater
than 2.99. The 1H calibration pool was still zero, so no actual 1H V4C score-series
effective N had yet been observed. Correction 1's directional-series proxy is
withdrawn by Correction 2.

Thus 500 selected pairs is necessary and demonstrably not sufficient in at
least one governed horizon. The approximately 2026-10-14 date marks only the
projected 1H raw-count floor under the observed rate, no filtering, and no
cohort reset. It does not predict `scale_status = MATURE`. Neither that date,
mid-November, the correction's longer extrapolations, nor any other estimated
date is a readiness fact or amendment boundary.

Accordingly, no quotient derived by dividing V4C calibration thresholds by
the six-per-session RTH target cap governs. In particular, the proposed
42-session, 75-session, 84-session, and universal 15-week claims are not
frozen facts. The exact readiness resolver determines when the cell qualifies.

### 2.5 Among V4C statuses, only scale status can affect V-1A

The scope note is correct on this narrow dependency boundary. In the complete
frozen V-1A contract, `ScaleResult` occurs once, while `range_status`,
`threshold_status`, `calibrate_range`, `build_thresholds`, `RangeResult`, and
`ThresholdResult` do not occur. For each selected V9 target forecast, causal
kappa is usable only when the reconstructed `ScaleResult.status` is `MATURE`
and kappa is finite and strictly positive. Otherwise the target window enters
`n_kappa_unavailable`. FAMILY-VOL has no V4C dependency and its
`n_kappa_unavailable` value is always zero.

The literal READY rule remains the six count minima in §7.1, not a direct
`scale_status` predicate. For V9 only, scale maturity and a finite positive
kappa affect which otherwise valid target windows reach those populations;
all unchanged identity, proof, admissibility, selector, prediction,
persistence, benchmark, and count rules still apply. The scope-note title
therefore must not be read as saying that scale status alone establishes
readiness.

The latest persisted V4C snapshot inspected on 2026-09-05 reported these
scale states and calibration-pool sizes: 30S `MATURE` / 4,773; 1M `MATURE` /
2,866; 5M `PROVISIONAL` / 598; 15M `PROVISIONAL` / 102; 30M `UNAVAILABLE` /
0; and 1H `UNAVAILABLE` / 0. Those are upstream snapshot observations only.
The scope note's phrase “usable kappa today” is not adopted as a V-1A result:
V-1A requires strict per-target causal reconstruction and may not substitute a
latest-state snapshot.

Neither `range_status` nor `threshold_status` is a V-1A readiness, population,
metric-availability, or classification predicate. V-1A computes its
descriptive `coverage_90` directly over `n_windows` as
`mean(realized_volatility_bps <= 1.6448536269514722 *
predicted_volatility_bps)` and defines no `n_range_unavailable` field. Sections
2.6 and 2.8 reconcile the bound correction trail only; their upstream subjects
do not supply an Amendment 2A premise or implementation change.

### 2.6 The fixed 250-pair range window is measured; its binding failure is not

The latest persisted state inspected for this evidence trail reported
`range_status = PROVISIONAL` at 30S, 1M, 5M, and 15M, and `UNAVAILABLE` at 30M
and 1H. The erratum's statement that all six horizons were `PROVISIONAL` is
therefore rejected.

The unchanged construction does establish a fixed-window fact:

```text
split = max(0, len(selected) - 250)
calibration_pairs = selected[:split]
validation_pairs  = selected[split:]
```

Once at least 250 selected pairs exist, the range-validation population is the
trailing 250. Unchanged `calibrate_range(...)` then conjunctively checks score
count and effective N, valid-validation count, coverage-indicator effective N
and interval, effective misses and miss balance, rolling-session effective N
and interval, and finite interval width. The persisted compact horizon state
retains `range_status` and `range_quantile` but not those `RangeResult`
diagnostics. The inspected state therefore cannot identify which predicate or
predicates failed.

Correction 2's stronger diagnosis—that the fixed population makes MATURE
structurally unreachable—is withdrawn. An independent exact-code reachability
check constructed finite 250-pair inputs satisfying the fixed-window
coverage-side requirements; the implementation's conjunction permits a
`MATURE` result. That synthetic counterexample proves only code-level
reachability, not production maturity. Conversely, the erratum's proposed
over-wide-interval explanation is a hypothesis, not a recovered production
fact. Neither diagnosis enters this amendment.

This section is retained because the complete evidence ledger contains the
claim and its erratum; it is not a V-1B gate. The six §7.1 READY predicates
continue to exclude range and threshold status. This amendment does not import
either status, change `calibrate_range(...)`, or add persistence for discarded
range diagnostics. Any observability change or future V-1 integration requires
its own prospective, reviewed phase.

### 2.7 The q3 effective-N table is real; its cross-series extrapolation is rejected

The V2 build receipt inspected for the erratum does contain these
`q3_volatility` values:

| Horizon | Admitted | Effective N | Implied tau |
|---|---:|---:|---:|
| 30S | 1,457 | 12.4003 | 117.4970 |
| 1M | 959 | 16.2447 | 59.0347 |
| 5M | 263 | 56.0726 | 4.6903 |
| 15M | 114 | 114.0000 | 1.0000 |
| 30M | 67 | 67.0000 | 1.0000 |
| 1H | 36 | 36.0000 | 1.0000 |

The implementation computes those values on the V2B q3 magnitude-residual
series `abs(target_bps) - forecast_value_bps`. That is not the V4C scale-score
series `(actual_bps - mean_bps)^2 / q0_bps2`, the threshold series
`abs(actual_bps)`, the range coverage-indicator series, or a V-1A selector
count. The table is evidence of severe serial dependence in the short-horizon
q3 series; it is not a mathematical bound on any different series or on V-1A
readiness.

In the shared `effective_n(...)` implementation, `tau = 1` can arise when
centered variance is numerically unidentifiable or when no positive paired
autocorrelation term is retained. It neither proves independence nor proves
the erratum's “almost certainly not detectable” explanation. No such
interpretation is frozen.

Accordingly, the erratum's claim that all readiness projections become upper
bounds because of this q3 table is rejected. Estimated dates remain planning
only for the independently established reasons in §§2.3–2.4: they are not
exact selector results, valid-score counts, effective-N results on the
governed series, or readiness boundaries.

### 2.8 Threshold status is distinct, undetermined, and outside V-1A

Correction 3 distinguishes threshold's growing calibration pool from range's
pinned validation window. Unchanged `build_thresholds(...)` operates on the
growing calibration pool and requires a nonempty absolute-realized-return
series, at least 20 sessions, and effective N of at least 500. The latest
persisted state covered only eight sessions. That session failure alone
explains `threshold_status = UNAVAILABLE` at every horizon and masks whether
effective N reaches 500 on the actual `abs(actual_bps)` series. Neither outcome
may be inferred now from another series.

The projected 20th session on 2026-09-23 is a prospective observation point,
not a frozen maturity date, readiness boundary, or guarantee. A 30S transition
to MATURE would show that the threshold effective-N condition is satisfiable;
continued UNAVAILABLE would show that effective N remains binding. Until an
authorized future phase observes and freezes that result, this amendment
legislates neither outcome. In all events, `threshold_status` remains outside
V-1A readiness, populations, metrics, and classification under §2.5.

Correction 3 also identifies a latent upstream session-definition mismatch:
V4C currently derives `session_id` from a UTC date while the evidence
scorecard uses `America/New_York`. Its inspected population had zero cutoffs at
or after 20:00 ET and equal counts of ET and UTC dates, so no current impact was
measured. This amendment neither repairs that latent issue nor treats it as a
hold. Any future session-boundary change requires its own reviewed phase.

### 2.9 Cohort rotation uses reset-and-record

The observed 1H selector state reset when its `cohort_hash` rotated. For each
candidate boundary, the resolver rederives the exact governed cohort and
lineage under V-1A. A pre-boundary rotation follows the unchanged V4C reset
law, appears in the frozen §8.2 `cohort_trace`, and cannot be bypassed by
splicing selected pairs from different cohort hashes. This amendment chooses
reset-and-record, not pinning cohort-hash inputs. A post-seal rotation cannot
move or replace the sealed boundary. No interim protected calibration
statistic may be measured merely to forecast a date.

---

## 3. Exact audit facts at the original V-1A boundary

The post-adoption count-only audit used:

```text
evaluation_session = 2026-09-04
evaluation_as_of_at = 2026-09-04T20:00:00.000000Z
```

It found all 12 cells count-insufficient without running protected inference.
The exact populations relevant to the six minima were:

| Cell | `n_windows / sessions` | Regression `windows / sessions` | Each gate `windows / sessions` |
|---|---:|---:|---:|
| FAMILY-VOL 30S | 2,128 / 7 | 985 / 7 | 984 / 7 |
| FAMILY-VOL 1M | 1,159 / 7 | 518 / 7 | 517 / 7 |
| FAMILY-VOL 5M | 274 / 7 | 121 / 7 | 120 / 6 |
| FAMILY-VOL 15M | 126 / 8 | 44 / 7 | 43 / 7 |
| FAMILY-VOL 30M | 69 / 8 | 26 / 6 | 25 / 6 |
| FAMILY-VOL 1H | 37 / 8 | 8 / 4 | 7 / 4 |
| V9-VOL 30S | 1,303 / 2 | 135 / 2 | 132 / 2 |
| V9-VOL 1M | 396 / 2 | 47 / 1 | 46 / 1 |
| V9-VOL 5M | 0 / 0 | 0 / 0 | 0 / 0 |
| V9-VOL 15M | 0 / 0 | 0 / 0 | 0 / 0 |
| V9-VOL 30M | 0 / 0 | 0 / 0 | 0 / 0 |
| V9-VOL 1H | 0 / 0 | 0 / 0 | 0 / 0 |

For this audit the unconditional and seasonal gate population counts were
equal, so the table reports them together. Readiness still verifies each
frozen gate population separately.

V9 1H reached the kappa stage with 39 target windows; all 39 had unavailable
kappa, leaving `n_windows = 0`. The 39 is a target-window accounting count,
not a count of V4C calibration pairs and not a valid subtraction from 500.

The first four cells below are fixed as a prospective short-horizon tranche,
not asserted to be the four objectively earliest cells. The count table alone
does not order future readiness: for example, FAMILY 5M already exceeds the
100-window thresholds but lacks gate sessions, while V9 1M lacks more
sessions. The source's two-to-three-week estimate is planning context only,
not a promise or boundary substitute.

---

## 4. Defect name and decision rationale

The defect is a **cross-constraint slowest-cell readiness bottleneck**.

The original all-cells rule makes the first official result wait for the
slowest of 12 heterogeneous populations even when a fixed subset has met every
prospective minimum. The constituent rules are not mathematically impossible
without another deadline or cap. They compose into stronger hidden floors:

- at 1H, at most six RTH target windows per full session plus the 20-window
  persistence warmup and 100-regression-window minimum require at least 120
  selected target windows, hence at least 20 full sessions even though the
  stated session minimum is 10; and
- for V9 kappa, latest-250 withholding plus the 250-raw-score MATURE minimum
  requires at least 500 governed selected calibration pairs before effective-N
  and finite-positive-kappa conditions can be decisive; Correction 2's 5M
  state remained scale-PROVISIONAL with a 598-pair calibration pool, so no
  pair-count calendar supplies a sufficient upper bound.

Tiering removes the all-12 slowest-cell gate and eliminates cross-cell waiting
among the eight deferred singleton manifests without weakening either floor.
The first four cells still share one boundary, and deferred execution begins
only after the early terminal receipt. No permission is created to change the
warmup, withholding, MATURE rule, session minimum, or inferential threshold.

---

## 5. Fixed manifest registry

Manifest identifiers, registry order, and membership are exact:

| Order | `manifest_id` | Frozen cells by V-1A §3.3 `cell_order` |
|---:|---|---|
| 1 | `v1b-early-4` | 0 FAMILY-VOL 30S; 1 FAMILY-VOL 1M; 6 V9-VOL 30S; 7 V9-VOL 1M |
| 2 | `v1b-family-5m` | 2 FAMILY-VOL 5M |
| 3 | `v1b-family-15m` | 3 FAMILY-VOL 15M |
| 4 | `v1b-family-30m` | 4 FAMILY-VOL 30M |
| 5 | `v1b-family-1h` | 5 FAMILY-VOL 1H |
| 6 | `v1b-v9-5m` | 8 V9-VOL 5M |
| 7 | `v1b-v9-15m` | 9 V9-VOL 15M |
| 8 | `v1b-v9-30m` | 10 V9-VOL 30M |
| 9 | `v1b-v9-1h` | 11 V9-VOL 1H |

`manifest_registry_order` is serialization order, not a dependency among
orders 2–9. Within a manifest, cells are serialized in ascending original
V-1A `cell_order`; those global values are never renumbered.

The registry is closed:

- every original cell appears exactly once;
- no cell may move between manifests;
- no dynamic “first cells to mature” substitution is permitted;
- no new cell, forecaster, horizon, lineage, or benchmark may be added; and
- no cell may receive a second confirmatory look under another manifest or
  run identity.

After the `v1b-early-4` first attempt is terminally recorded under §7.4, the
program remains incomplete until every deferred manifest is run at its own
first qualifying boundary, regardless of whether the early result is
favorable, unfavorable, or invalid. This requirement forbids selective
continuation; it does not compel the Owner to deploy or execute software.
Only a pre-existing authority or safety rule or an implementation defect may
pause it. A later documentation-first repair preserves confirmatory status
only if it leaves the fixed membership, population, selectors, boundary rule,
metrics, thresholds, and continuation duty unchanged. Any post-result
amendment changing one of those terms makes the affected work a separately
preregistered experiment and forfeits a complete-program V-1 claim under this
decision.

---

## 6. Bound documents and verified adoption identities

### 6.1 Complete evidence artifacts

The Amendment 2A documentation PR contains exactly this amendment and the
following eight complete, byte-identical evidence files:

```text
docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS-ORIGINAL.md
size_bytes = 8314
sha256     = aaa58a0a36f8921bde54f0215f2a189da79a6a5c25b6e9db5d2d4f2b562cf913

docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS.md
size_bytes = 8662
sha256     = 0b21fc0f9e2aec42939fcd74a91debbba916639cb84e95fe96c2bfcd55e41627

docs/evidence/CORRECTION-1-V9-1H-CALIBRATION-ARITHMETIC.md
size_bytes = 8267
sha256     = 06c993a6cd3290e306e75feb73f0facf52fd4ce6f2c04dd1357452cfc26ef3fd

docs/evidence/CORRECTION-1-COVER-NOTE.txt
size_bytes = 3149
sha256     = 9e85f3cfcfe7a0629cf014a218847738793d72d0deb7814329471b9ab5621611

docs/evidence/CORRECTION-2-N-EFF-SATURATION-AND-RANGE-STATUS-DEFECT.md
size_bytes = 7795
sha256     = 24bfda809cc55acb26d46ccdd8a3f741b3b06dccfc064ef00568a714090dc6a5

docs/evidence/CORRECTION-3-THRESHOLD-STATUS.md
size_bytes = 5370
sha256     = 717c4057229a9109803e05e0eb4647e9c4648c2a272e36918f1697552157eeb8

docs/evidence/ERRATUM-TO-CORRECTION-2.md
size_bytes = 4761
sha256     = 37a248d8a29fb258048c27549f06305ab2f5f886c38380d12cebe51da3ef33d4

docs/evidence/SCOPE-NOTE-V1A-READINESS-DEPENDS-ON-SCALE-STATUS-ONLY.md
size_bytes = 4915
sha256     = 8c8079b428e39fee8f41e64af384c540fbb363013dee00ad3e31a285adf8109b
```

For receipt and identity serialization, `evidence_artifacts` is an array in
that exact file order. Each object has exactly `role`, `path`, `size_bytes`,
and `sha256`. The exact roles in order are
`ORIGINAL_MEASUREMENT`, `CORRECTED_MEASUREMENT`, `CORRECTION_1`,
`CORRECTION_1_COVER_NOTE`, `CORRECTION_2`, `CORRECTION_3`,
`ERRATUM_CORRECTION_2`, and `SCOPE_NOTE_V1A_DEPENDENCY`; the other three values
are the corresponding literals above. No entry may be omitted, reordered, or
replaced.

All eight files are preserved whole because their withdrawals, methodological
caveat, correction trail, disagreements, and provenance are material. The
original 8,314-byte file is retained at a distinct historical path so the
superseded language remains auditable. The 8,662-byte measurement is its
corrected replacement; Correction 1 and its cover note document the selector
correction; Correction 2's scale-series finding supersedes Correction 1's
directional effective-N proxy, but its structural range diagnosis is withdrawn
by the erratum; Correction 3 distinguishes threshold's growing pool; and the
scope note confirms the narrow V4C dependency boundary. The erratum's all-six
status sentence and q3 cross-series extrapolation, and the scope note's
repeated calibration-pool and latest-state overstatements, are expressly
rejected in §§2.4–2.7. They are evidence, not controlling law. Where any
conflicts with §2 of this amendment—including literal 100% coverage, “no
leak,” any six-pair calibration cap, a universal 15-week floor, an estimated
readiness date, a claim that 500 selected pairs are required before the
calibration pool is nonempty, a claim that reaching 500 necessarily yields
`PROVISIONAL`, a structural or unreachable range diagnosis, an all-six
`PROVISIONAL` status claim, a universal upper-bound inference from q3, a
latest-state substitute for causal reconstruction, a claim that range maturity
blocks V-1B, or a prediction of threshold maturity—this amendment governs.

### 6.2 Amendment 2A merge identity

After Owner merge, V-1B determines the exact GitHub merge commit that
introduced all nine files specified by §6.1 into `main`.

Before any population derivation, verify that:

- `amendment_merge_sha` is 40 lowercase hexadecimal characters and reachable
  from the exact authorized execution revision;
- it is the Owner-merged main commit for the PR containing this exact path,
  decision ID, all eight evidence paths, byte sizes, and digests, not a branch
  head or caller-supplied arbitrary SHA;
- authenticated repository metadata identifies that PR as merged, has
  `merge_commit_sha = amendment_merge_sha`, and supplies its immutable UTC
  `merged_at`;
- the commit also contains the original V-1A contract; and
- the merge commit's UTC committer timestamp equals the PR's `merged_at` at
  their shared precision.

`T_amend` is the verified PR `merged_at`, rendered as UTC RFC3339
microseconds. A mismatch or unavailable proof is `BLOCKED`; no caller-supplied
time is accepted. Candidate-session rules below use session open, not close,
so an intraday adoption cannot admit a partly pre-adoption session.

### 6.3 Exact TLS prerequisite

The required separate TLS amendment identity is exactly:

```text
tls_amendment_id   = "ATOM-V1A-AMENDMENT-1-TLS-TRUST-ANCHOR-1"
tls_amendment_path = "docs/v-1a-amendment-1-tls-trust-anchor.md"
```

Before V-1B implementation or execution, that exact decision must be
Owner-merged and must resolve the V-1A §15.1 `sslrootcert=system` defect.
V-1B verifies its exact Owner-merged main commit by the same history rules and
records `tls_amendment_merge_sha`. That SHA must be reachable from every
authorized execution revision. This amendment does not choose the replacement
trust-anchor value or otherwise change TLS law.

For a new seal, failure of any required identity proof before evidence reading
is `BLOCKED`. Inconsistency discovered after evidence reading follows the
applicable amended V-1A §14 invalid schema. Exact recovery always follows the
sealed consuming-negative routing in §§7.3 and 8.6 and never returns BLOCKED.

---

## 7. One-pass deterministic readiness and evaluation

### 7.1 Candidate sessions and one snapshot

For every manifest, candidate sessions are the same sequence: qualifying
full-day XNYS sessions under V-1A §5.2 whose local market open is strictly
after `T_amend`, ordered by session date ascending.

For candidate session `S`:

```text
candidate_as_of_at = S regular close = 16:00:00 America/New_York
```

rendered as UTC RFC3339 microseconds.

Each invocation opens exactly one read-only `REPEATABLE READ` transaction. For
a new seal, its first database operation obtains `scan_started_at` from
PostgreSQL `transaction_timestamp()`, rendered as UTC RFC3339 microseconds,
before any evidence-table read; the transaction snapshot is then fixed. A
candidate is completed exactly when
`candidate_as_of_at < scan_started_at`; equality is not completed. Inside that
single snapshot the invocation scans completed candidates in ascending order
and stops at the first READY candidate; if none is READY, it scans all
completed candidates. For each candidate examined it applies only the
unchanged identity and population-building portions of V-1A §§3–8 and §10.3—
identity, proof/admissibility, selector, causal-kappa, persistence, and
benchmark-population rules—at `candidate_as_of_at`, subject to the strict §7.2
prohibitions. V9 lineage selection is recomputed for each candidate by
unchanged §3.2. `scan_started_at` is bound into readiness and cannot be
caller-supplied or changed during the scan.

Exact recovery does not generate or substitute a new `scan_started_at`. It
takes that value only from the retained hash-valid seal and uses the sealed
strict cutoff to enumerate completed candidates and rederive the earliest
boundary. The recovery transaction's first database operation separately
obtains `recovery_started_at` from `transaction_timestamp()` and requires
`recovery_started_at > scan_started_at`; `recovery_started_at` does not enter
either identity and cannot change the sealed candidate set.

A candidate is READY only if every cell in the fixed manifest satisfies all
six predicates:

```text
n_regression_windows            >= 100
n_regression_sessions           >= 10
n_unconditional_gate_windows    >= 100
n_unconditional_gate_sessions   >= 10
n_seasonal_gate_windows         >= 100
n_seasonal_gate_sessions        >= 10
```

The manifest boundary is the earliest candidate satisfying every predicate
for every manifest cell. Its session and close become `evaluation_session` and
`evaluation_as_of_at`. No operator may choose a later or earlier boundary.

Deferred manifests always scan from this same post-`T_amend` first candidate,
even when their invocation occurs after the early receipt. The early result
does not reset their clock or population.

### 7.2 Count-only scan

Before a boundary is sealed, the invocation may compute only:

- identities, selected-lineage transition events, proof/admissibility status,
  timestamps, mutually exclusive row accounting, exact selector membership,
  kappa availability status, persistence availability,
  benchmark-population membership, and the six counts above; and
- finite-validity predicates strictly necessary for population membership.

It may not compute, retain, log, serialize, or branch on:

- `mae_bps`, any rank correlation, level ratio, coverage, MZ coefficient or
  fit, `enc_b`, any confidence interval, any QLIKE value, aggregate, or loss
  difference, any gate result, any bootstrap draw, or any cell
  classification; or
- E-2 `|mu|/(kappa*sigma)`, a trading signal, position, option comparison,
  P&L, or capital result.

### 7.3 HOLD, seal, and exact-identity recovery

If no completed candidate is READY, the invocation performs no protected
computation, writes no file or receipt, writes nothing to stderr, exits with
code 0, and writes exactly this UTF-8 JSON plus one final newline to stdout
under V-1A §13.7 canonicalization:

```json
{"manifest_id":"<exact §5 identifier>","mode":"V1B","readiness_status":"HOLD"}
```

The angle-bracket token is replaced by the validated manifest ID; it is not
emitted literally. HOLD is expected, does not consume the manifest's
confirmatory look, and may be checked again later.

If an earliest candidate is READY, the invocation must, before any protected
computation:

1. construct and validate the exact §8 `readiness` object;
2. construct and validate the exact §8.4 `run_identity`;
3. freeze both objects, construct and hash the complete non-result seal record,
   and successfully emit it to the existing execution-log sink; and
4. continue in the same process and same database snapshot to compute the
   unchanged V-1A results at that sealed boundary.

`seal_record_body` has exactly:

```text
seal_schema_version
initial_authority_proof
readiness_identity_body
readiness
run_identity_body
run_identity
```

with `seal_schema_version = "ATOM-V1B-MANIFEST-SEAL-1"` and
`initial_authority_proof` equal to the complete passing V-1A §15.3 proof
obtained before evidence reads. The emitted `seal_record` has exactly those six
fields plus:

```text
seal_record_sha256 = sha256(canonical_json(seal_record_body))
```

It is written as canonical UTF-8 JSON plus one newline. The full record is
count-and-identity evidence only; it contains no protected statistic. The run
operator must retain the captured record through terminal-receipt review. A
logger error or inability to capture the complete record occurs after evidence
reading but before sealing; it routes to PRE-CELL INVALID with all three §8.6
seal fields null and reaches no protected computation.

Successful completion of step 3 is the exact seal and establishes and consumes
the manifest's sole confirmatory identity. Failure before that point is
pre-seal and reaches no protected computation. No human or second process
chooses whether to continue based on a protected result. The identity, rather
than an operating-system process, is the one look.

If the process fails after sealing but before producing a complete receipt,
re-execution is permitted only as exact recovery from the retained, hash-valid
seal record under the same `readiness_identity` and `run_identity`. The sole
authorized process input for that record is the validated local seal-record
file in §10.2; no caller may reconstruct fields or supply a hash alone. Before
any recovered protected calculation, the process must rederive and exactly
match the sealed authorized revision, runtime manifest, evidence and TLS
identities, manifest, boundary, lineages, cohort trace, counts, database
identity, reader identity, identity bodies, and all three hashes. A recovered
run may use a new read-only snapshot only to reproduce the already sealed
time-bounded population; any identity or input mismatch stops terminally
`INVALID` and cannot create a replacement identity. Exact recovery is V-1A
§19 reproducibility of the same look, not a second look.

The first complete evaluated or consuming-negative receipt produced under the
sealed identity must be preserved and submitted. It cannot be discarded or
replaced because of its result. If exact recovery cannot complete, the sealed
manifest terminates through the §8.6 consuming-negative route. No protected
partial value may appear in a log or negative receipt.

Loss or concealment of a successfully emitted seal record cannot authorize a
rerun. It is a protocol breach: the affected manifest has no conforming
terminal receipt, V-1 remains incomplete, and a documentation-first incident
determination may record `INVALID` but may not reconstruct results or create a
new confirmatory identity.

### 7.4 First-result order

The early manifest may seal without a prior terminal receipt. No deferred
manifest may seal until `v1b-early-4` has an official terminal receipt. Before
opening a database connection or reading evidence, every deferred invocation
hash-verifies authorized `main` history for that receipt as defined in §8.6.
If none exists, it writes no file, writes nothing to stderr, exits with code 0,
and writes exactly this canonical UTF-8 JSON plus one final newline to stdout:

```json
{"manifest_id":"<exact deferred §5 identifier>","mode":"V1B","readiness_status":"WAIT_FIRST_MANIFEST"}
```

The angle-bracket token is replaced by the validated deferred manifest ID.
This wait is pre-evidence and non-consuming. A failed early process must first
complete exact-identity recovery under §7.3 or publish its consuming-negative
terminal receipt; it cannot be replaced with a new early identity.

Once the early terminal receipt exists, each deferred manifest scans from the
same first post-`T_amend` candidate specified by §7.1. Waiting therefore
exposes no deferred protected statistic and does not change the deferred
boundary. An invalid early result changes only final program status, not
deferred continuation.

---

## 8. Manifest-scoped evaluated receipt

### 8.1 Exact top-level delta

The evaluated schema version becomes:

```text
ATOM-V1B-MANIFEST-RECEIPT-1
```

Its top-level key set is exactly the V-1A §13 evaluated key set plus:

```text
amendment_id
amendment_path
amendment_merge_sha
tls_amendment_id
tls_amendment_path
tls_amendment_merge_sha
evidence_artifacts
manifest_id
manifest_registry_order
manifest_cells
readiness
seal_record_sha256
result_scope
```

No other top-level key is added or removed. Exact fixed values and domains:

```text
schema_version          = "ATOM-V1B-MANIFEST-RECEIPT-1"
decision_id             = "ATOM-V1A-VOLATILITY-FIRST-FREEZE-1"
amendment_id            = "ATOM-V1A-AMENDMENT-2A-TIERED-READINESS-1"
job_id                  = "ATOM-V1B-READ-ONLY-VOLATILITY-SCORECARD-1"
contract_path           = "docs/v-1a-volatility-first-freeze.md"
amendment_path          = "docs/v-1a-amendment-2a-tiered-readiness-boundaries.md"
code_version             = "ATOM-V1B-MANIFEST-1"
amendment_merge_sha      = exact verified Amendment 2A merge SHA
tls_amendment_id         = "ATOM-V1A-AMENDMENT-1-TLS-TRUST-ANCHOR-1"
tls_amendment_path       = "docs/v-1a-amendment-1-tls-trust-anchor.md"
tls_amendment_merge_sha  = exact verified TLS-amendment merge SHA
evidence_artifacts        = exact §6.1 array
manifest_id               = exact §5 identifier
manifest_registry_order   = exact §5 integer
manifest_cells            = exact §8.2 array
seal_record_sha256        = exact §7.3 seal-record digest, 64 lowercase hex
result_scope              = "MANIFEST_ONLY"
```

All unchanged V-1A top-level fields retain their exact types and semantics
except `schema_version`, `code_version`, `verified_main_sha`,
`evaluation_session`, `evaluation_as_of_at`, `cells`, `overall_status`,
`overall_reason_codes`, `scouting_disclosure`, `run_identity`, and official
filename as expressly amended below.

### 8.2 Exact manifest and readiness objects

`manifest_cells` contains exactly the fixed manifest's cells in ascending
original `cell_order`. Each object has exactly:

```text
cell_order integer 0..11
forecaster string FAMILY-VOL | V9-VOL
horizon    string 30S | 1M | 5M | 15M | 30M | 1H
```

`readiness` has exactly:

```text
rule_version
status
amendment_merged_at_utc
scan_started_at
first_candidate_session
boundary_session
boundary_as_of_at
selected_lineages
cohort_trace
counts
readiness_identity
```

with:

```text
rule_version            = "ATOM-V1B-MANIFEST-READINESS-1"
status                  = "READY"
amendment_merged_at_utc = T_amend as UTC RFC3339 microseconds
scan_started_at          = exact §7.1 transaction timestamp
first_candidate_session = first qualifying §7.1 YYYY-MM-DD session
boundary_session        = earliest passing candidate YYYY-MM-DD
boundary_as_of_at       = its close as UTC RFC3339 microseconds
readiness_identity      = 64 lowercase hex
```

`selected_lineages` is the V-1A §13.6 array restricted to those exact cells,
in `manifest_cells` order. It contains exactly one object per manifest cell,
including FAMILY cells. Every object retains its original global `cell_order`
and exact base schema.

`cohort_trace` is empty for FAMILY cells. From the first completed candidate
examined through the boundary candidate inclusive, every V9 cell records one
`INITIAL` event and one `ROTATION` event at each later examined candidate whose
canonically serialized `selected_lineage_identity` differs from that cell's
previous event. No post-boundary event is included. Events are ordered by
`candidate_session`, then `cell_order`, and each object has exactly:

```text
cell_order
forecaster
horizon
candidate_session
event_type
selected_lineage_identity
```

`forecaster = "V9-VOL"`; `event_type` is `INITIAL | ROTATION`;
`selected_lineage_identity` is always the complete exact V9 lineage object with
exactly `v3_model_version`, `symbol`, `horizon`, `cohort_id`, and
`cohort_hash`. If unchanged V-1A §3.2 selects its reserved sentinel, the trace
serializes that exact five-field sentinel object, never `null` or a projection.
At the READY boundary the final event must equal that evaluated cell's
`lineage_identity` after canonicalization. The trace is count/identity evidence
only and never carries a score, effective N, kappa, range, gate, or
classification value.

`counts` is an array in the same order. Each object has exactly:

```text
cell_order
forecaster
horizon
n_regression_windows
n_regression_sessions
n_unconditional_gate_windows
n_unconditional_gate_sessions
n_seasonal_gate_windows
n_seasonal_gate_sessions
all_minima_pass
```

All six counts are nonnegative integers and `all_minima_pass` is exactly
`true`. A failing count cannot appear in an evaluated receipt.

`evaluation_session` equals `readiness.boundary_session` and
`evaluation_as_of_at` equals `readiness.boundary_as_of_at`. For every
`readiness.counts[i]`, the sole evaluated `cells` object with the same
`cell_order` must have equal values for all six identically named count
fields. The §8.4 `run_identity_body.selected_lineages` array equals
`readiness.selected_lineages` after canonicalization. Each evaluated cell's
`cell_order`, `forecaster`, and `horizon`, in order, equals both the
corresponding `manifest_cells` object and the three outer fields of the
corresponding `readiness.selected_lineages` wrapper. Its
`cells[i].lineage_identity` equals
`readiness.selected_lineages[i].lineage_identity` after canonicalization. The
FAMILY inner object has exactly `quant_id`, `formula_version`, `symbol`, and
`horizon`; the V9 inner object has exactly `v3_model_version`, `symbol`,
`horizon`, `cohort_id`, and `cohort_hash`, as in unchanged V-1A §13.6. Any
mismatch is `INVALID`.

### 8.3 Exact readiness identity

`readiness_identity_body` has exactly:

```text
decision_id
amendment_id
job_id
contract_path
amendment_path
verified_main_sha
v1a_merge_sha
amendment_merge_sha
tls_amendment_id
tls_amendment_path
tls_amendment_merge_sha
evidence_artifacts
manifest_id
manifest_registry_order
manifest_cells
rule_version
status
amendment_merged_at_utc
scan_started_at
first_candidate_session
boundary_session
boundary_as_of_at
selected_lineages
cohort_trace
counts
reader_identity
database_identity
runtime_manifest_sha256
```

`database_identity` is the exact V-1A §13.2 object;
`runtime_manifest_sha256` is the exact digest from §13.2.1; and
`readiness_identity = sha256(canonical_json(readiness_identity_body))` under
unchanged V-1A §13.7. This is a subobject-integrity hash. It is not a separate
READY artifact and does not itself prove that an operating-system process
persisted a result.

The complete `runtime_identity` and `authority_proof` remain bound by the
outer receipt hash. The invocation passes unchanged runtime verification and
the complete V-1A §15.3 authority proof before evidence reads and again before
receipt construction. On a new-seal invocation, a failed first check is
BLOCKED. On exact recovery, any failed or unavailable first check routes to
consuming PRE-CELL INVALID under §8.6. A failed final check after truthful cells
exist uses the amended post-evaluation authority-invalid schema in either
mode.

### 8.4 Exact run identity

The base V-1A §13.6 `selected_lineages` array is restricted to the manifest.
`run_identity_body` has exactly:

```text
decision_id
amendment_id
job_id
contract_path
amendment_path
verified_main_sha
v1a_merge_sha
amendment_merge_sha
tls_amendment_id
tls_amendment_path
tls_amendment_merge_sha
evidence_artifacts
manifest_id
manifest_registry_order
manifest_cells
readiness_identity
evaluation_session
evaluation_as_of_at
runtime_manifest_sha256
selected_lineages
```

`run_identity = sha256(canonical_json(run_identity_body))` under unchanged
V-1A §13.7.

Bootstrap streams do not depend on manifest or `run_identity`: unchanged
V-1A §10 instantiates `random.Random(0)` separately for each cell and each
benchmark. Partitioning may not change a cell's row order, RNG calls, draws,
fit, interval, or classification. Any change is a protocol defect.

### 8.5 `cells`, status, disclosure, and filename

V-1A §13.5 is amended only as follows:

- `cells` contains exactly `manifest_cells.length` objects, not 12;
- every object retains the complete unchanged base cell schema;
- objects appear in manifest order with original global `cell_order`; and
- no nonmanifest cell or placeholder is serialized.

`overall_status` and `overall_reason_codes` retain exact V-1A §16.5 derivation
over the manifest cells only. Because the field name is retained for
compatibility, `result_scope = "MANIFEST_ONLY"` is mandatory. A manifest
`PASS` or `FAIL` is not an all-V-1 verdict.

The five V-1A §17 disclosure strings remain first and unchanged. Append these
strings in exactly this order:

6. `A 2026-09-04 post-adoption audit inspected only identities, timestamps, accounting counts, selector counts, availability, and minimum failures; all 12 cells were count-insufficient and no protected V-1 inferential result was computed.`
7. `A 2026-09-05 cadence measurement inspected counts, timestamps, publication-proof presence, and inter-arrival gaps; its rates were not frozen selector results.`
8. `A 2026-09-05 correction and cover note withdrew the six-calibration-pairs-per-session and universal 15-week V9 1H claims; their persisted-selector rates and readiness dates remain planning evidence, not V-1A readiness results.`
9. `A 2026-09-05 second correction used persisted state and status values plus arithmetic, showed that 500 selected pairs was insufficient at 5M, and withdrew the directional effective-N proxy; its structural range diagnosis was later withdrawn, and range and threshold statuses are not V-1A inputs.`
10. `A 2026-09-05 third correction established that threshold_status uses a growing absolute-realized-return pool, was session-count-masked at eight sessions, and remains undetermined; its 2026-09-23 observation point is not a V-1A boundary, and its latent UTC-versus-ET session mismatch had no measured current impact.`
11. `A 2026-09-05 erratum correctly withdrew the claim that fixed-250 range validation makes MATURE structurally unreachable; its all-six-PROVISIONAL status statement and cross-series q3 effective-N extrapolation are rejected, and the actual failing range predicate remains unobserved.`
12. `A 2026-09-05 scope note correctly established that only scale among V4C component statuses can affect V-1A and that FAMILY-VOL has no V4C dependency; its claim that 500 selected pairs are needed before the calibration pool is nonempty and its latest-state substitute for causal kappa reconstruction are rejected.`
13. `Before Amendment 2A, no enc_b value, encompassing coefficient, bootstrap interval, QLIKE value or summary, gate result, cell classification, or E-2 |mu|/(kappa*sigma) statistic for an Amendment 2A boundary was computed or inspected.`

If independent review disproves statement 13 for a cell, unchanged V-1A §17
invalidates that cell for confirmatory claims. The cell cannot move or rerun to
cure preinspection.

The sole official evaluated filename is:

```text
docs/v-1b-volatility-scorecard-receipt-<manifest_id>-<evaluation_session>-<run_identity>-<receipt_sha256>.json
```

V-1A §13.7 canonical JSON and receipt-self-hash rules are unchanged.
Before publication, independent review retrieves the retained §7.3 seal
record, recomputes its three hashes and identity bodies, and verifies that the
receipt's `readiness`, `run_identity`, and `seal_record_sha256` match it
exactly. Failure is `INVALID`.

### 8.6 Negative receipts and exact routing

The three V-1A §14 negative schemas retain their base keys and add exactly:

```text
amendment_id
amendment_path
amendment_merge_sha
tls_amendment_id
tls_amendment_path
tls_amendment_merge_sha
evidence_artifacts
manifest_id
manifest_registry_order
manifest_cells
readiness
sealed_run_identity
seal_record_sha256
result_scope
```

Fixed string fields equal §8.1. `result_scope = "MANIFEST_ONLY"`.
`manifest_cells` is the exact §8.2 array. In BLOCKED, either merge SHA is null
only when failure of that exact merge-identity proof is the blocking cause;
otherwise it is verified. Both are non-null in either INVALID schema.
Before sealing, `readiness`, `sealed_run_identity`, and `seal_record_sha256`
are all `null`. After sealing, `readiness` is the complete sealed §8.2 object,
`sealed_run_identity` is the exact §8.4 `run_identity`, and
`seal_record_sha256` is the exact §7.3 digest; none can be non-null unless all
three are non-null.

Every negative receipt with non-null `readiness` is cross-bound to the retained
seal record. Its inherited `verified_main_sha`, `v1a_merge_sha`,
`reader_identity`, and `database_identity` equal the corresponding values in
the sealed `readiness_identity_body`; `evaluation_session` equals
`readiness.boundary_session`; and `evaluation_as_of_at` equals
`readiness.boundary_as_of_at`. Its amendment, TLS, evidence, manifest, and
readiness fields also equal the sealed values after canonicalization.

For a consuming PRE-CELL INVALID receipt, the inherited `authority_proof` is
non-null and equals the seal record's `initial_authority_proof`. For a
POST-EVALUATION AUTHORITY INVALID receipt, the inherited
`initial_authority_proof` equals that same sealed object and its inherited
`run_identity` equals both `sealed_run_identity` and the seal record's
`run_identity`. BLOCKED has no sealed route: all three seal fields remain null.

Their schema versions become respectively:

```text
ATOM-V1B-MANIFEST-BLOCKED-RECEIPT-1
ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1
ATOM-V1B-MANIFEST-POST-EVALUATION-AUTHORITY-INVALID-RECEIPT-1
```

On a new-seal invocation, missing, duplicate, extra, or invalid amendment,
evidence, TLS, boundary, lineage, count, revision, or prior-terminal identity
discovered before evidence reading routes to BLOCKED with the unchanged
singleton base reason code. The same defect after evidence reading but before
sealing routes to PRE-CELL INVALID with its unchanged singleton base reason
code and null readiness.

After a hash-valid seal record has been accepted and exact recovery has begun,
every preflight, initial runtime, initial authority, repository, credential,
database, TLS, sealed-identity, or sealed-input failure
or inability to verify found before protected calculation—including before
evidence reading—routes instead to consuming PRE-CELL INVALID with the sealed
`readiness`, `sealed_run_identity`, and `seal_record_sha256`. Recovery can
never return BLOCKED, clear those fields, or authorize a replacement identity.

After sealing, a calculation exception, receipt-construction or serialization
failure, final lineage/count mismatch, or late duplicate discovery routes to
PRE-CELL INVALID with non-null readiness, `sealed_run_identity`, and
`seal_record_sha256`; any receipt-construction defect may be repaired only to
serialize that negative
record and may not recompute under a new identity. Final authority failure
after truthful cells exist routes only to POST-EVALUATION AUTHORITY INVALID,
also with all three fields non-null. No protected partial statistic is serialized
in either negative schema.

The sole official negative filename is:

```text
docs/v-1b-volatility-scorecard-negative-<manifest_id>-<receipt_sha256>.json
```

An **official terminal receipt** is exactly either:

1. an Owner-merged, schema-valid, hash-valid evaluated receipt under §8.5; or
2. an Owner-merged, schema-valid, hash-valid amended negative receipt with
   non-null `readiness`, `sealed_run_identity`, and `seal_record_sha256`.

A negative receipt with all three fields null records a pre-seal failure,
consumes no confirmatory identity, and is nonterminal; repair and retry remain
governed by unchanged V-1A law. A negative receipt with all three fields
non-null proves the seal was crossed, consumes the identity, and is terminal.
No negative receipt is an official evaluated receipt.

Before publication of any consuming-negative receipt, independent review
retrieves the retained seal record, recomputes `readiness_identity`,
`run_identity`, and `seal_record_sha256` from their exact identity bodies, and
verifies every cross-binding in this section. A missing seal, hash failure, or
mismatch is `INVALID` and cannot authorize another identity.

---

## 9. One look, global multiplicity, and interpretation

### 9.1 One confirmatory look per cell

Before sealing and again during publication audit, inspect authorized `main`
history for every Owner-merged evaluated schema and all three amended negative
schemas in §8.6. Parse, schema-validate, and hash-verify receipts rather than
trusting filenames. For a new seal, the authority proof must show that
`verified_main_sha` is the then-current protected `main` head and descends from
every terminal receipt already merged; a stale authorized SHA cannot hide a
prior look. For exact recovery only, `verified_main_sha` remains the sealed
revision and must be an ancestor of the separately inspected current protected
head, which may contain no conflicting terminal receipt.

The run operator and publication reviewer must also inspect retained
`ATOM-V1B-MANIFEST-SEAL-1` records for the same manifest or any intersecting
cell. A hash-valid seal with no terminal receipt permits only §7.3 recovery
under its exact identity. A different identity is forbidden.

If an official terminal receipt already names the same `manifest_id` or any
intersecting `cell_order`, no new confirmatory identity or terminal receipt may
be created under another revision, runtime, readiness identity, or
`run_identity`. A pre-seal negative with null readiness is not terminal and
does not trigger this bar.

An exact V-1A §19 reproducibility rerun under an already official evaluated
identity may be performed locally, but it cannot create or publish another
official file. If a sealed process failed before any complete receipt existed,
§7.3 permits only exact recovery under that same identity. A same-manifest or
same-cell result under a different identity is a second inferential look, not
a retry. On a new-seal invocation, discovery before evidence reading is
BLOCKED and discovery after evidence reading is PRE-CELL INVALID. Exact
recovery follows §8.6's consuming PRE-CELL INVALID route at either stage. A
later amendment cannot relabel a second look as confirmatory after protected
statistics have been inspected.

The seal establishes the one look; process recovery does not establish a new
one. An Owner decision not to merge a validly generated unfavorable or invalid
receipt does not restore it. The complete seal record is retained execution-log
evidence, not a separately merged READY artifact, so Git history alone cannot
prove that an operator did not conceal an unsubmitted crash or result. Seal-log
retention, mandatory submission, and independent review are procedural
controls; loss or concealment is a protocol breach and leaves the affected V-1
program incomplete and `INVALID`.

### 9.2 Global multiplicity

Tiering does not replenish the inferential budget. Across all manifests:

```text
12 cells * 0.0005 nominal one-sided screen = 0.006
```

The unchanged V-1A caveats govern this report-only nominal sum. No manifest
receives a fresh 12-cell allowance, and no alternate correction may be chosen
after any result is seen.

### 9.3 Scope and final program audit

A manifest receipt answers only whether at least one cell in that exact
manifest is `INFORMATIVE` under V-1A. It does not establish:

- that V-1 as a 12-cell program is complete;
- an options edge or advantage over implied volatility;
- tradability, profitability, production readiness, or capital authority; or
- authority to change a production forecast, cadence, threshold, dashboard,
  broker, instrument, order, or risk limit.

V-1 is **terminal-complete** only when each of the nine manifests has exactly
one official terminal receipt and all nine hashes receive a separate final
program audit. Zero terminal receipts leaves that manifest incomplete; more
than one for a manifest or intersecting cell is a program defect.

The audit returns `INVALID` if any terminal receipt is negative, if any
evaluated receipt or cell is invalid, if the partition is not the exact 12-cell
registry, or if any run-level program defect exists. Only when all nine
terminal receipts are evaluated receipts does it apply unchanged V-1A §16.5
to the union of the 12 unique cells: `PASS` if at least one cell is
`INFORMATIVE`; otherwise `FAIL`. It performs no new statistical computation.
This amendment does not authorize a program-consolidation receipt or make a
partial status the complete-program status.

---

## 10. V-1B implementation and execution delta

### 10.1 Exhaustive implementation surface

The exhaustive V-1A §12.1 implementation surface remains unchanged:

```text
quant/volatility_scorecard.py
tests/test_volatility_scorecard.py
requirements.txt
```

and, only under the existing privilege condition:

```text
migrations/033_authorize_v1_volatility_scorecard_reader.sql
```

No new service, database, table, role, credential, dependency, production
writer, source, or production implementation path is authorized. The local
recovery-seal input in §10.2 is confined to the existing scorecard CLI and is
not a new evidence source or credential. This amendment specifically
authorizes no change to `quant/v9_v4c_predictive.py` or the existing
`select_non_overlapping(...)` implementation.

The separate documentation PR paths authorized by this amendment are:

```text
docs/v-1a-amendment-2a-tiered-readiness-boundaries.md
docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS-ORIGINAL.md
docs/evidence/V-1A-CADENCE-AND-READINESS-MEASUREMENTS.md
docs/evidence/CORRECTION-1-V9-1H-CALIBRATION-ARITHMETIC.md
docs/evidence/CORRECTION-1-COVER-NOTE.txt
docs/evidence/CORRECTION-2-N-EFF-SATURATION-AND-RANGE-STATUS-DEFECT.md
docs/evidence/CORRECTION-3-THRESHOLD-STATUS.md
docs/evidence/ERRATUM-TO-CORRECTION-2.md
docs/evidence/SCOPE-NOTE-V1A-READINESS-DEPENDS-ON-SCALE-STATUS-ONLY.md
docs/v-1b-volatility-scorecard-receipt-<manifest_id>-<evaluation_session>-<run_identity>-<receipt_sha256>.json
docs/v-1b-volatility-scorecard-negative-<manifest_id>-<receipt_sha256>.json
```

They do not expand V-1B implementation scope.

### 10.2 Invocation and required tests

The scorecard may add exactly these two options:

```text
--manifest-id <one exact §5 identifier>
--recovery-seal-file <absolute local path>  # optional; exact recovery only
```

`--manifest-id` is required for every invocation. Absence of
`--recovery-seal-file` selects new-seal mode. Its presence requests exact
recovery, and successful §10.2 seal validation enters recovery mode; before
that success the command remains in input-validation state. The option is
forbidden before a seal exists. No free-form manifest, other option, or new
environment variable is authorized.

The argument is validated against the closed registry before any repository
history check, database connection, or evidence read. An absent, malformed, or
unknown value writes no file, writes nothing to stderr, exits with code 2, and
writes exactly this canonical UTF-8 JSON plus one final newline to stdout:

```json
{"mode":"V1B","reason":"INVALID_MANIFEST_ID","status":"USAGE_ERROR"}
```

This command-line usage failure is not a V-1A receipt and consumes no look.

In recovery mode, before any repository check, database connection, or
evidence read, the process resolves the supplied path without following a
symbolic link and reads exactly one regular file. Its bytes must be canonical
UTF-8 JSON plus one final newline for one complete
`ATOM-V1B-MANIFEST-SEAL-1` record. The process verifies the exact key set,
canonical bytes, `seal_record_sha256`, both identity-body hashes, manifest ID,
and fixed amendment and evidence identities. The file path itself is not an
identity input; only the validated record is. It is a retained local copy of
the record emitted to the existing execution-log sink, and this option
authorizes no network log retrieval.

An absent value, relative path, symlink, non-regular or unreadable file,
noncanonical record, hash failure, or manifest mismatch writes no file, writes
nothing to stderr, opens no repository or database resource, exits with code
2, and writes exactly this canonical UTF-8 JSON plus one final newline to
stdout:

```json
{"manifest_id":"<validated exact §5 identifier>","mode":"V1B","reason":"INVALID_RECOVERY_SEAL","status":"USAGE_ERROR"}
```

The angle-bracket token is replaced by the validated manifest ID. This refusal
does not authorize a new seal or erase an existing one; the operator may retry
only by supplying the original retained, hash-valid record. Loss of that
record remains governed by §7.3.

In addition to every unchanged applicable V-1A test, tests must prove:

- the exact closed registry, original global cell orders, exhaustive 12-cell
  partition, and absence of duplication;
- dynamic substitution and free-form manifests fail closed;
- the first candidate session's market open is strictly after `T_amend`;
- for a new seal, `scan_started_at` is the first database operation's exact
  transaction time, candidate completion uses the strict §7.1 comparison, and
  candidates are scanned in ascending order inside that one `REPEATABLE READ`
  snapshot, stopping at the earliest passing candidate or exhausting all
  completed candidates when none passes;
- exact recovery reuses the sealed `scan_started_at`, obtains a strictly later
  `recovery_started_at`, and never expands or changes the sealed candidate set;
- the optional recovery-seal file is the sole recovery input, validates before
  repository or database access, rejects every noncanonical, unsafe, or
  mismatched input with the exact usage response, and cannot create a new
  identity;
- deferred scans use the same anchor regardless of actual invocation time;
- all six minima use unchanged population and exact selector results;
- inter-arrival, persisted-rate, capacity, effective-N proxy, and calendar
  estimates cannot satisfy readiness;
- the calibration split makes `calibration_pairs` first nonempty at 251
  selected pairs, makes 250 raw calibration scores first possible at 500, and
  does not force either `MATURE` or `PROVISIONAL` merely because 500 is reached;
- a latest V4C status snapshot and V2 q3 effective-N values cannot replace
  strict per-target causal reconstruction, satisfy readiness, or supply an
  effective-N conclusion for a different series;
- V9 prediction availability applies unchanged mature-scale, kappa, and
  predictive-variance law, while `range_status` and `threshold_status` are not
  imported into readiness, populations, metrics, or classification and
  `coverage_90` retains its exact direct V-1A formula;
- different selected V9 lineage identities are never spliced, a cohort
  rotation follows the exact V4C reset law, and `cohort_trace` emits only the
  required ordered full-lineage `INITIAL`/`ROTATION` events;
- HOLD emits the exact stdout/newline/exit behavior and reaches no protected
  metric, fit, QLIKE, gate, bootstrap, or classification path;
- a deferred invocation without the early terminal receipt emits the exact
  `WAIT_FIRST_MANIFEST` behavior before any database connection or evidence
  read;
- READY emits and retains the exact hash-valid seal record before protected
  computation, while a seal-log failure remains pre-seal, reaches no protected
  computation, and routes to null-seal PRE-CELL INVALID;
- exact evaluated and amended negative schemas, hashes, and retained-seal
  cross-bindings, including both consuming-negative authority fields;
- boundary, lineage, count, amendment, TLS, evidence, revision, runtime,
  database, authority, and manifest bindings;
- later evidence cannot move the sealed boundary;
- deferred sealing is blocked until the early official terminal receipt exists
  without changing the deferred boundary;
- evaluated and consuming-negative terminal receipts are both found by the
  prior-look guard, while null-readiness negatives remain nonterminal;
- a retained seal without a terminal receipt permits only exact-identity
  recovery and its digest matches the eventual terminal receipt;
- a second identity for the same manifest or cell is rejected even when
  revision, runtime, readiness, or run identity differs;
- post-seal failure can recover only under the exact sealed identity, and any
  mismatch terminates `INVALID` without a replacement identity;
- terminal completion requires exactly one terminal receipt per manifest and
  any terminal negative makes the complete program `INVALID`;
- manifest-only status derivation and `result_scope` wording;
- global 12-cell multiplicity remains unchanged;
- manifest partitioning leaves each cell's exact row order, RNG streams,
  draws, statistics, and classification invariant; and
- `v1b_implementation_merge_sha` identifies the isolated implementation diff,
  and rollback of that diff preserves every amendment, evidence file, seal,
  and receipt.

If this delta cannot be implemented inside the unchanged exhaustive surface,
stop `BLOCKED` for a documentation-first amendment.

### 10.3 Execution revision and rollback

For each manifest, the exact authorized execution revision is the Owner-merged
main commit containing:

1. V-1A;
2. the exact TLS amendment;
3. this amendment and all eight complete evidence artifacts; and
4. the independently reviewed V-1B implementation.

For every deferred manifest it must also contain the hash-verified early
official terminal receipt. Every new-seal invocation's authority proof must
establish that the revision is the then-current protected `main` head and
includes every terminal receipt already merged before invocation. Exact
recovery instead executes the sealed revision and separately verifies that it
remains an ancestor of the current protected head and that no conflicting
terminal receipt has appeared.

The existing `ATOM_V1B_AUTHORIZED_MAIN_SHA` is set to that exact
per-invocation main commit and verified against `RENDER_GIT_COMMIT` and
`git rev-parse HEAD` before evidence reads. This updates an existing execution
binding; it authorizes no new environment variable.

Authenticated repository metadata also fixes
`v1b_implementation_merge_sha` as the `merge_commit_sha` of the exact
Owner-merged implementation PR in §11 step 3. Its first-parent diff is limited
to the exhaustive §10.1 implementation surface, and every authorized execution
revision must descend from it.

Rollback reverts only that implementation first-parent diff, using a
separately reviewed revert applied to then-current `main`. The per-invocation
`verified_main_sha` is an execution/history identity, not a rollback target.
No rollback may delete or modify this amendment, an evidence artifact, a seal
record, or any receipt. If the implementation diff cannot be cleanly reverted
while preserving those immutable records, stop BLOCKED for a reviewed rollback
plan. History is never reset and receipts/evidence are never deleted or
rewritten.

---

## 11. Publication sequence and authority

Required order:

1. Owner merges the exact separate TLS documentation amendment.
2. Owner merges this documentation-only Amendment 2A together with all eight
   exact complete evidence artifacts after independent final-head review, green
   required checks, and zero unresolved material findings.
3. V-1B implementation is independently reviewed and Owner-merged.
4. `v1b-early-4` runs when READY and its first evaluated or consuming-negative
   terminal receipt is Owner-merged. An evaluated receipt is the intended
   first result; a non-null-readiness negative records terminal failure.
5. Each deferred manifest then runs independently when READY and publishes its
   evaluated or, if sealed execution fails, consuming-negative terminal
   receipt. Earlier results cannot suppress or reorder a deferred manifest's
   deterministic boundary.

Each receipt publication is a separate documentation-only PR adding exactly
one immutable JSON file. The first complete terminal receipt for the sealed
identity is the one submitted; publication is not a favorable-result selection
step. A pre-seal negative remains nonterminal under §8.6. All unchanged V-1A
§18 independent final-head review, green-check, zero-material-thread,
exact-recomputation, and Owner-merge gates apply.

ChatGPT Pro is architecture and final-audit authority. Codex-class agents may
implement, test, and assemble evidence. Only the Owner approves and merges.
No AI has merge, deployment, database-mutation, infrastructure, broker, order,
or capital authority under this amendment.

---

## 12. Explicit non-authorizations

This amendment does not authorize:

- a proof, outbox, or evidence backfill;
- a Family Evidence Cadence change, including 1H realignment;
- an all-cells retry at a later operator-chosen date;
- lowering any count, MATURE, effective-N, bootstrap, interval, or gate rule;
- changing the `calibrate_range(...)` split, range-maturity conditions, or
  threshold-status implementation;
- persisting or emitting discarded `RangeResult` diagnostics, or conducting a
  separate range-calibration investigation, inside V-1B;
- importing a latest V4C state or a V2 q3 effective-N result as a V-1A
  readiness fact or as a substitute for the governed series;
- reading current V4C state as a substitute for strict causal reconstruction;
- inspecting protected results while deciding readiness;
- selecting favorable cells, dates, lineages, manifests, attempts, or
  receipts;
- V-1C dashboard implementation;
- V-2, implied-volatility, options-economics, trading, or capital work; or
- any repository, Render, Supabase, database, broker, or production mutation
  merely because this proposed document exists.

---

## 13. Supersession and unchanged law

On Owner merge, this amendment supersedes only conflicting V-1A provisions
that require:

- one immutable evaluation boundary derived solely from the V-1A merge;
- all 12 cells in one `cells` array, selected-lineage array, run identity, and
  evaluated receipt;
- one all-12-cell overall status; or
- a single V-1B official receipt and rerun identity; or
- rollback of an entire per-invocation head that may already contain immutable
  evidence or receipts.

Sections 5 and 7–10 supply the exact replacements. Every other V-1A clause
remains controlling, including all read-only, evidence, reproducibility,
runtime, database, TLS-as-separately-amended, review, publication,
negative-receipt, and fail-closed requirements.

If this document and an unchanged V-1A sentence appear to conflict outside
the express subjects above, stop `BLOCKED` for Owner and freeze-author
resolution. Do not infer broader authority.

---

## 14. Re-entry statement

The next authorized action after Owner merge of this amendment and the exact
separate TLS amendment is documentation-conforming V-1B implementation only.
No run is valid until that implementation is independently reviewed, all
required checks are green on the exact final head, zero P1/P2/material
findings remain, and the Owner merges it.
