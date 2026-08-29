"""Deterministic contracts for the inert Schwab S1 transient market-data bus."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path
import sys
import threading
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.schwab_market_bus import (  # noqa: E402
    BOOK_KEY,
    MAX_AGE_SECONDS,
    NDX_KEY,
    SNAPSHOT_TTL_SECONDS,
    BookLevel,
    BookSnapshot,
    MarketBus,
    MarketDataConflictError,
    MarketDataInvalidError,
    MarketDataOrderError,
    MarketDataStaleError,
    NDXSnapshot,
    normalize_nasdaq_book,
    normalize_ndx_quote,
)


NOW = 1_700_000_009.0


class RecordingSink:
    """Strict in-memory proof of the bounded transient publication contract."""

    def __init__(self, results: list[bool] | None = None) -> None:
        self.calls: list[tuple[str, str, int, str]] = []
        self.latest: dict[str, str] = {}
        self._results = iter(results or [])

    def publish(
        self,
        key: str,
        payload_json: str,
        ttl_seconds: int,
        owner_token: str,
    ) -> bool:
        if not key.startswith("atom:v9:schwab:"):
            raise AssertionError("publication escaped the frozen namespace")
        if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 86_400:
            raise AssertionError("publication TTL must be positive and bounded")
        json.loads(payload_json)
        self.calls.append((key, payload_json, ttl_seconds, owner_token))
        try:
            accepted = next(self._results)
        except StopIteration:
            accepted = True
        if accepted:
            self.latest[key] = payload_json
        return accepted


def ndx_payload(
    *,
    last: object = 24_250.25,
    trade_ms: object = 1_700_000_000_000,
    mark: object = 24_251.0,
    quote_ms: object = 1_700_000_001_000,
    bid: object = 24_250.5,
    ask: object = 24_251.5,
    inner_symbol: object = "$NDX",
) -> dict[str, object]:
    return {
        "$NDX": {
            "symbol": inner_symbol,
            "quote": {
                "lastPrice": last,
                "tradeTime": trade_ms,
                "mark": mark,
                "quoteTime": quote_ms,
                "bidPrice": bid,
                "askPrice": ask,
            },
        }
    }


def level(
    price: object,
    size: object,
    count: object = 1,
    participants: object | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {"0": price, "1": size, "2": count}
    if participants is not None:
        value["3"] = participants
    return value


def book_payload(
    *,
    provider_ms: object = 1_700_000_000_000,
    symbol: object = "COIN",
    sequence: object = 17,
    bids: object | None = None,
    asks: object | None = None,
) -> dict[str, object]:
    return {
        "0": symbol,
        "1": provider_ms,
        "2": bids if bids is not None else [
            level(99.0, 9.0),
            level(102.0, 4.0),
            level(100.0, 7.0),
            level(101.0, 5.0),
        ],
        "3": asks if asks is not None else [
            level(105.0, 8.0),
            level(103.0, 3.0),
            level(106.0, 9.0),
            level(104.0, 6.0),
        ],
        "seq": sequence,
    }


def normalized_ndx(
    *, provider_ms: int = 1_700_000_000_000, received: float = NOW
) -> NDXSnapshot:
    return normalize_ndx_quote(
        ndx_payload(trade_ms=provider_ms),
        received_at_epoch=received,
    )


def normalized_book(
    *, provider_ms: int = 1_700_000_000_000, received: float = NOW
) -> BookSnapshot:
    return normalize_nasdaq_book(
        book_payload(provider_ms=provider_ms),
        received_at_epoch=received,
    )


class SchwabMarketNormalizationTests(unittest.TestCase):
    def test_ndx_normalizes_dollar_symbol_and_preserves_quote_time(self) -> None:
        value = normalize_ndx_quote(
            ndx_payload(
                last=24_250.25,
                trade_ms=1_700_000_000_125,
                mark=24_251.0,
                quote_ms=1_700_000_001_250,
            ),
            received_at_epoch=1_700_000_002.0,
        )

        self.assertEqual(value.symbol, "NDX")
        self.assertEqual(value.price, 24_250.25)
        self.assertEqual(value.provider_epoch, 1_700_000_000.125)
        self.assertEqual(value.trade_time_epoch, 1_700_000_000.125)
        self.assertEqual(value.quote_time_epoch, 1_700_000_001.25)
        self.assertEqual(value.received_at_epoch, 1_700_000_002.0)

        mark = normalize_ndx_quote(
            ndx_payload(last=None, trade_ms=None, mark=24_251.0),
            received_at_epoch=NOW,
        )
        self.assertEqual(mark.price, 24_251.0)
        self.assertEqual(mark.provider_epoch, 1_700_000_001.0)

        midpoint = normalize_ndx_quote(
            ndx_payload(
                last=None,
                trade_ms=None,
                mark=None,
                bid=24_249.0,
                ask=24_251.0,
            ),
            received_at_epoch=NOW,
        )
        self.assertEqual(midpoint.price, 24_250.0)
        self.assertEqual(midpoint.provider_epoch, 1_700_000_001.0)

        with self.assertRaises(FrozenInstanceError):
            value.price = 1.0  # type: ignore[misc]

    def test_ndx_rejects_wrong_symbol_or_invalid_price_and_provider_time(self) -> None:
        invalid_payloads = (
            {},
            {"NDX": ndx_payload()["$NDX"]},
            ndx_payload(inner_symbol="NDX"),
            ndx_payload(last=True, mark=None, bid=None, ask=None),
            ndx_payload(last="24250", mark=None, bid=None, ask=None),
            ndx_payload(last=0.0, mark=None, bid=None, ask=None),
            ndx_payload(last=-1.0, mark=None, bid=None, ask=None),
            ndx_payload(last=math.nan, mark=None, bid=None, ask=None),
            ndx_payload(last=math.inf, mark=None, bid=None, ask=None),
            ndx_payload(
                trade_ms=True,
                mark=None,
                quote_ms=None,
                bid=None,
                ask=None,
            ),
            ndx_payload(
                trade_ms="1700000000000",
                mark=None,
                quote_ms=None,
                bid=None,
                ask=None,
            ),
            ndx_payload(
                trade_ms=math.nan,
                mark=None,
                quote_ms=None,
                bid=None,
                ask=None,
            ),
            ndx_payload(
                trade_ms=0.0,
                mark=None,
                quote_ms=None,
                bid=None,
                ask=None,
            ),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(MarketDataInvalidError):
                    normalize_ndx_quote(payload, received_at_epoch=NOW)

        for received in (True, "1700000000", math.nan, math.inf, -1.0):
            with self.subTest(received=received):
                with self.assertRaises(MarketDataInvalidError):
                    normalize_ndx_quote(
                        ndx_payload(),
                        received_at_epoch=received,  # type: ignore[arg-type]
                    )

    def test_coin_nasdaq_book_parses_fields_zero_through_three_as_raw_top_three(self) -> None:
        participants = [
            {"0": "MM_ONE", "1": 2.5},
            {"0": "MM_TWO", "1": 3.5},
            {"0": "IGNORED", "1": -2.0},
            {"0": "IGNORED_BOOL", "1": True},
        ]
        value = normalize_nasdaq_book(
            book_payload(
                bids=[
                    level(99.0, 99.0),
                    level(102.0, "missing", 2, participants),
                    level(100.0, 7.0, -1),
                    level(101.0, 5.0, 3),
                    level(-1.0, 500.0),
                ],
                asks=[
                    level(106.0, 99.0),
                    level(103.0, None, 2, [{"0": "ASK", "1": 4.25}]),
                    level(105.0, 8.0, 4),
                    level(104.0, 6.0, 3),
                    level(102.0, 0.0),
                ],
            ),
            received_at_epoch=NOW,
        )

        self.assertEqual(value.symbol, "COIN")
        self.assertEqual(value.provider_epoch, 1_700_000_000.0)
        self.assertEqual(value.received_at_epoch, NOW)
        self.assertEqual(
            value.bids,
            (
                BookLevel(102.0, 6.0, 2),
                BookLevel(101.0, 5.0, 3),
                BookLevel(100.0, 7.0, 0),
            ),
        )
        self.assertEqual(
            value.asks,
            (
                BookLevel(103.0, 4.25, 2),
                BookLevel(104.0, 6.0, 3),
                BookLevel(105.0, 8.0, 4),
            ),
        )
        self.assertNotIn("MM_ONE", repr(value))
        self.assertNotIn("MM_TWO", repr(value))
        for forbidden in ("imbalance", "microprice", "signal", "score", "forecast"):
            self.assertFalse(hasattr(value, forbidden), forbidden)

        with self.assertRaises(FrozenInstanceError):
            value.bids = ()  # type: ignore[misc]

    def test_book_rejects_wrong_symbol_time_or_incomplete_depth(self) -> None:
        invalid_payloads = (
            book_payload(symbol="AAPL"),
            book_payload(symbol=True),
            book_payload(provider_ms=True),
            book_payload(provider_ms="1700000000000"),
            book_payload(provider_ms=math.nan),
            book_payload(provider_ms=math.inf),
            book_payload(provider_ms=0.0),
            book_payload(bids=[]),
            book_payload(asks=[]),
            book_payload(bids=[level(101.0, 1.0), level(100.0, 1.0)]),
            book_payload(asks=[level(103.0, 1.0), level(104.0, 1.0)]),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(MarketDataInvalidError):
                    normalize_nasdaq_book(payload, received_at_epoch=NOW)


class SchwabMarketBusTests(unittest.TestCase):
    def test_owner_token_has_one_publication_source(self) -> None:
        sink = RecordingSink()
        bus = MarketBus(sink=sink, clock=lambda: NOW)
        self.assertFalse(hasattr(bus, "_owner_token"))
        with self.assertRaises(TypeError):
            bus.publish_ndx(normalized_ndx())  # type: ignore[call-arg]
        self.assertTrue(
            bus.publish_ndx(normalized_ndx(), owner_token="lease-owner-token")
        )
        self.assertEqual(sink.calls[0][3], "lease-owner-token")

    def test_blocked_ndx_sink_does_not_delay_book_publication(self) -> None:
        ndx_entered = threading.Event()
        release_ndx = threading.Event()
        book_published = threading.Event()

        class IndependentSink(RecordingSink):
            def publish(
                self,
                key: str,
                payload_json: str,
                ttl_seconds: int,
                owner_token: str,
            ) -> bool:
                if key == NDX_KEY:
                    ndx_entered.set()
                    if not release_ndx.wait(2.0):
                        raise AssertionError("test did not release NDX sink")
                result = super().publish(key, payload_json, ttl_seconds, owner_token)
                if key == BOOK_KEY:
                    book_published.set()
                return result

        sink = IndependentSink()
        bus = MarketBus(sink=sink, clock=lambda: NOW)
        ndx_results: list[bool] = []
        book_results: list[bool] = []
        ndx_thread = threading.Thread(
            target=lambda: ndx_results.append(
                bus.publish_ndx(
                    normalized_ndx(),
                    owner_token="lease-owner-token",
                )
            )
        )
        book_thread = threading.Thread(
            target=lambda: book_results.append(
                bus.publish_book(
                    normalized_book(),
                    owner_token="lease-owner-token",
                )
            )
        )
        ndx_thread.start()
        self.assertTrue(ndx_entered.wait(1.0))
        book_thread.start()
        try:
            self.assertTrue(
                book_published.wait(0.5),
                "blocked NDX sink serialized independent book publication",
            )
        finally:
            release_ndx.set()
            ndx_thread.join(2.0)
            book_thread.join(2.0)
        self.assertFalse(ndx_thread.is_alive())
        self.assertFalse(book_thread.is_alive())
        self.assertEqual(ndx_results, [True])
        self.assertEqual(book_results, [True])

    def test_book_update_is_whole_replacement_not_delta_merge(self) -> None:
        sink = RecordingSink()
        bus = MarketBus(sink=sink, clock=lambda: NOW)
        first = normalize_nasdaq_book(
            book_payload(
                provider_ms=1_700_000_001_000,
                bids=[level(price, 1.0) for price in (106, 105, 104, 103, 102, 101)],
                asks=[level(price, 1.0) for price in (107, 108, 109, 110, 111, 112)],
            ),
            received_at_epoch=NOW,
        )
        second = normalize_nasdaq_book(
            book_payload(
                provider_ms=1_700_000_002_000,
                sequence=18,
                bids=[level(price, 2.0) for price in (96, 95, 94)],
                asks=[level(price, 2.0) for price in (97, 98, 99)],
            ),
            received_at_epoch=NOW,
        )

        self.assertTrue(bus.publish_book(first, owner_token="owner"))
        self.assertTrue(bus.publish_book(second, owner_token="owner"))
        latest = json.loads(sink.latest[BOOK_KEY])
        self.assertEqual([item["price"] for item in latest["bids"]], [96.0, 95.0, 94.0])
        self.assertEqual([item["price"] for item in latest["asks"]], [97.0, 98.0, 99.0])
        self.assertNotIn("106.0", sink.latest[BOOK_KEY])
        self.assertNotIn("107.0", sink.latest[BOOK_KEY])

    def test_provider_time_enforces_fresh_order_conflict_and_duplicate_rules(self) -> None:
        event_ms = 1_700_000_000_000

        for publisher, snapshot in (
            ("publish_ndx", normalized_ndx(provider_ms=event_ms)),
            ("publish_book", normalized_book(provider_ms=event_ms)),
        ):
            with self.subTest(kind=publisher, case="fresh"):
                sink = RecordingSink()
                bus = MarketBus(
                    sink=sink,
                    clock=lambda: event_ms / 1000.0 + 1.0,
                )
                self.assertTrue(getattr(bus, publisher)(snapshot, owner_token="owner"))
                self.assertFalse(
                    getattr(bus, publisher)(
                        replace(
                            snapshot,
                            received_at_epoch=snapshot.received_at_epoch + 0.5,
                        ),
                        owner_token="owner",
                    )
                )
                self.assertEqual(len(sink.calls), 1)

                if isinstance(snapshot, NDXSnapshot):
                    conflict = replace(snapshot, price=snapshot.price + 1.0)
                    older = replace(
                        snapshot,
                        provider_epoch=snapshot.provider_epoch - 0.001,
                        trade_time_epoch=snapshot.trade_time_epoch - 0.001,
                    )
                else:
                    conflict = replace(
                        snapshot,
                        bids=(
                            replace(snapshot.bids[0], size=snapshot.bids[0].size + 1.0),
                            *snapshot.bids[1:],
                        ),
                    )
                    older = replace(snapshot, provider_epoch=snapshot.provider_epoch - 0.001)

                with self.assertRaises(MarketDataConflictError):
                    getattr(bus, publisher)(conflict, owner_token="owner")
                with self.assertRaises(MarketDataOrderError):
                    getattr(bus, publisher)(older, owner_token="owner")
                self.assertEqual(len(sink.calls), 1)

            for case, now in (
                ("exact_boundary", event_ms / 1000.0 + MAX_AGE_SECONDS),
                ("future", event_ms / 1000.0 - 0.001),
            ):
                with self.subTest(kind=publisher, case=case):
                    sink = RecordingSink()
                    bus = MarketBus(
                        sink=sink,
                        clock=lambda now=now: now,
                    )
                    with self.assertRaises(MarketDataStaleError):
                        getattr(bus, publisher)(snapshot, owner_token="owner")
                    self.assertEqual(sink.calls, [])

    def test_final_freshness_recheck_blocks_event_that_ages_out_before_publish(self) -> None:
        event_ms = 1_700_000_000_000
        parsed = normalize_ndx_quote(
            ndx_payload(trade_ms=event_ms),
            received_at_epoch=event_ms / 1000.0 + MAX_AGE_SECONDS - 0.001,
        )
        sink = RecordingSink()
        bus = MarketBus(
            sink=sink,
            clock=lambda: event_ms / 1000.0 + MAX_AGE_SECONDS,
        )

        with self.assertRaises(MarketDataStaleError):
            bus.publish_ndx(parsed, owner_token="owner")
        self.assertEqual(sink.calls, [])

    def test_failed_sink_write_does_not_commit_duplicate_state(self) -> None:
        sink = RecordingSink(results=[False, True])
        bus = MarketBus(sink=sink, clock=lambda: NOW)
        value = normalized_ndx()

        self.assertFalse(bus.publish_ndx(value, owner_token="owner"))
        self.assertTrue(bus.publish_ndx(value, owner_token="owner"))
        self.assertEqual(len(sink.calls), 2)

        book_sink = RecordingSink(results=[False, True])
        book_bus = MarketBus(
            sink=book_sink,
            clock=lambda: NOW,
        )
        book = normalized_book()
        self.assertFalse(book_bus.publish_book(book, owner_token="owner"))
        self.assertTrue(book_bus.publish_book(book, owner_token="owner"))
        self.assertEqual(len(book_sink.calls), 2)
        self.assertEqual(json.loads(book_sink.latest[BOOK_KEY])["source_sequence"], 1)

    def test_transient_publication_contract_is_namespaced_bounded_and_secret_free(self) -> None:
        secret = "ACCESS_REFRESH_CLIENT_SECRET_SENTINEL"
        sink = RecordingSink()
        bus = MarketBus(sink=sink, clock=lambda: NOW)

        self.assertEqual(NDX_KEY, "atom:v9:schwab:ndx:snapshot:v1")
        self.assertEqual(BOOK_KEY, "atom:v9:schwab:nasdaq-book:coin:top3:v1")
        self.assertEqual(MAX_AGE_SECONDS, 10.0)
        self.assertTrue(bus.publish_ndx(normalized_ndx(), owner_token=secret))
        self.assertTrue(bus.publish_book(normalized_book(), owner_token=secret))
        self.assertEqual([call[0] for call in sink.calls], [NDX_KEY, BOOK_KEY])
        self.assertTrue(1 <= SNAPSHOT_TTL_SECONDS <= 86_400)

        forbidden_fields = {
            "account",
            "credential",
            "direction",
            "forecast",
            "imbalance",
            "microprice",
            "oauth",
            "order",
            "prediction",
            "refresh_token",
            "score",
            "secret",
            "signal",
            "token",
            "truth",
        }
        for key, payload_json, ttl_seconds, owner_token in sink.calls:
            self.assertTrue(key.startswith("atom:v9:schwab:"))
            self.assertEqual(ttl_seconds, SNAPSHOT_TTL_SECONDS)
            self.assertEqual(owner_token, secret)
            self.assertNotIn(secret, key)
            self.assertNotIn(secret, payload_json)
            payload = json.loads(payload_json)
            self.assertTrue(forbidden_fields.isdisjoint(payload))


if __name__ == "__main__":
    unittest.main()
