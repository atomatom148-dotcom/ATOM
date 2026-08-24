import math
import unittest
from types import SimpleNamespace

from quant.evidence import (
    DATA_SCHEMA_VERSION,
    EvidenceStore,
    ForecastRecord,
    PostgresEvidenceStore,
    SOURCE_SPEC_VERSION,
    VolatilityForecastRecord,
    records_for_results,
)
from quant.live_market import LiveMarketState
from quant.web import dashboard_data


class MemoryEvidence:
    """Constraint-faithful test double; tests never need PostgreSQL."""

    def __init__(self):
        self.forecasts = []
        self.outcomes = {}
        self.volatility_forecasts = []
        self.volatility_outcomes = {}

    def record_cycle_and_resolve(
        self, forecasts, *, observation_epoch, observation_midpoint,
        volatility_forecasts=None,
    ):
        for index, forecast in enumerate(self.forecasts):
            if index not in self.outcomes and forecast.maturity_epoch <= observation_epoch:
                self.outcomes[index] = (
                    observation_midpoint,
                    10_000 * math.log(observation_midpoint / forecast.cutoff_midpoint),
                    observation_epoch,
                )
        identities = {
            (f.quant_id, f.formula_version, f.cycle_id, f.symbol, f.horizon)
            for f in self.forecasts
        }
        for forecast in forecasts:
            identity = (forecast.quant_id, forecast.formula_version,
                        forecast.cycle_id, forecast.symbol, forecast.horizon)
            if identity in identities:
                raise ValueError("duplicate forecast identity")
            identities.add(identity)
            self.forecasts.append(forecast)
        if volatility_forecasts is not None:
            for index, forecast in enumerate(self.volatility_forecasts):
                if (index not in self.volatility_outcomes and
                        forecast.maturity_epoch <= observation_epoch):
                    self.volatility_outcomes[index] = (
                        observation_midpoint,
                        abs(10_000 * math.log(
                            observation_midpoint / forecast.cutoff_midpoint
                        )),
                        observation_epoch,
                    )
            identities = {
                (f.quant_id, f.formula_version, f.cycle_id, f.symbol, f.horizon)
                for f in self.volatility_forecasts
            }
            for forecast in volatility_forecasts:
                identity = (forecast.quant_id, forecast.formula_version,
                            forecast.cycle_id, forecast.symbol, forecast.horizon)
                if identity in identities:
                    raise ValueError("duplicate volatility forecast identity")
                identities.add(identity)
                self.volatility_forecasts.append(forecast)

    def counts(self):
        return (len(self.forecasts) + len(self.volatility_forecasts),
                len(self.outcomes) + len(self.volatility_outcomes))

    def put_nowait(self, work):
        self.record_cycle_and_resolve(
            work.directional,
            observation_epoch=work.current_observation.event_epoch,
            observation_midpoint=work.current_observation.midpoint,
            volatility_forecasts=work.q3,
        )
        return True


