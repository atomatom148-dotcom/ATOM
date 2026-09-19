#!/usr/bin/env python3
"""
Pre-registration A runner — COIN realized variance vs weekly ATM implied variance.
See prereg-A-realized-vs-implied-vol-v1.md. One run; refuses to run twice (receipt-A.json).

    python cboe_iv_study.py --cboe cboe/ --bars bars/COIN_1m_rth.csv --calendar calendar_manifest.json
    python cboe_iv_study.py --selftest        # synthetic data, proves the pipeline only

Inputs: Cboe DataShop "Option EOD Summary with Calcs" CSV(s) for COIN (headers are
normalised to lower-case snake_case, so either the web column names or the file's
own names work), the COIN 1-minute RTH bar export (daily close = last bar of each
session), and the XNYS calendar manifest.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
SEED = 20260918
DRAWS = 10_000
BURN_IN_WEEKS = 26
MARGIN_DIAG = 0.10


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", col.strip().lower()).strip("_")


# ----------------------------------------------------------------------------
# inputs
# ----------------------------------------------------------------------------
def load_sessions(calendar: Path, first: str, last: str) -> list[dict]:
    cal = json.loads(calendar.read_text())
    return [s for s in cal["us_cash_sessions"] if first <= s["date"] <= last]


def load_daily_closes(bars: Path, sessions: list[dict]) -> dict[str, float]:
    by = {s["date"]: (int(dt.datetime.fromisoformat(s["open_utc"].replace("Z", "+00:00")).timestamp()),
                      int(dt.datetime.fromisoformat(s["close_utc"].replace("Z", "+00:00")).timestamp())) for s in sessions}
    last: dict[str, tuple[int, float]] = {}
    with bars.open() as f:
        for line in f:
            e, _o, _h, _l, c, _v = line.rstrip("\n").split(",")
            e = int(e)
            d = dt.datetime.fromtimestamp(e, tz=dt.timezone.utc).astimezone(ET).date().isoformat()
            rng = by.get(d)
            if rng and rng[0] <= e < rng[1] and (d not in last or e > last[d][0]):
                last[d] = (e, float(c))
    return {d: v[1] for d, v in last.items()}


def load_cboe(folder: Path) -> tuple[dict, list[str]]:
    """Return {(quote_date, expiration, strike, type): row} for COIN and the list of files read."""
    rows: dict = {}
    files = sorted(glob.glob(str(folder / "*.csv")) + glob.glob(str(folder / "*.zip")))
    if not files:
        raise SystemExit(f"no Cboe csv/zip files in {folder}")
    for path in files:
        if path.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if name.lower().endswith(".csv"):
                        _ingest(io.TextIOWrapper(z.open(name), encoding="utf-8"), rows)
        else:
            with open(path, newline="") as f:
                _ingest(f, rows)
    return rows, files


def _ingest(fh, rows: dict) -> None:
    reader = csv.DictReader(fh)
    reader.fieldnames = [norm(c) for c in reader.fieldnames]
    need = ("underlying_symbol", "quote_date", "expiration", "strike", "option_type", "bid_1545", "ask_1545",
            "active_underlying_price_1545", "implied_volatility_1545")
    missing = [c for c in need if c not in reader.fieldnames]
    if missing:
        raise SystemExit(f"Cboe file lacks columns {missing}; have {reader.fieldnames}")
    for r in reader:
        if r["underlying_symbol"].strip().upper() != "COIN":
            continue
        try:
            key = (r["quote_date"][:10], r["expiration"][:10], float(r["strike"]), r["option_type"].strip().upper()[0])
            rows[key] = {"bid": float(r["bid_1545"] or 0), "ask": float(r["ask_1545"] or 0),
                         "und": float(r["active_underlying_price_1545"] or 0), "iv": float(r["implied_volatility_1545"] or 0)}
        except ValueError:
            continue


# ----------------------------------------------------------------------------
# construction
# ----------------------------------------------------------------------------
def decision_and_expiry_days(sessions: list[dict]) -> list[tuple[str, str, int]]:
    """(decision_day, expiry_day, T): last session of each ISO week -> last session of the next ISO week."""
    weeks: dict[tuple[int, int], list[str]] = defaultdict(list)
    for s in sessions:
        d = dt.date.fromisoformat(s["date"]); weeks[d.isocalendar()[:2]].append(s["date"])
    keys = sorted(weeks)
    dates = [s["date"] for s in sessions]
    out = []
    for i in range(len(keys) - 1):
        t = weeks[keys[i]][-1]; e = weeks[keys[i + 1]][-1]
        T = dates.index(e) - dates.index(t)
        out.append((t, e, T))
    return out


def atm_quote(rows: dict, t: str, e: str) -> dict | None:
    cands = [k for k in rows if k[0] == t and k[1] == e]
    if not cands:
        return None
    und = rows[cands[0]]["und"]
    if und <= 0:
        return None
    strikes = sorted({k[2] for k in cands}, key=lambda s: (abs(s - und), s))
    for K in strikes[:3]:  # nearest strike, then next-nearest if a leg is missing
        c = rows.get((t, e, K, "C")); p = rows.get((t, e, K, "P"))
        if c and p and c["bid"] > 0 and p["bid"] > 0 and c["iv"] > 0 and p["iv"] > 0:
            mid = (c["bid"] + c["ask"] + p["bid"] + p["ask"]) / 2
            spread = (c["ask"] - c["bid"]) + (p["ask"] - p["bid"])
            return {"strike": K, "und": und, "iv": (c["iv"] + p["iv"]) / 2, "rel_spread": spread / mid if mid > 0 else None}
    return None


def hc1_ols(X: np.ndarray, y: np.ndarray):
    n, k = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    meat = (X * resid[:, None] ** 2).T @ X
    cov = XtX_inv @ meat @ XtX_inv * n / (n - k)
    se = np.sqrt(np.diag(cov))
    r2 = 1 - resid @ resid / ((y - y.mean()) @ (y - y.mean()))
    return beta, se, float(r2), resid


def norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def run(rows: dict, closes: dict[str, float], sessions: list[dict]) -> dict:
    dates = [s["date"] for s in sessions]
    idx = {d: i for i, d in enumerate(dates)}
    # daily log returns and squared returns
    ret = {}
    for i in range(1, len(dates)):
        a, b = dates[i - 1], dates[i]
        if a in closes and b in closes:
            ret[b] = math.log(closes[b] / closes[a])
    rv = {d: r * r for d, r in ret.items()}

    weeks = []
    skipped = defaultdict(int)
    for t, e, T in decision_and_expiry_days(sessions):
        q = atm_quote(rows, t, e)
        if q is None:
            skipped["no_atm_quote"] += 1; continue
        span = dates[idx[t] + 1: idx[e] + 1]
        if len(span) != T or any(d not in rv for d in span):
            skipped["missing_closes"] += 1; continue
        # HAR regressors from history up to t (inclusive)
        hist = [rv[d] for d in dates[: idx[t] + 1] if d in rv]
        if len(hist) < 22:
            skipped["har_history"] += 1; continue
        x1 = math.log(max(hist[-1], 1e-12)); x2 = math.log(max(np.mean(hist[-5:]), 1e-12)); x3 = math.log(max(np.mean(hist[-22:]), 1e-12))
        ivar = q["iv"] ** 2 * T / 252
        rvar = float(sum(rv[d] for d in span))
        weeks.append({"t": t, "e": e, "T": T, "ivar": ivar, "rvar": rvar, "x": (1.0, x1, x2, x3), "rel_spread": q["rel_spread"], "strike": q["strike"], "und": q["und"]})

    # expanding-window HAR forecasts: fit on decision weeks whose expiry <= current t
    for i, w in enumerate(weeks):
        train = [v for v in weeks[:i] if v["e"] <= w["t"]]
        if len(train) < BURN_IN_WEEKS:
            w["har"] = None; continue
        X = np.array([v["x"] for v in train]); y = np.log(np.array([v["rvar"] for v in train]))
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        s2 = float(np.var(y - X @ beta, ddof=X.shape[1]))
        w["har"] = float(math.exp(np.array(w["x"]) @ beta + s2 / 2))

    fc = [w for w in weeks if w["har"] is not None and w["rel_spread"] is not None]
    out = {"weeks_total": len(weeks), "weeks_forecast": len(fc), "skipped": dict(skipped)}
    if len(fc) < 20:
        out["verdict"] = "INSUFFICIENT"; return out
    y = np.log(np.array([w["rvar"] for w in fc])); liv = np.log(np.array([w["ivar"] for w in fc])); lhar = np.log(np.array([w["har"] for w in fc]))
    # A1 encompassing
    X = np.column_stack([np.ones(len(fc)), liv, lhar])
    beta, se, r2, _ = hc1_ols(X, y)
    z_har = beta[2] / se[2]
    p_har = norm_sf(z_har)
    _, _, r2_iv, _ = hc1_ols(np.column_stack([np.ones(len(fc)), liv]), y)
    vrp = y - liv
    out["A1"] = {"n": len(fc), "beta_const": float(beta[0]), "beta_log_ivar": float(beta[1]), "beta_log_har": float(beta[2]),
                 "se_log_har_hc1": float(se[2]), "z_log_har": float(z_har), "p_one_sided": float(p_har), "r2_full": r2, "r2_ivar_only": r2_iv,
                 "variance_risk_premium_mean_log": float(vrp.mean()), "vrp_t": float(vrp.mean() / (vrp.std(ddof=1) / math.sqrt(len(fc)))),
                 "verdict": "PASS" if (beta[2] > 0 and p_har < 0.05) else "FAIL"}
    # A2 economic
    rng = np.random.default_rng(SEED)
    def a2(margin: float) -> dict:
        s = np.array([1.0 if w["har"] > w["ivar"] * (1 + margin) else (-1.0 if w["har"] < w["ivar"] * (1 - margin) else 0.0) for w in fc])
        pay = s * np.array([(w["rvar"] - w["ivar"]) / w["ivar"] for w in fc])
        cost = np.abs(s) * np.array([2 * w["rel_spread"] for w in fc])
        net = pay - cost
        boot = np.array([net[rng.integers(0, len(net), len(net))].mean() for _ in range(DRAWS)])
        return {"n_weeks": len(net), "n_traded": int((s != 0).sum()), "mean_gross": float(pay.mean()), "mean_cost": float(cost.mean()),
                "mean_net": float(net.mean()), "lb95_one_sided": float(np.quantile(boot, 0.05)), "hit_rate_traded": float(np.mean(net[s != 0] > 0)) if (s != 0).any() else None,
                "verdict": "PASS" if (net.mean() > 0 and np.quantile(boot, 0.05) > 0) else "FAIL"}
    out["A2"] = a2(0.0); out["A2_margin_10pct_diagnostic"] = a2(MARGIN_DIAG)
    out["iv_level_sanity"] = {"median_annualised_iv": float(np.median([w["ivar"] * 252 / w["T"] for w in fc]) ** 0.5),
                              "median_rel_straddle_spread": float(np.median([w["rel_spread"] for w in fc]))}
    out["verdict"] = f"A1 {out['A1']['verdict']}, A2 {out['A2']['verdict']}"
    return out


# ----------------------------------------------------------------------------
def selftest() -> None:
    """Synthetic COIN: GARCH-ish daily returns, options priced at true vol plus a premium; the
    pipeline must run and A1 should PASS when realized vol is persistent."""
    rng = np.random.default_rng(1)
    start = dt.date(2024, 9, 3)
    sessions, closes, d, px, vol = [], {}, start, 180.0, 0.03
    while len(sessions) < 500:
        if d.weekday() < 5:
            op = dt.datetime.combine(d, dt.time(13, 30), tzinfo=dt.timezone.utc)
            sessions.append({"date": d.isoformat(), "open_utc": op.isoformat().replace("+00:00", "Z"), "close_utc": (op + dt.timedelta(hours=6, minutes=30)).isoformat().replace("+00:00", "Z"), "expected_minutes": 390})
            vol = 0.9 * vol + 0.1 * 0.03 + 0.004 * rng.normal()
            vol = max(vol, 0.01)
            px *= math.exp(vol * rng.normal()); closes[d.isoformat()] = px
        d += dt.timedelta(days=1)
    rows = {}
    for t, e, T in decision_and_expiry_days(sessions):
        und = closes[t]; true_vol = vol_at = None
        # option IV = trailing 5-day realized vol * 1.1 (a premium) — a naive market
        i = [s["date"] for s in sessions].index(t)
        rets = [math.log(closes[sessions[j]["date"]] / closes[sessions[j - 1]["date"]]) for j in range(max(1, i - 4), i + 1)]
        iv = math.sqrt(np.mean(np.square(rets)) * 252) * 1.1
        for K in (round(und / 5) * 5 - 5, round(und / 5) * 5, round(und / 5) * 5 + 5):
            for typ in ("C", "P"):
                mid = und * iv * math.sqrt(T / 252) * 0.4
                rows[(t, e, float(K), typ)] = {"bid": mid * 0.97, "ask": mid * 1.03, "und": und, "iv": iv}
    out = run(rows, closes, sessions)
    print(json.dumps(out, indent=1, default=float))
    assert out["weeks_forecast"] > 40, out
    print("selftest OK: pipeline runs end to end")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cboe", default="cboe")
    ap.add_argument("--bars", default="bars/COIN_1m_rth.csv")
    ap.add_argument("--calendar", default="calendar_manifest.json")
    ap.add_argument("--first", default="2024-09-01")
    ap.add_argument("--last", default="2026-08-31")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    receipt = Path("receipt-A.json")
    if receipt.exists():
        print("receipt-A.json exists: the single look has been spent. Refusing to run.", file=sys.stderr); sys.exit(2)
    sessions = load_sessions(Path(args.calendar), args.first, args.last)
    closes = load_daily_closes(Path(args.bars), sessions)
    rows, files = load_cboe(Path(args.cboe))
    out = run(rows, closes, sessions)
    out.update({"study": "prereg-A-realized-vs-implied-vol-v1", "computed_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "code_sha256": sha256_file(Path(__file__)), "inputs": {"cboe_files": {f: sha256_file(Path(f)) for f in files},
                "bars_sha256": sha256_file(Path(args.bars)), "calendar_sha256": sha256_file(Path(args.calendar))},
                "fixed": {"burn_in_weeks": BURN_IN_WEEKS, "seed": SEED, "draws": DRAWS, "cost": "2 x ATM straddle relative spread at 15:45"}})
    receipt.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
