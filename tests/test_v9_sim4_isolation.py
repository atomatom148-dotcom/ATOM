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
        connection, *, monotonic_ns=lambda: 0, monotonic=lambda: 0.0):
    runtime = worker.SimulationEntryWorker(
        lambda: connection,
        SIM_PROJECT_REF,
        object(),
        utc_clock=lambda: WORKER_T0,
        monotonic_ns=monotonic_ns,
        monotonic=monotonic,
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


def test_web_contains_no_worker_runtime_or_quote_source_authority():
    source = WEB_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert not any(name.endswith("v9_sim4_worker") for name in imported)
    for forbidden in (
        "stream.data.alpaca.markets", "authx.alpaca.markets",
        "SimulationEntryWorker", "SIPWebSocketReceiver",
        "python -m quant.v9_sim4_worker",
    ):
        assert forbidden not in source
    assert "simulator_connection_factory = _isolated_simulator_connection_factory(" in source
    assert set(web._SIMULATOR_WORKER_CREDENTIAL_ENVS) == {
        worker.SIM4_DATABASE_URL_ENV,
        worker.AUTHX_CLIENT_ID_ENV,
        worker.AUTHX_CLIENT_SECRET_ENV,
        worker.AUTHX_ATTESTATION_ID_ENV,
        worker.AUTHX_ATTESTATION_SHA256_ENV,
    }


def valid_worker_environment(**changes):
    values = {
        worker.SIM4_ENABLED_ENV: "true",
        worker.SIM4_DATABASE_URL_ENV: direct_dsn(SIM_ENTRY_RUNTIME_ROLE),
        worker.SIM_PROJECT_REF_ENV: SIM_PROJECT_REF,
        worker.AUTHX_CLIENT_ID_ENV: "restricted-data-client",
        worker.AUTHX_CLIENT_SECRET_ENV: "restricted-data-secret",
        worker.AUTHX_ATTESTATION_ID_ENV: "provisioning-record-1",
        worker.AUTHX_ATTESTATION_SHA256_ENV: "a" * 64,
    }
    values.update(changes)
    return values


@pytest.mark.parametrize("value", (None, "", "TRUE", "True", "1", "false"))
def test_worker_is_disabled_unless_literal_lowercase_true(value):
    environment = {} if value is None else {worker.SIM4_ENABLED_ENV: value}
    assert worker.sim4_enabled(environment) is False
    with pytest.raises(worker.Sim4ConfigurationError):
        worker.load_sim4_config(environment)


@pytest.mark.parametrize("value", (None, "", "TRUE", "True", "1", "false"))
def test_disabled_worker_main_performs_no_database_or_network_io(value, monkeypatch):
    environment = {} if value is None else {worker.SIM4_ENABLED_ENV: value}
    stop_event = threading.Event()
    stop_event.set()
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("disabled SIM-4 attempted external I/O")

    monkeypatch.setattr(worker, "load_sim4_config", forbidden)
    monkeypatch.setattr(worker._SIM4_LOGGER, "warning", forbidden)

    assert worker.main(
        environment,
        stop_event=stop_event,
        connection_factory=forbidden,
        token_requester=forbidden,
        websocket_factory=forbidden,
        install_signal_handlers=False,
    ) == 0
    assert calls == []


def test_fail_closed_logging_is_fixed_aggregate_and_ignores_success_churn():
    telemetry = worker.Sim4Telemetry()
    previous = worker._fail_closed_telemetry_snapshot(telemetry)
    records = []
    logger = SimpleNamespace(
        warning=lambda message, *args: records.append(message % args))

    telemetry.increment("quote_admitted")
    current = worker._log_fail_closed_telemetry_changes(
        telemetry, previous, logger=logger)
    assert current == previous
    assert records == []

    telemetry.increment("socket_failures")
    telemetry.increment("quote_queue_full")
    telemetry.increment("quote_queue_full")
    current = worker._log_fail_closed_telemetry_changes(
        telemetry, current, logger=logger)
    assert len(records) == 1
    assert records[0].startswith("SIM4_FAIL_CLOSED status=STANDBY ")
    assert "socket_failures=1 delta=1" in records[0]
    assert "quote_queue_full=2 delta=2" in records[0]
    assert "quote_admitted" not in records[0]

    assert worker._log_fail_closed_telemetry_changes(
        telemetry, current, logger=logger) == current
    assert len(records) == 1

    telemetry.status("FAILED")
    failed = worker._log_fail_closed_telemetry_changes(
        telemetry, current, logger=logger)
    assert failed[0] == "FAILED"
    assert records[-1] == "SIM4_FAIL_CLOSED status=FAILED counter_delta=0"


def test_enabled_main_logs_failure_aggregates_without_authority_or_secrets(
        monkeypatch):
    records = []

    class FakeWorker:
        def __init__(self):
            self.telemetry = worker.Sim4Telemetry()
            self.state = "STANDBY"
            self.stopped = False

        def start(self):
            self.telemetry.increment("socket_failures")
            self.telemetry.increment("quote_invalid")
            self.telemetry.status("FAILED")
            self.state = "FAILED"
            return self.state

        def stop(self):
            self.stopped = True

    fake_worker = FakeWorker()
    monkeypatch.setattr(
        worker.SimulationEntryWorker,
        "from_config",
        lambda *_args, **_kwargs: fake_worker,
    )
    monkeypatch.setattr(
        worker._SIM4_LOGGER,
        "warning",
        lambda message, *args: records.append(message % args),
    )
    no_wait = SimpleNamespace(wait=lambda _seconds: False)
    environment = valid_worker_environment()

    assert worker.main(
        environment,
        stop_event=no_wait,
        install_signal_handlers=False,
    ) == 1
    assert fake_worker.stopped is True
    assert records == [
        "SIM4_FAIL_CLOSED status=FAILED "
        "socket_failures=1 delta=1 quote_invalid=1 delta=1"
    ]
    rendered = records[0]
    for forbidden in (
        environment[worker.SIM4_DATABASE_URL_ENV],
        environment[worker.AUTHX_CLIENT_ID_ENV],
        environment[worker.AUTHX_CLIENT_SECRET_ENV],
        environment[worker.AUTHX_ATTESTATION_ID_ENV],
        environment[worker.AUTHX_ATTESTATION_SHA256_ENV],
    ):
        assert forbidden not in rendered


def test_worker_config_uses_only_entry_role_dsn_and_exact_authx_attestation_names():
    config = worker.load_sim4_config(valid_worker_environment())
    assert config.database_url == direct_dsn(SIM_ENTRY_RUNTIME_ROLE)
    assert config.project_ref == SIM_PROJECT_REF
    assert config.authx_client_id == "restricted-data-client"
    assert config.authx_client_secret == "restricted-data-secret"
    assert config.provisioning_attestation_id == "provisioning-record-1"
    assert config.provisioning_attestation_sha256 == "a" * 64


def test_default_worker_connection_attempt_has_fixed_five_second_timeout(
        monkeypatch):
    import psycopg

    config = worker.load_sim4_config(valid_worker_environment())
    sentinel = object()
    calls = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(psycopg, "connect", connect)
    runtime = worker.SimulationEntryWorker.from_config(config)

    assert runtime._connection_factory() is sentinel
    assert calls == [(
        (config.database_url,),
        {"connect_timeout": worker.SIM4_DATABASE_CONNECT_TIMEOUT_SECONDS},
    )]


def test_worker_has_no_database_url_or_publisher_fallback():
    values = valid_worker_environment()
    del values[worker.SIM4_DATABASE_URL_ENV]
    values["DATABASE_URL"] = direct_dsn("atom_v9_v4_runtime", PRODUCTION_PROJECT_REF)
    values["ATOM_V9_SIM_DATABASE_URL"] = direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE)
    with pytest.raises(worker.Sim4ConfigurationError):
        worker.load_sim4_config(values)


def test_enabled_worker_rejects_forbidden_authority_before_external_io():
    values = valid_worker_environment(DATABASE_URL="")
    stop_event = threading.Event()
    stop_event.set()
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("configuration failure reached external I/O")

    with pytest.raises(worker.Sim4ConfigurationError):
        worker.main(
            values,
            stop_event=stop_event,
            connection_factory=forbidden,
            token_requester=forbidden,
            websocket_factory=forbidden,
            install_signal_handlers=False,
        )
    assert calls == []


@pytest.mark.parametrize(
    "name",
    (
        "DATABASE_URL",
        "ATOM_V9_SIM_DATABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "ATOM_V9_V4_WRITER_DATABASE_URL",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "ALPACA_BROKER_BASE_URL",
        "BROKER_ACCOUNT_ID",
        "ORDER_ENDPOINT",
        "MASSIVE_API_KEY",
        "HISTORICAL_EVIDENCE_DATABASE_URL",
        "HISTORICAL_SCORE_DATABASE_URL",
    ),
)
@pytest.mark.parametrize("value", ("production-secret", ""))
def test_worker_rejects_production_and_publisher_authority_by_presence(name, value):
    assert name in worker.FORBIDDEN_ENVIRONMENT_NAMES
    environment = valid_worker_environment(**{name: value})
    with pytest.raises(worker.Sim4ConfigurationError) as captured:
        worker.validate_forbidden_environment(environment)
    assert "production-secret" not in str(captured.value)


def test_worker_entry_dsn_validator_agrees_with_shared_validator():
    for url in (
        direct_dsn(SIM_ENTRY_RUNTIME_ROLE),
        pooler_dsn(SIM_ENTRY_RUNTIME_ROLE),
    ):
        shared = validate_simulator_database_url(
            url, project_ref=SIM_PROJECT_REF,
            required_role=SIM_ENTRY_RUNTIME_ROLE)
        isolated = worker.validate_sim4_database_url(url, SIM_PROJECT_REF)
        assert (isolated.project_ref, isolated.username, isolated.port,
                isolated.database) == (
            shared.project_ref,
            (SIM_ENTRY_RUNTIME_ROLE if shared.endpoint_kind == "DIRECT" else
             f"{SIM_ENTRY_RUNTIME_ROLE}.{SIM_PROJECT_REF}"),
            shared.port,
            shared.database,
        )


