from datetime import datetime, timezone
import threading
from types import SimpleNamespace

import pytest

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import LiveMarketState
from quant.q10_options_vol import OptionObservation
from quant.v9_production import (
    FORMULA_VERSION_MAP, V2_STATE_BUILD_EVIDENCE_PAGE_SIZE,
    ImmutableV2StateProvider,
    PostgresV2StateBuilder, build_live_v1,
)
from quant.v9_v2_state_store import V2StateRoleError
from quant.v9_v1_contract import HORIZONS, QUANT_IDS
from quant.web import dashboard_data


NOW = 1_800_000_000.0


class QueryCanceled(Exception):
    pass


def _live_snapshot():
    directional = SimpleNamespace(
        forecast_bps=tuple(float(i) for i in range(6)),
        source_as_of_epoch=NOW,
    )
    q4 = SimpleNamespace(
        forecast_bps=directional.forecast_bps, source_as_of_epoch=NOW - 2.0,
    )
    q10 = SimpleNamespace(
        forecast_bps=directional.forecast_bps, source_as_of_epoch=NOW - 3.0,
    )
    magnitude = SimpleNamespace(volatility_bps=tuple(float(i + 1) for i in range(6)))
    return SimpleNamespace(
        history=MidpointHistory((MidpointObservation(NOW, 100.0),)),
        momentum=directional,
        mean_reversion=directional,
        volatility=magnitude,
        stat_arb=q4,
        microstructure=directional,
        volume_liquidity=directional,
        relative_value=directional,
        cross_asset=directional,
        factor=directional,
        options_vol=q10,
        regime=directional,
        event_session=directional,
    )


def _v2_identity():
    return SimpleNamespace(
        state_id="v9v2:" + "a" * 64,
        state_version="V9-V2D-2",
        state_hash="a" * 64,
        state_as_of=NOW - 1,
        training_start=NOW - 100,
        training_end=NOW - 1,
    )


def test_live_v1_has_exact_72_typed_current_slots_and_v2_identity():
    v1 = build_live_v1(_live_snapshot(), _v2_identity())
    assert len(v1.slots) == 72
    assert tuple((slot.quant_id, slot.horizon) for slot in v1.slots) == tuple(
        (quant_id, horizon) for quant_id in QUANT_IDS for horizon in HORIZONS
    )
    assert all(slot.availability_state == "FRESH" for slot in v1.slots)
    assert all(slot.data_schema_version == DATA_SCHEMA_VERSION for slot in v1.slots)
    assert all(slot.source_spec_version == SOURCE_SPEC_VERSION for slot in v1.slots)
    q3 = tuple(slot for slot in v1.slots if slot.quant_id == "q3_volatility")
    assert all(slot.numerical_type == "MAGNITUDE_BPS" for slot in q3)
    assert all(slot.numerical_type == "DIRECTIONAL_BPS" for slot in v1.slots if slot not in q3)
    assert v1.evidence_state_id == _v2_identity().state_id
    assert v1.evidence_state_hash == _v2_identity().state_hash
    source_times = {
        quant_id: {slot.source_as_of_at.timestamp() for slot in v1.slots
                   if slot.quant_id == quant_id}
        for quant_id in (
            "q4_stat_arb", "q5_microstructure", "q6_volume_liquidity",
            "q7_relative_value", "q8_cross_asset", "q9_factor",
            "q10_options_vol",
        )
    }
    assert source_times == {
        "q4_stat_arb": {NOW - 2.0},
        "q5_microstructure": {NOW}, "q6_volume_liquidity": {NOW},
        "q7_relative_value": {NOW}, "q8_cross_asset": {NOW},
        "q9_factor": {NOW}, "q10_options_vol": {NOW - 3.0},
    }


@pytest.mark.parametrize("family", ("stat_arb", "options_vol"))
def test_live_v1_fails_closed_without_q4_or_q10_provider_time(family):
    snapshot = _live_snapshot()
    setattr(snapshot, family, SimpleNamespace(forecast_bps=(1.0,) * 6))
    with pytest.raises(RuntimeError, match="SOURCE_TIMESTAMP_UNAVAILABLE"):
        build_live_v1(snapshot, _v2_identity())


