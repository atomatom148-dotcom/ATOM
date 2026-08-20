"""Minimal in-memory COIN quote ingestion and Alpaca HTTPS polling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
import threading
import time
from typing import Callable
from urllib.request import Request, urlopen

from .history import MidpointHistory, MidpointObservation
from .quote_history import QuoteHistory, QuoteObservation
from .evidence import EvidenceStore, records_for_results
from .q1_momentum import MomentumResult, calculate_momentum
from .q2_mean_reversion import MeanReversionResult, calculate_mean_reversion
from .q3_volatility import VolatilityResult, calculate_volatility
from .q5_microstructure import MicrostructureResult, calculate_microstructure
from .q6_volume_liquidity import VolumeLiquidityResult, calculate_volume_liquidity


ALPACA_LATEST_QUOTE_URL = "https://data.alpaca.markets/v2/stocks/COIN/quotes/latest"
HISTORY_SECONDS = 3600.0


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    history: MidpointHistory
    quote_history: QuoteHistory
    last_cycle: float | None
    momentum: MomentumResult | None
    mean_reversion: MeanReversionResult | None
    volatility: VolatilityResult | None
    microstructure: MicrostructureResult | None
    volume_liquidity: VolumeLiquidityResult | None


class LiveMarketState:
    """Thread-safe, causal live state holding only Q1-Q3 midpoint history."""

    def __init__(self, *, clock: Callable[[], float] = time.time,
                 evidence_store: EvidenceStore | None = None) -> None:
        self._clock = clock
        self._evidence_store = evidence_store
        self._lock = threading.Lock()
        self._snapshot = LiveSnapshot(
            MidpointHistory(), QuoteHistory(), None, None, None, None, None, None
        )

    def accept_quote(
        self, *, bid: float, ask: float, event_epoch: float,
        bid_size: float | None = None, ask_size: float | None = None,
    ) -> bool:
        """Validate a quote, preserve its event time, and run Q1-Q3."""

        values = (bid, ask, event_epoch)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            return False
        bid, ask, event_epoch = map(float, values)
        if not all(map(math.isfinite, (bid, ask, event_epoch))):
            return False
        if bid <= 0 or ask <= 0 or ask < bid:
            return False

        observation = MidpointObservation(event_epoch, (bid + ask) / 2.0)
        with self._lock:
            old = self._snapshot.history.observations
            if old and event_epoch <= old[-1].event_epoch:
                return False
            observations = old + (observation,)
            boundary = event_epoch - HISTORY_SECONDS
            first_in_window = next(
                (index for index, item in enumerate(observations) if item.event_epoch >= boundary),
                len(observations),
            )
            # Q1 needs the last real observation at or before its 3600s target.
            observations = observations[max(0, first_in_window - 1):]
            history = MidpointHistory(observations)
            quote_history = self._snapshot.quote_history
            if bid_size is not None and ask_size is not None:
                try:
                    quote = QuoteObservation(event_epoch, bid, ask, bid_size, ask_size)
                except ValueError:
                    return False
                quote_observations = quote_history.observations + (quote,)
                quote_observations = tuple(
                    item for item in quote_observations
                    if item.event_epoch >= event_epoch - 300.0
                )
                quote_history = QuoteHistory(quote_observations)
            cycle = self._clock()
            next_snapshot = LiveSnapshot(
                history,
                quote_history,
                cycle,
                calculate_momentum(history, cutoff_epoch=event_epoch),
                calculate_mean_reversion(history, cutoff_epoch=event_epoch),
                calculate_volatility(history, cutoff_epoch=event_epoch),
                calculate_microstructure(quote_history, cutoff_epoch=event_epoch),
                calculate_volume_liquidity(quote_history, cutoff_epoch=event_epoch),
            )
            if self._evidence_store is not None:
                forecasts = records_for_results(
                    results=(next_snapshot.momentum, next_snapshot.mean_reversion),
                    cycle_id=f"COIN:{event_epoch:.9f}", symbol="COIN",
                    cutoff_epoch=event_epoch, cutoff_midpoint=observation.midpoint,
                    created_epoch=cycle,
                )
                self._evidence_store.record_cycle_and_resolve(
                    forecasts, observation_epoch=event_epoch,
                    observation_midpoint=observation.midpoint,
                )
            self._snapshot = next_snapshot
        return True

    def snapshot(self) -> LiveSnapshot:
        with self._lock:
            return self._snapshot


def parse_alpaca_timestamp(value: str) -> float:
    """Convert Alpaca's RFC 3339 event timestamp to Unix seconds."""

    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def poll_alpaca(state: LiveMarketState, *, interval: float = 1.0) -> None:
    """Continuously fetch Alpaca's latest COIN quote using standard-library HTTPS."""

    api_key = os.environ["ALPACA_API_KEY"]
    secret_key = os.environ["ALPACA_SECRET_KEY"]
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    while True:
        try:
            request = Request(ALPACA_LATEST_QUOTE_URL, headers=headers)
            with urlopen(request, timeout=10) as response:
                quote = json.load(response)["quote"]
            state.accept_quote(
                bid=quote["bp"],
                ask=quote["ap"],
                bid_size=quote["bs"],
                ask_size=quote["as"],
                event_epoch=parse_alpaca_timestamp(quote["t"]),
            )
        except Exception as error:  # Keep web-process health independent of market data.
            print(f"Alpaca quote poll failed: {error}", flush=True)
        time.sleep(interval)


def start_alpaca_poller(state: LiveMarketState) -> threading.Thread:
    thread = threading.Thread(target=poll_alpaca, args=(state,), daemon=True)
    thread.start()
    return thread


__all__ = ["LiveMarketState", "LiveSnapshot", "parse_alpaca_timestamp", "poll_alpaca", "start_alpaca_poller"]
