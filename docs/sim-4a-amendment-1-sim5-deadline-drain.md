# ATOM TRUE V9 — SIM-4A Amendment 1: SIM-5 Deadline Drain, Continuity Proof, and Ingress Observability

**Decision ID:** `ATOM-SIM-4A-AMENDMENT-1-SIM5-DEADLINE-DRAIN-1`  
**Status:** FROZEN ON OWNER-APPROVED MERGE  
**Effectivity:** Before merge this text grants no authority. At its Owner-approved merge commit it becomes controlling within the SIM-5 subject only, as an amendment to the freeze named below.  
**Amends:** `docs/sim-4a-exact-sim5-resolution-freeze.md` (`ATOM-SIM-4A-EXACT-SIM5-RESOLUTION-FREEZE-1`, file commit `4e6bd52`) — adds §3.1 and §9.1, restates one rule of §5; every other section is preserved exactly  
**Author of record:** ChatGPT Pro, adopting this Claude-prepared draft with one narrow correction to the §7 decision rule (relayed by the Owner, 2026-09-08). The Codex exact-head review findings on PR #328 — admission loss as an observation discontinuity, late registration, and the ingress heartbeat with minute-bucket completeness — are incorporated in §2, §3, §6 and §7. Owner approval of this exact text is the Owner's merge of the pull request that carries it.  
**Drafted by:** Claude at Owner request under `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B` §2 (delegated drafting; zero authority by itself; draft history: PR #327)  
**Implementation owner:** Claude, by explicit Owner assignment (2026-09-07) under `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1D`; Codex may be used as a resource  
**Change class:** documentation only  
**Base:** `main` at `9accee6056dfcd6a6ab06d7f538ce6e5b47ee4e9`; `quant/v9_sim4_worker.py` at file commit `6185991`; `quant/v9_sim5_resolution.py` at `479db09`; `migrations/031_create_v9_sim_resolutions.sql` as merged  
**Phase:** SIM-5 (active pointer unchanged)  
**Mode / symbol:** `PAPER_ONLY` / `COIN`, one `COIN_SHARE` — unchanged

## 0. Why — measured, on the one clean session

All figures are read-only reads of the isolated simulator project `mhexfuamuwhzmszvojre`, the Render worker `srv-dabgssvavr4c73852m3g` logs, and `main`. No protected statistic was computed.

SIM-5 on 2026-09-04, regular hours (`resolution_target_at` in 13:30–20:00 UTC): 630 terminal resolutions, **190 `RESOLVED` (30.2%)**, 440 `UNRESOLVED_OBSERVATION_GAP`, **0 `UNRESOLVED_WINDOW_EXPIRED`**. By UTC hour: 30.3 / 32.4 / 30.9 / 32.3 / 23.8%. Across all sessions since activation: 195 resolved, 548 unresolved, every unresolved row a gap.

Resolved exit lag (`exit_quote_accepted_at − resolution_target_at`): min 0.035 s, p25 0.30, p50 0.71, p75 1.27, max 1.97 s. Provider-event lag is the same to within 40 ms. Transit (`accepted_at − provider_event`) on every selected quote is 33–46 ms, p50 35 ms — admission is prompt and there is no clock-skew clipping.

Worker telemetry (`SIM4_FAIL_CLOSED` lines): `quote_queue_full` 1,874 at 13:30:07Z, 16,669 at 14:00:00Z, 20,775 at 14:11:56Z on instance `w6k6p`; after the 15:40Z redeploy to `3fcc672`, instance `mqhmh` shows 39 at 15:44:58Z, 1,482 at 19:55:01Z, 7,972 at 20:00:29Z. No `quote_queue_full` line at all during 17:00–17:01Z. `quote_invalid` reached 7 on `w6k6p` and 60 on `mqhmh`. No `quote_lock_contention` or `socket_failures` lines. `quote_admitted` is counted (`quant/v9_sim4_worker.py:549`, `:1294`) but never logged.

Three facts are established by the merged code, independent of any hypothesis:

1. **No deadline drain for resolutions.** `_ready_loop` terminalizes a pending resolution the moment the derived clock passes `deadline_epoch_ns` (`quant/v9_sim4_worker.py:2433–2438` → `_terminalize_due_resolutions`, `:2159–2196`). Quotes reach a pending resolution only when the owner thread drains them from the bounded FIFO (`_retain_admitted_quote` → `_offer_quote_to_pending_resolutions`, `:2061–2090`). Any quote with `accepted_at` inside the closed window that is still in the FIFO at that instant is never offered. The SIM-4 entry path does the opposite: strict-greater sample under the admission mutex, watermark, drain through the watermark, then decide (`_deadline_sample` `:1302–1310`, `_drain_through` `:2048–2059`; SIM-3B §6). SIM-4A §3 and §5 never said which model the resolver follows; the implementation chose the one without the drain.
2. **The continuity proof cannot succeed on the first connection.** `_sip_observed_continuously` returns `False` whenever the SIP streak began before the runtime anchor (`:1499–1523`, guard `streak_start_ns < anchor.monotonic_ns`). The receiver sets readiness and opens the streak back-to-back on its own thread (`:931–932`); the owner thread captures the anchor only after readiness (`:1443–1462`, `:1526–1537`). The streak therefore precedes the anchor in the normal startup order, and every deadline without a quote on that connection becomes `UNRESOLVED_OBSERVATION_GAP`. `tests/test_v9_sim5_resolution.py` (the `pre_anchor_entry` case) asserts exactly this outcome, so it is a design decision, not a slip. This is why 548 of 548 unresolved rows are gaps and `UNRESOLVED_WINDOW_EXPIRED` has never been written. SIM-4A §5 intends the opposite: a connection that has stayed open since before the window *is* the proof.
3. **The admitted-quote rate is unobservable.** Only the fail-closed counters are logged. Whether the resolver is starved by FIFO backlog at the deadline (fact 1), by `put_nowait` overflow (`SIM4_EVENT_QUEUE_CAPACITY = 256`, drop-incoming — frozen by SIM-3A §11.4), or by sparse delivery on the socket cannot be separated from persisted data. The lag shape above is consistent with roughly one admitted quote per 2–3 s reaching the resolver; the flat hourly rate and the drop-free minute at 17:00Z argue against overflow being the whole story.

What this amendment does **not** do, and why: it does not change the two-second window (`RESOLUTION_WINDOW_SECONDS = 2`, `quant/v9_sim5_resolution.py:53`; enforced again by migration 031 `atom_v9_sim_resolutions_window_check` and by `quant/v9_sim4_entry.py:805`). Widening it is a schema change with its own migration and record-contract consequences, and the measurement in §3 decides whether it is even the binding constraint. It does not change the event-queue capacity or overflow rule (SIM-3A law). It does not touch statuses, record fields, hashes, canonicalization, migration 031, roles, credentials, services, or sources.

## 1. Change 1 — Resolution deadline sampling and drain (adds §3.1 to SIM-4A)

The SIM-5 resolver adopts the SIM-3B §6 deadline model verbatim for every pending resolution:

1. The owner thread observes the resolution deadline by acquiring the admission mutex, reading `monotonic_now_ns` only after acquisition, comparing the derived instant with `resolution_deadline_at`, and, when strictly greater, snapshotting the last admitted sequence as the watermark before releasing the mutex. Equality is pending and schedules the existing bounded recheck.
2. It then drains every admitted envelope through that watermark, offering each drained quote to every pending resolution exactly as `_offer_quote_to_pending_resolutions` does today. A drained envelope with a sequence above the watermark is the existing generation failure.
3. Only after the drain completes does it classify: `RESOLVED` with the deterministic minimum `(accepted_at, provider_event_ns, quote_id)` among valid in-window quotes; otherwise §5's unresolved classification.
4. A quote whose `accepted_at` lies inside the closed window is a candidate whether it was drained before or after the wall-clock deadline. A quote admitted after the watermark cannot have `accepted_at` inside the window (admission stamps `accepted_at` under the same mutex, SIM-3B §6) and is excluded by construction.
5. Failure to complete the drain produces no terminal decision. The frozen restart rules then apply, and §5 already resolves unknown coverage as a gap.

When a SIM-4 entry deadline and a SIM-5 resolution deadline fall at the same derived instant, one sample/watermark/drain serves both; classification of resolutions precedes entry selection. The order is deterministic and must be tested.

Window bounds, exit side, causal floor, ordering tuple, return mathematics, hash, `resolution_id`, and the record's field order are unchanged. A `RESOLVED` record produced under this section is byte-identical in form to one produced today.

## 2. Change 2 — Continuous observation across the runtime anchor (amends §5)

Replace the second bullet's "or another provable observation discontinuity" reading with this exact rule:

Continuous authorized SIP observation over `[resolution_target_at, resolution_deadline_at]` is proven when one authenticated, subscribed WebSocket connection remained open — no disconnect, reconnect, stop, ownership loss, generation failure, or worker restart — from an instant at or before `resolution_target_at` through an instant at or after `resolution_deadline_at`.

A connection opened before the runtime anchor was captured counts as observed from the anchor instant onward. The anchor is the earliest instant the worker can express in UTC; observation before it is not claimed and not needed, because no window can be registered before the anchor exists. The implementation may capture the anchor before opening the streak, or clamp a pre-anchor streak start to the anchor; either way the guard that fails a pre-anchor streak closed is removed, and the test asserting `UNRESOLVED_OBSERVATION_GAP` for that case is replaced by tests for the outcomes in §6.

An open connection is necessary, not sufficient. Observation also requires that the worker admitted, and kept, every quote the connection delivered inside the interval. Each of the following is an observation discontinuity at its instant: an admission refused because the event queue was full or the admission mutex was contended (the SIM-3A §11.4 drop paths counted as `quote_queue_full` and `quote_lock_contention`), and an admitted envelope dropped from the quote buffer at capacity (`quote_buffer_full`). The worker records the derived instant of every such loss in a bounded, secret-free structure; an instant older than the retention bound below plus one second may be discarded, and if the bound is ever exceeded every window pending at that moment is treated as marked and every registration whose target precedes that moment has unproven coverage. Before classifying a window it marks the window if any admission-refusal instant lies inside the closed interval; a marked window with no admitted candidate is `UNRESOLVED_OBSERVATION_GAP`, never `UNRESOLVED_WINDOW_EXPIRED`, because the worker cannot prove the refused quote was not a valid exit. A marked window that holds a valid admitted candidate still resolves: §3's candidate set is, and always was, the admitted quotes, and a quote that was never admitted is not a candidate. A buffer-capacity drop cannot affect a resolution that was already pending when the envelope was drained — that envelope was offered to it first — and matters only to a resolution registered later, below.

Registration relative to the window. A pending resolution is normally registered at the durable `ENTERED` commit, before its `resolution_target_at`. SIM-1 bounds `eligible_at − cutoff_at` from below only, so registration may fall after `resolution_target_at`; the elapsed part of such a window was not being watched. At every registration the worker offers each retained quote-buffer envelope to the new pending resolution. Coverage of the elapsed part is proven only when the registration instant is within the quote-buffer retention bound of the target — registration minus `resolution_target_at` not greater than 2 seconds, so no in-window envelope could yet have been evicted — and no loss instant of any kind lies in `[resolution_target_at, registration]`. Otherwise the resolution's coverage is unproven and it terminalizes as `UNRESOLVED_OBSERVATION_GAP` at its deadline regardless of any quote offered afterwards, because an earlier valid exit may have been discarded and §3's first-quote rule could not be honored.

Everything else in §5 stands: startup after the interval began, restart, ownership loss, and any disconnect/reconnect inside the interval are gaps; unknown coverage is a gap; pre-activation windows cannot be reconstructed; both statuses are terminal evidence.

## 3. Change 3 — Ingress observability (adds §9.1 to SIM-4A)

The worker logs the existing `quote_admitted` counter with the same fixed-field, secret-free discipline as `SIM4_FAIL_CLOSED`: one line at every telemetry interval (`SIM4_TELEMETRY_LOG_INTERVAL_SECONDS`, 1.000 s) whether or not the value changed, of the form `SIM4_INGRESS status=<status> quote_admitted=<int> delta=<int>`, where `delta` is the change since the previous interval and may be `0`. Because it is unconditional, the line is also the ingress heartbeat: an interval with no line is a telemetry gap, and a minute of zero admissions is distinguishable from a minute the worker did not report. No new counter, no payload, no timestamp beyond the log's own, no configuration, URL, or exception text. SIM-3B §9's "every fail-closed event is observable through secret-free counters and logs" is extended to the success path so the admitted-quote rate per minute of regular hours becomes a number.

Purpose: with `quote_admitted` and `quote_queue_full` both logged, one session separates the three explanations in §0 fact 3 without touching the ledger.

## 4. Preserved exactly

- `resolution_target_at = cutoff_at + horizon_seconds`; `resolution_deadline_at = resolution_target_at + 2 seconds`; both bounds inclusive; provider-event and `accepted_at` both inside the window; strict post-entry causal floor.
- The three terminal statuses and their nullability rules; one resolution per `ENTERED` entry; idempotent replay; conflicting replay fails closed.
- `SimulationResolutionRecord` fields, order, constants, `canonical_sha256`, `resolution_id`; migration 031 and every constraint in it; `atom_v9_sim_entry_runtime` grants.
- Single existing SIM-4 worker, single Alpaca SIP data-only WebSocket, `SIM4_SUBSCRIPTION_PAYLOAD`, `SIM4_EVENT_QUEUE_CAPACITY = 256`, `SIM4_QUOTE_BUFFER_CAPACITY = 256`, the drop-incoming overflow rule, the admission mutex/sequence/`put_nowait` order, per-horizon advisory locks, horizon release only after durable insert, bounded six-entry recovery, `ATOM_V9_SIM5_ENABLED` gate.
- SIM-4 entry behavior, selection, and tests — untouched.
- No V9, family, E-1, E-2, E-3, Level-II, SIM-6, broker, account, order, or production path.

## 5. Implementation surface

After this amendment merges, exactly one implementation PR may change:

- `quant/v9_sim4_worker.py` — minimum integration for §1, §2, §3;
- `tests/test_v9_sim5_resolution.py` — tests in §6, including replacement of the pre-anchor assertion.

No other file. Not `quant/v9_sim5_resolution.py` (the window constant and record contract are unchanged), not `quant/v9_sim4_entry.py`, not any migration. If another file is required, stop `BLOCKED` and return to the author of record.

Implementation owner: Claude, by explicit Owner assignment under Amendment 1D (see header); Codex may be used as a resource. One owner through completion; independent final-head review by someone other than the implementer (Codex, Copilot PR review, or the Owner, per Amendment 1B); no self-review.

## 6. Required tests

- Drain: a quote admitted with `accepted_at` inside the window but still in the FIFO when the derived clock passes the deadline is selected; the resolution is `RESOLVED` with that quote, not unresolved.
- Watermark: a quote admitted after the watermark is not a candidate; a drained sequence above the watermark is the existing generation failure; deadline equality schedules the bounded recheck and produces no terminal decision.
- Determinism: two in-window quotes drained in either order select the same `(accepted_at, provider_event_ns, quote_id)` minimum.
- Shared instant: a SIM-4 entry deadline and a SIM-5 resolution deadline at the same derived instant use one watermark; resolution classification precedes entry selection; both outcomes are unchanged from separate handling.
- Continuity: streak opened before the anchor, window entirely after the anchor, no quote → `UNRESOLVED_WINDOW_EXPIRED`; window beginning before the anchor → `UNRESOLVED_OBSERVATION_GAP`; disconnect inside the window → gap; startup after the window began → gap; a reconnect that opens a new streak after the window began → gap.
- Admission loss: a queue-full refusal inside a window that holds no admitted candidate → gap; the same refusal outside every window leaves a quote-less window `UNRESOLVED_WINDOW_EXPIRED`; a refusal inside a window that holds a valid admitted candidate → `RESOLVED` with that candidate; a mutex-contention refusal is treated identically to a queue-full refusal.
- Registration: registration at or before the target is unchanged; registration after the target but within 2 s of it, with a valid in-window quote still retained in the buffer → `RESOLVED` with the first such quote; registration more than 2 s after the target → gap even when a valid quote arrives afterwards; registration within 2 s of the target with a buffer-capacity drop or admission refusal between target and registration → gap.
- Telemetry: the `SIM4_INGRESS` line is emitted at every interval including when `delta` is `0`, carries only the fixed fields, and can never contain configuration, URLs, payloads, exceptions, credentials, or tokens.
- Existing suite green; every SIM-4 entry test unchanged and green; SIM-5 disabled preserves SIM-4 behavior.

## 7. Merge, deployment, and acceptance

1. Implementation PR on the surface in §5; independent final-head review; required checks green; zero unresolved material threads; Owner merge.
2. No migration. No environment change. One deploy of the existing `atom-v9-sim4-worker` at the exact merged SHA, outside 09:25–16:05 ET on an XNYS session day.
3. Acceptance receipt after one complete regular session, as a documentation-only PR: `RESOLVED` share by horizon for regular-hours targets; `UNRESOLVED_WINDOW_EXPIRED` and `UNRESOLVED_OBSERVATION_GAP` counts; resolved exit-lag distribution; `quote_admitted` per minute (min, p50, p90) and `quote_queue_full` per minute over regular hours; the 2026-09-04 baseline (30.2%, 0 expired) beside each figure. Counts only — no return aggregates.

Minute buckets and completeness. Regular hours are the 390 one-minute buckets from 09:30:00 through 15:59:59 America/New_York on the session day, assigned by each log line's own timestamp. The per-minute admitted count of a bucket is the cumulative `quote_admitted` at the last `SIM4_INGRESS` line in that bucket minus the cumulative at the last line in the preceding bucket (for the first bucket, the last line before 09:30:00); a bucket in which the counter did not move contributes `0`. Complete telemetry means one worker instance for the whole session — no restart or deploy inside regular hours — and at least one `SIM4_INGRESS` line in every one of the 390 buckets. A bucket with no line is a telemetry gap, not a zero, and the ingress-rate threshold is then not met. The p50 is taken over the 390 per-minute values.

Decision rule, stated now so it cannot drift (narrowed by ChatGPT Pro on adoption, 2026-09-08):

This repair closes only when, on one complete regular session, both of the following hold: (a) the resolution-coverage threshold — `RESOLVED` share among regular-hours targets of at least 90% — is met at 30S and at 1M, each individually; and (b) the ingress-rate threshold — `quote_admitted` p50 of at least 5 quotes per second, i.e. at least 300 per minute over the 390 buckets — is met with complete telemetry as defined above.

Every other outcome remains diagnostic and does not authorize another change. Low ingress warrants investigation. High ingress with low coverage leaves the residual cause unexplained. Neither result independently authorizes widening the window, changing the SIM-3A queue or consumer, or any other change; each of those would require its own documentation-first amendment with its own measured basis, and any window change would also carry its own migration for `atom_v9_sim_resolutions_window_check`.

## 8. Not authorized

SIM-6, E-2, E-3, E-4, Level-II mathematical use, V9 or family changes, any change to the two-second window or migration 031, any change to SIM-3A queue capacity or overflow policy, a second market-data connection, new service/role/credential/source, broker/account/order/live-capital authority, any return-aggregate computation on the resolution ledger.

## 9. Frozen conclusion

> SIM-5 decides each resolution from the complete set of quotes admitted inside its closed two-second window — drained through a deadline watermark exactly as SIM-4 entries are — labels an empty window as expired only when one connection demonstrably covered it, no quote was refused or dropped inside it, and it was watched from its start, and as a gap otherwise; and it logs how many quotes it admitted, every second, so the next decision is made on a number.

**END — `ATOM-SIM-4A-AMENDMENT-1-SIM5-DEADLINE-DRAIN-1`**
