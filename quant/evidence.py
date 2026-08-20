"""Append-only PostgreSQL evidence for live Q1/Q2 forecasts."""

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


class EvidenceStore(Protocol):
    """The deliberately small API has no mutation or deletion operations."""

    def record_cycle_and_resolve(
        self, forecasts: Sequence[ForecastRecord], *, observation_epoch: float,
        observation_midpoint: float,
    ) -> None: ...

    def counts(self) -> tuple[int, int]: ...


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


def records_for_results(*, results: Sequence[object], cycle_id: str,
                        symbol: str, cutoff_epoch: float,
                        cutoff_midpoint: float,
                        created_epoch: float) -> tuple[ForecastRecord, ...]:
    """Map directional exact-six results to records; nulls are omitted."""

    records = []
    for result in results:
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


__all__ = ["EvidenceStore", "ForecastRecord", "PostgresEvidenceStore", "records_for_results"]
