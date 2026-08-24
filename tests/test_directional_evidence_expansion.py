import math
import unittest
from dataclasses import dataclass
from unittest.mock import Mock, patch

from quant.evidence import HORIZONS, HORIZON_SECONDS, records_for_results
from quant.live_market import LiveMarketState
from quant.q3_volatility import VolatilityResult


DIRECTIONAL_QUANTS = (
    "q1_momentum",
    "q2_mean_reversion",
    "q4_stat_arb",
    "q5_microstructure",
    "q6_volume_liquidity",
    "q7_relative_value",
    "q8_cross_asset",
    "q9_factor",
    "q10_options_vol",
    "q11_regime",
    "q12_event_session",
)


@dataclass(frozen=True)
class DirectionalResult:
    quant_id: str
    formula_version: str
    forecast_bps: tuple[float, ...]
    source_as_of_epoch: float | None = None


def result(quant_id: str) -> DirectionalResult:
    source_as_of = 0.0 if quant_id in {"q4_stat_arb", "q10_options_vol"} else None
    return DirectionalResult(
        quant_id, f"{quant_id}-v1", (1, 2, 3, 4, 5, 6), source_as_of,
    )


def records(results, cycle: int = 1):
    return records_for_results(
        results=results,
        cycle_id=f"COIN:{cycle:.9f}",
        symbol="COIN",
        cutoff_epoch=float(cycle),
        cutoff_midpoint=100.0 + cycle,
        created_epoch=float(cycle) + 1,
    )


