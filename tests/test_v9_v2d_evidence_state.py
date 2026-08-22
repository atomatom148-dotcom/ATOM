from dataclasses import FrozenInstanceError, replace
import re

import pytest

from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS, ExclusionCount, HORIZON_SECONDS, RawFamilyObservation, RawTarget,
    TargetIdentity, build_v2a_dataset,
)
from quant.v9_v2b_calibration import calibrate_v2b
from quant.v9_v2c_covariance import build_v2c_covariance
from quant.v9_v2d_evidence_state import HORIZONS, build_v2d_evidence_state


def _components(horizon="30S", *, state_as_of=10000.0, coefficient=None):
    seconds = HORIZON_SECONDS[horizon]
    targets, observations = [], []
    xs = (0.0, 1.0, 3.0, 6.0)
    ys = (2.0, 5.0, 9.0, 14.0)
    for index, (x, y) in enumerate(zip(xs, ys)):
        cutoff = float(index * seconds)
        identity = TargetIdentity(f"{horizon}-{index}", cutoff, cutoff + seconds)
        targets.append(RawTarget(index, identity.cycle_id, "COIN", "target", "ts1",
                                 "target-src1", horizon, cutoff, cutoff + seconds,
                                 cutoff + seconds, y))
        observations.append(RawFamilyObservation(
            index, identity, "COIN", "q1_momentum", "q1-f1", "qs1", "q-src1",
            horizon, DIRECTIONAL_BPS, x, cutoff, cutoff, cutoff, "FRESH"))
    dataset = build_v2a_dataset(
        state_as_of=state_as_of, horizon=horizon, target_spec_id="target",
        target_data_schema_version="ts1", target_source_spec_version="target-src1",
        family_versions=(("q1_momentum", "q1-f1", "qs1", "q-src1"),),
        targets=targets, observations=observations,
    )
    calibration = calibrate_v2b((dataset,))
    item = calibration.directional[0]
    item = replace(item, status="MATURE")
    if coefficient is not None:
        item = replace(item, calibration_intercept=coefficient)
    calibration = replace(calibration, directional=(item,))
    covariance = build_v2c_covariance(dataset, calibration)
    return dataset, calibration, covariance


def _state(components=(), **kwargs):
    return build_v2d_evidence_state(
        state_as_of=kwargs.pop("state_as_of", 10000.0),
        datasets=kwargs.pop("datasets", (item[0] for item in components)),
        calibrations=kwargs.pop("calibrations", (item[1] for item in components)),
        covariances=kwargs.pop("covariances", (item[2] for item in components)),
        **kwargs,
    )


def test_assembly_has_six_canonical_slots_and_no_forecast_or_range():
    component = _components()
    state = _state((component,))
    assert len(state.horizon_state_tuple) == 6
    assert tuple(item.horizon for item in state.horizon_state_tuple) == HORIZONS
    assert state.horizon_state_tuple[1].status == "UNAVAILABLE"
    assert state.horizon_state_tuple[1].reason_codes == ("HORIZON_EVIDENCE_UNAVAILABLE",)
    assert state.horizon_state_tuple[0].range_preparation_status == "PENDING_V3_REPLAY"
    assert state.horizon_state_tuple[0].range_score_count == 0
    assert state.horizon_state_tuple[0].range_quantile is None
    assert not any("forecast" in name.lower() or "range_lower" in name.lower()
                   for name in state.__dataclass_fields__)


def test_covariance_pair_support_is_forwarded_verbatim_and_immutable():
    component = _components()
    slot = _state((component,)).horizon_state_tuple[0]

    assert slot.ordered_quant_ids is component[2].ordered_quant_ids
    assert slot.pair_support_boolean_matrix is component[2].pair_support_boolean_matrix
    assert slot.ordered_directional_quant_ids == slot.ordered_quant_ids
    assert isinstance(slot.pair_support_boolean_matrix, tuple)
    assert all(isinstance(row, tuple) for row in slot.pair_support_boolean_matrix)
    assert all(isinstance(value, bool)
               for row in slot.pair_support_boolean_matrix for value in row)


@pytest.mark.parametrize(
    "matrix",
    (
        (),
        ((True, False),),
        ([True],),
        ((1,),),
    ),
)
def test_pair_support_contract_rejects_dimension_and_type_mismatches(matrix):
    dataset, calibration, covariance = _components()
    covariance = replace(covariance, pair_support_boolean_matrix=matrix)
    slot = _state(((dataset, calibration, covariance),)).horizon_state_tuple[0]

    assert slot.status == "UNAVAILABLE"
    assert slot.reason_codes == ("CROSS_LAYER_INTEGRITY_FAILURE",)


def test_pair_support_changes_state_hash_without_changing_mathematical_status():
    dataset, calibration, covariance = _components()
    baseline = _state(((dataset, calibration, covariance),))
    amended_covariance = replace(covariance, pair_support_boolean_matrix=((False,),))
    amended = _state(((dataset, calibration, amended_covariance),))

    assert baseline.horizon_state_tuple[0].status == amended.horizon_state_tuple[0].status
    assert baseline.state_hash != amended.state_hash


