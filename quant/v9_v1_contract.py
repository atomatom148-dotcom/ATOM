"""Immutable V9-V1 boundary over already-computed quant-family results.

This module only validates and canonicalizes observations.  It deliberately
contains no synthesis, calibration, weighting, or forecast mathematics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Iterable


CONTRACT_VERSION = "V9-V1"
OUTPUT_CONTRACT_VERSION = "V9-V1"
SYMBOL = "COIN"
MAX_ACTIVE_AGE_SECONDS = 10.0

QUANT_IDS = (
    "q1_momentum", "q2_mean_reversion", "q3_volatility", "q4_stat_arb",
    "q5_microstructure", "q6_volume_liquidity", "q7_relative_value",
    "q8_cross_asset", "q9_factor", "q10_options_vol", "q11_regime",
    "q12_event_session",
)
HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")
HORIZON_SECONDS = dict(zip(HORIZONS, (30, 60, 300, 900, 1800, 3600)))
AVAILABILITY_STATES = ("FRESH", "MISSING", "STALE", "INVALID")
DIRECTIONAL_BPS = "DIRECTIONAL_BPS"
MAGNITUDE_BPS = "MAGNITUDE_BPS"


def _expected_numerical_type(quant_id: str) -> str:
    return MAGNITUDE_BPS if quant_id == "q3_volatility" else DIRECTIONAL_BPS


def _require_timestamp(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class V1SlotObservation:
    """Unclassified, already-computed family observation supplied to V1."""

    quant_id: str
    formula_version: str
    horizon: str
    horizon_seconds: int
    numerical_type: str
    value_bps: float | None
    forecast_cutoff_at: datetime
    source_as_of_at: datetime
    available_at: datetime
    data_schema_version: str
    source_spec_version: str
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class V1Slot:
    quant_id: str
    formula_version: str
    horizon: str
    horizon_seconds: int
    numerical_type: str
    value_bps: float | None
    forecast_cutoff_at: datetime
    source_as_of_at: datetime
    available_at: datetime
    availability_state: str
    age_ms: int
    reason_code: str | None
    data_schema_version: str
    source_spec_version: str


@dataclass(frozen=True, slots=True)
class V1Input:
    contract_version: str
    cycle_id: str
    symbol: str
    cutoff_at: datetime
    target_spec_id: str
    data_schema_version: str
    source_spec_version: str
    horizons: tuple[str, ...]
    evidence_state_id: str | None
    evidence_state_version: str | None
    evidence_state_hash: str | None
    evidence_state_as_of: datetime | None
    evidence_training_start: datetime | None
    evidence_training_end: datetime | None
    slots: tuple[V1Slot, ...]


@dataclass(frozen=True, slots=True)
class V1HorizonResult:
    horizon: str
    horizon_seconds: int
    expected_return_bps: None = None
    move_percent: None = None
    range_lower_bps: None = None
    range_upper_bps: None = None
    nominal_range_coverage: None = None
    predictive_scale_bps: None = None
    status: str = "UNAVAILABLE"
    directional_input_count: int = 0
    used_quant_ids: tuple[str, ...] = ()
    effective_family_count: None = None
    q3_used: bool = False
    reason_codes: tuple[str, ...] = ("SYNTHESIS_NOT_IMPLEMENTED_V1",)
    meaningful_move_probabilities: None = None
    probability_calibration_status: None = None


@dataclass(frozen=True, slots=True)
class V1Output:
    output_contract_version: str
    model_version: str
    cycle_id: str
    symbol: str
    cutoff_at: datetime
    evidence_state_id: str | None
    evidence_state_as_of: datetime | None
    evidence_state_hash: str | None
    computation_status: str
    horizon_results: tuple[V1HorizonResult, ...]


def _classify(raw: V1SlotObservation, cutoff_at: datetime,
              data_schema_version: str, source_spec_version: str) -> V1Slot:
    for name in ("formula_version", "data_schema_version", "source_spec_version"):
        _require_text(getattr(raw, name), name)
    for name in ("forecast_cutoff_at", "source_as_of_at", "available_at"):
        _require_timestamp(getattr(raw, name), name)

    age_seconds = (cutoff_at - raw.forecast_cutoff_at).total_seconds()
    age_ms = round(age_seconds * 1000)
    reason = None
    value_bps = raw.value_bps
    state = "FRESH"
    if any(getattr(raw, name) > cutoff_at for name in
           ("forecast_cutoff_at", "source_as_of_at", "available_at")):
        state, reason = "INVALID", "FUTURE_TIMESTAMP"
    elif raw.numerical_type != _expected_numerical_type(raw.quant_id):
        state, reason = "INVALID", "WRONG_NUMERICAL_TYPE"
    elif raw.horizon_seconds != HORIZON_SECONDS[raw.horizon]:
        state, reason = "INVALID", "WRONG_HORIZON_SECONDS"
    elif (raw.data_schema_version != data_schema_version or
          raw.source_spec_version != source_spec_version):
        state, reason = "INVALID", "VERSION_MISMATCH"
    elif raw.value_bps is not None and (
        isinstance(raw.value_bps, bool) or not isinstance(raw.value_bps, (int, float))
        or not math.isfinite(raw.value_bps)
    ):
        state, reason = "INVALID", "INVALID_NUMERIC_VALUE"
        value_bps = None
    elif raw.quant_id == "q3_volatility" and raw.value_bps is not None and raw.value_bps < 0:
        state, reason = "INVALID", "NEGATIVE_MAGNITUDE"
    elif raw.reason_code == "SESSION_UNAVAILABLE":
        state, reason = "MISSING", "SESSION_UNAVAILABLE"
        value_bps = None
    elif raw.value_bps is None:
        state, reason = "MISSING", raw.reason_code or "MISSING_VALUE"
    elif age_seconds > MAX_ACTIVE_AGE_SECONDS:
        state, reason = "STALE", "MAX_ACTIVE_AGE_EXCEEDED"
    else:
        reason = raw.reason_code

    if state == "INVALID":
        value_bps = None

    return V1Slot(
        raw.quant_id, raw.formula_version, raw.horizon, raw.horizon_seconds,
        raw.numerical_type, value_bps, raw.forecast_cutoff_at,
        raw.source_as_of_at, raw.available_at, state, age_ms, reason,
        raw.data_schema_version, raw.source_spec_version,
    )


def build_v1_input(*, cycle_id: str, cutoff_at: datetime, target_spec_id: str,
                   data_schema_version: str, source_spec_version: str,
                   slots: Iterable[V1SlotObservation], symbol: str = SYMBOL,
                   contract_version: str = CONTRACT_VERSION,
                   evidence_state_id: str | None = None,
                   evidence_state_version: str | None = None,
                   evidence_state_hash: str | None = None,
                   evidence_state_as_of: datetime | None = None,
                   evidence_training_start: datetime | None = None,
                   evidence_training_end: datetime | None = None) -> V1Input:
    """Validate observations and return the exact canonical 72-slot input."""
    for name, value in (("contract_version", contract_version), ("cycle_id", cycle_id),
                        ("target_spec_id", target_spec_id),
                        ("data_schema_version", data_schema_version),
                        ("source_spec_version", source_spec_version)):
        _require_text(value, name)
    if contract_version != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION}")
    if symbol != SYMBOL:
        raise ValueError(f"symbol must be {SYMBOL}")
    _require_timestamp(cutoff_at, "cutoff_at")
    if evidence_state_as_of is not None:
        _require_timestamp(evidence_state_as_of, "evidence_state_as_of")
        if evidence_state_as_of > cutoff_at:
            raise ValueError("evidence_state_as_of cannot exceed cutoff_at")
    for name, value in (("evidence_training_start", evidence_training_start),
                        ("evidence_training_end", evidence_training_end)):
        if value is not None:
            _require_timestamp(value, name)

    by_identity: dict[tuple[str, str], V1SlotObservation] = {}
    for raw in slots:
        if raw.quant_id not in QUANT_IDS:
            raise ValueError(f"unknown quant_id: {raw.quant_id}")
        if raw.horizon not in HORIZONS:
            raise ValueError(f"unknown horizon: {raw.horizon}")
        identity = (raw.quant_id, raw.horizon)
        if identity in by_identity:
            raise ValueError(f"duplicate canonical identity: {identity}")
        by_identity[identity] = raw
    expected = {(quant_id, horizon) for quant_id in QUANT_IDS for horizon in HORIZONS}
    missing = expected - by_identity.keys()
    if missing:
        raise ValueError(f"all 72 canonical slots are required; missing {len(missing)}")
    canonical = tuple(_classify(by_identity[(q, h)], cutoff_at,
                                data_schema_version, source_spec_version)
                      for q in QUANT_IDS for h in HORIZONS)
    return V1Input(
        contract_version, cycle_id, symbol, cutoff_at, target_spec_id,
        data_schema_version, source_spec_version, HORIZONS, evidence_state_id,
        evidence_state_version, evidence_state_hash, evidence_state_as_of,
        evidence_training_start, evidence_training_end, canonical,
    )


def build_v1_output(value: V1Input, *, model_version: str) -> V1Output:
    """Return six empty V1 result shells; no forecasts are synthesized."""
    _require_text(model_version, "model_version")
    results = tuple(V1HorizonResult(h, HORIZON_SECONDS[h]) for h in HORIZONS)
    return V1Output(
        OUTPUT_CONTRACT_VERSION, model_version, value.cycle_id, value.symbol,
        value.cutoff_at, value.evidence_state_id, value.evidence_state_as_of,
        value.evidence_state_hash, "UNAVAILABLE", results,
    )


def v1_input_hash(value: V1Input) -> str:
    """Return a lowercase SHA-256 hex digest of canonical contract content."""
    def encode(item: object) -> object:
        if isinstance(item, datetime):
            return item.astimezone(timezone.utc).isoformat(timespec="microseconds")
        raise TypeError(f"unsupported canonical value: {type(item).__name__}")

    payload = json.dumps(asdict(value), default=encode, ensure_ascii=True,
                         allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "AVAILABILITY_STATES", "CONTRACT_VERSION", "DIRECTIONAL_BPS", "HORIZONS",
    "HORIZON_SECONDS", "MAGNITUDE_BPS", "MAX_ACTIVE_AGE_SECONDS", "QUANT_IDS",
    "V1HorizonResult", "V1Input", "V1Output", "V1Slot", "V1SlotObservation",
    "build_v1_input", "build_v1_output", "v1_input_hash",
]
