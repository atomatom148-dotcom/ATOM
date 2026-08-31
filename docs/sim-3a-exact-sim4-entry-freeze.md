# ATOM TRUE V9 — SIM-3A Exact SIM-4 Entry Freeze

**Status:** LAW after merge  
**Phase:** SIM-3A  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only  
**Simulator:** `ATOM_TRUE_V9_SIM_1`  
**Mode:** `PAPER_ONLY`  
**Instrument:** one simulated COIN share

This document is a binding amendment to `SIMULATION_FREEZE.md`. It resolves the exact SIM-4 causal executable-entry boundary. Where this document conflicts with earlier provisional SIM-4 language, this document controls. It does not implement SIM-4 and does not authorize SIM-5, SIM-6, broker access, options, order submission, or any production-mathematics change.

## 1. Exact SIM-4 purpose

SIM-4 consumes only immutable SIM-1 intents that SIM-3 has successfully persisted through SIM-2. It selects, records, and persists exactly one terminal entry result per observed intent under the rules below.

SIM-4 may:

- persist an immediate non-actionable entry result;
- wait for the first causal executable COIN quote inside the frozen entry window;
- open at most one simulated position per horizon;
- persist a collision, restart-gap, or expired-window result; and
- recover durable open-horizon occupancy after restart.

SIM-4 does not:

- resolve or close a position;
- calculate return, P&L, win/loss, drawdown, or aggregate state;
- choose a different direction, size, instrument, strike, or expiration;
- inspect V9 history, evidence, accuracy, RANGE, or probability;
- modify SIM-1 intents;
- submit broker orders; or
- run inside V1–V4 mathematics, a web request, or a production database transaction.

## 2. Frozen identities and constants

```text
SIM_EXECUTABLE_QUOTE_CONTRACT_VERSION = ATOM_TRUE_V9_SIM4_QUOTE_1
SIM_ENTRY_CONTRACT_VERSION = ATOM_TRUE_V9_SIM4_ENTRY_1
SIM_ENTRY_SCHEMA_VERSION = ATOM_TRUE_V9_SIM4_SCHEMA_1
SIM_ENTRY_STORE_VERSION = ATOM_TRUE_V9_SIM4_STORE_1
SIM_ENTRY_RUNTIME_VERSION = ATOM_TRUE_V9_SIM4_RUNTIME_1
SIM_CANONICALIZATION_VERSION = ATOM_TRUE_V9_SIM_CANONICAL_V4A_1
SIMULATOR_VERSION = ATOM_TRUE_V9_SIM_1
SIMULATION_MODE = PAPER_ONLY
SIM_ENTRY_TABLE = public.atom_v9_sim_entries
SIM_RUNTIME_ROLE = atom_v9_sim_runtime
MIGRATION_FILE = migrations/027_create_v9_sim_entries.sql
QUOTE_ID_PREFIX = v9simquote:
ENTRY_ID_PREFIX = v9simentry:
ENTRY_WINDOW_SECONDS = 2
SIM4_EVENT_QUEUE_CAPACITY = 256
SIM4_QUOTE_BUFFER_CAPACITY = 256
SIM4_QUOTE_SOURCE_SPEC = ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1
```

Migration ordinal `027` is currently the next unoccupied migration ordinal. If it is occupied when SIM-4 begins, implementation must stop without editing and report the conflict.

## 3. Publication timestamp

SIM-4 introduces no second forecast-publication clock.

For every intent:

```text
publication_at = intent.eligible_at
entry_deadline_at = publication_at + exactly 2 seconds
```

`intent.eligible_at` is already the frozen SIM-3 post-V4-persistence causal boundary. Database `created_at`, worker dequeue time, web display time, V9 cutoff time, and quote-poll time are not publication timestamps and must not replace it.

The two-second window is part of the mathematical entry record and hash. `publication_at` and `entry_deadline_at` must be timezone-aware UTC datetimes. The deadline must equal publication plus exactly 2,000,000 microseconds.

## 4. Immutable executable quote contract

SIM-4 defines one immutable simulator-only quote value:

```python
@dataclass(frozen=True, slots=True)
class SimulationExecutableQuote:
    contract_version: str
    canonicalization_version: str
    quote_id: str
    quote_hash: str
    source_spec: str
    symbol: str
    provider_event_ns: int
    accepted_at: datetime
    bid: float
    ask: float
    bid_size: float
    ask_size: float
```

