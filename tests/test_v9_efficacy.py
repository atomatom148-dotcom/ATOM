from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from quant.v9_v4a_evidence import canonical_sha256
from quant.v9_efficacy import (
    COMMIT_PROOF_METHOD,
    EFFICACY_VERSION,
    METHOD,
    EfficacyObservation,
    build_chronological_efficacy_report,
)

UTC = timezone.utc
START = datetime(2026, 1, 10, tzinfo=UTC)
END = datetime(2026, 1, 20, tzinfo=UTC)


def _hash(token):
    return canonical_sha256(token)


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
    target = cutoff + timedelta(seconds=30)
    available = available or target
    return EfficacyObservation(
        forecast_record_id=f"v9-{index}",
        forecast_record_hash=_hash(("v9", index)),
        v9_model_version="ATOM_TRUE_V9_V4",
        horizon=horizon,
        family=family,
        family_weight=weight,
        cutoff_at=cutoff,
        target_endpoint=target,
        forecast_available_at=cutoff + timedelta(microseconds=1),
        forecast_proof_method=COMMIT_PROOF_METHOD,
        v3_forecast_record_id=f"v3-{index}",
        v3_forecast_record_hash=_hash(("v3", index)),
        v3_model_version="ATOM_TRUE_V9_V3",
        v3_forecast_available_at=cutoff + timedelta(microseconds=2),
        v3_forecast_proof_method=COMMIT_PROOF_METHOD,
        outcome_record_id=f"o-{index}",
        outcome_record_hash=_hash(("outcome", index)),
        target_identity=f"target-{index}",
        target_timing_status="VERIFIED",
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
    future = observation(2, available=END + timedelta(seconds=1))
    unproven = observation(3, proof=False)
    report = build_chronological_efficacy_report(
        observations=(calibration, holdout, future, unproven),
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


def test_commit_after_cutoff_but_before_target_is_eligible():
    row = observation(1)
    assert row.cutoff_at < row.forecast_available_at < row.target_endpoint
    report = build_chronological_efficacy_report(
        observations=(row,), holdout_start=START, evaluation_as_of=END,
    )
    assert report.holdout_n == 1


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


def test_hash_serial_statistics_and_order_are_deterministic():
    rows = tuple(
        observation(i, family="Q1", v9=1 if i % 3 else -1)
        for i in range(1, 20)
    )
    first = build_chronological_efficacy_report(
        observations=rows, holdout_start=START, evaluation_as_of=END,
    )
    second = build_chronological_efficacy_report(
        observations=reversed(rows), holdout_start=START,
        evaluation_as_of=END,
    )
    assert first == second
    assert first.report_id == "v9efficacy:" + first.report_hash
    assert len(first.report_hash) == 64
    assert first.evidence_digest == canonical_sha256(
        tuple(asdict(row) for row in sorted(
            rows,
            key=lambda value: (
                value.cutoff_at, value.horizon, value.family,
                value.forecast_record_id,
            ),
        ))
    )


def test_overlapping_targets_are_removed_before_statistics():
    first = observation(1)
    overlap = observation(2, cutoff=first.cutoff_at + timedelta(seconds=10))
    next_window = observation(3, cutoff=first.target_endpoint)
    report = build_chronological_efficacy_report(
        observations=(next_window, overlap, first),
        holdout_start=START,
        evaluation_as_of=END,
    )
    assert report.holdout_n == 3
    assert report.slices[0].holdout_n == 2


def test_model_specific_effective_counts_drive_each_bound():
    rows = tuple(
        observation(i, v9=1 if i % 2 else -1, v3=-1, actual=1)
        for i in range(1, 40)
    )
    item = build_chronological_efficacy_report(
        observations=rows, holdout_start=START, evaluation_as_of=END,
    ).slices[0]
    assert item.v9_directional_effective_n != item.v3_directional_effective_n
    assert item.v9_lower_95 is not None
    assert item.v3_lower_95 is not None


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


def test_tiny_asymptotic_result_cannot_be_significant():
    rows = (
        observation(1, v9=-1, v3=-1, actual=1),
        observation(2, v9=1, v3=-1, actual=1),
    )
    item = build_chronological_efficacy_report(
        observations=rows, holdout_start=START, evaluation_as_of=END,
    ).slices[0]
    assert item.p_upper < 0.05
    assert "EFFICACY_EVIDENCE_INSUFFICIENT" in item.reason_codes
    assert item.significant_improvement is False


@pytest.mark.parametrize(
    "row",
    (
        observation(1, horizon="BAD"),
        observation(1, family=""),
        observation(1, weight=-1),
        observation(1, weight=1.1),
        observation(1, weight=True),
        observation(1, v9=True),
        replace(observation(1), forecast_record_hash="bad"),
        replace(observation(1), v3_forecast_record_hash="bad"),
        replace(observation(1), outcome_record_hash="bad"),
        replace(observation(1), target_timing_status="UNVERIFIED"),
        replace(observation(1), forecast_proof_method="CALLER_BOOLEAN"),
        replace(observation(1), v3_forecast_proof_method="CALLER_BOOLEAN"),
        replace(observation(1), forecast_available_at=START + timedelta(days=1)),
        replace(observation(1), v3_forecast_available_at=START + timedelta(days=1)),
        replace(
            observation(1),
            cutoff_at=observation(1).cutoff_at.replace(tzinfo=None),
            target_endpoint=observation(1).target_endpoint.replace(tzinfo=None),
            forecast_available_at=observation(1).forecast_available_at.replace(tzinfo=None),
            v3_forecast_available_at=observation(1).v3_forecast_available_at.replace(tzinfo=None),
            evidence_available_at=observation(1).evidence_available_at.replace(tzinfo=None),
        ),
    ),
)
def test_invalid_noncausal_or_unproven_rows_are_excluded(row):
    report = build_chronological_efficacy_report(
        observations=(row,), holdout_start=START, evaluation_as_of=END,
    )
    assert report.excluded_n == 1
    assert report.holdout_n == 0
    assert report.slices == ()


def test_future_invalid_rows_do_not_change_as_of_report_identity():
    known = observation(1)
    future = replace(
        observation(2, cutoff=END + timedelta(days=1),
                    available=END + timedelta(days=1, seconds=30)),
        proof_eligible=False,
    )
    first = build_chronological_efficacy_report(
        observations=(known,), holdout_start=START, evaluation_as_of=END,
    )
    second = build_chronological_efficacy_report(
        observations=(known, future), holdout_start=START,
        evaluation_as_of=END,
    )
    assert first == second


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
