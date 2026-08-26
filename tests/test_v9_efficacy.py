from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from quant.v9_v4a_evidence import canonical_sha256
from quant.v9_efficacy import (
    COMMIT_PROOF_METHOD,
    EFFICACY_VERSION,
    METHOD,
    V3_MODEL_VERSION,
    V9_MODEL_VERSION,
    EfficacyObservation,
    build_chronological_efficacy_report,
)

UTC = timezone.utc
START = datetime(2026, 1, 10, tzinfo=UTC)
END = datetime(2026, 1, 20, tzinfo=UTC)


def _hash(token):
    return canonical_sha256(token)


def _items(payload):
    return tuple(sorted(payload.items()))


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
    v9_record_id = f"v9-{index}"
    v3_record_id = f"v3-{index}"
    outcome_record_id = f"o-{index}"
    target_identity = f"target-{index}"
    v9_payload = {
        "record_id": v9_record_id,
        "model_version": V9_MODEL_VERSION,
        "horizon": horizon,
        "family": family,
        "family_weight": weight,
        "cutoff_at": cutoff,
        "target_endpoint": target,
        "target_identity": target_identity,
        "expected_return_bps": v9,
    }
    v3_payload = {
        "record_id": v3_record_id,
        "model_version": V3_MODEL_VERSION,
        "horizon": horizon,
        "cutoff_at": cutoff,
        "target_endpoint": target,
        "target_identity": target_identity,
        "expected_return_bps": v3,
    }
    outcome_payload = {
        "record_id": outcome_record_id,
        "forecast_record_id": v9_record_id,
        "baseline_forecast_record_id": v3_record_id,
        "target_identity": target_identity,
        "target_endpoint": target,
        "actual_return_bps": actual,
        "target_timing_status": "VERIFIED",
    }
    return EfficacyObservation(
        forecast_record_id=v9_record_id,
        forecast_record_hash=canonical_sha256(v9_payload),
        v9_model_version=V9_MODEL_VERSION,
        horizon=horizon,
        family=family,
        family_weight=weight,
        cutoff_at=cutoff,
        target_endpoint=target,
        forecast_available_at=cutoff + timedelta(microseconds=1),
        forecast_proof_method=COMMIT_PROOF_METHOD,
        v3_forecast_record_id=v3_record_id,
        v3_forecast_record_hash=canonical_sha256(v3_payload),
        v3_model_version=V3_MODEL_VERSION,
        v3_forecast_available_at=cutoff + timedelta(microseconds=2),
        v3_forecast_proof_method=COMMIT_PROOF_METHOD,
        outcome_record_id=outcome_record_id,
        outcome_record_hash=canonical_sha256(outcome_payload),
        target_identity=target_identity,
        target_timing_status="VERIFIED",
        evidence_available_at=available,
        v9_bps=v9,
        v3_bps=v3,
        actual_bps=actual,
        proof_eligible=proof,
        v9_forecast_payload=_items(v9_payload),
        v3_forecast_payload=_items(v3_payload),
        outcome_payload=_items(outcome_payload),
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


@pytest.mark.parametrize(
    ("field", "value"),
    (("v9_model_version", "ATOM_TRUE_V9_V4"),
     ("v3_model_version", "ATOM-TRUE-V9-V3")),
)
def test_only_exact_frozen_model_versions_are_eligible(field, value):
    report = build_chronological_efficacy_report(
        observations=(replace(observation(1), **{field: value}),),
        holdout_start=START,
        evaluation_as_of=END,
    )
    assert report.holdout_n == 0
    assert report.excluded_n == 1


def test_hash_verified_payload_must_link_to_observation():
    row = observation(1)
    payload = dict(row.v9_forecast_payload)
    payload["record_id"] = "different-record"
    row = replace(
        row,
        forecast_record_hash=canonical_sha256(payload),
        v9_forecast_payload=_items(payload),
    )
    report = build_chronological_efficacy_report(
        observations=(row,), holdout_start=START, evaluation_as_of=END,
    )
    assert report.holdout_n == 0
    assert report.excluded_n == 1


def test_forecast_proof_before_cutoff_is_ineligible():
    row = observation(1)
    row = replace(row, forecast_available_at=row.cutoff_at - timedelta(microseconds=1))
    report = build_chronological_efficacy_report(
        observations=(row,), holdout_start=START, evaluation_as_of=END,
    )
    assert report.holdout_n == 0
    assert report.excluded_n == 1


def test_target_endpoint_must_equal_cutoff_plus_horizon():
    row = observation(1)
    endpoint = row.target_endpoint + timedelta(seconds=1)
    v9_payload = dict(row.v9_forecast_payload)
    v3_payload = dict(row.v3_forecast_payload)
    outcome_payload = dict(row.outcome_payload)
    for payload in (v9_payload, v3_payload, outcome_payload):
        payload["target_endpoint"] = endpoint
    row = replace(
        row,
        target_endpoint=endpoint,
        forecast_record_hash=canonical_sha256(v9_payload),
        v3_forecast_record_hash=canonical_sha256(v3_payload),
        outcome_record_hash=canonical_sha256(outcome_payload),
        v9_forecast_payload=_items(v9_payload),
        v3_forecast_payload=_items(v3_payload),
        outcome_payload=_items(outcome_payload),
    )
    report = build_chronological_efficacy_report(
        observations=(row,), holdout_start=START, evaluation_as_of=END,
    )
    assert report.holdout_n == 0
    assert report.excluded_n == 1


def test_conflicting_logical_records_are_excluded_before_counts():
    first = observation(1)
    conflict = observation(2, cutoff=first.cutoff_at, v9=-1)
    report = build_chronological_efficacy_report(
        observations=(first, conflict), holdout_start=START,
        evaluation_as_of=END,
    )
    assert report.holdout_n == 0
    assert report.excluded_n == 2
    assert report.slices == ()


class _NaiveLikeTimezone(tzinfo):
    def utcoffset(self, dt):
        return None


def test_datetime_with_tzinfo_but_no_offset_is_excluded():
    row = observation(1)
    malformed = row.cutoff_at.replace(tzinfo=_NaiveLikeTimezone())
    report = build_chronological_efficacy_report(
        observations=(replace(row, cutoff_at=malformed),),
        holdout_start=START,
        evaluation_as_of=END,
    )
    assert report.holdout_n == 0
    assert report.excluded_n == 1


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
        observation(i, v9=1 if i <= 20 else -1, v3=-1, actual=1)
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
