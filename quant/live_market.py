"""Minimal in-memory market ingestion and read-only provider polling."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
import os
import re
import threading
import time
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .history import MidpointHistory, MidpointObservation
from .g2_cross_asset import CrossAssetState, append_bounded, synchronize
from .quote_history import QuoteHistory, QuoteObservation
from .evidence import EvidenceStore, records_for_results, records_for_volatility
from .q1_momentum import MomentumResult, calculate_momentum
from .q2_mean_reversion import MeanReversionResult, calculate_mean_reversion
from .q3_volatility import VolatilityResult, calculate_volatility
from .q4_stat_arb import StatArbResult, calculate_stat_arb
from .q5_microstructure import MicrostructureResult, calculate_microstructure
from .q6_volume_liquidity import VolumeLiquidityResult, calculate_volume_liquidity
from .q7_relative_value import RelativeValueResult, calculate_relative_value
from .q8_cross_asset import CrossAssetResult, calculate_cross_asset
from .q9_factor import FactorResult, calculate_factor
from .q10_options_vol import (OptionObservation, OptionSurface, OptionsVolResult,
                              calculate_options_vol)
from .q11_regime import RegimeResult, calculate_regime
from .q12_event_session import EventSessionResult, calculate_event_session
from .v9_math_core import V9MathCore, V9MathInput, V9QuantFamily
from .v9_telemetry import record_v9_observation
from .v9_v4d_integration import OperationalMetrics
from .evidence_outbox import EvidenceOutbox, QuoteEvidenceWork
from .schwab_market_bus import normalize_ndx_quote


ALPACA_LATEST_QUOTES_URL = "https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=COIN%2CQQQ"
ALPACA_BTC_STREAM_URL_TEMPLATE = (
    "wss://stream.data.alpaca.markets/v1beta3/crypto/{location}"
)
ALPACA_CRYPTO_LOCATIONS = ("us", "us-1", "eu-1")
# The only production service is in Render's Oregon region. Alpaca assigns OR
# to its ``us-1`` crypto location; an explicit environment override remains
# available if the service moves regions.
ALPACA_CRYPTO_LOCATION_DEFAULT = "us-1"
ALPACA_NDX_LATEST_VALUE_URL = (
    "https://data.alpaca.markets/v1beta1/indices/latest/values?index_symbols=NDX"
)
MASSIVE_NDX_SNAPSHOT_URL = (
    "https://api.massive.com/v3/snapshot/indices?ticker=I%3ANDX"
)
SCHWAB_NDX_QUOTE_URL = (
    "https://coin-market-api.onrender.com/schwab/quote/%24NDX"
)
SCHWAB_NDX_ENABLED_ENV = "ATOM_SCHWAB_NDX_ENABLED"
MAX_NDX_AGE_SECONDS = 10.0
HISTORY_SECONDS = 3600.0
MARKET_DISPLAY_FETCH_SECONDS = 0.25
QUANT_CYCLE_SECONDS = 1.0
EVIDENCE_HANDOFF_BUFFER_CAPACITY = 4096
EVIDENCE_HANDOFF_REPLAY_BATCH = 4
BTC_SOURCE_TIMEOUT_SECONDS = 1.0
MAX_BTC_AGE_SECONDS = 5.0
BTC_RECONNECT_SECONDS = 1.0
BTC_RECONNECT_MAX_SECONDS = 30.0
BTC_PUBLISH_INTERVAL_SECONDS = 0.25
BTC_HISTORY_MAX_OBSERVATIONS = int(
    HISTORY_SECONDS / BTC_PUBLISH_INTERVAL_SECONDS) + 1


def v9_math_core_enabled() -> bool:
    """Return whether the opt-in observer is enabled for this cycle."""

    return os.environ.get("V9_MATH_CORE_ENABLED", "false").lower() == "true"


def build_v9_quant_snapshot(snapshot: "LiveSnapshot", *, symbol: str,
                            as_of_epoch: float) -> V9MathInput:
    """Copy already-computed family outputs into V9's immutable contract."""

    results = (
        snapshot.momentum, snapshot.mean_reversion, snapshot.volatility,
        snapshot.stat_arb, snapshot.microstructure, snapshot.volume_liquidity,
        snapshot.relative_value, snapshot.cross_asset, snapshot.factor,
        snapshot.options_vol, snapshot.regime, snapshot.event_session,
    )
    families = tuple(
        V9QuantFamily(
            quant_id=result.quant_id,
            formula_version=result.formula_version,
            horizon_values=tuple(
                getattr(result, "volatility_bps", getattr(result, "forecast_bps", ()))
            ),
        )
        for result in results
        if result is not None
    )
    return V9MathInput(symbol=symbol, as_of_epoch=as_of_epoch, families=families)


def _observe_v9(snapshot: "LiveSnapshot", *, symbol: str, as_of_epoch: float) -> None:
    """Run the optional observer fail-open, without affecting ATOM's path."""

    if not v9_math_core_enabled():
        return
    try:
        value = build_v9_quant_snapshot(
            snapshot, symbol=symbol, as_of_epoch=as_of_epoch,
        )
        state = V9MathCore.evaluate(value)
        record_v9_observation(value, state)
    except Exception:
        # V9 is downstream and observer-only; its failure cannot fail the cycle.
        return


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    history: MidpointHistory
    qqq_history: MidpointHistory
    quote_history: QuoteHistory
    last_cycle: float | None
    momentum: MomentumResult | None
    mean_reversion: MeanReversionResult | None
    volatility: VolatilityResult | None
    stat_arb: StatArbResult | None
    microstructure: MicrostructureResult | None
    volume_liquidity: VolumeLiquidityResult | None
    relative_value: RelativeValueResult | None
    cross_asset: CrossAssetResult | None
    factor: FactorResult | None
    options_vol: OptionsVolResult | None
    regime: RegimeResult | None
    event_session: EventSessionResult | None
    option_observation: OptionObservation | None
    option_surface: OptionSurface | None


@dataclass(frozen=True, slots=True)
class LatestMarketDisplay:
    """Immutable provider-time values used only by the fast presentation path."""

    coin_midpoint: float | None = None
    coin_event_epoch: float | None = None
    qqq_midpoint: float | None = None
    qqq_event_epoch: float | None = None


@dataclass(frozen=True, slots=True)
class LivePublication:
    """One immutable market/V9 publication captured under one lock."""

    snapshot: LiveSnapshot
    v9_output: object | None
    cross_asset_state: CrossAssetState
    market_display: LatestMarketDisplay


