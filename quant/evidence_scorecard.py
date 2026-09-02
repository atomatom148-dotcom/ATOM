"""E-1 read-only evidence scorecard (E-1A, E-1B, E-1C).

Controlling law: ``docs/e-1-evidence-scorecard-freeze.md`` as amended by
E-1A, E-1B, and E-1C. Every statistic, count, selection rule, label, and guard below is fixed
by that document. The reader streams existing evidence through one explicitly
read-only ``REPEATABLE READ`` transaction, hydrates admissibility only through
the two authorized proof seams, computes the frozen statistics as pure
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
from typing import Iterable, Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo

CONTRACT = "docs/e-1-evidence-scorecard-freeze.md"
CODE_VERSION = "ATOM-E1-SCORECARD-5"

LAYER_FAMILY = "FAMILY"
LAYER_V9 = "V9"

HORIZON_SECONDS: Mapping[str, int] = {
    "30S": 30, "1M": 60, "5M": 300, "15M": 900, "30M": 1800, "1H": 3600,
}
HORIZON_ORDER: tuple[str, ...] = tuple(HORIZON_SECONDS)

NEW_YORK = ZoneInfo("America/New_York")
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)

BOOTSTRAP_RESAMPLES = 200_000
BOOTSTRAP_SEED = 0
INTERVAL_WIDE = 0.999
INTERVAL_NARROW = 0.95

MIN_ECONOMIC_WINDOWS = 100
MIN_SESSIONS = 10
MULTIPLICITY_BUDGET = 100
FALSE_CANDIDATE_RATE = (1.0 - INTERVAL_WIDE) / 2.0
COST_BPS = 0.0
OUTCOME_RESOLUTION_BOUND_SECONDS = 5.0

STATEMENT_TIMEOUT_MS = 60_000
PROOF_BATCH = 65_536
READONLY_URL_ENV = "ATOM_E1_SCORECARD_READONLY_DATABASE_URL"
READONLY_ROLE = "atom_e1_scorecard_reader"

LABEL_INSUFFICIENT = "INSUFFICIENT"
LABEL_NOISE = "NOISE"
LABEL_CANDIDATE = "CANDIDATE"
REASON_BUDGET = "MULTIPLICITY_BUDGET_EXCEEDED"

KIND_ABSTAIN = "ABSTAIN"
KIND_INVALID_OUTCOME = "INVALID_OUTCOME"
KIND_TIE = "TIE"
KIND_DECIDED = "DECIDED"

EVIDENCE_TABLES = (
    "public.forecasts", "public.forecast_outcomes",
    "public.atom_v9_v4_forecasts", "public.atom_v9_v4_outcomes",
)


# --------------------------------------------------------------------------
# Rows and windows
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Row:
    """One population candidate: a forecast, its outcome, and proof status.

    ``admissible`` and ``outcome_eligible`` are decided only by the proof seams
    (or by the test that constructs the row); the statistics never re-derive
    them.
    """

    layer: str
    cell: tuple[str, ...]
    horizon: str
    cutoff_epoch: float
    forecast_bps: float | None
    outcome_bps: float | None
    record_key: str
    admissible: bool
    outcome_eligible: bool


@dataclass(frozen=True, slots=True)
class CellCounts:
    n_rows: int
    n_inadmissible: int
    n_non_rth: int
    n_overlap_excluded: int
    n_windows: int

    @property
    def n_population(self) -> int:
        return self.n_rows - self.n_inadmissible


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


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


def window_kind(row: Row) -> str:
    forecast = _finite(row.forecast_bps)
    if forecast is None or not forecast:          # exactly 0 (finite guaranteed above)
        return KIND_ABSTAIN
    outcome = _finite(row.outcome_bps)
    if not row.outcome_eligible or outcome is None:
        return KIND_INVALID_OUTCOME
    if not outcome:                               # exactly 0
        return KIND_TIE
    return KIND_DECIDED


class CellSelector:
    """Sequential horizon-spaced window selection for one cell.

    Rows must arrive ordered by ``(session, cutoff, record_key)``. The selector
    restarts at each session and keeps every count the freeze requires.
    """

    __slots__ = ("cell", "layer", "horizon", "_last", "_last_session",
                 "_last_order", "n_rows", "n_inadmissible", "n_non_rth",
                 "n_overlap_excluded", "windows")

    def __init__(self, layer: str, cell: tuple[str, ...], horizon: str) -> None:
        if horizon not in HORIZON_SECONDS:
            raise ValueError(f"unknown horizon {horizon!r}")
        self.layer = layer
        self.cell = cell
        self.horizon = horizon
        self._last: float | None = None
        self._last_session: date | None = None
        self._last_order: tuple | None = None
        self.n_rows = 0
        self.n_inadmissible = 0
        self.n_non_rth = 0
        self.n_overlap_excluded = 0
        self.windows: list[Row] = []

    def feed(self, row: Row) -> None:
        if (row.layer, row.cell, row.horizon) != (self.layer, self.cell, self.horizon):
            raise ValueError("row belongs to a different cell")
        session = session_of(row.cutoff_epoch)
        order = (session, row.cutoff_epoch, row.record_key)
        if self._last_order is not None and order < self._last_order:
            raise ValueError("rows must be ordered by (session, cutoff, record_key)")
        self._last_order = order
        self.n_rows += 1
        if not row.admissible:
            self.n_inadmissible += 1
            return
        if not is_rth_window(row.cutoff_epoch, row.horizon):
            self.n_non_rth += 1
            return
        if session != self._last_session:
            self._last_session = session
            self._last = None
        if (self._last is not None and
                row.cutoff_epoch < self._last + HORIZON_SECONDS[row.horizon]):
            self.n_overlap_excluded += 1
            return
        self._last = row.cutoff_epoch
        self.windows.append(row)

    def counts(self) -> CellCounts:
        return CellCounts(self.n_rows, self.n_inadmissible, self.n_non_rth,
                          self.n_overlap_excluded, len(self.windows))


def select_cells(rows: Iterable[Row]) -> dict[tuple[str, tuple[str, ...]], CellSelector]:
    """Feed an ordered stream into one selector per cell."""

    selectors: dict[tuple[str, tuple[str, ...]], CellSelector] = {}
    for row in rows:
        key = (row.layer, row.cell)
        selector = selectors.get(key)
        if selector is None:
            selector = CellSelector(row.layer, row.cell, row.horizon)
            selectors[key] = selector
        selector.feed(row)
    return selectors


# --------------------------------------------------------------------------
# Statistics (pure)
# --------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float:
    return float(sum(values)) / len(values)


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    try:
        value = statistics.correlation(list(xs), list(ys))
    except statistics.StatisticsError:
        return None
    return value if math.isfinite(value) else None


def percentile_interval(sorted_values: Sequence[float], level: float) -> tuple[float, float]:
    if not sorted_values:
        raise ValueError("no bootstrap statistics")
    count = len(sorted_values)
    alpha = 1.0 - level
    lower = int(math.floor((alpha / 2.0) * (count - 1)))
    upper = int(math.ceil((1.0 - alpha / 2.0) * (count - 1)))
    return float(sorted_values[lower]), float(sorted_values[upper])


def session_bootstrap(
    sums_by_session: Mapping[date, float],
    counts_by_session: Mapping[date, int],
    rng: random.Random,
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> list[float]:
    """Session-clustered bootstrap of a ratio-of-sums mean.

    Draws ``n_sessions`` sessions with replacement from the sorted session
    list on every resample, consuming ``rng`` in order; the statistic is the
    sum of drawn sums over the sum of drawn counts.
    """

    sessions = sorted(sums_by_session)
    if not sessions:
        return []
    sums = [float(sums_by_session[s]) for s in sessions]
    counts = [int(counts_by_session[s]) for s in sessions]
    indices = range(len(sessions))
    results: list[float] = []
    for _ in range(resamples):
        drawn = rng.choices(indices, k=len(sessions))
        numerator = 0.0
        denominator = 0
        for index in drawn:
            numerator += sums[index]
            denominator += counts[index]
        results.append(numerator / denominator)
    results.sort()
    return results


def hit_rate_by_magnitude_quartile(
    ordered: Sequence[tuple[float, int]],
) -> list[dict[str, object]]:
    """``ordered`` is ``(|forecast|, hit)`` already sorted by the frozen order."""

    count = len(ordered)
    if count < 4:
        return []
    result = []
    for quartile in range(4):
        start = (quartile * count) // 4
        stop = ((quartile + 1) * count) // 4
        members = ordered[start:stop]
        result.append({
            "quartile": quartile + 1,
            "n": len(members),
            "min_abs_forecast_bps": members[0][0],
            "max_abs_forecast_bps": members[-1][0],
            "hit_rate": _mean([hit for _, hit in members]),
        })
    return result


def is_eligible(n_economic: int, n_sessions: int) -> bool:
    return n_economic >= MIN_ECONOMIC_WINDOWS and n_sessions >= MIN_SESSIONS


def cell_metrics(
    counts: CellCounts,
    windows: Sequence[Row],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, object]:
    """All frozen per-cell statistics. Labels are assigned later, receipt-wide."""

    kinds = [window_kind(w) for w in windows]
    n_abstain = kinds.count(KIND_ABSTAIN)
    n_invalid = kinds.count(KIND_INVALID_OUTCOME)
    n_ties = kinds.count(KIND_TIE)
    n_decided = kinds.count(KIND_DECIDED)
    n_economic = n_ties + n_decided

    signed_sums: dict[date, float] = {}
    signed_counts: dict[date, int] = {}
    hit_sums: dict[date, float] = {}
    hit_counts: dict[date, int] = {}
    signed_all: list[float] = []
    forecasts_econ: list[float] = []
    outcomes_econ: list[float] = []
    hits_all: list[int] = []
    magnitude_order: list[tuple[float, float, str, int]] = []

    for row, kind in zip(windows, kinds):
        if kind not in (KIND_TIE, KIND_DECIDED):
            continue
        forecast = float(row.forecast_bps)
        outcome = float(row.outcome_bps)
        session = session_of(row.cutoff_epoch)
        signed = math.copysign(1.0, forecast) * outcome
        signed_sums[session] = signed_sums.get(session, 0.0) + signed
        signed_counts[session] = signed_counts.get(session, 0) + 1
        signed_all.append(signed)
        forecasts_econ.append(forecast)
        outcomes_econ.append(outcome)
        if kind == KIND_DECIDED:
            hit = 1 if (forecast > 0.0) == (outcome > 0.0) else 0   # both nonzero here
            hit_sums[session] = hit_sums.get(session, 0.0) + hit
            hit_counts[session] = hit_counts.get(session, 0) + 1
            hits_all.append(hit)
            magnitude_order.append((abs(forecast), row.cutoff_epoch, row.record_key, hit))

    n_sessions = len(signed_counts)
    n_decided_sessions = len(hit_counts)

    hit_rate = _mean(hits_all) if hits_all else None
    z_hit = ((hit_rate - 0.5) * math.sqrt(n_decided) / 0.5
             if hit_rate is not None else None)
    mean_signed = _mean(signed_all) if signed_all else None

    magnitude_order.sort(key=lambda item: (item[0], item[1], item[2]))
    quartiles = hit_rate_by_magnitude_quartile(
        [(magnitude, hit) for magnitude, _, _, hit in magnitude_order])

    rng = random.Random(seed)
    signed_boot = session_bootstrap(signed_sums, signed_counts, rng, resamples=resamples)
    hit_boot = (session_bootstrap(hit_sums, hit_counts, rng, resamples=resamples)
                if n_decided > 0 else [])

    wide = percentile_interval(signed_boot, INTERVAL_WIDE) if signed_boot else None
    narrow = percentile_interval(signed_boot, INTERVAL_NARROW) if signed_boot else None
    hit_narrow = percentile_interval(hit_boot, INTERVAL_NARROW) if hit_boot else None

    return {
        "n_rows": counts.n_rows,
        "n_inadmissible": counts.n_inadmissible,
        "n_population": counts.n_population,
        "n_non_rth": counts.n_non_rth,
        "n_overlap_excluded": counts.n_overlap_excluded,
        "n_windows": counts.n_windows,
        "n_abstain": n_abstain,
        "n_invalid_outcome": n_invalid,
        "n_ties": n_ties,
        "n_decided": n_decided,
        "n_economic": n_economic,
        "n_sessions": n_sessions,
        "n_decided_sessions": n_decided_sessions,
        "hit_rate": hit_rate,
        "z_hit_descriptive": z_hit,
        "mean_signed_bps": mean_signed,
        "corr_forecast_outcome": pearson(forecasts_econ, outcomes_econ),
        "calibration_corr": pearson([abs(v) for v in forecasts_econ],
                                    [abs(v) for v in outcomes_econ]),
        "hit_rate_by_magnitude_quartile": quartiles,
        "bootstrap_mean_signed_bps": {
            "interval_999": list(wide) if wide else None,
            "interval_95": list(narrow) if narrow else None,
        },
        "bootstrap_hit_rate": {
            "interval_95": list(hit_narrow) if hit_narrow else None,
        },
        "eligible": is_eligible(n_economic, n_sessions),
    }


def assign_labels(cells: Sequence[dict[str, object]]) -> dict[str, object]:
    """Receipt-wide classification under the fixed multiplicity budget.

    Mutates each cell dict by adding ``label`` and ``classification_reason``.
    Returns the receipt-level budget fields.
    """

    n_eligible = sum(1 for cell in cells if cell["eligible"])
    exceeded = n_eligible > MULTIPLICITY_BUDGET
    for cell in cells:
        if not cell["eligible"]:
            cell["label"] = LABEL_INSUFFICIENT
            cell["classification_reason"] = None
            continue
        if exceeded:
            cell["label"] = None
            cell["classification_reason"] = REASON_BUDGET
            continue
        interval = cell["bootstrap_mean_signed_bps"]["interval_999"]
        candidate = interval is not None and interval[0] > 0.0
        cell["label"] = LABEL_CANDIDATE if candidate else LABEL_NOISE
        cell["classification_reason"] = None
    return {
        "n_cells_eligible": n_eligible,
        "multiplicity_budget": MULTIPLICITY_BUDGET,
        "expected_false_candidates": n_eligible * FALSE_CANDIDATE_RATE,
        "multiplicity_budget_exceeded": exceeded,
        "usable_for_e2": not exceeded,
    }


def _cell_fields(layer: str, cell: tuple[str, ...]) -> dict[str, str]:
    if layer == LAYER_FAMILY:
        quant_id, formula_version, symbol, horizon = cell
        return {"quant_id": quant_id, "formula_version": formula_version,
                "symbol": symbol, "horizon": horizon}
    v3_model_version, symbol, horizon, cohort_id, cohort_hash = cell
    return {"v3_model_version": v3_model_version, "symbol": symbol,
            "horizon": horizon, "cohort_id": cohort_id, "cohort_hash": cohort_hash}


def _cell_sort_key(layer: str, cell: tuple[str, ...]) -> tuple:
    if layer == LAYER_FAMILY:
        quant_id, formula_version, symbol, horizon = cell
        return (0, quant_id, formula_version, symbol, HORIZON_ORDER.index(horizon))
    v3_model_version, symbol, horizon, cohort_id, cohort_hash = cell
    return (1, v3_model_version, symbol, cohort_id, cohort_hash, HORIZON_ORDER.index(horizon))


def score_cells(
    selectors: Mapping[tuple[str, tuple[str, ...]], CellSelector],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[dict[str, object]]:
    """Score every cell in fixed order. No filtering by cell."""

    cells = []
    for key in sorted(selectors, key=lambda item: _cell_sort_key(item[0], item[1])):
        selector = selectors[key]
        metrics = cell_metrics(selector.counts(), selector.windows,
                               resamples=resamples, seed=seed)
        cells.append({"layer": selector.layer,
                      "cell": _cell_fields(selector.layer, selector.cell),
                      **metrics})
    return cells


# --------------------------------------------------------------------------
# Receipt
# --------------------------------------------------------------------------


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_receipt(
    *,
    sessions: Sequence[date],
    cells: Sequence[Mapping[str, object]],
    budget: Mapping[str, object],
    rows_read: Mapping[str, int],
    proof_rows: Mapping[str, int],
    snapshot: str,
    current_user: str,
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
        "cost_bps": COST_BPS,
        "snapshot": snapshot,
        "bootstrap": {
            "method": "session_clustered_percentile_ratio_of_sums",
            "resamples": resamples,
            "seed": seed,
            "intervals": [INTERVAL_WIDE, INTERVAL_NARROW],
        },
        "classification": {
            "min_economic_windows": MIN_ECONOMIC_WINDOWS,
            "min_sessions": MIN_SESSIONS,
            "candidate_rule": "interval_999_lower_bound_of_mean_signed_bps > 0",
            **dict(budget),
        },
        "rows_read": dict(rows_read),
        "proof_rows": dict(proof_rows),
        "query_wall_seconds": query_wall_seconds,
        "cells": list(cells),
        "forecast_writes": 0,
        "outcome_writes": 0,
        "evidence_writes": 0,
        "read_only": True,
        "rls_full_read_verified": True,
        "current_user": current_user,
    }
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return {**body, "sha256": digest}


# --------------------------------------------------------------------------
# Guards and sessions
# --------------------------------------------------------------------------


def refuse_during_rth(now: datetime | None = None) -> None:
    current = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    if current.weekday() < 5 and RTH_OPEN <= current.time() < RTH_CLOSE:
        raise SystemExit(
            f"E-1 reader refused: {current.isoformat()} is inside regular trading hours")


def recent_weekday_sessions(count: int, today: date) -> list[date]:
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


def parse_sessions(text: str) -> list[date]:
    sessions = sorted({date.fromisoformat(part.strip())
                       for part in text.split(",") if part.strip()})
    if not sessions:
        raise ValueError("no sessions supplied")
    return sessions


def session_epoch_bounds(sessions: Sequence[date]) -> tuple[float, float]:
    first, last = min(sessions), max(sessions)
    lo = datetime.combine(first, dtime(0, 0), NEW_YORK).timestamp()
    hi = datetime.combine(last + timedelta(days=1), dtime(0, 0), NEW_YORK).timestamp()
    return lo, hi


def batched(items: Sequence, size: int) -> Iterator[Sequence]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


# --------------------------------------------------------------------------
# Database seam (read-only, one snapshot)
# --------------------------------------------------------------------------

GUARD_SQL = """
SELECT current_user,
       bool_or(has_table_privilege(current_user, t, 'INSERT')
               OR has_table_privilege(current_user, t, 'UPDATE')
               OR has_table_privilege(current_user, t, 'DELETE')),
       pg_catalog.pg_current_snapshot()::text,
       now()
