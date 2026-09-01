# ATOM TRUE V9 — SIM-3A Final Runtime Fence Addendum

**Status:** LAW after merge  
**Amends:** `docs/sim-3a-p1-review-amendment.md` and `docs/sim-3a-review-fence-addendum.md`  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only

This addendum resolves the remaining Codex review findings on PR #227. Where this document conflicts with an earlier SIM-3A amendment, this document controls. It does not implement SIM-4 and does not authorize SIM-5 or SIM-6.

## 1. Preserve the complete ownership-wait handoff interval

A replacement process captures one injected UTC timestamp immediately before its first runtime-ownership attempt:

```text
ownership_wait_started_at
```

This value is process-local runtime metadata only. It is not hashed or persisted and does not change any SIM-1 or SIM-2 record.

While the replacement does not own the frozen SIM-4 runtime advisory lock:

- SIM-3 continues persisting immutable intents normally;
- the replacement performs no SIM-4 entry calculation or terminal persistence;
- process-local SIM-4 callbacks may be dropped without affecting SIM-1/SIM-2 persistence; and
- restart recovery is forbidden.

After the replacement acquires exclusive SIM-4 runtime ownership, it reads `runtime_started_at` exactly once and performs one bounded-by-generation recovery query for unmatched persisted intents whose `eligible_at` satisfies the **inclusive acquisition interval**:

```text
ownership_wait_started_at <= eligible_at <= runtime_started_at
```

The upper boundary is inclusive. An intent whose microsecond-resolution `eligible_at` equals `runtime_started_at` is part of handoff recovery and may not fall between recovery and live admission.

It then also applies the original normal recent-recovery rule where necessary. The effective recovery set is the union, deduplicated by immutable `intent_id`, so no intent persisted during the ownership-wait interval or exactly on the ownership-acquisition timestamp can become permanently unmatched.

If a live callback for an intent included by the inclusive recovery query is also admitted after ownership acquisition, the single worker deduplicates by immutable `intent_id` before terminal selection. Existing-terminal idempotency remains the final durable guard.

This query is finite because its lower bound is the current replacement generation's own `ownership_wait_started_at`. It must not scan before that timestamp and must not backfill historical SIM-1/SIM-2 intents from earlier generations.

Recovered intents use the already-frozen precedence:

1. existing terminal record;
2. non-actionable mapping;
3. durable open-position collision;
4. restart gap;
5. late-window expiry where applicable.

An actionable intent from the ownership-wait interval cannot be reconstructed into an `ENTERED` result from old quotes. If no durable open-position collision applies, it is classified under restart-gap rules because the replacement cannot prove the complete quote interval while it was not authoritative.

## 2. Runtime ownership and terminal persistence use the same PostgreSQL session

The dedicated PostgreSQL session that successfully acquires:

```sql
SELECT pg_try_advisory_lock(%s::bigint)
```

for the frozen SIM-4 runtime-owner key is the **only** database session permitted to execute SIM-4 terminal-entry transactions for that worker generation.

The SIM-4 runtime must not open a second independent connection for terminal persistence while it owns runtime authority.

For each terminal decision, on that same owner session:

1. begin the database transaction;
2. acquire the frozen per-horizon transaction advisory lock;
3. read any existing terminal record for the intent;
4. read durable open occupancy for the horizon;
5. choose or validate the frozen terminal status;
6. insert or validate the immutable terminal entry record;
7. commit or rollback; and
8. retain the session-level runtime-owner advisory lock on the same backend session after the transaction completes.

This makes runtime ownership and persistence inseparable at the PostgreSQL backend-session boundary.

If the owner session is lost at any point:

- PostgreSQL aborts any uncommitted terminal transaction on that session;
- the runtime-owner advisory lock is released by PostgreSQL with that session;
- the old worker generation becomes permanently inactive;
- it must not reconnect and continue under the same generation;
- it must not persist a SIM-4 terminal record through any replacement connection; and
- a later generation may acquire ownership and recover only after PostgreSQL has released the old session lock.

The earlier pre-event `SELECT 1` liveness probe is not an authorization fence and is no longer sufficient by itself. Same-session persistence is the controlling ownership fence.

## 3. Exact ownership-connection allowlist

The SIM-4 runtime-owner session must be backed by a PostgreSQL connection whose backend-session semantics are explicitly known. An arbitrary DSN is not considered session-capable merely because it is not a known transaction-pool endpoint.

For the production Supabase deployment, the runtime-owner DSN is accepted only when its normalized host/port matches one of these two forms:

```text
DIRECT:
  hostname starts with "db."
  hostname ends with ".supabase.co"
  port = 5432

SUPAVISOR_SESSION_MODE:
  hostname ends with ".pooler.supabase.com"
  port = 5432
```

The following are rejected before any runtime-owner advisory-lock attempt:

- any `.pooler.supabase.com` endpoint on port `6543`;
- any other port for the two allowed Supabase hostname classes;
- any hostname/port combination outside the two explicit production forms above;
- any DSN whose host or port cannot be parsed exactly; and
- any connection mode known or declared to be transaction pooled.

There is no fallback from an unrecognized DSN to a session advisory lock.

Tests may inject a dedicated non-pooled PostgreSQL connection factory without using a production Supabase hostname. Such an injected test connection is not a production configuration path and must prove stable backend-session identity across ownership acquisition and a terminal transaction using:

```sql
SELECT pg_backend_pid()
```

The observed backend PID must remain identical while the session advisory lock is owned. Production runtime configuration does not receive this test-only bypass.

The rejection reason for Supabase transaction mode is conceptually:

