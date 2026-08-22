from dataclasses import FrozenInstanceError, replace
import math
import sys

import pytest

from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS, MAGNITUDE_BPS, Q3, RawFamilyObservation, RawTarget,
    TargetIdentity, build_v2a_dataset,
)
from quant.v9_v2b_calibration import calibrate_v2b, effective_n
from quant.v9_v2c_covariance import (
    EPSILON_RELATIVE, OAS_METHOD, _oas, _psd, build_v2c_covariance,
)


def _inputs(ys, families, *, q3=None):
    targets, observations = [], []
    versions = [(q, "f1", "s1", "src1") for q in reversed(tuple(families))]
    if q3 is not None:
        versions.append((Q3, "f3", "s1", "src1"))
    for k, y in enumerate(ys):
        identity = TargetIdentity(f"c{k}", float(k*30), float(k*30+30))
        targets.append(RawTarget(k, identity.cycle_id, "COIN", "target", "ts1", "t-src",
                                 "30S", identity.cutoff_epoch, identity.maturity_epoch,
                                 identity.maturity_epoch, y))
        for j, (quant_id, values) in enumerate(reversed(tuple(families.items()))):
            observations.append(RawFamilyObservation(
                100*k+j, identity, "COIN", quant_id, "f1", "s1", "src1", "30S",
                DIRECTIONAL_BPS, values[k], identity.cutoff_epoch,
                identity.cutoff_epoch, identity.cutoff_epoch, "FRESH"))
        if q3 is not None:
            observations.append(RawFamilyObservation(
                100*k+90, identity, "COIN", Q3, "f3", "s1", "src1", "30S",
                MAGNITUDE_BPS, q3[k], identity.cutoff_epoch,
                identity.cutoff_epoch, identity.cutoff_epoch, "FRESH"))
    dataset = build_v2a_dataset(
        state_as_of=10000, horizon="30S", target_spec_id="target",
        target_data_schema_version="ts1", target_source_spec_version="t-src",
        family_versions=versions, targets=targets, observations=observations)
    return dataset, calibrate_v2b((dataset,))


def _identity_calibrations(dataset, calibration, status="MATURE"):
    directional = tuple(replace(item, calibration_intercept=0.0,
                                calibration_slope=1.0, status=status)
                        for item in calibration.directional)
    return replace(calibration, directional=directional)


def test_residual_pair_fixture_order_q3_exclusion_and_immutability():
    dataset, calibration = _inputs(
        (2.0, 5.0, 9.0, 14.0),
        {"q2_mean_reversion": (0.0, 1.0, 3.0, 6.0),
         "q1_momentum": (1.0, 3.0, 6.0, 10.0)},
        q3=(2.0, 3.0, 4.0, 5.0))
    result = build_v2c_covariance(dataset, _identity_calibrations(dataset, calibration))
    # Residuals are [1,2,3,4] and [2,4,6,8], hence sample covariance 10/3.
    assert result.raw_pairwise_covariance_matrix[0][1] == pytest.approx(10/3)
    assert result.ordered_quant_ids == ("q1_momentum", "q2_mean_reversion")
    assert Q3 not in result.ordered_quant_ids
    assert result.pairwise_raw_synchronized_n_matrix == ((4.0, 4.0), (4.0, 4.0))
    assert result.raw_pairwise_covariance_matrix[1][0] == result.raw_pairwise_covariance_matrix[0][1]
    assert result.status == "MATURE"
    assert isinstance(result.stabilized_covariance_matrix, tuple)
    with pytest.raises(FrozenInstanceError):
        result.status = "MATURE"


def test_exact_v2a_pair_support_is_not_reconstructed_or_imputed():
    dataset, calibration = _inputs(
        (1.0, 2.0, 3.0),
        {"q1_momentum": (0.0, 0.0, 0.0), "q2_mean_reversion": (0.0, 0.0, 0.0)})
    dataset = replace(dataset, pair_support=())
    result = build_v2c_covariance(dataset, _identity_calibrations(dataset, calibration))
    assert result.pairwise_raw_synchronized_n_matrix[0][1] == 0
    assert result.pair_support_boolean_matrix[0][1] is False
    assert result.raw_pairwise_covariance_matrix[0][1] == 0
    assert result.status != "MATURE"
    assert "PAIR_COVARIANCE_UNSUPPORTED" in result.reason_codes


def test_pair_effective_n_reuses_frozen_ips_and_support_rule():
    dataset, calibration = _inputs(
        (1, 2, 3, 4, 5, 6, 7, 8),
        {"q1_momentum": (0, 0, 0, 0, 0, 0, 0, 0),
         "q2_mean_reversion": (0, 0, 0, 0, 0, 0, 0, 0)})
    result = build_v2c_covariance(dataset, _identity_calibrations(dataset, calibration))
    residual = tuple(float(x) for x in (1, 2, 3, 4, 5, 6, 7, 8))
    mean = sum(residual)/len(residual)
    expected = effective_n(tuple((x-mean)**2 for x in residual)).effective_n
    assert result.pairwise_effective_n_matrix[0][1] == expected
    assert expected < len(residual)
    assert result.pair_support_boolean_matrix[0][1] is (expected > 1)