def test_quote_handler_runs_outside_state_lock_and_publishes_complete_output():
    observed = object()
    state = None

    def handler(snapshot, previous, current):
        assert state is not None
        acquired = state._lock.acquire(blocking=False)
        assert acquired
        state._lock.release()
        assert previous is None
        assert current.event_epoch == NOW
        return observed

    state = LiveMarketState(clock=lambda: NOW, v9_cycle_handler=handler)
    assert state.accept_quote(bid=99.0, ask=101.0, bid_size=1.0,
                              ask_size=1.0, event_epoch=NOW)
    assert state.v9_output() is observed
    assert state.v9_error() is None


def test_market_and_v9_publish_once_and_handler_failure_clears_old_output():
    first_output = object()
    second_entered = threading.Event()
    release_second = threading.Event()

    observed_options = []

    def handler(snapshot, previous, current):
        observed_options.append(snapshot.option_observation)
        if current.event_epoch == NOW:
            return first_output
        second_entered.set()
        assert release_second.wait(timeout=2)
        raise RuntimeError("v9 unavailable")

    state = LiveMarketState(clock=lambda: NOW, v9_cycle_handler=handler)
    assert state.update_market_display(
        coin_midpoint=100, coin_event_epoch=NOW,
        qqq_midpoint=500, qqq_event_epoch=NOW,
    )
    assert state.accept_quote(bid=99, ask=101, event_epoch=NOW)
    worker = threading.Thread(
        target=lambda: state.accept_quote(bid=100, ask=102, event_epoch=NOW + 1),
    )
    worker.start()
    assert second_entered.wait(timeout=1)
    assert state.accept_qqq_quote(bid=499, ask=501, event_epoch=NOW + .5)
    assert state.accept_g2_price(asset="BTC", price=60_000, event_epoch=NOW + .5)
    option = OptionObservation(
        "COIN-TEST", NOW + .5, 100, NOW + 100, "2027-01-01",
        1, .5, .5, .1, -.1, .2, .9, 1.1,
    )
    state.accept_option_observation(option)
    assert state.update_market_display(
        coin_midpoint=101, coin_event_epoch=NOW + .5,
    )

    during = state.publication()
    assert during.snapshot.history.latest.event_epoch == NOW
    assert during.snapshot.qqq_history.latest is None
    assert during.snapshot.option_observation is None
    assert during.cross_asset_state.btc_price is None
    assert during.market_display.coin_midpoint == 100
    assert during.v9_output is first_output

    release_second.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    after = state.publication()
    assert after.snapshot.history.latest.event_epoch == NOW + 1
    assert after.snapshot.qqq_history.latest is None
    assert after.snapshot.option_observation is None
    assert after.cross_asset_state.btc_price is None
    assert after.market_display.coin_midpoint == 100
    assert after.v9_output is None
    assert state.v9_error() == "RuntimeError"
    assert observed_options == [None, None]

    inputs = state.input_snapshot()
    assert inputs.qqq_history.latest.event_epoch == NOW + .5
    assert inputs.option_observation is option
    assert state.accept_qqq_quote(bid=500, ask=502, event_epoch=NOW + .75)
    assert state.accept_g2_price(asset="BTC", price=60_001, event_epoch=NOW + .75)
    assert state.update_market_display(
        coin_midpoint=102, coin_event_epoch=NOW + .75,
    )
    caught_up = state.publication()
    assert caught_up.snapshot.qqq_history.latest.event_epoch == NOW + .75
    assert caught_up.snapshot.option_observation is option
    assert caught_up.cross_asset_state.btc_price == 60_001
    assert caught_up.market_display.coin_midpoint == 102


