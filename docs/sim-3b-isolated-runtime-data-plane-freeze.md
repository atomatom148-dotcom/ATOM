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
  with database name `postgres` and PostgreSQL username exactly
  `atom_v9_sim_runtime` for the publisher DSN or
  `atom_v9_sim_entry_runtime` for the worker DSN; or
- a Supabase session-pooler endpoint ending in `.pooler.supabase.com` on port
  `5432`, with database name `postgres` and PostgreSQL username exactly
  `<role>.<project-ref>`, where `<role>` is the one exact role required for
  that DSN and `<project-ref>` is the same lowercase 20-character
  `[a-z0-9]{20}` value supplied by `ATOM_V9_SIM_PROJECT_REF`.

The session-pooler username contains exactly one period between the role and
project ref. A missing suffix, a different role, an additional suffix or
prefix, uppercase or punctuation in the project ref, or a project-ref value
obtained only from an untrusted query parameter fails closed.

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

Migration `027_create_v9_sim_entries.sql` is the one standalone bootstrap for
the new simulator project. Migration 010 is not replayed, edited, or assumed.
The bootstrap is one transaction and creates no object until every refusal
precondition below has passed.

### 4.1 Fresh-project refusal gate and installation identity

The operator must run bootstrap on one administrative PostgreSQL session in
one explicit transaction, with no migration-internal `COMMIT`:

```sql
BEGIN;
SET LOCAL atom_v9.sim_project_ref = '<ATOM_V9_SIM_PROJECT_REF>';
-- all migration 027 statements execute here on this same session
COMMIT;
```

The value must match lowercase `[a-z0-9]{20}` exactly. The migration reads it
with:

```sql
SELECT current_setting('atom_v9.sim_project_ref', true);
```

Missing, empty, malformed, or unavailable-on-that-same-session configuration
aborts the transaction atomically. The operator must use the exact `SET LOCAL`
procedure above; migration 027 must not begin, commit, or split a transaction
itself and must not persist the custom GUC.

The migration must also abort before creating anything when any of these is
true:

- schema `public` contains any pre-existing user relation of relkind ordinary
  table, partitioned table, view, materialized view, sequence, or foreign
  table, regardless of its name;
- any non-system schema name matches `atom\_%` with literal underscore;
- any foreign-data wrapper, foreign server, user mapping, or foreign table is
  installed;
- any of the roles `atom_v9_sim_owner`, `atom_v9_sim_runtime`, or
  `atom_v9_sim_entry_runtime` already exists;
- any target table, sequence, index, function, trigger, policy, or type named
  by this freeze already exists in any schema; or
- any production V9, forecast, outcome, evidence, state, benchmark, or archive
  object is discoverable.

An extension-owned object outside `public` is not adopted by the simulator,
but any extension that creates a foreign-data object still triggers refusal.
The migration never renames, drops, grants, revokes, or adopts a pre-existing
object to pass this gate.

After that refusal gate passes, migration 027 recreates
`public.atom_v9_sim_intents` with the exact column order, constraints, lookup
index, and role compatibility already merged in migration 010; it does not run
or import migration 010. It adds no nullable intent-admission column. The
unchanged `quant/v9_sim2_store.py` insert, conflict reread, and `current_user`
checks must operate against this fresh table without adaptation.

The migration creates exactly one installation row in:

```text
public.atom_v9_sim_installation
```

with this exact logical shape:

```text
installation_id  text PRIMARY KEY = 'ATOM_TRUE_V9_SIM_INSTALLATION_1'
project_ref      text UNIQUE NOT NULL
created_at       timestamptz NOT NULL DEFAULT transaction_timestamp()
```

`project_ref` must equal the validated transaction-local GUC. A check
constraint fixes the installation ID, and a statement-level trigger rejects a
second insert. Runtime startup proves equality among this row,
`ATOM_V9_SIM_PROJECT_REF`, and the project ref parsed from its own DSN before
reading or writing simulator evidence; the transaction-local install GUC is
not expected to exist at runtime.

### 4.2 Exact owners and login roles

The migration creates one operational owner:

```text
atom_v9_sim_owner NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB
                  NOCREATEROLE NOREPLICATION NOBYPASSRLS
```

Every simulator table, sequence, index, trigger, policy, and migration-created
function is owned by that NOLOGIN role after creation. It is not granted to
either login role and cannot be assumed with `SET ROLE`.

The two non-inheriting login roles are deliberately asymmetric:

- `atom_v9_sim_runtime` is the SIM-3 publisher role required by the frozen
  SIM-2 store. It may read installation and intent rows and insert intents. It
  has no direct privilege on publication, entry, checkpoint, or
  sequence objects.
- `atom_v9_sim_entry_runtime` is the SIM-4 worker role. It may read
  installation, intents, publications, entries, and checkpoint and
  insert entries. It cannot insert intents or directly insert publications or
  update the checkpoint.

The SIM-2 publisher store continues to require
`current_user = atom_v9_sim_runtime`. The SIM-4 entry store requires
`current_user = atom_v9_sim_entry_runtime`; it never accepts the publisher role
or falls back to it.

This role split expressly supersedes every carried SIM-3A grant of a SIM-4
fence, capture, reconciliation, or checkpoint function to
`atom_v9_sim_runtime`. Migration 027 creates none of the superseded operational
functions, revokes every migration-created operational-function `EXECUTE` from
the publisher, and grants only the fence-reader and compare-and-advance
functions named in Section 4.4 to `atom_v9_sim_entry_runtime`. The publisher
retains only its shared-lock trigger path; it cannot capture a fence, read the
publication sequence, or move reconciliation progress.

No login runtime role owns an object, inherits from another role, is a member
of another role, has schema `CREATE`, has sequence privilege, or receives
`UPDATE`, `DELETE`, `TRUNCATE`, ownership, RLS bypass, service-role, or
cross-data-plane privilege.

### 4.3 Exact publication sequence and sidecar

The migration creates:

```text
public.atom_v9_sim4_intent_admission_seq
public.atom_v9_sim_intent_publications
```

The sequence is `bigint`, starts at `1`, increments by `1`, has minimum `1`,
has no cycling, uses cache `1`, and is owned by `atom_v9_sim_owner`. Neither
login role receives `USAGE`, `SELECT`, or `UPDATE` on it.

The append-only sidecar has exactly these four columns, in this order:

```text
publication_seq bigint PRIMARY KEY
intent_id       text UNIQUE NOT NULL
publication_at  timestamptz NOT NULL
horizon_order   smallint NOT NULL
```

`intent_id` has a foreign key to
`public.atom_v9_sim_intents(intent_id) ON DELETE RESTRICT`. It enforces the
exact horizon mapping:

```text
30S -> 1
1M  -> 2
5M  -> 3
15M -> 4
30M -> 5
1H  -> 6
```

and `publication_seq > 0`. `publication_at` equals the referenced immutable
intent's `eligible_at`. These fields are operational sidecar data and are not
added to the intent hash or JSON.

Create exactly this additional semantic keyset index:

```text
atom_v9_sim_intent_publications_semantic_idx
    (publication_at, horizon_order, intent_id, publication_seq)
```

The primary-key index on `publication_seq` is the exact closed-sequence
membership access path. The semantic index is the exact ordered-keyset path.
Reconciliation may not use an unindexed sort, offset pagination, or an
unbounded scan.

Migration 027 creates these exact trigger functions and triggers:

```text
public.atom_v9_sim4_lock_intent_admission_before()
    SECURITY INVOKER
    BEFORE INSERT ON public.atom_v9_sim_intents FOR EACH ROW

public.atom_v9_sim4_publish_intent_after()
    SECURITY DEFINER
    AFTER INSERT ON public.atom_v9_sim_intents FOR EACH ROW

atom_v9_sim_intents_publication_before
atom_v9_sim_intents_publication_after
```

The `SECURITY INVOKER` BEFORE function does exactly one authority-bearing
operation before returning `NEW`:

```sql
PERFORM pg_catalog.pg_advisory_xact_lock_shared(
    1158704842749668574::bigint
);
```

