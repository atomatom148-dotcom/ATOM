"""Thin, data-only ATOM Quant web surface using the Python standard library."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
import signal
from html import escape
import time
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Callable, Iterable
from wsgiref.simple_server import make_server

from .g2_cross_asset import CrossAssetState
from .history import MidpointHistory
from .evidence import EvidenceStore, PostgresEvidenceStore
from .live_market import (
    MAX_BTC_AGE_SECONDS, LatestMarketDisplay, LiveMarketState, LiveSnapshot,
    start_alpaca_g2_poller, start_alpaca_options_poller, start_alpaca_poller,
    start_massive_ndx_poller,
)
from .q1_momentum import calculate_momentum
from .q2_mean_reversion import calculate_mean_reversion
from .q3_volatility import calculate_volatility
from .q10_options_vol import MAX_SURFACE_AGE_SECONDS
from .v9_production import FORMULA_VERSION_MAP
from .v9_telemetry import latest_v9_observation
from .v9_v4d_integration import OperationalMetrics


HORIZON_LABELS = ("30S", "1M", "5M", "15M", "30M", "1H")
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
    "q3_volatility": "Volatility",
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
_WEB_ENDPOINT_METRIC_PATHS = frozenset({
    "/",
    "/health",
    "/ready",
    "/api/g2-cross-asset",
    "/api/v9-math",
    "/api/performance",
    "/api/phase-e",
    "/api/historical-replay",
    "/api/live",
    "/api/dashboard",
})
_WEB_ENDPOINT_NOT_FOUND_METRIC = "not_found"


@dataclass(frozen=True, slots=True)
class DashboardEvidenceSnapshot:
    counts: tuple[int, int] | None = None
    phase_e_cohorts: tuple[object, ...] = ()
    as_of_epoch: float | None = None
    status: str = "UNAVAILABLE"
    historical_replay: object | None = None


class DashboardEvidenceCache:
    """Background-only cache; WSGI requests never scan evidence history."""

    def __init__(self, store: EvidenceStore, *, clock: Callable[[], float] = time.time):
        self._store = store
        self._clock = clock
        self._lock = Lock()
        self._snapshot = DashboardEvidenceSnapshot()

    def refresh(self) -> DashboardEvidenceSnapshot:
        as_of_epoch = self._clock()
        try:
            counts = self._store.counts()
        except Exception:
            with self._lock:
                return self._snapshot
        with self._lock:
            current = self._snapshot
        historical_replay = current.historical_replay
        historical_reader = getattr(
            self._store, "historical_replay_summary", None,
        )
        if callable(historical_reader):
            try:
                historical_replay = historical_reader()
            except Exception:
                pass
        with self._lock:
            self._snapshot = DashboardEvidenceSnapshot(
                counts, current.phase_e_cohorts,
                current.as_of_epoch, current.status, historical_replay,
            )
        try:
            cohorts = tuple(self._store.phase_e_cohorts(as_of_epoch))
            volatility_reader = getattr(self._store, "volatility_phase_e_cohorts", None)
            if callable(volatility_reader):
                cohorts += tuple(volatility_reader(as_of_epoch))
            candidate = DashboardEvidenceSnapshot(
                counts, cohorts, as_of_epoch, "AVAILABLE", historical_replay,
            )
        except Exception:
            with self._lock:
                return self._snapshot
        with self._lock:
            self._snapshot = candidate
        return candidate

    def snapshot(self) -> DashboardEvidenceSnapshot:
        with self._lock:
            return self._snapshot

    def start(self, *, interval_seconds: float = DASHBOARD_PHASE_E_TTL_SECONDS) -> Thread:
        interval = max(30.0, float(interval_seconds))

        def worker() -> None:
            while True:
                self.refresh()
                time.sleep(interval)

        thread = Thread(target=worker, name="atom-dashboard-evidence-cache", daemon=True)
        thread.start()
        return thread


def dashboard_data(
    history: MidpointHistory | None = None, *, cutoff_epoch: float | None = None,
    snapshot: LiveSnapshot | None = None, now_epoch: float | None = None,
    evidence_counts: tuple[int, int] | None = None,
    phase_e_cohorts: Iterable[object] = (),
    evidence_status: str = "UNAVAILABLE",
    historical_replay_summary: object | None = None,
    cross_asset_state: CrossAssetState | None = None,
    market_display: LatestMarketDisplay | None = None,
    v9_output: object | None = None,
    calculate_missing: bool = True,
) -> dict[str, object]:
    """Build the frozen dashboard structure, optionally using live quant results."""

    supplied = history is not None or snapshot is not None
    if snapshot is not None:
        history = snapshot.history
    history = history if history is not None else MidpointHistory()
    if cutoff_epoch is None:
        cutoff_epoch = history.latest.event_epoch if history.latest else 0.0
    current_epoch = time.time() if now_epoch is None else now_epoch

    q1 = snapshot.momentum if snapshot and snapshot.momentum else (
        calculate_momentum(history, cutoff_epoch=cutoff_epoch)
        if calculate_missing else None
    )
    q2 = snapshot.mean_reversion if snapshot and snapshot.mean_reversion else (
        calculate_mean_reversion(history, cutoff_epoch=cutoff_epoch)
        if calculate_missing else None
    )
    q3 = snapshot.volatility if snapshot and snapshot.volatility else (
        calculate_volatility(history, cutoff_epoch=cutoff_epoch)
        if calculate_missing else None
    )
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
        q1.forecast_bps if q1 else (None,) * 6,
        q2.forecast_bps if q2 else (None,) * 6,
        q3.volatility_bps if q3 else (None,) * 6,
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

    surface_age = (current_epoch - surface.event_epoch
                   if surface is not None else None)
    options_status = (
        "UNAVAILABLE" if surface_age is None or surface_age < 0 else
        "LIVE" if surface_age <= MAX_SURFACE_AGE_SECONDS else "STALE"
    )
    options_data = {
        "status": options_status,
        "as_of_epoch": surface.event_epoch if surface else None,
        "expiration": surface.expiration if surface else None,
        "calls": option_rows(surface.calls) if surface else [],
        "puts": option_rows(surface.puts) if surface else [],
    }
    canonical_cohorts: dict[tuple[str, str], dict[str, object]] = {}
    for cohort in phase_e_cohorts:
        if (cohort.quant_id not in PHASE_E_FAMILY_NAMES or
                cohort.horizon not in PHASE_E_HORIZONS or
                cohort.symbol != "COIN" or
                cohort.formula_version != FORMULA_VERSION_MAP[cohort.quant_id]):
            continue
        canonical_cohorts.setdefault(
            (cohort.quant_id, cohort.horizon),
            dict(asdict(cohort), family=PHASE_E_FAMILY_NAMES[cohort.quant_id]),
        )

    visible_cohorts = []
    for quant_id, family in PHASE_E_FAMILY_NAMES.items():
        for horizon in PHASE_E_HORIZONS:
            observed = canonical_cohorts.get((quant_id, horizon))
            if observed is not None:
                visible_cohorts.append(observed)
                continue
            visible_cohorts.append({
                "quant_id": quant_id, "formula_version": None,
                "symbol": "COIN", "horizon": horizon,
                "forecast_count": None, "matured_count": None,
                "resolved_count": None, "coverage": None,
                "rmse_bps": None, "directional_accuracy": None,
                "mae_bps": None, "bias_bps": None,
                "effective_n": None, "eligible": None,
                "evidence_window": None, "evidence_window_limit": None,
                "evidence_window_truncated": None, "family": family,
            })
    final_values = {metric: [None] * 6 for metric in ("BPS", "MOVE%", "RANGE")}
    results = getattr(v9_output, "final_numbers", ()) if v9_output is not None else ()
    if len(results) == 6:
        final_values["BPS"] = [item.final_bps for item in results]
        final_values["MOVE%"] = [item.move_percent for item in results]
        final_values["RANGE"] = [
            (None if item.range_lower_bps is None or item.range_upper_bps is None
             else f"{item.range_lower_bps:.2f} to {item.range_upper_bps:.2f}")
            for item in results
        ]
    accuracy_by_horizon = {
        item.horizon: item for item in
        (getattr(v9_output, "accuracy", ()) if v9_output is not None else ())
        if item is not None
    }
    v9_accuracy = []
    for horizon in PHASE_E_HORIZONS:
        item = accuracy_by_horizon.get(horizon)
        available = item is not None and item.directional_accuracy is not None
        v9_accuracy.append({
            "horizon": horizon,
            "directional_wins": item.directional_wins if available else None,
            "directional_losses": item.directional_losses if available else None,
            "directional_accuracy": item.directional_accuracy if available else None,
            "directional_effective_n": item.directional_effective_n if available else None,
            "status": item.status if available else "UNAVAILABLE",
        })
    v1_output = getattr(v9_output, "v1", None)
    forecast_cutoff = (v1_output.cutoff_at.timestamp()
                       if v1_output is not None else None)
    v3_output = getattr(v9_output, "v3", None)
    v3_horizons = getattr(v3_output, "horizon_results", ())
    horizon_statuses = (
        [item.status for item in v3_horizons]
        if (len(v3_horizons) == 6 and
            tuple(item.horizon for item in v3_horizons) == PHASE_E_HORIZONS)
        else ["UNAVAILABLE"] * 6
    )
    btc_event_epoch = (
        cross_asset_state.as_of_epoch - cross_asset_state.btc_age_seconds
        if (cross_asset_state is not None and
            cross_asset_state.btc_age_seconds is not None) else None
    )
    return {
        "title": "ATOM QUANT",
        "market": {
            "symbol": (
                market_display.coin_midpoint
                if market_display and market_display.coin_event_epoch is not None
                else history.latest.midpoint if history.latest else None
            ),
            "benchmarks": ["BTC", "QQQ", "NDX"],
            "btc": cross_asset_state.btc_price if cross_asset_state else None,
            "btc_event_epoch": btc_event_epoch,
            "btc_data_age": (current_epoch - btc_event_epoch
                             if btc_event_epoch is not None else None),
            "qqq": (market_display.qqq_midpoint if market_display else
                    snapshot.qqq_history.latest.midpoint
                    if snapshot and snapshot.qqq_history.latest else None),
            "ndx": cross_asset_state.ndx_price if cross_asset_state else None,
            "data_age": (
                current_epoch - market_display.coin_event_epoch
                if market_display and market_display.coin_event_epoch is not None
                else current_epoch - history.latest.event_epoch if history.latest else None
            ),
            "event_epoch": (
                market_display.coin_event_epoch
                if market_display and market_display.coin_event_epoch is not None
                else history.latest.event_epoch if history.latest else None
            ),
            "last_cycle": snapshot.last_cycle if snapshot else (cutoff_epoch if supplied else None),
        },
        "v9": {
            "forecast_cutoff": forecast_cutoff,
            "forecast_age": (current_epoch - forecast_cutoff
                             if forecast_cutoff is not None else None),
            "horizon_statuses": horizon_statuses,
        },
        "horizons": list(HORIZON_LABELS),
        "final_numbers": final_values,
        "v9_accuracy": v9_accuracy,
        "quant_families": families,
        "options_data": options_data,
        "evidence": {
            "Forecasts": evidence_counts[0] if evidence_counts else None,
            "Resolved": evidence_counts[1] if evidence_counts else None,
            "Status": evidence_status,
        },
        "phase_e_cohorts": visible_cohorts,
        "historical_replay": {
            "Status": (
                "AVAILABLE" if historical_replay_summary is not None
                else "UNAVAILABLE"
            ),
            "Certified Sessions": getattr(
                historical_replay_summary, "certified_sessions", None,
            ),
            "Cutoffs": getattr(historical_replay_summary, "cutoff_count", None),
            "Families": getattr(historical_replay_summary, "family_count", 12),
            "Horizons": getattr(historical_replay_summary, "horizon_count", 6),
            "Slots / Cutoff": getattr(
                historical_replay_summary, "slots_per_cutoff", 72,
            ),
            "Available Slots": getattr(
                historical_replay_summary, "available_slot_count", None,
            ),
            "Unavailable Slots": getattr(
                historical_replay_summary, "unavailable_slot_count", None,
            ),
            "Latest Session": getattr(
                historical_replay_summary, "latest_session", None,
            ),
        },
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
            f'{_decimal_cell(value) if decimal and label != "RANGE" else _cell(value)}</td>'
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
    v9_accuracy = data["v9_accuracy"]
    families = data["quant_families"]
    options = data["options_data"]
    evidence = data["evidence"]
    phase_e = data["phase_e_cohorts"]
    historical_replay = data["historical_replay"]
    accuracy_rows = (
        ("WINS", [item["directional_wins"] for item in v9_accuracy]),
        ("LOSSES", [item["directional_losses"] for item in v9_accuracy]),
        ("ACCURACY", [
            "—" if item["directional_accuracy"] is None
            else f'{item["directional_accuracy"] * 100:.1f}%'
            for item in v9_accuracy
        ]),
        ("EFFECTIVE N", [
            "—" if item["directional_effective_n"] is None
            else f'{item["directional_effective_n"]:.2f}'
            for item in v9_accuracy
        ]),
        ("STATUS", [item["status"] for item in v9_accuracy]),
    )
    phase_e_headers = ("FAMILY/HORIZON", "EFFECTIVE N", "ELIGIBLE", "ACC", "RMSE", "MAE", "BIAS", "COVERAGE")
    def phase_e_row(cohort: dict[str, object]) -> tuple[object, ...]:
        return (
            f"{cohort['family']} / {cohort['horizon']}", cohort["effective_n"],
            ("" if cohort["eligible"] is None else
             "YES" if cohort["eligible"] else "NO"),
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
    def option_cell(field: str, value: object) -> str:
        if field in {"Strike", "Bid", "Ask", "Premium", "Spread"}:
            return _decimal_cell(value)
        if field in {"IV", "Delta", "Gamma", "Theta", "Vega"}:
            return "" if value is None else f"{float(value):.4f}"
        return _cell(value)

    def option_table(side: str) -> str:
        body = "".join(
            "<tr>" + "".join(
                f'<td data-dashboard-field="options_data.{side}.{row_index}.{field}">{option_cell(field, row[field])}</td>'
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
<div><div class=label>BTC</div><div class=value data-dashboard-field="market.btc"></div></div><div><div class=label>QQQ</div><div class=value data-dashboard-field="market.qqq">{_decimal_cell(market['qqq'])}</div></div><div><div class=label>NDX</div><div class=value data-dashboard-field="market.ndx">{_decimal_cell(market['ndx'])}</div></div>
<div><div class=label>DATA AGE</div><div class=value data-dashboard-field="market.data_age">{_decimal_cell(market['data_age'], 's')}</div></div><div><div class=label>LAST CYCLE</div><div class=value data-dashboard-field="market.last_cycle">{_cycle_cell(market['last_cycle'])}</div></div></div>
<h2>FINAL NUMBERS</h2>{_table(horizons, final_numbers.items(), section='final_numbers', decimal=True)}
<h2>V9 DIRECTIONAL ACCURACY</h2>{_table(PHASE_E_HORIZONS, accuracy_rows, section='v9_accuracy')}
<h2>12 QUANT FAMILIES</h2>{_table(horizons, ((item['name'], item['values']) for item in families), section='quant_families', decimal=True)}
<h2>OPTIONS DATA</h2><div>STATUS: <span data-dashboard-field="options_data.status">{_cell(options['status'])}</span></div><div>AS OF: <span data-dashboard-field="options_data.as_of_epoch">{_cycle_cell(options['as_of_epoch'])}</span></div><div>EXPIRATION: <span data-dashboard-field="options_data.expiration">{_cell(options['expiration'])}</span></div>{option_table('calls')}{option_table('puts')}
<h2>EVIDENCE</h2>{_table((), ((key, (value,)) for key, value in evidence.items()), section='evidence')}{phase_e_table}
<h2>HISTORICAL REPLAY EVIDENCE</h2>{_table((), ((key, (value,)) for key, value in historical_replay.items()), section='historical_replay')}
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
  let btcExpiryTimer = null;
  let btcRenderGeneration = 0;
  const clearBtc = generation => {{
    if (generation !== btcRenderGeneration) return;
    if (btcExpiryTimer !== null) {{
      clearTimeout(btcExpiryTimer);
      btcExpiryTimer = null;
    }}
    set("market.btc", null, decimal);
  }};
  const renderLive = data => {{
    const generation = ++btcRenderGeneration;
    if (btcExpiryTimer !== null) {{
      clearTimeout(btcExpiryTimer);
      btcExpiryTimer = null;
    }}
    const btcEvent = Number(data.market.btc_event_epoch);
    const btcAge = Date.now() / 1000 - btcEvent;
    const btcLive = data.market.btc_source_status === "LIVE" &&
      Number.isFinite(btcEvent) && Number.isFinite(btcAge) &&
      btcAge >= 0 && btcAge < 5;
    set("market.symbol", data.market.symbol, decimal);
    set("market.btc", btcLive ? data.market.btc : null, decimal);
    if (btcLive) {{
      // Expire from the provider timestamp itself.  A hung or delayed refresh
      // therefore cannot keep a quote visible beyond the five-second limit.
      const remainingMs = Math.max(0, (btcEvent + 5 - Date.now() / 1000) * 1000);
      btcExpiryTimer = setTimeout(() => clearBtc(generation), remainingMs);
    }}
    set("market.qqq", data.market.qqq, decimal);
    set("market.ndx", data.market.ndx, decimal);
    set("market.data_age", data.market.data_age, value => decimal(value, "s"));
    set("market.last_cycle", data.market.last_cycle, cycle);
    Object.entries(data.final_numbers).forEach(([name, values]) =>
      values.forEach((value, index) => set(`final_numbers.${{name}}.${{index}}`, value,
        name === "RANGE" ? text : decimal)));
    const accuracyRows = {{
      "WINS": data.v9_accuracy.map(item => item.directional_wins ?? "—"),
      "LOSSES": data.v9_accuracy.map(item => item.directional_losses ?? "—"),
      "ACCURACY": data.v9_accuracy.map(item => item.directional_accuracy == null ? "—" :
        (item.directional_accuracy * 100).toFixed(1) + "%"),
      "EFFECTIVE N": data.v9_accuracy.map(item => item.directional_effective_n == null ? "—" :
        Number(item.directional_effective_n).toFixed(2)),
      "STATUS": data.v9_accuracy.map(item => item.status)
    }};
    Object.entries(accuracyRows).forEach(([name, values]) =>
      values.forEach((value, index) => set(`v9_accuracy.${{name}}.${{index}}`, value)));
    data.quant_families.forEach(family => family.values.forEach((value, index) =>
      set(`quant_families.${{family.name}}.${{index}}`, value, decimal)));
    set("options_data.status", data.options_data.status);
    set("options_data.as_of_epoch", data.options_data.as_of_epoch, cycle);
    set("options_data.expiration", data.options_data.expiration);
    const optionValue = (field, value) => {{
      if (["Strike", "Bid", "Ask", "Premium", "Spread"].includes(field))
        return decimal(value);
      if (["IV", "Delta", "Gamma", "Theta", "Vega"].includes(field))
        return value == null ? "" : Number(value).toFixed(4);
      return text(value);
    }};
    ["calls", "puts"].forEach(side => {{
      const body = document.getElementById(`options-${{side}}`);
      const fields = {json.dumps(list(option_columns))};
      body.replaceChildren(...data.options_data[side].map(contract => {{
        const row = document.createElement("tr");
        row.replaceChildren(...fields.map(field => {{
          const cell = document.createElement("td");
          cell.textContent = optionValue(field, contract[field]);
          return cell;
        }}));
        return row;
      }}));
    }});
  }};
  const renderEvidence = data => {{
    Object.entries(data.evidence).forEach(([name, value]) =>
      set(`evidence.${{name}}.0`, value));
    Object.entries(data.historical_replay).forEach(([name, value]) =>
      set(`historical_replay.${{name}}.0`, value));
    const phaseEBody = document.getElementById("phase-e-body");
    phaseEBody.replaceChildren(...data.phase_e_cohorts.map(cohort => {{
      const values = [
        `${{cohort.family}} / ${{cohort.horizon}}`, text(cohort.effective_n),
        cohort.eligible == null ? "" : cohort.eligible ? "YES" : "NO",
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
  const refreshLive = async () => {{
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1000);
    try {{
      const response = await fetch("/api/live", {{
        cache: "no-store", signal: controller.signal
      }});
      if (!response.ok) throw new Error(`live request failed: ${{response.status}}`);
      renderLive(await response.json());
    }} catch (_) {{
      // Network/JSON failures are not permission to retain a BTC price whose
      // provider age can no longer be proved.
      clearBtc(++btcRenderGeneration);
    }} finally {{
      clearTimeout(timeout);
      setTimeout(refreshLive, 250);
    }}
  }};
  const refreshEvidence = async () => {{
    try {{
      const response = await fetch("/api/dashboard", {{cache: "no-store"}});
      if (!response.ok) throw new Error(`dashboard request failed: ${{response.status}}`);
      renderEvidence(await response.json());
    }} catch (_) {{
      // Preserve the last successful evidence presentation.
    }} finally {{
      setTimeout(refreshEvidence, 30000);
    }}
  }};
  setTimeout(refreshLive, 250);
  setTimeout(refreshEvidence, 30000);
}})();
</script></body></html>"""
    return document.encode("utf-8")


