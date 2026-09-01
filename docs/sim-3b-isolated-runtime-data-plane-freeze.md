# ATOM TRUE V9 — SIM-3B Isolated SIM-4 Runtime and Data-Plane Freeze

**Status:** LAW after merge  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only  
**Amends:** `SIMULATION_FREEZE.md` and `docs/sim-3a-exact-sim4-entry-freeze.md`  
**Supersedes:** unmerged PRs #227 and #228

This freeze authorizes SIM-4 only after moving the simulator onto its own
Supabase project and its own Render background worker. It carries forward the
resolved SIM-3A review fences included in this PR and closes the remaining
review findings from PRs #227 and #228. Where this document conflicts with an
earlier simulator document, this document controls only for database placement,
database credential and role authority, runtime placement, durable intent
handoff, quote sourcing, clock ordering, data-provider credential authority,
activation, recovery, and the SIM-4 implementation-file boundary. Every other
merged simulator rule remains unchanged. In particular, Section 4 below
expressly supersedes the single-role reuse rule in merged SIM-3A Section 10.3.

No Python, SQL, database, Render, Supabase, market-data, or runtime change is
made by this documentation PR.

## 1. Invariants that do not change

The simulator remains downstream-only and paper-only.

- Simulator identity remains `ATOM_TRUE_V9_SIM_1`.
- Instrument remains exactly one `COIN` share.
- Horizons remain exactly, and in this order, `30S`, `1M`, `5M`, `15M`,
  `30M`, and `1H` with seconds `30`, `60`, `300`, `900`, `1800`, and `3600`.
- Direction still comes only from the frozen V9 final-bps contract. No
  confidence, accuracy, family, V4B, V4C, or V4D multiplier is added.
- At most one open position may exist per horizon, for at most six open
  positions total.
- Intent, entry, and future trade history is append-only and logically
  unlimited over time. No daily cap, row cap, truncation, replacement,
  rotation, TTL, or oldest-row eviction is authorized for durable evidence.
- SIM-4 retains the exact entry window, executable-side price and size rules,
  quote identity, hashes, collision rules, terminal statuses, and one-row-per-
  intent contract frozen by merged PR #223 except where a timing or runtime
  fence is made more exact below.
- The simulator receives no production truth credit and cannot change V9,
  Q1-Q12, forecasts, outcomes, evidence, confidence, accuracy, UI, broker
  state, account state, positions, or orders.
- SIM-5 and SIM-6 remain unauthorized.

SIM-4 still leaves every successful `ENTERED` position open until SIM-5.
Therefore SIM-4 alone can create at most six successful open entries. Repeated
completed trades require a later, separately frozen and reviewed SIM-5.

## 2. Mandatory two-platform isolation

### 2.1 Dedicated Supabase project

All new simulator intents, publications, entries, and later simulator evidence
must live in one Supabase project created only for the simulator. It must not be
the ATOM production project, the benchmark project, or any other existing
project.

The production application may reach this project only through:

```text
ATOM_V9_SIM_DATABASE_URL
ATOM_V9_SIM_PROJECT_REF
```

The SIM-4 worker may reach the same isolated project only through:

```text
ATOM_V9_SIM4_DATABASE_URL
ATOM_V9_SIM_PROJECT_REF
```

The two database URLs must authenticate as the two different exact roles in
Section 4. They may share the isolated project ref, but they must not be the
same credential or connection string.

There is no fallback to `DATABASE_URL`, a V4 URL, a service-role URL, or any
other credential. The configured project ref must match the simulator DSN and
must differ from every project ref discoverable from `DATABASE_URL`. Missing,
unparseable, mismatched, or equal project identity disables simulator capture
without affecting production.

Allowed simulator PostgreSQL endpoints are exactly:

- the Supabase direct endpoint `db.<project-ref>.supabase.co` on port `5432`;
  or
- a Supabase session-pooler endpoint ending in `.pooler.supabase.com` on port
  `5432`, with the same project ref in the PostgreSQL username.

