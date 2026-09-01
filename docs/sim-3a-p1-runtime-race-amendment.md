# ATOM TRUE V9 — SIM-3A Runtime/Admission Race Amendment

**Status:** LAW after merge  
**Amends:** PR #223, `docs/sim-3a-exact-sim4-entry-freeze.md`, and `docs/sim-3a-p1-review-amendment.md`  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only  
**Simulator:** `ATOM_TRUE_V9_SIM_1`  
**Mode:** `PAPER_ONLY`

This document resolves the final Codex race and boundedness findings discovered while reviewing the P1 amendment. Where it conflicts with earlier SIM-3A text, this document controls.

It does not implement SIM-4 and does not authorize or implement SIM-5, SIM-6, broker access, order submission, options, execution P&L, compact state, or any V9 mathematical change.

## 1. Exact authoritative SIM-4 runtime ownership fence

Only one SIM-4 runtime may recover unmatched intents, accept SIM-4 events as authoritative, or persist terminal SIM-4 entry records at a time.

Freeze:

```text
SIM4_RUNTIME_OWNER_NAMESPACE = ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1
SIM4_RUNTIME_OWNER_SYMBOL = COIN
SIM4_RUNTIME_OWNER_LOCK_KEY = 2839171023325220901
SIM4_RUNTIME_OWNER_RETRY_SECONDS = 0.100
SIM4_RUNTIME_OWNER_MAX_WAIT_SECONDS = 1.000
```

The runtime-owner lock key is derived exactly from:

```python
payload = b"ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1\x00COIN"
digest = hashlib.sha256(payload).digest()
unsigned_key = int.from_bytes(digest[:8], byteorder="big", signed=False)
lock_key = unsigned_key if unsigned_key < 2**63 else unsigned_key - 2**64
```

Golden values:

```text
first eight SHA-256 bytes = 2766c300cde1d025
signed bigint key         = 2839171023325220901
```

The candidate SIM-4 runtime opens one dedicated `atom_v9_sim_runtime` PostgreSQL connection used only for ownership. It attempts exactly:

```sql
SELECT pg_try_advisory_lock(%s::bigint)
```

with the frozen key.

The lock is session-scoped, not transaction-scoped. The dedicated ownership connection remains open for the entire authoritative SIM-4 runtime lifetime. Closing that connection releases ownership.

A replacement runtime may retry ownership acquisition every 100 ms for at most 1.000 second total. It may not recover unmatched intents, accept authoritative SIM-4 intent/quote events, inspect pending runtime state, or persist entry records before ownership is acquired.

If the lock is not acquired within the one-second bound, SIM-4 remains disabled in that process. Production, SIM-1, SIM-2, and SIM-3 continue normally. No request path retries SIM-4 startup.

When ownership is acquired, that runtime alone may:

1. read `runtime_started_at`;
2. perform the bounded restart-recovery query;
3. own the SIM-4 FIFO and quote buffer;
4. process SIM-4 intent/quote events; and
5. persist terminal entry records.

Shutdown order is exact:

1. stop accepting new SIM-4 quote events;
2. stop accepting new SIM-4 intent events;
3. stop/join the SIM-4 worker under the existing one-second join bound;
4. close the dedicated ownership connection exactly once; and
5. never transfer in-memory pending intents or quotes to a successor.

A successor may begin recovery only after it successfully acquires the same session advisory lock. Therefore a still-active predecessor cannot race a replacement recovery and cannot have its in-memory actionable intent reclassified by the replacement.

The existing per-horizon transaction-scoped collision locks remain separate and unchanged. Runtime ownership does not replace the exact horizon advisory locks; both fences are required.

## 2. Exact atomic event-admission sequence fence

SIM-4 freezes one observable admission order for its bounded FIFO.

The worker owns one monotonically increasing unsigned Python integer counter:

```text
next_admission_sequence
```

