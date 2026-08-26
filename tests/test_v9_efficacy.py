from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone, tzinfo
from fractions import Fraction
import json
from types import SimpleNamespace

import pytest

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.historical_replay import (
    ALLOWED_FORMULA_VERSIONS,
    DATA_SCHEMA_VERSION as REPLAY_DATA_SCHEMA_VERSION,
    SOURCE_SPEC_SHARES,
)
from quant.q10_options_vol import FORMULA_VERSION as Q10_FORMULA_VERSION
from quant.v9_v1_contract import CONTRACT_VERSION as V1_CONTRACT_VERSION
from quant.v9_v2d_evidence_state import (
    CALIBRATION_METHOD_VERSION, COVARIANCE_METHOD_VERSION,
    EFFECTIVE_N_METHOD_VERSION, NUMERICAL_CANONICALIZATION_VERSION,
    STATE_VERSION as V2_STATE_VERSION, V2A_METHOD_VERSION,
    V2B_METHOD_VERSION, V2C_METHOD_VERSION,
)
from quant.v9_v3_synthesis import (
    CANONICAL_FAMILIES, MODEL_VERSION as V3_MODEL_VERSION, V3HorizonResult,
)
from quant.v9_v4a_evidence import (
    COMMIT_PROOF_METHOD, build_forecast, build_outcome, canonical_sha256,
    canonical_target_identity, _canonical,
)
from quant.v9_v4b_accuracy import MODEL_VERSION as V4_MODEL_VERSION
from quant.v9_efficacy import (
    EFFICACY_VERSION, FILTERED_CANDIDATE_REASON, METHOD,
    MIXED_LINEAGE_REASON, TARGET_SPEC_ID, EfficacyObservation, _slice,
    build_chronological_efficacy_report,
)


UTC = timezone.utc
START = datetime(2026, 1, 12, 15, 0, tzinfo=UTC)
END = datetime(2026, 1, 23, 22, 0, tzinfo=UTC)
LEGACY_TARGET_TIMING_METHOD = "ATOM_TRUE_V9_V4_TARGET_FIRST_AT_OR_AFTER_1"
FORMULA_VERSIONS = {
    **ALLOWED_FORMULA_VERSIONS,
    "q10_options_vol": Q10_FORMULA_VERSION,
}


