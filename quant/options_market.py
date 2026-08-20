"""Alpaca COIN option discovery, snapshot parsing, and fixed-rate polling."""

from __future__ import annotations

from datetime import date, datetime, time as datetime_time, timedelta, timezone
import json
import math
import os
import time
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .q10_options_vol import OptionObservation, OptionSurface


ALPACA_OPTIONS_CONTRACTS_URL = "https://api.alpaca.markets/v2/options/contracts"
ALPACA_COIN_OPTION_SNAPSHOTS_URL = "https://data.alpaca.markets/v1beta1/options/snapshots/COIN"
OPTIONS_POLL_INTERVAL = 10.0


def alpaca_headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
    }


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _contract_date(contract: dict[str, object]) -> date | None:
    try:
        return date.fromisoformat(contract["expiration_date"])
    except (KeyError, TypeError, ValueError):
        return None


def _strike(value: object) -> float | None:
    """Parse Alpaca's decimal-string ``strike_price`` contract field."""

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def select_coin_option_contract(
    contracts: Iterable[dict[str, object]], *, midpoint: float, cutoff_epoch: float,
) -> dict[str, object] | None:
    """Select one real active COIN contract by expiry, call, ATM, and symbol."""

    cutoff = datetime.fromtimestamp(cutoff_epoch, timezone.utc)
    target = cutoff.date() + timedelta(days=30)
    valid: list[tuple[dict[str, object], date, float, str, bool]] = []
    for contract in contracts:
        expiration = _contract_date(contract)
        strike = _strike(contract.get("strike_price"))
        symbol = contract.get("symbol")
        underlying = contract.get("underlying_symbol")
        option_type = contract.get("type")
        status = contract.get("status")
        if (underlying != "COIN" or status != "active" or expiration is None or
                expiration <= cutoff.date() or strike is None or strike <= 0 or
                not isinstance(symbol, str) or not symbol):
            continue
        valid.append((contract, expiration, strike, symbol, option_type == "call"))
    if not valid:
        return None
    # Calls are preferred whenever at least one valid call exists.
    use_calls = any(item[4] for item in valid)
    pool = [item for item in valid if item[4] == use_calls]
    chosen_expiration = min({item[1] for item in pool}, key=lambda item: (abs((item - target).days), item))
    pool = [item for item in pool if item[1] == chosen_expiration]
    return min(pool, key=lambda item: (abs(item[2] - midpoint), item[2], item[3]))[0]