class LiveMarketState:
    """Thread-safe causal live state with separate COIN and QQQ histories."""

    def __init__(self, *, clock: Callable[[], float] = time.time,
                 evidence_store: EvidenceStore | None = None,
                 evidence_outbox: EvidenceOutbox | None = None,
                 evidence_acceptance_ready: Callable[[], bool] | None = None,
                 evidence_handoff_anchor: Callable[[], MidpointObservation | None] | None = None,
                 evidence_owner_generation: Callable[[], int | None] | None = None,
                 v9_cycle_handler: Callable[["LiveSnapshot", MidpointObservation | None,
                                             MidpointObservation], object | None] | None = None,
                 metrics: OperationalMetrics | None = None,
                 monotonic_clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._evidence_store = evidence_store
        self._evidence_outbox = evidence_outbox
        self._evidence_acceptance_ready = evidence_acceptance_ready
        self._evidence_handoff_anchor = evidence_handoff_anchor
        self._evidence_owner_generation = evidence_owner_generation
        self._observed_owner_generation: int | None = None
        self._owner_publication_armed = evidence_acceptance_ready is None
        self._evidence_handoff_quotes = deque()
        self._handoff_anchor_pending = False
        self._handoff_observation_ready = threading.Event()
        self._coin_sequence = 0
        # Preserve accepted COIN order through V4 calculation and the one
        # non-blocking outbox handoff.  The state lock remains narrowly scoped
        # and no database work is permitted inside this ingress boundary.
        self._coin_ingress_lock = threading.Lock()
        self._accepting_coin_quotes = True
        self._v9_cycle_handler = v9_cycle_handler
        self.metrics = metrics or OperationalMetrics()
        self.metrics.set_status("btc_source_status", "NOT_STARTED")
        self._monotonic = monotonic_clock
        self._lock = threading.Lock()
        self._btc_history = MidpointHistory()
        self._ndx_history = MidpointHistory()
        self._ndx_available = False
        self._g2_state = synchronize(
            as_of_epoch=0.0, btc=self._btc_history, coin=MidpointHistory(),
            qqq=MidpointHistory(), ndx=self._ndx_history,
        )
        self._snapshot = LiveSnapshot(
            MidpointHistory(), MidpointHistory(), QuoteHistory(), None,
            None, None, None, None, None, None, None, None, None,
            None, None, None, None, None,
        )
        self._market_display = LatestMarketDisplay()
        self._v9_output: object | None = None
        self._v9_error: str | None = None
        self._coin_cycle_pending = False
        self._publication = LivePublication(
            self._snapshot, self._v9_output, self._g2_state, self._market_display,
        )

    def _runtime_ready(self) -> bool:
        if self._evidence_acceptance_ready is None:
            return True
        try:
            ready = self._evidence_acceptance_ready() is True
        except Exception:
            ready = False
        if not ready:
            self._owner_publication_armed = False
        return ready

    def runtime_handoff_ready(self) -> bool:
        """A rolling replacement is ready after ownership or one overlap quote."""

        return self._runtime_ready() or self._handoff_observation_ready.is_set()

    def _can_publish(self) -> bool:
        return self._runtime_ready() and self._owner_publication_armed

    def _outbox_remaining_capacity(self) -> int:
        method = getattr(self._evidence_outbox, "remaining_capacity", None)
        if not callable(method):
            return 1
        value = method()
        if isinstance(value, bool) or not isinstance(value, int):
            return 1
        return max(0, value)

    def update_market_display(
        self, *, coin_midpoint: float | None = None,
        coin_event_epoch: float | None = None, qqq_midpoint: float | None = None,
        qqq_event_epoch: float | None = None,
    ) -> bool:
        """Publish only valid values with provider timestamps newer than current."""

        pairs = ((coin_midpoint, coin_event_epoch), (qqq_midpoint, qqq_event_epoch))
        for midpoint, event_epoch in pairs:
            if (midpoint is None) != (event_epoch is None):
                return False
            if midpoint is not None and (
                    isinstance(midpoint, bool) or isinstance(event_epoch, bool) or
                    not isinstance(midpoint, (int, float)) or
                    not isinstance(event_epoch, (int, float)) or
                    not math.isfinite(float(midpoint)) or float(midpoint) <= 0 or
                    not math.isfinite(float(event_epoch))):
                return False
        changed = False
        with self._lock:
            current = self._market_display
            coin_newer = (coin_event_epoch is not None and
                          (current.coin_event_epoch is None or
                           coin_event_epoch > current.coin_event_epoch))
            qqq_newer = (qqq_event_epoch is not None and
                         (current.qqq_event_epoch is None or
                          qqq_event_epoch > current.qqq_event_epoch))
            if coin_newer or qqq_newer:
                self._market_display = LatestMarketDisplay(
                    float(coin_midpoint) if coin_newer else current.coin_midpoint,
                    float(coin_event_epoch) if coin_newer else current.coin_event_epoch,
                    float(qqq_midpoint) if qqq_newer else current.qqq_midpoint,
                    float(qqq_event_epoch) if qqq_newer else current.qqq_event_epoch,
                )
                if not self._coin_cycle_pending and self._can_publish():
                    self._publication = replace(
                        self._publication, market_display=self._market_display,
                    )
                changed = True
        return changed

    def market_display(self) -> LatestMarketDisplay:
        """Return the current immutable display snapshot."""

        with self._lock:
            return self._publication.market_display

    def accept_qqq_quote(self, *, bid: float, ask: float, event_epoch: float) -> bool:
        """Store one validated QQQ midpoint without inventing or resampling data."""

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
            old = self._snapshot.qqq_history.observations
            if old and event_epoch <= old[-1].event_epoch:
                return False
            observations = old + (observation,)
            boundary = event_epoch - HISTORY_SECONDS
            observations = tuple(item for item in observations if item.event_epoch >= boundary)
            self._snapshot = LiveSnapshot(
                self._snapshot.history, MidpointHistory(observations),
                self._snapshot.quote_history, self._snapshot.last_cycle,
                self._snapshot.momentum, self._snapshot.mean_reversion,
                self._snapshot.volatility, self._snapshot.stat_arb,
                self._snapshot.microstructure, self._snapshot.volume_liquidity,
                self._snapshot.relative_value, self._snapshot.cross_asset,
                self._snapshot.factor,
                self._snapshot.options_vol, self._snapshot.regime,
                self._snapshot.event_session, self._snapshot.option_observation,
                self._snapshot.option_surface,
            )
            self._refresh_g2(event_epoch)
            if not self._coin_cycle_pending and self._can_publish():
                self._publication = replace(
                    self._publication, snapshot=self._snapshot,
                    cross_asset_state=self._g2_state,
                )
        return True

    def accept_g2_price(self, *, asset: str, price: float, event_epoch: float,
                        max_age_seconds: float | None = None) -> bool:
        """Accept a validated BTC or NDX observation without affecting ATOM."""

        values = (price, event_epoch)
        if (asset not in ("BTC", "NDX") or
                any(isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in values)):
            return False
        price, event_epoch = map(float, values)
        if not math.isfinite(price) or price <= 0 or not math.isfinite(event_epoch):
            return False
        if (max_age_seconds is not None and
                (isinstance(max_age_seconds, bool) or
                 not isinstance(max_age_seconds, (int, float)) or
                 not math.isfinite(float(max_age_seconds)) or
                 float(max_age_seconds) <= 0)):
            return False
        if asset == "NDX" and event_epoch > self._clock():
            return False
        with self._lock:
            # The stream validates age before calling us, but this second clock
            # read is the atomic acceptance boundary. A quote that becomes
            # stale while the poller is blocked never enters BTC history.
            if asset == "BTC" and max_age_seconds is not None:
                age = self._clock() - event_epoch
                if age < 0 or age >= float(max_age_seconds):
                    return False
            history = self._btc_history if asset == "BTC" else self._ndx_history
            latest = history.latest
            if latest is not None and event_epoch == latest.event_epoch:
                if price != latest.midpoint:
                    return False
                if asset == "NDX" and not self._ndx_available:
                    self._ndx_available = True
                    self._refresh_g2(event_epoch)
                    published_g2 = (
                        self._with_current_ndx(self._publication.cross_asset_state)
                        if self._coin_cycle_pending else self._g2_state
                    )
                    self._publication = replace(
                        self._publication, cross_asset_state=published_g2,
                    )
                return True
            try:
                updated = append_bounded(history, MidpointObservation(event_epoch, price))
            except ValueError:
                return False
            if asset == "BTC":
                if len(updated.observations) > BTC_HISTORY_MAX_OBSERVATIONS:
                    updated = MidpointHistory(
                        updated.observations[-BTC_HISTORY_MAX_OBSERVATIONS:])
                self._btc_history = updated
            else:
                self._ndx_history = updated
                self._ndx_available = True
            self._refresh_g2(event_epoch)
            # BTC and NDX are independent display inputs.  Keep them visible
            # while a replacement process waits for the evidence-writer lock;
            # ownership gates COIN/evidence publication, not benchmark data.
            if asset == "NDX":
                published_g2 = (
                    self._with_current_ndx(self._publication.cross_asset_state)
                    if self._coin_cycle_pending else self._g2_state
                )
                self._publication = replace(
                    self._publication, cross_asset_state=published_g2,
                )
            elif not self._coin_cycle_pending:
                self._publication = replace(
                    self._publication, cross_asset_state=self._g2_state,
                )
        return True

    def _with_current_ndx(self, base: CrossAssetState) -> CrossAssetState:
        latest = self._ndx_history.latest
        cutoff = max(
            base.as_of_epoch,
            latest.event_epoch if latest is not None else base.as_of_epoch,
        )
        delta = cutoff - base.as_of_epoch
        ndx = synchronize(
            as_of_epoch=cutoff,
            btc=MidpointHistory(), coin=MidpointHistory(),
            qqq=MidpointHistory(), ndx=self._ndx_history,
        )
        return replace(
            base,
            as_of_epoch=cutoff,
            btc_age_seconds=(
                None if base.btc_age_seconds is None
                else base.btc_age_seconds + delta
            ),
            coin_age_seconds=(
                None if base.coin_age_seconds is None
                else base.coin_age_seconds + delta
            ),
            qqq_age_seconds=(
                None if base.qqq_age_seconds is None
                else base.qqq_age_seconds + delta
            ),
            ndx_price=ndx.ndx_price if self._ndx_available else None,
            ndx_age_seconds=ndx.ndx_age_seconds if self._ndx_available else None,
            ndx_return_bps=ndx.ndx_return_bps if self._ndx_available else (None,) * 6,
        )

    def expire_ndx_if_stale(
        self, *, now_epoch: float,
        max_age_seconds: float = MAX_NDX_AGE_SECONDS,
    ) -> bool:
        """Publish honest NDX unavailability after its freshness window closes."""

        values = (now_epoch, max_age_seconds)
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        ) or float(max_age_seconds) <= 0:
            return False
        with self._lock:
            latest = self._ndx_history.latest
            if latest is not None:
                age = float(now_epoch) - latest.event_epoch
                if 0 <= age < float(max_age_seconds):
                    return False
            if not self._ndx_available and self._g2_state.ndx_price is None:
                return False
            self._ndx_available = False
            self._refresh_g2(self._g2_state.as_of_epoch)
            self._publication = replace(
                self._publication,
                cross_asset_state=self._with_current_ndx(
                    self._publication.cross_asset_state,
                ),
            )
        return True

    def btc_latest_observation(self) -> MidpointObservation | None:
        """Return the latest bounded BTC point for stream restart deduplication."""

        with self._lock:
            return self._btc_history.latest

    def _refresh_g2(self, event_epoch: float) -> None:
        cutoff = max(self._g2_state.as_of_epoch, event_epoch)
        self._g2_state = synchronize(
            as_of_epoch=cutoff, btc=self._btc_history,
            coin=self._snapshot.history, qqq=self._snapshot.qqq_history,
            ndx=self._ndx_history,
        )
        if not self._ndx_available:
            self._g2_state = replace(
                self._g2_state,
                ndx_price=None,
                ndx_age_seconds=None,
                ndx_return_bps=(None,) * 6,
            )

    def cross_asset_state(self) -> CrossAssetState:
        """Return the latest already-maintained immutable G2-A state."""

        if schwab_ndx_enabled():
            self.expire_ndx_if_stale(now_epoch=self._clock())
        with self._lock:
            return self._publication.cross_asset_state

    def accept_quote(
        self, *, bid: float, ask: float, event_epoch: float,
        bid_size: float | None = None, ask_size: float | None = None,
    ) -> bool:
        """Serialize one COIN ingress event through its outbox handoff."""

        with self._coin_ingress_lock:
            if not self._accepting_coin_quotes:
                return False
            ready = self._runtime_ready()
            owner_generation = (
                self._evidence_owner_generation()
                if ready and self._evidence_owner_generation is not None else None)
            owner_generation_changed = (
                owner_generation is not None and
                self._observed_owner_generation is not None and
                owner_generation != self._observed_owner_generation)
            if owner_generation is not None:
                self._observed_owner_generation = owner_generation
            if ready and self._evidence_handoff_anchor is not None:
                durable_anchor = self._evidence_handoff_anchor()
                local_latest = self._snapshot.history.latest
                if (durable_anchor is not None and
                        (owner_generation_changed or local_latest is None or
                         durable_anchor.event_epoch > local_latest.event_epoch or
                         (durable_anchor.event_epoch == local_latest.event_epoch and
                          durable_anchor.midpoint != local_latest.midpoint))):
                    # Ownership may have been lost and reacquired between two
                    # provider callbacks.  Compare the cached durable owner
                    # anchor on every owned ingress so that an unobserved loss
                    # interval cannot emit a bracket from stale local history.
                    while (self._evidence_handoff_quotes and
                           self._evidence_handoff_quotes[0][2] <=
                           durable_anchor.event_epoch):
                        self._evidence_handoff_quotes.popleft()
                    self._seed_midpoint_anchor(durable_anchor)
                    self._handoff_anchor_pending = False
                    if local_latest is not None:
                        self.metrics.increment("evidence_handoff.owner_rebase")
            remaining_capacity = self._outbox_remaining_capacity()
            if (not ready or self._evidence_handoff_quotes or
                    remaining_capacity < 1):
                first_waiting_quote = not self._evidence_handoff_quotes
                if not self._buffer_handoff_quote(
                        bid=bid, ask=ask, event_epoch=event_epoch,
                        bid_size=bid_size, ask_size=ask_size):
                    return False
                if not ready:
                    if first_waiting_quote:
                        # Every loss of ownership starts a new durable handoff,
                        # even when this process has an older local history.
                        self._handoff_anchor_pending = True
                    self.metrics.set_status(
                        "evidence_ingress_status", "BUFFERING_FOR_OWNER")
                    return True
                if self._handoff_anchor_pending:
                    durable_anchor = (self._evidence_handoff_anchor()
                                      if self._evidence_handoff_anchor is not None
                                      else None)
                    if durable_anchor is not None:
                        while (self._evidence_handoff_quotes and
                               self._evidence_handoff_quotes[0][2] <=
                               durable_anchor.event_epoch):
                            self._evidence_handoff_quotes.popleft()
                        self._seed_midpoint_anchor(durable_anchor)
                    elif self._evidence_handoff_quotes:
                        anchor = self._evidence_handoff_quotes.popleft()
                        self._seed_handoff_anchor(
                            bid=anchor[0], ask=anchor[1], event_epoch=anchor[2],
                            bid_size=anchor[3], ask_size=anchor[4])
                    self._handoff_anchor_pending = False
                replay_count = min(
                    EVIDENCE_HANDOFF_REPLAY_BATCH,
                    self._outbox_remaining_capacity(),
                    len(self._evidence_handoff_quotes),
                )
                for _index in range(replay_count):
                    values = self._evidence_handoff_quotes.popleft()
                    if not self._accept_quote_serialized(
                            bid=values[0], ask=values[1], event_epoch=values[2],
                            bid_size=values[3], ask_size=values[4]):
                        self.metrics.increment(
                            "evidence_handoff.replay_failure")
                        self.metrics.set_status(
                            "evidence_ingress_status", "REPLAY_FAILED")
                        return False
                self.metrics.set_status(
                    "evidence_ingress_status",
                    "REPLAYING" if self._evidence_handoff_quotes else "ACTIVE",
                )
                return True
            if (self._evidence_acceptance_ready is not None and
                    self._snapshot.history.latest is None):
                durable_anchor = (self._evidence_handoff_anchor()
                                  if self._evidence_handoff_anchor is not None
                                  else None)
                if durable_anchor is not None:
                    self._seed_midpoint_anchor(durable_anchor)
                    if event_epoch > durable_anchor.event_epoch:
                        return self._accept_quote_serialized(
                            bid=bid, ask=ask, event_epoch=event_epoch,
                            bid_size=bid_size, ask_size=ask_size)
                else:
                    self._seed_handoff_anchor(
                        bid=bid, ask=ask, event_epoch=event_epoch,
                        bid_size=bid_size, ask_size=ask_size)
                self.metrics.set_status("evidence_ingress_status", "ACTIVE")
                return True
            self.metrics.set_status("evidence_ingress_status", "ACTIVE")
            return self._accept_quote_serialized(
                bid=bid, ask=ask, event_epoch=event_epoch,
                bid_size=bid_size, ask_size=ask_size,
            )

    def _buffer_handoff_quote(
        self, *, bid: float, ask: float, event_epoch: float,
        bid_size: float | None, ask_size: float | None,
    ) -> bool:
        values = (bid, ask, event_epoch)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               for value in values):
            return False
        bid, ask, event_epoch = map(float, values)
        if (not all(map(math.isfinite, (bid, ask, event_epoch))) or
                bid <= 0 or ask <= 0 or ask < bid):
            return False
        if (bid_size is None) != (ask_size is None):
            return False
        if bid_size is not None:
            try:
                QuoteObservation(event_epoch, bid, ask, bid_size, ask_size)
            except (TypeError, ValueError):
                return False
        if self._evidence_handoff_quotes:
            prior = self._evidence_handoff_quotes[-1]
            if event_epoch == prior[2]:
                if (bid, ask, bid_size, ask_size) == (
                        prior[0], prior[1], prior[3], prior[4]):
                    return True
                self.metrics.increment("evidence_handoff.timestamp_conflict")
                return False
            if event_epoch < prior[2]:
                return False
        else:
            latest = self._snapshot.history.latest
            if latest is not None and event_epoch <= latest.event_epoch:
                return False
        if len(self._evidence_handoff_quotes) >= EVIDENCE_HANDOFF_BUFFER_CAPACITY:
            self.metrics.increment("evidence_handoff.buffer_full")
            self.metrics.set_status("evidence_ingress_status", "BUFFER_FULL")
            return False
        self._evidence_handoff_quotes.append(
            (bid, ask, event_epoch, bid_size, ask_size))
        self._handoff_observation_ready.set()
        return True

    def _seed_handoff_anchor(
        self, *, bid: float, ask: float, event_epoch: float,
        bid_size: float | None, ask_size: float | None,
    ) -> None:
        """Seed one real provider observation without creating a duplicate cycle."""

        observation = MidpointObservation(
            float(event_epoch), (float(bid) + float(ask)) / 2.0)
        with self._lock:
            current = self._snapshot
            if current.history.latest is not None:
                return
            quote_history = current.quote_history
            if bid_size is not None and ask_size is not None:
                quote_history = QuoteHistory((QuoteObservation(
                    float(event_epoch), float(bid), float(ask),
                    float(bid_size), float(ask_size)),))
            self._snapshot = LiveSnapshot(
                MidpointHistory((observation,)), current.qqq_history,
                quote_history, current.last_cycle, current.momentum,
                current.mean_reversion, current.volatility, current.stat_arb,
                current.microstructure, current.volume_liquidity,
                current.relative_value, current.cross_asset, current.factor,
                current.options_vol, current.regime, current.event_session,
                current.option_observation, current.option_surface,
            )
            self._refresh_g2(float(event_epoch))

    def _seed_midpoint_anchor(self, observation: MidpointObservation) -> None:
        with self._lock:
            current = self._snapshot
            causal_history = tuple(
                item for item in current.history.observations
                if (item.event_epoch < observation.event_epoch and
                    item.event_epoch >= observation.event_epoch - HISTORY_SECONDS)
            )
            history = MidpointHistory(causal_history + (observation,))
            quote_history = QuoteHistory(tuple(
                item for item in current.quote_history.observations
                if (item.event_epoch < observation.event_epoch and
                    item.event_epoch >= observation.event_epoch - 300.0)
            ))
            # The durable anchor, not this process's pre-loss cache, is now the
            # only causal predecessor. Derived family output is rebuilt by the
            # first strictly newer provider quote.
            self._snapshot = replace(
                current, history=history, quote_history=quote_history,
                last_cycle=None, momentum=None, mean_reversion=None,
                volatility=None, stat_arb=None, microstructure=None,
                volume_liquidity=None, relative_value=None, cross_asset=None,
                factor=None, options_vol=None, regime=None, event_session=None,
            )
            self._refresh_g2(observation.event_epoch)

    def stop_accepting_quotes(self) -> None:
        """Close COIN ingress after any in-flight outbox handoff completes."""

        with self._coin_ingress_lock:
            if self._evidence_handoff_quotes and not self._runtime_ready():
                # This process never became the authoritative writer.  Its
                # overlap observations remain useful only to a process that
                # actually acquires the durable session owner.
                self.metrics.increment(
                    "evidence_handoff.non_owner_shutdown")
                self._evidence_handoff_quotes.clear()
            if self._handoff_anchor_pending and self._runtime_ready():
                durable_anchor = (self._evidence_handoff_anchor()
                                  if self._evidence_handoff_anchor is not None
                                  else None)
                if durable_anchor is not None:
                    while (self._evidence_handoff_quotes and
                           self._evidence_handoff_quotes[0][2] <=
                           durable_anchor.event_epoch):
                        self._evidence_handoff_quotes.popleft()
                    self._seed_midpoint_anchor(durable_anchor)
                elif self._evidence_handoff_quotes:
                    anchor = self._evidence_handoff_quotes.popleft()
                    self._seed_handoff_anchor(
                        bid=anchor[0], ask=anchor[1], event_epoch=anchor[2],
                        bid_size=anchor[3], ask_size=anchor[4])
                self._handoff_anchor_pending = False
            while self._evidence_handoff_quotes:
                capacity = self._outbox_remaining_capacity()
                if capacity < 1:
                    time.sleep(.01)
                    continue
                values = self._evidence_handoff_quotes.popleft()
                if not self._accept_quote_serialized(
                        bid=values[0], ask=values[1], event_epoch=values[2],
                        bid_size=values[3], ask_size=values[4]):
                    raise RuntimeError("evidence handoff drain failed")
            self._accepting_coin_quotes = False
            self.metrics.set_status("evidence_ingress_status", "CLOSED")

    def _accept_quote_serialized(
        self, *, bid: float, ask: float, event_epoch: float,
        bid_size: float | None = None, ask_size: float | None = None,
    ) -> bool:
        """Validate a quote, preserve its event time, and run Q1-Q3."""

        if not self._accepting_coin_quotes:
            return False
        values = (bid, ask, event_epoch)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            return False
        bid, ask, event_epoch = map(float, values)
        if not all(map(math.isfinite, (bid, ask, event_epoch))):
            return False
        if bid <= 0 or ask <= 0 or ask < bid:
            return False

        update_started = self._monotonic()
        observation = MidpointObservation(event_epoch, (bid + ask) / 2.0)
        previous_observation: MidpointObservation | None = None
        with self._lock:
            old = self._snapshot.history.observations
            if old and event_epoch <= old[-1].event_epoch:
                return False
            previous_observation = old[-1] if old else None
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
            def family(name: str, calculation: Callable[[], object]) -> object | None:
                started = self._monotonic()
                try:
                    result = calculation()
                except Exception:
                    result = None
                    self.metrics.increment(f"family.{name}.failure")
                elapsed = (self._monotonic() - started) * 1000
                self.metrics.observe(f"family.{name}.runtime_ms", elapsed)
                return result

            next_snapshot = LiveSnapshot(
                history,
                self._snapshot.qqq_history,
                quote_history,
                cycle,
                family("q1_momentum", lambda: calculate_momentum(history, cutoff_epoch=event_epoch)),
                family("q2_mean_reversion", lambda: calculate_mean_reversion(history, cutoff_epoch=event_epoch)),
                family("q3_volatility", lambda: calculate_volatility(history, cutoff_epoch=event_epoch)),
                family("q4_stat_arb", lambda: calculate_stat_arb(history, self._snapshot.qqq_history, cutoff_epoch=event_epoch)),
                family("q5_microstructure", lambda: calculate_microstructure(quote_history, cutoff_epoch=event_epoch)),
                family("q6_volume_liquidity", lambda: calculate_volume_liquidity(quote_history, cutoff_epoch=event_epoch)),
                family("q7_relative_value", lambda: calculate_relative_value(history, self._snapshot.qqq_history, cutoff_epoch=event_epoch)),
                family("q8_cross_asset", lambda: calculate_cross_asset(history, self._snapshot.qqq_history, cutoff_epoch=event_epoch)),
                family("q9_factor", lambda: calculate_factor(history, self._snapshot.qqq_history, cutoff_epoch=event_epoch)),
                family("q10_options_vol", lambda: calculate_options_vol(self._snapshot.option_surface, cutoff_epoch=event_epoch)),
                family("q11_regime", lambda: calculate_regime(history, cutoff_epoch=event_epoch)),
                family("q12_event_session", lambda: calculate_event_session(history, cutoff_epoch=event_epoch)),
                self._snapshot.option_observation,
                self._snapshot.option_surface,
            )
            _observe_v9(next_snapshot, symbol="COIN", as_of_epoch=event_epoch)
            forecasts = records_for_results(
                    results=(
                        next_snapshot.momentum,
                        next_snapshot.mean_reversion,
                        next_snapshot.stat_arb,
                        next_snapshot.microstructure,
                        next_snapshot.volume_liquidity,
                        next_snapshot.relative_value,
                        next_snapshot.cross_asset,
                        next_snapshot.factor,
                        next_snapshot.options_vol,
                        next_snapshot.regime,
                        next_snapshot.event_session,
                    ),
                    cycle_id=f"COIN:{event_epoch:.9f}", symbol="COIN",
                    cutoff_epoch=event_epoch, cutoff_midpoint=observation.midpoint,
                    created_epoch=cycle,
                )
            volatility_forecasts = records_for_volatility(
                    result=next_snapshot.volatility,
                    cycle_id=f"COIN:{event_epoch:.9f}", symbol="COIN",
                    cutoff_epoch=event_epoch, cutoff_midpoint=observation.midpoint,
                    created_epoch=cycle,
                )
            self._snapshot = next_snapshot
            self._refresh_g2(event_epoch)
            self._coin_sequence += 1
            sequence = self._coin_sequence
            self._coin_cycle_pending = True
            cycle_g2_state = self._g2_state
            cycle_market_display = self._market_display
        output = None
        v9_error = None
        if self._v9_cycle_handler is not None:
            try:
                output = self._v9_cycle_handler(
                    next_snapshot, previous_observation, observation,
                )
            except Exception as error:
                v9_error = type(error).__name__
        delivery_status = "NOT_CONFIGURED"
        if self._evidence_outbox is not None:
            try:
                v4 = tuple(result.forecast for result in output.persistence) if output else ()
                delivered = self._evidence_outbox.put_nowait(QuoteEvidenceWork(
                    sequence=sequence,
                    cycle_id=f"COIN:{event_epoch:.9f}",
                    previous_observation=previous_observation,
                    current_observation=observation,
                    received_at=datetime.fromtimestamp(cycle, timezone.utc),
                    directional=tuple(forecasts), q3=tuple(volatility_forecasts), v4=v4,
                    state_cohort_id=getattr(output, "state_cohort_id", None),
                    v4d_output=output,
                ))
                delivery_status = "ENQUEUED" if delivered else "DROPPED"
            except Exception as error:
                delivery_status = "FAILED"
                v9_error = v9_error or type(error).__name__
                self.metrics.increment("evidence_outbox.failure")
        if output is not None:
            try:
                if hasattr(output, "evidence_delivery_status"):
                    output = replace(output, evidence_delivery_status=delivery_status)
            except Exception as error:
                output = None
                v9_error = v9_error or type(error).__name__
        with self._lock:
            self._v9_output = output
            self._v9_error = v9_error
            self._coin_cycle_pending = False
            if self._runtime_ready():
                self._owner_publication_armed = True
                cycle_g2_state = self._with_current_ndx(cycle_g2_state)
                self._publication = LivePublication(
                    next_snapshot, output, cycle_g2_state, cycle_market_display,
                )
        self.metrics.observe("coin_market_state_update_latency_ms",
                             (self._monotonic() - update_started) * 1000)
        return True

    def snapshot(self) -> LiveSnapshot:
        with self._lock:
            return self._publication.snapshot

    def publication(self) -> LivePublication:
        """Return market, V9, cross-asset, and display state from one commit."""

        if schwab_ndx_enabled():
            self.expire_ndx_if_stale(now_epoch=self._clock())
        with self._lock:
            return self._publication

    def input_snapshot(self) -> LiveSnapshot:
        """Return the latest accepted inputs, including a cycle still in flight."""

        with self._lock:
            return self._snapshot

    def v9_output(self) -> object | None:
        """Return the latest complete immutable V1→V4D cycle, if available."""

        with self._lock:
            return self._publication.v9_output

    def v9_error(self) -> str | None:
        with self._lock:
            return self._v9_error

    def accept_option_observation(self, observation: OptionObservation) -> None:
        """Atomically publish a validated option observation without running Q10."""

        if not isinstance(observation, OptionObservation):
            raise TypeError("observation must be an OptionObservation")
        with self._lock:
            current = self._snapshot
            self._snapshot = LiveSnapshot(
                current.history, current.qqq_history, current.quote_history,
                current.last_cycle, current.momentum, current.mean_reversion,
                current.volatility, current.stat_arb, current.microstructure,
                current.volume_liquidity, current.relative_value,
                current.cross_asset, current.factor, current.options_vol,
                current.regime, current.event_session, observation,
                current.option_surface,
            )
            if not self._coin_cycle_pending and self._can_publish():
                self._publication = replace(
                    self._publication, snapshot=self._snapshot,
                )

    def accept_option_surface(self, surface: OptionSurface, *, midpoint: float) -> None:
        """Atomically publish a complete surface and its dashboard anchor call."""

        if not isinstance(surface, OptionSurface):
            raise TypeError("surface must be an OptionSurface")
        representative = min(
            surface.calls,
            key=lambda item: (abs(item.strike - midpoint), item.strike, item.contract_symbol),
            default=None,
        )
        with self._lock:
            current = self._snapshot
            self._snapshot = LiveSnapshot(
                current.history, current.qqq_history, current.quote_history,
                current.last_cycle, current.momentum, current.mean_reversion,
                current.volatility, current.stat_arb, current.microstructure,
                current.volume_liquidity, current.relative_value,
                current.cross_asset, current.factor, current.options_vol,
                current.regime, current.event_session, representative, surface,
            )
            if not self._coin_cycle_pending and self._can_publish():
                self._publication = replace(
                    self._publication, snapshot=self._snapshot,
                )


