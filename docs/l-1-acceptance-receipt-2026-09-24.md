# L-1 — Evidence ledger throughput: acceptance receipt

**Controlling freeze:** `docs/l-1-evidence-ledger-throughput-freeze.md` (L-1), "Acceptance receipt": *"After the first two complete regular XNYS sessions with the gate active, one read-only SQL receipt reports, per session: p95 and maximum persist lag over regular-session cutoffs; the share of regular-session 30S and 1M rows with `persisted_at > target_endpoint`; and the same table as the Finding above. Both acceptance criteria must hold in both sessions."*
**Prepared by:** Claude, read-only, 2026-09-24 01:30Z, against `atom_v9_v4_forecasts` in the ATOM project (`afyiydxbjgzaiswnbcyj`). No write, no deploy, no gate change.
**Authority:** this receipt is the read-only artifact L-1 itself authorizes ("runs under this freeze whichever phase the pointer names at the time"). It adopts nothing and changes no law.

## Gate activation

L-1's implementation merged on 2026-09-02 (`b00328d`, `1fb7e89`) and reached `atom-v9-thin` with the 2026-09-03 13:58Z deploy. The next redeploy, 2026-09-05 04:40Z at the same commit with trigger `service_updated`, is consistent with the Owner setting `ATOM_EVIDENCE_LEDGER_BATCH_ENABLED=1` (L-1 order of work, step 3); Claude cannot read the service's environment, so the Owner confirms the gate value and date on merge. The verdict below does not depend on the exact activation date: no regular session since 2026-09-08 meets the p95 criterion.

## Measurement

Regular-session cutoffs only (09:30:00–15:59:59 ET). Persist lag is `persisted_at - cutoff_at` on 30S rows (one row per cycle; all six horizons of a cycle share `persisted_at`). "Late" is `persisted_at > target_endpoint`, the exact L-1 definition; a late row is never truth-credited (FREEZE law 4).

| Session | cycles | lag p95 | lag max | late 30S | late 1M | late 5M | late 15M | late 30M | late 1H |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-08 | 8,821 | 53.0 s | 71 s | 15.5% | 0.9% | 0.0% | 0.0% | 0.0% | 0.0% |
| 2026-09-09 | 8,653 | 9.2 s | 48 s | 0.8% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| 2026-09-10 | 9,107 | 62.9 s | 83 s | 18.3% | 7.5% | 0.0% | 0.0% | 0.0% | 0.0% |
| 2026-09-11 | 8,513 | 94.0 s | 176 s | 24.1% | 18.8% | 0.0% | 0.0% | 0.0% | 0.0% |
| 2026-09-14 | 11,017 | 353.6 s | 375 s | 35.8% | 33.4% | 11.7% | 0.0% | 0.0% | 0.0% |
| 2026-09-15 | 12,040 | 579.1 s | 610 s | 67.9% | 64.6% | 42.1% | 0.0% | 0.0% | 0.0% |
| 2026-09-16 | 12,160 | 382.0 s | 405 s | 56.1% | 43.8% | 16.9% | 0.0% | 0.0% | 0.0% |
| 2026-09-17 | 10,943 | 325.1 s | 354 s | 42.1% | 40.5% | 17.8% | 0.0% | 0.0% | 0.0% |
| 2026-09-18 | 13,421 | 590.8 s | 604 s | 60.7% | 48.0% | 33.5% | 0.0% | 0.0% | 0.0% |
| 2026-09-21 | 12,070 | 415.9 s | 426 s | 44.5% | 42.2% | 28.0% | 0.0% | 0.0% | 0.0% |
| 2026-09-22 | 11,266 | 433.2 s | 451 s | 40.9% | 38.5% | 27.6% | 0.0% | 0.0% | 0.0% |
| 2026-09-23 | 11,593 | 426.0 s | 438 s | 41.9% | 38.6% | 25.1% | 0.0% | 0.0% | 0.0% |

Reference: L-1's own baseline table (2026-08-28 → 09-02) showed peak lag 663–2,870 s and 41–100% late 30S rows. The gate improved the ledger (2026-09-09 is the best regular session on record) and did not bring it to the bar.

## Verdict

**FAIL.** Criterion 1 (p95 persist lag < 5.0 s over regular-session cutoffs): not met in any session; best 9.2 s (2026-09-09). Criterion 2 (30S and 1M late shares each < 5%): met only on 2026-09-09; the first two complete sessions after the inferred activation (2026-09-08, 2026-09-09) fail because 2026-09-08 is 15.5% late at 30S. Every later pair fails both criteria.

## What L-1 says follows

L-1, "Acceptance receipt": *"If either fails, the owner sets the gate to `0`, the result is reported, and L-1 stops; no further tuning, capacity change, or second mechanism is authorized under L-1."* This receipt is the report. The gate decision is the Owner's; Claude notes, without authority over it, that the sessions before the gate were worse than the sessions after it, and that the gate-off condition of L-1 was written for a mechanism that made things worse, not one that fell short.

`FREEZE.md`, "Clock-independence and continuous-evidence amendment": the bounded evidence outbox (`EVIDENCE_OUTBOX_CAPACITY = 256`) *"must be replaced by durable buffering and asynchronous draining under its own separately frozen phase."* That phase is the next authorized step for the ledger. A draft of it is proposed separately for Owner adoption under Amendment 1B; this receipt does not authorize it.

## Observed cause (informational, not part of the frozen receipt)

The regular-session cycle rate rose from ~8.8k to ~11.9k cycles per session on 2026-09-14 (+36%), reaching 0.55–0.76 cycles/s in the first two hours. The in-process ledger worker measures 1.68 s per cycle at p50 (`evidence_ledger_worker_latency_ms`, 2026-09-21), i.e. a ceiling near 0.6 cycles/s. Its own SQL executes in roughly 80–150 ms per cycle; the remainder is round trips and time spent waiting for the interpreter, which the same process uses for quote ingestion, the twelve families, V1–V4 (`complete_v9_cycle_latency_ms` p50 505 ms), the SIM-3 capture thread and the dashboard evidence refresh. The lag appears exactly when the cycle rate exceeds the ceiling (open and close) and clears by noon; it is a capacity problem of a single-process design, which is what the continuous-evidence amendment anticipated.
