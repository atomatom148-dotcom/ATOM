from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest

from quant.v9_v1_contract import HORIZONS, HORIZON_SECONDS
from quant.v9_v2d_evidence_state import DirectionalCalibrationState
from quant.v9_v3_synthesis import CANONICAL_FAMILIES, synthesize_v3


def _cal(q, *, a=0.0, c=1.0, residual=1.0, status="MATURE"):
    return DirectionalCalibrationState(q, "f1", a, c, ((0.0, 0.0), (0.0, 0.0)),
                                       100.0, residual, residual ** .5, status, ())


def _inputs(ids=("q1_momentum", "q2_mean_reversion"), *, matrix=None, support=None,
            values=None, covariance_status="MATURE", dependence=True, horizon="30S"):
    ids = tuple(ids); n = len(ids)
    matrix = matrix or tuple(tuple(float(i == j) for j in range(n)) for i in range(n))
    support = support or tuple(tuple(True for _ in range(n)) for _ in range(n))
    values = values or {q: float(i + 1) for i, q in enumerate(ids)}
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    slots = []
    for h in HORIZONS:
        for q in (*CANONICAL_FAMILIES, "q3_volatility"):
            present = h == horizon and q in values
            slots.append(SimpleNamespace(horizon=h, quant_id=q, formula_version="f1",
                                         horizon_seconds=HORIZON_SECONDS[h],
                                         numerical_type=("MAGNITUDE_BPS" if q == "q3_volatility"
                                                         else "DIRECTIONAL_BPS"),
                                         availability_state="FRESH" if present else "MISSING",
                                         value_bps=values.get(q) if present else None,
                                         forecast_cutoff_at=cutoff, source_as_of_at=cutoff,
                                         available_at=cutoff, data_schema_version="schema",
                                         source_spec_version="source"))
    v1 = SimpleNamespace(contract_version="V9-V1", horizons=HORIZONS, cutoff_at=cutoff,
                         target_spec_id="target", data_schema_version="schema",
                         source_spec_version="source", evidence_state_as_of=cutoff,
                         evidence_state_id="id", evidence_state_version="V9-V2D-2",
                         evidence_state_hash="hash", cycle_id="cycle", symbol="COIN",
                         slots=tuple(slots))
    states = []
    for h in HORIZONS:
        active = h == horizon
        states.append(SimpleNamespace(
            horizon=h, directional_calibrations=tuple(_cal(q) for q in ids) if active else (),
            ordered_quant_ids=ids if active else (), pair_support_boolean_matrix=support if active else (),
            stabilized_covariance_matrix=matrix if active else None,
            covariance_status=covariance_status if active else "UNAVAILABLE",
            dependence_modeled=dependence if active else False))
    v2 = SimpleNamespace(state_id="id", state_version="V9-V2D-2", state_hash="hash",
                         symbol="COIN", state_as_of=cutoff.timestamp(), target_spec_id="target",
                         target_data_schema_version="schema", target_source_spec_version="source",
                         horizon_state_tuple=tuple(states))
    return v1, v2


def _first(v1, v2):
    return synthesize_v3(v1, v2).horizon_results[0]


def test_unsupported_pair_cannot_enter_full_dependence_and_family_drops():
    v1, v2 = _inputs(support=((True, False), (False, True)))
    result = _first(v1, v2)
    assert result.used_quant_ids == ("q1_momentum",)
    assert result.covariance_mode == "PRINCIPAL_SUBSET"
    assert result.status == "MATURE"


def test_largest_supported_subset_and_canonical_tie_are_deterministic():
    ids = CANONICAL_FAMILIES[:4]
    support = ((True, True, True, False), (True, True, True, False),
               (True, True, True, False), (False, False, False, True))
    result = _first(*_inputs(ids, support=support))
    assert result.used_quant_ids == ids[:3]

    ties = ((True, True, False, False), (True, True, False, False),
            (False, False, True, True), (False, False, True, True))
    # An equally large supported pair remains complete; canonical ordering
    # chooses the first pair deterministically.
    assert _first(*_inputs(ids, support=ties)).used_quant_ids == ids[:2]