No mutable nested value is permitted.

### 4.1 Quote source and event identity

Initial SIM-4 accepts only the existing production COIN Alpaca SIP latest-quote path. `source_spec` must equal `ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1` and `symbol` must equal `COIN`.

`provider_event_ns` is the exact integer nanosecond identity returned by the existing Alpaca RFC3339 timestamp parser. SIM-4 must not reconstruct it by rounding a binary64 epoch after the exact provider value has been discarded.

`accepted_at` is one injected UTC-clock read taken only after the COIN quote has passed the existing production validation and the corresponding immutable market/V9 publication has committed. It records when that exact accepted quote became available to the simulator. It is not supplied by the provider.

### 4.2 Quote validity

A quote object is valid only when:

- all exact version/source/symbol constants match;
- `provider_event_ns` is a nonnegative integer and not a Boolean;
- `accepted_at` is a finite timezone-aware UTC datetime;
- bid, ask, bid size, and ask size are finite binary64 values and not Booleans;
- `bid > 0`;
- `ask >= bid`;
- `bid_size >= 0`; and
- `ask_size >= 0`.

A quote is executable for a one-share `LONG` only when `ask_size >= 1`. It is executable for a one-share `SHORT` only when `bid_size >= 1`.

### 4.3 Quote hash and identity

`quote_hash` is SHA-256 over exactly these fields in this order:

1. `contract_version`
2. `canonicalization_version`
3. `source_spec`
4. `symbol`
5. `provider_event_ns`
6. `accepted_at`
7. `bid`
8. `ask`
9. `bid_size`
10. `ask_size`

It excludes exactly `quote_id` and `quote_hash`.

```text
quote_id = "v9simquote:" + quote_hash
```

SIM-4 reuses the frozen V4A canonicalization behavior without modification. Stored or deserialized quote hash/ID mismatches are rejected.

No separate quote-history table is authorized. The exact quote object is embedded in the immutable entry record.

## 5. Exact two-second entry window

For an actionable intent, a quote is inside the entry window only when all of the following hold:

```text
publication_at < provider_event_time <= entry_deadline_at
publication_at <= accepted_at <= entry_deadline_at
provider_event_time <= accepted_at
```

For comparison, `publication_at` and `entry_deadline_at` are converted deterministically to integer epoch nanoseconds from their canonical UTC microsecond values. No float-timestamp tolerance is authorized.

The lower provider-time boundary is strict because the quote must be after publication. The upper boundary is inclusive because the freeze states “no more than two seconds.”

The selected quote is the first valid executable quote in ascending order of:

1. `accepted_at`;
2. `provider_event_ns`; and
3. `quote_id`.

A quote accepted before publication is never used. A quote accepted after the deadline is never used even if its provider timestamp falls inside the window. Reconstruction, interpolation, midpoint execution, backdating, stale-quote reuse, and fabricated sizes are forbidden.

`LONG` entry price is exactly the selected ask. `SHORT` entry price is exactly the selected bid.

## 6. Immutable entry record

SIM-4 defines exactly one terminal immutable value per observed intent:

```python
@dataclass(frozen=True, slots=True)
class SimulationEntryRecord:
    contract_version: str
    canonicalization_version: str
    simulator_version: str
    entry_id: str
    entry_hash: str
    mode: str
    symbol: str
    instrument: str
    intent_id: str
    intent_hash: str
    source_cycle_id: str
    cutoff_at: datetime
    publication_at: datetime
    entry_deadline_at: datetime
    horizon: str
    horizon_seconds: int
    decision: str
    intent_status: str
    entry_status: str
    quantity_shares: int
    blocking_entry_id: str | None
    quote: SimulationExecutableQuote | None
    entry_price: float | None
```

No lists, mappings, or mutable nested values are permitted.

### 6.1 Entry hash and identity

`entry_hash` is SHA-256 over exactly these fields in declaration order, excluding exactly `entry_id` and `entry_hash`.

```text
entry_id = "v9simentry:" + entry_hash
```

Deserialization independently recalculates and verifies the entry hash, entry ID, nested quote hash, and nested quote ID.

