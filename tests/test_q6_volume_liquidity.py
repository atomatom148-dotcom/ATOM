import unittest
from quant.q6_volume_liquidity import calculate_volume_liquidity, quote_liquidity
from quant.quote_history import QuoteHistory, QuoteObservation


class VolumeLiquidityTests(unittest.TestCase):
    def test_spread_depth_factor_sign_and_six_horizons(self):
        quote = QuoteObservation(0, 99, 101, 3, 1)
        spread, depth, imbalance = quote_liquidity(quote)
        self.assertAlmostEqual(spread, 200.0)
        self.assertEqual(depth, 4)
        self.assertEqual(imbalance, .5)
        history = QuoteHistory((quote, QuoteObservation(10,99,101,3,1)))
        result = calculate_volume_liquidity(history, cutoff_epoch=10)
        self.assertAlmostEqual(result.liquidity_factor, .5/201)
        self.assertEqual(result.mean_depth, 4)
        self.assertEqual(len(result.forecast_bps), 6)
        self.assertGreater(result.forecast_bps[0], 0)
        negative = QuoteHistory((QuoteObservation(0,99,101,1,3), QuoteObservation(10,99,101,1,3)))
        self.assertLess(calculate_volume_liquidity(negative, cutoff_epoch=10).forecast_bps[0], 0)

    def test_zero_depth_insufficient_future_and_unchanged(self):
        zero = QuoteObservation(0,99,101,0,0)
        self.assertIsNone(quote_liquidity(zero))
        self.assertIsNone(calculate_volume_liquidity(QuoteHistory((zero, QuoteObservation(1,99,101,1,1))), cutoff_epoch=1))
        self.assertIsNone(calculate_volume_liquidity(QuoteHistory((QuoteObservation(0,99,101,1,1),)), cutoff_epoch=0))
        history = QuoteHistory((QuoteObservation(0,99,101,3,1), QuoteObservation(10,99,101,3,1), QuoteObservation(20,99,101,1,99)))
        original = history.observations
        self.assertGreater(calculate_volume_liquidity(history, cutoff_epoch=10).forecast_bps[0], 0)
        self.assertEqual(history.observations, original)


if __name__ == '__main__': unittest.main()
