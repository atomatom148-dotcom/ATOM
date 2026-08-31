from datetime import datetime, timedelta, timezone

from quant.v4_state_worker import (
    V4_STATE_BUILD_RUNTIME_LOCK_ID,
    _submit_recovery_builds,
    _try_acquire_lease,
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
