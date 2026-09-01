# ATOM TRUE V9 — SIM-3A Durable Intent Fence Final Amendment

**Status:** LAW after merge  
**Amends:** PR #223 and every prior SIM-3A amendment in PR #227  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only

This is the controlling amendment for SIM-4 intent handoff/recovery. It resolves the final two Codex P1 findings: ownership-acquisition equality classification and transactions that cross the recovery snapshot. Where this document conflicts with any earlier SIM-3A text, this document controls.

It does not implement SIM-4 and does not authorize SIM-5 or SIM-6.

## 1. Ownership-wait equality is always a restart gap

The initial authoritative SIM-4 recovery set is established only after the frozen runtime-owner session lock has been acquired.

For the current worker generation define:

```text
ownership_wait_started_at
runtime_started_at
```

The initial handoff interval remains inclusive:

```text
ownership_wait_started_at <= intent.eligible_at <= runtime_started_at
```

For every actionable intent recovered from that inclusive interval, terminal precedence is exactly:

1. existing terminal entry record;
2. durable open-position collision -> `SKIPPED_POSITION_OPEN` with the exact blocker `entry_id`;
3. otherwise -> `SKIPPED_RESTART_GAP`.

This rule applies to the upper equality boundary exactly:

```text
intent.eligible_at == runtime_started_at
```

An actionable intent recovered by the initial handoff query at equality must never proceed into live pending quote selection and must never become `ENTERED`.

The fact that the timestamp equals `runtime_started_at` does not prove that the replacement observed the complete post-publication quote interval. Recovery origin controls the classification.

Non-actionable recovered intents retain their exact normal mappings:

```text
NO_TRADE    -> SKIPPED_NO_TRADE
UNAVAILABLE -> SKIPPED_UNAVAILABLE
```

## 2. Durable SIM-2 -> SIM-4 database admission fence

A callback alone is not sufficient proof that every committed SIM-1/SIM-2 intent reached the SIM-4 FIFO. SIM-4 therefore uses one durable database admission sequence plus one PostgreSQL shared/exclusive advisory fence.

Freeze:

```text
SIM4_INTENT_FENCE_NAMESPACE = ATOM_TRUE_V9_SIM4_INTENT_HANDOFF_FENCE_1
SIM4_INTENT_FENCE_LOCK_KEY = 1158704842749668574
SIM4_INTENT_RECONCILE_SECONDS = 1.000
SIM4_INTENT_RECONCILE_BATCH = 256
SIM4_INTENT_ADMISSION_SEQUENCE = public.atom_v9_sim4_intent_admission_seq
SIM4_INTENT_ADMISSION_COLUMN = sim4_admission_seq
SIM4_INTENT_ADMISSION_INDEX = atom_v9_sim_intents_sim4_admission_idx
SIM4_INTENT_ADMISSION_FUNCTION = public.atom_v9_sim4_assign_intent_admission_seq
SIM4_INTENT_ADMISSION_TRIGGER = atom_v9_sim_intents_sim4_admission_seq
```

Exact fence-key derivation:

```python
payload = b"ATOM_TRUE_V9_SIM4_INTENT_HANDOFF_FENCE_1\x00COIN"
digest = hashlib.sha256(payload).digest()
unsigned_key = int.from_bytes(digest[:8], byteorder="big", signed=False)
lock_key = unsigned_key if unsigned_key < 2**63 else unsigned_key - 2**64
```

Golden values:

```text
first eight SHA-256 bytes = 10148bea579e6cde
signed bigint key         = 1158704842749668574
```

This fence is separate from both:

- the session-scoped SIM-4 runtime-owner lock; and
- the per-horizon transaction advisory locks.

All three have distinct namespaces and purposes.

## 3. Migration 027 adds operational admission metadata to SIM-2 intents

The already-authorized `migrations/027_create_v9_sim_entries.sql` must additionally create the durable SIM-4 admission fence objects below. This does not change SIM-1 mathematical content, `intent_hash`, `intent_id`, `record_json`, or any existing SIM-2 decision/status field.

