"""Immutable SIM-1 paper-simulation trade-intent contract.

This module is deliberately a pure value boundary.  It performs no clock or
I/O access and delegates canonical numerical encoding to the frozen V4A
canonicalization implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
import json
import math
import re
from types import MappingProxyType
from typing import Mapping

from quant.v9_v4a_evidence import _canonical, _decanonical, canonical_sha256


SIM_INTENT_CONTRACT_VERSION = "ATOM_TRUE_V9_SIM1_INTENT_1"
SIMULATOR_VERSION = "ATOM_TRUE_V9_SIM_1"
SIM_CANONICALIZATION_VERSION = "ATOM_TRUE_V9_SIM_CANONICAL_V4A_1"
SIMULATION_MODE = "PAPER_ONLY"
IDENTITY_PREFIX = "v9simintent:"
SYMBOL = "COIN"
INSTRUMENT = "COIN_SHARE"

HORIZON_SECONDS = MappingProxyType({
    "30S": 30,
    "1M": 60,
    "5M": 300,
    "15M": 900,
    "30M": 1800,
    "1H": 3600,
})
HORIZONS = tuple(HORIZON_SECONDS)
SOURCE_V3_STATUSES = frozenset(("AVAILABLE", "PROVISIONAL", "UNAVAILABLE"))
DECISIONS = frozenset(("LONG", "SHORT", "NO_TRADE"))
STATUSES = frozenset(("ACTIONABLE", "NO_TRADE", "UNAVAILABLE"))

_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class SimulationTradeIntent:
    contract_version: str
    canonicalization_version: str
    simulator_version: str
    intent_id: str
    intent_hash: str
    mode: str
    symbol: str
    instrument: str
    source_cycle_id: str
    source_forecast_record_id: str
    source_forecast_record_hash: str
    source_v2_state_id: str
    source_v2_state_hash: str
    source_v3_contract_version: str
    source_v3_model_version: str
    cutoff_at: datetime
    eligible_at: datetime
    horizon: str
    horizon_seconds: int
    final_bps: float | None
    source_v3_status: str
    decision: str
    status: str
    quantity_shares: int

    def __post_init__(self) -> None:
        _validate(self)


_FIELD_NAMES = tuple(field.name for field in fields(SimulationTradeIntent))
_HASH_FIELDS = tuple(name for name in _FIELD_NAMES
                     if name not in ("intent_id", "intent_hash"))


def _nonempty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")


def _validate(intent: SimulationTradeIntent) -> None:
    exact = {
        "contract_version": SIM_INTENT_CONTRACT_VERSION,
        "canonicalization_version": SIM_CANONICALIZATION_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "mode": SIMULATION_MODE,
        "symbol": SYMBOL,
        "instrument": INSTRUMENT,
    }
    for name, expected in exact.items():
        if getattr(intent, name) != expected:
            raise ValueError(f"invalid {name}")

    for name in ("source_cycle_id", "source_forecast_record_id",
                 "source_v2_state_id", "source_v3_contract_version",
                 "source_v3_model_version"):
        _nonempty_string(name, getattr(intent, name))
    for name in ("source_forecast_record_hash", "source_v2_state_hash",
                 "intent_hash"):
        value = getattr(intent, name)
        if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
            raise ValueError(f"invalid {name}")
    _nonempty_string("intent_id", intent.intent_id)

    for name in ("cutoff_at", "eligible_at"):
        value = getattr(intent, name)
        if (not isinstance(value, datetime) or value.tzinfo is None or
                value.utcoffset() is None):
            raise ValueError(f"{name} must be timezone-aware")
    if intent.eligible_at < intent.cutoff_at:
        raise ValueError("eligible_at must not precede cutoff_at")

    if not isinstance(intent.horizon, str) or intent.horizon not in HORIZON_SECONDS:
        raise ValueError("invalid horizon")
    if (isinstance(intent.horizon_seconds, bool) or
            not isinstance(intent.horizon_seconds, int) or
            intent.horizon_seconds != HORIZON_SECONDS[intent.horizon]):
        raise ValueError("invalid horizon_seconds")
    if intent.source_v3_status not in SOURCE_V3_STATUSES:
        raise ValueError("invalid source_v3_status")
    if intent.decision not in DECISIONS or intent.status not in STATUSES:
        raise ValueError("invalid decision or status")
    if (isinstance(intent.quantity_shares, bool) or
            not isinstance(intent.quantity_shares, int)):
        raise ValueError("quantity_shares must be an integer")

    expected = _mapping(intent.final_bps)
    if intent.source_v3_status == "UNAVAILABLE" and intent.final_bps is not None:
        raise ValueError("UNAVAILABLE source cannot contain final_bps")
    if (intent.decision, intent.status, intent.quantity_shares) != expected:
        raise ValueError("decision, status, and quantity do not match final_bps")
    digest = canonical_sha256(_math_payload(intent))
    if intent.intent_hash != digest or intent.intent_id != IDENTITY_PREFIX + digest:
        raise ValueError("intent mathematical identity mismatch")


def _mapping(final_bps: float | None) -> tuple[str, str, int]:
    if final_bps is None:
        return "NO_TRADE", "UNAVAILABLE", 0
    if isinstance(final_bps, bool) or not isinstance(final_bps, float):
        raise ValueError("final_bps must be a finite number or None")
    value = float(final_bps)
    if not math.isfinite(value):
        raise ValueError("final_bps must be finite")
    if value > 0.0:
        return "LONG", "ACTIONABLE", 1
    if value < 0.0:
        return "SHORT", "ACTIONABLE", 1
    return "NO_TRADE", "NO_TRADE", 0


def _math_payload(intent: SimulationTradeIntent) -> dict[str, object]:
    values = asdict(intent)
    return {name: values[name] for name in _HASH_FIELDS}


def build_simulation_trade_intent(*, source_cycle_id: str,
        source_forecast_record_id: str, source_forecast_record_hash: str,
        source_v2_state_id: str, source_v2_state_hash: str,
        source_v3_contract_version: str, source_v3_model_version: str,
        cutoff_at: datetime, eligible_at: datetime, horizon: str,
        horizon_seconds: int, final_bps: float | None,
        source_v3_status: str) -> SimulationTradeIntent:
    """Build and deterministically identify one validated simulator intent."""
    decision, status, quantity = _mapping(final_bps)
    values: dict[str, object] = {
        "contract_version": SIM_INTENT_CONTRACT_VERSION,
        "canonicalization_version": SIM_CANONICALIZATION_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "mode": SIMULATION_MODE, "symbol": SYMBOL, "instrument": INSTRUMENT,
        "source_cycle_id": source_cycle_id,
        "source_forecast_record_id": source_forecast_record_id,
        "source_forecast_record_hash": source_forecast_record_hash,
        "source_v2_state_id": source_v2_state_id,
        "source_v2_state_hash": source_v2_state_hash,
        "source_v3_contract_version": source_v3_contract_version,
        "source_v3_model_version": source_v3_model_version,
        "cutoff_at": cutoff_at, "eligible_at": eligible_at,
        "horizon": horizon, "horizon_seconds": horizon_seconds,
        "final_bps": None if final_bps is None else float(final_bps),
        "source_v3_status": source_v3_status, "decision": decision,
        "status": status, "quantity_shares": quantity,
    }
    digest = canonical_sha256(values)
    return SimulationTradeIntent(intent_id=IDENTITY_PREFIX + digest,
                                 intent_hash=digest, **values)  # type: ignore[arg-type]


def serialize_simulation_trade_intent(intent: SimulationTradeIntent) -> str:
    """Return the exact V4A-canonical JSON representation of an intent."""
    if not isinstance(intent, SimulationTradeIntent):
        raise ValueError("intent must be a SimulationTradeIntent")
    _validate(intent)
    digest = canonical_sha256(_math_payload(intent))
    if intent.intent_hash != digest or intent.intent_id != IDENTITY_PREFIX + digest:
        raise ValueError("intent mathematical identity mismatch")
    return json.dumps(_canonical(asdict(intent)), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True)


def deserialize_simulation_trade_intent(
        payload: str | Mapping[str, object]) -> SimulationTradeIntent:
    """Strictly decode an intent and fail closed on malformed or tampered data."""
    try:
        canonical = json.loads(payload) if isinstance(payload, str) else payload
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("intent payload is not valid JSON") from error
    if not isinstance(canonical, Mapping):
        raise ValueError("intent payload must be an object")
    if set(canonical) != set(_FIELD_NAMES):
        raise ValueError("intent payload has missing or unknown fields")
    try:
        value = _decanonical(dict(canonical))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("intent payload has invalid canonical values") from error
    if not isinstance(value, dict) or set(value) != set(_FIELD_NAMES):
        raise ValueError("intent payload does not match the contract")
    try:
        intent = SimulationTradeIntent(**value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("intent payload does not match the contract") from error
    digest = canonical_sha256(_math_payload(intent))
    if intent.intent_hash != digest or intent.intent_id != IDENTITY_PREFIX + digest:
        raise ValueError("intent mathematical identity mismatch")
    return intent