The first successfully admitted event receives sequence `1`; every later successfully admitted event receives the next integer. Sequence values are runtime-only metadata and are not persisted or hashed.

Both intent and quote submissions use one shared narrow admission mutex owned by the SIM-4 runtime. Under that same mutex, and only after authoritative runtime ownership is confirmed:

1. verify the runtime is accepting events;
2. construct the immutable internal event payload except for sequence;
3. calculate `candidate_sequence = next_admission_sequence`;
4. call `put_nowait` while still holding the admission mutex;
5. if `put_nowait` succeeds, freeze `admission_sequence = candidate_sequence`, increment `next_admission_sequence` by one, and return success;
6. if `put_nowait` fails because the queue is full or throws, do not consume the sequence and return the existing failure/drop result.

The immutable runtime event types are exactly conceptually:

```python
@dataclass(frozen=True, slots=True)
class SimulationEntryIntentEvent:
    intent: SimulationTradeIntent
    handed_off_at: datetime
    admission_sequence: int

@dataclass(frozen=True, slots=True)
class SimulationEntryQuoteEvent:
    quote: SimulationExecutableQuote
    admission_sequence: int
```

`admission_sequence` must be a positive integer and not a Boolean.

No producer may enqueue outside this shared admission mutex. The mutex protects only bounded in-memory sequence assignment and `put_nowait`; it performs no database, serialization, clock wait, network, or V9 work.

## 3. Exact expiry admission fence

When a pending intent reaches its inclusive deadline and no eligible quote is yet selected, equality does not expire it.

At the first injected UTC clock observation strictly greater than `entry_deadline_at`, the worker acquires the same shared admission mutex and snapshots:

```text
expiry_admission_fence = next_admission_sequence - 1
```

It then releases the mutex.

That snapshot is the exact cutoff. An event is considered admitted before expiry only when:

```text
admission_sequence <= expiry_admission_fence
```

The worker drains and processes FIFO events through that fence before finalizing the pending intent. Events with larger sequences were admitted after the fence and cannot affect that expired intent even if their `accepted_at` or `handed_off_at` timestamp is at or before the deadline.

A producer that read an equality-boundary `accepted_at` but had not completed the atomic admission step before the worker took the fence receives a sequence greater than the fence and cannot be applied retroactively.

A producer that completed atomic admission before the fence receives a sequence at or below the fence and is processed before expiry.

This sequence fence, not callback start time or clock-read time, is the authoritative enqueue cutoff.

After all events through the fence are processed:

- if the intent entered or collided, preserve that terminal result;
- otherwise persist `SKIPPED_WINDOW_EXPIRED` under the existing precedence and horizon transaction lock.

No event is removed from FIFO out of order. Events beyond the fence remain queued for normal later processing.

## 4. Exact worker wake boundaries

The SIM-4 worker may not block indefinitely while a pending intent or retained quote has a finite boundary.

Freeze:

```text
SIM4_BOUNDARY_RECHECK_SECONDS = 0.001
```

At every worker loop, calculate the earliest finite boundary among:

1. every pending intent `entry_deadline_at`; and
2. every retained quote `quote.accepted_at + 2 seconds`.

The queue wait timeout must be no later than that earliest boundary.

If the injected UTC clock reads exactly equal to the earliest boundary, the object remains valid under the frozen inclusive rule. The worker then schedules another wake no later than 1 ms later and repeats until the clock is strictly greater than the boundary or an event arrives first.

Therefore:

- pending intents expire without requiring another market quote;
- retained quotes are evicted without requiring another intent or market quote;
- equality remains inclusive; and
- strict-greater expiry/eviction is eventually observed without busy-spinning indefinitely.

For a quote with no pending intents, the worker still wakes at `quote.accepted_at + 2 seconds`; if equality is observed, it rechecks within 1 ms until strictly greater, then evicts the quote.

For a pending intent with no retained quotes, the worker still wakes at `entry_deadline_at`; equality remains pending, and the first strictly-greater observation triggers the atomic admission-fence procedure in Section 3.

