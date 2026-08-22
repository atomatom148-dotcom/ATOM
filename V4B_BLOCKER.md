# ATOM TRUE V9 — V4B implementation blocker

## Decision

V4B implementation is intentionally stopped before production or test changes.
The frozen V4B contract requires durable immutable compact-state persistence and
forbids automatically creating a third V4 table when no suitable mechanism
exists.

## Repository inspection

Current main provides two V4A append-only evidence ledgers:

- `public.atom_v9_v4_forecasts`
- `public.atom_v9_v4_outcomes`

Migration `008_create_v9_v4a_evidence.sql` explicitly identifies those ledgers
as V4A's only durable state. They store forecast and outcome evidence, not the
compact per-horizon V4B accuracy state. No general-purpose durable immutable
state store exists that V4B can safely reuse without modifying frozen V1, V2,
or V3 state.

The Python V2D accuracy/evidence state is an immutable in-memory value and does
not provide a durable V4 persistence mechanism. The V4A writer is deliberately
limited to SELECT and INSERT operations on the two evidence ledgers and must not
be repurposed into a mutable state writer.

## Smallest architecture decision required

Approve one durable, append-only V4B compact-state relation (plus its immutable
write/read contract) capable of storing:

1. the canonical six-horizon accuracy-state payload;
2. its mathematical SHA-256 state hash;
3. the mathematical `state_as_of` evidence boundary; and
4. enough identity to retrieve the latest compatible state without mutating an
   earlier state.

The approved design must specify whether uniqueness is by state hash alone or
also by symbol/cohort/evidence boundary, and how “latest compatible state” is
selected deterministically. The existing V4A ledgers should remain unchanged.

## Beta quantile dependency decision

The repository declares only `psycopg[binary]` and contains no deterministic
Beta quantile implementation or scientific dependency. V4B also requires exact
deterministic 95% Beta quantiles and forbids inventing an unapproved
approximation. The smallest dependency decision is either:

- approve `scipy.special.betaincinv` through a pinned SciPy dependency; or
- approve a small, repository-owned regularized-incomplete-beta inverse
  implementation with frozen tolerances, iteration bounds, and numerical test
  fixtures.

No quantile approximation or new dependency has been introduced by this
blocker report.

## Current evidence eligibility

Under the frozen V4A implementation, outcomes are created with
`target_timing_status = UNVERIFIED`, the reason
`TARGET_TIMING_UNVERIFIED`, and `proof_eligible = False`. Therefore evidence
created under the current rule cannot populate V4B accuracy state. This does not
block FINAL BPS or exact MOVE% once the persistence and quantile decisions are
resolved; it only leaves historical accuracy unavailable.
