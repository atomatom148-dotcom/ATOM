#!/usr/bin/env python3
"""
Pull COIN / QQQ 1-minute SIP bars and BTC/USD 5-minute bars from Alpaca for
2021-04-14 .. 2024-08-30, write them in the exact CSV layout the research
harness expects, and record hashes in provenance_history.json.

Runs on the Owner's desktop. Keys are read from the environment and never
printed:  APCA_API_KEY_ID, APCA_API_SECRET_KEY.

    pip install "alpaca-py==0.42.0" "exchange_calendars==4.13.2"
    python alpaca_history_pull.py --out bars_history

Output files (no header, same columns as the existing exports):
    COIN_1m_rth_2021_2024.csv   epoch,open,high,low,close,volume   (RTH bar starts only)
    QQQ_5m_rth_2021_2024.csv    bucket_epoch,open,high,low,close,volume,nbars
    BTC_5m_0900_1610ET_2021_2024.csv  bucket_epoch,close,nbars   (09:00-16:10 ET only)
    provenance_history.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
START = dt.date(2021, 4, 14)
END = dt.date(2024, 8, 30)


def die(msg: str) -> None:
    print("ERROR:", msg, file=sys.stderr)
    sys.exit(1)


def month_ranges(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        nxt = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        yield cur, min(nxt - dt.timedelta(days=1), end)
        cur = nxt


def rth(ts_utc: dt.datetime) -> bool:
    t = ts_utc.astimezone(ET).time()
    return dt.time(9, 30) <= t < dt.time(16, 0)


def pull_stock_minutes(client, symbol: str, out: Path, feed) -> int:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment
    n = 0
    with out.open("w") as f:
        for a, b in month_ranges(START, END):
            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute,
                                   start=dt.datetime.combine(a, dt.time(9, 0), tzinfo=ET),
                                   end=dt.datetime.combine(b, dt.time(16, 30), tzinfo=ET),
                                   adjustment=Adjustment.RAW, feed=feed, limit=10000)
            for attempt in range(5):
                try:
                    bars = client.get_stock_bars(req).data.get(symbol, [])
                    break
                except Exception as e:  # rate limit / transient
                    if attempt == 4:
                        raise
                    time.sleep(5 * (attempt + 1))
            for bar in bars:
                ts = bar.timestamp if bar.timestamp.tzinfo else bar.timestamp.replace(tzinfo=dt.timezone.utc)
                if not rth(ts):
                    continue
                f.write(f"{int(ts.timestamp())},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}\n")
                n += 1
            print(f"  {symbol} {a}..{b}: {len(bars)} bars", flush=True)
    return n


def pull_qqq_5m(client, out: Path, feed) -> int:
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import Adjustment
    n = 0
    with out.open("w") as f:
        for a, b in month_ranges(START, END):
            req = StockBarsRequest(symbol_or_symbols="QQQ", timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                                   start=dt.datetime.combine(a, dt.time(9, 0), tzinfo=ET),
                                   end=dt.datetime.combine(b, dt.time(16, 30), tzinfo=ET),
                                   adjustment=Adjustment.RAW, feed=feed, limit=10000)
            bars = client.get_stock_bars(req).data.get("QQQ", [])
            for bar in bars:
                ts = bar.timestamp if bar.timestamp.tzinfo else bar.timestamp.replace(tzinfo=dt.timezone.utc)
                if not rth(ts):
                    continue
                f.write(f"{int(ts.timestamp())},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume},{bar.trade_count or 5}\n")
                n += 1
            print(f"  QQQ 5m {a}..{b}: {len(bars)} bars", flush=True)
    return n


def pull_btc_5m(client, out: Path) -> int:
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    n = 0
    with out.open("w") as f:
        for a, b in month_ranges(START, END):
            req = CryptoBarsRequest(symbol_or_symbols="BTC/USD", timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                                    start=dt.datetime.combine(a, dt.time(0, 0), tzinfo=dt.timezone.utc),
                                    end=dt.datetime.combine(b, dt.time(23, 59), tzinfo=dt.timezone.utc), limit=10000)
            bars = client.get_crypto_bars(req).data.get("BTC/USD", [])
            for bar in bars:
                ts = bar.timestamp if bar.timestamp.tzinfo else bar.timestamp.replace(tzinfo=dt.timezone.utc)
                t = ts.astimezone(ET).time()
                if not (dt.time(9, 0) <= t < dt.time(16, 10)):
                    continue
                f.write(f"{int(ts.timestamp())},{bar.close},{bar.trade_count or 5}\n")
                n += 1
            print(f"  BTC/USD 5m {a}..{b}: {len(bars)} bars", flush=True)
    return n


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="bars_history")
    ap.add_argument("--feed", default="sip", choices=["sip", "iex"])
    args = ap.parse_args()
    key, secret = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        die("set APCA_API_KEY_ID and APCA_API_SECRET_KEY in the environment")
    try:
        import alpaca
        from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
        from alpaca.data.enums import DataFeed
        import exchange_calendars as xcals
    except ImportError as e:
        die(f"missing package: {e}. pip install 'alpaca-py==0.42.0' 'exchange_calendars==4.13.2'")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    feed = DataFeed.SIP if args.feed == "sip" else DataFeed.IEX
    stocks = StockHistoricalDataClient(key, secret)
    crypto = CryptoHistoricalDataClient(key, secret)

    files = {}
    p = out / "COIN_1m_rth_2021_2024.csv"; files[p.name] = pull_stock_minutes(stocks, "COIN", p, feed)
    p = out / "QQQ_5m_rth_2021_2024.csv"; files[p.name] = pull_qqq_5m(stocks, p, feed)
    p = out / "BTC_5m_0900_1610ET_2021_2024.csv"; files[p.name] = pull_btc_5m(crypto, p)

    # session calendar for the window, written once so the study never recomputes it
    cal = xcals.get_calendar("XNYS")
    sessions = []
    for s in cal.sessions_in_range(str(START), str(END)):
        op = cal.session_open(s).to_pydatetime(); cl = cal.session_close(s).to_pydatetime()
        sessions.append({"date": str(s.date()), "open_utc": op.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                         "close_utc": cl.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                         "expected_minutes": int((cl - op).total_seconds() // 60)})
    (out / "calendar_history.json").write_text(json.dumps({"exchange_calendars_version": xcals.__version__, "us_cash_sessions": sessions}, indent=1))

    prov = {"pulled_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "alpaca_py_version": alpaca.__version__,
            "feed": args.feed, "window": [str(START), str(END)],
            "files": {name: {"rows": rows, "sha256": sha256(out / name)} for name, rows in files.items()},
            "calendar_sha256": sha256(out / "calendar_history.json"), "sessions": len(sessions)}
    (out / "provenance_history.json").write_text(json.dumps(prov, indent=1))
    print(json.dumps(prov, indent=1))


if __name__ == "__main__":
    main()