_ALPACA_RFC3339 = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[Tt]"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?"
    r"(?P<zone>[Zz]|[+-]\d{2}:\d{2})$"
)
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_alpaca_timestamp_identity(value: str) -> tuple[float, int]:
    """Return a float epoch plus the exact RFC3339 nanosecond identity."""

    if not isinstance(value, str):
        raise TypeError("Alpaca timestamp must be a string")
    matched = _ALPACA_RFC3339.fullmatch(value)
    if matched is None:
        raise ValueError("Alpaca timestamp must be RFC3339 with a timezone")
    zone = matched.group("zone")
    if zone in {"Z", "z"}:
        zone = "+00:00"
    parsed = datetime.fromisoformat(
        f"{matched.group('date')}T{matched.group('time')}{zone}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Alpaca timestamp must include a timezone")
    delta = parsed.astimezone(timezone.utc) - _UNIX_EPOCH
    whole_seconds = delta.days * 86_400 + delta.seconds
    fraction = (matched.group("fraction") or "").ljust(9, "0")
    event_nanoseconds = whole_seconds * 1_000_000_000 + int(fraction or "0")
    event_epoch = event_nanoseconds / 1_000_000_000.0
    if not math.isfinite(event_epoch):
        raise ValueError("Alpaca timestamp is not finite")
    return event_epoch, event_nanoseconds


