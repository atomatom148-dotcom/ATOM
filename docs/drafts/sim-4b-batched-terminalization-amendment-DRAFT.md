# SIM-4B — Batched persistence of non-entering terminal decisions (DRAFT amendment)

**Draft status:** prepared by Claude at Owner request ("keep building ATOM") under Amendment 1B delegated drafting; zero authority until the Owner adopts it as author of record (1B §2.1) and merges it at its final path with the `AGENTS.md` pointer entry.
**Subject:** SIM-4 terminal-entry persistence throughput. Simulator work; `SIMULATION_FREEZE.md` and the merged SIM-3A/SIM-4A documents control everything this draft does not name.
**Amends, explicitly:** `docs/sim-3a-final-runtime-fence-addendum.md` §2, the list beginning *"For each terminal decision, on that same owner session: 1. begin the database transaction; 2. acquire the frozen per-horizon transaction advisory lock; …"*. Every other SIM rule — the two-second window, quote predicates, terminal precedence, existing-terminal idempotency, restart-gap and late-intent routing, the admission fence, single runtime ownership, one open position per horizon, append-only evidence, SIM-5 resolution — is unchanged.

## 0. Finding (measured, read-only, 2026-09-21 → 09-23)

Regular-hours intents arrive at 3–5 per second (six per V4 cycle). The worker persists each terminal decision in its own transaction on the owner session (lock settings, horizon advisory lock, existing-terminal read, occupancy read, insert, commit) and sustains about three terminal rows per second. It therefore cannot keep up in regular hours: on 2026-09-21, 72,138 regular-hours intents produced 70,276 `SKIPPED_WINDOW_EXPIRED`, 1,862 `SKIPPED_POSITION_OPEN` and 0 `ENTERED`; on 2026-09-23, 69,192 intents at 2.96/s were written a median of 2,996 s after publication with 3 `ENTERED`. Pre-market, at 1.9 intents/s, the same worker entered 421 of 36,882 (1.1%) with a median write lag of 17.6 s. Regular-hours entries by session: 901 (09-14), 363, 184, 165, 0 (09-18), 0 (09-21), 0 (09-22), 3 (09-23). No open entry is stuck unresolved; occupancy is not the cause. The frozen one-transaction-per-decision procedure, not a defect in it, sets the ceiling. This is the case AGENTS.md names: the frozen design cannot work as written at production intent rates, so it is presented as an amendment, not repaired.

Separately, while the evidence writer lags (L-1 receipt), publications reach the simulator minutes after cutoff at the open; SIM-4B does not fix that and does not claim to. It makes the simulator keep up with what it is given.

## 1. Decision

A terminal decision whose status is not `ENTERED` may be persisted together with other such decisions of the same horizon in one bounded transaction. `ENTERED` decisions keep the existing one-decision transaction unchanged.

| Frozen field | Exact value |
|---|---|
| Batch scope | decisions already determined by the unchanged precedence and admission-fence procedure as `SKIPPED_WINDOW_EXPIRED`, `SKIPPED_RESTART_GAP`, `SKIPPED_NO_TRADE`, `SKIPPED_UNAVAILABLE`, or collision candidates; never a decision that could become `ENTERED` |
| Batch size | `SIM4_TERMINAL_BATCH_ROWS = 64`, one horizon per batch |
| Transaction | begin; the same `SET LOCAL lock_timeout` / `statement_timeout` as today; acquire the frozen per-horizon transaction advisory lock once; read durable occupancy once under the lock; for each intent in `publication_seq` order: existing-terminal read (idempotent return), then the unchanged terminal precedence with that occupancy (a durable open position turns the row into `SKIPPED_POSITION_OPEN` with the same `blocking_entry_id` for every intent in the batch, exactly as sequential processing would); insert each record; commit once |
| Semantics | every intent still receives exactly one immutable terminal record with the identical status, hash, and identity it would receive under sequential processing; occupancy cannot change under the held lock, so the batch result equals the sequential result by construction |
| Failure | any error rolls back the whole batch; the worker then retries each intent of that batch singly under the existing procedure; batch failures increment `terminal_batch_failures`; nothing is skipped |
| Session | the same owner session and the same generation rules; a batch is one explicit bounded transaction returning the connection to autocommit as today |
| Telemetry | `terminal_batches`, `terminal_batch_rows`, `terminal_batch_failures` added to the fixed telemetry set; no dynamic labels |
| Acceptance | on the first two complete regular XNYS sessions after deployment, each separately: terminal-row write lag (`created_at - publication_at`) p95 `< 5.0 s` over regular-hours intents; `SKIPPED_WINDOW_EXPIRED` share of actionable regular-hours intents `< 10%`; at least one `ENTERED` per horizon per session; zero duplicate terminal records; zero entries whose status differs from the sequential rule (checked by a read-only replay of the day's decisions) |
| Rollback | redeploy the previous commit; no schema, role, or data change to undo |

## 2. Implementation surface (after adoption, one PR)

`quant/v9_sim4_worker.py` (batch collection and the batch transaction), `quant/v9_sim4_entry.py` (`terminalize_batch_in_transaction`, reusing the existing record builder, existing-terminal read, occupancy read, and insert; no change to `terminalize_in_transaction`), `tests/test_v9_sim4_entry.py` (batch store tests), `tests/test_v9_sim4b_batched_terminalization.py` (new). No migration, schema, role, credential, contract, hash, canonicalization, SIM-5, web, or production change. Any other file is `BLOCKED`.

## 3. Required tests

Batch result equals sequential result for every status mix, including occupied and unoccupied horizons and pre-existing terminal rows; one lock acquisition per batch in the frozen horizon order; batch never contains a decision eligible to enter; rollback-and-retry-singly on any failure; idempotency of a replayed batch; `publication_seq` ordering inside the batch; telemetry counters; the worker's per-intent path unchanged when a batch has one member; SIM-5 registration unaffected; full existing suite green, including every isolation and void-return test.

## 4. Order of work

1. Owner adopts this text (final path `docs/sim-4b-batched-terminalization-amendment.md`; pointer entry in `AGENTS.md`) under the freeze merge gate.
2. Implementation PR, independent final-head review, green required checks, Owner merge.
3. Deploy `atom-v9-sim4-worker` at the merged SHA (the existing worker; no new service).
4. Acceptance receipt after two complete sessions; on FAIL, redeploy the previous commit and report.

## 5. Claude's recommendation to the Owner (not part of the amendment)

Two to four days of work. Without L-3 it restores the simulator only when the ledger keeps up (mid-session and extended hours) and for the longer horizons; with L-3 it restores it fully. Adopt it only if the simulator's evidence is worth having, which the Owner's 2026-09-18 decision said it is not on its own.
