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
| 1,000 | 25,550,848 B | 819,298 B | 819,298 B | 0.324 s |
| 10,000 | 28,262,400 B | 8,040,546 B | 8,040,546 B | 2.081 s |
| 65,535 | 29,708,288 B | 58,458,210 B | 58,458,210 B | 13.483 s |
| 65,536 | 29,847,552 B | 58,458,210 B | 58,458,210 B | 12.551 s |
| 65,537 | 29,708,288 B | 58,458,210 B | 58,458,210 B | 12.552 s |
| 200,000 | 29,593,600 B | 180,981,858 B | 180,981,858 B | 40.576 s |

The 200,000-row peak is 28.22 MiB, leaving 99.78 MiB below the fixed 128 MiB
budget. Peak RSS remains essentially flat from 65,535 through 200,000 rather
than growing proportionally with evidence count.

## Failure matrix

Focused tests cover duplicate identity, missing target, wrong formula, wrong
data/source schema, non-causal observations, a 4,096/4,097 page-boundary
omission, staged-payload corruption, simulated disk full, interruption during
ingestion, interruption during the ordered pass, refusal to clean an unowned
path, and parity mismatch validation. Every construction failure removes its
owned workspace; corruption and mismatch fail closed before V2B.

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
PEAK_RSS: 29,593,600 B (< 128 MiB)
WORKSPACE_CLEANUP: PASS
```