`cutoff_at`, `publication_at`, horizon, horizon seconds, decision, intent status, and source-cycle identity must exactly match the referenced immutable SIM-1 intent. `publication_at` must equal `intent.eligible_at`.

## 7. Exact entry statuses

The only valid SIM-4 entry statuses are:

```text
ENTERED
SKIPPED_NO_TRADE
SKIPPED_UNAVAILABLE
SKIPPED_POSITION_OPEN
SKIPPED_WINDOW_EXPIRED
SKIPPED_RESTART_GAP
```

Their exact field rules are:

### `ENTERED`

- source intent status is `ACTIONABLE`;
- decision is `LONG` or `SHORT`;
- quantity is exactly `1`;
- quote is present and executable inside the exact window;
- blocking entry is null; and
- entry price equals ask for `LONG` or bid for `SHORT`.

### `SKIPPED_NO_TRADE`

- source intent status is `NO_TRADE`;
- decision is `NO_TRADE`;
- quantity is `0`;
- quote, blocking entry, and entry price are null.

### `SKIPPED_UNAVAILABLE`

- source intent status is `UNAVAILABLE`;
- decision is `NO_TRADE`;
- quantity is `0`;
- quote, blocking entry, and entry price are null.

### `SKIPPED_POSITION_OPEN`

- source intent status is `ACTIONABLE`;
- decision is `LONG` or `SHORT`;
- quantity is `0`;
- `blocking_entry_id` identifies the exact durable open entry for that horizon;
- quote and entry price are null.

### `SKIPPED_WINDOW_EXPIRED`

- source intent status is `ACTIONABLE`;
- decision is `LONG` or `SHORT`;
- no valid executable quote was admitted before the inclusive deadline;
- quantity is `0`;
- quote, blocking entry, and entry price are null.

Invalid and unsupported quotes are ignored while the window remains open; they do not create a separate terminal status.

### `SKIPPED_RESTART_GAP`

- source intent status is `ACTIONABLE`;
- decision is `LONG` or `SHORT`;
- the intent publication preceded the current SIM-4 runtime start and the exact first post-publication quote cannot be proven because an in-memory quote interval was lost;
- quantity is `0`;
- quote, blocking entry, and entry price are null.

There is no persisted `PENDING` status. Pending selection is bounded in-memory runtime state only.

## 8. One-open-position rule

The six horizon books remain independent. At most one simulated position may be open for each horizon.

A persisted `ENTERED` record occupies its horizon. `NO_TRADE`, `UNAVAILABLE`, collision, expiry, and restart-gap records never occupy a horizon.

Before SIM-5 exists, every persisted `ENTERED` record remains open. This intentionally means SIM-4 acceptance can create at most one successful entry per horizon. SIM-5 will later define the immutable resolution record and the exact durable rule by which a resolved entry no longer counts as open. SIM-4 must not prebuild or infer SIM-5 closure.

### 8.1 Atomic collision decision

The open-position check and terminal entry insertion occur in one database transaction under one deterministic transaction-scoped PostgreSQL advisory lock for `(COIN, horizon)`. Python’s randomized `hash()` must not be used for the lock key.

Inside that transaction:

1. validate whether an entry already exists for the intent;
2. validate the durable open entry for the horizon;
3. choose `ENTERED` or `SKIPPED_POSITION_OPEN`;
4. build the final immutable entry record; and
5. insert or validate idempotency.

Concurrent intents cannot both enter the same horizon. Other horizons do not share the lock and remain independent.

When several pending same-horizon actionable intents can use the same quote, they are considered in ascending order of:

1. `publication_at`;
2. canonical horizon order; and
3. `intent_id`.

The first transactionally successful entry occupies the horizon. Later candidates become `SKIPPED_POSITION_OPEN` and preserve the winning `blocking_entry_id`.

## 9. Restart and recovery rules

SIM-4 never reconstructs an entry from database market history or from a quote observed before the current worker started.

At one successful runtime start, SIM-4 reads its injected UTC clock exactly once as `runtime_started_at`, then:

1. recovers durable horizon occupancy from persisted `ENTERED` records;
2. reads only unmatched intents whose `eligible_at` is within the bounded interval `[runtime_started_at - 2 seconds, runtime_started_at)`;
3. creates `SKIPPED_RESTART_GAP` for recent actionable intents because the exact first quote may have been missed;
4. creates the normal deterministic non-actionable status for recent `NO_TRADE` or `UNAVAILABLE` intents; and
5. does not scan, backfill, or create entry records for older unmatched intents.