def select_coin_option_surface_contracts(
    contracts: Iterable[dict[str, object]], *, midpoint: float, cutoff_epoch: float,
) -> tuple[date | None, tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    """Select up to five real calls and puts at one deterministic expiration."""

    cutoff = datetime.fromtimestamp(cutoff_epoch, timezone.utc).date()
    target = cutoff + timedelta(days=30)
    valid: list[tuple[dict[str, object], date, float, str, str]] = []
    for contract in contracts:
        expiration = _contract_date(contract)
        strike = _strike(contract.get("strike_price"))
        symbol = contract.get("symbol")
        kind = contract.get("type")
        if (contract.get("underlying_symbol") != "COIN" or contract.get("status") != "active" or
                expiration is None or expiration <= cutoff or strike is None or strike <= 0 or
                not isinstance(symbol, str) or not symbol or kind not in ("call", "put")):
            continue
        valid.append((contract, expiration, strike, symbol, kind))
    if not valid:
        return None, (), ()
    expiration = min({item[1] for item in valid}, key=lambda item: (abs((item - target).days), item))

    def side(kind: str) -> tuple[dict[str, object], ...]:
        candidates = [item for item in valid if item[1] == expiration and item[4] == kind]
        nearest = sorted(candidates, key=lambda item: (abs(item[2] - midpoint), item[2], item[3]))[:5]
        return tuple(item[0] for item in sorted(nearest, key=lambda item: (item[2], item[3])))

    return expiration, side("call"), side("put")


def parse_alpaca_option_snapshot(
    contract: dict[str, object], snapshot: dict[str, object], *, cutoff_epoch: float,
) -> OptionObservation:
    """Map documented Alpaca contract/snapshot fields without filling omissions."""

    expiration = contract["expiration_date"]
    expiration_date = date.fromisoformat(expiration)
    expiration_epoch = datetime.combine(
        expiration_date, datetime_time.max, timezone.utc,
    ).timestamp()
    quote = snapshot.get("latestQuote")
    quote = quote if isinstance(quote, dict) else {}
    bid = _finite_number(quote.get("bp"))
    ask = _finite_number(quote.get("ap"))
    valid_market = bid is not None and ask is not None and bid >= 0 and ask >= bid
    if not valid_market:
        bid = bid if bid is not None and bid >= 0 else None
        ask = ask if ask is not None and ask >= 0 else None
    premium = (bid + ask) / 2 if valid_market else None
    event_epoch = cutoff_epoch
    timestamp = quote.get("t")
    if isinstance(timestamp, str):
        event_epoch = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    greeks = snapshot.get("greeks")
    greeks = greeks if isinstance(greeks, dict) else {}
    return OptionObservation(
        contract_symbol=str(contract["symbol"]), event_epoch=event_epoch,
        strike=float(contract["strike_price"]), expiration_epoch=expiration_epoch,
        expiration=expiration, premium=premium,
        implied_volatility=_finite_number(snapshot.get("impliedVolatility")),
        delta=_finite_number(greeks.get("delta")), gamma=_finite_number(greeks.get("gamma")),
        theta=_finite_number(greeks.get("theta")), vega=_finite_number(greeks.get("vega")),
        bid=bid, ask=ask,
    )


def fetch_coin_option_observation(*, midpoint: float, cutoff_epoch: float) -> OptionObservation | None:
    """Fetch Alpaca's contract catalog and snapshots for deterministic selection."""

    headers = alpaca_headers()
    query = {
        "underlying_symbols": "COIN", "status": "active",
        "expiration_date_gte": datetime.fromtimestamp(cutoff_epoch, timezone.utc).date().isoformat(),
        "limit": "10000",
    }
    contracts = []
    while True:
        with urlopen(Request(f"{ALPACA_OPTIONS_CONTRACTS_URL}?{urlencode(query)}", headers=headers), timeout=10) as response:
            page = json.load(response)
        contracts.extend(page.get("option_contracts", []))
        token = page.get("next_page_token")
        if not token:
            break
        query["page_token"] = token
    contract = select_coin_option_contract(contracts, midpoint=midpoint, cutoff_epoch=cutoff_epoch)
    if contract is None:
        return None
    snapshot = None
    snapshot_query: dict[str, object] = {"limit": 1000}
    while snapshot is None:
        url = f"{ALPACA_COIN_OPTION_SNAPSHOTS_URL}?{urlencode(snapshot_query)}"
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            page = json.load(response)
        snapshot = page.get("snapshots", {}).get(contract["symbol"])
        token = page.get("next_page_token")
        if snapshot is not None or not token:
            break
        snapshot_query["page_token"] = token
    return parse_alpaca_option_snapshot(contract, snapshot, cutoff_epoch=cutoff_epoch) if isinstance(snapshot, dict) else None


def fetch_coin_option_surface(*, midpoint: float, cutoff_epoch: float) -> OptionSurface | None:
    """Discover contracts, then map one bulk Alpaca snapshot response."""

    headers = alpaca_headers()
    query = {
        "underlying_symbols": "COIN", "status": "active",
        "expiration_date_gte": datetime.fromtimestamp(cutoff_epoch, timezone.utc).date().isoformat(),
        "limit": "10000",
    }
    contracts: list[dict[str, object]] = []
    while True:
        with urlopen(Request(f"{ALPACA_OPTIONS_CONTRACTS_URL}?{urlencode(query)}", headers=headers), timeout=10) as response:
            page = json.load(response)
        contracts.extend(page.get("option_contracts", []))
        token = page.get("next_page_token")
        if not token:
            break
        query["page_token"] = token
    expiration, calls, puts = select_coin_option_surface_contracts(
        contracts, midpoint=midpoint, cutoff_epoch=cutoff_epoch,
    )
    selected = calls + puts
    if expiration is None or not selected:
        return None
    symbols = {str(item["symbol"]) for item in selected}
    snapshots: dict[str, object] = {}
    snapshot_query: dict[str, object] = {"limit": 1000}
    while symbols - snapshots.keys():
        with urlopen(Request(
            f"{ALPACA_COIN_OPTION_SNAPSHOTS_URL}?{urlencode(snapshot_query)}", headers=headers,
        ), timeout=10) as response:
            page = json.load(response)
        page_snapshots = page.get("snapshots", {})
        if isinstance(page_snapshots, dict):
            snapshots.update((symbol, value) for symbol, value in page_snapshots.items()
                             if symbol in symbols)
        token = page.get("next_page_token")
        if not token:
            break
        snapshot_query["page_token"] = token

    def observations(items: tuple[dict[str, object], ...]) -> tuple[OptionObservation, ...]:
        return tuple(parse_alpaca_option_snapshot(item, snapshots[item["symbol"]], cutoff_epoch=cutoff_epoch)
                     for item in items if isinstance(snapshots.get(item["symbol"]), dict))

    call_observations, put_observations = observations(calls), observations(puts)
    if not call_observations and not put_observations:
        return None
    return OptionSurface(cutoff_epoch, expiration.isoformat(), call_observations, put_observations)


def poll_alpaca_options(state: object, *, interval: float = OPTIONS_POLL_INTERVAL,
                        clock: Callable[[], float] = time.time) -> None:
    """Poll independently; failures deliberately retain the last valid snapshot."""

    while True:
        try:
            snapshot = state.snapshot()
            if snapshot.history.latest is not None:
                surface = fetch_coin_option_surface(
                    midpoint=snapshot.history.latest.midpoint, cutoff_epoch=clock(),
                )
                if surface is not None:
                    state.accept_option_surface(surface, midpoint=snapshot.history.latest.midpoint)
        except HTTPError as error:
            body = error.read(2048).decode("utf-8", errors="replace")
            for credential_name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
                credential = os.environ.get(credential_name)
                if credential:
                    body = body.replace(credential, "[REDACTED]")
            print(f"Alpaca options poll failed: HTTP {error.code}: {body}", flush=True)
        except Exception as error:
            print(f"Alpaca options poll failed: {error}", flush=True)
        time.sleep(interval)


__all__ = ["ALPACA_COIN_OPTION_SNAPSHOTS_URL", "ALPACA_OPTIONS_CONTRACTS_URL",
           "OPTIONS_POLL_INTERVAL", "fetch_coin_option_observation", "fetch_coin_option_surface",
           "parse_alpaca_option_snapshot", "poll_alpaca_options", "select_coin_option_contract",
           "select_coin_option_surface_contracts"]
