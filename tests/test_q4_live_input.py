import math
import unittest

from quant.live_market import ALPACA_LATEST_QUOTES_URL, LiveMarketState
from quant.q1_momentum import calculate_momentum
from quant.q2_mean_reversion import calculate_mean_reversion
from quant.q3_volatility import calculate_volatility
from quant.q4_stat_arb import FORMULA_VERSION
from quant.web import dashboard_data


def midpoint_quote(value):
    return {"bid": value - 0.01, "ask": value + 0.01}


def feed_pair(state, index, *, qqq_offset=0.0):
    event_epoch = float(index * 10)
    q_log = 4.0 + index * 0.001
    residual = 0.002 * math.sin(index)
    qqq_midpoint = math.exp(q_log)
    coin_midpoint = math.exp(1.0 + 1.5 * q_log + residual)
    qqq = midpoint_quote(qqq_midpoint)
    coin = midpoint_quote(coin_midpoint)
    state.accept_qqq_quote(**qqq, event_epoch=event_epoch + qqq_offset)
    state.accept_quote(**coin, event_epoch=event_epoch)


class Q4LiveInputTests(unittest.TestCase):
    def test_multi_symbol_alpaca_request_is_explicit(self):
        self.assertEqual(
            ALPACA_LATEST_QUOTES_URL,
            "https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=COIN%2CQQQ",
        )

    def test_qqq_midpoint_and_event_timestamp_are_stored_separately(self):
        state = LiveMarketState()
        self.assertTrue(state.accept_qqq_quote(bid=399.0, ask=401.0, event_epoch=12.25))
        self.assertTrue(state.accept_quote(bid=199.0, ask=201.0, event_epoch=13.0))
        snapshot = state.snapshot()
        self.assertEqual(snapshot.qqq_history.latest.midpoint, 400.0)
        self.assertEqual(snapshot.qqq_history.latest.event_epoch, 12.25)
        self.assertEqual(snapshot.history.latest.midpoint, 200.0)

    def test_duplicate_out_of_order_and_invalid_qqq_quotes_are_rejected(self):
        state = LiveMarketState()
        self.assertTrue(state.accept_qqq_quote(bid=99, ask=101, event_epoch=10))
        for bid, ask, epoch in (
            (99, 101, 10), (99, 101, 9), (0, 1, 11), (2, 1, 11),
            (1, float("nan"), 11),
        ):
            self.assertFalse(state.accept_qqq_quote(bid=bid, ask=ask, event_epoch=epoch))
        self.assertEqual(state.snapshot().qqq_history.count, 1)

    def test_future_and_stale_qqq_cannot_satisfy_q4(self):
        for offset in (0.1, -6.0):
            state = LiveMarketState()
            for index in range(20):
                feed_pair(state, index, qqq_offset=offset)
            self.assertIsNone(state.snapshot().stat_arb)

    def test_q4_waits_for_minimum_then_populates_naturally(self):
        state = LiveMarketState()
        for index in range(19):
            feed_pair(state, index)
        self.assertIsNone(state.snapshot().stat_arb)
        feed_pair(state, 19)
        self.assertIsNotNone(state.snapshot().stat_arb)
        data = dashboard_data(snapshot=state.snapshot(), now_epoch=190.0)
        self.assertEqual(data["quant_families"][3]["values"], list(state.snapshot().stat_arb.forecast_bps))

    def test_q4_preserves_exact_paired_qqq_provider_timestamp(self):
        state = LiveMarketState()
        for index in range(20):
            feed_pair(state, index, qqq_offset=-0.25)
        result = state.snapshot().stat_arb
        self.assertIsNotNone(result)
        self.assertEqual(result.cutoff_epoch, 190.0)
        self.assertEqual(result.source_as_of_epoch, 189.75)
        self.assertEqual(result.formula_version, "coin-market-residual-ar1-v2")
        self.assertEqual(result.formula_version, FORMULA_VERSION)

    def test_q4_fails_closed_when_latest_paired_provider_time_is_stale(self):
        state = LiveMarketState()
        for index in range(20):
            feed_pair(state, index)
        self.assertIsNotNone(state.snapshot().stat_arb)
        self.assertTrue(state.accept_quote(bid=199, ask=201, event_epoch=1000))
        self.assertIsNone(state.snapshot().stat_arb)

    def test_market_qqq_uses_latest_valid_midpoint(self):
        state = LiveMarketState()
        state.accept_qqq_quote(bid=399, ask=401, event_epoch=10)
        state.accept_qqq_quote(bid=409, ask=411, event_epoch=11)
        state.accept_qqq_quote(bid=500, ask=499, event_epoch=12)
        self.assertEqual(dashboard_data(snapshot=state.snapshot())["market"]["qqq"], 410.0)

    def test_qqq_intake_does_not_change_frozen_quant_outputs_or_evidence(self):
        state = LiveMarketState()
        for index in range(20):
            feed_pair(state, index)
        before = state.snapshot()
        frozen = (
            calculate_momentum(before.history, cutoff_epoch=190),
            calculate_mean_reversion(before.history, cutoff_epoch=190),
            calculate_volatility(before.history, cutoff_epoch=190),
            before.microstructure, before.volume_liquidity,
        )
        self.assertTrue(state.accept_qqq_quote(bid=60, ask=62, event_epoch=200))
        after = state.snapshot()
        self.assertEqual(
            frozen,
            (after.momentum, after.mean_reversion, after.volatility,
             after.microstructure, after.volume_liquidity),
        )
        self.assertFalse(hasattr(after.stat_arb, "evidence"))


if __name__ == "__main__":
    unittest.main()