The wake/recheck timer is in-memory scheduling only. It creates no persisted timestamp, hash field, database row, or synthetic evidence.

## 5. Updated restart precedence under runtime ownership

The earlier terminal-decision precedence remains unchanged, but restart recovery is authorized only after the runtime-owner session lock is acquired.

Exact restart sequence:

1. acquire the frozen runtime-owner session advisory lock;
2. if not acquired within one second, disable SIM-4 in that process and perform no recovery;
3. read `runtime_started_at` once;
4. recover durable open occupancy;
5. query unmatched intents only in `[runtime_started_at - 2 seconds, runtime_started_at)`;
6. process them in ascending `publication_at`, canonical horizon order, and `intent_id`;
7. for each actionable intent, acquire the exact horizon transaction advisory lock and re-read durable occupancy;
8. emit `SKIPPED_POSITION_OPEN` with the exact blocker when occupied;
9. otherwise emit `SKIPPED_RESTART_GAP`.

Because only the authoritative runtime can recover, an active predecessor cannot simultaneously own a pending intent while a replacement terminalizes it as a restart gap.

## 6. Required additional SIM-4 tests

SIM-4 implementation must add tests covering all earlier SIM-3A and P1-amendment requirements plus the following.

### Runtime-owner fence

- exact runtime-owner namespace bytes and golden bigint key;
- exact `pg_try_advisory_lock(bigint)` call;
- dedicated ownership connection retained for runtime lifetime;
- replacement cannot recover while predecessor owns the lock;
- predecessor pending actionable intent cannot be reclassified by replacement;
- replacement acquisition after predecessor connection close;
- 100 ms retry cadence and one-second maximum acquisition window;
- failed acquisition disables only SIM-4;
- no request-path retry;
- ownership connection closes on shutdown;
- runtime-owner fence and per-horizon transaction locks are both enforced.

### Admission fence

- first admitted event sequence is 1;
- monotonically increasing successful admission sequences;
- failed/full `put_nowait` does not consume a sequence;
- intent and quote events share one sequence domain;
- sequence assignment and `put_nowait` are atomic under one mutex;
- expiry fence snapshots `next_admission_sequence - 1` under that same mutex;
- equality-boundary quote admitted before the fence is processed before expiry;
- equality-boundary quote admitted after the fence cannot affect the expired intent;
- FIFO order is preserved through the fence;
- events beyond the fence remain queued;
- sequence metadata is not persisted or hashed.

### Wake boundaries

- pending-intent deadline bounds queue wait;
- retained-quote expiry bounds queue wait even with no pending intents;
- equality causes a recheck no later than 1 ms;
- strictly-greater intent deadline invokes the admission-fence drain before expiry;
- strictly-greater quote-retention boundary evicts the quote;
- quote buffer drains without any later market or intent event;
- no busy unbounded wait at equality;
- timers create no synthetic evidence or persisted state.

## 7. Hard documentation-only boundary

This amendment changes documentation only.

It creates no Python implementation, test implementation, migration, schema, database object, Render change, web route, runtime hook, broker capability, simulator entry, simulator resolution, P&L, compact state, or V9 change.

The original six-file SIM-4 implementation boundary remains unchanged:

1. `migrations/027_create_v9_sim_entries.sql`;
2. `quant/v9_sim4_entry.py`;
3. `tests/test_v9_sim4_entry.py`;
4. minimal post-success persisted-intent callback changes in `quant/v9_sim3_capture.py`;
5. minimal exact SIP/provider-nanosecond and post-publication callback changes in `quant/live_market.py`; and
6. SIM-4 construction/lifecycle changes only in `quant/web.py`.

The dedicated runtime-owner connection, event admission fence, counters, mutex, and timers must be implemented only inside those already-authorized SIM-4 files. No new implementation file is authorized by this amendment.

SIM-5 and SIM-6 remain unauthorized.
