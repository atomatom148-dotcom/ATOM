from datetime import datetime, timezone
import threading
from types import SimpleNamespace

import pytest

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import LiveMarketState
from quant.q10_options_vol import OptionObservation
from quant.v9_production import PostgresV2StateBuilder, build_live_v1
from quant.v9_v1_contract import HORIZONS, QUANT_IDS
from quant.web import dashboard_data


NOW = 1_800_000_000.0


def _live_snapshot():
    directional = SimpleNamespace(forecast_bps=tuple(float(i) for i in range(6)))
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
        for quant_id in ("q4_stat_arb", "q10_options_vol")
    }
    assert source_times == {
        "q4_stat_arb": {NOW - 2.0}, "q10_options_vol": {NOW - 3.0},
    }


@pytest.mark.parametrize("family", ("stat_arb", "options_vol"))
def test_live_v1_fails_closed_without_q4_or_q10_provider_time(family):
    snapshot = _live_snapshot()
    setattr(snapshot, family, SimpleNamespace(forecast_bps=(1.0,) * 6))
    with pytest.raises(RuntimeError, match="PROVIDER_TIMESTAMP_UNAVAILABLE"):
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
    assert connection.rollbacks == 1
    assert connection.value.closed and connection.closed