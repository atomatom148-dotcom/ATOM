# ATOM V9 Phase 1B — external V2A parity prototype

**Verdict: PASS.** The approved freeze amendment adds a separate offline-only
SQLite view and external q1_momentum / 30S adapters. The legacy `V2ADataset`,
public V2A→V2D path, production database, publishing, web, migrations, and live
services are unchanged.

## Data flow and invariants

Ordered offline target and observation iterators are admitted into a mode-0700,
ownership-marked temporary workspace in 4,096-row commits. SQLite performs only
ordered storage, grouping, and joins; all floating-point reductions use Python
`math.fsum` in frozen row order. Deterministic passes construct the skeleton,
q1 observations, complete cases, and streaming canonical V2A SHA-256 without
materializing a `V2ADataset`. Separate external V2B and V2C adapters scan the
view and return the existing bounded result dataclasses. The external V2D
adapter produces and validates the existing canonical state. Receipt creation
uses the existing frozen receipt codec.

The external path has no row ceiling, sampling, truncation, `OFFSET`, or window.
The exact frozen paired-IPS operation order is retained. A non-degenerate input
can require quadratic-time ordered lag passes, matching the frozen algorithm;
the authoritative constant-residual fixture takes its identical early-return
path.

Every successful read revalidates staged payload digests, ownership metadata,
and the streaming dataset hash. Success and all exceptions close and remove
only the validated owned workspace. Cleanup refuses paths outside the selected
root, names without the owned prefix, absent/invalid markers, and marker/path or
UID mismatches.

## Exact parity

The 16-row Phase 1A golden fixture was rebuilt through both paths in one test.
Equality is exact for the V2A hash, V2B component hash, V2C value/component
hash, evidence manifest, canonical state bytes, state hash/ID, canonical receipt
bytes, and receipt SHA-256. The six cardinality dataset and state hashes also
match the authoritative fresh-process legacy results checked into
`docs/v2-frozen-schema-measurements.json`.

## Fresh-process measurements

Linux x86-64, CPython 3.14.4, local overlay filesystem. `ru_maxrss` is absolute
process peak RSS. Each row was run in a new interpreter. Temporary disk is the
sealed workspace; peak temporary disk is sampled before and after every page
commit and ordered-pass seal. V2B/V2C/V2D verification runs after the recorded
external-V2A peak and is not attributed to that memory gate.

| Rows | External V2A peak RSS | Temp disk | Peak temp disk | End-to-end runtime |
|---:|---:|---:|---:|---:|
| 1,000 | 25,546,752 B | 999,522 B | 999,522 B | 0.377 s |
| 10,000 | 28,446,720 B | 9,740,386 B | 9,740,386 B | 3.907 s |
| 65,535 | 30,568,448 B | 69,914,722 B | 69,914,722 B | 17.091 s |
| 65,536 | 30,756,864 B | 69,914,722 B | 69,914,722 B | 25.844 s |
| 65,537 | 30,793,728 B | 69,914,722 B | 69,914,722 B | 19.901 s |
| 200,000 | 30,560,256 B | 216,342,626 B | 216,342,626 B | 49.364 s |

The 200,000-row peak is 29.14 MiB, leaving 98.86 MiB below the fixed 128 MiB
budget. Peak RSS remains essentially flat from 65,535 through 200,000 rather
than growing proportionally with evidence count.

## Failure matrix

Focused tests cover duplicate identity, missing target, wrong formula, wrong
data/source schema, non-causal observations, a 4,096/4,097 page-boundary
omission, staged-payload corruption, simulated disk full, interruption during
ingestion, interruption during the ordered pass, refusal to clean an unowned
path, and parity mismatch validation. Every construction failure removes its
owned workspace; corruption and mismatch fail closed before V2B.

The representative side-by-side fixtures additionally cover varied targets and
forecasts, serially correlated residuals, Effective N below raw N, nonzero bias
and variance, identifiable and unidentifiable slopes, supported positive
covariance, all-evidence-excluded behavior, frozen exclusion counts, and exact
canonical duplicate selection. Every fixture requires exact V2A, V2B, and V2C
results/component hashes, evidence manifest, canonical state bytes and state
ID, and canonical receipt bytes/hash. A dependency-free statement coverage gate runs
the real adapter tests under `trace` and requires at least 80% coverage.

## Final retained-lag correction

Neither external Effective-N path retains an in-memory rho vector. Each lag is
calculated in frozen order; one odd/even IPS pair is held at a time, and each
accepted weighted term is staged in an ordered SQLite workspace table. A final
ordered cursor feeds `math.fsum`, preserving the legacy summand order and exact
binary64 result while RAM remains bounded even when many lags are retained.

The side-by-side retained-lag fixture exercises at least four retained lags in
both directional and covariance-score paths and requires exact V2A/V2B/V2C,
state, and receipt parity. The additional 65,537-row non-degenerate fixture ran
in a fresh process with alternating residuals:

| Rows | V2A peak RSS | V2B/V2C verification peak RSS | Temp / peak disk | Runtime | Cleanup |
|---:|---:|---:|---:|---:|:---:|
| 65,537 | 30,560,256 B | 30,560,256 B | 70,864,994 B | 15.008 s | PASS |

Both independently sampled RSS values are 29.14 MiB, below 128 MiB. The local
CI-equivalent full suite passes with 1,083 tests, 7 skips, and 292 subtests; the
coverage gate reports 94.92% statement coverage (299/315), above 80%. Hosted CI and Sonar
results remain pending on PR #186; no local result is represented as a hosted
service result.

## Acceptance

```
SCOPE: q1_momentum / 30S
ROWS: 200000
DATASET_HASH_MATCH: YES
V2B_HASH_MATCH: YES
V2C_HASH_MATCH: YES
STATE_BYTES_MATCH: YES
STATE_ID_MATCH: YES
RECEIPT_HASH_MATCH: YES
PEAK_RSS: 30,560,256 B (< 128 MiB)
WORKSPACE_CLEANUP: PASS
```
