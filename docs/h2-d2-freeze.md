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
   authorized. This PostgreSQL advisory lock remains database-wide and is the
   cross-process and cross-host single-coordinator exclusion, including against
   an accidentally started contender on another host. Cross-host lock scope
   does not authorize cross-host execution. Before it can be accepted as the
   winning coordinator or acquire either date fence, the lock holder must prove
   that it runs on the one configured Linux execution host and in the one PID
   namespace identity pinned for that generation. Host identity is the
   configured machine identity plus Linux boot ID; PID-namespace identity is
   the device/inode identity of `/proc/self/ns/pid`. A missing, stale,
   unverifiable, or mismatched identity releases the global lock exactly once
   in `finally` and stops before supervisor admission.
4. After acquiring the coordinator lock, the same session must acquire both
   date-fence locks exclusively before creating any workload process:
   `pg_try_advisory_lock(-5133988379539764595)` for `2026-06-15` and
   `pg_try_advisory_lock(8459531074882316998)` for `2026-07-22`. Failure to
   acquire either releases every acquired date fence exactly once, releases
   the global coordinator lock exactly once in `finally`, and stops. This
   pre-claim path requires no new terminal receipt because no supervisor
   generation was changed. After acquiring both, it contacts the two exact,
   configured durable host
   supervisors pinned by the canary configuration digest. Each supervisor must
   attest a monotonic record version, terminal receipt identity, `CLEAN`, the
   prior worker and guardian reaped, and its fixed workload cgroup at
   `populated 0`; a missing, stale, malformed, unreachable, or nonterminal
   attestation stops. Each supervisor serializes admission and atomically
   compare-and-swaps that exact attested `CLEAN` version and terminal receipt
   to a fsynced `CLAIMING` generation record containing the next monotonic
   version, date, generation ID, commit, coordinator OS PID, coordinator
   procfs start-time ticks, database backend PID, host identity, and fixed
   cgroup path. A false compare-and-swap,
   stale version, or generation mismatch stops; every later transition is
   conditional on the exact predecessor version and generation. If fewer than
   two compare-and-swaps succeed, no fence handoff or guardian creation occurs
   and each partial claim must complete terminal cleanup before any later
   admission. A
   failure before the first supervisor compare-and-swap follows the same
   pre-claim unlock path and requires no new terminal receipt. Both fixed
   supervisors must run on that same configured Linux execution host and PID
   namespace as the winning coordinator. Here, independently supervised means
   separate durable OS processes and process/service failure domains, not
   separate hosts: each supervisor has its own fixed service identity,
   lifecycle, admission serialization, generation record, and workload cgroup.
   Each attestation and generation record must bind the configured host
   identity, current Linux boot ID, PID-namespace device/inode identity, and
   supervisor service identity. It must also bind the supervisor instance ID,
   supervisor OS PID and procfs start-time ticks, a monotonic heartbeat
   sequence, and the monotonic timestamp of the last fsynced heartbeat. The
   heartbeat is evidence of the fixed supervisor's liveness only; heartbeat
   age is never a lease, never transfers ownership, and never permits another
   coordinator or generation to proceed. A restarted fixed supervisor may
   recover its own service record only after its service manager has serialized
   admission and it has proved the recorded supervisor instance dead by exact
   `pidfd` readability plus matching procfs start-time ticks on the pinned host,
   boot, and PID namespace. Missing or ambiguous death proof leaves the record
   nonterminal and blocks admission. Any cross-host or cross-namespace
   combination fails closed. On any admission
   failure after the first successful compare-and-swap but before both guardian
   claim receipts, no worker may start. The coordinator retains the global lock
   until every changed supervisor has fsynced terminal cleanup, every created
   guardian has been reaped, and every unchanged supervisor re-attests the
   exact prior `CLEAN` version. It then explicitly unlocks and verifies every
   exclusive date fence still held by its control session exactly once before
   unlocking the global coordinator lock. A date fence already handed to a
   guardian must not be unlocked a second time. Only after both records are
   durable may the supervisors create exactly two claim-only date guardians
   outside the coordinator's process/service failure domain but on the same
   configured host and in the same PID namespace. The coordinator creates one
   distinct liveness pipe per guardian with `pipe2(O_CLOEXEC)`. The assigned
   read end reaches only the exact generation/date guardian, either directly
   over an authenticated local Unix-domain `SOCK_SEQPACKET` socket using
   `SCM_RIGHTS` after `SO_PEERCRED` and generation verification, or through
   exact allowlisted pre-spawn inheritance into that guardian. For the latter,
   only the assigned read descriptor may have close-on-exec cleared across the
   guardian exec boundary. The coordinator remains the sole write-end owner for
   both pipes; each exact guardian becomes the sole read-end owner for its pipe.
   The coordinator closes every read-end copy after verified delivery, and each
   supervisor closes every temporary pipe-descriptor copy immediately after
   verified guardian handoff. The other guardian, every worker, and every
   descendant must inherit neither end. Ambiguous peer identity, duplicate or
   cross-generation delivery, a leaked descriptor copy, or inability to prove
   this final custody stops admission. The coordinator unlocks each exclusive
   date fence exactly once only so the corresponding guardian can claim it in
   shared mode. No worker, stage, or provider call may begin during this
   handoff.
