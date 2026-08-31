# ATOM TRUE V9 — SIM-3A P1 Amendment to Exact SIM-4 Entry Freeze

**Status:** LAW after merge  
**Phase:** SIM-3A amendment  
**Change type:** Documentation only  
**Amends:** `docs/sim-3a-exact-sim4-entry-freeze.md` from PR #223  
**Authorized next phase:** SIM-4 only  
**Simulator:** `ATOM_TRUE_V9_SIM_1`  
**Mode:** `PAPER_ONLY`  
**Instrument:** one simulated COIN share

This document resolves the four remaining Codex P1 review threads on PR #223. It changes no runtime, schema, migration, test, deployment, broker, or simulator behavior by itself. Where this amendment conflicts with the PR #223 freeze, this amendment controls. Every PR #223 rule not expressly amended below remains binding.

## 1. Exact Alpaca SIP source identity

`SIM4_QUOTE_SOURCE_SPEC = ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1` may be assigned only to a COIN quote returned by a successful Alpaca latest-stock-quotes request with this exact request identity:

```text
method = GET
scheme = https
host = data.alpaca.markets
port = absent or 443
path = /v2/stocks/quotes/latest
fragment = absent
query multimap = {
  symbols: COIN,QQQ
  feed: sip
}
```

Query-pair ordering and percent-encoding may differ, but the decoded query multimap must equal the map above, with exactly one value for each key and no additional query key. The outbound request actually passed to the HTTP client must explicitly contain `feed=sip`. An account entitlement, credential default, SDK default, constant name, response shape, or assumption about provider routing is not proof of SIP identity.

The source identity must be classified from the exact request actually sent. If the request omits `feed=sip`, uses another feed, contains an unknown or duplicate query key, uses a fallback source, or otherwise fails the exact identity above, the production quote path continues unchanged but the SIM-4 adapter receives no supported source identity and emits no SIM-4 quote event. Such a quote may not be labeled or hashed as `ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1`.

SIM-4 must not add, remove, or rewrite any parameter on the shared production polling request; change its endpoint, symbols, cadence, timeout, fallback, or consumers; or issue a second provider request. Its authorized `quant/live_market.py` change is limited to preserving the exact provider nanosecond value, classifying the already-constructed outbound request identity without mutation, and making the frozen post-publication nonblocking callback only when that identity is the exact SIP identity above.

The current shared request is therefore not made SIP by SIM-4. Until an independently frozen, reviewed, merged, deployed, and live-proven production-source change makes the request actually sent satisfy the exact identity above, live SIM-4 quote admission remains disabled. This amendment does not authorize or implement that production-source change.

## 2. Exact ownership and actionable-intent precedence

The bounded restart-ownership interval is exactly:

```text
recovery_lower_bound = runtime_started_at - exactly 2 seconds
owned pre-start interval = [recovery_lower_bound, runtime_started_at)
```

An unmatched intent with `publication_at < recovery_lower_bound` is outside SIM-4 runtime ownership. Whether it arrives through startup recovery, a delayed live callback, or replayed callback, SIM-4 must end without creating an entry row, scanning quotes, or classifying collision, restart gap, or expiry. Equality at `recovery_lower_bound` is owned. This preserves the original no-historical-backfill boundary.

For every owned actionable intent, the following precedence is binding. No later item may override an earlier item:

1. Begin a short entry transaction and acquire both the active-worker fence required by section 4.1 and the exact horizon advisory lock frozen in section 4.2.
2. Under those locks, read any terminal entry row for the same `intent_id`. If one exists, validate and return the frozen idempotent result.
3. If the intent is pre-start and older than `recovery_lower_bound`, end the transaction without an entry row under the ownership rule above.
4. Under the same horizon lock, read durable open occupancy for the intent horizon.
5. If a durable open `ENTERED` row exists, persist or validate `SKIPPED_POSITION_OPEN` with that row's exact `entry_id` as `blocking_entry_id`.
6. Otherwise, if `publication_at < runtime_started_at`, persist or validate `SKIPPED_RESTART_GAP`.
7. Otherwise, if the live intent is late under section 3.1, persist or validate `SKIPPED_WINDOW_EXPIRED`.
8. Otherwise, end the short classification transaction without an entry row and admit the intent to the normal bounded quote-selection window.

