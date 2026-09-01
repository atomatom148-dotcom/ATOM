"""Separate, lease-fenced V4 derived-state process.

This process has no market-data, forecast, outcome, or evidence-writer path.
It polls the existing bounded recovery reader and publishes only V4B/V4C state.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import signal
import threading
from typing import Callable

from .evidence import PostgresEvidenceStore
from .evidence_outbox import (
    EvidenceLedgerWorker,
    EvidenceOutbox,
    PostgresV4BStateBuilder,
    PostgresV4CStateBuilder,
    PostgresV4StateBuilder,
    V4StateBuildWorker,
    _transient_database_error,
)
from .v9_v4d_integration import OfflineStateBuildScheduler, OperationalMetrics


V4_STATE_BUILD_RUNTIME_LOCK_ID = int.from_bytes(b"ATOMV4SB", "big")
DEFAULT_POLL_SECONDS = 15.0


def _try_acquire_lease(connection) -> bool:
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT pg_catalog.pg_try_advisory_lock(%s)",
            (V4_STATE_BUILD_RUNTIME_LOCK_ID,),
        )
        row = cursor.fetchone()
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
        return bool(row and row[0] is True)
    except Exception:
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
        raise
    finally:
        cursor.close()


def _submit_recovery_builds(reader, worker, *, now: datetime) -> int:
    submitted = 0
    for symbol, cohorts, outcome_created_at in (
            reader.recovery_state_build_candidates()):
        worker.submit(
            symbol=symbol,
            state_as_of=max(now, outcome_created_at),
            cohorts=cohorts,
            new_outcome=True,
        )
        submitted += 1
    return submitted


def _connect(database_url: str):
    import psycopg

    return psycopg.connect(
        database_url,
        connect_timeout=5,
        keepalives=1,
        keepalives_idle=5,
        keepalives_interval=2,
        keepalives_count=3,
    )


def run(*, database_url: str, stop_event: threading.Event,
        connect: Callable = _connect, poll_seconds: float = DEFAULT_POLL_SECONDS) -> None:
    """Poll durable evidence while holding the single derived-state lease."""

    interval = max(5.0, float(poll_seconds))
    while not stop_event.is_set():
        lease_connection = None
        state_connection = None
        reader = None
        worker = None
        started = False
        try:
            lease_connection = connect(database_url)
            if not _try_acquire_lease(lease_connection):
                lease_connection.close()
                lease_connection = None
                stop_event.wait(interval)
                continue
            state_connection = connect(database_url)
            metrics = OperationalMetrics()
            reader = EvidenceLedgerWorker(
                EvidenceOutbox(metrics=metrics),
                evidence_store=PostgresEvidenceStore(
                    database_url, connection=lease_connection),
                connection=lease_connection,
                connect=connect,
                database_url=database_url,
                metrics=metrics,
                load_pending=False,
            )
            accuracy_builder = PostgresV4BStateBuilder(state_connection)
            compact_builder = PostgresV4CStateBuilder(state_connection)
            state_builder = PostgresV4StateBuilder(
                accuracy_builder, compact_builder, connection=state_connection)
            scheduler = OfflineStateBuildScheduler(
                state_builder.build_and_publish, metrics=metrics)
            worker = V4StateBuildWorker(
                state_builder,
                scheduler,
                connection=state_connection,
                connect=connect,
                database_url=database_url,
                metrics=metrics,
            )
            worker.start()
            started = True
            while not stop_event.is_set():
                _submit_recovery_builds(
                    reader, worker, now=datetime.now(timezone.utc))
                stop_event.wait(interval)
        except Exception as error:
            if (not stop_event.is_set() and
                    (started or _transient_database_error(error))):
                stop_event.wait(min(interval, 5.0))
            elif not stop_event.is_set():
                raise
        finally:
            try:
                if worker is not None:
                    worker.close()
                elif state_connection is not None:
                    state_connection.close()
            finally:
                if reader is not None:
                    reader.close()
                elif lease_connection is not None:
                    lease_connection.close()


def main() -> None:
    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    if os.environ.get("ATOM_V4_STATE_WORKER_ENABLED", "0") != "1":
        while not stop_event.wait(60.0):
            pass
        return

    database_url = os.environ["DATABASE_URL"]
    poll_seconds = float(os.environ.get(
        "ATOM_V4_STATE_POLL_SECONDS", str(DEFAULT_POLL_SECONDS)))
    run(
        database_url=database_url,
        stop_event=stop_event,
        poll_seconds=poll_seconds,
    )


if __name__ == "__main__":
    main()
