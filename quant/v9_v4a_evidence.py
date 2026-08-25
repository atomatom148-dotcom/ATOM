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

from quant.v9_v1_contract import HORIZON_SECONDS, V1Input, v1_input_hash
from quant.v9_v2d_evidence_state import V2EvidenceState
from quant.v9_v3_synthesis import (
    CANONICAL_FAMILIES, CONTRACT_VERSION as V3_CONTRACT_VERSION,
    MODEL_VERSION, V3HorizonResult,
)


CONTRACT_VERSION = "ATOM_TRUE_V9_V4_1"
EVIDENCE_VERSION = "ATOM_TRUE_V9_V4A_1"
REPLAY_METHOD_VERSION = "ATOM_TRUE_V9_V4_REPLAY_1"
EVIDENCE_ORIGINS = frozenset(("PRODUCTION", "CAUSAL_REPLAY"))
TARGET_TIMING_REASON = "TARGET_TIMING_UNVERIFIED"
TARGET_TIMING_METHOD_VERSION = "ATOM_TRUE_V9_V4_TARGET_FIRST_AT_OR_AFTER_1"
OVERLAP_METHOD_VERSION = "ATOM_TRUE_V9_V4_OVERLAP_1"
COMMIT_PROOF_METHOD = "POST_COMMIT_DB_OBSERVATION_V1"
COMMIT_PROOF_MISSING_REASON = "FORECAST_COMMIT_PROOF_MISSING"
COMMIT_PROOF_LATE_REASON = "FORECAST_COMMITTED_AT_OR_AFTER_TARGET_ENDPOINT"


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
    if hasattr(value, "__dict__"):
        return _canonical(vars(value))
    return value


def _decanonical(value: object) -> object:
    """Reverse the frozen JSON wrappers used by every compact V4 record."""
    if isinstance(value, list):
        return tuple(_decanonical(item) for item in value)
    if isinstance(value, dict):
        if set(value) == {"$timestamp_utc"}:
            token = value["$timestamp_utc"]
            if not isinstance(token, str):
                raise ValueError("invalid canonical timestamp")
            parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("canonical timestamp is not timezone-aware")
            return parsed.astimezone(timezone.utc)
        if set(value) == {"$float64"}:
            token = value["$float64"]
            if not isinstance(token, str):
                raise ValueError("invalid canonical float")
            parsed = float.fromhex(token)
            if not math.isfinite(parsed):
                raise ValueError("canonical float is not finite")
            return 0.0 if parsed == 0.0 else parsed
        return {str(key): _decanonical(item) for key, item in value.items()}
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
        ("compatible_family_formula_map", tuple(
            (family, family_formula_map[family]) for family in CANONICAL_FAMILIES
            if family in family_formula_map
        )),
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
    v3_contract_version: str
    v3_model_version: str
    v2_state_id: str
    v2_state_version: str
    v2_state_hash: str
    v2_state_as_of: float
    expected_return_bps: float | None
    predictive_variance_bps2: float | None
    q3_diagnostic_magnitude_bps: float | None
    status: str
    reason_codes: tuple[str, ...]
    persisted_at: datetime | None = None
    persistence_proof_eligible: bool | None = None
    persistence_reason: str | None = None
    v1_contract_version: str | None = None
    v1_input_hash: str | None = None
    target_spec_id: str | None = None
    data_schema_version: str | None = None
    source_spec_version: str | None = None
    cutoff_midpoint: float | None = None
    used_quant_ids: tuple[str, ...] = ()
    family_weights: tuple[float, ...] = ()
    directional_input_count: int = 0
    covariance_mode: str | None = None
    q3_used: bool = False
    gamma: float = 0.0
    phi: float = 1.0

    @property
    def logical_key(self) -> tuple[object, ...]:
        return self.symbol, self.cutoff_at, self.horizon, self.cycle_id, self.v3_model_version


def _forecast_math(record: ForecastRecord) -> dict[str, object]:
    excluded = {"forecast_record_id", "forecast_record_hash", "persisted_at",
                "persistence_proof_eligible", "persistence_reason"}
    return {key: value for key, value in asdict(record).items() if key not in excluded}


