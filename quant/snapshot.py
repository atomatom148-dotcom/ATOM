"""Market snapshot intake. Thin v1: manual/replay/simple feed."""

from __future__ import annotations

import time
from typing import Optional

from .models import Snapshot


def from_price(
    symbol: str,
    last: Optional[float],
    *,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    source: str = "manual",
    fresh: bool = True,
    asof_epoch: Optional[float] = None,
    reason_codes: Optional[list[str]] = None,
) -> Snapshot:
    return Snapshot(
        symbol=symbol,
        asof_epoch=asof_epoch if asof_epoch is not None else time.time(),
        last=last,
        bid=bid,
        ask=ask,
        bar_close=last,
        source=source,
        fresh=fresh,
        reason_codes=list(reason_codes or []),
    )


def stale_example(symbol: str = "COIN") -> Snapshot:
    return from_price(symbol, last=150.0, fresh=False, reason_codes=["STALE_CORE"])


def missing_example(symbol: str = "COIN") -> Snapshot:
    return from_price(symbol, last=None, fresh=True, reason_codes=["MISSING_LAST"])