def test_worker_source_has_no_production_runtime_or_trading_import_surface():
    source = WORKER_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    for forbidden in (
        "quant.web", "quant.live_market", "quant.v9_production",
        "quant.evidence", "quant.evidence_outbox", "alpaca_trade_api",
    ):
        assert not any(name == forbidden or name.startswith(forbidden + ".")
                       for name in imported)
    for forbidden_endpoint in (
        "paper-api.alpaca.markets", "api.alpaca.markets/v2/account",
        "api.alpaca.markets/v2/orders", "/v2/positions",
    ):
        assert forbidden_endpoint not in source


def test_deadline_terminalizes_before_checkpoint_and_releases_closure_transaction():
    intent = build_worker_intent()
    published = PublishedSimulationIntent(1, WORKER_T0, 1, intent)
    deadline_ns = datetime_to_epoch_nanoseconds(WORKER_T0) + 2_000_000_000
    publication = worker.PublicationRecord(
        1, WORKER_T0, 1, intent, deadline_ns - 1)
    connection = WorkerTransactionConnection(((None,), (1,)))
    runtime = make_authoritative_worker(connection)
    runtime._pending[intent.intent_id] = worker.PendingIntent(
        publication, deadline_ns)
    events = []

    class Store:
        page_calls = 0

        def load_publication_page_on_cursor(self, _cursor, **kwargs):
            events.append(("page", kwargs))
            self.page_calls += 1
            return (published,) if self.page_calls == 1 else ()

        def get_existing_entry_in_transaction(self, _cursor, requested_intent):
            events.append(("existing", requested_intent.intent_id))
            return None

        def terminalize_in_transaction(
                self, _cursor, requested_intent, *, requested_status, quote):
            events.append(("terminal", requested_intent.intent_id,
                           requested_status, quote))
            return INSERTED, SimpleNamespace(intent_id=requested_intent.intent_id)

        def compare_and_advance_checkpoint_on_cursor(self, _cursor, **kwargs):
            assert any(event[0] == "terminal" for event in events)
            events.append(("checkpoint", kwargs))
            return True

    store = Store()
    assert runtime._begin_due_deadline(
        deadline_ns, sampled=(True, deadline_ns + 1, 0))

    # The blocking deadline lock/fence is committed before any terminal or
    # checkpoint transaction begins, so the checkpoint definer cannot wait on
    # the worker's own still-held handoff lock.
    assert connection.commits == 1
    assert connection.autocommit is True
    deadline_cursor = next(
        cursor for cursor in connection.cursors
        if any(sql == worker._DEADLINE_LOCK_SQL
               for sql, _parameters in cursor.executions)
    )
    assert [item[0] for item in deadline_cursor.executions] == [
        "SET LOCAL lock_timeout = '5000ms'",
        "SET LOCAL statement_timeout = '6000ms'",
        worker._DEADLINE_LOCK_SQL,
        worker._FENCE_READER_SQL,
    ]

    assert runtime._process_target_page(store)
    assert runtime._process_target_page(store)
    assert runtime._checkpoint_last == 1
    assert connection.commits == 4
    kinds = [event[0] for event in events]
    assert kinds.index("terminal") < kinds.index("checkpoint")
    # Advancing through a fully terminal deadline now retires its closure in
    # the same successful checkpoint path; no later transaction is needed.
    assert deadline_ns not in runtime._deadline_closures


def test_reconciliation_preserves_semantic_order_when_publication_sequences_invert():
    earlier = build_worker_intent(2, final_bps=0.0)
    later_time = WORKER_T0 + timedelta(microseconds=1)
    later = build_worker_intent(3, eligible_at=later_time, final_bps=0.0)
    semantic_page = (
        PublishedSimulationIntent(9, WORKER_T0, 1, earlier),
        PublishedSimulationIntent(5, later_time, 1, later),
    )
    sequence_by_intent = {earlier.intent_id: 9, later.intent_id: 5}
    connection = WorkerTransactionConnection()
    runtime = make_authoritative_worker(connection)
    runtime._checkpoint_last = 4
    runtime._checkpoint_version = 2
    runtime._new_target(9, "RECONCILIATION")
    terminal_order = []

    class Store:
        page_calls = 0
        page_kwargs = None

        def load_publication_page_on_cursor(self, _cursor, **kwargs):
            self.page_kwargs = kwargs
            self.page_calls += 1
            return semantic_page if self.page_calls == 1 else ()

        @staticmethod
        def get_existing_entry_in_transaction(_cursor, _intent):
            return None

        @staticmethod
        def terminalize_in_transaction(
                _cursor, intent, *, requested_status, quote):
            assert requested_status == "SKIPPED_NO_TRADE"
            assert quote is None
            terminal_order.append(sequence_by_intent[intent.intent_id])
            return INSERTED, SimpleNamespace(intent_id=intent.intent_id)

        @staticmethod
        def compare_and_advance_checkpoint_on_cursor(_cursor, **_kwargs):
            return True

    store = Store()
    assert runtime._process_target_page(store)
    completed_cursor = runtime._target.cursor
    assert terminal_order == [9, 5]
    assert completed_cursor == (
        later_time, 1, later.intent_id, 5)
    assert store.page_kwargs["after_completed_publication_seq"] == 4
    assert store.page_kwargs["captured_publication_fence"] == 9
    assert runtime._process_target_page(store)
    assert runtime._checkpoint_last == 9


def test_deadline_rebuilds_from_checkpoint_and_preserves_known_timely_discovery(
        monkeypatch):
    intent = build_worker_intent(4)
    deadline_ns = datetime_to_epoch_nanoseconds(WORKER_T0) + 2_000_000_000
    known = worker.PublicationRecord(
        5, WORKER_T0, 1, intent, deadline_ns - 1)
    runtime = make_authoritative_worker(WorkerTransactionConnection())
    runtime._checkpoint_last = 4
    runtime._checkpoint_version = 2
    runtime._target = worker.ReconciliationTarget(
        "RECONCILIATION", 4, 6, 2,
        cursor=(WORKER_T0 + timedelta(seconds=1), 1, "later", 6),
    )
    runtime._pending[intent.intent_id] = worker.PendingIntent(known, deadline_ns)
    capture_calls = []

    def capture():
        capture_calls.append(True)
        return 9

    monkeypatch.setattr(runtime, "_capture_deadline_publication_fence", capture)
    assert runtime._begin_due_deadline(
        deadline_ns, sampled=(True, deadline_ns + 1, 0))
    assert len(capture_calls) == 1
    assert (
        runtime._target.lower_publication_seq,
        runtime._target.fence_publication_seq,
        runtime._target.expected_checkpoint_version,
        runtime._target.cursor,
    ) == (4, 9, 2, None)
    assert runtime._deadline_closures[deadline_ns].publication_fence == 9

    class Store:
        kwargs = None

        def load_publication_page_on_cursor(self, _cursor, **kwargs):
            self.kwargs = kwargs
            return (PublishedSimulationIntent(5, WORKER_T0, 1, intent),)

    def rediscovered_late(_published):
        raise AssertionError("known timely discovery was replaced")

    monkeypatch.setattr(runtime, "_discover_publication", rediscovered_late)
    store = Store()
    runtime._load_target_page(store)
    assert runtime._target.page == [known]
    assert runtime._target.page[0].discovered_epoch_ns == deadline_ns - 1
    assert store.kwargs["after_completed_publication_seq"] == 4
    assert store.kwargs["captured_publication_fence"] == 9
    assert store.kwargs["after"] is None


def test_deadline_fence_late_page_uses_frozen_quote_snapshot(monkeypatch):
    known_intent = build_worker_intent(45)
    later_page_intent = build_worker_intent(46)
    deadline_ns = datetime_to_epoch_nanoseconds(WORKER_T0) + 2_000_000_000
    connection = WorkerTransactionConnection()
    runtime = make_authoritative_worker(
        connection, monotonic_ns=lambda: deadline_ns + 1)
    quote = build_worker_quote()
    runtime._quotes.append(worker.AdmissionEnvelope(1, quote))
    runtime._last_drained_sequence = 1
    known = worker.PublicationRecord(
        16, WORKER_T0, 1, known_intent, deadline_ns - 1)
    runtime._pending[known_intent.intent_id] = worker.PendingIntent(
        known, deadline_ns)
    monkeypatch.setattr(
        runtime, "_capture_deadline_publication_fence", lambda: 17)

    assert runtime._begin_due_deadline(
        deadline_ns, sampled=(True, deadline_ns + 1, 1))
    closure = runtime._deadline_closures[deadline_ns]
    assert closure.admitted_quotes == (quote,)

    runtime._target.cursor = known.semantic_key
    terminal = []

    class Store:
        @staticmethod
        def load_publication_page_on_cursor(_cursor, **kwargs):
            assert kwargs["after"] is not None
            return (PublishedSimulationIntent(
                17, WORKER_T0, 1, later_page_intent),)

        @staticmethod
        def get_existing_entry_in_transaction(_cursor, _intent):
            return None

        @staticmethod
        def terminalize_in_transaction(
                _cursor, intent, *, requested_status, quote):
            terminal.append((intent.intent_id, requested_status, quote))
            return INSERTED, SimpleNamespace(intent_id=intent.intent_id)

    store = Store()
    runtime._load_target_page(store)
    later_page = runtime._target.page[0]
    assert later_page.discovered_epoch_ns > deadline_ns
    assert runtime._classify_publication(store, later_page)
    assert terminal == [(later_page_intent.intent_id, "ENTERED", quote)]


def test_page_discovery_registers_all_timely_intents_before_database_yield(
        monkeypatch):
    eligible_at = WORKER_T0 + timedelta(seconds=1)
    deadline_ns = datetime_to_epoch_nanoseconds(eligible_at) + 2_000_000_000
    clock = SimpleNamespace(now=2_999_999_999)
    runtime = make_authoritative_worker(
        WorkerTransactionConnection(), monotonic_ns=lambda: clock.now)
    first = build_worker_intent(51, eligible_at=eligible_at)
    second = build_worker_intent(52, eligible_at=eligible_at)
    runtime._new_target(2, "RECONCILIATION")

    class Store:
        @staticmethod
        def load_publication_page_on_cursor(_cursor, **_kwargs):
            return (
                PublishedSimulationIntent(1, eligible_at, 1, first),
                PublishedSimulationIntent(2, eligible_at, 1, second),
            )

    existing = build_simulation_entry_record(
        intent=first, entry_status="SKIPPED_WINDOW_EXPIRED")
    probes = []

    def existing_entry(_store, intent):
        if not probes:
            assert set(runtime._pending) == {first.intent_id, second.intent_id}
        probes.append(intent.intent_id)
        clock.now = 3_000_000_001
        return existing if intent.intent_id == first.intent_id else None

    monkeypatch.setattr(runtime, "_existing_entry", existing_entry)

    assert runtime._process_target_page(Store()) is False
    assert probes == [first.intent_id, second.intent_id]
    assert first.intent_id not in runtime._pending
    assert runtime._pending[second.intent_id].deadline_epoch_ns == deadline_ns
    assert (
        runtime._pending[second.intent_id].publication.discovered_epoch_ns
        == deadline_ns - 1
    )


