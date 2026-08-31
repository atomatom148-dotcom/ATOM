# H2-D-6 historical-persistence gate freeze

**Status:** LAW — implementation authorized; execution not yet passed
**Current runtime:** bounded H2-D-5 proof complete
**Next gate:** one exact idempotent persistence retry

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

## Exclusions and stopping rule

H2-D-6 changes no V9 mathematics, thresholds, behavior, outputs, or live
service. It authorizes no new historical date, evidence rewrite, deletion,
repair, scheduler, continuous replay, parallel replay, Supabase or Render tier
change, simulator authority, broker authority, or production deployment.

After one final receipt, stop. Restore the benchmark start command to
`sleep infinity` and suspend it. A passing receipt permits a separate decision
for one new certified historical session; it does not itself enable backfill or
continuous operation.
