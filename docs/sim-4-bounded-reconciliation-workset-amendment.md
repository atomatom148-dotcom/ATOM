# ATOM TRUE V9 — SIM-4 Bounded Reconciliation Workset Amendment

**Status:** LAW after merge  
**Change type:** Documentation only  
**Authorized next phase:** SIM-4 only  
**Amends:** `docs/sim-3b-isolated-runtime-data-plane-freeze.md` and the
SIM-3A reconciliation amendments it controls  
**Implementation boundary:** the existing six authorized SIM-4 implementation
files only

This is the narrow controlling amendment for one feasibility defect in the
SIM-4 reconciliation access path. Where it conflicts with an earlier simulator
document, it controls only for closed-interval reconciliation paging, the one
session-local workset defined below, and the database `TEMPORARY` privilege
needed to create that workset. Every other merged simulator rule remains law.

This documentation change does not activate SIM-4, apply a migration, create a
database object, change Render or Supabase, or authorize SIM-5 or SIM-6.

## 1. The two durable indexes cannot bound the frozen intersection query

The durable publication sidecar keeps both existing indexes unchanged:

```text
PRIMARY KEY (publication_seq)

atom_v9_sim_intent_publications_semantic_idx
    (publication_at, horizon_order, intent_id, publication_seq)
```

They are each exact for one dimension. The primary key defines closed-set
membership. The semantic index defines terminal-decision order. They do not,
however, make this two-dimensional query bounded:

```sql
WHERE lower_publication_seq < publication_seq
  AND publication_seq <= captured_publication_fence
  AND semantic_key > semantic_cursor
ORDER BY semantic_key
LIMIT 16
```

For arbitrary, explicitly supported inversions between publication sequence and
semantic order, PostgreSQL has only two general choices:

- scan the sequence interval through the primary key and sort every qualifying
  row before returning the first 16; or
- scan in semantic-index order and reject an arbitrarily large number of rows
  outside the sequence interval before finding 16 members.

`LIMIT 16` bounds returned rows, not rows scanned or sorted. A larger database
or worker does not change that property. Planner settings, a statement timeout,
an application row cap, or an assumption that sequence usually correlates with
time cannot make the frozen worst case exact. Adding sequence before the
semantic tuple in another B-tree would still require sorting the full interval.

Therefore the earlier statement that the two durable indexes alone provide a
bounded direct semantic page over an arbitrary closed sequence interval is
superseded. The durable index definitions themselves are not changed or
dropped. The earlier prohibition on an unbounded sort, offset pagination, and
an unrelated-history scan remains absolute.

## 2. Invariants that do not change

This amendment changes an operational access path only.

- The immutable intent, publication, quote, entry, hash, canonicalization, and
  installation contracts do not change.
- Closed-set membership remains exactly
  `(last_completed_publication_seq, captured_publication_fence]`.
- Global semantic order remains exactly
  `(publication_at, horizon_order, intent_id, publication_seq)`.
- Publication sequence never becomes terminal-decision precedence.
- A complete semantic page is validated and terminalized before the next
  semantic page is read.
- Existing-terminal, restart-gap, durable-position, deadline, quote, and
  same-horizon precedence do not change.
- Durable simulator history remains append-only and has no row, day, trade,
  age, TTL, rotation, or retention ceiling.
- At most one position per horizon and at most six open SIM-4 positions remain
  law. SIM-5 is still required for exits and repeated completed trades.
- No simulator failure, timeout, restart, or capacity event may fabricate a
  quote, intent, entry, resolution, or trade.

The workset below is operational scratch state. It is not evidence, is not
hashed, is not published, and cannot replace a durable publication or terminal
entry.

## 3. Exact narrow `TEMPORARY` authority

Migration 027 must make database temporary-object authority explicit on the
isolated database named `postgres`:

```sql
REVOKE TEMPORARY ON DATABASE postgres FROM PUBLIC;
REVOKE TEMPORARY ON DATABASE postgres FROM atom_v9_sim_runtime;
GRANT TEMPORARY ON DATABASE postgres TO atom_v9_sim_entry_runtime;
```

The migration and post-migration authority audit must prove:

```text
PUBLIC                         TEMPORARY = false
atom_v9_sim_runtime            TEMPORARY = false
atom_v9_sim_entry_runtime      TEMPORARY = true
```

No runtime role receives `CREATE` on a persistent schema. No persistent table,
index, sequence, view, function, trigger, policy, extension, schema, or foreign
object is added by this amendment. The publisher cannot create a temporary
object. The entry runtime's only authorized use of database `TEMPORARY` is the
one workset below on the one backend session that currently holds the SIM-4
session ownership lock.

This is the sole exception to the earlier general statement that a login
runtime owns no object: `atom_v9_sim_entry_runtime` owns its session-local
workset and automatically created temporary support objects only. It receives
no ownership or mutation authority over durable simulator objects. All
`SECURITY DEFINER` functions retain `search_path = pg_catalog` and all durable
relations remain schema-qualified, so a temporary-name shadow cannot redirect
a definer or evidence operation.

Standby sessions, publisher sessions, non-owning replacement sessions, and the
web service may not create the workset. Unexpected user-named objects in the
authoritative session's temporary schema fail the generation closed.

## 4. Exact session-local workset

After the worker has acquired the session ownership lock, proved the stable
backend PID, exact entry-runtime role, and installation identity, that same
session creates exactly one user-named temporary table:

```text
pg_temp.atom_v9_sim4_reconciliation_workset

publication_seq  bigint      PRIMARY KEY, greater than zero
intent_id        text        UNIQUE NOT NULL
publication_at   timestamptz NOT NULL, finite
horizon_order    smallint    NOT NULL, between 1 and 6
```

It is `ON COMMIT PRESERVE ROWS`. It has exactly this semantic B-tree access
path, created while the table is empty:

```text
atom_v9_sim4_reconciliation_workset_semantic_idx
    (publication_at, horizon_order, intent_id, publication_seq)
```

Primary-key, unique-constraint, semantic-index, and PostgreSQL internal
temporary support objects are part of this one workset. No other user-named
temporary relation is authorized.

The workset contains only the four immutable publication locator fields. It
contains no intent JSON, quote, entry, price, position, credential, token,
attestation, production data, or terminal result. It is never treated as the
source of canonical evidence. Its rows are checked against durable rows before
discovery or terminalization.

The workset lives only for the authoritative backend session. It is never
shared across a pooler backend, process, Render instance, or owner generation.
Backend loss remains generation-terminal and causes PostgreSQL to drop the
workset automatically.

## 5. One closed target has two bounded phases

The existing exclusive capture and checkpoint values do not change. A worker
still captures one fixed target fence and does not widen or replace that target
while it is incomplete. The runtime-only target now also records:

```text
phase = STAGING | SEMANTIC
stage_after_publication_seq
semantic_cursor
stage_exhausted
semantic_exhausted
```

These values are operational, unhashed, and not evidence. The workset is empty
before staging a new target. It may be emptied for reuse only after the prior
target's checkpoint compare-and-advance has committed successfully.

### 5.1 Bounded primary-key staging

`STAGING` copies locator fields from the complete closed membership set in
primary-key pages. Each staging slice performs the equivalent of:

```sql
SELECT publication_seq, intent_id, publication_at, horizon_order
FROM public.atom_v9_sim_intent_publications
WHERE publication_seq > stage_after_publication_seq
  AND publication_seq <= captured_publication_fence
ORDER BY publication_seq
LIMIT 16;
```

The durable publication primary key is the required access path. One bounded
transaction inserts or idempotently revalidates those at-most-16 exact rows in
the temporary workset. The runtime staging cursor advances only after that
transaction commits and only to the last returned sequence. A conflict that is
not byte-for-byte/column-for-column identical fails the generation closed.

A page smaller than 16 seals staging after all returned rows commit. A page of
exactly 16 never proves exhaustion; a later bounded page, including an empty
page, does. Sequence gaps are permitted and do not synthesize workset rows.

Exactly one staging page is handled in one reconciliation slice. After every
staging page, the database owner thread yields to the ordinary worker loop.
Quote FIFO service and already-due deadline/expiry boundaries retain their
existing priority. A target with any number of durable rows is therefore built
with finite application memory and no single scan or sort over the whole
interval.

