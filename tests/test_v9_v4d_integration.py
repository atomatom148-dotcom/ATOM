from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from quant.v9_v1_contract import HORIZONS, HORIZON_SECONDS
from quant.v9_v2d_evidence_state import DirectionalCalibrationState
from quant.v9_v3_synthesis import CANONICAL_FAMILIES
from quant.v9_v4a_evidence import build_forecast
from quant.v9_v4c_predictive import CompactHorizonState, build_v4c_state
from quant.v9_v4d_integration import (
    OfflineStateBuildScheduler, OperationalMetrics, V4DCoordinator,
    resolve_outcome,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _inputs(family_count=1, unavailable_horizon=None):
    ids = CANONICAL_FAMILIES[:family_count]
    slots = []
    for horizon in HORIZONS:
        for quant_id in (*CANONICAL_FAMILIES, "q3_volatility"):
            fresh = quant_id in ids and horizon != unavailable_horizon
            slots.append(SimpleNamespace(
                quant_id=quant_id, horizon=horizon,
                horizon_seconds=HORIZON_SECONDS[horizon],
                numerical_type="MAGNITUDE_BPS" if quant_id == "q3_volatility" else "DIRECTIONAL_BPS",
                availability_state="FRESH" if fresh else "MISSING",
                value_bps=float(ids.index(quant_id) + 1) if fresh else None,
                formula_version="f1", data_schema_version="schema",
                source_spec_version="source", forecast_cutoff_at=NOW,
                source_as_of_at=NOW, available_at=NOW,
            ))
    v1 = SimpleNamespace(
        contract_version="V9-V1", horizons=HORIZONS, cutoff_at=NOW,
        target_spec_id="target", data_schema_version="schema",
        source_spec_version="source", evidence_state_as_of=NOW,
        evidence_state_id="v2", evidence_state_version="V9-V2D-2",
        evidence_state_hash="hash", cycle_id="cycle-1", symbol="COIN",
        slots=tuple(slots),
    )
    states = []
    for horizon in HORIZONS:
        active = horizon != unavailable_horizon
        calibrations = tuple(DirectionalCalibrationState(
            quant_id, "f1", 0.0, 1.0, ((0.0, 0.0), (0.0, 0.0)),
            100.0, 1.0, 1.0, "PROVISIONAL", ()) for quant_id in ids) if active else ()
        n = len(calibrations)
        states.append(SimpleNamespace(
            horizon=horizon, directional_calibrations=calibrations,
            ordered_quant_ids=ids if active else (),
            pair_support_boolean_matrix=tuple(tuple(True for _ in range(n)) for _ in range(n)),
            stabilized_covariance_matrix=tuple(tuple(float(i == j) for j in range(n)) for i in range(n)) if n > 1 else None,
            covariance_status="MATURE" if active else "UNAVAILABLE",
            dependence_modeled=True,
        ))
    v2 = SimpleNamespace(
        state_id="v2", state_version="V9-V2D-2", state_hash="hash",
        symbol="COIN", state_as_of=NOW.timestamp(), target_spec_id="target",
        target_data_schema_version="schema", target_source_spec_version="source",
        horizon_state_tuple=tuple(states), v2a_method_version="a",
        v2b_method_version="b", v2c_method_version="c",
        effective_n_method_version="n", calibration_method_version="cal",
        covariance_method_version="cov", numerical_canonicalization_version="num",
    )
    return v1, v2


class Writer:
    def __init__(self, fail_horizon=None):
        self.fail_horizon = fail_horizon
        self.forecasts = []
        self.outcomes = []
        self.last_write_status = None

    def persist_forecast(self, record, persisted_at):
        if record.horizon == self.fail_horizon:
            raise OSError("isolated")
        stored = replace(record, persisted_at=persisted_at,
                         persistence_proof_eligible=True)
        self.forecasts.append(stored)
        self.last_write_status = "INSERT"
        return stored

    def persist_outcome(self, record, created_at):
        stored = replace(record, created_at=created_at)
        self.outcomes.append(stored)
        self.last_write_status = "INSERT"
        return stored


def _empty_state():
    horizons = tuple(CompactHorizonState(
        horizon, "UNAVAILABLE", None, None, "UNAVAILABLE", None, None,
        "UNAVAILABLE", None, (), ("UNAVAILABLE",) * 6,
    ) for horizon in HORIZONS)
    return build_v4c_state(symbol="COIN", cohort_id="cohort", state_as_of=NOW,
        evidence_first_cutoff=None, evidence_last_cutoff=None, horizons=horizons)


@pytest.mark.parametrize("family_count", (11, 10, 7, 3, 1, 0))
def test_continuous_cycle_uses_current_subset_without_readiness_gate(family_count):
    v1, v2 = _inputs(family_count)
    writer = Writer()
    coordinator = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=writer, compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort",
    )
    output = coordinator.run_cycle()
    assert output.v1 is v1 and output.v2 is v2
    assert tuple(x.horizon for x in output.final_numbers) == HORIZONS
    assert len(writer.forecasts) == 6
    for v3, final in zip(output.v3.horizon_results, output.final_numbers):
        assert v3.directional_input_count == family_count
        assert final.final_bps == v3.expected_return_bps
        assert (final.gamma, final.phi, final.gamma_status) == (0, 1, "INACTIVE")
        assert (v3.status == "UNAVAILABLE") == (family_count == 0)


