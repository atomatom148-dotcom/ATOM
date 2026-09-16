from datetime import datetime, timedelta, timezone
import threading

import pytest

import quant.v4_state_worker as state_worker_module
from quant.evidence_outbox import V4StateBuildWorker
from quant.v9_v4d_integration import OfflineStateBuildScheduler
from quant.v4_state_worker import (
    V4_STATE_BUILD_RUNTIME_LOCK_ID,
    _submit_recovery_builds,
    _try_acquire_lease,
    run,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_recovery_retry_retains_lease_until_slow_builder_finishes(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    replacement_attempted = threading.Event()
    stop = threading.Event()
    connections = []
    workers = []
    errors = []
    lease_owner = [None]
    build_calls = []

    class OperationalError(Exception):
        pass

    class StopEvent:
        def is_set(self):
            return stop.is_set()

        def wait(self, _timeout):
            return stop.wait(.005)

    class Connection:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1
            if lease_owner[0] is self:
                lease_owner[0] = None

    def connect(_url):
        connection = Connection()
        connections.append(connection)
        return connection

    def acquire(connection):
        if connections.index(connection) >= 2:
            replacement_attempted.set()
        if lease_owner[0] is not None:
            return False
        lease_owner[0] = connection
        return True

    class Reader:
        def __init__(self, *_args, connection, **_kwargs):
            self.connection = connection
            self.calls = 0

        def recovery_state_build_candidates(self):
            self.calls += 1
            if self.calls > 1:
                assert started.wait(2)
                raise OperationalError("synthetic recovery reader failure")
            cohorts = {h: (h, h) for h in ("30S", "1M", "5M", "15M", "30M", "1H")}
            return (("COIN", cohorts, NOW),)

        def close(self):
            self.connection.close()

    class Builder:
        def __init__(self, *_args, **_kwargs):
            pass

        def prepare(self, **_candidate):
            pass

        def build_and_publish(self):
            build_calls.append(1)
            started.set()
            assert release.wait(2)
            return "INSERT"

    def make_worker(*args, **kwargs):
        worker = V4StateBuildWorker(*args, shutdown_timeout_seconds=.01, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(state_worker_module, "_try_acquire_lease", acquire)
    monkeypatch.setattr(state_worker_module, "PostgresEvidenceStore", lambda *a, **k: None)
    monkeypatch.setattr(state_worker_module, "EvidenceLedgerWorker", Reader)
    monkeypatch.setattr(state_worker_module, "PostgresV4BStateBuilder", Builder)
    monkeypatch.setattr(state_worker_module, "PostgresV4CStateBuilder", Builder)
    monkeypatch.setattr(state_worker_module, "PostgresV4StateBuilder", Builder)
    monkeypatch.setattr(state_worker_module, "V4StateBuildWorker", make_worker)

    def run_worker():
        try:
            run(database_url="synthetic", stop_event=StopEvent(), connect=connect)
        except Exception as error:
            errors.append(error)

    runner = threading.Thread(target=run_worker)
    runner.start()
    try:
        assert started.wait(2)
        assert replacement_attempted.wait(2)
        assert connections[0].close_calls == 0, "lease released during active build"
        assert connections[1].close_calls == 0
        assert lease_owner[0] is connections[0]
        assert build_calls == [1]
        stop.set()
        runner.join(1)
        assert not runner.is_alive(), "shutdown must remain bounded"
        assert connections[0].close_calls == 0
    finally:
        stop.set()
        release.set()
        runner.join(2)
        for worker in workers:
            worker.close()

    assert not errors
    assert not runner.is_alive()
    assert all(not worker._thread.is_alive() for worker in workers)
    assert connections[0].close_calls == 1
    assert connections[1].close_calls == 1
    assert lease_owner[0] is None


@pytest.mark.parametrize("reconnect", (False, True))
def test_unstarted_worker_releases_lease_once_after_final_connection_close(reconnect):
    closed = []

    class Connection:
        def __init__(self, name):
            self.name = name

        def rollback(self):
            pass

        def close(self):
            closed.append(self.name)

    class Builder:
        def rebind_connection(self, connection):
            self.connection = connection

    worker = V4StateBuildWorker(
        Builder(), OfflineStateBuildScheduler(lambda: "INSERT"),
        connection=Connection("initial"),
        connect=lambda _url: Connection("reconnected"),
        database_url="synthetic",
        on_stopped=lambda: closed.append("lease"),
    )
    if reconnect:
        worker._reconnect()
        assert closed == ["initial"]
    worker.close()
    worker.close()
    assert closed == (["initial", "reconnected", "lease"] if reconnect
                      else ["initial", "lease"])


def test_failed_thread_start_releases_state_connection_and_lease(monkeypatch):
    closed = []

    class Connection:
        def close(self):
            closed.append("state")

    def fail_start(_thread):
        raise RuntimeError("synthetic thread start failure")

    worker = V4StateBuildWorker(
        object(), OfflineStateBuildScheduler(lambda: "INSERT"),
        connection=Connection(), on_stopped=lambda: closed.append("lease"),
    )
    monkeypatch.setattr(threading.Thread, "start", fail_start)
    with pytest.raises(RuntimeError, match="synthetic thread start failure"):
        worker.start()
    worker.close()
    worker.close()
    assert closed == ["state", "lease"]


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
        def __init__(self, *_args, connection, on_stopped=None, **_kwargs):
            self.connection = connection
            self.on_stopped = on_stopped

        def start(self):
            nonlocal start_calls
            start_calls += 1
            if failure_stage == "worker_start" and start_calls == 1:
                raise OperationalError("transient worker start failure")
            starts.append(True)
            stop_event.set()

        def close(self):
            self.connection.close()
            if self.on_stopped is not None:
                self.on_stopped()

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