It performs no sequence access, sidecar read/write, dynamic SQL, role change,
or validation bypass.

The AFTER function is owned by `atom_v9_sim_owner`, fixes
`search_path = pg_catalog`, schema-qualifies every object, validates the exact
horizon mapping, obtains one value from
`public.atom_v9_sim4_intent_admission_seq`, and inserts the exact four-column
sidecar. It is revoked from `PUBLIC`, `anon`, `authenticated`, `service_role`,
and both login runtime roles. The trigger invokes it; no caller may execute it
directly.

For a new intent, intent and sidecar commit or roll back together. PostgreSQL
still invokes the BEFORE shared-lock trigger when `ON CONFLICT DO NOTHING`
later chooses the no-op path, but does not invoke the AFTER trigger. Therefore
an idempotent retry of an existing intent allocates no new sequence and
preserves the sidecar created by the original successful insert. A fresh
installation may never contain an intent without its sidecar; startup and
reconciliation fail closed if that invariant is false. This phase has no
legacy NULL repair path because it imports no legacy intents. Concurrent
identical attempts may create a sequence gap only when a transaction that did
run AFTER later rolls back; gaps have no semantic meaning. No trigger updates
an intent or sidecar.

### 4.4 Exact fence reader and operational checkpoint

The migration creates one operational singleton:

```text
public.atom_v9_sim4_reconciliation_checkpoint
```

with:

```text
checkpoint_key                  text PRIMARY KEY
last_completed_publication_seq  bigint NOT NULL
checkpoint_version              bigint NOT NULL
runtime_started_at              timestamptz NULL
updated_at                      timestamptz NOT NULL
```

The one row starts as:

```text
checkpoint_key = 'ATOM_TRUE_V9_SIM4_RECONCILIATION_1'
last_completed_publication_seq = 0
checkpoint_version = 0
runtime_started_at = NULL
```

The checkpoint is operational progress metadata, not intent, entry, trade, or
historical evidence. Direct `INSERT`, `UPDATE`, `DELETE`, and `TRUNCATE` are
forbidden to both login roles. Its narrowly authorized compare-and-advance
update does not weaken the append-only law for evidence/history.

The second migration-created `SECURITY DEFINER` function is the zero-argument
fence reader:

```text
public.atom_v9_sim4_read_intent_admission_fence() RETURNS bigint
```

It is owned by `atom_v9_sim_owner`, fixes `search_path = pg_catalog`, verifies
`session_user = 'atom_v9_sim_entry_runtime'`, and returns `0` before the
sequence has been called or the exact current sequence value otherwise. It
performs no sequence mutation and no data-table scan. Only
`atom_v9_sim_entry_runtime` receives `EXECUTE`; nobody receives direct sequence
read authority.

The third and final migration-created `SECURITY DEFINER` function is:

```text
public.atom_v9_sim4_compare_and_advance_checkpoint(
    expected_last_completed_publication_seq bigint,
    expected_checkpoint_version bigint,
    new_last_completed_publication_seq bigint,
    capture_kind text,
    captured_publication_fence bigint,
    runtime_started_at timestamptz
) RETURNS boolean
```

It is owned by `atom_v9_sim_owner`, fixes `search_path = pg_catalog`, uses only
schema-qualified objects, grants `EXECUTE` only to
`atom_v9_sim_entry_runtime`, verifies `session_user` is exactly that role,
locks the singleton checkpoint row, and returns `false` without a write if
either expected value does not equal the current row.

Before reading the sequence or checkpoint, it makes exactly one nonblocking
transaction-scoped exclusive attempt:

```sql
SELECT pg_try_advisory_xact_lock(1158704842749668574::bigint);
```

`false` returns `false` without any read-side conclusion or write. On `true`,
the function reads the exact current sequence fence under that lock. It rejects
a caller-supplied `captured_publication_fence` above the current fence; no
future, nonexistent sequence gap can be checkpointed.

It accepts only `capture_kind IN ('ACTIVATION', 'RECONCILIATION')`, requires:

```text
0 <= expected_last <= new_last = captured_publication_fence <= current_fence
expected_checkpoint_version >= 0
```