def test_one_horizon_and_one_persistence_failure_do_not_block_other_five():
    v1, v2 = _inputs(1, unavailable_horizon="30S")
    writer = Writer(fail_horizon="1M")
    output = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=writer, compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort",
    ).run_cycle()
    assert output.final_numbers[0].final_bps is None
    assert all(item.final_bps is not None for item in output.final_numbers[1:])
    assert [item.status for item in output.persistence].count("FAILED") == 1
    assert len(writer.forecasts) == 5


def test_latest_compact_state_is_consumed_and_conflict_fails_closed():
    v1, v2 = _inputs(1)
    state = _empty_state()
    available = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (state, "AVAILABLE"),
        state_cohort_id=lambda one, two: "cohort",
    ).run_cycle()
    conflicted = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (None, "STATE_CONFLICT"),
        state_cohort_id=lambda one, two: "cohort",
    ).run_cycle()
    assert available.v4_state_status == "AVAILABLE"
    assert conflicted.v4_state_status == "STATE_CONFLICT"
    assert [x.final_bps for x in available.final_numbers] == [x.final_bps for x in conflicted.final_numbers]


def test_outcome_is_separate_unverified_append_and_cannot_mutate_forecast():
    v1, v2 = _inputs(1)
    from quant.v9_v3_synthesis import synthesize_v3
    forecast = build_forecast(v1=v1, v2=v2,
        result=synthesize_v3(v1, v2).horizon_results[0], evidence_origin="PRODUCTION")
    writer = Writer()
    outcome = resolve_outcome(writer=writer, forecast=forecast,
        target_identity="target/source/schema/endpoint", endpoint_observation_at=NOW+timedelta(seconds=31),
        target_resolved_at=NOW+timedelta(seconds=32), actual_return_bps=2.0)
    assert outcome.forecast_record_id == forecast.forecast_record_id
    assert outcome.endpoint_observation_delay == 1
    assert outcome.target_timing_status == "UNVERIFIED" and not outcome.proof_eligible
    assert forecast.persisted_at is None and len(writer.outcomes) == 1


def test_offline_builder_requires_new_outcome_and_sixty_seconds():
    clock = [0.0]
    calls = []
    scheduler = OfflineStateBuildScheduler(lambda: calls.append(1) or "INSERT",
                                            monotonic_clock=lambda: clock[0])
    assert scheduler.run_if_due() == "SKIPPED_NO_NEW_OUTCOME"
    scheduler.note_new_outcome()
    assert scheduler.run_if_due() == "INSERT"
    scheduler.note_new_outcome(); clock[0] = 59
    assert scheduler.run_if_due() == "SKIPPED_RATE_LIMIT"
    clock[0] = 60
    assert scheduler.run_if_due() == "INSERT" and len(calls) == 2


def test_metrics_have_percentiles_and_do_not_change_forecast():
    metrics = OperationalMetrics(retained_samples=10)
    for value in (5, 1, 3, 2, 4):
        metrics.observe("latency", value)
    distribution = dict(metrics.snapshot().distributions)["latency"]
    assert (distribution.count, distribution.minimum, distribution.p50,
            distribution.p95, distribution.p99, distribution.maximum) == (5, 1, 3, 5, 5, 5)


@pytest.mark.parametrize("status", ("MATURE", "PROVISIONAL", "UNAVAILABLE"))
def test_v3_horizon_status_is_recorded_exactly(monkeypatch, status):
    import quant.v9_v4d_integration as integration
    from quant.v9_v3_synthesis import synthesize_v3

    v1, v2 = _inputs(1)
    original = synthesize_v3(v1, v2)
    replaced = replace(original, horizon_results=tuple(
        replace(result, status=status) for result in original.horizon_results))
    monkeypatch.setattr(integration, "synthesize_v3", lambda one, two: replaced)
    metrics = OperationalMetrics()
    V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort", metrics=metrics,
    ).run_cycle()
    counters = dict(metrics.snapshot().counters)
    assert counters[f"horizon.30S.{status}"] == 1
    assert not any(key.startswith("horizon.") and key.endswith(".AVAILABLE")
                   for key in counters)


def test_unexpected_v3_horizon_status_is_rejected(monkeypatch):
    import quant.v9_v4d_integration as integration
    from quant.v9_v3_synthesis import synthesize_v3

    v1, v2 = _inputs(1)
    original = synthesize_v3(v1, v2)
    unexpected = replace(original, horizon_results=(
        replace(original.horizon_results[0], status="AVAILABLE"),
        *original.horizon_results[1:],
    ))
    monkeypatch.setattr(integration, "synthesize_v3", lambda one, two: unexpected)
    metrics = OperationalMetrics()
    coordinator = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort", metrics=metrics,
    )
    with pytest.raises(RuntimeError, match="UNEXPECTED_V3_HORIZON_STATUS"):
        coordinator.run_cycle()
    assert not any(key.startswith("horizon.") for key, _ in metrics.snapshot().counters)
