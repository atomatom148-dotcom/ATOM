"""E-1 read-only evidence scorecard.

Controlling law: ``docs/e-1-evidence-scorecard-freeze.md``. Every statistic
below is fixed by that document. This module reads existing evidence through
one explicitly read-only credential, computes the frozen statistics as pure
functions over in-memory rows, and prints one JSON receipt to standard output.
It never writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

CONTRACT = "docs/e-1-evidence-scorecard-freeze.md"
CODE_VERSION = "ATOM-E1-SCORECARD-1"

LAYER_FAMILY = "FAMILY"
LAYER_V9 = "V9"

HORIZON_SECONDS: Mapping[str, int] = {
    "30S": 30, "1M": 60, "5M": 300, "15M": 900, "30M": 1800, "1H": 3600,
}
HORIZON_ORDER: tuple[str, ...] = tuple(HORIZON_SECONDS)

NEW_YORK = ZoneInfo("America/New_York")
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 0
INTERVAL_WIDE = 0.999
INTERVAL_NARROW = 0.95

MIN_ECONOMIC_WINDOWS = 100
MIN_SESSIONS = 10

STATEMENT_TIMEOUT_MS = 60_000
READONLY_URL_ENV = "ATOM_E1_SCORECARD_READONLY_DATABASE_URL"

LABEL_INSUFFICIENT = "INSUFFICIENT"
LABEL_NOISE = "NOISE"
LABEL_CANDIDATE = "CANDIDATE"

KIND_ABSTAIN = "ABSTAIN"
KIND_UNRESOLVED = "UNRESOLVED"
KIND_TIE = "TIE"
KIND_DECIDED = "DECIDED"


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Observation:
    """One forecast/outcome pair before window selection."""

    layer: str
    cell: tuple[str, ...]
    horizon: str
    cutoff_epoch: float
    forecast_bps: float | None
    outcome_bps: float | None
    record_key: str


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def observation_kind(observation: Observation) -> str:
    forecast = _finite(observation.forecast_bps)
    if forecast is None or forecast == 0.0:
        return KIND_ABSTAIN
    outcome = _finite(observation.outcome_bps)
    if outcome is None:
        return KIND_UNRESOLVED
    if outcome == 0.0:
        return KIND_TIE
    return KIND_DECIDED


# --------------------------------------------------------------------------
# Sessions and windows
# --------------------------------------------------------------------------


def session_of(cutoff_epoch: float) -> date:
    return datetime.fromtimestamp(cutoff_epoch, timezone.utc).astimezone(NEW_YORK).date()


def is_rth_window(cutoff_epoch: float, horizon: str) -> bool:
    """True only when ``[cutoff, cutoff + horizon]`` lies inside one RTH session."""

    seconds = HORIZON_SECONDS[horizon]
    start = datetime.fromtimestamp(cutoff_epoch, timezone.utc).astimezone(NEW_YORK)
    end = datetime.fromtimestamp(cutoff_epoch + seconds, timezone.utc).astimezone(NEW_YORK)
    if start.weekday() >= 5 or start.date() != end.date():
        return False
    return start.time() >= RTH_OPEN and end.time() <= RTH_CLOSE


def interval_index(cutoff_epoch: float, horizon: str) -> int:
    return int(math.floor(cutoff_epoch / HORIZON_SECONDS[horizon]))


def select_windows(observations: Iterable[Observation]) -> list[Observation]:
    """Keep the earliest-cutoff observation per cell per epoch-aligned interval.

    Ties on cutoff break on ``record_key`` ascending so selection is total and
    reproducible. Output order is deterministic.
    """

    chosen: dict[tuple, Observation] = {}
    for observation in observations:
        if observation.horizon not in HORIZON_SECONDS:
            raise ValueError(f"unknown horizon {observation.horizon!r}")
        key = (observation.layer, observation.cell,
               interval_index(observation.cutoff_epoch, observation.horizon))
        current = chosen.get(key)
        if current is None or (
            (observation.cutoff_epoch, observation.record_key)
            < (current.cutoff_epoch, current.record_key)
        ):
            chosen[key] = observation
    return [chosen[key] for key in sorted(chosen, key=lambda item: (item[0], item[1], item[2]))]


# --------------------------------------------------------------------------
# Statistics (pure)
# --------------------------------------------------------------------------


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    try:
        value = statistics.correlation(list(xs), list(ys))
    except statistics.StatisticsError:
        return None
    return value if math.isfinite(value) else None


def percentile_interval(sorted_values: Sequence[float], level: float) -> tuple[float, float]:
    """Percentile interval over already-sorted bootstrap statistics."""

    if not sorted_values:
        raise ValueError("no bootstrap statistics")
    count = len(sorted_values)
    alpha = 1.0 - level
    lower = int(math.floor((alpha / 2.0) * (count - 1)))
    upper = int(math.ceil((1.0 - alpha / 2.0) * (count - 1)))
    return float(sorted_values[lower]), float(sorted_values[upper])


def session_bootstrap(
    values_by_session: Mapping[date, Sequence[float]],
    statistic: Callable[[Sequence[float]], float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[float]:
    """Session-clustered bootstrap: resample sessions with replacement."""

    sessions = sorted(values_by_session)
    if not sessions:
        return []
    rng = random.Random(seed)
    results: list[float] = []
    for _ in range(resamples):
        drawn = rng.choices(sessions, k=len(sessions))
        pooled: list[float] = []
        for session in drawn:
            pooled.extend(values_by_session[session])
        results.append(float(statistic(pooled)))
    results.sort()
    return results


def _mean(values: Sequence[float]) -> float:
    return float(sum(values)) / len(values)


def hit_rate_by_magnitude_quartile(
    magnitudes: Sequence[float], hits: Sequence[int],
) -> list[dict[str, object]]:
    """Hit rate in four within-cell quartiles of |forecast|, lowest first."""

    if len(magnitudes) < 4:
        return []
    order = sorted(range(len(magnitudes)), key=lambda i: (magnitudes[i], i))
    count = len(order)
    result = []
    for quartile in range(4):
        start = (quartile * count) // 4
        stop = ((quartile + 1) * count) // 4
        members = order[start:stop]
        result.append({
            "quartile": quartile + 1,
            "n": len(members),
            "min_abs_forecast_bps": magnitudes[members[0]],
            "max_abs_forecast_bps": magnitudes[members[-1]],
            "hit_rate": _mean([hits[i] for i in members]),
        })
    return result


def label_cell(
    n_economic: int, n_sessions: int, wide_lower: float | None,
) -> str:
    if n_economic < MIN_ECONOMIC_WINDOWS or n_sessions < MIN_SESSIONS:
        return LABEL_INSUFFICIENT
    if wide_lower is not None and wide_lower > 0.0:
        return LABEL_CANDIDATE
    return LABEL_NOISE


def cell_metrics(
    windows: Sequence[Observation],
    *,
    cost_bps: float,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, object]:
    """All frozen statistics for one cell over already-selected windows."""

    n_windows = len(windows)
    rth = [w for w in windows if is_rth_window(w.cutoff_epoch, w.horizon)]
    n_excluded_non_rth = n_windows - len(rth)

    kinds = {w: observation_kind(w) for w in rth}
    n_abstain = sum(1 for k in kinds.values() if k == KIND_ABSTAIN)
    n_unresolved = sum(1 for k in kinds.values() if k == KIND_UNRESOLVED)
    n_ties = sum(1 for k in kinds.values() if k == KIND_TIE)

    economic = [w for w in rth if kinds[w] in (KIND_TIE, KIND_DECIDED)]
    decided = [w for w in rth if kinds[w] == KIND_DECIDED]
    n_economic = len(economic)
    n_decided = len(decided)

    signed_by_session: dict[date, list[float]] = {}
    signed_all: list[float] = []
    forecasts_econ: list[float] = []
    outcomes_econ: list[float] = []
    for w in economic:
        forecast = float(w.forecast_bps)
        outcome = float(w.outcome_bps)
        signed = math.copysign(1.0, forecast) * outcome
        signed_by_session.setdefault(session_of(w.cutoff_epoch), []).append(signed)
        signed_all.append(signed)
        forecasts_econ.append(forecast)
        outcomes_econ.append(outcome)

    hits_by_session: dict[date, list[float]] = {}
    hits_all: list[int] = []
    magnitudes: list[float] = []
    for w in decided:
        forecast = float(w.forecast_bps)
        outcome = float(w.outcome_bps)
        hit = 1 if math.copysign(1.0, forecast) == math.copysign(1.0, outcome) else 0
        hits_by_session.setdefault(session_of(w.cutoff_epoch), []).append(float(hit))
        hits_all.append(hit)
        magnitudes.append(abs(forecast))

    n_sessions = len(signed_by_session)

    hit_rate = _mean(hits_all) if hits_all else None
    z_hit = ((hit_rate - 0.5) * math.sqrt(n_decided) / 0.5
             if hit_rate is not None else None)
    mean_signed = _mean(signed_all) if signed_all else None
    mean_cost_adjusted = (mean_signed - cost_bps) if mean_signed is not None else None

    corr = pearson(forecasts_econ, outcomes_econ)
    calibration = pearson([abs(v) for v in forecasts_econ],
                          [abs(v) for v in outcomes_econ])
    quartiles = hit_rate_by_magnitude_quartile(magnitudes, hits_all)

    signed_boot = session_bootstrap(
        signed_by_session, lambda v: _mean(v) - cost_bps,
        resamples=resamples, seed=seed)
    hit_boot = session_bootstrap(
        hits_by_session, _mean, resamples=resamples, seed=seed)

    wide = percentile_interval(signed_boot, INTERVAL_WIDE) if signed_boot else None
    narrow = percentile_interval(signed_boot, INTERVAL_NARROW) if signed_boot else None
    hit_narrow = percentile_interval(hit_boot, INTERVAL_NARROW) if hit_boot else None

    return {
        "n_windows": n_windows,
        "n_excluded_non_rth": n_excluded_non_rth,
        "n_abstain": n_abstain,
        "n_unresolved": n_unresolved,
        "n_ties": n_ties,
        "n_decided": n_decided,
        "n_economic": n_economic,
        "n_sessions": n_sessions,
        "hit_rate": hit_rate,
        "z_hit_descriptive": z_hit,
        "mean_signed_bps": mean_signed,
        "mean_cost_adjusted_bps": mean_cost_adjusted,
        "corr_forecast_outcome": corr,
        "calibration_corr": calibration,
        "hit_rate_by_magnitude_quartile": quartiles,
        "bootstrap_mean_cost_adjusted_bps": {
            "interval_999": list(wide) if wide else None,
            "interval_95": list(narrow) if narrow else None,
        },
        "bootstrap_hit_rate": {
            "interval_95": list(hit_narrow) if hit_narrow else None,
        },
        "label": label_cell(n_economic, n_sessions, wide[0] if wide else None),
    }


def score_layer(
    observations: Iterable[Observation],
    *,
    cost_bps: float,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[dict[str, object]]:
    """Select windows and score every cell. No filtering by cell."""

    windows = select_windows(observations)
    by_cell: dict[tuple[str, tuple[str, ...]], list[Observation]] = {}
    for w in windows:
        by_cell.setdefault((w.layer, w.cell), []).append(w)
    cells = []
    for (layer, cell) in sorted(by_cell, key=lambda item: (item[0], _cell_sort_key(item[0], item[1]))):
        metrics = cell_metrics(by_cell[(layer, cell)], cost_bps=cost_bps,
                               resamples=resamples, seed=seed)
        cells.append({"layer": layer, "cell": _cell_fields(layer, cell), **metrics})
    return cells


def _cell_fields(layer: str, cell: tuple[str, ...]) -> dict[str, str]:
    if layer == LAYER_FAMILY:
        quant_id, formula_version, symbol, horizon = cell
        return {"quant_id": quant_id, "formula_version": formula_version,
                "symbol": symbol, "horizon": horizon}
    v3_model_version, symbol, horizon = cell
    return {"v3_model_version": v3_model_version, "symbol": symbol, "horizon": horizon}


def _cell_sort_key(layer: str, cell: tuple[str, ...]) -> tuple:
    horizon = cell[-1]
    order = HORIZON_ORDER.index(horizon) if horizon in HORIZON_ORDER else len(HORIZON_ORDER)
    return (*cell[:-1], order)


# --------------------------------------------------------------------------
# Receipt
# --------------------------------------------------------------------------


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_receipt(
    *,
    sessions: Sequence[date],
    cost_bps: float,
    cells: Sequence[Mapping[str, object]],
    rows_read: Mapping[str, int],
    query_wall_seconds: float,
    generated_at: datetime,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, object]:
    body = {
        "contract": CONTRACT,
        "code_version": CODE_VERSION,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "sessions": [s.isoformat() for s in sessions],
        "cost_bps": cost_bps,
        "bootstrap": {
            "method": "session_clustered_percentile",
            "resamples": resamples,
            "seed": seed,
            "intervals": [INTERVAL_WIDE, INTERVAL_NARROW],
        },
        "classification": {
            "min_economic_windows": MIN_ECONOMIC_WINDOWS,
            "min_sessions": MIN_SESSIONS,
            "candidate_rule": "interval_999_lower_bound_of_mean_cost_adjusted_bps > 0",
        },
        "rows_read": dict(rows_read),
        "query_wall_seconds": query_wall_seconds,
        "cells": list(cells),
        "forecast_writes": 0,
        "outcome_writes": 0,
        "evidence_writes": 0,
        "read_only": True,
    }
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return {**body, "sha256": digest}


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------


def refuse_during_rth(now: datetime | None = None) -> None:
    """The reader must not run during regular XNYS hours. No override."""

    current = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    if current.weekday() < 5 and RTH_OPEN <= current.time() < RTH_CLOSE:
        raise SystemExit(
            f"E-1 reader refused: {current.isoformat()} is inside regular trading hours")


def recent_weekday_sessions(count: int, today: date) -> list[date]:
    """The ``count`` most recent weekdays strictly before ``today`` (ET)."""

    if count < 1:
        raise ValueError("count must be positive")
    sessions: list[date] = []
    cursor = today - timedelta(days=1)
    while len(sessions) < count:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor -= timedelta(days=1)
    sessions.reverse()
    return sessions


def session_epoch_bounds(sessions: Sequence[date]) -> tuple[float, float]:
    """Epoch range covering every calendar day (ET) in ``sessions``."""

    first = min(sessions)
    last = max(sessions)
    lo = datetime.combine(first, dtime(0, 0), NEW_YORK).timestamp()
    hi = datetime.combine(last + timedelta(days=1), dtime(0, 0), NEW_YORK).timestamp()
    return lo, hi


# --------------------------------------------------------------------------
# Database seam (read-only)
# --------------------------------------------------------------------------

_HORIZON_VALUES_SQL = (
    "hz(horizon, secs) AS (VALUES "
    "('30S',30),('1M',60),('5M',300),('15M',900),('30M',1800),('1H',3600))"
)

FAMILY_SQL = f"""
WITH {_HORIZON_VALUES_SQL}
SELECT DISTINCT ON (f.quant_id, f.formula_version, f.symbol, f.horizon,
                    floor(f.cutoff_epoch / hz.secs))
       f.forecast_id, f.quant_id, f.formula_version, f.symbol, f.horizon,
       f.cutoff_epoch, f.forecast_bps, o.outcome_bps