class LiveEvidenceTests(unittest.TestCase):
    def test_directional_records_preserve_provider_source_time(self):
        result = SimpleNamespace(
            quant_id="q4_stat_arb", formula_version="stat-arb-v1",
            forecast_bps=(1.0,) * 6, source_as_of_epoch=98.5,
        )

        records = records_for_results(
            results=(result,), cycle_id="COIN:100", symbol="COIN",
            cutoff_epoch=100.0, cutoff_midpoint=50.0, created_epoch=101.0,
        )

        self.assertEqual(len(records), 6)
        self.assertEqual({row.source_as_of_epoch for row in records}, {98.5})

    def test_provider_timed_family_without_source_time_is_not_persisted(self):
        result = SimpleNamespace(
            quant_id="q10_options_vol", formula_version="options-v1",
            forecast_bps=(1.0,) * 6,
        )

        records = records_for_results(
            results=(result,), cycle_id="COIN:100", symbol="COIN",
            cutoff_epoch=100.0, cutoff_midpoint=50.0, created_epoch=101.0,
        )

        self.assertEqual(records, ())

    def populated_state(self):
        store = MemoryEvidence()
        now = [0.0]
        state = LiveMarketState(clock=lambda: now[0], evidence_outbox=store)
        for second in range(0, 3601, 30):
            now[0] = float(second) + 1
            state.accept_quote(bid=99 + second / 100,
                               ask=101 + second / 100,
                               event_epoch=float(second))
        return state, store, now

    def test_live_q1_q2_map_once_to_records_with_causal_cutoff(self):
        _, store, _ = self.populated_state()
        latest = [row for row in store.forecasts if row.cutoff_epoch == 3600]
        q1_q2 = [row for row in latest if row.quant_id in
                 {"q1_momentum", "q2_mean_reversion"}]
        self.assertEqual(len(q1_q2), 12)
        self.assertEqual(
            {quant_id: sum(row.quant_id == quant_id for row in q1_q2)
             for quant_id in ("q1_momentum", "q2_mean_reversion")},
            {"q1_momentum": 6, "q2_mean_reversion": 6},
        )
        self.assertEqual({row.cutoff_midpoint for row in latest}, {136.0})
        self.assertTrue(all(row.created_epoch <= row.maturity_epoch for row in latest))
        self.assertNotIn("q3_volatility", {row.quant_id for row in store.forecasts})

    def test_live_q3_writes_six_separate_non_directional_records(self):
        _, store, _ = self.populated_state()
        latest = [row for row in store.volatility_forecasts
                  if row.cutoff_epoch == 3600]

        self.assertEqual(len(latest), 6)
        self.assertEqual({row.quant_id for row in latest}, {"q3_volatility"})
        self.assertEqual(
            {row.horizon for row in latest},
            {"30S", "1M", "5M", "15M", "30M", "1H"},
        )
        self.assertNotIn("q3_volatility", {row.quant_id for row in store.forecasts})
        self.assertTrue(all(row.data_schema_version == DATA_SCHEMA_VERSION
                            for row in latest))
        self.assertTrue(all(row.source_spec_version == SOURCE_SPEC_VERSION
                            for row in latest))

    def test_unavailable_forecasts_are_not_persisted(self):
        store = MemoryEvidence()
        state = LiveMarketState(clock=lambda: 1.0, evidence_outbox=store)
        state.accept_quote(bid=99, ask=101, event_epoch=0.0)
        self.assertEqual(store.forecasts, [])
        self.assertEqual(store.volatility_forecasts, [])

    def test_volatility_outcome_is_absolute_move_not_direction(self):
        row = VolatilityForecastRecord(
            "q3_volatility", "v1", "cycle", "COIN", "30S",
            100, 130, 100, 5, 101,
        )
        store = MemoryEvidence()
        store.record_cycle_and_resolve(
            (), observation_epoch=100, observation_midpoint=100,
            volatility_forecasts=(row,),
        )
        store.record_cycle_and_resolve(
            (), observation_epoch=131, observation_midpoint=90,
            volatility_forecasts=(),
        )

        self.assertAlmostEqual(
            store.volatility_outcomes[0][1], abs(10_000 * math.log(.9)),
        )
        self.assertGreater(store.volatility_outcomes[0][1], 0)

    def test_duplicate_identity_is_rejected(self):
        row = ForecastRecord("q1_momentum", "v1", "cycle", "COIN", "30S",
                             1, 31, 100, 2, 2)
        store = MemoryEvidence()
        store.record_cycle_and_resolve((row,), observation_epoch=1,
                                       observation_midpoint=100)
        with self.assertRaises(ValueError):
            store.record_cycle_and_resolve((row,), observation_epoch=2,
                                           observation_midpoint=100)

    def test_outcome_requires_forecast_uses_first_real_observation_once(self):
        store = MemoryEvidence()
        store.record_cycle_and_resolve((), observation_epoch=50,
                                       observation_midpoint=999)
        self.assertEqual(store.outcomes, {})
        row = ForecastRecord("q1_momentum", "v1", "c", "COIN", "30S",
                             100, 130, 100, 5, 101)
        store.record_cycle_and_resolve((row,), observation_epoch=100,
                                       observation_midpoint=100)
        original = store.forecasts[0]
        store.record_cycle_and_resolve((), observation_epoch=129,
                                       observation_midpoint=105)
        self.assertEqual(store.outcomes, {})
        store.record_cycle_and_resolve((), observation_epoch=131,
                                       observation_midpoint=110)
        outcome = store.outcomes[0]
        self.assertEqual(outcome[0], 110)
        self.assertAlmostEqual(outcome[1], 10_000 * math.log(1.1))
        store.record_cycle_and_resolve((), observation_epoch=140,
                                       observation_midpoint=120)
        self.assertEqual(store.outcomes[0], outcome)
        self.assertEqual(store.forecasts[0], original)

    def test_postgres_outcome_resolution_is_idempotent(self):
        class Cursor:
            def __init__(self):
                self.outcomes = {}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, statement, parameters):
                if statement.lstrip().startswith("SELECT"):
                    self.watermark = max(
                        (row[2] for row in self.outcomes.values()),
                        default=-math.inf,
                    )
                    return
                self.assert_conflict_safe(statement)
                midpoint, _, resolved_epoch, _, _ = parameters
                if 1 not in self.outcomes:
                    self.outcomes[1] = (
                        midpoint,
                        10_000 * math.log(midpoint / 100),
                        resolved_epoch,
                    )

            def fetchone(self):
                return (self.watermark,)

            def executemany(self, statement, parameters):
                self.assertEqual(parameters, [])

            def assert_conflict_safe(self, statement):
                normalized = " ".join(statement.split())
                if "ON CONFLICT (forecast_id) DO NOTHING" not in normalized:
                    raise RuntimeError("duplicate forecast outcome")

            def assertEqual(self, first, second):
                if first != second:
                    raise AssertionError(f"{first!r} != {second!r}")

        class Connection:
            def __init__(self, cursor):
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def cursor(self):
                return self._cursor

        cursor = Cursor()
        store = object.__new__(PostgresEvidenceStore)
        store._database_url = "postgresql://test"
        store._connect = lambda _: Connection(cursor)

        store.record_cycle_and_resolve(
            (), observation_epoch=131, observation_midpoint=110
        )
        first = cursor.outcomes[1]
        store.record_cycle_and_resolve(
            (), observation_epoch=140, observation_midpoint=120
        )

        self.assertEqual(len(cursor.outcomes), 1)
        self.assertEqual(cursor.outcomes[1], first)
        self.assertEqual(first[0], 110)
        self.assertAlmostEqual(first[1], 10_000 * math.log(1.1))
        self.assertEqual(first[2], 131)

    def test_postgres_resolution_is_bounded_by_latest_resolved_epoch(self):
        class Cursor:
            def __init__(self):
                self.statements = []

            def __enter__(self): return self
            def __exit__(self, *args): pass

            def execute(self, statement, parameters):
                self.statements.append((" ".join(statement.split()), parameters))

            def fetchone(self):
                return (123.0,)

            def executemany(self, statement, parameters):
                self.forecast_parameters = parameters

        class Connection:
            def __init__(self, cursor): self._cursor = cursor
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): return self._cursor

        cursor = Cursor()
        store = object.__new__(PostgresEvidenceStore)
        store._database_url = "postgresql://test"
        store._connect = lambda _: Connection(cursor)
        store.record_cycle_and_resolve(
            (), observation_epoch=131, observation_midpoint=110,
        )

        watermark_sql, watermark_parameters = cursor.statements[0]
        resolution_sql, resolution_parameters = cursor.statements[1]
        self.assertIn("max(resolved_epoch)", watermark_sql)
        self.assertEqual(watermark_parameters, ())
        self.assertIn("f.maturity_epoch > %s", resolution_sql)
        self.assertIn("f.maturity_epoch <= %s", resolution_sql)
        self.assertEqual(resolution_parameters, (110, 110, 131, 123.0, 131))

    def test_postgres_q3_uses_separate_append_only_volatility_tables(self):
        class Cursor:
            def __init__(self):
                self.executions = []
                self.batches = []

            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, statement, parameters):
                self.executions.append((" ".join(statement.split()), parameters))
            def fetchone(self): return (-math.inf,)
            def executemany(self, statement, parameters):
                self.batches.append((" ".join(statement.split()), parameters))

        class Connection:
            def __init__(self, cursor): self._cursor = cursor
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def cursor(self): return self._cursor

        cursor = Cursor()
        store = object.__new__(PostgresEvidenceStore)
        store._database_url = "postgresql://test"
        store._connect = lambda _: Connection(cursor)
        row = VolatilityForecastRecord(
            "q3_volatility", "realized-volatility-v1", "COIN:100", "COIN",
            "30S", 100, 130, 100, 5, 101,
        )

        store.record_cycle_and_resolve(
            (), observation_epoch=100, observation_midpoint=100,
            volatility_forecasts=(row,),
        )

        volatility_resolution_sql, resolution_parameters = cursor.executions[3]
        volatility_insert_sql, insert_parameters = cursor.batches[1]
        self.assertIn("INSERT INTO volatility_forecast_outcomes", volatility_resolution_sql)
        self.assertIn("abs(10000 * ln(%s / f.cutoff_midpoint))", volatility_resolution_sql)
        self.assertIn("ON CONFLICT (forecast_id) DO NOTHING", volatility_resolution_sql)
        self.assertEqual(resolution_parameters, (100, 100, 100, -math.inf, 100))
        self.assertIn("INSERT INTO volatility_forecasts", volatility_insert_sql)
        self.assertIn("data_schema_version", volatility_insert_sql)
        self.assertIn("source_spec_version", volatility_insert_sql)
        self.assertIn("DO NOTHING", volatility_insert_sql)
        self.assertEqual(
            insert_parameters[0][-2:],
            (DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION),
        )

    def test_postgres_duplicate_forecast_preserves_first_and_resolves(self):
        class Cursor:
            def __init__(self):
                self.forecasts = {}
                self.outcomes = {}
                self.next_forecast_id = 1

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, statement, parameters):
                if statement.lstrip().startswith("SELECT"):
                    self.watermark = max(
                        (row[2] for row in self.outcomes.values()),
                        default=-math.inf,
                    )
                    return
                midpoint, _, resolved_epoch, watermark, observation_epoch = parameters
                for forecast_id, values in self.forecasts.values():
                    if (forecast_id not in self.outcomes
                            and values[6] > watermark
                            and values[6] <= observation_epoch):
                        self.outcomes[forecast_id] = (
                            midpoint,
                            10_000 * math.log(midpoint / values[7]),
                            resolved_epoch,
                        )

            def fetchone(self):
                return (self.watermark,)

            def executemany(self, statement, parameters):
                normalized = " ".join(statement.split())
                self.forecast_statement = normalized
                conflict_clause = (
                    "ON CONFLICT (quant_id, formula_version, cycle_id, "
                    "symbol, horizon) DO NOTHING"
                )
                if conflict_clause not in normalized:
                    raise RuntimeError("duplicate forecast identity")
                for values in parameters:
                    identity = values[:5]
                    if identity not in self.forecasts:
                        self.forecasts[identity] = (
                            self.next_forecast_id, values
                        )
                        self.next_forecast_id += 1

        class Connection:
            def __init__(self, cursor):
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def cursor(self):
                return self._cursor

        cursor = Cursor()
        store = object.__new__(PostgresEvidenceStore)
        store._database_url = "postgresql://test"
        store._connect = lambda _: Connection(cursor)
        original = ForecastRecord(
            "q1_momentum", "direct-log-momentum-v1", "COIN:cycle", "COIN",
            "30S", 100, 130, 100, 5, 101,
        )
        conflicting = ForecastRecord(
            "q1_momentum", "direct-log-momentum-v1", "COIN:cycle", "COIN",
            "30S", 110, 140, 999, 999, 111,
        )

        store.record_cycle_and_resolve(
            (original,), observation_epoch=100, observation_midpoint=100
        )
        identity = (
            original.quant_id, original.formula_version, original.cycle_id,
            original.symbol, original.horizon,
        )
        first_forecast_id, first_values = cursor.forecasts[identity]
        store.record_cycle_and_resolve(
            (conflicting,), observation_epoch=131, observation_midpoint=110
        )

        self.assertEqual(len(cursor.forecasts), 1)
        authoritative_forecast_id, authoritative_values = cursor.forecasts[identity]
        self.assertEqual(authoritative_forecast_id, first_forecast_id)
        self.assertEqual(authoritative_values, first_values)
        self.assertEqual(
            authoritative_values[5:],
            (100, 130, 100, 5, 101,
             DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, None),
        )
        self.assertIn("data_schema_version", cursor.forecast_statement)
        self.assertIn("source_spec_version", cursor.forecast_statement)
        self.assertIn("source_as_of_epoch", cursor.forecast_statement)
        self.assertEqual(len(cursor.outcomes), 1)
        outcome = cursor.outcomes[first_forecast_id]
        self.assertEqual(outcome[0], 110)
        self.assertAlmostEqual(outcome[1], 10_000 * math.log(1.1))
        self.assertEqual(outcome[2], 131)

        store.record_cycle_and_resolve(
            (), observation_epoch=140, observation_midpoint=120
        )
        self.assertEqual(len(cursor.outcomes), 1)
        self.assertEqual(cursor.outcomes[first_forecast_id], outcome)

    def test_shared_connection_rolls_back_before_worker_recovery(self):
        class OperationalError(Exception): pass
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, *_args): pass
            def executemany(self, *_args):
                raise OperationalError("connection lost")
        class Connection:
            def __init__(self): self.rollbacks = 0
            def cursor(self): return Cursor()
            def rollback(self): self.rollbacks += 1

        connection = Connection()
        store = object.__new__(PostgresEvidenceStore)
        store._database_url = "postgresql://test"
        store._connection = connection
        store._connect = None
        with self.assertRaises(OperationalError):
            store.record_cycle_and_resolve(
                (), observation_epoch=100, observation_midpoint=100,
                resolution_enabled=False,
            )
        self.assertEqual(connection.rollbacks, 1)

    def test_store_contract_has_no_update_or_delete_api(self):
        self.assertFalse(hasattr(EvidenceStore, "update"))
        self.assertFalse(hasattr(EvidenceStore, "delete"))

    def test_dashboard_only_populates_durable_counts(self):
        evidence = dashboard_data(evidence_counts=(17, 4))["evidence"]
        self.assertEqual(evidence, {"Forecasts": 17, "Resolved": 4})


if __name__ == "__main__":
    unittest.main()