The bounded two-second recovery query prevents historical backfill on first deployment. Older intents remain valid SIM-1/SIM-2 evidence but are outside SIM-4 runtime ownership.

The in-memory quote buffer is never reconstructed. A restart cannot turn a pre-restart quote into an entry. Open horizons remain occupied after restart because occupancy is recovered from durable entry records.

## 10. Persistence boundary

SIM-4 persists entry records in one new isolated append-only table:

```text
public.atom_v9_sim_entries
```

No separate quote table, mutable position table, or simulator current-state table is authorized.

### 10.1 Exact table column order

1. `entry_id text PRIMARY KEY`
2. `entry_hash text UNIQUE NOT NULL`
3. `contract_version text NOT NULL`
4. `canonicalization_version text NOT NULL`
5. `simulator_version text NOT NULL`
6. `symbol text NOT NULL`
7. `horizon text NOT NULL`
8. `horizon_seconds integer NOT NULL`
9. `intent_id text UNIQUE NOT NULL`
10. `publication_at timestamptz NOT NULL`
11. `entry_deadline_at timestamptz NOT NULL`
12. `decision text NOT NULL`
13. `intent_status text NOT NULL`
14. `entry_status text NOT NULL`
15. `quantity_shares integer NOT NULL`
16. `blocking_entry_id text NULL`
17. `quote_id text NULL`
18. `quote_hash text NULL`
19. `quote_source_spec text NULL`
20. `quote_event_ns bigint NULL`
21. `quote_accepted_at timestamptz NULL`
22. `entry_price double precision NULL`
23. `record_json jsonb NOT NULL`
24. `created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP`

`created_at` is operational metadata and is excluded from the mathematical entry hash.

### 10.2 Table constraints

The migration must enforce:

- exact entry-ID and lowercase hash formats;
- exact contract/canonicalization/simulator constants;
- exact symbol and horizon/seconds pairs;
- `entry_deadline_at = publication_at + interval '2 seconds'`;
- exact decision, intent-status, and entry-status domains;
- quantity/status consistency;
- all-or-none quote relational columns for `ENTERED`;
- null quote relational columns for every skipped status;
- nonnull `blocking_entry_id` only for `SKIPPED_POSITION_OPEN`;
- positive finite entry price only for `ENTERED`;
- JSON-object payload;
- one entry result per `intent_id`; and
- no foreign key to production or simulator tables.

Create exactly one non-unique lookup index:

```text
atom_v9_sim_entries_lookup_idx
```

on:

```text
(symbol, horizon, entry_status, publication_at, entry_id)
```

### 10.3 Security and immutability

Reuse the existing `atom_v9_sim_runtime` role. SIM-4 does not create or alter a role and contains no password.

Grant that role only:

- `SELECT` and `INSERT` on `public.atom_v9_sim_entries`; and
- the existing explicitly frozen access to simulator intents.

Grant no production-table privilege and no `UPDATE`, `DELETE`, `TRUNCATE`, ownership, schema mutation, sequence privilege, inheritance, or RLS bypass.

Enable and FORCE RLS. Create exactly one runtime SELECT policy and one runtime INSERT policy. Reuse the existing append-only simulator mutation-rejection function and add row-level UPDATE/DELETE and statement-level TRUNCATE rejection triggers.

Revoke entry-table access from `PUBLIC`, `anon`, `authenticated`, `service_role`, and `atom_v9_v4_runtime`.

### 10.4 Store behavior

SIM-4 defines `SimulationEntryStore` using an explicit no-argument simulator connection factory. It reads no environment variable and has no privileged fallback.

The store verifies `current_user = atom_v9_sim_runtime` before table access.

Successful insert results are exactly:

```text
INSERTED
IDEMPOTENT
```

One terminal result per intent is enforced. Identical content is idempotent. Different content reusing an intent ID, entry ID, or entry hash raises a frozen entry-conflict error. Malformed or relationally inconsistent stored content raises a frozen invalid-row error.

Every success commits. Every conflict/failure rolls back. Connections and cursors close on all paths.

An entry becomes an open simulated position only after its `ENTERED` record commits successfully. A candidate quote or in-memory reservation is not an open position.