5. Each guardian must run on a Linux host with delegated cgroup v2 support for
   `cgroup.freeze`, `cgroup.kill`, and the `populated` field in
   `cgroup.events`; missing or unverified support stops before claim. The
   guardian opens its own session-pinned, read-only fence connection, acquires
   its date key with `pg_try_advisory_lock_shared`, verifies its own backend
   ownership through `pg_locks`, and verifies that the exact recorded
   coordinator backend PID still owns `8098937340306602170`. Before accepting
   its pipe or opening a process handle, it must independently attest the same
   configured host identity, Linux boot ID, and PID-namespace device/inode as
   the coordinator, both supervisors, the other guardian, and every process
   assigned to either worker cgroup. It then opens a `pidfd` for the exact
   coordinator OS PID: it calls `pidfd_open()` for the exact recorded
   coordinator OS PID, verifies its procfs start-time ticks against the
   generation record, and requires the resulting `pidfd` to be initially
   non-readable. Same-host and same-PID-namespace placement is what makes this
   local process identity check feasible; remote-PID interpretation is
   forbidden. Unsupported `pidfd_open()`, an invisible or already-dead PID,
   process-identity drift, or a host or PID-namespace identity that is missing,
   stale, unverifiable, or mismatched fails closed before claim. The guardian
   also verifies that it is the sole read-end owner of its assigned
   close-on-exec liveness pipe and that the coordinator is its sole write-end
   owner. The supervisor must then
   atomically transition and fsync its durable generation record from
   `CLAIMING` to `ACTIVE`. Only then may the guardian return a claim receipt.
   Both claim receipts are required before either guardian may create its
   single worker and issue a start signal. The generation record is independent
   of PostgreSQL sessions; only the fixed supervisor may change it, and any
   `CLAIMING`, `ACTIVE`, `CLEANING`, or unknown state blocks replacement
   admission.
   A fsynced `CLAIMING` record is supervisor-owned even if the coordinator dies
   before a guardian or liveness pipe exists. The fixed supervisor must watch
   the recorded coordinator identity from the first successful `CLEAN` to
   `CLAIMING` compare-and-swap. Before guardians exist, coordinator death is
   proved only by both (a) readability of an exact coordinator `pidfd` whose
   procfs start-time ticks matched the record when opened and (b) absence of
   the recorded backend's global advisory-lock ownership, checked through a
   new read-only observer session. A heartbeat timeout, observer error, PID
   reuse, or either proof alone is insufficient. Once both proofs hold, the
   supervisor atomically compare-and-swaps the exact generation and predecessor
   version from `CLAIMING` to fsynced `CLEANING`; this cancellation makes every
   late guardian creation or `ACTIVE` transition fail its predecessor CAS. It
   closes and accounts for every claim-time descriptor, creates no worker,
   proves the fixed cgroup `populated 0`, and within the frozen cleanup deadline
   fsyncs a terminal aborted-before-guardian receipt before changing the record
   to `CLEAN` as the last operation. Failure to prove emptiness, descriptor
   custody, owner death, or terminal fsync keeps the record nonterminal and
   blocks all replacement admission; no manual record edit, age-based reset,
   or later coordinator admission is authorized.
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
   same no-escape cgroup and the generation's pinned PID namespace. A
   parent-death signal or process-group kill alone is not accepted as proof of
   containment. The fixed persistent supervisor must run a deadline watchdog
   outside the guardian's process and failure domain; an independently
   supervised out-of-guardian watchdog with the same fixed service identity is
   acceptable, but a guardian thread, callback, timer, or child is not. Before
   worker authorization, that watchdog opens the exact guardian `pidfd`,
   verifies its procfs start-time ticks, and opens the generation's cgroup
   directory. Immediately after the worker is spawned and before any stage may
   start, it must also open the exact worker `pidfd` and verify that worker's
   procfs start-time ticks. It binds the generation ID, supervisor record
   version, host/boot/PID-namespace identity, and cgroup path plus filesystem
   device/inode identity. Missing, stale, ambiguous, or changed identity fails
   closed and leaves admission blocked. Before it creates a guardian, each
   fixed supervisor must call `prctl(PR_SET_CHILD_SUBREAPER, 1)`, verify the
   setting through `PR_GET_CHILD_SUBREAPER`, and remain the guardian's living
   ancestor for the generation. Missing subreaper support or ancestry proof
   stops admission. This makes the hung guardian's worker tree adoptable and
   waitable by that exact supervisor after guardian termination; `pidfd`
   signaling alone does not confer `waitid`/`waitpid` parentage. No guardian,
   worker, or descendant may
   use or inherit the coordinator connection or liveness-pipe write end.
