# Pre-registration B — COIN morning-move continuation on unseen history (2021-04 → 2024-08)

**Version 1 — 2026-09-18 — prepared by Claude for the Owner. Frozen at Owner approval; the code (`history_study.py`) is hashed before the history is pulled.**
**Runs on the home desktop, outside ATOM law.** One read of Alpaca historical bars with the Owner's key. Touches nothing in ATOM.

## 1. Origin of the hypothesis (disclosed)

Two exploratory sweeps on the development partition (2024-09-03 → 2026-02-27, 373 sessions; 68 tests, all logged in `edge_sweep_logbook.json` and `edge_sweep2_logbook.json`) produced one coherent candidate: on sessions with heavy morning volume, the direction of COIN's 09:30–12:00 move continued into 12:00–16:00. In-sample with the full-sample median: 74 qualifying sessions, +110 bps per trade net of 2 bps, t 3.67, hit 63.5%; all sessions +30 bps, t 2.5. Re-run with the real-time rule below (trailing 60-session median, first 60 sessions burn-in): 60 qualifying sessions, +62 bps, t 2.0, hit 55%, one-sided 95% lower bound +14 bps, and the 2026 slice (15 sessions) is −8 bps. The volume condition was chosen after seeing the magnitude decomposition, so every in-sample figure is inflated by selection. This study is the out-of-sample test on data nobody in this project has examined.

## 2. Data

- Alpaca SIP 1-minute bars, COIN and QQQ, 2021-04-14 (COIN listing) → 2024-08-30, regular session bar starts 09:30:00–15:59:00 ET, raw (unadjusted) prices. Pulled by `alpaca_history_pull.py`; SHA-256 and row counts written to `provenance_history.json` before analysis.
- Alpaca crypto 5-minute bars, BTC/USD, same dates, 09:00–16:10 ET only (secondary test).
- XNYS sessions from `exchange_calendars` (pinned version recorded in the provenance file). Early-close sessions and any session with fewer than 385 of 390 minutes are excluded and counted.

## 3. Rule under test (fixed)

- Morning volume `V_s` = sum of 1-minute volume, bars 09:30–11:59.
- Trailing median `M_s` = median of `V` over the previous 60 eligible sessions, exclusive of `s`. The first 60 sessions are burn-in.
- Qualify if `V_s > 1.5 · M_s`.
- Direction `d_s` = sign of `ln(close[11:59] / open[09:30])`; zero → skip and count.
- Position `d_s` from `close[11:59]` to `close[15:59]`. Return `p_s = d_s · ln(close[15:59] / close[11:59]) − 2.0 bps`.

## 4. Tests and decision rules

**B1 — primary (the rule).** Over qualifying sessions (expected ≈ 150–180): mean `p_s`, one-sided 95% bootstrap lower bound (10,000 draws, seed 20260918, sessions as the unit), hit rate. PASS if lower bound > 0 **and** mean ≥ 30 bps (half the honest in-sample size of 62 bps). WEAK if lower bound > 0 but mean < 30 bps. FAIL otherwise.

**B2 — secondary, reported.** Same position rule on all eligible sessions (no volume condition), ≈ 850 sessions: mean, lower bound, hit rate.

**B3 — secondary, reported.** Unabsorbed BTC overnight move: `sign(ln(BTC_09:30 / BTC_prev_16:00) − ln(open[09:30] / prev close[15:59]))` held from `open[09:30]` to `close[09:59]`, cost 2 bps, ≈ 850 sessions.

Diagnostics reported with no decision weight: B1 by calendar year; B1 with the top 5% of |morning move| sessions removed; share of P&L from the ten best sessions.

Outcomes: B1 PASS → a pre-registered forward paper test of the rule (one trade a day at most, no capital) is justified; B1 WEAK → paper test only if Test A also passes, otherwise close; B1 FAIL → direction research on COIN is closed. B2/B3 change nothing on their own.

## 5. Discipline

- One look at this history. The runner records the data hashes and its own hash in `receipt-B.json` and refuses to run again if the receipt exists.
- No parameter is tuned on this data. The 1.5× threshold, 60-session window, 12:00 split and 2 bps cost are fixed above.
- The validation and confirmation partitions of the Sep 10 study (2026-03-02 → 2026-08-19) are not used here and are released to Study A.

## 6. Owner actions before the run

1. Put the Alpaca key in the desktop environment (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`); the SIP plan already paid for covers the history.
2. Run `alpaca_history_pull.py` (≈ 10–20 minutes, ≈ 350 MB), then `history_study.py`. The runner prints the receipt.
3. Approve this text first. After approval the code hash is recorded.