def create_app(
    history: MidpointHistory | None = None, *, cutoff_epoch: float | None = None,
    state: LiveMarketState | None = None, clock: Callable[[], float] = time.time,
    evidence_store: EvidenceStore | None = None,
    evidence_cache: DashboardEvidenceCache | None = None,
    metrics: OperationalMetrics | None = None,
    monotonic_clock: Callable[[], float] = time.perf_counter,
    readiness_check: Callable[[], bool] | None = None,
) -> Callable:
    """Create the WSGI application, rendering current state on every request."""

    del evidence_store  # retained only for backward-compatible construction
    metrics = metrics or getattr(state, "metrics", None) or OperationalMetrics()

    def apply_btc_source_truth(data: dict[str, object]) -> None:
        statuses = dict(metrics.snapshot().statuses)
        market = data["market"]
        base_status = statuses.get("btc_source_status", "NOT_STARTED")
        age = market.get("btc_data_age")
        live = (
            base_status == "LIVE" and
            isinstance(age, (int, float)) and not isinstance(age, bool) and
            math.isfinite(float(age)) and 0.0 <= float(age) < MAX_BTC_AGE_SECONDS
        )
        market["btc_source_status"] = "LIVE" if live else (
            "NOT_STARTED" if base_status == "NOT_STARTED" else "UNAVAILABLE")
        market["btc_stream_location"] = statuses.get(
            "btc_stream_location", "UNCONFIGURED")
        reason = statuses.get("btc_source_failure_reason")
        market["btc_source_failure_reason"] = (
            None if reason in (None, "NONE") else reason)
        # Keep the raw cached value/event/age in the API for audit, but never
        # render stale BTC as an unlabeled current price.
        market["btc_display"] = market.get("btc") if live else None

    def application(environ: dict[str, object], start_response: Callable) -> list[bytes]:
        path = environ.get("PATH_INFO", "")
        request_started = monotonic_clock()
        original_start_response = start_response
        endpoint_metric = (
            path if path in _WEB_ENDPOINT_METRIC_PATHS
            else _WEB_ENDPOINT_NOT_FOUND_METRIC
        )

        def measured_start_response(status: str, headers: list[tuple[str, str]],
                                    exc_info: object = None) -> object:
            metrics.observe(
                "web_endpoint." + endpoint_metric + ".duration_ms",
                (monotonic_clock() - request_started) * 1000,
            )
            if exc_info is None:
                return original_start_response(status, headers)
            return original_start_response(status, headers, exc_info)

        start_response = measured_start_response
        if path == "/health":
            body = json.dumps({
                "status": "running",
                "commit": os.environ.get("RENDER_GIT_COMMIT"),
            }, separators=(",", ":")).encode()
            start_response("200 OK", [("Content-Type", "application/json"),
                                      ("Content-Length", str(len(body)))])
            return [body]
        if path == "/ready":
            try:
                ready = (
                    readiness_check is not None and
                    readiness_check() is True
                )
            except Exception:
                ready = False
            body = json.dumps({
                "status": "ready" if ready else "not_ready",
            }, separators=(",", ":")).encode()
            start_response(
                "200 OK" if ready else "503 Service Unavailable",
                [("Content-Type", "application/json"),
                 ("Content-Length", str(len(body)))],
            )
            return [body]
        if path == "/api/g2-cross-asset":
            value = state.publication().cross_asset_state if state is not None else None
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
        if path == "/api/performance":
            telemetry = metrics.snapshot()
            body = json.dumps(asdict(telemetry), separators=(",", ":"),
                              allow_nan=False).encode()
            start_response("200 OK", [("Content-Type", "application/json"),
                                      ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/phase-e":
            cached = evidence_cache.snapshot() if evidence_cache is not None else DashboardEvidenceSnapshot()
            if cached.status != "AVAILABLE":
                status, content_type, body = (
                    "503 Service Unavailable", "application/json",
                    b'{"error":"evidence store unavailable"}',
                )
            else:
                body = json.dumps({
                    "as_of_epoch": cached.as_of_epoch,
                    "cohorts": [asdict(cohort) for cohort in cached.phase_e_cohorts],
                }, separators=(",", ":"), allow_nan=False).encode()
                status, content_type = "200 OK", "application/json"
            start_response(status, [("Content-Type", content_type),
                                    ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/historical-replay":
            cached = evidence_cache.snapshot() if evidence_cache is not None else DashboardEvidenceSnapshot()
            if cached.historical_replay is None:
                status, content_type, body = (
                    "503 Service Unavailable", "application/json",
                    b'{"error":"historical replay evidence unavailable"}',
                )
            else:
                body = json.dumps(
                    asdict(cached.historical_replay),
                    separators=(",", ":"), allow_nan=False,
                ).encode()
                status, content_type = "200 OK", "application/json"
            start_response(status, [("Content-Type", content_type),
                                    ("Content-Length", str(len(body)))])
            return [body]
        if path == "/api/live":
            publication = state.publication() if state is not None else None
            snapshot = publication.snapshot if publication is not None else None
            cross_asset_state = (
                publication.cross_asset_state if publication is not None else None
            )
            market_display = publication.market_display if publication is not None else None
            v9_output = publication.v9_output if publication is not None else None
            as_of_epoch = clock()
            data = dashboard_data(
                history, cutoff_epoch=cutoff_epoch, snapshot=snapshot,
                now_epoch=as_of_epoch, cross_asset_state=cross_asset_state,
                market_display=market_display, v9_output=v9_output,
                calculate_missing=False,
            )
            apply_btc_source_truth(data)
            live = {key: data[key] for key in (
                "market", "v9", "final_numbers", "v9_accuracy",
                "quant_families", "options_data",
            )}
            body = json.dumps(
                live, separators=(",", ":"), allow_nan=False,
            ).encode()
            start_response("200 OK", [("Content-Type", "application/json"),
                                      ("Content-Length", str(len(body)))])
            return [body]
        if path not in ("/", "/api/dashboard"):
            body = b"Not Found"
            start_response("404 Not Found", [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ])
            return [body]
        publication = state.publication() if state is not None else None
        snapshot = publication.snapshot if publication is not None else None
        cross_asset_state = (
            publication.cross_asset_state if publication is not None else None
        )
        market_display = publication.market_display if publication is not None else None
        v9_output = publication.v9_output if publication is not None else None
        as_of_epoch = clock()
        cached = evidence_cache.snapshot() if evidence_cache is not None else DashboardEvidenceSnapshot()
        counts = cached.counts
        cohorts = cached.phase_e_cohorts
        data = dashboard_data(
            history, cutoff_epoch=cutoff_epoch, snapshot=snapshot,
            now_epoch=as_of_epoch, evidence_counts=counts, phase_e_cohorts=cohorts,
            evidence_status=cached.status,
            historical_replay_summary=cached.historical_replay,
            cross_asset_state=cross_asset_state, market_display=market_display,
            v9_output=v9_output,
            calculate_missing=False,
        )
        apply_btc_source_truth(data)
        if path == "/":
            status, content_type, body = "200 OK", "text/html; charset=utf-8", dashboard_page(data)
        elif path == "/api/dashboard":
            status, content_type, body = "200 OK", "application/json", json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
        start_response(status, [("Content-Type", content_type), ("Content-Length", str(len(body)))])
        return [body]

    return application


def _start_sim3(simulator_connection_factory: Callable | None,
                utc_clock: Callable[[], datetime]):
    """Construct SIM-3 once from an explicit least-privilege factory."""
    if simulator_connection_factory is None:
        return None
    from .v9_sim2_store import SimulationIntentStore
    from .v9_sim3_capture import Sim3Telemetry, SimulationCaptureAdapter
    telemetry = Sim3Telemetry()
    try:
        store = SimulationIntentStore(simulator_connection_factory)
        adapter = SimulationCaptureAdapter(store, utc_clock, telemetry=telemetry)
        adapter.start()
        return adapter
    except Exception:
        try:
            telemetry.status("FAILED")
        except Exception:
            pass
        return None


def _install_shutdown_handlers(shutdown_requested: Event) -> dict[int, object]:
    """Translate Render/terminal signals into the coordinated drain path."""

    previous = {}
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        previous[signal_number] = signal.getsignal(signal_number)
        signal.signal(signal_number, lambda _signum, _frame: shutdown_requested.set())
    return previous


def _restore_shutdown_handlers(previous: dict[int, object]) -> None:
    for signal_number, handler in previous.items():
        signal.signal(signal_number, handler)


def main(*, simulator_connection_factory: Callable | None = None,
         simulator_utc_clock: Callable[[], datetime] =
         lambda: datetime.now(timezone.utc)) -> None:
    parser = argparse.ArgumentParser(description="Serve the ATOM numerical dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    shutdown_requested = Event()
    previous_handlers = _install_shutdown_handlers(shutdown_requested)
    ledger_worker = state_build_worker = v9_runtime = sim3 = None
    ledger_connection = state_connection = None
    state = None
    poller_threads: list[Thread] = []
    try:
        database_url = os.environ["DATABASE_URL"]
        evidence_store = PostgresEvidenceStore(database_url)
        evidence_cache = DashboardEvidenceCache(evidence_store)
        from .v9_production import (
            ImmutableV2StateProvider, PostgresV2StateBuilder, ProductionV9Runtime,
        )
        metrics = OperationalMetrics()
        v2_provider = ImmutableV2StateProvider(
            PostgresV2StateBuilder(database_url), metrics=metrics,
        )
        v2_provider.start()
        v9_runtime = ProductionV9Runtime(database_url, v2_provider, metrics=metrics)
        from .evidence_outbox import (
            EvidenceLedgerWorker, EvidenceOutbox, PostgresV4BStateBuilder,
            PostgresV4CStateBuilder, PostgresV4StateBuilder,
            V4StateBuildWorker, V4StateCacheRefresher,
        )
        from .v9_v4d_integration import OfflineStateBuildScheduler
        from .v9_v4b_accuracy import AccuracyStateStore
        from .v9_v4c_predictive import V4CStateStore
        import psycopg
        def runtime_connect(url: str):
            return psycopg.connect(
                url, connect_timeout=5, keepalives=1,
                keepalives_idle=5, keepalives_interval=2,
                keepalives_count=3,
            )
        outbox = EvidenceOutbox(metrics=metrics)
        ledger_connection = runtime_connect(database_url)
        state_connection = runtime_connect(database_url)
        cache_refresher = V4StateCacheRefresher(
            compact_store=V4CStateStore(ledger_connection),
            accuracy_store=AccuracyStateStore(ledger_connection),
            compact_cache=v9_runtime.compact_cache,
            accuracy_cache=v9_runtime.accuracy_cache,
            metrics=metrics,
        )
        accuracy_builder = PostgresV4BStateBuilder(state_connection)
        compact_builder = PostgresV4CStateBuilder(state_connection)
        state_builder = PostgresV4StateBuilder(
            accuracy_builder, compact_builder, connection=state_connection)
        state_scheduler = OfflineStateBuildScheduler(
            state_builder.build_and_publish, metrics=metrics,
        )
        state_build_worker = V4StateBuildWorker(
            state_builder, state_scheduler, connection=state_connection,
            connect=runtime_connect, database_url=database_url, metrics=metrics)
        state_build_worker.start()
        sim3 = _start_sim3(simulator_connection_factory, simulator_utc_clock)
        ledger_worker = EvidenceLedgerWorker(
            outbox, evidence_store=PostgresEvidenceStore(
                database_url, connection=ledger_connection),
            connection=ledger_connection,
            connect=runtime_connect, database_url=database_url,
            metrics=metrics, cache_refresher=cache_refresher,
            state_build_submit=state_build_worker.submit,
            simulation_submit=sim3.submit if sim3 is not None else None,
        )
        ledger_worker.start()
        state = LiveMarketState(evidence_outbox=outbox,
                                evidence_acceptance_ready=ledger_worker.is_runtime_owner,
                                evidence_handoff_anchor=ledger_worker.runtime_handoff_anchor,
                                evidence_owner_generation=ledger_worker.runtime_ownership_generation,
                                v9_cycle_handler=v9_runtime.on_quote,
                                metrics=metrics)
        poller_threads = [
            start_alpaca_poller(state, stop_event=shutdown_requested),
            start_alpaca_g2_poller(state, stop_event=shutdown_requested),
            start_massive_ndx_poller(state, stop_event=shutdown_requested),
            start_alpaca_options_poller(state, stop_event=shutdown_requested),
        ]
        # During a rolling replacement, do not report the new process healthy
        # until it either owns the evidence session or has captured a real COIN
        # overlap observation that can bridge the ownership handoff causally.
        handoff_deadline = time.monotonic() + 15.0
        while (not state.runtime_handoff_ready() and
               not shutdown_requested.is_set() and
               time.monotonic() < handoff_deadline):
            shutdown_requested.wait(.05)
        if not state.runtime_handoff_ready():
            raise RuntimeError("evidence handoff observation unavailable")
        evidence_cache.start()
        def readiness_check() -> bool:
            statuses = dict(metrics.snapshot().statuses)
            owner_status = statuses.get("evidence_runtime_owner_status")
            ingress_status = statuses.get("evidence_ingress_status")
            if (owner_status == "ERROR" or
                    ingress_status in {"BUFFER_FULL", "REPLAY_FAILED", "CLOSED"} or
                    statuses.get(
                        "evidence_ledger_worker.last_terminal_failure"
                    ) not in {None, "NONE"}):
                return False
            if ledger_worker.is_runtime_owner():
                return True
            return (
                owner_status in {"WAITING", "WAITING_FOR_LEGACY_WRITER"}
                and state.runtime_handoff_ready()
            )

        app = create_app(
            state=state, evidence_cache=evidence_cache, metrics=metrics,
            readiness_check=readiness_check,
        )
        with make_server(args.host, args.port, app) as server:
            Thread(
                target=lambda: (shutdown_requested.wait(), server.shutdown()),
                name="atom-shutdown-watcher", daemon=True,
            ).start()
            server.serve_forever()
    finally:
        try:
            shutdown_requested.set()
            if state is not None:
                # This barrier completes any currently accepted quote and its
                # outbox put before the ledger transitions to drain-only mode.
                state.stop_accepting_quotes()
            # Release the session owner immediately after the producer barrier
            # and durable FIFO drain.  Network pollers are already stopped and
            # any late return is rejected by the barrier, so holding the lock
            # through their socket joins would create an avoidable bracket gap.
            if ledger_worker is not None:
                ledger_worker.close()
                ledger_worker = None
            elif ledger_connection is not None:
                ledger_connection.close()
                ledger_connection = None
            poller_deadline = time.monotonic() + 11.0
            for thread in poller_threads:
                thread.join(timeout=max(0.0, poller_deadline - time.monotonic()))
            if state_build_worker is not None:
                state_build_worker.close()
            elif state_connection is not None:
                state_connection.close()
            if v9_runtime is not None:
                v9_runtime.close()
            if sim3 is not None:
                try:
                    sim3.stop()
                except Exception:
                    pass
        finally:
            _restore_shutdown_handlers(previous_handlers)


if __name__ == "__main__":
    main()