@pytest.mark.parametrize("family_count", (9, 8, 6, 5, 4, 2))
def test_every_covariance_compatible_family_is_retained(family_count):
    ids = CANONICAL_FAMILIES[:family_count]
    result = _first(*_inputs(ids))
    assert result.used_quant_ids == ids
    assert len(result.weights) == family_count


def test_single_family_uses_frozen_residual_variance_without_covariance():
    v1, v2 = _inputs(("q1_momentum",), matrix=(), support=())
    result = _first(v1, v2)
    assert result.covariance_mode == "SINGLE_FAMILY_RESIDUAL_VARIANCE"
    assert result.weights == (1.0,)
    assert result.predictive_variance_bps2 == pytest.approx(1.0)


def test_diagonal_provisional_is_usable_and_provisional():
    result = _first(*_inputs(covariance_status="PROVISIONAL", dependence=False))
    assert result.status == "PROVISIONAL"
    assert result.reason_codes == ("DIAGONAL_PROVISIONAL",)


@pytest.mark.parametrize("unsupported", ("q8_cross_asset", "q10_options_vol"))
def test_unsupported_optional_family_does_not_block_unrelated_family(unsupported):
    result = _first(*_inputs(("q1_momentum", unsupported),
                             support=((True, False), (False, True))))
    assert result.used_quant_ids == ("q1_momentum",)


def test_unavailable_horizon_does_not_block_other_horizons_and_exactly_six_results():
    output = synthesize_v3(*_inputs(("q1_momentum",), horizon="1M"))
    assert len(output.horizon_results) == 6
    assert output.horizon_results[0].status == "UNAVAILABLE"
    assert output.horizon_results[1].status == "MATURE"


def test_singular_psd_pseudoinverse_duplicate_invariants():
    ids = CANONICAL_FAMILIES[:3]
    duplicate = tuple(tuple(2.0 for _ in ids) for _ in ids)
    equal = _first(*_inputs(ids, matrix=duplicate, values={q: 4.0 for q in ids}))
    single = _first(*_inputs(("q1_momentum",), values={"q1_momentum": 4.0}))
    assert equal.predictive_variance_bps2 == pytest.approx(2.0)
    assert equal.expected_return_bps == pytest.approx(single.expected_return_bps)
    assert sum(equal.weights) == pytest.approx(1.0)


def test_missing_path_is_pure_and_q3_cannot_change_direction():
    empty1, empty2 = _inputs((), matrix=(), support=())
    assert _first(empty1, empty2).status == "UNAVAILABLE"
    base = _first(*_inputs(values={"q1_momentum": 1.0, "q2_mean_reversion": 2.0,
                                  "q3_volatility": 10.0}))
    changed = _first(*_inputs(values={"q1_momentum": 1.0, "q2_mean_reversion": 2.0,
                                     "q3_volatility": 999.0}))
    assert (base.expected_return_bps, base.weights) == (changed.expected_return_bps, changed.weights)
    assert not base.q3_used and base.gamma == 0.0 and base.phi == 1.0


def test_materially_non_psd_and_nonfinite_never_publish_numbers():
    bad = _first(*_inputs(CANONICAL_FAMILIES[:3],
                         matrix=((1.0, 2.0, 0.0), (2.0, 1.0, 0.0), (0.0, 0.0, 1.0))))
    assert bad.status == "UNAVAILABLE"
    assert bad.expected_return_bps is None and bad.predictive_variance_bps2 is None


@pytest.mark.parametrize(
    ("field", "value"),
    (("numerical_type", "MAGNITUDE_BPS"),
     ("horizon_seconds", 999),
     ("data_schema_version", "wrong"),
     ("source_spec_version", "wrong"),
     ("value_bps", float("nan")),
     ("value_bps", True)),
)
def test_v1_ineligible_slot_is_excluded_without_blocking_unrelated_family(field, value):
    v1, v2 = _inputs()
    slot = next(item for item in v1.slots
                if item.horizon == "30S" and item.quant_id == "q2_mean_reversion")
    setattr(slot, field, value)
    result = _first(v1, v2)
    assert result.used_quant_ids == ("q1_momentum",)


