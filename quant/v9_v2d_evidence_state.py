"""Immutable assembly boundary for the complete V9-V2 evidence state.

V2D deliberately performs no estimation and has no persistence or live-path
integration.  It validates and compacts caller-supplied, frozen V2A/B/C
results into a deterministic six-horizon value object.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from functools import lru_cache
import hashlib
import json
import math
import re
import types
from typing import Iterable, Mapping, Union, get_args, get_origin, get_type_hints

from quant.v9_v2a_dataset import (
    DIRECTIONAL_FAMILIES, FamilyLineage, HORIZON_SECONDS,
    METHOD_VERSION as V2A_METHOD_VERSION, Q3, SYMBOL, V2ADataset,
    v2a_dataset_hash,
)
from quant.v9_v2b_calibration import (
    FORMULA_VERSION as V2B_METHOD_VERSION, DirectionalCalibration,
    Q3MagnitudeCalibration, V2BCalibration, v2b_component_hash,
)
from quant.v9_v2c_covariance import METHOD_VERSION as V2C_METHOD_VERSION, V2CCovariance


STATE_SCHEMA_VERSION = "V9-V2D-STATE-3"
STATE_VERSION = "V9-V2D-3"
MODEL_FAMILY = "V9-V2"
EFFECTIVE_N_METHOD_VERSION = "V9-V2B-PAIRED-IPS-1"
CALIBRATION_METHOD_VERSION = V2B_METHOD_VERSION
COVARIANCE_METHOD_VERSION = V2C_METHOD_VERSION
NUMERICAL_CANONICALIZATION_VERSION = "IEEE754-BINARY64-HEX-1"
HORIZONS = tuple(HORIZON_SECONDS)
STATUSES = frozenset(("MATURE", "PROVISIONAL", "UNAVAILABLE"))
_STATE_ID_PREFIX = "v9v2:"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_Q3_INTEGER_FLOAT_DEFAULTS = {
    "calibration_alpha": 0,
    "calibration_beta": 1,
    "effective_n": 0,
    "magnitude_residual_variance": 0,
    "magnitude_mae": 0,
    "magnitude_rmse": 0,
}
_MISSING_HORIZON_REASONS = frozenset((
    "HORIZON_EVIDENCE_UNAVAILABLE",
    "CROSS_LAYER_INTEGRITY_FAILURE",
    "NONFINITE_COMPONENT_STATE",
))


@dataclass(frozen=True, slots=True)
class DirectionalCalibrationState:
    quant_id: str
    formula_version: str
    data_schema_version: str
    source_spec_version: str
    dataset_hash: str
    calibration_intercept: float
    calibration_slope: float
    calibration_parameter_covariance_2x2: tuple[tuple[float, float], tuple[float, float]]
    effective_n: float
    residual_variance: float
    residual_standard_deviation: float
    status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Q3MagnitudeState:
    status: str
    reason_codes: tuple[str, ...]
    quant_id: str | None = None
    formula_version: str | None = None
    data_schema_version: str | None = None
    source_spec_version: str | None = None
    dataset_hash: str | None = None
    calibration_alpha: float | None = None
    calibration_beta: float | None = None
    parameter_covariance_2x2: tuple[tuple[float, float], tuple[float, float]] | None = None
    effective_n: float | None = None
    magnitude_residual_variance: float | None = None
    magnitude_mae: float | None = None
    magnitude_rmse: float | None = None


@dataclass(frozen=True, slots=True)
class HorizonEvidenceState:
    horizon: str
    horizon_seconds: int
    status: str
    reason_codes: tuple[str, ...]
    directional_calibrations: tuple[DirectionalCalibrationState, ...]
    family_lineage: tuple[FamilyLineage, ...]
    ordered_quant_ids: tuple[str, ...]
    pair_support_boolean_matrix: tuple[tuple[bool, ...], ...]
    stabilized_covariance_matrix: tuple[tuple[float, ...], ...] | None
    dependence_modeled: bool
    covariance_status: str
    covariance_reason_codes: tuple[str, ...]
    q3: Q3MagnitudeState
    gamma: float = 0.0
    scale_conditioning_status: str = "PENDING_CAUSAL_V3_REPLAY"
    range_preparation_status: str = "PENDING_V3_REPLAY"
    range_score_count: int = 0
    range_quantile: None = None

    @property
    def ordered_directional_quant_ids(self) -> tuple[str, ...]:
        """Backward-compatible name for the covariance quant ordering."""
        return self.ordered_quant_ids


@dataclass(frozen=True, slots=True, order=True)
class ComponentHash:
    horizon: str
    layer: str
    digest: str


@dataclass(frozen=True, slots=True)
class V2EvidenceState:
    state_schema_version: str
    state_version: str
    model_family: str
    symbol: str
    state_as_of: float
    training_start: float | None
    training_end: float | None
    target_spec_id: str | None
    target_data_schema_version: str | None
    target_source_spec_version: str | None
    v2a_method_version: str
    v2b_method_version: str
    v2c_method_version: str
    effective_n_method_version: str
    calibration_method_version: str
    covariance_method_version: str
    numerical_canonicalization_version: str
    evidence_manifest_hash: str
    component_hash_tuple: tuple[ComponentHash, ...]
    horizon_state_tuple: tuple[HorizonEvidenceState, ...]
    exclusion_count_tuple: tuple[tuple[str, int], ...]
    top_level_status: str
    creation_status: str
    reason_code_tuple: tuple[str, ...]
    state_hash: str
    state_id: str


def _float_token(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("non-finite float in V2D state")
    return (0.0 if value == 0.0 else value).hex()


def _same_float(left: float, right: float) -> bool:
    """Compare finite binary64 values under the canonical signed-zero policy."""

    return _float_token(left) == _float_token(right)


def _canonical(value: object, *, excluded: frozenset[str] = frozenset()) -> object:
    if isinstance(value, float):
        return {"$float64": _float_token(value)}
    if isinstance(value, tuple):
        return [_canonical(item, excluded=excluded) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {key: _canonical(item, excluded=excluded)
                for key, item in asdict(value).items() if key not in excluded}
    if isinstance(value, dict):
        return {str(key): _canonical(value[key], excluded=excluded)
                for key in sorted(value, key=str)}
    return value


def _digest(value: object, *, excluded: frozenset[str] = frozenset()) -> str:
    payload = json.dumps(_canonical(value, excluded=excluded), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


def v2d_state_hash(state: V2EvidenceState) -> str:
    """Recompute the canonical identity of an assembled V2D state."""

    if not isinstance(state, V2EvidenceState):
        raise TypeError("state must be a V2EvidenceState")
    return _digest(state, excluded=frozenset(("state_hash", "state_id")))


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_json_constant(token: str) -> object:
    raise ValueError(f"invalid JSON constant: {token}")


@lru_cache(maxsize=None)
def _dataclass_contract(value_type: type) -> tuple[tuple[str, object], ...]:
    hints = get_type_hints(value_type)
    return tuple((field.name, hints[field.name]) for field in fields(value_type))


def _decode_canonical(
        value: object, annotation: object, *, path: str,
        allow_q3_integer_default: bool = False) -> object:
    """Decode one exact V2D canonical value according to its frozen annotation."""

    if annotation is float:
        field_name = path.rsplit(".", 1)[-1]
        if (allow_q3_integer_default and type(value) is int and
                _Q3_INTEGER_FLOAT_DEFAULTS.get(field_name) == value):
            # V2B's frozen no-evidence Q3 record predates the float annotations
            # and intentionally hashes these exact zero/one values as JSON ints.
            return value
        if (not isinstance(value, Mapping) or set(value) != {"$float64"} or
                type(value["$float64"]) is not str):
            raise ValueError(f"{path} is not a canonical binary64 value")
        token = value["$float64"]
        try:
            decoded = float.fromhex(token)
        except (OverflowError, ValueError) as error:
            raise ValueError(f"{path} has an invalid binary64 token") from error
        if not math.isfinite(decoded) or token != _float_token(decoded):
            raise ValueError(f"{path} has a noncanonical binary64 token")
        return decoded

    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ValueError(f"{path} has an invalid scalar type")
        return value

    if annotation is type(None):
        if value is not None:
            raise ValueError(f"{path} must be null")
        return None

    origin = get_origin(annotation)
    if origin in (types.UnionType, Union):
        for option in get_args(annotation):
            try:
                return _decode_canonical(
                    value, option, path=path,
                    allow_q3_integer_default=allow_q3_integer_default,
                )
            except (TypeError, ValueError, OverflowError):
                continue
        raise ValueError(f"{path} does not match an allowed value type")

    if origin is tuple:
        if type(value) is not list:
            raise ValueError(f"{path} must be a canonical JSON array")
        item_types = get_args(annotation)
        if len(item_types) == 2 and item_types[1] is Ellipsis:
            return tuple(_decode_canonical(
                item, item_types[0], path=f"{path}[{index}]",
            ) for index, item in enumerate(value))
        if len(value) != len(item_types):
            raise ValueError(f"{path} has an invalid tuple length")
        return tuple(_decode_canonical(
            item, item_type, path=f"{path}[{index}]",
        ) for index, (item, item_type) in enumerate(zip(value, item_types)))

    if isinstance(annotation, type) and is_dataclass(annotation):
        contract = _dataclass_contract(annotation)
        expected = {name for name, _ in contract}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError(f"{path} has missing or unknown fields")
        legacy_q3_defaults = (
            annotation is Q3MagnitudeState
            and value.get("status") == "UNAVAILABLE"
            and value.get("reason_codes") == ["NO_EVIDENCE"]
            and all(
                type(value.get(name)) is int and value.get(name) == default
                for name, default in _Q3_INTEGER_FLOAT_DEFAULTS.items()
            )
        )
        return annotation(**{
            name: _decode_canonical(
                value[name], item_type, path=f"{path}.{name}",
                allow_q3_integer_default=(
                    legacy_q3_defaults and name in _Q3_INTEGER_FLOAT_DEFAULTS
                ),
            )
            for name, item_type in contract
        })

    raise TypeError(f"unsupported V2D contract annotation at {path}")


def _canonical_reason_tuple(value: tuple[str, ...]) -> bool:
    return (value == tuple(sorted(set(value))) and
            all(isinstance(item, str) and item for item in value))


def _sha256(value: str) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _square_matrix(value: tuple[tuple[object, ...], ...], size: int,
                   item_type: type) -> bool:
    return (len(value) == size and all(
        len(row) == size and all(type(item) is item_type for item in row)
        for row in value
    ))


def _symmetric_matrix(value: tuple[tuple[object, ...], ...], size: int,
                      item_type: type) -> bool:
    return (_square_matrix(value, size, item_type) and all(
        value[row][column] == value[column][row]
        for row in range(size) for column in range(size)
    ))


def _validate_q3_state(value: Q3MagnitudeState,
                       lineage: FamilyLineage | None,
                       dataset_hash: str | None) -> None:
    if value.status not in STATUSES or not _canonical_reason_tuple(value.reason_codes):
        raise ValueError("invalid Q3 status or reason codes")
    optional = (
        value.quant_id, value.formula_version, value.data_schema_version,
        value.source_spec_version, value.dataset_hash, value.calibration_alpha,
        value.calibration_beta, value.parameter_covariance_2x2,
        value.effective_n, value.magnitude_residual_variance,
        value.magnitude_mae, value.magnitude_rmse,
    )
    if value.quant_id is None:
        if value != Q3MagnitudeState(
                "UNAVAILABLE", ("Q3_EVIDENCE_UNAVAILABLE",)):
            raise ValueError("absent Q3 state is not canonical unavailable state")
        if any(item is not None for item in optional):
            raise ValueError("absent Q3 state contains partial values")
        if lineage is not None:
            raise ValueError("Q3 lineage is present without Q3 state")
        return
    if (value.quant_id != Q3 or lineage is None or
            (value.quant_id, value.formula_version, value.data_schema_version,
             value.source_spec_version) !=
            (lineage.quant_id, lineage.formula_version,
             lineage.data_schema_version, lineage.source_spec_version) or
            not _sha256(value.dataset_hash) or value.dataset_hash != dataset_hash):
        raise ValueError("Q3 state lineage is invalid")
    if any(item is None for item in optional[1:]):
        raise ValueError("Q3 state contains partial values")
    covariance = value.parameter_covariance_2x2
    if covariance is None or not _symmetric_matrix(covariance, 2, float):
        raise ValueError("Q3 parameter covariance is invalid")
    q3_default_values = tuple(
        getattr(value, name) for name in _Q3_INTEGER_FLOAT_DEFAULTS
    )
    if value.status == "UNAVAILABLE" or "NO_EVIDENCE" in value.reason_codes:
        if (
            value.status != "UNAVAILABLE"
            or value.reason_codes != ("NO_EVIDENCE",)
            or any(
                type(item) is not int or item != expected
                for item, expected in zip(
                    q3_default_values, _Q3_INTEGER_FLOAT_DEFAULTS.values()
                )
            )
            or covariance != ((0.0, 0.0), (0.0, 0.0))
        ):
            raise ValueError("no-evidence Q3 state is not canonical")
    elif any(type(item) is int for item in q3_default_values):
        raise ValueError("legacy Q3 integer defaults appear outside no-evidence state")


def _validate_horizon_state(
        value: HorizonEvidenceState,
        components: Mapping[str, str]) -> None:
    if (value.horizon not in HORIZON_SECONDS or
            value.horizon_seconds != HORIZON_SECONDS[value.horizon] or
            value.status not in STATUSES or value.covariance_status not in STATUSES or
            not _canonical_reason_tuple(value.reason_codes) or
            not _canonical_reason_tuple(value.covariance_reason_codes)):
        raise ValueError("invalid horizon identity, status, or reasons")
    if (not _same_float(value.gamma, 0.0) or
            value.scale_conditioning_status != "PENDING_CAUSAL_V3_REPLAY" or
            value.range_preparation_status != "PENDING_V3_REPLAY" or
            value.range_score_count != 0 or value.range_quantile is not None):
        raise ValueError("invalid frozen V2D replay or range fields")

    if not components:
        if (len(value.reason_codes) != 1 or
                value.reason_codes[0] not in _MISSING_HORIZON_REASONS or
                value != _missing(value.horizon, value.reason_codes[0])):
            raise ValueError("component-free horizon is not canonical unavailable state")
        return
    if set(components) != {"V2A", "V2B", "V2C"}:
        raise ValueError("horizon component manifest is incomplete")

    ordered_ids = value.ordered_quant_ids
    if (ordered_ids != tuple(q for q in DIRECTIONAL_FAMILIES if q in ordered_ids) or
            tuple(item.quant_id for item in value.directional_calibrations) != ordered_ids):
        raise ValueError("directional calibration order is invalid")

    lineage_ids = tuple(item.quant_id for item in value.family_lineage)
    if lineage_ids != tuple(q for q in (*DIRECTIONAL_FAMILIES, Q3)
                            if q in lineage_ids):
        raise ValueError("family lineage order is invalid")
    q3_lineage = next((item for item in value.family_lineage
                       if item.quant_id == Q3), None)
    expected_lineage_ids = ordered_ids + ((Q3,) if value.q3.quant_id is not None else ())
    if lineage_ids != expected_lineage_ids:
        raise ValueError("family lineage does not match compact horizon content")
    lineage_by_quant = {item.quant_id: item for item in value.family_lineage}
    if len(lineage_by_quant) != len(value.family_lineage):
        raise ValueError("family lineage contains duplicate quant IDs")

    dataset_hash = components["V2A"]
    for calibration in value.directional_calibrations:
        lineage = lineage_by_quant.get(calibration.quant_id)
        if (lineage is None or calibration.status not in STATUSES or
                not _canonical_reason_tuple(calibration.reason_codes) or
                not _sha256(calibration.dataset_hash) or
                calibration.dataset_hash != dataset_hash or
                (calibration.quant_id, calibration.formula_version,
                 calibration.data_schema_version, calibration.source_spec_version) !=
                (lineage.quant_id, lineage.formula_version,
                 lineage.data_schema_version, lineage.source_spec_version) or
                not _symmetric_matrix(
                    calibration.calibration_parameter_covariance_2x2, 2, float)):
            raise ValueError("directional calibration state is invalid")
        if (calibration.status == "UNAVAILABLE" or
                "NO_EVIDENCE" in calibration.reason_codes):
            if (
                calibration.status != "UNAVAILABLE"
                or calibration.reason_codes != ("NO_EVIDENCE",)
                or not _same_float(calibration.calibration_intercept, 0.0)
                or not _same_float(calibration.calibration_slope, 1.0)
                or calibration.calibration_parameter_covariance_2x2 !=
                ((0.0, 0.0), (0.0, 0.0))
                or not _same_float(calibration.effective_n, 0.0)
                or not _same_float(calibration.residual_variance, 0.0)
                or not _same_float(calibration.residual_standard_deviation, 0.0)
            ):
                raise ValueError(
                    "no-evidence directional calibration is not canonical")

    _validate_q3_state(value.q3, q3_lineage, dataset_hash)
    size = len(ordered_ids)
    if not _symmetric_matrix(value.pair_support_boolean_matrix, size, bool):
        raise ValueError("pair-support matrix is invalid")
    if value.stabilized_covariance_matrix is not None and not _symmetric_matrix(
            value.stabilized_covariance_matrix, size, float):
        raise ValueError("stabilized covariance matrix is invalid")
    if ((value.covariance_status == "UNAVAILABLE") !=
            (value.stabilized_covariance_matrix is None)):
        raise ValueError("covariance status and matrix availability disagree")
    if value.stabilized_covariance_matrix is None and value.dependence_modeled:
        raise ValueError("dependence cannot be modeled without covariance")
    if value.covariance_status == "MATURE" and (
            not value.dependence_modeled or
            not all(item for row in value.pair_support_boolean_matrix for item in row)):
        raise ValueError("mature covariance lacks complete pair support")

    usable = tuple(item for item in value.directional_calibrations
                   if item.status != "UNAVAILABLE")
    covariance_usable = (value.covariance_status != "UNAVAILABLE" and
                         value.stabilized_covariance_matrix is not None)
    expected_status = (
        "UNAVAILABLE" if not usable or not covariance_usable else
        "MATURE" if (
            all(item.status == "MATURE" for item in value.directional_calibrations) and
            value.covariance_status == "MATURE" and
            (value.q3.quant_id is None or value.q3.status == "MATURE") and
            "HETEROGENEOUS_COMPONENT_CUTOFF" not in value.reason_codes
        ) else "PROVISIONAL"
    )
    if value.status != expected_status:
        raise ValueError("horizon status is not derived from compact evidence")

    expected_reasons = {
        reason for calibration in value.directional_calibrations
        for reason in calibration.reason_codes
    }
    expected_reasons.update(value.covariance_reason_codes)
    expected_reasons.update(value.q3.reason_codes)
    if usable and not covariance_usable:
        expected_reasons.add("COVARIANCE_UNAVAILABLE")
    if "HETEROGENEOUS_COMPONENT_CUTOFF" in value.reason_codes:
        expected_reasons.add("HETEROGENEOUS_COMPONENT_CUTOFF")
    if value.reason_codes != tuple(sorted(expected_reasons)):
        raise ValueError("horizon reason codes are not derived from compact evidence")


def _validate_v2_evidence_state(state: V2EvidenceState) -> None:
    if type(state) is not V2EvidenceState:
        raise ValueError("state must be an exact V2EvidenceState")
    structurally_decoded = _decode_canonical(
        _canonical(state), V2EvidenceState, path="state")
    if structurally_decoded != state:
        raise ValueError("state contains noncanonical runtime values")

    if ((state.state_schema_version, state.state_version, state.model_family,
         state.symbol) != (STATE_SCHEMA_VERSION, STATE_VERSION, MODEL_FAMILY, SYMBOL) or
            (state.v2a_method_version, state.v2b_method_version,
             state.v2c_method_version) !=
            (V2A_METHOD_VERSION, V2B_METHOD_VERSION, V2C_METHOD_VERSION) or
            (state.effective_n_method_version, state.calibration_method_version,
             state.covariance_method_version,
             state.numerical_canonicalization_version) !=
            (EFFECTIVE_N_METHOD_VERSION, CALIBRATION_METHOD_VERSION,
             COVARIANCE_METHOD_VERSION, NUMERICAL_CANONICALIZATION_VERSION)):
        raise ValueError("V2D state version lineage is invalid")
    if ((state.training_start is None) != (state.training_end is None) or
            state.training_start is not None and not (
                state.training_start <= state.training_end <= state.state_as_of)):
        raise ValueError("V2D training boundaries are invalid")
    target_lineage = (state.target_spec_id, state.target_data_schema_version,
                      state.target_source_spec_version)
    if any(item is None for item in target_lineage) and any(
            item is not None for item in target_lineage):
        raise ValueError("V2D target lineage is partial")
    if state.top_level_status not in STATUSES or state.creation_status not in {
            "VALID", "INVALID"}:
        raise ValueError("V2D aggregate status is invalid")
    if (not _sha256(state.evidence_manifest_hash) or
            not _sha256(state.state_hash)):
        raise ValueError("V2D state contains an invalid hash")

    components = state.component_hash_tuple
    if components != tuple(sorted(set(components))):
        raise ValueError("V2D component hashes are not canonical")
    by_horizon: dict[str, dict[str, str]] = {}
    component_keys: set[tuple[str, str]] = set()
    for component in components:
        if (component.horizon not in HORIZONS or
                component.layer not in {"V2A", "V2B", "V2C"} or
                not _sha256(component.digest)):
            raise ValueError("V2D component hash is invalid")
        key = (component.horizon, component.layer)
        if key in component_keys:
            raise ValueError("V2D component horizon/layer identity is duplicated")
        component_keys.add(key)
        by_horizon.setdefault(component.horizon, {})[component.layer] = component.digest
    if any(set(items) != {"V2A", "V2B", "V2C"}
           for items in by_horizon.values()):
        raise ValueError("V2D component hash groups are incomplete")
    expected_manifest = _digest(tuple(
        (item.horizon, item.layer, item.digest) for item in components))
    if state.evidence_manifest_hash != expected_manifest:
        raise ValueError("V2D evidence manifest hash mismatch")

    if tuple(item.horizon for item in state.horizon_state_tuple) != HORIZONS:
        raise ValueError("V2D state does not contain six canonical horizons")
    for horizon_state in state.horizon_state_tuple:
        _validate_horizon_state(
            horizon_state, by_horizon.get(horizon_state.horizon, {}))

    if (state.exclusion_count_tuple != tuple(sorted(state.exclusion_count_tuple)) or
            len({reason for reason, _ in state.exclusion_count_tuple}) !=
            len(state.exclusion_count_tuple) or
            any(not reason or count <= 0
                for reason, count in state.exclusion_count_tuple)):
        raise ValueError("V2D exclusion counts are invalid")
    expected_top = (
        "MATURE" if all(item.status == "MATURE"
                        for item in state.horizon_state_tuple) else
        "UNAVAILABLE" if all(item.status == "UNAVAILABLE"
                             for item in state.horizon_state_tuple) else
        "PROVISIONAL"
    )
    expected_reasons = tuple(sorted({
        reason for item in state.horizon_state_tuple for reason in item.reason_codes
    }))
    if (state.top_level_status != expected_top or
            state.reason_code_tuple != expected_reasons or
            not _canonical_reason_tuple(state.reason_code_tuple)):
        raise ValueError("V2D aggregate status or reasons are invalid")
    if not components and (target_lineage != (None, None, None) or
                           state.training_start is not None or
                           state.exclusion_count_tuple):
        raise ValueError("component-free V2D state contains aggregate evidence metadata")
    if components and any(item is None for item in target_lineage):
        raise ValueError("component-bearing V2D state lacks target lineage")
    if state.creation_status == "INVALID" and components:
        raise ValueError("invalid V2D creation cannot contain accepted components")

    digest = v2d_state_hash(state)
    if state.state_hash != digest or state.state_id != _STATE_ID_PREFIX + digest:
        raise ValueError("V2D state mathematical identity mismatch")


def serialize_v2_evidence_state(state: V2EvidenceState) -> str:
    """Return the exact canonical JSON representation of one V2 evidence state."""

    try:
        _validate_v2_evidence_state(state)
        canonical = _canonical(state)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("invalid V2 evidence state") from error
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def deserialize_v2_evidence_state(
        payload: str | Mapping[str, object]) -> V2EvidenceState:
    """Strictly reconstruct and verify one canonical V2 evidence state."""

    try:
        canonical = (json.loads(
            payload, object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        ) if isinstance(payload, str) else payload)
        if not isinstance(canonical, Mapping):
            raise ValueError("V2 evidence state payload must be an object")
        state = _decode_canonical(
            canonical, V2EvidenceState, path="state")
        if not isinstance(state, V2EvidenceState):
            raise ValueError("V2 evidence state payload is invalid")
        _validate_v2_evidence_state(state)
        return state
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError,
            OverflowError) as error:
        raise ValueError("V2 evidence state payload is invalid") from error


def _all_finite(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, (tuple, list)):
        return all(_all_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_all_finite(item) for item in value.values())
    if hasattr(value, "__dataclass_fields__"):
        return _all_finite(asdict(value))
    return True


def _reasons(*groups: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for group in groups for reason in group}))


def _missing(horizon: str, reason: str = "HORIZON_EVIDENCE_UNAVAILABLE") -> HorizonEvidenceState:
    return HorizonEvidenceState(
        horizon, HORIZON_SECONDS[horizon], "UNAVAILABLE", (reason,), (), (), (), (), None,
        False, "UNAVAILABLE", (("COVARIANCE_UNAVAILABLE",) if reason != "COVARIANCE_UNAVAILABLE" else (reason,)),
        Q3MagnitudeState("UNAVAILABLE", ("Q3_EVIDENCE_UNAVAILABLE",)),
    )


def _directional(item: DirectionalCalibration) -> DirectionalCalibrationState:
    return DirectionalCalibrationState(
        item.quant_id, item.formula_version, item.data_schema_version,
        item.source_spec_version, item.dataset_hash, item.calibration_intercept,
        item.calibration_slope, item.calibration_parameter_covariance_2x2,
        item.effective_n, item.residual_variance, item.residual_standard_deviation,
        item.status, tuple(sorted(item.reason_codes)),
    )


def _q3(item: Q3MagnitudeCalibration | None) -> Q3MagnitudeState:
    if item is None:
        return Q3MagnitudeState("UNAVAILABLE", ("Q3_EVIDENCE_UNAVAILABLE",))
    return Q3MagnitudeState(
        item.status, tuple(sorted(item.reason_codes)), item.quant_id,
        item.formula_version, item.data_schema_version,
        item.source_spec_version, item.dataset_hash,
        item.calibration_alpha, item.calibration_beta,
        item.parameter_covariance_2x2, item.effective_n,
        item.magnitude_residual_variance, item.magnitude_mae, item.magnitude_rmse,
    )


def _assemble_horizon(dataset: V2ADataset, calibration: V2BCalibration,
                      covariance: V2CCovariance,
                      heterogeneous: bool) -> tuple[HorizonEvidenceState, bool]:
    horizon = dataset.horizon
    subsets = tuple(dataset.directional_subsets)
    expected_ids = tuple(item.quant_id for item in subsets)
    expected_formulas = tuple(item.formula_version for item in subsets)
    components = (dataset, calibration, covariance)
    if not _all_finite(components):
        return _missing(horizon, "NONFINITE_COMPONENT_STATE"), False
    lineage_map = {item.quant_id: item for item in dataset.family_lineage}
    expected_lineage = tuple(lineage_map.get(quant_id) for quant_id in expected_ids)
    q3_lineage = lineage_map.get(Q3)
    b_items = tuple(item for item in calibration.directional if item.horizon == horizon)
    b_map = {(item.quant_id, item.formula_version,
              item.data_schema_version, item.source_spec_version,
              item.dataset_hash): item for item in b_items}
    ordered_b = tuple(b_map.get((
        quant_id, formula, lineage.data_schema_version,
        lineage.source_spec_version, dataset.dataset_hash,
    )) if lineage is not None else None
        for quant_id, formula, lineage in zip(
            expected_ids, expected_formulas, expected_lineage))
    q3_subset = dataset.q3_subset
    q3_items = tuple(item for item in calibration.q3_magnitude if item.horizon == horizon)
    q3_item = next((item for item in q3_items if q3_subset and
                    q3_lineage is not None and
                    (item.quant_id, item.formula_version,
                     item.data_schema_version, item.source_spec_version,
                     item.dataset_hash) ==
                    (q3_subset.quant_id, q3_subset.formula_version,
                     q3_lineage.data_schema_version,
                     q3_lineage.source_spec_version,
                     dataset.dataset_hash)), None)
    calibration_hash = v2b_component_hash(calibration, horizon)
    manifest = dict(calibration.input_manifest)
    canonical_family_lineage = tuple(
        lineage_map[q] for q in (*DIRECTIONAL_FAMILIES, Q3)
        if q in lineage_map
    )
    integrity = (
        dataset.symbol == SYMBOL and dataset.method_version == V2A_METHOD_VERSION and
        dataset.dataset_hash == v2a_dataset_hash(dataset) and
        calibration.formula_version == V2B_METHOD_VERSION and
        len(manifest) == len(calibration.input_manifest) and
        manifest.get(horizon) == dataset.dataset_hash and
        covariance.method_version == V2C_METHOD_VERSION and covariance.horizon == horizon and
        covariance.dataset_hash == dataset.dataset_hash and
        covariance.v2b_component_hash == calibration_hash and
        all(item.horizon == horizon for item in b_items + q3_items) and
        len(b_map) == len(b_items) and
        dataset.family_lineage == canonical_family_lineage and
        all(item is not None for item in expected_lineage) and
        covariance.ordered_family_lineage == expected_lineage and
        expected_ids == tuple(q for q in DIRECTIONAL_FAMILIES if q in expected_ids) and
        len(b_items) == len(expected_ids) and all(ordered_b) and
        covariance.ordered_quant_ids == expected_ids and
        covariance.ordered_formula_versions == expected_formulas and
        isinstance(covariance.pair_support_boolean_matrix, tuple) and
        len(covariance.pair_support_boolean_matrix) == len(covariance.ordered_quant_ids) and
        all(isinstance(row, tuple) and
            len(row) == len(covariance.ordered_quant_ids) and
            all(isinstance(value, bool) for value in row)
            for row in covariance.pair_support_boolean_matrix) and
        len(covariance.stabilized_covariance_matrix) == len(covariance.ordered_quant_ids) and
        all(len(row) == len(covariance.ordered_quant_ids)
            for row in covariance.stabilized_covariance_matrix) and
        Q3 not in expected_ids and Q3 not in covariance.ordered_quant_ids and
        ((q3_subset is None and not q3_items) or
         (q3_subset is not None and len(q3_items) == 1 and q3_item is not None))
    )
    if not integrity:
        return _missing(horizon, "CROSS_LAYER_INTEGRITY_FAILURE"), False

    directional = tuple(_directional(item) for item in ordered_b if item is not None)
    usable = tuple(item for item in directional if item.status != "UNAVAILABLE")
    q3_state = _q3(q3_item)
    covariance_usable = (covariance.status != "UNAVAILABLE" and
                         len(covariance.stabilized_covariance_matrix) == len(directional) and
                         all(len(row) == len(directional)
                             for row in covariance.stabilized_covariance_matrix))
    reasons = set(covariance.reason_codes)
    reasons.update(reason for item in directional for reason in item.reason_codes)
    reasons.update(q3_state.reason_codes)
    if heterogeneous:
        reasons.add("HETEROGENEOUS_COMPONENT_CUTOFF")
    if not usable:
        status = "UNAVAILABLE"
    elif not covariance_usable:
        status = "UNAVAILABLE"
        reasons.add("COVARIANCE_UNAVAILABLE")
    elif (all(item.status == "MATURE" for item in directional) and
          covariance.status == "MATURE" and
          (q3_subset is None or q3_state.status == "MATURE") and not heterogeneous):
        status = "MATURE"
    else:
        status = "PROVISIONAL"
    return HorizonEvidenceState(
        horizon, HORIZON_SECONDS[horizon], status, tuple(sorted(reasons)), directional,
        dataset.family_lineage,
        covariance.ordered_quant_ids,
        covariance.pair_support_boolean_matrix,
        covariance.stabilized_covariance_matrix if covariance_usable else None,
        covariance.dependence_modeled if covariance_usable else False,
        covariance.status, tuple(sorted(covariance.reason_codes)), q3_state,
    ), True


def build_v2d_evidence_state(*, state_as_of: float,
                             datasets: Iterable[V2ADataset],
                             calibrations: Iterable[V2BCalibration],
                             covariances: Iterable[V2CCovariance]) -> V2EvidenceState:
    """Validate and assemble immutable A/B/C results without reads or writes."""
    if not isinstance(state_as_of, (int, float)) or isinstance(state_as_of, bool) or not math.isfinite(state_as_of):
        raise ValueError("state_as_of must be a finite binary64 value")
    ds_items = tuple(datasets)
    cal_items = tuple(calibrations)
    cov_items = tuple(covariances)
    ds_by_h = {item.horizon: item for item in ds_items}
    cov_by_h = {item.horizon: item for item in cov_items}
    duplicate_horizons = (len(ds_by_h) != len(ds_items) or len(cov_by_h) != len(cov_items))
    invalid_calibration_manifests = set()
    for calibration in cal_items:
        entries = tuple(calibration.input_manifest)
        manifest = dict(entries)
        expected = tuple(
            (horizon, ds_by_h[horizon].dataset_hash)
            for horizon in HORIZONS
            if horizon in manifest and horizon in ds_by_h
        )
        if len(manifest) != len(entries) or entries != expected:
            invalid_calibration_manifests.add(id(calibration))
    horizon_states = []
    hashes: list[ComponentHash] = []
    accepted_datasets: list[V2ADataset] = []
    accepted_indexes: list[int] = []
    for horizon in HORIZONS:
        dataset = ds_by_h.get(horizon)
        covariance = cov_by_h.get(horizon)
        matching_calibrations = tuple(cal for cal in cal_items if
                                      any(item.horizon == horizon for item in cal.directional) or
                                      any(item.horizon == horizon for item in cal.q3_magnitude))
        if dataset is None and covariance is None and not matching_calibrations:
            horizon_states.append(_missing(horizon)); continue
        if dataset is None or covariance is None or len(matching_calibrations) != 1:
            horizon_states.append(_missing(horizon, "CROSS_LAYER_INTEGRITY_FAILURE")); continue
        if id(matching_calibrations[0]) in invalid_calibration_manifests:
            horizon_states.append(_missing(horizon, "CROSS_LAYER_INTEGRITY_FAILURE")); continue
        if dataset.state_as_of > state_as_of:
            horizon_states.append(_missing(horizon, "CROSS_LAYER_INTEGRITY_FAILURE")); continue
        if duplicate_horizons:
            horizon_states.append(_missing(horizon, "CROSS_LAYER_INTEGRITY_FAILURE")); continue
        calibration = matching_calibrations[0]
        state, accepted = _assemble_horizon(dataset, calibration, covariance, False)
        horizon_states.append(state)
        if accepted:
            accepted_datasets.append(dataset)
            accepted_indexes.append(len(horizon_states) - 1)
            hashes.extend((
                ComponentHash(horizon, "V2A", dataset.dataset_hash),
                ComponentHash(horizon, "V2B", v2b_component_hash(
                    calibration, horizon)),
                ComponentHash(horizon, "V2C", _digest(covariance)),
            ))
    accepted_identities = {
        (item.target_spec_id, item.target_data_schema_version,
         item.target_source_spec_version) for item in accepted_datasets
    }
    if len(accepted_identities) > 1:
        for index in accepted_indexes:
            horizon_states[index] = _missing(
                horizon_states[index].horizon, "CROSS_LAYER_INTEGRITY_FAILURE")
        accepted_datasets.clear()
        accepted_indexes.clear()
        hashes.clear()
    heterogeneous = len({item.state_as_of for item in accepted_datasets}) > 1
    if heterogeneous:
        for index in accepted_indexes:
            state = horizon_states[index]
            horizon_states[index] = replace(
                state,
                status="PROVISIONAL" if state.status == "MATURE" else state.status,
                reason_codes=_reasons(state.reason_codes,
                                      ("HETEROGENEOUS_COMPONENT_CUTOFF",)),
            )
    horizon_tuple = tuple(horizon_states)
    component_tuple = tuple(sorted(set(hashes)))
    manifest = _digest(tuple((item.horizon, item.layer, item.digest) for item in component_tuple))
    starts = [item.training_start for item in accepted_datasets
              if item.training_start is not None]
    ends = [item.training_end for item in accepted_datasets
            if item.training_end is not None]
    identities = {(item.target_spec_id, item.target_data_schema_version,
                   item.target_source_spec_version) for item in accepted_datasets}
    identity = next(iter(identities)) if len(identities) == 1 else (None, None, None)
    exclusion: dict[str, int] = {}
    for item in accepted_datasets:
        for count in item.exclusions:
            exclusion[count.reason_code] = exclusion.get(count.reason_code, 0) + count.count
    statuses = tuple(item.status for item in horizon_tuple)
    top = ("MATURE" if all(item == "MATURE" for item in statuses) else
           "UNAVAILABLE" if all(item == "UNAVAILABLE" for item in statuses) else "PROVISIONAL")
    top_reasons = set(reason for item in horizon_tuple for reason in item.reason_codes)
    if heterogeneous:
        top_reasons.add("HETEROGENEOUS_COMPONENT_CUTOFF")
    creation = "INVALID" if duplicate_horizons else "VALID"
    shell = V2EvidenceState(
        STATE_SCHEMA_VERSION, STATE_VERSION, MODEL_FAMILY, SYMBOL, float(state_as_of),
        min(starts) if starts else None, max(ends) if ends else None, *identity,
        V2A_METHOD_VERSION, V2B_METHOD_VERSION, V2C_METHOD_VERSION,
        EFFECTIVE_N_METHOD_VERSION, CALIBRATION_METHOD_VERSION,
        COVARIANCE_METHOD_VERSION, NUMERICAL_CANONICALIZATION_VERSION,
        manifest, component_tuple, horizon_tuple, tuple(sorted(exclusion.items())),
        top, creation, tuple(sorted(top_reasons)), "", "",
    )
    state_hash = v2d_state_hash(shell)
    result = replace(shell, state_hash=state_hash, state_id="v9v2:" + state_hash)
    if not _all_finite(result):
        raise ValueError("non-finite float in assembled V2D state")
    return result


# Concise construction alias for offline rebuild jobs.
assemble_v2_evidence_state = build_v2d_evidence_state
