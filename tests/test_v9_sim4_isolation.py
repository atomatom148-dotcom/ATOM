"""Security and deployment-isolation tests for the isolated SIM-4 runtime."""

from __future__ import annotations

import ast
from collections import deque
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import threading
import traceback
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

from quant import web
from quant import v9_sim4_worker as worker
from quant.v9_sim1_contract import (
    build_simulation_trade_intent,
    serialize_simulation_trade_intent,
)
from quant.v9_sim4_entry import (
    INSERTED,
    SIM4_QUOTE_SOURCE_SPEC,
    SIM_ENTRY_RUNTIME_ROLE,
    SIM_INSTALLATION_ID,
    SIM_PUBLISHER_RUNTIME_ROLE,
    PublishedSimulationIntent,
    SimulationDatabaseConfigurationError,
    SimulationEntryBackendError,
    SimulationEntryInstallationError,
    SimulationEntryRoleError,
    SimulationEntryStateError,
    SimulationEntryStore,
    build_simulation_entry_record,
    build_simulation_executable_quote,
    datetime_to_epoch_nanoseconds,
    discover_supabase_project_ref,
    horizon_advisory_lock_key,
    serialize_simulation_entry_record,
    validate_simulator_database_url,
)
from quant.v9_sim5_resolution import RESOLUTION_WINDOW_SECONDS


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/027_create_v9_sim_entries.sql"
ENTRY_SOURCE = ROOT / "quant/v9_sim4_entry.py"
WORKER_SOURCE = ROOT / "quant/v9_sim4_worker.py"
WEB_SOURCE = ROOT / "quant/web.py"
SQL = MIGRATION.read_text(encoding="utf-8")
NORMAL_SQL = " ".join(SQL.split())

# Migration 027 deliberately refuses every production-shaped cluster role.
# The legacy PostgreSQL tests create such a role without dropping it, so this
# one clean-room bootstrap must execute first while preserving all other test
# ordering.  Self-registration makes this test module's narrowly scoped hook
# available during the final collection-order pass.
pytest_plugins = [__name__]
POSTGRES_BOOTSTRAP_TEST_NAME = (
    "test_bootstrap_executes_in_dedicated_disposable_postgres_database")

SIM_PROJECT_REF = "abcdefghijklmnopqrst"
PRODUCTION_PROJECT_REF = "zyxwvutsrqponmlkjihg"
WORKER_T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
PAPER_API_KEY_ID = "paper-data-key-id"
PAPER_API_SECRET_KEY = "paper-data-secret-key"


