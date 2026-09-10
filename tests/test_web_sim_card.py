"""SIM-5W read-only simulation web card.

Authority: docs/sim-5w-read-only-sim-web-card-freeze.md.  These tests freeze
the dedicated reader credential boundary, the exact read path, the card's
presentation, and migration 032's privilege set.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

from quant import web
from quant.v9_sim4_entry import (
    SIM_ENTRY_RUNTIME_ROLE,
    SIM_PUBLISHER_RUNTIME_ROLE,
    SimulationDatabaseConfigurationError,
    validate_simulator_database_url,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "032_authorize_sim_web_reader.sql"
SQL = MIGRATION.read_text(encoding="utf-8")
NORMAL_SQL = " ".join(SQL.split())
BOOTSTRAP_MIGRATION = ROOT / "migrations" / "027_create_v9_sim_entries.sql"
RESOLUTION_MIGRATION = ROOT / "migrations" / "031_create_v9_sim_resolutions.sql"

READER_ROLE = "atom_v9_sim_web_reader"
SIM_PROJECT_REF = "abcdefghijklmnopqrst"
PRODUCTION_PROJECT_REF = "zyxwvutsrqponmlkjihg"
UTC = timezone.utc
NOW_EPOCH = 1_770_000_000.0
NOW = datetime.fromtimestamp(NOW_EPOCH, tz=UTC)
HORIZONS = web.PHASE_E_HORIZONS
FROZEN_STATEMENTS = (
    "SET LOCAL statement_timeout = '2000ms'",
    "SELECT horizon, resolution_status, count(*) AS n "
    "FROM public.atom_v9_sim_resolutions "
    "GROUP BY horizon, resolution_status",
    "SELECT max(created_at) FROM public.atom_v9_sim_resolutions",
)


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


def valid_environment(**changes):
    values = {
        "DATABASE_URL": direct_dsn("atom_v9_v4_runtime", PRODUCTION_PROJECT_REF),
        web.SIMULATOR_PROJECT_REF_ENV: SIM_PROJECT_REF,
        web.SIM_WEB_READONLY_DATABASE_URL_ENV: direct_dsn(READER_ROLE),
    }
    values.update(changes)
    return values


def request(app, path):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({"PATH_INFO": path}, start_response))
    return response


class ScriptedCursor:
    def __init__(self, *, grouped=(), latest=(None,), fail_at=None,
                 error=RuntimeError("scripted failure")):
        self._grouped = list(grouped)
        self._latest = latest
        self._fail_at = fail_at
        self._error = error
        self.executions: list[tuple[str, object]] = []
        self.closed = False
        self._pending = None

    def execute(self, sql, params=None):
        self.executions.append((sql, params))
        if self._fail_at is not None and len(self.executions) == self._fail_at:
            raise self._error
        if sql == FROZEN_STATEMENTS[1]:
            self._pending = ("all", self._grouped)
        elif sql == FROZEN_STATEMENTS[2]:
            self._pending = ("one", self._latest)
        else:
            self._pending = None

    def fetchall(self):
        kind, value = self._pending
        assert kind == "all"
        return list(value)

    def fetchone(self):
        kind, value = self._pending
        assert kind == "one"
        return value

    def close(self):
        self.closed = True


class ScriptedConnection:
    def __init__(self, cursor, *, reject_read_only=False):
        self._cursor = cursor
        self._reject_read_only = reject_read_only
        self.read_only_history: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    @property
    def read_only(self):
        return self.read_only_history[-1] if self.read_only_history else None

    @read_only.setter
    def read_only(self, value):
        if self._reject_read_only:
            raise RuntimeError("read-only mode unavailable")
        self.read_only_history.append(value)

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def scripted_factory(*, grouped=(), latest=(None,), fail_at=None,
                     error=RuntimeError("scripted failure"),
                     reject_read_only=False):
    cursor = ScriptedCursor(grouped=grouped, latest=latest, fail_at=fail_at,
                            error=error)
    connection = ScriptedConnection(cursor, reject_read_only=reject_read_only)
    calls = []

    def factory():
        calls.append("connected")
        return connection

    return factory, connection, cursor, calls


def card_block(page: str) -> str:
    start = page.index("<h2>SIM — PAPER ONLY</h2>")
    end = page.index("<h2>12 QUANT FAMILIES</h2>")
    return page[start:end]


def card_status(page: str) -> str:
    match = re.search(
        r'data-dashboard-field="sim_paper_only\.status">([^<]*)</span>', page)
    assert match is not None
    return match.group(1)


def card_cells(page: str) -> dict[str, list[str]]:
    block = card_block(page)
    cells: dict[str, list[str]] = {row: [] for row in web.SIM5W_ROWS}
    for row, index, value in re.findall(
            r'data-dashboard-field="sim_paper_only\.([A-Z]+)\.(\d)">([^<]*)</td>',
            block):
        cells[row].append(value)
    for row in web.SIM5W_ROWS:
        assert len(cells[row]) == 6
    return cells


def card_headers(page: str) -> list[str]:
    block = card_block(page)
    head = block.split("<thead>", 1)[1].split("</thead>", 1)[0]
    return re.findall(r"<th>([^<]*)</th>", head)


# ---------------------------------------------------------------------------
# Reader credential boundary (freeze sections 1, 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "environment",
    (
        {},
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV: ""}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV: "not-a-url"}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV: "postgresql://"}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             direct_dsn(READER_ROLE) + " "}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE)}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             direct_dsn(SIM_ENTRY_RUNTIME_ROLE)}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             direct_dsn("atom_v9_v4_runtime")}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             pooler_dsn(SIM_PUBLISHER_RUNTIME_ROLE)}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             direct_dsn(READER_ROLE, PRODUCTION_PROJECT_REF)}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             pooler_dsn(READER_ROLE, PRODUCTION_PROJECT_REF)}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             direct_dsn(READER_ROLE, port=6543)}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             direct_dsn(READER_ROLE, sslmode="prefer")}),
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV:
                             "postgresql://atom_v9_sim_web_reader:secret@example.com:5432/postgres?sslmode=require"}),
        valid_environment(**{web.SIMULATOR_PROJECT_REF_ENV: ""}),
        valid_environment(**{web.SIMULATOR_PROJECT_REF_ENV: "UPPERCASEPROJECTREF"}),
        valid_environment(DATABASE_URL=""),
        valid_environment(DATABASE_URL=direct_dsn("atom_v9_v4_runtime", SIM_PROJECT_REF)),
        valid_environment(DATABASE_URL="postgresql://prod:secret@example.com:5432/db"),
    ),
)
def test_reader_factory_fails_closed_without_io(environment):
    calls = []
    factory = web._sim_web_reader_connection_factory(
        environment, lambda url: calls.append(url))
    assert factory is None
    assert calls == []


@pytest.mark.parametrize("name", sorted(web._SIMULATOR_WORKER_CREDENTIAL_ENVS))
@pytest.mark.parametrize("value", ("worker-secret", ""))
def test_reader_factory_rejects_worker_credentials_by_presence_without_io(name, value):
    calls = []
    factory = web._sim_web_reader_connection_factory(
        valid_environment(**{name: value}), lambda url: calls.append(url))
    assert factory is None
    assert calls == []


@pytest.mark.parametrize("name", sorted(web._SIMULATOR_WORKER_CREDENTIAL_ENVS))
@pytest.mark.parametrize("value", ("worker-secret", ""))
def test_existing_publisher_worker_credential_rejection_is_unchanged(name, value):
    environment = {
        "DATABASE_URL": direct_dsn("atom_v9_v4_runtime", PRODUCTION_PROJECT_REF),
        web.SIMULATOR_DATABASE_URL_ENV: direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE),
        web.SIMULATOR_PROJECT_REF_ENV: SIM_PROJECT_REF,
        name: value,
    }
    calls = []
    factory = web._isolated_simulator_connection_factory(
        environment, lambda: calls.append("connected"))
    assert factory is None
    assert calls == []


@pytest.mark.parametrize(
    "url",
    (direct_dsn(READER_ROLE), pooler_dsn(READER_ROLE)),
)
def test_reader_factory_accepts_only_the_dedicated_role_and_binds_the_exact_dsn(url):
    calls = []
    connection = object()
    factory = web._sim_web_reader_connection_factory(
        valid_environment(**{web.SIM_WEB_READONLY_DATABASE_URL_ENV: url}),
        lambda database_url: calls.append(database_url) or connection)
    assert callable(factory)
    assert calls == []
    assert factory() is connection
    assert calls == [url]


def test_shared_validator_accepts_the_reader_role_and_still_rejects_unlisted_roles():
    identity = validate_simulator_database_url(
        direct_dsn(READER_ROLE), project_ref=SIM_PROJECT_REF,
        required_role=READER_ROLE)
    assert identity.role == READER_ROLE
    assert identity.project_ref == SIM_PROJECT_REF
    for other in ("atom_v9_v4_runtime", "postgres", "atom_v9_sim_owner", ""):
        with pytest.raises(SimulationDatabaseConfigurationError):
            validate_simulator_database_url(
                direct_dsn(other), project_ref=SIM_PROJECT_REF,
                required_role=other)
    with pytest.raises(SimulationDatabaseConfigurationError):
        validate_simulator_database_url(
            direct_dsn(SIM_PUBLISHER_RUNTIME_ROLE), project_ref=SIM_PROJECT_REF,
            required_role=READER_ROLE)


# ---------------------------------------------------------------------------
# Exact read path (freeze section 6)
# ---------------------------------------------------------------------------


def test_read_runs_exactly_the_frozen_statements_read_only_without_commit_or_lock():
    factory, connection, cursor, calls = scripted_factory(
        grouped=[("5M", "RESOLVED", 3)], latest=(NOW,))

    result = web._read_sim_paper_only_counts(factory, now_epoch=NOW_EPOCH)

    assert calls == ["connected"]
    assert [sql for sql, _ in cursor.executions] == list(FROZEN_STATEMENTS)
    assert all(params is None for _, params in cursor.executions)
    assert connection.read_only_history == [True]
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed and cursor.closed
    for sql, _ in cursor.executions:
        assert "advisory" not in sql.lower()
        assert "atom_v9_sim_entries" not in sql
        assert "record_json" not in sql
        assert "return_bps" not in sql
    assert result["status"] == "LIVE"
    assert result["counts"]["RESOLVED"][HORIZONS.index("5M")] == 3


def test_read_without_a_factory_performs_no_io_and_renders_no_data():
    result = web._read_sim_paper_only_counts(None, now_epoch=NOW_EPOCH)
    assert result == web._sim_paper_only_no_data()
    assert result["status"] == "NO DATA"
    assert all(value is None for row in web.SIM5W_ROWS for value in result["counts"][row])


def test_read_only_mode_failure_fails_closed_before_any_statement():
    factory, connection, cursor, _ = scripted_factory(
        grouped=[("5M", "RESOLVED", 3)], latest=(NOW,), reject_read_only=True)
    result = web._read_sim_paper_only_counts(factory, now_epoch=NOW_EPOCH)
    assert result["status"] == "NO DATA"
    assert cursor.executions == []
    assert connection.commits == 0
    assert connection.closed


# ---------------------------------------------------------------------------
# Count assembly and status semantics (freeze sections 4, 5)
# ---------------------------------------------------------------------------


def test_zero_rows_render_no_data_with_blank_cells_not_zeros():
    factory, *_ = scripted_factory(grouped=[], latest=(None,))
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    page = request(app, "/")["body"].decode()
    assert card_status(page) == "NO DATA"
    cells = card_cells(page)
    assert cells == {row: [""] * 6 for row in web.SIM5W_ROWS}
    assert ">0<" not in card_block(page)


@pytest.mark.parametrize(
    "age_seconds,expected",
    (
        (0.0, "LIVE"),
        (89 * 60, "LIVE"),
        (90 * 60, "LIVE"),
        (90 * 60 + 0.001, "STALE"),
        (90 * 60 + 1, "STALE"),
        (7 * 24 * 3600, "STALE"),
        (-60.0, "LIVE"),
    ),
)
def test_freshness_live_stale_and_exact_ninety_minute_boundary(age_seconds, expected):
    latest = datetime.fromtimestamp(NOW_EPOCH - age_seconds, tz=UTC)
    factory, *_ = scripted_factory(grouped=[("30S", "RESOLVED", 1)], latest=(latest,))
    result = web._read_sim_paper_only_counts(factory, now_epoch=NOW_EPOCH)
    assert result["status"] == expected
    assert web.SIM5W_LIVE_WINDOW == timedelta(minutes=90)


def test_counts_group_correctly_and_closed_equals_resolved_plus_unresolved():
    grouped = [
        ("30S", "RESOLVED", 4),
        ("30S", "UNRESOLVED_WINDOW_EXPIRED", 1),
        ("30S", "UNRESOLVED_OBSERVATION_GAP", 2),
        ("1M", "UNRESOLVED_OBSERVATION_GAP", 5),
        ("5M", "RESOLVED", 7),
        ("15M", "RESOLVED", 1),
        ("15M", "UNRESOLVED_WINDOW_EXPIRED", 1),
        ("1H", "UNRESOLVED_WINDOW_EXPIRED", 9),
    ]
    factory, *_ = scripted_factory(grouped=grouped, latest=(NOW,))
    result = web._read_sim_paper_only_counts(factory, now_epoch=NOW_EPOCH)
    counts = result["counts"]
    assert counts["RESOLVED"] == [4, 0, 7, 1, 0, 0]
    assert counts["UNRESOLVED"] == [3, 5, 0, 1, 0, 9]
    assert counts["CLOSED"] == [7, 5, 7, 2, 0, 9]
    for index in range(6):
        assert counts["CLOSED"][index] == (
            counts["RESOLVED"][index] + counts["UNRESOLVED"][index])
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    page = request(app, "/")["body"].decode()
    assert card_status(page) == "LIVE"
    assert card_cells(page) == {
        "CLOSED": ["7", "5", "7", "2", "0", "9"],
        "RESOLVED": ["4", "0", "7", "1", "0", "0"],
        "UNRESOLVED": ["3", "5", "0", "1", "0", "9"],
    }


def test_absent_canonical_horizon_renders_zero_counts_while_rows_exist_elsewhere():
    factory, *_ = scripted_factory(grouped=[("5M", "RESOLVED", 2)], latest=(NOW,))
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    page = request(app, "/")["body"].decode()
    assert card_status(page) == "LIVE"
    assert card_cells(page) == {
        "CLOSED": ["0", "0", "2", "0", "0", "0"],
        "RESOLVED": ["0", "0", "2", "0", "0", "0"],
        "UNRESOLVED": ["0", "0", "0", "0", "0", "0"],
    }


def test_non_canonical_horizons_are_discarded_not_rendered():
    factory, *_ = scripted_factory(
        grouped=[("2H", "RESOLVED", 50), ("1M", "RESOLVED", 1)], latest=(NOW,))
    result = web._read_sim_paper_only_counts(factory, now_epoch=NOW_EPOCH)
    assert result["counts"]["CLOSED"] == [0, 1, 0, 0, 0, 0]
    only_foreign, *_ = scripted_factory(grouped=[("2H", "RESOLVED", 50)], latest=(NOW,))
    assert web._read_sim_paper_only_counts(only_foreign, now_epoch=NOW_EPOCH)["status"] == "NO DATA"


@pytest.mark.parametrize(
    "grouped,latest",
    (
        ([("5M", "SOMETHING_ELSE", 1)], (NOW,)),
        ([("5M", "RESOLVED", "1")], (NOW,)),
        ([("5M", "RESOLVED", True)], (NOW,)),
        ([("5M", "RESOLVED", -1)], (NOW,)),
        ([("5M", "RESOLVED")], (NOW,)),
        ([("5M", "RESOLVED", 1, "extra")], (NOW,)),
        ([("5M", "RESOLVED", 1)], (None,)),
        ([("5M", "RESOLVED", 1)], None),
        ([("5M", "RESOLVED", 1)], (NOW.replace(tzinfo=None),)),
        ([("5M", "RESOLVED", 1)], ("2026-09-04T00:00:00Z",)),
    ),
)
def test_malformed_or_unknown_rows_fail_closed_to_no_data(grouped, latest):
    factory, connection, _, _ = scripted_factory(grouped=grouped, latest=latest)
    result = web._read_sim_paper_only_counts(factory, now_epoch=NOW_EPOCH)
    assert result == web._sim_paper_only_no_data()
    assert connection.commits == 0
    assert connection.closed


class _ExplodingFactory:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise ConnectionError("connection refused")


def _assert_other_cards_intact(page: str) -> None:
    assert "<h2>V9 DIRECTIONAL ACCURACY</h2>" in page
    assert "<h2>12 QUANT FAMILIES</h2>" in page
    assert "<h2>EVIDENCE</h2>" in page
    assert 'data-dashboard-field="final_numbers.BPS.0"' in page
    assert ">None<" not in page


def test_connection_failure_renders_no_data_without_affecting_other_cards():
    factory = _ExplodingFactory()
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    response = request(app, "/")
    page = response["body"].decode()
    assert response["status"] == "200 OK"
    assert factory.calls == 1
    assert card_status(page) == "NO DATA"
    assert card_cells(page) == {row: [""] * 6 for row in web.SIM5W_ROWS}
    _assert_other_cards_intact(page)


@pytest.mark.parametrize("fail_at", (1, 2, 3))
def test_timeout_and_query_errors_render_no_data_without_affecting_other_cards(fail_at):
    error = TimeoutError("canceling statement due to statement timeout") if fail_at == 1 \
        else RuntimeError("query failed")
    factory, connection, cursor, _ = scripted_factory(
        grouped=[("5M", "RESOLVED", 1)], latest=(NOW,), fail_at=fail_at, error=error)
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    response = request(app, "/")
    page = response["body"].decode()
    assert response["status"] == "200 OK"
    assert card_status(page) == "NO DATA"
    assert card_cells(page) == {row: [""] * 6 for row in web.SIM5W_ROWS}
    assert len(cursor.executions) == fail_at
    assert connection.commits == 0
    assert connection.closed and cursor.closed
    _assert_other_cards_intact(page)


# ---------------------------------------------------------------------------
# Card presentation (freeze sections 4, 7)
# ---------------------------------------------------------------------------


def test_card_shape_uses_existing_table_helper_with_six_horizons_in_canonical_order():
    factory, *_ = scripted_factory(
        grouped=[("30S", "RESOLVED", 1), ("1H", "UNRESOLVED_OBSERVATION_GAP", 2)],
        latest=(NOW,))
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    page = request(app, "/")["body"].decode()
    block = card_block(page)
    assert block.startswith("<h2>SIM — PAPER ONLY</h2>")
    assert card_headers(page) == ["", *HORIZONS]
    assert HORIZONS == ("30S", "1M", "5M", "15M", "30M", "1H")
    row_labels = re.findall(r"<tr><th>([A-Z]+)</th>", block)
    assert row_labels == list(web.SIM5W_ROWS) == ["CLOSED", "RESOLVED", "UNRESOLVED"]
    assert block.count("<table>") == 1
    assert block.count('data-dashboard-field="sim_paper_only.status"') == 1
    assert page.count("<h2>SIM — PAPER ONLY</h2>") == 1
    expected_table = web._table(
        HORIZONS,
        (("CLOSED", [1, 0, 0, 0, 0, 2]), ("RESOLVED", [1, 0, 0, 0, 0, 0]),
         ("UNRESOLVED", [0, 0, 0, 0, 0, 2])),
        section="sim_paper_only")
    assert expected_table in block
    accuracy_block = page.split("<h2>V9 DIRECTIONAL ACCURACY</h2>", 1)[1].split("<h2>", 1)[0]
    assert accuracy_block.count("<div class=scroll><table>") == block.count("<div class=scroll><table>") == 1


def test_card_renders_no_forbidden_value():
    factory, *_ = scripted_factory(
        grouped=[("5M", "RESOLVED", 3), ("5M", "UNRESOLVED_WINDOW_EXPIRED", 1)],
        latest=(NOW,))
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    page = request(app, "/")["body"].decode()
    block = card_block(page)
    for forbidden in ("%", "$", "return_bps", "RETURN", "P&amp;L", "P&L", "WIN",
                      "ACCURACY", "SHARPE", "DRAWDOWN", "EXIT", "PRICE", "AVERAGE",
                      "MEDIAN", "EXPECTANCY", "<canvas", "<svg", "<select",
                      "<input", "<a ", "href="):
        assert forbidden not in block
    values = [value for row in card_cells(page).values() for value in row]
    assert all(re.fullmatch(r"\d+", value) for value in values)
    assert card_status(page) in {"LIVE", "STALE", "NO DATA"}


def test_default_app_renders_the_card_as_no_data_and_page_is_data_only():
    page = request(web.create_app(), "/")["body"].decode()
    assert card_status(page) == "NO DATA"
    assert card_cells(page) == {row: [""] * 6 for row in web.SIM5W_ROWS}
    rendered = web.dashboard_page(
        web.dashboard_data(now_epoch=NOW_EPOCH, calculate_missing=False)).decode()
    assert card_status(rendered) == "NO DATA"


def test_only_the_page_render_reads_the_simulator_and_only_once_per_render():
    factory, connection, cursor, calls = scripted_factory(
        grouped=[("5M", "RESOLVED", 1)], latest=(NOW,))
    app = web.create_app(clock=lambda: NOW_EPOCH,
                         sim_web_reader_connection_factory=factory)
    for path in ("/api/dashboard", "/api/live", "/api/phase-e",
                 "/api/historical-replay", "/health", "/ready", "/favicon.ico"):
        request(app, path)
    assert calls == []
    payload = request(app, "/api/dashboard")["body"].decode()
    assert "sim_paper_only" not in payload
    request(app, "/")
    assert calls == ["connected"]
    assert len(cursor.executions) == 3
    request(app, "/")
    assert calls == ["connected", "connected"]


def test_main_wires_the_reader_factory_exactly_once_from_environment():
    startup = ast.parse(inspect.getsource(web.main))
    factory_calls = [
        node for node in ast.walk(startup)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_sim_web_reader_connection_factory"
    ]
    assert len(factory_calls) == 1
    assert tuple(ast.unparse(arg) for arg in factory_calls[0].args) == (
        "os.environ", "runtime_connect")
    app_calls = [
        node for node in ast.walk(startup)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_app"
    ]
    assert len(app_calls) == 1
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in app_calls[0].keywords}
    assert keywords["sim_web_reader_connection_factory"] == "sim_web_reader_connection_factory"
    source = inspect.getsource(web)
    assert source.count('"ATOM_V9_SIM_WEB_READONLY_DATABASE_URL"') == 1
    assert "pg_advisory" not in inspect.getsource(web._read_sim_paper_only_counts)


# ---------------------------------------------------------------------------
# Migration 032 text (freeze section 2)
# ---------------------------------------------------------------------------


def test_migration_032_is_the_next_ordinal_and_contains_no_password_or_transaction_control():
    ordinals = sorted(
        int(path.name[:3]) for path in (ROOT / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
    assert ordinals.count(32) == 1
    assert max(ordinals) == 32
    statements = "\n".join(
        line.split("--", 1)[0] for line in SQL.splitlines())
    upper = statements.upper()
    assert "PASSWORD" not in upper
    for forbidden in (r"^\s*BEGIN\s*;", r"^\s*COMMIT\s*;", r"^\s*ROLLBACK\s*;",
                      r"\bSET\s+ROLE\b", r"^\s*ALTER\b", r"^\s*DROP\b",
                      r"^\s*CREATE\s+(?:TABLE|FUNCTION|SEQUENCE|OR\s+REPLACE|INDEX|SCHEMA)\b",
                      r"^\s*INSERT\b", r"^\s*UPDATE\b", r"^\s*DELETE\b", r"^\s*TRUNCATE\b",
                      r"\bWITH\s+ADMIN\s+OPTION\b", r"\bBYPASSRLS\s+TO\b",
                      r"^\s*REVOKE\b(?!.*atom_v9_sim_owner)"):
        assert re.search(forbidden, upper, re.MULTILINE) is None, forbidden
    assert NORMAL_SQL.count("EXECUTE pg_catalog.format(") == 2


def test_migration_032_creates_exactly_the_frozen_role():
    assert NORMAL_SQL.count("CREATE ROLE") == 1
    assert (
        "CREATE ROLE atom_v9_sim_web_reader WITH LOGIN NOINHERIT NOSUPERUSER "
        "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
    ) in NORMAL_SQL
    assert "refusing to adopt it" in SQL


def test_migration_032_grants_exactly_schema_usage_and_resolution_select():
    grants = re.findall(r"GRANT\s+(?!atom_v9_sim_owner\b)([^;]+);", NORMAL_SQL)
    assert grants == [
        "USAGE ON SCHEMA public TO atom_v9_sim_web_reader",
        "SELECT ON TABLE public.atom_v9_sim_resolutions TO atom_v9_sim_web_reader",
    ]
    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "EXECUTE", "CREATE ON",
                      "REFERENCES", "TRIGGER", "ALL PRIVILEGES", "SEQUENCE"):
        assert not re.search(rf"GRANT\s+[^;]*\b{privilege}\b[^;]*;", NORMAL_SQL), privilege
    assert not re.search(r"GRANT\s+[^;]*atom_v9_sim_entries", NORMAL_SQL)
    assert not re.search(r"GRANT\s+[^;]*atom_v9_sim_installation", NORMAL_SQL)
    assert not re.search(r"GRANT\s+[^;]*TO\s+(?:atom_v9_sim_runtime|atom_v9_sim_entry_runtime|PUBLIC|anon|authenticated|service_role)\b",
                         NORMAL_SQL)


def test_migration_032_creates_exactly_one_scoped_select_policy():
    assert NORMAL_SQL.count("CREATE POLICY") == 1
    assert (
        "CREATE POLICY atom_v9_sim_resolutions_web_reader_select "
        "ON public.atom_v9_sim_resolutions "
        "FOR SELECT TO atom_v9_sim_web_reader USING (true);"
    ) in NORMAL_SQL
    assert "WITH CHECK" not in NORMAL_SQL
    assert "refusing to redefine it" in SQL


def test_migration_032_only_role_membership_is_the_bracketed_owner_bootstrap():
    memberships = re.findall(r"'(GRANT|REVOKE) atom_v9_sim_owner (?:TO|FROM) %I'", SQL)
    assert memberships == ["GRANT", "REVOKE"]
    grant_at = SQL.index("'GRANT atom_v9_sim_owner TO %I'")
    revoke_at = SQL.index("'REVOKE atom_v9_sim_owner FROM %I'")
    usage_at = SQL.index("GRANT USAGE ON SCHEMA public TO atom_v9_sim_web_reader;")
    select_at = SQL.index("GRANT SELECT ON TABLE public.atom_v9_sim_resolutions TO atom_v9_sim_web_reader;")
    policy_at = SQL.index("CREATE POLICY atom_v9_sim_resolutions_web_reader_select")
    verify_at = SQL.index("DO $atom_v9_sim5w_verify_final_authority$")
    assert grant_at < usage_at < select_at < policy_at < revoke_at < verify_at
    assert not re.search(r"GRANT\s+atom_v9_sim_\w+\s+TO\s+atom_v9_sim_web_reader", NORMAL_SQL)
    assert not re.search(r"GRANT\s+atom_v9_sim_web_reader\s+TO", NORMAL_SQL)


def test_migration_032_verification_asserts_the_frozen_final_state():
    for required in (
        "must hold and receive no role membership",
        "bootstrap membership in atom_v9_sim_owner was not revoked",
        "schema authority is not exactly USAGE",
        "authority on atom_v9_sim_resolutions is not exactly SELECT",
        "must hold no privilege on ",
        "must hold no sequence privilege",
        "must hold no EXECUTE on ",
        "scoped by exactly one SELECT policy on atom_v9_sim_resolutions",
        "row-level security is not enabled and forced",
        "pre-existing atom_v9_sim_resolutions policies changed",
        "atom_v9_sim_entry_runtime authority on atom_v9_sim_resolutions changed",
        "atom_v9_sim_runtime authority on atom_v9_sim_resolutions changed",
        "atom_v9_sim_owner authority on atom_v9_sim_resolutions changed",
        "ownership or owner schema authority changed",
        "requires the already-bootstrapped isolated simulator installation",
        "requires the existing atom_v9_sim_resolutions table",
    ):
        assert required in SQL, required
    assert "rel.relname = 'atom_v9_sim_entries'" in SQL
    assert "has_table_privilege(reader_oid, other_relation, 'SELECT')" in SQL
    assert "'public.atom_v9_sim_reject_mutation()'" in SQL


# ---------------------------------------------------------------------------
# Migration 032 against a live disposable PostgreSQL (explicit CI only)
# ---------------------------------------------------------------------------


SIM_ROLES = ("atom_v9_sim_owner", SIM_PUBLISHER_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE)
ALL_ROLES = SIM_ROLES + (READER_ROLE,)
INTEGRATION_LOCK_KEY = 772642391846415919

# Migration 027 refuses every production-shaped cluster role, and the legacy
# PostgreSQL tests create such roles without dropping them.  This clean-room
# bootstrap therefore runs immediately after the SIM-4 isolation bootstrap
# (which hooks itself to position zero) and ahead of every legacy database
# test, preserving all other ordering.  Self-registration makes this module's
# narrowly scoped hook available during the final collection-order pass.
pytest_plugins = [__name__]
POSTGRES_BOOTSTRAP_TEST_NAME = (
    "test_migration_032_applies_to_a_disposable_simulator_database_with_exact_authority")
ISOLATION_BOOTSTRAP_TEST_NAME = (
    "test_bootstrap_executes_in_dedicated_disposable_postgres_database")


@pytest.hookimpl(trylast=True)
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
    position = 1 if items and items[0].name == ISOLATION_BOOTSTRAP_TEST_NAME else 0
    items.insert(position, bootstrap)


def test_collection_hook_places_bootstrap_directly_after_the_isolation_bootstrap():
    from types import SimpleNamespace

    other_path = ROOT / "tests/test_historical_outcomes_postgres.py"
    isolation_path = ROOT / "tests/test_v9_sim4_isolation.py"
    original = [
        SimpleNamespace(name=ISOLATION_BOOTSTRAP_TEST_NAME, path=isolation_path),
        SimpleNamespace(name="legacy_first", path=other_path),
        SimpleNamespace(name=POSTGRES_BOOTSTRAP_TEST_NAME, path=Path(__file__)),
        SimpleNamespace(name="legacy_second", path=other_path),
    ]
    pytest_collection_modifyitems(original)
    assert [item.name for item in original] == [
        ISOLATION_BOOTSTRAP_TEST_NAME, POSTGRES_BOOTSTRAP_TEST_NAME,
        "legacy_first", "legacy_second",
    ]

    without_isolation = [
        SimpleNamespace(name="legacy_first", path=other_path),
        SimpleNamespace(name=POSTGRES_BOOTSTRAP_TEST_NAME, path=Path(__file__)),
    ]
    pytest_collection_modifyitems(without_isolation)
    assert [item.name for item in without_isolation] == [
        POSTGRES_BOOTSTRAP_TEST_NAME, "legacy_first"]

    foreign = [
        SimpleNamespace(name=POSTGRES_BOOTSTRAP_TEST_NAME, path=other_path),
        SimpleNamespace(name="legacy_first", path=other_path),
    ]
    pytest_collection_modifyitems(foreign)
    assert [item.name for item in foreign] == [
        POSTGRES_BOOTSTRAP_TEST_NAME, "legacy_first"]


def _snapshot_authority(cursor) -> dict[str, object]:
    cursor.execute(
        "SELECT rolname, rolcanlogin, rolinherit, rolsuper, rolcreatedb, "
        "rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_catalog.pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
        (list(SIM_ROLES),),
    )
    roles = cursor.fetchall()
    cursor.execute(
        "SELECT grantee, table_schema, table_name, privilege_type "
        "FROM information_schema.role_table_grants "
        "WHERE grantee = ANY(%s) ORDER BY 1, 2, 3, 4",
        (list(SIM_ROLES),),
    )
    table_grants = cursor.fetchall()
    cursor.execute(
        "SELECT pol.polrelid::regclass::text, pol.polname, pol.polcmd, "
        "pol.polpermissive, pol.polroles::regrole[]::text[], "
        "pg_catalog.pg_get_expr(pol.polqual, pol.polrelid), "
        "pg_catalog.pg_get_expr(pol.polwithcheck, pol.polrelid) "
        "FROM pg_catalog.pg_policy AS pol ORDER BY 1, 2",
    )
    policies = cursor.fetchall()
    cursor.execute(
        "SELECT roleid::regrole::text, member::regrole::text "
        "FROM pg_catalog.pg_auth_members "
        "WHERE roleid::regrole::text = ANY(%s) OR member::regrole::text = ANY(%s) "
        "ORDER BY 1, 2",
        (list(SIM_ROLES), list(SIM_ROLES)),
    )
    memberships = cursor.fetchall()
    # Relation ACLs are compared with any entry for the new reader removed, so
    # the comparison proves every pre-existing grant survived unchanged.
    cursor.execute(
        "SELECT rel.relname, rel.relowner::regrole::text, rel.relrowsecurity, "
        "rel.relforcerowsecurity, ("
        "  SELECT array_agg(COALESCE(grantee_role.rolname, 'PUBLIC') || ':' "
        "                   || acl.privilege_type || ':' || acl.is_grantable::text "
        "                   ORDER BY 1) "
        "  FROM pg_catalog.aclexplode(rel.relacl) AS acl "
        "  LEFT JOIN pg_catalog.pg_roles AS grantee_role ON grantee_role.oid = acl.grantee "
        "  WHERE COALESCE(grantee_role.rolname, '') <> %s) "
        "FROM pg_catalog.pg_class AS rel "
        "JOIN pg_catalog.pg_namespace AS ns ON ns.oid = rel.relnamespace "
        "WHERE ns.nspname = 'public' AND rel.relkind IN ('r', 'S') ORDER BY 1",
        (READER_ROLE,),
    )
    relations = cursor.fetchall()
    cursor.execute(
        "SELECT proc.oid::regprocedure::text, proc.proacl::text "
        "FROM pg_catalog.pg_proc AS proc "
        "JOIN pg_catalog.pg_namespace AS ns ON ns.oid = proc.pronamespace "
        "WHERE ns.nspname = 'public' ORDER BY 1",
    )
    functions = cursor.fetchall()
    cursor.execute(
        "SELECT rolname, pg_catalog.has_schema_privilege(rolname, 'public', 'USAGE'), "
        "pg_catalog.has_schema_privilege(rolname, 'public', 'CREATE') "
        "FROM pg_catalog.pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
        (list(SIM_ROLES),),
    )
    schema = cursor.fetchall()
    return {
        "roles": roles, "table_grants": table_grants, "memberships": memberships,
        "relations": relations, "functions": functions, "schema": schema,
        "policies_excluding_reader": [
            policy for policy in policies if READER_ROLE not in str(policy[4])],
    }


def test_migration_032_applies_to_a_disposable_simulator_database_with_exact_authority():
    database_url = os.environ.get("H2C_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("H2C_TEST_DATABASE_URL disposable PostgreSQL required")
    if os.environ.get("CI") != "true":
        pytest.skip("SIM-5W migration integration runs only in explicit CI")
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
        pytest.fail("SIM-5W migration integration requires the exact local CI postgres DSN")

    database_name = f"atom_v9_sim5w_{uuid4().hex[:12]}"
    simulator_url = urlunsplit((
        parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, ""))
    reader_password = uuid4().hex
    reader_url = urlunsplit((
        parsed.scheme,
        f"{READER_ROLE}:{reader_password}@{parsed.hostname}:{parsed.port}",
        f"/{database_name}", "", ""))
    admin = None
    lock_acquired = False
    database_created = False
    roles_created = False
    try:
        admin = psycopg.connect(database_url, autocommit=True)
        with admin.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone() != ("postgres",):
                pytest.fail("refusing SIM-5W bootstrap outside the local CI postgres DB")
            cursor.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole "
                "FROM pg_catalog.pg_roles WHERE rolname = current_user")
            if cursor.fetchone() != (True, True, True):
                pytest.skip("local CI PostgreSQL superuser authority required")
            cursor.execute("SELECT pg_catalog.pg_advisory_lock(%s::bigint)",
                           (INTEGRATION_LOCK_KEY,))
            lock_acquired = True
            cursor.execute(
                "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
                (list(ALL_ROLES),))
            preexisting = tuple(row[0] for row in cursor.fetchall())
            if preexisting:
                pytest.fail("refusing to adopt or drop pre-existing SIM roles: "
                            + ", ".join(preexisting))
            cursor.execute(pg_sql.SQL("CREATE DATABASE {}").format(
                pg_sql.Identifier(database_name)))
            database_created = True

        simulator = psycopg.connect(simulator_url, autocommit=True)
        try:
            for migration, needs_project_ref in (
                    (BOOTSTRAP_MIGRATION, True), (RESOLUTION_MIGRATION, False)):
                with simulator.transaction():
                    with simulator.cursor() as cursor:
                        if needs_project_ref:
                            cursor.execute(pg_sql.SQL(
                                "SET LOCAL atom_v9.sim_project_ref = {}"
                            ).format(pg_sql.Literal(SIM_PROJECT_REF)))
                        cursor.execute(migration.read_text(encoding="utf-8"))
                roles_created = True
            with simulator.cursor() as cursor:
                before = _snapshot_authority(cursor)

            # Migration 032 owns no transaction control; the operator's
            # BEGIN/.../COMMIT boundary wraps it exactly once.
            with simulator.transaction():
                with simulator.cursor() as cursor:
                    cursor.execute(SQL)

            with simulator.cursor() as cursor:
                after = _snapshot_authority(cursor)
                assert after == before, "migration 032 changed a pre-existing object"

                cursor.execute(
                    "SELECT rolcanlogin, rolinherit, rolsuper, rolcreatedb, "
                    "rolcreaterole, rolreplication, rolbypassrls, rolpassword "
                    "FROM pg_catalog.pg_authid WHERE rolname = %s", (READER_ROLE,))
                assert cursor.fetchone() == (
                    True, False, False, False, False, False, False, None)
                cursor.execute(
                    "SELECT table_name, privilege_type "
                    "FROM information_schema.role_table_grants "
                    "WHERE grantee = %s ORDER BY 1, 2", (READER_ROLE,))
                assert cursor.fetchall() == [("atom_v9_sim_resolutions", "SELECT")]
                cursor.execute(
                    "SELECT pg_catalog.has_schema_privilege(%s, 'public', 'USAGE'), "
                    "pg_catalog.has_schema_privilege(%s, 'public', 'CREATE')",
                    (READER_ROLE, READER_ROLE))
                assert cursor.fetchone() == (True, False)
                cursor.execute(
                    "SELECT rel.relname FROM pg_catalog.pg_class AS rel "
                    "JOIN pg_catalog.pg_namespace AS ns ON ns.oid = rel.relnamespace "
                    "WHERE ns.nspname = 'public' AND rel.relkind = 'r' ORDER BY 1")
                tables = [row[0] for row in cursor.fetchall()]
                assert "atom_v9_sim_entries" in tables
                for table in tables:
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE",
                                      "TRUNCATE", "REFERENCES", "TRIGGER"):
                        cursor.execute(
                            "SELECT pg_catalog.has_table_privilege(%s, %s, %s)",
                            (READER_ROLE, f"public.{table}", privilege))
                        expected = table == "atom_v9_sim_resolutions" and privilege == "SELECT"
                        assert cursor.fetchone() == (expected,), (table, privilege)
                cursor.execute(
                    "SELECT count(*) FROM pg_catalog.pg_auth_members "
                    "WHERE roleid = %s::regrole OR member = %s::regrole",
                    (READER_ROLE, READER_ROLE))
                assert cursor.fetchone() == (0,)
                cursor.execute(
                    "SELECT pol.polrelid::regclass::text, pol.polname, pol.polcmd, "
                    "pol.polpermissive, pg_catalog.pg_get_expr(pol.polqual, pol.polrelid) "
                    "FROM pg_catalog.pg_policy AS pol "
                    "WHERE pol.polroles @> ARRAY[%s::regrole::oid]", (READER_ROLE,))
                assert cursor.fetchall() == [(
                    "atom_v9_sim_resolutions",
                    "atom_v9_sim_resolutions_web_reader_select", "r", True, "true")]
                cursor.execute(
                    "SELECT proc.oid::regprocedure::text FROM pg_catalog.pg_proc AS proc "
                    "JOIN pg_catalog.pg_namespace AS ns ON ns.oid = proc.pronamespace "
                    "WHERE ns.nspname = 'public'")
                for (function,) in cursor.fetchall():
                    cursor.execute(
                        "SELECT pg_catalog.has_function_privilege(%s, %s, 'EXECUTE')",
                        (READER_ROLE, function))
                    assert cursor.fetchone() == (False,), function
                cursor.execute(
                    "SELECT rel.oid::regclass::text FROM pg_catalog.pg_class AS rel "
                    "JOIN pg_catalog.pg_namespace AS ns ON ns.oid = rel.relnamespace "
                    "WHERE ns.nspname = 'public' AND rel.relkind = 'S'")
                for (sequence,) in cursor.fetchall():
                    for privilege in ("USAGE", "SELECT", "UPDATE"):
                        cursor.execute(
                            "SELECT pg_catalog.has_sequence_privilege(%s, %s, %s)",
                            (READER_ROLE, sequence, privilege))
                        assert cursor.fetchone() == (False,), (sequence, privilege)
                cursor.execute(pg_sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
                    pg_sql.Identifier(READER_ROLE), pg_sql.Literal(reader_password)))
        finally:
            simulator.close()

        reader = psycopg.connect(reader_url)
        try:
            reader.read_only = True
            with reader.cursor() as cursor:
                cursor.execute("SELECT current_user")
                assert cursor.fetchone() == (READER_ROLE,)
                for statement in FROZEN_STATEMENTS:
                    cursor.execute(statement)
                cursor.execute(FROZEN_STATEMENTS[1])
                assert cursor.fetchall() == []
                cursor.execute(FROZEN_STATEMENTS[2])
                assert cursor.fetchone() == (None,)
            reader.rollback()
            for denied in (
                    "SELECT count(*) FROM public.atom_v9_sim_entries",
                    "SELECT count(*) FROM public.atom_v9_sim_installation",
                    "SELECT count(*) FROM public.atom_v9_sim_intents",
                    "SELECT public.atom_v9_sim4_read_intent_admission_fence()",
                    "SELECT nextval('public.atom_v9_sim4_intent_admission_seq')",
                    "CREATE TABLE public.sim5w_probe (id int)"):
                with pytest.raises(psycopg.Error):
                    with reader.cursor() as cursor:
                        cursor.execute(denied)
                reader.rollback()
            reader.read_only = False
            with pytest.raises(psycopg.Error):
                with reader.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO public.atom_v9_sim_resolutions DEFAULT VALUES")
            reader.rollback()
        finally:
            reader.close()
    finally:
        if admin is not None:
            try:
                with admin.cursor() as cursor:
                    if database_created:
                        cursor.execute(
                            "SELECT pg_catalog.pg_terminate_backend(pid) "
                            "FROM pg_catalog.pg_stat_activity "
                            "WHERE datname = %s AND pid <> pg_catalog.pg_backend_pid()",
                            (database_name,))
                        cursor.execute(pg_sql.SQL("DROP DATABASE IF EXISTS {}").format(
                            pg_sql.Identifier(database_name)))
                    if roles_created:
                        cursor.execute(
                            "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
                            (list(ALL_ROLES),))
                        for (role,) in cursor.fetchall():
                            cursor.execute(pg_sql.SQL("DROP ROLE {}").format(
                                pg_sql.Identifier(role)))
                    if lock_acquired:
                        cursor.execute(
                            "SELECT pg_catalog.pg_advisory_unlock(%s::bigint)",
                            (INTEGRATION_LOCK_KEY,))
            finally:
                admin.close()
