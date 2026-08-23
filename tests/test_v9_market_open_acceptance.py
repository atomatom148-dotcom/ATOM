"""Production-market acceptance; enabled only by the scheduled CI workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pytest

from quant.live_market import ALPACA_LATEST_QUOTES_URL, LiveMarketState, parse_alpaca_timestamp
from quant.v9_production import (
    ImmutableV2StateProvider, PostgresV2StateBuilder, ProductionV9Runtime,
)
from quant.web import create_app


pytestmark = pytest.mark.skipif(
    os.environ.get("ATOM_MARKET_OPEN_ACCEPTANCE") != "1",
    reason="scheduled market-open acceptance only",
)


def _quote() -> tuple[tuple[float, float, float, float, float],
                      tuple[float, float, float]]:
    headers = {
        "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
    }
    with urlopen(Request(ALPACA_LATEST_QUOTES_URL, headers=headers), timeout=15) as response:
        quotes = json.load(response)["quotes"]
    coin, qqq = quotes["COIN"], quotes["QQQ"]
    return (
        (float(coin["bp"]), float(coin["ap"]), float(coin["bs"]),
         float(coin["as"]), parse_alpaca_timestamp(coin["t"])),
        (float(qqq["bp"]), float(qqq["ap"]), parse_alpaca_timestamp(qqq["t"])),
    )


def _request_json(app, path: str) -> dict:
    result = {}
    def start_response(status, headers):
        result["status"] = status
    body = b"".join(app({"PATH_INFO": path}, start_response))
    assert result["status"] == "200 OK"
    return json.loads(body)


def test_market_open_database_backed_v1_through_website_and_verified_outcome():
    import psycopg

    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user", ())
            assert cursor.fetchone()[0] == "atom_v9_v4_runtime"
            cursor.execute(
                """
                SELECT has_table_privilege(current_user,'public.atom_v9_v4_forecasts','SELECT'),
                       has_table_privilege(current_user,'public.atom_v9_v4_forecasts','INSERT'),
                       has_table_privilege(current_user,'public.atom_v9_v4_forecasts','UPDATE'),
                       has_table_privilege(current_user,'public.atom_v9_v4_forecasts','DELETE')
                """,
                (),
            )
            assert cursor.fetchone() == (True, True, False, False)

    provider = ImmutableV2StateProvider(PostgresV2StateBuilder(database_url))
    assert provider.refresh().status == "AVAILABLE"
    runtime = ProductionV9Runtime(database_url, provider)
    state = LiveMarketState(v9_cycle_handler=runtime.on_quote)
    try:
        coin, qqq = _quote()
        market_time = datetime.fromtimestamp(coin[4], ZoneInfo("America/New_York"))
        assert market_time.weekday() < 5
        assert (market_time.hour, market_time.minute) >= (9, 30)
        assert (market_time.hour, market_time.minute) < (16, 0)
        state.accept_qqq_quote(bid=qqq[0], ask=qqq[1], event_epoch=qqq[2])
        assert state.accept_quote(bid=coin[0], ask=coin[1], bid_size=coin[2],
                                  ask_size=coin[3], event_epoch=coin[4])

        deadline = time.monotonic() + 20
        second = None
        while time.monotonic() < deadline:
            candidate, qqq = _quote()
            if candidate[4] > coin[4]:
                second = candidate
                state.accept_qqq_quote(bid=qqq[0], ask=qqq[1], event_epoch=qqq[2])
                assert state.accept_quote(
                    bid=second[0], ask=second[1], bid_size=second[2],
                    ask_size=second[3], event_epoch=second[4],
                )
                break
            time.sleep(1)
        assert second is not None
        output = state.v9_output()
        assert output is not None
        assert output.v1.evidence_state_id == output.v2.state_id
        assert output.v3.cycle_id == output.v1.cycle_id
        scoreable = [item for item in output.final_numbers if item.final_bps is not None]
        assert scoreable
        payload = _request_json(create_app(state=state), "/api/live")
        assert payload["final_numbers"]["BPS"] == [
            item.final_bps for item in output.final_numbers
        ]

        forecast = next(
            item.forecast for item in output.persistence
            if item.horizon == "30S" and item.status != "FAILED"
        )
        wait_seconds = max(0.0, forecast.target_endpoint.timestamp() - time.time() + 2.0)
        time.sleep(wait_seconds)
        deadline = time.monotonic() + 20
        crossed = None
        while time.monotonic() < deadline:
            candidate, qqq = _quote()
            if candidate[4] >= forecast.target_endpoint.timestamp():
                crossed = candidate
                state.accept_qqq_quote(bid=qqq[0], ask=qqq[1], event_epoch=qqq[2])
                assert state.accept_quote(
                    bid=crossed[0], ask=crossed[1], bid_size=crossed[2],
                    ask_size=crossed[3], event_epoch=crossed[4],
                )
                break
            time.sleep(1)
        assert crossed is not None

        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT record_json FROM public.atom_v9_v4_outcomes "
                    "WHERE forecast_record_id=%s ORDER BY created_at DESC LIMIT 1",
                    (forecast.forecast_record_id,),
                )
                row = cursor.fetchone()
        assert row is not None
        outcome = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        assert outcome["target_timing_status"] == "VERIFIED"
        assert outcome["proof_eligible"] is True
    finally:
        runtime.close()