def parse_alpaca_timestamp(value: str) -> float:
    """Convert Alpaca's RFC 3339 event timestamp to Unix seconds."""

    return _parse_alpaca_timestamp_identity(value)[0]


def parse_alpaca_ndx_value(payload: object) -> tuple[float, float]:
    """Return Alpaca's latest NDX index value and provider timestamp."""

    if not isinstance(payload, dict):
        raise TypeError("NDX latest-value response must be an object")
    values = payload.get("values")
    if not isinstance(values, dict):
        raise ValueError("NDX latest-value response is missing values")
    item = values.get("NDX")
    if not isinstance(item, dict):
        raise ValueError("NDX latest-value response is missing NDX")
    value = item.get("v")
    timestamp = item.get("t")
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not isinstance(timestamp, str)):
        raise ValueError("NDX latest-value response has invalid v or t")
    value = float(value)
    event_epoch = parse_alpaca_timestamp(timestamp)
    if not math.isfinite(value) or value <= 0 or not math.isfinite(event_epoch):
        raise ValueError("NDX latest-value response has invalid v or t")
    return value, event_epoch


def parse_massive_ndx_snapshot(payload: object) -> tuple[float, float]:
    """Return Massive's real-time NDX value and provider timestamp."""

    if not isinstance(payload, dict):
        raise TypeError("Massive NDX snapshot response must be an object")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Massive NDX snapshot response is missing results")
    item = next(
        (result for result in results
         if isinstance(result, dict) and result.get("ticker") == "I:NDX"),
        None,
    )
    if item is None:
        raise ValueError("Massive NDX snapshot response is missing I:NDX")
    if item.get("timeframe") != "REAL-TIME":
        raise ValueError("Massive NDX snapshot is not real-time")
    value = item.get("value")
    last_updated = item.get("last_updated")
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            isinstance(last_updated, bool) or
            not isinstance(last_updated, (int, float))):
        raise ValueError("Massive NDX snapshot has invalid value or last_updated")
    value = float(value)
    event_epoch = float(last_updated) / 1_000_000_000.0
    if not math.isfinite(value) or value <= 0 or not math.isfinite(event_epoch):
        raise ValueError("Massive NDX snapshot has invalid value or last_updated")
    return value, event_epoch


