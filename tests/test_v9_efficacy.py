from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from quant.v9_v4a_evidence import canonical_sha256
from quant.v9_efficacy import (
    EFFICACY_VERSION, METHOD, EfficacyObservation,
    build_chronological_efficacy_report,
)

UTC = timezone.utc
START = datetime(2026, 1, 10, tzinfo=UTC)
END = datetime(2026, 1, 20, tzinfo=UTC)


def observation(
    index,
    *,
    family="Q1",
    horizon="30S",
    cutoff=None,
    available=None,
    v9=1.0,
    v3=-1.0,
    actual=1.0,
    proof=True,
    weight=0.25,
):
    cutoff = cutoff or START + timedelta(minutes=index)
    available = available or cutoff + timedelta(seconds=30)
    return EfficacyObservation(
        forecast_record_id=f"f-{index}",
        horizon=horizon,
        family=family,
        family_weight=weight,
        cutoff_at=cutoff,
        forecast_available_at=cutoff - timedelta(microseconds=1),
        evidence_available_at=available,
        v9_bps=v9,
        v3_bps=v3,
        actual_bps=actual,
        proof_eligible=proof,
    )


def test_report_uses_only_forward_available_proven_holdout():
    calibration = observation(
        -1,
        cutoff=START - timedelta(days=2),
        available=START - timedelta(days=1),
    )
    holdout = observation(1)
    late = observation(2, available=END + timedelta(seconds=1))
    unproven = observation(3, proof=False)
    report = build_chronological_efficacy_report(
        observations=(calibration, holdout, late, unproven),
        holdout_start=START,
        evaluation_as_of=END,
    )
    assert report.version == EFFICACY_VERSION
    assert report.method == METHOD
    assert report.calibration_n == 1
    assert report.holdout_n == 1
    assert report.excluded_n == 1
    assert report.slices[0].holdout_n == 1
    assert report.slices[0].v9_directional_accuracy == 1
    assert report.slices[0].v3_directional_accuracy == 0


def test_holdout_metrics_do_not_train_on_pre_holdout_values():
    pre = observation(
        -1,
        cutoff=START - timedelta(days=2),
        available=START - timedelta(days=1),
        v9=-999,
        v3=999,
        actual=10,
    )
    rows = tuple(
        observation(i, v9=1 if i % 3 else -1, v3=-1, actual=1)
        for i in range(1, 61)
    )
    first = build_chronological_efficacy_report(
        observations=(pre,) + rows,
        holdout_start=START,
        evaluation_as_of=END,
    )
    second = build_chronological_efficacy_report(
        observations=(replace(pre, v9_bps=999, v3_bps=-999),) + rows,
        holdout_start=START,
        evaluation_as_of=END,
    )
    assert first.slices == second.slices
    assert first.evidence_digest == second.evidence_digest


def test_family_weights_and_v3_baseline_are_reported_separately():
    rows = (
        observation(1, family="Q1", weight=0.2, v9=1, v3=-1, actual=1),
        observation(2, family="Q1", weight=0.4, v9=-1, v3=1, actual=1),
        observation(3, family="Q2", weight=0.8, v9=1, v3=1, actual=1),
    )
    report = build_chronological_efficacy_report(
        observations=rows, holdout_start=START, evaluation_as_of=END,
    )
    q1, q2 = report.slices
    assert (q1.family, q2.family) == ("Q1", "Q2")
    assert q1.mean_family_weight == pytest.approx(0.3)
    assert q1.v9_directional_accuracy == q1.v3_directional_accuracy == 0.5
    assert q2.mean_family_weight == pytest.approx(0.8)
    assert q2.v9_directional_accuracy == q2.v3_directional_accuracy == 1


def test_hash_and_order_are_deterministic():
    rows = (
        observation(2, family="Q2", horizon="1M"),
        observation(1, family="Q1", horizon="30S"),
    )
    first = build_chronological_efficacy_report(
        observations=rows, holdout_start=START, evaluation_as_of=END,
    )
    second = build_chronological_efficacy_report(
        observations=reversed(rows), holdout_start=START, evaluation_as_of=END,
    )
    assert first == second
    assert first.report_id == "v9efficacy:" + first.report_hash
    assert len(first.report_hash) == 64
    assert first.evidence_digest == canonical_sha256(
        tuple(
            {
                "forecast_record_id": row.forecast_record_id,
                "horizon": row.horizon,
                "family": row.family,
                "family_weight": row.family_weight,
                "cutoff_at": row.cutoff_at,
                "forecast_available_at": row.forecast_available_at,
                "evidence_available_at": row.evidence_available_at,
                "v9_bps": row.v9_bps,
                "v3_bps": row.v3_bps,
                "actual_bps": row.actual_bps,
                "proof_eligible": row.proof_eligible,
            }
            for row in sorted(
                rows,
                key=lambda value: (
                    value.cutoff_at, value.horizon, value.family,
                    value.forecast_record_id,
                ),
            )
        )
    )


def test_zero_actual_is_not_directionally_scoreable_and_gate_fails_closed():
    report = build_chronological_efficacy_report(
        observations=(observation(1, actual=0),),
        holdout_start=START,
        evaluation_as_of=END,
    )
    item = report.slices[0]
    assert item.holdout_n == 0
    assert item.hac_status == "UNAVAILABLE"
    assert item.p_upper == 1
    assert item.significant_improvement is False
    assert item.reason_codes == ("NO_SCOREABLE_HOLDOUT",)


@pytest.mark.parametrize(
    "row",
    (
        observation(1, horizon="BAD"),
        observation(1, family=""),
        observation(1, weight=-1),
        replace(observation(1), forecast_available_at=START + timedelta(days=1)),
    ),
)
def test_invalid_or_noncausal_rows_are_excluded(row):
    report = build_chronological_efficacy_report(
        observations=(row,), holdout_start=START, evaluation_as_of=END,
    )
    assert report.excluded_n == 1
    assert report.holdout_n == 0
    assert report.slices == ()


def test_boundaries_must_be_aware_and_forward():
    with pytest.raises(ValueError):
        build_chronological_efficacy_report(
            observations=(), holdout_start=START.replace(tzinfo=None),
            evaluation_as_of=END,
        )
    with pytest.raises(ValueError):
        build_chronological_efficacy_report(
            observations=(), holdout_start=END, evaluation_as_of=START,
        )