```text
SIM-4 runtime ownership requires a direct or Supavisor session-mode connection; transaction pooling is forbidden
```

This validation applies only to the SIM-4 runtime-owner connection required by this freeze and does not modify production V9 connection behavior.

## 4. Ownership release only after persistence is impossible

The existing public `stop()` call remains bounded and must return within the already-frozen one-second join bound. That bound does **not** authorize early release of runtime ownership.

Shutdown is frozen as follows:

1. stop accepting new SIM-4 events;
2. signal the SIM-4 worker to stop;
3. `stop()` may wait for the worker only up to the existing one-second public join bound;
4. if the worker has fully terminated, its own worker-finalization path releases/closes the runtime-owner session;
5. if the one-second public join expires while the worker is still alive, `stop()` returns without unlocking, closing, transferring, or otherwise releasing the owner session from another thread;
6. the still-running worker retains ownership until it reaches its own finalization path and can no longer execute a terminal persistence transaction; and
7. process termination closes the PostgreSQL session, causing any active transaction to roll back and the session advisory lock to release atomically at the database boundary.

Only the worker's finalization path, after its processing loop has ended and no terminal transaction remains active, may explicitly call:

```sql
SELECT pg_advisory_unlock(%s::bigint)
```

and close the owner connection.

A caller-side timeout must never explicitly unlock an ownership session that a still-running worker can use.

Because all terminal persistence uses the same owner session, unexpected loss of that session also makes further persistence by the old generation impossible. The worker may not switch to a new connection after ownership loss.

## 5. Nonblocking admission-lock contention

Production quote ingress and the SIM-3 persisted-intent callback must never block waiting for the SIM-4 admission lock.

For producer-side submission, acquire the shared admission lock exactly with nonblocking semantics:

```python
if not admission_lock.acquire(blocking=False):
    drop_only_this_incoming_sim4_event()
    return
```

On this contention path:

- no admission sequence is consumed;
- no queue operation is attempted;
- no existing queued event is evicted;
- no synthetic entry record is created;
- no retry occurs on the production or SIM-3 callback path; and
- production and SIM-1/SIM-2 behavior remain unchanged.

If the nonblocking lock acquisition succeeds, the producer executes only the already-frozen bounded critical section:

1. read `candidate_seq = next_admission_seq`;
2. construct the immutable runtime-only envelope;
3. call `put_nowait`;
4. increment `next_admission_seq` only after successful queue insertion; and
5. release the lock in `finally`.

The worker may take the same admission lock when it snapshots an expiry fence because that operation is off the production ingress path. The worker must never hold the admission lock while performing database I/O, sleeping, waiting on the queue, quote selection, or terminal persistence.

The existing warmed producer submit p99 requirement of no more than 1 ms remains unchanged.

## 6. Required tests added by this final addendum

SIM-4 implementation must test all earlier requirements plus the following.

### Ownership-wait recovery

- capture `ownership_wait_started_at` before the first ownership attempt;
- a wait longer than two seconds does not lose persisted SIM-3 intents;
- recovery covers the full current-generation ownership-wait interval;
- recovery includes `eligible_at == runtime_started_at` exactly;
- recovery never scans before `ownership_wait_started_at`;
- the union with normal recent recovery is deduplicated by `intent_id`;
- a recovered intent also delivered by live callback is deduplicated by `intent_id`;
- waiting-generation actionable intents cannot become retroactive `ENTERED` records; and
- normal collision precedence remains intact during handoff recovery.

### Same-session ownership/persistence

- the session that owns the runtime advisory lock is the session used for every SIM-4 terminal transaction;
- no second persistence connection is opened by an authoritative generation;
- horizon transaction lock and terminal insert execute on the owner session;
- owner-session loss during a transaction causes rollback and prevents later commit by that generation;
- owner-session loss permanently deactivates that generation;
- the old generation cannot reconnect and persist after ownership loss; and
- a replacement cannot become authoritative until PostgreSQL releases the predecessor's session lock.

### Connection validation

- direct `db.*.supabase.co:5432` is accepted by the production owner-DSN allowlist;
- `.pooler.supabase.com:5432` session mode is accepted by the production owner-DSN allowlist;
- `.pooler.supabase.com:6543` is rejected;
- unrecognized production hostname/port combinations are rejected;
- missing or invalid host/port values fail closed;
- arbitrary non-Supabase production DSNs are not assumed session-capable;
- injected test connections prove stable `pg_backend_pid()` while ownership is held; and
- no transaction-pool fallback exists.

### Shutdown ownership retention

- a worker that terminates within one second releases ownership only after its final transaction is impossible;
- a worker still alive after the one-second public join retains the owner session and lock;
- public `stop()` still returns within the frozen bound;
- a replacement cannot acquire while the old worker remains capable of persistence;
- final worker exit releases/closes ownership;
- process/session loss rolls back an active terminal transaction; and
- caller-side timeout never explicitly unlocks a live worker's session.

### Nonblocking admission

- producer uses `acquire(blocking=False)`;
- lock contention drops only the incoming SIM-4 event;
- contention consumes no admission sequence;
- contention performs no queue operation or retry;
- worker never holds the admission lock during database I/O or blocking waits; and
- warmed quote and intent submit p99 remains no greater than 1 ms.

## 7. Documentation-only hard boundary

This addendum changes documentation only. It creates no Python implementation, migration, schema, database object, Render change, broker capability, web route, SIM-4 entry, SIM-5 resolution, or SIM-6 state.

The original exact six-file SIM-4 implementation boundary remains unchanged. This addendum authorizes no seventh implementation file.

SIM-5 and SIM-6 remain unauthorized.
