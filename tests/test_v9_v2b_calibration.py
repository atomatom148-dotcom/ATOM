from dataclasses import FrozenInstanceError, replace
import math

import pytest

from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS, MAGNITUDE_BPS, Q3, RawFamilyObservation, RawTarget,
    TargetIdentity, build_v2a_dataset,
)
from quant.v9_v2b_calibration import calibrate_v2b, effective_n


def _dataset(horizon, ys, families, q3=None):
    seconds = {"30S": 30, "1M": 60, "5M": 300}[horizon]
    targets = []
    observations = []
    versions = [(name, "f1", "s1", "src1") for name in families]
    if q3 is not None:
        versions.append((Q3, "f3", "s1", "src1"))
    for i, y in enumerate(ys):
        cutoff = float(i * seconds)
        target = RawTarget(i, f"c{i}", "COIN", "target", "ts1", "t-src",
                           horizon, cutoff, cutoff + seconds, cutoff + seconds, y)
        targets.append(target)
        identity = TargetIdentity(target.cycle_id, cutoff, cutoff + seconds)
        for j, (name, values) in enumerate(families.items()):
            observations.append(RawFamilyObservation(
                i * 100 + j, identity, "COIN", name, "f1", "s1", "src1",
                horizon, DIRECTIONAL_BPS, values[i], cutoff, cutoff, cutoff,
                "FRESH"))
        if q3 is not None:
            observations.append(RawFamilyObservation(
                i * 100 + 90, identity, "COIN", Q3, "f3", "s1", "src1",
                horizon, MAGNITUDE_BPS, q3[i], cutoff, cutoff, cutoff, "FRESH"))
    return build_v2a_dataset(
        state_as_of=100000, horizon=horizon, target_spec_id="target",
        target_data_schema_version="ts1", target_source_spec_version="t-src",
        family_versions=versions, targets=targets, observations=observations)


def test_effective_n_equal_weights_positive_serial_dependence_and_bounds():
    independent = effective_n((1, -1, 1, -1, 1, -1))
    correlated = effective_n((1, 2, 3, 4, 5, 6))
    assert independent.kish_n == independent.observation_count == 6
    assert correlated.serial_dependence_factor > 1
    assert 1 <= correlated.effective_n < correlated.kish_n


def test_ips_first_nonpositive_pair_stops_and_constant_rule():
    alternating = effective_n((1, -1, 1, -1, 1, -1))
    constant = effective_n((4, 4, 4, 4))
    assert alternating.retained_lags == 0
    assert alternating.serial_dependence_factor == 1
    assert constant.effective_n == constant.kish_n == 4
    assert constant.reasons == ("SERIAL_DEPENDENCE_UNIDENTIFIABLE",)


def test_fewer_than_two_donors_uses_identity_fallback():
    dataset = _dataset("30S", (1, 4, 2, 8), {"q1_momentum": (0, 1, 2, 3)})
    result = calibrate_v2b((dataset,)).directional[0]
    assert (result.calibration_intercept, result.calibration_slope) == (0, 1)
    assert result.status == "PROVISIONAL"
    assert "HYPERPRIOR_UNIDENTIFIABLE" in result.reason_codes


def test_directional_constraints_covariance_and_bias_are_finite():
    ys = (1, 4, -1, 8, 3, 12)
    dataset = _dataset("30S", ys, {
        "q1_momentum": (0, 1, 2, 3, 4, 5),
        "q2_mean_reversion": (5, 4, 3, 2, 1, 0),
    })
    results = calibrate_v2b((dataset,)).directional
    assert all(item.calibration_slope >= 0 for item in results)
    assert all(math.isfinite(v) for item in results
               for row in item.calibration_parameter_covariance_2x2 for v in row)
    assert all(item.bias_diagnostic.result in {"PASS", "FAIL", "UNDETERMINED"}
               for item in results)


def test_q3_is_separate_nonnegative_and_gamma_is_frozen():
    a = _dataset("30S", (-1, 4, -2, 8, -3), {}, (1, 2, 1, 4, 2))
    b = _dataset("1M", (2, -3, 6, -7, 9), {}, (1, 1, 3, 2, 5))
    result = calibrate_v2b((a, b))
    assert not result.directional
    assert result.gamma == 0
    assert "V3" in result.gamma_state
    assert all(q.calibration_alpha >= 0 and q.calibration_beta >= 0
               for q in result.q3_magnitude)
    assert all(q.magnitude_target_specification == "ABSOLUTE_DIRECTIONAL_TARGET_BPS"
               for q in result.q3_magnitude)
    with pytest.raises(FrozenInstanceError):
        result.gamma = 1


def test_nonfinite_scores_are_rejected():
    with pytest.raises(ValueError):
        effective_n((1, math.nan))


def test_input_manifest_and_family_lineage_are_exact_and_duplicate_horizons_fail():
    dataset = _dataset("30S", (1, 2, 3), {"q1_momentum": (0, 1, 2)})
    result = calibrate_v2b((dataset,))

    assert result.input_manifest == (("30S", dataset.dataset_hash),)
    assert (result.directional[0].data_schema_version,
            result.directional[0].source_spec_version,
            result.directional[0].dataset_hash) == (
                "s1", "src1", dataset.dataset_hash)
    with pytest.raises(ValueError, match="duplicate V2-A horizon"):
        calibrate_v2b((dataset, dataset))
    with pytest.raises(ValueError, match="invalid V2-A dataset hash"):
        calibrate_v2b((replace(dataset, dataset_hash="0" * 64),))