def test_exact_forecast_cutoff_is_accepted():
    v1, v2 = _inputs()
    assert _first(v1, v2).used_quant_ids == CANONICAL_FAMILIES[:2]


@pytest.mark.parametrize("offset", (timedelta(microseconds=-1), timedelta(microseconds=1)))
def test_inexact_forecast_cutoff_is_excluded_without_blocking_valid_family(offset):
    v1, v2 = _inputs()
    slot = next(item for item in v1.slots
                if item.horizon == "30S" and item.quant_id == "q2_mean_reversion")
    slot.forecast_cutoff_at = v1.cutoff_at + offset
    assert _first(v1, v2).used_quant_ids == ("q1_momentum",)


@pytest.mark.parametrize("timestamp_field", ("source_as_of_at", "available_at"))
def test_source_and_availability_before_cutoff_remain_allowed(timestamp_field):
    v1, v2 = _inputs()
    for slot in v1.slots:
        if slot.horizon == "30S" and slot.quant_id in CANONICAL_FAMILIES[:2]:
            setattr(slot, timestamp_field, v1.cutoff_at - timedelta(days=1))
    assert _first(v1, v2).used_quant_ids == CANONICAL_FAMILIES[:2]


@pytest.mark.parametrize("age", (timedelta(days=30), timedelta(0)))
def test_v2_state_at_or_before_current_cutoff_is_accepted(age):
    v1, v2 = _inputs()
    state_as_of = v1.cutoff_at - age
    v1.evidence_state_as_of = state_as_of
    v2.state_as_of = state_as_of.timestamp()
    assert _first(v1, v2).used_quant_ids == CANONICAL_FAMILIES[:2]


def test_v2_state_after_current_cutoff_is_rejected():
    v1, v2 = _inputs()
    state_as_of = v1.cutoff_at + timedelta(microseconds=1)
    v1.evidence_state_as_of = state_as_of
    v2.state_as_of = state_as_of.timestamp()
    assert all(result.status == "UNAVAILABLE"
               for result in synthesize_v3(v1, v2).horizon_results)


@pytest.mark.parametrize("field", ("evidence_state_id", "evidence_state_hash"))
def test_captured_v2_state_identity_remains_mandatory(field):
    v1, v2 = _inputs()
    setattr(v1, field, "wrong")
    assert all(result.status == "UNAVAILABLE"
               for result in synthesize_v3(v1, v2).horizon_results)


def test_old_v2_state_does_not_change_missing_family_independence():
    v1, v2 = _inputs()
    old = v1.cutoff_at - timedelta(days=30)
    v1.evidence_state_as_of = old
    v2.state_as_of = old.timestamp()
    missing = next(item for item in v1.slots
                   if item.horizon == "30S" and item.quant_id == "q2_mean_reversion")
    missing.availability_state = "MISSING"
    missing.value_bps = None
    assert _first(v1, v2).used_quant_ids == ("q1_momentum",)


@pytest.mark.parametrize(
    ("owner", "field", "value"),
    (("v1", "evidence_state_as_of", datetime(2025, 1, 1, tzinfo=timezone.utc)),
     ("v1", "target_spec_id", "wrong"),
     ("v1", "data_schema_version", "wrong"),
     ("v1", "source_spec_version", "wrong"),
     ("v2", "symbol", "WRONG")),
)
def test_v1_v2_identity_mismatch_makes_every_horizon_unavailable(owner, field, value):
    v1, v2 = _inputs()
    setattr(v1 if owner == "v1" else v2, field, value)
    output = synthesize_v3(v1, v2)
    assert all(result.status == "UNAVAILABLE" for result in output.horizon_results)
