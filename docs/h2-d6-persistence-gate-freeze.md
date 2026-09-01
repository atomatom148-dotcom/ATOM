# H2-D-6 historical-persistence gate freeze

**Status:** COMPLETE — exact frozen execution passed
**Current runtime:** H2-D-7 passed; benchmark is idle and suspended
**Next gate:** a separate bounded read-only qualification freeze

## Decision

H2-D-6 may run one chronological replay of the smallest H2-D-5 session and
exercise the existing append-only forecast and outcome persistence seams. It
does not create a second storage system, add a table, or admit a new date.

| Frozen field | Exact value |
|---|---|
| Historical session | `2026-06-23` |
| Replay run ID | `h2d-2026-06-23` |
| Frame count | `10,332` |
| Forecast count | `743,904` |
| Outcome count | `61,992` |
| D5 metric SHA-256 | `80758914447775d02f9a247ee1e5593714345434ab5204cd43eb65be4a47dc0c` |
| D5 stored-control SHA-256 | `30e0ed37295ae8ff9be29bf818af259165314860aeb5e6468a04ac2eadde6c6b` |

No alternate date or replay identity is accepted.

## Ordered gate

1. Read and verify the frozen manifest, forecasts, outcomes, and all 72 derived
   metrics through the historical score-reader role.
2. Recompute H1 into a private temporary spool with the same sequential V9
   mathematics and require exact lineage, counts, artifact hash, and ordered
   forecast hash.
3. Connect as exactly `atom_historical_replay_writer` and invoke the existing
   append-only forecast writer in `require_existing` compare-only mode with the
   frozen identity. It must compare the complete stored run and return `0`
   writes; a missing manifest must fail before an insert.
4. Connect as exactly `atom_historical_outcome_resolver`, re-fetch the same SIP
   session, and invoke the existing outcome resolver in `require_existing`
   compare-only mode. It must compare every stored outcome and return `0`
   writes; a missing outcome must fail before an insert.
5. Read the control again and require byte-exact equality with the pre-run
   snapshot and both frozen D5 hashes.

A role mismatch, nonzero write count, numerical mismatch, lineage mismatch,
hash mismatch, duplicate, mutation, partial receipt, or database interruption
fails the complete gate.

## Existing database boundary

The existing H2-A/H2-C migrations remain authoritative: forced RLS, append-only
mutation triggers, composite primary keys, and separate forecast-writer,
outcome-resolver, and score-reader credentials. H2-D-6 adds no migration and
grants no privilege. Metrics remain deterministic read-only derivations and are
recorded by hash in the final receipt; no redundant metrics table is added.

## Completion receipt

The completed gate was one exact idempotent persistence retry. It passed on
August 31, 2026.

| Result | Exact value |
|---|---|
| Historical session | `2026-06-23` |
| Replay run ID | `h2d-2026-06-23` |
| Frames | `10,332` |
| Forecasts / outcomes | `743,904 / 61,992` |
| Forecast writes / outcome writes | `0 / 0` |
| Artifact SHA-256 | `cb3f785d2f27fc5db12808461d6676e90c103c5c69bf91f0af59adac8d6f7371` |
| Ordered forecast SHA-256 | `caa66e6a6a94b64ee31224553acf1eb0b2a05d3e7d56e72e4d0c67bb28f26d0d` |
| Metric SHA-256 | `80758914447775d02f9a247ee1e5593714345434ab5204cd43eb65be4a47dc0c` |
| Control SHA-256 | `30e0ed37295ae8ff9be29bf818af259165314860aeb5e6468a04ac2eadde6c6b` |
| Elapsed / replay / outcome retry | `3315.997264s / 2412.221343s / 730.287785s` |
| Peak RSS | `378,848 KiB` |
| Pre/post unchanged | `true` |
| New-date admission / continuous replay | `false / false` |

The exact writer, resolver, and score-reader roles passed. The retry wrote no
evidence and left the stored control unchanged.

## Exclusions and stopping rule

H2-D-6 changes no V9 mathematics, thresholds, behavior, outputs, or live
service. It authorizes no new historical date, evidence rewrite, deletion,
repair, scheduler, continuous replay, parallel replay, Supabase or Render tier
change, simulator authority, broker authority, or production deployment.

After one final receipt, stop. Restore the benchmark start command to
`sleep infinity` and suspend it. A passing receipt permits a separate decision
for one new certified historical session; it does not itself enable backfill or
continuous operation.