FROM public.forecasts f
JOIN hz ON hz.horizon = f.horizon
LEFT JOIN public.forecast_outcomes o ON o.forecast_id = f.forecast_id
WHERE f.cutoff_epoch >= %(lo)s AND f.cutoff_epoch < %(hi)s
ORDER BY f.quant_id, f.formula_version, f.symbol, f.horizon,
         floor(f.cutoff_epoch / hz.secs), f.cutoff_epoch, f.forecast_id
"""

V9_SQL = f"""
WITH {_HORIZON_VALUES_SQL},
picked AS (
  SELECT DISTINCT ON (f.v3_model_version, f.symbol, f.horizon,
                      floor(extract(epoch FROM f.cutoff_at) / hz.secs))
         f.forecast_record_id, f.forecast_record_hash, f.v3_model_version,
         f.symbol, f.horizon, f.cutoff_at, f.record_json
  FROM public.atom_v9_v4_forecasts f
  JOIN hz ON hz.horizon = f.horizon
  WHERE f.cutoff_at >= %(lo_ts)s AND f.cutoff_at < %(hi_ts)s
  ORDER BY f.v3_model_version, f.symbol, f.horizon,
           floor(extract(epoch FROM f.cutoff_at) / hz.secs),
           f.cutoff_at, f.forecast_record_id
)
SELECT DISTINCT ON (p.forecast_record_id)
       p.forecast_record_id, p.forecast_record_hash, p.v3_model_version,
       p.symbol, p.horizon, p.record_json,
       o.outcome_record_hash, o.record_json