Staging a four-column locator is not discovery. It does not deserialize or
validate an intent, sample a discovery time, inspect quotes, choose a terminal
status, or persist an entry. This distinction preserves the existing exact
discovery rule.

### 5.2 Semantic pages from the completed workset

Only after staging is sealed may the target enter `SEMANTIC`. The worker reads
at most 16 workset locators through the temporary semantic index with the exact
keyset predicate and order:

```text
(publication_at, horizon_order, intent_id, publication_seq) > semantic_cursor
ORDER BY (publication_at, horizon_order, intent_id, publication_seq)
LIMIT 16
```

The workset contains the entire fixed closed interval before the first such
page is read. Consequently, the first row of every page is the true next row in
global semantic order even when database publication sequence is arbitrarily
inverted.

The selected workset page must be materialized as a set of at most 16 locators
before durable validation. For each locator, in page order, the worker performs
one publication-primary-key point read joined by exact `intent_id` to the
durable intent primary/unique key. No durable range scan, offset, or semantic
filter scan is permitted in this phase. The durable publication row must exist
and must equal all four workset fields. The joined intent columns, canonical
JSON, identity, hash, horizon mapping, project installation, and publication
invariants then pass the existing exact validation.

Only after one row has passed those checks may it enter the controlling
discovery critical section. The owner thread acquires the same admission mutex
used by deadline closure, samples the same monotonic-derived discovery instant,
and atomically registers the validated intent in pending state before releasing
that mutex. This remains after durable validation and before any yield, quote
inspection, or terminal decision. The existing mutex total order between
discovery registration and strict-greater deadline closure remains unchanged.
Workset staging time is not backdated and does not make a late row timely.

All rows in the semantic page are durably validated and pass through that
frozen discovery-registration rule in semantic order without a yield. The page
is then terminalized in semantic order under all existing precedence and
horizon-lock rules. The semantic cursor advances to the last row only after the
whole page has terminalized successfully. A partial failure does not advance
past any row; later replay is idempotent against immutable terminal entries.

A semantic page smaller than 16 proves semantic exhaustion only after every
returned row succeeds. A page of exactly 16 requires a later indexed page or
empty-page proof. Page boundaries cannot change global same-horizon order.

## 6. Checkpoint, cleanup, crash, and replacement

After semantic exhaustion, the existing
`atom_v9_sim4_compare_and_advance_checkpoint` call remains the only checkpoint
authority. Its indexed proof over the entire closed publication-sequence
interval is deliberately retained and accepted. It independently proves that
every durable publication in the captured interval has a valid terminal entry;
it does not trust the temporary workset, its row count, or runtime cursors.

The checkpoint function, signature, lock, current-fence validation, full-
interval completeness proof, compare-and-update, RLS authority, and exactly
three-definer-function limit do not change. Its one primary-key-bounded closed-
interval proof is not replaced by per-page checkpoint writes and is not the
unrelated-history semantic scan superseded by this amendment.

On compare-and-advance `false`, timeout, or rollback, the target, cursors, and
workset remain logically incomplete and retry without widening the fence. The
workset may be emptied only after a successful checkpoint commit, or by
automatic session teardown. No cleanup deletes or mutates durable evidence.

If the process or authoritative backend is lost before checkpoint success, the
temporary workset disappears and the durable checkpoint remains unchanged. A
successor acquires a new backend and rebuilds the same closed interval from the
durable checkpoint in bounded staging slices. Already-created terminal rows are
replayed and validated idempotently. If the checkpoint commit succeeded but
the client failed before local cleanup, the durable checkpoint controls; the
old session's workset is discarded and cannot be adopted by a successor.

Graceful shutdown stops new work, completes only the already-authorized bounded
shutdown actions, releases ownership when possible, and closes the session. It
does not serialize, upload, or preserve the workset.

## 7. Capacity, fairness, and failure behavior

The workset removes an accidental full-history scan; it does not create a total
row ceiling. A closed interval of any size is staged and processed through
bounded 16-row slices until exhaustion. PostgreSQL may use its own bounded
memory and temporary storage for the temporary relation; application memory
must not grow with the interval.

