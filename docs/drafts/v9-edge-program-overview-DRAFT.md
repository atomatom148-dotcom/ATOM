# V9 Edge Program — Overview (DRAFT, zero authority)

**Draft status:** prepared by Claude at Owner request under `ATOM_AI_ROLE_INNOVATION_AUTHORITY_FREEZE_1B` delegated drafting. Nothing in this folder is law. Each document becomes controlling only when adopted by its author of record (ChatGPT Pro, or the Owner directly under 1B), independently reviewed on its final head, and Owner-merged as a documentation-only change, one phase at a time.  
**Date:** 2026-09-03  
**Purpose:** give ChatGPT Pro one package to review, reject, amend, or adopt.

---

## 1. The finding this program answers

Measured read-only over 8 sessions (2026-08-24 → 09-02), recorded in `docs/atom-findings-2026-09-02.md` and the official E-1 receipt:

- No directional edge in the twelve families at 30S–5M (49.8%–51.9% raw hit rates).
- Every apparent edge decomposed to drift: q10 at 5M is a long-bias proxy (89% long; mean signed return equals raw market move to three decimals); the dashboard's 73.2% at 1H collapses to ~54% across 56,804 rows against an always-short rule scoring 54.5%.
- V9's ensemble cannot exceed its best input, and its best input is drift.
- V9 *does* learn its own uncertainty: V4C kappa is MATURE at 30S (1.28) and PROVISIONAL at 1M/5M (1.10 / 1.44). Direction is fixed equations and never learns.
- Scored evidence was selection-biased toward quiet periods until L-1 batching went live on 09-02; ~20% of windows still die to the 5 s endpoint rule against a polled quote feed.

## 2. What follows

V9 gains edge only through (a) selectivity using what it already calibrates, (b) a new information source into Q5, or (c) removing drift proxies from the blend — never through more sessions, more families, or more averaging.

## 3. The four documents, in dependency order

| # | Draft | Type | Depends on | Authorizes if adopted |
|---|---|---|---|---|
| 1 | `e-1e-drift-adjusted-baseline-amendment-DRAFT.md` | E-1 amendment | E-1 receipt exists | three descriptive fields per cell; no classification change |
| 2 | `e-3-cost-model-freeze-DRAFT.md` | new phase E-3 | none (reads SIM-4 entry quotes already stored) | one read-only cost receipt; fixes `cost_bps(h)` for E-2 |
| 3 | `e-2-selectivity-hypothesis-preregistration-DRAFT.md` | new phase E-2 | 1, 2, ten clean sessions | one pre-registered hypothesis, pilot then confirmatory, evaluated once |
| 4 | `level2-depth-capture-amendment-1A-DRAFT.md` | Level II amendment | Owner decision (a) 09-03 | one observer worker service; capture only |

Family pruning (drift proxies out of V3) is deliberately **not** drafted: it changes cohort identity and restarts effective N, so it waits for the E-1 receipt over ten clean sessions and its own freeze.

## 4. Sequence

1. #292 SIM-4A merges (already open) — SIM-5 gives V9 its first bid/ask-priced paper scoring.
2. Adopt 1 and 2 — both read-only, both can run before the ten-session receipt.
3. L-1 acceptance (two clean sessions) and E-1 ten-session receipt (~09-17).
4. Adopt 3 — pilot window starts only after the ten-session receipt; the tail threshold is fixed from the pilot, then the confirmatory window is evaluated once.
5. Adopt 4 in parallel; depth accumulates for a later, separately preregistered S3 test.

## 5. Disclosure of what has already been examined

So that preregistration is honest: informal read-only queries on 09-02/09-03 examined family and V9 raw hit rates by horizon; long/short splits for q10 (5M) and V9 (1H); time-of-day buckets; per-session breakdowns; unscoreable shares; V4C calibration values. **No query has examined the signal-to-noise ratio `|μ|/(κσ)`, its distribution, or any tail statistic.** The E-2 hypothesis is therefore preregistered relative to the statistic it tests.

## 6. Not authorized by anything in this folder

Any change to Q1–Q12, V1–V4 mathematics, cohort identity, thresholds, weights, or family set; any use of Level II by a family or V9; S3; E-4; SIM-6; broker, account, order, or live-capital authority; any deployment.
