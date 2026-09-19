# Pre-registration A — COIN realized volatility versus option-implied volatility

**Version 1 — 2026-09-18 — prepared by Claude for the Owner. Frozen at Owner approval; the code (`cboe_iv_study.py`) is hashed before the Cboe file is opened.**
**Runs on the home desktop, outside ATOM law.** Reads the Cboe file and one local daily-close series. Touches no ATOM ledger, no Render or Supabase state, no freeze, and no V-1B look (nothing here uses Q3, V9 or any ATOM forecast).

## 1. Question

COIN's 30-minute realized variance is forecastable beyond persistence on two years of bars (HAR out-of-sample R² 0.52 vs 0.38, edge sweep 2026-09-15). That is worth money only if the forecast contains information the options market has not already priced. This study asks, once:

1. Does a realized-volatility (HAR) forecast add information about future realized variance beyond the implied variance of at-the-money weekly options? (necessary condition)
2. Does trading that difference through a variance-swap proxy earn a positive return after the option spread? (sufficient condition for a paper test)

## 2. Data

- Cboe DataShop "Option EOD Summary with Calcs", underlying COIN, 2024-09-01 → 2026-08-31 (the re-order of the cancelled Sep 4 order). Fields used: quote_date, expiration, strike, option_type, bid_1545, ask_1545, active_underlying_price_1545, implied_volatility_1545, open_interest. Nothing else.
- COIN daily regular-session closes: the 15:59 one-minute bar close from the legacy bar export (`bars/COIN_1m_rth.csv`, SHA-256 391240be…), which covers 2024-09-03 → 2026-08-19; sessions after that come from the same table if re-exported before the run, otherwise the study ends at 2026-08-19.
- XNYS session calendar from `calendar_manifest.json` (SHA-256 cba041db…).

## 3. Construction (fixed)

- **Decision days**: every Friday that is a session (or the last session of the week when Friday is closed). Let `t` be the decision day.
- **Target expiry**: the listed expiration that is the last session of the following week (normally the next Friday). If no options are listed for it, the decision day is skipped and counted.
- **ATM strike**: the strike nearest `active_underlying_price_1545` on day `t` for that expiry; ties go to the lower strike.
- **Implied variance**: `IV_t` = mean of the call and put `implied_volatility_1545` at the ATM strike; both must have `bid_1545 > 0`. Horizon `T` = number of sessions from `t+1` to expiry inclusive (normally 5). Implied variance over the horizon `IVar_t = IV_t² · T / 252`.
- **Realized variance**: `RVar_t` = sum of squared daily log close-to-close returns over the same `T` sessions (includes overnight gaps, as the option does).
- **HAR forecast**: computed on `t` from daily RV history only (`RV_d` = squared daily log return). Regressors: `log RV_{t}`, `log mean(RV_{t-4..t})`, `log mean(RV_{t-21..t})`; target `log RVar` over the next horizon. Fitted by OLS on an **expanding window** of past decision days; first forecast after 26 decision days of burn-in. No other specification is fitted.
- **Sample**: about 104 weekly, non-overlapping observations, of which about 78 carry a HAR forecast.

## 4. Tests and decision rules

**A1 — encompassing (necessary condition).** OLS of `log RVar_t` on a constant, `log IVar_t`, and `log HAR_t` over the forecast weeks. PASS if the coefficient on `log HAR_t` is positive with one-sided p < 0.05 (heteroskedasticity-robust standard errors; observations are non-overlapping). Also reported, not decisive: the variance risk premium `mean(log RVar_t − log IVar_t)` and its t-statistic; the same regression with `log IVar_t` alone (R²).

**A2 — economic value (sufficient condition for a paper test).** Each forecast week: if `HAR_t > IVar_t` take long variance, if `HAR_t < IVar_t` take short variance. Payoff in variance-return units `P_t = s_t · (RVar_t − IVar_t) / IVar_t`. Cost per week `c_t = 2 · (ask − bid) / mid` of the ATM straddle at 15:45 on day `t` (round trip, straddle relative spread; a straddle's price is proportional to σ, so this is conservative in variance units). Net `P_t − c_t`. PASS if the mean net is > 0 and the one-sided 95% bootstrap lower bound (10,000 draws, seed 20260918, weeks as the unit) is > 0. A margin filter of ±10% around `IVar_t` is reported as a diagnostic only.

Outcomes: A1 FAIL → the volatility program ends; the forecast knows nothing the market does not. A1 PASS, A2 FAIL → the information exists but the spread eats it; ends unless a cheaper instrument is identified in a new pre-registration. A1 PASS and A2 PASS → grounds for a pre-registered, delta-hedged paper-trading test of weekly ATM straddles; not grounds for capital.

## 5. Discipline

- One run. The runner writes a receipt (`receipt-A.json`: file hashes, code hash, sample counts, results) and refuses to run again if the receipt exists.
- No variants. The three free choices (weekly horizon, ATM by nearest strike, expanding-window HAR with 26-week burn-in) are fixed above.
- The Sep 10 momentum pre-registration v1 is **closed without spending its look**: its development partition showed nothing (+0.46 bps, t 0.31), so its validation/confirmation partitions are never examined for momentum and are released to this study's daily-close series. This study computes no intraday momentum quantity.

## 6. Owner actions before the run

1. Re-order the Cboe file (COIN, Option EOD Summary, with Calcs, 2024-09-01 → 2026-08-31, ≈ $490) and place the CSV(s) in `research/cboe/`.
2. Approve this text. After approval the code hash is recorded and the run happens once.
