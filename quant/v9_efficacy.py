"""Read-only chronological V9 efficacy evaluation.

This module is deliberately disconnected from live synthesis and persistence.
It evaluates already-proven forecasts on a forward holdout without changing
weights, thresholds, evidence, or production decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import math
from numbers import Real
import re
from typing import Iterable

from quant.v9_v1_contract import HORIZONS
from quant.v9_v4a_evidence import canonical_sha256
from quant.v9_v4b_accuracy import (
    effective_n, inverse_regularized_incomplete_beta,
)
from quant.v9_v4c_predictive import hac, holm

EFFICACY_VERSION = "ATOM_TRUE_V9_CHRONOLOGICAL_EFFICACY_2"
METHOD = "PAIRED_NONOVERLAP_DIRECTIONAL_HAC_HOLM_005_2"
SIGNIFICANCE_ALPHA = 0.05
MIN_SIGNIFICANCE_RAW_N = 500
MIN_SIGNIFICANCE_EFFECTIVE_N = 400.0
COMMIT_PROOF_METHOD = "POST_COMMIT_DB_OBSERVATION_V1"
VERIFIED_TARGET_TIMING = "VERIFIED"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
    return isinstance(value, datetime) and value.tzinfo is not None


def _finite_real(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


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


def _valid(row: EfficacyObservation) -> bool:
    timestamps = (
        row.cutoff_at, row.target_endpoint, row.forecast_available_at,
        row.v3_forecast_available_at, row.evidence_available_at,
    )
    return (
        row.proof_eligible is True
        and row.horizon in HORIZONS
        and bool(row.family)
        and bool(row.forecast_record_id)
        and bool(row.v3_forecast_record_id)
        and bool(row.outcome_record_id)
        and bool(row.target_identity)
        and bool(row.v9_model_version)
        and bool(row.v3_model_version)
        and _sha256(row.forecast_record_hash)
        and _sha256(row.v3_forecast_record_hash)
        and _sha256(row.outcome_record_hash)
        and row.forecast_proof_method == COMMIT_PROOF_METHOD
        and row.v3_forecast_proof_method == COMMIT_PROOF_METHOD
        and row.target_timing_status == VERIFIED_TARGET_TIMING
        and all(_aware(value) for value in timestamps)
        and row.cutoff_at < row.target_endpoint
        and row.forecast_available_at < row.target_endpoint
        and row.v3_forecast_available_at < row.target_endpoint
        and row.target_endpoint <= row.evidence_available_at
        and all(_finite_real(value) for value in (
            row.family_weight, row.v9_bps, row.v3_bps, row.actual_bps
        ))
        and 0 <= row.family_weight <= 1
    )


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


def _slice(
    horizon: str,
    family: str,
    rows: tuple[EfficacyObservation, ...],
) -> EfficacySlice:
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
            ("NO_SCOREABLE_HOLDOUT",),
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
    valid = tuple(row for row in candidates if _valid(row))
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
    digest = canonical_sha256(tuple(asdict(row) for row in ordered))
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