TLS is mandatory with `sslmode=require` or stronger. Port `6543`, transaction
pooling, an endpoint that can change the PostgreSQL backend during a session,
and any non-Supabase database host fail closed. The SIM-4 worker verifies that
its ownership connection keeps one stable `pg_backend_pid()` for the entire
owned generation.

The simulator database exposes no foreign data wrapper, database link, foreign
key, view, function, or privilege into a production database. Production roles
and tables must be absent.

### 2.2 Dedicated Render background worker

SIM-4 runs only as one dedicated Render Background Worker with the start
command:

```text
python -m quant.v9_sim4_worker
```

It performs runtime work only when `ATOM_V9_SIM4_ENABLED` equals the lowercase
string `true`; missing or any other value is disabled and fail closed.

`quant/web.py` no longer constructs, starts, stops, retries, or owns SIM-4.
Its only new SIM-4 authorization is fail-closed simulator DSN/project
validation for the existing SIM-3 publisher. SIM-3 remains a bounded,
nonblocking production-side publisher of immutable intents only.

The SIM worker service must not receive `DATABASE_URL`,
`ATOM_V9_SIM_DATABASE_URL`, production Supabase credentials, a service-role
key, the simulator publisher credential, V9 writer credentials, broker base
URLs, account endpoints, order endpoints, or production web secrets. It
receives only its entry-worker database credential, simulator project ref, and
the cryptographically restricted data-only credential required by Section 5.

Render may run a rolling replacement, but only the generation holding the
database ownership fence in Section 7 is active. Adding Render instances does
not create parallel SIM-4 decision authority.

Production remains healthy and continues serving requests when the simulator
project or worker is absent, slow, full, disconnected, restarting, or failed.
No production request waits for SIM-4.

## 3. Exact cross-platform data flow

The only V9-to-simulator payload is the already-frozen immutable
`SimulationTradeIntent` persisted by SIM-3. The production process performs no
SIM-4 selection, quote buffering, collision decision, entry insert, recovery,
or trade calculation.

SIM-4 consumes durable intent rows from the simulator project. There is no
process-local intent callback between `quant.web` and SIM-4. There is no V9
quote callback, quote relay, simulator HTTP route, PostgreSQL quote-ingress
table, or raw-quote copy through production. The dedicated worker obtains its
own read-only SIP quote stream under Section 5.

This boundary keeps simulator entry and future trade volume off production
Render compute and off the production Supabase project. Production performs
only the already-authorized nonblocking SIM-3 intent publication.

## 4. Simulator-only database bootstrap and cutover

Migration `027_create_v9_sim_entries.sql` is the standalone bootstrap for the
new simulator project. It must refuse to run when any frozen production V9,
forecast, outcome, evidence, or state table is present. It must not reference,
grant to, revoke from, or depend on a production role or table.

The migration creates and secures only simulator objects, including:

```text
public.atom_v9_sim_installation
public.atom_v9_sim_intents
public.atom_v9_sim_intent_publications
public.atom_v9_sim_entries
atom_v9_sim_runtime
atom_v9_sim_entry_runtime
```

`atom_v9_sim_installation` contains one immutable installation identity and the
expected Supabase project ref. Runtime startup verifies both before reading or
writing evidence.

The two non-inheriting login roles are deliberately asymmetric:

- `atom_v9_sim_runtime` is the SIM-3 publisher role required by the frozen
  SIM-2 store. It may `SELECT` and `INSERT` simulator intents and read the
  installation identity. It cannot insert or mutate publications or entries.
- `atom_v9_sim_entry_runtime` is the SIM-4 worker role. It may `SELECT` the
  installation identity, intents, publications, and entries and may `INSERT`
  entries. It cannot insert or mutate intents or publications.

The existing SIM-2 publisher store continues to require
`current_user = atom_v9_sim_runtime`. The new SIM-4 entry store requires
`current_user = atom_v9_sim_entry_runtime`; it never accepts the publisher role
or falls back to it.

The publication sidecar is inserted only by the narrowly scoped
`SECURITY DEFINER` trigger owned by the migration owner in the same transaction
as a newly inserted intent. Its function is schema-qualified, fixes
`search_path` to `pg_catalog`, and is not executable by either login role or
public API roles. No login runtime role owns a simulator object or belongs to
the other runtime role.

