"""E-1 read-only evidence scorecard.

Controlling law: docs/e-1-evidence-scorecard-freeze.md. Every statistic below
is fixed by that document. This module reads existing evidence, computes the
frozen statistics over non-overlapping regular-trading-hours windows, and
emits one JSON receipt. It writes nothing anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

CODE_VERSION = "ATOM-E1-SCORECARD-1"
FREEZE_DOCUMENT = "docs/e-1-evidence-scorecard-freeze.md"

HORIZON_SECONDS = {"30S": 30, "1M": 60, "5M": 300, "15M": 900, "30M": 1800, "1H": 3600}
HORIZON_ORDER = tuple(HORIZON_SECONDS)

MARKET_TZ = ZoneInfo("America/New_York")
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
RTH_SECONDS = 6.5 * 3600.0

BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 0
INTERVAL_LEVELS = (0.999, 0.95)
CLASSIFICATION_LEVEL = 0.999

MIN_ECONOMIC_WINDOWS = 100
MIN_SESSIONS = 10
PARTIAL_SESSION_MIN_COVERAGE = 0.9
STATEMENT_TIMEOUT_SECONDS = 60

LAYER_FAMILY = "FAMILY"
LAYER_V9 = "V9"
LAYERS = (LAYER_FAMILY, LAYER_V9)

LABEL_INSUFFICIENT = "INSUFFICIENT"
LABEL_NOISE = "NOISE"
LABEL_CANDIDATE = "CANDIDATE"

KIND_ABSTAIN = "ABSTAIN"
KIND_UNRESOLVED = "UNRESOLVED"
KIND_TIE = "TIE"
KIND_DECIDED = "DECIDED"


@dataclass(frozen=True, slots=True)
class Observation:
    """One forecast/outcome pair as read from the ledger. Immutable."""

    layer: str
    cell: tuple[str, ...]
    horizon: str
    session: str
    cutoff_epoch: float
    forecast_bps: float | None
    outcome_bps: float | None

    def __post_init__(self) -> None:
        if self.layer not in LAYERS:
            raise ValueError(f"unknown layer {self.layer!r}")
        if self.horizon not in HORIZON_SECONDS:
            raise ValueError(f"unknown horizon {self.horizon!r}")
        if not isinstance(self.cutoff_epoch, (int, float)) or isinstance(self.cutoff_epoch, bool):
            raise ValueError("cutoff_epoch must be numeric")
        if not math.isfinite(self.cutoff_epoch):
            raise ValueError("cutoff_epoch must be finite")
        date.fromisoformat(self.session)


# --------------------------------------------------------------------------- #
# Sessions and regular trading hours
# --------------------------------------------------------------------------- #

def session_rth_bounds(session: str) -> tuple[float, float]:
    """Epoch seconds of the RTH open and close for one market date."""

    day = date.fromisoformat(session)
    open_at = datetime.combine(day, RTH_OPEN, tzinfo=MARKET_TZ)
    close_at = datetime.combine(day, RTH_CLOSE, tzinfo=MARKET_TZ)
    return open_at.timestamp(), close_at.timestamp()


def market_session_of(epoch: float) -> str:
    """Market date (America/New_York) that contains an epoch instant."""

    return datetime.fromtimestamp(epoch, MARKET_TZ).date().isoformat()


def is_rth_window(cutoff_epoch: float, horizon: str, session: str) -> bool:
    """True when [cutoff, cutoff + horizon] lies inside RTH of the session."""

    open_epoch, close_epoch = session_rth_bounds(session)
    return open_epoch <= cutoff_epoch and (
        cutoff_epoch + HORIZON_SECONDS[horizon] <= close_epoch)


def refuse_during_rth(now: datetime | None = None) -> None:
    """The reader must not run during regular XNYS session hours."""

    current = (now or datetime.now(timezone.utc)).astimezone(MARKET_TZ)
    if current.weekday() < 5 and RTH_OPEN <= current.time() < RTH_CLOSE:
        raise RuntimeError(
            "E-1 reader refused: regular trading hours in America/New_York")


def default_sessions(count: int, today: date | None = None) -> list[str]:
    """The most recent `count` weekdays strictly before today (market date).

    Holidays are not known here; they surface as sessions with zero windows
    and are reported as excluded by `score`.
    """

    if count < 1:
        raise ValueError("session count must be at least 1")
    current = today or datetime.now(MARKET_TZ).date()
    sessions: list[str] = []
    cursor = current
    while len(sessions) < count:
        cursor = cursor - timedelta(days=1)
        if cursor.weekday() < 5:
            sessions.append(cursor.isoformat())
    return sorted(sessions)


# --------------------------------------------------------------------------- #
# Frozen statistics — pure functions
# --------------------------------------------------------------------------- #

def _finite(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def observation_kind(observation: Observation) -> str:
    """ABSTAIN (forecast unusable), UNRESOLVED (outcome unusable), TIE, DECIDED."""

    forecast = observation.forecast_bps
    if not _finite(forecast) or forecast == 0:
        return KIND_ABSTAIN
    outcome = observation.outcome_bps
    if not _finite(outcome):
        return KIND_UNRESOLVED
    if outcome == 0:
        return KIND_TIE
    return KIND_DECIDED


def select_independent_windows(
    observations: Iterable[Observation],
) -> tuple[dict[tuple[str, tuple[str, ...]], list[Observation]], int]:
    """Keep the earliest-cutoff observation per epoch-aligned horizon interval.

    Returns cells mapped to their windows (sorted by cutoff) and the number of
    discarded overlapping observations. Deterministic: ties on cutoff resolve
    by the smaller forecast value, then the smaller outcome value.
    """

    chosen: dict[tuple[str, tuple[str, ...]], dict[int, Observation]] = {}
    discarded = 0
    for observation in observations:
        key = (observation.layer, observation.cell)
        interval = math.floor(
            observation.cutoff_epoch / HORIZON_SECONDS[observation.horizon])
        bucket = chosen.setdefault(key, {})
        incumbent = bucket.get(interval)
        if incumbent is None:
            bucket[interval] = observation
            continue
        discarded += 1
        if _sort_key(observation) < _sort_key(incumbent):
            bucket[interval] = observation
    cells = {
        key: sorted(bucket.values(), key=_sort_key)
        for key, bucket in chosen.items()
    }
    return cells, discarded


def _sort_key(observation: Observation) -> tuple[float, float, float]:
    forecast = observation.forecast_bps if _finite(observation.forecast_bps) else math.inf
    outcome = observation.outcome_bps if _finite(observation.outcome_bps) else math.inf
    return (observation.cutoff_epoch, forecast, outcome)


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson correlation; None when undefined (n < 2 or zero variance)."""

    if len(xs) != len(ys):
        raise ValueError("pearson requires equal-length inputs")
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    value = sxy / math.sqrt(sxx * syy)
    return max(-1.0, min(1.0, value))


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile on an ascending sequence (numpy default)."""

    if not sorted_values:
        raise ValueError("quantile of empty sequence")
    if not 0.0 <= q <= 1.0:
        raise ValueError("quantile level must be within [0, 1]")
    position = (len(sorted_values) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(sorted_values[low])
    weight = position - low
    return float(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


def clustered_bootstrap(
    session_values: dict[str, Sequence[float]],
    statistic: Callable[[Sequence[float]], float],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    levels: Sequence[float] = INTERVAL_LEVELS,
) -> dict[str, tuple[float, float]]:
    """Session-clustered percentile bootstrap of `statistic`.

    Sessions (clusters) are resampled with replacement, all values of each
    drawn session are concatenated, and the statistic is recomputed. Returns
    two-sided percentile intervals keyed by level string (e.g. "0.999").
    """

    sessions = sorted(session for session, values in session_values.items() if values)
    if not sessions:
        raise ValueError("bootstrap requires at least one session with values")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    rng = random.Random(seed)
    count = len(sessions)
    draws: list[float] = []
    for _ in range(resamples):
        pooled: list[float] = []
        for _ in range(count):
            pooled.extend(session_values[sessions[rng.randrange(count)]])
        draws.append(float(statistic(pooled)))
    draws.sort()
    intervals: dict[str, tuple[float, float]] = {}
    for level in levels:
        if not 0.0 < level < 1.0:
            raise ValueError("interval level must be within (0, 1)")
        tail = (1.0 - level) / 2.0
        intervals[_level_key(level)] = (
            quantile(draws, tail), quantile(draws, 1.0 - tail))
    return intervals


def _level_key(level: float) -> str:
    return format(level, "g")


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def magnitude_quartiles(decided: Sequence[Observation]) -> list[dict[str, object]]:
    """Hit rate within four near-equal chunks of decided windows by |forecast|."""

    ordered = sorted(decided, key=lambda o: (abs(o.forecast_bps), _sort_key(o)))
    n = len(ordered)
    result: list[dict[str, object]] = []
    for index in range(4):
        start = (n * index) // 4
        stop = (n * (index + 1)) // 4
        chunk = ordered[start:stop]
        hits = sum(1 for o in chunk if _same_sign(o))
        result.append({
            "quartile": index + 1,
            "n": len(chunk),
            "hit_rate": (hits / len(chunk)) if chunk else None,
            "min_abs_forecast_bps": abs(chunk[0].forecast_bps) if chunk else None,
            "max_abs_forecast_bps": abs(chunk[-1].forecast_bps) if chunk else None,
        })
    return result


def _same_sign(observation: Observation) -> bool:
    return math.copysign(1.0, observation.forecast_bps) == math.copysign(
        1.0, observation.outcome_bps)


def _signed_outcome(observation: Observation) -> float:
    """sign(forecast) * outcome; ties contribute exactly zero."""

    if observation.outcome_bps == 0:
        return 0.0
    return math.copysign(1.0, observation.forecast_bps) * observation.outcome_bps


def cell_metrics(
    windows: Sequence[Observation],
    *,
    cost_bps: float,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, object]:
    """All frozen per-cell statistics plus the label, over RTH windows only."""

    if not _finite(cost_bps):
        raise ValueError("cost_bps must be finite")
    rth: list[Observation] = []
    n_excluded_non_rth = 0
    for observation in windows:
        if is_rth_window(observation.cutoff_epoch, observation.horizon, observation.session):
            rth.append(observation)
        else:
            n_excluded_non_rth += 1
    kinds = {observation: observation_kind(observation) for observation in rth}
    abstain = [o for o in rth if kinds[o] == KIND_ABSTAIN]
    unresolved = [o for o in rth if kinds[o] == KIND_UNRESOLVED]
    ties = [o for o in rth if kinds[o] == KIND_TIE]
    decided = [o for o in rth if kinds[o] == KIND_DECIDED]
    economic = [o for o in rth if kinds[o] in (KIND_TIE, KIND_DECIDED)]
    sessions = sorted({o.session for o in economic})

    n_decided = len(decided)
    n_economic = len(economic)
    hits = sum(1 for o in decided if _same_sign(o))
    hit_rate = (hits / n_decided) if n_decided else None
    z_hit = (((hit_rate - 0.5) * math.sqrt(n_decided) / 0.5)
             if n_decided else None)
    signed = [_signed_outcome(o) for o in economic]
    mean_signed = _mean(signed) if economic else None
    mean_cost_adjusted = (mean_signed - cost_bps) if economic else None
    corr = pearson([o.forecast_bps for o in economic],
                   [o.outcome_bps for o in economic]) if economic else None
    calibration = pearson([abs(o.forecast_bps) for o in economic],
                          [abs(o.outcome_bps) for o in economic]) if economic else None

    intervals_signed: dict[str, tuple[float, float]] | None = None
    intervals_hit: dict[str, tuple[float, float]] | None = None
    if economic:
        by_session_signed: dict[str, list[float]] = {}
        for o in economic:
            by_session_signed.setdefault(o.session, []).append(_signed_outcome(o))
        intervals_signed = {
            level: (low - cost_bps, high - cost_bps)
            for level, (low, high) in clustered_bootstrap(
                by_session_signed, _mean, resamples=resamples, seed=seed).items()
        }
    if decided:
        by_session_hit: dict[str, list[float]] = {}
        for o in decided:
            by_session_hit.setdefault(o.session, []).append(1.0 if _same_sign(o) else 0.0)
        intervals_hit = clustered_bootstrap(
            by_session_hit, _mean, resamples=resamples, seed=seed, levels=(0.95,))

    metrics: dict[str, object] = {
        "n_windows": len(windows),
        "n_excluded_non_rth": n_excluded_non_rth,
        "n_rth_windows": len(rth),
        "n_abstain": len(abstain),
        "n_unresolved": len(unresolved),
        "n_ties": len(ties),
        "n_decided": n_decided,
        "n_economic": n_economic,
        "n_sessions": len(sessions),
        "hit_rate": hit_rate,
        "z_hit_descriptive_only": z_hit,
        "mean_signed_bps": mean_signed,
        "mean_cost_adjusted_bps": mean_cost_adjusted,
        "corr_forecast_outcome": corr,
        "calibration_corr_abs": calibration,
        "hit_rate_by_magnitude_quartile": magnitude_quartiles(decided),
        "bootstrap_mean_cost_adjusted_bps": (
            {level: list(bounds) for level, bounds in intervals_signed.items()}
            if intervals_signed else None),
        "bootstrap_hit_rate": (
            {level: list(bounds) for level, bounds in intervals_hit.items()}
            if intervals_hit else None),
    }
    metrics["label"] = label_cell(metrics)
    return metrics


def label_cell(metrics: dict[str, object]) -> str:
    """INSUFFICIENT / CANDIDATE / NOISE exactly as frozen. Nothing else."""

    if metrics["n_economic"] < MIN_ECONOMIC_WINDOWS or metrics["n_sessions"] < MIN_SESSIONS:
        return LABEL_INSUFFICIENT
    intervals = metrics["bootstrap_mean_cost_adjusted_bps"]
    if not intervals:
        return LABEL_INSUFFICIENT
    low, _high = intervals[_level_key(CLASSIFICATION_LEVEL)]
    if low > 0.0:
        return LABEL_CANDIDATE
    return LABEL_NOISE


def session_coverage(observations: Iterable[Observation], session: str) -> float:
    """Fraction of RTH spanned by forecasts observed inside RTH for a session."""

    open_epoch, close_epoch = session_rth_bounds(session)
    cutoffs = [
        o.cutoff_epoch for o in observations
        if o.session == session and open_epoch <= o.cutoff_epoch <= close_epoch
    ]
    if not cutoffs:
        return 0.0
    return (max(cutoffs) - min(cutoffs)) / RTH_SECONDS


def score(
    observations: Sequence[Observation],
    *,
    sessions: Sequence[str],
    cost_bps: float,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, object]:
    """Score every cell of every layer over the accepted sessions."""

    requested = sorted(set(sessions))
    for session in requested:
        date.fromisoformat(session)
    coverage = {s: session_coverage(observations, s) for s in requested}
    accepted = [s for s in requested if coverage[s] >= PARTIAL_SESSION_MIN_COVERAGE]
    excluded = {s: coverage[s] for s in requested if s not in accepted}
    accepted_set = set(accepted)
    in_scope = [o for o in observations if o.session in accepted_set]
    cells, discarded = select_independent_windows(in_scope)
    scored = []
    for (layer, cell), windows in sorted(cells.items()):
        metrics = cell_metrics(windows, cost_bps=cost_bps, resamples=resamples, seed=seed)
        scored.append({"layer": layer, "cell": list(cell), "horizon": windows[0].horizon,
                       **metrics})
    scored.sort(key=lambda c: (c["layer"], HORIZON_ORDER.index(c["horizon"]), c["cell"]))
    return {
        "sessions_requested": requested,
        "sessions_scored": accepted,
        "sessions_excluded_partial": {s: round(v, 6) for s, v in excluded.items()},
        "session_coverage": {s: round(v, 6) for s, v in coverage.items()},
        "observations_in_scope": len(in_scope),
        "overlapping_observations_discarded": discarded,
        "cells": scored,
        "label_counts": {
            label: sum(1 for c in scored if c["label"] == label)
            for label in (LABEL_INSUFFICIENT, LABEL_NOISE, LABEL_CANDIDATE)
        },
    }


# --------------------------------------------------------------------------- #
# Receipt
# --------------------------------------------------------------------------- #

def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True)


def build_receipt(
    scored: dict[str, object],
    *,
    cost_bps: float,
    rows_read: dict[str, int],
    query_seconds: float,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, object]:
    body: dict[str, object] = {
        "receipt": "ATOM_E1_EVIDENCE_SCORECARD",
        "code_version": CODE_VERSION,
        "freeze_document": FREEZE_DOCUMENT,
        "cost_bps": cost_bps,
        "cost_bps_note": (
            "executable-cost assumption (declared round-trip quoted-spread "
            "crossing plus slippage); not a measured realized or effective spread"),
        "bootstrap": {"resamples": resamples, "seed": seed,
                      "levels": [_level_key(level) for level in INTERVAL_LEVELS],
                      "classification_level": _level_key(CLASSIFICATION_LEVEL)},
        "thresholds": {"min_economic_windows": MIN_ECONOMIC_WINDOWS,
                       "min_sessions": MIN_SESSIONS,
                       "partial_session_min_coverage": PARTIAL_SESSION_MIN_COVERAGE},
        "rows_read": dict(rows_read),
        "query_wall_seconds": round(query_seconds, 3),
        "forecast_writes": 0,
        "outcome_writes": 0,
        "evidence_writes": 0,
        "read_only": True,
        **scored,
    }
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return {**body, "receipt_sha256": digest}


# --------------------------------------------------------------------------- #
# Thin read-only database seam
# --------------------------------------------------------------------------- #

FAMILY_SQL = """
SELECT DISTINCT ON (f.quant_id, f.formula_version, f.symbol, f.horizon, h.secs,
                    floor(f.cutoff_epoch / h.secs))
       f.quant_id, f.formula_version, f.symbol, f.horizon,
       f.cutoff_epoch, f.forecast_bps, o.outcome_bps