## 11. Runtime ownership and handoff

SIM-4 uses exactly one daemon `SimulationEntryWorker`. It alone owns:

- the bounded SIM-4 event queue;
- the bounded two-second executable-quote buffer;
- pending intents;
- deadline expiry;
- restart-gap classification;
- same-horizon ordering;
- collision transactions; and
- entry-record persistence.

### 11.1 Composition root

`quant/web.py` remains the sole composition/lifecycle root. It may construct SIM-4 only from the existing explicit simulator connection factory and injected UTC clock.

Startup order is:

1. construct and start the SIM-4 worker;
2. inject its nonblocking persisted-intent adapter into SIM-3;
3. inject its nonblocking accepted-quote adapter into `LiveMarketState`; and
4. start SIM-3 under its existing freeze.

If SIM-4 construction/startup fails, production and SIM-3 continue without SIM-4. No request retries startup. Shutdown stops new quote intake, stops SIM-3 intent submission, then calls SIM-4 `stop()` once. SIM-4 total join time is bounded to one second and cannot prevent production shutdown.

### 11.2 Persisted-intent owner

`SimulationCaptureAdapter` may call the SIM-4 intent adapter only after `SimulationIntentStore.insert()` returns exactly `INSERTED` or `IDEMPOTENT`. It passes the exact immutable `SimulationTradeIntent`; it performs no entry calculation, quote lookup, collision check, or entry persistence.

Callback failure, worker absence, queue full, or ordinary exception does not change the successful SIM-2 intent persistence result and does not retry production work.

### 11.3 Accepted-quote owner

`LiveMarketState._accept_quote_serialized()` is the only production quote hook. After the quote has passed existing validation and the immutable `LivePublication` has committed, it may make one nonblocking SIM-4 quote submission containing the exact accepted COIN SIP fields, exact provider-event nanoseconds, and one injected UTC `accepted_at` clock read.

The hook performs no intent lookup, selection, collision check, timer work, database work, serialization, or persistence. Existing callers that do not provide the exact supported source identity/provider nanoseconds remain unchanged and produce no SIM-4 quote event.

The hook must not extend the COIN ingress critical section beyond bounded immutable construction and `put_nowait`. Deterministic warmed submit p99 must be no greater than 1 ms.

### 11.4 Queue behavior

The single event queue has capacity 256. Intent and quote submissions are nonblocking. On overflow, the incoming event is dropped; no older event is evicted and no synthetic entry record is created. Telemetry is bounded and operational only.

The quote buffer holds at most 256 exact quote objects and evicts only quotes that cannot satisfy any current or future two-second pending window. Quote-buffer overflow drops the incoming quote and cannot affect production.

SIM-4 does not read historical market tables or production evidence to repair a dropped quote.

## 12. Failure isolation

SIM-4 failure, delay, queue overflow, clock failure, database failure, malformed intent, malformed quote, collision, restart, or shutdown must not affect:

- market-data ingestion;
- Q1–Q12;
- V1–V4;
- Final Numbers;
- V4 forecast/outcome persistence;
- SIM-1/SIM-2 intent persistence;
- SIM-3 capture; or
- website availability.

No SIM-4 operation runs under a broker credential, production database role, web request, COIN/ BTC provider network call, V9 mathematical function, or production evidence transaction.

## 13. Exact authorized SIM-4 files

After SIM-3A merges, SIM-4 may change exactly these six files and no others:

1. create `migrations/027_create_v9_sim_entries.sql`;
2. create `quant/v9_sim4_entry.py`;
3. create `tests/test_v9_sim4_entry.py`;
4. minimally modify `quant/v9_sim3_capture.py` only for the post-success nonblocking persisted-intent callback;
5. minimally modify `quant/live_market.py` only to preserve the exact Alpaca provider nanosecond identity and perform the post-publication nonblocking accepted-quote callback; and
6. minimally modify `quant/web.py` only for SIM-4 construction, dependency injection, startup, and shutdown.

No SIM-1/SIM-2 contract/store modification is authorized. No V1–V4, quant-family, evidence, historical-replay, website-route, Render, requirements, broker, or unrelated test/documentation file is authorized.

## 14. Required SIM-4 tests

SIM-4 implementation must test at minimum:

### Contract and canonical identity

- exact quote field order and entry field order;
- frozen/slotted/deeply immutable values;
- exact constants and identity prefixes;
- exact V4A canonicalization reuse;
- deterministic quote and entry hashes;
- hash sensitivity for every included field;
- exclusion of ID/hash fields;
- timezone-equivalent canonicalization;
- binary64 golden vectors and negative-zero normalization;
- nested quote tamper detection;
- missing/unknown field rejection; and
- NaN, infinity, Boolean numerics, naive datetimes, and invalid provider nanoseconds rejection.

### Publication and window

- `publication_at` equals exact intent `eligible_at`;
- database `created_at`, cutoff time, and worker time cannot replace publication;
- deadline is exactly two seconds;
- provider event equal to publication is rejected;
- first provider event one nanosecond after publication is eligible;
- quote exactly at the inclusive upper boundary is eligible;
- quote one nanosecond/one microsecond beyond an applicable upper boundary is rejected;
- accepted-at before publication or after deadline is rejected;
- provider event after accepted-at is rejected;
- buffered post-publication quote may satisfy an intent delivered later inside the window;
- pre-publication buffered quote cannot satisfy it;
- first-quote ordering is deterministic; and
- no interpolation, midpoint entry, backdating, or stale reuse.

### Direction and executable price

- `LONG` uses ask and requires ask size at least one;
- `SHORT` uses bid and requires bid size at least one;
- invalid or undersized quotes are ignored until expiry;
- one-share quantity only; and
- no confidence or accuracy multiplier.

### Statuses

- exact six-status domain;
- immediate `SKIPPED_NO_TRADE` mapping;
- immediate `SKIPPED_UNAVAILABLE` mapping;
- successful `ENTERED` mapping;
- no quote by deadline produces `SKIPPED_WINDOW_EXPIRED`;
- open horizon produces `SKIPPED_POSITION_OPEN` with exact blocker ID;
- recent pre-start actionable intent produces `SKIPPED_RESTART_GAP`;
- skipped statuses carry no quote/price and zero quantity; and
- there is no persisted pending status.

### Collision and restart

- six horizons are independent;
- two concurrent same-horizon candidates cannot both enter;
- deterministic same-horizon intent ordering;
- atomic advisory-lock collision decision;
- open occupancy starts only after committed `ENTERED`;
- durable open occupancy survives restart;
- SIM-4 phase treats every `ENTERED` as open until SIM-5;
- recent unmatched recovery is bounded to two seconds;
- older intents are not backfilled;
- no pre-restart quote is reconstructed; and
- restart does not create a retroactive entry.

### Database and store

- migration ordinal/file exactness;
- exact table and column order;
- exact constraints and one lookup index;
- existing role required and not altered;
- exact grants/revocations;
- ENABLE/FORCE RLS and exact policies;
- UPDATE/DELETE/TRUNCATE rejection;
- no foreign key and no production privilege;
- current-user enforcement;
- canonical JSON/relational equality;
- inserted, idempotent, conflict, and invalid-row paths;
- concurrent identical insertion;
- commit/rollback/closure on all paths; and
- no environment credential lookup or fallback.

### Runtime and isolation

- exact startup/shutdown ownership and order;
- post-success SIM-3 callback only;
- post-publication accepted-quote hook only;
- exact provider nanosecond preservation;
- nonblocking queue submissions and capacities;
- incoming-event drop with no eviction or synthetic record;
- bounded quote-buffer behavior;
- worker single ownership and double-start/stop idempotency;
- one-second total shutdown join bound;
- p99 quote and intent submit no greater than 1 ms;
- no request-path work;
- no historical scan;
- no broker capability;
- production and SIM-3 failure isolation;
- no SIM-5/SIM-6 behavior;
- full existing suite remains green; and
- final diff contains only the six authorized SIM-4 files.

## 15. Hard phase boundary

SIM-3A is documentation only. It creates no Python, test, migration, database, Render, runtime, web, broker, or simulator behavior.

After SIM-3A is merged, only SIM-4 becomes authorized. SIM-4 ends after immutable terminal entry-record persistence and durable one-open-horizon enforcement. It does not authorize exit selection, return/P&L, successful resolution, unresolved lifecycle, compact simulator state, a simulation page, broker integration, or live order submission.