7. A guardian holds its shared date fence from claim through terminal cleanup
   on success and every failure path while that database session exists. On
   normal completion it validates the final receipt, waits for worker exit,
   reaps the worker, and proves the workload cgroup is empty before it releases
   the shared fence exactly once and exits. After reaping the guardian and
   independently reproving `populated 0`, the supervisor atomically persists
   and fsyncs the terminal cleanup receipt and changes its generation state to
   `CLEAN` as the last operation. For a fully claimed generation, the
   coordinator retains the global advisory lock until both supervisors attest
   those terminal receipts. For a partial claim, it follows the terminal or
   unchanged-version and date-fence release rule in step 4. Only then does the
   coordinator release
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
   database connections at once during ordinary execution. A cleanup takeover
   permits at most one additional shared cleanup-fence connection per date,
   opened only after fsynced `CLEANING` and closed immediately after final reap
   and `populated 0`; it cannot execute replay queries or outlive terminalization.

The fixed coordinator advisory lock enforces fast-path single ownership across
processes and hosts connected to the evidence database. The selected execution
topology remains deliberately local: the winning coordinator, two independently
durable supervisor processes, two guardians, and both worker process trees are
one configured Linux host/one PID namespace per generation. The durable
supervisor generation records are the independent admission fence when database
sessions all disappear. Database primary keys and existing per-run advisory
locks remain the final row-integrity barrier; they do not replace the
coordinator/date-claim law. Manifest content includes performance fields, so two
simultaneous H1 writers for one date can safely conflict even when their
mathematics matches.

## Stage, generation, and failure contract

- Stage order is exact: `H1`, `H2B`, `H2C_RESOLVE`, then `H2C_SCORE`.
- The H2-D-3 configuration digest must pin a positive finite monotonic-runtime
  deadline for each named stage, a positive finite whole-date deadline covering
  the complete four-stage chain, and a positive finite cleanup deadline. The
  whole-date deadline is absolute from the guardian's start authorization and
  is not reset at stage boundaries; each stage deadline is absolute from that
  stage's start and is not extended by progress, restarts, subprocess output, or
  provider/database activity. The earlier of the current stage deadline and
  whole-date deadline always governs. A missing, zero, negative, non-finite,
  mutable, or unpinned deadline fails before either worker starts.