and proves through the publication primary-key membership path that every
publication row in the entire closed interval `(expected_last, new_last]` has
one committed, valid terminal entry before it may advance. Semantic pages may
be processed in bounded slices, but no partial page or partial captured
interval advances the singleton because semantic order can invert sequence
order. A crash replays the still-unadvanced interval idempotently. Empty
sequence gaps may be crossed only inside that complete, already-current closed
fence. On success, the function compare-and-updates only the
singleton to `new_last`, version `expected_checkpoint_version + 1`, the passed
`runtime_started_at`, and transaction time, then returns `true` atomically.
It inserts no receipt and mutates no evidence row.

### 4.5 Forced RLS and exact definer count

Installation, intents, publications, entries, and checkpoint tables
all have `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
Migration 027 creates explicit policies for only these paths:

- publisher SELECT on installation and intents;
- publisher INSERT on intents;
- worker SELECT on installation, intents, publications, entries, and
  checkpoint;
- worker INSERT on entries; and
- operational-owner paths narrowly required by the three definer functions.

All other actions are denied. One `SECURITY INVOKER` rejection function backs
the exact mutation triggers: installation rejects every post-seed INSERT,
UPDATE, DELETE, and TRUNCATE; intents, publications, and entries reject UPDATE,
DELETE, and TRUNCATE; checkpoint rejects INSERT, DELETE, and TRUNCATE. The
checkpoint deliberately has no blanket UPDATE-rejection trigger because its
one owner-policy UPDATE is reachable only through the compare-and-advance
definer; login roles still have no UPDATE grant or policy. Migration 027 creates
exactly three `SECURITY DEFINER` functions: the AFTER publication function, the
zero-argument fence reader, and the compare-and-advance function above. The
BEFORE shared-lock and rejection functions are `SECURITY INVOKER`. Migration
027 creates no definer view and no fourth definer function.

The publication function's owner-only forced-RLS policy permits only sidecar
INSERT. The fence reader's owner-only policy permits no table write. The
checkpoint function's owner-only forced-RLS policies permit only the SELECTs
and singleton compare-and-update named above. No owner policy grants a login
role additional direct authority.

The current simulator intents in the ATOM production project remain immutable
there. They are not copied, deleted, rewritten, assigned entries, or used as a
SIM-4 recovery source. Cutover changes only future SIM-3 writes to the new
project. Because no SIM-4 entry table exists in the old project, this loses no
completed simulator trade history.

Activation order is exact:

1. create a fresh simulator Supabase project;
2. on one administrative session, begin one explicit transaction and set the
   exact transaction-local project-ref GUC;
3. apply and verify migration 027 inside that same transaction, then commit it
   once, including the refusal gate, singleton,
   roles, RLS, sidecar, fence-reader, and checkpoint invariants;
4. deploy the SIM worker with `ATOM_V9_SIM4_ENABLED=false`,
   `ATOM_V9_SIM4_DATABASE_URL`, and its isolated environment;
5. change production `ATOM_V9_SIM_DATABASE_URL` and
   `ATOM_V9_SIM_PROJECT_REF` to the new project;
6. verify every new immutable intent has its exact sidecar and the checkpoint
   remains internally valid; and
7. set `ATOM_V9_SIM4_ENABLED=true` on the SIM worker only.

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
The worker accepts the client credential only through these exact environment
names:

```text
ATOM_V9_SIM4_ALPACA_AUTHX_CLIENT_ID
ATOM_V9_SIM4_ALPACA_AUTHX_CLIENT_SECRET
ATOM_V9_SIM4_ALPACA_PROVISIONING_ATTESTATION_ID
ATOM_V9_SIM4_ALPACA_PROVISIONING_ATTESTATION_SHA256
```

The attestation ID identifies the external, access-controlled provisioning
record. Its SHA-256 variable is exactly 64 lowercase hexadecimal characters
and identifies the redacted record proving Data-read-only, Accounts-No-Access,
Trading-No-Access, and live SIP entitlement at deployment time. The secret is
never part of that record. Runtime cannot introspect AuthX custom Access
Controls or treat token claims as proof of scopes that AuthX does not expose;
it validates only attestation presence/shape and the live SIP handshake. The
operator must verify the external record before setting
`ATOM_V9_SIM4_ENABLED=true`.

The worker obtains the short-lived bearer token only from:

```text
https://authx.alpaca.markets/v1/oauth2/token
```

using one HTTPS `POST`, TLS certificate validation, redirects disabled,
`Content-Type: application/x-www-form-urlencoded`, and exact
`client_secret_post` form fields:

```text
grant_type=client_credentials
client_id=<ATOM_V9_SIM4_ALPACA_AUTHX_CLIENT_ID>
client_secret=<ATOM_V9_SIM4_ALPACA_AUTHX_CLIENT_SECRET>
```

The token connect timeout is 5 seconds and total request/read timeout is 10
seconds; the complete response body is capped at 16 KiB. Only HTTP 200 from the
same final URL, a JSON-object response, a nonempty string `access_token`,
`token_type` case-insensitively equal to `Bearer`, and a positive non-Boolean
integer `expires_in` are accepted. Credentials and tokens are forbidden in
URLs, query strings, Basic authentication, logs, telemetry, exceptions, or
persistence.

The websocket opening handshake uses exactly:

```text
Authorization: Bearer <access_token>
```

with TLS validation, redirects disabled, and a 10-second connection/handshake
timeout. The `websocket-client` call sets `redirect_limit=0` and the connected
socket uses an exact 1.000-second receive timeout so shutdown/deadline work can
be observed without an indefinite receive. No token is sent in a query string
or subprotocol. After authentication acknowledgement, the exact compact
subscription payload is:

```json
{"action":"subscribe","quotes":["COIN"]}
```

Authentication and the subsequent successful `quotes = ["COIN"]`
subscription acknowledgement must each arrive within 10 seconds. Only then
may the worker admit the `quotes` channel for `COIN`.
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
state and reconnects with one attempt at a time after exact delays of 1, 2, 4,
8, 16, then at most 30 seconds between later attempts. A connection stable for
60 continuous seconds resets the next delay to 1 second. Every reconnect
obtains a fresh token and repeats both acknowledgements; there is no busy loop,
parallel reconnect, redirect, or alternate endpoint. During a gap,
affected intents expire or receive the already-frozen restart classification;
quotes are never reconstructed or backfilled.

The websocket quote's `provider_event_ns` is preserved at nanosecond precision
and is valid only when it is an integer, not a Boolean, satisfying:

```text
0 <= provider_event_ns <= 9223372036854775807
```

This is the exact PostgreSQL `bigint` domain; an overflow or negative value
rejects the quote before admission.

The worker-admission event and monotonic-derived timestamp in Section 6
expressly replace merged PR #223's requirement that `accepted_at` be sampled
after a corresponding production market/V9 publication commits. SIM-4 has no
production quote callback or publication visibility. Its successful
mutex-serialized worker queue admission is the sole replacement causal point
for `accepted_at`, quote identity, window eligibility, and the quote hash. Bid,
ask, sizes, symbol, provider timestamp, source identity, canonicalization, and
every other quote/hash field retain the merged PR #223 contract.

## 6. Monotonic accepted time and deterministic quote ordering

The startup order is exact: acquire the owner lock; complete SIP authentication
and COIN subscription acknowledgement with quote admission still disabled;
acquire the admission mutex; read one `monotonic_ns` anchor and then one
validated UTC anchor while still holding that mutex; enable admission; and only
then attempt the activation capture in Section 7. This read order biases the
derived clock conservatively later by any anchor-read interval; it can never
backdate a quote across that interval. No quote receives an accepted time before
both anchors exist.

Thus each owned runtime generation reads exactly one UTC anchor and one
monotonic-nanosecond anchor after ownership and SIP readiness:

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

No new actionable intent may terminalize before its inclusive deadline, even
when an executable candidate or a durable open-position blocker is already
known. In particular, a timely `SKIPPED_POSITION_OPEN` collision is not
persisted early; only immutable validation of an already-existing terminal row
and the non-actionable `SKIPPED_NO_TRADE`/`SKIPPED_UNAVAILABLE` mappings remain
immediate. The worker's strict-greater
deadline observation acquires the same admission mutex, reads
`monotonic_now_ns` only after acquisition, compares the derived nanosecond
instant with the exact deadline, and snapshots the last admitted sequence
before releasing the mutex. It then drains every admitted quote through that
fixed sequence, filters the full eligible candidate set, and sorts that set by
the complete tuple above, but does not yet choose or persist a terminal result.
Only after this complete local candidate set exists does the database owner
thread queue the deadline-publication closure, reconcile the closed durable
set, apply global semantic ordering, and perform terminal selection under the
horizon lock. A quote producer
cannot sample a pre-deadline time, stall outside the mutex, and enqueue after
the watermark. Later admissions cannot affect that intent. Equal
`accepted_at` values are therefore resolved by provider event nanoseconds and
quote ID before any terminal decision, never by queue arrival order.

Equality remains pending and schedules a bounded recheck. Failure to complete
the bounded drain cannot choose a partial winner; it produces no terminal
decision until the complete fixed set is drained or a frozen restart/failure
rule applies.

When a pending deadline and quote-age eviction become due at the same logical
instant, deadline sampling, watermark capture, and fixed-set drain run first.
Quote eviction may run only afterward, so eviction cannot remove a member of a
deadline's closed candidate set.

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

SIM4_RECONCILE_INTERVAL_MS = 1000
SIM4_CAPTURE_STATEMENT_TIMEOUT_MS = 100
SIM4_DEADLINE_LOCK_TIMEOUT_MS = 5000
SIM4_DEADLINE_STATEMENT_TIMEOUT_MS = 6000
```

