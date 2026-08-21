"""Append-only PostgreSQL evidence for live directional forecasts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, Sequence


HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
MIN_EFFECTIVE_N = 20
DATA_SCHEMA_VERSION = "atom-market-input-v1"
SOURCE_SPEC_VERSION = "alpaca-market-data-v1"


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
    data_schema_version: str = DATA_SCHEMA_VERSION
    source_spec_version: str = SOURCE_SPEC_VERSION


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
    directional_accuracy: float | None
    mae_bps: float | None
    bias_bps: float | None
    effective_n: int
    eligible: bool


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
                    SELECT COALESCE(
                        max(resolved_epoch), '-Infinity'::double precision
                    )
                    FROM forecast_outcomes
                    """,
                    (),
                )
                resolution_watermark = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO forecast_outcomes
                        (forecast_id, maturity_midpoint, outcome_bps, resolved_epoch)
                    SELECT f.forecast_id, %s,
                           10000 * ln(%s / f.cutoff_midpoint), %s
                    FROM forecasts AS f
                    LEFT JOIN forecast_outcomes AS o USING (forecast_id)
                    WHERE o.forecast_id IS NULL
                      AND f.maturity_epoch > %s
                      AND f.maturity_epoch <= %s
                    ON CONFLICT (forecast_id) DO NOTHING
                    """,
                    (observation_midpoint, observation_midpoint,
                     observation_epoch, resolution_watermark,
                     observation_epoch),
                )
                cursor.executemany(
                    """
                    INSERT INTO forecasts
                        (quant_id, formula_version, cycle_id, symbol, horizon,
                         cutoff_epoch, maturity_epoch, cutoff_midpoint,
                         forecast_bps, created_epoch, data_schema_version,
                         source_spec_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT
                        (quant_id, formula_version, cycle_id, symbol, horizon)
                    DO NOTHING
                    """,
                    [(
                        row.quant_id, row.formula_version, row.cycle_id,
                        row.symbol, row.horizon, row.cutoff_epoch,
                        row.maturity_epoch, row.cutoff_midpoint,
                        row.forecast_bps, row.created_epoch,
                        row.data_schema_version, row.source_spec_version,
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
                                 AND o.resolved_epoch <= %s
                           ) AS resolved_count,
                           count(o.forecast_id) FILTER (
                               WHERE f.maturity_epoch <= %s
                                 AND o.resolved_epoch <= %s
                           )::double precision /
                               NULLIF(count(*) FILTER (
                                   WHERE f.maturity_epoch <= %s
                               ), 0) AS coverage,
                           sqrt(avg(power(f.forecast_bps - o.outcome_bps, 2))
                               FILTER (WHERE f.maturity_epoch <= %s
                                      AND o.forecast_id IS NOT NULL
                                      AND o.resolved_epoch <= %s)) AS rmse_bps,
                           avg(CASE
                                   WHEN f.forecast_bps <> 0
                                    AND o.outcome_bps <> 0
                                   THEN CASE
                                       WHEN (f.forecast_bps > 0 AND o.outcome_bps > 0)
                                         OR (f.forecast_bps < 0 AND o.outcome_bps < 0)
                                       THEN 1.0 ELSE 0.0
                                   END
                               END) FILTER (WHERE f.maturity_epoch <= %s
                                           AND o.forecast_id IS NOT NULL
                                           AND o.resolved_epoch <= %s)
                               AS directional_accuracy,
                           avg(abs(f.forecast_bps - o.outcome_bps))
                               FILTER (WHERE f.maturity_epoch <= %s
                                      AND o.forecast_id IS NOT NULL
                                      AND o.resolved_epoch <= %s) AS mae_bps,
                           avg(f.forecast_bps - o.outcome_bps)
                               FILTER (WHERE f.maturity_epoch <= %s
                                      AND o.forecast_id IS NOT NULL
                                      AND o.resolved_epoch <= %s) AS bias_bps
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
                    (as_of_epoch,) * 14,
                )
                rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT f.quant_id, f.formula_version, f.symbol, f.horizon,
                           f.cutoff_epoch, f.forecast_id
                    FROM forecasts AS f
                    JOIN forecast_outcomes AS o USING (forecast_id)
                    WHERE f.maturity_epoch <= %s
                      AND o.forecast_id IS NOT NULL
                      AND o.resolved_epoch <= %s
                    ORDER BY f.quant_id, f.formula_version, f.symbol,
                             CASE f.horizon
                                 WHEN '30S' THEN 1 WHEN '1M' THEN 2
                                 WHEN '5M' THEN 3 WHEN '15M' THEN 4
                                 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                             END,
                             f.cutoff_epoch, f.forecast_id
                    """,
                    (as_of_epoch, as_of_epoch),
                )
                effective_rows = cursor.fetchall()

        horizon_seconds = dict(zip(HORIZONS, HORIZON_SECONDS))
        effective_counts: dict[tuple[str, str, str, str], int] = {}
        next_cutoff: dict[tuple[str, str, str, str], float] = {}
        for quant_id, formula_version, symbol, horizon, cutoff_epoch, _ in effective_rows:
            cohort = (str(quant_id), str(formula_version), str(symbol), str(horizon))
            cutoff = float(cutoff_epoch)
            if cohort not in next_cutoff or cutoff >= next_cutoff[cohort]:
                effective_counts[cohort] = effective_counts.get(cohort, 0) + 1
                next_cutoff[cohort] = cutoff + horizon_seconds[cohort[3]]

        return tuple(PhaseECohortMetrics(
            quant_id=str(row[0]), formula_version=str(row[1]),
            symbol=str(row[2]), horizon=str(row[3]),
            forecast_count=int(row[4]), matured_count=int(row[5]),
            resolved_count=int(row[6]),
            coverage=None if row[7] is None else float(row[7]),
            rmse_bps=None if row[8] is None else float(row[8]),
            directional_accuracy=None if row[9] is None else float(row[9]),
            mae_bps=None if row[10] is None else float(row[10]),
            bias_bps=None if row[11] is None else float(row[11]),
            effective_n=effective_counts.get(
                (str(row[0]), str(row[1]), str(row[2]), str(row[3])), 0,
            ),
            eligible=effective_counts.get(
                (str(row[0]), str(row[1]), str(row[2]), str(row[3])), 0,
            ) >= MIN_EFFECTIVE_N,
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
    "DATA_SCHEMA_VERSION", "EvidenceStore", "ForecastRecord", "MIN_EFFECTIVE_N",
    "PhaseECohortMetrics", "PostgresEvidenceStore", "SOURCE_SPEC_VERSION",
    "records_for_results",
]
