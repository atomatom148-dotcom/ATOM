"""Production-market acceptance; enabled only by the scheduled CI workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
import time
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from quant.v9_v1_contract import HORIZONS, MAX_ACTIVE_AGE_SECONDS
from quant.v9_v4a_evidence import (
    canonical_target_identity, deserialize_forecast_record,
    deserialize_outcome_record,
)


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
    horizon_statuses = payload.get("v9", {}).get("horizon_statuses")
    assert isinstance(horizon_statuses, list) and len(horizon_statuses) == 6
    assert horizon_statuses[0] in {"MATURE", "PROVISIONAL"}
    age = payload.get("market", {}).get("data_age")
    assert isinstance(age, (int, float)) and not isinstance(age, bool)
    assert math.isfinite(age) and 0.0 <= age <= MAX_ACTIVE_AGE_SECONDS
    forecast_age = payload.get("v9", {}).get("forecast_age")
    assert isinstance(forecast_age, (int, float)) and not isinstance(forecast_age, bool)
    assert math.isfinite(forecast_age) and 0.0 <= forecast_age <= MAX_ACTIVE_AGE_SECONDS


def _deployed_json(base_url: str, path: str, *, deadline: float | None = None) -> dict:
    """Read one deployed endpoint, retrying only transient transport failures."""

    deadline = time.monotonic() + 45 if deadline is None else deadline
    last_error = None
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            with urlopen(
                base_url.rstrip("/") + path,
                timeout=max(0.001, min(15.0, remaining)),
            ) as response:
                assert response.status == 200
                payload = json.load(response)
            assert isinstance(payload, dict)
            return payload
        except HTTPError as error:
            if error.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise AssertionError(
                    f"deployed endpoint returned non-retryable HTTP {error.code}: {path}"
                ) from error
            last_error = error
        except (AssertionError, URLError, TimeoutError,
                json.JSONDecodeError, OSError) as error:
            last_error = error
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    raise AssertionError(f"deployed endpoint remained unavailable: {path}") from last_error


def _database_read(database_url: str, operation: Callable, *, deadline: float):
    """Run a retryable operation in a fresh, explicitly read-only transaction."""

    import psycopg

    last_error = None
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining < 1.0:
            break
        connect_timeout = max(1, min(10, math.ceil(remaining)))
        statement_timeout_ms = max(1, min(10_000, int(remaining * 1000)))
        try:
            with psycopg.connect(
                database_url,
                connect_timeout=connect_timeout,
                options=f"-c statement_timeout={statement_timeout_ms}",
            ) as connection:
                connection.read_only = True
                with connection.cursor() as cursor:
                    return operation(cursor)
        except (psycopg.OperationalError, psycopg.InterfaceError,
                ConnectionError, TimeoutError) as error:
            last_error = error
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    raise AssertionError("read-only database operation remained unavailable") from last_error


def test_database_reads_force_read_only_and_bounded_timeouts(monkeypatch):
    import psycopg

    cursor = SimpleNamespace()

    class CursorContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *_args):
            return False

    class ConnectionContext:
        read_only = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return CursorContext()

    connection = ConnectionContext()
    observed = {}

    def connect(database_url, **kwargs):
        observed.update(database_url=database_url, **kwargs)
        return connection

    monkeypatch.setattr(psycopg, "connect", connect)
    assert _database_read(
        "postgresql://read-only-test",
        lambda value: value,
        deadline=time.monotonic() + 2,
    ) is cursor
    assert connection.read_only is True
    assert observed["database_url"] == "postgresql://read-only-test"
    assert 1 <= observed["connect_timeout"] <= 10
    assert observed["options"].startswith("-c statement_timeout=")


def _skip_if_xnys_closed(now: datetime | None = None) -> None:
    """Skip scheduled/manual runs outside an authoritative XNYS open minute."""

    import exchange_calendars
    import pandas

    current = pandas.Timestamp(now or datetime.now(timezone.utc))
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")
    minute = current.floor("min")
    if not exchange_calendars.get_calendar("XNYS").is_open_on_minute(minute):
        pytest.skip(f"XNYS session is closed at {minute.isoformat()}")


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


def _deployed_payload(
    *, bps=None, horizon_statuses=None, market_age=1.0, forecast_age=1.0,
):
    return {
        "final_numbers": {
            "BPS": bps if bps is not None else [1.0, None, None, None, None, None],
        },
        "market": {"data_age": market_age},
        "v9": {
            "forecast_age": forecast_age,
            "horizon_statuses": (
                horizon_statuses if horizon_statuses is not None
                else ["MATURE"] + ["UNAVAILABLE"] * 5
            ),
        },
    }


def test_deployed_response_validation_requires_health_and_finite_30s():
    _validate_deployed_health({"status":"running"})
    _validate_deployed_live(_deployed_payload())
    with pytest.raises(AssertionError):_validate_deployed_health({"status":"stopped"})
    with pytest.raises(AssertionError):
        _validate_deployed_live(_deployed_payload(bps=[1.0]))
    with pytest.raises(AssertionError):
        _validate_deployed_live(_deployed_payload(horizon_statuses=["MATURE"]))
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


def _assert_live_forecast_agreement(payload: dict, forecast) -> None:
    """Bind the visible 30S number to the exact durable 30S record."""

    live_bps = payload["final_numbers"]["BPS"][0]
    live_status = payload["v9"]["horizon_statuses"][0]
    assert isinstance(live_bps, (int, float)) and not isinstance(live_bps, bool)
    assert math.isfinite(live_bps)
    assert forecast.status in {"MATURE", "PROVISIONAL"}
    assert live_status == forecast.status
    assert isinstance(forecast.expected_return_bps, (int, float))
    assert not isinstance(forecast.expected_return_bps, bool)
    assert math.isfinite(forecast.expected_return_bps)
    assert forecast.expected_return_bps == live_bps


def test_live_30s_must_exactly_match_scoreable_persisted_forecast():
    for status in ("MATURE", "PROVISIONAL"):
        payload = _deployed_payload(
            bps=[1.25, None, None, None, None, None],
            horizon_statuses=[status] + ["UNAVAILABLE"] * 5,
        )
        _assert_live_forecast_agreement(
            payload, SimpleNamespace(status=status, expected_return_bps=1.25))
    payload = _deployed_payload(bps=[1.25, None, None, None, None, None])
    for forecast in (
        SimpleNamespace(status="MATURE", expected_return_bps=1.5),
        SimpleNamespace(status="UNAVAILABLE", expected_return_bps=1.25),
        SimpleNamespace(status="PROVISIONAL", expected_return_bps=None),
    ):
        with pytest.raises(AssertionError):
            _assert_live_forecast_agreement(payload, forecast)
    with pytest.raises(AssertionError):
        _assert_live_forecast_agreement(
            _deployed_payload(
                bps=[1.25, None, None, None, None, None],
                horizon_statuses=["PROVISIONAL"] + ["UNAVAILABLE"] * 5,
            ),
            SimpleNamespace(status="MATURE", expected_return_bps=1.25),
        )


def _poll_new_deployed_cycle(base_url: str, baseline_cutoff: float) -> dict:
    deadline = time.monotonic() + 90
    last_error = None
    while time.monotonic() < deadline:
        payload = _deployed_json(base_url, "/api/live", deadline=deadline)
        try:
            _validate_deployed_live(payload)
            cutoff = payload["v9"]["forecast_cutoff"]
            assert isinstance(cutoff, (int, float)) and not isinstance(cutoff, bool)
            assert math.isfinite(cutoff) and cutoff > baseline_cutoff
        except (AssertionError, KeyError, TypeError) as error:
            last_error = error
            time.sleep(1)
            continue
        return payload
    raise AssertionError("deployed service did not publish a new scoreable cycle") from last_error


def _logical_duplicate_surplus(database_url: str, *, deadline: float) -> tuple[int, int]:
    def read(cursor):
        cursor.execute(
            """
            SELECT
              COALESCE((SELECT sum(row_count - 1) FROM (
                 SELECT count(*) AS row_count
                 FROM public.atom_v9_v4_forecasts
                 GROUP BY symbol, cutoff_at, horizon, cycle_id, v3_model_version
                 HAVING count(*) > 1
               ) AS forecast_conflicts), 0),
              COALESCE((SELECT sum(row_count - 1) FROM (
                 SELECT count(*) AS row_count
                 FROM public.atom_v9_v4_outcomes
                 GROUP BY forecast_record_id, target_identity
                 HAVING count(*) > 1
               ) AS outcome_conflicts), 0)
            """,
            (),
        )
        return tuple(map(int, cursor.fetchone()))

    return _database_read(database_url, read, deadline=deadline)


def _assert_duplicate_surplus_unchanged(
    baseline: tuple[int, int], current: tuple[int, int],
) -> None:
    """Allow immutable historical conflicts, but reject every newly added row."""

    assert current == baseline


def test_duplicate_gate_allows_history_but_detects_growth_in_existing_group():
    _assert_duplicate_surplus_unchanged((3, 2), (3, 2))
    with pytest.raises(AssertionError):
        _assert_duplicate_surplus_unchanged((3, 2), (4, 2))
    with pytest.raises(AssertionError):
        _assert_duplicate_surplus_unchanged((3, 2), (3, 3))


def _poll_forecasts(database_url: str, cutoff_at: datetime):
    deadline = time.monotonic() + 45
    rows = ()
    while time.monotonic() < deadline:
        def read(cursor):
            cursor.execute(
                """SELECT forecast_record_hash, record_json
                   FROM public.atom_v9_v4_forecasts
                   WHERE symbol='COIN' AND cutoff_at=%s
                   ORDER BY cutoff_at, horizon, forecast_record_id""",
                (cutoff_at,),
            )
            return tuple(cursor.fetchall())

        rows = _database_read(database_url, read, deadline=deadline)
        if len(rows) >= 6:
            break
        time.sleep(1)
    assert len(rows) == 6
    return tuple(deserialize_forecast_record(
        payload, expected_hash=str(record_hash),
    ) for record_hash, payload in rows)


def _poll_verified_outcome(database_url: str, forecast):
    target_identity = canonical_target_identity(forecast)
    deadline = time.monotonic() + 90
    rows = ()
    while time.monotonic() < deadline:
        def read(cursor):
            cursor.execute(
                """SELECT outcome_record_hash, record_json
                   FROM public.atom_v9_v4_outcomes
                   WHERE forecast_record_id=%s AND target_identity=%s
                   ORDER BY created_at, outcome_record_id""",
                (forecast.forecast_record_id, target_identity),
            )
            return tuple(cursor.fetchall())

        rows = _database_read(database_url, read, deadline=deadline)
        if rows:
            break
        time.sleep(1)
    assert len(rows) == 1
    return deserialize_outcome_record(
        rows[0][1], expected_hash=str(rows[0][0]),
    )


def test_market_open_workflow_scopes_credentials_and_pins_dependencies():
    workflow = Path(".github/workflows/v9-market-open-acceptance.yml").read_text(
        encoding="utf-8"
    )
    job_header, _steps = workflow.split("    steps:", 1)
    assert "DATABASE_URL:" not in job_header
    assert "ATOM_V9_RUNTIME_DATABASE_URL" not in workflow
    assert "ATOM_V9_ACCEPTANCE_READONLY_DATABASE_URL" in workflow
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in workflow
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in workflow
    assert "--only-binary=:all:" in workflow
    requirements = Path(".github/requirements/v9-market-open.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    assert requirements == [
        "exchange-calendars==4.13.2",
        "psycopg[binary]==3.3.4",
        "pytest==9.1.1",
    ]


@market_open_only
def test_market_open_database_backed_v1_through_website_and_verified_outcome():
    _skip_if_xnys_closed()
    database_url = os.environ["DATABASE_URL"]
    base_url = os.environ["ATOM_PRODUCTION_BASE_URL"]
    _validate_deployed_health(_deployed_json(base_url, "/health"))
    initial = _deployed_json(base_url, "/api/live")
    baseline_cutoff = initial.get("v9", {}).get("forecast_cutoff")
    if (not isinstance(baseline_cutoff, (int, float)) or
            isinstance(baseline_cutoff, bool) or
            not math.isfinite(baseline_cutoff)):
        baseline_cutoff = -math.inf

    def runtime_permissions(cursor):
        cursor.execute("SELECT current_user", ())
        current_user = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT has_table_privilege(current_user,'public.atom_v9_v4_forecasts','SELECT'),
                   has_table_privilege(current_user,'public.atom_v9_v4_forecasts','INSERT'),
                   has_table_privilege(current_user,'public.atom_v9_v4_forecasts','UPDATE'),
                   has_table_privilege(current_user,'public.atom_v9_v4_forecasts','DELETE'),
                   has_table_privilege(current_user,'public.atom_v9_v4_outcomes','SELECT'),
                   has_table_privilege(current_user,'public.atom_v9_v4_outcomes','INSERT'),
                   has_table_privilege(current_user,'public.atom_v9_v4_outcomes','UPDATE'),
                   has_table_privilege(current_user,'public.atom_v9_v4_outcomes','DELETE')
            """,
            (),
        )
        return current_user, cursor.fetchone()

    current_user, privileges = _database_read(
        database_url, runtime_permissions, deadline=time.monotonic() + 45)
    assert current_user != "atom_v9_v4_runtime"
    assert privileges == (True, False, False, False, True, False, False, False)
    baseline_surplus = _logical_duplicate_surplus(
        database_url, deadline=time.monotonic() + 45)

    payload = _poll_new_deployed_cycle(base_url, float(baseline_cutoff))
    cutoff = float(payload["v9"]["forecast_cutoff"])
    market_time = datetime.fromtimestamp(
        cutoff, ZoneInfo("America/New_York"))
    assert market_time.weekday() < 5
    assert (market_time.hour, market_time.minute) >= (9, 30)
    assert (market_time.hour, market_time.minute) < (16, 0)
    cutoff_at = datetime.fromtimestamp(cutoff, timezone.utc)
    forecasts = _poll_forecasts(database_url, cutoff_at)
    assert {forecast.horizon for forecast in forecasts} == set(HORIZONS)
    assert len({forecast.logical_key for forecast in forecasts}) == 6
    assert len({forecast.cycle_id for forecast in forecasts}) == 1
    cycle_id = forecasts[0].cycle_id
    assert all(forecast.cycle_id == cycle_id for forecast in forecasts)
    assert all(forecast.cutoff_at == cutoff_at for forecast in forecasts)
    assert all(forecast.persistence_proof_eligible is True
               for forecast in forecasts)
    forecast_30s = next(
        forecast for forecast in forecasts if forecast.horizon == "30S")
    assert forecast_30s.target_endpoint.timestamp() == cutoff + 30
    _assert_live_forecast_agreement(payload, forecast_30s)

    wait_seconds = max(
        0.0, forecast_30s.target_endpoint.timestamp() - time.time())
    if wait_seconds:
        time.sleep(wait_seconds)
    outcome = _poll_verified_outcome(database_url, forecast_30s)
    target_identity = canonical_target_identity(forecast_30s)
    assert outcome.forecast_record_id == forecast_30s.forecast_record_id
    assert outcome.target_identity == target_identity
    assert outcome.target_endpoint == forecast_30s.target_endpoint
    assert outcome.previous_observation_at < outcome.target_endpoint
    assert outcome.target_endpoint <= outcome.endpoint_observation_at
    assert outcome.target_resolved_at >= outcome.endpoint_observation_at
    assert outcome.target_timing_status == "VERIFIED"
    assert outcome.proof_eligible is True
    _assert_duplicate_surplus_unchanged(
        baseline_surplus,
        _logical_duplicate_surplus(
            database_url, deadline=time.monotonic() + 45),
    )

    _validate_deployed_health(_deployed_json(base_url, "/health"))
    _validate_deployed_live(_deployed_json(base_url, "/api/live"))