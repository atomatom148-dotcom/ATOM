"""Immutable assembly boundary for the complete V9-V2 evidence state.

V2D deliberately performs no estimation and has no persistence or live-path
integration.  It validates and compacts caller-supplied, frozen V2A/B/C
results into a deterministic six-horizon value object.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from typing import Iterable

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