The short classification transaction must commit an immediate terminal row or end without one; it must never remain open while waiting for a quote.

When a pending intent later reaches quote selection or expiry, its terminal transaction must reacquire the active-worker fence condition and the same horizon advisory lock and repeat, in order, the existing-intent idempotency read and durable-occupancy read before choosing a terminal result. A blocker found then produces `SKIPPED_POSITION_OPEN`; only a still-unblocked intent may become `ENTERED` or `SKIPPED_WINDOW_EXPIRED`.

`NO_TRADE` and `UNAVAILABLE` intents retain their exact immediate mappings only inside the same bounded ownership interval. Older unmatched pre-start non-actionable intents remain untouched.

Within the owned interval, collision precedence applies both to startup recovery and to a live intent delivered after a worker restart. A recent unmatched actionable intent for a horizon already occupied by a durable `ENTERED` row is always `SKIPPED_POSITION_OPEN`, never `SKIPPED_RESTART_GAP`, and preserves the exact blocker ID. `SKIPPED_RESTART_GAP` is permitted only when no durable blocker exists.

The idempotency read, occupancy read, and insertion or validation of each immediate actionable terminal result occur in one fenced and horizon-locked transaction. A restart, rolling replacement, or timing boundary cannot change a provable owned collision into a restart gap or expiry.

## 3. Bounded late-intent handling, queued-quote drain, and quote eviction

### 3.1 Exact live-intent observation time

When the active `SimulationEntryWorker` dequeues a live persisted-intent event, it reads the injected UTC clock exactly once, before any quote-buffer scan or entry-store work:

```text
intent_observed_at = injected_utc_clock()
```

`intent_observed_at` is operational in-memory metadata only. It is not added to `SimulationEntryRecord`, its hash, or the database schema.

After the ownership, collision, and restart checks in section 2, a live actionable intent is late exactly when:

```text
intent_observed_at > entry_deadline_at
```

A live actionable intent observed exactly at the inclusive deadline is not late. A late intent becomes `SKIPPED_WINDOW_EXPIRED` without scanning, selecting, or reconstructing any quote that was not already successfully enqueued by the watermark rule in section 3.2. Database insertion delay, SIM-3 callback delay, event-queue delay, and worker backlog do not extend the frozen two-second window.

### 3.2 Exact event sequence and expiry watermark

The one active worker owns one submission mutex and one monotonically increasing operational enqueue sequence:

```text
next_enqueue_sequence starts at 1 for each fenced runtime
last_successful_enqueue_sequence starts at 0
```

Intent and quote adapters acquire the submission mutex only for bounded event construction and `put_nowait`. The candidate sequence is assigned inside that critical section. It becomes consumed and visible as `last_successful_enqueue_sequence` only if `put_nowait` succeeds. A full-queue drop consumes no sequence. Sequence values are Python integers, never wrap, and are not persisted, hashed, or added to the immutable intent, quote, or entry contracts.

For a quote event, the injected `accepted_at` clock read occurs inside the same submission critical section immediately before the successful `put_nowait`. A quote event that is not successfully enqueued is not admitted to SIM-4 and cannot satisfy an intent.

The worker processes the event queue in ascending enqueue sequence and tracks `last_processed_sequence`. When it first observes that a pending intent satisfies:

```text
entry_deadline_at < worker_now
```

it snapshots, under the submission mutex:

```text
expiry_watermark = last_successful_enqueue_sequence
```

The watermark is fixed for that expiry decision. The worker must continue FIFO processing until `last_processed_sequence >= expiry_watermark` before persisting `SKIPPED_WINDOW_EXPIRED` for that intent. Every valid quote event with sequence at or below the watermark is therefore admitted or rejected under the frozen quote rules before expiry; a quote among them with `accepted_at <= entry_deadline_at` remains eligible even when worker or database backlog causes it to be processed after the wall-clock deadline.

Events successfully enqueued after the watermark have greater sequences and cannot delay or alter that expiry decision. Continuous producers cannot move an existing watermark. If an eligible quote produces `ENTERED` or a collision produces `SKIPPED_POSITION_OPEN` while the watermark is draining, no expiry row is created.