- Every provider/network/database call must have its own finite operation
  timeout no later than the governing stage/date deadline. Before the worker
  start authorization, the supervisor-owned out-of-guardian watchdog must
  durably record the whole-date absolute deadline. Before each stage launch it
  must durably record that stage identity and absolute deadline and acknowledge
  them to the guardian; a stage cannot launch before that acknowledgement. The
  watchdog uses its own monotonic clock and execution context and must remain
  able to enforce those deadlines when the guardian itself, a worker, provider
  SDK, database driver, launcher, process group, or descendant deadlocks or
  ignores cancellation. Deadline expiry
  irrevocably fails that generation; the same generation can never resume,
  restart, or be readmitted. Each guardian must publish authenticated,
  monotonically sequenced heartbeat and stage-progress records at the pinned
  finite interval. A missed heartbeat or progress bound is a permanent control
  failure signal, not a lease expiry and not authority for a new owner or
  generation. The persistent supervisor already owns cleanup authority: after
  revalidating the exact generation, predecessor version, guardian `pidfd`, and
  cgroup identity, it must within the pinned bounded takeover interval
  compare-and-swap `ACTIVE` to fsynced `CLEANING`. Uncertain identity or a false
  compare-and-swap fails closed with the durable state nonterminal and all
  replacement admission blocked.

  Once `CLEANING` is durable, the out-of-guardian watchdog enforces the cleanup
  deadline even while the guardian is alive and hung. Before terminating that
  guardian, the supervisor opens a dedicated session-pinned read-only cleanup
  fence connection, acquires the same date key in shared mode while the
  guardian still holds its shared fence, verifies its exact backend ownership
  through `pg_locks`, and records that handoff in the generation. The cleanup
  fence is not a new owner or generation; it only preserves the exclusion gap
  when guardian death closes the guardian-owned session. Failure to acquire or
  verify it leaves the workload frozen, the state nonterminal, and replacement
  admission blocked.

  With that cleanup fence held, the watchdog performs this exact order: freeze
  the exact workload cgroup; signal and `cgroup.kill` the worker tree if needed;
  terminate the hung guardian through its verified `pidfd`; reap the guardian
  through `waitid(P_PIDFD, ...)`; require the configured persistent subreaper to
  adopt the worker and descendants; perform final `waitid`/`waitpid` reaping of
  every adopted generation process; prove no generation child remains and
  `cgroup.events` reports `populated 0`; then unlock and verify the supervisor's
  cleanup fence exactly once. Only after that ordered fence release may it
  fsync the terminal deadline-failure receipt and perform the supervisor's
  final `CLEAN` transition. Guardian-session closure is not accepted as final
  fence release because the overlapping supervisor cleanup fence remains held.
  A process that has exited but is not wait-reaped is not terminal cleanup. No
  signal sent only by PID, cooperative cancellation, guardian acknowledgement,
  heartbeat age, or `populated 0` without wait-reaping is cleanup proof.
  Normal completion uses the same bounded
  kill-if-needed, reap, cgroup-empty, fence-release, and terminal-receipt path;
  it may not bypass cleanup merely because all four stage receipts validated.
- Expiration of the cleanup deadline does not authorize abandonment or a
  replacement generation. It is a permanent control failure: the durable
  record remains nonterminal, admission remains blocked, and an operator must
  repair containment without deleting, rewriting, or force-cleaning the
  generation record.
- Every stage receipt must return the claimed historical date and run ID. A
  missing or mismatched identity fails the date before the next stage.
- Every failed generation is irrevocably terminal and can never resume,
  restart, or be readmitted. There is no blind, timed, or automatic replay.
  Failure quarantines the date. Only if policy permits, an operator may later
  authorize a separate new generation with a new generation ID, a fresh
  supervisor compare-and-swap, and complete admission from the beginning. That
  new generation must replay the exact same date, run ID, job key, commit,
  runtime versions, configuration digest, dataset digest, session digest, and
  artifact hash. If any immutable input cannot be reproduced exactly, new
  generation admission fails before worker start. This separately authorized
  replay does not alter, reopen, supersede, or continue the failed generation.
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
`(cutoff_at, horizon)` order. Every key component is ascending. `cutoff_at` is
compared as a timezone-aware UTC instant. `quant_id` and `horizon` are encoded
as UTF-8 and compared byte by byte as unsigned octets, with a shorter exact
prefix sorting first. Database or locale collation must not participate. Thus
`q1`, `q10`, `q11`, `q12`, `q2` is the relevant ASCII prefix example, and the
six frozen horizons sort as `15M`, `1H`, `1M`, `30M`, `30S`, `5M`.