def test_invalid_handler_output_cannot_wedge_publication_barrier():
    class InvalidOutput:
        evidence_delivery_status = "INVALID"

    state = LiveMarketState(v9_cycle_handler=lambda *_: InvalidOutput())
    assert state.accept_quote(bid=99, ask=101, event_epoch=NOW)
    assert state.publication().v9_output is None
    assert state.v9_error() == "TypeError"
    assert state.accept_qqq_quote(bid=499, ask=501, event_epoch=NOW + 1)
    assert state.publication().snapshot.qqq_history.latest.event_epoch == NOW + 1


def test_website_final_numbers_are_read_from_published_v4d_output():
    finals = tuple(SimpleNamespace(
        final_bps=float(index), move_percent=float(index) / 100,
        range_lower_bps=None, range_upper_bps=None,
    ) for index in range(6))
    payload = dashboard_data(v9_output=SimpleNamespace(final_numbers=finals))
    assert payload["final_numbers"]["BPS"] == [float(index) for index in range(6)]
    assert payload["final_numbers"]["MOVE%"] == [float(index) / 100 for index in range(6)]
    assert payload["final_numbers"]["RANGE"] == [None] * 6


def test_v2_background_provider_retries_failed_build_after_one_minute():
    class FailingBuilder:
        last_rows_materialized = 0

        def build(self):
            raise RuntimeError("temporary database failure")

    class StopAfterFirstWait:
        def __init__(self):
            self.seconds = []

        def is_set(self):
            return False

        def wait(self, seconds):
            self.seconds.append(seconds)
            return True

    stop = StopAfterFirstWait()
    provider = ImmutableV2StateProvider(FailingBuilder())
    thread = provider.start(interval_seconds=3600.0, stop_event=stop)
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert stop.seconds == [60.0]


def test_v2_provider_restores_then_retains_last_good_state_on_overflow():
    prior = SimpleNamespace(
        state_id="v9v2:" + "b" * 64,
        state_as_of=NOW - 10,
        creation_status="VALID",
    )

    class OverflowingBuilder:
        last_rows_materialized = V2_STATE_BUILD_EVIDENCE_PAGE_SIZE + 1

        def build(self):
            raise QueryCanceled("statement timeout")

    class Store:
        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            return prior, "AVAILABLE"

        def insert(self, _state):
            raise AssertionError("overflow must not persist a partial state")

    provider = ImmutableV2StateProvider(OverflowingBuilder(), store=Store())
    restored = provider.restore(datetime.fromtimestamp(NOW, timezone.utc))
    failed = provider.refresh()

    assert restored.status == "AVAILABLE"
    assert failed.status == "STALE"
    assert failed.state_id == prior.state_id
    assert failed.state_as_of == prior.state_as_of
    assert failed.error_type == "QueryCanceled"
    assert failed.error_code == "QueryCanceled"
    assert failed.rows_materialized == V2_STATE_BUILD_EVIDENCE_PAGE_SIZE + 1
    assert provider.capture(datetime.fromtimestamp(NOW, timezone.utc)) is prior
    telemetry = provider.metrics.snapshot()
    assert ("v2_state_restore_success_total", 1) in telemetry.counters
    assert ("v2_background_refresh_failures_total", 1) in telemetry.counters
    assert ("v2_background_status", "STALE") in telemetry.statuses
    assert (
        "v2_background_error_code", "QueryCanceled"
    ) in telemetry.statuses


def test_v2_provider_retries_restore_before_overflowing_rebuild():
    prior = SimpleNamespace(
        state_id="v9v2:" + "d" * 64,
        state_as_of=NOW - 10,
        creation_status="VALID",
    )

    class OverflowingBuilder:
        last_rows_materialized = V2_STATE_BUILD_EVIDENCE_PAGE_SIZE + 1

        def build(self):
            raise QueryCanceled("statement timeout")

    class Store:
        def __init__(self):
            self.latest_calls = 0

        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            self.latest_calls += 1
            if self.latest_calls == 1:
                raise RuntimeError("temporary database failure")
            return prior, "FOUND"

        def insert(self, _state):
            raise AssertionError("overflow must not persist a partial state")

    store = Store()
    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    provider = ImmutableV2StateProvider(
        OverflowingBuilder(),
        store=store,
        utc_clock=lambda: cutoff,
    )

    initial = provider.restore(cutoff)
    retried = provider.refresh()

    assert initial.status == "UNAVAILABLE"
    assert retried.status == "STALE"
    assert retried.state_id == prior.state_id
    assert retried.error_code == "QueryCanceled"
    assert store.latest_calls == 2
    assert provider.capture(cutoff) is prior


