"""Production wiring for the frozen V1 → V2 → V3 → V4D path.

Historical evidence is read only by the explicit offline V2 refresh worker.
Live quote handling captures one immutable V2 state, performs bounded synthesis,
persists immutable V4 evidence, and publishes one complete in-memory result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import threading
import time
from typing import Callable

from .evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from .history import MidpointObservation
from .live_market import LiveSnapshot
from .q1_momentum import FORMULA_VERSION as Q1_VERSION
from .q2_mean_reversion import FORMULA_VERSION as Q2_VERSION
from .q3_volatility import FORMULA_VERSION as Q3_VERSION
from .q4_stat_arb import FORMULA_VERSION as Q4_VERSION
from .q5_microstructure import FORMULA_VERSION as Q5_VERSION
from .q6_volume_liquidity import FORMULA_VERSION as Q6_VERSION
from .q7_relative_value import FORMULA_VERSION as Q7_VERSION
from .q8_cross_asset import FORMULA_VERSION as Q8_VERSION
from .q9_factor import FORMULA_VERSION as Q9_VERSION
from .q10_options_vol import FORMULA_VERSION as Q10_VERSION
from .q11_regime import FORMULA_VERSION as Q11_VERSION
from .q12_event_session import FORMULA_VERSION as Q12_VERSION
from .v9_v1_contract import (
    DIRECTIONAL_BPS, HORIZONS, HORIZON_SECONDS, MAGNITUDE_BPS, QUANT_IDS,
    V1Input, V1SlotObservation, build_v1_input,
)
from .v9_v2a_dataset import (
    RawFamilyObservation, RawTarget, TargetIdentity, build_v2a_dataset,
)
from .v9_v2b_calibration import build_v2b_calibration
from .v9_v2c_covariance import build_v2c_covariance
from .v9_v2d_evidence_state import V2EvidenceState, build_v2d_evidence_state
from .v9_v4a_evidence import (
    V4AWriter, build_cohort, canonical_sha256, canonical_target_identity,
    deserialize_forecast_record,
)
from .v9_v4b_accuracy import AccuracyStateStore
from .v9_v4c_predictive import V4CStateStore
from .v9_v4d_integration import V4DCycleOutput, V4DCoordinator
from .v9_v4d_integration import ImmutableStateCache, OperationalMetrics


TARGET_SPEC_ID = "COIN_MIDPOINT_LOG_RETURN_BPS_1"
V2_REFRESH_SECONDS = 3600.0
V2_STATE_BUILD_EVIDENCE_LIMIT = 65_536

FORMULA_VERSIONS = (
    ("q1_momentum", Q1_VERSION),
    ("q2_mean_reversion", Q2_VERSION),
    ("q3_volatility", Q3_VERSION),
    ("q4_stat_arb", Q4_VERSION),
    ("q5_microstructure", Q5_VERSION),
    ("q6_volume_liquidity", Q6_VERSION),
    ("q7_relative_value", Q7_VERSION),
    ("q8_cross_asset", Q8_VERSION),
    ("q9_factor", Q9_VERSION),
    ("q10_options_vol", Q10_VERSION),
    ("q11_regime", Q11_VERSION),
    ("q12_event_session", Q12_VERSION),
)
FORMULA_VERSION_MAP = dict(FORMULA_VERSIONS)


@dataclass(frozen=True, slots=True)
class V2RefreshSnapshot:
    status: str
    state_id: str | None
    state_as_of: float | None
    error_type: str | None
    duration_ms: float | None = None
    rows_materialized: int = 0


class PostgresV2StateBuilder:
    """Canonical batch V2 builder over one repeatable-read evidence snapshot."""

    def __init__(self, database_url: str, *, connect: Callable | None = None):
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._database_url = database_url
        self._connect = connect
        self.last_rows_materialized = 0

    def build(self) -> V2EvidenceState:
        self.last_rows_materialized = 0
        connection = self._connect(self._database_url)
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY", ())
                cursor.execute(
                    "SELECT extract(epoch FROM pg_catalog.transaction_timestamp())",
                    (),
                )
                row = cursor.fetchone()
                state_as_of = None if row is None else row[0]
                if state_as_of is None or not math.isfinite(float(state_as_of)):
                    raise RuntimeError("V2_RESOLVED_EVIDENCE_UNAVAILABLE")
                state_as_of = float(state_as_of)
                cursor.execute(
                    """
                    SELECT f.forecast_id, f.quant_id, f.formula_version,
                           f.cycle_id, f.symbol, f.horizon, f.cutoff_epoch,
                           f.maturity_epoch, f.forecast_bps, f.created_epoch,
                           f.data_schema_version, f.source_spec_version,
                           f.source_as_of_epoch, o.outcome_bps, o.resolved_epoch,
                           extract(epoch FROM fp.commit_observed_at),
                           extract(epoch FROM op.commit_observed_at)
                    FROM public.forecasts AS f
                    JOIN public.forecast_outcomes AS o USING (forecast_id)
                    JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
                        'DIRECTIONAL_FORECAST', f.forecast_id
                    ) AS fp ON true
                    JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
                        'DIRECTIONAL_OUTCOME', o.forecast_id
                    ) AS op ON true
                    WHERE f.data_schema_version=%s AND f.source_spec_version=%s
                      AND fp.commit_observed_at < to_timestamp(f.maturity_epoch)
                      AND o.resolved_epoch >= f.maturity_epoch
                      AND o.resolved_epoch <= f.maturity_epoch + %s
                      AND op.commit_observed_at<=to_timestamp(%s)
                    ORDER BY f.horizon, f.cutoff_epoch, f.forecast_id
                    LIMIT %s
                    """,
                    (DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, 5.0, state_as_of,
                     V2_STATE_BUILD_EVIDENCE_LIMIT + 1),
                )
                directional_rows = tuple(cursor.fetchall())
                self.last_rows_materialized = len(directional_rows)
                if len(directional_rows) > V2_STATE_BUILD_EVIDENCE_LIMIT:
                    raise RuntimeError("V2_EVIDENCE_ROW_LIMIT_EXCEEDED")
                cursor.execute(
                    """
                    SELECT f.forecast_id, f.quant_id, f.formula_version,
                           f.cycle_id, f.symbol, f.horizon, f.cutoff_epoch,
                           f.maturity_epoch, f.forecast_volatility_bps,
                           f.created_epoch, f.data_schema_version,
                           f.source_spec_version, o.resolved_epoch,
                           extract(epoch FROM fp.commit_observed_at),
                           extract(epoch FROM op.commit_observed_at)
                    FROM public.volatility_forecasts AS f
                    JOIN public.volatility_forecast_outcomes AS o USING (forecast_id)
                    JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
                        'VOLATILITY_FORECAST', f.forecast_id
                    ) AS fp ON true
                    JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
                        'VOLATILITY_OUTCOME', o.forecast_id
                    ) AS op ON true
                    WHERE f.data_schema_version=%s AND f.source_spec_version=%s
                      AND fp.commit_observed_at < to_timestamp(f.maturity_epoch)
                      AND o.resolved_epoch >= f.maturity_epoch
                      AND o.resolved_epoch <= f.maturity_epoch + %s
                      AND op.commit_observed_at<=to_timestamp(%s)
                    ORDER BY f.horizon, f.cutoff_epoch, f.forecast_id
                    LIMIT %s
                    """,
                    (DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, 5.0, state_as_of,
                     V2_STATE_BUILD_EVIDENCE_LIMIT + 1),
                )
                magnitude_rows = tuple(cursor.fetchall())
                self.last_rows_materialized = len(directional_rows) + len(magnitude_rows)
                if len(magnitude_rows) > V2_STATE_BUILD_EVIDENCE_LIMIT:
                    raise RuntimeError("V2_EVIDENCE_ROW_LIMIT_EXCEEDED")
            finally:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

        targets_by_horizon: dict[str, list[RawTarget]] = {h: [] for h in HORIZONS}
        observations_by_horizon: dict[str, list[RawFamilyObservation]] = {
            h: [] for h in HORIZONS
        }
        target_available_by_identity: dict[TargetIdentity, float] = {}
        for row in directional_rows:
            identity = TargetIdentity(str(row[3]), float(row[6]), float(row[7]))
            available = float(row[16])
            target_available_by_identity[identity] = max(
                available, target_available_by_identity.get(identity, available),
            )

        for row in directional_rows:
            (record_id, quant_id, formula_version, cycle_id, symbol, horizon,
             cutoff, maturity, value, created, schema, source, source_as_of,
             outcome, _resolved, forecast_available, outcome_available) = row
            if (horizon not in targets_by_horizon or
                    FORMULA_VERSION_MAP.get(str(quant_id)) != str(formula_version)):
                continue
            identity = TargetIdentity(str(cycle_id), float(cutoff), float(maturity))
            targets_by_horizon[str(horizon)].append(RawTarget(
                int(record_id), str(cycle_id), str(symbol), TARGET_SPEC_ID,
                str(schema), str(source), str(horizon), float(cutoff),
                float(maturity), target_available_by_identity[identity],
                float(outcome),
            ))
            if (str(quant_id) in {"q4_stat_arb", "q10_options_vol"} and
                    source_as_of is None):
                continue
            source_epoch = float(cutoff if source_as_of is None else source_as_of)
            observations_by_horizon[str(horizon)].append(RawFamilyObservation(
                int(record_id), identity, str(symbol), str(quant_id),
                str(formula_version), str(schema), str(source), str(horizon),
                DIRECTIONAL_BPS, float(value), float(cutoff), source_epoch,
                float(forecast_available), "FRESH",
            ))
        for row in magnitude_rows:
            (record_id, quant_id, formula_version, cycle_id, symbol, horizon,
             cutoff, maturity, value, created, schema, source, _resolved,
             forecast_available, _outcome_available) = row
            if (horizon not in observations_by_horizon or
                    str(quant_id) != "q3_volatility" or
                    FORMULA_VERSION_MAP["q3_volatility"] != str(formula_version)):
                continue
            identity = TargetIdentity(str(cycle_id), float(cutoff), float(maturity))
            observations_by_horizon[str(horizon)].append(RawFamilyObservation(
                int(record_id), identity, str(symbol), str(quant_id),
                str(formula_version), str(schema), str(source), str(horizon),
                MAGNITUDE_BPS, float(value), float(cutoff), float(cutoff),
                float(forecast_available), "FRESH",
            ))

        family_versions = tuple(
            (quant_id, version, DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION)
            for quant_id, version in FORMULA_VERSIONS
        )
        datasets = tuple(build_v2a_dataset(
            state_as_of=state_as_of, horizon=horizon,
            target_spec_id=TARGET_SPEC_ID,
            target_data_schema_version=DATA_SCHEMA_VERSION,
            target_source_spec_version=SOURCE_SPEC_VERSION,
            family_versions=family_versions,
            targets=targets_by_horizon[horizon],
            observations=observations_by_horizon[horizon],
        ) for horizon in HORIZONS)
        calibration = build_v2b_calibration(datasets)
        covariances = tuple(build_v2c_covariance(dataset, calibration)
                            for dataset in datasets)
        state = build_v2d_evidence_state(
            state_as_of=state_as_of, datasets=datasets,
            calibrations=(calibration,), covariances=covariances,
        )
        if state.creation_status != "VALID" or state.top_level_status == "UNAVAILABLE":
            raise RuntimeError("V2_STATE_NOT_USABLE")
        return state


class ImmutableV2StateProvider:
    """Atomically publish complete frozen V2 states built outside request paths."""

    def __init__(self, builder: PostgresV2StateBuilder, *,
                 metrics: OperationalMetrics | None = None):
        self._builder = builder
        self._lock = threading.Lock()
        self._state: V2EvidenceState | None = None
        self._status = V2RefreshSnapshot("UNAVAILABLE", None, None, None)
        self.metrics = metrics or OperationalMetrics()

    def refresh(self) -> V2RefreshSnapshot:
        started = time.perf_counter()
        try:
            candidate = self._builder.build()
        except Exception as error:
            duration = (time.perf_counter() - started) * 1000
            snapshot = V2RefreshSnapshot("UNAVAILABLE", None, None,
                                         type(error).__name__, duration,
                                         self._builder.last_rows_materialized)
            self.metrics.observe("v2_background_build_duration_ms", duration)
            self.metrics.observe("v2_background_rows_materialized",
                                 float(self._builder.last_rows_materialized))
            with self._lock:
                self._status = snapshot
            return snapshot
        duration = (time.perf_counter() - started) * 1000
        snapshot = V2RefreshSnapshot("AVAILABLE", candidate.state_id,
                                     candidate.state_as_of, None, duration,
                                     self._builder.last_rows_materialized)
        self.metrics.observe("v2_background_build_duration_ms", duration)
        self.metrics.observe("v2_background_rows_materialized",
                             float(self._builder.last_rows_materialized))
        with self._lock:
            self._state = candidate
            self._status = snapshot
        return snapshot

    def capture(self, cutoff_at: datetime) -> V2EvidenceState:
        with self._lock:
            state = self._state
        if state is None:
            raise RuntimeError("V2_STATE_UNAVAILABLE")
        if (cutoff_at.tzinfo is None or state.state_as_of > cutoff_at.timestamp() or
                state.creation_status != "VALID"):
            raise RuntimeError("V2_STATE_CAUSALITY_OR_INTEGRITY_FAILURE")
        return state

    def status(self) -> V2RefreshSnapshot:
        with self._lock:
            return self._status

    def start(self, *, interval_seconds: float = V2_REFRESH_SECONDS) -> threading.Thread:
        interval = max(60.0, float(interval_seconds))

        def worker() -> None:
            while True:
                self.refresh()
                time.sleep(interval)

        thread = threading.Thread(target=worker, name="atom-v9-v2-builder", daemon=True)
        thread.start()
        return thread


def build_live_v1(snapshot: LiveSnapshot, v2: V2EvidenceState) -> V1Input:
    latest = snapshot.history.latest
    if latest is None:
        raise RuntimeError("LIVE_CUTOFF_UNAVAILABLE")
    cutoff_at = datetime.fromtimestamp(latest.event_epoch, timezone.utc)
    results = {
        "q1_momentum": snapshot.momentum,
        "q2_mean_reversion": snapshot.mean_reversion,
        "q3_volatility": snapshot.volatility,
        "q4_stat_arb": snapshot.stat_arb,
        "q5_microstructure": snapshot.microstructure,
        "q6_volume_liquidity": snapshot.volume_liquidity,
        "q7_relative_value": snapshot.relative_value,
        "q8_cross_asset": snapshot.cross_asset,
        "q9_factor": snapshot.factor,
        "q10_options_vol": snapshot.options_vol,
        "q11_regime": snapshot.regime,
        "q12_event_session": snapshot.event_session,
    }
    observations = []
    for quant_id in QUANT_IDS:
        result = results[quant_id]
        values = (getattr(result, "volatility_bps", None) if quant_id == "q3_volatility"
                  else getattr(result, "forecast_bps", None))
        source_epoch = latest.event_epoch
        if quant_id in (
            "q4_stat_arb", "q5_microstructure", "q6_volume_liquidity",
            "q7_relative_value", "q8_cross_asset", "q9_factor",
            "q10_options_vol",
        ) and result is not None:
            source_epoch = getattr(result, "source_as_of_epoch", None)
            if (isinstance(source_epoch, bool) or
                    not isinstance(source_epoch, (int, float)) or
                    not math.isfinite(source_epoch)):
                raise RuntimeError(f"{quant_id.upper()}_SOURCE_TIMESTAMP_UNAVAILABLE")
        source_at = datetime.fromtimestamp(source_epoch, timezone.utc)
        for index, horizon in enumerate(HORIZONS):
            value = None if values is None else values[index]
            observations.append(V1SlotObservation(
                quant_id, FORMULA_VERSION_MAP[quant_id], horizon,
                HORIZON_SECONDS[horizon],
                MAGNITUDE_BPS if quant_id == "q3_volatility" else DIRECTIONAL_BPS,
                value, cutoff_at, source_at, cutoff_at,
                DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION,
                None if value is not None else "MISSING_VALUE",
            ))
    return build_v1_input(
        cycle_id=f"COIN:{latest.event_epoch:.9f}", cutoff_at=cutoff_at,
        target_spec_id=TARGET_SPEC_ID, data_schema_version=DATA_SCHEMA_VERSION,
        source_spec_version=SOURCE_SPEC_VERSION, slots=observations,
        evidence_state_id=v2.state_id, evidence_state_version=v2.state_version,
        evidence_state_hash=v2.state_hash,
        evidence_state_as_of=datetime.fromtimestamp(v2.state_as_of, timezone.utc),
        evidence_training_start=(None if v2.training_start is None else
                                 datetime.fromtimestamp(v2.training_start, timezone.utc)),
        evidence_training_end=(None if v2.training_end is None else
                               datetime.fromtimestamp(v2.training_end, timezone.utc)),
    )


def v4_state_cohort_id(v1: V1Input, v2: V2EvidenceState) -> str:
    identities = []
    for horizon in HORIZONS:
        formula_map = {slot.quant_id: slot.formula_version for slot in v1.slots
                       if slot.horizon == horizon}
        cohort = build_cohort(v1=v1, v2=v2, horizon=horizon,
                              family_formula_map=formula_map)
        identities.append((cohort.cohort_id, cohort.cohort_hash))
    return "v9v4statecohort:" + canonical_sha256(tuple(identities))


class ProductionV9Runtime:
    """I/O-free production coordinator used by the quote path."""

    def __init__(self, database_url: str, v2_provider: ImmutableV2StateProvider,
                 *, connect: Callable | None = None,
                 metrics: OperationalMetrics | None = None,
                 monotonic_clock: Callable[[], float] = time.perf_counter):
        self._provider = v2_provider
        self.metrics = metrics or OperationalMetrics()
        self._monotonic = monotonic_clock
        self.compact_cache = ImmutableStateCache()
        self.accuracy_cache = ImmutableStateCache()

    def on_quote(self, snapshot: LiveSnapshot,
                 previous: MidpointObservation | None,
                 current: MidpointObservation) -> V4DCycleOutput | None:
        cutoff_at = datetime.fromtimestamp(current.event_epoch, timezone.utc)
        try:
            v2 = self._provider.capture(cutoff_at)
        except RuntimeError:
            return None
        v1_started = self._monotonic()
        v1 = build_live_v1(snapshot, v2)
        self.metrics.observe("v1_capture_latency_ms",
                             (self._monotonic() - v1_started) * 1000)
        coordinator = V4DCoordinator(
            capture_v1=lambda: v1,
            capture_v2=lambda _captured: v2,
            forecast_writer=None,
            compact_state_lookup=self.compact_cache.latest,
            accuracy_state_lookup=self.accuracy_cache.latest,
            state_cohort_id=v4_state_cohort_id,
            cutoff_midpoint=lambda _captured: current.midpoint,
            metrics=self.metrics,
            monotonic_clock=self._monotonic,
        )
        return coordinator.run_cycle()

    def close(self) -> None:
        return None


__all__ = [
    "ImmutableV2StateProvider", "PostgresV2StateBuilder",
    "ProductionV9Runtime", "TARGET_SPEC_ID", "V2RefreshSnapshot",
    "build_live_v1", "v4_state_cohort_id",
]