def observation(
    index,
    *,
    family="q1_momentum",
    horizon="30S",
    horizon_seconds=None,
    cutoff=None,
    available=None,
    predicted=1.0,
    actual=1.0,
    proof=True,
    weight=1.0,
    lineage=None,
    evidence_origin="PRODUCTION",
    data_schema_version=DATA_SCHEMA_VERSION,
    source_spec_version=SOURCE_SPEC_VERSION,
    endpoint_delay=0.0,
    target_timing_method=None,
    gamma=0.0,
    phi=1.0,
    q3_used=False,
    directional_input_count=None,
    covariance_mode=None,
    reverse_used=False,
    cycle_id_value=None,
):
    cutoff = cutoff or START + timedelta(minutes=index)
    horizon_seconds = 30 if horizon_seconds is None else horizon_seconds
    cycle_id = (
        f"cycle-{index}-{cutoff.isoformat()}"
        if cycle_id_value is None else cycle_id_value
    )
    other = "q2_mean_reversion" if family != "q2_mean_reversion" else "q1_momentum"
    weight_by_family = (
        {family: 1.0} if weight == 1.0
        else {family: weight, other: 1.0 - weight}
    )
    used = tuple(
        quant_id for quant_id in CANONICAL_FAMILIES
        if quant_id in weight_by_family
    )
    if reverse_used:
        used = tuple(reversed(used))
    weights = tuple(weight_by_family[quant_id] for quant_id in used)
    slots = tuple(SimpleNamespace(
        quant_id=quant_id,
        formula_version=FORMULA_VERSIONS[quant_id],
        horizon=horizon,
    ) for quant_id in CANONICAL_FAMILIES)
    v1 = SimpleNamespace(
        symbol="COIN",
        cutoff_at=cutoff,
        cycle_id=cycle_id,
        contract_version=V1_CONTRACT_VERSION,
        target_spec_id=TARGET_SPEC_ID,
        data_schema_version=data_schema_version,
        source_spec_version=source_spec_version,
        slots=slots,
    )
    state_hash = canonical_sha256(("v2", cycle_id, lineage))
    v2 = SimpleNamespace(
        v2a_method_version=V2A_METHOD_VERSION if lineage is None else lineage,
        v2b_method_version=V2B_METHOD_VERSION,
        v2c_method_version=V2C_METHOD_VERSION,
        effective_n_method_version=EFFECTIVE_N_METHOD_VERSION,
        calibration_method_version=CALIBRATION_METHOD_VERSION,
        covariance_method_version=COVARIANCE_METHOD_VERSION,
        numerical_canonicalization_version=NUMERICAL_CANONICALIZATION_VERSION,
        state_id="v9v2:" + state_hash,
        state_version=V2_STATE_VERSION,
        state_hash=state_hash,
        state_as_of=cutoff.timestamp(),
    )
    directional_input_count = (
        len(used) if directional_input_count is None
        else directional_input_count
    )
    covariance_mode = covariance_mode or (
        "SINGLE_FAMILY_RESIDUAL_VARIANCE" if len(used) == 1
        else "FULL_DEPENDENCE"
    )
    result = V3HorizonResult(
        horizon, horizon_seconds, predicted, 4.0, "MATURE",
        used, weights, directional_input_count, covariance_mode,
        q3_used=q3_used, gamma=gamma, phi=phi,
    )
    forecast = build_forecast(
        v1=v1, v2=v2, result=result, evidence_origin=evidence_origin,
        cutoff_midpoint=100.0,
    )
    commit_at = cutoff + timedelta(microseconds=1)
    hydrated = replace(
        forecast, persisted_at=commit_at,
        persistence_proof_eligible=True, persistence_reason=None,
    )
    target_identity = canonical_target_identity(hydrated)
    outcome = build_outcome(
        forecast=hydrated,
        target_identity=target_identity,
        previous_observation_at=hydrated.target_endpoint - timedelta(microseconds=1),
        endpoint_observation_at=(
            hydrated.target_endpoint + timedelta(seconds=endpoint_delay)
        ),
        target_resolved_at=(
            hydrated.target_endpoint + timedelta(seconds=endpoint_delay)
        ),
        actual_return_bps=actual,
    )
    if target_timing_method is not None:
        outcome = replace(
            outcome,
            target_timing_method_version=target_timing_method,
            reason_codes=(),
            proof_eligible=True,
        )
        outcome_payload = {
            key: value for key, value in asdict(outcome).items()
            if key not in {"outcome_record_id", "outcome_record_hash", "created_at"}
        }
        outcome_hash = canonical_sha256(outcome_payload)
        outcome = replace(
            outcome,
            outcome_record_id="v9v4o:" + outcome_hash,
            outcome_record_hash=outcome_hash,
        )
    available = available or (
        hydrated.target_endpoint + timedelta(seconds=max(1.0, endpoint_delay + 1.0))
    )
    outcome = replace(outcome, created_at=available)
    return EfficacyObservation(
        forecast_record_id=hydrated.forecast_record_id,
        forecast_record_hash=hydrated.forecast_record_hash,
        v9_model_version=V4_MODEL_VERSION,
        horizon=horizon,
        family=family,
        family_weight=weight,
        cutoff_at=cutoff,
        target_endpoint=hydrated.target_endpoint,
        forecast_available_at=commit_at,
        forecast_proof_method=COMMIT_PROOF_METHOD,
        v3_forecast_record_id=hydrated.forecast_record_id,
        v3_forecast_record_hash=hydrated.forecast_record_hash,
        v3_model_version=V3_MODEL_VERSION,
        v3_forecast_available_at=commit_at,
        v3_forecast_proof_method=COMMIT_PROOF_METHOD,
        outcome_record_id=outcome.outcome_record_id,
        outcome_record_hash=outcome.outcome_record_hash,
        target_identity=target_identity,
        target_timing_status="VERIFIED",
        evidence_available_at=available,
        v9_bps=predicted,
        v3_bps=predicted,
        actual_bps=actual,
        proof_eligible=proof,
        forecast_record_json=asdict(forecast),
        forecast_commit_proof=(
            hydrated.forecast_record_id, hydrated.forecast_record_hash,
            commit_at, hydrated.target_endpoint, True, COMMIT_PROOF_METHOD,
        ),
        outcome_record_json=asdict(outcome),
        outcome_created_at=available,
    )


