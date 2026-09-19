#!/usr/bin/env python3
"""
Pre-registration B runner — single look at COIN history 2021-04-14 .. 2024-08-30.
See prereg-B-morning-continuation-history-v1.md. Refuses to run twice (receipt-B.json).

    python history_study.py --data bars_history

Nothing here is tunable from the command line by design.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
COST = 2.0 / 1e4
SEED = 20260918
DRAWS = 10_000
VOL_MULT = 1.5
TRAIL = 60
PASS_MEAN_BPS = 30.0


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Session:
    def __init__(self, date, open_epoch, close_epoch, expected):
        self.date, self.open_epoch, self.close_epoch, self.expected = date, open_epoch, close_epoch, expected
        self.open_px = np.full(expected, np.nan); self.close = np.full(expected, np.nan); self.vol = np.full(expected, np.nan)


def load(data: Path):
    cal = json.loads((data / "calendar_history.json").read_text())
    sessions = {}
    for s in cal["us_cash_sessions"]:
        op = int(dt.datetime.fromisoformat(s["open_utc"].replace("Z", "+00:00")).timestamp())
        cl = int(dt.datetime.fromisoformat(s["close_utc"].replace("Z", "+00:00")).timestamp())
        sessions[s["date"]] = Session(s["date"], op, cl, s["expected_minutes"])
    with (data / "COIN_1m_rth_2021_2024.csv").open() as f:
        for line in f:
            e, o, _h, _l, c, v = line.rstrip("\n").split(",")
            e = int(e)
            d = dt.datetime.fromtimestamp(e, tz=dt.timezone.utc).astimezone(ET).date().isoformat()
            s = sessions.get(d)
            if s is None or not (s.open_epoch <= e < s.close_epoch):
                continue
            k = (e - s.open_epoch) // 60
            s.open_px[k] = float(o); s.close[k] = float(c); s.vol[k] = float(v)
    btc = {}
    with (data / "BTC_5m_0900_1610ET_2021_2024.csv").open() as f:
        for line in f:
            b5, c, _n = line.rstrip("\n").split(",")
            btc[int(b5)] = float(c)
    ordered = [sessions[d] for d in sorted(sessions)]
    return ordered, btc


def bucket_close(btc, epoch):
    b = (epoch // 300) * 300
    if b + 300 > epoch:
        b -= 300
    return btc.get(b)


def stats(p: np.ndarray) -> dict:
    p = np.asarray(p, float)
    n = len(p)
    if n == 0:
        return {"n": 0}
    rng = np.random.default_rng(SEED)
    boot = np.array([p[rng.integers(0, n, n)].mean() for _ in range(DRAWS)])
    se = p.std(ddof=1) / math.sqrt(n)
    return {"n": int(n), "mean_bps": float(p.mean() * 1e4), "se_bps": float(se * 1e4), "t": float(p.mean() / se),
            "lb95_one_sided_bps": float(np.quantile(boot, 0.05) * 1e4), "hit_rate": float(np.mean(p > 0)),
            "median_bps": float(np.median(p) * 1e4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="bars_history")
    args = ap.parse_args()
    data = Path(args.data)
    receipt = data / "receipt-B.json"
    if receipt.exists():
        print("receipt-B.json exists: the single look has been spent. Refusing to run.", file=sys.stderr)
        sys.exit(2)
    prov = json.loads((data / "provenance_history.json").read_text())
    for name, meta in prov["files"].items():
        if sha256(data / name) != meta["sha256"]:
            print(f"hash mismatch for {name}; data changed since the pull", file=sys.stderr); sys.exit(3)

    sessions, btc = load(data)
    eligible, excluded = [], {"early_close": 0, "missing_minutes": 0}
    for s in sessions:
        if s.expected != 390:
            excluded["early_close"] += 1; continue
        if np.isnan(s.close).sum() > 5 or np.isnan(s.vol[:150]).any() or np.isnan(s.open_px[0]) or np.isnan(s.close[149]) or np.isnan(s.close[389]):
            excluded["missing_minutes"] += 1; continue
        eligible.append(s)

    # B1 / B2
    morning_vol = [float(s.vol[:150].sum()) for s in eligible]
    b1, b2, years, b1_no_big, am_abs = [], [], {}, [], []
    for i, s in enumerate(eligible):
        am = math.log(s.close[149] / s.open_px[0]); pm = math.log(s.close[389] / s.close[149])
        d = np.sign(am)
        if d == 0:
            continue
        p = d * pm - COST
        b2.append(p)
        if i >= TRAIL:
            med = float(np.median(morning_vol[i - TRAIL:i]))
            if morning_vol[i] > VOL_MULT * med:
                b1.append(p); am_abs.append(abs(am)); years.setdefault(s.date[:4], []).append(p)
    b1 = np.array(b1); am_abs = np.array(am_abs)
    r1 = stats(b1); r2 = stats(np.array(b2))
    verdict = "PASS" if (r1.get("n", 0) > 0 and r1["lb95_one_sided_bps"] > 0 and r1["mean_bps"] >= PASS_MEAN_BPS) else \
              "WEAK" if (r1.get("n", 0) > 0 and r1["lb95_one_sided_bps"] > 0) else "FAIL"
    diag = {"by_year": {y: stats(np.array(v)) for y, v in years.items()}}
    if len(b1) > 20:
        cut = np.quantile(am_abs, 0.95)
        diag["excluding_top5pct_morning_moves"] = stats(b1[am_abs <= cut])
        srt = np.sort(b1)[::-1]
        diag["top10_share_of_total"] = float(srt[:10].sum() / b1.sum()) if b1.sum() != 0 else None

    # B3 unabsorbed BTC overnight -> first 30 min
    b3 = []
    prev = None
    for s in eligible:
        if prev is not None:
            b_open = bucket_close(btc, s.open_epoch); b_prev = bucket_close(btc, prev.close_epoch)
            if None not in (b_open, b_prev) and not np.isnan(prev.close[389]) and not np.isnan(s.close[29]):
                r_btc = math.log(b_open / b_prev); gap = math.log(s.open_px[0] / prev.close[389])
                d = np.sign(r_btc - gap)
                if d != 0:
                    b3.append(d * math.log(s.close[29] / s.open_px[0]) - COST)
        prev = s
    r3 = stats(np.array(b3))

    out = {"study": "prereg-B-morning-continuation-history-v1", "computed_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "code_sha256": sha256(Path(__file__)), "provenance": prov, "sessions_total": len(sessions), "eligible": len(eligible), "excluded": excluded,
           "B1_rule": r1, "B1_verdict": verdict, "B2_unconditional": r2, "B3_btc_unabsorbed_first30": r3, "diagnostics": diag,
           "fixed_parameters": {"cost_bps": 2.0, "vol_multiple": VOL_MULT, "trailing_sessions": TRAIL, "split": "12:00", "pass_mean_bps": PASS_MEAN_BPS}}
    receipt.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