The worker obtains `SIM4_OWNER_LOCK_KEY` with
`pg_try_advisory_lock(bigint)` on one dedicated direct/session-mode connection.
It may not recover, accept quotes, inspect pending state, or persist a terminal
entry until it owns that lock. The same backend session remains open and owns
all SIM-4 terminal transactions. Loss or change of the backend PID disables
the generation before another terminal write.

The owner connection is in autocommit mode before its first owner-lock attempt
and returns to autocommit after every explicit transaction below. A `SET LOCAL`
value belongs only to its current explicit transaction and may not leak into a
later capture or terminal transaction.

The websocket receiver is one separately scheduled, non-authoritative thread.
It may validate messages and perform the bounded mutex/`put_nowait` admission
from Section 6, including while the database owner thread waits up to five
seconds for a deadline closure. It performs no database call, durable-intent
read, collision decision, checkpoint change, or terminal selection.

Every SIM-3 intent-insert transaction takes
`pg_advisory_xact_lock_shared(SIM4_ACTIVATION_LOCK_KEY)` before inserting. A
replacement worker performs activation only in the exact Section 6 startup
order: owner authority, successful SIP auth/subscription acknowledgement,
anchor capture under the admission mutex, and quote admission enabled. It then
begins a short activation transaction and calls exactly:

```sql
SET LOCAL statement_timeout = '100ms';
SELECT pg_try_advisory_xact_lock(1158704842749668574::bigint);
```

On `false`, it rolls back, keeps buffering SIP quotes, and retries only in the
background. On `true`, it calls the zero-argument definer fence reader, loads
durable open occupancy, and—while still inside the activation transaction—takes
the admission mutex once, samples `runtime_started_monotonic_ns`, and derives:

```text
runtime_started_at = monotonic_derived_utc(runtime_started_monotonic_ns)
```

from the immutable Section 6 anchors with the same checked upward-microsecond
conversion. `runtime_started_at` is not a later wall-clock or database-clock
read and cannot move backward relative to accepted-time ordering. The worker
then commits. Quote intake stays active throughout this database fence.

The snapshot defines the closed recovery set. Publisher transactions whose
INSERT path acquired or queued the shared lock ahead of the exclusive request
have completed before the snapshot. A transaction may have begun earlier but
not yet reached its INSERT/shared-lock request; it is deliberately classified
after the exclusive fence and is found by continuous reconciliation. No
interval exists in which an intent can commit but belong to neither recovery
nor active intake.

### 7.1 Periodic reconciliation capture

While the worker is READY, no closed reconciliation target is incomplete, and
no deadline closure is in flight, it schedules exactly one periodic capture
opportunity no later than 1,000 milliseconds after the preceding opportunity
completed. It never schedules more than one opportunity in that interval.
Quote admission and an already-due deadline take priority, but they may delay
only the in-flight opportunity and may not cancel or starve the next capture.
The owner connection begins a separate short transaction and executes exactly:

```sql
SET LOCAL statement_timeout = '100ms';
SELECT pg_try_advisory_xact_lock(1158704842749668574::bigint);
```

On `false`, timeout, or malformed result it rolls back and yields; it does not
move the checkpoint. On `true`, it calls the zero-argument fence reader once,
commits immediately, and treats the returned value only as a periodic closed
reconciliation membership fence. This capture does not create a deadline
closure, admit a late intent, choose a quote, or change `runtime_started_at`.

### 7.2 Per-deadline closure

The activation snapshot is not sufficient by itself to authorize same-horizon
terminal order. Before the worker terminalizes any ordinarily pending
actionable intent through its deadline `D`, the admission fence in Section 6
must already be fixed and the authoritative database session must queue one
deadline-publication closure. The late-publication and restart paths in
Section 8 cannot create this closure or inspect its quote set.
For one unique deadline `D`, the worker first completes the local
strict-greater sample, watermark, drain, and complete sorted candidate set from
Section 6. Only then does the database owner thread begin a short transaction,
set the exact independent deadline timeouts, and call:

```sql
SET LOCAL lock_timeout = '5000ms';
SET LOCAL statement_timeout = '6000ms';
SELECT pg_advisory_xact_lock(1158704842749668574::bigint);
```

This deadline call is blocking only on the database owner thread; SIP quote
intake remains active and bounded. Once the exclusive request is queued, later
shared publisher requests cannot pass it. Every shared request queued or
granted ahead of it finishes before the exclusive lock is granted; a
transaction that merely began earlier but requests the shared lock later is on
the post-fence side. The worker then snapshots the maximum committed
publication sequence through the zero-argument fence reader and commits
immediately.
Lock timeout, connection loss, or ambiguity rolls back and permanently
deactivates that generation; it never retries in a way that could widen the
closed deadline set.

The first successfully captured pair:

```text
(local_quote_watermark, database_publication_fence)
```

