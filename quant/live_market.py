"""Minimal in-memory COIN quote ingestion and Alpaca HTTPS polling."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
import os
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


ALPACA_LATEST_QUOTES_URL = "https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=COIN%2CQQQ"
ALPACA_BTC_LATEST_QUOTE_URL = "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD"
ALPACA_NDX_LATEST_VALUE_URL = (
    "https://data.alpaca.markets/v1beta1/indices/latest/values?index_symbols=NDX"
)
MASSIVE_NDX_SNAPSHOT_URL = (
    "https://api.massive.com/v3/snapshot/indices?ticker=I%3ANDX"
)
MAX_NDX_AGE_SECONDS = 10.0
HISTORY_SECONDS = 3600.0
MARKET_DISPLAY_FETCH_SECONDS = 0.25
QUANT_CYCLE_SECONDS = 1.0
BTC_FETCH_SECONDS = 0.25
BTC_SOURCE_TIMEOUT_SECONDS = 1.0
MAX_BTC_AGE_SECONDS = 5.0


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
                 v9_cycle_handler: Callable[["LiveSnapshot", MidpointObservation | None,
                                             MidpointObservation], object | None] | None = None,
                 metrics: OperationalMetrics | None = None,
                 monotonic_clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._evidence_store = evidence_store
        self._evidence_outbox = evidence_outbox
        self._coin_sequence = 0
        # Preserve accepted COIN order through V4 calculation and the one
        # non-blocking outbox handoff.  The state lock remains narrowly scoped
        # and no database work is permitted inside this ingress boundary.
        self._coin_ingress_lock = threading.Lock()
        self._v9_cycle_handler = v9_cycle_handler
        self.metrics = metrics or OperationalMetrics()
        self.metrics.set_status("btc_source_status", "NOT_STARTED")
        self._monotonic = monotonic_clock
        self._lock = threading.Lock()
        self._btc_history = MidpointHistory()
        self._ndx_history = MidpointHistory()
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
                if not self._coin_cycle_pending:
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
            if not self._coin_cycle_pending:
                self._publication = replace(
                    self._publication, snapshot=self._snapshot,
                    cross_asset_state=self._g2_state,
                )
        return True

    def accept_g2_price(self, *, asset: str, price: float, event_epoch: float) -> bool:
        """Accept a validated BTC or NDX observation without affecting ATOM."""

        values = (price, event_epoch)
        if (asset not in ("BTC", "NDX") or
                any(isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in values)):
            return False
        price, event_epoch = map(float, values)
        if not math.isfinite(price) or price <= 0 or not math.isfinite(event_epoch):
            return False
        if asset == "NDX" and event_epoch > self._clock():
            return False
        with self._lock:
            history = self._btc_history if asset == "BTC" else self._ndx_history
            try:
                updated = append_bounded(history, MidpointObservation(event_epoch, price))
            except ValueError:
                return False
            if asset == "BTC":
                self._btc_history = updated
            else:
                self._ndx_history = updated
            self._refresh_g2(event_epoch)
            if not self._coin_cycle_pending:
                self._publication = replace(
                    self._publication, cross_asset_state=self._g2_state,
                )
        return True

    def _refresh_g2(self, event_epoch: float) -> None:
        cutoff = max(self._g2_state.as_of_epoch, event_epoch)
        self._g2_state = synchronize(
            as_of_epoch=cutoff, btc=self._btc_history,
            coin=self._snapshot.history, qqq=self._snapshot.qqq_history,
            ndx=self._ndx_history,
        )

    def cross_asset_state(self) -> CrossAssetState:
        """Return the latest already-maintained immutable G2-A state."""

        with self._lock:
            return self._publication.cross_asset_state

    def accept_quote(
        self, *, bid: float, ask: float, event_epoch: float,
        bid_size: float | None = None, ask_size: float | None = None,
    ) -> bool:
        """Serialize one COIN ingress event through its outbox handoff."""

        with self._coin_ingress_lock:
            return self._accept_quote_serialized(
                bid=bid, ask=ask, event_epoch=event_epoch,
                bid_size=bid_size, ask_size=ask_size,
            )

    def _accept_quote_serialized(
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
            if not self._coin_cycle_pending:
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
            if not self._coin_cycle_pending:
                self._publication = replace(
                    self._publication, snapshot=self._snapshot,
                )


def parse_alpaca_timestamp(value: str) -> float:
    """Convert Alpaca's RFC 3339 event timestamp to Unix seconds."""

    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


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


