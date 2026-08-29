# H2-D-2 date-level parallel architecture freeze

**Status:** LAW — architecture frozen; parallel runtime disabled  
**Current runtime:** `H2-D-1`, bounded and sequential  
**Next possible phase:** H2-D-3 Parallel Canary, only after separate approval

## Decision

The only approved future concurrency unit is one complete historical trading
date. A future persistent date worker owns the full
`H1 → H2B → H2C_RESOLVE → H2C_SCORE` chain.
Frames, quote alignment, family calculations, horizons, target resolution,
verification, persistence, and scoring inside that date remain sequential.
The future canary uses process isolation, never threads, and allows no nested
pool or executor.

This freeze changes no runtime code and grants no authority to execute the
canary. The present `for day in days` path remains the only executable path.
H2-D-3 must use non-writing H1 replay and outcome-verification modes for the two
already-certified dates. H1 may re-fetch and calculate but cannot pass
`--persist-certified`. H2C resolution is a read-only completeness verification,
not the current mutating resolver command. If those modes do not exist, the
canary must add and verify them before it can dispatch two dates.

## Ownership and scheduling contract

1. One coordinator owns the complete, ascending, unique date plan and the
   final ordered receipt. Workers cannot enqueue, split, or reassign work.
2. One guardian exclusively owns one date from claim through terminal cleanup;
   its single worker process owns that date's full stage chain through validated
   receipt. The job key is the ISO date. Only distinct dates may coexist.
3. Exactly one coordinator may be active. Before any preflight query or worker
   creation, it opens exactly one dedicated, session-pinned,
   non-transaction-pooled control connection to the same evidence database,
   enables `default_transaction_read_only`, records `pg_backend_pid()`, and
   calls `SELECT pg_try_advisory_lock(8098937340306602170)` exactly once.
   False, null, or error stops before workers. A distributed queue, lease
   expiry, abandoned-worker reassignment, and more than two workers are not
   authorized.
4. After acquiring the coordinator lock, the same session must acquire both
   date-fence locks exclusively before creating any workload process:
   `pg_try_advisory_lock(-5133988379539764595)` for `2026-06-15` and
   `pg_try_advisory_lock(8459531074882316998)` for `2026-07-22`. Failure to
   acquire either releases every acquired date fence exactly once and stops.
   After acquiring both, it contacts the two exact, configured durable host
   supervisors pinned by the canary configuration digest. Each supervisor must
   attest a monotonic record version, terminal receipt identity, `CLEAN`, the
   prior worker and guardian reaped, and its fixed workload cgroup at
   `populated 0`; a missing, stale, malformed, unreachable, or nonterminal
   attestation stops. Each supervisor serializes admission and atomically
   compare-and-swaps that exact attested `CLEAN` version and terminal receipt
   to a fsynced `CLAIMING` generation record containing the next monotonic
   version, date, generation ID, commit, coordinator OS PID and database
   backend PID, host identity, and fixed cgroup path. A false compare-and-swap,
   stale version, or generation mismatch stops; every later transition is
   conditional on the exact predecessor version and generation. If fewer than
   two compare-and-swaps succeed, no fence handoff or guardian creation occurs
   and each partial claim must complete terminal cleanup before a retry. Only
   after both records are durable may the supervisors
   create exactly two claim-only date guardians outside the coordinator and
   workload failure domains. The coordinator unlocks each exclusive date fence
   exactly once only so the corresponding guardian can claim it in shared
   mode. No worker, stage, or provider call may begin during this handoff.
5. Each guardian must run on a Linux host with delegated cgroup v2 support for
   `cgroup.freeze`, `cgroup.kill`, and the `populated` field in
   `cgroup.events`; missing or unverified support stops before claim. The
   guardian opens its own session-pinned, read-only fence connection, acquires
   its date key with `pg_try_advisory_lock_shared`, verifies its own backend
   ownership through `pg_locks`, and verifies that the exact recorded
   coordinator backend PID still owns `8098937340306602170`. It also opens a
   `pidfd` for the exact coordinator OS PID and a close-on-exec liveness pipe
   whose write end is owned only by the coordinator. The supervisor must then
   atomically transition and fsync its durable generation record from
   `CLAIMING` to `ACTIVE`. Only then may the guardian return a claim receipt.
   Both claim receipts are required before either guardian may create its
   single worker and issue a start signal. The generation record is independent
   of PostgreSQL sessions; only the fixed supervisor may change it, and any
   `CLAIMING`, `ACTIVE`, `CLEANING`, or unknown state blocks replacement
   admission.
