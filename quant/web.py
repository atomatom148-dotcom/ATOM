"""Thin, data-only ATOM Quant web surface using the Python standard library."""

from __future__ import annotations

import argparse
import json
import os
from html import escape
import time
from typing import Callable, Iterable
from wsgiref.simple_server import make_server

from .history import MidpointHistory
from .live_market import LiveMarketState, LiveSnapshot, start_alpaca_poller
from .q1_momentum import calculate_momentum
from .q2_mean_reversion import calculate_mean_reversion
from .q3_volatility import calculate_volatility


HORIZON_LABELS = ("30S", "1M", "5M", "15M", "30M", "60M")
FAMILY_NAMES = (
    "Momentum",
    "Mean Reversion",
    "Volatility",
    "Stat Arb",
    "Microstructure",
    "Volume/Liquidity",
    "Relative Value",
    "Cross-Asset",
    "Factor",
    "Options/Vol",
    "Regime",
    "Event/Session",
)
OPTION_FIELDS = (
    "Strike", "Expiration", "Premium", "IV", "Delta", "Gamma",
    "Theta", "Vega", "Bid", "Ask", "Spread",
)
EVIDENCE_FIELDS = (
    "Forecasts", "Resolved", "Eligible", "RMSE", "Coverage", "Effective N",
)


def dashboard_data(
    history: MidpointHistory | None = None, *, cutoff_epoch: float | None = None,
    snapshot: LiveSnapshot | None = None, now_epoch: float | None = None,
) -> dict[str, object]:
    """Build the frozen dashboard structure, optionally calculating Q1-Q3."""

    supplied = history is not None or snapshot is not None
    if snapshot is not None:
        history = snapshot.history
    history = history if history is not None else MidpointHistory()
    if cutoff_epoch is None:
        cutoff_epoch = history.latest.event_epoch if history.latest else 0.0

    q1 = snapshot.momentum if snapshot and snapshot.momentum else calculate_momentum(history, cutoff_epoch=cutoff_epoch)
    q2 = snapshot.mean_reversion if snapshot and snapshot.mean_reversion else calculate_mean_reversion(history, cutoff_epoch=cutoff_epoch)
    q3 = snapshot.volatility if snapshot and snapshot.volatility else calculate_volatility(history, cutoff_epoch=cutoff_epoch)
    populated = (q1.forecast_bps, q2.forecast_bps, q3.volatility_bps)
    families = [
        {
            "name": name,
            "values": list(populated[index]) if index < 3 else [None] * 6,
        }
        for index, name in enumerate(FAMILY_NAMES)
    ]
    return {
        "title": "ATOM QUANT",
        "market": {
            "symbol": history.latest.midpoint if history.latest else None,
            "benchmarks": ["BTC", "QQQ", "NDX"],
            "data_age": max(0.0, (time.time() if now_epoch is None else now_epoch) - history.latest.event_epoch) if history.latest else None,
            "last_cycle": snapshot.last_cycle if snapshot else (cutoff_epoch if supplied else None),
        },
        "horizons": list(HORIZON_LABELS),
        "final_numbers": {
            metric: [None] * 6 for metric in ("BPS", "MOVE%", "RANGE")
        },
        "quant_families": families,
        "options_data": {field: None for field in OPTION_FIELDS},
        "evidence": {field: None for field in EVIDENCE_FIELDS},
    }


def _cell(value: object) -> str:
    return "" if value is None else escape(str(value))


def _table(headers: Iterable[str], rows: Iterable[tuple[str, Iterable[object]]]) -> str:
    heading = "".join(f"<th>{escape(item)}</th>" for item in headers)
    body = "".join(
        "<tr><th>" + escape(label) + "</th>" +
        "".join(f"<td>{_cell(value)}</td>" for value in values) + "</tr>"
        for label, values in rows
    )
    return f"<div class=scroll><table><thead><tr><th></th>{heading}</tr></thead><tbody>{body}</tbody></table></div>"


def dashboard_page(data: dict[str, object]) -> bytes:
    """Render the numerical dashboard; null JSON values become blank cells."""

    market = data["market"]
    horizons = data["horizons"]
    final_numbers = data["final_numbers"]
    families = data["quant_families"]
    options = data["options_data"]
    evidence = data["evidence"]
    document = f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>ATOM QUANT</title><style>
:root{{color-scheme:dark}}body{{margin:0;background:#090c0a;color:#c8facc;font:14px ui-monospace,SFMono-Regular,Consolas,monospace}}main{{max-width:1100px;margin:auto;padding:24px}}h1{{font-size:22px}}h2{{font-size:15px;margin-top:30px;border-bottom:1px solid #315636;padding-bottom:7px}}.market{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}}.label{{color:#7bad80;font-size:11px}}.value{{min-height:1.2em;margin-top:4px}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:7px 10px;border-bottom:1px solid #203a24;text-align:right}}th:first-child{{text-align:left}}thead th{{color:#7bad80}}.scroll{{overflow-x:auto}}@media(max-width:600px){{main{{padding:14px}}th,td{{padding:6px 8px}}}}
</style></head><body><main><h1>ATOM QUANT</h1>
<h2>MARKET</h2><div class=market>
<div><div class=label>COIN</div><div class=value>{_cell(market['symbol'])}</div></div>
<div><div class=label>BTC</div><div class=value></div></div><div><div class=label>QQQ</div><div class=value></div></div><div><div class=label>NDX</div><div class=value></div></div>
<div><div class=label>DATA AGE</div><div class=value>{_cell(market['data_age'])}</div></div><div><div class=label>LAST CYCLE</div><div class=value>{_cell(market['last_cycle'])}</div></div></div>
<h2>FINAL NUMBERS</h2>{_table(horizons, final_numbers.items())}
<h2>12 QUANT FAMILIES</h2>{_table(horizons, ((item['name'], item['values']) for item in families))}
<h2>OPTIONS DATA</h2>{_table((), ((key, (value,)) for key, value in options.items()))}
<h2>EVIDENCE</h2>{_table((), ((key, (value,)) for key, value in evidence.items()))}
</main></body></html>"""
    return document.encode("utf-8")


def create_app(
    history: MidpointHistory | None = None, *, cutoff_epoch: float | None = None,
    state: LiveMarketState | None = None, clock: Callable[[], float] = time.time,
) -> Callable:
    """Create the WSGI application, rendering current state on every request."""

    def application(environ: dict[str, object], start_response: Callable) -> list[bytes]:
        path = environ.get("PATH_INFO", "")
        snapshot = state.snapshot() if state is not None else None
        data = dashboard_data(history, cutoff_epoch=cutoff_epoch, snapshot=snapshot, now_epoch=clock())
        if path == "/":
            status, content_type, body = "200 OK", "text/html; charset=utf-8", dashboard_page(data)
        elif path == "/api/dashboard":
            status, content_type, body = "200 OK", "application/json", json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
        elif path == "/health":
            status, content_type, body = "200 OK", "application/json", b'{"status":"running"}'
        else:
            status, content_type, body = "404 Not Found", "text/plain; charset=utf-8", b"Not Found"
        start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body)))])
        return [body]

    return application


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the ATOM numerical dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    state = LiveMarketState()
    start_alpaca_poller(state)
    with make_server(args.host, args.port, create_app(state=state)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
