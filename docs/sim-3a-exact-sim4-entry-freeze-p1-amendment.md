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

## 2. Exact actionable-intent classification precedence

For every actionable intent, the following precedence is binding. No later item may override an earlier item:

1. Begin a short entry transaction and acquire the exact advisory lock frozen in section 4.
2. Under that lock, read any terminal entry row for the same `intent_id`. If one exists, validate and return the frozen idempotent result.
3. Under the same lock, read durable open occupancy for the intent horizon.
4. If a durable open `ENTERED` row exists, persist or validate `SKIPPED_POSITION_OPEN` with that row's exact `entry_id` as `blocking_entry_id`.
5. Otherwise, if `publication_at < runtime_started_at`, persist or validate `SKIPPED_RESTART_GAP`.
6. Otherwise, if the live intent is late under section 3, persist or validate `SKIPPED_WINDOW_EXPIRED`.
7. Otherwise, end the short classification transaction without an entry row and admit the intent to the normal bounded quote-selection window.

The short classification transaction must commit an immediate terminal row or end without one; it must never remain open while waiting for a quote.

When a pending intent later reaches quote selection or expiry, its terminal transaction must reacquire the same advisory lock and repeat, in order, the existing-intent idempotency read and durable-occupancy read before choosing a terminal result. A blocker found then produces `SKIPPED_POSITION_OPEN`; only a still-unblocked intent may become `ENTERED` or `SKIPPED_WINDOW_EXPIRED`.

`NO_TRADE` and `UNAVAILABLE` intents retain their exact immediate mappings and do not participate in open-position collision classification.

This precedence applies both to startup recovery and to a live intent delivered after a worker restart. During startup recovery, a recent unmatched actionable intent for a horizon already occupied by a durable `ENTERED` row is always `SKIPPED_POSITION_OPEN`, never `SKIPPED_RESTART_GAP`, and preserves the exact blocker ID. `SKIPPED_RESTART_GAP` is permitted only when no durable blocker exists.

The idempotency read, occupancy read, and insertion or validation of each immediate actionable terminal result occur in one locked transaction. A restart, rolling replacement, or timing boundary cannot change a provable collision into a restart gap or expiry.

## 3. Bounded late-intent handling and quote eviction

### 3.1 Exact live-intent observation time

When `SimulationEntryWorker` dequeues a live persisted-intent event, it reads the injected UTC clock exactly once, before any quote-buffer scan or entry-store work:

```text
intent_observed_at = injected_utc_clock()
```

`intent_observed_at` is operational in-memory metadata only. It is not added to `SimulationEntryRecord`, its hash, or the database schema.

After the collision and restart checks in section 2, a live actionable intent is late exactly when:

```text
intent_observed_at > entry_deadline_at
```

A live actionable intent observed exactly at the inclusive deadline is not late. A late intent becomes `SKIPPED_WINDOW_EXPIRED` without scanning, selecting, or reconstructing any buffered quote. This rule applies even if a buffered quote would otherwise have timestamps inside the intent's historical two-second window.

An intent first observed after its deadline therefore cannot claim an older buffered quote. Database insertion delay, SIM-3 callback delay, event-queue delay, and worker backlog do not extend the frozen two-second window.

### 3.2 Exact age-based quote eviction

For each worker event iteration and each deadline sweep, the worker reads the injected UTC clock once as `worker_now`. Before age eviction, it must first complete deterministic processing for the dequeued event and terminalize every pending intent satisfying:

```text
entry_deadline_at < worker_now
```

using every valid candidate quote already admitted to that intent's window. An intent whose deadline equals `worker_now` remains open because the upper boundary is inclusive.

After those decisions, the worker computes:

```text
quote_eviction_cutoff = worker_now - exactly 2 seconds
```

Before testing quote-buffer capacity or retaining an incoming quote, it evicts every buffered quote satisfying:

```text
quote.accepted_at < quote_eviction_cutoff
```

A quote exactly equal to the cutoff is retained. No other age cutoff is permitted. An incoming valid quote may be considered for currently pending intents before the capacity decision; if retained after stale eviction, it counts toward the same 256-object cap.

This eviction is safe because, after expired pending intents are terminalized, every remaining pending intent has `publication_at >= worker_now - 2 seconds`. Every future live intent first observed after `worker_now` with an earlier publication time is terminally late under section 3.1. Because a usable quote requires `quote.accepted_at >= publication_at`, a quote older than the cutoff cannot satisfy any current or future admissible intent.

After stale eviction, the quote buffer remains capped at 256. If it is still full, the incoming quote is dropped under the existing nonblocking overflow rule. Stale quotes may not keep the buffer permanently full, and eviction never reaches historical tables or reconstructs missed data.

## 4. Exact PostgreSQL advisory-lock key

Every SIM-4 open-position decision uses the two-argument transaction-scoped PostgreSQL advisory lock with these exact frozen inputs:

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

`$1` is the validated `horizon_seconds` for the frozen `COIN` intent. The symbol must be validated as exactly `COIN` before lock acquisition. The namespace is a frozen literal; implementations must not recompute it.

The lock must be acquired after the transaction begins and before any read used to decide existing-intent idempotency, durable horizon occupancy, restart-gap status, late-expiry status, quote-backed entry status, or entry insertion. It is held until commit or rollback.

No Python `hash()`, database text hash, one-argument bigint advisory lock, alternate namespace, horizon ordinal, string concatenation, process-local mutex, or version-dependent derivation is compliant. Every concurrently deployed SIM-4 version must acquire the same pair `(209182638, horizon_seconds)` for the same COIN horizon.

## 5. Required SIM-4 test amendments

The SIM-4 implementation test obligation is extended by exactly these cases:

- exact SIP source identity is classified from the outbound request actually sent;
- an explicit decoded `feed=sip` pair is required before a SIM-4 quote event may be emitted;
- missing, duplicate, unknown, or non-SIP feed identity produces no SIM-4 quote event;
- SIM-4 neither mutates the shared production request nor creates a second provider request;
- a recovered durable blocker yields `SKIPPED_POSITION_OPEN`, not `SKIPPED_RESTART_GAP`, with the exact blocker ID;
- restart gap is emitted only when the actionable pre-start intent has no durable blocker;
- transaction start and exact advisory-lock acquisition precede the idempotency read;
- the first and repeated terminal transactions both recheck idempotency before occupancy;
- no database transaction remains open while an intent waits for a quote;
- `intent_observed_at == entry_deadline_at` remains eligible for normal selection;
- the first representable time after the deadline yields `SKIPPED_WINDOW_EXPIRED` without a quote-buffer scan;
- expired pending intents are terminalized before age eviction;
- quotes strictly older than `worker_now - 2 seconds` are evicted before capacity testing;
- a stale full buffer cannot permanently reject new quotes after age eviction;
- the exact SQL lock function, namespace literal, and horizon-seconds second key are used;
- rolling-version concurrency maps the same COIN horizon to the same advisory-lock pair; and
- the full existing suite remains green with no SIM-5 or SIM-6 behavior.

## 6. Hard boundary

This amendment is documentation only. It does not implement SIM-4, SIM-5, or SIM-6. It creates no Python behavior, migration, database object, test, Render change, broker access, order path, resolution, P&L, or UI.

After merge, SIM-4 remains the only authorized next simulator implementation phase, within the exact six-file surface frozen by PR #223. The source-identity classification permitted in section 1 may observe but may not mutate the existing production request. A production-source change that makes the shared request explicitly SIP requires its own later freeze and is not authorized here. SIM-5 and SIM-6 remain unauthorized.