### 3.1 Admission sequence

Create exactly:

```sql
CREATE SEQUENCE public.atom_v9_sim4_intent_admission_seq
    AS bigint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    NO CYCLE;
```

No simulator runtime role receives direct `USAGE`, `SELECT`, or `UPDATE` on this sequence.

### 3.2 Operational column

Add exactly one nullable operational column to the existing intent table:

```sql
ALTER TABLE public.atom_v9_sim_intents
ADD COLUMN sim4_admission_seq bigint;
```

The column is excluded from all SIM-1 mathematical hashes and canonical payloads. Existing pre-SIM-4 rows remain `NULL`.

After the trigger below exists, every newly attempted SIM intent insertion receives a positive sequence before row insertion. Sequence gaps caused by rollback or `ON CONFLICT DO NOTHING` are valid and must not be reused.

### 3.3 Shared-lock trigger

Create exactly one `BEFORE INSERT FOR EACH ROW` trigger function:

```text
public.atom_v9_sim4_assign_intent_admission_seq()
```

Properties:

```text
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
```

Its behavior is exactly:

```sql
PERFORM pg_advisory_xact_lock_shared(1158704842749668574::bigint);
NEW.sim4_admission_seq := nextval('public.atom_v9_sim4_intent_admission_seq'::regclass);
RETURN NEW;
```

Attach it exactly as:

```sql
CREATE TRIGGER atom_v9_sim_intents_sim4_admission_seq
BEFORE INSERT ON public.atom_v9_sim_intents
FOR EACH ROW
EXECUTE FUNCTION public.atom_v9_sim4_assign_intent_admission_seq();
```

The trigger is part of the same transaction as SIM-2 intent persistence.

Therefore any insert transaction that has acquired a SIM-4 admission sequence also holds the shared transaction advisory lock until commit or rollback.

Revoke direct function execution from:

- `PUBLIC`;
- `anon`;
- `authenticated`;
- `service_role`;
- `atom_v9_v4_runtime`; and
- `atom_v9_sim_runtime`.

The trigger remains able to invoke the function under PostgreSQL trigger semantics; no runtime role is authorized to call it directly.

### 3.4 Reconciliation index

Create exactly one partial index:

```sql
CREATE INDEX atom_v9_sim_intents_sim4_admission_idx
ON public.atom_v9_sim_intents (sim4_admission_seq, intent_id)
WHERE sim4_admission_seq IS NOT NULL;
```

This index exists solely for bounded SIM-4 reconciliation. It does not alter SIM-2 uniqueness or mathematical identity.

## 4. Exact exclusive reconciliation fence

Only the authoritative SIM-4 runtime-owner session may perform reconciliation.

To establish a reconciliation fence, that same owner PostgreSQL session begins a transaction and executes exactly:

```sql
SELECT pg_advisory_xact_lock(1158704842749668574::bigint);
```

This is the exclusive form of the same key used by the SIM-2 insert trigger's shared lock.

The exclusive call has two effects:

1. it waits until every already-shared SIM-2 insert transaction has committed or rolled back; and
2. while held, no new SIM-2 intent insertion can pass its `BEFORE INSERT` shared-lock trigger and receive an admission sequence.

After the exclusive lock is acquired, read the sequence fence on that same transaction/session.

If the sequence has never been called, define:

```text
fence_seq = 0
```

Otherwise:

```text
fence_seq = public.atom_v9_sim4_intent_admission_seq.last_value
```

Then commit the fence transaction. Commit releases only the transaction-scoped intent handoff fence; the separate session-scoped runtime-owner lock remains held.

At the instant the exclusive fence is acquired, every successfully committed row with:

```text
sim4_admission_seq <= fence_seq
```

is durably visible. A later transaction cannot appear with a newly assigned sequence at or below that fence.

This property, not a one-time MVCC snapshot by itself, closes the concurrent-commit race.

## 5. Initial authoritative recovery