def test_every_row_in_a_full_semantic_page_is_classified_without_short_circuit(
        monkeypatch):
    connection = WorkerTransactionConnection()
    runtime = make_authoritative_worker(connection)
    page = [
        worker.PublicationRecord(
            index,
            WORKER_T0 + timedelta(microseconds=index),
            1,
            build_worker_intent(
                index + 10,
                eligible_at=WORKER_T0 + timedelta(microseconds=index)),
            datetime_to_epoch_nanoseconds(WORKER_T0),
        )
        for index in range(1, worker.SIM4_RECONCILE_QUERY_ROWS + 1)
    ]
    runtime._target = worker.ReconciliationTarget(
        "RECONCILIATION", 0, worker.SIM4_RECONCILE_QUERY_ROWS, 0,
        page=page.copy(),
    )
    classified = []

    monkeypatch.setattr(runtime, "_load_target_page", lambda _store: None)

    def classify(_store, publication):
        classified.append(publication.publication_seq)
        if publication.publication_seq != 1:
            return True
        runtime._pending[publication.intent.intent_id] = worker.PendingIntent(
            publication,
            datetime_to_epoch_nanoseconds(WORKER_T0) + 2_000_000_000,
        )
        return False

    monkeypatch.setattr(runtime, "_classify_publication", classify)
    assert runtime._process_target_page(object()) is False
    assert classified == list(range(1, worker.SIM4_RECONCILE_QUERY_ROWS + 1))
    assert runtime._target.page == page
    assert runtime._target.page_complete is False


def test_keyset_reconciliation_crosses_65536_rows_with_bounded_pages(monkeypatch):
    total_rows = 65_537
    connection = WorkerTransactionConnection()
    runtime = make_authoritative_worker(connection)
    runtime._new_target(total_rows, "RECONCILIATION")
    classified = 0

    class Store:
        page_calls = 0
        checkpoint_calls = 0

        def load_publication_page_on_cursor(
                self, _cursor, *, after_completed_publication_seq,
                captured_publication_fence, after, limit):
            assert after_completed_publication_seq == 0
            assert captured_publication_fence == total_rows
            assert limit == worker.SIM4_RECONCILE_QUERY_ROWS
            start = 1 if after is None else after.publication_seq + 1
            stop = min(start + limit, total_rows + 1)
            self.page_calls += 1
            return tuple(
                SimpleNamespace(
                    publication_seq=index,
                    publication_at=(
                        WORKER_T0 + timedelta(microseconds=index)),
                    horizon_order=1,
                    intent=SimpleNamespace(
                        intent_id=f"large-history-{index:06d}",
                        status="NO_TRADE",
                    ),
                )
                for index in range(start, stop)
            )

        def compare_and_advance_checkpoint_on_cursor(self, _cursor, **kwargs):
            self.checkpoint_calls += 1
            assert kwargs["new_last_completed_publication_seq"] == total_rows
            return True

    def classify(_store, _publication):
        nonlocal classified
        classified += 1
        return True

    store = Store()
    monkeypatch.setattr(runtime, "_classify_publication", classify)
    iterations = 0
    while runtime._target is not None:
        assert runtime._process_target_page(store)
        iterations += 1

    expected_pages = (
        total_rows + worker.SIM4_RECONCILE_QUERY_ROWS - 1
    ) // worker.SIM4_RECONCILE_QUERY_ROWS
    assert store.page_calls == expected_pages
    assert iterations == expected_pages + 1
    assert classified == total_rows
    assert store.checkpoint_calls == 1
    assert runtime._checkpoint_last == total_rows


def test_checkpoint_compare_false_sets_backoff_and_does_not_spin():
    clock = SimpleNamespace(now=10.0)
    connection = WorkerTransactionConnection()
    runtime = make_authoritative_worker(
        connection, monotonic=lambda: clock.now)
    runtime._target = worker.ReconciliationTarget(
        "RECONCILIATION", 0, 1, 0, exhausted=True)

    class Store:
        calls = 0

        def compare_and_advance_checkpoint_on_cursor(self, _cursor, **_kwargs):
            self.calls += 1
            return self.calls > 1

    store = Store()
    assert runtime._process_target_page(store) is False
    retry_at = runtime._target.retry_not_before_monotonic
    assert retry_at == 10.0 + worker.SIM4_RUNTIME_OWNER_RETRY_SECONDS
    assert store.calls == 1
    assert connection.rollbacks == 1

    assert runtime._process_target_page(store) is False
    assert store.calls == 1
    assert connection.rollbacks == 1

    clock.now = retry_at
    assert runtime._process_target_page(store)
    assert store.calls == 2
    assert connection.commits == 1
    assert runtime._target is None


def test_checkpoint_backoff_services_quote_fifo_instead_of_waiting(monkeypatch):
    clock = SimpleNamespace(now=10.0)
    connection = WorkerTransactionConnection()
    runtime = make_authoritative_worker(
        connection, monotonic=lambda: clock.now)
    runtime._target = worker.ReconciliationTarget(
        "RECONCILIATION", 0, 1, 0, exhausted=True)

    class Store:
        calls = 0

        def compare_and_advance_checkpoint_on_cursor(self, _cursor, **_kwargs):
            self.calls += 1
            return False

    store = Store()
    assert runtime._process_target_page(store) is False
    assert runtime._target.retry_not_before_monotonic > clock.now

    intent = build_worker_intent(42)
    due = datetime_to_epoch_nanoseconds(WORKER_T0) + 2_000_000_000
    publication = worker.PublicationRecord(1, WORKER_T0, 1, intent, due - 1)
    runtime._pending[intent.intent_id] = worker.PendingIntent(publication, due)
    runtime._deadline_closures[due] = worker.DeadlineClosure(
        due, 1, {intent.intent_id: None}, 1)
    envelope = worker.AdmissionEnvelope(1, build_worker_quote())
    runtime._events.put_nowait(envelope)
    monkeypatch.setattr(runtime, "_new_target", lambda *_args: None)
    monkeypatch.setattr(
        runtime, "_stop_wait",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("checkpoint backoff blocked the owner loop")),
    )
    original_drain = runtime._drain_one_quote_event

    def drain_then_stop():
        drained = original_drain()
        runtime._stop_requested.set()
        return drained

    monkeypatch.setattr(runtime, "_drain_one_quote_event", drain_then_stop)
    runtime._ready_loop(store, 0)

    assert store.calls == 1
    assert list(runtime._quotes) == [envelope]
    assert runtime._last_drained_sequence == 1


@pytest.mark.parametrize("mode", ("malformed", "timeout"))
def test_periodic_capture_failure_yields_only_after_rollback_and_pid_proof(mode):
    class QueryCanceled(Exception):
        sqlstate = "57014"

    class PeriodicCursor(WorkerTransactionCursor):
        def execute(self, statement, parameters=None):
            super().execute(statement, parameters)
            if mode == "timeout" and statement == worker._ACTIVATION_TRY_SQL:
                raise QueryCanceled("statement timeout")

    class PeriodicConnection(WorkerTransactionConnection):
        def cursor(self):
            cursor = PeriodicCursor(self)
            self.cursors.append(cursor)
            return cursor

    scripted = ((("malformed",),),) if mode == "malformed" else ()
    connection = PeriodicConnection(*scripted)
    runtime = make_authoritative_worker(connection)

    assert runtime._try_periodic_capture() is None
    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert [cursor.executions for cursor in connection.cursors] == [
        [(worker._BACKEND_PID_SQL, None)],
        [
            ("SET LOCAL statement_timeout = '100ms'", None),
            (worker._ACTIVATION_TRY_SQL, (worker.SIM4_ACTIVATION_LOCK_KEY,)),
        ],
        [(worker._BACKEND_PID_SQL, None)],
    ]
    assert all(cursor.closed for cursor in connection.cursors)
    assert runtime.telemetry.snapshot()["reconciliation_failures"] == 1
    assert runtime._generation_failed is False


def test_periodic_fence_equal_to_checkpoint_performs_no_checkpoint_write():
    connection = WorkerTransactionConnection(((True,), (5,)))
    runtime = make_authoritative_worker(connection)
    runtime._checkpoint_last = 5
    runtime._checkpoint_version = 2

    fence = runtime._try_periodic_capture()
    assert fence == 5
    assert connection.commits == 1
    runtime._new_target(fence, "RECONCILIATION")
    assert runtime._target is None

    class Store:
        @staticmethod
        def compare_and_advance_checkpoint_on_cursor(*_args, **_kwargs):
            raise AssertionError("empty periodic fence wrote a checkpoint")

    cursors_before = len(connection.cursors)
    assert runtime._process_target_page(Store()) is False
    assert len(connection.cursors) == cursors_before
    assert (runtime._checkpoint_last, runtime._checkpoint_version) == (5, 2)

    runtime._new_target(fence, "ACTIVATION")
    assert runtime._target is not None
    assert (
        runtime._target.lower_publication_seq,
        runtime._target.fence_publication_seq,
    ) == (5, 5)


def test_stale_full_quote_buffer_evicts_before_ordinary_capacity_rejection():
    now_ns = 3_000_001_000
    runtime = make_authoritative_worker(
        WorkerTransactionConnection(), monotonic_ns=lambda: now_ns)
    runtime._quotes = deque(
        worker.AdmissionEnvelope(
            index, SimpleNamespace(accepted_at=WORKER_T0))
        for index in range(1, worker.SIM4_QUOTE_BUFFER_CAPACITY + 1)
    )
    runtime._last_drained_sequence = worker.SIM4_QUOTE_BUFFER_CAPACITY
    fresh = worker.AdmissionEnvelope(
        worker.SIM4_QUOTE_BUFFER_CAPACITY + 1,
        SimpleNamespace(accepted_at=WORKER_T0 + timedelta(seconds=3)),
    )
    runtime._events.put_nowait(fresh)

    assert runtime._drain_one_quote_event()
    assert list(runtime._quotes) == [fresh]
    assert runtime._last_drained_sequence == fresh.admission_sequence
    assert runtime.telemetry.snapshot()["quote_buffer_full"] == 0


