# ATOM V9 Thin — Phases

## Phase 0 — Empty baseline
New repo, FREEZE.md, new Render, empty DB. No old archive merge.

## Phase A — Contracts
Single owner, six horizons, short states, honest status tests, no broker.

## Phase B — Spine (main target)
Snapshot → UQ → exact-six commit → resolve → truthful status.

**Exit:** Loop is boringly reliable. Do not start C before this.

## Phase C — Optional evidence (one at a time)
- C1: simple vol/friction gate
- C2: minimal structure features
Stop after each.

## Phase D — Honest ops
Restart, stale, blocked-model, exact-six hydration tests. Reason codes on UNAVAILABLE.

## Phase E — Later
Calibration / Truth credit from eligible resolves only. Still no broker.

**Rule:** Quant pipeline first. Platform never.

## Read-only Schwab market-data phases

### S0 — Freeze amendment (complete)
Authorize only the isolated read-only source boundary. No code or deployment.

### S1 — Disabled backend worker (complete)
Add deterministic NDX, `NASDAQ_BOOK`, OAuth, freshness, deduplication, and
transient-publication contracts. The worker remains disabled by default. No UI
or quant-family input changes.

### S2A — NDX production activation (authorized)
After the controlling S2 activation freeze and deterministic bridge checks,
merge and deploy the read-only Schwab NDX bridge through the existing
independent NDX benchmark/display seam. Enable only with
`ATOM_SCHWAB_NDX_ENABLED=true`. Stale or invalid NDX must become honestly
unavailable. No V9 mathematics, evidence, Truth credit, broker, account, order,
execution, or trading authority changes are authorized.

COIN Level II proof is not a prerequisite for S2A and cannot block NDX
activation.

### S2B — COIN Level II market-hours proof (pending)
Level II remains observer-only and must pass its own separate regular-market-
hours proof. S2A success grants no Q5, family, V2/V3/V4, evidence, outcome,
Truth-credit, simulator, broker, account, order, execution, or trading use to
Level II.

### S3 — Optional Q5 successor
Only after sufficient causal Top-3 evidence, consider a separate freeze for a
new Q5 version and evidence lineage. S3 is not authorized by S0, S1, S2A, or
S2B.

**Rule:** S2A is authorized only through the existing NDX benchmark/display
seam. S2B remains a separate observer-only proof. Do not implement S3 early.

## Historical replay performance phases

### DB-0 — Baseline freeze (complete)

Freeze the production replay counts, content hashes, query plans, health, and
configuration before database work.

### DB-1 — Statistics (complete)

Keep append-only replay planner statistics current without touching evidence.

### DB-2 — Scoring index (complete)

Add only the approved concurrent index for the frozen scoring query shape.

### DB-3 — Proof run (complete)

Prove exact numerical parity and measure the optimized query on one certified
replay.

### H2-D-2 — Date-level parallel architecture freeze (complete)

Freeze whole-date process isolation, exactly two read-only workers, zero retry,
exact parity fields, and two certified canary dates. This phase is documentation
and contract tests only. Parallel execution remains disabled.

### H2-D-3 — Parallel Canary (complete)

Implement and run exactly two process-isolated date jobs under the H2-D-2
contract. No within-date concurrency or evidence writes. Exact parity is
mandatory. Passing does not enable scaled or scheduled replay.

### H2-D-4 — Compute decision (complete)

Use canary CPU, memory, database, provider, and wall-time measurements to decide
whether any Render or Supabase sizing change is justified. The recorded decision
is to keep both tiers unchanged; see `docs/h2-d4-compute-decision.md`.

### H2-D-5 — Scaled replay (complete)

Run one bounded four-date, read-only scale proof in two ordered batches of two
workers under `docs/h2-d5-freeze.md`. No scheduler, evidence writes, or tier
changes are authorized.

### H2-D-6 — Historical-persistence gate (complete)

The prior contract marker was “H2-D-6 — Historical-persistence gate
(implementation authorized).” The exact retry of the smallest H2-D-5 session
passed with zero forecast and outcome writes, unchanged pre/post evidence, and
exact least-privilege roles under `docs/h2-d6-persistence-gate-freeze.md`.
No new date or continuous replay is authorized by H2-D-6.

### H2-D-7 — One-session historical admission (complete)

The single `2026-07-24` / `h2d-2026-07-24` append-only admission passed
through the existing sequential certified replay, persistence,
outcome-resolution, and score-reader seams under
`docs/h2-d7-one-session-write-freeze.md`. Parallel and continuous replay
remain disabled.

### H2-D-8 — Two-session target qualification (freeze only)

Qualify at most two absent historical sessions from the fixed ordered candidate
set under `docs/h2-d8-target-qualification-freeze.md`. Qualification is
read-only and sequential. No admission, evidence write, scheduler, parallel
replay, continuous replay, tier change, or V9 change is authorized. Exact
targets require a separate narrow amendment before any write canary.

## Paper simulator phases

The simulator is an isolated downstream research path governed by `SIMULATION_FREEZE.md`. SIM-0A is documentation-only. Only SIM-1 becomes authorized after SIM-0A is merged, and no later phase may be implemented early.

### SIM-0 — Architecture freeze

### SIM-1 — Immutable contracts, identities, statuses, canonical serialization, and tests

### SIM-2 — Append-only persistence and least-privilege runtime role

### SIM-3 — Asynchronous immutable V4D forecast capture

### SIM-4 — Causal executable entry selection

### SIM-5 — Six-horizon causal resolution

### SIM-6 — Compact accuracy and P&L state

### SIM-7 — Read-only simulation page

### SIM-8 — Security, isolation, and freeze audit

### SIM-9 — Database-backed market-open acceptance

### SIM-10 — Continuous evidence operation

## Evidence scoring phases

Scoring is read-only research over existing evidence. Each phase is separate.
No phase in this section changes V9 mathematics, families, synthesis,
evidence, simulator behavior, or trading authority; any such change requires
its own freeze.

### E-1 — Read-only evidence scorecard (freeze only)

One single-process, read-only reader over FAMILY and V9 evidence with
statistics fixed in advance under `docs/e-1-evidence-scorecard-freeze.md`:
independent epoch-aligned windows, ties and abstentions excluded and reported,
hit rate with z, signed bps with t, correlation, magnitude calibration, an
echoed cost line, and `INSUFFICIENT` / `NOISE` / `CANDIDATE` labels with a fixed
`|z| >= 3.0` guard. Emits a receipt. Authorizes nothing.

### E-2 — Pre-registered single hypothesis (not authorized)

Freeze exactly one hypothesis — family set, combination rule, horizon,
evaluation sessions, pass/fail thresholds — before any further data is read,
with the E-1 receipt as baseline. Evaluate it once on the frozen sessions.

### E-3 — Cost model (not authorized)

Measure COIN realized spread and a fixed slippage assumption from existing
quotes only. Produces the `cost_bps` input for later phases.

### E-4 — Driver and universe candidates (not authorized)

Consider, each under its own freeze, one additional read-only driver or symbol
at a time. Nothing here is authorized by E-1, E-2, or E-3.

**Rule:** Score before changing. No family is retired, reweighted, or
sign-flipped on the strength of a scorecard alone.
