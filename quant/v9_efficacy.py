"""Read-only chronological V9 efficacy evaluation.

This module is deliberately disconnected from live synthesis and persistence.
It evaluates already-proven forecasts on a forward holdout without changing
weights, thresholds, evidence, or production decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
import math
import re
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from quant.evidence import (
    DATA_SCHEMA_VERSION as LIVE_DATA_SCHEMA_VERSION,
    SOURCE_SPEC_VERSION as LIVE_SOURCE_SPEC_VERSION,
)
from quant.historical_replay import (
    ALLOWED_FORMULA_VERSIONS, DATA_SCHEMA_VERSION as REPLAY_DATA_SCHEMA_VERSION,
    SOURCE_SPEC_ROUND_LOTS, SOURCE_SPEC_SHARES,
)
from quant.q10_options_vol import FORMULA_VERSION as Q10_FORMULA_VERSION
from quant.v9_v1_contract import (
    CONTRACT_VERSION as V1_CONTRACT_VERSION,
    HORIZONS, HORIZON_SECONDS, SYMBOL,
)
from quant.v9_v2d_evidence_state import (
    CALIBRATION_METHOD_VERSION, COVARIANCE_METHOD_VERSION,
    EFFECTIVE_N_METHOD_VERSION, NUMERICAL_CANONICALIZATION_VERSION,
    STATE_VERSION as V2_STATE_VERSION, V2A_METHOD_VERSION,
    V2B_METHOD_VERSION, V2C_METHOD_VERSION,
)
from quant.v9_v3_synthesis import (
    CANONICAL_FAMILIES, CONTRACT_VERSION as V3_CONTRACT_VERSION,
    MODEL_VERSION as V3_MODEL_VERSION,
)
from quant.v9_v4a_evidence import (
    COMMIT_PROOF_METHOD, CONTRACT_VERSION as V4_CONTRACT_VERSION,
    EVIDENCE_ORIGINS, EVIDENCE_VERSION as V4_EVIDENCE_VERSION,
    MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS, TARGET_TIMING_METHOD_VERSION,
    REPLAY_METHOD_VERSION as V4_REPLAY_METHOD_VERSION, V4AWriter,
    canonical_sha256, canonical_target_identity,
    deserialize_forecast_record, deserialize_outcome_record,
)
from quant.v9_v4b_accuracy import (
    MODEL_VERSION as V4_MODEL_VERSION, effective_n,
    inverse_regularized_incomplete_beta,
)
from quant.v9_v4c_predictive import hac, holm

EFFICACY_VERSION = "ATOM_TRUE_V9_CHRONOLOGICAL_EFFICACY_3"
METHOD = "PAIRED_NONOVERLAP_DIRECTIONAL_HAC_HOLM_005_3"
SIGNIFICANCE_ALPHA = 0.05
MIN_SIGNIFICANCE_RAW_N = 500
MIN_SIGNIFICANCE_EFFECTIVE_N = 400.0
VERIFIED_TARGET_TIMING = "VERIFIED"
FILTERED_CANDIDATE_REASON = "IMMUTABLE_FILTERED_CANDIDATE_EVIDENCE_UNAVAILABLE"
MIXED_LINEAGE_REASON = "MIXED_IMMUTABLE_LINEAGE"
TARGET_SPEC_ID = "COIN_MIDPOINT_LOG_RETURN_BPS_1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EASTERN = ZoneInfo("America/New_York")
_ALLOWED_SOURCE_LINEAGE = frozenset((
    ("PRODUCTION", LIVE_DATA_SCHEMA_VERSION, LIVE_SOURCE_SPEC_VERSION),
    ("CAUSAL_REPLAY", REPLAY_DATA_SCHEMA_VERSION, SOURCE_SPEC_ROUND_LOTS),
    ("CAUSAL_REPLAY", REPLAY_DATA_SCHEMA_VERSION, SOURCE_SPEC_SHARES),
))
_ALLOWED_TARGET_TIMING_METHODS = frozenset((
    "ATOM_TRUE_V9_V4_TARGET_FIRST_AT_OR_AFTER_1",
    TARGET_TIMING_METHOD_VERSION,
))
_EXPECTED_V2_METHOD_LINEAGE = (
    V2A_METHOD_VERSION, V2B_METHOD_VERSION, V2C_METHOD_VERSION,
    EFFECTIVE_N_METHOD_VERSION, CALIBRATION_METHOD_VERSION,
    COVARIANCE_METHOD_VERSION, NUMERICAL_CANONICALIZATION_VERSION,
)
_CANONICAL_FORMULA_VERSIONS = {
    **ALLOWED_FORMULA_VERSIONS,
    "q10_options_vol": Q10_FORMULA_VERSION,
}


@dataclass(frozen=True, slots=True)
class EfficacyObservation:
    forecast_record_id: str
    forecast_record_hash: str
    v9_model_version: str
    horizon: str
    family: str
    family_weight: float
    cutoff_at: datetime
    target_endpoint: datetime
    forecast_available_at: datetime
    forecast_proof_method: str
    v3_forecast_record_id: str
    v3_forecast_record_hash: str
    v3_model_version: str
    v3_forecast_available_at: datetime
    v3_forecast_proof_method: str
    outcome_record_id: str
    outcome_record_hash: str
    target_identity: str
    target_timing_status: str
    evidence_available_at: datetime
    v9_bps: float
    v3_bps: float
    actual_bps: float
    proof_eligible: bool
    forecast_record_json: str | Mapping[str, object]
    forecast_commit_proof: tuple[object, ...]
    outcome_record_json: str | Mapping[str, object]
    outcome_created_at: datetime


@dataclass(frozen=True, slots=True)
class EfficacySlice:
    horizon: str
    family: str
    holdout_n: int
    directional_effective_n: float
    v9_directional_effective_n: float
    v3_directional_effective_n: float
    mean_family_weight: float | None
    v9_directional_accuracy: float | None
    v3_directional_accuracy: float | None
    paired_improvement: float | None
    v9_lower_95: float | None
    v3_lower_95: float | None
    hac_status: str
    hac_z: float | None
    p_upper: float
    holm_rank: int | None
    holm_threshold: float | None
    significant_improvement: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EfficacyReport:
    report_id: str
    report_hash: str
    version: str
    method: str
    holdout_start: datetime
    evaluation_as_of: datetime
    calibration_n: int
    holdout_n: int
    excluded_n: int
    evidence_digest: str
    slices: tuple[EfficacySlice, ...]


def _aware(value: object) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        return value.utcoffset() is not None
    except (OverflowError, TypeError, ValueError):
        return False


def _finite_real(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _verified_records(row: EfficacyObservation):
    try:
        forecast = deserialize_forecast_record(
            row.forecast_record_json,
            expected_hash=row.forecast_record_hash,
        )
        forecast = V4AWriter._apply_commit_proof(
            forecast, row.forecast_commit_proof,
        )
        outcome = deserialize_outcome_record(
            row.outcome_record_json,
            expected_hash=row.outcome_record_hash,
        )
    except (TypeError, ValueError, KeyError):
        return None
    return forecast, outcome


def _same_real(left: object, right: object) -> bool:
    return _finite_real(left) and _finite_real(right) and float(left) == float(right)


def _expected_cohort_hash(forecast) -> str:
    payload = {
        "symbol": forecast.symbol,
        "horizon": forecast.horizon,
        "v3_contract_version": V3_CONTRACT_VERSION,
        "v3_model_version": V3_MODEL_VERSION,
        "compatible_family_formula_map": tuple(
            (family, _CANONICAL_FORMULA_VERSIONS[family])
            for family in CANONICAL_FAMILIES
        ),
        "v2_method_lineage": _EXPECTED_V2_METHOD_LINEAGE,
        "target_spec_id": forecast.target_spec_id,
        "data_schema_version": forecast.data_schema_version,
        "source_spec_version": forecast.source_spec_version,
        "replay_method_version": V4_REPLAY_METHOD_VERSION,
    }
    return canonical_sha256(payload)


def _rth_target(cutoff: datetime, target: datetime) -> bool:
    local_cutoff = cutoff.astimezone(_EASTERN)
    local_target = target.astimezone(_EASTERN)
    return (
        local_cutoff.date() == local_target.date()
        and local_cutoff.weekday() < 5
        and (local_cutoff.hour, local_cutoff.minute, local_cutoff.second) >= (
            9, 30, 0
        )
        and (local_target.hour, local_target.minute, local_target.second) < (
            16, 0, 0
        )
    )


def _directional_win(predicted: float, actual: float) -> float | None:
    if actual == 0:
        return None
    return float(
        (predicted > 0 and actual > 0)
        or (predicted < 0 and actual < 0)
    )


def _lower_95(wins: float, effective_count: float) -> float | None:
    if effective_count <= 0:
        return None
    effective_wins = effective_count * wins
    return inverse_regularized_incomplete_beta(
        effective_wins + 0.5,
        effective_count - effective_wins + 0.5,
        0.025,
    )


def _valid_verified(row: EfficacyObservation) -> bool:
    verified = _verified_records(row)
    if verified is None:
        return False
    forecast, outcome = verified
    timestamps = (
        row.cutoff_at, row.target_endpoint, row.forecast_available_at,
        row.v3_forecast_available_at, row.evidence_available_at,
        row.outcome_created_at,
    )
    expected_target = (
        row.cutoff_at + timedelta(seconds=HORIZON_SECONDS[row.horizon])
        if row.horizon in HORIZON_SECONDS and _aware(row.cutoff_at)
        else None
    )
    proof = row.forecast_commit_proof
    weights = forecast.family_weights
    used = forecast.used_quant_ids
    family_indexes = tuple(
        index for index, quant_id in enumerate(used)
        if quant_id == row.family
    )
    derived_delay = (
        (outcome.endpoint_observation_at - outcome.target_endpoint).total_seconds()
        if _aware(outcome.endpoint_observation_at) and _aware(outcome.target_endpoint)
        else math.inf
    )
    return (
        row.proof_eligible is True
        and row.horizon in HORIZONS
        and row.family in CANONICAL_FAMILIES
        and bool(row.forecast_record_id)
        and bool(row.v3_forecast_record_id)
        and bool(row.outcome_record_id)
        and bool(row.target_identity)
        and row.v9_model_version == V4_MODEL_VERSION
        and row.v3_model_version == V3_MODEL_VERSION
        and _sha256(row.forecast_record_hash)
        and _sha256(row.v3_forecast_record_hash)
        and _sha256(row.outcome_record_hash)
        and row.forecast_proof_method == COMMIT_PROOF_METHOD
        and row.v3_forecast_proof_method == COMMIT_PROOF_METHOD
        and row.target_timing_status == VERIFIED_TARGET_TIMING
        and all(_aware(value) for value in timestamps)
        and expected_target == row.target_endpoint
        and _rth_target(row.cutoff_at, row.target_endpoint)
        and row.cutoff_at <= row.forecast_available_at < row.target_endpoint
        and row.v3_forecast_available_at == row.forecast_available_at
        and row.target_endpoint <= row.evidence_available_at
        and all(_finite_real(value) for value in (
            row.family_weight, row.v9_bps, row.v3_bps, row.actual_bps
        ))
        and 0 <= row.family_weight <= 1
        and forecast.forecast_record_id == row.forecast_record_id
        and forecast.forecast_record_hash == row.forecast_record_hash
        and forecast.contract_version == V4_CONTRACT_VERSION
        and forecast.evidence_version == V4_EVIDENCE_VERSION
        and forecast.evidence_origin in EVIDENCE_ORIGINS
        and (
            forecast.evidence_origin,
            forecast.data_schema_version,
            forecast.source_spec_version,
        ) in _ALLOWED_SOURCE_LINEAGE
        and forecast.symbol == SYMBOL
        and isinstance(forecast.cycle_id, str)
        and bool(forecast.cycle_id)
        and forecast.cutoff_at == row.cutoff_at
        and forecast.target_endpoint == row.target_endpoint
        and forecast.horizon == row.horizon
        and forecast.horizon_seconds == HORIZON_SECONDS[row.horizon]
        and forecast.v1_contract_version == V1_CONTRACT_VERSION
        and _sha256(forecast.v1_input_hash)
        and forecast.v2_state_version == V2_STATE_VERSION
        and _sha256(forecast.v2_state_hash)
        and forecast.v2_state_id == "v9v2:" + forecast.v2_state_hash
        and _finite_real(forecast.v2_state_as_of)
        and forecast.v2_state_as_of <= row.cutoff_at.timestamp()
        and forecast.v3_contract_version == V3_CONTRACT_VERSION
        and forecast.v3_model_version == V3_MODEL_VERSION
        and forecast.target_spec_id == TARGET_SPEC_ID
        and _sha256(forecast.cohort_hash)
        and forecast.cohort_id == "v9v4cohort:" + forecast.cohort_hash
        and forecast.cohort_hash == _expected_cohort_hash(forecast)
        and forecast.persistence_proof_eligible is True
        and forecast.persisted_at == row.forecast_available_at
        and len(proof) == 6
        and proof[0] == row.forecast_record_id
        and proof[1] == row.forecast_record_hash
        and proof[2] == row.forecast_available_at
        and proof[3] == row.target_endpoint
        and proof[4] is True
        and proof[5] == COMMIT_PROOF_METHOD
        and len(used) == len(weights) > 0
        and len(set(used)) == len(used)
        and all(quant_id in CANONICAL_FAMILIES for quant_id in used)
        and used == tuple(
            quant_id for quant_id in CANONICAL_FAMILIES
            if quant_id in used
        )
        and all(_finite_real(weight) and 0 <= weight <= 1 for weight in weights)
        and math.isclose(math.fsum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12)
        and len(family_indexes) == 1
        and _same_real(weights[family_indexes[0]], row.family_weight)
        and forecast.status in {"MATURE", "PROVISIONAL"}
        and _finite_real(forecast.predictive_variance_bps2)
        and forecast.predictive_variance_bps2 >= 0
        and (
            forecast.q3_diagnostic_magnitude_bps is None
            or (
                _finite_real(forecast.q3_diagnostic_magnitude_bps)
                and forecast.q3_diagnostic_magnitude_bps >= 0
            )
        )
        and isinstance(forecast.directional_input_count, int)
        and not isinstance(forecast.directional_input_count, bool)
        and (
            (
                len(used) == forecast.directional_input_count == 1
                and forecast.covariance_mode ==
                "SINGLE_FAMILY_RESIDUAL_VARIANCE"
            )
            or (
                len(used) == forecast.directional_input_count > 1
                and forecast.covariance_mode == "FULL_DEPENDENCE"
            )
            or (
                1 <= len(used) < forecast.directional_input_count
                <= len(CANONICAL_FAMILIES)
                and forecast.covariance_mode == "PRINCIPAL_SUBSET"
            )
        )
        and forecast.q3_used is False
        and _same_real(forecast.gamma, 0.0)
        and _same_real(forecast.phi, 1.0)
        and _same_real(forecast.expected_return_bps, row.v9_bps)
        and row.v3_forecast_record_id == row.forecast_record_id
        and row.v3_forecast_record_hash == row.forecast_record_hash
        and row.v3_forecast_available_at == row.forecast_available_at
        and row.v3_forecast_proof_method == row.forecast_proof_method
        and _same_real(row.v9_bps, row.v3_bps)
        and outcome.outcome_record_id == row.outcome_record_id
        and outcome.outcome_record_hash == row.outcome_record_hash
        and outcome.contract_version == V4_CONTRACT_VERSION
        and outcome.evidence_version == V4_EVIDENCE_VERSION
        and outcome.forecast_record_id == row.forecast_record_id
        and outcome.target_identity == row.target_identity
        and row.target_identity == canonical_target_identity(forecast)
        and outcome.target_endpoint == row.target_endpoint
        and outcome.target_timing_status == VERIFIED_TARGET_TIMING
        and outcome.target_timing_method_version in _ALLOWED_TARGET_TIMING_METHODS
        and outcome.reason_codes == ()
        and outcome.proof_eligible is True
        and outcome.previous_observation_at is not None
        and outcome.previous_observation_at < row.target_endpoint
        and row.target_endpoint <= outcome.endpoint_observation_at
        and outcome.endpoint_observation_at <= outcome.target_resolved_at
        and outcome.target_resolved_at <= row.outcome_created_at
        and row.outcome_created_at == outcome.created_at
        and row.evidence_available_at == row.outcome_created_at
        and _same_real(outcome.endpoint_observation_delay, derived_delay)
        and 0.0 <= derived_delay <= MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS
        and _same_real(outcome.actual_return_bps, row.actual_bps)
    )


def _valid(row: EfficacyObservation) -> bool:
    try:
        return _valid_verified(row)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        return False


def _known_as_of(row: EfficacyObservation, evaluation_as_of: datetime) -> bool:
    """Exclude aware future rows entirely; retain malformed rows as exclusions."""
    if not _aware(row.cutoff_at) or not _aware(row.evidence_available_at):
        return True
    return row.cutoff_at <= evaluation_as_of and row.evidence_available_at <= evaluation_as_of


def _non_overlapping(
    rows: Iterable[EfficacyObservation],
) -> tuple[EfficacyObservation, ...]:
    ordered = sorted(rows, key=lambda row: (row.cutoff_at, row.forecast_record_id))
    selected: list[EfficacyObservation] = []
    for row in ordered:
        if not selected or row.cutoff_at >= selected[-1].target_endpoint:
            selected.append(row)
    return tuple(selected)


def _deduplicate(
    rows: Iterable[EfficacyObservation],
) -> tuple[EfficacyObservation, ...]:
    groups: dict[tuple[object, ...], list[EfficacyObservation]] = {}
    for row in rows:
        verified = _verified_records(row)
        if verified is None:
            continue
        forecast, _outcome = verified
        groups.setdefault(
            forecast.logical_key + (row.family,),
            [],
        ).append(row)
    return tuple(
        values[0]
        for _key, values in sorted(groups.items())
        if len({_normalized_observation_hash(value) for value in values}) == 1
    )


def _normalized_observation(row: EfficacyObservation) -> dict[str, object]:
    verified = _verified_records(row)
    if verified is None:
        raise ValueError("observation records are not verifiable")
    forecast, outcome = verified
    payload = asdict(row)
    payload["forecast_record_json"] = asdict(forecast)
    payload["forecast_commit_proof"] = tuple(row.forecast_commit_proof)
    payload["outcome_record_json"] = asdict(outcome)
    return payload


def _normalized_observation_hash(row: EfficacyObservation) -> str:
    return canonical_sha256(_normalized_observation(row))


def _lineage(row: EfficacyObservation) -> tuple[object, ...] | None:
    verified = _verified_records(row)
    if verified is None:
        return None
    forecast, _outcome = verified
    return (
        forecast.cohort_id, forecast.cohort_hash, forecast.evidence_origin,
        forecast.data_schema_version, forecast.source_spec_version,
        forecast.target_spec_id, forecast.v1_contract_version,
        forecast.v2_state_version, forecast.v3_contract_version,
        forecast.v3_model_version,
    )


def _slice(
    horizon: str,
    family: str,
    rows: tuple[EfficacyObservation, ...],
) -> EfficacySlice:
    lineages = {_lineage(row) for row in rows}
    if None in lineages or len(lineages) != 1:
        return EfficacySlice(
            horizon, family, 0, 0.0, 0.0, 0.0, None, None, None, None,
            None, None, "UNAVAILABLE", None, 1.0, None, None, False,
            (FILTERED_CANDIDATE_REASON, MIXED_LINEAGE_REASON),
        )
    rows = _non_overlapping(rows)
    scored = tuple(
        (row, _directional_win(row.v9_bps, row.actual_bps),
         _directional_win(row.v3_bps, row.actual_bps))
        for row in rows
    )
    scored = tuple(item for item in scored if item[1] is not None and item[2] is not None)
    if not scored:
        return EfficacySlice(
            horizon, family, 0, 0.0, 0.0, 0.0, None, None, None, None,
            None, None, "UNAVAILABLE", None, 1.0, None, None, False,
            (FILTERED_CANDIDATE_REASON, "NO_SCOREABLE_HOLDOUT"),
        )
    v9 = tuple(float(item[1]) for item in scored)
    v3 = tuple(float(item[2]) for item in scored)
    paired = tuple(a - b for a, b in zip(v9, v3, strict=True))
    paired_n_eff, paired_reasons = effective_n(paired)
    v9_n_eff, v9_reasons = effective_n(v9)
    v3_n_eff, v3_reasons = effective_n(v3)
    v9_accuracy = math.fsum(v9) / len(v9)
    v3_accuracy = math.fsum(v3) / len(v3)
    result = hac(paired)
    reasons = tuple(sorted(set(
        paired_reasons + v9_reasons + v3_reasons + result.reason_codes
        + (FILTERED_CANDIDATE_REASON,)
    )))
    sufficient = (
        len(scored) >= MIN_SIGNIFICANCE_RAW_N
        and paired_n_eff >= MIN_SIGNIFICANCE_EFFECTIVE_N
        and v9_n_eff >= MIN_SIGNIFICANCE_EFFECTIVE_N
        and v3_n_eff >= MIN_SIGNIFICANCE_EFFECTIVE_N
    )
    if not sufficient:
        reasons = tuple(sorted(set(reasons + ("EFFICACY_EVIDENCE_INSUFFICIENT",))))
    return EfficacySlice(
        horizon=horizon,
        family=family,
        holdout_n=len(scored),
        directional_effective_n=paired_n_eff,
        v9_directional_effective_n=v9_n_eff,
        v3_directional_effective_n=v3_n_eff,
        mean_family_weight=math.fsum(row.family_weight for row, _, _ in scored) / len(scored),
        v9_directional_accuracy=v9_accuracy,
        v3_directional_accuracy=v3_accuracy,
        paired_improvement=v9_accuracy - v3_accuracy,
        v9_lower_95=_lower_95(v9_accuracy, v9_n_eff),
        v3_lower_95=_lower_95(v3_accuracy, v3_n_eff),
        hac_status=result.status,
        hac_z=result.z,
        p_upper=result.p_upper,
        holm_rank=None,
        holm_threshold=None,
        significant_improvement=False,
        reason_codes=reasons,
    )


def build_chronological_efficacy_report(
    *,
    observations: Iterable[EfficacyObservation],
    holdout_start: datetime,
    evaluation_as_of: datetime,
) -> EfficacyReport:
    """Evaluate a fixed chronological holdout without training on it."""

    if (
        not _aware(holdout_start)
        or not _aware(evaluation_as_of)
        or holdout_start >= evaluation_as_of
    ):
        raise ValueError("aware chronological boundaries with holdout_start < evaluation_as_of required")
    incoming = tuple(observations)
    candidates = tuple(
        row for row in incoming if _known_as_of(row, evaluation_as_of)
    )
    valid = _deduplicate(row for row in candidates if _valid(row))
    calibration = tuple(
        row for row in valid if row.evidence_available_at < holdout_start
    )
    holdout = tuple(
        row for row in valid
        if row.cutoff_at >= holdout_start
        and row.evidence_available_at <= evaluation_as_of
    )
    families = sorted({(row.horizon, row.family) for row in holdout},
                      key=lambda item: (HORIZONS.index(item[0]), item[1]))
    slices = tuple(
        _slice(
            horizon,
            family,
            tuple(sorted(
                (row for row in holdout
                 if row.horizon == horizon and row.family == family),
                key=lambda row: (row.cutoff_at, row.forecast_record_id),
            )),
        )
        for horizon, family in families
    )
    if slices:
        corrected = holm(tuple(item.p_upper for item in slices), alpha=SIGNIFICANCE_ALPHA)
        by_index = {item.index: item for item in corrected}
        slices = tuple(
            replace(
                item,
                holm_rank=by_index[index].rank,
                holm_threshold=by_index[index].threshold,
                significant_improvement=(
                    item.hac_status == "AVAILABLE"
                    and "EFFICACY_EVIDENCE_INSUFFICIENT" not in item.reason_codes
                    and FILTERED_CANDIDATE_REASON not in item.reason_codes
                    and item.paired_improvement is not None
                    and item.paired_improvement > 0
                    and by_index[index].passed
                ),
            )
            for index, item in enumerate(slices)
        )
    ordered = sorted(
        holdout,
        key=lambda row: (
            row.cutoff_at, row.horizon, row.family, row.forecast_record_id
        ),
    )
    digest = canonical_sha256(tuple(
        _normalized_observation(row) for row in ordered
    ))
    shell = EfficacyReport(
        report_id="",
        report_hash="",
        version=EFFICACY_VERSION,
        method=METHOD,
        holdout_start=holdout_start,
        evaluation_as_of=evaluation_as_of,
        calibration_n=len(calibration),
        holdout_n=len(holdout),
        excluded_n=len(candidates) - len(valid),
        evidence_digest=digest,
        slices=slices,
    )
    payload = {
        key: value for key, value in asdict(shell).items()
        if key not in {"report_id", "report_hash"}
    }
    report_hash = canonical_sha256(payload)
    return replace(
        shell,
        report_id="v9efficacy:" + report_hash,
        report_hash=report_hash,
    )