def test_full_retained_quote_buffer_drops_only_incoming_and_completes_drain():
    runtime = make_authoritative_worker(
        WorkerTransactionConnection(), monotonic_ns=lambda: 1_000_000_000)
    runtime._admission_enabled = True
    runtime._quotes = deque(
        worker.AdmissionEnvelope(
            index, SimpleNamespace(accepted_at=WORKER_T0))
        for index in range(1, worker.SIM4_QUOTE_BUFFER_CAPACITY + 1)
    )
    runtime._last_drained_sequence = worker.SIM4_QUOTE_BUFFER_CAPACITY
    rejected = worker.AdmissionEnvelope(
        worker.SIM4_QUOTE_BUFFER_CAPACITY + 1,
        SimpleNamespace(accepted_at=WORKER_T0 + timedelta(seconds=1)),
    )
    runtime._events.put_nowait(rejected)

    assert runtime._drain_one_quote_event()

    assert runtime._generation_failed is False
    assert runtime._admission_enabled is True
    assert len(runtime._quotes) == worker.SIM4_QUOTE_BUFFER_CAPACITY
    assert rejected not in runtime._quotes
    assert runtime._last_drained_sequence == rejected.admission_sequence
    assert runtime.telemetry.snapshot()["quote_buffer_full"] == 1
    assert runtime._events.empty()


def test_quote_expiry_equal_to_pending_deadline_preempts_ordinary_eviction():
    deadline_ns = datetime_to_epoch_nanoseconds(
        WORKER_T0 + timedelta(seconds=2))
    runtime = make_authoritative_worker(
        WorkerTransactionConnection(), monotonic_ns=lambda: 2_000_000_001)
    intent = build_worker_intent(41)
    publication = worker.PublicationRecord(
        1, WORKER_T0, 1, intent, deadline_ns - 1)
    old = worker.AdmissionEnvelope(
        1, SimpleNamespace(accepted_at=WORKER_T0))
    fresh = worker.AdmissionEnvelope(
        2, SimpleNamespace(accepted_at=WORKER_T0 + timedelta(seconds=2)))
    runtime._quotes.append(old)
    runtime._last_drained_sequence = 1
    runtime._pending[intent.intent_id] = worker.PendingIntent(
        publication, deadline_ns)

    runtime._retain_admitted_quote(fresh, allow_safe_eviction=True)

    assert list(runtime._quotes) == [old, fresh]
    assert runtime._last_drained_sequence == 2
    assert runtime._generation_failed is False
    assert runtime.telemetry.snapshot()["quote_buffer_full"] == 0


def test_quote_clock_crossing_deadline_rechecks_before_expired_quote_eviction(
        monkeypatch):
    due = datetime_to_epoch_nanoseconds(
        WORKER_T0 + timedelta(seconds=3))
    runtime = make_authoritative_worker(
        WorkerTransactionConnection(), monotonic_ns=lambda: 3_000_000_000)
    intent = build_worker_intent(43)
    publication = worker.PublicationRecord(1, WORKER_T0, 1, intent, due - 1)
    runtime._pending[intent.intent_id] = worker.PendingIntent(publication, due)
    envelope = worker.AdmissionEnvelope(
        1, SimpleNamespace(accepted_at=WORKER_T0))
    runtime._quotes.append(envelope)
    deadline_samples = []

    def sample(deadline_ns):
        assert deadline_ns == due
        deadline_samples.append(deadline_ns)
        if len(deadline_samples) == 2:
            runtime._stop_requested.set()
        return False, due - 1, 0

    monkeypatch.setattr(runtime, "_new_target", lambda *_args: None)
    monkeypatch.setattr(runtime, "_deadline_sample", sample)
    monkeypatch.setattr(
        runtime,
        "_evict_quotes_after_deadlines",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("expired quote evicted before deadline recheck")),
    )

    runtime._ready_loop(object(), 0)

    assert deadline_samples == [due, due]
    assert list(runtime._quotes) == [envelope]


def test_cached_deadline_page_yields_to_one_waiting_quote_before_next_page(
        monkeypatch):
    due = datetime_to_epoch_nanoseconds(
        WORKER_T0 + timedelta(seconds=2))
    runtime = make_authoritative_worker(WorkerTransactionConnection())
    intent = build_worker_intent(44)
    publication = worker.PublicationRecord(1, WORKER_T0, 1, intent, due - 1)
    runtime._pending[intent.intent_id] = worker.PendingIntent(publication, due)
    runtime._deadline_closures[due] = worker.DeadlineClosure(
        due, 0, {intent.intent_id: None}, 2)
    runtime._target = worker.ReconciliationTarget(
        "RECONCILIATION", 0, 2, 0)
    envelope = worker.AdmissionEnvelope(1, build_worker_quote())
    runtime._events.put_nowait(envelope)
    page_calls = []

    def process_page(_store):
        page_calls.append(True)
        runtime._ordinary_since_slice = False
        return True

    monkeypatch.setattr(runtime, "_process_target_page", process_page)
    monkeypatch.setattr(
        runtime, "_complete_deadline_if_reconciled", lambda *_args: False)
    original_drain = runtime._drain_one_quote_event

    def drain_then_stop():
        drained = original_drain()
        runtime._stop_requested.set()
        return drained

    monkeypatch.setattr(runtime, "_drain_one_quote_event", drain_then_stop)
    runtime._ready_loop(object(), 0)

    assert page_calls == [True]
    assert list(runtime._quotes) == [envelope]
    assert runtime._last_drained_sequence == 1


def test_existing_terminal_is_read_and_validated_only_after_horizon_lock():
    intent = build_worker_intent(40)
    existing = build_simulation_entry_record(
        intent=intent, entry_status="SKIPPED_WINDOW_EXPIRED")
    cursor = ScriptedCursor(one=(
        (SIM_ENTRY_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE, 4321),
        (None,),
        entry_database_row(existing),
    ))
    store = SimulationEntryStore(
        ScriptedConnection(cursor), project_ref=SIM_PROJECT_REF,
        expected_backend_pid=4321)

    assert store.get_existing_entry_in_transaction(cursor, intent) == existing
    assert cursor.executions[0][0] == (
        "SELECT current_user, session_user, pg_backend_pid()")
    assert cursor.executions[1] == (
        "SELECT pg_advisory_xact_lock(%s::bigint)",
        (horizon_advisory_lock_key(intent.horizon),),
    )
    assert "WHERE intent_id = %s" in cursor.executions[2][0]
    assert cursor.executions[2][1] == (intent.intent_id,)


def test_worker_retries_flapping_sip_readiness_on_same_receiver():
    class FlappingReady:
        def __init__(self):
            self.waits = 0

        def wait(self, _timeout):
            self.waits += 1
            return True

        def is_set(self):
            return self.waits >= 2

    class Receiver:
        def __init__(self):
            self.ready_event = FlappingReady()
            self.starts = 0

        def start(self):
            self.starts += 1

    receiver = Receiver()
    runtime = worker.SimulationEntryWorker(
        lambda: object(),
        SIM_PROJECT_REF,
        object(),
        utc_clock=lambda: WORKER_T0,
        monotonic_ns=lambda: 1,
        receiver_factory=lambda _callback: receiver,
    )

    assert runtime._wait_for_sip_readiness()
    assert receiver.starts == 1
    assert receiver.ready_event.waits == 2
    assert runtime._anchor is not None
    assert runtime._admission_enabled is True


@pytest.mark.parametrize(
    ("predicate", "ack"),
    (
        (worker._authentication_ack,
         {"T": "success", "msg": "authenticated"}),
        (worker._subscription_ack,
         {"T": "subscription", "quotes": ["COIN"]}),
    ),
)
def test_authx_ack_same_frame_error_wins(predicate, ack):
    receiver = worker.SIPWebSocketReceiver(
        object(), lambda _quote: True,
        websocket_factory=lambda *args, **kwargs: None,
        monotonic=lambda: 0.0,
    )
    error = {"T": "error", "msg": "denied"}
    for frame_items in ((ack, error), (error, ack)):
        stream = SimpleNamespace(
            recv=lambda items=frame_items: json.dumps(items))
        with pytest.raises(worker.Sim4ProtocolError, match="rejected"):
            receiver._recv_until(stream, predicate, 10.0)


def test_authx_ack_returning_at_deadline_is_rejected_after_receive():
    samples = iter((9.999, 10.0))

    class Stream:
        @staticmethod
        def recv():
            return json.dumps([{"T": "success", "msg": "authenticated"}])

    receiver = worker.SIPWebSocketReceiver(
        object(), lambda _quote: True,
        websocket_factory=lambda *args, **kwargs: None,
        monotonic=lambda: next(samples),
    )
    with pytest.raises(worker.Sim4ProtocolError, match="timed out"):
        receiver._recv_until(Stream(), worker._authentication_ack, 10.0)


def test_authx_token_failure_counts_as_auth_not_socket():
    class TokenClient:
        @staticmethod
        def fetch():
            raise RuntimeError("credential rejected")

    telemetry = worker.Sim4Telemetry()
    receiver = worker.SIPWebSocketReceiver(
        TokenClient(),
        lambda _quote: True,
        websocket_factory=lambda *_args, **_kwargs: pytest.fail(
            "token failure opened a websocket"),
        wait=lambda _seconds: True,
        telemetry=telemetry,
    )

    receiver._run()

    snapshot = telemetry.snapshot()
    assert snapshot["auth_failures"] == 1
    assert snapshot["socket_failures"] == 0


def test_websocket_handshake_failure_counts_as_auth_not_socket():
    class TokenClient:
        @staticmethod
        def fetch():
            return worker.AuthXToken("data-only-token", 30)

    class Stream:
        closed = False

        @staticmethod
        def settimeout(_timeout):
            return None

        @staticmethod
        def recv():
            return '[{"T":"error","msg":"denied"}]'

        def close(self):
            self.closed = True

    telemetry = worker.Sim4Telemetry()
    stream = Stream()
    receiver = worker.SIPWebSocketReceiver(
        TokenClient(),
        lambda _quote: True,
        websocket_factory=lambda *_args, **_kwargs: stream,
        monotonic=lambda: 0.0,
        wait=lambda _seconds: True,
        telemetry=telemetry,
    )

    receiver._run()

    snapshot = telemetry.snapshot()
    assert snapshot["auth_failures"] == 1
    assert snapshot["socket_failures"] == 0
    assert stream.closed is True


