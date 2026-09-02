# L-1 evidence ledger throughput freeze

**Status:** PROPOSED — documentation-only freeze; implementation is queued behind the E-1 receipt and an owner-approved active-phase pointer change  
**Current runtime:** `atom-v9-thin`, V4 worker, and SIM-4 worker at `941b3e2`; Family Evidence Cadence active since August 31  
**Next gate:** E-1 receipt (separate phase, unchanged), then the pointer change, then the L-1 implementation PR under the merge gate

## Finding

Measured on September 2, 2026 by read-only SQL over `public.atom_v9_v4_forecasts`
and `public.atom_v9_v4_outcomes`.

The evidence ledger worker — the single serial FIFO
`quant.evidence_outbox.EvidenceLedgerWorker` hosted by `atom-v9-thin` — spends
about ninety sequential database round trips on every accepted COIN cycle: six
separate forecast transactions (advisory lock, select, insert, commit), six
separate commit-proof observations, one transaction per resolved outcome, the
legacy family-ledger transaction, and one new TLS connection per cycle for the
legacy publication proofs. The ledger's own statements average 1–4 ms of
server time and the service runs at 0.2–0.4 of 4 CPUs; the per-cycle cost is
round-trip count, not database work or compute. Sustained throughput is about
28 cycles per minute. Regular-session quote cadence reaches 40–47 cycles per
minute at the open and close.

The backlog is visible as persist lag, `persisted_at - cutoff_at`, which is
3–6 s outside regular hours. Regular-session rows persisted after their own
`target_endpoint`:

| Session | Peak lag | 30S | 1M | 5M | 15M | 30M | 1H |
|---|---|---|---|---|---|---|---|
| 2026-08-28 | `2,870s` | `100.0%` | `100.0%` | `100.0%` | `92.9%` | `18.0%` | `0.0%` |
| 2026-08-31 | `1,614s` | `99.6%` | `99.1%` | `86.7%` | `18.1%` | `0.0%` | `0.0%` |
| 2026-09-01 | `687s` | `41.0%` | `33.1%` | `6.5%` | `0.0%` | `0.0%` | `0.0%` |
| 2026-09-02 (to 11:10 ET) | `663s` | `100.0%` | `100.0%` | `84.0%` | `0.0%` | `0.0%` | `0.0%` |

FREEZE law 4 requires exact-six rows to be written before horizon maturity. The
commit proof `proof_eligible = commit_observed_at < target_endpoint` correctly
refuses truth credit to every late row, and late rows are never reconstructed.
Nothing in the fail-closed design is wrong; the ledger is too slow to satisfy
law 4 during regular hours. About 62% of the current 30S and 1M `MATURE`
accuracy evidence is extended-hours evidence.

## Decision

L-1 authorizes exactly one thing: fewer database round trips for the same
statements, in the same order, producing the same rows. It is a throughput
change and not an evidence change. Every mathematical value, identity, hash,
proof, eligibility rule, ordering rule, and failure disposition is preserved
exactly.

| Frozen field | Exact value |
|---|---|
| Gate variable | `ATOM_EVIDENCE_LEDGER_BATCH_ENABLED` |
| Gate default | disabled; active only when the value is exactly `1` |
| Acceptance: persist lag | p95 of `persisted_at - cutoff_at` over regular-session cutoffs `< 5.0s` |
| Acceptance: unscoreable share | regular-session 30S rows and 1M rows with `persisted_at > target_endpoint`, each `< 5%` |
| Acceptance window | the first two complete regular XNYS sessions after activation, each session judged separately |
| Throughput | about 4× current is a target only; it is not a frozen guarantee and not an acceptance criterion |

## Exact authorized change

Four mechanisms and nothing else. Each is active only under the gate; with the
gate off, every existing code path executes unchanged.

