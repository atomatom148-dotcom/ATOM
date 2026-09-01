# ATOM TRUE V9 — SIM-3A Review Fence Addendum

**Status:** LAW after merge  
**Amends:** `docs/sim-3a-p1-review-amendment.md`  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only

This addendum resolves the remaining Codex review findings on PR #227. Where this addendum conflicts with the prior SIM-3A amendment, this addendum controls. It does not implement SIM-4 and does not authorize SIM-5 or SIM-6.

## 1. Rolling-runtime ownership fence

Only one SIM-4 runtime may own recovery, pending intents, quote admission, collision decisions, or terminal entry persistence at a time, including during rolling deployment overlap.

Freeze:

```text
SIM4_RUNTIME_OWNER_NAMESPACE = ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1
SIM4_RUNTIME_OWNER_RETRY_SECONDS = 0.25
```

Construct exactly:

```python
owner_payload = b"ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1\x00COIN"
digest = hashlib.sha256(owner_payload).digest()
unsigned_key = int.from_bytes(digest[:8], byteorder="big", signed=False)
owner_lock_key = unsigned_key if unsigned_key < 2**63 else unsigned_key - 2**64
```

Golden identity:

```text
first eight SHA-256 bytes = 2766c300cde1d025
owner_lock_key = 2839171023325220901
```

SIM-4 acquires this as a dedicated session-scoped PostgreSQL advisory lock using the existing simulator runtime role:

```sql
SELECT pg_try_advisory_lock(%s::bigint)
```

The dedicated ownership connection remains open for the entire authoritative worker generation. The runtime may not read `runtime_started_at`, run restart recovery, accept intent/quote events, inspect pending state, or persist any SIM-4 terminal result until this call returns exactly true.

If acquisition returns false, the new generation remains inactive and retries only from its background daemon no more frequently than every 0.25 seconds. Production startup, SIM-3, V9, and web requests do not block on ownership acquisition.

`runtime_started_at` is read exactly once only after successful ownership acquisition. Therefore a replacement generation cannot classify intents while an authoritative predecessor still holds the lock.

Before processing each admitted event or performing recovery, the owner verifies the dedicated ownership connection is still usable with `SELECT 1`. Any ownership-connection failure immediately transitions that worker generation to inactive: it stops accepting new SIM-4 events and performs no further terminal entry persistence. It may not silently continue from in-memory ownership state.

On normal shutdown, the owner stops intake, completes the existing bounded stop behavior, executes:

```sql
SELECT pg_advisory_unlock(%s::bigint)
```

on the same dedicated session when possible, then closes that connection. Connection close is also sufficient to release the session lock.

A non-owner generation must not recover unmatched intents. Recovery begins only after exclusive runtime ownership is established.

## 2. Exact queue-admission fence

The prior statement "admitted before the strictly-greater expiry observation" is made observable with one exact in-process admission sequence.

`SimulationEntryWorker` owns one process-local `threading.Lock` named conceptually `admission_lock` and one integer counter:

```text
next_admission_seq starts at 1
```

Every SIM-4 queue submission, intent or quote, must use the same admission lock.

Define one immutable runtime-only envelope:

```python
@dataclass(frozen=True, slots=True)
class SimulationEntryQueueEnvelope:
    admission_seq: int
    event_kind: str
    payload: object
```

`event_kind` is exactly `INTENT` or `QUOTE`. The payload is the already-frozen immutable intent-event or executable-quote object. The envelope is runtime-only and is never hashed, persisted, or added to any database schema.

Under `admission_lock`, the submitting callback performs exactly:

1. read `candidate_seq = next_admission_seq`;
2. construct the immutable envelope with that sequence;
3. call `put_nowait(envelope)`;
4. only if `put_nowait` succeeds, set `next_admission_seq = candidate_seq + 1`;
5. release `admission_lock`.

If the queue is full, no sequence is consumed and the event is not admitted.