def test_input_order_is_irrelevant_and_all_mature_can_make_top_mature():
    components = tuple(_components(horizon) for horizon in HORIZONS)
    left = _state(components)
    right = _state(tuple(reversed(components)))
    assert left.state_hash == right.state_hash
    assert left.horizon_state_tuple == right.horizon_state_tuple
    assert all(item.status == "MATURE" for item in left.horizon_state_tuple)
    assert left.top_level_status == "MATURE"


@pytest.mark.parametrize("mutation", ("horizon", "quant", "formula", "q3_covariance"))
def test_cross_layer_integrity_rejects_mismatches(mutation):
    dataset, calibration, covariance = _components()
    if mutation == "horizon":
        covariance = replace(covariance, horizon="1M")
    elif mutation == "quant":
        covariance = replace(covariance, ordered_quant_ids=("q2_mean_reversion",))
    elif mutation == "formula":
        covariance = replace(covariance, ordered_formula_versions=("different",))
    else:
        covariance = replace(covariance, ordered_quant_ids=("q3_volatility",))
    state = _state(((dataset, calibration, covariance),))
    slot = state.horizon_state_tuple[0]
    assert slot.status == "UNAVAILABLE"
    assert "CROSS_LAYER_INTEGRITY_FAILURE" in slot.reason_codes


def test_future_cutoff_is_excluded_and_heterogeneous_cutoffs_are_explicit():
    future = _components(state_as_of=10001.0)
    rejected = _state((future,), state_as_of=10000.0)
    assert rejected.horizon_state_tuple[0].status == "UNAVAILABLE"
    assert not rejected.component_hash_tuple

    first = _components("30S", state_as_of=9000.0)
    second = _components("1M", state_as_of=10000.0)
    state = _state((first, second))
    assert state.top_level_status == "PROVISIONAL"
    assert "HETEROGENEOUS_COMPONENT_CUTOFF" in state.reason_code_tuple
    assert all("HETEROGENEOUS_COMPONENT_CUTOFF" in item.reason_codes
               for item in state.horizon_state_tuple[:2])


def test_status_propagation_q3_separation_and_covariance_requirement():
    dataset, calibration, covariance = _components()
    provisional_cal = replace(calibration, directional=(replace(
        calibration.directional[0], status="PROVISIONAL"),))
    provisional_cov = build_v2c_covariance(dataset, provisional_cal)
    state = _state(((dataset, provisional_cal, provisional_cov),))
    slot = state.horizon_state_tuple[0]
    assert slot.status == "PROVISIONAL"
    assert slot.q3.status == "UNAVAILABLE"  # Q3 absence does not invalidate direction.
    assert slot.gamma == 0.0
    assert slot.scale_conditioning_status == "PENDING_CAUSAL_V3_REPLAY"
    assert "q3_volatility" not in slot.ordered_directional_quant_ids

    unavailable = replace(covariance, status="UNAVAILABLE")
    slot = _state(((dataset, calibration, unavailable),)).horizon_state_tuple[0]
    assert slot.status == "UNAVAILABLE"
    assert "COVARIANCE_UNAVAILABLE" in slot.reason_codes

    no_direction = replace(calibration, directional=(replace(
        calibration.directional[0], status="UNAVAILABLE"),))
    slot = _state(((dataset, no_direction, covariance),)).horizon_state_tuple[0]
    assert slot.status == "UNAVAILABLE"


def test_top_level_mixed_and_unavailable_statuses():
    assert _state(()).top_level_status == "UNAVAILABLE"
    assert _state((_components(),)).top_level_status == "PROVISIONAL"


def test_hash_identity_determinism_and_meaningful_changes():
    base = _components()
    state = _state((base,))
    repeated = _state((base,))
    assert re.fullmatch(r"[0-9a-f]{64}", state.state_hash)
    assert state.state_id == "v9v2:" + state.state_hash
    assert state.state_hash == repeated.state_hash

    changed_cal = _components(coefficient=1.25)
    assert _state((changed_cal,)).state_hash != state.state_hash
    covariance_changed = replace(base[2], stabilized_covariance_matrix=((123.0,),))
    assert _state(((base[0], base[1], covariance_changed),)).state_hash != state.state_hash
    formula_changed = replace(base[2], method_version="V9-V2C-DIFFERENT")
    assert _state(((base[0], base[1], formula_changed),)).state_hash != state.state_hash
    reason_changed = replace(base[2], reason_codes=base[2].reason_codes + ("NEW_REASON",))
    assert _state(((base[0], base[1], reason_changed),)).state_hash != state.state_hash