def test_v2_restore_telemetry_uses_stable_store_reason_code():
    class Builder:
        last_rows_materialized = 0

    class Store:
        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            raise V2StateRoleError("database role does not match V2 runtime")

    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    provider = ImmutableV2StateProvider(Builder(), store=Store())

    snapshot = provider.restore(cutoff)

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.error_type == "V2StateRoleError"
    assert snapshot.error_code == "V2_STATE_ROLE_MISMATCH"


def test_v2_provider_rejects_candidate_older_than_restored_state():
    prior = SimpleNamespace(
        state_id="v9v2:" + "e" * 64,
        state_as_of=NOW - 10,
        creation_status="VALID",
    )
    candidate = SimpleNamespace(
        state_id="v9v2:" + "f" * 64,
        state_as_of=NOW - 20,
        creation_status="VALID",
    )

    class Builder:
        last_rows_materialized = 12

        def build(self):
            return candidate

    class Store:
        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            return prior, "FOUND"

        def insert(self, _state):
            raise AssertionError("regressive candidate must not be persisted")

    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    provider = ImmutableV2StateProvider(Builder(), store=Store())
    provider.restore(cutoff)

    snapshot = provider.refresh()

    assert snapshot.status == "STALE"
    assert snapshot.state_id == prior.state_id
    assert snapshot.error_code == "V2_STATE_AS_OF_REGRESSION"
    assert provider.capture(cutoff) is prior


def test_v2_provider_does_not_publish_when_durable_insert_fails():
    candidate = SimpleNamespace(
        state_id="v9v2:" + "c" * 64,
        state_as_of=NOW - 1,
        creation_status="VALID",
    )

    class Builder:
        last_rows_materialized = 12

        def build(self):
            return candidate

    class Store:
        def insert(self, state):
            assert state is candidate
            raise RuntimeError("V2_STATE_PERSISTENCE_FAILED")

    provider = ImmutableV2StateProvider(Builder(), store=Store())
    snapshot = provider.refresh()

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.error_code == "V2_STATE_PERSISTENCE_FAILED"
    with pytest.raises(RuntimeError, match="V2_STATE_UNAVAILABLE"):
        provider.capture(datetime.fromtimestamp(NOW, timezone.utc))


def test_v2_provider_persists_state_and_receipt_atomically():
    candidate = SimpleNamespace(
        state_id="v9v2:" + "d" * 64,
        state_as_of=NOW - 1,
        creation_status="VALID",
    )
    receipt = object()

    class Builder:
        last_rows_materialized = 12

        def __init__(self):
            self.last_receipt = receipt

        def build(self):
            return candidate

    class Store:
        def __init__(self):
            self.calls = []

        def insert_with_receipt(self, state, proof):
            self.calls.append((state, proof))

    store = Store()
    snapshot = ImmutableV2StateProvider(Builder(), store=store).refresh()

    assert snapshot.status == "AVAILABLE"
    assert store.calls == [(candidate, receipt)]


def test_v2_provider_requires_atomic_receipt_store_for_postgres_builder():
    candidate = SimpleNamespace(
        state_id="v9v2:" + "e" * 64,
        state_as_of=NOW - 1,
        creation_status="VALID",
    )

    class Builder(PostgresV2StateBuilder):
        last_rows_materialized = 12

        def __init__(self):
            self.last_receipt = object()

        def build(self):
            return candidate

    class Store:
        def insert(self, _state):
            raise AssertionError("split state persistence must not be attempted")

    snapshot = ImmutableV2StateProvider(Builder(), store=Store()).refresh()

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.error_code == "V2_RECEIPT_PERSISTENCE_UNAVAILABLE"


