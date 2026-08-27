from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from quant.v9_production import (
    CERTIFIED_V2_RECOVERY_WITNESS,
    ImmutableV2StateProvider,
    PostgresV2StateBuilder,
    V2_CERTIFIED_RECOVERY_STATE_AS_OF,
    V2_CERTIFIED_RECOVERY_STATE_HASH,
    V2_CERTIFIED_RECOVERY_STATE_ID,
    V2_STATE_BUILD_EVIDENCE_LIMIT,
)


NOW = V2_CERTIFIED_RECOVERY_STATE_AS_OF + 86_400.0


def _candidate(**overrides):
    values = {
        "state_id": V2_CERTIFIED_RECOVERY_STATE_ID,
        "state_hash": V2_CERTIFIED_RECOVERY_STATE_HASH,
        "state_as_of": V2_CERTIFIED_RECOVERY_STATE_AS_OF,
        "state_version": CERTIFIED_V2_RECOVERY_WITNESS.state_version,
        "creation_status": "VALID",
        "top_level_status": "PROVISIONAL",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_v2_builder_uses_exact_explicit_cutoff_for_both_evidence_queries():
    class Cursor:
        def __init__(self):
            self.statements = []
            self.closed = False

        def execute(self, sql, parameters):
            self.statements.append((" ".join(sql.split()), parameters))

        def fetchone(self):
            return (NOW,)

        def fetchall(self):
            return []

        def close(self):
            self.closed = True

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.rollbacks = 0
            self.closed = False

        def cursor(self):
            return self.cursor_value

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = Connection()
    builder = PostgresV2StateBuilder(
        "postgresql://unused", connect=lambda _url: connection,
    )

    with pytest.raises(RuntimeError, match="V2_STATE_NOT_USABLE"):
        builder.build(state_as_of=V2_CERTIFIED_RECOVERY_STATE_AS_OF)

    evidence_queries = connection.cursor_value.statements[2:]
    assert len(evidence_queries) == 2
    assert all(
        parameters[3] == V2_CERTIFIED_RECOVERY_STATE_AS_OF
        for _sql, parameters in evidence_queries
    )
    assert connection.rollbacks == 1
    assert connection.cursor_value.closed and connection.closed


@pytest.mark.parametrize(
    "invalid",
    [True, "1787744574", float("nan"), 0.0, NOW + 1.0],
)
def test_v2_builder_rejects_invalid_or_future_explicit_cutoff(invalid):
    class Cursor:
        def execute(self, _sql, _parameters):
            pass

        def fetchone(self):
            return (NOW,)

        def fetchall(self):
            raise AssertionError("invalid cutoff must fail before evidence reads")

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    builder = PostgresV2StateBuilder(
        "postgresql://unused", connect=lambda _url: Connection(),
    )
    with pytest.raises(
        RuntimeError, match="V2_CERTIFIED_RECOVERY_AS_OF_INVALID",
    ):
        builder.build(state_as_of=invalid)


def test_v2_provider_bootstraps_exact_witness_after_not_found_and_overflow():
    candidate = _candidate()

    class Builder:
        last_rows_materialized = 0

        def __init__(self):
            self.calls = []

        def build(self, **kwargs):
            self.calls.append(kwargs)
            if not kwargs:
                self.last_rows_materialized = V2_STATE_BUILD_EVIDENCE_LIMIT + 1
                raise RuntimeError("V2_EVIDENCE_ROW_LIMIT_EXCEEDED")
            assert kwargs == {
                "state_as_of": V2_CERTIFIED_RECOVERY_STATE_AS_OF,
            }
            self.last_rows_materialized = 1_121
            return candidate

    class Store:
        def __init__(self):
            self.inserted = []

        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            return None, "NOT_FOUND"

        def insert(self, state):
            self.inserted.append(state)
            return "INSERTED"

    builder = Builder()
    store = Store()
    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    provider = ImmutableV2StateProvider(
        builder, store=store, utc_clock=lambda: cutoff,
    )

    snapshot = provider.refresh()

    assert snapshot.status == "AVAILABLE"
    assert snapshot.state_id == V2_CERTIFIED_RECOVERY_STATE_ID
    assert snapshot.state_as_of == V2_CERTIFIED_RECOVERY_STATE_AS_OF
    assert builder.calls == [
        {},
        {"state_as_of": V2_CERTIFIED_RECOVERY_STATE_AS_OF},
    ]
    assert store.inserted == [candidate]
    assert provider.capture(cutoff) is candidate
    telemetry = provider.metrics.snapshot()
    assert ("v2_certified_recovery_success_total", 1) in telemetry.counters
    assert (
        "v2_certified_recovery_status", "AVAILABLE"
    ) in telemetry.statuses


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("state_id", "v9v2:" + "0" * 64),
        ("state_hash", "0" * 64),
        ("state_as_of", V2_CERTIFIED_RECOVERY_STATE_AS_OF - 1.0),
        ("state_version", "V9-V2D-WRONG"),
        ("creation_status", "INVALID"),
        ("top_level_status", "UNAVAILABLE"),
    ],
)
def test_v2_provider_rejects_any_certified_witness_mismatch(field, value):
    candidate = _candidate(**{field: value})

    class Builder:
        last_rows_materialized = V2_STATE_BUILD_EVIDENCE_LIMIT + 1

        def build(self, **kwargs):
            if not kwargs:
                raise RuntimeError("V2_EVIDENCE_ROW_LIMIT_EXCEEDED")
            return candidate

    class Store:
        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            return None, "NOT_FOUND"

        def insert(self, _state):
            raise AssertionError("mismatched recovery state must not be inserted")

    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    provider = ImmutableV2StateProvider(
        Builder(), store=Store(), utc_clock=lambda: cutoff,
    )

    snapshot = provider.refresh()

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.error_code == "V2_CERTIFIED_RECOVERY_MISMATCH"
    with pytest.raises(RuntimeError, match="V2_STATE_UNAVAILABLE"):
        provider.capture(cutoff)