def build_forecast(*, v1: V1Input, v2: V2EvidenceState, result: V3HorizonResult,
                   evidence_origin: str, cutoff_midpoint: float | None = None) -> ForecastRecord:
    if evidence_origin not in EVIDENCE_ORIGINS:
        raise ValueError("unsupported durable evidence_origin")
    if result.horizon not in HORIZON_SECONDS:
        raise ValueError("unsupported horizon")
    formula_map = {slot.quant_id: slot.formula_version for slot in v1.slots
                   if slot.horizon == result.horizon}
    cohort = build_cohort(v1=v1, v2=v2, horizon=result.horizon,
                          family_formula_map=formula_map)
    if cutoff_midpoint is not None and (
            isinstance(cutoff_midpoint, bool) or
            not isinstance(cutoff_midpoint, (int, float)) or
            not math.isfinite(cutoff_midpoint) or cutoff_midpoint <= 0):
        raise ValueError("cutoff_midpoint must be positive and finite")
    input_hash = (v1_input_hash(v1) if isinstance(v1, V1Input)
                  else canonical_sha256(v1))
    record = ForecastRecord("", "", CONTRACT_VERSION, EVIDENCE_VERSION,
        evidence_origin, cohort.cohort_id, cohort.cohort_hash, v1.symbol,
        v1.cutoff_at, v1.cutoff_at + timedelta(seconds=result.horizon_seconds),
        result.horizon, result.horizon_seconds, v1.cycle_id,
        V3_CONTRACT_VERSION, MODEL_VERSION,
        v2.state_id, v2.state_version, v2.state_hash, v2.state_as_of,
        result.expected_return_bps, result.predictive_variance_bps2,
        result.q3_diagnostic_magnitude_bps, result.status, result.reason_codes,
        v1_contract_version=v1.contract_version, v1_input_hash=input_hash,
        target_spec_id=v1.target_spec_id,
        data_schema_version=v1.data_schema_version,
        source_spec_version=v1.source_spec_version,
        cutoff_midpoint=None if cutoff_midpoint is None else float(cutoff_midpoint),
        used_quant_ids=tuple(result.used_quant_ids),
        family_weights=tuple(result.weights),
        directional_input_count=result.directional_input_count,
        covariance_mode=result.covariance_mode, q3_used=result.q3_used,
        gamma=result.gamma, phi=result.phi)
    digest = canonical_sha256(_forecast_math(record))
    return replace(record, forecast_record_id="v9v4f:" + digest,
                   forecast_record_hash=digest)


def deserialize_forecast_record(payload: str | Mapping[str, object], *,
                                expected_hash: str | None = None) -> ForecastRecord:
    """Reconstruct and verify one immutable forecast-ledger payload."""

    canonical = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(canonical, Mapping):
        raise ValueError("forecast record JSON must be an object")
    value = _decanonical(dict(canonical))
    if not isinstance(value, dict):
        raise ValueError("forecast record JSON is invalid")
    for field in ("reason_codes", "used_quant_ids", "family_weights"):
        if field in value:
            value[field] = tuple(value[field])
    try:
        record = ForecastRecord(**value)
    except TypeError as error:
        raise ValueError("forecast record JSON does not match the contract") from error
    if expected_hash is not None and record.forecast_record_hash != expected_hash:
        raise ValueError("forecast record stored hash mismatch")
    digest = canonical_sha256(_forecast_math(record))
    if (record.forecast_record_hash != digest or
            record.forecast_record_id != "v9v4f:" + digest):
        raise ValueError("forecast record mathematical hash mismatch")
    return record


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
    previous_observation_at: datetime | None = None
    target_timing_method_version: str = TARGET_TIMING_METHOD_VERSION

    @property
    def logical_key(self) -> tuple[str, str]:
        return self.forecast_record_id, self.target_identity