def test_v2_batch_builder_uses_read_only_repeatable_read_and_closes_snapshot():
    class Cursor:
        def __init__(self):
            self.statements = []
            self.fetches = 0
            self.closed = False

        def execute(self, sql, parameters):
            self.statements.append((" ".join(sql.split()), parameters))

        def fetchone(self):
            return (NOW - 1,)

        def fetchall(self):
            self.fetches += 1
            return []

        def close(self):
            self.closed = True

    class Connection:
        def __init__(self):
            self.value = Cursor()
            self.rollbacks = 0
            self.closed = False

        def cursor(self):
            return self.value

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = Connection()
    builder = PostgresV2StateBuilder(
        "postgresql://unused", connect=lambda _url: connection,
    )
    with pytest.raises(RuntimeError, match="V2_STATE_NOT_USABLE"):
        builder.build()
    assert connection.value.statements[0][0] == (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    )
    assert connection.value.fetches == 2
    bounded = connection.value.statements[2:]
    assert len(bounded) == 2
    assert all("LIMIT %s" in sql for sql, _params in bounded)
    assert all(params[-4] == V2_STATE_BUILD_EVIDENCE_PAGE_SIZE
               for _sql, params in bounded)
    assert bounded[0][1][-3:] == (
        "DIRECTIONAL_FORECAST", "DIRECTIONAL_OUTCOME", NOW - 1,
    )
    assert bounded[1][1][-3:] == (
        "VOLATILITY_FORECAST", "VOLATILITY_OUTCOME", NOW - 1,
    )
    assert all("OFFSET" not in sql for sql, _params in bounded)
    assert all("o.resolved_epoch <= f.maturity_epoch + %s" in sql
               for sql, _params in bounded)
    assert all("o.resolved_epoch >= f.maturity_epoch" in sql
               for sql, _params in bounded)
    assert all(params[2] == 5.0 for _sql, params in bounded)
    assert all(
        "read_legacy_evidence_publications_for_records" in sql
        for sql, _parameters in bounded
    )
    assert all(
        "read_legacy_evidence_publication(" not in sql
        for sql, _parameters in bounded
    )
    assert all("JOIN LATERAL" not in sql for sql, _parameters in bounded)
    assert all(
        "forecast_proofs AS MATERIALIZED" in sql
        and "outcome_proofs AS MATERIALIZED" in sql
        and sql.count("read_legacy_evidence_publications_for_records") == 2
        and "LEFT JOIN forecast_proofs" in sql
        and "LEFT JOIN outcome_proofs" in sql
        and "fp.commit_observed_at < to_timestamp(f.maturity_epoch)" in sql
        for sql, _parameters in bounded
    )
    assert connection.rollbacks == 1
    assert connection.value.closed and connection.closed