FROM unnest(%(tables)s::text[]) AS t
"""

RLS_FULL_READ_SQL = """
SELECT t.qualified,
       has_table_privilege(current_user, t.qualified, 'SELECT') AS can_select,
       EXISTS (
           SELECT 1 FROM pg_catalog.pg_policies AS p
           WHERE p.schemaname = 'public' AND p.tablename = t.short
             AND p.cmd IN ('SELECT', 'ALL') AND p.permissive = 'PERMISSIVE'
             AND p.qual = 'true'
             AND (current_user::name = ANY(p.roles) OR 'public'::name = ANY(p.roles))
       ) AS permissive_full_read,
       EXISTS (
           SELECT 1 FROM pg_catalog.pg_policies AS p
           WHERE p.schemaname = 'public' AND p.tablename = t.short
             AND p.cmd IN ('SELECT', 'ALL') AND p.permissive = 'RESTRICTIVE'
             AND (current_user::name = ANY(p.roles) OR 'public'::name = ANY(p.roles))
       ) AS restrictive_applies
FROM (VALUES ('public.forecasts', 'forecasts'),
             ('public.forecast_outcomes', 'forecast_outcomes'),
             ('public.atom_v9_v4_forecasts', 'atom_v9_v4_forecasts'),
             ('public.atom_v9_v4_outcomes', 'atom_v9_v4_outcomes')) AS t(qualified, short)
