"""Production-market acceptance; enabled only by the scheduled CI workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
import time
from urllib.request import Request, urlopen
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from quant.live_market import ALPACA_LATEST_QUOTES_URL, LiveMarketState, parse_alpaca_timestamp
from quant.v9_production import (
    ImmutableV2StateProvider, PostgresV2StateBuilder, ProductionV9Runtime,
)
from quant.v9_v1_contract import MAX_ACTIVE_AGE_SECONDS
from quant.web import create_app


market_open_only = pytest.mark.skipif(
    os.environ.get("ATOM_MARKET_OPEN_ACCEPTANCE") != "1",
    reason="scheduled market-open acceptance only",
)


def _require_fresh_quote(event_epoch: float, now_epoch: float) -> None:
    age = now_epoch - event_epoch
    assert math.isfinite(age)
    assert 0.0 <= age <= MAX_ACTIVE_AGE_SECONDS


def _scoreable_30s(output):
    v3 = next(item for item in output.v3.horizon_results if item.horizon == "30S")
    final = next(item for item in output.final_numbers if item.horizon == "30S")
    persisted = next(item for item in output.persistence if item.horizon == "30S")
    assert v3.status != "UNAVAILABLE"
    assert v3.expected_return_bps is not None and math.isfinite(v3.expected_return_bps)
    assert final.final_bps is not None and math.isfinite(final.final_bps)
    assert final.final_bps == v3.expected_return_bps
    assert persisted.status != "FAILED"
    assert persisted.forecast.persistence_proof_eligible is True
    return persisted.forecast


def _validate_deployed_health(payload: dict) -> None:
    assert payload.get("status") == "running"


def _validate_deployed_live(payload: dict) -> None:
    bps = payload.get("final_numbers", {}).get("BPS")
    assert isinstance(bps, list) and len(bps) == 6
    assert (isinstance(bps[0], (int, float)) and not isinstance(bps[0], bool)
            and math.isfinite(bps[0]))
    age = payload.get("market", {}).get("data_age")
    assert isinstance(age, (int, float)) and not isinstance(age, bool)
    assert math.isfinite(age) and 0.0 <= age <= MAX_ACTIVE_AGE_SECONDS
    forecast_age = payload.get("v9", {}).get("forecast_age")
    assert isinstance(forecast_age, (int, float)) and not isinstance(forecast_age, bool)
    assert math.isfinite(forecast_age) and 0.0 <= forecast_age <= MAX_ACTIVE_AGE_SECONDS


def _deployed_json(base_url: str, path: str) -> dict:
    with urlopen(base_url.rstrip("/") + path, timeout=15) as response:
        assert response.status == 200
        return json.load(response)


def test_quote_freshness_accepts_fresh_and_rejects_stale_or_future():
    _require_fresh_quote(95.0, 100.0)
    with pytest.raises(AssertionError):
        _require_fresh_quote(89.999, 100.0)
    with pytest.raises(AssertionError):
        _require_fresh_quote(100.001, 100.0)


def _acceptance_output(*, scoreable: bool):
    value = 1.0 if scoreable else None
    status = "AVAILABLE" if scoreable else "UNAVAILABLE"
    forecast = SimpleNamespace(persistence_proof_eligible=scoreable)
    return SimpleNamespace(
        v3=SimpleNamespace(horizon_results=(SimpleNamespace(
            horizon="30S",status=status,expected_return_bps=value),)),
        final_numbers=(SimpleNamespace(horizon="30S",final_bps=value),),
        persistence=(SimpleNamespace(horizon="30S",status="INSERT",forecast=forecast),),
    )


def test_30s_scoreability_accepts_complete_and_rejects_unavailable():
    assert _scoreable_30s(_acceptance_output(scoreable=True)).persistence_proof_eligible
    with pytest.raises(AssertionError):
        _scoreable_30s(_acceptance_output(scoreable=False))


def test_30s_scoreability_rejects_finite_mismatched_final_bps():
    output = _acceptance_output(scoreable=True)
    output.final_numbers[0].final_bps = 2.0
    with pytest.raises(AssertionError):
        _scoreable_30s(output)


def _deployed_payload(*, bps=None, market_age=1.0, forecast_age=1.0):
    return {"final_numbers":{"BPS":bps or [1.0,None,None,None,None,None]},
            "market":{"data_age":market_age}, "v9":{"forecast_age":forecast_age}}


def test_deployed_response_validation_requires_health_and_finite_30s():
    _validate_deployed_health({"status":"running"})
    _validate_deployed_live(_deployed_payload())
    with pytest.raises(AssertionError):_validate_deployed_health({"status":"stopped"})
    with pytest.raises(AssertionError):
        _validate_deployed_live(_deployed_payload(bps=[1.0]))
    with pytest.raises(AssertionError):
        _validate_deployed_live(_deployed_payload(
            bps=[None, 1.0, None, None, None, None]))


def test_deployed_response_validation_rejects_stale_v9_with_fresh_market():
    with pytest.raises(AssertionError):
        _validate_deployed_live(_deployed_payload(
            market_age=1.0, forecast_age=MAX_ACTIVE_AGE_SECONDS + 0.001))


def test_deployed_response_validation_rejects_future_market_timestamp():
    with pytest.raises(AssertionError):
        _validate_deployed_live(_deployed_payload(market_age=-0.001))


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


@market_open_only
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
        _require_fresh_quote(coin[4], time.time())
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
                _require_fresh_quote(second[4], time.time())
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
        forecast = _scoreable_30s(output)
        payload = _request_json(create_app(state=state), "/api/live")
        assert payload["final_numbers"]["BPS"] == [
            item.final_bps for item in output.final_numbers
        ]

        wait_seconds = max(0.0, forecast.target_endpoint.timestamp() - time.time() + 2.0)
        time.sleep(wait_seconds)
        deadline = time.monotonic() + 20
        crossed = None
        # The accepted one-second quant-cycle observations remain consecutive:
        # polling quotes are display-only until the first observation at/after target.
        while time.monotonic() < deadline:
            candidate, qqq = _quote()
            if candidate[4] >= forecast.target_endpoint.timestamp():
                crossed = candidate
                _require_fresh_quote(crossed[4], time.time())
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

        base_url = os.environ["ATOM_PRODUCTION_BASE_URL"]
        _validate_deployed_health(_deployed_json(base_url, "/health"))
        _validate_deployed_live(_deployed_json(base_url, "/api/live"))
    finally:
        runtime.close()
