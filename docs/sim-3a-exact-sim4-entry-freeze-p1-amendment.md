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
path = /v2/stocks/quotes/latest
query multimap = {
  symbols: COIN,QQQ
  feed: sip
}
```

Query-parameter ordering and percent-encoding may differ, but the decoded query multimap must equal the map above. The outbound request itself must explicitly contain `feed=sip`. An account entitlement, credential default, SDK default, response shape, or assumption about Alpaca routing is not proof of SIP identity.

A response obtained without the explicit `feed=sip` request parameter, with a different feed value, through a fallback source, or with missing or unknown request identity produces no SIM-4 quote event and may not use `ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1`. QQQ may remain in the existing multi-symbol request, but SIM-4 admits only the COIN quote.

The PR #223 authorization for `quant/live_market.py` is amended only to permit the minimal addition of the explicit `feed=sip` parameter to the existing latest-quotes request, together with the already frozen provider-nanosecond preservation and post-publication nonblocking callback. No provider, endpoint, symbol set, polling cadence, fallback, or production mathematics change is authorized.

## 2. Exact actionable-intent classification precedence

For every actionable intent, the following precedence is binding. No later item may override an earlier item:

1. If a terminal entry row already exists for the same `intent_id`, validate and return the frozen idempotent result.
2. Begin the entry transaction, acquire the exact advisory lock frozen in section 4, and read durable open occupancy for the intent horizon.
3. If a durable open `ENTERED` row exists, persist or validate `SKIPPED_POSITION_OPEN` with that row's exact `entry_id` as `blocking_entry_id`.
4. Otherwise, if `publication_at < runtime_started_at`, persist or validate `SKIPPED_RESTART_GAP`.
5. Otherwise, if the live intent is late under section 3, persist or validate `SKIPPED_WINDOW_EXPIRED`.
6. Otherwise, admit the intent to the normal bounded quote-selection window. Any later terminal transaction must reacquire the same advisory lock and recheck durable occupancy before choosing `ENTERED`; a blocker found then produces `SKIPPED_POSITION_OPEN`.

`NO_TRADE` and `UNAVAILABLE` intents retain their exact immediate mappings and do not participate in open-position collision classification.

This precedence applies both to startup recovery and to a live intent delivered after a worker restart. During startup recovery, a recent unmatched actionable intent for a horizon already occupied by a durable `ENTERED` row is always `SKIPPED_POSITION_OPEN`, never `SKIPPED_RESTART_GAP`, and preserves the exact blocker ID. `SKIPPED_RESTART_GAP` is permitted only when no durable blocker exists.

The open-occupancy read and insertion or idempotency validation of an immediate actionable terminal result occur in the same locked transaction. A restart, rolling replacement, or timing boundary cannot change a provable collision into a restart gap or expiry.

## 3. Bounded late-intent handling and quote eviction

### 3.1 Exact live-intent observation time

When `SimulationEntryWorker` dequeues a live persisted-intent event, it reads the injected UTC clock exactly once, immediately before any quote-buffer scan or entry-store work:

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

At the start of each worker event iteration and each deadline sweep, the worker reads the injected UTC clock once as `worker_now` and computes:

```text
quote_eviction_cutoff = worker_now - exactly 2 seconds
```

Before testing quote-buffer capacity or appending an incoming quote, it evicts every buffered quote satisfying:

```text
quote.accepted_at < quote_eviction_cutoff
```

A quote exactly equal to the cutoff is retained. No other age cutoff is permitted.

This eviction is safe because every pending intent whose window is still open has `publication_at >= worker_now - 2 seconds`, and every future live intent first observed after `worker_now` must also have `publication_at >= its intent_observed_at - 2 seconds` or be terminally late. Since a usable quote requires `quote.accepted_at >= publication_at`, a quote older than the cutoff cannot satisfy any current or future admissible intent.

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

The lock must be acquired after the transaction begins and before any read used to decide existing intent idempotency, durable horizon occupancy, restart-gap status, late-expiry status, or entry insertion. It is held until commit or rollback.

No Python `hash()`, database text hash, one-argument bigint advisory lock, alternate namespace, horizon ordinal, string concatenation, process-local mutex, or version-dependent derivation is compliant. Every concurrently deployed SIM-4 version must acquire the same pair `(209182638, horizon_seconds)` for the same COIN horizon.

## 5. Required SIM-4 test amendments

The SIM-4 implementation test obligation is extended by exactly these cases:

- the outbound latest-quotes request explicitly contains the exact decoded query pair `feed=sip`;
- missing, unknown, or non-SIP feed identity produces no SIM-4 quote event;
- a recovered durable blocker yields `SKIPPED_POSITION_OPEN`, not `SKIPPED_RESTART_GAP`, with the exact blocker ID;
- restart gap is emitted only when the actionable pre-start intent has no durable blocker;
- `intent_observed_at == entry_deadline_at` remains eligible for normal selection;
- the first representable time after the deadline yields `SKIPPED_WINDOW_EXPIRED` without a quote-buffer scan;
- quotes strictly older than `worker_now - 2 seconds` are evicted before capacity testing;
- a stale full buffer cannot permanently reject new quotes after age eviction;
- the exact SQL lock function, namespace literal, and horizon-seconds second key are used;
- rolling-version concurrency maps the same COIN horizon to the same advisory-lock pair; and
- the full existing suite remains green with no SIM-5 or SIM-6 behavior.

## 6. Hard boundary

This amendment is documentation only. It does not implement SIM-4, SIM-5, or SIM-6. It creates no Python behavior, migration, database object, test, Render change, broker access, order path, resolution, P&L, or UI.

After merge, SIM-4 remains the only authorized next implementation phase, within the exact six-file surface frozen by PR #223 as narrowly amended in section 1. SIM-5 and SIM-6 remain unauthorized.