def test_v2_provider_does_not_recover_for_non_overflow_build_failure():
    class Builder:
        last_rows_materialized = 0

        def __init__(self):
            self.calls = []

        def build(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise AssertionError("non-overflow failure must not use recovery")
            raise RuntimeError("temporary database failure")

    class Store:
        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            return None, "NOT_FOUND"

        def insert(self, _state):
            raise AssertionError("failed build must not be inserted")

    builder = Builder()
    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    provider = ImmutableV2StateProvider(
        builder, store=Store(), utc_clock=lambda: cutoff,
    )

    snapshot = provider.refresh()

    assert snapshot.status == "UNAVAILABLE"
    assert snapshot.error_code == "RuntimeError"
    assert builder.calls == [{}]


def test_retained_overflow_uses_normal_refresh_interval():
    prior = _candidate(state_as_of=V2_CERTIFIED_RECOVERY_STATE_AS_OF - 1.0)

    class Builder:
        last_rows_materialized = V2_STATE_BUILD_EVIDENCE_LIMIT + 1

        def build(self):
            raise RuntimeError("V2_EVIDENCE_ROW_LIMIT_EXCEEDED")

    class Store:
        def latest(self, *, requested_cutoff):
            assert requested_cutoff == NOW
            return prior, "FOUND"

        def insert(self, _state):
            raise AssertionError("overflow must not insert")

    class StopAfterFirstWait:
        def __init__(self):
            self.seconds = []

        def is_set(self):
            return False

        def wait(self, seconds):
            self.seconds.append(seconds)
            return True

    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    provider = ImmutableV2StateProvider(
        Builder(), store=Store(), utc_clock=lambda: cutoff,
    )
    stop = StopAfterFirstWait()
    thread = provider.start(interval_seconds=3_600.0, stop_event=stop)
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert stop.seconds == [3_600.0]
    assert provider.capture(cutoff) is prior