There is no `OFFSET`, full-interval application list, in-memory global sort,
durable-history rescan in semantic order, sequence/semantic correlation
assumption, or fallback to the old direct intersection query. Failure to create
the exact workset, obtain the exact plan/access paths, stage or validate a page,
retain the backend, or respect its finite operational resources fails that SIM
generation closed. It cannot loosen ordering or fabricate evidence.

Every staging and semantic slice returns to the ordinary event loop. Existing
quote-admission bounds, deadline priority, retry backoff, shutdown bounds, and
secret-free logging rules remain unchanged. Scaling Render or Supabase may
improve throughput but does not alter this algorithm or its evidence semantics.

Operational status must expose, without IDs, payloads, DSNs, tokens, or other
unbounded labels:

- current reconciliation phase;
- fixed lower and fence distances or counts, not raw evidence payloads;
- staging pages and rows completed;
- semantic pages and point validations completed;
- workset rebuilds after a new owner generation;
- staging, workset-plan, durable-mismatch, timeout, checkpoint, and cleanup
  failures; and
- the existing overall reconciliation and generation state.

Counters and logs are diagnostic only. They never authorize cursor or
checkpoint movement.

## 8. Required verification before activation

The two existing authorized test files must cover at least:

- migration ACLs deny database `TEMPORARY` to `PUBLIC` and the publisher and
  grant it only to the entry runtime among login runtime roles;
- the publisher, web, and non-owner paths cannot create the workset;
- the authoritative stable-PID session creates exactly the one temporary table
  and exact empty-built semantic index with `ON COMMIT PRESERVE ROWS`;
- no persistent schema object, fourth definer function, new RLS path, or durable
  grant is added;
- adversarial publication data inverts sequence and semantic order, with target
  members placed after an arbitrarily large nonmember semantic prefix;
- every durable staging query uses the publication primary key, returns at most
  16 rows, performs no sort, and advances only after exact temporary persistence;
- every semantic workset query uses its semantic index, returns at most 16
  locators, and performs no scan or sort over durable history;
- durable validation performs no more than 16 publication primary-key point
  reads per semantic page and detects missing, altered, orphaned, or
  noncanonical rows before discovery;
- a complete interval greater than 65,536 rows is processed in exact global
  semantic order with finite application memory and no total-row cap;
- exactly-16 boundaries require a later empty-page proof in both phases;
- ordinary FIFO service and deadline boundaries occur between staging and
  semantic slices under a large backlog;
- no discovery timestamp is sampled during staging, and semantic validation is
  immediately followed by the frozen mutex-atomic discovery registration;
- page failure, checkpoint `false`, process crash, backend loss, and rolling
  replacement never advance the durable checkpoint incorrectly;
- a successor rebuilds the lost workset from the unchanged checkpoint and
  validates existing terminal rows idempotently; and
- successful checkpoint commit precedes temporary cleanup.

The disposable PostgreSQL integration test must inspect `EXPLAIN (FORMAT JSON)`
and adversarial `EXPLAIN (ANALYZE, FORMAT JSON)` plans on the supported
PostgreSQL major version. It must reject a plan that restores the old durable
semantic-filter scan, sorts the closed durable interval, uses offset paging, or
reads more than the bounded page before point validation. Mock-store pagination
alone is not evidence of a bounded database access path.

## 9. Hard implementation boundary

This amendment authorizes implementation only inside the already-frozen six
SIM-4 files:

```text
migrations/027_create_v9_sim_entries.sql
quant/v9_sim4_entry.py
quant/v9_sim4_worker.py
quant/web.py
tests/test_v9_sim4_entry.py
tests/test_v9_sim4_isolation.py
```

`quant/web.py` receives no new workset or entry authority. No seventh
implementation file, dependency, persistent disk, queue service, Redis/Valkey
instance, database project, Render service, broker capability, AI trading
logic, production callback, SIM-5 exit, or SIM-6 state is authorized.

The only persistent database-authority change is the explicit database
`TEMPORARY` ACL in Section 3. The durable schema and all evidence mathematics
remain exactly as frozen.
