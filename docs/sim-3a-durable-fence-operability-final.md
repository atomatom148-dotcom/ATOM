# ATOM TRUE V9 — SIM-3A Durable Fence Operability Final Amendment

**Status:** LAW after merge  
**Amends:** PR #223 and all prior SIM-3A documentation in PR #227  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only

This document resolves the two final Codex P1 operability findings on the durable intent fence: least-privilege access to the admission fence value and bounded exclusive-fence acquisition. Where this document conflicts with earlier SIM-3A text, this document controls.

It does not implement SIM-4 and does not authorize SIM-5 or SIM-6.

## 1. Narrow least-privilege admission-fence reader

`atom_v9_sim_runtime` continues to receive **no direct sequence privileges** on:

```text
public.atom_v9_sim4_intent_admission_seq
```

In particular, do not grant direct `USAGE`, `SELECT`, or `UPDATE` on the sequence.

Migration `027_create_v9_sim_entries.sql` must instead create exactly one narrowly scoped reader:

```text
SIM4_INTENT_FENCE_READER_FUNCTION = public.atom_v9_sim4_read_intent_admission_fence
```

Exact SQL contract:

```sql
CREATE FUNCTION public.atom_v9_sim4_read_intent_admission_fence()
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    value bigint;
    called boolean;
BEGIN
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

The function has no parameters and returns only the current durable sequence fence:

- `0` if the sequence has never been called;
- otherwise the exact `last_value`.

It performs no insert, update, delete, sequence mutation, advisory locking, dynamic SQL, role change, or data-table scan.

Privilege boundary is exact:

```sql
REVOKE ALL ON FUNCTION public.atom_v9_sim4_read_intent_admission_fence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_read_intent_admission_fence() FROM anon;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_read_intent_admission_fence() FROM authenticated;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_read_intent_admission_fence() FROM service_role;
REVOKE ALL ON FUNCTION public.atom_v9_sim4_read_intent_admission_fence() FROM atom_v9_v4_runtime;
GRANT EXECUTE ON FUNCTION public.atom_v9_sim4_read_intent_admission_fence() TO atom_v9_sim_runtime;
```

No other simulator-facing role receives execute authority.

The migration owner/definer must own the sequence or otherwise possess only the privileges needed for this exact read. `SECURITY DEFINER` is authorized only for this zero-argument fence-reader function and the previously frozen insert-trigger function.

The authoritative SIM-4 runtime reads the fence only while holding the successful **exclusive intent-handoff transaction lock** described below, and on the same runtime-owner PostgreSQL backend session, by executing exactly:

```sql
SELECT public.atom_v9_sim4_read_intent_admission_fence();
```

No direct `SELECT ... FROM public.atom_v9_sim4_intent_admission_seq` by `atom_v9_sim_runtime` is authorized.

## 2. Nonblocking exclusive reconciliation-lock acquisition

The prior blocking call:

```sql
SELECT pg_advisory_xact_lock(1158704842749668574::bigint);
```

is superseded for SIM-4 reconciliation.

The authoritative SIM-4 worker must use exactly the nonblocking transaction-scoped try-lock:

```sql
SELECT pg_try_advisory_xact_lock(1158704842749668574::bigint);
```

on its already-authoritative runtime-owner PostgreSQL session.

The result must be exactly `true` before the worker may read a reconciliation fence value or enumerate a new closed sequence interval.

If the result is `false`:

1. roll back that reconciliation transaction immediately;
2. do not read or advance a fence;
3. do not query the intent reconciliation interval;
4. leave `last_reconciled_fence_seq` unchanged;
5. return control immediately to the ordinary SIM-4 worker loop so quote processing, pending-intent expiry, and terminal entry work remain live; and
6. retry reconciliation only on a later background reconciliation opportunity.

There is no blocking wait, spin loop, sleep, or retry inside that reconciliation attempt.

The normal background reconciliation cadence remains:

```text
SIM4_INTENT_RECONCILE_SECONDS = 1.000
```

A callback-drop signal may request an earlier **single** reconciliation opportunity, but each opportunity still performs exactly one `pg_try_advisory_xact_lock` attempt and returns immediately on `false`.

Producer quote ingress and the SIM-3 persisted-intent callback never execute this database lock attempt.

## 3. Exact successful reconciliation transaction

When `pg_try_advisory_xact_lock(...)` returns `true`, the same runtime-owner backend session performs exactly:

1. begin/continue the reconciliation transaction;
2. obtain the exclusive intent-handoff xact lock successfully;
3. execute:

   ```sql
   SELECT public.atom_v9_sim4_read_intent_admission_fence();
   ```

   to obtain `new_fence_seq`;
4. commit the short fence-capture transaction, releasing the intent-handoff xact lock while retaining the separate session-scoped SIM-4 runtime-owner lock;
5. enumerate only the already-frozen closed interval:

   ```text
   last_reconciled_fence_seq < sim4_admission_seq <= new_fence_seq
   ```

   using bounded 256-row indexed pages;
6. advance `last_reconciled_fence_seq` only after the entire closed interval is successfully enumerated and handled.

The shared SIM-2 insert-trigger lock and exclusive SIM-4 try-lock remain the same advisory key. Therefore a successful exclusive acquisition proves all previously assigned shared-lock insert transactions have committed or rolled back before the fence reader executes, and no new insertion can receive a sequence until the short fence-capture transaction commits.

A failed try-lock proves no fence and closes no interval.

## 4. Stalled SIM-2 insert behavior

A SIM-2 insertion transaction that stalls while holding the shared intent-handoff advisory lock must not stall the sole SIM-4 worker.

While that shared lock remains held:

- SIM-4 reconciliation try-lock returns `false`;
- SIM-4 continues processing its in-memory quote/intent event loop;
- pending deadlines continue expiring under the frozen rules;
- quote eviction continues on its frozen wake schedule;
- already-closed reconciliation intervals remain valid;
- `last_reconciled_fence_seq` does not advance into the unsettled transaction;
- production and SIM-3 remain isolated from the failed reconciliation attempt.

After the stalled SIM-2 transaction eventually commits or rolls back, a later reconciliation opportunity may acquire the exclusive lock and close the next durable sequence interval.

No reconciliation attempt may wait indefinitely for a shared holder.

## 5. Reader failure and privilege failure

If the fence-reader function is missing, inaccessible, malformed, returns null/non-integer/negative data, or raises an error after the exclusive try-lock succeeds:

1. roll back the fence-capture transaction;
2. do not advance `last_reconciled_fence_seq`;
3. fail that reconciliation attempt closed;
4. return control to normal SIM-4 event processing;
5. record only bounded simulator operational telemetry; and
6. retry only at a later reconciliation opportunity.

No privileged fallback, direct sequence read, service-role connection, schema-owner connection, or production database credential is permitted.

## 6. Required additional SIM-4 tests

SIM-4 implementation must test all earlier freeze requirements plus the following.

### Fence reader

- exact function name and zero-argument signature;
- `RETURNS bigint`;
- `LANGUAGE plpgsql`;
- `SECURITY DEFINER`;
- `SET search_path = pg_catalog`;
- returns `0` when `is_called = false`;
- returns exact `last_value` when `is_called = true`;
- performs no sequence mutation or table scan;
- runtime has no direct `USAGE`, `SELECT`, or `UPDATE` on the sequence;
- `PUBLIC`, `anon`, `authenticated`, `service_role`, and `atom_v9_v4_runtime` cannot execute the reader;
- only `atom_v9_sim_runtime` receives runtime execute authority;
- runtime reads the fence through the exact function call, not direct sequence access;
- malformed or inaccessible reader fails reconciliation closed with no privilege fallback.

### Bounded reconciliation lock

- exact call is `pg_try_advisory_xact_lock(1158704842749668574::bigint)`;
- the old blocking `pg_advisory_xact_lock` form is forbidden for reconciliation;
- `false` causes immediate rollback/return;
- a failed try-lock performs no fence read and no interval query;
- a failed try-lock does not advance `last_reconciled_fence_seq`;
- a stalled shared insert lock cannot stall quote processing or pending expiry;
- exactly one try-lock attempt occurs per reconciliation opportunity;
- no tight retry/spin occurs after false;
- later successful reconciliation closes the next sequence interval correctly;
- callback-drop-triggered reconciliation remains background-only and nonblocking to the producer.

### Successful fence capture

- successful exclusive try-lock and fence-reader call use the authoritative runtime-owner backend session;
- fence reader executes while the exclusive xact lock is held;
- short fence-capture commit releases the handoff xact lock but retains runtime session ownership;
- no new SIM-2 sequence assignment can cross into the captured closed interval;
- only complete closed-interval handling advances `last_reconciled_fence_seq`.

## 7. Documentation-only hard boundary

This amendment is documentation only.

It creates no Python implementation, migration execution, schema mutation, database object, Render change, web route, broker capability, entry record, SIM-5 resolution, SIM-6 state, or V9 behavior in this PR.

Future SIM-4 implementation remains constrained to the already-authorized six-file boundary. The reader function and bounded reconciliation lock behavior belong inside the already-authorized `migrations/027_create_v9_sim_entries.sql` and SIM-4 runtime implementation; no additional implementation file is authorized.

SIM-5 and SIM-6 remain unauthorized.