6. The coordinator retains its physical control session for the complete
   canary. Its wait loop checks `SELECT pg_backend_pid()`, and each guardian
   checks both its own shared fence ownership and the exact coordinator lock
   owner, at an interval of at most five seconds. Coordinator `pidfd`
   readability, liveness-pipe EOF, error, PID drift, lock loss, or any control
   or fence-connection loss permanently fails the canary. The supervisor keeps
   the durable state nonterminal and fsyncs `CLEANING`; the guardian must then
   freeze its dedicated workload cgroup, invoke `cgroup.kill`, reap its worker,
   and wait until `cgroup.events` reports `populated 0`. If the guardian exits
   early, the persistent supervisor performs the same cleanup and reaps it.
   Only after that ordered cleanup may the guardian unlock or close its shared
   fence connection. Each stage has a dedicated process group inside that
   cgroup, and every worker, launcher, stage, and descendant must remain in the
   same no-escape cgroup. A parent-death signal or process-group kill alone is
   not accepted as proof of containment. No guardian, worker, or descendant
   may use or inherit the coordinator connection or liveness-pipe write end.
7. A guardian holds its shared date fence from claim through terminal cleanup
   on success and every failure path while that database session exists. On
   normal completion it validates the final receipt, waits for worker exit,
   reaps the worker, and proves the workload cgroup is empty before it releases
   the shared fence exactly once and exits. After reaping the guardian and
   independently reproving `populated 0`, the supervisor atomically persists
   and fsyncs the terminal cleanup receipt and changes its generation state to
   `CLEAN` as the last operation. The coordinator retains the global advisory
   lock until both supervisors attest those terminal receipts. On every path
   after successful acquisition, only then does the coordinator release
   `8098937340306602170` exactly once in `finally` and close its session. False
   unlock, early guardian death, incomplete reaping, a nonempty cgroup,
   nonterminal supervisor state, or connection error is a control failure;
   connection closure is only a backstop. Every replacement must repeat both
   supervisor checks in step 4, so it cannot begin while any prior workload
   cgroup remains populated even after a database restart or failover drops all
   three advisory-lock sessions.
8. The later canary is capped at exactly two worker processes and the two dates
   frozen below. Completion order cannot change receipt order.
9. For a date with no manifest, the run ID is `h2d-YYYY-MM-DD`. If exactly one
   certified manifest already exists, its immutable run ID is reused. More
   than one manifest for a date is a permanent failure.
10. Each database-owning stage uses its own bounded connection/transaction.
   No worker may hold a row, table, or transaction lock while waiting on
   another worker or provider/network I/O; its guardian's frozen shared
   date-fence advisory lock is the sole exception. The canary permits at most
   two replay-workload, two guardian-fence, and one coordinator-control
   database connections at once.

The fixed coordinator advisory lock enforces fast-path single ownership across
processes and hosts connected to the evidence database. The durable supervisor
generation records are the independent admission fence when database sessions
all disappear. Database primary keys and existing per-run advisory locks remain
the final row-integrity barrier; they do not replace the coordinator/date-claim
law. Manifest content includes performance fields, so two simultaneous H1
writers for one date can safely conflict even when their mathematics matches.

## Stage, retry, and failure contract

- Stage order is exact: `H1`, `H2B`, `H2C_RESOLVE`, then `H2C_SCORE`.
- Every stage receipt must return the claimed historical date and run ID. A
  missing or mismatched identity fails the date before the next stage.
- There is no blind or timed automatic retry. Failure quarantines the date.
  An operator may later reauthorize the whole canary date only with the same
  date, run ID, job key, commit, runtime versions, configuration digest, dataset
  digest, session digest, and artifact hash. If the immutable input cannot be
  reproduced exactly, the retry fails.
- H2-D-3 requires exactly one certified manifest and complete outcomes before
  launch. Zero manifests, incomplete outcomes, or more than one manifest fail
  closed. The current write-capable H1 persistence and H2C resolver commands
  are forbidden. A zero-manifest H1 write belongs only to a later, separately
  approved write phase. H2B is never bypassed; content is never overwritten or
  deleted.
- Invalid JSON, nonzero exit, database interruption, missing or uncertified
  manifest, incomplete outcomes, lineage/hash/count/metric drift, or any
  duplicate identity fails the canary. No pending date begins after failure;
  an already-running date may finish only to produce a diagnostic receipt.
- The canary must use fail-stop behavior equivalent to
  `continue_on_failure=False`.
- H2-D-3 opens replay database connections read-only and requires
  `outcome_writes = 0`. Missing outcomes fail before launch; the current
  write-capable resolver is never called. Pre/post manifest, forecast, and
  outcome counts and hashes must match.

## Exact completeness and parity contract

For each date, all of these identities and counts are exact:

- one historical session and one replay run;
- `forecast_count = frame_count × 12 × 6`;
- `outcome_count = frame_count × 6`;
- 12 quant identities, six horizons, and exactly 72 metric objects;
- available plus unavailable counts equal their table totals;
- database primary-key count equals row count for manifests, forecasts, and
  outcomes.

The immutable parity signature includes the date/run identity; pinned commit
and runtime versions; dataset, configuration, session, artifact, manifest,
ordered forecast, and ordered outcome hashes; all counts; the H2B stored
forecast summary; the scoring input summary; and a canonical SHA-256 over all
72 metric objects. The full 72 metrics must also compare field-for-field.
Floating-point equality is exact; no tolerance or reordering is allowed.

