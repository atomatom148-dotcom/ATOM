import math
import unittest

from quant.evidence import EvidenceStore, ForecastRecord, records_for_results
from quant.live_market import LiveMarketState
from quant.web import dashboard_data


class MemoryEvidence:
    """Constraint-faithful test double; tests never need PostgreSQL."""

    def __init__(self):
        self.forecasts = []
        self.outcomes = {}

    def record_cycle_and_resolve(self, forecasts, *, observation_epoch, observation_midpoint):
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

    def counts(self):
        return len(self.forecasts), len(self.outcomes)


class LiveEvidenceTests(unittest.TestCase):
    def populated_state(self):
        store = MemoryEvidence()
        now = [0.0]
        state = LiveMarketState(clock=lambda: now[0], evidence_store=store)
        for second in range(0, 3601, 30):
            now[0] = float(second) + 1
            state.accept_quote(bid=99 + second / 100,
                               ask=101 + second / 100,
                               event_epoch=float(second))
        return state, store, now

    def test_live_q1_q2_map_to_records_with_causal_cutoff(self):
        _, store, _ = self.populated_state()
        latest = [row for row in store.forecasts if row.cutoff_epoch == 3600]
        self.assertEqual(len(latest), 12)
        self.assertEqual({row.quant_id for row in latest},
                         {"q1_momentum", "q2_mean_reversion"})
        self.assertEqual({row.cutoff_midpoint for row in latest}, {136.0})
        self.assertTrue(all(row.created_epoch <= row.maturity_epoch for row in latest))
        self.assertNotIn("q3_volatility", {row.quant_id for row in store.forecasts})

    def test_unavailable_forecasts_are_not_persisted(self):
        store = MemoryEvidence()
        state = LiveMarketState(clock=lambda: 1.0, evidence_store=store)
        state.accept_quote(bid=99, ask=101, event_epoch=0.0)
        self.assertEqual(store.forecasts, [])

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

    def test_store_contract_has_no_update_or_delete_api(self):
        self.assertFalse(hasattr(EvidenceStore, "update"))
        self.assertFalse(hasattr(EvidenceStore, "delete"))

    def test_dashboard_only_populates_durable_counts(self):
        evidence = dashboard_data(evidence_counts=(17, 4))["evidence"]
        self.assertEqual(evidence["Forecasts"], 17)
        self.assertEqual(evidence["Resolved"], 4)
        for field in ("Eligible", "RMSE", "Coverage", "Effective N"):
            self.assertIsNone(evidence[field])


if __name__ == "__main__":
    unittest.main()
