"""Inert read-only Schwab market-data normalization and publication boundary.

This module owns no network, broker, database, UI, evidence, or quant-family
behavior.  It accepts only the frozen NDX quote and COIN NASDAQ_BOOK shapes and
publishes short-lived, lease-fenced JSON snapshots through an injected sink.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import math
import threading
from typing import Protocol


NDX_KEY = "atom:v9:schwab:ndx:snapshot:v1"
BOOK_KEY = "atom:v9:schwab:nasdaq-book:coin:top3:v1"
SNAPSHOT_TTL_SECONDS = 15
MAX_TTL_SECONDS = 86_400
MAX_AGE_SECONDS = 10.0


class MarketDataError(ValueError):
    """Base rejection raised by the isolated market-data boundary."""


class MarketDataInvalidError(MarketDataError):
    """The provider payload does not satisfy the frozen input contract."""


class MarketDataStaleError(MarketDataError):
    """The snapshot is future-dated or no longer fresh at publication."""


class MarketDataOrderError(MarketDataError):
    """The snapshot predates the most recently published provider event."""


class MarketDataConflictError(MarketDataError):
    """The same provider time carries different market data."""


@dataclass(frozen=True, slots=True)
class NDXSnapshot:
    """One causally timestamped Schwab ``$NDX`` price, canonicalized to NDX."""

    symbol: str
    price: float
    provider_epoch: float
    received_at_epoch: float
    quote_time_epoch: float | None
    trade_time_epoch: float | None


@dataclass(frozen=True, slots=True)
class BookLevel:
    """One raw displayed price level; no imbalance or other math is derived."""

    price: float
    size: float
    count: int


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    """One whole replacement containing exactly three levels on each side."""

    symbol: str
    provider_epoch: float
    received_at_epoch: float
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    source_sequence: int


class TransientSink(Protocol):
    """Lease-fenced transient publication seam supplied by the worker."""

    def publish(
        self,
        key: str,
        payload_json: str,
        ttl_seconds: int,
        owner_token: str,
    ) -> bool:
        """Atomically validate ``owner_token`` and commit the whole value."""

        ...


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def _positive_number(value: object) -> float | None:
    result = _number(value)
    return result if result is not None and result > 0 else None


def _provider_milliseconds(value: object) -> float | None:
    result = _positive_number(value)
    return result / 1000.0 if result is not None else None


def _received_epoch(value: object) -> float:
    result = _positive_number(value)
    if result is None:
        raise MarketDataInvalidError("received_at_epoch must be a positive finite number")
    return result


def normalize_ndx_quote(
    payload: object, *, received_at_epoch: float,
) -> NDXSnapshot:
    """Normalize the frozen Schwab REST ``$NDX`` quote response.

    Price/timestamp pairs are selected in this causal order: last trade,
    provider mark, then the positive bid/ask midpoint.  Schwab timestamps are
    epoch milliseconds; strings and booleans are never coerced.
    """

    if not isinstance(payload, Mapping):
        raise MarketDataInvalidError("NDX response must be a mapping")
    matches = [
        value
        for key, value in payload.items()
        if isinstance(key, str) and key.upper() == "$NDX"
    ]
    if len(matches) != 1 or not isinstance(matches[0], Mapping):
        raise MarketDataInvalidError("NDX response must contain $NDX")
    instrument = matches[0]
    symbol = instrument.get("symbol", "$NDX")
    if not isinstance(symbol, str) or symbol.upper() != "$NDX":
        raise MarketDataInvalidError("NDX symbol must be $NDX")
    quote = instrument.get("quote")
    if not isinstance(quote, Mapping):
        raise MarketDataInvalidError("NDX quote must be a mapping")

    quote_epoch = _provider_milliseconds(quote.get("quoteTime"))
    trade_epoch = _provider_milliseconds(quote.get("tradeTime"))
    last_price = _positive_number(quote.get("lastPrice"))
    mark = _positive_number(quote.get("mark"))
    bid = _positive_number(quote.get("bidPrice"))
    ask = _positive_number(quote.get("askPrice"))

    price: float | None = None
    provider_epoch: float | None = None
    if last_price is not None and trade_epoch is not None:
        price, provider_epoch = last_price, trade_epoch
    elif mark is not None and quote_epoch is not None:
        price, provider_epoch = mark, quote_epoch
    elif bid is not None and ask is not None and quote_epoch is not None:
        price, provider_epoch = (bid + ask) / 2.0, quote_epoch

    if price is None or provider_epoch is None:
        raise MarketDataInvalidError("NDX quote has no valid causal price")
    return NDXSnapshot(
        symbol="NDX",
        price=price,
        provider_epoch=provider_epoch,
        received_at_epoch=_received_epoch(received_at_epoch),
        quote_time_epoch=quote_epoch,
        trade_time_epoch=trade_epoch,
    )


def _level_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value >= 0 else 0
    if isinstance(value, float) and math.isfinite(value) and value >= 0 and value.is_integer():
        return int(value)
    return 0


def _participant_size(raw: object) -> float | None:
    if not isinstance(raw, Mapping):
        return None
    return _positive_number(raw.get("1"))


def _book_level(raw: object) -> BookLevel | None:
    if not isinstance(raw, Mapping):
        return None
    price = _positive_number(raw.get("0"))
    aggregate = _number(raw.get("1"))
    if aggregate is None:
        participants = raw.get("3")
        rows = participants if isinstance(participants, list) else []
        sizes = tuple(
            size
            for size in (_participant_size(item) for item in rows)
            if size is not None
        )
        aggregate = sum(sizes) if sizes else None
    if price is None or aggregate is None or aggregate <= 0:
        return None
    return BookLevel(price=price, size=aggregate, count=_level_count(raw.get("2")))


def _book_side(raw: object, *, reverse: bool) -> tuple[BookLevel, ...]:
    rows = raw if isinstance(raw, list) else []
    levels = (
        level
        for level in (_book_level(item) for item in rows)
        if level is not None
    )
    ordered = sorted(levels, key=lambda level: level.price, reverse=reverse)
    return tuple(ordered[:3])


def normalize_nasdaq_book(
    payload: object, *, received_at_epoch: float,
) -> BookSnapshot:
    """Normalize one genuine COIN ``NASDAQ_BOOK`` whole-book content row."""

    if not isinstance(payload, Mapping):
        raise MarketDataInvalidError("NASDAQ_BOOK content must be a mapping")
    if payload.get("0") != "COIN":
        raise MarketDataInvalidError("NASDAQ_BOOK symbol must be COIN")
    provider_epoch = _provider_milliseconds(payload.get("1"))
    if provider_epoch is None:
        raise MarketDataInvalidError("NASDAQ_BOOK provider time is required")
    bids = _book_side(payload.get("2"), reverse=True)
    asks = _book_side(payload.get("3"), reverse=False)
    if len(bids) != 3 or len(asks) != 3:
        raise MarketDataInvalidError("NASDAQ_BOOK requires three valid levels per side")
    return BookSnapshot(
        symbol="COIN",
        provider_epoch=provider_epoch,
        received_at_epoch=_received_epoch(received_at_epoch),
        bids=bids,
        asks=asks,
        source_sequence=0,
    )


def _validate_ndx_snapshot(snapshot: NDXSnapshot) -> None:
    if not isinstance(snapshot, NDXSnapshot) or snapshot.symbol != "NDX":
        raise MarketDataInvalidError("invalid NDX snapshot")
    if _positive_number(snapshot.price) is None:
        raise MarketDataInvalidError("invalid NDX price")
    if _positive_number(snapshot.provider_epoch) is None:
        raise MarketDataInvalidError("invalid NDX provider time")
    if _positive_number(snapshot.received_at_epoch) is None:
        raise MarketDataInvalidError("invalid NDX receive time")
    times = (snapshot.quote_time_epoch, snapshot.trade_time_epoch)
    if any(value is not None and _positive_number(value) is None for value in times):
        raise MarketDataInvalidError("invalid NDX quote or trade time")
    if snapshot.provider_epoch not in times:
        raise MarketDataInvalidError("NDX provider time must preserve a quote or trade time")


def _validate_book_snapshot(snapshot: BookSnapshot) -> None:
    if not isinstance(snapshot, BookSnapshot) or snapshot.symbol != "COIN":
        raise MarketDataInvalidError("invalid COIN book snapshot")
    if _positive_number(snapshot.provider_epoch) is None:
        raise MarketDataInvalidError("invalid book provider time")
    if _positive_number(snapshot.received_at_epoch) is None:
        raise MarketDataInvalidError("invalid book receive time")
    if (isinstance(snapshot.source_sequence, bool) or
            not isinstance(snapshot.source_sequence, int) or
            snapshot.source_sequence < 0):
        raise MarketDataInvalidError("invalid book source sequence")
    if len(snapshot.bids) != 3 or len(snapshot.asks) != 3:
        raise MarketDataInvalidError("book must contain exactly three levels per side")
    for level in snapshot.bids + snapshot.asks:
        if (not isinstance(level, BookLevel) or
                _positive_number(level.price) is None or
                _positive_number(level.size) is None or
                isinstance(level.count, bool) or
                not isinstance(level.count, int) or level.count < 0):
            raise MarketDataInvalidError("invalid book level")
    if tuple(level.price for level in snapshot.bids) != tuple(
            sorted((level.price for level in snapshot.bids), reverse=True)):
        raise MarketDataInvalidError("bid levels must be descending")
    if tuple(level.price for level in snapshot.asks) != tuple(
            sorted(level.price for level in snapshot.asks)):
        raise MarketDataInvalidError("ask levels must be ascending")


def _ndx_identity(snapshot: NDXSnapshot) -> tuple[object, ...]:
    return (
        snapshot.symbol,
        snapshot.price,
        snapshot.provider_epoch,
        snapshot.quote_time_epoch,
        snapshot.trade_time_epoch,
    )


def _book_identity(snapshot: BookSnapshot) -> tuple[object, ...]:
    return (
        snapshot.symbol,
        snapshot.provider_epoch,
        snapshot.bids,
        snapshot.asks,
    )


def _ndx_payload(snapshot: NDXSnapshot) -> str:
    return json.dumps(
        {
            "price": snapshot.price,
            "provider_epoch": snapshot.provider_epoch,
            "quote_time_epoch": snapshot.quote_time_epoch,
            "received_at_epoch": snapshot.received_at_epoch,
            "symbol": snapshot.symbol,
            "trade_time_epoch": snapshot.trade_time_epoch,
        },
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _level_payload(level: BookLevel) -> dict[str, float | int]:
    return {"count": level.count, "price": level.price, "size": level.size}


def _book_payload(snapshot: BookSnapshot) -> str:
    return json.dumps(
        {
            "asks": [_level_payload(level) for level in snapshot.asks],
            "bids": [_level_payload(level) for level in snapshot.bids],
            "provider_epoch": snapshot.provider_epoch,
            "received_at_epoch": snapshot.received_at_epoch,
            "source_sequence": snapshot.source_sequence,
            "symbol": snapshot.symbol,
        },
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class MarketBus:
    """Thread-safe, fail-closed transient snapshot publisher."""

    def __init__(
        self,
        sink: TransientSink,
        *,
        clock: Callable[[], float],
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._sink = sink
        self._clock = clock
        self._ndx_lock = threading.Lock()
        self._book_lock = threading.Lock()
        self._ndx_provider_epoch: float | None = None
        self._ndx_identity: tuple[object, ...] | None = None
        self._book_provider_epoch: float | None = None
        self._book_identity: tuple[object, ...] | None = None
        self._book_source_sequence = 0

    def _check_fresh(self, provider_epoch: float) -> None:
        now = _number(self._clock())
        if now is None:
            raise MarketDataInvalidError("clock must return a finite number")
        age = now - provider_epoch
        if age < 0 or age >= MAX_AGE_SECONDS:
            raise MarketDataStaleError("snapshot is outside the freshness window")

    @staticmethod
    def _check_order(
        provider_epoch: float,
        identity: tuple[object, ...],
        previous_epoch: float | None,
        previous_identity: tuple[object, ...] | None,
    ) -> bool:
        if previous_epoch is None:
            return True
        if provider_epoch < previous_epoch:
            raise MarketDataOrderError("provider time moved backwards")
        if provider_epoch == previous_epoch:
            if identity == previous_identity:
                return False
            raise MarketDataConflictError("provider time has conflicting data")
        return True

    def publish_ndx(self, snapshot: NDXSnapshot, *, owner_token: str) -> bool:
        """Publish one fresh NDX snapshot, or return ``False`` for a duplicate/failure."""

        _validate_ndx_snapshot(snapshot)
        if not isinstance(owner_token, str) or not owner_token:
            raise MarketDataInvalidError("owner token is required")
        identity = _ndx_identity(snapshot)
        with self._ndx_lock:
            self._check_fresh(snapshot.provider_epoch)
            if not self._check_order(
                snapshot.provider_epoch,
                identity,
                self._ndx_provider_epoch,
                self._ndx_identity,
            ):
                return False
            committed = self._sink.publish(
                NDX_KEY,
                _ndx_payload(snapshot),
                SNAPSHOT_TTL_SECONDS,
                owner_token,
            )
            if committed is not True:
                return False
            self._ndx_provider_epoch = snapshot.provider_epoch
            self._ndx_identity = identity
            return True

    def publish_book(self, snapshot: BookSnapshot, *, owner_token: str) -> bool:
        """Publish one whole Top-3 replacement with a committed source sequence."""

        _validate_book_snapshot(snapshot)
        if not isinstance(owner_token, str) or not owner_token:
            raise MarketDataInvalidError("owner token is required")
        identity = _book_identity(snapshot)
        with self._book_lock:
            self._check_fresh(snapshot.provider_epoch)
            if not self._check_order(
                snapshot.provider_epoch,
                identity,
                self._book_provider_epoch,
                self._book_identity,
            ):
                return False
            next_sequence = self._book_source_sequence + 1
            publication = BookSnapshot(
                symbol=snapshot.symbol,
                provider_epoch=snapshot.provider_epoch,
                received_at_epoch=snapshot.received_at_epoch,
                bids=snapshot.bids,
                asks=snapshot.asks,
                source_sequence=next_sequence,
            )
            committed = self._sink.publish(
                BOOK_KEY,
                _book_payload(publication),
                SNAPSHOT_TTL_SECONDS,
                owner_token,
            )
            if committed is not True:
                return False
            self._book_provider_epoch = snapshot.provider_epoch
            self._book_identity = identity
            self._book_source_sequence = next_sequence
            return True
