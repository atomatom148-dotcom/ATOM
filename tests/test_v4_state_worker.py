from datetime import datetime, timedelta, timezone

import pytest

import quant.v4_state_worker as state_worker_module
from quant.v4_state_worker import (
    V4_STATE_BUILD_RUNTIME_LOCK_ID,
    _submit_recovery_builds,
    _try_acquire_lease,
    run,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_state_builder_lease_is_session_scoped_and_committed():
    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchone(self):
            return (True,)

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.commits = 0

        def cursor(self):
            return self.cursor_value

        def commit(self):
            self.commits += 1

    connection = Connection()

    assert _try_acquire_lease(connection) is True
    assert connection.cursor_value.calls == [(
        "SELECT pg_catalog.pg_try_advisory_lock(%s)",
        (V4_STATE_BUILD_RUNTIME_LOCK_ID,),
    )]
    assert connection.commits == 1


def test_recovery_candidates_submit_without_changing_identity():
    cohorts = {
        horizon: (f"cohort-{horizon}", horizon * 8)
        for horizon in ("30S", "1M", "5M", "15M", "30M", "1H")
    }

    class Reader:
        def recovery_state_build_candidates(self):
            return (("COIN", cohorts, NOW + timedelta(seconds=1)),)

    class Worker:
        def __init__(self):
            self.calls = []

        def submit(self, **candidate):
            self.calls.append(candidate)

    worker = Worker()
    later = NOW + timedelta(seconds=2)

    assert _submit_recovery_builds(Reader(), worker, now=later) == 1
    assert worker.calls == [{
        "symbol": "COIN",
        "state_as_of": later,
        "cohorts": cohorts,
        "new_outcome": True,
    }]


@pytest.mark.parametrize(
    "failure_stage",
    ("lease_connect", "state_connect", "reader_init", "worker_start"),
)
def test_worker_retries_transient_startup_connections_and_releases_lease(
        monkeypatch, failure_stage):
    class OperationalError(Exception):
        pass

    class StopEvent:
        def __init__(self):
            self.stopped = False
            self.waits = []

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        def wait(self, timeout):
            self.waits.append(timeout)
            return self.stopped

    class Connection:
        def __init__(self, name):
            self.name = name
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    stop_event = StopEvent()
    connections = []
    connect_calls = 0

    def connect(_database_url):
        nonlocal connect_calls
        connect_calls += 1
        if ((failure_stage == "lease_connect" and connect_calls == 1) or
                (failure_stage == "state_connect" and connect_calls == 2)):
            raise OperationalError("transient startup failure")
        connection = Connection(f"connection-{connect_calls}")
        connections.append(connection)
        return connection

    acquired = []
    monkeypatch.setattr(
        state_worker_module, "_try_acquire_lease",
        lambda connection: acquired.append(connection) or True)
    monkeypatch.setattr(
        state_worker_module, "OperationalMetrics", lambda: object())
    monkeypatch.setattr(
        state_worker_module, "EvidenceOutbox", lambda **_kwargs: object())
    monkeypatch.setattr(
        state_worker_module, "PostgresEvidenceStore",
        lambda *_args, **_kwargs: object())

    reader_calls = 0

    class Reader:
        def __init__(self, *_args, connection, **_kwargs):
            nonlocal reader_calls
            reader_calls += 1
            if failure_stage == "reader_init" and reader_calls == 1:
                raise OperationalError("transient reader initialization failure")
            self.connection = connection

        def close(self):
            self.connection.close()

    class Builder:
        def __init__(self, connection):
            self.connection = connection

        def build_and_publish(self):
            return "INSERT"

    class CombinedBuilder:
        def __init__(self, *_args, connection):
            self.connection = connection

        def build_and_publish(self):
            return "INSERT"

    class Scheduler:
        def __init__(self, *_args, **_kwargs):
            pass

    starts = []
    start_calls = 0

    class StateWorker:
        def __init__(self, *_args, connection, **_kwargs):
            self.connection = connection

        def start(self):
            nonlocal start_calls
            start_calls += 1
            if failure_stage == "worker_start" and start_calls == 1:
                raise OperationalError("transient worker start failure")
            starts.append(True)
            stop_event.set()

        def close(self):
            self.connection.close()

    monkeypatch.setattr(state_worker_module, "EvidenceLedgerWorker", Reader)
    monkeypatch.setattr(state_worker_module, "PostgresV4BStateBuilder", Builder)
    monkeypatch.setattr(state_worker_module, "PostgresV4CStateBuilder", Builder)
    monkeypatch.setattr(
        state_worker_module, "PostgresV4StateBuilder", CombinedBuilder)
    monkeypatch.setattr(
        state_worker_module, "OfflineStateBuildScheduler", Scheduler)
    monkeypatch.setattr(state_worker_module, "V4StateBuildWorker", StateWorker)

    run(
        database_url="postgresql://runtime@db.example/atom",
        stop_event=stop_event,
        connect=connect,
        poll_seconds=5.0,
    )

    assert starts == [True]
    assert stop_event.waits == [5.0]
    assert all(connection.close_calls == 1 for connection in connections)
    if failure_stage == "lease_connect":
        assert [connection.name for connection in acquired] == ["connection-2"]
    elif failure_stage == "state_connect":
        assert [connection.name for connection in acquired] == [
            "connection-1", "connection-3"]
    else:
        assert [connection.name for connection in acquired] == [
            "connection-1", "connection-3"]