def parse_schwab_ndx_quote(
    payload: object, *, received_at_epoch: float,
) -> tuple[float, float]:
    """Validate Coin's read-only Schwab wrapper and preserve provider time."""

    if not isinstance(payload, dict):
        raise TypeError("Schwab NDX response must be an object")
    if payload.get("ok") is not True or payload.get("mode") != "READ ONLY":
        raise ValueError("Schwab NDX response is not an authorized read-only quote")
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or symbol.upper() not in {"NDX", "$NDX"}:
        raise ValueError("Schwab NDX response has the wrong symbol")
    snapshot = normalize_ndx_quote(
        payload.get("data"), received_at_epoch=received_at_epoch,
    )
    return snapshot.price, snapshot.provider_epoch


def poll_alpaca(
    state: LiveMarketState, *, interval: float = MARKET_DISPLAY_FETCH_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    stop_event: threading.Event | None = None,
) -> None:
    """Continuously fetch latest COIN and QQQ quotes in one Alpaca request."""

    api_key = os.environ["ALPACA_API_KEY"]
    secret_key = os.environ["ALPACA_SECRET_KEY"]
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    last_quant_cycle: float | None = None
    while stop_event is None or not stop_event.is_set():
        try:
            request = Request(ALPACA_LATEST_QUOTES_URL, headers=headers)
            with urlopen(request, timeout=10) as response:
                quotes = json.load(response)["quotes"]
            qqq = quotes.get("QQQ")
            qqq_values = None
            if qqq is not None:
                try:
                    qqq_values = (float(qqq["bp"]), float(qqq["ap"]),
                                  parse_alpaca_timestamp(qqq["t"]))
                except (KeyError, TypeError, ValueError) as error:
                    print(f"Alpaca QQQ quote rejected: {error}", flush=True)
            quote = quotes["COIN"]
            coin_values = (float(quote["bp"]), float(quote["ap"]),
                           parse_alpaca_timestamp(quote["t"]))
            state.update_market_display(
                coin_midpoint=(coin_values[0] + coin_values[1]) / 2.0,
                coin_event_epoch=coin_values[2],
                qqq_midpoint=((qqq_values[0] + qqq_values[1]) / 2.0
                              if qqq_values else None),
                qqq_event_epoch=qqq_values[2] if qqq_values else None,
            )
            cycle_time = monotonic()
            if (last_quant_cycle is None or
                    cycle_time - last_quant_cycle >= QUANT_CYCLE_SECONDS):
                last_quant_cycle = cycle_time
                if qqq_values:
                    state.accept_qqq_quote(
                        bid=qqq_values[0], ask=qqq_values[1],
                        event_epoch=qqq_values[2],
                    )
                state.accept_quote(
                    bid=coin_values[0], ask=coin_values[1],
                    bid_size=quote["bs"], ask_size=quote["as"],
                    event_epoch=coin_values[2],
                )
        except Exception as error:  # Keep web-process health independent of market data.
            print(f"Alpaca quote poll failed: {error}", flush=True)
        if stop_event is None:
            time.sleep(interval)
        elif stop_event.wait(interval):
            return


