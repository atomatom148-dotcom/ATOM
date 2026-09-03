# L-2 state cache read reduction phase

**Status:** DOCUMENTATION-ONLY ADOPTION CANDIDATE. Prepared by Claude at Owner request under `AGENTS.md` "Freeze-author continuity and delegated drafting." ChatGPT Pro is author of record for the adopted architecture. Zero controlling authority until independent final-head review, green required checks, and Owner merge.

**Supersedes:** `l-2-evidence-drain-capacity-phase-DRAFT.md` (v1). The title changed because the study found the bottleneck is not the outbox.

**Current runtime:** `atom-v9-thin` at `2fa3d517f85a52aea082e2e036a05225f59fb37a`.

## Owner decisions recorded 2026-09-03

- `ATOM_EVIDENCE_LEDGER_BATCH_ENABLED` **stays at `1`**. The Owner explicitly supersedes the L-1 gate-to-`0` failure step. L-1 batching is retained.
- **O1 — pointer:** L-2 runs alongside SIM-5. SIM-5 keeps the active-phase pointer. L-2 touches no SIM file and no simulator boundary.
- **O4 — reviewer:** Copilot's PR reviewer is the independent final-head reviewer for Claude-authored work.
- **O3 — author of record:** ChatGPT Pro is author of record; Owner approval/merge makes the document effective.
- **O5 — lost evidence:** the missing 30S/1M rows are permanent operational evidence loss/failure evidence. No backfill, reconstruction, repair, re-scoring, or conversion of missing evidence into model losses is authorized.
- **O6 — today:** no interim L-2 production action is expected; L-1 batching remains enabled.
- **O7 — unbounded V4C state growth:** deferred to a separate future phase.
- **O8 — unstudied FIFO step:** study only if L-2 acceptance fails.

---

## 1. Finding

L-1 acceptance failed on 2026-09-03: p95 persist lag 87.1s against a `< 5.0s` gate; 48.3% of regular-session 30S rows and 17.5% of 1M rows persisted after their own `target_endpoint`; zero 30S outcomes written for any cutoff after 13:55:04 UTC. Detail in `l-1-interim-measurement-2026-09-03.md`.

**Root cause, located by read-only study of `quant/evidence_outbox.py` at `2fa3d517`.**

`EvidenceLedgerWorker.process` is the single serial FIFO. Its final step is:

```python
if self._cache_refresher is not None and item.state_cohort_id is not None:
    self._cache_refresher.refresh(
        symbol="COIN", cohort_id=item.state_cohort_id, cutoff=refresh_cutoff)
```

`V4StateCacheRefresher.refresh` calls `latest_json` on both the V4C compact store and the V4B accuracy store. Each `latest_json` executes:

```sql
SELECT state_id, state_hash, ..., state_json
FROM atom_v9_v4_states
...
ORDER BY state_as_of DESC, state_id DESC
LIMIT 2
```

The exact runtime implementations at `2fa3d517` were verified before adoption. Both use the same `WHERE`, parameter set, ordering, and `LIMIT 2`, and both fetch the full `state_json` payload.

Measured document sizes in `public.atom_v9_v4_states`:

| State version | Row size | Trend |
|---|---:|---|
| `ATOM_TRUE_V9_V4C_PROBABILITY_1` | **222,174 bytes** | 171,024 → 222,174 bytes over the 18 hours to 2026-09-03 16:00 UTC, monotonic |
| `ATOM_TRUE_V9_V4B_ACCURACY_1` | 11,392 bytes | flat |

So each cycle transfers and deserializes on the order of **450 KB** on the FIFO thread — two V4C documents plus two V4B documents. At regular-session cadence of approximately 44 cycles/min that is roughly **20 MB/min** of redundant transfer, and the payload grows every day because `CompactHorizonState.sorted_residuals` retains the full sorted residual list per horizon with no bound.

The cost is worse than transfer alone. The V4C path performs a full `json.loads`, canonical re-encode, SHA-256 verification over the re-encoded payload, reconstructs six `CompactHorizonState` objects, and each object's `__post_init__` re-validates the residual tuple ordering and finiteness. The V4B path likewise deserializes and independently re-hashes its full document. These operations occur repeatedly on the single FIFO writer thread.

**It is almost entirely redundant.** New states are published 20–30 times per hour (measured, `atom_v9_v4_states` insert counts). Cycles run about 2,600 times per hour. Approximately **99% of these reads re-fetch a document the cache already holds.**

This accounts for every observed feature:

- Baseline per-cycle cost of roughly 1.4–1.8s even outside regular hours, matching the measured 1.6–2.1s pre-open persist lag.
- Regular-session arrival interval of about 1.36s/cycle — just under the per-cycle cost — so backlog accumulates from the open and never clears.
- Monotonic degradation session over session as the V4C document grows.
- Why L-1 helped but was not enough: L-1's four mechanisms reduced round-trip *count*. This is round-trip *payload* and repeated CPU validation, and L-1 explicitly left the cache refresh unchanged.

