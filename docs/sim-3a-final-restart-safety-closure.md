# ATOM TRUE V9 — SIM-3A Final Restart-Safety Closure

**Status:** LAW after merge  
**Amends:** all prior SIM-3A / PR #227 controlling documents  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only

This final closure resolves the remaining Codex P1 findings on PR #227 without implementing SIM-4, SIM-5, or SIM-6. Where this document conflicts with an earlier SIM-3A amendment, this document controls.

## 1. Persist the completed reconciliation fence

Migration `027_create_v9_sim_entries.sql` must persist one singleton reconciliation checkpoint for SIM-4.

Freeze one row keyed exactly by:

```text
checkpoint_id = ATOM_TRUE_V9_SIM4_RECONCILIATION_1
```

The row stores at minimum:

```text
last_completed_admission_seq bigint not null
updated_at timestamptz not null
```

Initial value:

```text
last_completed_admission_seq = 0
```

The row is simulator-only operational metadata. It is not market evidence, not a forecast, not an outcome, not V9 state, and not part of any immutable entry hash.

Only the authoritative SIM-4 runtime owner may advance the checkpoint, and only after every durable intent with:

```text
old_last_completed_admission_seq < sim4_admission_seq <= target_fence_seq
```

has either:

1. been matched to an existing immutable terminal entry; or
2. had its terminal result persisted successfully under the frozen precedence.

An in-flight cursor and target fence remain runtime-only until the whole closed interval is complete. A crash before completion MUST leave the durable checkpoint unchanged.

On replacement startup, after exclusive runtime ownership is acquired, reconciliation starts from:

```text
last_completed_admission_seq + 1
```

not from `ownership_wait_started_at`, not from zero unless the durable checkpoint is zero, and not from a newly captured fence. The new worker may capture a new target fence, but it must first finish every durable sequence greater than the stored completed checkpoint up to that target.

Checkpoint advancement must be atomic with verification that the interval is complete. Never advance the checkpoint merely because a page was read or queued.

This makes reconciliation restart-safe without rescanning already-completed historical rows and without losing an incomplete interval.

## 2. Late reconciled intents use the same FIFO admission-expiry fence

A durable intent discovered by reconciliation after its `entry_deadline_at` must NOT immediately become `SKIPPED_WINDOW_EXPIRED` merely because no eligible quote is currently in the retained quote buffer.

For every actionable reconciled intent whose deadline has passed, apply the existing terminal precedence first:

1. existing terminal record;
2. durable open-position collision;
3. restart-gap classification when the intent belongs to a handoff/restart-gap cohort explicitly frozen by the earlier documents.

If none of those terminal rules applies and the intent is eligible for ordinary late-window expiry, the worker must route it through the SAME in-process admission-fence procedure used by an ordinary pending intent:

1. acquire the shared in-process admission mutex;
2. snapshot `expiry_admission_fence = next_admission_sequence - 1`;
3. release the mutex;
4. drain/process every already-admitted FIFO event through that sequence in normal FIFO order;
5. re-evaluate the reconciled intent against every causal executable quote admitted through the fence using the original publication/provider/accepted-time predicates; and
6. only if no terminal result arises, persist `SKIPPED_WINDOW_EXPIRED`.

An admitted quote beyond the fence cannot be applied retroactively. A causal quote already admitted at or below the fence cannot be skipped merely because reconciliation ran before that quote was drained from FIFO.

No second queue, no historical quote reconstruction, and no synthetic quote are authorized.

## 3. Runtime ownership attempts are autocommit statements

The dedicated SIM-4 runtime-owner PostgreSQL session must be placed in autocommit mode before the first ownership attempt.

Every ownership attempt is exactly one standalone statement:

```sql
SELECT pg_try_advisory_lock(%s::bigint)
```

with no client-managed transaction surrounding it.

Therefore:

- an unsuccessful attempt leaves no open transaction;
- the 100 ms standby retry loop cannot become `idle in transaction`;
- a successful session-scoped advisory lock remains owned after the statement ends because it is session-scoped;
- the same connection can immediately execute the already-frozen autocommitted fence-capture operation; and
- there is no later autocommit mode transition blocked by an outstanding ownership-attempt transaction.

The runtime-owner connection must remain autocommit for ownership attempts and server-side fence-capture calls. When executing a SIM-4 terminal-entry transaction on that same owner session, the implementation must use an explicit bounded transaction block and return the connection to autocommit after commit/rollback while retaining the session advisory lock.

Any failure to restore the owner session to the required operational state fails SIM-4 closed for that generation; production and SIM-1/SIM-2/SIM-3 remain unaffected.

## 4. Required tests

SIM-4 implementation must add all earlier tests plus:

### Durable checkpoint

- singleton checkpoint starts at sequence 0;
- a partial 16-row reconciliation page does not advance the durable completed checkpoint;
- crash after target-fence capture but before interval completion leaves the checkpoint unchanged;
- replacement resumes from stored `last_completed_admission_seq + 1`;
- completed intervals advance exactly once and monotonically;
- existing terminal rows count as reconciled without creating duplicates;
- no sequence greater than the completed checkpoint is skipped across restart; and
- the checkpoint is simulator operational metadata only and never enters immutable forecast/outcome/entry hashes.

### Reconciled late intent

- reconciled late intent with a causal quote already admitted but not yet drained can still enter under the exact original window predicates;
- expiry fence is captured from the same admission sequence domain as ordinary expiry;
- every FIFO event at or below the fence is processed before `SKIPPED_WINDOW_EXPIRED`;
- events above the fence cannot enter retroactively;
- collision and restart-gap precedence remain higher than ordinary late expiry; and
- no historical quote reconstruction occurs.

### Ownership autocommit

- owner connection is autocommit before first `pg_try_advisory_lock`;
- failed ownership attempt leaves no open transaction;
- repeated standby retries never become idle-in-transaction;
- successful session advisory ownership survives statement completion;
- server-side fence capture can execute immediately after ownership acquisition;
- explicit terminal transaction commits/rolls back on the same backend session and returns to autocommit; and
- owner-session state failure disables only SIM-4.

## 5. Documentation-only boundary

This file changes documentation only.

It does not create or execute migration 027, does not change schema now, does not implement Python, does not deploy Render, does not alter broker access, and does not implement SIM-4, SIM-5, or SIM-6.

Future SIM-4 implementation remains limited to the previously frozen six implementation files, including all migration-027 objects described by the complete SIM-3A freeze set.

SIM-5 and SIM-6 remain unauthorized.