def deserialize_outcome_record(payload: str | Mapping[str, object], *,
                               expected_hash: str | None = None) -> OutcomeRecord:
    """Reconstruct and validate the originally stored outcome metadata."""
    canonical = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(canonical, Mapping):
        raise ValueError("outcome record JSON must be an object")
    value = _decanonical(dict(canonical))
    if not isinstance(value, dict):
        raise ValueError("outcome record JSON is invalid")
    if "reason_codes" in value:
        value["reason_codes"] = tuple(value["reason_codes"])
    try:
        record = OutcomeRecord(**value)
    except TypeError as error:
        raise ValueError("outcome record JSON does not match the contract") from error
    digest = canonical_sha256(_outcome_math(record))
    if (expected_hash is not None and record.outcome_record_hash != expected_hash) or (
            record.outcome_record_hash != digest or
            record.outcome_record_id != "v9v4o:" + digest):
        raise ValueError("outcome record hash mismatch")
    return record


def _outcome_math(record: OutcomeRecord) -> dict[str, object]:
    excluded = {"outcome_record_id", "outcome_record_hash", "created_at"}
    return {key: value for key, value in asdict(record).items() if key not in excluded}


def canonical_target_identity(forecast: ForecastRecord) -> str:
    payload = {
        "symbol": forecast.symbol,
        "cycle_id": forecast.cycle_id,
        "cutoff_at": forecast.cutoff_at,
        "target_endpoint": forecast.target_endpoint,
        "horizon": forecast.horizon,
        "target_spec_id": forecast.target_spec_id,
        "data_schema_version": forecast.data_schema_version,
        "source_spec_version": forecast.source_spec_version,
    }
    return "v9target:" + canonical_sha256(payload)


