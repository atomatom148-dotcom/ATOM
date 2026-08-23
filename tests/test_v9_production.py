from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import LiveMarketState
from quant.v9_production import PostgresV2StateBuilder, build_live_v1
from quant.v9_v1_contract import HORIZONS, QUANT_IDS
from quant.web import dashboard_data


NOW = 1_800_000_000.0


def _live_snapshot():
    directional = SimpleNamespace(forecast_bps=tuple(float(i) for i in range(6)))
    magnitude = SimpleNamespace(volatility_bps=tuple(float(i + 1) for i in range(6)))
    return SimpleNamespace(
        history=MidpointHistory((MidpointObservation(NOW, 100.0),)),
        momentum=directional,
        mean_reversion=directional,
        volatility=magnitude,
        stat_arb=directional,
        microstructure=directional,
        volume_liquidity=directional,
        relative_value=directional,
        cross_asset=directional,
        factor=directional,
        options_vol=directional,
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
