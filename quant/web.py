"""Thin, data-only ATOM Quant web surface using the Python standard library."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from html import escape
import time
from threading import Lock, Thread
from typing import Callable, Iterable
from wsgiref.simple_server import make_server

from .history import MidpointHistory
from .evidence import EvidenceStore, PostgresEvidenceStore
from .live_market import (LiveMarketState, LiveSnapshot, start_alpaca_g2_poller,
                          start_alpaca_options_poller, start_alpaca_poller)
from .q1_momentum import calculate_momentum
from .q2_mean_reversion import calculate_mean_reversion
from .q3_volatility import calculate_volatility
from .v9_telemetry import latest_v9_observation


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
    "Symbol", "Strike", "Expiration", "Premium", "IV", "Delta", "Gamma",
    "Theta", "Vega", "Bid", "Ask", "Spread",
)
PHASE_E_FAMILY_NAMES = {
    "q1_momentum": "Momentum",
    "q2_mean_reversion": "Mean Reversion",
    "q4_stat_arb": "Stat Arb",
    "q5_microstructure": "Microstructure",
    "q6_volume_liquidity": "Volume/Liquidity",
    "q7_relative_value": "Relative Value",
    "q8_cross_asset": "Cross-Asset",
    "q9_factor": "Factor",
    "q10_options_vol": "Options/Vol",
    "q11_regime": "Regime",
    "q12_event_session": "Event/Session",
}
PHASE_E_HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")
DASHBOARD_PHASE_E_TTL_SECONDS = 300.0


def dashboard_data(
    history: MidpointHistory | None = None, *, cutoff_epoch: float | None = None,
    snapshot: LiveSnapshot | None = None, now_epoch: float | None = None,
    evidence_counts: tuple[int, int] | None = None,
    phase_e_cohorts: Iterable[object] = (),
) -> dict[str, object]:
    """Build the frozen dashboard structure, optionally using live quant results."""

    supplied = history is not None or snapshot is not None
    if snapshot is not None:
        history = snapshot.history
    history = history if history is not None else MidpointHistory()
    if cutoff_epoch is None:
        cutoff_epoch = history.latest.event_epoch if history.latest else 0.0

    q1 = snapshot.momentum if snapshot and snapshot.momentum else calculate_momentum(history, cutoff_epoch=cutoff_epoch)
    q2 = snapshot.mean_reversion if snapshot and snapshot.mean_reversion else calculate_mean_reversion(history, cutoff_epoch=cutoff_epoch)
    q3 = snapshot.volatility if snapshot and snapshot.volatility else calculate_volatility(history, cutoff_epoch=cutoff_epoch)
    q4 = snapshot.stat_arb if snapshot else None
    q5 = snapshot.microstructure if snapshot else None
    q6 = snapshot.volume_liquidity if snapshot else None
    q7 = snapshot.relative_value if snapshot else None
    q8 = snapshot.cross_asset if snapshot else None
    q9 = snapshot.factor if snapshot else None
    q10 = snapshot.options_vol if snapshot else None
    q11 = snapshot.regime if snapshot else None
    q12 = snapshot.event_session if snapshot else None
    populated = (
        q1.forecast_bps, q2.forecast_bps, q3.volatility_bps,
        q4.forecast_bps if q4 else (None,) * 6,
        q5.forecast_bps if q5 else (None,) * 6,
        q6.forecast_bps if q6 else (None,) * 6,
        q7.forecast_bps if q7 else (None,) * 6,
        q8.forecast_bps if q8 else (None,) * 6,
        q9.forecast_bps if q9 else (None,) * 6,
        q10.forecast_bps if q10 else (None,) * 6,
        q11.forecast_bps if q11 else (None,) * 6,
        q12.forecast_bps if q12 else (None,) * 6,
    )
    families = [
        {
            "name": name,
            "values": list(populated[index]),
        }
        for index, name in enumerate(FAMILY_NAMES)
    ]
    surface = snapshot.option_surface if snapshot else None
    midpoint = history.latest.midpoint if history.latest else None

    def option_rows(observations: Iterable[object]) -> list[dict[str, object]]:
        """Build a detached display slice without changing the Q10 surface."""

        ordered = sorted(
            observations,
            key=lambda item: (abs(item.strike - midpoint), item.strike, item.contract_symbol),
        ) if midpoint is not None else list(observations)
        rows: list[dict[str, object]] = []
        strikes: set[float] = set()
        for option in ordered:
            if option.strike in strikes:
                continue
            strikes.add(option.strike)
            rows.append({
                "Symbol": option.contract_symbol, "Strike": option.strike,
                "Expiration": option.expiration, "Premium": option.premium,
                "IV": option.implied_volatility, "Delta": option.delta,
                "Gamma": option.gamma, "Theta": option.theta, "Vega": option.vega,
                "Bid": option.bid, "Ask": option.ask, "Spread": option.spread,
            })
            if len(rows) == 5:
                break
        return rows

    options_data = {
        "expiration": surface.expiration if surface else None,
        "calls": option_rows(surface.calls) if surface else [],
        "puts": option_rows(surface.puts) if surface else [],
    }
    family_order = {quant_id: index for index, quant_id in enumerate(PHASE_E_FAMILY_NAMES)}
    horizon_order = {horizon: index for index, horizon in enumerate(PHASE_E_HORIZONS)}
    visible_cohorts = sorted(
        (cohort for cohort in phase_e_cohorts if cohort.quant_id in PHASE_E_FAMILY_NAMES),
        key=lambda cohort: (
            family_order[cohort.quant_id], cohort.formula_version, cohort.symbol,
            horizon_order.get(cohort.horizon, len(horizon_order)), cohort.horizon,
        ),
    )
    return {
        "title": "ATOM QUANT",
        "market": {
            "symbol": history.latest.midpoint if history.latest else None,
            "benchmarks": ["BTC", "QQQ", "NDX"],
            "btc": None,
            "qqq": snapshot.qqq_history.latest.midpoint if snapshot and snapshot.qqq_history.latest else None,
            "ndx": None,
            "data_age": max(0.0, (time.time() if now_epoch is None else now_epoch) - history.latest.event_epoch) if history.latest else None,
            "last_cycle": snapshot.last_cycle if snapshot else (cutoff_epoch if supplied else None),
        },
        "horizons": list(HORIZON_LABELS),
        "final_numbers": {
            metric: [None] * 6 for metric in ("BPS", "MOVE%", "RANGE")
        },
        "quant_families": families,
        "options_data": options_data,
        "evidence": {
            "Forecasts": evidence_counts[0] if evidence_counts else None,
            "Resolved": evidence_counts[1] if evidence_counts else None,
        },
        "phase_e_cohorts": [dict(asdict(cohort), family=PHASE_E_FAMILY_NAMES[cohort.quant_id])
                            for cohort in visible_cohorts],
    }


def _cell(value: object) -> str:
    return "" if value is None else escape(str(value))


def _decimal_cell(value: object, suffix: str = "") -> str:
    """Format a numeric value for the HTML presentation without changing its source."""

    return "" if value is None else f"{float(value):.2f}{suffix}"


def _cycle_cell(value: object) -> str:
    """Render an epoch as a concise UTC time for the HTML presentation."""

    return "" if value is None else time.strftime("%H:%M:%S UTC", time.gmtime(float(value)))


def _table(
    headers: Iterable[str],
    rows: Iterable[tuple[str, Iterable[object]]],
    *,
    section: str,
    decimal: bool = False,
) -> str:
    heading = "".join(f"<th>{escape(item)}</th>" for item in headers)
    body = "".join(
        "<tr><th>" + escape(label) + "</th>" +
        "".join(
            f'<td data-dashboard-field="{section}.{escape(label)}.{index}">'
            f'{_decimal_cell(value) if decimal else _cell(value)}</td>'
            for index, value in enumerate(values)
        ) + "</tr>"
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
    phase_e = data["phase_e_cohorts"]
    phase_e_headers = ("FAMILY/HORIZON", "EFFECTIVE N", "ELIGIBLE", "ACC", "RMSE", "MAE", "BIAS", "COVERAGE")
    def phase_e_row(cohort: dict[str, object]) -> tuple[object, ...]:
        return (
            f"{cohort['family']} / {cohort['horizon']}", cohort["effective_n"],
            "YES" if cohort["eligible"] else "NO",
            "" if cohort["directional_accuracy"] is None else f"{cohort['directional_accuracy'] * 100:.1f}%",
            _decimal_cell(cohort["rmse_bps"]), _decimal_cell(cohort["mae_bps"]),
            _decimal_cell(cohort["bias_bps"]),
            "" if cohort["coverage"] is None else f"{cohort['coverage'] * 100:.1f}%",
        )
    phase_e_body = "".join(
        "<tr>" + "".join(
            f'<td data-dashboard-field="phase_e_cohorts.{row_index}.{column_index}">{_cell(value)}</td>'
            for column_index, value in enumerate(phase_e_row(cohort))
        ) + "</tr>"
        for row_index, cohort in enumerate(phase_e)
    )
    phase_e_table = ("<div class=scroll><table><thead><tr>" +
                     "".join(f"<th>{header}</th>" for header in phase_e_headers) +
                     f"</tr></thead><tbody id=phase-e-body>{phase_e_body}</tbody></table></div>")
    option_columns = ("Symbol", "Strike", "Bid", "Ask", "Premium", "IV", "Delta",
                      "Gamma", "Theta", "Vega", "Spread")
    def option_table(side: str) -> str:
        body = "".join(
            "<tr>" + "".join(
                f'<td data-dashboard-field="options_data.{side}.{row_index}.{field}">{_cell(row[field])}</td>'
                for field in option_columns
            ) + "</tr>"
            for row_index, row in enumerate(options[side])
        )
        headers = "".join(f"<th>{field}</th>" for field in option_columns)
        return f"<h3>{side.upper()}</h3><div class=scroll><table><thead><tr>{headers}</tr></thead><tbody id=options-{side}>{body}</tbody></table></div>"
    document = f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>ATOM QUANT</title><style>
:root{{color-scheme:dark}}body{{margin:0;background:#090c0a;color:#c8facc;font:14px ui-monospace,SFMono-Regular,Consolas,monospace}}main{{max-width:1100px;margin:auto;padding:24px}}h1{{font-size:22px}}h2{{font-size:15px;margin-top:30px;border-bottom:1px solid #315636;padding-bottom:7px}}.market{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}}.label{{color:#7bad80;font-size:11px}}.value{{min-height:1.2em;margin-top:4px}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:7px 10px;border-bottom:1px solid #203a24;text-align:right}}th:first-child{{text-align:left}}thead th{{color:#7bad80}}.scroll{{overflow-x:auto}}@media(max-width:600px){{main{{padding:14px}}.market{{grid-template-columns:repeat(2,minmax(0,1fr))}}th,td{{padding:6px 8px}}}}
</style></head><body><main><h1>ATOM QUANT</h1>
<h2>MARKET</h2><div class=market>
<div><div class=label>COIN</div><div class=value data-dashboard-field="market.symbol">{_decimal_cell(market['symbol'])}</div></div>
<div><div class=label>BTC</div><div class=value data-dashboard-field="market.btc">{_decimal_cell(market['btc'])}</div></div><div><div class=label>QQQ</div><div class=value data-dashboard-field="market.qqq">{_decimal_cell(market['qqq'])}</div></div><div><div class=label>NDX</div><div class=value data-dashboard-field="market.ndx">{_decimal_cell(market['ndx'])}</div></div>
<div><div class=label>DATA AGE</div><div class=value data-dashboard-field="market.data_age">{_decimal_cell(market['data_age'], 's')}</div></div><div><div class=label>LAST CYCLE</div><div class=value data-dashboard-field="market.last_cycle">{_cycle_cell(market['last_cycle'])}</div></div></div>
<h2>FINAL NUMBERS</h2>{_table(horizons, final_numbers.items(), section='final_numbers', decimal=True)}
<h2>12 QUANT FAMILIES</h2>{_table(horizons, ((item['name'], item['values']) for item in families), section='quant_families', decimal=True)}
<h2>OPTIONS DATA</h2><div>EXPIRATION: <span data-dashboard-field="options_data.expiration">{_cell(options['expiration'])}</span></div>{option_table('calls')}{option_table('puts')}
<h2>EVIDENCE</h2>{_table((), ((key, (value,)) for key, value in evidence.items()), section='evidence')}{phase_e_table}
</main><script>
(() => {{
  const cells = new Map(
    Array.from(document.querySelectorAll("[data-dashboard-field]"),
      cell => [cell.dataset.dashboardField, cell])
  );
  const text = value => value == null ? "" : String(value);
  const decimal = (value, suffix = "") => value == null ? "" : Number(value).toFixed(2) + suffix;
  const cycle = value => value == null ? "" :
    new Date(Number(value) * 1000).toLocaleTimeString("en-GB", {{
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      hour12: false, timeZone: "UTC"
    }}) + " UTC";
  const set = (field, value, format = text) => {{
    const cell = cells.get(field);
    if (cell) cell.textContent = format(value);
  }};
  const render = data => {{
    set("market.symbol", data.market.symbol, decimal);
    set("market.btc", data.market.btc, decimal);
    set("market.qqq", data.market.qqq, decimal);
    set("market.ndx", data.market.ndx, decimal);
    set("market.data_age", data.market.data_age, value => decimal(value, "s"));
    set("market.last_cycle", data.market.last_cycle, cycle);
    Object.entries(data.final_numbers).forEach(([name, values]) =>
      values.forEach((value, index) => set(`final_numbers.${{name}}.${{index}}`, value, decimal)));
    data.quant_families.forEach(family => family.values.forEach((value, index) =>
      set(`quant_families.${{family.name}}.${{index}}`, value, decimal)));
    set("options_data.expiration", data.options_data.expiration);
    ["calls", "puts"].forEach(side => {{
      const body = document.getElementById(`options-${{side}}`);
      const fields = {json.dumps(list(option_columns))};
      body.replaceChildren(...data.options_data[side].map(contract => {{
        const row = document.createElement("tr");
        row.replaceChildren(...fields.map(field => {{
          const cell = document.createElement("td");
          cell.textContent = text(contract[field]);
          return cell;
        }}));
        return row;
      }}));
    }}));
    Object.entries(data.evidence).forEach(([name, value]) =>
      set(`evidence.${{name}}.0`, value));
    const phaseEBody = document.getElementById("phase-e-body");
    phaseEBody.replaceChildren(...data.phase_e_cohorts.map(cohort => {{
      const values = [
        `${{cohort.family}} / ${{cohort.horizon}}`, String(cohort.effective_n),
        cohort.eligible ? "YES" : "NO",
        cohort.directional_accuracy == null ? "" : (cohort.directional_accuracy * 100).toFixed(1) + "%",
        decimal(cohort.rmse_bps), decimal(cohort.mae_bps), decimal(cohort.bias_bps),
        cohort.coverage == null ? "" : (cohort.coverage * 100).toFixed(1) + "%"
      ];
      const row = document.createElement("tr");
      row.replaceChildren(...values.map(value => {{
        const cell = document.createElement("td");
        cell.textContent = value;
        return cell;
      }}));
      return row;
    }}));
  }};
  const refreshDashboard = async () => {{
    try {{
      const response = await fetch("/api/dashboard", {{cache: "no-store"}});
      if (!response.ok) throw new Error(`dashboard request failed: ${{response.status}}`);
      render(await response.json());
    }} catch (_) {{
      // Preserve the last successful display; the interval performs the next retry.
    }}
  }};
  setInterval(refreshDashboard, 1000);
}})();
</script></body></html>"""
    return document.encode("utf-8")