class DirectionalEvidenceExpansionTests(unittest.TestCase):
    def test_live_cycle_wires_all_eleven_directional_families(self):
        class CapturingStore:
            forecasts = ()
            def put_nowait(self, work):
                self.forecasts = work.directional
                return True

        store = CapturingStore()
        directional_results = {
            function: result(quant_id)
            for function, quant_id in zip(
                (
                    "calculate_momentum", "calculate_mean_reversion",
                    "calculate_stat_arb", "calculate_microstructure",
                    "calculate_volume_liquidity", "calculate_relative_value",
                    "calculate_cross_asset", "calculate_factor",
                    "calculate_options_vol",
                    "calculate_regime", "calculate_event_session",
                ),
                DIRECTIONAL_QUANTS,
            )
        }
        with patch.multiple(
            "quant.live_market",
            **{name: Mock(return_value=value)
               for name, value in directional_results.items()},
        ), patch(
            "quant.live_market.calculate_volatility",
            return_value=VolatilityResult(
                "q3_volatility", "realized-volatility-v1", 1.0,
                (1, 2, 3, 4, 5, 6),
            ),
        ):
            state = LiveMarketState(clock=lambda: 2.0, evidence_outbox=store)
            self.assertTrue(state.accept_quote(bid=100, ask=102, event_epoch=1))

        self.assertEqual(len(store.forecasts), 66)
        self.assertEqual({row.quant_id for row in store.forecasts},
                         set(DIRECTIONAL_QUANTS))

    def test_all_eleven_directional_families_create_shared_cycle_records(self):
        generated = records(tuple(map(result, DIRECTIONAL_QUANTS)))

        self.assertEqual(len(generated), 66)
        self.assertEqual({row.quant_id for row in generated}, set(DIRECTIONAL_QUANTS))
        self.assertEqual({row.cycle_id for row in generated}, {"COIN:1.000000000"})
        self.assertEqual({row.cutoff_midpoint for row in generated}, {101.0})
        self.assertEqual(
            {row.quant_id: sum(item.quant_id == row.quant_id for item in generated)
             for row in generated},
            {quant_id: 6 for quant_id in DIRECTIONAL_QUANTS},
        )
        for row in generated:
            seconds = HORIZON_SECONDS[HORIZONS.index(row.horizon)]
            self.assertEqual(row.maturity_epoch, row.cutoff_epoch + seconds)

    def test_each_directional_family_creates_exactly_six_records(self):
        for quant_id in DIRECTIONAL_QUANTS:
            with self.subTest(quant_id=quant_id):
                generated = records((result(quant_id),))
                self.assertEqual(len(generated), 6)
                self.assertEqual({row.quant_id for row in generated}, {quant_id})
                self.assertEqual(tuple(row.horizon for row in generated), HORIZONS)

    def test_none_family_result_creates_no_records(self):
        self.assertEqual(records((None,)), ())
        mixed = records((result("q4_stat_arb"), None, result("q5_microstructure")))
        self.assertEqual(len(mixed), 12)
        self.assertEqual({row.quant_id for row in mixed},
                         {"q4_stat_arb", "q5_microstructure"})

    def test_q3_and_unavailable_q10_create_no_directional_records(self):
        generated = records(tuple(
            result(quant_id) for quant_id in DIRECTIONAL_QUANTS
            if quant_id != "q10_options_vol"
        ) + (None,))
        quant_ids = {row.quant_id for row in generated}
        self.assertNotIn("q3_volatility", quant_ids)
        self.assertNotIn("q10_options_vol", quant_ids)

    def test_live_cycle_writes_zero_q10_records_when_result_is_none(self):
        class CapturingStore:
            forecasts = ()
            def put_nowait(self, work):
                self.forecasts = work.directional
                return True

        store = CapturingStore()
        directional_results = {
            function: result(quant_id)
            for function, quant_id in zip(
                (
                    "calculate_momentum", "calculate_mean_reversion",
                    "calculate_stat_arb", "calculate_microstructure",
                    "calculate_volume_liquidity", "calculate_relative_value",
                    "calculate_cross_asset", "calculate_factor",
                    "calculate_regime", "calculate_event_session",
                ),
                (quant_id for quant_id in DIRECTIONAL_QUANTS
                 if quant_id != "q10_options_vol"),
            )
        }
        with patch.multiple(
            "quant.live_market",
            **{name: Mock(return_value=value)
               for name, value in directional_results.items()},
        ), patch("quant.live_market.calculate_options_vol", return_value=None):
            state = LiveMarketState(clock=lambda: 2.0, evidence_outbox=store)
            self.assertTrue(state.accept_quote(bid=100, ask=102, event_epoch=1))

        self.assertEqual(len(store.forecasts), 60)
        self.assertNotIn(
            "q10_options_vol", {row.quant_id for row in store.forecasts}
        )

    def test_q10_uses_immutable_identity_and_common_coin_cutoff(self):
        q10 = DirectionalResult(
            "q10_options_vol", "coin-options-skew-delta-v2",
            (1, 2, 3, 4, 5, 6), 0.0,
        )

        generated = records((q10,))

        self.assertEqual(len(generated), 6)
        self.assertEqual({row.quant_id for row in generated}, {"q10_options_vol"})
        self.assertEqual(
            {row.formula_version for row in generated},
            {"coin-options-skew-delta-v2"},
        )
        self.assertEqual({row.cycle_id for row in generated}, {"COIN:1.000000000"})
        self.assertEqual({row.symbol for row in generated}, {"COIN"})
        self.assertEqual({row.cutoff_epoch for row in generated}, {1.0})
        self.assertEqual({row.cutoff_midpoint for row in generated}, {101.0})
        self.assertEqual(tuple(row.horizon for row in generated), HORIZONS)

    def test_one_hundred_cycles_have_6600_idempotent_identities(self):
        durable = {}
        attempts = []
        for cycle in range(100):
            attempts.extend(records(tuple(map(result, DIRECTIONAL_QUANTS)), cycle))

        self.assertEqual(len(attempts), 6_600)
        for row in attempts:
            identity = (row.quant_id, row.formula_version, row.cycle_id,
                        row.symbol, row.horizon)
            durable.setdefault(identity, row)
        self.assertEqual(len(durable), 6_600)

        for row in attempts:
            identity = (row.quant_id, row.formula_version, row.cycle_id,
                        row.symbol, row.horizon)
            durable.setdefault(identity, row)
        self.assertEqual(len(durable), 6_600)
        self.assertEqual(
            len({(row.cycle_id, row.quant_id, row.horizon) for row in attempts}),
            6_600,
        )

    def test_expanded_records_use_the_common_coin_outcome_equation(self):
        generated = records(tuple(map(result, DIRECTIONAL_QUANTS)))
        maturity_midpoint = 111.0
        outcomes = {
            row.quant_id: 10_000 * math.log(
                maturity_midpoint / row.cutoff_midpoint
            )
            for row in generated if row.horizon == "30S"
        }
        self.assertEqual(len(outcomes), 11)
        self.assertEqual(len(set(outcomes.values())), 1)


if __name__ == "__main__":
    unittest.main()
