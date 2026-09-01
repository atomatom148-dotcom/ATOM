# ATOM TRUE V9 — SIM-3A Final Review Closure

**Status:** LAW after merge  
**Amends:** PR #223 and all prior SIM-3A documentation in PR #227  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only

This is the final controlling SIM-3A amendment for the three P1 findings from the Codex review of commit `e560b36`: resumable bounded reconciliation work, continued background ownership acquisition after the synchronous startup bound, and server-bounded/autocommitted durable fence capture.

Where this document conflicts with any earlier SIM-3A text, this document controls.

It does not implement SIM-4 and does not authorize SIM-5 or SIM-6.

## 1. Synchronous startup bound does not permanently disable ownership acquisition

The one-second ownership-acquisition bound is only the maximum amount of time application startup may wait synchronously for SIM-4 to become authoritative. It is **not** a lifetime retry limit.

Freeze:

```text
SIM4_RUNTIME_OWNER_RETRY_SECONDS = 0.100
SIM4_RUNTIME_OWNER_STARTUP_WAIT_SECONDS = 1.000
```

`ownership_wait_started_at` is captured exactly once, before the first ownership attempt, and remains unchanged until that process either:

- acquires authoritative runtime ownership; or
- shuts down without ever acquiring ownership.

The single `SimulationEntryWorker` starts in exactly one of these runtime states:

```text
STANDBY
RECOVERING
READY
STOPPING
STOPPED
FAILED
```

### 1.1 Startup behavior

During the first one second after worker startup:

1. the worker in `STANDBY` makes nonblocking ownership attempts using the already-frozen `pg_try_advisory_lock` owner key;
2. attempts are separated by at least 100 ms;
3. if ownership is acquired, the worker transitions to `RECOVERING`, executes the frozen authoritative recovery, then becomes `READY`;
4. if ownership is not acquired within one second, application startup returns normally with SIM-4 status `STANDBY`.

No application-lifecycle caller waits longer than one second for SIM-4 ownership.

### 1.2 Background acquisition after startup

After the synchronous one-second startup window expires, the **same single worker thread** remains in `STANDBY` and continues nonblocking ownership attempts every 100 ms until one of:

- ownership is acquired;
- `stop()` is requested; or
- an unrecoverable configuration error marks the worker `FAILED`.

No second ownership thread or second SIM-4 worker is authorized.

While `STANDBY`:

- the process is not authoritative;
- it does not recover intents;
- it does not persist SIM-4 terminal records;
- it does not accept authoritative quote or intent FIFO admission;
- producer callbacks fail/drop only their SIM-4 handoff and remain isolated;
- SIM-1/SIM-2/SIM-3 and production continue normally;
- durable SIM-2 intents are later recovered/reconciled after ownership acquisition under the already-frozen durable sequence fence.

Candidate ownership connection failures before ownership is acquired may be replaced by a fresh candidate connection on a later 100 ms attempt, subject to the exact session-capable DSN allowlist. Once ownership is acquired, the existing rule remains absolute: unexpected loss of the authoritative owner session permanently deactivates that worker generation; it may not reconnect and resume persistence.

When a long-waiting replacement eventually acquires ownership, it uses the original unchanged `ownership_wait_started_at` so every current-generation wait-interval intent is accounted for by the controlling durable recovery rules.

## 2. Reconciliation is sliced and resumable

A successfully closed durable sequence interval must never monopolize the single worker until the whole interval is exhausted.

Freeze:

```text
SIM4_RECONCILE_QUERY_ROWS = 16
SIM4_RECONCILE_MAX_PAGES_PER_SLICE = 1
```

The prior 256-row value is superseded for worker-side reconciliation query pages. Each reconciliation slice may query and handle at most one page of at most 16 durable intent rows before yielding back to the ordinary SIM-4 event loop.

### 2.1 Runtime-only resumable cursor

The authoritative worker maintains these runtime-only values:

```text
last_reconciled_fence_seq
reconcile_target_fence_seq: int | None
reconcile_cursor_seq
reconcile_cursor_intent_id
```

They are not persisted, not hashed, and do not modify SIM-1/SIM-2 evidence.

When no closed interval is in flight:

1. perform the frozen nonblocking fence-capture operation;
2. if no fence is captured, yield immediately;
3. set `reconcile_target_fence_seq = new_fence_seq`;
4. set the cursor to the already-completed lower boundary represented by `last_reconciled_fence_seq`.

While a target interval is in flight, the worker does **not** capture a newer target fence. It continues the same closed interval across later slices.