All evidence tables retain forced RLS and mutation-rejection triggers. No
runtime role receives `UPDATE`, `DELETE`, `TRUNCATE`, ownership, schema
mutation, RLS bypass, production-table, service-role, or cross-data-plane
privilege.

The current simulator intents in the ATOM production project remain immutable
there. They are not copied, deleted, rewritten, assigned entries, or used as a
SIM-4 recovery source. Cutover changes only future SIM-3 writes to the new
project. Because no SIM-4 entry table exists in the old project, this loses no
completed simulator trade history.

Activation order is exact:

1. create the new simulator Supabase project;
2. apply and verify migration 027 there;
3. deploy the SIM worker with `ATOM_V9_SIM4_ENABLED=false`,
   `ATOM_V9_SIM4_DATABASE_URL`, and its isolated environment;
4. change production `ATOM_V9_SIM_DATABASE_URL` and
   `ATOM_V9_SIM_PROJECT_REF` to the new project;
5. verify new immutable intents arrive in the new project; and
6. set `ATOM_V9_SIM4_ENABLED=true` on the SIM worker only.

Rollback disables the SIM worker and restores only the simulator publisher
environment if necessary. It never deletes evidence in either project.

## 5. Exact independent executable-quote source

The dedicated worker opens exactly:

```text
SIM4_QUOTE_SOURCE_SPEC = ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1
wss://stream.data.alpaca.markets/v2/sip
```

It authenticates with a dedicated Alpaca Broker API client-credentials token
whose server-side custom Access Controls are frozen to `Data = Read only` and
every other scope, including `Accounts` and `Trading`, equal to `No Access`.
The worker obtains the short-lived bearer token only from
`https://authx.alpaca.markets/v1/oauth2/token`, uses it only to authenticate
this exact websocket, and subscribes only to the `quotes` channel for `COIN`.
It never receives a standard Alpaca Trading API key pair, legacy Broker key,
Alpaca Connect user token, or any credential capable of reading or mutating an
account, position, or order. A quote is classifiable as the frozen Alpaca SIP
source only after the socket returns successful authentication and successful
COIN quote subscription for this exact URL.

The restricted Broker credential and its SIP entitlement are deployment
prerequisites, not optional hardening. Provisioning records must establish the
exact server-side scope assignment without exposing a secret. If those scopes
cannot be created or the scoped credential lacks live SIP entitlement, SIM-4
remains disabled. A broad Trading API key must never be substituted to make
activation succeed.

For the literal credential prohibition in `SIMULATION_FREEZE.md`, this
document authorizes only that Data-read-only, all-other-scopes-No-Access
credential as a market-data entitlement. It authorizes no Broker API call and
conveys no broker, account, position, or order authority. `BROKER_AUTHORITY =
NONE` and `ORDER_SUBMISSION = IMPOSSIBLE` remain unchanged.

The worker may use no Alpaca trading or account host, no paper or live order
endpoint, no positions endpoint, no order/trading SDK call, and no REST latest-
quote fallback. It may not relabel IEX, delayed SIP, BOATS, overnight, cached,
replayed, or default-feed data as SIP.

Authentication, entitlement, subscription, schema, timestamp, symbol, size,
or socket failure admits no quote. The worker logs a secret-free fail-closed
state and reconnects in the background with bounded backoff. During a gap,
affected intents expire or receive the already-frozen restart classification;
quotes are never reconstructed or backfilled.

The websocket quote's provider timestamp is preserved at nanosecond precision.
Bid, ask, bid size, ask size, symbol, provider timestamp, accepted timestamp,
source identity, and quote hash retain the merged PR #223 contract.

## 6. Monotonic accepted time and deterministic quote ordering

Each owned runtime generation reads one UTC anchor and one monotonic-nanosecond
anchor after ownership acquisition:

```text
accepted_at = anchor_utc + (monotonic_now_ns - anchor_monotonic_ns)
```

