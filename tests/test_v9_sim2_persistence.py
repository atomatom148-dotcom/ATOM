"""Exhaustive, deterministic audit tests for the frozen SIM-2 boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import ast
import json
from pathlib import Path
import re
import threading
import unittest
from unittest.mock import patch

from quant.v9_sim1_contract import (
    build_simulation_trade_intent,
    serialize_simulation_trade_intent,
)
from quant.v9_sim2_store import (
    IDEMPOTENT,
    INSERTED,
    SIM_INTENT_TABLE,
    SIM_RUNTIME_ROLE,
    SimulationIntentConflictError,
    SimulationIntentRoleError,
    SimulationIntentRowInvalidError,
    SimulationIntentStore,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/010_create_v9_sim_intents.sql"
STORE_SOURCE = ROOT / "quant/v9_sim2_store.py"
SQL = MIGRATION.read_text(encoding="utf-8")
NORMAL_SQL = " ".join(SQL.split())
UTC = timezone.utc


def build(**changes):
    values = dict(
        source_cycle_id="cycle-1",
        source_forecast_record_id="v9v4f:source",
        source_forecast_record_hash="a" * 64,
        source_v2_state_id="v9v2:state",
        source_v2_state_hash="b" * 64,
        source_v3_contract_version="V3-C",
        source_v3_model_version="V3-M",
        cutoff_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
        eligible_at=datetime(2026, 8, 24, 12, 0, 0, 1, tzinfo=UTC),
        horizon="30S",
        horizon_seconds=30,
        final_bps=1.25,
        source_v3_status="AVAILABLE",
    )
    values.update(changes)
    return build_simulation_trade_intent(**values)


def payload(value):
    return json.loads(serialize_simulation_trade_intent(value))


def row(value, *, record=None, **columns):
    values = dict(
        intent_id=value.intent_id,
        intent_hash=value.intent_hash,
        contract_version=value.contract_version,
        canonicalization_version=value.canonicalization_version,
        simulator_version=value.simulator_version,
        symbol=value.symbol,
        horizon=value.horizon,
        horizon_seconds=value.horizon_seconds,
        cutoff_at=value.cutoff_at,
        eligible_at=value.eligible_at,
        source_v3_status=value.source_v3_status,
        decision=value.decision,
        status=value.status,
        record_json=payload(value) if record is None else record,
    )
    values.update(columns)
    return tuple(values[name] for name in (
        "intent_id", "intent_hash", "contract_version",
        "canonicalization_version", "simulator_version", "symbol", "horizon",
        "horizon_seconds", "cutoff_at", "eligible_at", "source_v3_status",
        "decision", "status", "record_json"))


class ScriptedCursor:
    def __init__(self, rows=(), *, execute_error_at=None):
        self.rows = iter(rows)
        self.execute_error_at = execute_error_at
        self.executions = []
        self.closed = False

    def execute(self, statement, parameters=None):
        self.executions.append((statement, parameters))
        if self.execute_error_at == len(self.executions):
            raise RuntimeError("deterministic database failure")

    def fetchone(self):
        return next(self.rows, None)

    def close(self):
        self.closed = True


class ScriptedConnection:
    def __init__(self, rows=(), *, execute_error_at=None):
        self.cursor_value = ScriptedCursor(rows, execute_error_at=execute_error_at)
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


def connection(rows=(), **kwargs):
    return ScriptedConnection(rows, **kwargs)


class MigrationShapeTests(unittest.TestCase):
    def test_exact_table_column_order_types_nullability_and_default(self):
        self.assertEqual(SIM_INTENT_TABLE, "public.atom_v9_sim_intents")
        match = re.search(
            r"CREATE TABLE public\.atom_v9_sim_intents \((.*?)\n\);",
            SQL, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group(1)
        declarations = [line.strip().rstrip(",") for line in body.splitlines()
                        if re.match(r"\s{4}[a-z]", line)]
        expected = [
            "intent_id text PRIMARY KEY CHECK (intent_id ~ '^v9simintent:[0-9a-f]{64}$')",
            "intent_hash text UNIQUE NOT NULL CHECK (intent_hash ~ '^[0-9a-f]{64}$')",
            "contract_version text NOT NULL CHECK (contract_version = 'ATOM_TRUE_V9_SIM1_INTENT_1')",
            "canonicalization_version text NOT NULL CHECK (canonicalization_version = 'ATOM_TRUE_V9_SIM_CANONICAL_V4A_1')",
            "simulator_version text NOT NULL CHECK (simulator_version = 'ATOM_TRUE_V9_SIM_1')",
            "symbol text NOT NULL CHECK (symbol = 'COIN')",
            "horizon text NOT NULL", "horizon_seconds integer NOT NULL",
            "cutoff_at timestamptz NOT NULL", "eligible_at timestamptz NOT NULL",
            "source_v3_status text NOT NULL CHECK (source_v3_status IN ('AVAILABLE', 'PROVISIONAL', 'UNAVAILABLE'))",
            "decision text NOT NULL CHECK (decision IN ('LONG', 'SHORT', 'NO_TRADE'))",
            "status text NOT NULL CHECK (status IN ('ACTIONABLE', 'NO_TRADE', 'UNAVAILABLE'))",
            "record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object')",
            "created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP",
        ]
        self.assertEqual(declarations, expected)
        self.assertEqual(body.count("PRIMARY KEY"), 1)
        self.assertEqual(body.count("UNIQUE"), 1)

    def test_every_table_check_constraint(self):
        required = (
            "intent_id ~ '^v9simintent:[0-9a-f]{64}$'",
            "intent_hash ~ '^[0-9a-f]{64}$'",
            "contract_version = 'ATOM_TRUE_V9_SIM1_INTENT_1'",
            "canonicalization_version = 'ATOM_TRUE_V9_SIM_CANONICAL_V4A_1'",
            "simulator_version = 'ATOM_TRUE_V9_SIM_1'", "symbol = 'COIN'",
            "source_v3_status IN ('AVAILABLE', 'PROVISIONAL', 'UNAVAILABLE')",
            "decision IN ('LONG', 'SHORT', 'NO_TRADE')",
            "status IN ('ACTIONABLE', 'NO_TRADE', 'UNAVAILABLE')",
            "jsonb_typeof(record_json) = 'object'", "eligible_at >= cutoff_at",
            "(('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900), ('30M', 1800), ('1H', 3600))",
        )
        for constraint in required:
            with self.subTest(constraint=constraint):
                self.assertIn(constraint, NORMAL_SQL)
        self.assertNotIn("FOREIGN KEY", SQL.upper())

    def test_exact_single_nonunique_lookup_index(self):
        indexes = re.findall(r"CREATE\s+(UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+([^;]+);",
                             SQL, re.IGNORECASE | re.DOTALL)
        self.assertEqual(len(indexes), 1)
        unique, name, target = indexes[0]
        self.assertEqual(unique, "")
        self.assertEqual(name, "atom_v9_sim_intents_lookup_idx")
        self.assertEqual(" ".join(target.split()),
                         "public.atom_v9_sim_intents (symbol, horizon, eligible_at, intent_id)")

    def test_unlimited_history_has_no_limiting_uniqueness(self):
        table = re.search(r"CREATE TABLE .*?\((.*?)\n\);", SQL, re.DOTALL).group(1)
        self.assertNotRegex(table, r"UNIQUE[^\n]*(horizon|cutoff|cycle|session|date)")
        for forbidden in ("daily", "session", "lifetime", "rotation", "retention"):
            self.assertNotIn(forbidden, table.lower())

        first = build()
        second = build(source_cycle_id="cycle-2",
                       eligible_at=first.eligible_at.replace(microsecond=2))
        for value in (first, second):
            database = connection([("atom_v9_sim_runtime",), (value.intent_id,)])
            self.assertEqual(SimulationIntentStore(lambda: database).insert(value), INSERTED)


class MigrationSecurityTests(unittest.TestCase):
    def test_exact_role_attributes_and_existing_role_rejection(self):
        self.assertEqual(SIM_RUNTIME_ROLE, "atom_v9_sim_runtime")
        self.assertIn("IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_runtime')",
                      NORMAL_SQL)
        self.assertIn("RAISE duplicate_object", NORMAL_SQL)
        self.assertRegex(NORMAL_SQL, r"CREATE ROLE atom_v9_sim_runtime WITH LOGIN NOINHERIT "
                         r"NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;")
        role_statement = re.search(r"CREATE ROLE atom_v9_sim_runtime WITH (.*?);",
                                   NORMAL_SQL).group(1)
        self.assertNotIn("PASSWORD", role_statement.upper())

    def test_exact_grants_revocations_and_production_isolation(self):
        grants = re.findall(r"GRANT\s+(.+?);", NORMAL_SQL, re.IGNORECASE)
        self.assertEqual(grants, [
            "USAGE ON SCHEMA public TO atom_v9_sim_runtime",
            "SELECT, INSERT ON TABLE public.atom_v9_sim_intents TO atom_v9_sim_runtime",
        ])
        self.assertIn("REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_sim_intents FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime, atom_v9_sim_runtime;",
                      NORMAL_SQL)
        production = ("atom_v9_v4_forecasts", "atom_v9_v4_outcomes",
                      "atom_v9_v4_states", "forecasts", "forecast_outcomes",
                      "volatility_forecasts", "volatility_forecast_outcomes")
        for table in production:
            self.assertRegex(NORMAL_SQL, rf"REVOKE ALL PRIVILEGES ON TABLE .*public\.{table}.* FROM atom_v9_sim_runtime;")
            self.assertFalse(any(f"public.{table}" in grant for grant in grants))
        self.assertNotRegex(NORMAL_SQL, r"(?i)GRANT .* (SEQUENCE|ROLE) ")

    def test_forced_rls_and_exact_policies(self):
        self.assertIn("ALTER TABLE public.atom_v9_sim_intents ENABLE ROW LEVEL SECURITY;",
                      NORMAL_SQL)
        self.assertIn("ALTER TABLE public.atom_v9_sim_intents FORCE ROW LEVEL SECURITY;",
                      NORMAL_SQL)
        policies = re.findall(r"CREATE POLICY (\w+) ON public\.atom_v9_sim_intents (.*?);",
                              NORMAL_SQL)
        self.assertEqual(policies, [
            ("atom_v9_sim_intents_runtime_select",
             "FOR SELECT TO atom_v9_sim_runtime USING (true)"),
            ("atom_v9_sim_intents_runtime_insert",
             "FOR INSERT TO atom_v9_sim_runtime WITH CHECK (true)"),
        ])

    def test_append_only_triggers_and_safe_function(self):
        self.assertIn("LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog",
                      NORMAL_SQL)
        self.assertIn("RAISE EXCEPTION 'SIM evidence is append-only';", NORMAL_SQL)
        self.assertIn("atom_v9_sim_intents_reject_update_delete BEFORE UPDATE OR DELETE ON public.atom_v9_sim_intents FOR EACH ROW",
                      NORMAL_SQL)
        self.assertIn("atom_v9_sim_intents_reject_truncate BEFORE TRUNCATE ON public.atom_v9_sim_intents FOR EACH STATEMENT",
                      NORMAL_SQL)
        self.assertIn("REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_sim_reject_mutation() FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime, atom_v9_sim_runtime;",
                      NORMAL_SQL)


class StoreBehaviorTests(unittest.TestCase):
    def assert_closed(self, database, *, commits, rollbacks):
        self.assertEqual((database.commits, database.rollbacks), (commits, rollbacks))
        self.assertTrue(database.cursor_value.closed)
        self.assertTrue(database.closed)

    def test_inserted_is_atomic_committed_and_closed(self):
        value = build()
        database = connection([("atom_v9_sim_runtime",), (value.intent_id,)])
        result = SimulationIntentStore(lambda: database).insert(value)
        self.assertEqual(result, INSERTED)
        insert_sql = database.cursor_value.executions[1][0]
        self.assertIn("ON CONFLICT DO NOTHING RETURNING intent_id", insert_sql)
        self.assert_closed(database, commits=1, rollbacks=0)

    def test_idempotent_requires_validated_reread(self):
        value = build()
        database = connection([("atom_v9_sim_runtime",), None, row(value)])
        self.assertEqual(SimulationIntentStore(lambda: database).insert(value), IDEMPOTENT)
        reread, parameters = database.cursor_value.executions[2]
        self.assertIn("WHERE intent_id = %s OR intent_hash = %s", reread)
        self.assertEqual(parameters, (value.intent_id, value.intent_hash))
        self.assert_closed(database, commits=1, rollbacks=0)

    def test_concurrent_identical_insertions_are_idempotent(self):
        value = build()
        databases = [connection([("atom_v9_sim_runtime",), None, row(value)])
                     for _ in range(2)]
        barrier = threading.Barrier(2)
        results = []

        def worker(database):
            barrier.wait()
            results.append(SimulationIntentStore(lambda: database).insert(value))

        threads = [threading.Thread(target=worker, args=(database,))
                   for database in databases]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(results, [IDEMPOTENT, IDEMPOTENT])
        for database in databases:
            self.assert_closed(database, commits=1, rollbacks=0)

    def test_get_uses_sim1_deserializer_and_commits(self):
        value = build()
        database = connection([("atom_v9_sim_runtime",), row(value)])
        with patch("quant.v9_sim2_store.deserialize_simulation_trade_intent",
                   wraps=__import__("quant.v9_sim1_contract", fromlist=[
                       "deserialize_simulation_trade_intent"]).deserialize_simulation_trade_intent) as decode:
            self.assertEqual(SimulationIntentStore(lambda: database).get(value.intent_id), value)
        decode.assert_called_once()
        self.assert_closed(database, commits=1, rollbacks=0)

    def test_insert_uses_sim1_serializer(self):
        value = build()
        database = connection([("atom_v9_sim_runtime",), (value.intent_id,)])
        with patch("quant.v9_sim2_store.serialize_simulation_trade_intent",
                   wraps=serialize_simulation_trade_intent) as encode:
            SimulationIntentStore(lambda: database).insert(value)
        encode.assert_called_once_with(value)

    def test_wrong_or_missing_role_fails_closed(self):
        for role_row in (("postgres",), None):
            database = connection([role_row])
            with self.subTest(role_row=role_row), self.assertRaises(SimulationIntentRoleError):
                SimulationIntentStore(lambda: database).get("v9simintent:" + "a" * 64)
            self.assertEqual(len(database.cursor_value.executions), 1)
            self.assert_closed(database, commits=0, rollbacks=1)

    def test_conflicting_identity_fails_closed(self):
        requested = build()
        other = build(source_cycle_id="cycle-2")
        database = connection([("atom_v9_sim_runtime",), None, row(other)])
        with self.assertRaises(SimulationIntentConflictError) as raised:
            SimulationIntentStore(lambda: database).insert(requested)
        self.assertEqual(raised.exception.reason, "SIM2_INTENT_CONFLICT")
        self.assert_closed(database, commits=0, rollbacks=1)

    def test_every_malformed_or_mismatched_row_fails_closed(self):
        value = build()
        cases = {}
        for name in ("missing", "unknown", "hash", "id"):
            damaged = payload(value)
            if name == "missing": damaged.pop("symbol")
            elif name == "unknown": damaged["extra"] = True
            elif name == "hash": damaged["intent_hash"] = "f" * 64
            else: damaged["intent_id"] = "v9simintent:" + "f" * 64
            cases[name] = row(value, record=damaged)
        cases["malformed"] = row(value, record="not-json")
        cases["relational"] = row(value, symbol="MSFT")
        cases["shape"] = row(value)[:-1]
        for name, stored in cases.items():
            database = connection([("atom_v9_sim_runtime",), stored])
            with self.subTest(name=name), self.assertRaises(SimulationIntentRowInvalidError) as raised:
                SimulationIntentStore(lambda: database).get(value.intent_id)
            self.assertEqual(raised.exception.reason, "SIM2_ROW_INVALID")
            self.assert_closed(database, commits=0, rollbacks=1)

    def test_every_duplicated_relational_column_must_match_payload(self):
        value = build()
        replacements = {
            "intent_id": "v9simintent:" + "f" * 64,
            "intent_hash": "f" * 64,
            "contract_version": "wrong", "canonicalization_version": "wrong",
            "simulator_version": "wrong", "symbol": "MSFT", "horizon": "1M",
            "horizon_seconds": 60,
            "cutoff_at": value.cutoff_at.replace(microsecond=1),
            "eligible_at": value.eligible_at.replace(microsecond=2),
            "source_v3_status": "PROVISIONAL", "decision": "SHORT",
            "status": "NO_TRADE",
        }
        for name, replacement in replacements.items():
            database = connection([("atom_v9_sim_runtime",),
                                   row(value, **{name: replacement})])
            with self.subTest(column=name), self.assertRaises(SimulationIntentRowInvalidError):
                SimulationIntentStore(lambda: database).get(value.intent_id)
            self.assert_closed(database, commits=0, rollbacks=1)

    def test_database_failure_rolls_back_and_closes(self):
        database = connection([], execute_error_at=2)
        database.cursor_value.rows = iter([("atom_v9_sim_runtime",)])
        with self.assertRaises(RuntimeError):
            SimulationIntentStore(lambda: database).get("x")
        self.assert_closed(database, commits=0, rollbacks=1)

    def test_missing_get_commits_and_closes(self):
        database = connection([("atom_v9_sim_runtime",), None])
        self.assertIsNone(SimulationIntentStore(lambda: database).get("missing"))
        self.assert_closed(database, commits=1, rollbacks=0)

    def test_no_trade_and_unavailable_are_persistable(self):
        values = (build(final_bps=0.0),
                  build(final_bps=None, source_v3_status="UNAVAILABLE"))
        for value in values:
            database = connection([("atom_v9_sim_runtime",), (value.intent_id,)])
            with self.subTest(status=value.status):
                self.assertEqual(SimulationIntentStore(lambda: database).insert(value), INSERTED)
                parameters = database.cursor_value.executions[1][1]
                self.assertEqual(parameters[12], value.status)


class ScopeTests(unittest.TestCase):
    def test_no_forbidden_store_surface_or_later_phase_behavior(self):
        source = STORE_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree)
                   if isinstance(node, ast.Import) for alias in node.names}
        imports.update(node.module or "" for node in ast.walk(tree)
                       if isinstance(node, ast.ImportFrom))
        for forbidden in ("os", "web", "render", "broker", "v9_v4", "v9_v3"):
            self.assertFalse(any(forbidden in name.lower() for name in imports))
        self.assertNotRegex(source, r"DATABASE_URL|environ|getenv|credential|password")
        sql_literals = " ".join(value.value for value in ast.walk(tree)
                                if isinstance(value, ast.Constant)
                                and isinstance(value.value, str))
        self.assertNotRegex(sql_literals.upper(), r"\b(UPDATE|DELETE|TRUNCATE)\b")
        for later in ("entry", "resolution", "pnl", "position", "quote", "state"):
            self.assertNotIn(later, source.lower())

    def test_migration_contains_no_evidence_mutation_or_application(self):
        self.assertNotRegex(NORMAL_SQL, r"(?i)\b(UPDATE|DELETE FROM|TRUNCATE TABLE)\s+public\.atom_v9_sim_intents")
        self.assertNotRegex(SQL, r"(?i)\b(psql|database_url|connect\(|cursor\(|execute\()")
        self.assertNotRegex(NORMAL_SQL, r"(?i)\b(ALTER ROLE|DROP TABLE|DROP ROLE)\b")


if __name__ == "__main__":
    unittest.main()