1. **Exact-six forecast persistence in one transaction.** `V4AWriter` gains
   `persist_forecasts(records, persisted_at)`. For the exact six records in
   order `30S`, `1M`, `5M`, `15M`, `30M`, `1H`, it takes the same six advisory
   transaction locks with the same lock identities in that order, runs the
   same logical-key `SELECT` and the same `INSERT` per record with the same
   parameters, and commits once. The per-record `INSERT`, `IDEMPOTENT`, and
   `FORECAST_DUPLICATE_CONFLICT` statuses are preserved per horizon and
   returned as the same validated records the sequential path returns. On the
   first record whose status is a terminal conflict, the transaction commits
   the preceding records exactly as the sequential path would have committed
   them, the conflicting record is returned with that status, later horizons
   are not attempted, and the worker raises the same `TerminalDeliveryError`.
   One wall-clock read supplies `persisted_at` for the batch; `persisted_at`
   is operational metadata outside every mathematical hash.
2. **Batched commit-proof observation.** After that commit, `V4AWriter` gains
   `record_forecast_commit_proofs(records)`, which in a new transaction issues
   one statement that calls the existing
   `atom_v9_internal.record_forecast_commit_proof(text)` once per record
   through `unnest(...) WITH ORDINALITY` and `JOIN LATERAL`, ordered by
   ordinality, then commits. The function, `POST_COMMIT_DB_OBSERVATION_V1`,
   the later-transaction requirement, and
   `proof_eligible = commit_observed_at < target_endpoint` are unchanged.
   Every returned row is applied through the existing `_apply_commit_proof`.
   If the batched statement fails for any reason, the transaction is rolled
   back and the proofs are recorded through the existing per-record
   `record_forecast_commit_proof` in the same order, so the failure disposition
   is identical to today's.
3. **Batched outcome persistence per bracket.** `V4AWriter` gains
   `persist_outcomes(records, created_at)`. For the outcomes resolved in one
   bracket, in the existing `(target_endpoint, forecast_record_id)` order, it
   takes the same per-outcome advisory locks in that order, runs the same
   `SELECT` and `INSERT` per record, and commits once, preserving the
   per-record `INSERT`, `IDEMPOTENT`, and `OUTCOME_CONFLICT` statuses. On the
   first `OUTCOME_CONFLICT` the transaction commits the preceding outcomes
   exactly as today, stops, and the worker raises the same
   `TerminalDeliveryError`. `build_outcome`, `canonical_target_identity`, the
   bracket rule, `actual_return_bps`, timing statuses, and state-build
   candidate submission are unchanged; one wall-clock read supplies
   `created_at` for the bracket, and `created_at` is outside the outcome hash.
4. **Persistent legacy proof session.**
   `PostgresEvidenceStore._record_publication_proofs` reuses one lazily opened
   dedicated secondary connection for its four existing
   `record_legacy_evidence_publication` statements instead of opening a new
   connection every cycle. It remains a separate session and a separate
   transaction from the ledger commit, committed after the four statements.
   On any exception the secondary connection is closed and discarded, the
   existing sqlstate handling and re-raise apply unchanged, and the connection
   reopens lazily on the next cycle. The four statements and their parameters
   are unchanged.

Within the single transactions of mechanisms 1 and 3 the implementation may
use psycopg pipeline mode. It may not reorder statements, merge statements
across records, change any statement text or parameter, or hold a transaction
open across FIFO items.

The worker's FIFO order is unchanged: resolve due outcomes, legacy family
ledger, persist the exact six, commit proofs, SIM-3 hook, state-build submit,
cache refresh. `_load_due`, `_load_pending`, `_complete_cycles_cohorts`, the
handoff anchor, the runtime ownership lock, sequence-gap handling, and
`FinalizedV4PersistenceResult` construction are unchanged. `quant/web.py`
reads the gate once at startup exactly as it reads
`ATOM_FAMILY_EVIDENCE_CADENCE_ENABLED`.

## Preserved exactly