After runtime ownership is acquired:

1. capture `runtime_started_at` under the already-frozen rule;
2. establish the exclusive durable intent fence and obtain `initial_fence_seq`;
3. query committed unmatched intents through `initial_fence_seq` using the new admission index;
4. include the current-generation ownership-wait interval and the original recent restart interval;
5. deduplicate by immutable `intent_id`;
6. process in ascending `sim4_admission_seq`, then `intent_id`.

For initial handoff/restart recovery, an actionable recovered intent with:

```text
intent.eligible_at <= runtime_started_at
```

is recovery-origin evidence, not live-origin evidence.

After existing-terminal and durable-open collision checks, it must become:

```text
SKIPPED_RESTART_GAP
```

This includes `eligible_at == runtime_started_at` exactly.

No recovered pre/equality-start actionable intent may consume a quote or become `ENTERED`.

## 6. Continuous bounded reconciliation closes callback drops

The SIM-4 FIFO callbacks remain the low-latency path, but durable reconciliation is the completeness path.

The authoritative worker performs one reconciliation fence no less safely than once every:

```text
1.000 second
```

and also may request an earlier reconciliation after an intent callback is dropped because of:

- admission-lock contention;
- queue full;
- worker temporarily unavailable; or
- an ordinary nonblocking callback failure.

Producer callbacks must not perform database reconciliation themselves.

Maintain one runtime-only integer:

```text
last_reconciled_fence_seq
```

After each exclusive fence yields `new_fence_seq`, query only committed unmatched intents satisfying:

```text
last_reconciled_fence_seq < sim4_admission_seq <= new_fence_seq
```

ordered by:

```text
sim4_admission_seq ASC, intent_id ASC
```

Use pages of at most:

```text
256 rows
```

until that closed sequence interval is exhausted. Pagination must use the `(sim4_admission_seq, intent_id)` index and must not scan historical rows outside the closed fence interval.

Only after the entire interval has been enumerated may the worker advance:

```text
last_reconciled_fence_seq = new_fence_seq
```

Rows whose callback already produced an entry record are skipped idempotently by exact `intent_id`/terminal validation. Rows whose callback was dropped remain discoverable and are terminalized through the same frozen precedence.

Because future SIM-2 inserts cannot receive a sequence `<= new_fence_seq`, no transaction can commit later into an already-closed reconciliation interval.

## 7. Live-origin reconciliation behavior

A reconciled intent with:

```text
intent.eligible_at > runtime_started_at
```

is live-origin for the current authoritative generation.

Apply precedence exactly:

1. existing terminal record;
2. non-actionable mapping;
3. durable open-position collision;
4. if current worker time is strictly greater than `entry_deadline_at`, `SKIPPED_WINDOW_EXPIRED`;
5. otherwise it may enter normal pending/quote selection using only exact retained quotes that satisfy every frozen provider-time, accepted-time, admission-fence, and two-second-window rule.

Durable reconciliation does not authorize historical quote reconstruction. If the required quote is no longer present in the bounded in-memory quote buffer, the intent must wait only until its exact deadline and then expire.

A reconciliation query never manufactures a quote and never widens the entry window.

## 8. Pre-migration NULL admission rows

Rows created before migration 027 have:

```text
sim4_admission_seq IS NULL
```

They are never included in continuous sequence reconciliation.

On the first SIM-4 deployment only, the authoritative initial recovery may inspect NULL-sequence intents solely inside the already-frozen recent restart interval. Migration 027's table-locking DDL must complete before SIM-4 starts, so these pre-trigger rows are durably settled before runtime ownership begins.

For such recent NULL-sequence rows:

- non-actionable statuses retain normal mappings;
- an actionable row with a durable open blocker becomes `SKIPPED_POSITION_OPEN`;
- otherwise it becomes `SKIPPED_RESTART_GAP`;
- it can never become `ENTERED` through recovery.

No older NULL-sequence history is backfilled or scanned.

## 9. Failure isolation