def create_app(
    history: MidpointHistory | None = None, *, cutoff_epoch: float | None = None,
    state: LiveMarketState | None = None, clock: Callable[[], float] = time.time,
    evidence_store: EvidenceStore | None = None,
) -> Callable:
    """Create the WSGI application, rendering current state on every request."""

    phase_e_cache: tuple[object, ...] = ()
    phase_e_cache_time: float | None = None
    phase_e_refreshing = False
    phase_e_cache_lock = Lock()

    def refresh_phase_e(as_of_epoch: float, cache_time: float) -> None:
        nonlocal phase_e_cache, phase_e_cache_time, phase_e_refreshing
        try:
            refreshed = tuple(evidence_store.phase_e_cohorts(as_of_epoch))
        except Exception:
            refreshed = None
        with phase_e_cache_lock:
            if refreshed is not None:
                phase_e_cache = refreshed
                phase_e_cache_time = cache_time
            phase_e_refreshing = False

    def dashboard_phase_e_cohorts(as_of_epoch: float) -> tuple[object, ...]:
        nonlocal phase_e_refreshing
        if evidence_store is None:
            return ()
        cache_time = time.monotonic()
        start_refresh = False
        with phase_e_cache_lock:
            if (phase_e_cache_time is not None and
                    cache_time - phase_e_cache_time < DASHBOARD_PHASE_E_TTL_SECONDS):
                return phase_e_cache
            if not phase_e_refreshing:
                phase_e_refreshing = True
                start_refresh = True
            cached = phase_e_cache
        if start_refresh:
            Thread(
                target=refresh_phase_e, args=(as_of_epoch, cache_time), daemon=True,
            ).start()
        return cached

    def application(environ: dict[str, object], start_response: Callable) -> list[bytes]:
        path = environ.get("PATH_INFO", "")
        if path == "/health":
            body = b'{"status":"running"}'
            start_response("200 OK", [("Content-Type", "application/json"),
                                      ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/g2-cross-asset":
            value = state.cross_asset_state() if state is not None else None
            body = json.dumps(
                asdict(value) if value is not None else None,
                separators=(",", ":"), allow_nan=False,
            ).encode()
            start_response("200 OK", [("Content-Type", "application/json"),
                                      ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/v9-math":
            enabled = os.environ.get("V9_MATH_CORE_ENABLED", "false").lower() == "true"
            telemetry = latest_v9_observation() if enabled else None
            body = json.dumps({
                "enabled": enabled,
                "status": telemetry.status if telemetry else (
                    "NO_OBSERVATION_YET" if enabled else "DISABLED"
                ),
                "family_count": telemetry.family_count if telemetry else 0,
                "non_null_variable_count": (
                    telemetry.non_null_variable_count if telemetry else 0
                ),
                "as_of_epoch": telemetry.as_of_epoch if telemetry else None,
            }, separators=(",", ":"), allow_nan=False).encode()
            start_response("200 OK", [("Content-Type", "application/json"),
                                      ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/phase-e":
            if evidence_store is None:
                status, content_type, body = (
                    "503 Service Unavailable", "application/json",
                    b'{"error":"evidence store unavailable"}',
                )
            else:
                as_of_epoch = clock()
                cohorts = evidence_store.phase_e_cohorts(as_of_epoch)
                body = json.dumps({
                    "as_of_epoch": as_of_epoch,
                    "cohorts": [asdict(cohort) for cohort in cohorts],
                }, separators=(",", ":"), allow_nan=False).encode()
                status, content_type = "200 OK", "application/json"
            start_response(status, [("Content-Type", content_type),
                                    ("Content-Length", str(len(body)))])
            return [body]
        if path not in ("/", "/api/dashboard"):
            body = b"Not Found"
            start_response("404 Not Found", [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ])
            return [body]
        as_of_epoch = clock()
        snapshot = state.snapshot() if state is not None else None
        counts = evidence_store.counts() if evidence_store is not None else None
        cohorts = (
            dashboard_phase_e_cohorts(as_of_epoch)
            if path in ("/", "/api/dashboard")
            else evidence_store.phase_e_cohorts(as_of_epoch) if evidence_store is not None else ()
        )
        data = dashboard_data(
            history, cutoff_epoch=cutoff_epoch, snapshot=snapshot,
            now_epoch=as_of_epoch, evidence_counts=counts, phase_e_cohorts=cohorts,
        )
        if path == "/":
            status, content_type, body = "200 OK", "text/html; charset=utf-8", dashboard_page(data)
        elif path == "/api/dashboard":
            status, content_type, body = "200 OK", "application/json", json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
        start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body)))])
        return [body]

    return application


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the ATOM numerical dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    evidence_store = PostgresEvidenceStore(os.environ["DATABASE_URL"])
    state = LiveMarketState(evidence_store=evidence_store)
    start_alpaca_poller(state)
    start_alpaca_g2_poller(state)
    start_alpaca_options_poller(state)
    app = create_app(state=state, evidence_store=evidence_store)
    with make_server(args.host, args.port, app) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