def paper_credentials():
    return worker.PaperTradingCredentials(
        PAPER_API_KEY_ID,
        PAPER_API_SECRET_KEY,
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    bootstrap_items = [
        item for item in items
        if item.name == POSTGRES_BOOTSTRAP_TEST_NAME
        and Path(str(item.path)).resolve() == Path(__file__).resolve()
    ]
    if len(bootstrap_items) != 1:
        return
    bootstrap = bootstrap_items[0]
    items.remove(bootstrap)
    items.insert(0, bootstrap)


def direct_dsn(role: str, project_ref: str = SIM_PROJECT_REF,
               *, sslmode: str = "require", port: int = 5432) -> str:
    return (
        f"postgresql://{role}:sim-secret@db.{project_ref}.supabase.co:"
        f"{port}/postgres?sslmode={sslmode}"
    )


def pooler_dsn(role: str, project_ref: str = SIM_PROJECT_REF,
               *, sslmode: str = "verify-full", port: int = 5432) -> str:
    return (
        f"postgresql://{role}.{project_ref}:sim-secret@"
        f"aws-0-us-west-1.pooler.supabase.com:{port}/postgres?sslmode={sslmode}"
    )


class ScriptedCursor:
    def __init__(self, *, one=(), all_rows=()):
        self._one = iter(one)
        self._all = iter(all_rows)
        self.executions: list[tuple[str, object]] = []
        self.closed = False

    def execute(self, statement, parameters=None):
        self.executions.append((statement, parameters))

    def fetchone(self):
        return next(self._one, None)

    def fetchall(self):
        return next(self._all, [])

    def close(self):
        self.closed = True


class ScriptedConnection:
    def __init__(self, cursor: ScriptedCursor):
        self.cursor_value = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class WorkerTransactionCursor:
    """Cursor that keeps backend-authority probes separate from row scripts."""

    def __init__(self, connection):
        self._connection = connection
        self._rows = None
        self.executions: list[tuple[str, object]] = []
        self.closed = False

    def execute(self, statement, parameters=None):
        self.executions.append((statement, parameters))

    def _scripted_rows(self):
        if self._rows is None:
            rows = (
                self._connection._cursor_rows.popleft()
                if self._connection._cursor_rows else ()
            )
            self._rows = iter(rows)
        return self._rows

    def fetchone(self):
        if self.executions[-1][0] == worker._BACKEND_PID_SQL:
            return (self._connection.backend_pid,)
        return next(self._scripted_rows(), None)

    def fetchall(self):
        return list(self._scripted_rows())

    def close(self):
        self.closed = True


class WorkerTransactionConnection:
    """Small transaction/session double for worker ordering regressions."""

    def __init__(self, *cursor_rows):
        self._cursor_rows = deque(cursor_rows)
        self.cursors: list[WorkerTransactionCursor] = []
        self.backend_pid = 4321
        self.autocommit = True
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        cursor = WorkerTransactionCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def build_worker_intent(index: int = 1, *, eligible_at=WORKER_T0,
                        final_bps=1.25, source_v3_status="AVAILABLE"):
    return build_simulation_trade_intent(
        source_cycle_id=f"isolation-cycle-{index}",
        source_forecast_record_id=f"v9v4f:isolation-{index}",
        source_forecast_record_hash=f"{index % 16:x}" * 64,
        source_v2_state_id=f"v9v2:isolation-{index}",
        source_v2_state_hash=f"{(index + 1) % 16:x}" * 64,
        source_v3_contract_version="V3-C",
        source_v3_model_version="V3-M",
        cutoff_at=eligible_at - timedelta(seconds=1),
        eligible_at=eligible_at,
        horizon="30S",
        horizon_seconds=30,
        final_bps=final_bps,
        source_v3_status=source_v3_status,
    )


def build_worker_quote(*, accepted_at=WORKER_T0 + timedelta(microseconds=1)):
    return build_simulation_executable_quote(
        source_spec=SIM4_QUOTE_SOURCE_SPEC,
        symbol="COIN",
        provider_event_ns=datetime_to_epoch_nanoseconds(WORKER_T0) + 1,
        accepted_at=accepted_at,
        bid=100.0,
        ask=100.25,
        bid_size=2.0,
        ask_size=3.0,
    )


def entry_database_row(entry):
    quote = entry.quote
    return (
        entry.entry_id, entry.entry_hash, entry.contract_version,
        entry.canonicalization_version, entry.simulator_version, entry.symbol,
        entry.horizon, entry.horizon_seconds, entry.intent_id,
        entry.publication_at, entry.entry_deadline_at, entry.decision,
        entry.intent_status, entry.entry_status, entry.quantity_shares,
        entry.blocking_entry_id,
        None if quote is None else quote.quote_id,
        None if quote is None else quote.quote_hash,
        None if quote is None else quote.source_spec,
        None if quote is None else quote.provider_event_ns,
        None if quote is None else quote.accepted_at,
        entry.entry_price,
        serialize_simulation_entry_record(entry),
    )


def make_authoritative_worker(
        connection, *, monotonic_ns=lambda: 0, monotonic=lambda: 0.0,
        sim5_enabled=False):
    runtime = worker.SimulationEntryWorker(
        lambda: connection,
        SIM_PROJECT_REF,
        paper_credentials(),
        utc_clock=lambda: WORKER_T0,
        monotonic_ns=monotonic_ns,
        monotonic=monotonic,
        sim5_enabled=sim5_enabled,
    )
    runtime._owner_connection = connection
    runtime._owner_acquired = True
    runtime._owner_backend_pid = 4321
    runtime._anchor = worker.MonotonicUTCAnchor(
        0, datetime_to_epoch_nanoseconds(WORKER_T0) // 1_000)
    runtime._runtime_started_at = WORKER_T0 - timedelta(seconds=10)
    runtime._runtime_started_epoch_ns = (
        datetime_to_epoch_nanoseconds(runtime._runtime_started_at))
    return runtime


@pytest.mark.parametrize(
    ("url", "role", "endpoint_kind"),
    (
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE),
         SIM_PUBLISHER_RUNTIME_ROLE, "DIRECT"),
        (pooler_dsn(SIM_PUBLISHER_RUNTIME_ROLE),
         SIM_PUBLISHER_RUNTIME_ROLE, "SESSION_POOLER"),
        (direct_dsn(SIM_ENTRY_RUNTIME_ROLE, sslmode="verify-ca"),
         SIM_ENTRY_RUNTIME_ROLE, "DIRECT"),
        (pooler_dsn(SIM_ENTRY_RUNTIME_ROLE),
         SIM_ENTRY_RUNTIME_ROLE, "SESSION_POOLER"),
    ),
)
def test_shared_database_validator_accepts_only_exact_role_bound_session_dsns(
        url, role, endpoint_kind):
    identity = validate_simulator_database_url(
        url, project_ref=SIM_PROJECT_REF, required_role=role)

    assert identity.project_ref == SIM_PROJECT_REF
    assert identity.role == role
    assert identity.endpoint_kind == endpoint_kind
    assert identity.port == 5432
    assert identity.database == "postgres"
    assert discover_supabase_project_ref(url) == SIM_PROJECT_REF