The subtraction is exact nanoseconds. For the frozen Python `datetime`, hash,
and PostgreSQL `timestamptz` representation, each derived instant is
independently rounded upward to the first representable UTC microsecond:

```text
elapsed_ns = monotonic_now_ns - anchor_monotonic_ns
accepted_at_epoch_us = anchor_utc_epoch_us + ((elapsed_ns + 999) // 1000)
```

This conservative quantization never timestamps a quote earlier than its
derived causal instant, adds less than one microsecond, and never accumulates
skew across quotes. If the rounded microsecond reaches beyond an intent
deadline, that quote is ineligible for that intent; time is never rounded
backward to admit it. Equal representable accepted timestamps are allowed and
are resolved only by the complete frozen selection tuple after the deadline
fence below.

The conversion uses only checked integer arithmetic. Binary floating-point
division, `datetime.timestamp()`, and a float epoch are forbidden.

This monotonic-derived UTC clock is used for quote acceptance and worker
deadline scheduling. A backward wall-clock adjustment cannot move accepted
time backward or admit a quote retroactively. Restart creates a new anchor and
is handled by the frozen restart rules; anchors are never joined across
generations.

Provider parsing and source/value validation may occur before the narrow
admission mutex, but the quote's `monotonic_now_ns` read, derived-time
calculation, microsecond quantization, sequence allocation, and successful
`put_nowait` occur together while holding that mutex, in that order. Every
successfully admitted quote receives one positive, monotonically increasing,
runtime-only admission sequence. A failed or full admission consumes no
sequence. Admission sequence is not hashed or persisted and does not replace
the frozen selection order:

```text
(accepted_at, provider_event_ns, quote_id)
```

No actionable intent may terminalize before its inclusive deadline, even when
an executable candidate is already buffered. The worker's strict-greater
deadline observation acquires the same admission mutex, reads
`monotonic_now_ns` only after acquisition, compares the derived nanosecond
instant with the exact deadline, and snapshots the last admitted sequence
before releasing the mutex. It then drains every admitted quote through that
fixed sequence, filters the full eligible candidate set, and sorts that set by
the complete tuple above before choosing the first quote. A quote producer
cannot sample a pre-deadline time, stall outside the mutex, and enqueue after
the watermark. Later admissions cannot affect that intent. Equal
`accepted_at` values are therefore resolved by provider event nanoseconds and
quote ID before any terminal decision, never by queue arrival order.

Equality remains pending and schedules a bounded recheck. Failure to complete
the bounded drain cannot choose a partial winner; it produces no terminal
decision until the complete fixed set is drained or a frozen restart/failure
rule applies.

Quote buffering remains finite and time-bounded for process safety. A bounded
runtime queue is not a durable-history cap. Overflow is fail closed, never
evicts an older admitted quote to make room, and cannot affect production.

## 7. Exact runtime ownership and gap-free activation

Freeze:

```text
SIM4_OWNER_NAMESPACE = ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1
SIM4_OWNER_PAYLOAD = b"ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1\x00COIN"
SIM4_OWNER_SHA256_FIRST_8 = 2766c300cde1d025
SIM4_OWNER_LOCK_KEY = 2839171023325220901

SIM4_ACTIVATION_NAMESPACE = ATOM_TRUE_V9_SIM4_INTENT_HANDOFF_FENCE_1
SIM4_ACTIVATION_PAYLOAD = b"ATOM_TRUE_V9_SIM4_INTENT_HANDOFF_FENCE_1\x00COIN"
SIM4_ACTIVATION_SHA256_FIRST_8 = 10148bea579e6cde
SIM4_ACTIVATION_LOCK_KEY = 1158704842749668574

SIM4_DEADLINE_LOCK_TIMEOUT_MS = 5000
```

The worker obtains `SIM4_OWNER_LOCK_KEY` with
`pg_try_advisory_lock(bigint)` on one dedicated direct/session-mode connection.
It may not recover, accept quotes, inspect pending state, or persist a terminal
entry until it owns that lock. The same backend session remains open and owns
all SIM-4 terminal transactions. Loss or change of the backend PID disables
the generation before another terminal write.