def test_v2_builder_advances_raw_page_when_proofs_are_missing(monkeypatch):
    class Cursor:
        def __init__(self):
            self.parameters = ()
            self.volatility = False
            self.directional_fetches = 0

        def execute(self, sql, parameters):
            self.parameters = parameters
            self.volatility = "volatility_forecasts" in sql

        def fetchone(self):
            return (NOW,)

        def fetchall(self):
            if self.volatility:
                return []
            self.directional_fetches += 1
            if self.directional_fetches == 1:
                rows = []
                for index in range(V2_STATE_BUILD_EVIDENCE_PAGE_SIZE):
                    forecast_proof = float(index) if index % 2 == 0 else None
                    outcome_proof = float(index + 30) if index % 2 else None
                    rows.append((
                        index, "q1_momentum",
                        FORMULA_VERSION_MAP["q1_momentum"],
                        f"cycle-{index}", "COIN", "30S", float(index),
                        float(index + 30), 1.0, float(index),
                        DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, None, 2.0,
                        float(index + 30), forecast_proof, outcome_proof,
                    ))
                return rows
            if self.directional_fetches == 2:
                index = V2_STATE_BUILD_EVIDENCE_PAGE_SIZE
                return [(
                    index, "q1_momentum",
                    FORMULA_VERSION_MAP["q1_momentum"],
                    f"cycle-{index}", "COIN", "30S", float(index),
                    float(index + 30), 1.0, float(index),
                    DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, None, 2.0,
                    float(index + 30), float(index), float(index + 30),
                )]
            raise AssertionError("candidate pagination must terminate")

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()

        def cursor(self):
            return self.cursor_value

        def rollback(self):
            pass

        def close(self):
            pass

    captured = {}

    def dataset(**kwargs):
        captured[kwargs["horizon"]] = kwargs
        return SimpleNamespace(horizon=kwargs["horizon"])

    monkeypatch.setattr("quant.v9_production.build_v2a_dataset", dataset)
    monkeypatch.setattr(
        "quant.v9_production.build_v2b_calibration", lambda _datasets: object(),
    )
    monkeypatch.setattr(
        "quant.v9_production.build_v2c_covariance", lambda *_args: object(),
    )
    monkeypatch.setattr(
        "quant.v9_production.build_v2d_evidence_state",
        lambda **_kwargs: SimpleNamespace(
            creation_status="VALID", top_level_status="PROVISIONAL",
        ),
    )
    connection = Connection()
    builder = PostgresV2StateBuilder(
        "postgresql://unused", connect=lambda _url: connection,
    )

    builder.build()

    assert connection.cursor_value.directional_fetches == 2
    assert builder.last_rows_materialized == 1
    assert [row.record_id for row in captured["30S"]["observations"]] == [
        V2_STATE_BUILD_EVIDENCE_PAGE_SIZE,
    ]


def test_v2_builder_materializes_provider_time_and_rejects_unproven_rows(monkeypatch):
    cutoff = NOW - 10.0
    directional = [
        (1, "q4_stat_arb", FORMULA_VERSION_MAP["q4_stat_arb"], "cycle", "COIN",
         "30S", cutoff, cutoff + 30, 1.0, cutoff + 1,
         DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, cutoff - 2, 2.0, NOW,
         cutoff + 1, NOW - 3),
        (2, "q10_options_vol", FORMULA_VERSION_MAP["q10_options_vol"], "cycle", "COIN",
         "30S", cutoff, cutoff + 30, 1.0, cutoff + 1,
         DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, None, 2.0, NOW,
         cutoff + 1, NOW - 2),
        (3, "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"], "cycle", "COIN",
         "30S", cutoff, cutoff + 30, 1.0, cutoff + 1,
         DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, None, 2.0, NOW,
         cutoff + 1, NOW - 1),
    ]

    class Cursor:
        def __init__(self):
            self.fetchall_calls = 0
            self.statements = []
        def execute(self, sql, parameters):
            self.statements.append((" ".join(sql.split()), parameters))
        def fetchone(self): return (NOW,)
        def fetchall(self):
            self.fetchall_calls += 1
            return directional if self.fetchall_calls == 1 else []
        def close(self): pass

    class Connection:
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value
        def rollback(self): pass
        def close(self): pass

    captured = {}
    def dataset(**kwargs):
        captured[kwargs["horizon"]] = kwargs
        return SimpleNamespace(horizon=kwargs["horizon"])
    monkeypatch.setattr("quant.v9_production.build_v2a_dataset", dataset)
    monkeypatch.setattr("quant.v9_production.build_v2b_calibration", lambda _datasets: object())
    monkeypatch.setattr("quant.v9_production.build_v2c_covariance", lambda *_args: object())
    monkeypatch.setattr(
        "quant.v9_production.build_v2d_evidence_state",
        lambda **_kwargs: SimpleNamespace(
            creation_status="VALID", top_level_status="PROVISIONAL"),
    )
    connection = Connection()

    PostgresV2StateBuilder(
        "postgresql://unused", connect=lambda _url: connection,
    ).build()

    observations = captured["30S"]["observations"]
    assert [(row.quant_id, row.source_as_of_epoch) for row in observations] == [
        ("q4_stat_arb", cutoff - 2),
        ("q1_momentum", cutoff),
    ]
    targets = captured["30S"]["targets"]
    assert len(targets) == 3
    assert {row.resolved_epoch for row in targets} == {NOW - 1}
    assert "f.source_as_of_epoch" in connection.cursor_value.statements[2][0]