FROM picked p
LEFT JOIN public.atom_v9_v4_outcomes o
  ON o.forecast_record_id = p.forecast_record_id
 AND o.record_json->>'target_timing_status' = 'VERIFIED'
ORDER BY p.forecast_record_id, o.created_at, o.outcome_record_id
"""

COUNT_SQL = {
    "forecasts": "SELECT count(*) FROM public.forecasts WHERE cutoff_epoch >= %(lo)s AND cutoff_epoch < %(hi)s",
    "forecast_outcomes": ("SELECT count(*) FROM public.forecast_outcomes o "
                          "JOIN public.forecasts f ON f.forecast_id = o.forecast_id "
                          "WHERE f.cutoff_epoch >= %(lo)s AND f.cutoff_epoch < %(hi)s"),
    "atom_v9_v4_forecasts": ("SELECT count(*) FROM public.atom_v9_v4_forecasts "
                             "WHERE cutoff_at >= %(lo_ts)s AND cutoff_at < %(hi_ts)s"),
    "atom_v9_v4_outcomes": ("SELECT count(*) FROM public.atom_v9_v4_outcomes o "
                            "JOIN public.atom_v9_v4_forecasts f ON f.forecast_record_id = o.forecast_record_id "
                            "WHERE f.cutoff_at >= %(lo_ts)s AND f.cutoff_at < %(hi_ts)s"),
}

_WRITE_PRIVILEGE_SQL = """
SELECT current_user,
       bool_or(has_table_privilege(current_user, t, 'INSERT')
               OR has_table_privilege(current_user, t, 'UPDATE')
               OR has_table_privilege(current_user, t, 'DELETE'))
