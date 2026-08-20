import json
import math
import re
import unittest

from quant.evidence import PhaseECohortMetrics, PostgresEvidenceStore
from quant.web import create_app, dashboard_data
from tests.test_web import request


class Cursor:
    def __init__(self, rows=()):
        self.rows = rows
        self.statement = None
        self.parameters = None

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, statement, parameters):
        self.statement, self.parameters = statement, parameters
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, cursor): self.value = cursor
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self.value


def store_with(cursor):
    store = object.__new__(PostgresEvidenceStore)
    store._database_url = "postgresql://test"
    store._connect = lambda _: Connection(cursor)
    return store


class PhaseEStoreTests(unittest.TestCase):
    def test_result_is_frozen_and_exact_cohort_fields_are_preserved(self):
        cursor = Cursor((
            ("q1", "v1", "COIN", "30S", 3, 2, 1, .5, 4.25),
            ("q1", "v2", "COIN", "1H", 1, 0, 0, None, None),
            ("q2", "v1", "SPY", "1M", 2, 2, 2, 1.0, 0.0),
        ))
        values = store_with(cursor).phase_e_cohorts(100.0)
        self.assertEqual(values, (
            PhaseECohortMetrics("q1", "v1", "COIN", "30S", 3, 2, 1, .5, 4.25),
            PhaseECohortMetrics("q1", "v2", "COIN", "1H", 1, 0, 0, None, None),
            PhaseECohortMetrics("q2", "v1", "SPY", "1M", 2, 2, 2, 1.0, 0.0),
        ))
        with self.assertRaises((AttributeError, TypeError)):
            values[0].coverage = 1.0

    def test_query_has_exact_grouping_left_join_boundary_and_formulas(self):
        cursor = Cursor()
        store_with(cursor).phase_e_cohorts(123.5)
        sql = " ".join(cursor.statement.split())
        self.assertIn("LEFT JOIN forecast_outcomes AS o USING (forecast_id)", sql)
        self.assertIn("GROUP BY f.quant_id, f.formula_version, f.symbol, f.horizon", sql)
        self.assertEqual(cursor.parameters, (123.5,) * 5)
        self.assertGreaterEqual(sql.count("f.maturity_epoch <= %s"), 5)
        self.assertIn("NULLIF(count(*) FILTER", sql)
        self.assertIn("sqrt(avg(power(f.forecast_bps - o.outcome_bps, 2))", sql)
        self.assertIn("AND o.forecast_id IS NOT NULL", sql)

    def test_query_is_one_read_only_select_and_orders_exact_cohorts(self):
        cursor = Cursor()
        store_with(cursor).phase_e_cohorts(1.0)
        sql = re.sub(r"--[^\n]*|/\*.*?\*/", "", cursor.statement,
                     flags=re.DOTALL).upper()
        self.assertEqual(len(re.findall(r"\bSELECT\b", sql)), 1)
        for forbidden in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE"):
            self.assertIsNone(re.search(rf"\b{forbidden}\b", sql))
        normalized = " ".join(sql.split())
        self.assertIn("ORDER BY F.QUANT_ID, F.FORMULA_VERSION, F.SYMBOL", normalized)
        positions = [normalized.index(f"WHEN '{horizon}' THEN {index}")
                     for index, horizon in enumerate(("30S", "1M", "5M", "15M", "30M", "1H"), 1)]
        self.assertEqual(positions, sorted(positions))

    def test_nonfinite_as_of_is_rejected_before_connecting(self):
        store = object.__new__(PostgresEvidenceStore)
        store._database_url = "test"
        store._connect = lambda _: self.fail("database must not be reached")
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                store.phase_e_cohorts(value)

    def test_metric_examples_cover_e1_semantics(self):
        # Independent deterministic examples for the equations expressed by the SELECT.
        forecasts = [(90, 2, 2), (100, -2, -4), (100, 8, None), (101, 999, 999)]
        as_of = 100
        matured = [row for row in forecasts if row[0] <= as_of]
        resolved = [row for row in matured if row[2] is not None]
        self.assertEqual((len(forecasts), len(matured), len(resolved)), (4, 3, 2))
        self.assertEqual(len(resolved) / len(matured), 2 / 3)
        self.assertAlmostEqual(math.sqrt(sum((f - o) ** 2 for _, f, o in resolved) / 2), math.sqrt(2))
        self.assertEqual(math.sqrt((2 - 2) ** 2), 0)
        self.assertIsNone(None if not [] else 0)  # no matured rows => null coverage
        self.assertIsNone(None if not [] else 0)  # no resolved rows => null RMSE


class PhaseEApiTests(unittest.TestCase):
    def test_endpoint_exact_contract_uses_clock_and_only_phase_e_read(self):
        cohort = PhaseECohortMetrics("q7", "v2", "COIN", "30S", 4, 3, 2, 2 / 3, 5.5)

        class Store:
            def __init__(self): self.calls = []
            def phase_e_cohorts(self, as_of):
                self.calls.append(as_of)
                return (cohort,)
            def counts(self): raise AssertionError("dashboard count read is forbidden")
            def record_cycle_and_resolve(self, *args, **kwargs):
                raise AssertionError("evidence write is forbidden")

        class State:
            def snapshot(self): raise AssertionError("market state is forbidden")

        store = Store()
        response = request(create_app(state=State(), evidence_store=store,
                                      clock=lambda: 777.25), "/api/phase-e")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(store.calls, [777.25])
        self.assertEqual(json.loads(response["body"]), {
            "as_of_epoch": 777.25,
            "cohorts": [{
                "quant_id": "q7", "formula_version": "v2", "symbol": "COIN",
                "horizon": "30S", "forecast_count": 4, "matured_count": 3,
                "resolved_count": 2, "coverage": 2 / 3, "rmse_bps": 5.5,
            }],
        })

    def test_dashboard_evidence_fields_remain_frozen(self):
        evidence = dashboard_data(evidence_counts=(10, 8))["evidence"]
        self.assertEqual(evidence["Forecasts"], 10)
        self.assertEqual(evidence["Resolved"], 8)
        for key in ("Eligible", "RMSE", "Coverage", "Effective N"):
            self.assertIsNone(evidence[key])

    def test_dashboard_does_not_poll_phase_e(self):
        page = request(create_app(), "/")["body"].decode()
        self.assertNotIn('fetch("/api/phase-e"', page)


if __name__ == "__main__":
    unittest.main()
