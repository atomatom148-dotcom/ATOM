# ATOM COIN Level II Durable Depth Capture Freeze

**Decision ID:** `ATOM-LEVEL2-DEPTH-CAPTURE-FREEZE-1`  
**Status:** FROZEN ON OWNER-APPROVED MERGE  
**Effectivity:** Before merge this text grants no authority. At its Owner-approved merge commit it becomes controlling technical law for this exact observer-only capture scope.  
**Author:** ChatGPT Pro, ATOM Chief Architect and Freeze Custodian  
**Scope:** COIN Schwab `NASDAQ_BOOK` observer lane only

---

## 0. Objective

Begin preserving causal COIN Level II Top-3 depth snapshots already received and normalized by the existing read-only Schwab observer lane.

The purpose is evidence preservation only. Current Level II publication is transient and cannot produce a historical dataset suitable for later research. This freeze authorizes durable capture only. It authorizes no mathematical use of depth.

This observer-only capture may operate alongside the current E-1 scoring phase because it is not a quant-family, V9, SIM, or evidence-scorecard phase and has no consumer into those paths. It does not move the active E-1 pointer and does not authorize E-2, E-3, E-4, SIM-5, SIM-6, or S3.

---

## 1. Source Boundary

The only permitted source is the existing authorized Schwab COIN `NASDAQ_BOOK` observer lane.

The existing normalized source contract remains:

- symbol;
- provider timestamp;
- receive timestamp;
- exactly three bid levels;
- exactly three ask levels;
- price;
- size;
- count; and
- existing source-sequence identity where produced by the current observer implementation.

No additional market-data source is authorized.

---

## 2. Persistence

Create exactly one new isolated append-only table for Level II depth capture.

Each durable record represents one accepted normalized Top-3 snapshot and stores only:

- `symbol`;
- `provider_epoch`;
- `received_at_epoch`;
- `source_sequence`;
- bid level 1 price, size, count;
- bid level 2 price, size, count;
- bid level 3 price, size, count;
- ask level 1 price, size, count;
- ask level 2 price, size, count; and
- ask level 3 price, size, count.

No derived imbalance, signal, score, prediction, direction, probability, expected return, family output, V9 output, or trade output may be stored by this phase.

---

## 3. Append-Only Law

The table is immutable after insertion.

The authorized runtime may insert accepted snapshots and perform only the minimum reads required for deterministic verification.

The runtime may not `UPDATE`, `DELETE`, or `TRUNCATE` this table. Mutation rejection must be enforced at the database boundary, not only by application convention.

No historical rewrite, replacement, deletion, or backfill is authorized by this freeze.

---

## 4. Observer-Only Isolation

Persisted Level II depth remains observer-only and may not enter:

- Q5;
- any Q1-Q12 family;
- V2;
- V3;
- V4;
- eligibility;
- aggregation;
- forecasts;
- outcomes;
- Truth credit;
- E-1 scoring;
- SIM;
- broker logic;
- execution logic;
- position sizing;
- trade selection; or
- any live-capital path.

No existing quant mathematics change.

Q5 remains `top-book-imbalance-v1`.

No Top-3 mathematical successor is authorized.

S3 remains unauthorized.

---

## 5. No Research Promotion

This phase captures data only.

It does not authorize testing whether depth predicts returns, changing a family using depth, building a depth signal, calculating a production imbalance factor, changing V9, changing E-1, changing E-3, changing simulator behavior, or promoting Level II into a forecasting input.

Any such use requires a later separate preregistered freeze and new evidence lineage where applicable.

---

## 6. Capture Semantics

Persistence attaches only to an already-valid normalized Level II snapshot.

The capture path may not loosen source validation, symbol validation, freshness, causal timestamp validation, ordering, duplicate detection, three-level completeness, or observer isolation.

A snapshot rejected by the existing Level II normalization/publication boundary must not become valid merely because durable capture exists.

---

## 7. Publication and Capture Independence

The existing transient observer publication remains unchanged.

Durable storage is an additional observer sink, not a replacement for the existing transient publication contract.

