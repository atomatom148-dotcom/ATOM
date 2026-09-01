"""SIM-4 regression: PostgreSQL ``void`` reaches psycopg as ``("",)``.

``SELECT pg_advisory_xact_lock(...)`` returns one row whose single column has
the PostgreSQL ``void`` type.  psycopg 3 has no loader for ``void`` and falls
through to the text loader, so the fetched row is ``("",)`` in production.
Both SIM-4 fetch sites must accept that representation alongside the already
accepted ``None`` / ``(None,)`` shapes and must keep rejecting everything else.

This module covers the worker's deadline-closure fence, which existing tests
replace with a stub and therefore never exercised.  The entry-store site is
covered in ``tests/test_v9_sim4_entry.py``.
"""

import pytest

from quant.v9_sim4_worker import (
    SIM4_ACTIVATION_LOCK_KEY,
    PaperTradingCredentials,
    Sim4GenerationFailed,
    SimulationEntryWorker,
)


PROJECT_REF = "abcdefghijklmnopqrst"
OWNER_PID = 4321
CLOSING_DEADLINE_NS = 1_000_000_000


class ScriptedCursor:
    def __init__(self, steps):
        self.steps = list(steps)
        self.executed = []
        self.current = []
        self.close_calls = 0

    def execute(self, sql, parameters=None):
        self.executed.append((sql, parameters))
        if not self.steps:
            raise AssertionError(f"unexpected SQL: {sql}")
        expected, rows = self.steps.pop(0)
        if expected not in sql:
            raise AssertionError(f"expected {expected!r}, got {sql!r}")
        self.current = list(rows)

    def fetchone(self):
        return None if not self.current else self.current.pop(0)

    def fetchall(self):
        rows = self.current
        self.current = []
        return rows

    def close(self):
        self.close_calls += 1


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.autocommit = True
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


def build_runtime(connection):
    runtime = SimulationEntryWorker(
        lambda: connection,
        PROJECT_REF,
        PaperTradingCredentials("key", "secret"),
        monotonic_ns=lambda: 0,
        monotonic=lambda: 0.0,
    )
    runtime._owner_connection = connection
    runtime._owner_acquired = True
    runtime._owner_backend_pid = OWNER_PID
    return runtime


def deadline_steps(lock_rows):
    return [
        ("pg_backend_pid", [(OWNER_PID,)]),
        ("lock_timeout", []),
        ("statement_timeout", []),
        ("pg_advisory_xact_lock", lock_rows),
        ("atom_v9_sim4_read_intent_admission_fence", [(17,)]),
    ]


@pytest.mark.parametrize("lock_rows", ([], [(None,)], [("",)]))
def test_deadline_fence_accepts_every_postgres_void_representation(lock_rows):
    cursor = ScriptedCursor(deadline_steps(lock_rows))
    connection = FakeConnection(cursor)
    runtime = build_runtime(connection)

    assert runtime._capture_deadline_publication_fence(CLOSING_DEADLINE_NS) == 17

    lock_sql, lock_parameters = cursor.executed[3]
    assert lock_sql == "SELECT pg_advisory_xact_lock(%s::bigint)"
    assert lock_parameters == (SIM4_ACTIVATION_LOCK_KEY,)
    assert "atom_v9_sim4_read_intent_admission_fence" in cursor.executed[4][0]
    assert (connection.commit_calls, connection.rollback_calls) == (1, 0)
    assert connection.autocommit is True
    assert runtime.telemetry.snapshot()["deadline_closure_failures"] == 0


@pytest.mark.parametrize(
    "lock_rows", ([("x",)], [(True,)], [(0,)], [(None, None)], [("", "")]),
)
def test_deadline_fence_still_rejects_malformed_lock_results(lock_rows):
    cursor = ScriptedCursor(deadline_steps(lock_rows))
    connection = FakeConnection(cursor)
    runtime = build_runtime(connection)

    with pytest.raises(Sim4GenerationFailed):
        runtime._capture_deadline_publication_fence(CLOSING_DEADLINE_NS)

    # The fence reader must never run after a malformed lock result.
    assert len(cursor.executed) == 4
    assert (connection.commit_calls, connection.rollback_calls) == (0, 1)
    assert connection.autocommit is True
    assert runtime.telemetry.snapshot()["deadline_closure_failures"] == 1
