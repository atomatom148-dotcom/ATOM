import json
import math
import re
import unittest

from quant.evidence import MIN_EFFECTIVE_N, PhaseECohortMetrics, PostgresEvidenceStore
from quant.web import create_app, dashboard_data
from tests.test_web import request


class Cursor:
    def __init__(self, rows=(), effective_rows=()):
        self.metric_rows = rows
        self.effective_rows = effective_rows
        self.rows = ()
        self.statement = None
        self.parameters = None
        self.executions = []

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, statement, parameters):
        self.statement, self.parameters = statement, parameters
        self.executions.append((statement, parameters))
        self.rows = (self.effective_rows if "f.cutoff_epoch, f.forecast_id" in statement
                     else self.metric_rows)
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
            ("q1", "v1", "COIN", "30S", 3, 2, 1, .5, 4.25, 1.0, 4.0, 2.0),
            ("q1", "v2", "COIN", "1H", 1, 0, 0, None, None, None, None, None),
            ("q2", "v1", "SPY", "1M", 2, 2, 2, 1.0, 0.0, .5, 0.0, 0.0),
        ))
        values = store_with(cursor).phase_e_cohorts(100.0)
        self.assertEqual(values, (
            PhaseECohortMetrics("q1", "v1", "COIN", "30S", 3, 2, 1, .5, 4.25, 1.0, 4.0, 2.0, 0, False),
            PhaseECohortMetrics("q1", "v2", "COIN", "1H", 1, 0, 0, None, None, None, None, None, 0, False),
            PhaseECohortMetrics("q2", "v1", "SPY", "1M", 2, 2, 2, 1.0, 0.0, .5, 0.0, 0.0, 0, False),
        ))
        with self.assertRaises((AttributeError, TypeError)):
            values[0].coverage = 1.0

    def test_query_has_exact_grouping_left_join_boundary_and_formulas(self):
        cursor = Cursor()
        store_with(cursor).phase_e_cohorts(123.5)
        sql = " ".join(cursor.executions[0][0].split())
        self.assertIn("LEFT JOIN forecast_outcomes AS o USING (forecast_id)", sql)
        self.assertIn("GROUP BY f.quant_id, f.formula_version, f.symbol, f.horizon", sql)
        self.assertEqual(cursor.executions[0][1], (123.5,) * 14)
        self.assertEqual(sql.count("f.maturity_epoch <= %s"), 8)
        self.assertEqual(sql.count("o.resolved_epoch <= %s"), 6)
        self.assertIn("NULLIF(count(*) FILTER", sql)
        self.assertIn("sqrt(avg(power(f.forecast_bps - o.outcome_bps, 2))", sql)
        self.assertIn("AND o.forecast_id IS NOT NULL", sql)

    def test_outcome_is_invisible_until_its_resolution_epoch(self):
        class PointInTimeCursor(Cursor):
            maturity_epoch = 100
            resolved_epoch = 110
            forecast_bps = 5.0
            outcome_bps = 2.0

            def execute(self, statement, parameters):
                super().execute(statement, parameters)
                if "f.cutoff_epoch, f.forecast_id" in statement:
                    self.rows = ()
                    return
                as_of = parameters[0]
                matured = self.maturity_epoch <= as_of
                outcome_is_visible = matured and self.resolved_epoch <= as_of
                self.rows = ((
                    "q1", "v1", "COIN", "30S", 1, int(matured),
                    int(outcome_is_visible),
                    int(outcome_is_visible) / int(matured) if matured else None,
                    abs(self.forecast_bps - self.outcome_bps)
                    if outcome_is_visible else None,
                    1.0 if outcome_is_visible else None,
                    abs(self.forecast_bps - self.outcome_bps)
                    if outcome_is_visible else None,
                    self.forecast_bps - self.outcome_bps
                    if outcome_is_visible else None,
                ),)

        before = store_with(PointInTimeCursor()).phase_e_cohorts(105)
        self.assertEqual(
            before,
            (PhaseECohortMetrics(
                "q1", "v1", "COIN", "30S", 1, 1, 0, 0.0, None,
                None, None, None, 0, False,
            ),),
        )

        at_resolution = store_with(PointInTimeCursor()).phase_e_cohorts(110)
        self.assertEqual(at_resolution[0].resolved_count, 1)
        self.assertEqual(at_resolution[0].coverage, 1.0)
        self.assertEqual(at_resolution[0].rmse_bps, 3.0)
        self.assertEqual(at_resolution[0].directional_accuracy, 1.0)
        self.assertEqual(at_resolution[0].mae_bps, 3.0)
        self.assertEqual(at_resolution[0].bias_bps, 3.0)

    def test_resolution_epoch_bound_applies_to_each_outcome_population(self):
        cursor = Cursor()
        store_with(cursor).phase_e_cohorts(105)
        sql = " ".join(cursor.executions[0][0].split())
        resolved_filter = re.search(
            r"count\(o\.forecast_id\) FILTER \( WHERE f\.maturity_epoch <= %s "
            r"AND o\.resolved_epoch <= %s \) AS resolved_count",
            sql,
        )
        coverage_filter = re.search(
            r"count\(o\.forecast_id\) FILTER \( WHERE f\.maturity_epoch <= %s "
            r"AND o\.resolved_epoch <= %s \)::double precision",
            sql,
        )
        rmse_filter = re.search(
            r"FILTER \(WHERE f\.maturity_epoch <= %s "
            r"AND o\.forecast_id IS NOT NULL AND o\.resolved_epoch <= %s\)",
            sql,
        )
        self.assertIsNotNone(resolved_filter)
        self.assertIsNotNone(coverage_filter)
        self.assertIsNotNone(rmse_filter)

    def test_e2_equations_and_causal_population_are_in_grouped_select(self):
        cursor = Cursor()
        store_with(cursor).phase_e_cohorts(50)
        sql = " ".join(cursor.executions[0][0].split())
        self.assertIn("f.forecast_bps <> 0 AND o.outcome_bps <> 0", sql)
        self.assertIn("f.forecast_bps > 0 AND o.outcome_bps > 0", sql)
        self.assertIn("f.forecast_bps < 0 AND o.outcome_bps < 0", sql)
        self.assertIn("THEN 1.0 ELSE 0.0", sql)
        self.assertIn("avg(abs(f.forecast_bps - o.outcome_bps))", sql)
        self.assertIn("avg(f.forecast_bps - o.outcome_bps)", sql)
        e2_filters = re.findall(
            r"FILTER \(WHERE f\.maturity_epoch <= %s "
            r"AND o\.forecast_id IS NOT NULL "
            r"AND o\.resolved_epoch <= %s\)", sql,
        )
        self.assertEqual(len(e2_filters), 4)  # RMSE plus all three E2 metrics.

    def test_e2_deterministic_direction_mae_and_bias_examples(self):
        # (maturity, resolution, forecast, outcome): includes every sign and zero case.
        rows = [
            (10, 10, 4, 2), (10, 10, -5, -2),
            (10, 10, 3, -1), (10, 10, -2, 1),
            (10, 10, 0, 7), (10, 10, 8, 0), (10, 10, 0, 0),
            (51, 10, 999, 1),       # immature
            (10, None, 999, 1),     # matured but unresolved
            (10, 51, 999, 1),       # future outcome
        ]
        visible = [row for row in rows
                   if row[0] <= 50 and row[1] is not None and row[1] <= 50]
        directional = [(forecast, outcome) for _, _, forecast, outcome in visible
                       if forecast != 0 and outcome != 0]
        hits = sum((forecast > 0) == (outcome > 0)
                   for forecast, outcome in directional)
        self.assertEqual((hits, len(directional), hits / len(directional)), (2, 4, .5))
        errors = [forecast - outcome for _, _, forecast, outcome in visible]
        self.assertEqual(errors, [2, -3, 4, -3, -7, 8, 0])
        self.assertEqual(sum(map(abs, errors)) / len(errors), 27 / 7)
        self.assertEqual(sum(errors) / len(errors), 1 / 7)
        self.assertIn(0, errors)  # Zero error contributes zero to both averages.

        cancelling = [(5, 3), (1, 3)]
        self.assertEqual(sum(forecast - outcome for forecast, outcome in cancelling) / 2, 0)
        self.assertIsNone(None if not [] else 0)  # no resolved rows => MAE null
        self.assertIsNone(None if not [] else 0)  # no resolved rows => bias null
        self.assertIsNone(None if not [] else 0)  # no nonzero signs => direction null

    def test_query_is_one_read_only_select_and_orders_exact_cohorts(self):
        cursor = Cursor()
        store_with(cursor).phase_e_cohorts(1.0)
        sql = re.sub(r"--[^\n]*|/\*.*?\*/", "", cursor.executions[0][0],
                     flags=re.DOTALL).upper()
        self.assertEqual(len(re.findall(r"\bSELECT\b", sql)), 1)
        for forbidden in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE"):
            self.assertIsNone(re.search(rf"\b{forbidden}\b", sql))
        normalized = " ".join(sql.split())
        self.assertIn("ORDER BY F.QUANT_ID, F.FORMULA_VERSION, F.SYMBOL", normalized)
        positions = [normalized.index(f"WHEN '{horizon}' THEN {index}")
                     for index, horizon in enumerate(("30S", "1M", "5M", "15M", "30M", "1H"), 1)]
        self.assertEqual(positions, sorted(positions))

    def test_effective_n_uses_exact_horizon_spacing_and_greedy_boundaries(self):
        metric_rows = tuple(
            ("q1", "v1", "COIN", horizon, 4, 4, 4, 1.0, 0.0, 1.0, 0.0, 0.0)
            for horizon in ("30S", "1M", "5M", "15M", "30M", "1H")
        )
        seconds = {"30S": 30, "1M": 60, "5M": 300,
                   "15M": 900, "30M": 1800, "1H": 3600}
        effective_rows = []
        for horizon, spacing in seconds.items():
            effective_rows.extend(("q1", "v1", "COIN", horizon, cutoff, forecast_id)
                                  for forecast_id, cutoff in enumerate(
                                      (0, spacing - 1, spacing, 2 * spacing), 1))
        values = store_with(Cursor(metric_rows, effective_rows)).phase_e_cohorts(10_000)
        self.assertEqual({value.horizon: value.effective_n for value in values},
                         {horizon: 3 for horizon in seconds})
        self.assertTrue(all(value.effective_n <= value.resolved_count for value in values))

    def test_effective_n_matches_five_minute_example(self):
        metrics = (("q1", "v1", "COIN", "5M", 8, 8, 8, 1.0,
                    0.0, 1.0, 0.0, 0.0),)
        cutoffs = (0, 30, 60, 299, 300, 301, 599, 600)
        resolved = tuple(("q1", "v1", "COIN", "5M", cutoff, index)
                         for index, cutoff in enumerate(cutoffs, 1))
        value = store_with(Cursor(metrics, resolved)).phase_e_cohorts(1_000)[0]
        self.assertEqual(value.effective_n, 3)

    def test_effective_n_never_shares_exact_cohort_observations(self):
        identities = (
            ("q1", "v1", "COIN", "30S"),
            ("q2", "v1", "COIN", "30S"),  # quant
            ("q1", "v2", "COIN", "30S"),  # formula
            ("q1", "v1", "SPY", "30S"),   # symbol
            ("q1", "v1", "COIN", "1M"),   # horizon
        )
        metrics = tuple(identity + (1, 1, 1, 1.0, 0.0, 1.0, 0.0, 0.0)
                        for identity in identities)
        resolved = tuple(identity + (0, index)
                         for index, identity in enumerate(identities, 1))
        values = store_with(Cursor(metrics, resolved)).phase_e_cohorts(100)
        self.assertEqual([value.effective_n for value in values], [1] * 5)

    def test_effective_n_query_is_causal_deterministic_and_read_only(self):
        cursor = Cursor()
        values = store_with(cursor).phase_e_cohorts(123.5)
        self.assertEqual(values, ())
        self.assertEqual(len(cursor.executions), 2)
        sql, parameters = cursor.executions[1]
        normalized = " ".join(sql.split())
        self.assertEqual(parameters, (123.5, 123.5))
        self.assertIn("f.maturity_epoch <= %s", normalized)
        self.assertIn("o.forecast_id IS NOT NULL", normalized)
        self.assertIn("o.resolved_epoch <= %s", normalized)
        self.assertIn("f.cutoff_epoch, f.forecast_id", normalized)
        self.assertRegex(normalized, r"ORDER BY .* f.cutoff_epoch, f.forecast_id")
        for statement, _ in cursor.executions:
            command = re.sub(r"--[^\n]*|/\*.*?\*/", "", statement,
                             flags=re.DOTALL).strip().upper()
            self.assertTrue(command.startswith("SELECT"))
            for forbidden in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP",
                              "CREATE", "TRUNCATE"):
                self.assertIsNone(re.search(rf"\b{forbidden}\b", command))

    def test_no_causally_resolved_forecasts_means_zero_effective_n(self):
        metrics = (("q1", "v1", "COIN", "30S", 3, 2, 0, 0.0,
                    None, None, None, None),)
        value = store_with(Cursor(metrics)).phase_e_cohorts(50)[0]
        self.assertEqual(value.effective_n, 0)

    def test_eligibility_threshold_boundaries(self):
        self.assertEqual(MIN_EFFECTIVE_N, 20)
        for effective_n, expected in ((0, False), (1, False), (19, False),
                                      (20, True), (21, True)):
            with self.subTest(effective_n=effective_n):
                metrics = (("q1", "v1", "COIN", "30S", effective_n,
                            effective_n, effective_n, 1.0, 0.0, 1.0,
                            0.0, 0.0),)
                resolved = tuple(
                    ("q1", "v1", "COIN", "30S", index * 30, index)
                    for index in range(effective_n)
                )
                value = store_with(Cursor(metrics, resolved)).phase_e_cohorts(10_000)[0]
                self.assertEqual(value.effective_n, effective_n)
                self.assertIs(value.eligible, expected)

    def test_eligibility_uses_only_effective_n(self):
        identities = (
            ("excellent", "v1", "COIN", "30S", 19, .01, 1.0, .01, 0.0),
            ("terrible", "v2", "SPY", "1H", 20, 9999.0, 0.0, 9999.0, -9999.0),
        )
        metrics = tuple(
            (quant_id, version, symbol, horizon, effective_n, effective_n,
             effective_n, .001 if quant_id == "excellent" else 1.0,
             rmse, direction, mae, bias)
            for (quant_id, version, symbol, horizon, effective_n, rmse,
                 direction, mae, bias) in identities
        )
        spacing = {"30S": 30, "1H": 3600}
        resolved = tuple(
            (quant_id, version, symbol, horizon, index * spacing[horizon],
             f"{quant_id}-{index}")
            for (quant_id, version, symbol, horizon, effective_n, *_rest) in identities
            for index in range(effective_n)
        )
        values = store_with(Cursor(metrics, resolved)).phase_e_cohorts(100_000)
        self.assertEqual([(value.effective_n, value.eligible) for value in values],
                         [(19, False), (20, True)])

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
        cohort = PhaseECohortMetrics(
            "q7", "v2", "COIN", "30S", 4, 3, 2, 2 / 3, 5.5,
            0.5, 4.5, -1.25, 2, False,
        )

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
                "directional_accuracy": 0.5, "mae_bps": 4.5,
                "bias_bps": -1.25, "effective_n": 2, "eligible": False,
            }],
        })

    def test_dashboard_keeps_only_global_evidence_totals(self):
        evidence = dashboard_data(evidence_counts=(10, 8))["evidence"]
        self.assertEqual(evidence, {"Forecasts": 10, "Resolved": 8})

    def test_dashboard_does_not_poll_phase_e(self):
        page = request(create_app(), "/")["body"].decode()
        self.assertNotIn('fetch("/api/phase-e"', page)


if __name__ == "__main__":
    unittest.main()