def report(rows):
    return build_chronological_efficacy_report(
        observations=rows, holdout_start=START, evaluation_as_of=END,
    )


def test_governed_evidence_is_baseline_only_and_cannot_claim_improvement():
    result = report((observation(1),))

    assert result.version == EFFICACY_VERSION
    assert result.method == METHOD
    assert result.holdout_n == 1
    item = result.slices[0]
    assert item.v9_directional_accuracy == item.v3_directional_accuracy == 1
    assert item.paired_improvement == 0
    assert FILTERED_CANDIDATE_REASON in item.reason_codes
    assert item.significant_improvement is False


def test_report_uses_only_forward_available_proven_holdout():
    calibration = observation(
        -1, cutoff=datetime(2026, 1, 9, 15, 0, tzinfo=UTC),
    )
    holdout = observation(1)
    future = observation(2, available=END + timedelta(seconds=1))
    unproven = observation(3, proof=False)

    result = report((calibration, holdout, future, unproven))

    assert result.calibration_n == 1
    assert result.holdout_n == 1
    assert result.excluded_n == 1


def test_commit_after_cutoff_but_before_target_is_eligible():
    row = observation(1)
    assert row.cutoff_at < row.forecast_available_at < row.target_endpoint
    assert report((row,)).holdout_n == 1


def test_commit_proof_observed_before_cutoff_is_excluded():
    row = observation(1)
    pre_cutoff = row.cutoff_at - timedelta(microseconds=1)
    forged = replace(
        row,
        forecast_available_at=pre_cutoff,
        v3_forecast_available_at=pre_cutoff,
        forecast_commit_proof=(
            *row.forecast_commit_proof[:2], pre_cutoff,
            *row.forecast_commit_proof[3:],
        ),
    )

    result = report((forged,))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


def test_hash_order_and_normalized_evidence_digest_are_deterministic():
    rows = tuple(observation(index) for index in range(1, 20))
    first = report(rows)
    second = report(reversed(rows))

    assert first == second
    assert first.report_id == "v9efficacy:" + first.report_hash
    assert len(first.report_hash) == 64
    assert len(first.evidence_digest) == 64


def test_evidence_identity_includes_commit_and_outcome_observation_times():
    row = observation(1)
    shifted_commit_at = row.forecast_available_at + timedelta(microseconds=1)
    shifted_commit = replace(
        row,
        forecast_available_at=shifted_commit_at,
        v3_forecast_available_at=shifted_commit_at,
        forecast_commit_proof=(
            *row.forecast_commit_proof[:2], shifted_commit_at,
            *row.forecast_commit_proof[3:],
        ),
    )
    shifted_created_at = row.outcome_created_at + timedelta(microseconds=1)
    shifted_outcome_payload = dict(row.outcome_record_json)
    shifted_outcome_payload["created_at"] = shifted_created_at
    shifted_outcome = replace(
        row,
        outcome_record_json=shifted_outcome_payload,
        outcome_created_at=shifted_created_at,
        evidence_available_at=shifted_created_at,
    )

    baseline = report((row,))
    commit_report = report((shifted_commit,))
    outcome_report = report((shifted_outcome,))
    assert baseline.holdout_n == commit_report.holdout_n == outcome_report.holdout_n == 1
    assert len({baseline.evidence_digest, commit_report.evidence_digest,
                outcome_report.evidence_digest}) == 3
    assert len({baseline.report_hash, commit_report.report_hash,
                outcome_report.report_hash}) == 3


def test_semantically_equal_mapping_and_canonical_json_deduplicate():
    row = observation(1)
    canonical_json_row = replace(
        row,
        forecast_record_json=json.dumps(
            _canonical(row.forecast_record_json), sort_keys=True,
            separators=(",", ":"),
        ),
        outcome_record_json=json.dumps(
            _canonical(row.outcome_record_json), sort_keys=True,
            separators=(",", ":"),
        ),
    )

    result = report((row, canonical_json_row))
    assert result.holdout_n == 1
    assert result.excluded_n == 1


