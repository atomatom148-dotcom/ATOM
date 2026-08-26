"""Isolated, deterministic inputs for one-session ATOM V9 replay.

This module reads historical Alpaca SIP quotes once, advances a causal
event-time clock, and calls the existing frozen family equations.  It has no
production runtime, database, outbox, Render, web, or SIM integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
import calendar
import hashlib
import json
import math
import os
import re
from typing import Callable, Iterable, Iterator, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .history import MidpointHistory, MidpointObservation
from .q1_momentum import FORMULA_VERSION as Q1_VERSION, calculate_momentum
from .q2_mean_reversion import FORMULA_VERSION as Q2_VERSION, calculate_mean_reversion
from .q3_volatility import FORMULA_VERSION as Q3_VERSION, calculate_volatility
from .q4_stat_arb import FORMULA_VERSION as Q4_VERSION, calculate_stat_arb
from .q5_microstructure import FORMULA_VERSION as Q5_VERSION, calculate_microstructure
from .q6_volume_liquidity import FORMULA_VERSION as Q6_VERSION, calculate_volume_liquidity
from .q7_relative_value import FORMULA_VERSION as Q7_VERSION, calculate_relative_value
from .q8_cross_asset import FORMULA_VERSION as Q8_VERSION, calculate_cross_asset
from .q9_factor import FORMULA_VERSION as Q9_VERSION, calculate_factor
from .q11_regime import FORMULA_VERSION as Q11_VERSION, calculate_regime
from .q12_event_session import FORMULA_VERSION as Q12_VERSION, calculate_event_session
from .quote_history import QuoteHistory, QuoteObservation
from .v9_v2a_dataset import (
    DIRECTIONAL_FAMILIES, HORIZON_SECONDS, METHOD_VERSION as V2A_METHOD_VERSION,
    Q3, SYMBOL as V2_SYMBOL, FamilyLineage, RawFamilyObservation, RawTarget,
    build_v2a_dataset,
)
from .v9_v2b_calibration import (
    FORMULA_VERSION as V2B_METHOD_VERSION, build_v2b_calibration,
)
from .v9_v2c_covariance import METHOD_VERSION as V2C_METHOD_VERSION, build_v2c_covariance
from .v9_v2d_evidence_state import (
    CALIBRATION_METHOD_VERSION, COVARIANCE_METHOD_VERSION,
    EFFECTIVE_N_METHOD_VERSION, MODEL_FAMILY as V2_MODEL_FAMILY,
    NUMERICAL_CANONICALIZATION_VERSION,
    STATE_SCHEMA_VERSION as V2_STATE_SCHEMA_VERSION,
    STATE_VERSION as V2_STATE_VERSION, V2EvidenceState, build_v2d_evidence_state,
    v2d_state_hash,
)


ALPACA_HISTORICAL_QUOTES_URL = "https://data.alpaca.markets/v2/stocks/quotes"
SYMBOLS = ("COIN", "QQQ")
DATA_SCHEMA_VERSION = "alpaca-historical-sip-nbbo-v1"
SOURCE = "ALPACA_SIP"
SOURCE_SPEC_ROUND_LOTS = "alpaca-sip-quote-size-round-lots-v1"
SOURCE_SPEC_SHARES = "alpaca-sip-quote-size-shares-v1"
REPLAY_METHOD_VERSION = "alpaca-sip-logical-1s-rth-window-v5"
REPLAY_STATE_SCHEMA_VERSION = "ATOM-HISTORICAL-V2-ENVELOPE-1"
EVIDENCE_ORIGIN = "HISTORICAL_REPLAY"
TARGET_SPEC_ID = "COIN_MIDPOINT_LOG_RETURN_BPS_1"
MAX_TARGET_RESOLUTION_DELAY_SECONDS = 5.0
ALLOWED_FORMULA_VERSIONS = {
    "q1_momentum": Q1_VERSION,
    "q2_mean_reversion": Q2_VERSION,
    "q3_volatility": Q3_VERSION,
    "q4_stat_arb": Q4_VERSION,
    "q5_microstructure": Q5_VERSION,
    "q6_volume_liquidity": Q6_VERSION,
    "q7_relative_value": Q7_VERSION,
    "q8_cross_asset": Q8_VERSION,
    "q9_factor": Q9_VERSION,
    "q11_regime": Q11_VERSION,
    "q12_event_session": Q12_VERSION,
}
_SIZE_SHARES_START_NS = 1_762_146_000_000_000_000  # 2025-11-03 00:00 ET
_NANOSECONDS = 1_000_000_000
_HISTORY_SECONDS = 3600.0
_QUOTE_HISTORY_SECONDS = 300.0
_EASTERN = ZoneInfo("America/New_York")
_RFC3339_NANOSECONDS = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[Tt]"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?"
    r"(?P<zone>[Zz]|[+-]\d{2}:\d{2})$"
)
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _datetime_ns(value: datetime) -> int:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("session boundaries must be timezone-aware")
    utc = value.astimezone(timezone.utc)
    seconds = calendar.timegm(utc.utctimetuple())
    return seconds * _NANOSECONDS + utc.microsecond * 1000


def _parse_provider_ns(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError("provider timestamp must be RFC-3339 text")
    matched = _RFC3339_NANOSECONDS.fullmatch(value)
    if matched is None:
        raise ValueError("provider timestamp must be RFC-3339")
    zone = matched.group("zone")
    if zone in {"Z", "z"}:
        zone = "+00:00"
    try:
        parsed = datetime.fromisoformat(
            f"{matched.group('date')}T{matched.group('time')}{zone}"
        ).astimezone(timezone.utc)
    except ValueError as error:
        raise ValueError("provider timestamp is invalid") from error
    delta = parsed - _UNIX_EPOCH
    whole = delta.days * 86_400 + delta.seconds
    fraction = (matched.group("fraction") or "").ljust(9, "0")
    return whole * _NANOSECONDS + int(fraction or "0")


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _finite_number(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(float(value)))


@dataclass(frozen=True, slots=True)
class HistoricalSipQuote:
    symbol: str
    provider_event_ns: int
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    source: str = SOURCE
    data_schema_version: str = DATA_SCHEMA_VERSION
    source_spec_version: str = SOURCE_SPEC_SHARES

    def __post_init__(self) -> None:
        if self.symbol not in SYMBOLS:
            raise ValueError("historical quote symbol must be COIN or QQQ")
        if (isinstance(self.provider_event_ns, bool) or
                not isinstance(self.provider_event_ns, int) or
                self.provider_event_ns <= 0):
            raise ValueError("provider_event_ns must be a positive integer")
        values = (self.bid, self.ask, self.bid_size, self.ask_size)
        if any(not _finite_number(value) for value in values):
            raise ValueError("historical quote fields must be finite numbers")
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            raise ValueError("historical quote has an invalid top of book")
        if self.bid_size < 0 or self.ask_size < 0:
            raise ValueError("historical quote sizes must be nonnegative")
        if self.source != SOURCE or self.data_schema_version != DATA_SCHEMA_VERSION:
            raise ValueError("historical quote lineage is invalid")
        expected = (SOURCE_SPEC_SHARES if self.provider_event_ns >= _SIZE_SHARES_START_NS
                    else SOURCE_SPEC_ROUND_LOTS)
        if self.source_spec_version != expected:
            raise ValueError("historical quote size-unit lineage is invalid")

    @property
    def event_epoch(self) -> float:
        return self.provider_event_ns / _NANOSECONDS

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2.0

    def midpoint_observation(self) -> MidpointObservation:
        return MidpointObservation(self.event_epoch, self.midpoint)

    def quote_observation(self) -> QuoteObservation:
        return QuoteObservation(
            self.event_epoch, self.bid, self.ask, self.bid_size, self.ask_size,
        )


@dataclass(frozen=True, slots=True)
class HistoricalSipRetrievalProof:
    requested_symbols: tuple[str, ...]
    feed: str
    request_start_ns: int
    request_end_ns: int
    page_limit: int
    page_count: int
    page_raw_row_counts: tuple[int, ...]
    raw_row_count: int
    retained_row_count: int
    bucket_sampled_row_count: int
    rejected_row_count: int
    rejection_reason_counts: tuple[tuple[str, int], ...]
    terminal_next_page_token: str | None


class AlpacaHistoricalSipReader:
    """Read and deterministically sample one bounded COIN+QQQ SIP session."""

    def __init__(
        self, api_key: str, secret_key: str, *,
        opener: Callable = urlopen, page_limit: int = 10_000,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("Alpaca API key is required")
        if not isinstance(secret_key, str) or not secret_key:
            raise ValueError("Alpaca secret key is required")
        if (isinstance(page_limit, bool) or not isinstance(page_limit, int) or
                not 1 <= page_limit <= 10_000):
            raise ValueError("page_limit must be between 1 and 10000")
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }
        self._opener = opener
        self._page_limit = page_limit
        self._last_retrieval_proof: HistoricalSipRetrievalProof | None = None

    @property
    def last_retrieval_proof(self) -> HistoricalSipRetrievalProof | None:
        return self._last_retrieval_proof

    @classmethod
    def from_environment(cls, *, opener: Callable = urlopen) -> "AlpacaHistoricalSipReader":
        return cls(
            os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"],
            opener=opener,
        )

    def read_session(
        self, *, session_open: datetime, session_close: datetime,
    ) -> tuple[HistoricalSipQuote, ...]:
        self._last_retrieval_proof = None
        open_ns, close_ns = _session_bounds(session_open, session_close)
        base_query = {
            "symbols": ",".join(SYMBOLS),
            "start": _rfc3339(session_open),
            "end": _rfc3339(session_close),
            "feed": "sip",
            "asof": "-",
            "currency": "USD",
            "sort": "asc",
            "limit": str(self._page_limit),
        }
        coin_by_cutoff: dict[
            int, tuple[HistoricalSipQuote, HistoricalSipQuote]
        ] = {}
        qqq_by_cutoff: dict[
            int, tuple[HistoricalSipQuote, HistoricalSipQuote]
        ] = {}
        qqq_predecessors: dict[int, HistoricalSipQuote] = {}
        page_token: str | None = None
        seen_tokens: set[str] = set()
        last_row_by_symbol: dict[str, HistoricalSipQuote] = {}
        qqq_started = False
        coin_rows: tuple[HistoricalSipQuote, ...] = ()
        coin_index = 0
        last_qqq: HistoricalSipQuote | None = None
        page_raw_row_counts: list[int] = []
        valid_row_count = 0
        rejection_counts = {
            "INVALID_TOP_OF_BOOK": 0,
            "OUTSIDE_REQUEST_WINDOW": 0,
        }
        while True:
            query = dict(base_query)
            if page_token is not None:
                query["page_token"] = page_token
            request = Request(
                f"{ALPACA_HISTORICAL_QUOTES_URL}?{urlencode(query)}",
                headers=self._headers,
            )
            with self._opener(request, timeout=30) as response:
                payload = json.load(response)
            if not isinstance(payload, dict) or not isinstance(payload.get("quotes"), dict):
                raise ValueError("Alpaca historical quote response is malformed")
            quotes = payload["quotes"]
            page_raw_row_count = 0
            for symbol in SYMBOLS:
                items = quotes.get(symbol, ())
                if not isinstance(items, (list, tuple)):
                    raise ValueError("Alpaca historical quote collection is malformed")
                page_raw_row_count += len(items)
                for item in items:
                    decoded, rejection_reason = self._decode(
                        symbol, item, open_ns, close_ns,
                    )
                    if decoded is None:
                        rejection_counts[rejection_reason] += 1
                        continue
                    valid_row_count += 1
                    previous = last_row_by_symbol.get(symbol)
                    if (previous is not None and
                            decoded.provider_event_ns < previous.provider_event_ns):
                        raise ValueError(
                            "Alpaca historical quotes are out of order")
                    if (previous is not None and
                            decoded.provider_event_ns == previous.provider_event_ns):
                        if decoded != previous:
                            raise ValueError(
                                "conflicting historical quote identity")
                        continue
                    last_row_by_symbol[symbol] = decoded
                    cutoff_ns = open_ns + (
                        (decoded.provider_event_ns - open_ns +
                         _NANOSECONDS - 1) // _NANOSECONDS
                    ) * _NANOSECONDS
                    if symbol == "COIN":
                        if qqq_started:
                            raise ValueError(
                                "Alpaca historical quotes are out of order")
                        retained = coin_by_cutoff.get(cutoff_ns)
                        coin_by_cutoff[cutoff_ns] = (
                            (decoded, decoded) if retained is None else
                            (retained[0], decoded)
                        )
                        continue
                    if not qqq_started:
                        qqq_started = True
                        coin_rows = tuple(
                            last for _first, last in coin_by_cutoff.values()
                        )
                    while (coin_index < len(coin_rows) and
                           coin_rows[coin_index].provider_event_ns <
                           decoded.provider_event_ns):
                        if last_qqq is not None:
                            qqq_predecessors[last_qqq.provider_event_ns] = last_qqq
                        coin_index += 1
                    last_qqq = decoded
                    retained = qqq_by_cutoff.get(cutoff_ns)
                    qqq_by_cutoff[cutoff_ns] = (
                        (decoded, decoded) if retained is None else
                        (retained[0], decoded)
                    )
                    while (coin_index < len(coin_rows) and
                           coin_rows[coin_index].provider_event_ns ==
                           decoded.provider_event_ns):
                        qqq_predecessors[decoded.provider_event_ns] = decoded
                        coin_index += 1
            page_raw_row_counts.append(page_raw_row_count)
            if "next_page_token" not in payload:
                raise ValueError("Alpaca historical quote pagination is invalid")
            token = payload["next_page_token"]
            if token is None:
                break
            if not isinstance(token, str) or not token or token in seen_tokens:
                raise ValueError("Alpaca historical quote pagination is invalid")
            seen_tokens.add(token)
            page_token = token

        if not qqq_started:
            coin_rows = tuple(
                last for _first, last in coin_by_cutoff.values()
            )
        while coin_index < len(coin_rows):
            if last_qqq is not None:
                qqq_predecessors[last_qqq.provider_event_ns] = last_qqq
            coin_index += 1
        retained_coin_rows = {
            row.provider_event_ns: row
            for first, last in coin_by_cutoff.values()
            for row in (first, last)
        }
        qqq_rows = {
            row.provider_event_ns: row
            for boundary in qqq_by_cutoff.values()
            for row in boundary
        }
        qqq_rows.update(qqq_predecessors)
        retained_rows = tuple(sorted(
            (*retained_coin_rows.values(), *qqq_rows.values()),
            key=lambda row: (row.provider_event_ns, SYMBOLS.index(row.symbol)),
        ))
        raw_row_count = sum(page_raw_row_counts)
        rejected_row_count = sum(rejection_counts.values())
        bucket_sampled_row_count = valid_row_count - len(retained_rows)
        if (bucket_sampled_row_count < 0 or
                raw_row_count != (
                    len(retained_rows) + bucket_sampled_row_count +
                    rejected_row_count
                )):
            raise RuntimeError("REPLAY_ROW_ACCOUNTING_MISMATCH")
        self._last_retrieval_proof = HistoricalSipRetrievalProof(
            SYMBOLS, "sip", open_ns, close_ns, self._page_limit,
            len(page_raw_row_counts), tuple(page_raw_row_counts),
            raw_row_count, len(retained_rows), bucket_sampled_row_count,
            rejected_row_count, tuple(
                (reason, count) for reason, count in sorted(
                    rejection_counts.items()
                ) if count
            ), None,
        )
        return retained_rows

    @staticmethod
    def _decode(
        symbol: str, payload: object, open_ns: int, close_ns: int,
    ) -> tuple[HistoricalSipQuote | None, str | None]:
        if not isinstance(payload, dict):
            raise ValueError("Alpaca historical quote is malformed")
        try:
            event_ns = _parse_provider_ns(payload["t"])
            raw_values = tuple(payload[key] for key in ("bp", "ap", "bs", "as"))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Alpaca historical quote is malformed") from error
        if any(not _finite_number(value) for value in raw_values):
            raise ValueError("Alpaca historical quote is malformed")
        bid, ask, bid_size, ask_size = map(float, raw_values)
        if not open_ns <= event_ns < close_ns:
            return None, "OUTSIDE_REQUEST_WINDOW"
        if bid <= 0 or ask <= 0 or ask < bid:
            return None, "INVALID_TOP_OF_BOOK"
        source_spec = (SOURCE_SPEC_SHARES if event_ns >= _SIZE_SHARES_START_NS
                       else SOURCE_SPEC_ROUND_LOTS)
        return (
            HistoricalSipQuote(
                symbol, event_ns, bid, ask, bid_size, ask_size,
                source_spec_version=source_spec,
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class ReplayFrame:
    clock_ns: int
    cutoff_ns: int
    coin_source_as_of_ns: int
    qqq_source_as_of_ns: int | None
    coin_history: MidpointHistory
    qqq_history: MidpointHistory
    coin_quote_history: QuoteHistory
    source: str = SOURCE
    data_schema_version: str = DATA_SCHEMA_VERSION
    source_spec_version: str = SOURCE_SPEC_SHARES
    replay_method_version: str = REPLAY_METHOD_VERSION

    def __post_init__(self) -> None:
        exact_times = (
            self.clock_ns, self.cutoff_ns, self.coin_source_as_of_ns,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
               for value in exact_times):
            raise ValueError("replay frame timestamps must be positive integers")
        if self.clock_ns != self.cutoff_ns:
            raise ValueError("replay cutoff must equal the logical clock")
        if self.coin_source_as_of_ns > self.cutoff_ns:
            raise ValueError("COIN source cannot be newer than the replay cutoff")
        if self.qqq_source_as_of_ns is not None:
            if (isinstance(self.qqq_source_as_of_ns, bool) or
                    not isinstance(self.qqq_source_as_of_ns, int) or
                    self.qqq_source_as_of_ns <= 0 or
                    self.qqq_source_as_of_ns > self.coin_source_as_of_ns):
                raise ValueError("QQQ source must be causal to the selected COIN source")
        expected = (SOURCE_SPEC_SHARES
                    if self.coin_source_as_of_ns >= _SIZE_SHARES_START_NS
                    else SOURCE_SPEC_ROUND_LOTS)
        cutoff_at = datetime.fromtimestamp(
            self.cutoff_ns / _NANOSECONDS, timezone.utc,
        ).astimezone(_EASTERN)
        local_cutoff = cutoff_at.timetz().replace(tzinfo=None)
        session_open = cutoff_at.replace(
            hour=9, minute=30, second=0, microsecond=0,
        )
        session_open_ns = _datetime_ns(session_open)
        history_epochs = tuple(
            row.event_epoch for history in (
                self.coin_history, self.qqq_history, self.coin_quote_history,
            ) for row in history.observations
        )
        if (not time(9, 30) <= local_cutoff < time(16, 0) or
                self.coin_source_as_of_ns < session_open_ns or
                (self.qqq_source_as_of_ns is not None and
                 self.qqq_source_as_of_ns < session_open_ns) or
                any(epoch < session_open.timestamp() or
                    epoch > self.cutoff_epoch for epoch in history_epochs)):
            raise ValueError("replay frame must contain only current-session RTH data")
        coin_source_epoch = self.coin_source_as_of_epoch
        qqq_source_epoch = self.qqq_source_as_of_epoch
        coin_source_ceiling = math.nextafter(coin_source_epoch, math.inf)
        qqq_source_ceiling = (None if qqq_source_epoch is None else
                              math.nextafter(qqq_source_epoch, math.inf))
        if (any(row.event_epoch > coin_source_ceiling
                for row in self.coin_history.observations) or
                any(row.event_epoch > coin_source_ceiling
                    for row in self.coin_quote_history.observations) or
                (qqq_source_epoch is None and self.qqq_history.observations) or
                (qqq_source_epoch is not None and any(
                    row.event_epoch > qqq_source_ceiling
                    for row in self.qqq_history.observations))):
            raise ValueError("replay histories exceed their exact source markers")
        if (self.source != SOURCE or
                self.data_schema_version != DATA_SCHEMA_VERSION or
                self.source_spec_version != expected or
                self.replay_method_version != REPLAY_METHOD_VERSION):
            raise ValueError("replay frame lineage is invalid")

    @property
    def clock_epoch(self) -> float:
        return self.clock_ns / _NANOSECONDS

    @property
    def cutoff_epoch(self) -> float:
        return self.cutoff_ns / _NANOSECONDS

    @property
    def coin_source_as_of_epoch(self) -> float:
        return self.coin_source_as_of_ns / _NANOSECONDS

    @property
    def qqq_source_as_of_epoch(self) -> float | None:
        if self.qqq_source_as_of_ns is None:
            return None
        return self.qqq_source_as_of_ns / _NANOSECONDS


@dataclass(frozen=True, slots=True)
class ReplayFamilyResults:
    cutoff_epoch: float
    q1_momentum: object | None
    q2_mean_reversion: object | None
    q3_volatility: object | None
    q4_stat_arb: object | None
    q5_microstructure: object | None
    q6_volume_liquidity: object | None
    q7_relative_value: object | None
    q8_cross_asset: object | None
    q9_factor: object | None
    q10_options_vol: None
    q11_regime: object | None
    q12_event_session: object | None


@dataclass(frozen=True, slots=True)
class HistoricalReplayV2State:
    """Replay-only provenance envelope around the frozen generic V2 state."""

    replay_state_schema_version: str
    evidence_origin: str
    replay_run_id: str
    replay_method_version: str
    historical_session: str
    source: str
    data_schema_version: str
    source_spec_version: str
    target_spec_id: str
    v2_state: V2EvidenceState
    replay_state_hash: str
    replay_state_id: str

    def __post_init__(self) -> None:
        valid_run_id = (isinstance(self.replay_run_id, str) and
                        1 <= len(self.replay_run_id) <= 128)
        expected_session = datetime.fromtimestamp(
            self.v2_state.state_as_of, timezone.utc,
        ).astimezone(_EASTERN).date().isoformat() if isinstance(
            self.v2_state, V2EvidenceState
        ) else None
        if (self.replay_state_schema_version != REPLAY_STATE_SCHEMA_VERSION or
                self.evidence_origin != EVIDENCE_ORIGIN or
                not valid_run_id or
                self.replay_method_version != REPLAY_METHOD_VERSION or
                self.historical_session != expected_session or
                self.source != SOURCE or
                self.data_schema_version != DATA_SCHEMA_VERSION or
                self.source_spec_version not in {
                    SOURCE_SPEC_ROUND_LOTS, SOURCE_SPEC_SHARES,
                } or
                self.target_spec_id != TARGET_SPEC_ID or
                not isinstance(self.v2_state, V2EvidenceState) or
                self.v2_state.target_spec_id != TARGET_SPEC_ID or
                self.v2_state.target_data_schema_version != DATA_SCHEMA_VERSION or
                self.v2_state.target_source_spec_version != self.source_spec_version):
            raise ValueError("historical replay V2 envelope lineage is invalid")
        inner_hash = v2d_state_hash(self.v2_state)
        if (self.v2_state.state_hash != inner_hash or
                self.v2_state.state_id != f"v9v2:{inner_hash}"):
            raise ValueError("historical replay V2 inner identity is invalid")
        if not _authorized_replay_v2_state(
            self.v2_state, source_spec_version=self.source_spec_version,
        ):
            raise ValueError("historical replay V2 state is not an authorized baseline")
        expected = _replay_state_hash(
            replay_run_id=self.replay_run_id,
            historical_session=self.historical_session,
            source_spec_version=self.source_spec_version,
            v2_state=self.v2_state,
        )
        if (self.replay_state_hash != expected or
                self.replay_state_id != f"historical-v2:{expected}"):
            raise ValueError("historical replay V2 envelope identity is invalid")


def _replay_state_hash(
    *, replay_run_id: str, historical_session: str,
    source_spec_version: str, v2_state: V2EvidenceState,
) -> str:
    identity = (
        REPLAY_STATE_SCHEMA_VERSION, EVIDENCE_ORIGIN, replay_run_id,
        REPLAY_METHOD_VERSION, historical_session, SOURCE,
        DATA_SCHEMA_VERSION, source_spec_version, TARGET_SPEC_ID,
        v2_state.state_id, v2_state.state_hash,
    )
    return hashlib.sha256(json.dumps(
        identity, ensure_ascii=True, separators=(",", ":"),
    ).encode()).hexdigest()


def _authorized_replay_v2_state(
    state: V2EvidenceState, *, source_spec_version: str,
) -> bool:
    local_as_of = datetime.fromtimestamp(
        state.state_as_of, timezone.utc,
    ).astimezone(_EASTERN)
    expected_directional = tuple(
        quant_id for quant_id in DIRECTIONAL_FAMILIES
        if quant_id in ALLOWED_FORMULA_VERSIONS
    )
    expected_lineage = tuple(FamilyLineage(
        quant_id, ALLOWED_FORMULA_VERSIONS[quant_id],
        DATA_SCHEMA_VERSION, source_spec_version,
    ) for quant_id in (*expected_directional, Q3))
    horizon_states = state.horizon_state_tuple
    expected_source_spec = (
        SOURCE_SPEC_SHARES
        if state.state_as_of >= _SIZE_SHARES_START_NS / _NANOSECONDS
        else SOURCE_SPEC_ROUND_LOTS
    )
    if (state.state_schema_version != V2_STATE_SCHEMA_VERSION or
            state.state_version != V2_STATE_VERSION or
            state.model_family != V2_MODEL_FAMILY or
            state.symbol != V2_SYMBOL or
            state.v2a_method_version != V2A_METHOD_VERSION or
            state.v2b_method_version != V2B_METHOD_VERSION or
            state.v2c_method_version != V2C_METHOD_VERSION or
            state.effective_n_method_version != EFFECTIVE_N_METHOD_VERSION or
            state.calibration_method_version != CALIBRATION_METHOD_VERSION or
            state.covariance_method_version != COVARIANCE_METHOD_VERSION or
            state.numerical_canonicalization_version !=
            NUMERICAL_CANONICALIZATION_VERSION or
            source_spec_version != expected_source_spec or
            state.creation_status != "VALID" or
            not time(9, 30) <= local_as_of.timetz().replace(tzinfo=None) < time(16, 0) or
            tuple(item.horizon for item in horizon_states) != tuple(HORIZON_SECONDS)):
        return False
    verified_statuses = []
    for item in horizon_states:
        expected_calibrations = tuple(
            (quant_id, ALLOWED_FORMULA_VERSIONS[quant_id],
             DATA_SCHEMA_VERSION, source_spec_version)
            for quant_id in expected_directional
        )
        actual_calibrations = tuple(
            (row.quant_id, row.formula_version, row.data_schema_version,
             row.source_spec_version)
            for row in item.directional_calibrations
        )
        q3_identity = (
            item.q3.quant_id, item.q3.formula_version,
            item.q3.data_schema_version, item.q3.source_spec_version,
        )
        usable = tuple(
            row for row in item.directional_calibrations
            if row.status != "UNAVAILABLE"
        )
        covariance = item.stabilized_covariance_matrix
        covariance_usable = (
            item.covariance_status != "UNAVAILABLE" and
            covariance is not None and
            len(covariance) == len(item.directional_calibrations) and
            all(len(row) == len(item.directional_calibrations)
                for row in covariance)
        )
        if not usable or not covariance_usable:
            verified_status = "UNAVAILABLE"
        elif (all(row.status == "MATURE"
                  for row in item.directional_calibrations) and
              item.covariance_status == "MATURE" and
              item.q3.status == "MATURE" and
              "HETEROGENEOUS_COMPONENT_CUTOFF" not in item.reason_codes):
            verified_status = "MATURE"
        else:
            verified_status = "PROVISIONAL"
        if (item.horizon_seconds != HORIZON_SECONDS[item.horizon] or
                item.status != verified_status or
                item.family_lineage != expected_lineage or
                item.ordered_quant_ids != expected_directional or
                actual_calibrations != expected_calibrations or
                q3_identity != (
                    Q3, ALLOWED_FORMULA_VERSIONS[Q3],
                    DATA_SCHEMA_VERSION, source_spec_version,
                )):
            return False
        verified_statuses.append(verified_status)
    expected_top = (
        "MATURE" if all(status == "MATURE" for status in verified_statuses) else
        "UNAVAILABLE" if all(status == "UNAVAILABLE"
                             for status in verified_statuses) else
        "PROVISIONAL"
    )
    return state.top_level_status == expected_top


class OneSessionReplayClock:
    """Select the latest causal provider quote at fixed one-second cutoffs."""

    def __init__(
        self, quotes: Iterable[HistoricalSipQuote], *,
        session_open: datetime, session_close: datetime,
    ) -> None:
        open_ns, close_ns = _session_bounds(session_open, session_close)
        materialized = tuple(quotes)
        if any(not isinstance(row, HistoricalSipQuote) for row in materialized):
            raise TypeError("quotes must contain HistoricalSipQuote values")
        canonical = tuple(sorted(
            materialized,
            key=lambda row: (row.provider_event_ns, SYMBOLS.index(row.symbol)),
        ))
        if materialized != canonical:
            raise ValueError("historical quotes must be in canonical chronological order")
        if any(not open_ns <= row.provider_event_ns < close_ns for row in materialized):
            raise ValueError("historical quote is outside the replay session")
        last_by_symbol: dict[str, int] = {}
        for row in materialized:
            previous = last_by_symbol.get(row.symbol)
            if previous is not None and row.provider_event_ns <= previous:
                raise ValueError(
                    "historical quote timestamps must be strictly increasing")
            last_by_symbol[row.symbol] = row.provider_event_ns
        self._quotes = materialized
        self._open_ns = open_ns
        self._close_ns = close_ns

    def frames(self) -> Iterator[ReplayFrame]:
        index = 0
        latest_coin: HistoricalSipQuote | None = None
        qqq_seen: list[HistoricalSipQuote] = []
        qqq_causal_index = -1
        last_coin_ns: int | None = None
        last_qqq_ns: int | None = None
        coin_history = MidpointHistory()
        qqq_history = MidpointHistory()
        quote_history = QuoteHistory()
        last_coin_float: float | None = None
        last_qqq_float: float | None = None

        cutoff_ns = self._open_ns
        while cutoff_ns < self._close_ns:
            while (index < len(self._quotes) and
                   self._quotes[index].provider_event_ns <= cutoff_ns):
                row = self._quotes[index]
                if row.symbol == "COIN":
                    latest_coin = row
                else:
                    qqq_seen.append(row)
                index += 1
            coin = latest_coin
            if coin is not None and coin.provider_event_ns != last_coin_ns:
                while (qqq_causal_index + 1 < len(qqq_seen) and
                       qqq_seen[qqq_causal_index + 1].provider_event_ns <=
                       coin.provider_event_ns):
                    qqq_causal_index += 1
                qqq = (None if qqq_causal_index < 0
                       else qqq_seen[qqq_causal_index])
                if qqq is not None and qqq.provider_event_ns != last_qqq_ns:
                    qqq_float = _monotonic_epoch(
                        qqq.provider_event_ns, last_qqq_float, cutoff_ns,
                    )
                    qqq_history = _append_qqq(
                        qqq_history, MidpointObservation(qqq_float, qqq.midpoint),
                    )
                    last_qqq_ns = qqq.provider_event_ns
                    last_qqq_float = qqq_float
                coin_float = _monotonic_epoch(
                    coin.provider_event_ns, last_coin_float, cutoff_ns,
                )
                observation = MidpointObservation(coin_float, coin.midpoint)
                coin_history = _append_coin(coin_history, observation)
                quote_history = _append_quote(quote_history, QuoteObservation(
                    coin_float, coin.bid, coin.ask, coin.bid_size, coin.ask_size,
                ))
                last_coin_ns = coin.provider_event_ns
                last_coin_float = coin_float
                yield ReplayFrame(
                    cutoff_ns,
                    cutoff_ns,
                    coin.provider_event_ns,
                    None if qqq is None else qqq.provider_event_ns,
                    coin_history,
                    qqq_history,
                    quote_history,
                    source_spec_version=coin.source_spec_version,
                )
            cutoff_ns += _NANOSECONDS


def calculate_replay_families(frame: ReplayFrame) -> ReplayFamilyResults:
    """Apply the deployed frozen equations; Q10 remains unavailable."""

    cutoff = frame.cutoff_epoch
    return ReplayFamilyResults(
        cutoff,
        calculate_momentum(frame.coin_history, cutoff_epoch=cutoff),
        calculate_mean_reversion(frame.coin_history, cutoff_epoch=cutoff),
        calculate_volatility(frame.coin_history, cutoff_epoch=cutoff),
        calculate_stat_arb(frame.coin_history, frame.qqq_history,
                           cutoff_epoch=cutoff),
        calculate_microstructure(frame.coin_quote_history, cutoff_epoch=cutoff),
        calculate_volume_liquidity(frame.coin_quote_history, cutoff_epoch=cutoff),
        calculate_relative_value(frame.coin_history, frame.qqq_history,
                                 cutoff_epoch=cutoff),
        calculate_cross_asset(frame.coin_history, frame.qqq_history,
                              cutoff_epoch=cutoff),
        calculate_factor(frame.coin_history, frame.qqq_history,
                         cutoff_epoch=cutoff),
        None,
        calculate_regime(frame.coin_history, cutoff_epoch=cutoff),
        calculate_event_session(frame.coin_history, cutoff_epoch=cutoff),
    )


def build_replay_v2_as_of(
    *, frame: ReplayFrame,
    replay_run_id: str,
    targets_by_horizon: Mapping[str, Iterable[RawTarget]],
    observations_by_horizon: Mapping[str, Iterable[RawFamilyObservation]],
    family_versions: Iterable[tuple[str, str, str, str]],
) -> HistoricalReplayV2State:
    """Build V2 only from tuples already visible to the replay clock."""

    if not isinstance(frame, ReplayFrame):
        raise TypeError("frame must be a ReplayFrame")
    if (not isinstance(replay_run_id, str) or not replay_run_id or
            len(replay_run_id) > 128):
        raise ValueError("replay_run_id must be 1-128 characters")
    state_as_of = frame.cutoff_epoch
    targets_snapshot = {
        horizon: tuple(rows) for horizon, rows in targets_by_horizon.items()
    }
    observations_snapshot = {
        horizon: tuple(rows) for horizon, rows in observations_by_horizon.items()
    }
    versions = tuple(family_versions)
    try:
        declared = {
            quant_id: (formula, schema, source_spec)
            for quant_id, formula, schema, source_spec in versions
        }
    except (TypeError, ValueError) as error:
        raise RuntimeError("REPLAY_FORMULA_LINEAGE_MISMATCH") from error
    if len(declared) != len(versions):
        raise RuntimeError("REPLAY_FORMULA_LINEAGE_MISMATCH")
    if "q10_options_vol" in declared or any(
        row.quant_id == "q10_options_vol"
        for rows in observations_snapshot.values() for row in rows
    ):
        raise RuntimeError("REPLAY_Q10_DATA_UNAVAILABLE")
    if any(
        ALLOWED_FORMULA_VERSIONS.get(quant_id) != formula
        for quant_id, (formula, _schema, _source_spec) in declared.items()
    ):
        raise RuntimeError("REPLAY_FORMULA_LINEAGE_MISMATCH")
    if set(declared) != set(ALLOWED_FORMULA_VERSIONS):
        raise RuntimeError("REPLAY_BASELINE_FAMILY_SET_MISMATCH")
    if any(
        schema != frame.data_schema_version or
        source_spec != frame.source_spec_version
        for _formula, schema, source_spec in declared.values()
    ):
        raise RuntimeError("REPLAY_LINEAGE_MISMATCH")
    known_horizons = set(HORIZON_SECONDS)
    if (set(targets_snapshot) - known_horizons or
            set(observations_snapshot) - known_horizons):
        raise ValueError("replay evidence contains an unknown horizon")
    targets: dict[str, tuple[RawTarget, ...]] = {}
    observations: dict[str, tuple[RawFamilyObservation, ...]] = {}
    for horizon in HORIZON_SECONDS:
        target_rows = targets_snapshot.get(horizon, ())
        observation_rows = observations_snapshot.get(horizon, ())
        if any(row.target_spec_id != TARGET_SPEC_ID for row in target_rows):
            raise RuntimeError("REPLAY_TARGET_SPEC_MISMATCH")
        if any(
            row.quant_id not in declared or
            row.formula_version != declared[row.quant_id][0]
            for row in observation_rows
        ):
            raise RuntimeError("REPLAY_FORMULA_LINEAGE_MISMATCH")
        if any(
            row.data_schema_version != frame.data_schema_version or
            row.source_spec_version != frame.source_spec_version
            for row in (*target_rows, *observation_rows)
        ):
            raise RuntimeError("REPLAY_LINEAGE_MISMATCH")
        if any(
            row.cutoff_epoch > state_as_of or
            row.maturity_epoch > state_as_of or
            row.resolved_epoch > state_as_of
            for row in target_rows
        ):
            raise RuntimeError("REPLAY_LOOKAHEAD_VIOLATION")
        if any(
            row.horizon != horizon or
            row.maturity_epoch != row.cutoff_epoch + HORIZON_SECONDS[horizon] or
            row.resolved_epoch < row.maturity_epoch or
            row.resolved_epoch > (
                row.maturity_epoch + MAX_TARGET_RESOLUTION_DELAY_SECONDS
            ) or
            not _same_rth_target_window(row.cutoff_epoch, row.maturity_epoch)
            for row in target_rows
        ):
            raise RuntimeError("REPLAY_TARGET_TIMING_VIOLATION")
        visible_identities = {
            (row.cycle_id, row.cutoff_epoch, row.maturity_epoch): row
            for row in target_rows
        }
        for row in observation_rows:
            times = (
                row.target_identity.cutoff_epoch,
                row.forecast_cutoff_epoch,
                row.source_as_of_epoch,
                row.available_epoch,
            )
            identity = (
                row.target_identity.cycle_id,
                row.target_identity.cutoff_epoch,
                row.target_identity.maturity_epoch,
            )
            if any(value > state_as_of for value in times):
                raise RuntimeError("REPLAY_LOOKAHEAD_VIOLATION")
            if identity not in visible_identities:
                raise RuntimeError("REPLAY_UNRESOLVED_OBSERVATION")
            target = visible_identities[identity]
            if not (
                row.horizon == horizon and
                row.target_identity.cutoff_epoch == row.forecast_cutoff_epoch ==
                target.cutoff_epoch and
                row.target_identity.maturity_epoch == target.maturity_epoch and
                row.source_as_of_epoch <= row.forecast_cutoff_epoch <=
                row.available_epoch < target.maturity_epoch and
                _rth_source_for_cutoff(
                    row.source_as_of_epoch, row.forecast_cutoff_epoch,
                ) and
                row.availability_state == "FRESH"
            ):
                raise RuntimeError("REPLAY_LOOKAHEAD_VIOLATION")
        targets[horizon] = target_rows
        observations[horizon] = observation_rows

    datasets = tuple(build_v2a_dataset(
        state_as_of=state_as_of,
        horizon=horizon,
        target_spec_id=TARGET_SPEC_ID,
        target_data_schema_version=frame.data_schema_version,
        target_source_spec_version=frame.source_spec_version,
        family_versions=versions,
        targets=targets[horizon],
        observations=observations[horizon],
    ) for horizon in HORIZON_SECONDS)
    calibration = build_v2b_calibration(datasets)
    covariances = tuple(
        build_v2c_covariance(dataset, calibration) for dataset in datasets
    )
    v2_state = build_v2d_evidence_state(
        state_as_of=state_as_of,
        datasets=datasets,
        calibrations=(calibration,),
        covariances=covariances,
    )
    historical_session = datetime.fromtimestamp(
        state_as_of, timezone.utc,
    ).astimezone(_EASTERN).date().isoformat()
    replay_hash = _replay_state_hash(
        replay_run_id=replay_run_id,
        historical_session=historical_session,
        source_spec_version=frame.source_spec_version,
        v2_state=v2_state,
    )
    return HistoricalReplayV2State(
        REPLAY_STATE_SCHEMA_VERSION, EVIDENCE_ORIGIN, replay_run_id,
        frame.replay_method_version, historical_session, frame.source,
        frame.data_schema_version, frame.source_spec_version, TARGET_SPEC_ID,
        v2_state, replay_hash, f"historical-v2:{replay_hash}",
    )


def _session_bounds(session_open: datetime, session_close: datetime) -> tuple[int, int]:
    open_ns, close_ns = _datetime_ns(session_open), _datetime_ns(session_close)
    if close_ns <= open_ns:
        raise ValueError("session_close must be after session_open")
    opened = session_open.astimezone(_EASTERN)
    closed = session_close.astimezone(_EASTERN)
    if (opened.date() != closed.date() or
            opened.timetz().replace(tzinfo=None) != time(9, 30) or
            closed.timetz().replace(tzinfo=None) != time(16, 0)):
        raise ValueError("historical replay requires one complete 09:30-16:00 ET session")
    return open_ns, close_ns


def _same_rth_target_window(cutoff_epoch: float, maturity_epoch: float) -> bool:
    cutoff = datetime.fromtimestamp(cutoff_epoch, timezone.utc).astimezone(_EASTERN)
    maturity = datetime.fromtimestamp(maturity_epoch, timezone.utc).astimezone(_EASTERN)
    cutoff_time = cutoff.timetz().replace(tzinfo=None)
    maturity_time = maturity.timetz().replace(tzinfo=None)
    return (cutoff.date() == maturity.date() and
            time(9, 30) <= cutoff_time < time(16, 0) and
            cutoff < maturity and maturity_time <= time(16, 0))


def _rth_source_for_cutoff(source_epoch: float, cutoff_epoch: float) -> bool:
    source = datetime.fromtimestamp(source_epoch, timezone.utc).astimezone(_EASTERN)
    cutoff = datetime.fromtimestamp(cutoff_epoch, timezone.utc).astimezone(_EASTERN)
    source_time = source.timetz().replace(tzinfo=None)
    return (source.date() == cutoff.date() and
            time(9, 30) <= source_time < time(16, 0))


def _monotonic_epoch(
    provider_event_ns: int, previous_epoch: float | None, cutoff_ns: int,
) -> float:
    """Project exact nanoseconds into the frozen float clock without collisions."""

    projected = provider_event_ns / _NANOSECONDS
    if previous_epoch is not None and projected <= previous_epoch:
        projected = math.nextafter(previous_epoch, math.inf)
    if projected > cutoff_ns / _NANOSECONDS:
        raise RuntimeError("REPLAY_TIMESTAMP_PRECISION_COLLISION")
    return projected


def _append_coin(
    history: MidpointHistory, observation: MidpointObservation,
) -> MidpointHistory:
    rows = history.observations + (observation,)
    if len(rows) > 1 and rows[-2].event_epoch >= observation.event_epoch:
        raise RuntimeError("REPLAY_TIMESTAMP_PRECISION_COLLISION")
    boundary = observation.event_epoch - _HISTORY_SECONDS
    first = next((i for i, row in enumerate(rows)
                  if row.event_epoch >= boundary), len(rows))
    return MidpointHistory(rows[max(0, first - 1):])


def _append_qqq(
    history: MidpointHistory, observation: MidpointObservation,
) -> MidpointHistory:
    rows = history.observations + (observation,)
    if len(rows) > 1 and rows[-2].event_epoch >= observation.event_epoch:
        raise RuntimeError("REPLAY_TIMESTAMP_PRECISION_COLLISION")
    return MidpointHistory(tuple(
        row for row in rows
        if row.event_epoch >= observation.event_epoch - _HISTORY_SECONDS
    ))


def _append_quote(
    history: QuoteHistory, observation: QuoteObservation,
) -> QuoteHistory:
    rows = history.observations + (observation,)
    if len(rows) > 1 and rows[-2].event_epoch >= observation.event_epoch:
        raise RuntimeError("REPLAY_TIMESTAMP_PRECISION_COLLISION")
    return QuoteHistory(tuple(
        row for row in rows
        if row.event_epoch >= observation.event_epoch - _QUOTE_HISTORY_SECONDS
    ))


__all__ = [
    "ALLOWED_FORMULA_VERSIONS", "ALPACA_HISTORICAL_QUOTES_URL",
    "AlpacaHistoricalSipReader",
    "DATA_SCHEMA_VERSION", "EVIDENCE_ORIGIN", "HistoricalReplayV2State",
    "HistoricalSipQuote", "HistoricalSipRetrievalProof",
    "MAX_TARGET_RESOLUTION_DELAY_SECONDS",
    "OneSessionReplayClock",
    "REPLAY_METHOD_VERSION", "ReplayFamilyResults", "ReplayFrame", "SOURCE",
    "REPLAY_STATE_SCHEMA_VERSION", "SOURCE_SPEC_ROUND_LOTS",
    "SOURCE_SPEC_SHARES", "TARGET_SPEC_ID",
    "build_replay_v2_as_of", "calculate_replay_families",
]