def test_standard_oas_frozen_formula_uses_n_and_edge_cases():
    empirical, sigma, delta, pooled = _oas([[1.0, 2.0], [2.0, 5.0], [4.0, 8.0]])
    t1 = empirical[0][0] + empirical[1][1]
    t2 = sum(empirical[i][j]**2 for i in range(2) for j in range(2))
    expected = min(1.0, max(0.0, (t1*t1)/((3.0)*(t2-t1*t1/2.0))))
    assert delta == pytest.approx(expected)
    assert 0 <= delta <= 1 and pooled == pytest.approx(t1/2)
    assert _oas([[1.0, 1.0], [1.0, 1.0]])[2] == 1.0  # DEN <= 0
    assert _oas([[1.0], [3.0]])[1] == [[1.0]]


def test_duplicates_collapse_expand_and_preserve_uncertainty_but_near_does_not():
    dataset, calibration = _inputs(
        (1, 4, 2, 8),
        {"q1_momentum": (0, 0, 0, 0), "q2_mean_reversion": (0, 0, 0, 0),
         "q4_stat_arb": (0, 0, 0, 1e-5)})
    result = build_v2c_covariance(dataset, _identity_calibrations(dataset, calibration))
    assert result.duplicate_groups == (("q1_momentum", "q2_mean_reversion"),)
    assert result.complete_case_quant_ids == ("q1_momentum", "q4_stat_arb")
    a = result.psd_projected_matrix
    assert a[0][0] == pytest.approx(a[0][1], rel=2e-14)
    assert a[1][1] == pytest.approx(a[0][1], rel=2e-14)
    for w in (0.0, .25, .5, 1.0):
        variance = w*w*a[0][0] + 2*w*(1-w)*a[0][1] + (1-w)**2*a[1][1]
        assert variance == pytest.approx(a[0][0], rel=2e-14)


def test_psd_projection_and_ridge_diagnostics():
    unchanged, *_ = _psd([[2.0, 1.0], [1.0, 2.0]])
    assert tuple(x for row in unchanged for x in row) == pytest.approx((2.0, 1.0, 1.0, 2.0), rel=1e-14)
    projected, before, after, count, correction, relative = _psd([[1.0, 2.0], [2.0, 1.0]])
    assert before < 0 <= after + 1e-14 and count == 1
    assert projected[0][1] == projected[1][0]
    assert correction > 0 and relative > 0
    dataset, calibration = _inputs((1, 2, 3), {"q1_momentum": (0, 0, 0)})
    result = build_v2c_covariance(dataset, _identity_calibrations(dataset, calibration))
    expected = max(sys.float_info.min, EPSILON_RELATIVE*result.psd_projected_matrix[0][0])
    assert result.numerical_ridge == expected
    assert all(math.isfinite(x) for row in result.stabilized_covariance_matrix for x in row)


def test_complete_case_fallback_and_no_scale_unavailable():
    dataset, calibration = _inputs(
        (1, 3, 2), {"q1_momentum": (0, 0, 0), "q2_mean_reversion": (0, 0, 0)})
    dataset = replace(dataset, complete_case_target_identities=())
    result = build_v2c_covariance(dataset, _identity_calibrations(dataset, calibration))
    assert result.status == "PROVISIONAL" and not result.dependence_modeled
    assert result.shrinkage_method is None and result.shrinkage_intensity is None
    assert "COMPLETE_CASE_DEPENDENCE_UNAVAILABLE" in result.reason_codes
    flat_dataset, flat_cal = _inputs((1, 1, 1), {"q1_momentum": (0, 0, 0)})
    unavailable = build_v2c_covariance(
        replace(flat_dataset, complete_case_target_identities=()),
        _identity_calibrations(flat_dataset, flat_cal))
    assert unavailable.status == "UNAVAILABLE" and unavailable.numerical_ridge is None


def test_rejected_complete_case_retains_finite_covariance_but_blocks_maturity():
    dataset, calibration = _inputs(
        (1, 3, 6), {"q1_momentum": (0, 0, 0), "q2_mean_reversion": (0, 0, 0)})
    missing = dict(enumerate(dataset.directional_subsets))
    subset = missing[0]
    broken = replace(dataset, directional_subsets=(replace(subset, observations=subset.observations[:-1]),
                                                    dataset.directional_subsets[1]))
    result = build_v2c_covariance(broken, _identity_calibrations(dataset, calibration, "MATURE"))
    assert result.complete_case_n == 2
    assert "COMPLETE_CASE_INTEGRITY_REJECTED" in result.reason_codes
    assert result.status == "PROVISIONAL"
    assert result.shrinkage_method == OAS_METHOD
    assert result.dependence_modeled
    assert all(math.isfinite(value)
               for row in result.stabilized_covariance_matrix for value in row)


def test_intact_complete_case_with_mature_calibrations_can_remain_mature():
    dataset, calibration = _inputs(
        (2.0, 5.0, 9.0, 14.0),
        {"q1_momentum": (1.0, 3.0, 6.0, 10.0),
         "q2_mean_reversion": (0.0, 1.0, 3.0, 6.0)})
    result = build_v2c_covariance(
        dataset, _identity_calibrations(dataset, calibration, "MATURE"))
    assert result.status == "MATURE"
    assert "COMPLETE_CASE_INTEGRITY_REJECTED" not in result.reason_codes


def test_nonfinite_residual_is_rejected_without_manufacturing_scale():
    dataset, calibration = _inputs((1, 2, 3), {"q1_momentum": (0, 0, 0)})
    item = replace(calibration.directional[0], calibration_intercept=math.nan,
                   status="MATURE")
    result = build_v2c_covariance(dataset, replace(calibration, directional=(item,)))
    assert result.status == "UNAVAILABLE"
    assert "NONFINITE_RESIDUAL" in result.reason_codes
    assert result.pair_support_boolean_matrix == ((False,),)
