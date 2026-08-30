# H2-D-2 date-level parallel architecture freeze

**Status:** LAW — architecture frozen; parallel runtime disabled  
**Current runtime:** H2-D-1 sequential  
**Next phase:** H2-D-3 two-date read-only canary

## Decision

H2-D-3 may test concurrency only at the complete historical-date boundary.
Exactly two certified dates may run concurrently in exactly two isolated worker
processes. Everything inside one date remains chronological and sequential:
frames, families, horizons, verification, outcomes, scoring, and receipts.

H2-D-2 changes no runtime and authorizes no replay, deployment, database write,
or infrastructure scaling.

## Canary boundary

1. The coordinator accepts only `2026-06-15` and `2026-07-22`, in ascending
   order, with no duplicates.
2. The coordinator uses at most two worker processes. Each process owns one
   complete date. Workers cannot create another process, thread, executor,
   queue, or asynchronous task.
3. Each worker runs exactly `H1 → H2B → H2C_RESOLVE → H2C_SCORE`. H1 uses a
   non-writing replay/verification mode. H2C resolution verifies existing
   outcomes without inserting, updating, or deleting them. If those read-only
   modes are unavailable, H2-D-3 must add them before the canary can run.
4. Every database connection used by the canary is read-only. The canary may
   read existing certified evidence but may not rewrite, repair, recertify, or
   delete it.
5. A worker failure fails the canary. No automatic retry, replacement worker,
   distributed queue, or production scheduler is authorized.
6. Results are reported in the frozen ascending date order regardless of
   completion order.
7. H2-D-3 is a bounded experiment only. Passing it does not authorize scaled
   replay, production scheduling, Render changes, or Supabase tier changes.

## Exact parity gate

Before the parallel run, execute the same two dates sequentially in the same
read-only mode to create the control receipt. Parallel output must match that
control exactly for each date:

- historical date and immutable replay run ID;
- dataset, configuration, session, artifact, manifest, forecast-content, and
  outcome-content hashes;
- `forecast_count = frame_count × 12 × 6`;
- `outcome_count = frame_count × 6`;
- available and unavailable counts;
- exactly 12 quant identities, six horizons, and 72 metric objects;
- all 72 metric objects field-for-field using the canonical serialization in
  `docs/h2-d2-canary-baselines.json`;
- H2B and scoring receipt correlation;
- zero evidence writes and unchanged pre/post database counts and hashes.

Any numerical, lineage, count, hash, duplicate, ordering, or receipt mismatch
fails the canary. No tolerance, repair, or partial promotion is allowed.

## Operational limits

- Each worker and the whole canary must have a finite timeout.
- On timeout or failure, terminate and join both workers before returning.
- The final receipt records sequential runtime, parallel runtime, speedup,
  worker exit status, and peak memory.
- Performance telemetry never participates in numerical parity.

## Frozen sessions

The immutable identities and counts for the two certified sessions are stored
in `docs/h2-d2-canary-baselines.json`. The bundle intentionally pins behavior,
outputs, evidence, and lineage—not unrelated source-file hashes.

## Promotion

H2-D-3 passes only when both dates complete read-only with exact parity and no
surviving worker. Otherwise ATOM remains on H2-D-1 sequential execution.