ORDER BY t.qualified
"""

FAMILY_STREAM_SQL = """
SELECT f.forecast_id, f.quant_id, f.formula_version, f.symbol, f.horizon,
       f.cutoff_epoch, f.maturity_epoch, f.forecast_bps,
       o.outcome_bps, o.resolved_epoch
FROM public.forecasts AS f
LEFT JOIN public.forecast_outcomes AS o ON o.forecast_id = f.forecast_id
WHERE f.cutoff_epoch >= %(lo)s AND f.cutoff_epoch < %(hi)s
  AND f.horizon = ANY(%(horizons)s::text[])
ORDER BY f.quant_id, f.formula_version, f.symbol, f.horizon,
         f.cutoff_epoch, f.forecast_id
"""

FAMILY_PROOF_SQL = """
SELECT record_id, commit_observed_at
FROM atom_v9_internal.read_legacy_evidence_publications_for_records(
    %(kind)s, %(as_of)s, %(ids)s::bigint[])
"""

V9_STREAM_SQL = """
SELECT f.forecast_record_id, f.forecast_record_hash, f.v3_model_version,
       f.symbol, f.horizon,
       f.record_json->>'cohort_id', f.record_json->>'cohort_hash',
       f.record_json, o.outcome_record_hash, o.record_json
FROM public.atom_v9_v4_forecasts AS f
LEFT JOIN LATERAL (
    SELECT o.outcome_record_hash, o.record_json
    FROM public.atom_v9_v4_outcomes AS o
    WHERE o.forecast_record_id = f.forecast_record_id
      AND o.record_json->>'target_timing_status' = 'VERIFIED'
    ORDER BY o.created_at, o.outcome_record_id
    LIMIT 1
) AS o ON true
WHERE f.cutoff_at >= %(lo_ts)s AND f.cutoff_at < %(hi_ts)s
  AND f.horizon = ANY(%(horizons)s::text[])
  AND f.record_json->>'evidence_origin' = 'PRODUCTION'