def poll_alpaca(
    state: LiveMarketState, *, interval: float = MARKET_DISPLAY_FETCH_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Continuously fetch latest COIN and QQQ quotes in one Alpaca request."""

    api_key = os.environ["ALPACA_API_KEY"]
    secret_key = os.environ["ALPACA_SECRET_KEY"]
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    last_quant_cycle: float | None = None
    while True:
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
        time.sleep(interval)


def poll_alpaca_g2(
    state: LiveMarketState, *, interval: float = BTC_FETCH_SECONDS,
    timeout: float = BTC_SOURCE_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.time,
    monotonic: Callable[[], float] = time.perf_counter,
) -> None:
    """Maintain the independent BTC input without blocking the ATOM cycle."""

    headers = {
        "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
    }
    while True:
        try:
            with urlopen(Request(ALPACA_BTC_LATEST_QUOTE_URL, headers=headers),
                         timeout=timeout) as response:
                payload = json.load(response)
            received_at = monotonic()
            item = payload["quotes"]["BTC/USD"]
            price = (float(item["bp"]) + float(item["ap"])) / 2.0
            event_epoch = parse_alpaca_timestamp(item["t"])
            quote_age_ms = (clock() - event_epoch) * 1000.0
            if quote_age_ms < 0 or quote_age_ms >= MAX_BTC_AGE_SECONDS * 1000.0:
                raise ValueError("Alpaca BTC quote is stale or future-dated")
            if not state.accept_g2_price(
                    asset="BTC", price=price, event_epoch=event_epoch):
                raise ValueError("Alpaca BTC quote was rejected")
            state.metrics.observe("btc_quote_age_ms", quote_age_ms)
            state.metrics.observe(
                "btc_ingest_latency_ms", (monotonic() - received_at) * 1000.0,
            )
            state.metrics.set_status("btc_source_status", "LIVE")
        except Exception as error:
            state.metrics.set_status("btc_source_status", "UNAVAILABLE")
            print(f"Alpaca BTC quote poll failed: {error}", flush=True)
        time.sleep(interval)


def poll_massive_ndx(state: LiveMarketState, *, interval: float = 1.0) -> None:
    """Maintain the independent real-time NDX input without blocking ATOM."""

    headers = {"Authorization": f"Bearer {os.environ['MASSIVE_API_KEY']}"}
    while True:
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
        time.sleep(interval)


def start_alpaca_poller(state: LiveMarketState) -> threading.Thread:
    thread = threading.Thread(target=poll_alpaca, args=(state,), daemon=True)
    thread.start()
    return thread


def start_alpaca_g2_poller(state: LiveMarketState) -> threading.Thread:
    thread = threading.Thread(target=poll_alpaca_g2, args=(state,), daemon=True)
    thread.start()
    return thread


def start_massive_ndx_poller(state: LiveMarketState) -> threading.Thread:
    thread = threading.Thread(target=poll_massive_ndx, args=(state,), daemon=True)
    thread.start()
    return thread


def start_alpaca_options_poller(state: LiveMarketState) -> threading.Thread:
    """Start the independent ten-second backend options ingestion loop."""

    from .options_market import poll_alpaca_options

    thread = threading.Thread(target=poll_alpaca_options, args=(state,), daemon=True)
    thread.start()
    return thread


__all__ = ["LatestMarketDisplay", "LiveMarketState", "LivePublication", "LiveSnapshot",
           "BTC_FETCH_SECONDS", "BTC_SOURCE_TIMEOUT_SECONDS", "MAX_BTC_AGE_SECONDS",
           "MARKET_DISPLAY_FETCH_SECONDS", "QUANT_CYCLE_SECONDS", "parse_alpaca_ndx_value",
           "parse_alpaca_timestamp", "parse_massive_ndx_snapshot", "poll_alpaca",
           "poll_alpaca_g2", "poll_massive_ndx", "start_alpaca_g2_poller",
           "start_alpaca_options_poller", "start_alpaca_poller",
           "start_massive_ndx_poller"]