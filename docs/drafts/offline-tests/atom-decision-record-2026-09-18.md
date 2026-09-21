# ATOM decision record — 2026-09-18

**Owner decision ("Go"), recorded by Claude. This is the Owner's operating decision, not ATOM law; it lives outside the repository unless the Owner puts it there.**

## What was measured (two weeks, read-only, all logged)

- Directional accuracy of the 11 families: 66 cells on 16 sessions of regular hours, non-overlapping windows — all between 45.6% and 59.0%, four beyond 2σ where chance gives three, nothing repeating across periods, the best cells duplicates of each other.
- Combined V9: 30S 50.1% (N 10,348), 1M 50.0% (3,121/3,121), 5M 50.5%, 15M 49.2%, 30M 53.5% (N 344), 1H 56.0% (N_eff 94, interval includes 50). No time-of-day, consensus or conviction cut adds anything.
- Two years of COIN minute bars, 68 pre-declared tests on the development partition: no positive test cleared |t| ≥ 3; one candidate (news-day morning continuation) at t 2.0–2.5 in-sample.
- Replay corpus: one solid cell (QQQ-factor family at 30 seconds, 52.4% on 8,553 windows, 11 of 11 sessions) — not observable live, and worth ~0.5 bps against ≥ 1.1 bps of spread.
- Volatility: COIN 30-minute realized variance is forecastable beyond persistence (out-of-sample R² 0.52 vs 0.38; QLIKE −21%).

## Decisions

1. **Direction research is closed.** No further SIM-5 amendments, no L-2, no E-2 look, no new directional families. The simulator keeps running only while the evidence writer does, at no further engineering cost.
2. **Two tests decide the program.** Both offline, both pre-registered before their data is opened, both single-look:
   - **Test A** — realized vs implied volatility on the Cboe EOD file (`prereg-A-realized-vs-implied-vol-v1.md`, runner `cboe_iv_study.py`).
   - **Test B** — news-day morning continuation on COIN's unseen 2021-04 → 2024-08 history (`prereg-B-morning-continuation-history-v1.md`, runner `history_study.py`, pull `alpaca_history_pull.py`).
3. **Kill criteria, set before the results.** Both tests FAIL → ATOM stops: cloud services suspended, repository and data kept, hours to Alliance War. A1 PASS and A2 PASS, or B1 PASS → that single program continues on a right-sized rebuild (one feed, one writer, one database, research offline first), not on the current stack and not under the current law process. B1 WEAK alone → paper test only if Test A passes. No other outcome extends ATOM.
4. **Cost.** Suspend Coin-market-api web and coin-v8-schwab-level2-worker; downgrade benchmark-210 to Micro or export and delete it. Keep atom-v9-thin, ATOM-matrix V4, the ATOM database and the SIM project until the tests are decided. Expected saving ≈ $90–100/month now, ≈ $370/month if the program stops.
5. **Law.** No new freeze, amendment or governance document is written for either test; they are outside ATOM. V1B proceeds only if Codex and the Owner can reach a receipt with zero new law; it is not on the critical path.
6. **Budget and time.** ≈ $490 (Cboe file) plus existing subscriptions; target four to six weeks from the Cboe file's arrival to both verdicts.

## Owner actions

- Re-order the Cboe DataShop Option EOD Summary with Calcs, underlying COIN, 2024-09-01 → 2026-08-31; place the CSV/zip in `research/cboe/`.
- Put the Alpaca key in the desktop environment (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`); run `alpaca_history_pull.py`, then `history_study.py` once.
- Render dashboard: suspend `Coin-market-api` (web, srv-d9g2leflk1mc739qk81g) and `coin-v8-schwab-level2-worker` (srv-d9p88sfavr4c73b1hgkg). Supabase dashboard: `atom-v9-benchmark-210` (ipnfiudkswcslzjhxkkt) → compute Micro, or export and delete.
- Approve both pre-registrations in writing; the code hashes at approval are the ones in `hashes_2026-09-18.txt`.
- Schwab re-login is no longer needed unless the program continues.

## Claude's standing role until the verdicts

Daily read-only numbers scan on request; no ATOM writes, no law, no deploys. Runs neither test — both run on the Owner's desktop with the Owner's data — and reads only the receipts.
