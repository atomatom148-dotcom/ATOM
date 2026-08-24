"""Focused unit checks for the frozen SIM-2 persistence boundary."""

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from quant.v9_sim1_contract import build_simulation_trade_intent, serialize_simulation_trade_intent
from quant.v9_sim2_store import IDEMPOTENT, INSERTED, SimulationIntentRoleError, SimulationIntentStore


def intent():
    return build_simulation_trade_intent(
        source_cycle_id="cycle", source_forecast_record_id="forecast",
        source_forecast_record_hash="a" * 64, source_v2_state_id="state",
        source_v2_state_hash="b" * 64, source_v3_contract_version="v3c",
        source_v3_model_version="v3m",
        cutoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        eligible_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        horizon="30S", horizon_seconds=30, final_bps=1.0,
        source_v3_status="AVAILABLE")


class Cursor:
    def __init__(self, rows): self.rows, self.closed = iter(rows), False
    def execute(self, sql, params=None): self.last = (sql, params)
    def fetchone(self): return next(self.rows, None)
    def close(self): self.closed = True


class Connection:
    def __init__(self, rows):
        self.cursor_value = Cursor(rows); self.commits = self.rollbacks = 0; self.closed = False
    def cursor(self): return self.cursor_value
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): self.closed = True


def row(value):
    return (value.intent_id, value.intent_hash, value.contract_version,
            value.canonicalization_version, value.simulator_version, value.symbol,
            value.horizon, value.horizon_seconds, value.cutoff_at, value.eligible_at,
            value.source_v3_status, value.decision, value.status,
            json.loads(serialize_simulation_trade_intent(value)))


class StoreTests(unittest.TestCase):
    def test_inserted_idempotent_and_get(self):
        value = intent()
        for rows, expected in (([("atom_v9_sim_runtime",), (value.intent_id,)], INSERTED),
                               ([("atom_v9_sim_runtime",), None, row(value)], IDEMPOTENT)):
            connection = Connection(rows)
            self.assertEqual(SimulationIntentStore(lambda: connection).insert(value), expected)
            self.assertEqual((connection.commits, connection.rollbacks, connection.closed), (1, 0, True))
        connection = Connection([("atom_v9_sim_runtime",), row(value)])
        self.assertEqual(SimulationIntentStore(lambda: connection).get(value.intent_id), value)

    def test_wrong_role_rolls_back_and_closes(self):
        connection = Connection([("postgres",)])
        with self.assertRaises(SimulationIntentRoleError):
            SimulationIntentStore(lambda: connection).get("x")
        self.assertEqual((connection.commits, connection.rollbacks, connection.closed), (0, 1, True))

    def test_migration_has_frozen_security_boundaries(self):
        sql = Path("migrations/010_create_v9_sim_intents.sql").read_text()
        for phrase in ("FORCE ROW LEVEL SECURITY", "NOINHERIT", "NOBYPASSRLS",
                       "BEFORE UPDATE OR DELETE", "BEFORE TRUNCATE",
                       "SIM evidence is append-only", "GRANT SELECT, INSERT"):
            self.assertIn(phrase, sql)
        self.assertNotIn("FOREIGN KEY", sql.upper())


if __name__ == "__main__":
    unittest.main()