def test_v2_builder_fails_closed_if_keyset_does_not_advance():
    class Cursor:
        def __init__(self):
            self.fetches = 0
        def execute(self, _sql, _parameters):
            pass
        def fetchone(self):
            return (NOW,)
        def fetchall(self):
            self.fetches += 1
            row = (
                1, "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"],
                "cycle", "COIN", "30S", 1.25, 31.25, 1.0, 1.25,
                DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, None, 2.0, 31.25,
                1.0, 31.0,
            )
            return [row] * V2_STATE_BUILD_EVIDENCE_PAGE_SIZE
        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.rollbacks = 0
        def cursor(self):
            return self.cursor_value
        def rollback(self):
            self.rollbacks += 1
        def close(self):
            pass

    connection = Connection()
    builder = PostgresV2StateBuilder(
        "postgresql://unused", connect=lambda _url: connection,
    )
    with pytest.raises(RuntimeError, match="V2_EVIDENCE_PAGINATION_STALLED"):
        builder.build()
    assert builder.last_rows_materialized == V2_STATE_BUILD_EVIDENCE_PAGE_SIZE * 2
    assert connection.cursor_value.fetches == 2
    assert connection.rollbacks == 0


@pytest.mark.parametrize("row_count", (65_536, 65_537, 200_000))
def test_v2_builder_keyset_pages_admit_all_qualified_rows(monkeypatch, row_count):
    class Cursor:
        def __init__(self):
            self.parameters = ()
            self.volatility = False
            self.keys = []
        def execute(self, sql, parameters):
            self.parameters = parameters
            self.volatility = "volatility_forecasts" in sql
            assert "OFFSET" not in sql
            if not self.volatility and self.keys:
                assert parameters[3:6] == self.keys[-1]
        def fetchone(self): return (NOW,)
        def fetchall(self):
            if self.volatility:
                return []
            after = -1 if len(self.parameters) == 7 else int(self.parameters[5])
            first = after + 1
            stop = min(first + V2_STATE_BUILD_EVIDENCE_PAGE_SIZE, row_count)
            rows = [
                (index, "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"],
                 f"cycle-{index}", "COIN", "30S", float(2 * index) + 0.25,
                 float(2 * index) + 30.25, 1.0, float(index), DATA_SCHEMA_VERSION,
                 SOURCE_SPEC_VERSION, None, 2.0, float(index + 30),
                 float(index), float(index + 30))
                for index in range(first, stop)
            ]
            if rows:
                self.keys.append((rows[-1][5], rows[-1][6], rows[-1][0]))
            return rows
        def close(self): pass

    class Connection:
        def __init__(self): self.value = Cursor()
        def cursor(self): return self.value
        def rollback(self): pass
        def close(self): pass

    captured = 0
    def dataset(**kwargs):
        nonlocal captured
        captured += len(tuple(kwargs["observations"]))
        return SimpleNamespace(horizon=kwargs["horizon"])
    monkeypatch.setattr("quant.v9_production.build_v2a_dataset", dataset)
    monkeypatch.setattr("quant.v9_production.build_v2b_calibration", lambda _datasets: object())
    monkeypatch.setattr("quant.v9_production.build_v2c_covariance", lambda *_args: object())
    monkeypatch.setattr("quant.v9_production.build_v2d_evidence_state", lambda **_kwargs:
        SimpleNamespace(creation_status="VALID", top_level_status="PROVISIONAL"))
    connection = Connection()
    builder = PostgresV2StateBuilder("postgresql://unused", connect=lambda _url: connection)

    builder.build()

    assert captured == row_count
    assert builder.last_rows_materialized == row_count
    assert connection.value.keys[0][2] == V2_STATE_BUILD_EVIDENCE_PAGE_SIZE - 1
    assert connection.value.keys[-1][2] == row_count - 1
    assert connection.value.keys == sorted(set(connection.value.keys))
