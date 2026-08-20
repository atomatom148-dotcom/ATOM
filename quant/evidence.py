"""Append-only PostgreSQL evidence for live directional forecasts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, Sequence


HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    quant_id: str
    formula_version: str
    cycle_id: str
    symbol: str
    horizon: str
    cutoff_epoch: float
    maturity_epoch: float
    cutoff_midpoint: float
    forecast_bps: float
    created_epoch: float


@dataclass(frozen=True, slots=True)
class PhaseECohortMetrics:
    """Foundational resolved quality for one exact forecast cohort."""

    quant_id: str
    formula_version: str
    symbol: str
    horizon: str
    forecast_count: int
    matured_count: int
    resolved_count: int
    coverage: float | None
    rmse_bps: float | None


class EvidenceStore(Protocol):
    """The deliberately small API has no mutation or deletion operations."""

    def record_cycle_and_resolve(
        self, forecasts: Sequence[ForecastRecord], *, observation_epoch: float,
        observation_midpoint: float,
    ) -> None: ...

    def counts(self) -> tuple[int, int]: ...

    def phase_e_cohorts(
        self, as_of_epoch: float,
    ) -> tuple[PhaseECohortMetrics, ...]: ...


class PostgresEvidenceStore:
    """psycopg v3 implementation; each observed cycle commits atomically."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        import psycopg

        self._database_url = database_url
        self._connect = psycopg.connect

    def record_cycle_and_resolve(
        self, forecasts: Sequence[ForecastRecord], *, observation_epoch: float,
        observation_midpoint: float,
    ) -> None:
        with self._connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                # Quotes arrive strictly in event-time order, so this is the first
                # eligible observation seen by this single-process resolver.
                cursor.execute(
                    """
                    INSERT INTO forecast_outcomes
                        (forecast_id, maturity_midpoint, outcome_bps, resolved_epoch)
                    SELECT f.forecast_id, %s,
                           10000 * ln(%s / f.cutoff_midpoint), %s
                    FROM forecasts AS f
                    LEFT JOIN forecast_outcomes AS o USING (forecast_id)
                    WHERE o.forecast_id IS NULL AND f.maturity_epoch <= %s
                    ON CONFLICT (forecast_id) DO NOTHING
                    """,
                    (observation_midpoint, observation_midpoint,
                     observation_epoch, observation_epoch),
                )
                cursor.executemany(
                    """
                    INSERT INTO forecasts
                        (quant_id, formula_version, cycle_id, symbol, horizon,
                         cutoff_epoch, maturity_epoch, cutoff_midpoint,
                         forecast_bps, created_epoch)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT
                        (quant_id, formula_version, cycle_id, symbol, horizon)
                    DO NOTHING
                    """,
                    [(
                        row.quant_id, row.formula_version, row.cycle_id,
                        row.symbol, row.horizon, row.cutoff_epoch,
                        row.maturity_epoch, row.cutoff_midpoint,
                        row.forecast_bps, row.created_epoch,
                    ) for row in forecasts],
                )

    def counts(self) -> tuple[int, int]:
        with self._connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT (SELECT count(*) FROM forecasts), "
                    "(SELECT count(*) FROM forecast_outcomes)"
                )
                forecasts, resolved = cursor.fetchone()
        return int(forecasts), int(resolved)

    def phase_e_cohorts(
        self, as_of_epoch: float,
    ) -> tuple[PhaseECohortMetrics, ...]:
        """Read E1 measurements at an explicit, deterministic evaluation time."""

        if not math.isfinite(as_of_epoch):
            raise ValueError("as_of_epoch must be finite")
        with self._connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT f.quant_id, f.formula_version, f.symbol, f.horizon,
                           count(*) AS forecast_count,
                           count(*) FILTER (
                               WHERE f.maturity_epoch <= %s
                           ) AS matured_count,
                           count(o.forecast_id) FILTER (
                               WHERE f.maturity_epoch <= %s
                           ) AS resolved_count,
                           count(o.forecast_id) FILTER (
                               WHERE f.maturity_epoch <= %s
                           )::double precision /
                               NULLIF(count(*) FILTER (
                                   WHERE f.maturity_epoch <= %s
                               ), 0) AS coverage,
                           sqrt(avg(power(f.forecast_bps - o.outcome_bps, 2))
                               FILTER (WHERE f.maturity_epoch <= %s
                                      AND o.forecast_id IS NOT NULL)) AS rmse_bps
                    FROM forecasts AS f
                    LEFT JOIN forecast_outcomes AS o USING (forecast_id)
                    GROUP BY f.quant_id, f.formula_version, f.symbol, f.horizon
                    ORDER BY f.quant_id, f.formula_version, f.symbol,
                             CASE f.horizon
                                 WHEN '30S' THEN 1 WHEN '1M' THEN 2
                                 WHEN '5M' THEN 3 WHEN '15M' THEN 4
                                 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                             END
                    """,
                    (as_of_epoch,) * 5,
                )
                rows = cursor.fetchall()
        return tuple(PhaseECohortMetrics(
            quant_id=str(row[0]), formula_version=str(row[1]),
            symbol=str(row[2]), horizon=str(row[3]),
            forecast_count=int(row[4]), matured_count=int(row[5]),
            resolved_count=int(row[6]),
            coverage=None if row[7] is None else float(row[7]),
            rmse_bps=None if row[8] is None else float(row[8]),
        ) for row in rows)


def records_for_results(*, results: Sequence[object], cycle_id: str,
                        symbol: str, cutoff_epoch: float,
                        cutoff_midpoint: float,
                        created_epoch: float) -> tuple[ForecastRecord, ...]:
    """Map directional exact-six results to records; nulls are omitted."""

    records = []
    for result in results:
        if result is None:
            continue
        values = result.forecast_bps
        for horizon, seconds, value in zip(HORIZONS, HORIZON_SECONDS, values):
            if value is None:
                continue
            maturity = cutoff_epoch + seconds
            if created_epoch > maturity:
                continue
            if not math.isfinite(value):
                continue
            records.append(ForecastRecord(
                result.quant_id, result.formula_version, cycle_id, symbol,
                horizon, cutoff_epoch, maturity, cutoff_midpoint, float(value),
                created_epoch,
            ))
    return tuple(records)


__all__ = [
    "EvidenceStore", "ForecastRecord", "PhaseECohortMetrics",
    "PostgresEvidenceStore", "records_for_results",
]
