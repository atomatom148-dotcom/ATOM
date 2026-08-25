import unittest
from quant.q5_microstructure import calculate_microstructure, calculate_queue_imbalance
from quant.quote_history import QuoteHistory, QuoteObservation


class MicrostructureTests(unittest.TestCase):
    def history(self, sizes):
        return QuoteHistory(QuoteObservation(i*10, 99, 101, *pair) for i, pair in enumerate(sizes))

    def test_queue_imbalance_sign_zero_and_exact_horizons(self):
        self.assertEqual(calculate_queue_imbalance(bid_size=3, ask_size=1), .5)
        for sizes, sign in (([(3,1),(3,1)], 1), ([(1,3),(1,3)], -1), ([(2,2),(2,2)], 0)):
            result = calculate_microstructure(self.history(sizes), cutoff_epoch=10)
            self.assertEqual(len(result.forecast_bps), 6)
            self.assertEqual(result.source_as_of_epoch, 10)
            self.assertEqual((result.forecast_bps[0] > 0)-(result.forecast_bps[0] < 0), sign)

    def test_missing_zero_depth_future_and_immutability(self):
        self.assertIsNone(calculate_microstructure(self.history([(1,1)]), cutoff_epoch=0))
        self.assertIsNone(calculate_microstructure(self.history([(0,0),(1,1)]), cutoff_epoch=10))
        history = self.history([(3,1),(3,1),(1,99)])
        original = history.observations
        result = calculate_microstructure(history, cutoff_epoch=10)
        self.assertGreater(result.forecast_bps[0], 0)
        self.assertEqual(history.observations, original)
        self.assertIsNone(calculate_microstructure(history, cutoff_epoch=11))

    def test_invalid_quotes_and_history_order_rejected(self):
        invalid = ((0, 0, 2, 1, 1), (0, 2, 1, 1, 1), (0, 1, 2, -1, 1), (float('nan'),1,2,1,1))
        for values in invalid:
            with self.assertRaises(ValueError): QuoteObservation(*values)
        quote = QuoteObservation(1,1,2,1,1)
        with self.assertRaises(ValueError): QuoteHistory((quote, quote))


if __name__ == '__main__': unittest.main()