Indexes were checked and are not implicated: `atom_v9_v4_forecasts_due_idx (target_endpoint, forecast_record_id)` serves `_load_due`; `atom_v9_v4_forecasts_logical_key_idx` serves `_load_cycle_forecasts`; `atom_v9_v4_states_compatible_idx` serves `latest_json`.

**Scoping consequence.** The Sep 2 amendment anticipated replacing the lossy bounded outbox with durable buffering and asynchronous draining. That is not the fix for this defect. The outbox is not dropping items — `EVIDENCE_OUTBOX_FULL` is not the failure mode; the drain is slow because it re-reads and re-validates a large state document on almost every cycle. Durable buffering should be evaluated on its own merits later, not built to compensate for this.

## 2. Decision

L-2 authorizes exactly one thing: **stop re-fetching an unchanged state document on the evidence FIFO.** The published cache contents, statuses, ordering, and every mathematical value are preserved exactly. It is a read reduction. It is not an evidence change, a state change, or a threading change.

## 3. Exact authorized change

Two mechanisms and nothing else. Both are active only under the gate; with the gate off every existing code path executes unchanged.

| Frozen field | Exact value |
|---|---|
| Gate variable | `ATOM_V4_STATE_CACHE_PROBE_ENABLED` |
| Gate default | disabled; active only when the value is exactly `1` |

1. **Generation probe.** `V4CStateStore` and `AccuracyStateStore` each gain `latest_generation(*, symbol, cohort_id, requested_cutoff)`, which runs the existing `latest_json` row-selection statement with the identical `WHERE`, identical parameters, identical `ORDER BY state_as_of DESC, state_id DESC` and identical `LIMIT 2`, selecting the same metadata columns **except `state_json`**.

   `latest_generation()` may return only dispositions determinable without `state_json`:

   - `UNAVAILABLE`;
   - `STATE_CONFLICT`; or
   - `AVAILABLE_GENERATION` with `(state_id, state_hash, state_as_of)` for the selected generation.

   It does **not** claim `STATE_HASH_MISMATCH`, `STATE_DESERIALIZATION_INVALID`, or any other disposition that requires inspecting or deserializing `state_json`.

2. **Conditional refresh.** `V4StateCacheRefresher.refresh` first calls `latest_generation` on both stores. The fast path is allowed only when:

   - both probes return `AVAILABLE_GENERATION`; and
   - each probe's `(state_id, state_hash, state_as_of)` is byte-identical to the already-validated immutable document currently held by the corresponding `ImmutableStateCache`.

   If all conditions hold, `refresh` returns without fetching `state_json` and without republishing. Otherwise — including any probe exception, uncertainty, missing cached identity, unavailable/conflict result, or generation mismatch — the probe result is discarded and the existing full `latest_json` path runs exactly as today. `latest_json` remains the sole authority for document hash/deserialization validation and existing final statuses.

   On the full path, the existing `AVAILABLE` check, the `compact_key != accuracy_key` comparison, the `v4_state_pair.generation_mismatch` metric, both `set_status("v4_state_pair_status", ...)` calls, and both `publish` calls execute in the existing order.

Nothing else changes. In particular: no change to `LIMIT 2`, to `ImmutableStateCache.publish`, to the FIFO step order, to the threading model, to `OfflineStateBuildScheduler`, or to any state contents or hash.

**Implementation surface.** The implementation PR may change exactly:

- `quant/v9_v4c_predictive.py` — `latest_generation` only;
- `quant/v9_v4b_accuracy.py` — `latest_generation` only;
- `quant/evidence_outbox.py` — `V4StateCacheRefresher.refresh` and gate plumbing only;
- `quant/web.py` — reading and passing the gate only, exactly as it reads `ATOM_EVIDENCE_LEDGER_BATCH_ENABLED`;
- `tests/test_l2_state_cache_probe.py` (new) and minimal additions to existing tests.

**Required tests.**

- Unchanged generation: no `state_json` is fetched, no `publish` occurs, both caches are identical objects afterwards, and `v4_state_pair_status` is unchanged.
- Changed generation: the published `compact` and `accuracy` documents, their hashes, and the publish order are identical to the gate-off path.
- Probe `UNAVAILABLE` or `STATE_CONFLICT` falls through to `latest_json`, which reproduces the existing final disposition.
- Every existing final disposition reproduces byte-identically under the gate after fallback: `UNAVAILABLE`, `STATE_CONFLICT`, `STATE_HASH_MISMATCH`, `STATE_DESERIALIZATION_INVALID`, `GENERATION_MISMATCH`, the mismatch metric, and the case where only one of the two stores advances.
- Probe raises → full `latest_json` path runs → identical outcome.
- Missing or unvalidated cache identity → full `latest_json` path runs.
- Gate off → byte-identical existing behavior.
- Full existing suite green, including every SIM-3 test asserting unchanged ledger behavior.