Failure to obtain the exclusive intent reconciliation fence, query a closed sequence interval, deserialize a row, or persist a terminal SIM-4 entry:

- fails SIM-4 closed for the affected reconciliation attempt;
- does not advance `last_reconciled_fence_seq` past an incomplete interval;
- does not alter the SIM-1/SIM-2 intent;
- does not retry on the production quote or SIM-3 callback thread;
- does not affect V9, market ingestion, website availability, or SIM-3 persistence.

The next authoritative worker reconciliation may retry the same unadvanced closed sequence interval.

## 10. Exact additional implementation authorization

The original SIM-4 implementation remains confined to the already-authorized files except for the database behavior implemented entirely by migration 027.

No modification to `quant/v9_sim2_store.py` is required or authorized by this amendment. The shared insertion fence is enforced by the database trigger created in:

```text
migrations/027_create_v9_sim_entries.sql
```

Therefore the original six-file SIM-4 Python/migration boundary remains unchanged.

No seventh implementation file is authorized.

## 11. Required additional tests

SIM-4 implementation must add all earlier required tests plus the following.

### Equality recovery classification

- actionable `eligible_at < runtime_started_at` recovered with no blocker -> `SKIPPED_RESTART_GAP`;
- actionable `eligible_at == runtime_started_at` recovered with no blocker -> `SKIPPED_RESTART_GAP`;
- recovered equality intent with a durable blocker -> `SKIPPED_POSITION_OPEN` with exact blocker ID;
- recovered equality intent never enters live pending selection;
- non-actionable equality intents preserve normal mappings.

### Database admission fence

- exact fence namespace bytes, digest bytes, and golden bigint key;
- exact sequence name/start/increment/no-cycle contract;
- exact nullable `sim4_admission_seq` column;
- exact partial reconciliation index;
- exact trigger/function names;
- trigger uses `pg_advisory_xact_lock_shared` before `nextval`;
- trigger assigns sequence in the same SIM-2 insert transaction;
- rollback/conflict sequence gaps are permitted and not reused;
- function is SECURITY DEFINER with `search_path = pg_catalog`;
- direct runtime function execution is revoked;
- SIM-1 payload/hash/ID are unchanged.

### Concurrent-commit fencing

- an insert transaction holding the shared fence must commit/rollback before SIM-4 acquires the exclusive fence;
- no new insert receives a sequence while the exclusive fence is held;
- all committed rows at or below captured `fence_seq` are visible after fence acquisition;
- a transaction started earlier but reaching INSERT later receives a sequence only after the exclusive fence releases and therefore lands above the closed fence;
- no later commit can appear inside an already-reconciled sequence interval.

### Continuous reconciliation

- dropped intent callback remains discoverable by its durable admission sequence;
- reconciliation runs on bounded closed sequence intervals;
- pagination is at most 256 rows and uses `(sim4_admission_seq, intent_id)` order;
- successful interval completion advances the fence exactly once;
- partial/failing interval does not advance the fence;
- callback-delivered and reconciliation-delivered copies deduplicate by `intent_id`;
- no historical full-table scan;
- no quote reconstruction;
- live reconciled intent before deadline may use only an already-retained valid quote;
- live reconciled intent after deadline becomes `SKIPPED_WINDOW_EXPIRED` unless collision precedence applies.

### Pre-migration rows

- NULL-sequence rows are excluded from continuous reconciliation;
- only recent NULL-sequence rows may be inspected on first deployment;
- actionable recent NULL row cannot become `ENTERED` through recovery;
- older NULL history is never backfilled.

## 12. Documentation-only hard boundary

This amendment is documentation only.

It creates no Python implementation, migration execution, schema mutation, database object, Render change, web route, broker capability, entry record, SIM-5 resolution, SIM-6 state, or V9 behavior in this PR.

SIM-4 may be implemented only after this amendment is merged and only under the complete controlling SIM-3A freeze set.

SIM-5 and SIM-6 remain unauthorized.