def alpaca_btc_stream_url() -> str:
    """Return the one allowlisted crypto venue configured for this runtime."""

    location = os.environ.get(
        "ALPACA_CRYPTO_LOCATION", ALPACA_CRYPTO_LOCATION_DEFAULT).strip()
    if location not in ALPACA_CRYPTO_LOCATIONS:
        raise ValueError("ALPACA_CRYPTO_LOCATION is not allowlisted")
    return ALPACA_BTC_STREAM_URL_TEMPLATE.format(location=location)


def _websocket_timeout(error: Exception) -> bool:
    return any(base.__name__ in {"TimeoutError", "WebSocketTimeoutException"}
               for base in type(error).__mro__)


def _stream_messages(raw) -> tuple[dict[str, object], ...]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("Alpaca stream payload must be an array of objects")
    return tuple(payload)


class _AlpacaConnectionLimit(RuntimeError):
    pass


class _AlpacaControlFailure(RuntimeError):
    def __init__(self, message: str, *, reason: str = "CONTROL"):
        super().__init__(message)
        self.reason = reason


class _AlpacaWatchdogExpired(RuntimeError):
    pass


def poll_alpaca_g2(
    state: LiveMarketState, *, interval: float = BTC_RECONNECT_SECONDS,
    timeout: float = BTC_SOURCE_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.time,
    monotonic: Callable[[], float] = time.perf_counter,
    stop_event: threading.Event | None = None,
    websocket_factory: Callable | None = None,
) -> None:
    """Maintain BTC from provider-timed Alpaca quotes on its streaming path."""

    last_status: str | None = None

    def publish_status(status: str) -> None:
        nonlocal last_status
        if status != last_status:
            state.metrics.set_status("btc_source_status", status)
            last_status = status

    def wait_before_reconnect(seconds: float) -> bool:
        if stop_event is None:
            time.sleep(seconds)
            return False
        return stop_event.wait(seconds)

    try:
        if websocket_factory is None:
            from websocket import create_connection
            websocket_factory = create_connection
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
        url = alpaca_btc_stream_url()
    except Exception:
        state.metrics.increment("btc_stream.configuration_failure")
        state.metrics.set_status("btc_source_failure_reason", "CONFIGURATION")
        publish_status("UNAVAILABLE")
        return

    location = url.rsplit("/", 1)[-1]
    state.metrics.set_status("btc_stream_location", location)
    initial = state.btc_latest_observation()
    last_published_event_epoch = (
        initial.event_epoch if initial is not None else None)
    latest_provider_event_nanoseconds = (
        round(last_published_event_epoch * 1_000_000_000)
        if last_published_event_epoch is not None else None)
    latest_provider_price = initial.midpoint if initial is not None else None
    consecutive_failures = 0

    while stop_event is None or not stop_event.is_set():
        stream = None
        try:
            stream = websocket_factory(url, timeout=timeout)
            publish_status("UNAVAILABLE")
            connected_at = clock()
            session_latest_event_epoch: float | None = None
            subscription_requested = False
            subscription_confirmed = False
            stale_episode = False
            stream.send(json.dumps({
                "action": "auth", "key": api_key, "secret": secret_key,
            }, separators=(",", ":")))

            def require_fresh() -> None:
                nonlocal stale_episode
                reference = (connected_at if session_latest_event_epoch is None
                             else session_latest_event_epoch)
                age = clock() - reference
                if age < 0 or age >= MAX_BTC_AGE_SECONDS:
                    publish_status("UNAVAILABLE")
                    if not stale_episode:
                        stale_episode = True
                        state.metrics.increment(
                            "btc_stream.watchdog_unavailable")
                    raise _AlpacaWatchdogExpired(
                        "Alpaca BTC provider time expired")

            while stop_event is None or not stop_event.is_set():
                try:
                    raw = stream.recv()
                except Exception as error:
                    if not _websocket_timeout(error):
                        raise
                    require_fresh()
                    continue
                received_at = monotonic()
                if raw in (None, "", b""):
                    raise ConnectionError("Alpaca BTC stream closed")
                # Irrelevant or malformed traffic must not keep a stale provider
                # session labeled live.
                require_fresh()
                try:
                    messages = _stream_messages(raw)
                except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
                    state.metrics.increment("btc_stream.malformed_message")
                    continue
                batch_quotes: dict[int, tuple[float, float]] = {}
                for item in messages:
                    message_type = item.get("T")
                    if message_type == "success":
                        if (item.get("msg") == "authenticated" and
                                not subscription_requested):
                            stream.send(json.dumps({
                                "action": "subscribe", "quotes": ["BTC/USD"],
                            }, separators=(",", ":")))
                            subscription_requested = True
                        continue
                    if message_type == "subscription":
                        quotes = item.get("quotes")
                        if (not subscription_requested or
                                not isinstance(quotes, list) or
                                "BTC/USD" not in quotes):
                            state.metrics.increment(
                                "btc_stream.subscription_invalid")
                            raise _AlpacaControlFailure(
                                "Alpaca BTC subscription was not confirmed",
                                reason="SUBSCRIPTION")
                        subscription_confirmed = True
                        continue
                    if message_type == "error":
                        if item.get("code") == 406:
                            raise _AlpacaConnectionLimit(
                                "Alpaca BTC stream connection limit")
                        raise _AlpacaControlFailure(
                            "Alpaca BTC stream control error", reason="CONTROL")
                    if message_type != "q" or item.get("S") != "BTC/USD":
                        continue
                    if not subscription_confirmed:
                        state.metrics.increment("btc_stream.quote_before_subscription")
                        raise _AlpacaControlFailure(
                            "Alpaca BTC quote preceded subscription confirmation",
                            reason="SUBSCRIPTION")
                    try:
                        raw_bid, raw_ask = item["bp"], item["ap"]
                        if isinstance(raw_bid, bool) or isinstance(raw_ask, bool):
                            raise ValueError("boolean quote price")
                        bid, ask = float(raw_bid), float(raw_ask)
                        event_epoch, event_nanoseconds = \
                            _parse_alpaca_timestamp_identity(item["t"])
                        if (not math.isfinite(bid) or not math.isfinite(ask) or
                                bid <= 0 or ask < bid):
                            raise ValueError("invalid quote prices")
                        quote_age_ms = (clock() - event_epoch) * 1000.0
                        if (quote_age_ms < 0 or
                                quote_age_ms >= MAX_BTC_AGE_SECONDS * 1000.0):
                            raise ValueError("stale or future quote")
                        price = (bid + ask) / 2.0
                    except (KeyError, TypeError, ValueError, AttributeError):
                        state.metrics.increment("btc_stream.quote_rejected")
                        state.metrics.set_status(
                            "btc_source_failure_reason", "QUOTE_REJECTED")
                        publish_status("UNAVAILABLE")
                        continue
                    existing = batch_quotes.get(event_nanoseconds)
                    if existing is not None and existing[1] != price:
                        state.metrics.increment(
                            "btc_stream.timestamp_conflict")
                        publish_status("UNAVAILABLE")
                        raise _AlpacaControlFailure(
                            "conflicting Alpaca BTC prices share one timestamp",
                            reason="TIMESTAMP_CONFLICT")
                    batch_quotes[event_nanoseconds] = (event_epoch, price)

                for event_nanoseconds in sorted(batch_quotes):
                    event_epoch, price = batch_quotes[event_nanoseconds]
                    if (latest_provider_event_nanoseconds is not None and
                            event_nanoseconds <
                            latest_provider_event_nanoseconds):
                        state.metrics.increment("btc_stream.quote_out_of_order")
                        continue
                    if (latest_provider_event_nanoseconds is not None and
                            event_nanoseconds ==
                            latest_provider_event_nanoseconds):
                        if price == latest_provider_price:
                            state.metrics.increment("btc_stream.quote_duplicate")
                            continue
                        state.metrics.increment("btc_stream.timestamp_conflict")
                        publish_status("UNAVAILABLE")
                        raise _AlpacaControlFailure(
                            "conflicting Alpaca BTC prices share one timestamp",
                            reason="TIMESTAMP_CONFLICT")
                    # Recheck after all frame parsing and ordering. A slow
                    # consumer must not publish a quote that was fresh only
                    # when the frame first arrived.
                    quote_age_ms = (clock() - event_epoch) * 1000.0
                    if (quote_age_ms < 0 or
                            quote_age_ms >= MAX_BTC_AGE_SECONDS * 1000.0):
                        state.metrics.increment("btc_stream.quote_rejected")
                        state.metrics.set_status(
                            "btc_source_failure_reason", "QUOTE_STALE")
                        publish_status("UNAVAILABLE")
                        continue
                    latest_provider_event_nanoseconds = event_nanoseconds
                    latest_provider_price = price
                    session_latest_event_epoch = event_epoch
                    stale_episode = False
                    if (last_published_event_epoch is None or
                            event_epoch - last_published_event_epoch >=
                            BTC_PUBLISH_INTERVAL_SECONDS):
                        if not state.accept_g2_price(
                                asset="BTC", price=price,
                                event_epoch=event_epoch,
                                max_age_seconds=MAX_BTC_AGE_SECONDS):
                            state.metrics.increment("btc_stream.quote_rejected")
                            publish_status("UNAVAILABLE")
                            raise _AlpacaControlFailure(
                                "validated Alpaca BTC quote was not accepted",
                                reason="QUOTE_REJECTED")
                        last_published_event_epoch = event_epoch
                    state.metrics.observe("btc_quote_age_ms", quote_age_ms)
                    state.metrics.observe(
                        "btc_ingest_latency_ms",
                        (monotonic() - received_at) * 1000.0,
                    )
                    publish_status("LIVE")
                    state.metrics.set_status(
                        "btc_source_failure_reason", "NONE")
                    consecutive_failures = 0
                require_fresh()
        except _AlpacaConnectionLimit:
            state.metrics.increment("btc_stream.connection_limit")
            state.metrics.set_status(
                "btc_source_failure_reason", "CONNECTION_LIMIT")
            publish_status("UNAVAILABLE")
            consecutive_failures += 1
        except _AlpacaWatchdogExpired:
            state.metrics.increment("btc_stream.watchdog_reconnect")
            state.metrics.set_status("btc_source_failure_reason", "WATCHDOG")
            publish_status("UNAVAILABLE")
            consecutive_failures += 1
        except _AlpacaControlFailure as error:
            state.metrics.increment("btc_stream.control_error")
            state.metrics.set_status(
                "btc_source_failure_reason", error.reason)
            publish_status("UNAVAILABLE")
            consecutive_failures += 1
        except Exception:
            state.metrics.increment("btc_stream.connection_failure")
            state.metrics.set_status("btc_source_failure_reason", "TRANSPORT")
            publish_status("UNAVAILABLE")
            consecutive_failures += 1
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        if stop_event is not None and stop_event.is_set():
            return
        backoff = min(
            BTC_RECONNECT_MAX_SECONDS,
            max(0.0, interval) * (
                2 ** min(10, max(0, consecutive_failures - 1))),
        )
        if wait_before_reconnect(backoff):
            return