@pytest.mark.parametrize(
    "url,project_ref,required_role",
    (
        (direct_dsn(SIM_ENTRY_RUNTIME_ROLE), SIM_PROJECT_REF,
         SIM_PUBLISHER_RUNTIME_ROLE),
        (pooler_dsn(SIM_PUBLISHER_RUNTIME_ROLE), SIM_PROJECT_REF,
         SIM_ENTRY_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE, PRODUCTION_PROJECT_REF),
         SIM_PROJECT_REF, SIM_PUBLISHER_RUNTIME_ROLE),
        ("postgresql://atom_v9_sim_runtime:secret@example.com:5432/postgres"
         "?sslmode=require", SIM_PROJECT_REF, SIM_PUBLISHER_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE, port=6543), SIM_PROJECT_REF,
         SIM_PUBLISHER_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE).replace("?sslmode=require", ""),
         SIM_PROJECT_REF, SIM_PUBLISHER_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE, sslmode="prefer"),
         SIM_PROJECT_REF, SIM_PUBLISHER_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE) + "&sslmode=verify-full",
         SIM_PROJECT_REF, SIM_PUBLISHER_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE).replace("/postgres", "/other"),
         SIM_PROJECT_REF, SIM_PUBLISHER_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE), "UPPERCASEPROJECTREF",
         SIM_PUBLISHER_RUNTIME_ROLE),
        (direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE), SIM_PROJECT_REF,
         "atom_v9_v4_runtime"),
    ),
)
def test_shared_database_validator_fails_closed_for_ambiguous_or_cross_role_dsn(
        url, project_ref, required_role):
    with pytest.raises(SimulationDatabaseConfigurationError):
        validate_simulator_database_url(
            url, project_ref=project_ref, required_role=required_role)


def test_project_discovery_never_trusts_query_parameters_or_malformed_supabase_names():
    assert discover_supabase_project_ref(
        "postgresql://user:secret@example.com:5432/postgres"
        f"?project_ref={SIM_PROJECT_REF}"
    ) is None
    malformed = (
        "postgresql://atom_v9_sim_runtime.short:secret@"
        "aws-0.pooler.supabase.com:5432/postgres?sslmode=require"
    )
    with pytest.raises(SimulationDatabaseConfigurationError):
        discover_supabase_project_ref(malformed)


def test_entry_store_startup_proves_role_session_installation_backend_and_sidecar():
    cursor = ScriptedCursor(
        one=((SIM_ENTRY_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE, 4123),
             (True, True)),
        all_rows=([(SIM_INSTALLATION_ID, SIM_PROJECT_REF)],),
    )
    store = SimulationEntryStore(
        ScriptedConnection(cursor), project_ref=SIM_PROJECT_REF)

    assert store.verify_startup_on_cursor(cursor) == 4123
    assert store.backend_pid == 4123
    assert cursor.executions[0] == (
        "SELECT current_user, session_user, pg_backend_pid()", None)
    assert "FROM public.atom_v9_sim_installation" in cursor.executions[1][0]
    assert "LEFT JOIN public.atom_v9_sim_intent_publications" in cursor.executions[2][0]


@pytest.mark.parametrize(
    "authority,error",
    (
        ((SIM_PUBLISHER_RUNTIME_ROLE, SIM_PUBLISHER_RUNTIME_ROLE, 10),
         SimulationEntryRoleError),
        ((SIM_ENTRY_RUNTIME_ROLE, SIM_PUBLISHER_RUNTIME_ROLE, 10),
         SimulationEntryRoleError),
        ((SIM_ENTRY_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE, 11),
         SimulationEntryBackendError),
    ),
)
def test_entry_store_rejects_publisher_set_role_and_backend_replacement(authority, error):
    cursor = ScriptedCursor(one=(authority,))
    store = SimulationEntryStore(
        ScriptedConnection(cursor), project_ref=SIM_PROJECT_REF,
        expected_backend_pid=10)
    with pytest.raises(error):
        store.verify_startup_on_cursor(cursor)


