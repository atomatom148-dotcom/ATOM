# L-3 — Durable evidence outbox and asynchronous drain (DRAFT freeze)

**Draft status:** prepared by Claude at Owner request ("keep building ATOM") under Amendment 1B delegated drafting; zero authority until the Owner adopts it as author of record (1B §2.1) and merges it at its final path with the `AGENTS.md` pointer entry. Nothing here is implemented, deployed, or authorized by this draft.
**Phase:** L-3 (evidence ledger operations; the phase the continuous-evidence amendment names: *"the bounded evidence outbox … must be replaced by durable buffering and asynchronous draining under its own separately frozen phase"*).
**Amends, explicitly:** `FREEZE.md` derived-state worker amendment, sentence *"The live web runtime remains the sole market, forecast, outcome, and evidence writer"* — see §3. Every other freeze is unchanged.
**Prerequisite:** the L-1 acceptance receipt (FAIL) is merged. L-1 stops per its own terms; L-3 is its successor, not a second L-1 mechanism.

## 0. Why this phase exists

The L-1 receipt shows regular-session persist lag p95 of 325–591 s on every session since 2026-09-14 and 36–68% of 30S rows written after their horizon matured. The ledger worker is a thread inside `atom-v9-thin`, sharing one interpreter with quote ingestion, twelve families, V1–V4 (505 ms per cycle at p50), the SIM-3 capture thread and the dashboard refresh. It measures 1.68 s per cycle against a regular-session cycle rate of 0.55–0.76/s at the open; its own SQL is roughly 0.1 s of that. The in-memory outbox (`EVIDENCE_OUTBOX_CAPACITY = 256`) is the evidence-loss mechanism the continuous-evidence amendment already condemns. L-1's batching helped (41–100% of 30S rows late before it, 36–68% since 2026-09-14) and cannot reach the bar; L-1 forbids further tuning under L-1.

## 1. Decision

Evidence persistence leaves the web process. The web process durably enqueues each accepted cycle; a separate single drain process persists it with the existing, unchanged ledger logic. No mathematics, identity, hash, eligibility rule, proof, ordering rule, cadence, or failure disposition changes. Law 4 is untouched: a row committed after its horizon matures is still never credited. What changes is that no accepted cycle is ever dropped, and the writer no longer competes with the hot path for the interpreter.

| Frozen field | Exact value |
|---|---|
| Queue table | `public.atom_v9_evidence_outbox` in the existing ATOM project only |
| Queue row | `sequence bigint PRIMARY KEY` (the existing `QuoteEvidenceWork.sequence`), `cycle_id text NOT NULL`, `received_at timestamptz NOT NULL`, `payload jsonb NOT NULL` (exact canonical serialization of the `QuoteEvidenceWork` item, §2), `payload_sha256 text NOT NULL`, `enqueued_at timestamptz NOT NULL DEFAULT now()`, `drained_at timestamptz NULL`, `drain_result text NULL` |
| Queue writer | `atom-v9-thin` only, role `atom_v9_v4_runtime`, `INSERT` only |
| Drain process | one Render background worker `atom-evidence-writer`, command `python -m quant.evidence_drain_worker`, Starter plan, region `oregon`, same repository and branch `main`, Auto-Deploy Off; role `atom_v9_v4_runtime`; it is the only process that runs `EvidenceLedgerWorker.process` when the gate is on |
| Ownership | the drain process holds the existing evidence runtime-owner session lease; the web process holds no ledger lease and accepts quotes whenever its durable enqueue is available; the handoff-anchor contiguity check moves with the worker and is evaluated against the durable sequence, not process memory |
| Gate | `ATOM_EVIDENCE_DURABLE_OUTBOX_ENABLED`; active only when exactly `1` on both services; default off is byte-identical current behavior |
| Enqueue bound | the hot path performs one non-blocking hand-off to a dedicated enqueue thread; that thread writes rows in arrival order in batches of at most 64 and confirms durability within 1.0 s of acceptance at p99; the in-memory hand-off buffer is 4,096 items and its overflow is counted, never silently dropped: on overflow the web process marks evidence ingress `UNAVAILABLE` until the buffer drains below 2,048, so no observation is accepted that cannot be made durable |
| Drain order | strictly ascending `sequence`; one item at a time; `process` semantics unchanged, including the SIM-3 Stage-B submit, the V4 state-build submit, and the cache refresher, which move to the drain process with it |
| Exactly-once | `drained_at` is set in the same transaction as the item's last ledger commit; a restart re-reads the smallest undrained sequence; a replayed item is idempotent through the existing duplicate-conflict rules |
| Retention | drained rows may be deleted by the drain process only, only when `drained_at < now() - interval '7 days'`; undrained rows are never deleted |
| Migration | `migrations/034_create_v9_evidence_outbox.sql`: table, index on `(drained_at, sequence)`, `INSERT` for `atom_v9_v4_runtime`, `UPDATE (drained_at, drain_result)` and `DELETE` for the same role, nothing else; no other table, role, grant, or policy changes |
| Acceptance | the L-1 bar, judged on the first two complete regular XNYS sessions with the gate on, each separately: p95 of `persisted_at - cutoff_at` over regular-session cutoffs `< 5.0 s`; regular-session 30S and 1M rows with `persisted_at > target_endpoint` each `< 5%`; plus zero sequence gaps and zero undrained rows older than 60 s at session close |
| Cost | one Starter worker, $7/month; no tier change to any database or existing service |

