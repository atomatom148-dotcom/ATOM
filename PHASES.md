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

### S0 — Freeze amendment
Authorize only the isolated read-only source boundary. No code or deployment.

### S1 — Disabled backend worker
Add deterministic NDX, `NASDAQ_BOOK`, OAuth, freshness, deduplication, and
transient-publication contracts. The worker remains disabled by default. No UI
or quant-family input changes.

### S2 — Live source proof
After S1 verification, authorize and observe one Schwab connection. NDX may use
its existing independent seam; Level II remains observer-only.

### S3 — Optional Q5 successor
Only after sufficient causal Top-3 evidence, consider a separate freeze for a
new Q5 version and evidence lineage. S3 is not authorized by S0.

**Rule:** Only S1 becomes authorized after S0 is merged. Do not implement S2 or
S3 early.

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

### H2-D-5 — Scaled replay (implementation authorized)

Run one bounded four-date, read-only scale proof in two ordered batches of two
workers under `docs/h2-d5-freeze.md`. No scheduler, evidence writes, or tier
changes are authorized.

### H2-D-6 — Production gate (not authorized)

Require operational receipts, rollback, alerting, and numerical parity before
any continuous replay workload.

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

### SIM-9 — Database-backed market-open acceptance

### SIM-10 — Continuous evidence operation
