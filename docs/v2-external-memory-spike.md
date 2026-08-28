# ATOM V9 V2 external-memory architecture spike

**Status:** draft; architecture and measurement only. No deployment, schema
change, production database access, or production V2 formula change is part of
this spike.

## Decision and invariants

V2A, V2B, V2C, V2D, their canonical codecs, operation order, constants,
eligibility rules, and hashes remain frozen. The live service becomes a reader
of completed immutable states only. A separate command owns extraction, build,
verification, and publication. Evidence and previously published state rows are
append-only inputs and are never cleanup targets.

There is one important blocker: the frozen `V2ADataset` embeds every admitted
target, observation, pair-support identity, and complete-case identity in
tuples. Consequently the **current in-memory object and serializer are O(n)**.
Disk-backed ingestion alone cannot truthfully demonstrate bounded end-to-end
RAM. The implementation must add streaming, byte-identical component encoders
and disk-backed component views behind new offline-only interfaces; changing
the state schema to references would violate parity and is rejected.

## Proposed data flow

1. The offline command takes an advisory lock keyed by the V2 model identity;
   lock failure exits before creating a workspace.
2. Start one repeatable-read, read-only transaction and select `state_as_of`.
   Read the existing directional and magnitude queries in **4,096-row keyset
   pages**, ordered by `(horizon, cutoff_epoch, forecast_id)`.
3. Create a mode `0700` workspace under an operator-selected filesystem. Write
   each committed page into separate `directional`/`magnitude` staging tables.
   Store float64 canonical tokens (including normalized negative zero where the
   frozen codec does), text identities, source ordinal, and a page digest.
4. Seal ingestion with row counts, first/last identities, and a digest chain.
   Close the database snapshot; subsequent passes read only the workspace.
5. Run deterministic external passes: V2A filters/deduplicates via ordered
   indices and merge joins; V2B scans each exact frozen series order and writes
   sufficient intermediates; V2C merge-joins exact pair support and scans in
   the current left/right and identity order; V2D streams canonical JSON and
   hashes in precisely the current field/tuple order. No parallel reduction is
   allowed where floating-point operation order affects bytes.
6. Deserialize and validate the candidate with the existing frozen codec.
   Compare state bytes, state hash/id, receipt bytes/hash, counts, and lineage
   against the legacy builder during the parity phase.
7. In one database transaction, call the existing atomic state-plus-receipt
   insertion. Commit makes both visible; rollback makes neither visible.
8. Release the advisory lock and recursively delete **only the recorded,
   ownership-marked workspace**, on success or failure.

Every SQL pass has a total order with the immutable record id as final tie
breaker. SQLite is suitable for the prototype; production should use an
embedded engine only after pinning its version, pragmas, collation (`BINARY`),
filesystem, and crash semantics. Application code, not engine aggregate
functions, performs frozen floating-point reductions.

## Smallest interfaces requiring change

| Area | Existing interface | Minimal change |
|---|---|---|
| Web lifecycle | `quant.web._start_v2` restores then calls `provider.start()` | Replace with restore-only construction; no builder dependency or refresh thread. |
| Live provider | `ImmutableV2StateProvider` accepts a builder and exposes `refresh/start` | Split a read-only `ImmutableV2StateProvider(store)` from offline orchestration. Keep capture/status consumers unchanged. |
| Extraction | Nested `PostgresV2StateBuilder.read_pages` | Extract a read-only `iter_evidence_pages(page_size=4096)` protocol, preserving SQL and keys. |
| Frozen math | `build_v2a_dataset`, `calibrate_v2b`, `build_v2c_covariance`, V2D codec | Add offline disk-view/streaming adapters; do not modify formulas or public frozen results. |
| Publication | `PostgresV2StateStore.insert_with_receipt` | Reuse unchanged as the single atomic publish boundary. |
| Offline entry point | none | Add one CLI with advisory-lock, workspace manifest, recovery cleanup, build, parity verification, and publish orchestration. |

No migration is proposed. Database evidence, state, and receipt deletion is not
granted to the builder role.

## Parity strategy and acceptance gates

Parity means byte equality, not approximate numeric equality. Capture frozen
legacy state JSON and receipt JSON first, then run the external builder from the
same repeatable-read snapshot and `state_as_of`. Assert equality of serialized
bytes, SHA-256, state id/hash, receipt hash, every component hash, row counts,
exclusions, effective-N values, first/last source identities, and statuses.

Run this on every existing V2 fixture and production-shaped anonymized fixture,
then on 65,535, 65,536, 65,537, and 200,000 qualified rows. Inject termination
after every lifecycle transition and around both insert statements. Verify no
new state/receipt is visible, old states/evidence are unchanged, the stale
owned workspace is removed on restart, and an unowned path is refused.