### 3.3 Exact age-based quote eviction

For each deadline sweep, the worker first completes every due intent's fixed expiry watermark from section 3.2 and terminalizes those decisions. It then reads the injected UTC clock once as `eviction_now` and computes:

```text
quote_eviction_cutoff = eviction_now - exactly 2 seconds
```

Before testing quote-buffer capacity or retaining an incoming quote, it evicts every buffered quote satisfying:

```text
quote.accepted_at < quote_eviction_cutoff
```

A quote exactly equal to the cutoff is retained. No other age cutoff is permitted. An incoming valid quote may be considered for currently pending intents before the capacity decision; if retained after stale eviction, it counts toward the same 256-object cap.

Age eviction may run only when no pending intent with `entry_deadline_at < eviction_now` is still waiting for its fixed expiry watermark. At that point every remaining pending intent has `publication_at >= eviction_now - 2 seconds`. Every future live intent first observed after `eviction_now` with an earlier publication time is terminally late under section 3.1 or outside bounded restart ownership under section 2. Because a usable quote requires `quote.accepted_at >= publication_at`, a quote older than the cutoff cannot satisfy any current or future admissible intent.

After stale eviction, the quote buffer remains capped at 256. If it is still full, the incoming quote is dropped under the existing nonblocking overflow rule. Stale quotes may not keep the buffer permanently full, and eviction never reaches historical tables or reconstructs missed data.

## 4. Exact PostgreSQL worker fencing and horizon advisory locks

### 4.1 Single active-worker fence

Exactly one SIM-4 worker may be active across all processes and concurrently deployed versions. The global fence is the two-argument session-scoped PostgreSQL advisory lock with these exact inputs:

```text
SIM4_ACTIVE_WORKER_FENCE_NAMESPACE = 209182638
SIM4_ACTIVE_WORKER_FENCE_KEY = -1
SIM4_ACTIVE_WORKER_FENCE_RETRY_SECONDS = 0.100
```

Acquisition uses exactly:

```sql
SELECT pg_try_advisory_lock(
    209182638::integer,
    -1::integer
);
```

The worker obtains one dedicated connection from the existing simulator connection factory and calls the acquisition exactly once per attempt. Only a `true` result activates that worker. The fence connection is also the sole connection on which that active worker performs SIM-4 recovery reads and entry-store transactions. Cursors still close after each operation and every transaction commits or rolls back; the fence connection itself remains open only for the fenced runtime and closes at deactivation. This dedicated runtime connection is the sole exception to earlier per-operation connection-close language.

A worker that receives `false` is inactive. It may retry in its daemon lifecycle no more often than once every exactly 100 milliseconds, but it must not read `runtime_started_at`, run recovery, accept or queue intent or quote events, retain a quote buffer, or perform an entry read or write before acquiring the fence. Its adapters return immediately without affecting production or SIM-3.

After acquiring the fence, the worker clears all operational queue and buffer state, reads `runtime_started_at` exactly once, runs bounded recovery, and only then atomically enables event intake. No event collected while inactive may cross the activation boundary.

On normal shutdown, the active worker atomically disables intake, stops all entry processing, ends or rolls back any transaction, and only then executes:

```sql
SELECT pg_advisory_unlock(
    209182638::integer,
    -1::integer
);
```

and closes the fence connection. If the one-second join bound is reached, the worker is first marked inactive and its sole fence/store connection is closed so any in-flight transaction rolls back and no further terminal write is possible; process shutdown then continues without voluntarily handing an active writer to the next version.

If the fence connection is lost, the worker immediately becomes inactive, drops its in-memory queue, pending state, and quote buffer, and may not perform another entry read or write. Reacquisition creates a fresh fenced runtime with a new `runtime_started_at` and the exact bounded restart rules. It may not resume old in-memory candidates.

Because inactive workers accept no events and only the fence holder can execute entry transactions, rolling deployments cannot let a later quote or later same-horizon intent in another process overtake an earlier candidate held by the active worker. Cross-version scheduling therefore cannot choose the terminal entry result.

### 4.2 Exact per-horizon transaction lock

Every active SIM-4 open-position decision additionally uses the two-argument transaction-scoped PostgreSQL advisory lock with these exact frozen inputs:

```text
SIM4_ADVISORY_LOCK_NAMESPACE = 209182638
SIM4_ADVISORY_LOCK_HORIZON_KEY = horizon_seconds
allowed horizon_seconds = 30, 60, 300, 900, 1800, 3600
```

The exact SQL operation is semantically:

```sql
SELECT pg_advisory_xact_lock(
    209182638::integer,
    $1::integer
);
```

`$1` is the validated `horizon_seconds` for the frozen `COIN` intent. The symbol must be validated as exactly `COIN` before lock acquisition. The namespace is a frozen literal; implementations must not recompute it. The negative fence key and positive horizon keys are disjoint.

The horizon lock must be acquired after the transaction begins and while the same connection still holds the active-worker fence, before any read used to decide existing-intent idempotency, durable horizon occupancy, restart-gap status, late-expiry status, quote-backed entry status, or entry insertion. It is held until commit or rollback.

No Python `hash()`, database text hash, one-argument bigint advisory lock, alternate namespace, horizon ordinal, string concatenation, process-local mutex, or version-dependent derivation is compliant. Every concurrently deployable SIM-4 version maps the same COIN horizon to the same pair `(209182638, horizon_seconds)` and maps global worker ownership to `(209182638, -1)`.

## 5. Required SIM-4 test amendments

The SIM-4 implementation test obligation is extended by exactly these cases:

- exact SIP source identity is classified from the outbound request actually sent;
- an explicit decoded `feed=sip` pair is required before a SIM-4 quote event may be emitted;
- missing, duplicate, unknown, or non-SIP feed identity produces no SIM-4 quote event;
- SIM-4 neither mutates the shared production request nor creates a second provider request;
- the bounded owned pre-start interval is exactly `[runtime_started_at - 2 seconds, runtime_started_at)`;
- an older unmatched pre-start intent, including a delayed live callback, creates no entry row;
- equality at the recovery lower bound remains owned;
- a recovered durable blocker inside the owned interval yields `SKIPPED_POSITION_OPEN`, not `SKIPPED_RESTART_GAP`, with the exact blocker ID;
- restart gap is emitted only for an owned actionable pre-start intent with no durable blocker;
- transaction start, active fence, and exact horizon-lock acquisition precede the idempotency read;
- the first and repeated terminal transactions both recheck idempotency before occupancy;
- no database transaction remains open while an intent waits for a quote;
- successful queue events receive gap-free increasing operational sequences and dropped events consume no sequence;
- quote `accepted_at` and successful enqueue occur under the same bounded submission critical section;
- `intent_observed_at == entry_deadline_at` remains eligible for normal selection;
- the first representable time after the deadline starts a fixed expiry watermark rather than immediate expiry;
- every already-enqueued quote at or below that watermark is processed before expiry;
- a watermark does not advance when later events arrive and remains bounded under continuous production;
- expired pending intents complete their watermarks before age eviction;
- quotes strictly older than `eviction_now - 2 seconds` are evicted before capacity testing;
- a stale full buffer cannot permanently reject new quotes after age eviction;
- the exact session fence SQL and `(209182638, -1)` key are used;
- two rolling workers cannot both activate, accept events, or write entries;
- an inactive worker carries no queue or quote state into activation;
- fence loss disables writes, rolls back in-flight work, and requires fresh bounded recovery;
- the exact horizon-lock SQL, namespace literal, and horizon-seconds second key are used;
- rolling-version concurrency maps every lock identically and cannot reorder terminal candidates;
- the full existing suite remains green with no SIM-5 or SIM-6 behavior; and
- final implementation diff remains inside the six-file SIM-4 boundary frozen by PR #223.

## 6. Hard boundary

This amendment is documentation only. It does not implement SIM-4, SIM-5, or SIM-6. It creates no Python behavior, migration, database object, test, Render change, broker access, order path, resolution, P&L, or UI.

After merge, SIM-4 remains the only authorized next simulator implementation phase, within the exact six-file surface frozen by PR #223. The source-identity classification permitted in section 1 may observe but may not mutate the existing production request. A production-source change that makes the shared request explicitly SIP requires its own later freeze and is not authorized here. SIM-5 and SIM-6 remain unauthorized.