FROM public.forecasts AS f
JOIN (VALUES ('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900),
             ('30M', 1800), ('1H', 3600)) AS h(horizon, secs)
  ON h.horizon = f.horizon
LEFT JOIN public.forecast_outcomes AS o ON o.forecast_id = f.forecast_id
WHERE f.symbol = %(symbol)s
  AND f.cutoff_epoch >= %(start_epoch)s AND f.cutoff_epoch < %(end_epoch)s
  AND f.created_epoch >= %(start_epoch)s
ORDER BY f.quant_id, f.formula_version, f.symbol, f.horizon, h.secs,
         floor(f.cutoff_epoch / h.secs), f.cutoff_epoch, f.forecast_id
"""

V9_SQL = """
SELECT DISTINCT ON (f.v3_model_version, f.symbol, f.horizon, h.secs,
                    floor(extract(epoch FROM f.cutoff_at) / h.secs))
       f.v3_model_version, f.symbol, f.horizon,
       f.forecast_record_hash, f.record_json,
       o.outcome_record_hash, o.record_json
FROM public.atom_v9_v4_forecasts AS f
JOIN (VALUES ('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900),
             ('30M', 1800), ('1H', 3600)) AS h(horizon, secs)
  ON h.horizon = f.horizon
LEFT JOIN public.atom_v9_v4_outcomes AS o
  ON o.forecast_record_id = f.forecast_record_id
 AND o.record_json->>'target_timing_status' = 'VERIFIED'
WHERE f.symbol = %(symbol)s
  AND f.cutoff_at >= to_timestamp(%(start_epoch)s)
  AND f.cutoff_at < to_timestamp(%(end_epoch)s)
ORDER BY f.v3_model_version, f.symbol, f.horizon, h.secs,
         floor(extract(epoch FROM f.cutoff_at) / h.secs), f.cutoff_at,
         f.forecast_record_id
"""


def session_read_bounds(session: str) -> tuple[float, float]:
    """Whole market day [04:00, 20:00) America/New_York as epoch seconds."""

    day = date.fromisoformat(session)
    start = datetime.combine(day, dtime(4, 0), tzinfo=MARKET_TZ)
    end = datetime.combine(day, dtime(20, 0), tzinfo=MARKET_TZ)
    return start.timestamp(), end.timestamp()


def connect_read_only(database_url: str):
    """One explicitly read-only psycopg connection with a bounded timeout."""

    import psycopg  # imported lazily so the statistics need no driver

    connection = psycopg.connect(
        database_url,
        connect_timeout=10,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_SECONDS * 1000}",
    )
    connection.read_only = True
    return connection


def read_family_observations(connection, session: str, *, symbol: str = "COIN",
                             ) -> list[Observation]:
    start_epoch, end_epoch = session_read_bounds(session)
    with connection.cursor() as cursor:
        cursor.execute(FAMILY_SQL, {"symbol": symbol, "start_epoch": start_epoch,
                                    "end_epoch": end_epoch})
        rows = cursor.fetchall()
    observations = []
    for quant_id, formula_version, sym, horizon, cutoff_epoch, forecast_bps, outcome_bps in rows:
        observations.append(Observation(
            layer=LAYER_FAMILY,
            cell=(str(quant_id), str(formula_version), str(sym), str(horizon)),
            horizon=str(horizon),
            session=session,
            cutoff_epoch=float(cutoff_epoch),
            forecast_bps=_as_float(forecast_bps),
            outcome_bps=_as_float(outcome_bps),
        ))
    return observations


def read_v9_observations(connection, session: str, *, symbol: str = "COIN",
                         decode_forecast=None, decode_outcome=None) -> list[Observation]:
    if decode_forecast is None or decode_outcome is None:
        from quant.v9_v4a_evidence import (  # existing seams; no new parser
            deserialize_forecast_record, deserialize_outcome_record,
        )
        decode_forecast = decode_forecast or deserialize_forecast_record
        decode_outcome = decode_outcome or deserialize_outcome_record
    start_epoch, end_epoch = session_read_bounds(session)
    with connection.cursor() as cursor:
        cursor.execute(V9_SQL, {"symbol": symbol, "start_epoch": start_epoch,
                                "end_epoch": end_epoch})
        rows = cursor.fetchall()
    observations = []
    for (model_version, sym, horizon, forecast_hash, forecast_json,
         outcome_hash, outcome_json) in rows:
        forecast = decode_forecast(forecast_json, expected_hash=str(forecast_hash))
        outcome_bps = None
        if outcome_json is not None:
            outcome = decode_outcome(outcome_json, expected_hash=str(outcome_hash))
            if getattr(outcome, "target_timing_status", None) != "VERIFIED":
                raise RuntimeError("E-1 reader: non-VERIFIED outcome returned by query")
            outcome_bps = _as_float(getattr(outcome, "actual_return_bps"))
        observations.append(Observation(
            layer=LAYER_V9,
            cell=(str(model_version), str(sym), str(horizon)),
            horizon=str(horizon),
            session=session,
            cutoff_epoch=float(forecast.cutoff_at.timestamp()),
            forecast_bps=_as_float(getattr(forecast, "expected_return_bps")),
            outcome_bps=outcome_bps,
        ))
    return observations


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_observations(connection, sessions: Sequence[str], *, symbol: str = "COIN",
                      ) -> tuple[list[Observation], dict[str, int], float]:
    started = time.monotonic()
    observations: list[Observation] = []
    rows_read = {LAYER_FAMILY: 0, LAYER_V9: 0}
    for session in sessions:
        family = read_family_observations(connection, session, symbol=symbol)
        v9 = read_v9_observations(connection, session, symbol=symbol)
        rows_read[LAYER_FAMILY] += len(family)
        rows_read[LAYER_V9] += len(v9)
        observations.extend(family)
        observations.extend(v9)
    return observations, rows_read, time.monotonic() - started


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m quant.evidence_scorecard",
        description="E-1 read-only evidence scorecard; emits one JSON receipt.")
    parser.add_argument("--cost-bps", type=float, required=True,
                        help="declared executable-cost assumption in bps (echoed)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sessions", help="comma-separated market dates YYYY-MM-DD")
    group.add_argument("--session-count", type=int, default=MIN_SESSIONS,
                       help="most recent weekdays before today (default 10)")
    parser.add_argument("--symbol", default="COIN")
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    parser.add_argument("--allow-rth", action="store_true",
                        help="testing only; the freeze forbids RTH runs")
    return parser


def main(argv: Sequence[str] | None = None, *, connection=None, now=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.allow_rth:
        refuse_during_rth(now)
    if args.resamples != BOOTSTRAP_RESAMPLES:
        raise SystemExit(
            f"E-1 freezes resamples at {BOOTSTRAP_RESAMPLES}; got {args.resamples}")
    sessions = (sorted(set(s.strip() for s in args.sessions.split(",") if s.strip()))
                if args.sessions else default_sessions(args.session_count))
    if connection is None:
        database_url = os.environ.get(args.database_url_env)
        if not database_url:
            raise SystemExit(f"{args.database_url_env} is not set")
        connection = connect_read_only(database_url)
    try:
        observations, rows_read, query_seconds = read_observations(
            connection, sessions, symbol=args.symbol)
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()
    scored = score(observations, sessions=sessions, cost_bps=args.cost_bps)
    receipt = build_receipt(scored, cost_bps=args.cost_bps, rows_read=rows_read,
                            query_seconds=query_seconds)
    sys.stdout.write(canonical_json(receipt) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