def poll_massive_ndx(state: LiveMarketState, *, interval: float = 1.0,
                     stop_event: threading.Event | None = None) -> None:
    """Maintain the independent real-time NDX input without blocking ATOM."""

    headers = {"Authorization": f"Bearer {os.environ['MASSIVE_API_KEY']}"}
    while stop_event is None or not stop_event.is_set():
        try:
            with urlopen(Request(MASSIVE_NDX_SNAPSHOT_URL, headers=headers),
                         timeout=10) as response:
                payload = json.load(response)
            price, event_epoch = parse_massive_ndx_snapshot(payload)
            age = time.time() - event_epoch
            if age < 0 or age >= MAX_NDX_AGE_SECONDS:
                raise ValueError("Massive NDX snapshot is stale")
            if not state.accept_g2_price(
                    asset="NDX", price=price, event_epoch=event_epoch):
                raise ValueError("Massive NDX snapshot was rejected")
        except HTTPError as error:
            if error.code == 403:
                print("Massive NDX access is forbidden/unavailable", flush=True)
                return
            print(f"Massive NDX snapshot poll failed: {error}", flush=True)
        except Exception as error:
            print(f"Massive NDX snapshot poll failed: {error}", flush=True)
        if stop_event is None:
            time.sleep(interval)
        elif stop_event.wait(interval):
            return