**Expected effect, stated as a target and not a guarantee.** Per-cycle state transfer falls from roughly 450 KB to under 1 KB on approximately 99% of cycles, while also eliminating repeated JSON parse/re-encode/hash/object-validation work on those unchanged-generation cycles. Whether that alone returns p95 persist lag below `5.0s` at regular-session cadence is a measurement, not a promise. If it does not, the remaining cost is in `record_cycle_and_resolve` (see §8, O8) and belongs to a further phase.

## 4. Preserved exactly

- Record contents, canonical serialization, hashes, identities, cohorts, `contract_version`, `evidence_version`, `evidence_origin`.
- `MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS = 5.0`, `TARGET_TIMING_METHOD_VERSION`, the commit-proof function, method, table and `proof_eligible` rule, the resolution bracket rule, overlap selection, and all V4B / V4C / V4D mathematics.
- Every state document's contents, hash, `state_as_of`, and publication path.
- Exact-six commit before maturity; "Missing ≠ 0"; single runtime owner; single serial FIFO and its step order; `EVIDENCE_OUTBOX_CAPACITY = 256`; fail-closed behavior.
- The Family Evidence Cadence gate and every legacy ledger statement.
- Late rows stay unscoreable. **No backfill, repair, re-scoring, or reconstruction of any row, session, or state**, including the 30S and 1M operational evidence loss from 2026-09-01 through 2026-09-03. Missing evidence is never converted into directional/model losses.
- Every SIM-3, SIM-4 and SIM-5 boundary, tuple, and placement.

## 5. Acceptance

| Criterion | Threshold |
|---|---|
| p95 `persisted_at - cutoff_at` over regular-session cutoffs | `< 5.0s` |
| Regular-session 30S rows with `persisted_at > target_endpoint` | `< 5%` |
| Regular-session 1M rows with `persisted_at > target_endpoint` | `< 5%` |
| Window | the first two complete regular XNYS sessions after activation, judged separately |

Additionally required, because L-1's failure was invisible until a human read a dashboard: an automated signal when p95 persist lag crosses the shortest horizon. No resolver or drain log line was emitted during 37 minutes of total 30S resolution failure on 2026-09-03.

Failure disposition: report the result, leave the gate in whichever state produces the lower measured lag, return to the Owner. Do not revert to a slower path to satisfy a literal rollback instruction.

## 6. Order of work

1. Owner adopts this document under ChatGPT Pro authorship; independent final-head review by Copilot's PR reviewer; green required checks; Owner merges it as a documentation-only change.
2. One implementation PR by the active implementation owner — Codex by default, Claude automatically under effective governance when authorized. Independent final-head review by Copilot's PR reviewer, zero unresolved P1 or P2 threads, every required check green, Owner merge unless a later effective governance amendment expressly permits the active implementation owner to perform the merge after all mandatory gates pass.
3. Owner sets `ATOM_V4_STATE_CACHE_PROBE_ENABLED=1` on `atom-v9-thin`. One authorized deploy of the merged commit to `atom-v9-thin` only, only when the evidence outbox is confirmed drained and restarting the sole writer discards no accepted evidence.
4. Acceptance receipt after two complete regular sessions.

## 7. What L-2 does not authorize

- No change to any mathematics, threshold, weight, family, synthesis, V1–V4 value, cohort, hash, proof rule, cadence rule, or resolution rule.
- No change to state document contents, the V4C state contract, or residual retention.
- No second ledger thread or process, no change to FIFO ordering, no relocation of any FIFO step off the FIFO.
- No outbox capacity change and no durable-buffering work.
- No migration, schema, index, function, trigger, role, grant, or policy change.
- No Supabase tier, region, pooler, or credential change.
- No Render plan, region, or instance-count change; no environment change beyond the single gate variable; no deployment other than step 3.
- No change to the V4 state worker, the dashboard, the E-1 scorecard, historical replay, or any simulator phase.
- No E-2, E-3, E-4, Level-II mathematical use, or V9 forecasting change.
- No broker, account, order, execution, or trading authority.

## 8. Deferred items

- **O7 — unbounded V4C state growth.** `CompactHorizonState.sorted_residuals` retains every residual with no bound; the document grew 171 KB → 222 KB in 18 hours and will keep growing. L-2 does not touch it because it is part of the frozen V4C state contract. It requires a separate ChatGPT Pro architecture decision.
- **O8 — unstudied FIFO step.** `PostgresEvidenceStore.record_cycle_and_resolve` in `quant/evidence.py` is the other per-cycle FIFO step and was not studied. Study it only if §3 does not clear the acceptance gates.

## 9. Exact-runtime verification

Before adoption, both `latest_json` implementations were verified directly at runtime commit `2fa3d517f85a52aea082e2e036a05225f59fb37a`.

`AccuracyStateStore.latest_json` and `V4CStateStore.latest_json` each select the full `state_json` together with generation metadata from `atom_v9_v4_states`, using their respective existing state/model constants, the same `symbol`, `cohort_id`, and `state_as_of <= requested_cutoff` predicates, `ORDER BY state_as_of DESC, state_id DESC`, and `LIMIT 2`.

The metadata-only generation probe authorized in §3 preserves those row-selection semantics but cannot and does not claim dispositions that depend on inspecting `state_json`.
