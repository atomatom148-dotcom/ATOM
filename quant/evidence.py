"""Append-only PostgreSQL evidence for live directional and volatility forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
import json
import math
from typing import Protocol, Sequence


HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
HORIZON_SECONDS_BY_NAME = dict(zip(HORIZONS, HORIZON_SECONDS))
MIN_EFFECTIVE_N = 20
PHASE_E_COHORT_WINDOW_LIMIT = 256
DATA_SCHEMA_VERSION = "atom-market-input-v1"
SOURCE_SPEC_VERSION = "alpaca-market-data-v1"


def _canonical_phase_e_cohort_specs(*, volatility: bool) -> str:
    """Return the bounded canonical cohorts displayed by the live dashboard."""

    # Imported lazily because v9_production imports this evidence module.
    from .v9_production import FORMULA_VERSION_MAP

    quant_ids = (
        ("q3_volatility",) if volatility else
        tuple(quant_id for quant_id in FORMULA_VERSION_MAP
              if quant_id != "q3_volatility")
    )
    return json.dumps([
        {
            "quant_id": quant_id,
            "formula_version": FORMULA_VERSION_MAP[quant_id],
            "symbol": "COIN",
            "horizon": horizon,
        }
        for quant_id in quant_ids
        for horizon in HORIZONS
    ], sort_keys=True, separators=(",", ":"))


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
    source_as_of_epoch: float | None = None


@dataclass(frozen=True, slots=True)
class VolatilityForecastRecord:
    quant_id: str
    formula_version: str
    cycle_id: str
    symbol: str
    horizon: str
    cutoff_epoch: float
    maturity_epoch: float
    cutoff_midpoint: float
    forecast_volatility_bps: float
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
    evidence_window: str = "MOST_RECENT_PER_COHORT"
    evidence_window_limit: int = PHASE_E_COHORT_WINDOW_LIMIT
    evidence_window_truncated: bool = False


@dataclass(frozen=True, slots=True)
class HistoricalReplaySummary:
    """Bounded manifest-only totals for certified historical replay evidence."""

    certified_sessions: int
    cutoff_count: int
    available_slot_count: int
    unavailable_slot_count: int
    latest_session: str | None
    family_count: int = 12
    horizon_count: int = 6
    slots_per_cutoff: int = 72


class EvidenceStore(Protocol):
    """The deliberately small API has no mutation or deletion operations."""

    def record_cycle_and_resolve(
        self, forecasts: Sequence[ForecastRecord], *, observation_epoch: float,
        observation_midpoint: float, resolution_symbol: str,
        volatility_forecasts: Sequence[VolatilityForecastRecord] | None = None,
        previous_observation_epoch: float | None = None,
        resolution_enabled: bool = True,
    ) -> None: ...

    def counts(self) -> tuple[int, int]: ...

    def historical_replay_summary(self) -> HistoricalReplaySummary: ...

    def phase_e_cohorts(
        self, as_of_epoch: float,
    ) -> tuple[PhaseECohortMetrics, ...]: ...

    def volatility_phase_e_cohorts(
        self, as_of_epoch: float,
    ) -> tuple[PhaseECohortMetrics, ...]: ...


class PostgresEvidenceStore:
    """psycopg v3 implementation; each observed cycle commits atomically."""

    def __init__(self, database_url: str, *, connection=None,
                 family_cadence_enabled: bool = False) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        import psycopg

        self._database_url = database_url
        self._connect = psycopg.connect
        self._connection = connection
        self._family_cadence_enabled = family_cadence_enabled

    @staticmethod
    def _cadence_interval(horizon: str, cutoff_epoch: float) -> tuple[float, float]:
        """Return the deterministic UTC epoch-aligned interval for one horizon."""

        seconds = HORIZON_SECONDS_BY_NAME[horizon]
        start = math.floor(cutoff_epoch / seconds) * seconds
        return float(start), float(start + seconds)

    def _cadence_parameters(self, row, values: tuple) -> tuple:
        return (
            *values, not getattr(self, "_family_cadence_enabled", False),
            row.quant_id, row.formula_version, row.symbol, row.horizon,
            *self._cadence_interval(row.horizon, row.cutoff_epoch),
        )

    def rebind_connection(self, connection) -> None:
        """Move shared-connection operation to a recovered DB session."""

        self._connection = connection

    def _record_publication_proofs(
        self, forecasts: Sequence[ForecastRecord], *,
        observation_epoch: float, resolution_symbol: str,
        volatility_forecasts: Sequence[VolatilityForecastRecord],
        resolution_enabled: bool,
    ) -> None:
        """Observe committed legacy rows in a separate database transaction.

        Missing proof infrastructure never makes legacy evidence admissible:
        the V2 and Phase-E readers join only authoritative proof rows.
        """
        cycle_ids = tuple(sorted({
            row.cycle_id for row in (*tuple(forecasts), *tuple(volatility_forecasts))
        }))
        try:
            with self._connect(self._database_url) as connection:
                with connection.cursor() as cursor:
                    if cycle_ids:
                        cursor.execute(
                            """
                            SELECT atom_v9_internal.record_legacy_evidence_publication(
                                'DIRECTIONAL_FORECAST', f.forecast_id)
                            FROM public.forecasts AS f
                            WHERE f.cycle_id = ANY(%s)
                            """,
                            (list(cycle_ids),),
                        )
                        cursor.execute(
                            """
                            SELECT atom_v9_internal.record_legacy_evidence_publication(
                                'VOLATILITY_FORECAST', f.forecast_id)
                            FROM public.volatility_forecasts AS f
                            WHERE f.cycle_id = ANY(%s)
                            """,
                            (list(cycle_ids),),
                        )
                    if resolution_enabled:
                        cursor.execute(
                            """
                            SELECT atom_v9_internal.record_legacy_evidence_publication(
                                'DIRECTIONAL_OUTCOME', o.forecast_id)
                            FROM public.forecast_outcomes AS o
                            JOIN public.forecasts AS f USING (forecast_id)
                            WHERE o.resolved_epoch=%s AND f.symbol=%s
                            """,
                            (observation_epoch, resolution_symbol),
                        )
                        cursor.execute(
                            """
                            SELECT atom_v9_internal.record_legacy_evidence_publication(
                                'VOLATILITY_OUTCOME', o.forecast_id)
                            FROM public.volatility_forecast_outcomes AS o
                            JOIN public.volatility_forecasts AS f USING (forecast_id)
                            WHERE o.resolved_epoch=%s AND f.symbol=%s
                            """,
                            (observation_epoch, resolution_symbol),
                        )
        except Exception as error:
            # A deliberately unapplied protected migration leaves these objects
            # absent; readers then fail closed because no proof can exist.
            if getattr(error, "sqlstate", None) in {
                "3F000",  # invalid_schema_name
                "42P01",  # undefined_table
                "42883",  # undefined_function
            }:
                return
            # Transient database failures must reach the worker retry loop so a
            # committed ledger row is not permanently left without its proof.
            raise

    def record_cycle_and_resolve(
        self, forecasts: Sequence[ForecastRecord], *, observation_epoch: float,
        observation_midpoint: float, resolution_symbol: str,
        volatility_forecasts: Sequence[VolatilityForecastRecord] | None = None,
        previous_observation_epoch: float | None = None,
        resolution_enabled: bool = True,
    ) -> None:
        if not isinstance(resolution_symbol, str) or not resolution_symbol:
            raise ValueError("resolution_symbol must be a non-empty string")
        volatility_rows = (() if volatility_forecasts is None
                           else tuple(volatility_forecasts))
        supplied_symbols = {
            row.symbol for row in (*tuple(forecasts), *volatility_rows)
        }
        if supplied_symbols and supplied_symbols != {resolution_symbol}:
            raise ValueError(
                "every forecast must match the explicit resolution_symbol")
        shared_connection = getattr(self, "_connection", None)
        owner = (self._connect(self._database_url) if shared_connection is None
                 else nullcontext(shared_connection))
        try:
            with owner as connection:
                with connection.cursor() as cursor:
                    # Quotes arrive strictly in event-time order, so this is the
                    # first eligible observation seen by this process resolver.
                    if resolution_enabled:
                        if previous_observation_epoch is None:
                            cursor.execute(
                                """SELECT COALESCE(max(o.resolved_epoch),
                                                   '-Infinity'::double precision)
                                   FROM forecast_outcomes AS o
                                   JOIN forecasts AS f USING (forecast_id)
                                   WHERE f.symbol=%s""", (resolution_symbol,))
                            resolution_watermark = cursor.fetchone()[0]
                        else:
                            resolution_watermark = previous_observation_epoch
                        cursor.execute(
                            """
                            INSERT INTO forecast_outcomes
                                (forecast_id, maturity_midpoint, outcome_bps,
                                 resolved_epoch)
                            SELECT f.forecast_id, %s,
                                   10000 * ln(%s / f.cutoff_midpoint), %s
                            FROM forecasts AS f
                            LEFT JOIN forecast_outcomes AS o USING (forecast_id)
                            WHERE o.forecast_id IS NULL
                              AND f.symbol = %s
                              AND f.maturity_epoch > %s
                              AND f.maturity_epoch <= %s
                            ON CONFLICT (forecast_id) DO NOTHING
                            """,
                            (observation_midpoint, observation_midpoint,
                             observation_epoch, resolution_symbol,
                             resolution_watermark,
                             observation_epoch),
                        )
                    cursor.executemany(
                        """
                        INSERT INTO forecasts
                            (quant_id, formula_version, cycle_id, symbol, horizon,
                             cutoff_epoch, maturity_epoch, cutoff_midpoint,
                             forecast_bps, created_epoch, data_schema_version,
                             source_spec_version, source_as_of_epoch)
                        SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        WHERE %s OR NOT EXISTS (
                            SELECT 1 FROM forecasts AS existing
                            WHERE existing.quant_id=%s
                              AND existing.formula_version=%s
                              AND existing.symbol=%s
                              AND existing.horizon=%s
                              AND existing.cutoff_epoch >= %s
                              AND existing.cutoff_epoch < %s
                        )
                        ON CONFLICT
                            (quant_id, formula_version, cycle_id, symbol, horizon)
                        DO NOTHING
                        """,
                        [self._cadence_parameters(row, (
                            row.quant_id, row.formula_version, row.cycle_id,
                            row.symbol, row.horizon, row.cutoff_epoch,
                            row.maturity_epoch, row.cutoff_midpoint,
                            row.forecast_bps, row.created_epoch,
                            row.data_schema_version, row.source_spec_version,
                            row.source_as_of_epoch,
                        )) for row in forecasts],
                    )
                    if volatility_forecasts is not None:
                        if resolution_enabled:
                            if previous_observation_epoch is None:
                                cursor.execute(
                                    """SELECT COALESCE(max(o.resolved_epoch),
                                                       '-Infinity'::double precision)
                                       FROM volatility_forecast_outcomes AS o
                                       JOIN volatility_forecasts AS f
                                         USING (forecast_id)
                                       WHERE f.symbol=%s""", (resolution_symbol,))
                                volatility_resolution_watermark = cursor.fetchone()[0]
                            else:
                                volatility_resolution_watermark = previous_observation_epoch
                            cursor.execute(
                                """
                                INSERT INTO volatility_forecast_outcomes
                                    (forecast_id, maturity_midpoint,
                                     realized_move_bps, resolved_epoch)
                                SELECT f.forecast_id, %s,
                                       abs(10000 * ln(%s / f.cutoff_midpoint)), %s
                                FROM volatility_forecasts AS f
                                LEFT JOIN volatility_forecast_outcomes AS o
                                    USING (forecast_id)
                                WHERE o.forecast_id IS NULL
                                  AND f.symbol = %s
                                  AND f.maturity_epoch > %s
                                  AND f.maturity_epoch <= %s
                                ON CONFLICT (forecast_id) DO NOTHING
                                """,
                                (observation_midpoint, observation_midpoint,
                                 observation_epoch, resolution_symbol,
                                 volatility_resolution_watermark,
                                 observation_epoch),
                            )
                        cursor.executemany(
                            """
                            INSERT INTO volatility_forecasts
                                (quant_id, formula_version, cycle_id, symbol,
                                 horizon, cutoff_epoch, maturity_epoch,
                                 cutoff_midpoint, forecast_volatility_bps,
                                 created_epoch, data_schema_version,
                                 source_spec_version)
                            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            WHERE %s OR NOT EXISTS (
                                SELECT 1 FROM volatility_forecasts AS existing
                                WHERE existing.quant_id=%s
                                  AND existing.formula_version=%s
                                  AND existing.symbol=%s
                                  AND existing.horizon=%s
                                  AND existing.cutoff_epoch >= %s
                                  AND existing.cutoff_epoch < %s
                            )
                            ON CONFLICT
                                (quant_id, formula_version, cycle_id, symbol,
                                 horizon)
                            DO NOTHING
                            """,
                            [self._cadence_parameters(row, (
                                row.quant_id, row.formula_version, row.cycle_id,
                                row.symbol, row.horizon, row.cutoff_epoch,
                                row.maturity_epoch, row.cutoff_midpoint,
                                row.forecast_volatility_bps, row.created_epoch,
                                row.data_schema_version, row.source_spec_version,
                            )) for row in volatility_rows],
                        )
                if shared_connection is not None:
                    connection.commit()
        except Exception:
            if shared_connection is not None:
                rollback = getattr(shared_connection, "rollback", None)
                if callable(rollback):
                    try:
                        rollback()
                    except Exception:
                        pass
            raise

        self._record_publication_proofs(
            forecasts, observation_epoch=observation_epoch,
            resolution_symbol=resolution_symbol,
            volatility_forecasts=volatility_rows,
            resolution_enabled=resolution_enabled,
        )

    def counts(self) -> tuple[int, int]:
        with self._connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT (SELECT count(*) FROM forecasts) + "
                    "(SELECT count(*) FROM volatility_forecasts), "
                    "(SELECT count(*) FROM forecast_outcomes) + "
                    "(SELECT count(*) FROM volatility_forecast_outcomes)"
                )
                forecasts, resolved = cursor.fetchone()
        return int(forecasts), int(resolved)

    def historical_replay_summary(self) -> HistoricalReplaySummary:
        """Read only the certified run manifests; never scan replay forecasts."""

        with self._connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH latest_certified_sessions AS (
                        SELECT DISTINCT ON (historical_session)
                               historical_session,
                               frame_count,
                               available_observation_count,
                               unavailable_observation_count
                        FROM public.atom_historical_replay_runs
                        WHERE execution_stage = 'REPLAY_COMPLETE'
                          AND certification_status = 'CERTIFIED'
                        ORDER BY historical_session, created_at DESC,
                                 replay_run_id DESC
                    )
                    SELECT count(*), COALESCE(sum(frame_count), 0),
                           COALESCE(sum(available_observation_count), 0),
                           COALESCE(sum(unavailable_observation_count), 0),
                           max(historical_session)::text
                    FROM latest_certified_sessions
                    """,
                    (),
                )
                sessions, cutoffs, available, unavailable, latest = cursor.fetchone()
        return HistoricalReplaySummary(
            int(sessions), int(cutoffs), int(available), int(unavailable), latest,
        )

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
                    WITH forecast_proofs AS MATERIALIZED (
                        SELECT *
                        FROM atom_v9_internal.read_legacy_evidence_publications_for_cohorts(
                            'DIRECTIONAL_FORECAST', to_timestamp(%s), %s::jsonb,
                            256
                        )
                    ),
                    outcome_proofs AS MATERIALIZED (
                        SELECT *
                        FROM atom_v9_internal.read_legacy_evidence_publications_for_records(
                            'DIRECTIONAL_OUTCOME', to_timestamp(%s),
                            ARRAY(
                                SELECT ids.record_id
                                FROM forecast_proofs AS ids
                            )
                        )
                    )
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
                                      AND o.resolved_epoch <= %s) AS bias_bps,
                           bool_or(fp.window_truncated)
                               AS evidence_window_truncated
                    FROM forecast_proofs AS fp
                    JOIN forecasts AS f ON f.forecast_id=fp.record_id
                    LEFT JOIN outcome_proofs AS op
                      ON op.record_id=f.forecast_id
                    LEFT JOIN forecast_outcomes AS o
                      ON o.forecast_id=op.record_id
                     AND o.resolved_epoch >= f.maturity_epoch
                     AND o.resolved_epoch <= f.maturity_epoch + 5.0
                    WHERE fp.commit_observed_at < to_timestamp(f.maturity_epoch)
                    GROUP BY f.quant_id, f.formula_version, f.symbol, f.horizon
                    ORDER BY f.quant_id, f.formula_version, f.symbol,
                             CASE f.horizon
                                 WHEN '30S' THEN 1 WHEN '1M' THEN 2
                                 WHEN '5M' THEN 3 WHEN '15M' THEN 4
                                 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                             END
                    """,
                    (
                        as_of_epoch,
                        _canonical_phase_e_cohort_specs(volatility=False),
                        *((as_of_epoch,) * 15),
                    ),
                )
                rows = cursor.fetchall()
                cohort_specs = json.dumps([
                    {
                        "quant_id": str(row[0]),
                        "formula_version": str(row[1]),
                        "symbol": str(row[2]),
                        "horizon": str(row[3]),
                    }
                    for row in rows
                ], sort_keys=True, separators=(",", ":"))
                cursor.execute(
                    """
                    SELECT f.quant_id, f.formula_version, f.symbol, f.horizon,
                           f.cutoff_epoch, f.forecast_id
                    FROM atom_v9_internal.read_legacy_effective_observations(
                        'DIRECTIONAL_FORECAST', to_timestamp(%s), %s::jsonb, 64
                    ) AS f
                    ORDER BY f.quant_id, f.formula_version, f.symbol,
                             CASE f.horizon
                                 WHEN '30S' THEN 1 WHEN '1M' THEN 2
                                 WHEN '5M' THEN 3 WHEN '15M' THEN 4
                                 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                             END,
                             f.cutoff_epoch, f.forecast_id
                    """,
                    (as_of_epoch, cohort_specs),
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
            evidence_window_truncated=(
                len(row) > 12 and bool(row[12])
            ),
        ) for row in rows)

    def volatility_phase_e_cohorts(
        self, as_of_epoch: float,
    ) -> tuple[PhaseECohortMetrics, ...]:
        """Read non-directional Q3 calibration at an explicit evaluation time."""

        if not math.isfinite(as_of_epoch):
            raise ValueError("as_of_epoch must be finite")
        with self._connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH forecast_proofs AS MATERIALIZED (
                        SELECT *
                        FROM atom_v9_internal.read_legacy_evidence_publications_for_cohorts(
                            'VOLATILITY_FORECAST', to_timestamp(%s), %s::jsonb,
                            256
                        )
                    ),
                    outcome_proofs AS MATERIALIZED (
                        SELECT *
                        FROM atom_v9_internal.read_legacy_evidence_publications_for_records(
                            'VOLATILITY_OUTCOME', to_timestamp(%s),
                            ARRAY(
                                SELECT ids.record_id
                                FROM forecast_proofs AS ids
                            )
                        )
                    )
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
                           sqrt(avg(power(
                               f.forecast_volatility_bps - o.realized_move_bps, 2
                           )) FILTER (WHERE f.maturity_epoch <= %s
                                      AND o.forecast_id IS NOT NULL
                                      AND o.resolved_epoch <= %s)) AS rmse_bps,
                           NULL::double precision AS directional_accuracy,
                           avg(abs(
                               f.forecast_volatility_bps - o.realized_move_bps
                           )) FILTER (WHERE f.maturity_epoch <= %s
                                      AND o.forecast_id IS NOT NULL
                                      AND o.resolved_epoch <= %s) AS mae_bps,
                           avg(
                               f.forecast_volatility_bps - o.realized_move_bps
                           ) FILTER (WHERE f.maturity_epoch <= %s
                                      AND o.forecast_id IS NOT NULL
                                      AND o.resolved_epoch <= %s) AS bias_bps,
                           bool_or(fp.window_truncated)
                               AS evidence_window_truncated
                    FROM forecast_proofs AS fp
                    JOIN volatility_forecasts AS f
                      ON f.forecast_id=fp.record_id
                    LEFT JOIN outcome_proofs AS op
                      ON op.record_id=f.forecast_id
                    LEFT JOIN volatility_forecast_outcomes AS o
                      ON o.forecast_id=op.record_id
                     AND o.resolved_epoch >= f.maturity_epoch
                     AND o.resolved_epoch <= f.maturity_epoch + 5.0
                    WHERE fp.commit_observed_at < to_timestamp(f.maturity_epoch)
                    GROUP BY f.quant_id, f.formula_version, f.symbol, f.horizon
                    ORDER BY f.quant_id, f.formula_version, f.symbol,
                             CASE f.horizon
                                 WHEN '30S' THEN 1 WHEN '1M' THEN 2
                                 WHEN '5M' THEN 3 WHEN '15M' THEN 4
                                 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                             END
                    """,
                    (
                        as_of_epoch,
                        _canonical_phase_e_cohort_specs(volatility=True),
                        *((as_of_epoch,) * 13),
                    ),
                )
                rows = cursor.fetchall()
                cohort_specs = json.dumps([
                    {
                        "quant_id": str(row[0]),
                        "formula_version": str(row[1]),
                        "symbol": str(row[2]),
                        "horizon": str(row[3]),
                    }
                    for row in rows
                ], sort_keys=True, separators=(",", ":"))
                cursor.execute(
                    """
                    SELECT f.quant_id, f.formula_version, f.symbol, f.horizon,
                           f.cutoff_epoch, f.forecast_id
                    FROM atom_v9_internal.read_legacy_effective_observations(
                        'VOLATILITY_FORECAST', to_timestamp(%s), %s::jsonb, 64
                    ) AS f
                    ORDER BY f.quant_id, f.formula_version, f.symbol,
                             CASE f.horizon
                                 WHEN '30S' THEN 1 WHEN '1M' THEN 2
                                 WHEN '5M' THEN 3 WHEN '15M' THEN 4
                                 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                             END,
                             f.cutoff_epoch, f.forecast_id
                    """,
                    (as_of_epoch, cohort_specs),
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
            directional_accuracy=None,
            mae_bps=None if row[10] is None else float(row[10]),
            bias_bps=None if row[11] is None else float(row[11]),
            effective_n=effective_counts.get(
                (str(row[0]), str(row[1]), str(row[2]), str(row[3])), 0,
            ),
            eligible=effective_counts.get(
                (str(row[0]), str(row[1]), str(row[2]), str(row[3])), 0,
            ) >= MIN_EFFECTIVE_N,
            evidence_window_truncated=(
                len(row) > 12 and bool(row[12])
            ),
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
        source_as_of_epoch = getattr(result, "source_as_of_epoch", None)
        provider_timed = result.quant_id in {
            "q4_stat_arb", "q10_options_vol",
        }
        if source_as_of_epoch is None:
            if provider_timed:
                continue
            source_as_of_epoch = cutoff_epoch
        if (isinstance(source_as_of_epoch, bool) or
                not isinstance(source_as_of_epoch, (int, float)) or
                not math.isfinite(source_as_of_epoch) or
                source_as_of_epoch > cutoff_epoch):
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
                created_epoch, source_as_of_epoch=float(source_as_of_epoch),
            ))
    return tuple(records)


def records_for_volatility(*, result: object | None, cycle_id: str,
                           symbol: str, cutoff_epoch: float,
                           cutoff_midpoint: float,
                           created_epoch: float) -> tuple[VolatilityForecastRecord, ...]:
    """Map Q3's non-directional exact-six result to volatility records."""

    if result is None:
        return ()
    records = []
    for horizon, seconds, value in zip(
            HORIZONS, HORIZON_SECONDS, result.volatility_bps):
        if value is None:
            continue
        maturity = cutoff_epoch + seconds
        if created_epoch > maturity or not math.isfinite(value) or value < 0:
            continue
        records.append(VolatilityForecastRecord(
            result.quant_id, result.formula_version, cycle_id, symbol,
            horizon, cutoff_epoch, maturity, cutoff_midpoint, float(value),
            created_epoch,
        ))
    return tuple(records)


__all__ = [
    "DATA_SCHEMA_VERSION", "EvidenceStore", "ForecastRecord",
    "HistoricalReplaySummary", "MIN_EFFECTIVE_N", "PhaseECohortMetrics",
    "PostgresEvidenceStore", "SOURCE_SPEC_VERSION",
    "VolatilityForecastRecord", "records_for_results", "records_for_volatility",
]