def test_numeric_quote_overflow_rejects_only_the_bad_item():
    valid = {
        "T": "q", "S": "COIN", "bp": 100, "ap": 101,
        "bs": 2, "as": 3, "t": "2026-09-01T12:00:00.000000001Z",
    }
    invalid = dict(valid, bp=10**10000)
    admitted = []
    telemetry = worker.Sim4Telemetry()
    receiver = worker.SIPWebSocketReceiver(
        object(), admitted.append, telemetry=telemetry)

    receiver._process_stream_items((invalid, valid))

    assert len(admitted) == 1
    assert admitted[0].bid == 100.0
    assert telemetry.snapshot()["quote_invalid"] == 1


def test_subscription_ack_frame_preserves_following_quote_without_third_recv():
    quote = {
        "T": "q", "S": "COIN", "bp": 100, "ap": 101,
        "bs": 2, "as": 3, "t": "2026-09-01T12:00:00.000000001Z",
    }

    class TokenClient:
        @staticmethod
        def fetch():
            return worker.AuthXToken("data-only-token", 30)

    class Stream:
        def __init__(self):
            self.frames = iter((
                '[{"T":"success","msg":"authenticated"}]',
                json.dumps([
                    {"T": "subscription", "quotes": ["COIN"]},
                    quote,
                ]),
            ))
            self.recv_calls = 0
            self.closed = False

        @staticmethod
        def settimeout(_timeout):
            return None

        def recv(self):
            self.recv_calls += 1
            return next(self.frames)

        @staticmethod
        def send(payload):
            assert payload == worker.SIM4_SUBSCRIPTION_PAYLOAD

        def close(self):
            self.closed = True

    stream = Stream()
    admitted = []
    receiver = None

    def admit(parsed):
        admitted.append(parsed)
        receiver.stop()
        return True

    receiver = worker.SIPWebSocketReceiver(
        TokenClient(), admit,
        websocket_factory=lambda *_args, **_kwargs: stream,
        monotonic=lambda: 0.0,
    )

    assert receiver._connect_once() == 0.0
    assert len(admitted) == 1
    assert admitted[0].provider_event_ns == (
        datetime_to_epoch_nanoseconds(WORKER_T0) + 1)
    assert stream.recv_calls == 2
    assert stream.closed is True


@pytest.mark.parametrize("as_bytes", (False, True))
def test_websocket_message_byte_cap_accepts_boundary_and_rejects_oversize(
        as_bytes):
    assert worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES == 1024 * 1024
    prefix = '[{"T":"noop","padding":"'
    suffix = '"}]'
    padding_size = (
        worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES
        - len(prefix.encode("utf-8"))
        - len(suffix.encode("utf-8"))
    )
    boundary = prefix + ("a" * padding_size) + suffix
    assert len(boundary.encode("utf-8")) == (
        worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES)

    value = boundary.encode("utf-8") if as_bytes else boundary
    assert worker._decode_frame(value) == [
        {"T": "noop", "padding": "a" * padding_size}]

    oversize = prefix + ("a" * (padding_size + 1)) + suffix
    value = oversize.encode("utf-8") if as_bytes else oversize
    with pytest.raises(worker.Sim4ProtocolError, match="message exceeds 1 MiB"):
        worker._decode_frame(value)


def test_websocket_message_cap_uses_utf8_bytes_before_decode_and_both_recv_paths(
        monkeypatch):
    prefix = '[{"T":"success","msg":"authenticated","padding":"'
    suffix = '"}]'
    padding_size = (
        worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES
        - len(prefix.encode("utf-8"))
        - len(suffix.encode("utf-8"))
    )
    # Replacing one ASCII byte with a two-byte character keeps the Python
    # character count at the ceiling while exceeding the wire-byte ceiling.
    multibyte_oversize = prefix + ("a" * (padding_size - 1)) + "é" + suffix
    assert len(multibyte_oversize) == worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES
    assert len(multibyte_oversize.encode("utf-8")) == (
        worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES + 1)
    real_json_loads = worker.json.loads
    monkeypatch.setattr(
        worker.json, "loads",
        lambda _value: pytest.fail("oversize websocket message reached JSON decode"),
    )
    with pytest.raises(worker.Sim4ProtocolError, match="message exceeds 1 MiB"):
        worker._decode_frame(multibyte_oversize)
    with pytest.raises(worker.Sim4ProtocolError, match="message exceeds 1 MiB"):
        worker._decode_frame(
            b"\xff" * (worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES + 1))
    monkeypatch.setattr(worker.json, "loads", real_json_loads)

    receiver = worker.SIPWebSocketReceiver(
        object(), lambda _quote: True,
        websocket_factory=lambda *args, **kwargs: None,
        monotonic=lambda: 0.0,
    )
    ack_stream = SimpleNamespace(recv=lambda: multibyte_oversize)
    with pytest.raises(worker.Sim4ProtocolError, match="acknowledgement failed"):
        receiver._recv_until(ack_stream, worker._authentication_ack, 10.0)

    live_oversize = b"[" + (
        b" " * (worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES - 1)) + b"]"

    class TokenClient:
        @staticmethod
        def fetch():
            return worker.AuthXToken("data-only-token", 30)

    class LiveStream:
        def __init__(self):
            self.frames = iter((
                '[{"T":"success","msg":"authenticated"}]',
                '[{"T":"subscription","quotes":["COIN"]}]',
                live_oversize,
            ))
            self.closed = False

        @staticmethod
        def settimeout(_timeout):
            return None

        def recv(self):
            return next(self.frames)

        @staticmethod
        def send(payload):
            assert payload == worker.SIM4_SUBSCRIPTION_PAYLOAD

        def close(self):
            self.closed = True

    live_stream = LiveStream()
    receiver = worker.SIPWebSocketReceiver(
        TokenClient(), lambda _quote: True,
        websocket_factory=lambda *args, **kwargs: live_stream,
        monotonic=lambda: 0.0,
    )
    with pytest.raises(worker.Sim4ProtocolError, match="SIP receive failed"):
        receiver._connect_once()
    assert live_stream.closed is True
    assert receiver.ready_event.is_set() is False


def test_default_websocket_transport_caps_frame_length_and_fragment_aggregate(
        monkeypatch):
    import websocket

    calls = []
    sentinel = object()

    def create_connection(url, **options):
        calls.append((url, options))
        return sentinel

    monkeypatch.setattr(websocket, "create_connection", create_connection)
    receiver = worker.SIPWebSocketReceiver(object(), lambda _quote: True)
    assert receiver._websocket_factory(
        worker.SIM4_WEBSOCKET_URL, timeout=10.0) is sentinel
    assert len(calls) == 1
    bounded_class = calls[0][1].pop("class_")
    assert calls == [(worker.SIM4_WEBSOCKET_URL, {"timeout": 10.0})]
    assert issubclass(bounded_class, websocket.WebSocket)

    exact_stream = bounded_class(enable_multithread=False)
    exact_wire = bytearray(
        b"\x82\x7f"
        + worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES.to_bytes(8, "big"))

    def exact_recv(size):
        result = bytes(exact_wire[:size])
        del exact_wire[:size]
        return result

    exact_stream.frame_buffer.recv = exact_recv
    exact_stream.frame_buffer.recv_header()
    exact_stream.frame_buffer.recv_length()
    assert exact_stream.frame_buffer.length == (
        worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES)
    assert exact_wire == bytearray()

    stream = bounded_class(enable_multithread=False)
    # A server frame declares cap+1 in its 64-bit header but supplies no
    # payload.  Rejection must happen after only the two header reads; asking
    # the socket for payload bytes would fail this deterministic fixture.
    wire = bytearray(
        b"\x82\x7f"
        + (worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES + 1).to_bytes(8, "big"))
    reads = []

    def recv(size):
        reads.append(size)
        if not wire:
            raise AssertionError("oversize websocket payload was requested")
        result = bytes(wire[:size])
        del wire[:size]
        return result

    stream.frame_buffer.recv = recv
    with pytest.raises(
        websocket.WebSocketPayloadException,
        match="message exceeds 1 MiB",
    ):
        stream.frame_buffer.recv_frame()
    assert reads == [2, 8]
    assert wire == bytearray()

    first_payload = b"a" * worker.SIM4_WEBSOCKET_MESSAGE_MAX_BYTES
    stream.cont_frame.add(SimpleNamespace(
        opcode=websocket.ABNF.OPCODE_TEXT,
        data=first_payload,
        fin=0,
    ))
    assert stream.cont_frame.cont_data[1] is first_payload
    with pytest.raises(
        websocket.WebSocketPayloadException,
        match="message exceeds 1 MiB",
    ):
        stream.cont_frame.add(SimpleNamespace(
            opcode=websocket.ABNF.OPCODE_CONT,
            data=b"b",
            fin=1,
        ))
    assert stream.cont_frame.cont_data is None
    assert stream.cont_frame.recving_frames is None