is cached exactly once per unique `D` and is shared by every horizon/intent
with that deadline. It is never recomputed, extended, or replaced. A periodic
or activation fence cannot substitute for either half of this pair. The
100-millisecond capture timeout never applies to this transaction, and the
5,000/6,000-millisecond deadline settings disappear when it commits or rolls
back.

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
(publication_at, horizon_order, intent_id, publication_seq)
```

with publication sequence used only as the unique final cursor tie-breaker.
The closed publication-sequence predicate still defines membership, but
publication sequence never reverses semantic order. Page boundaries never
alter this order. A page is terminalized before the next semantic page is read;
the worker does not stage the whole closed interval in memory and does not
terminalize a later page while an earlier row remains incomplete.

For timing classification, a fetched publication becomes discovered exactly
once after its sidecar, joined intent row, canonical JSON/hash, project identity,
and publication invariants have all validated. Before any yield, the owner
thread acquires the same admission mutex used by the deadline fence, samples
`monotonic_ns`, derives one discovery instant through the immutable Section 6
anchor, and atomically registers the validated intent in pending state before
releasing that mutex. Registration is timely only when the derived instant is
at or before the inclusive deadline and that deadline has not already been
marked closed under the mutex. The strict-greater deadline path marks its
deadline closed and snapshots its quote watermark in the same mutex critical
section. Therefore discovery registration and deadline closure have one total
order: whichever completes that critical section first controls, and no row can
be fetched before the deadline yet ambiguously register after its closure. A
validation failure registers nothing and fails closed under its frozen error
rule.

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

Both test files are new. No existing test file may be edited by SIM-4.

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
- exact direct-role and `<role>.<project-ref>` session-pooler username grammar;
- TLS is mandatory;
- stable ownership backend PID;
- migration requires the same-session/same-explicit-transaction `SET LOCAL`
  project-ref GUC, performs no internal commit, and creates the exact
  three-column installation singleton atomically;
- migration refuses every pre-existing public user relation, `atom_%` schema,
  foreign-data object, target role/object, and production schema;
- publisher and entry-worker DSNs authenticate as their exact different roles;
- publisher can insert intents but cannot insert entries or publications;
- entry worker can read intents/publications and insert entries but cannot
  insert intents or publications;
- neither runtime role has production, mutation, ownership, membership in the
  other role, or RLS-bypass privilege;
- exact NOLOGIN owner, forced-RLS policies, and exactly three definer functions;
- every carried publisher operational-function grant is superseded/revoked and
  only the entry-worker role can execute the two SIM-4 operational functions;
- exact four-column sidecar, 1..6 horizon order, restrictive FK, semantic
  keyset index, and publication-sequence membership path;
- BEFORE invoker shared-lock and AFTER definer publication behavior, including
  idempotent `ON CONFLICT DO NOTHING` and rollback interleavings;
- zero-argument fence reader exposes no direct sequence privilege;
- checkpoint direct update is denied and compare-and-advance nonblocking-locks
  the handoff key, rejects stale/above-current/incomplete captures, and
  advances only a complete captured interval despite semantic paging;
- old production intents are not scanned or copied; and
- simulator failure does not block production startup or requests.

### Quote source and authority

- exact SIP websocket URL and COIN-only quote subscription;
- successful auth and subscription are required before admission;
- the exact four AuthX/attestation environment names are required;
- worker queue admission, never a production publication callback or commit,
  is the sole `accepted_at` causal point used by identity/hash/window logic;
- the external provisioning record, not runtime token introspection, attests
  Data-read-only, every other scope No-Access, and SIP entitlement;
- a standard Trading API key, legacy Broker key, Alpaca Connect user token, or
  missing/unverifiable scope evidence keeps SIM-4 disabled;
- exact `client_secret_post`, redirects-disabled token request, Bearer websocket
  handshake, TLS, 16-KiB response cap, `redirect_limit=0`, 1.000-second receive
  timeout, exact compact subscription payload, 5/10-second acknowledgements,
  token secrecy, and 1/2/4/8/16/30-second reconnect bounds;
- `provider_event_ns` rejects Boolean, negative, and values above signed-bigint
  maximum;
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
- forced interleavings prove discovery registration and deadline closure share
  that mutex and produce one total timely/late order;
- equal accepted timestamps are fully drained and sorted by provider
  nanoseconds and quote ID before selection;
- reverse arrival order with equal accepted time selects lower provider
  nanoseconds, then lower quote ID when provider nanoseconds also tie;
- quantization uses checked integer arithmetic and round-trips exactly through
  the Python hash and PostgreSQL `timestamptz` value;
- no actionable intent terminalizes before its inclusive deadline;
- a timely durable-open collision also cannot terminalize before deadline;
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
- deadline processing wins over quote eviction at an equal logical instant;
- each unique deadline caches one immutable local-watermark/database-fence
  pair, never an activation/periodic substitute.

### Runtime and recovery

- missing or non-`true` `ATOM_V9_SIM4_ENABLED` performs no runtime work;
- golden owner and activation payloads, digests, keys, and SQL calls;
- exact owner-lock, SIP acknowledgements, anchor-under-mutex, admission-enable,
  then activation-capture startup order;
- activation and periodic captures use exact 100-millisecond statement timeout;
- deadline closure uses exact 5,000-millisecond lock timeout and
  6,000-millisecond statement timeout without setting leakage;
- exact 5,000-millisecond queued deadline-lock timeout and fail-closed
  generation deactivation on timeout;
- the non-authoritative SIP receiver continues bounded admission during the
  owner thread's deadline-lock wait but has no database/decision authority;
- `runtime_started_at` is monotonic-derived from the immutable runtime anchors;
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
