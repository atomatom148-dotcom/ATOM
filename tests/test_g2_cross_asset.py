import json
import math
from dataclasses import FrozenInstanceError
import unittest

from quant.g2_cross_asset import (
    CrossAssetState, HORIZON_SECONDS, MAX_HISTORY_SECONDS, append_bounded,
    synchronize,
)
from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import LiveMarketState
from quant.models import HORIZONS
from quant.web import create_app


def history(*values):
    return MidpointHistory(MidpointObservation(epoch, price) for epoch, price in values)


def request(app, path="/api/g2-cross-asset"):
    response = {}
    body = b"".join(app({"PATH_INFO": path}, lambda status, headers: response.update(status=status)))
    return response["status"], json.loads(body)


class G2CrossAssetTests(unittest.TestCase):
    def test_exact_six_prices_returns_moves_and_signs(self):
        current_epoch = 4000.0
        epochs = tuple(current_epoch - seconds for seconds in reversed(HORIZON_SECONDS))
        btc = history(*zip(epochs, (90, 91, 92, 93, 94, 95)), (current_epoch, 100))
        coin = history(*zip(epochs, (180, 181, 182, 183, 184, 185)), (current_epoch, 200))
        qqq = history(*zip(epochs, (360, 361, 362, 363, 364, 365)), (current_epoch, 400))
        ndx = history(*zip(epochs, (18_000, 18_100, 18_200, 18_300, 18_400, 18_500)),
                      (current_epoch, 20_000))
        value = synchronize(as_of_epoch=current_epoch, btc=btc, coin=coin, qqq=qqq, ndx=ndx)

        self.assertEqual(HORIZONS, ("30S", "1M", "5M", "15M", "30M", "1H"))
        self.assertEqual(HORIZON_SECONDS, (30, 60, 300, 900, 1800, 3600))
        self.assertEqual((value.btc_price, value.coin_price, value.qqq_price, value.ndx_price),
                         (100, 200, 400, 20_000))
        for actual, current, priors in (
            (value.btc_return_bps, 100, (95, 94, 93, 92, 91, 90)),
            (value.coin_return_bps, 200, (185, 184, 183, 182, 181, 180)),
            (value.qqq_return_bps, 400, (365, 364, 363, 362, 361, 360)),
            (value.ndx_return_bps, 20_000, (18_500, 18_400, 18_300, 18_200, 18_100, 18_000)),
        ):
            self.assertEqual(len(actual), 6)
            for got, prior in zip(actual, priors):
                self.assertAlmostEqual(got, 10_000 * math.log(current / prior))
        self.assertEqual(value.btc_usd_move, (5, 6, 7, 8, 9, 10))

        negative = synchronize(
            as_of_epoch=60, btc=history((0, 200), (60, 100)),
            coin=MidpointHistory(), qqq=MidpointHistory(), ndx=MidpointHistory(),
        )
        self.assertEqual(negative.btc_usd_move[1], -100)

    def test_common_cutoff_rejects_future_and_missing_is_none(self):
        value = synchronize(
            as_of_epoch=100, btc=history((70, 90), (100, 100), (101, 999)),
            coin=history((101, 200)), qqq=history((100, 400)), ndx=MidpointHistory(),
        )
        self.assertEqual(value.as_of_epoch, 100)
        self.assertEqual(value.btc_price, 100)
        self.assertAlmostEqual(value.btc_return_bps[0], 10_000 * math.log(100 / 90))
        self.assertEqual(value.btc_usd_move[0], 10)
        self.assertIsNone(value.coin_price)
        self.assertEqual(value.coin_return_bps, (None,) * 6)
        self.assertEqual(value.qqq_price, 400)
        self.assertEqual(value.qqq_return_bps, (None,) * 6)
        self.assertIsNone(value.ndx_price)
        self.assertEqual(value.ndx_return_bps, (None,) * 6)
        self.assertNotIn(0, value.coin_return_bps + value.qqq_return_bps + value.ndx_return_bps)

    def test_each_missing_asset_stays_independently_missing(self):
        histories = {name: history((1, index + 1)) for index, name in enumerate(
            ("btc", "coin", "qqq", "ndx"))}
        fields = (("btc", "btc_price", "btc_return_bps"),
                  ("coin", "coin_price", "coin_return_bps"),
                  ("qqq", "qqq_price", "qqq_return_bps"),
                  ("ndx", "ndx_price", "ndx_return_bps"))
        for asset, price_field, return_field in fields:
            supplied = dict(histories)
            supplied[asset] = MidpointHistory()
            value = synchronize(as_of_epoch=1, **supplied)
            self.assertIsNone(getattr(value, price_field))
            self.assertEqual(getattr(value, return_field), (None,) * 6)
            for other, other_price, _ in fields:
                if other != asset:
                    self.assertIsNotNone(getattr(value, other_price))

    def test_state_is_immutable_and_history_is_time_bounded(self):
        value = synchronize(as_of_epoch=0, btc=MidpointHistory(), coin=MidpointHistory(),
                            qqq=MidpointHistory(), ndx=MidpointHistory())
        self.assertIsInstance(value, CrossAssetState)
        with self.assertRaises(FrozenInstanceError):
            value.btc_price = 1
        bounded = append_bounded(history((0, 1), (1, 2)),
                                 MidpointObservation(MAX_HISTORY_SECONDS + 1, 3))
        self.assertEqual(tuple(item.event_epoch for item in bounded.observations), (1, 3601))

    def test_live_state_reuses_coin_qqq_and_endpoint_only_reads_state(self):
        state = LiveMarketState()
        state.accept_quote(bid=199, ask=201, event_epoch=100)
        state.accept_qqq_quote(bid=399, ask=401, event_epoch=99)
        state.accept_g2_price(asset="BTC", price=60_000, event_epoch=98)
        state.accept_g2_price(asset="NDX", price=20_000, event_epoch=97)
        before = state.cross_asset_state()
        status, payload = request(create_app(state=state))
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["as_of_epoch"], 100)
        self.assertEqual((payload["btc_price"], payload["coin_price"],
                          payload["qqq_price"], payload["ndx_price"]),
                         (60_000, 200, 400, 20_000))
        self.assertIs(state.cross_asset_state(), before)

    def test_g2_rejections_fail_open_without_changing_atom_snapshot(self):
        state = LiveMarketState()
        state.accept_quote(bid=99, ask=101, event_epoch=10)
        snapshot = state.snapshot()
        self.assertFalse(state.accept_g2_price(asset="BTC", price=0, event_epoch=11))
        self.assertFalse(state.accept_g2_price(asset="NDX", price=20_000, event_epoch=float("nan")))
        self.assertFalse(state.accept_g2_price(asset="COIN", price=100, event_epoch=11))
        self.assertIs(state.snapshot(), snapshot)


if __name__ == "__main__":
    unittest.main()