- Record contents, canonical serialization, hashes, identities, cohorts,
  `contract_version`, `evidence_version`, and `evidence_origin`.
- The commit-proof function, method, table, and eligibility rule; the
  resolution bracket rule; `MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS`;
  overlap selection; V4B, V4C, and V4D mathematics.
- The Family Evidence Cadence gate and every legacy ledger statement.
- Single runtime owner, single serial FIFO, outbox capacity `256`,
  fail-closed behavior, and the `SELECT` plus `INSERT` SQL surface of the
  writer.
- Late rows stay unscoreable. No backfill, repair, re-scoring, or
  reconstruction of any row, session, or state.
- SIM-3 Stage A and Stage B placement, the SIM-3 result tuple, and every
  simulator boundary.

## Implementation surface

After the order of work below reaches step 4, the implementation PR may change
exactly:

- `quant/v9_v4a_evidence.py` — the three batch methods only;
- `quant/evidence_outbox.py` — gated calls to those methods and the
  fallback only;
- `quant/evidence.py` — the secondary session in `_record_publication_proofs`
  only;
- `quant/web.py` — reading and passing the gate only;
- `tests/test_l1_evidence_ledger_throughput.py` (new) and minimal additions
  to existing tests.

Required tests: for identical inputs the batch and sequential paths produce
identical statement texts, parameters, lock identities and order, row
contents, hashes, identities, per-horizon statuses, the identical
`FinalizedV4PersistenceResult` tuple, and the identical
`TerminalDeliveryError` disposition for a conflict at every horizon and
outcome position; gate off is byte-identical existing behavior; the proof
fallback runs on batch failure; the secondary session is discarded on failure
and reopened lazily; pipeline use never reorders statements; the full existing
suite, including every SIM-3 test that asserts unchanged ledger behavior,
remains green.

## Acceptance receipt

After the first two complete regular XNYS sessions with the gate active, one
read-only SQL receipt reports, per session: p95 and maximum persist lag over
regular-session cutoffs; the share of regular-session 30S and 1M rows with
`persisted_at > target_endpoint`; and the same table as the Finding above.
Both acceptance criteria must hold in both sessions. If either fails, the
owner sets the gate to `0`, the result is reported, and L-1 stops; no further
tuning, capacity change, or second mechanism is authorized under L-1.

## Order of work

1. This freeze merged by the owner under the merge gate.
2. The E-1 receipt produced and reviewed under the E-1 freeze, unchanged.
3. An owner-approved documentation change moving the `AGENTS.md` active-phase
   pointer to L-1.
4. The implementation PR under the merge gate: review on the final intended
   head, zero unresolved material threads, green required checks.
5. The owner sets `ATOM_EVIDENCE_LEDGER_BATCH_ENABLED=1` on `atom-v9-thin`.
   One deploy of the merged implementation commit to `atom-v9-thin` only is
   authorized, outside 13:30–20:00 UTC. Rollback is the gate at `0` or
   redeploying the previous commit. No other service is deployed.
6. The acceptance receipt, then stop.

No L-1 implementation work begins before steps 1–3, in that order.

## What L-1 does not authorize

- No change to any mathematics, threshold, weight, family, synthesis, V1–V4
  value, cohort, hash, proof rule, cadence rule, or resolution rule.
- No outbox capacity change, second ledger thread or process, relocation of
  the legacy family ledger off the FIFO, or change to FIFO order.
- No migration, schema, table, index, function, trigger, role, grant, policy,
  or default-privilege change.
- No Supabase tier, compute, region, pooler, or credential change.
- No Render plan, region, instance-count, or environment change beyond the
  gate variable set by the owner; no deployment other than the one in step 5.
- No change to the V4 state worker, its rebuild cadence, the dashboard, the
  E-1 scorecard, historical replay, or any simulator phase.
- No reconstruction, backfill, or re-scoring of unscoreable rows.
- No broker, account, order, execution, or trading authority.