### 2.2 Exact page query

Each slice queries at most 16 rows from the current closed interval in deterministic order:

```text
sim4_admission_seq ASC, intent_id ASC
```

with conditions equivalent to:

```text
last_reconciled_fence_seq < sim4_admission_seq <= reconcile_target_fence_seq
AND (sim4_admission_seq, intent_id) > (reconcile_cursor_seq, reconcile_cursor_intent_id)
```

The existing `(sim4_admission_seq, intent_id)` partial index is the required access path.

No page may exceed 16 rows. Exactly one page maximum is handled in one reconciliation slice.

### 2.3 Cursor advancement and failure

Rows in the returned page are handled in query order.

After one row is successfully handled idempotently, the runtime cursor may advance to that row's exact `(sim4_admission_seq, intent_id)`.

If handling a row fails:

- do not advance the cursor past that row;
- do not advance `last_reconciled_fence_seq`;
- end the reconciliation slice immediately;
- return to ordinary event processing;
- retry that row on a later slice.

After a page is handled successfully, the worker yields to its ordinary event loop before any next reconciliation page.

If the page contains fewer than 16 rows, the closed target interval is exhausted after the page succeeds. Then and only then:

```text
last_reconciled_fence_seq = reconcile_target_fence_seq
reconcile_target_fence_seq = None
```

If a page contains exactly 16 rows, completion is not assumed; the next reconciliation slice performs the next indexed page query. A later zero-row page closes the target interval.

### 2.4 Live work priority and fairness

Reconciliation is background completeness work. It never replaces normal FIFO servicing.

After every reconciliation slice, the worker returns to the ordinary event loop. If ordinary SIM-4 FIFO events are waiting, at least one ordinary event is processed before another reconciliation slice may begin.

Pending-intent deadline wakes and retained-quote expiry wakes retain their existing frozen priority and strict timing semantics. Reconciliation must yield when either boundary is due.

Thus an ownership outage or callback-drop backlog can take multiple slices to reconcile without starving live quote admission, pending-intent expiry, or quote eviction.

If the process restarts while an in-flight cursor exists, the runtime-only cursor is lost safely. The new authoritative worker begins from durable `last_reconciled_fence_seq` semantics and exact terminal-record idempotency; replaying an already-handled row is harmless and required to validate the existing terminal record.

## 3. Exact server-bounded autocommit fence capture

The earlier multi-statement client transaction for successful durable fence capture is superseded.

Migration 027 must create one exact combined server-side function:

```text
SIM4_INTENT_FENCE_CAPTURE_FUNCTION = public.atom_v9_sim4_try_capture_intent_fence
```

### 3.1 Exact function

```sql
CREATE FUNCTION public.atom_v9_sim4_try_capture_intent_fence()
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    acquired boolean;
    value bigint;
    called boolean;
BEGIN
    acquired := pg_catalog.pg_try_advisory_xact_lock(1158704842749668574::bigint);
    IF NOT acquired THEN
        RETURN NULL;
    END IF;

    SELECT last_value, is_called
      INTO value, called
      FROM public.atom_v9_sim4_intent_admission_seq;

    IF called THEN
        RETURN value;
    END IF;
    RETURN 0::bigint;
END;
$$;
```

The function is nonblocking because its advisory acquisition is `pg_try_advisory_xact_lock`.

Direct execute privileges are exact:

```sql
REVOKE ALL ON FUNCTION public.atom_v9_sim4_try_capture_intent_fence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_try_capture_intent_fence() FROM anon;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_try_capture_intent_fence() FROM authenticated;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_try_capture_intent_fence() FROM service_role;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_try_capture_intent_fence() FROM atom_v9_v4_runtime;
GRANT EXECUTE ON FUNCTION public.atom_v9_sim4_try_capture_intent_fence() TO atom_v9_sim_runtime;
```

The previously frozen read-only fence-reader function may exist for diagnostics/tests but is **not** the authoritative runtime fence-capture path. The authoritative runtime uses only the combined function above.

### 3.2 Exact autocommit call

Fence capture is permitted only when:

- the authoritative owner session has no terminal-entry transaction active;
- the connection is idle; and
- the same session-scoped runtime-owner advisory lock is still held.

For the fence-capture statement only, the authoritative owner connection must be in autocommit mode so the SQL statement forms its own implicit PostgreSQL transaction.

Before enabling SIM-4 on the owner session, configure exactly:

```sql
SET statement_timeout = '100ms';
```

The runtime then calls exactly one SQL statement:

```sql
SELECT public.atom_v9_sim4_try_capture_intent_fence();
```

No explicit `BEGIN` surrounds this call.

Because autocommit is active, PostgreSQL commits or aborts the implicit statement transaction before the command completes to the client. Any transaction-scoped exclusive intent-handoff advisory lock acquired inside the function is therefore released at the statement transaction boundary, not at some later client-controlled commit.

If the result is:

- a nonnegative bigint: that is the exact newly captured closed fence;
- `NULL`: the exclusive try-lock was unavailable; no fence was captured and the worker yields;
- an error/timeout: the implicit transaction aborts, no fence is captured, and the worker yields.

No explicit rollback is required for the autocommitted fence-capture statement itself. An error must not trigger privileged fallback or a blocking retry.

`statement_timeout = 100ms` applies to this owner session and therefore bounds server execution even if the function or server stalls unexpectedly. A statement timeout does not authorize reconnecting an authoritative generation after owner-session loss.

### 3.3 Isolation property

The SIM-2 insert trigger still acquires the shared transaction advisory lock on the same handoff-fence key before assigning `sim4_admission_seq`.

A successful combined capture function:

1. obtains the exclusive xact try-lock without waiting;
2. reads the sequence while that exclusive lock is held;
3. returns the fence;
4. ends the implicit transaction automatically;
5. releases the exclusive xact lock before any later client work.

There is no network/client idle gap while an explicit open transaction holds the exclusive fence.

If a shared SIM-2 insertion lock is active, the try-lock returns `false` and the function returns `NULL`; SIM-4 immediately yields instead of blocking SIM-2 or its own worker.

## 4. Required additional tests

SIM-4 implementation must test all earlier freeze requirements plus these exact rules.

### Background ownership acquisition

- application startup waits no more than one second;
- failure to acquire within one second leaves the same worker `STANDBY`, not permanently disabled;
- the same worker retries every at least 100 ms after startup;
- no second ownership/retry thread exists;
- `ownership_wait_started_at` remains the original value across extended waiting;
- eventual ownership acquisition enters `RECOVERING` then `READY`;
- durable wait-interval intents are recovered after delayed acquisition;
- `stop()` terminates standby retry behavior;
- authoritative owner-session loss remains generation-terminal and does not reconnect.

### Reconciliation slicing

- query page size is at most 16;
- exactly one page maximum per reconciliation slice;
- an in-flight `reconcile_target_fence_seq` prevents capture of a newer target;
- cursor ordering is `(sim4_admission_seq, intent_id)`;
- successful row handling advances the runtime cursor exactly to that row;
- row failure does not advance past the failed row;
- every slice yields to ordinary event processing;
- queued live events receive service between reconciliation slices;
- deadline/quote-expiry boundaries preempt another reconciliation slice when due;
- fewer-than-16 successful rows close the target interval;
- exactly 16 rows require a later page/empty-page proof before target completion;
- `last_reconciled_fence_seq` advances only when the full closed target interval is exhausted;
- restart with lost runtime cursor remains correct through durable terminal idempotency.

### Autocommit fence capture

- exact combined function name/signature/body;
- function uses `pg_try_advisory_xact_lock`, never blocking `pg_advisory_xact_lock`;
- function reads sequence only after successful exclusive acquisition;
- function returns `NULL` when lock unavailable, `0` before first sequence call, exact last value otherwise;
- direct function execution is granted only to `atom_v9_sim_runtime` among runtime-facing roles;
- owner session has exact `statement_timeout = 100ms`;
- fence capture occurs only on an idle authoritative owner session;
- fence capture executes in autocommit mode with no explicit BEGIN;
- exclusive handoff lock is released at the statement transaction boundary;
- client pause or lost response after server statement completion cannot retain the exclusive transaction lock;
- timeout/error closes no interval and immediately yields normal worker control;
- active shared SIM-2 insertion causes `NULL` rather than a wait;
- producer callbacks never call the fence-capture function.

## 5. Documentation-only hard boundary

This amendment is documentation only.

It creates no Python implementation, migration execution, schema mutation, database object, Render change, web route, broker capability, SIM-4 entry, SIM-5 resolution, SIM-6 state, or V9 change in this PR.

Future SIM-4 remains confined to the already-authorized six implementation files. The combined fence function belongs in already-authorized migration 027; standby acquisition, reconciliation slicing, and runtime cursor behavior belong in the already-authorized SIM-4 runtime implementation. No additional implementation file is authorized.

SIM-5 and SIM-6 remain unauthorized.