Every SIM-3 intent-insert transaction takes
`pg_advisory_xact_lock_shared(SIM4_ACTIVATION_LOCK_KEY)` before inserting. A
replacement worker performs activation only after it has owner authority and a
successfully authenticated SIP subscription that is already buffering valid
quotes. It then begins a short transaction and calls exactly:

```sql
SELECT pg_try_advisory_xact_lock(1158704842749668574::bigint)
```

On `false`, it rolls back, keeps buffering SIP quotes, and retries only in the
background. On `true`, it reads one `runtime_started_at`, snapshots the maximum
committed publication sequence, loads durable open occupancy, and commits.
Quote intake stays active throughout this database fence.

The snapshot defines the closed recovery set. Publisher transactions whose
INSERT path acquired or queued the shared lock ahead of the exclusive request
have completed before the snapshot. A transaction may have begun earlier but
not yet reached its INSERT/shared-lock request; it is deliberately classified
after the exclusive fence and is found by continuous reconciliation. No
interval exists in which an intent can commit but belong to neither recovery
nor active intake.

The activation snapshot is not sufficient by itself to authorize same-horizon
terminal order. Before the worker terminalizes any ordinarily pending
actionable intent through its deadline `D`, the admission fence in Section 6
must already be fixed and the authoritative database session must queue one
deadline-publication closure. The late-publication and restart paths in
Section 8 cannot create this closure or inspect its quote set.
It begins a short transaction, sets a frozen bounded lock timeout, and calls:

```sql
SET LOCAL lock_timeout = '5000ms';
SELECT pg_advisory_xact_lock(1158704842749668574::bigint)
```

This deadline call is blocking only on the database owner thread; SIP quote
intake remains active and bounded. Once the exclusive request is queued, later
shared publisher requests cannot pass it. Every shared request queued or
granted ahead of it finishes before the exclusive lock is granted; a
transaction that merely began earlier but requests the shared lock later is on
the post-fence side. The worker then snapshots the maximum committed
publication sequence and commits immediately.
Lock timeout, connection loss, or ambiguity rolls back and permanently
deactivates that generation; it never retries in a way that could widen the
closed deadline set.

Before any terminal decision at `D`, the worker reconciles every publication
through that deadline sequence and proves that each same-horizon semantic
predecessor with deadline at or before `D` is already terminal or is included
in the complete candidate batch. That batch is ordered by
`(publication_at, canonical_horizon_order, intent_id)` before the per-horizon
transaction. An intent released after the deadline closure with its own
deadline at or before `D` is late and can never enter or retroactively outrank
the closed batch. It receives the late-publication rule in Section 8.

Thus an actionable entry is deliberately persisted after its two-second
window closes, while its price remains the first frozen executable quote
inside that exact window. Delayed persistence changes no quote mathematics and
prevents a later-discovered smaller semantic key from losing to an already
terminalized larger key.

A nonowner keeps no decision authority and retries ownership only in the
background. Shutdown stops quote intake, stops intent reconciliation, completes
the bounded worker drain, unlocks on the same session when possible, and closes
the session. Connection close also releases ownership. A successor performs no
recovery until it owns the same lock.

The per-horizon transaction advisory locks carried forward from the SIM-3A
amendments remain mandatory and separate from the global owner and activation
fences.

## 8. Durable intent discovery and publication precedence

`atom_v9_sim_intent_publications` is append-only and contains exactly one
durable publication record per intent in the isolated project. It is created in
the same transaction as the intent. Its positive database publication sequence
is used only to define closed-set membership and restart checkpoints; it is not
terminal-decision precedence.

The fresh isolated project activates only when every intent has exactly one
publication row and no nullable or orphan discovery state exists. Startup fails
closed if that invariant is false. An idempotent insert of an existing intent
preserves and reuses the existing database publication identity while the
frozen store API still returns only `IDEMPOTENT`; it cannot create a
null-discovery legacy row. Conflicting identity or hash data rolls back.