def poll_schwab_ndx(state: LiveMarketState, *, interval: float = 1.0,
                    stop_event: threading.Event | None = None) -> None:
    """Consume only Coin's read-only `$NDX` route into the existing NDX seam."""

    while stop_event is None or not stop_event.is_set():
        try:
            request = Request(
                SCHWAB_NDX_QUOTE_URL,
                headers={"Accept": "application/json"},
            )
            with urlopen(request, timeout=10) as response:
                payload = json.load(response)
            received_at_epoch = time.time()
            price, event_epoch = parse_schwab_ndx_quote(
                payload, received_at_epoch=received_at_epoch,
            )
            age = received_at_epoch - event_epoch
            if age < 0 or age >= MAX_NDX_AGE_SECONDS:
                raise ValueError("Schwab NDX quote is stale")
            if not state.accept_g2_price(
                    asset="NDX", price=price, event_epoch=event_epoch):
                raise ValueError("Schwab NDX quote was rejected")
        except Exception as error:
            state.expire_ndx_if_stale(now_epoch=time.time())
            print(f"Schwab NDX quote poll failed: {error}", flush=True)
        if stop_event is None:
            time.sleep(interval)
        elif stop_event.wait(interval):
            return


def schwab_ndx_enabled() -> bool:
    """Return whether the disabled-by-default Schwab NDX bridge is selected."""

    return os.environ.get(SCHWAB_NDX_ENABLED_ENV, "false").strip().lower() == "true"


def start_alpaca_poller(state: LiveMarketState, *,
                        stop_event: threading.Event | None = None) -> threading.Thread:
    thread = threading.Thread(
        target=poll_alpaca, args=(state,), kwargs={"stop_event": stop_event}, daemon=True)
    thread.start()
    return thread


def start_alpaca_g2_poller(state: LiveMarketState, *,
                           stop_event: threading.Event | None = None) -> threading.Thread:
    thread = threading.Thread(
        target=poll_alpaca_g2, args=(state,), kwargs={"stop_event": stop_event}, daemon=True)
    thread.start()
    return thread


def start_massive_ndx_poller(state: LiveMarketState, *,
                             stop_event: threading.Event | None = None) -> threading.Thread:
    target = poll_schwab_ndx if schwab_ndx_enabled() else poll_massive_ndx
    thread = threading.Thread(
        target=target, args=(state,), kwargs={"stop_event": stop_event}, daemon=True)
    thread.start()
    return thread


def start_alpaca_options_poller(state: LiveMarketState, *,
                                stop_event: threading.Event | None = None) -> threading.Thread:
    """Start the independent ten-second backend options ingestion loop."""

    from .options_market import poll_alpaca_options

    thread = threading.Thread(
        target=poll_alpaca_options, args=(state,),
        kwargs={"stop_event": stop_event}, daemon=True)
    thread.start()
    return thread


__all__ = ["LatestMarketDisplay", "LiveMarketState", "LivePublication", "LiveSnapshot",
           "BTC_RECONNECT_SECONDS", "BTC_SOURCE_TIMEOUT_SECONDS", "MAX_BTC_AGE_SECONDS",
           "MARKET_DISPLAY_FETCH_SECONDS", "QUANT_CYCLE_SECONDS", "parse_alpaca_ndx_value",
           "alpaca_btc_stream_url", "parse_alpaca_timestamp",
           "parse_massive_ndx_snapshot", "parse_schwab_ndx_quote", "poll_alpaca",
           "poll_alpaca_g2", "poll_massive_ndx", "poll_schwab_ndx",
           "schwab_ndx_enabled", "start_alpaca_g2_poller",
           "start_alpaca_options_poller", "start_alpaca_poller",
           "start_massive_ndx_poller"]
