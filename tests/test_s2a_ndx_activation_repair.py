"""Focused tests for the bounded S2A NDX activation repair."""

from __future__ import annotations

from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

import quant.live_market as live_market
from quant.live_market import LiveMarketState


def _payload(*, symbol: str = "$NDX") -> dict[str, object]:
    return {
        "ok": True,
        "mode": "READ ONLY",
        "symbol": symbol,
        "data": {
            "$NDX": {
                "symbol": "$NDX",
                "quote": {
                    "lastPrice": 23_812.125,
                    "tradeTime": 100_000,
                    "quoteTime": 100_500,
                },
            },
        },
    }


class _Response(BytesIO):
    def __init__(self, payload: object, *, final_url: str):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self._final_url = final_url

    def geturl(self) -> str:
        return self._final_url


class S2ANDXActivationRepairTests(unittest.TestCase):
    def test_wrapper_requires_exact_frozen_symbol(self):
        price, event_epoch = live_market.parse_schwab_ndx_quote(
            _payload(), received_at_epoch=101.0,
        )
        self.assertEqual(price, 23_812.125)
        self.assertEqual(event_epoch, 100.0)

        for symbol in ("NDX", "$ndx", "COIN"):
            with self.subTest(symbol=symbol):
                with self.assertRaisesRegex(ValueError, "wrong symbol"):
                    live_market.parse_schwab_ndx_quote(
                        _payload(symbol=symbol), received_at_epoch=101.0,
                    )

    def test_exact_route_uses_only_the_no_redirect_opener(self):
        request = Request(
            live_market.SCHWAB_NDX_QUOTE_URL,
            headers={"Authorization": "Basic opaque"},
        )
        sentinel = object()
        with patch.object(
            live_market._SCHWAB_NDX_OPENER, "open", return_value=sentinel,
        ) as secure_open, patch.object(
            live_market, "_stdlib_urlopen",
        ) as standard_open:
            result = live_market.urlopen(request, timeout=10)

        self.assertIs(result, sentinel)
        secure_open.assert_called_once_with(request, timeout=10)
        standard_open.assert_not_called()

    def test_other_routes_keep_the_existing_standard_opener(self):
        sentinel = object()
        with patch.object(
            live_market, "_stdlib_urlopen", return_value=sentinel,
        ) as standard_open, patch.object(
            live_market._SCHWAB_NDX_OPENER, "open",
        ) as secure_open:
            result = live_market.urlopen(
                "https://example.invalid/quote", timeout=3,
            )

        self.assertIs(result, sentinel)
        standard_open.assert_called_once_with(
            "https://example.invalid/quote", timeout=3,
        )
        secure_open.assert_not_called()

    def test_redirect_handler_rejects_before_a_second_request(self):
        request = Request(live_market.SCHWAB_NDX_QUOTE_URL)
        with self.assertRaisesRegex(HTTPError, "redirect rejected"):
            live_market._RejectRedirects().redirect_request(
                request, None, 302, "Found", {},
                "https://example.invalid/steal",
            )

    def test_missing_credentials_fail_closed_without_a_request(self):
        state = LiveMarketState(clock=lambda: 101.0)
        with patch.dict(os.environ, {}, clear=True), patch.object(
            live_market, "urlopen",
        ) as opened, patch.object(
            live_market.time, "sleep", side_effect=RuntimeError("stop"),
        ), patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                live_market.poll_schwab_ndx(state)

        opened.assert_not_called()
        self.assertIsNone(state.cross_asset_state().ndx_price)

    def test_changed_response_url_is_unavailable_and_secret_safe(self):
        state = LiveMarketState(clock=lambda: 101.0)
        response = _Response(
            _payload(), final_url="https://example.invalid/redirected",
        )
        username = "private-reader-name"
        password = "private-reader-password"
        with patch.dict(os.environ, {
            live_market.COIN_MARKET_USERNAME_ENV: username,
            live_market.COIN_MARKET_PASSWORD_ENV: password,
        }, clear=True), patch.object(
            live_market, "urlopen", return_value=response,
        ) as opened, patch.object(
            live_market.time, "sleep", side_effect=RuntimeError("stop"),
        ), patch("builtins.print") as printed:
            with self.assertRaisesRegex(RuntimeError, "stop"):
                live_market.poll_schwab_ndx(state)

        opened.assert_called_once()
        rendered = " ".join(str(call) for call in printed.call_args_list)
        self.assertNotIn(username, rendered)
        self.assertNotIn(password, rendered)
        self.assertIsNone(state.cross_asset_state().ndx_price)


if __name__ == "__main__":
    unittest.main()