ORDER BY f.v3_model_version, f.symbol, f.horizon,
         f.record_json->>'cohort_id', f.record_json->>'cohort_hash',
         f.cutoff_at, f.forecast_record_id
"""

V9_PROOF_SQL = """
SELECT ids.id, p.forecast_record_id, p.forecast_record_hash, p.commit_observed_at,
       p.target_endpoint, p.proof_eligible, p.proof_method
FROM unnest(%(ids)s::text[]) AS ids(id)
LEFT JOIN LATERAL atom_v9_internal.read_forecast_commit_proof(ids.id) AS p ON true
"""

COUNT_SQL = {
    "forecasts": ("SELECT count(*) FROM public.forecasts "
                  "WHERE cutoff_epoch >= %(lo)s AND cutoff_epoch < %(hi)s"),
    "forecast_outcomes": ("SELECT count(*) FROM public.forecast_outcomes AS o "
                          "JOIN public.forecasts AS f ON f.forecast_id = o.forecast_id "
                          "WHERE f.cutoff_epoch >= %(lo)s AND f.cutoff_epoch < %(hi)s"),
    "atom_v9_v4_forecasts": ("SELECT count(*) FROM public.atom_v9_v4_forecasts "
                             "WHERE cutoff_at >= %(lo_ts)s AND cutoff_at < %(hi_ts)s"),
    "atom_v9_v4_outcomes": ("SELECT count(*) FROM public.atom_v9_v4_outcomes AS o "
                            "JOIN public.atom_v9_v4_forecasts AS f "
                            "ON f.forecast_record_id = o.forecast_record_id "
                            "WHERE f.cutoff_at >= %(lo_ts)s AND f.cutoff_at < %(hi_ts)s"),
}


def family_rows(
    raw_batch: Sequence[Sequence[object]],
    forecast_proofs: Mapping[int, datetime],
    outcome_proofs: Mapping[int, datetime],
) -> list[Row]:
    """Map one streamed FAMILY batch plus its proof lookups to rows."""

    rows = []
    for (forecast_id, quant_id, formula_version, symbol, horizon, cutoff_epoch,
         maturity_epoch, forecast_bps, outcome_bps, resolved_epoch) in raw_batch:
        record_id = int(forecast_id)
        maturity = float(maturity_epoch)
        commit_at = forecast_proofs.get(record_id)
        admissible = commit_at is not None and commit_at.timestamp() < maturity
        resolved = _finite(resolved_epoch)
        outcome_eligible = (
            admissible and record_id in outcome_proofs and resolved is not None
            and maturity <= resolved <= maturity + OUTCOME_RESOLUTION_BOUND_SECONDS
        )
        rows.append(Row(
            layer=LAYER_FAMILY,
            cell=(str(quant_id), str(formula_version), str(symbol), str(horizon)),
            horizon=str(horizon),
            cutoff_epoch=float(cutoff_epoch),
            forecast_bps=_finite(forecast_bps),
            outcome_bps=_finite(outcome_bps),
            record_key=str(record_id).zfill(20),
            admissible=admissible,
            outcome_eligible=outcome_eligible,
        ))
    return rows


def v9_rows(
    raw_batch: Sequence[Sequence[object]],
    proofs: Mapping[str, Sequence[object] | None],
) -> list[Row]:
    """Map one streamed V9 batch plus its commit-proof lookups to rows.

    Persistence eligibility is hydrated only through
    ``V4AWriter._apply_commit_proof`` with the authoritative proof row.
    """

    from quant.v9_v4a_evidence import (
        V4AWriter, deserialize_forecast_record, deserialize_outcome_record,
    )

    rows = []
    for (record_id, forecast_hash, v3_model_version, symbol, horizon, cohort_id,
         cohort_hash, forecast_json, outcome_hash, outcome_json) in raw_batch:
        forecast = deserialize_forecast_record(forecast_json, expected_hash=str(forecast_hash))
        proof = proofs.get(str(record_id))
        forecast = V4AWriter._apply_commit_proof(
            forecast, tuple(proof) if proof is not None else None)
        admissible = forecast.persistence_proof_eligible is True
        outcome_bps = None
        outcome_eligible = False
        if outcome_json is not None:
            outcome = deserialize_outcome_record(outcome_json, expected_hash=str(outcome_hash))
            outcome_bps = _finite(outcome.actual_return_bps)
            outcome_eligible = (
                admissible and outcome.target_timing_status == "VERIFIED"
                and outcome.proof_eligible is True
            )
        rows.append(Row(
            layer=LAYER_V9,
            cell=(str(v3_model_version), str(symbol), str(horizon),
                  str(cohort_id), str(cohort_hash)),
            horizon=str(horizon),
            cutoff_epoch=float(forecast.cutoff_at.timestamp()),
            forecast_bps=_finite(forecast.expected_return_bps),
            outcome_bps=outcome_bps,
            record_key=str(record_id),
            admissible=admissible,
            outcome_eligible=outcome_eligible,
        ))
    return rows


def read_and_select(database_url: str, sessions: Sequence[date]):
    """Stream both layers inside one read-only REPEATABLE READ snapshot.

    Returns ``(selectors, rows_read, proof_rows, snapshot, current_user,
    wall_seconds)``. Refuses any credential other than the dedicated E-1 role,
    any credential that holds a write privilege on the four evidence tables,
    and any credential that fails full-read verification on any of them.
    """

    import psycopg

    lo, hi = session_epoch_bounds(sessions)
    params = {
        "lo": lo, "hi": hi,
        "lo_ts": datetime.fromtimestamp(lo, timezone.utc),
        "hi_ts": datetime.fromtimestamp(hi, timezone.utc),
        "horizons": list(HORIZON_ORDER),
    }
    started = time.monotonic()
    proof_rows = {"DIRECTIONAL_FORECAST": 0, "DIRECTIONAL_OUTCOME": 0,
                  "read_forecast_commit_proof": 0}
    selectors: dict[tuple[str, tuple[str, ...]], CellSelector] = {}

    with psycopg.connect(
        database_url,
        connect_timeout=10,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
    ) as connection:
        connection.read_only = True
        connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(GUARD_SQL, {"tables": list(EVIDENCE_TABLES)})
                current_user, can_write, snapshot, as_of = cursor.fetchone()
                verify_reader_identity(current_user)
                if can_write:
                    raise SystemExit(
                        f"E-1 reader refused: {current_user!r} holds a write privilege")
                cursor.execute(RLS_FULL_READ_SQL, ())
                verify_full_read(current_user, cursor.fetchall())

                rows_read: dict[str, int] = {}
                for table, sql in COUNT_SQL.items():
                    cursor.execute(sql, params)
                    rows_read[table] = int(cursor.fetchone()[0])

            with connection.cursor(name="e1_family") as stream, connection.cursor() as lookup:
                stream.itersize = PROOF_BATCH
                stream.execute(FAMILY_STREAM_SQL, params)
                while True:
                    batch = stream.fetchmany(PROOF_BATCH)
                    if not batch:
                        break
                    ids = [int(row[0]) for row in batch]
                    proofs = {}
                    for kind in ("DIRECTIONAL_FORECAST", "DIRECTIONAL_OUTCOME"):
                        lookup.execute(FAMILY_PROOF_SQL,
                                       {"kind": kind, "as_of": as_of, "ids": ids})
                        found = {int(rid): observed for rid, observed in lookup.fetchall()}
                        proof_rows[kind] += len(found)
                        proofs[kind] = found
                    for row in family_rows(batch, proofs["DIRECTIONAL_FORECAST"],
                                           proofs["DIRECTIONAL_OUTCOME"]):
                        _feed(selectors, row)

            with connection.cursor(name="e1_v9") as stream, connection.cursor() as lookup:
                stream.itersize = PROOF_BATCH
                stream.execute(V9_STREAM_SQL, params)
                while True:
                    batch = stream.fetchmany(PROOF_BATCH)
                    if not batch:
                        break
                    ids = [str(row[0]) for row in batch]
                    lookup.execute(V9_PROOF_SQL, {"ids": ids})
                    proofs = {}
                    for record in lookup.fetchall():
                        key, *proof = record
                        proofs[str(key)] = None if proof[0] is None else proof
                    proof_rows["read_forecast_commit_proof"] += sum(
                        1 for value in proofs.values() if value is not None)
                    for row in v9_rows(batch, proofs):
                        _feed(selectors, row)

    return (selectors, rows_read, proof_rows, str(snapshot), str(current_user),
            time.monotonic() - started)


def verify_reader_identity(current_user: object) -> None:
    """Refuse any credential other than the dedicated E-1 role (E-1C)."""

    if str(current_user) != READONLY_ROLE:
        raise SystemExit(
            f"E-1 reader refused: {current_user!r} is not {READONLY_ROLE!r}")


def verify_full_read(current_user: object, rows: Sequence[Sequence[object]]) -> None:
    """Refuse unless every evidence table is fully readable by ``current_user``.

    Each row is ``(table, can_select, permissive_full_read, restrictive_applies)``
    as returned by ``RLS_FULL_READ_SQL``. A policy-filtered read would score an
    empty ledger as if it were evidence, so anything short of a permissive
    ``USING (true)`` SELECT policy with no applicable restrictive policy refuses.
    """

    seen = {str(row[0]) for row in rows}
    if seen != set(EVIDENCE_TABLES):
        raise SystemExit("E-1 reader refused: full-read verification did not cover all four tables")
    for table, can_select, permissive_full_read, restrictive_applies in rows:
        if can_select is not True or permissive_full_read is not True or restrictive_applies:
            raise SystemExit(
                f"E-1 reader refused: {current_user!r} fails full-read verification on {table}")


def _feed(selectors: dict, row: Row) -> None:
    key = (row.layer, row.cell)
    selector = selectors.get(key)
    if selector is None:
        selector = CellSelector(row.layer, row.cell, row.horizon)
        selectors[key] = selector
    selector.feed(row)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m quant.evidence_scorecard",
        description="E-1 read-only evidence scorecard (emits one JSON receipt).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sessions", help="comma-separated ISO dates (ET sessions)")
    group.add_argument("--recent-sessions", type=int,
                       help="most recent N weekdays strictly before today (ET)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    refuse_during_rth()
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

    (selectors, rows_read, proof_rows, snapshot, current_user,
     wall) = read_and_select(database_url, sessions)
    cells = score_cells(selectors)
    budget = assign_labels(cells)
    receipt = build_receipt(
        sessions=sessions, cells=cells, budget=budget, rows_read=rows_read,
        proof_rows=proof_rows, snapshot=snapshot, current_user=current_user,
        query_wall_seconds=wall, generated_at=datetime.now(timezone.utc))
    sys.stdout.write(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