No migration or runtime may silently adopt legacy null admission state. If
evidence is ever imported in a separately authorized future operation, the
import must create the intent and its nonnull publication record atomically
before activation. The old production-project intents are not imported by this
phase.

For every closed recovery or reconciliation set, the worker queries bounded
pages of at most 16 rows using semantic keyset order exactly:

```text
(publication_at, canonical_horizon_order, intent_id)
```

with publication sequence appended only as a unique final cursor tie-breaker.
The closed publication-sequence predicate still defines membership, but
publication sequence never reverses semantic order. Page boundaries never
alter this order. A page is terminalized before the next semantic page is read;
the worker does not stage the whole closed interval in memory and does not
terminalize a later page while an earlier row remains incomplete.

An ordinary pending intent must be discovered no later than its inclusive
deadline. If an intent is first discovered strictly after its own deadline and
the worker did not already capture that intent's ordinary admission and
deadline-publication fences, it is late. It may not create a new closure,
inspect retained quotes, or enter retroactively. This rule applies even when no
other intent was known and no prior closure exists for that exact deadline.

An already-known ordinary pending intent is also late when its publication
sequence falls after the first closed deadline-publication set captured for
its own deadline. After existing-terminal, durable-open-position, and frozen
restart-gap precedence, either late case fails closed to
`SKIPPED_WINDOW_EXPIRED`. Only an intent discovered by its deadline and
included no later than its own closed deadline set may use the quote-admission
fence captured for that deadline.

The frozen same-horizon order applies globally to timely intents, not merely
inside whichever recovery or reconciliation page happened to reveal them. A
late publication is outside that pending candidate domain by causal rule; its
older `publication_at` cannot reverse a terminal decision made from the
complete timely closed set.

These rules close late reconciliation, inverted database admission order,
page-boundary ordering, and idempotent legacy-discovery races without changing
entry mathematics.

## 9. Capacity and history law

There is no application row ceiling on simulator intents, entries, or future
resolved trades. Queries and reconciliation use bounded pages and durable
keysets until exhaustion; they do not use a total-row cap. The service may be
resized vertically and the Supabase project may be upgraded without a freeze
change because those changes do not alter mathematical or evidence semantics.

In-memory queues, websocket buffers, query pages, retry intervals, and graceful
shutdown waits remain finite to prevent memory exhaustion and to preserve
production isolation. They are operational bounds, not limits on the number of
trades or evidence rows stored over time.

No drop, disconnect, restart, overflow, slow query, or capacity event creates a
synthetic quote or trade. Every fail-closed event is observable through
secret-free counters and logs.

## 10. Exact SIM-4 implementation boundary

After this documentation PR merges and passes final review, SIM-4 implementation
may change only:

1. `migrations/027_create_v9_sim_entries.sql`;
2. `quant/v9_sim4_entry.py`;
3. `quant/v9_sim4_worker.py`;
4. minimal simulator-project validation in `quant/web.py`;
5. `tests/test_v9_sim4_entry.py`; and
6. `tests/test_v9_sim4_isolation.py`.

`requirements.txt` already contains the authorized websocket dependency. No
`render.yaml` is required; the dedicated worker is created explicitly on
Render after the implementation merges.

SIM-4 may not change `quant/live_market.py`, V9 mathematics, V4 persistence,
production evidence, production database schema, broker code, web routes,
request handlers, SIM-5, or SIM-6. Existing SIM-3 code remains unchanged except
for its external simulator DSN at deployment.

## 11. Required implementation tests

The SIM-4 implementation must prove at minimum:

### Isolation and bootstrap

- production and simulator project refs cannot match;
- no DSN fallback and no non-Supabase host;
- direct/session port 5432 accepted and transaction-pooler port 6543 rejected;
- TLS is mandatory;
- stable ownership backend PID;
- simulator migration refuses a production schema;
- publisher and entry-worker DSNs authenticate as their exact different roles;
- publisher can insert intents but cannot insert entries or publications;
- entry worker can read intents/publications and insert entries but cannot
  insert intents or publications;
- neither runtime role has production, mutation, ownership, membership in the
  other role, or RLS-bypass privilege;