## 2. Serialization

`QuoteEvidenceWork` and its members (`MidpointObservation`, `RawForecastRecord`, `VolatilityForecastRecord`, `V4ForecastRecord`, `V4DCycleOutput`, `state_cohort_id`) serialize through the frozen V4A canonicalization (`quant.v9_v4a_evidence._canonical` / `canonical_sha256`), unchanged. Deserialization rebuilds the exact frozen objects and re-verifies every carried record hash and `payload_sha256`; any mismatch fails the item closed with `drain_result = MALFORMED` and stops the drain (it does not skip forward). Serialization must be proven by round-trip tests over live-shaped fixtures for all six horizons, `PROVISIONAL` and `UNAVAILABLE` cases, and `v4d_output = None`.

## 3. Law amended

`FREEZE.md`, derived-state worker amendment, currently: *"The live web runtime remains the sole market, forecast, outcome, and evidence writer."* On adoption it reads: *"The live web runtime remains the sole market-data acceptor and the sole producer of forecast, outcome, and evidence items. Under L-3 those items are made durable in the evidence outbox by the web runtime and are written to the ledger by exactly one drain process holding the evidence runtime-owner lease; when the L-3 gate is off, the web runtime writes the ledger itself as before."* No other sentence of `FREEZE.md` changes. Permanent laws 1–10 are unchanged; the drain process is not a second brain, computes nothing, and receives no truth credit.

## 4. Implementation surface (after adoption, one PR)

May change only: `migrations/034_create_v9_evidence_outbox.sql` (new); `quant/evidence_outbox.py` (serialization of `QuoteEvidenceWork`, durable enqueue thread, drain loop; the `process` method is not edited); `quant/evidence_drain_worker.py` (new process entry point); `quant/web.py` (composition only: construct the durable enqueue under the gate, do not start the in-process ledger worker under the gate, evidence-ingress availability tied to the enqueue buffer); `quant/live_market.py` (only the acceptance-ready callable changes source under the gate); `tests/test_l3_durable_outbox.py` (new). Any other file is `BLOCKED`.

## 5. Required tests

Round-trip and hash verification (§2); gate off is byte-identical (existing suite unchanged); enqueue order equals sequence order; overflow marks ingress unavailable and never drops; drain is strictly ascending and exactly-once across a simulated restart; a malformed row stops the drain; `process` is invoked with objects equal to the originals; SIM-3 Stage-B and state-build submits occur from the drain process only; the web process never runs `process` under the gate; lease held by the drain process only; retention deletes only drained rows older than 7 days; full existing suite green.

## 6. Order of work

1. Owner adopts this text (final path `docs/l-3-durable-evidence-outbox-freeze.md`, pointer entry in `AGENTS.md`) under the freeze merge gate.
2. Implementation PR (Claude under Amendment 1D, or Codex), independent final-head review, green required checks, Owner merge.
3. Migration 034 applied once to the ATOM project.
4. Create `atom-evidence-writer` in Render exactly as frozen; deploy both services at the merged SHA with the gate on `atom-evidence-writer` first, then on `atom-v9-thin`, outside regular hours, only when the current in-memory outbox is drained (the L-1 restart restriction applies until this phase is accepted).
5. Acceptance receipt after two complete sessions. On FAIL: gate to `0` on both services (byte-identical fallback), report, stop.

## 7. Not authorized

Any change to V9 mathematics, families, cadence, proof eligibility, evidence identities or hashes; any second drain process; any queue outside the ATOM project; any new role or credential (the existing runtime role is reused); any database tier change; any SIM, E-, V-, G-, HIST8 change; any broker or trading path.

## 8. Claude's recommendation to the Owner (not part of the freeze)

This is the only fix with a credible path to the bar; it is also two to three weeks of implementation and review on a program whose direction research the Owner closed on 2026-09-18. Adopt it if the program continues (a test passes, or the Owner decides the live ledger is worth keeping regardless); otherwise leave it unadopted. Adopting it does not cause the work; the implementation PR does.