The metric digest bytes are frozen by
`metric_hash_contract` in the machine-readable baseline bundle:

1. Require exactly the Cartesian order of the listed 12 `quant_order` values
   followed by the listed six `horizon_order` values (quant outer, horizon
   inner). Duplicate, missing, extra, or reordered metric objects fail.
2. Rebuild each object with exactly the listed `field_order`; missing or extra
   fields fail. `eligible_count` and `resolved_count` are non-boolean JSON
   integers. `directional_wins` and `directional_losses` are either
   non-boolean JSON integers or JSON `null`.
3. `directional_accuracy`, `rmse`, `mae`, and `bias` are either finite
   IEEE-754 binary64 values or JSON `null`; `coverage` is always a finite
   binary64 value. NaN and positive or negative infinity fail.
4. Replace every non-null binary64 value with the lowercase ASCII string
   returned by Python 3.12 `float.hex()`. Preserve JSON `null` unchanged. This
   preserves signed zero and exact binary value without decimal ambiguity.
5. Serialize the 72-object array as UTF-8 JSON with `ensure_ascii=False`,
   `allow_nan=False`, `sort_keys=False`, separators `(",", ":")`, and no
   trailing newline. Hash those exact bytes with SHA-256 and encode the digest
   as lowercase hexadecimal.

The digest is a secondary receipt: promotion also requires all original metric
fields to compare exactly before float-to-hex transformation.

The baseline ordered-content hashes are SHA-256 over the UTF-8 stored
`content_sha256` values joined by one LF with no trailing separator. Forecasts
use `(cutoff_at, quant_id, horizon)` order; outcomes use
`(cutoff_at, horizon)` order.

`scoring_hash_summary` alone is insufficient because it hashes admitted input
rows rather than the computed metric values. The current H2-D
`receipt_sha256` is also excluded from mathematical parity because it includes
elapsed timings and memory telemetry. Timestamps, stage timings, RSS,
`outcome_writes`, completion order, and the full operational receipt hash are
diagnostics only.

## Frozen canary sessions

The read-only baseline bundle is
`docs/h2-d2-canary-baselines.json`.
Its canonical values and the SHA-256 source digests of the current H2-D-1
orchestrator, entry stages, and complete local H1 replay/family dependency
closure are pinned by contract tests. The closure test resolves every
repository-local Python import recursively and includes every package
initializer on each module path, so a newly imported local module or
initializer cannot escape the digest and sequential-runtime guards.
Source hashing reads UTF-8 text, removes all terminal LF characters, appends
exactly one LF, and hashes those normalized bytes.
Changing a digest or stage implementation requires a separately approved freeze
update; an arbitrary well-formed replacement hash is not accepted.

- `2026-06-15` exercises the legacy certified-manifest resume path with run ID
  `h2a-2026-06-15-persistence-v3`.
- `2026-07-22` exercises the newer H2-D cohort and carries the independent
  DB-3 parity receipt.

These stored baselines certify existing immutable evidence; they do not by
themselves authorize or claim a successful parallel canary. H2-D-3 must first
capture a fresh sequential, non-writing control bundle with stage receipt
identities, H2B/scoring summaries, all 72 metrics, and canonical metric hash.
The two-date process canary must match that control exactly.

## Promotion gate

H2-D-3 passes only if both dates complete with exact immutable parity, exact
receipt correlation, zero duplicate rows/identities, no database lock wait or
timeout, and bounded resource use. Any mismatch stops the project at the
sequential runtime. Compute sizing, scaled replay, and production scheduling
remain separate, later decisions.

Before the parity run, an integration test must send abrupt `SIGKILL` to the
coordinator while both stage process groups are active. It must prove both
guardians survive coordinator death long enough to freeze and kill their
cgroups; zero surviving descendant PIDs; `populated 0`; worker reaping before
shared-fence release; and that a replacement coordinator cannot acquire both
exclusive date fences until that ordered cleanup is complete. A separate
normal-completion test must prove the coordinator lock remains held until both
supervisors have persisted terminal cleanup receipts. Separate fault tests must
kill a guardian and must restart or fail over PostgreSQL so all three
advisory-lock sessions drop while both workers are active. In each case an
immediate replacement attempt must remain blocked by nonterminal durable state
until both workers and guardians are reaped, both cgroups report `populated 0`,
and both terminal receipts are fsynced. A two-coordinator failover race test
must prove the versioned compare-and-swaps allow only one generation to obtain
both supervisor claims; a split or partial claim starts no guardian. Unsupported
cgroup, `pidfd`, durable state, or supervisor semantics, an unreachable
supervisor, an orphan PID, early fence release, a nonempty cgroup, or any
old/new generation overlap permanently fails H2-D-3.

## Explicit non-goals

H2-D-2 adds no multiprocessing/executor/async runtime, CLI concurrency flag,
queue service, Render service or deployment, Supabase migration or compute-tier
change, evidence insert/update/delete/rewrite, replay execution, V9 mathematics
change, broker path, automatic retry, compute decision, or scaled replay.