- old production intents are not scanned or copied; and
- simulator failure does not block production startup or requests.

### Quote source and authority

- exact SIP websocket URL and COIN-only quote subscription;
- successful auth and subscription are required before admission;
- Broker custom scope evidence is exactly Data-read-only with every other
  scope No-Access before activation;
- a standard Trading API key, legacy Broker key, Alpaca Connect user token, or
  missing/unverifiable scope evidence keeps SIM-4 disabled;
- bearer tokens come only from the exact AuthX token endpoint and are used only
  on the exact SIP websocket;
- IEX, delayed, default, REST fallback, malformed, wrong-symbol, and
  non-entitled streams admit no quote;
- no trading, account, position, or order host/call exists; and
- secrets never appear in logs or persisted records.

### Timing and ordering

- monotonic-derived accepted UTC never moves backward when wall UTC moves
  backward;
- accepted time independently rounds upward to UTC microseconds with less than
  one microsecond of nonaccumulating conservative skew;
- quote time sampling, sequence allocation, and successful queue admission are
  one mutex-serialized operation;
- deadline time sampling and watermark capture use that same mutex, so a
  pre-deadline sample cannot enqueue after the fence;
- equal accepted timestamps are fully drained and sorted by provider
  nanoseconds and quote ID before selection;
- reverse arrival order with equal accepted time selects lower provider
  nanoseconds, then lower quote ID when provider nanoseconds also tie;
- quantization uses checked integer arithmetic and round-trips exactly through
  the Python hash and PostgreSQL `timestamptz` value;
- no actionable intent terminalizes before its inclusive deadline;
- a post-deadline instant rejects rather than rounding backward into the
  window;
- provider nanoseconds and the frozen quote-selection tuple are preserved;
- equality is inclusive and strictly-greater deadline creates one admission
  fence;
- pre-fence quotes drain and post-fence quotes cannot enter retroactively;
- a late-reconciled intent never inspects retained quotes;
- an intent first discovered after its deadline cannot create its first
  closure even when no intent was known at that deadline;
- the queued exclusive deadline closure prevents later shared publishers from
  passing, snapshots one complete timely set, and never widens on timeout;
- a later-committed smaller semantic key is classified late and cannot reverse
  a completed timely batch;
- recovery and later reconciliation cannot split same-horizon precedence;
- each semantic 16-row page is complete before that page's terminal selection;
- inverted publication-sequence values cannot reverse publication order; and
- page boundaries cannot change same-horizon precedence.

### Runtime and recovery

- missing or non-`true` `ATOM_V9_SIM4_ENABLED` performs no runtime work;
- golden owner and activation payloads, digests, keys, and SQL calls;
- exact 5,000-millisecond queued deadline-lock timeout and fail-closed
  generation deactivation on timeout;
- nonowner performs no recovery, quote admission, or terminal write;
- SIP intake is active before the exclusive activation snapshot;
- a concurrent publisher is classified on exactly one side of that snapshot;
- no recovery-to-intake gap under forced transaction interleavings;
- rolling replacement cannot classify predecessor-owned state;
- backend loss disables writes before ownership can move; and
- shutdown releases ownership and a successor recovers only afterward.

### Evidence, concurrency, and volume

- exactly one immutable publication and one terminal entry per intent;
- idempotent repeats preserve the same publication identity;
- conflicts fail closed;
- concurrent same-horizon entries produce at most one `ENTERED` row and the
  exact blocker identity for collisions;
- six independent horizons can be open simultaneously;
- append-only mutation and truncation attempts fail;
- bounded keyset iteration continues beyond 65,536 rows without a total cap;
- bounded runtime overflow is observable and never fabricates evidence; and
- the full existing test suite remains green.

## 12. Hard phase boundary

This freeze authorizes only isolated SIM-4 entry implementation and the two
explicit infrastructure resources required to run it: one simulator Supabase
project and one simulator Render background worker.

It does not authorize broker access, order submission, production-source
changes, SIM-5 resolution, P&L, compact simulator state, UI work, or SIM-6.
Any such work requires its own freeze and review after SIM-4 is merged and
verified.
