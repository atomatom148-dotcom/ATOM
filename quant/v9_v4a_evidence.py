"""Frozen V4A evidence contracts, identities, persistence, and overlap selection.

V4A records production or causal-replay evidence; it performs no accuracy or
Effective-N calculation.  Durable records are immutable values and the writer
uses only SELECT and INSERT statements.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Iterable, Mapping

from quant.v9_v1_contract import HORIZON_SECONDS, V1Input
from quant.v9_v2d_evidence_state import V2EvidenceState
from quant.v9_v3_synthesis import MODEL_VERSION, V3HorizonResult


CONTRACT_VERSION = "ATOM_TRUE_V9_V4_1"
EVIDENCE_VERSION = "ATOM_TRUE_V9_V4A_1"
REPLAY_METHOD_VERSION = "ATOM_TRUE_V9_V4_REPLAY_1"
V3_CONTRACT_VERSION = None
EVIDENCE_ORIGINS = frozenset(("PRODUCTION", "CAUSAL_REPLAY"))
TARGET_TIMING_STATUS = "UNVERIFIED"
TARGET_TIMING_REASON = "TARGET_TIMING_UNVERIFIED"
OVERLAP_METHOD_VERSION = "ATOM_TRUE_V9_V4_OVERLAP_1"


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(value: object) -> object:
    if isinstance(value, datetime):
        return {"$timestamp_utc": _timestamp(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("V4A evidence cannot contain NaN or infinity")
        return {"$float64": (0.0 if value == 0.0 else value).hex()}
    if isinstance(value, tuple) or isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if hasattr(value, "__dataclass_fields__"):
        return _canonical(asdict(value))
    return value


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CohortIdentity:
    cohort_id: str
    cohort_hash: str
    payload: tuple[tuple[str, object], ...]


def build_cohort(*, v1: V1Input, v2: V2EvidenceState, horizon: str,
                 family_formula_map: Mapping[str, str]) -> CohortIdentity:
    """Build identity solely from lineage exposed by frozen upstream values."""
    lineage = (
        v2.v2a_method_version, v2.v2b_method_version, v2.v2c_method_version,
        v2.effective_n_method_version, v2.calibration_method_version,
        v2.covariance_method_version, v2.numerical_canonicalization_version,
    )
    payload = (
        ("symbol", v1.symbol), ("horizon", horizon),
        ("v3_contract_version", V3_CONTRACT_VERSION),
        ("v3_model_version", MODEL_VERSION),
        ("compatible_family_formula_map", tuple(sorted(family_formula_map.items()))),
        ("v2_method_lineage", lineage), ("target_spec_id", v1.target_spec_id),
        ("data_schema_version", v1.data_schema_version),
        ("source_spec_version", v1.source_spec_version),
        ("replay_method_version", REPLAY_METHOD_VERSION),
    )
    digest = canonical_sha256(dict(payload))
    return CohortIdentity("v9v4cohort:" + digest, digest, payload)


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    forecast_record_id: str
    forecast_record_hash: str
    contract_version: str
    evidence_version: str
    evidence_origin: str
    cohort_id: str
    cohort_hash: str
    symbol: str
    cutoff_at: datetime
    target_endpoint: datetime
    horizon: str
    horizon_seconds: int
    cycle_id: str
    v3_contract_version: None
    v3_model_version: str
    expected_return_bps: float | None
    predictive_variance_bps2: float | None
    q3_diagnostic_magnitude_bps: float | None
    status: str
    reason_codes: tuple[str, ...]
    persisted_at: datetime | None = None
    persistence_proof_eligible: bool | None = None
    persistence_reason: str | None = None

    @property
    def logical_key(self) -> tuple[object, ...]:
        return self.symbol, self.cutoff_at, self.horizon, self.cycle_id, self.v3_model_version


def _forecast_math(record: ForecastRecord) -> dict[str, object]:
    excluded = {"forecast_record_id", "forecast_record_hash", "persisted_at",
                "persistence_proof_eligible", "persistence_reason"}
    return {key: value for key, value in asdict(record).items() if key not in excluded}


def build_forecast(*, v1: V1Input, v2: V2EvidenceState, result: V3HorizonResult,
                   evidence_origin: str) -> ForecastRecord:
    if evidence_origin not in EVIDENCE_ORIGINS:
        raise ValueError("unsupported durable evidence_origin")
    if result.horizon not in HORIZON_SECONDS:
        raise ValueError("unsupported horizon")
    formula_map = {slot.quant_id: slot.formula_version for slot in v1.slots
                   if slot.horizon == result.horizon}
    cohort = build_cohort(v1=v1, v2=v2, horizon=result.horizon,
                          family_formula_map=formula_map)
    record = ForecastRecord("", "", CONTRACT_VERSION, EVIDENCE_VERSION,
        evidence_origin, cohort.cohort_id, cohort.cohort_hash, v1.symbol,
        v1.cutoff_at, v1.cutoff_at + timedelta(seconds=result.horizon_seconds),
        result.horizon, result.horizon_seconds, v1.cycle_id, None, MODEL_VERSION,
        result.expected_return_bps, result.predictive_variance_bps2,
        result.q3_diagnostic_magnitude_bps, result.status, result.reason_codes)
    digest = canonical_sha256(_forecast_math(record))
    return replace(record, forecast_record_id="v9v4f:" + digest,
                   forecast_record_hash=digest)


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    outcome_record_id: str
    outcome_record_hash: str
    contract_version: str
    evidence_version: str
    forecast_record_id: str
    target_identity: str
    target_endpoint: datetime
    endpoint_observation_at: datetime
    endpoint_observation_delay: float
    target_resolved_at: datetime
    actual_return_bps: float | None
    target_timing_status: str
    reason_codes: tuple[str, ...]
    proof_eligible: bool
    created_at: datetime | None = None

    @property
    def logical_key(self) -> tuple[str, str]:
        return self.forecast_record_id, self.target_identity


def _outcome_math(record: OutcomeRecord) -> dict[str, object]:
    excluded = {"outcome_record_id", "outcome_record_hash", "created_at"}
    return {key: value for key, value in asdict(record).items() if key not in excluded}


def build_outcome(*, forecast: ForecastRecord, target_identity: str,
                  endpoint_observation_at: datetime, target_resolved_at: datetime,
                  actual_return_bps: float | None) -> OutcomeRecord:
    delay = (endpoint_observation_at - forecast.target_endpoint).total_seconds()
    reasons = [TARGET_TIMING_REASON]
    if forecast.persisted_at is None or forecast.persisted_at > forecast.target_endpoint:
        reasons.append("FORECAST_PERSISTED_AFTER_TARGET_ENDPOINT")
    record = OutcomeRecord("", "", CONTRACT_VERSION, EVIDENCE_VERSION,
        forecast.forecast_record_id, target_identity, forecast.target_endpoint,
        endpoint_observation_at, delay, target_resolved_at, actual_return_bps,
        TARGET_TIMING_STATUS, tuple(sorted(reasons)), False)
    digest = canonical_sha256(_outcome_math(record))
    return replace(record, outcome_record_id="v9v4o:" + digest,
                   outcome_record_hash=digest)


class DuplicateConflict(RuntimeError):
    pass


def classify_duplicate(existing_hash: str | None, candidate_hash: str, *, outcome=False) -> str:
    if existing_hash is None:
        return "INSERT"
    if existing_hash == candidate_hash:
        return "IDEMPOTENT"
    raise DuplicateConflict("OUTCOME_CONFLICT" if outcome else "FORECAST_DUPLICATE_CONFLICT")


@dataclass(frozen=True, slots=True)
class OverlapSelection:
    raw_resolved_n: int
    non_overlapping_n: int
    first_cutoff: datetime | None
    last_cutoff: datetime | None
    selected_ids: tuple[str, ...]
    selected_digest: str
    method_version: str = OVERLAP_METHOD_VERSION


def select_non_overlapping(records: Iterable[tuple[ForecastRecord, OutcomeRecord]]) -> OverlapSelection:
    resolved = list(records)
    eligible = [(f, o) for f, o in resolved if o.proof_eligible]
    groups: dict[tuple[object, ...], list[tuple[ForecastRecord, OutcomeRecord]]] = {}
    for pair in eligible:
        groups.setdefault(pair[0].logical_key, []).append(pair)
    canonical = []
    for pairs in groups.values():
        hashes = {pair[0].forecast_record_hash for pair in pairs}
        if len(hashes) == 1:
            canonical.append(min(pairs, key=lambda pair: pair[0].forecast_record_id))
    canonical.sort(key=lambda pair: (pair[0].cutoff_at, pair[0].forecast_record_id))
    selected: list[tuple[ForecastRecord, OutcomeRecord]] = []
    for pair in canonical:
        if not selected or pair[0].cutoff_at >= selected[-1][0].cutoff_at + timedelta(seconds=selected[-1][0].horizon_seconds):
            selected.append(pair)
    ids = tuple(pair[0].forecast_record_id for pair in selected)
    return OverlapSelection(len(eligible), len(selected),
        selected[0][0].cutoff_at if selected else None,
        selected[-1][0].cutoff_at if selected else None, ids,
        canonical_sha256(ids))


class V4AWriter:
    """Least-privilege DB-API writer: its SQL surface is SELECT plus INSERT."""

    def __init__(self, connection):
        self.connection = connection

    def persist_forecast(self, record: ForecastRecord, persisted_at: datetime) -> ForecastRecord:
        eligible = persisted_at <= record.target_endpoint
        stored = replace(record, persisted_at=persisted_at,
                         persistence_proof_eligible=eligible,
                         persistence_reason=None if eligible else "FORECAST_PERSISTED_AFTER_TARGET_ENDPOINT")
        cursor = self.connection.cursor()
        cursor.execute("SELECT forecast_record_hash FROM atom_v9_v4_forecasts WHERE symbol=%s AND cutoff_at=%s AND horizon=%s AND cycle_id=%s AND v3_model_version=%s", record.logical_key)
        row = cursor.fetchone()
        if classify_duplicate(row[0] if row else None, record.forecast_record_hash) == "INSERT":
            cursor.execute("INSERT INTO atom_v9_v4_forecasts (forecast_record_id, forecast_record_hash, symbol, cutoff_at, horizon, cycle_id, v3_model_version, record_json, persisted_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                           (record.forecast_record_id, record.forecast_record_hash,
                            record.symbol, record.cutoff_at, record.horizon,
                            record.cycle_id, record.v3_model_version,
                            json.dumps(_canonical(asdict(stored)), sort_keys=True), persisted_at))
        return stored

    def persist_outcome(self, record: OutcomeRecord, created_at: datetime) -> OutcomeRecord:
        stored = replace(record, created_at=created_at)
        cursor = self.connection.cursor()
        cursor.execute("SELECT outcome_record_hash FROM atom_v9_v4_outcomes WHERE forecast_record_id=%s AND target_identity=%s", record.logical_key)
        row = cursor.fetchone()
        if classify_duplicate(row[0] if row else None, record.outcome_record_hash, outcome=True) == "INSERT":
            cursor.execute("INSERT INTO atom_v9_v4_outcomes (outcome_record_id, outcome_record_hash, forecast_record_id, target_identity, record_json, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                           (record.outcome_record_id, record.outcome_record_hash,
                            record.forecast_record_id, record.target_identity,
                            json.dumps(_canonical(asdict(stored)), sort_keys=True), created_at))
        return stored