def test_overlapping_targets_and_exact_duplicates_count_once():
    first = observation(1)
    overlap = observation(2, cutoff=first.cutoff_at + timedelta(seconds=10))
    next_window = observation(3, cutoff=first.target_endpoint)

    result = report((first,) * 500 + (overlap, next_window))

    assert result.holdout_n == 3
    assert result.excluded_n == 499
    assert result.slices[0].holdout_n == 2
    assert result.slices[0].significant_improvement is False


def test_conflicting_outcomes_for_one_forecast_are_all_excluded():
    positive = observation(1, actual=1.0)
    negative = observation(1, actual=-1.0)
    assert positive.forecast_record_id == negative.forecast_record_id
    assert positive.outcome_record_id != negative.outcome_record_id

    result = report((positive, negative))
    assert result.holdout_n == 0
    assert result.excluded_n == 2
    assert result.slices == ()


def test_conflicting_forecasts_for_one_logical_key_are_all_excluded():
    positive = observation(1, predicted=1.0)
    negative = observation(1, predicted=-1.0)
    assert positive.forecast_record_id != negative.forecast_record_id
    assert positive.cutoff_at == negative.cutoff_at

    result = report((positive, negative))
    assert result.holdout_n == 0
    assert result.excluded_n == 2
    assert result.slices == ()


def test_private_statistical_core_still_uses_paired_model_specific_counts():
    # Binding is tested through the public report; this directly isolates the
    # already-existing statistical core with intentionally altered scalars.
    rows = tuple(
        replace(
            observation(index),
            v9_bps=1 if index <= 20 else -1,
            v3_bps=-1,
        )
        for index in range(1, 40)
    )
    item = _slice("30S", "q1_momentum", rows)

    assert item.v9_directional_effective_n != item.v3_directional_effective_n
    assert item.v9_lower_95 is not None
    assert item.v3_lower_95 is not None
    assert item.significant_improvement is False


def test_zero_actual_is_not_directionally_scoreable_and_fails_closed():
    item = report((observation(1, actual=0),)).slices[0]
    assert item.holdout_n == 0
    assert item.hac_status == "UNAVAILABLE"
    assert item.p_upper == 1
    assert item.significant_improvement is False
    assert "NO_SCOREABLE_HOLDOUT" in item.reason_codes
    assert FILTERED_CANDIDATE_REASON in item.reason_codes


@pytest.mark.parametrize(
    "mutate",
    (
        lambda row: replace(row, horizon="BAD"),
        lambda row: replace(row, family="q3_volatility"),
        lambda row: replace(row, family_weight=0.5),
        lambda row: replace(row, family_weight=True),
        lambda row: replace(row, v9_bps=-1.0),
        lambda row: replace(row, forecast_record_hash="bad"),
        lambda row: replace(row, v3_forecast_record_id="distinct"),
        lambda row: replace(row, v3_forecast_record_hash="b" * 64),
        lambda row: replace(row, outcome_record_hash="bad"),
        lambda row: replace(row, target_timing_status="UNVERIFIED"),
        lambda row: replace(row, v9_model_version="ARBITRARY"),
        lambda row: replace(row, v3_model_version="ATOM_TRUE_V9_V3"),
        lambda row: replace(row, forecast_proof_method="CALLER_BOOLEAN"),
        lambda row: replace(row, v3_forecast_proof_method="CALLER_BOOLEAN"),
        lambda row: replace(row, proof_eligible=False),
        lambda row: replace(
            row,
            cutoff_at=row.cutoff_at.replace(tzinfo=None),
        ),
    ),
)
def test_unbound_arbitrary_or_noncausal_rows_are_excluded(mutate):
    result = report((mutate(observation(1)),))
    assert result.excluded_n == 1
    assert result.holdout_n == 0
    assert result.slices == ()


def test_payload_tamper_and_commit_proof_tamper_are_excluded():
    row = observation(1)
    payload = dict(row.forecast_record_json)
    payload["expected_return_bps"] = 999.0
    tampered_payload = replace(row, forecast_record_json=payload)
    tampered_proof = replace(
        row,
        forecast_commit_proof=(*row.forecast_commit_proof[:4], False,
                               row.forecast_commit_proof[5]),
    )

    for candidate in (tampered_payload, tampered_proof):
        result = report((candidate,))
        assert result.excluded_n == 1
        assert result.holdout_n == 0