def test_negative_zero_is_canonical_and_nonfinite_never_enters_state():
    dataset, calibration, covariance = _components()
    positive = replace(calibration, gamma=0.0)
    negative = replace(calibration, gamma=-0.0)
    assert _state(((dataset, positive, covariance),)).state_hash == _state(
        ((dataset, negative, covariance),)).state_hash

    bad_item = replace(calibration.directional[0], calibration_slope=float("nan"))
    bad = replace(calibration, directional=(bad_item,))
    state = _state(((dataset, bad, covariance),))
    assert state.horizon_state_tuple[0].status == "UNAVAILABLE"
    assert state.horizon_state_tuple[0].reason_codes == ("NONFINITE_COMPONENT_STATE",)
    assert all(item.layer != "V2B" for item in state.component_hash_tuple)


def test_every_published_collection_is_immutable_and_build_has_no_side_effects(tmp_path):
    state = _state((_components(),))
    slot = state.horizon_state_tuple[0]
    assert isinstance(slot.directional_calibrations, tuple)
    assert isinstance(slot.stabilized_covariance_matrix, tuple)
    with pytest.raises(FrozenInstanceError):
        state.top_level_status = "MATURE"
    with pytest.raises(FrozenInstanceError):
        slot.status = "MATURE"
    # V2D exposes only a pure constructor: no publisher, database, API, or file path.
    assert tuple(tmp_path.iterdir()) == ()


def _rejected_bundle_fixture(kind):
    valid = _components("30S", state_as_of=10000.0)
    rejected = _components("1M", state_as_of=10000.0)
    rejected_dataset = replace(
        rejected[0], training_start=-500.0, training_end=9999.0,
        target_spec_id="must-not-aggregate",
        target_data_schema_version="must-not-aggregate",
        target_source_spec_version="must-not-aggregate",
        exclusions=(ExclusionCount("REJECTED_ONLY_EXCLUSION", 77),),
    )
    if kind == "nonfinite":
        item = replace(rejected[1].directional[0], calibration_slope=float("nan"))
        rejected = (rejected_dataset, replace(rejected[1], directional=(item,)), rejected[2])
    elif kind == "integrity":
        rejected = (rejected_dataset, rejected[1], replace(
            rejected[2], ordered_formula_versions=("wrong-formula",)))
    elif kind == "future":
        rejected = (replace(rejected_dataset, state_as_of=10001.0), rejected[1], rejected[2])
    else:  # pragma: no cover - protects the test helper itself
        raise AssertionError(kind)
    return valid, rejected


@pytest.mark.parametrize(
    ("kind", "reason"),
    (("nonfinite", "NONFINITE_COMPONENT_STATE"),
     ("integrity", "CROSS_LAYER_INTEGRITY_FAILURE"),
     ("future", "CROSS_LAYER_INTEGRITY_FAILURE")),
)
def test_rejected_bundle_does_not_contribute_top_level_metadata(kind, reason):
    valid, rejected = _rejected_bundle_fixture(kind)
    baseline = _state((valid,))
    state = _state((valid, rejected))

    assert state.horizon_state_tuple[0] == baseline.horizon_state_tuple[0]
    assert state.horizon_state_tuple[1].status == "UNAVAILABLE"
    assert state.horizon_state_tuple[1].reason_codes == (reason,)
    assert (state.training_start, state.training_end) == (
        baseline.training_start, baseline.training_end)
    assert state.evidence_manifest_hash == baseline.evidence_manifest_hash
    assert state.component_hash_tuple == baseline.component_hash_tuple
    assert state.exclusion_count_tuple == baseline.exclusion_count_tuple
    assert (state.target_spec_id, state.target_data_schema_version,
            state.target_source_spec_version) == (
                baseline.target_spec_id, baseline.target_data_schema_version,
                baseline.target_source_spec_version)


def test_fixed_rejected_bundle_participates_and_changes_state_identity():
    valid, rejected = _rejected_bundle_fixture("nonfinite")
    rejected_state = _state((valid, rejected))
    fixed = _components("1M", state_as_of=10000.0)
    fixed_dataset = replace(
        fixed[0], training_start=-500.0, training_end=9999.0,
        exclusions=(ExclusionCount("FIXED_BUNDLE_EXCLUSION", 3),),
        dataset_hash="f" * 64,
    )
    fixed_state = _state((valid, (fixed_dataset, fixed[1], fixed[2])))

    assert fixed_state.horizon_state_tuple[1].status == "MATURE"
    assert fixed_state.training_start == -500.0
    assert fixed_state.training_end == 9999.0
    assert ("FIXED_BUNDLE_EXCLUSION", 3) in fixed_state.exclusion_count_tuple
    assert fixed_state.component_hash_tuple != rejected_state.component_hash_tuple
    assert fixed_state.evidence_manifest_hash != rejected_state.evidence_manifest_hash
    assert fixed_state.state_hash != rejected_state.state_hash
    assert not any("forecast" in field.lower() or "final_bps" in field.lower()
                   for field in fixed_state.__dataclass_fields__)
