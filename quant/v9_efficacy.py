"""Read-only chronological V9 efficacy evaluation.

This module is deliberately disconnected from live synthesis and persistence.
It evaluates already-proven forecasts on a forward holdout without changing
weights, thresholds, evidence, or production decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import math
from typing import Iterable

from quant.v9_v1_contract import HORIZONS
from quant.v9_v4a_evidence import canonical_sha256
from quant.v9_v4b_accuracy import (
    effective_n, inverse_regularized_incomplete_beta,
)
from quant.v9_v4c_predictive import hac, holm

EFFICACY_VERSION = "ATOM_TRUE_V9_CHRONOLOGICAL_EFFICACY_1"
METHOD = "PAIRED_DIRECTIONAL_HAC_HOLM_005_1"
SIGNIFICANCE_ALPHA = 0.05


@dataclass(frozen=True, slots=True)
class EfficacyObservation:
    forecast_record_id: str
    horizon: str
    family: str
    family_weight: float
    cutoff_at: datetime
    forecast_available_at: datetime
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
    return (
        row.proof_eligible
        and row.horizon in HORIZONS
        and bool(row.family)
        and bool(row.forecast_record_id)
        and row.forecast_available_at <= row.cutoff_at
        and row.cutoff_at < row.evidence_available_at
        and all(math.isfinite(value) for value in (
            row.family_weight, row.v9_bps, row.v3_bps, row.actual_bps
        ))
        and row.family_weight >= 0
    )


def _slice(
    horizon: str,
    family: str,
    rows: tuple[EfficacyObservation, ...],
) -> EfficacySlice:
    scored = tuple(
        (row, _directional_win(row.v9_bps, row.actual_bps),
         _directional_win(row.v3_bps, row.actual_bps))
        for row in rows
    )
    scored = tuple(item for item in scored if item[1] is not None and item[2] is not None)
    if not scored:
        return EfficacySlice(
            horizon, family, 0, 0.0, None, None, None, None,
            None, None, "UNAVAILABLE", None, 1.0, None, None, False,
            ("NO_SCOREABLE_HOLDOUT",),
        )
    v9 = tuple(float(item[1]) for item in scored)
    v3 = tuple(float(item[2]) for item in scored)
    paired = tuple(a - b for a, b in zip(v9, v3, strict=True))
    n_eff, effective_reasons = effective_n(paired)
    v9_accuracy = math.fsum(v9) / len(v9)
    v3_accuracy = math.fsum(v3) / len(v3)
    result = hac(paired)
    reasons = tuple(sorted(set(effective_reasons + result.reason_codes)))
    return EfficacySlice(
        horizon=horizon,
        family=family,
        holdout_n=len(scored),
        directional_effective_n=n_eff,
        mean_family_weight=math.fsum(row.family_weight for row, _, _ in scored) / len(scored),
        v9_directional_accuracy=v9_accuracy,
        v3_directional_accuracy=v3_accuracy,
        paired_improvement=v9_accuracy - v3_accuracy,
        v9_lower_95=_lower_95(v9_accuracy, n_eff),
        v3_lower_95=_lower_95(v3_accuracy, n_eff),
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
        holdout_start.tzinfo is None
        or evaluation_as_of.tzinfo is None
        or holdout_start >= evaluation_as_of
    ):
        raise ValueError("aware chronological boundaries with holdout_start < evaluation_as_of required")
    incoming = tuple(observations)
    valid = tuple(row for row in incoming if _valid(row))
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
            tuple(row for row in holdout if row.horizon == horizon and row.family == family),
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
        excluded_n=len(incoming) - len(valid),
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