A persistence failure must be surfaced through deterministic health or receipt evidence, must not fabricate durability, must not route data into a quant path, and must not alter market mathematics.

No snapshot may be claimed durable unless its database commit succeeded.

---

## 8. Minimal Implementation Scope

Implementation may add only what is necessary for:

- the one isolated append-only table;
- least-privilege insert/read verification authority;
- serialization of the existing accepted normalized Top-3 object into that table;
- immutable mutation protections;
- deterministic duplicate handling sufficient to prevent accidental duplicate durable records;
- tests;
- capture health/receipts; and
- the smallest observer-lane integration needed to persist accepted normalized Top-3 snapshots.

Do not refactor surrounding Schwab, V9, family, evidence, simulator, UI, or broker code.

No new service is authorized. If the existing observer runtime cannot safely own this append-only capture without a new service or broader credential boundary, implementation returns `BLOCKED` for a separate decision.

---

## 9. Implementation Ownership

After this freeze is Owner approved and merged, one exact implementation job may begin beneath it.

The Owner or ChatGPT Pro must issue the job card naming exactly one implementation owner. Codex remains the default. If governance Amendment `ATOM-AI-ROLE-AUTHORITY-FREEZE-1B` is effective, Claude may instead be named implementation owner under that amendment.

No implementation begins from this document before its merge.

---

## 10. Required Deterministic Tests

Before activation, prove at minimum:

- only `COIN` is accepted;
- exactly three bids and three asks are required;
- price, size, and count survive persistence exactly;
- provider timestamp survives persistence exactly;
- receive timestamp survives persistence exactly;
- bid/ask ordering survives persistence exactly;
- duplicate handling is deterministic;
- older or invalid source events cannot overwrite newer history;
- `UPDATE` fails;
- `DELETE` fails;
- `TRUNCATE` fails;
- no Q5 invocation occurs;
- no family invocation occurs;
- no V2/V3/V4 invocation occurs;
- no forecast or outcome write is caused;
- no simulator write is caused;
- no broker/account/order endpoint is reachable through the capture path; and
- disabled capture preserves current behavior.

Every required check must be green.

---

## 11. Activation Gate

Implementation must be disabled by default behind one explicit Level II depth-capture gate.

Activation requires:

1. this documentation-only freeze merged;
2. implementation and migration completed beneath the exact job card;
3. final-head independent review;
4. every required check green;
5. database mutation protections proven;
6. exact deployed revision identified; and
7. explicit Owner activation approval.

Activation authorizes data capture only. It does not authorize S3 or research use of the captured history.

---

## 12. Acceptance Receipt

After activation during a regular XNYS market session, produce a deterministic receipt proving:

- exact deployed revision;
- source identity = Schwab `NASDAQ_BOOK`;
- symbol = `COIN`;
- first durable provider timestamp;
- last durable provider timestamp;
- advancing durable row count;
- exactly three bid and three ask levels per sampled record;
- append-only enforcement active;
- no UPDATE/DELETE/TRUNCATE runtime authority;
- no Q5/family/V4 consumer;
- no trading/broker authority; and
- no unexplained loss between snapshots accepted for durable capture and committed durable rows.

Any unexplained durability gap is `FAIL` or `INVALID`, not PASS.

---

## 13. Frozen Boundaries

This freeze grants only:

> Existing accepted COIN Schwab `NASDAQ_BOOK` Top-3 observer data -> one append-only historical table.

It does not authorize E-3, drift-adjusted benchmarking, S3, Q5 changes, V9 changes, family changes, a trading signal, or live trading.

---

## 14. Frozen Conclusion

> Preserve the COIN Schwab `NASDAQ_BOOK` Top-3 observer stream exactly through the existing normalized boundary. Store it append-only so future research has actual history. Do not calculate with it, promote it, feed it to Q5 or V9, or grant it trading authority. Capture first. Research later under a separate preregistered freeze.

**END — ATOM-LEVEL2-DEPTH-CAPTURE-FREEZE-1**