def build_outcome(*, forecast: ForecastRecord, target_identity: str,
                  endpoint_observation_at: datetime, target_resolved_at: datetime,
                  actual_return_bps: float | None,
                  previous_observation_at: datetime | None = None) -> OutcomeRecord:
    for name, value in (("endpoint_observation_at", endpoint_observation_at),
                        ("target_resolved_at", target_resolved_at)):
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError(f"{name} must be timezone-aware")
    if previous_observation_at is not None and (
            not isinstance(previous_observation_at, datetime) or
            previous_observation_at.tzinfo is None):
        raise ValueError("previous_observation_at must be timezone-aware")
    delay = (endpoint_observation_at - forecast.target_endpoint).total_seconds()
    canonical_identity = canonical_target_identity(forecast)
    timing_verified = (
        target_identity == canonical_identity and
        previous_observation_at is not None and
        previous_observation_at < forecast.target_endpoint <= endpoint_observation_at and
        target_resolved_at >= endpoint_observation_at
    )
    reasons = [] if timing_verified else [TARGET_TIMING_REASON]
    if forecast.persistence_proof_eligible is not True:
        reasons.append(forecast.persistence_reason or COMMIT_PROOF_MISSING_REASON)
    elif forecast.persisted_at is None:
        reasons.append(COMMIT_PROOF_MISSING_REASON)
    elif forecast.persisted_at >= forecast.target_endpoint:
        reasons.append(COMMIT_PROOF_LATE_REASON)
    if actual_return_bps is not None and (
            isinstance(actual_return_bps, bool) or
            not isinstance(actual_return_bps, (int, float)) or
            not math.isfinite(actual_return_bps)):
        reasons.append("TARGET_VALUE_INVALID")
    proof_eligible = (timing_verified and not reasons and
                      actual_return_bps is not None and
                      forecast.persistence_proof_eligible is True)
    record = OutcomeRecord("", "", CONTRACT_VERSION, EVIDENCE_VERSION,
        forecast.forecast_record_id, target_identity, forecast.target_endpoint,
        endpoint_observation_at, delay, target_resolved_at, actual_return_bps,
        "VERIFIED" if timing_verified else "UNVERIFIED",
        tuple(sorted(reasons)), proof_eligible,
        previous_observation_at=previous_observation_at,
        target_timing_method_version=TARGET_TIMING_METHOD_VERSION)
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
    forecast_groups: dict[tuple[object, ...], list[tuple[ForecastRecord, OutcomeRecord]]] = {}
    for pair in resolved:
        forecast_groups.setdefault(pair[0].logical_key, []).append(pair)
    forecast_unconflicted = [pair for pairs in forecast_groups.values()
                             if len({pair[0].forecast_record_hash for pair in pairs}) == 1
                             for pair in pairs]

    outcome_groups: dict[tuple[str, str], list[tuple[ForecastRecord, OutcomeRecord]]] = {}
    for pair in forecast_unconflicted:
        outcome_groups.setdefault(pair[1].logical_key, []).append(pair)
    outcome_unconflicted = [pair for pairs in outcome_groups.values()
                            if len({pair[1].outcome_record_hash for pair in pairs}) == 1
                            for pair in pairs]
    eligible = [(f, o) for f, o in outcome_unconflicted if o.proof_eligible]
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
        if getattr(connection, "autocommit", False):
            raise ValueError("V4A logical uniqueness requires a transaction")
        self.connection = connection
        self.last_write_status: str | None = None

    @staticmethod
    def _logical_lock_id(namespace: str, logical_key: tuple[object, ...]) -> int:
        digest = canonical_sha256(
            ("ATOM_TRUE_V9_V4A_LOGICAL_LOCK_1", namespace, logical_key))
        return int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True)

    @staticmethod
    def _without_commit_proof(record: ForecastRecord) -> ForecastRecord:
        return replace(
            record,
            persisted_at=None,
            persistence_proof_eligible=False,
            persistence_reason=COMMIT_PROOF_MISSING_REASON,
        )

    @staticmethod
    def _apply_commit_proof(record: ForecastRecord, row) -> ForecastRecord:
        if row is None or len(row) != 6:
            return V4AWriter._without_commit_proof(record)
        (record_id, record_hash, observed_at, target_endpoint,
         proof_eligible, proof_method) = row
        if (str(record_id) != record.forecast_record_id or
                str(record_hash) != record.forecast_record_hash or
                target_endpoint != record.target_endpoint or
                proof_method != COMMIT_PROOF_METHOD or
                not isinstance(observed_at, datetime) or
                observed_at.tzinfo is None):
            raise ValueError("forecast commit proof failed integrity validation")
        eligible = bool(proof_eligible) and observed_at < target_endpoint
        return replace(
            record,
            persisted_at=observed_at,
            persistence_proof_eligible=eligible,
            persistence_reason=None if eligible else COMMIT_PROOF_LATE_REASON,
        )

    def record_forecast_commit_proof(self, record: ForecastRecord) -> ForecastRecord:
        """Observe a previously committed forecast in a separate transaction."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "SELECT forecast_record_id, forecast_record_hash, "
                "commit_observed_at, target_endpoint, proof_eligible, proof_method "
                "FROM atom_v9_internal.record_forecast_commit_proof(%s)",
                (record.forecast_record_id,),
            )
            row = cursor.fetchone()
            _commit_if_supported(self.connection)
            return self._apply_commit_proof(record, row)
        except Exception:
            _rollback_if_supported(self.connection)
            raise
        finally:
            _close_if_supported(cursor)

    def read_forecast_commit_proof(self, record: ForecastRecord) -> ForecastRecord:
        """Hydrate eligibility only from the narrow authoritative proof reader."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "SELECT forecast_record_id, forecast_record_hash, "
                "commit_observed_at, target_endpoint, proof_eligible, proof_method "
                "FROM atom_v9_internal.read_forecast_commit_proof(%s)",
                (record.forecast_record_id,),
            )
            row = cursor.fetchone()
            _commit_if_supported(self.connection)
            return self._apply_commit_proof(record, row)
        except Exception:
            _rollback_if_supported(self.connection)
            raise
        finally:
            _close_if_supported(cursor)

    def persist_forecast(self, record: ForecastRecord, persisted_at: datetime) -> ForecastRecord:
        stored = self._without_commit_proof(record)
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "SELECT pg_catalog.pg_advisory_xact_lock(%s)",
                (self._logical_lock_id("FORECAST", record.logical_key),),
            )
            cursor.execute("SELECT forecast_record_hash, record_json FROM atom_v9_v4_forecasts WHERE symbol=%s AND cutoff_at=%s AND horizon=%s AND cycle_id=%s AND v3_model_version=%s", record.logical_key)
            rows = tuple(cursor.fetchall())
            hashes = tuple(row[0] for row in rows)
            distinct_hashes = set(hashes)
            if len(distinct_hashes) > 1:
                self.last_write_status = "FORECAST_DUPLICATE_CONFLICT"
                stored = replace(stored, persistence_proof_eligible=False,
                                 persistence_reason="FORECAST_DUPLICATE_CONFLICT")
                _commit_if_supported(self.connection)
                return stored
            if record.forecast_record_hash in distinct_hashes:
                self.last_write_status = "IDEMPOTENT"
                _commit_if_supported(self.connection)
                original = next(row for row in rows if row[0] == record.forecast_record_hash)
                if len(original) > 1 and original[1] is not None:
                    return self._without_commit_proof(deserialize_forecast_record(
                        original[1], expected_hash=record.forecast_record_hash))
                return stored
            if distinct_hashes:
                self.last_write_status = "FORECAST_DUPLICATE_CONFLICT"
                stored = replace(stored, persistence_proof_eligible=False,
                                 persistence_reason="FORECAST_DUPLICATE_CONFLICT")
                _commit_if_supported(self.connection)
                return stored
            self.last_write_status = "INSERT"
            cursor.execute("INSERT INTO atom_v9_v4_forecasts (forecast_record_id, forecast_record_hash, symbol, cutoff_at, target_endpoint, horizon, cycle_id, v3_model_version, record_json, persisted_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                           (record.forecast_record_id, record.forecast_record_hash,
                            record.symbol, record.cutoff_at, record.target_endpoint, record.horizon,
                            record.cycle_id, record.v3_model_version,
                            json.dumps(_canonical(asdict(stored)), sort_keys=True), persisted_at))
            _commit_if_supported(self.connection)
            return stored
        except Exception:
            _rollback_if_supported(self.connection)
            raise
        finally:
            _close_if_supported(cursor)

    def persist_outcome(self, record: OutcomeRecord, created_at: datetime) -> OutcomeRecord:
        stored = replace(record, created_at=created_at)
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "SELECT pg_catalog.pg_advisory_xact_lock(%s)",
                (self._logical_lock_id("OUTCOME", record.logical_key),),
            )
            cursor.execute("SELECT outcome_record_hash, record_json FROM atom_v9_v4_outcomes WHERE forecast_record_id=%s AND target_identity=%s", record.logical_key)
            rows = tuple(cursor.fetchall())
            hashes = tuple(row[0] for row in rows)
            distinct_hashes = set(hashes)
            if len(distinct_hashes) > 1:
                self.last_write_status = "OUTCOME_CONFLICT"
                _commit_if_supported(self.connection)
                return stored
            if record.outcome_record_hash in distinct_hashes:
                self.last_write_status = "IDEMPOTENT"
                _commit_if_supported(self.connection)
                original = next(row for row in rows if row[0] == record.outcome_record_hash)
                if len(original) > 1 and original[1] is not None:
                    return deserialize_outcome_record(
                        original[1], expected_hash=record.outcome_record_hash)
                return stored
            if distinct_hashes:
                self.last_write_status = "OUTCOME_CONFLICT"
                _commit_if_supported(self.connection)
                return stored
            self.last_write_status = "INSERT"
            cursor.execute("INSERT INTO atom_v9_v4_outcomes (outcome_record_id, outcome_record_hash, forecast_record_id, target_identity, record_json, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                           (record.outcome_record_id, record.outcome_record_hash,
                            record.forecast_record_id, record.target_identity,
                            json.dumps(_canonical(asdict(stored)), sort_keys=True), created_at))
            _commit_if_supported(self.connection)
            return stored
        except Exception:
            _rollback_if_supported(self.connection)
            raise
        finally:
            _close_if_supported(cursor)


def _close_if_supported(value: object) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()


def _commit_if_supported(connection: object) -> None:
    if not getattr(connection, "autocommit", False):
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()


def _rollback_if_supported(connection: object) -> None:
    if not getattr(connection, "autocommit", False):
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()