def test_authx_http_request_uses_one_absolute_total_deadline(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    instances = []

    class Socket:
        def __init__(self):
            self.timeouts = []

        def settimeout(self, timeout):
            self.timeouts.append(timeout)

    class Response:
        status = 200

        @staticmethod
        def read1(_amount):
            clock.now += 3.0
            return b'{}'

    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert (host, port, timeout) == (
                "authx.alpaca.markets", 443,
                worker.SIM4_TOKEN_CONNECT_TIMEOUT_SECONDS,
            )
            assert context is fake_context
            self.sock = Socket()
            self.closed = False
            instances.append(self)

        def connect(self):
            clock.now += 2.0

        def request(self, method, path, *, body, headers):
            assert (method, path, body, headers) == (
                "POST", "/v1/oauth2/token", b"request", {"X-Test": "1"})
            clock.now += 2.0

        @staticmethod
        def getresponse():
            clock.now += 3.0
            return Response()

        def close(self):
            self.closed = True

    fake_context = object()
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(worker.ssl, "create_default_context", lambda: fake_context)
    monkeypatch.setattr(worker.http.client, "HTTPSConnection", Connection)

    with pytest.raises(TimeoutError, match="timed out"):
        worker._default_token_requester(
            worker.SIM4_AUTHX_TOKEN_URL,
            b"request",
            {"X-Test": "1"},
            worker.SIM4_TOKEN_CONNECT_TIMEOUT_SECONDS,
            worker.SIM4_TOKEN_TOTAL_TIMEOUT_SECONDS,
            worker.SIM4_TOKEN_RESPONSE_MAX_BYTES,
        )

    assert instances[0].sock.timeouts == [8.0, 6.0, 3.0]
    assert instances[0].closed is True


def test_authx_http_request_rejects_every_nonliteral_endpoint_before_io(
        monkeypatch):
    monkeypatch.setattr(
        worker.http.client,
        "HTTPSConnection",
        lambda *_args, **_kwargs: pytest.fail(
            "nonliteral AuthX endpoint reached the network"),
    )

    with pytest.raises(worker.Sim4ProtocolError, match="invalid AuthX"):
        worker._default_token_requester(
            worker.SIM4_AUTHX_TOKEN_URL + "?redirect=https://example.com",
            b"request",
            {},
            worker.SIM4_TOKEN_CONNECT_TIMEOUT_SECONDS,
            worker.SIM4_TOKEN_TOTAL_TIMEOUT_SECONDS,
            worker.SIM4_TOKEN_RESPONSE_MAX_BYTES,
        )


def test_authx_client_forwards_exact_endpoint_budgets_and_response_cap():
    calls = []

    def requester(url, body, headers, connect_timeout, total_timeout, limit):
        calls.append((url, body, headers, connect_timeout, total_timeout, limit))
        return (
            200,
            url,
            b'{"access_token":"token","token_type":"Bearer","expires_in":30}',
        )

    token = worker.AuthXTokenClient(
        "client", "secret", requester=requester).fetch()

    assert token.access_token == "token"
    assert calls[0][0] == worker.SIM4_AUTHX_TOKEN_URL
    assert calls[0][3:] == (
        5.0,
        10.0,
        16 * 1024,
    )
    assert calls[0][2]["Content-Length"] == str(len(calls[0][1]))


@pytest.mark.parametrize(
    ("last_chunk", "expected_error"),
    ((b"", None), (b"x", "exceeds 16 KiB")),
)
def test_authx_http_response_has_exact_16_kib_cap(
        monkeypatch, last_chunk, expected_error):
    chunks = deque([b"a" * 4096] * 4 + [last_chunk])
    read_amounts = []

    class Socket:
        @staticmethod
        def settimeout(_timeout):
            return None

    class Response:
        status = 200

        @staticmethod
        def read1(amount):
            read_amounts.append(amount)
            return chunks.popleft()

    class Connection:
        def __init__(self, *_args, **_kwargs):
            self.sock = Socket()

        @staticmethod
        def connect():
            return None

        @staticmethod
        def request(*_args, **_kwargs):
            return None

        @staticmethod
        def getresponse():
            return Response()

        @staticmethod
        def close():
            return None

    monkeypatch.setattr(worker.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(worker.http.client, "HTTPSConnection", Connection)

    call = lambda: worker._default_token_requester(
        worker.SIM4_AUTHX_TOKEN_URL,
        b"request",
        {},
        worker.SIM4_TOKEN_CONNECT_TIMEOUT_SECONDS,
        worker.SIM4_TOKEN_TOTAL_TIMEOUT_SECONDS,
        worker.SIM4_TOKEN_RESPONSE_MAX_BYTES,
    )
    if expected_error is not None:
        with pytest.raises(worker.Sim4ProtocolError, match=expected_error):
            call()
    else:
        status, final_url, response_body = call()
        assert (status, final_url) == (200, worker.SIM4_AUTHX_TOKEN_URL)
        assert response_body == b"a" * worker.SIM4_TOKEN_RESPONSE_MAX_BYTES
    assert read_amounts == [4096, 4096, 4096, 4096, 1]


def test_entry_contract_has_no_environment_network_or_connection_opening_surface():
    source = ENTRY_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert imports.isdisjoint({"os", "socket", "ssl", "http", "urllib.request", "websocket"})
    assert not re.search(r"\b(?:connect|create_connection)\s*\(", source)
    assert not re.search(r"\b(?:environ|getenv)\b", source)


def test_bootstrap_requires_same_transaction_project_ref_before_creating_objects():
    assert "current_setting('atom_v9.sim_project_ref', true)" in SQL
    assert "configured_project_ref !~ '^[a-z0-9]{20}$'" in NORMAL_SQL
    assert not re.search(r"^\s*(?:BEGIN|START\s+TRANSACTION|COMMIT)\s*;",
                         SQL, re.IGNORECASE | re.MULTILINE)
    refusal_end = SQL.index("$atom_v9_sim_refusal_gate$;", 1)
    first_create = min(
        match.start() for match in re.finditer(
            r"^CREATE\s+(?:ROLE|TABLE|SEQUENCE|FUNCTION|INDEX|TRIGGER|POLICY)\b",
            SQL, re.IGNORECASE | re.MULTILINE)
    )
    assert refusal_end < first_create
    refusal = SQL[:refusal_end]
    for catalog in (
        "pg_catalog.pg_class", "pg_catalog.pg_namespace",
        "pg_catalog.pg_foreign_data_wrapper", "pg_catalog.pg_foreign_server",
        "pg_catalog.pg_user_mapping", "pg_catalog.pg_foreign_table",
        "pg_catalog.pg_roles", "pg_catalog.pg_proc", "pg_catalog.pg_trigger",
        "pg_catalog.pg_policy", "pg_catalog.pg_type",
    ):
        assert catalog in refusal
    assert "relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')" in refusal
    assert "namespace.nspname ~ '^atom_'" in refusal
    assert "production-shaped object or role exists" in refusal


def test_bootstrap_installation_singleton_is_exact_and_runtime_immutable():
    table = re.search(
        r"CREATE TABLE public\.atom_v9_sim_installation \((.*?)\n\);",
        SQL, re.DOTALL)
    assert table is not None
    declarations = [
        line.strip().rstrip(",")
        for line in table.group(1).splitlines()
        if re.match(r"\s{4}[a-z][a-z_]+\s", line)
    ]
    assert len(declarations) == 3
    assert declarations[0].startswith("installation_id text PRIMARY KEY")
    assert declarations[1].startswith("project_ref text UNIQUE NOT NULL")
    assert declarations[2] == (
        "created_at timestamptz NOT NULL DEFAULT transaction_timestamp()")
    assert "'ATOM_TRUE_V9_SIM_INSTALLATION_1'" in table.group(1)
    assert "pg_catalog.current_setting('atom_v9.sim_project_ref', true)" in NORMAL_SQL
    assert (
        "BEFORE INSERT OR UPDATE OR DELETE ON public.atom_v9_sim_installation "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation()"
    ) in NORMAL_SQL
    assert (
        "BEFORE TRUNCATE ON public.atom_v9_sim_installation FOR EACH STATEMENT "
        "EXECUTE FUNCTION public.atom_v9_sim_reject_mutation()"
    ) in NORMAL_SQL


def test_bootstrap_roles_are_distinct_fixed_noninheriting_and_passwordless():
    options = (
        "NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
        "NOBYPASSRLS"
    )
    assert f"CREATE ROLE atom_v9_sim_owner WITH NOLOGIN {options};" in NORMAL_SQL
    for role in (SIM_PUBLISHER_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE):
        assert f"CREATE ROLE {role} WITH LOGIN {options};" in NORMAL_SQL
    assert "PASSWORD" not in SQL.upper()
    assert not re.search(r"\bALTER\s+ROLE\b", SQL, re.IGNORECASE)
    assert not re.search(
        r"\bGRANT\s+(?:atom_v9_sim_owner|atom_v9_sim_runtime|"
        r"atom_v9_sim_entry_runtime)\s+TO\s+"
        r"(?:atom_v9_sim_runtime|atom_v9_sim_entry_runtime)\b",
        NORMAL_SQL, re.IGNORECASE)
    assert "'GRANT atom_v9_sim_owner TO %I'" in SQL
    assert "'REVOKE atom_v9_sim_owner FROM %I'" in SQL
    assert SQL.index("'GRANT atom_v9_sim_owner TO %I'") < SQL.index(
        "'REVOKE atom_v9_sim_owner FROM %I'")
    assert "FROM pg_catalog.pg_auth_members AS membership" in NORMAL_SQL
    assert (
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC;"
    ) in NORMAL_SQL


def test_bootstrap_grants_are_asymmetric_and_sequence_is_owner_only():
    assert (
        "GRANT SELECT, INSERT ON TABLE public.atom_v9_sim_intents "
        "TO atom_v9_sim_runtime;"
    ) in NORMAL_SQL
    assert (
        "GRANT SELECT ON TABLE public.atom_v9_sim_intents "
        "TO atom_v9_sim_entry_runtime;"
    ) in NORMAL_SQL
    assert (
        "GRANT SELECT ON TABLE public.atom_v9_sim_intent_publications "
        "TO atom_v9_sim_entry_runtime;"
    ) in NORMAL_SQL
    assert (
        "GRANT SELECT, INSERT ON TABLE public.atom_v9_sim_entries "
        "TO atom_v9_sim_entry_runtime;"
    ) in NORMAL_SQL
    assert (
        "GRANT SELECT ON TABLE public.atom_v9_sim4_reconciliation_checkpoint "
        "TO atom_v9_sim_entry_runtime;"
    ) in NORMAL_SQL
    grant_statements = re.findall(r"\bGRANT\s+.*?;", NORMAL_SQL,
                                  re.IGNORECASE)
    login_grants = [grant for grant in grant_statements if re.search(
        r"\bTO\b.*\b(?:atom_v9_sim_runtime|atom_v9_sim_entry_runtime)\b",
        grant, re.IGNORECASE)]
    assert not any(re.search(r"\b(?:UPDATE|DELETE|TRUNCATE|CREATE|OWNERSHIP)\b", grant,
                             re.IGNORECASE) for grant in login_grants)
    assert not any("ON SEQUENCE" in grant.upper() for grant in grant_statements)
    assert (
        "REVOKE ALL PRIVILEGES ON SEQUENCE "
        "public.atom_v9_sim4_intent_admission_seq FROM PUBLIC, "
        "atom_v9_sim_runtime, atom_v9_sim_entry_runtime;"
    ) in NORMAL_SQL


def test_bootstrap_forces_rls_and_exposes_only_frozen_login_role_paths():
    tables = (
        "atom_v9_sim_installation",
        "atom_v9_sim_intents",
        "atom_v9_sim_intent_publications",
        "atom_v9_sim_entries",
        "atom_v9_sim4_reconciliation_checkpoint",
    )
    for table in tables:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in NORMAL_SQL
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;" in NORMAL_SQL
        assert f"ALTER TABLE public.{table} OWNER TO atom_v9_sim_owner;" in NORMAL_SQL
    policies = re.findall(
        r"CREATE POLICY (\w+) ON public\.(\w+) (.*?);",
        NORMAL_SQL, re.IGNORECASE)
    login_policies = [policy for policy in policies if re.search(
        r"\bTO\s+(?:atom_v9_sim_runtime|atom_v9_sim_entry_runtime)\b",
        policy[2], re.IGNORECASE)]
    assert {(table, body) for _, table, body in login_policies} == {
        ("atom_v9_sim_installation",
         "FOR SELECT TO atom_v9_sim_runtime USING (true)"),
        ("atom_v9_sim_installation",
         "FOR SELECT TO atom_v9_sim_entry_runtime USING (true)"),
        ("atom_v9_sim_intents",
         "FOR SELECT TO atom_v9_sim_runtime USING (true)"),
        ("atom_v9_sim_intents",
         "FOR INSERT TO atom_v9_sim_runtime WITH CHECK (true)"),
        ("atom_v9_sim_intents",
         "FOR SELECT TO atom_v9_sim_entry_runtime USING (true)"),
        ("atom_v9_sim_intent_publications",
         "FOR SELECT TO atom_v9_sim_entry_runtime USING (true)"),
        ("atom_v9_sim_entries",
         "FOR SELECT TO atom_v9_sim_entry_runtime USING (true)"),
        ("atom_v9_sim_entries",
         "FOR INSERT TO atom_v9_sim_entry_runtime WITH CHECK (true)"),
        ("atom_v9_sim4_reconciliation_checkpoint",
         "FOR SELECT TO atom_v9_sim_entry_runtime USING (true)"),
    }


def test_bootstrap_has_exact_hardened_definers_and_publication_lock_pair():
    assert len(re.findall(r"\bSECURITY\s+DEFINER\b", SQL,
                         re.IGNORECASE)) == 3
    assert len(re.findall(r"\bSECURITY\s+INVOKER\b", SQL,
                         re.IGNORECASE)) == 2
    for function in (
        "atom_v9_sim4_publish_intent_after",
        "atom_v9_sim4_read_intent_admission_fence",
        "atom_v9_sim4_compare_and_advance_checkpoint",
    ):
        body = re.search(
            rf"CREATE FUNCTION public\.{function}\(.*?\n\$[a-z0-9_]+\$;",
            SQL, re.DOTALL | re.IGNORECASE)
        assert body is not None
        assert "SECURITY DEFINER" in body.group(0)
        assert "SET search_path = pg_catalog" in body.group(0)
        assert f"ALTER FUNCTION public.{function}(" in NORMAL_SQL
    assert "pg_catalog.pg_advisory_xact_lock_shared( 1158704842749668574::bigint )" in NORMAL_SQL
    assert (
        "BEFORE INSERT ON public.atom_v9_sim_intents FOR EACH ROW EXECUTE FUNCTION "
        "public.atom_v9_sim4_lock_intent_admission_before()"
    ) in NORMAL_SQL
    assert (
        "AFTER INSERT ON public.atom_v9_sim_intents FOR EACH ROW EXECUTE FUNCTION "
        "public.atom_v9_sim4_publish_intent_after()"
    ) in NORMAL_SQL
    assert "SESSION_USER::text <> 'atom_v9_sim_entry_runtime'" in NORMAL_SQL
    assert "pg_catalog.pg_try_advisory_xact_lock( 1158704842749668574::bigint )" in NORMAL_SQL


def test_bootstrap_revokes_public_api_roles_and_creates_no_cross_database_surface():
    for role in ("PUBLIC", "anon", "authenticated", "service_role",
                 "atom_v9_v4_runtime"):
        assert role in SQL
    upper = SQL.upper()
    for forbidden in (
        "CREATE FOREIGN DATA WRAPPER", "CREATE SERVER", "CREATE USER MAPPING",
        "CREATE FOREIGN TABLE", "IMPORT FOREIGN SCHEMA", "CREATE EXTENSION",
        "CREATE DATABASE", "CREATE VIEW", "CREATE MATERIALIZED VIEW",
    ):
        assert forbidden not in upper
    assert not re.search(r"\b(?:postgres|postgresql)://", SQL, re.IGNORECASE)
    assert "PASSWORD" not in upper


def test_collection_hook_moves_only_bootstrap_ahead_of_legacy_database_tests():
    other_path = ROOT / "tests/test_historical_outcomes_postgres.py"
    original = [
        SimpleNamespace(name="legacy_first", path=other_path),
        SimpleNamespace(
            name=POSTGRES_BOOTSTRAP_TEST_NAME, path=Path(__file__)),
        SimpleNamespace(name="legacy_second", path=other_path),
    ]

    pytest_collection_modifyitems(original)

    assert [item.name for item in original] == [
        POSTGRES_BOOTSTRAP_TEST_NAME,
        "legacy_first",
        "legacy_second",
    ]


def test_bootstrap_executes_in_dedicated_disposable_postgres_database():
    database_url = os.environ.get("H2C_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("H2C_TEST_DATABASE_URL disposable PostgreSQL required")
    if os.environ.get("CI") != "true":
        pytest.skip("SIM-4 bootstrap integration runs only in explicit CI")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql as pg_sql

    parsed = urlsplit(database_url)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.port != 5432
        or parsed.username != "postgres"
        or parsed.path != "/postgres"
        or parsed.query
        or parsed.fragment
    ):
        pytest.fail(
            "SIM-4 bootstrap integration requires the exact local CI postgres DSN")

    database_name = f"atom_v9_sim4_isolation_{uuid4().hex[:12]}"
    simulator_url = urlunsplit((
        parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, ""))
    sim_roles = (
        "atom_v9_sim_owner",
        SIM_PUBLISHER_RUNTIME_ROLE,
        SIM_ENTRY_RUNTIME_ROLE,
    )
    integration_lock_key = 772642391846415907
    admin = None
    simulator = None
    lock_acquired = False
    database_created = False
    roles_created = False

    try:
        admin = psycopg.connect(database_url, autocommit=True)
        with admin.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone() != ("postgres",):
                pytest.fail(
                    "refusing SIM-4 bootstrap outside the local CI postgres DB")
            cursor.execute(
                "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole "
                "FROM pg_catalog.pg_roles WHERE rolname = current_user"
            )
            authority = cursor.fetchone()
            if authority is None or authority[1:] != (True, True, True):
                pytest.skip("local CI PostgreSQL superuser authority required")
            cursor.execute(
                "SELECT pg_catalog.pg_advisory_lock(%s::bigint)",
                (integration_lock_key,),
            )
            lock_acquired = True
            cursor.execute(
                "SELECT rolname FROM pg_catalog.pg_roles "
                "WHERE rolname = ANY(%s) ORDER BY rolname",
                (list(sim_roles),),
            )
            preexisting_roles = tuple(row[0] for row in cursor.fetchall())
            if preexisting_roles:
                pytest.fail(
                    "refusing to adopt or drop pre-existing SIM roles: "
                    + ", ".join(preexisting_roles))
            cursor.execute(
                "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s",
                (database_name,),
            )
            if cursor.fetchone() is not None:
                pytest.fail("refusing pre-existing SIM-4 integration database")
            cursor.execute(
                pg_sql.SQL("CREATE DATABASE {}").format(
                    pg_sql.Identifier(database_name)))
            database_created = True

        # The migration itself owns no transaction control.  Execute it with
        # the operator's exact BEGIN/SET LOCAL/.../COMMIT boundary.
        migration_connection = psycopg.connect(simulator_url, autocommit=True)
        try:
            with migration_connection.transaction():
                with migration_connection.cursor() as cursor:
                    cursor.execute(
                        pg_sql.SQL(
                            "SET LOCAL atom_v9.sim_project_ref = {}"
                        ).format(pg_sql.Literal(SIM_PROJECT_REF)))
                    cursor.execute(SQL)
            roles_created = True
        finally:
            migration_connection.close()

        simulator = psycopg.connect(simulator_url, autocommit=True)
        with simulator.cursor() as cursor:
            cursor.execute(
                "SELECT installation_id, project_ref "
                "FROM public.atom_v9_sim_installation"
            )
            assert cursor.fetchall() == [(
                SIM_INSTALLATION_ID, SIM_PROJECT_REF)]
            cursor.execute(
                "SELECT checkpoint_key, last_completed_publication_seq, "
                "checkpoint_version, runtime_started_at "
                "FROM public.atom_v9_sim4_reconciliation_checkpoint"
            )
            assert cursor.fetchall() == [(
                "ATOM_TRUE_V9_SIM4_RECONCILIATION_1", 0, 0, None)]

            cursor.execute(
                "SELECT rolname, rolcanlogin, rolinherit, rolsuper, "
                "rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, "
                "rolpassword IS NULL FROM pg_catalog.pg_authid "
                "WHERE rolname = ANY(%s)",
                (list(sim_roles),),
            )
            roles = {row[0]: row[1:] for row in cursor.fetchall()}
            assert roles == {
                "atom_v9_sim_owner": (
                    False, False, False, False, False, False, False, True),
                SIM_PUBLISHER_RUNTIME_ROLE: (
                    True, False, False, False, False, False, False, True),
                SIM_ENTRY_RUNTIME_ROLE: (
                    True, False, False, False, False, False, False, True),
            }
            cursor.execute(
                "SELECT granted.rolname, member.rolname "
                "FROM pg_catalog.pg_auth_members AS membership "
                "JOIN pg_catalog.pg_roles AS granted "
                "ON granted.oid = membership.roleid "
                "JOIN pg_catalog.pg_roles AS member "
                "ON member.oid = membership.member "
                "WHERE granted.rolname = ANY(%s) OR member.rolname = ANY(%s)",
                (list(sim_roles), list(sim_roles)),
            )
            assert cursor.fetchall() == []
            for role in sim_roles:
                cursor.execute(
                    "SELECT pg_catalog.has_schema_privilege(%s, 'public', 'CREATE')",
                    (role,),
                )
                assert cursor.fetchone() == (False,)

            tables = (
                "atom_v9_sim_installation",
                "atom_v9_sim_intents",
                "atom_v9_sim_intent_publications",
                "atom_v9_sim_entries",
                "atom_v9_sim4_reconciliation_checkpoint",
            )
            cursor.execute(
                "SELECT relation.relname, owner.rolname, "
                "relation.relrowsecurity, relation.relforcerowsecurity "
                "FROM pg_catalog.pg_class AS relation "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid = relation.relnamespace "
                "JOIN pg_catalog.pg_roles AS owner "
                "ON owner.oid = relation.relowner "
                "WHERE namespace.nspname = 'public' "
                "AND relation.relname = ANY(%s)",
                (list(tables),),
            )
            table_security = {
                row[0]: row[1:] for row in cursor.fetchall()
            }
            assert table_security == {
                table: ("atom_v9_sim_owner", True, True)
                for table in tables
            }
            cursor.execute(
                "SELECT owner.rolname, relation.relkind "
                "FROM pg_catalog.pg_class AS relation "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid = relation.relnamespace "
                "JOIN pg_catalog.pg_roles AS owner "
                "ON owner.oid = relation.relowner "
                "WHERE namespace.nspname = 'public' "
                "AND relation.relname = "
                "'atom_v9_sim4_intent_admission_seq'"
            )
            assert cursor.fetchone() == ("atom_v9_sim_owner", "S")

            cursor.execute(
                "SELECT procedure.proname, owner.rolname, "
                "procedure.prosecdef, procedure.proconfig "
                "FROM pg_catalog.pg_proc AS procedure "
                "JOIN pg_catalog.pg_namespace AS namespace "
                "ON namespace.oid = procedure.pronamespace "
                "JOIN pg_catalog.pg_roles AS owner "
                "ON owner.oid = procedure.proowner "
                "WHERE namespace.nspname = 'public' "
                "AND procedure.proname LIKE 'atom_v9_sim%' "
                "ORDER BY procedure.proname"
            )
            functions = cursor.fetchall()
            assert len(functions) == 5
            definers = {
                "atom_v9_sim4_publish_intent_after",
                "atom_v9_sim4_read_intent_admission_fence",
                "atom_v9_sim4_compare_and_advance_checkpoint",
            }
            assert {row[0] for row in functions if row[2]} == definers
            for name, owner, _definer, settings in functions:
                assert owner == "atom_v9_sim_owner"
                assert settings is not None
                assert "search_path=pg_catalog" in settings

            allowed = {
                SIM_PUBLISHER_RUNTIME_ROLE: {
                    ("atom_v9_sim_installation", "SELECT"),
                    ("atom_v9_sim_intents", "SELECT"),
                    ("atom_v9_sim_intents", "INSERT"),
                },
                SIM_ENTRY_RUNTIME_ROLE: {
                    ("atom_v9_sim_installation", "SELECT"),
                    ("atom_v9_sim_intents", "SELECT"),
                    ("atom_v9_sim_intent_publications", "SELECT"),
                    ("atom_v9_sim_entries", "SELECT"),
                    ("atom_v9_sim_entries", "INSERT"),
                    ("atom_v9_sim4_reconciliation_checkpoint", "SELECT"),
                },
            }
            for role in (SIM_PUBLISHER_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE):
                for table in tables:
                    for privilege in (
                            "SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute(
                            "SELECT pg_catalog.has_table_privilege(%s, %s, %s)",
                            (role, f"public.{table}", privilege),
                        )
                        assert cursor.fetchone() == (
                            (table, privilege) in allowed[role],)
                for privilege in ("USAGE", "SELECT", "UPDATE"):
                    cursor.execute(
                        "SELECT pg_catalog.has_sequence_privilege(%s, %s, %s)",
                        (role, "public.atom_v9_sim4_intent_admission_seq",
                         privilege),
                    )
                    assert cursor.fetchone() == (False,)

            function_signatures = {
                "reject": "public.atom_v9_sim_reject_mutation()",
                "lock": "public.atom_v9_sim4_lock_intent_admission_before()",
                "publish": "public.atom_v9_sim4_publish_intent_after()",
                "fence": "public.atom_v9_sim4_read_intent_admission_fence()",
                "checkpoint": (
                    "public.atom_v9_sim4_compare_and_advance_checkpoint("
                    "bigint,bigint,bigint,text,bigint,timestamptz)"),
            }
            for role in (SIM_PUBLISHER_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE):
                for name, signature in function_signatures.items():
                    cursor.execute(
                        "SELECT pg_catalog.has_function_privilege(%s, %s, 'EXECUTE')",
                        (role, signature),
                    )
                    assert cursor.fetchone() == (
                        role == SIM_ENTRY_RUNTIME_ROLE
                        and name in {"fence", "checkpoint"},)

        intent = build_worker_intent(100, final_bps=0.0)
        intent_parameters = (
            intent.intent_id, intent.intent_hash, intent.contract_version,
            intent.canonicalization_version, intent.simulator_version,
            intent.symbol, intent.horizon, intent.horizon_seconds,
            intent.cutoff_at, intent.eligible_at, intent.source_v3_status,
            intent.decision, intent.status,
            serialize_simulation_trade_intent(intent),
        )
        insert_intent = (
            "INSERT INTO public.atom_v9_sim_intents ("
            "intent_id, intent_hash, contract_version, canonicalization_version, "
            "simulator_version, symbol, horizon, horizon_seconds, cutoff_at, "
            "eligible_at, source_v3_status, decision, status, record_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING RETURNING intent_id"
        )
        with simulator.cursor() as cursor:
            cursor.execute(
                pg_sql.SQL("SET SESSION AUTHORIZATION {}").format(
                    pg_sql.Identifier(SIM_PUBLISHER_RUNTIME_ROLE)))
            try:
                cursor.execute(insert_intent, intent_parameters)
                assert cursor.fetchone() == (intent.intent_id,)
                cursor.execute(insert_intent, intent_parameters)
                assert cursor.fetchone() is None
                with pytest.raises(psycopg.Error) as denied:
                    cursor.execute(
                        "SELECT publication_seq "
                        "FROM public.atom_v9_sim_intent_publications"
                    )
                assert denied.value.sqlstate == "42501"
            finally:
                cursor.execute("RESET SESSION AUTHORIZATION")

            cursor.execute(
                "SELECT publication_seq, intent_id, publication_at, horizon_order "
                "FROM public.atom_v9_sim_intent_publications"
            )
            assert cursor.fetchall() == [(
                1, intent.intent_id, intent.eligible_at, 1)]
            cursor.execute(
                "SELECT last_value, is_called "
                "FROM public.atom_v9_sim4_intent_admission_seq"
            )
            assert cursor.fetchone() == (1, True)

        entry = build_simulation_entry_record(
            intent=intent, entry_status="SKIPPED_NO_TRADE")
        entry_columns = (
            "entry_id, entry_hash, contract_version, canonicalization_version, "
            "simulator_version, symbol, horizon, horizon_seconds, intent_id, "
            "publication_at, entry_deadline_at, decision, intent_status, "
            "entry_status, quantity_shares, blocking_entry_id, quote_id, "
            "quote_hash, quote_source_spec, quote_event_ns, quote_accepted_at, "
            "entry_price, record_json"
        )
        with simulator.cursor() as cursor:
            cursor.execute(
                pg_sql.SQL("SET SESSION AUTHORIZATION {}").format(
                    pg_sql.Identifier(SIM_ENTRY_RUNTIME_ROLE)))
            try:
                cursor.execute(
                    f"INSERT INTO public.atom_v9_sim_entries ({entry_columns}) "
                    f"VALUES ({', '.join(('%s',) * 23)}) RETURNING entry_id",
                    entry_database_row(entry),
                )
                assert cursor.fetchone() == (entry.entry_id,)
                cursor.execute(
                    "SELECT public.atom_v9_sim4_read_intent_admission_fence()"
                )
                assert cursor.fetchone() == (1,)
                cursor.execute(
                    "SELECT public.atom_v9_sim4_compare_and_advance_checkpoint("
                    "%s, %s, %s, %s, %s, %s)",
                    (0, 0, 1, "RECONCILIATION", 1, WORKER_T0),
                )
                assert cursor.fetchone() == (True,)
                cursor.execute(
                    "SELECT public.atom_v9_sim4_compare_and_advance_checkpoint("
                    "%s, %s, %s, %s, %s, %s)",
                    (0, 0, 1, "RECONCILIATION", 1, WORKER_T0),
                )
                assert cursor.fetchone() == (False,)
            finally:
                cursor.execute("RESET SESSION AUTHORIZATION")
            cursor.execute(
                "SELECT last_completed_publication_seq, checkpoint_version, "
                "runtime_started_at FROM public.atom_v9_sim4_reconciliation_checkpoint"
            )
            assert cursor.fetchone() == (1, 1, WORKER_T0)
    finally:
        if simulator is not None:
            simulator.close()
        if admin is not None:
            try:
                with admin.cursor() as cursor:
                    if database_created:
                        cursor.execute(
                            "SELECT pg_catalog.pg_terminate_backend(pid) "
                            "FROM pg_catalog.pg_stat_activity "
                            "WHERE datname = %s AND pid <> pg_catalog.pg_backend_pid()",
                            (database_name,),
                        )
                        cursor.execute(
                            pg_sql.SQL("DROP DATABASE {}").format(
                                pg_sql.Identifier(database_name)))
                    if roles_created:
                        cursor.execute(
                            pg_sql.SQL("DROP ROLE {}, {}, {}").format(
                                pg_sql.Identifier(SIM_ENTRY_RUNTIME_ROLE),
                                pg_sql.Identifier(SIM_PUBLISHER_RUNTIME_ROLE),
                                pg_sql.Identifier("atom_v9_sim_owner"),
                            ))
                    if lock_acquired:
                        cursor.execute(
                            "SELECT pg_catalog.pg_advisory_unlock(%s::bigint)",
                            (integration_lock_key,),
                        )
            finally:
                admin.close()
