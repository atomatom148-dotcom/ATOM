# ATOM V9 Phase 1B — external V2A parity prototype gate

**Verdict: `BLOCKED_BY_FROZEN_V2A_INTERFACE`.** This investigation stopped at
the mandatory interface gate. No production database was accessed and no
publishing, deployment, migration, live-service, formula, schema, codec,
state, or receipt change was made.

## Precise blocker

The frozen `V2ADataset` result is not a bounded logical view. Its public fields
require concrete tuples containing every admitted target, observation, pair
support identity, and complete-case identity. For q1_momentum / 30S, the
`skeleton`, `directional_subsets[0].observations`, and
`complete_case_target_identities` fields each contain O(n) objects. Constructing
the exact frozen logical result therefore necessarily reconstructs the full
O(n) object graph in RAM.

The canonical identity boundary makes a disk-backed sequence adapter
insufficient. `v2a_dataset_hash` recursively calls `dataclasses.asdict`, which
deep-copies the entire dataclass graph before JSON encoding it. The legacy
builder repeats this expansion when sealing the draft with its hash. Replacing
tuples with SQLite cursors, lazy sequences, paths, or references would change
the frozen result schema and would not be accepted by this canonicalizer.

The required existing V2B verification path independently assumes the same
materialized interface. Its `_series` function constructs an O(n) target
dictionary and concrete `pairs`, `x`, `y`, and `score` tuples. Its frozen
`effective_n` then creates concrete `values` and `centered` tuples (and, for a
non-degenerate series, an autocorrelation list). Those V2B allocations may be
measured separately, but they prevent a lazy proxy from serving as a transparent
drop-in for the existing path without changing frozen interfaces and operation
boundaries.

SQLite staging followed by creation of those tuples would only move ingestion
to disk; it would still materialize the full V2A result and would violate the
explicit instruction not to disguise staging as bounded-memory construction.

## Prototype data-flow decision

The proposed ingestion path would have been ordered fixture iterators → owned
temporary SQLite workspace → deterministic target pass → deterministic family
pass → streaming canonical hash → frozen V2B/V2C/V2D parity verification.
Work stopped before implementing this path because its output cannot cross the
frozen `V2ADataset` boundary while both preserving its exact logical type and
remaining below a fixed memory budget.

## Acceptance and measurements

No parity or resource result is claimed. In particular, the six required
cardinalities and failure-injection matrix were **not run**, because measuring
a staging-only implementation after identifying this blocker would not satisfy
the acceptance criterion. The authoritative Phase 1A measurement already shows
legacy construction at 1,756,434,432 bytes peak RSS for 200,000 rows, far above
the 128 MiB gate.

| Required result | Status |
|---|---|
| Scope q1_momentum / 30S | inspected |
| V2A dataset hash parity | not claimed — blocked before candidate construction |
| V2B/V2C/evidence-manifest parity | not claimed — no valid V2A candidate |
| State/receipt byte and identity parity | not claimed — no valid V2A candidate |
| External V2A peak RSS below 128 MiB | not claimed — frozen output is O(n) |
| Temporary/peak disk usage and runtime | not measured — staging-only figures are non-accepting |
| Required failure tests | not run — no conforming prototype exists to test |
| Workspace cleanup | not applicable — no prototype workspace is created |

## Smallest interface change that would unblock a later phase

A freeze exception would be required for an explicit disk-backed V2A view and
a streaming canonical V2A encoder/hash accepted by streaming V2B/V2C adapters.
The view would need bounded iterators for skeleton rows, family observations,
pair support, and complete cases, plus scalar metadata and exclusions. V2B
would also need exact-order multi-pass reductions that reproduce every frozen
floating-point operation without materializing its `_Series` tuples. Until
that exception is granted, the correct fail-closed result is this blocker,
not a prototype or a parity claim.