FROM unnest(ARRAY['public.forecasts', 'public.forecast_outcomes',
                  'public.atom_v9_v4_forecasts', 'public.atom_v9_v4_outcomes']) AS t
"""


def family_observation(row: Sequence[object]) -> Observation:
    (forecast_id, quant_id, formula_version, symbol, horizon,
     cutoff_epoch, forecast_bps, outcome_bps) = row
    return Observation(
        layer=LAYER_FAMILY,
        cell=(str(quant_id), str(formula_version), str(symbol), str(horizon)),
        horizon=str(horizon),
        cutoff_epoch=float(cutoff_epoch),
        forecast_bps=_finite(forecast_bps),
        outcome_bps=_finite(outcome_bps),
        record_key=str(forecast_id),
    )


def v9_observation(row: Sequence[object]) -> Observation:
    from quant.v9_v4a_evidence import (
        deserialize_forecast_record, deserialize_outcome_record,
    )

    (forecast_record_id, forecast_hash, v3_model_version, symbol, horizon,
     forecast_json, outcome_hash, outcome_json) = row
    forecast = deserialize_forecast_record(forecast_json, expected_hash=str(forecast_hash))
    outcome_bps = None
    if outcome_json is not None:
        outcome = deserialize_outcome_record(outcome_json, expected_hash=str(outcome_hash))
        if outcome.target_timing_status == "VERIFIED":
            outcome_bps = _finite(outcome.actual_return_bps)
    return Observation(
        layer=LAYER_V9,
        cell=(str(v3_model_version), str(symbol), str(horizon)),
        horizon=str(horizon),
        cutoff_epoch=float(forecast.cutoff_at.timestamp()),
        forecast_bps=_finite(forecast.expected_return_bps),
        outcome_bps=outcome_bps,
        record_key=str(forecast_record_id),
    )


def read_observations(database_url: str, sessions: Sequence[date]):
    """Read both layers in one explicitly read-only connection.

    Returns ``(family_observations, v9_observations, rows_read, wall_seconds)``.
    Refuses any credential that holds a write privilege on the four tables.
    """

    import psycopg

    lo, hi = session_epoch_bounds(sessions)
    params = {
        "lo": lo, "hi": hi,
        "lo_ts": datetime.fromtimestamp(lo, timezone.utc),
        "hi_ts": datetime.fromtimestamp(hi, timezone.utc),
    }
    started = time.monotonic()
    with psycopg.connect(
        database_url,
        connect_timeout=10,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
    ) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(_WRITE_PRIVILEGE_SQL, ())
            current_user, can_write = cursor.fetchone()
            if can_write:
                raise SystemExit(
                    f"E-1 reader refused: {current_user!r} holds a write privilege")
            rows_read: dict[str, int] = {}
            for table, sql in COUNT_SQL.items():
                cursor.execute(sql, params)
                rows_read[table] = int(cursor.fetchone()[0])
            cursor.execute(FAMILY_SQL, params)
            family = [family_observation(row) for row in cursor.fetchall()]
            cursor.execute(V9_SQL, params)
            v9 = [v9_observation(row) for row in cursor.fetchall()]
    return family, v9, rows_read, time.monotonic() - started


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def parse_sessions(text: str) -> list[date]:
    sessions = sorted({date.fromisoformat(part.strip()) for part in text.split(",") if part.strip()})
    if not sessions:
        raise ValueError("no sessions supplied")
    return sessions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m quant.evidence_scorecard",
        description="E-1 read-only evidence scorecard (emits one JSON receipt).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sessions", help="comma-separated ISO dates (ET sessions)")
    group.add_argument("--recent-sessions", type=int,
                       help="most recent N weekdays strictly before today (ET)")
    parser.add_argument("--cost-bps", type=float, required=True,
                        help="declared executable round-trip cost assumption in bps")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    refuse_during_rth()
    if not math.isfinite(args.cost_bps) or args.cost_bps < 0.0:
        raise SystemExit("E-1 reader refused: cost_bps must be finite and non-negative")
    database_url = os.environ.get(READONLY_URL_ENV)
    if not database_url:
        raise SystemExit(f"E-1 reader refused: {READONLY_URL_ENV} is not set")
    if args.sessions:
        sessions = parse_sessions(args.sessions)
    else:
        today = datetime.now(timezone.utc).astimezone(NEW_YORK).date()
        sessions = recent_weekday_sessions(args.recent_sessions, today)
    if any(s.weekday() >= 5 for s in sessions):
        raise SystemExit("E-1 reader refused: sessions must be weekdays")

    family, v9, rows_read, wall = read_observations(database_url, sessions)
    cells = score_layer(family, cost_bps=args.cost_bps)
    cells.extend(score_layer(v9, cost_bps=args.cost_bps))
    receipt = build_receipt(
        sessions=sessions, cost_bps=args.cost_bps, cells=cells,
        rows_read=rows_read, query_wall_seconds=wall,
        generated_at=datetime.now(timezone.utc))
    sys.stdout.write(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