`scoring_hash_summary` alone is insufficient because it hashes admitted input
rows rather than the computed metric values. The current H2-D
`receipt_sha256` is also excluded from mathematical parity because it includes
elapsed timings and memory telemetry. Timestamps, stage timings, RSS,
`outcome_writes`, completion order, and the full operational receipt hash are
diagnostics only.

## Frozen canary sessions

The read-only baseline bundle is
`docs/h2-d2-canary-baselines.json`.
Its canonical numerical, evidence, lineage, count, receipt-correlation, and
metric-serialization values are pinned by focused contract tests. H2-D-2 does
not pin source-file hashes for the H1 runtime, quant families, or V9 modules.
Future harmless implementation edits therefore do not require a freeze update;
changes that alter the frozen behavior or exact numerical parity still fail the
canary gate.

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

A separate topology and descriptor-custody test must try a foreign host, a
foreign PID namespace, a stale Linux boot identity, a failed `pidfd_open()`, a
misdelivered read end, and a leaked supervisor/read/write descriptor copy. Each
case must fail before worker start. The success case must inspect the live
processes and descriptor tables and prove one configured Linux execution host,
one PID namespace identity, one coordinator-owned write end per pipe, one
corresponding guardian-owned read end, no supervisor pipe copy, and no inherited
worker or descendant pipe end. Passing these tests belongs only to a separately
approved H2-D-3 implementation; H2-D-2 still authorizes no runtime.

A separate pre-guardian recovery fault test must kill the coordinator after
each first and second fsynced `CLAIMING` compare-and-swap and before any
guardian exists. It must prove the durable supervisor owner identity and
heartbeat are bound, neither heartbeat age nor a single liveness signal permits
takeover, both coordinator-death proofs are required, late `ACTIVE` and guardian
creation lose their predecessor compare-and-swap, no worker starts, every
claim-time descriptor is closed, each cgroup is `populated 0`, the aborted
terminal receipt is fsynced, and replacement admission stays blocked until all
changed records are `CLEAN`. It must also restart one fixed supervisor during
that interval and prove exact prior-supervisor death and service admission are
required before the restarted instance may perform the same recovery.

Separate deadline fault tests must hang provider I/O, database I/O, a stage
launcher, a stage child, and an uncooperative descendant, and must deadlock both
before and after partial diagnostic output. They must also hang a guardian
while its worker remains live, stop guardian heartbeat and progress separately,
and keep the guardian alive past stage, whole-date, and cleanup boundaries.
They must exercise every named stage, the whole-date deadline, and normal
completion. Each expiry must irrevocably fail its generation with no
same-generation restart, resumption,
readmission, or next-stage start and must prove the exact
`CLEANING` → overlapping cleanup-fence claim → freeze → worker kill → guardian
pidfd termination/reap → subreaper adoption → final worker wait-reap →
`populated 0` → cleanup-fence release → terminal-receipt → `CLEAN` ordering.
The normal case must prove the same bounded
reap, empty-cgroup, fence-release, and terminal-receipt invariants without
changing any mathematical or evidence hash. The hung-guardian cases must prove
the supervisor-owned watchdog remains live outside the guardian, validates the
exact generation and cgroup, wins the exact predecessor compare-and-swap,
begins cleanup while the guardian is still unresponsive, proves the supervisor
was configured as the guardian's subreaper before admission, acquires the
overlapping cleanup fence before guardian termination, reaps the guardian so
the worker tree becomes adoptable, wait-reaps every adopted process before
`populated 0` and cleanup-fence release, and never treats heartbeat age as an
ownership lease. It must prove guardian-session closure alone never opens the
date fence. Wrong-generation, stale-version, reused-PID, replaced-cgroup,
missing-parentage, failed-adoption, failed-wait-reap, and unverifiable-identity
cases must remain nonterminal and block admission.

## Explicit non-goals

H2-D-2 adds no multiprocessing/executor/async runtime, CLI concurrency flag,
queue service, Render service or deployment, Supabase migration or compute-tier
change, evidence insert/update/delete/rewrite, replay execution, V9 mathematics
change, broker path, automatic retry, compute decision, or scaled replay.