def test_hash_valid_one_second_1h_target_is_excluded():
    row = observation(1, horizon="1H", horizon_seconds=1)
    result = report((row,))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


def test_outcome_cannot_be_reused_for_a_different_forecast():
    first = observation(1)
    second = observation(2)
    reused = replace(
        second,
        outcome_record_id=first.outcome_record_id,
        outcome_record_hash=first.outcome_record_hash,
        outcome_record_json=first.outcome_record_json,
        outcome_created_at=first.outcome_created_at,
        evidence_available_at=first.evidence_available_at,
        target_identity=first.target_identity,
        actual_bps=first.actual_bps,
    )
    result = report((reused,))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


def test_non_rth_and_mixed_lineage_rows_fail_closed():
    premarket = observation(
        1, cutoff=datetime(2026, 1, 12, 13, 0, tzinfo=UTC),
    )
    assert report((premarket,)).holdout_n == 0

    first = observation(1)
    second = observation(
        2,
        evidence_origin="CAUSAL_REPLAY",
        data_schema_version=REPLAY_DATA_SCHEMA_VERSION,
        source_spec_version=SOURCE_SPEC_SHARES,
    )
    item = report((first, second)).slices[0]
    assert item.holdout_n == 0
    assert MIXED_LINEAGE_REASON in item.reason_codes
    assert item.significant_improvement is False


def test_arbitrary_v2_method_lineage_is_excluded():
    result = report((observation(1, lineage="arbitrary-v2-method"),))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


@pytest.mark.parametrize(
    "change",
    (
        {"gamma": 123.0},
        {"phi": 0.5},
        {"q3_used": True},
        {"weight": 0.5, "reverse_used": True},
    ),
)
def test_nonfrozen_v3_semantics_are_excluded(change):
    result = report((observation(1, **change),))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


@pytest.mark.parametrize(
    "change",
    (
        {"directional_input_count": 2},
        {
            "weight": 0.5,
            "directional_input_count": 3,
            "covariance_mode": "FULL_DEPENDENCE",
        },
        {
            "weight": 0.5,
            "directional_input_count": 2,
            "covariance_mode": "PRINCIPAL_SUBSET",
        },
    ),
)
def test_impossible_v3_covariance_semantics_are_excluded(change):
    result = report((observation(1, **change),))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


def test_one_used_family_principal_subset_with_two_eligible_is_valid():
    row = observation(
        1,
        directional_input_count=2,
        covariance_mode="PRINCIPAL_SUBSET",
    )
    assert report((row,)).holdout_n == 1


@pytest.mark.parametrize(
    "field",
    ("family_weight", "v9_bps", "v3_bps", "actual_bps"),
)
def test_noncanonical_real_scalars_fail_closed_without_report_error(field):
    row = replace(observation(1), **{field: Fraction(1, 1)})
    result = report((row,))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


def test_nonfunctional_timezone_fails_closed_without_report_error():
    class NullOffsetTimezone(tzinfo):
        def utcoffset(self, _value): return None
        def dst(self, _value): return None

    row = observation(1)
    malformed = replace(
        row, cutoff_at=row.cutoff_at.replace(tzinfo=NullOffsetTimezone()),
    )
    result = report((malformed,))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


def test_nonstring_cycle_id_fails_closed_without_deduplication_error():
    result = report((observation(1, cycle_id_value=["unhashable"]),))
    assert result.excluded_n == 1
    assert result.holdout_n == 0


def test_legacy_timing_method_is_revalidated_against_current_delay_limit():
    boundary = observation(
        1,
        endpoint_delay=5.0,
        target_timing_method=LEGACY_TARGET_TIMING_METHOD,
    )
    late = observation(
        2,
        endpoint_delay=5.000001,
        target_timing_method=LEGACY_TARGET_TIMING_METHOD,
    )

    assert report((boundary,)).holdout_n == 1
    result = report((late,))
    assert result.holdout_n == 0
    assert result.excluded_n == 1


def test_future_invalid_rows_do_not_change_as_of_report_identity():
    known = observation(1)
    future = replace(
        observation(
            2,
            cutoff=datetime(2026, 1, 26, 15, 0, tzinfo=UTC),
            available=datetime(2026, 1, 26, 15, 1, tzinfo=UTC),
        ),
        proof_eligible=False,
    )
    assert report((known,)) == report((known, future))


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