Because all submissions use the same lock, successful queue insertion order and `admission_seq` order are identical.

### 2.1 Expiry fence snapshot

When a pending intent reaches a clock observation strictly greater than its `entry_deadline_at`, the worker must not immediately expire it. The worker first acquires `admission_lock` and snapshots:

```text
expiry_fence_seq = next_admission_seq - 1
```

then releases the lock.

The worker then processes, in normal FIFO order, every already-admitted queue envelope with:

```text
admission_seq <= expiry_fence_seq
```

before finalizing that intent as `SKIPPED_WINDOW_EXPIRED`.

Only quote events that also satisfy the original provider/accepted-time entry-window predicates may enter the position. An envelope with `admission_seq > expiry_fence_seq` is after the frozen expiry fence and cannot be applied retroactively to that intent, even if its quote `accepted_at` is numerically at or before the deadline.

This makes the equality boundary independent of callback pauses between timestamp capture and `put_nowait`.

## 3. Exact quote-expiry wake boundary

The worker's blocking wait must be bounded by both pending-intent deadlines and retained-quote expiry boundaries.

For every buffered quote define:

```text
quote_expiry_boundary = quote.accepted_at + exactly 2 seconds
```

The next worker wake target is the earliest of:

- the earliest pending intent `entry_deadline_at`; and
- the earliest retained `quote_expiry_boundary`.

If the injected UTC clock is strictly before the target, the worker may block only until that target or until a new queue event arrives, whichever occurs first.

Because both intent expiry and quote eviction use a strict `>` comparison, a wake that observes time exactly equal to the target does not finalize or evict. The worker must perform a bounded recheck no later than:

```text
STRICT_BOUNDARY_RECHECK_SECONDS = 0.001
```

until the injected UTC clock is strictly greater than the boundary or a new queue event arrives.

Therefore a quote cannot remain buffered indefinitely merely because no pending intent and no later market event exists. Once time is strictly greater than `quote.accepted_at + 2 seconds`, the quote is evicted under the existing amendment rule.

The same 1 ms maximum recheck applies to an intent observed exactly at its deadline before creating the expiry admission fence.

## 4. Required tests added by this addendum

SIM-4 implementation must test at minimum:

### Runtime ownership

- exact owner namespace bytes, digest bytes, and golden signed bigint key;
- exact `pg_try_advisory_lock(bigint)` call;
- replacement runtime cannot recover while predecessor holds ownership;
- replacement acquires ownership only after predecessor releases/closes;
- `runtime_started_at` is captured only after ownership acquisition;
- non-owner receives no intent/quote ownership and persists no SIM-4 result;
- ownership-connection failure disables the generation before further persistence;
- background acquisition retry is no more frequent than 0.25 seconds;
- ownership acquisition never blocks production startup or request paths.

### Admission fence

- all intent and quote submissions share one admission sequence domain;
- successful FIFO insertion order equals sequence order;
- queue-full submissions consume no sequence;
- expiry fence snapshot is taken under the same admission lock;
- event inserted before the snapshot has sequence at or below the fence and is processed before expiry;
- callback timestamped at the deadline but inserted after the fence has a higher sequence and cannot enter retroactively;
- equality-boundary behavior is deterministic under forced callback pauses and thread interleavings.

### Quote-expiry wake

- with no pending intents and no later events, a retained quote causes a wake at its own two-second boundary;
- equality retains the quote;
- the first strictly-greater observation evicts it;
- equality rechecks occur no later than 1 ms apart;
- worker wait is bounded by the minimum pending-intent/quote-expiry target;
- quote buffer drains after the frozen retention bound without requiring a market event.

## 5. Scope remains documentation-only

This addendum changes documentation only. It creates no Python, migration, schema, runtime, Render, broker, web, SIM-4, SIM-5, or SIM-6 behavior.

The original six-file SIM-4 implementation boundary remains unchanged. No additional implementation file is authorized by this addendum.