This architecture spike does **not** claim the end-to-end parity gate has
passed. The repository has no 65k/200k frozen V2 golden fixtures, and the
streaming frozen codec/external calculations intentionally are not implemented
here. That is the blocking Phase 1 exit criterion, rather than a result to
fabricate.

## Measurements

The included synthetic harness measures only staging plus a deterministic
ordered byte pass. Ubuntu x86-64, CPython 3.11, local overlay filesystem; one
fresh process per result:

| Rows | Pages | Peak RSS | Temp disk | Wall time |
|---:|---:|---:|---:|---:|
| 65,535 | 16 | 27,598,848 B | 5,128,192 B | 2.281166 s |
| 65,536 | 16 | 27,725,824 B | 5,128,192 B | 1.914553 s |
| 65,537 | 17 | 27,721,728 B | 5,128,192 B | 2.510192 s |
| 200,000 | 49 | 27,430,912 B | 15,884,288 B | 6.286476 s |

RSS for this staging pass should remain approximately flat; the row payload is
never retained beyond one page or cursor row. These figures must not be called
end-to-end V2 memory results until all external passes and streaming output are
implemented. CI verifies the boundary/cleanup behavior at 4,097 rows; the four
larger runs are an explicit spike command to avoid burdening the unit suite.

Capacity planning is provisionally linear and must be replaced with measured
end-to-end amplification after Phase 1. Use the observed staging bytes/row and
seconds/row with a conservative **3x disk safety factor** (staging + indices +
outputs) and **2x runtime contingency**:

`disk(N) = 3 * measured_bytes_per_row * N`; `runtime(N) = 2 * measured_seconds_per_row * N`.

Using the 200,000-row run (79.42144 bytes/row and 0.00003143238
seconds/row), that formula gives the following **staging-only synthetic
estimates**, not production commitments:

| Evidence rows | Disk with 3x safety | Runtime with 2x contingency |
|---:|---:|---:|
| 1M | 238 MB (0.222 GiB) | 62.9 s (1.05 min) |
| 10M | 2.38 GB (2.22 GiB) | 629 s (10.5 min) |
| 100M | 23.8 GB (22.2 GiB) | 6,286 s (1.75 h) |

## Failure, restart, and cleanup rules

The workspace contains a manifest with random build id, absolute canonical
path, owner uid, creation time, input snapshot, and phase. Cleanup requires all
of: configured root containment, expected directory prefix, matching uid, and
valid manifest. Symlinks and mount crossings are refused. Startup removes only
validated abandoned workspaces whose lock owner is dead; it never executes SQL
`DELETE`/`TRUNCATE`, touches evidence storage, or removes published artifacts.

Publishing is last and transactional. Receipt/state validation happens before
the transaction. Any exception, signal, disk-full condition, corrupt page,
digest mismatch, lock loss, or parity mismatch rolls back. The process must not
publish a receipt alone, a state alone, or an unavailable/partial candidate.

## Implementation phases

1. **Parity laboratory:** golden bytes, extracted page protocol, disk staging,
   external V2A/B/C/D adapters, boundary datasets, operation-order audit, fault
   matrix, and end-to-end resource measurements. No database writes.
2. **Offline publisher:** CLI, least-privilege role, advisory lock, manifest and
   restart janitor, existing atomic insert, dry-run default, operational metrics.
3. **Live decoupling:** remove builder/thread creation from web startup; restore
   latest compatible immutable state only; retain last-good capture semantics.
4. **Scale qualification:** 1M/10M/100M production-shaped dry runs, disk-full
   drills, runtime window validation, runbook and rollback review.

Promotion is blocked unless every parity byte matches and peak RSS stays within
a predeclared fixed budget across the required cardinalities.

## Risks and blockers

* Frozen payload size itself grows with evidence; a streaming serializer and
  validator are mandatory even after external math is complete.
* SQLite/PostgreSQL collation, NULL, float, and tie behavior can silently alter
  order; canonical tokens and explicit total ordering are required.
* V2B/V2C may contain order-sensitive floating-point loops; SQL aggregates,
  vectorization, and parallel reduction are prohibited without byte proof.
* One database transaction spanning extraction could stress snapshot retention;
  production timing must be tested without weakening snapshot consistency.
* The current runtime database role/publishing privileges may not be appropriate
  for an offline principal; security review is required, but no migration is in
  this spike.
* End-to-end acceptance, production runtime, and production disk estimates are
  blocked on the deliberately unimplemented external adapters and representative
  golden fixtures.
