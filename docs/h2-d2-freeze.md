# H2-D-2 date-level parallel architecture freeze

**Status:** LAW — architecture frozen; parallel runtime disabled  
**Current runtime:** `H2-D-1`, bounded and sequential  
**Next possible phase:** H2-D-3 Parallel Canary, only after separate approval

## Decision

The only approved future concurrency unit is one complete historical trading
date. A future persistent date worker owns the full
`H1 → H2B → H2C_RESOLVE → H2C_SCORE` chain.
Frames, quote alignment, family calculations, horizons, target resolution,
verification, persistence, and scoring inside that date remain sequential.
The future canary uses process isolation, never threads, and allows no nested
pool or executor.

This freeze changes no runtime code and grants no authority to execute the
canary. The present `for day in days` path remains the only executable path.
H2-D-3 must use non-writing H1 replay and outcome-verification modes for the two
already-certified dates. H1 may re-fetch and calculate but cannot pass
`--persist-certified`. H2C resolution is a read-only completeness verification,
not the current mutating resolver command. If those modes do not exist, the
canary must add and verify them before it can dispatch two dates.

## Ownership and scheduling contract

1. One coordinator owns the complete, ascending, unique date plan and the
   final ordered receipt. Workers cannot enqueue, split, or reassign work.
2. One worker process exclusively owns one date from claim through validated
   receipt. The job key is the ISO date. Only distinct dates may coexist.
3. Exactly one coordinator may be active. A distributed queue, lease expiry,
   abandoned-worker reassignment, and more than two workers are not authorized.
4. The later canary is capped at exactly two worker processes and the two dates
   frozen below. Completion order cannot change receipt order.
5. For a date with no manifest, the run ID is `h2d-YYYY-MM-DD`. If exactly one
   certified manifest already exists, its immutable run ID is reused. More
   than one manifest for a date is a permanent failure.
6. Each database-owning stage uses its own bounded connection/transaction.
   No worker may hold a database lock while waiting on another worker or on
   provider/network I/O. The two-date canary permits at most two replay-workload
   database connections at once.

The database primary keys and existing per-run advisory locks remain the final
integrity barrier. They do not replace the single-coordinator/date-claim law:
manifest content includes performance fields, so two simultaneous H1 writers
for one date can safely conflict even when their mathematics matches.

## Stage, retry, and failure contract

- Stage order is exact: `H1`, `H2B`, `H2C_RESOLVE`, then `H2C_SCORE`.
- Every stage receipt must return the claimed historical date and run ID. A
  missing or mismatched identity fails the date before the next stage.
- There is no blind or timed automatic retry. Failure quarantines the date.
  An operator may later reauthorize the whole canary date only with the same
  date, run ID, job key, commit, runtime versions, configuration digest, dataset
  digest, session digest, and artifact hash. If the immutable input cannot be
  reproduced exactly, the retry fails.
- H2-D-3 requires exactly one certified manifest and complete outcomes before
  launch. Zero manifests, incomplete outcomes, or more than one manifest fail
  closed. The current write-capable H1 persistence and H2C resolver commands
  are forbidden. A zero-manifest H1 write belongs only to a later, separately
  approved write phase. H2B is never bypassed; content is never overwritten or
  deleted.
- Invalid JSON, nonzero exit, database interruption, missing or uncertified
  manifest, incomplete outcomes, lineage/hash/count/metric drift, or any
  duplicate identity fails the canary. No pending date begins after failure;
  an already-running date may finish only to produce a diagnostic receipt.
- The canary must use fail-stop behavior equivalent to
  `continue_on_failure=False`.
- H2-D-3 opens replay database connections read-only and requires
  `outcome_writes = 0`. Missing outcomes fail before launch; the current
  write-capable resolver is never called. Pre/post manifest, forecast, and
  outcome counts and hashes must match.

## Exact completeness and parity contract

For each date, all of these identities and counts are exact:

- one historical session and one replay run;
- `forecast_count = frame_count × 12 × 6`;
- `outcome_count = frame_count × 6`;
- 12 quant identities, six horizons, and exactly 72 metric objects;
- available plus unavailable counts equal their table totals;
- database primary-key count equals row count for manifests, forecasts, and
  outcomes.

The immutable parity signature includes the date/run identity; pinned commit
and runtime versions; dataset, configuration, session, artifact, manifest,
ordered forecast, and ordered outcome hashes; all counts; the H2B stored
forecast summary; the scoring input summary; and a canonical SHA-256 over all
72 metric objects. The full 72 metrics must also compare field-for-field.
Floating-point equality is exact; no tolerance or reordering is allowed.

The baseline ordered-content hashes are SHA-256 over the UTF-8 stored
`content_sha256` values joined by one LF with no trailing separator. Forecasts
use `(cutoff_at, quant_id, horizon)` order; outcomes use
`(cutoff_at, horizon)` order.

`scoring_hash_summary` alone is insufficient because it hashes admitted input
rows rather than the computed metric values. The current H2-D
`receipt_sha256` is also excluded from mathematical parity because it includes
elapsed timings and memory telemetry. Timestamps, stage timings, RSS,
`outcome_writes`, completion order, and the full operational receipt hash are
diagnostics only.

## Frozen canary sessions

The read-only baseline bundle is
`docs/h2-d2-canary-baselines.json`.

- `2026-06-15` exercises the legacy certified-manifest resume path with run ID
  `h2a-2026-06-15-persistence-v3`.
- `2026-07-22` exercises the newer H2-D cohort and carries the independent
  DB-3 parity receipt.

These stored baselines certify existing immutable evidence; they do not by
themselves authorize or claim a successful parallel canary. H2-D-3 must first
capture a fresh sequential, non-writing control bundle with stage receipt
identities, H2B/scoring summaries, all 72 metrics, and canonical metric hash.
The two-date process canary must match that control exactly.

## Promotion gate

H2-D-3 passes only if both dates complete with exact immutable parity, exact
receipt correlation, zero duplicate rows/identities, no database lock wait or
timeout, and bounded resource use. Any mismatch stops the project at the
sequential runtime. Compute sizing, scaled replay, and production scheduling
remain separate, later decisions.

## Explicit non-goals

H2-D-2 adds no multiprocessing/executor/async runtime, CLI concurrency flag,
queue service, Render service or deployment, Supabase migration or compute-tier
change, evidence insert/update/delete/rewrite, replay execution, V9 mathematics
change, broker path, automatic retry, compute decision, or scaled replay.