def test_entry_store_rejects_wrong_installation_or_incomplete_publication_sidecar():
    wrong_install = ScriptedCursor(
        one=((SIM_ENTRY_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE, 10),),
        all_rows=([(SIM_INSTALLATION_ID, PRODUCTION_PROJECT_REF)],),
    )
    with pytest.raises(SimulationEntryInstallationError):
        SimulationEntryStore(
            ScriptedConnection(wrong_install), project_ref=SIM_PROJECT_REF,
        ).verify_startup_on_cursor(wrong_install)

    missing_sidecar = ScriptedCursor(
        one=((SIM_ENTRY_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE, 10),
             (False, True)),
        all_rows=([(SIM_INSTALLATION_ID, SIM_PROJECT_REF)],),
    )
    with pytest.raises(SimulationEntryStateError):
        SimulationEntryStore(
            ScriptedConnection(missing_sidecar), project_ref=SIM_PROJECT_REF,
        ).verify_startup_on_cursor(missing_sidecar)


def valid_web_environment(**changes):
    values = {
        "DATABASE_URL": direct_dsn(
            "atom_v9_v4_runtime", PRODUCTION_PROJECT_REF),
        web.SIMULATOR_DATABASE_URL_ENV: direct_dsn(
            SIM_PUBLISHER_RUNTIME_ROLE),
        web.SIMULATOR_PROJECT_REF_ENV: SIM_PROJECT_REF,
    }
    values.update(changes)
    return values


def test_web_publisher_factory_keeps_production_and_simulator_identity_separate():
    cursor = ScriptedCursor(one=((
        SIM_PUBLISHER_RUNTIME_ROLE, SIM_INSTALLATION_ID, SIM_PROJECT_REF),))
    connection = ScriptedConnection(cursor)
    calls = []

    environment = valid_web_environment()
    configured = web._configured_simulator_connection_factory(
        environment, lambda url: calls.append(url) or connection)
    factory = web._isolated_simulator_connection_factory(
        environment, configured)

    assert callable(factory)
    assert calls == []
    assert factory() is connection
    assert calls == [direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE)]
    assert cursor.executions == [(
        "SELECT current_user, installation_id, project_ref "
        "FROM public.atom_v9_sim_installation WHERE installation_id = %s",
        (SIM_INSTALLATION_ID,),
    )]
    assert connection.commits == 1
    assert connection.rollbacks == 0


@pytest.mark.parametrize(
    "environment",
    (
        {},
        valid_web_environment(**{web.SIMULATOR_DATABASE_URL_ENV: ""}),
        valid_web_environment(**{web.SIMULATOR_PROJECT_REF_ENV: ""}),
        valid_web_environment(DATABASE_URL=""),
        valid_web_environment(DATABASE_URL=direct_dsn(
            "atom_v9_v4_runtime", SIM_PROJECT_REF)),
        valid_web_environment(DATABASE_URL="postgresql://prod:secret@example.com:5432/db"),
        valid_web_environment(**{web.SIMULATOR_DATABASE_URL_ENV:
                                direct_dsn(SIM_ENTRY_RUNTIME_ROLE)}),
        valid_web_environment(**{web.SIMULATOR_DATABASE_URL_ENV:
                                direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE, port=6543)}),
    ),
)
def test_web_invalid_or_unproved_project_identity_disables_without_io(environment):
    calls = []
    factory = web._isolated_simulator_connection_factory(
        environment, lambda: calls.append("connected"))
    assert factory is None
    assert calls == []


@pytest.mark.parametrize("name", sorted(web._SIMULATOR_WORKER_CREDENTIAL_ENVS))
@pytest.mark.parametrize("value", ("worker-secret", ""))
def test_web_rejects_worker_credentials_by_presence_without_io(name, value):
    calls = []
    factory = web._isolated_simulator_connection_factory(
        valid_web_environment(**{name: value}),
        lambda: calls.append("connected"))
    assert factory is None
    assert calls == []


def test_web_installation_mismatch_rolls_back_closes_and_never_returns_connection():
    cursor = ScriptedCursor(one=((
        SIM_PUBLISHER_RUNTIME_ROLE, SIM_INSTALLATION_ID, PRODUCTION_PROJECT_REF),))
    connection = ScriptedConnection(cursor)
    factory = web._isolated_simulator_connection_factory(
        valid_web_environment(), lambda: connection)
    assert factory is not None

    with pytest.raises(RuntimeError, match="installation identity mismatch"):
        factory()
    assert (connection.commits, connection.rollbacks, connection.closed) == (0, 1, True)
    assert cursor.closed