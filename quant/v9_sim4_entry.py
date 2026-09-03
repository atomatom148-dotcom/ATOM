"""Exact immutable SIM-4 entry contracts and isolated persistence helpers.

The module is intentionally free of environment, clock, network, and
connection-opening behavior.  The dedicated worker supplies its already-open
authoritative PostgreSQL session and owns every transaction boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlsplit

from quant.v9_sim1_contract import (
    HORIZONS,
    HORIZON_SECONDS,
    IDENTITY_PREFIX as INTENT_ID_PREFIX,
    SimulationTradeIntent,
    deserialize_simulation_trade_intent,
    serialize_simulation_trade_intent,
)
from quant.v9_v4a_evidence import _canonical, _decanonical, canonical_sha256


SIM_EXECUTABLE_QUOTE_CONTRACT_VERSION = "ATOM_TRUE_V9_SIM4_QUOTE_1"
SIM_ENTRY_CONTRACT_VERSION = "ATOM_TRUE_V9_SIM4_ENTRY_1"
SIM_ENTRY_SCHEMA_VERSION = "ATOM_TRUE_V9_SIM4_SCHEMA_1"
SIM_ENTRY_STORE_VERSION = "ATOM_TRUE_V9_SIM4_STORE_1"
SIM_ENTRY_RUNTIME_VERSION = "ATOM_TRUE_V9_SIM4_RUNTIME_1"
SIM_CANONICALIZATION_VERSION = "ATOM_TRUE_V9_SIM_CANONICAL_V4A_1"
SIMULATOR_VERSION = "ATOM_TRUE_V9_SIM_1"
SIMULATION_MODE = "PAPER_ONLY"
SIM_ENTRY_TABLE = "public.atom_v9_sim_entries"
SIM_INSTALLATION_TABLE = "public.atom_v9_sim_installation"
SIM_PUBLICATION_TABLE = "public.atom_v9_sim_intent_publications"
SIM_CHECKPOINT_TABLE = "public.atom_v9_sim4_reconciliation_checkpoint"
SIM_INSTALLATION_ID = "ATOM_TRUE_V9_SIM_INSTALLATION_1"
SIM_RECONCILIATION_CHECKPOINT_KEY = "ATOM_TRUE_V9_SIM4_RECONCILIATION_1"
SIM_PUBLISHER_RUNTIME_ROLE = "atom_v9_sim_runtime"
SIM_ENTRY_RUNTIME_ROLE = "atom_v9_sim_entry_runtime"
SIM_RUNTIME_ROLE = SIM_ENTRY_RUNTIME_ROLE
SIM4_QUOTE_SOURCE_SPEC = "ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1"
QUOTE_ID_PREFIX = "v9simquote:"
ENTRY_ID_PREFIX = "v9simentry:"
SYMBOL = "COIN"
INSTRUMENT = "COIN_SHARE"
ENTRY_WINDOW_SECONDS = 2
SIM4_RECONCILIATION_PAGE_SIZE = 16
POSTGRES_BIGINT_MAX = 9223372036854775807

INSERTED = "INSERTED"
IDEMPOTENT = "IDEMPOTENT"

ENTRY_STATUSES = frozenset((
    "ENTERED",
    "SKIPPED_NO_TRADE",
    "SKIPPED_UNAVAILABLE",
    "SKIPPED_POSITION_OPEN",
    "SKIPPED_WINDOW_EXPIRED",
    "SKIPPED_RESTART_GAP",
))
HORIZON_ORDER = MappingProxyType({horizon: index + 1
                                  for index, horizon in enumerate(HORIZONS)})

SIM4_ADVISORY_LOCK_NAMESPACE = "ATOM_TRUE_V9_SIM4_ENTRY_LOCK_1"
_HORIZON_LOCK_KEYS = MappingProxyType({
    "30S": 1464455111187090143,
    "1M": -258020115535043520,
    "5M": -4937564732027059942,
    "15M": -1356851238941253914,
    "30M": -2824415193672952787,
    "1H": 6209627528392171927,
})

_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_PROJECT_REF_RE = re.compile(r"[a-z0-9]{20}\Z")
SIM_PROJECT_REF_PATTERN = r"[a-z0-9]{20}"
_ENTRY_ID_RE = re.compile(r"v9simentry:[0-9a-f]{64}\Z")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_ALLOWED_SSL_MODES = frozenset(("require", "verify-ca", "verify-full"))


class SimulationEntryError(RuntimeError):
    reason = "SIM4_ERROR"


class SimulationEntryConflictError(SimulationEntryError):
    reason = "SIM4_ENTRY_CONFLICT"


class SimulationEntryRowInvalidError(SimulationEntryError):
    reason = "SIM4_ROW_INVALID"


class SimulationEntryRoleError(SimulationEntryError):
    reason = "SIM4_ROLE_MISMATCH"


class SimulationEntryInstallationError(SimulationEntryError):
    reason = "SIM4_INSTALLATION_MISMATCH"


class SimulationEntryBackendError(SimulationEntryError):
    reason = "SIM4_BACKEND_CHANGED"


class SimulationEntryStateError(SimulationEntryError):
    reason = "SIM4_STATE_INVALID"


class SimulationDatabaseConfigurationError(SimulationEntryError):
    reason = "SIM4_DATABASE_CONFIGURATION"


def _aware_datetime(name: str, value: object) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None or
            value.utcoffset() is None):
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def _utc_datetime(name: str, value: object) -> datetime:
    result = _aware_datetime(name, value)
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be UTC")
    return result.astimezone(timezone.utc)


def _integer(name: str, value: object, *, minimum: int = 0,
             maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside its allowed range")
    return value


def _finite_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite binary64 value")
    return value


def datetime_to_epoch_microseconds(value: datetime) -> int:
    """Convert an aware datetime to exact integer UTC epoch microseconds."""
    normalized = _aware_datetime("value", value).astimezone(timezone.utc)
    delta = normalized - _EPOCH
    return ((delta.days * 86_400 + delta.seconds) * 1_000_000
            + delta.microseconds)


def datetime_to_epoch_nanoseconds(value: datetime) -> int:
    """Convert a Python datetime to its exact microsecond-aligned epoch ns."""
    return datetime_to_epoch_microseconds(value) * 1_000


def epoch_microseconds_to_datetime(value: int) -> datetime:
    """Convert exact integer epoch microseconds to a UTC datetime."""
    microseconds = _integer("value", value, minimum=-62_135_596_800_000_000)
    try:
        return _EPOCH + timedelta(microseconds=microseconds)
    except OverflowError as error:
        raise ValueError("epoch microseconds are outside datetime range") from error


def ceil_nanoseconds_to_microseconds(value: int) -> int:
    """Independently round a nonnegative nanosecond duration upward."""
    nanoseconds = _integer("value", value)
    return (nanoseconds + 999) // 1_000


def monotonic_derived_utc(*, anchor_utc: datetime,
                          anchor_monotonic_ns: int,
                          monotonic_now_ns: int) -> datetime:
    """Derive conservative UTC from one monotonic/UTC anchor pair."""
    anchor = _utc_datetime("anchor_utc", anchor_utc)
    anchor_ns = _integer("anchor_monotonic_ns", anchor_monotonic_ns)
    now_ns = _integer("monotonic_now_ns", monotonic_now_ns)
    if now_ns < anchor_ns:
        raise ValueError("monotonic clock moved backward")
    result_us = (datetime_to_epoch_microseconds(anchor)
                 + ceil_nanoseconds_to_microseconds(now_ns - anchor_ns))
    return epoch_microseconds_to_datetime(result_us)


@dataclass(frozen=True, slots=True)
class SimulationExecutableQuote:
    contract_version: str
    canonicalization_version: str
    quote_id: str
    quote_hash: str
    source_spec: str
    symbol: str
    provider_event_ns: int
    accepted_at: datetime
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    def __post_init__(self) -> None:
        _validate_quote(self)


_QUOTE_FIELD_NAMES = tuple(field.name for field in fields(SimulationExecutableQuote))
_QUOTE_HASH_FIELDS = tuple(name for name in _QUOTE_FIELD_NAMES
                           if name not in ("quote_id", "quote_hash"))


def _quote_math_payload(quote: SimulationExecutableQuote) -> dict[str, object]:
    values = asdict(quote)
    return {name: values[name] for name in _QUOTE_HASH_FIELDS}


def _validate_quote(quote: SimulationExecutableQuote) -> None:
    if quote.contract_version != SIM_EXECUTABLE_QUOTE_CONTRACT_VERSION:
        raise ValueError("invalid contract_version")
    if quote.canonicalization_version != SIM_CANONICALIZATION_VERSION:
        raise ValueError("invalid canonicalization_version")
    if quote.source_spec != SIM4_QUOTE_SOURCE_SPEC:
        raise ValueError("invalid source_spec")
    if quote.symbol != SYMBOL:
        raise ValueError("invalid symbol")
    _integer("provider_event_ns", quote.provider_event_ns,
             maximum=POSTGRES_BIGINT_MAX)
    _utc_datetime("accepted_at", quote.accepted_at)
    bid = _finite_float("bid", quote.bid)
    ask = _finite_float("ask", quote.ask)
    bid_size = _finite_float("bid_size", quote.bid_size)
    ask_size = _finite_float("ask_size", quote.ask_size)
    if bid <= 0.0:
        raise ValueError("bid must be positive")
    if ask < bid:
        raise ValueError("ask must not be below bid")
    if bid_size < 0.0 or ask_size < 0.0:
        raise ValueError("quote sizes must be nonnegative")
    if not isinstance(quote.quote_hash, str) or _HASH_RE.fullmatch(quote.quote_hash) is None:
        raise ValueError("invalid quote_hash")
    digest = canonical_sha256(_quote_math_payload(quote))
    if quote.quote_hash != digest or quote.quote_id != QUOTE_ID_PREFIX + digest:
        raise ValueError("quote mathematical identity mismatch")


def build_simulation_executable_quote(*, source_spec: str, symbol: str,
        provider_event_ns: int, accepted_at: datetime, bid: float, ask: float,
        bid_size: float, ask_size: float) -> SimulationExecutableQuote:
    """Build and deterministically identify one validated executable quote."""
    accepted = _aware_datetime("accepted_at", accepted_at).astimezone(timezone.utc)
    values: dict[str, object] = {
        "contract_version": SIM_EXECUTABLE_QUOTE_CONTRACT_VERSION,
        "canonicalization_version": SIM_CANONICALIZATION_VERSION,
        "source_spec": source_spec,
        "symbol": symbol,
        "provider_event_ns": provider_event_ns,
        "accepted_at": accepted,
        "bid": bid,
        "ask": ask,
        "bid_size": bid_size,
        "ask_size": ask_size,
    }
    digest = canonical_sha256(values)
    return SimulationExecutableQuote(quote_id=QUOTE_ID_PREFIX + digest,
                                     quote_hash=digest,
                                     **values)  # type: ignore[arg-type]


def serialize_simulation_executable_quote(quote: SimulationExecutableQuote) -> str:
    if not isinstance(quote, SimulationExecutableQuote):
        raise ValueError("quote must be a SimulationExecutableQuote")
    _validate_quote(quote)
    return json.dumps(_canonical(asdict(quote)), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True)


def deserialize_simulation_executable_quote(
        payload: str | Mapping[str, object]) -> SimulationExecutableQuote:
    try:
        canonical = json.loads(payload) if isinstance(payload, str) else dict(payload)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("quote payload is not valid JSON") from error
    if not isinstance(canonical, dict) or set(canonical) != set(_QUOTE_FIELD_NAMES):
        raise ValueError("quote payload has missing or unknown fields")
    try:
        value = _decanonical(canonical)
        if not isinstance(value, dict) or set(value) != set(_QUOTE_FIELD_NAMES):
            raise ValueError("quote payload does not match the contract")
        quote = SimulationExecutableQuote(**value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("quote payload does not match the contract") from error
    if canonical != json.loads(serialize_simulation_executable_quote(quote)):
        raise ValueError("quote payload is not canonical")
    return quote


@dataclass(frozen=True, slots=True)
class SimulationEntryRecord:
    contract_version: str
    canonicalization_version: str
    simulator_version: str
    entry_id: str
    entry_hash: str
    mode: str
    symbol: str
    instrument: str
    intent_id: str
    intent_hash: str
    source_cycle_id: str
    cutoff_at: datetime
    publication_at: datetime
    entry_deadline_at: datetime
    horizon: str
    horizon_seconds: int
    decision: str
    intent_status: str
    entry_status: str
    quantity_shares: int
    blocking_entry_id: str | None
    quote: SimulationExecutableQuote | None
    entry_price: float | None

    def __post_init__(self) -> None:
        _validate_entry(self)


_ENTRY_FIELD_NAMES = tuple(field.name for field in fields(SimulationEntryRecord))
_ENTRY_HASH_FIELDS = tuple(name for name in _ENTRY_FIELD_NAMES
                           if name not in ("entry_id", "entry_hash"))


def _entry_math_payload(entry: SimulationEntryRecord) -> dict[str, object]:
    values = asdict(entry)
    return {name: values[name] for name in _ENTRY_HASH_FIELDS}


def _validate_entry(entry: SimulationEntryRecord) -> None:
    exact = {
        "contract_version": SIM_ENTRY_CONTRACT_VERSION,
        "canonicalization_version": SIM_CANONICALIZATION_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "mode": SIMULATION_MODE,
        "symbol": SYMBOL,
        "instrument": INSTRUMENT,
    }
    for name, expected in exact.items():
        if getattr(entry, name) != expected:
            raise ValueError(f"invalid {name}")
    if not isinstance(entry.entry_hash, str) or _HASH_RE.fullmatch(entry.entry_hash) is None:
        raise ValueError("invalid entry_hash")
    if not isinstance(entry.entry_id, str) or _ENTRY_ID_RE.fullmatch(entry.entry_id) is None:
        raise ValueError("invalid entry_id")
    if not isinstance(entry.intent_id, str) or not entry.intent_id:
        raise ValueError("intent_id must be a nonempty string")
    if not isinstance(entry.intent_hash, str) or _HASH_RE.fullmatch(entry.intent_hash) is None:
        raise ValueError("invalid intent_hash")
    if entry.intent_id != INTENT_ID_PREFIX + entry.intent_hash:
        raise ValueError("intent identity pair is invalid")
    if not isinstance(entry.source_cycle_id, str) or not entry.source_cycle_id:
        raise ValueError("source_cycle_id must be a nonempty string")
    _aware_datetime("cutoff_at", entry.cutoff_at)
    publication = _utc_datetime("publication_at", entry.publication_at)
    if publication < entry.cutoff_at:
        raise ValueError("publication_at must not precede cutoff_at")
    deadline = _utc_datetime("entry_deadline_at", entry.entry_deadline_at)
    if deadline != publication + timedelta(seconds=ENTRY_WINDOW_SECONDS):
        raise ValueError("entry deadline must be exactly two seconds after publication")
    if entry.horizon not in HORIZON_SECONDS:
        raise ValueError("invalid horizon")
    if (isinstance(entry.horizon_seconds, bool) or
            not isinstance(entry.horizon_seconds, int) or
            entry.horizon_seconds != HORIZON_SECONDS[entry.horizon]):
        raise ValueError("invalid horizon_seconds")
    if entry.decision not in ("LONG", "SHORT", "NO_TRADE"):
        raise ValueError("invalid decision")
    if entry.intent_status not in ("ACTIONABLE", "NO_TRADE", "UNAVAILABLE"):
        raise ValueError("invalid intent_status")
    if entry.entry_status not in ENTRY_STATUSES:
        raise ValueError("invalid entry_status")
    _integer("quantity_shares", entry.quantity_shares)

    if entry.entry_status == "ENTERED":
        if (entry.intent_status != "ACTIONABLE" or
                entry.decision not in ("LONG", "SHORT") or
                entry.quantity_shares != 1 or
                entry.blocking_entry_id is not None or
                not isinstance(entry.quote, SimulationExecutableQuote) or
                entry.entry_price is None):
            raise ValueError("invalid ENTERED fields")
        _finite_float("entry_price", entry.entry_price)
        if entry.entry_price <= 0.0:
            raise ValueError("entry_price must be positive")
        if not _quote_is_executable(entry.decision, publication, deadline, entry.quote):
            raise ValueError("ENTERED quote is not executable inside the entry window")
        expected_price = entry.quote.ask if entry.decision == "LONG" else entry.quote.bid
        if entry.entry_price != expected_price:
            raise ValueError("entry_price does not match executable quote side")
    elif entry.entry_status == "SKIPPED_POSITION_OPEN":
        if (entry.intent_status != "ACTIONABLE" or
                entry.decision not in ("LONG", "SHORT") or
                entry.quantity_shares != 0 or entry.quote is not None or
                entry.entry_price is not None or
                not isinstance(entry.blocking_entry_id, str) or
                _ENTRY_ID_RE.fullmatch(entry.blocking_entry_id) is None):
            raise ValueError("invalid SKIPPED_POSITION_OPEN fields")
    else:
        if (entry.quantity_shares != 0 or entry.blocking_entry_id is not None or
                entry.quote is not None or entry.entry_price is not None):
            raise ValueError("skipped entry contains forbidden executable fields")
        expected = {
            "SKIPPED_NO_TRADE": ("NO_TRADE", "NO_TRADE"),
            "SKIPPED_UNAVAILABLE": ("UNAVAILABLE", "NO_TRADE"),
            "SKIPPED_WINDOW_EXPIRED": ("ACTIONABLE", entry.decision),
            "SKIPPED_RESTART_GAP": ("ACTIONABLE", entry.decision),
        }[entry.entry_status]
        if entry.intent_status != expected[0]:
            raise ValueError("entry status does not match source intent status")
        if (entry.entry_status in ("SKIPPED_WINDOW_EXPIRED", "SKIPPED_RESTART_GAP")
                and entry.decision not in ("LONG", "SHORT")):
            raise ValueError("actionable skipped entry has invalid decision")
        if (entry.entry_status in ("SKIPPED_NO_TRADE", "SKIPPED_UNAVAILABLE")
                and entry.decision != "NO_TRADE"):
            raise ValueError("non-actionable skipped entry has invalid decision")

    digest = canonical_sha256(_entry_math_payload(entry))
    if entry.entry_hash != digest or entry.entry_id != ENTRY_ID_PREFIX + digest:
        raise ValueError("entry mathematical identity mismatch")


def _quote_is_executable(decision: str, publication_at: datetime,
                         deadline_at: datetime,
                         quote: SimulationExecutableQuote) -> bool:
    try:
        _validate_quote(quote)
    except ValueError:
        return False
    publication_ns = datetime_to_epoch_nanoseconds(publication_at)
    deadline_ns = datetime_to_epoch_nanoseconds(deadline_at)
    accepted_ns = datetime_to_epoch_nanoseconds(quote.accepted_at)
    if not (publication_ns < quote.provider_event_ns <= deadline_ns):
        return False
    if not (publication_ns <= accepted_ns <= deadline_ns):
        return False
    if quote.provider_event_ns > accepted_ns:
        return False
    if decision == "LONG":
        return quote.ask_size >= 1.0
    if decision == "SHORT":
        return quote.bid_size >= 1.0
    return False


def quote_is_executable_for_intent(intent: SimulationTradeIntent,
                                   quote: SimulationExecutableQuote) -> bool:
    if not isinstance(intent, SimulationTradeIntent) or intent.status != "ACTIONABLE":
        return False
    publication = intent.eligible_at.astimezone(timezone.utc)
    return _quote_is_executable(intent.decision, publication,
                                publication + timedelta(seconds=ENTRY_WINDOW_SECONDS),
                                quote)


def select_executable_quote(intent: SimulationTradeIntent,
                            quotes: Iterable[SimulationExecutableQuote]
                            ) -> SimulationExecutableQuote | None:
    """Select the complete frozen first-quote tuple for one intent."""
    if not isinstance(intent, SimulationTradeIntent):
        raise ValueError("intent must be a SimulationTradeIntent")
    eligible = [quote for quote in quotes
                if isinstance(quote, SimulationExecutableQuote)
                and quote_is_executable_for_intent(intent, quote)]
    if not eligible:
        return None
    return min(eligible, key=lambda quote: (
        datetime_to_epoch_microseconds(quote.accepted_at),
        quote.provider_event_ns,
        quote.quote_id,
    ))


def build_simulation_entry_record(*, intent: SimulationTradeIntent,
        entry_status: str, quote: SimulationExecutableQuote | None = None,
        blocking_entry_id: str | None = None) -> SimulationEntryRecord:
    """Build one exact terminal entry result from an immutable SIM-1 intent."""
    if not isinstance(intent, SimulationTradeIntent):
        raise ValueError("intent must be a SimulationTradeIntent")
    publication = intent.eligible_at.astimezone(timezone.utc)
    cutoff = intent.cutoff_at.astimezone(timezone.utc)
    if entry_status == "ENTERED":
        quantity = 1
        price = (quote.ask if intent.decision == "LONG" and quote is not None
                 else quote.bid if intent.decision == "SHORT" and quote is not None
                 else None)
    else:
        quantity = 0
        price = None
    values: dict[str, object] = {
        "contract_version": SIM_ENTRY_CONTRACT_VERSION,
        "canonicalization_version": SIM_CANONICALIZATION_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "mode": SIMULATION_MODE,
        "symbol": SYMBOL,
        "instrument": INSTRUMENT,
        "intent_id": intent.intent_id,
        "intent_hash": intent.intent_hash,
        "source_cycle_id": intent.source_cycle_id,
        "cutoff_at": cutoff,
        "publication_at": publication,
        "entry_deadline_at": publication + timedelta(seconds=ENTRY_WINDOW_SECONDS),
        "horizon": intent.horizon,
        "horizon_seconds": intent.horizon_seconds,
        "decision": intent.decision,
        "intent_status": intent.status,
        "entry_status": entry_status,
        "quantity_shares": quantity,
        "blocking_entry_id": blocking_entry_id,
        "quote": quote,
        "entry_price": price,
    }
    digest = canonical_sha256(values)
    return SimulationEntryRecord(entry_id=ENTRY_ID_PREFIX + digest,
                                 entry_hash=digest,
                                 **values)  # type: ignore[arg-type]


def validate_entry_matches_intent(entry: SimulationEntryRecord,
                                  intent: SimulationTradeIntent) -> None:
    """Prove every entry field copied from its immutable source intent."""
    if not isinstance(entry, SimulationEntryRecord):
        raise ValueError("entry must be a SimulationEntryRecord")
    if not isinstance(intent, SimulationTradeIntent):
        raise ValueError("intent must be a SimulationTradeIntent")
    expected = {
        "intent_id": intent.intent_id,
        "intent_hash": intent.intent_hash,
        "source_cycle_id": intent.source_cycle_id,
        "cutoff_at": intent.cutoff_at,
        "publication_at": intent.eligible_at,
        "horizon": intent.horizon,
        "horizon_seconds": intent.horizon_seconds,
        "decision": intent.decision,
        "intent_status": intent.status,
    }
    for name, value in expected.items():
        if getattr(entry, name) != value:
            raise ValueError(f"entry {name} does not match immutable intent")


def serialize_simulation_entry_record(entry: SimulationEntryRecord) -> str:
    if not isinstance(entry, SimulationEntryRecord):
        raise ValueError("entry must be a SimulationEntryRecord")
    _validate_entry(entry)
    return json.dumps(_canonical(asdict(entry)), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True)


def deserialize_simulation_entry_record(
        payload: str | Mapping[str, object]) -> SimulationEntryRecord:
    try:
        canonical = json.loads(payload) if isinstance(payload, str) else dict(payload)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("entry payload is not valid JSON") from error
    if not isinstance(canonical, dict) or set(canonical) != set(_ENTRY_FIELD_NAMES):
        raise ValueError("entry payload has missing or unknown fields")
    try:
        value = _decanonical(canonical)
        if not isinstance(value, dict) or set(value) != set(_ENTRY_FIELD_NAMES):
            raise ValueError("entry payload does not match the contract")
        nested = value.get("quote")
        if nested is not None:
            if not isinstance(nested, dict) or set(nested) != set(_QUOTE_FIELD_NAMES):
                raise ValueError("entry quote does not match the contract")
            value["quote"] = SimulationExecutableQuote(**nested)
        entry = SimulationEntryRecord(**value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("entry payload does not match the contract") from error
    if canonical != json.loads(serialize_simulation_entry_record(entry)):
        raise ValueError("entry payload is not canonical")
    return entry


def horizon_advisory_lock_key(horizon: str) -> int:
    """Return and independently verify the frozen signed-bigint lock key."""
    if horizon not in HORIZON_SECONDS:
        raise ValueError("invalid horizon")
    payload = (b"ATOM_TRUE_V9_SIM4_ENTRY_LOCK_1\x00COIN\x00"
               + horizon.encode("ascii"))
    unsigned = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    calculated = unsigned if unsigned < 2 ** 63 else unsigned - 2 ** 64
    if calculated != _HORIZON_LOCK_KEYS[horizon]:
        raise RuntimeError("SIM-4 advisory-lock key invariant failed")
    return calculated


@dataclass(frozen=True, slots=True)
class SimulatorDatabaseIdentity:
    project_ref: str
    role: str
    endpoint_kind: str
    hostname: str
    port: int
    database: str


def _split_database_url(database_url: str):
    if not isinstance(database_url, str) or not database_url or database_url != database_url.strip():
        raise SimulationDatabaseConfigurationError("database URL is missing or malformed")
    try:
        parsed = urlsplit(database_url)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise SimulationDatabaseConfigurationError("database URL is malformed") from error
    if parsed.scheme not in ("postgres", "postgresql") or parsed.hostname is None:
        raise SimulationDatabaseConfigurationError("database URL must be PostgreSQL")
    raw_host_port = parsed.netloc.rsplit("@", 1)[-1]
    raw_hostname = raw_host_port.rsplit(":", 1)[0]
    if raw_hostname != parsed.hostname or raw_hostname != raw_hostname.lower():
        raise SimulationDatabaseConfigurationError(
            "database hostname must use exact lowercase DNS form")
    return parsed, parsed.hostname, port


def discover_supabase_project_ref(database_url: str) -> str | None:
    """Discover an exact Supabase project ref without trusting query data."""
    parsed, hostname, _ = _split_database_url(database_url)
    direct = re.fullmatch(r"db\.([a-z0-9]{20})\.supabase\.co", hostname)
    if direct is not None:
        return direct.group(1)
    if hostname.endswith(".supabase.co") and hostname.startswith("db."):
        raise SimulationDatabaseConfigurationError("malformed Supabase direct project identity")
    if hostname.endswith(".pooler.supabase.com"):
        username = parsed.username
        if not isinstance(username, str):
            raise SimulationDatabaseConfigurationError("pooler username is missing")
        pieces = username.split(".")
        if len(pieces) != 2 or _PROJECT_REF_RE.fullmatch(pieces[1]) is None:
            raise SimulationDatabaseConfigurationError("malformed Supabase pooler project identity")
        return pieces[1]
    if hostname.endswith(".supabase.com"):
        raise SimulationDatabaseConfigurationError("unrecognized Supabase database endpoint")
    return None


def validate_simulator_database_url(database_url: str, *, project_ref: str,
        required_role: str) -> SimulatorDatabaseIdentity:
    """Validate one direct or session-mode isolated Supabase runtime DSN."""
    if not isinstance(project_ref, str) or _PROJECT_REF_RE.fullmatch(project_ref) is None:
        raise SimulationDatabaseConfigurationError("simulator project ref is malformed")
    if required_role not in (SIM_PUBLISHER_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE):
        raise SimulationDatabaseConfigurationError("simulator database role is not authorized")
    parsed, hostname, port = _split_database_url(database_url)
    if parsed.fragment or parsed.path != "/postgres" or port != 5432:
        raise SimulationDatabaseConfigurationError(
            "simulator database requires database postgres on explicit port 5432")
    if parsed.username is None or parsed.password is None or not parsed.password:
        raise SimulationDatabaseConfigurationError("simulator database credentials are incomplete")
    try:
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise SimulationDatabaseConfigurationError("database URL query is malformed") from error
    if len(query) != 1 or query[0][0] != "sslmode" or query[0][1] not in _ALLOWED_SSL_MODES:
        raise SimulationDatabaseConfigurationError(
            "simulator database requires an unambiguous mandatory TLS mode")

    direct_hostname = f"db.{project_ref}.supabase.co"
    if hostname == direct_hostname:
        if parsed.username != required_role:
            raise SimulationDatabaseConfigurationError("direct database role mismatch")
        endpoint_kind = "DIRECT"
    elif hostname.endswith(".pooler.supabase.com"):
        prefix = hostname[:-len(".pooler.supabase.com")]
        if not prefix or re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*", prefix) is None:
            raise SimulationDatabaseConfigurationError("pooler hostname is malformed")
        if parsed.username != f"{required_role}.{project_ref}":
            raise SimulationDatabaseConfigurationError("session-pooler role or project mismatch")
        endpoint_kind = "SESSION_POOLER"
    else:
        raise SimulationDatabaseConfigurationError(
            "simulator database must use an allowed Supabase endpoint")
    discovered = discover_supabase_project_ref(database_url)
    if discovered != project_ref:
        raise SimulationDatabaseConfigurationError("simulator database project mismatch")
    return SimulatorDatabaseIdentity(project_ref, required_role, endpoint_kind,
                                     hostname, port, "postgres")


@dataclass(frozen=True, slots=True)
class PublicationCursor:
    publication_at: datetime
    horizon_order: int
    intent_id: str
    publication_seq: int

    def __post_init__(self) -> None:
        _utc_datetime("publication_at", self.publication_at)
        _integer("horizon_order", self.horizon_order, minimum=1, maximum=6)
        if not isinstance(self.intent_id, str) or not self.intent_id:
            raise ValueError("intent_id must be a nonempty string")
        _integer("publication_seq", self.publication_seq, minimum=1,
                 maximum=POSTGRES_BIGINT_MAX)


@dataclass(frozen=True, slots=True)
class PublishedSimulationIntent:
    publication_seq: int
    admitted_at: datetime
    publication_at: datetime
    horizon_order: int
    intent: SimulationTradeIntent

    def __post_init__(self) -> None:
        _integer("publication_seq", self.publication_seq, minimum=1,
                 maximum=POSTGRES_BIGINT_MAX)
        _utc_datetime("admitted_at", self.admitted_at)
        publication = _utc_datetime("publication_at", self.publication_at)
        if not isinstance(self.intent, SimulationTradeIntent):
            raise ValueError("intent must be a SimulationTradeIntent")
        if publication != self.intent.eligible_at:
            raise ValueError("publication_at does not equal intent eligible_at")
        _integer("horizon_order", self.horizon_order, minimum=1, maximum=6)
        if self.horizon_order != HORIZON_ORDER[self.intent.horizon]:
            raise ValueError("publication horizon order mismatch")

    @property
    def cursor(self) -> PublicationCursor:
        return PublicationCursor(self.publication_at, self.horizon_order,
                                 self.intent.intent_id, self.publication_seq)


@dataclass(frozen=True, slots=True)
class ReconciliationCheckpoint:
    checkpoint_key: str
    last_completed_publication_seq: int
    checkpoint_version: int
    runtime_started_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.checkpoint_key != SIM_RECONCILIATION_CHECKPOINT_KEY:
            raise ValueError("checkpoint key mismatch")
        _integer("last_completed_publication_seq",
                 self.last_completed_publication_seq,
                 maximum=POSTGRES_BIGINT_MAX)
        _integer("checkpoint_version", self.checkpoint_version,
                 maximum=POSTGRES_BIGINT_MAX)
        if self.runtime_started_at is not None:
            _utc_datetime("runtime_started_at", self.runtime_started_at)
        _utc_datetime("updated_at", self.updated_at)


_ENTRY_COLUMNS = (
    "entry_id", "entry_hash", "contract_version", "canonicalization_version",
    "simulator_version", "symbol", "horizon", "horizon_seconds", "intent_id",
    "publication_at", "entry_deadline_at", "decision", "intent_status",
    "entry_status", "quantity_shares", "blocking_entry_id", "quote_id",
    "quote_hash", "quote_source_spec", "quote_event_ns", "quote_accepted_at",
    "entry_price", "record_json",
)
_ENTRY_SELECT = "SELECT " + ", ".join(_ENTRY_COLUMNS) + " FROM " + SIM_ENTRY_TABLE + " AS e"
_RESOLUTION_TARGET_EPOCH_NS_SQL = (
    "(((EXTRACT(EPOCH FROM r.resolution_target_at) * 1000000)::bigint) * 1000)"
)
_RESOLUTION_DEADLINE_EPOCH_NS_SQL = (
    "(((EXTRACT(EPOCH FROM r.resolution_deadline_at) * 1000000)::bigint) * 1000)"
)
_VALID_TERMINAL_RESOLUTION_CLAUSE = (
    "("
    "r.resolution_hash ~ '^[0-9a-f]{64}$' "
    "AND r.resolution_id = 'v9simresolution:' || r.resolution_hash "
    "AND r.contract_version = 'ATOM_TRUE_V9_SIM5_RESOLUTION_1' "
    "AND r.canonicalization_version = 'ATOM_TRUE_V9_SIM_CANONICAL_V4A_1' "
    "AND r.simulator_version = 'ATOM_TRUE_V9_SIM_1' "
    "AND r.mode = 'PAPER_ONLY' "
    "AND r.symbol = 'COIN' "
    "AND r.instrument = 'COIN_SHARE' "
    "AND r.entry_hash ~ '^[0-9a-f]{64}$' "
    "AND r.entry_id = 'v9simentry:' || r.entry_hash "
    "AND (r.horizon, r.horizon_seconds) IN "
    "(('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900), ('30M', 1800), ('1H', 3600)) "
    "AND r.decision IN ('LONG', 'SHORT') "
    "AND r.entry_quote_hash ~ '^[0-9a-f]{64}$' "
    "AND r.entry_quote_id = 'v9simquote:' || r.entry_quote_hash "
    "AND r.entry_price > 0 "
    "AND r.entry_price NOT IN ('NaN'::double precision, '-Infinity'::double precision, "
    "'Infinity'::double precision) "
    "AND r.cutoff_at NOT IN ('-infinity'::timestamptz, 'infinity'::timestamptz) "
    "AND r.resolution_target_at = r.cutoff_at + make_interval(secs => r.horizon_seconds) "
    "AND r.resolution_deadline_at = r.resolution_target_at + interval '2 seconds' "
    "AND r.resolution_status IN ('RESOLVED', 'UNRESOLVED_WINDOW_EXPIRED', "
    "'UNRESOLVED_OBSERVATION_GAP') "
    "AND jsonb_typeof(r.record_json) = 'object' "
    "AND jsonb_object_length(r.record_json) = 24 "
    "AND r.record_json ?& ARRAY['contract_version', 'canonicalization_version', "
    "'simulator_version', 'resolution_id', 'resolution_hash', 'mode', 'symbol', "
    "'instrument', 'entry_id', 'entry_hash', 'source_cycle_id', 'cutoff_at', "
    "'horizon', 'horizon_seconds', 'decision', 'entry_quote_id', 'entry_quote_hash', "
    "'entry_price', 'resolution_target_at', 'resolution_deadline_at', "
    "'resolution_status', 'exit_quote', 'exit_price', 'return_bps'] "
    "AND r.record_json ->> 'contract_version' = r.contract_version "
    "AND r.record_json ->> 'canonicalization_version' = r.canonicalization_version "
    "AND r.record_json ->> 'simulator_version' = r.simulator_version "
    "AND r.record_json ->> 'resolution_id' = r.resolution_id "
    "AND r.record_json ->> 'resolution_hash' = r.resolution_hash "
    "AND r.record_json ->> 'mode' = r.mode "
    "AND r.record_json ->> 'symbol' = r.symbol "
    "AND r.record_json ->> 'instrument' = r.instrument "
    "AND r.record_json ->> 'entry_id' = r.entry_id "
    "AND r.record_json ->> 'entry_hash' = r.entry_hash "
    "AND r.record_json ->> 'source_cycle_id' = r.source_cycle_id "
    "AND r.record_json #>> '{cutoff_at,$timestamp_utc}' = "
    "to_char(r.cutoff_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
    "AND r.record_json ->> 'horizon' = r.horizon "
    "AND r.record_json ->> 'horizon_seconds' = r.horizon_seconds::text "
    "AND r.record_json ->> 'decision' = r.decision "
    "AND r.record_json ->> 'entry_quote_id' = r.entry_quote_id "
    "AND r.record_json ->> 'entry_quote_hash' = r.entry_quote_hash "
    "AND r.record_json #>> '{resolution_target_at,$timestamp_utc}' = "
    "to_char(r.resolution_target_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
    "AND r.record_json #>> '{resolution_deadline_at,$timestamp_utc}' = "
    "to_char(r.resolution_deadline_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
    "AND r.record_json ->> 'resolution_status' = r.resolution_status "
    "AND ("
    "("
    "r.resolution_status = 'RESOLVED' "
    "AND r.exit_quote_id IS NOT NULL "
    "AND r.exit_quote_hash ~ '^[0-9a-f]{64}$' "
    "AND r.exit_quote_id = 'v9simquote:' || r.exit_quote_hash "
    "AND r.exit_quote_source_spec = 'ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1' "
    "AND r.exit_quote_event_ns IS NOT NULL "
    "AND r.exit_quote_event_ns BETWEEN " + _RESOLUTION_TARGET_EPOCH_NS_SQL + " AND "
    + _RESOLUTION_DEADLINE_EPOCH_NS_SQL + " "
    "AND r.exit_quote_accepted_at IS NOT NULL "
    "AND r.exit_quote_accepted_at NOT IN ('-infinity'::timestamptz, 'infinity'::timestamptz) "
    "AND r.exit_quote_accepted_at BETWEEN r.resolution_target_at AND r.resolution_deadline_at "
    "AND r.exit_price IS NOT NULL "
    "AND r.exit_price > 0 "
    "AND r.exit_price NOT IN ('NaN'::double precision, '-Infinity'::double precision, "
    "'Infinity'::double precision) "
    "AND r.return_bps IS NOT NULL "
    "AND r.return_bps NOT IN ('NaN'::double precision, '-Infinity'::double precision, "
    "'Infinity'::double precision) "
    "AND jsonb_typeof(r.record_json -> 'exit_quote') = 'object' "
    "AND r.record_json #>> '{exit_quote,quote_id}' = r.exit_quote_id "
    "AND r.record_json #>> '{exit_quote,quote_hash}' = r.exit_quote_hash "
    "AND r.record_json #>> '{exit_quote,source_spec}' = r.exit_quote_source_spec "
    "AND r.record_json #>> '{exit_quote,provider_event_ns}' = r.exit_quote_event_ns::text "
    "AND r.record_json #>> '{exit_quote,accepted_at,$timestamp_utc}' = "
    "to_char(r.exit_quote_accepted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
    ") OR ("
    "r.resolution_status IN ('UNRESOLVED_WINDOW_EXPIRED', 'UNRESOLVED_OBSERVATION_GAP') "
    "AND r.exit_quote_id IS NULL "
    "AND r.exit_quote_hash IS NULL "
    "AND r.exit_quote_source_spec IS NULL "
    "AND r.exit_quote_event_ns IS NULL "
    "AND r.exit_quote_accepted_at IS NULL "
    "AND r.exit_price IS NULL "
    "AND r.return_bps IS NULL "
    "AND r.record_json -> 'exit_quote' = 'null'::jsonb "
    "AND r.record_json -> 'exit_price' = 'null'::jsonb "
    "AND r.record_json -> 'return_bps' = 'null'::jsonb"
    "))"
    ")"
)
# A durably resolved entry no longer occupies its horizon (SIM-5 freeze,
# docs/sim-4a-exact-sim5-resolution-freeze.md section 10: "minimum
# query/locking change needed so a durably resolved entry no longer blocks
# its horizon").  This also bounds worker startup/recovery to unresolved
# ENTERED rows without any separate query (freeze section 9), since
# load_open_occupancy_on_cursor is exactly the method the worker calls at
# startup.  atom_v9_sim_resolutions does not exist before migration 031 is
# applied and SIM-5 is activated only behind ATOM_V9_SIM5_ENABLED=true; this
# anti-join is unconditional so it must be present the moment 031 lands.
_ENTRY_NOT_RESOLVED_CLAUSE = (
    " AND NOT EXISTS (SELECT 1 FROM public.atom_v9_sim_resolutions AS r "
    "WHERE r.entry_id = e.entry_id AND " + _VALID_TERMINAL_RESOLUTION_CLAUSE + ")"
)
_INTENT_COLUMNS = (
    "intent_id", "intent_hash", "contract_version", "canonicalization_version",
    "simulator_version", "symbol", "horizon", "horizon_seconds", "cutoff_at",
    "eligible_at", "source_v3_status", "decision", "status", "record_json",
)


class SimulationEntryStore:
    """Cursor-scoped access on the worker's already-owned backend session.

    This class never opens or closes a connection and never commits or rolls
    back.  The worker retains sole authority over the owner session and every
    explicit transaction boundary.
    """

    def __init__(self, connection, *, project_ref: str,
                 expected_backend_pid: int | None = None):
        if connection is None:
            raise TypeError("connection is required")
        if not isinstance(project_ref, str) or _PROJECT_REF_RE.fullmatch(project_ref) is None:
            raise ValueError("project_ref must be lowercase 20-character identity")
        if expected_backend_pid is not None:
            _integer("expected_backend_pid", expected_backend_pid, minimum=1)
        self._connection = connection
        self._project_ref = project_ref
        self._backend_pid = expected_backend_pid

    @property
    def backend_pid(self) -> int | None:
        return self._backend_pid

    @staticmethod
    def _fetchall(cursor):
        rows = cursor.fetchall()
        return [] if rows is None else list(rows)

    def _verify_authority_on_cursor(self, cursor) -> int:
        cursor.execute("SELECT current_user, session_user, pg_backend_pid()")
        row = cursor.fetchone()
        if row is None or len(row) != 3:
            raise SimulationEntryRoleError("database authority result is malformed")
        if row[0] != SIM_ENTRY_RUNTIME_ROLE or row[1] != SIM_ENTRY_RUNTIME_ROLE:
            raise SimulationEntryRoleError("database role does not match SIM-4 entry runtime")
        try:
            pid = _integer("pg_backend_pid", row[2], minimum=1)
        except ValueError as error:
            raise SimulationEntryBackendError("database backend PID is malformed") from error
        if self._backend_pid is None:
            self._backend_pid = pid
        elif pid != self._backend_pid:
            raise SimulationEntryBackendError("authoritative database backend changed")
        return pid

    def verify_startup_on_cursor(self, cursor) -> int:
        """Verify exact role, installation, backend, and sidecar completeness."""
        pid = self._verify_authority_on_cursor(cursor)
        cursor.execute(
            "SELECT installation_id, project_ref FROM public.atom_v9_sim_installation "
            "ORDER BY installation_id"
        )
        rows = self._fetchall(cursor)
        if rows != [(SIM_INSTALLATION_ID, self._project_ref)]:
            raise SimulationEntryInstallationError("simulator installation identity mismatch")
        cursor.execute(
            "SELECT NOT EXISTS ("
            "SELECT 1 FROM public.atom_v9_sim_intents i "
            "LEFT JOIN public.atom_v9_sim_intent_publications p "
            "ON p.intent_id = i.intent_id WHERE p.intent_id IS NULL), "
            "NOT EXISTS (SELECT 1 FROM public.atom_v9_sim_intent_publications p "
            "LEFT JOIN public.atom_v9_sim_intents i ON i.intent_id = p.intent_id "
            "WHERE i.intent_id IS NULL)"
        )
        completeness = cursor.fetchone()
        if completeness != (True, True):
            raise SimulationEntryStateError("intent publication sidecar is incomplete")
        return pid

    def verify_startup(self) -> int:
        cursor = self._connection.cursor()
        try:
            return self.verify_startup_on_cursor(cursor)
        finally:
            cursor.close()

    @staticmethod
    def _decode_intent_columns(row) -> SimulationTradeIntent:
        if row is None or len(row) != len(_INTENT_COLUMNS):
            raise SimulationEntryRowInvalidError("stored intent row has invalid shape")
        values = dict(zip(_INTENT_COLUMNS, row))
        payload = values["record_json"]
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            intent = deserialize_simulation_trade_intent(payload)
            if payload != json.loads(serialize_simulation_trade_intent(intent)):
                raise ValueError("intent JSON is not canonical")
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise SimulationEntryRowInvalidError("stored intent payload is invalid") from error
        for name in _INTENT_COLUMNS[:-1]:
            if values[name] != getattr(intent, name):
                raise SimulationEntryRowInvalidError(
                    f"stored intent column {name} does not match payload")
        return intent

    @staticmethod
    def _decode_entry_row(row) -> SimulationEntryRecord:
        if row is None or len(row) != len(_ENTRY_COLUMNS):
            raise SimulationEntryRowInvalidError("stored entry row has invalid shape")
        values = dict(zip(_ENTRY_COLUMNS, row))
        payload = values["record_json"]
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            entry = deserialize_simulation_entry_record(payload)
            if payload != json.loads(serialize_simulation_entry_record(entry)):
                raise ValueError("entry JSON is not canonical")
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise SimulationEntryRowInvalidError("stored entry payload is invalid") from error
        direct = _ENTRY_COLUMNS[:15]
        for name in direct:
            if values[name] != getattr(entry, name):
                raise SimulationEntryRowInvalidError(
                    f"stored entry column {name} does not match payload")
        quote = entry.quote
        expected_quote = (
            (None, None, None, None, None) if quote is None else
            (quote.quote_id, quote.quote_hash, quote.source_spec,
             quote.provider_event_ns, quote.accepted_at)
        )
        relational = (
            values["quote_id"], values["quote_hash"], values["quote_source_spec"],
            values["quote_event_ns"], values["quote_accepted_at"],
        )
        if values["blocking_entry_id"] != entry.blocking_entry_id:
            raise SimulationEntryRowInvalidError("stored blocker does not match payload")
        if relational != expected_quote or values["entry_price"] != entry.entry_price:
            raise SimulationEntryRowInvalidError("stored executable columns do not match payload")
        return entry

    def get_entry_for_intent_on_cursor(self, cursor, intent_id: str, *,
            expected_intent: SimulationTradeIntent | None = None
            ) -> SimulationEntryRecord | None:
        if not isinstance(intent_id, str) or not intent_id:
            raise ValueError("intent_id must be a nonempty string")
        cursor.execute(_ENTRY_SELECT + " WHERE intent_id = %s", (intent_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        entry = self._decode_entry_row(row)
        if entry.intent_id != intent_id:
            raise SimulationEntryRowInvalidError(
                "stored entry does not match requested intent identity")
        if expected_intent is not None:
            if intent_id != expected_intent.intent_id:
                raise ValueError("intent_id does not match expected_intent")
            try:
                validate_entry_matches_intent(entry, expected_intent)
            except ValueError as error:
                raise SimulationEntryRowInvalidError(
                    "stored entry does not match immutable intent") from error
        return entry

    def get_existing_entry_in_transaction(
            self, cursor, intent: SimulationTradeIntent
            ) -> SimulationEntryRecord | None:
        """Read/validate existing-terminal precedence under its horizon lock."""
        if not isinstance(intent, SimulationTradeIntent):
            raise ValueError("intent must be a SimulationTradeIntent")
        self._verify_authority_on_cursor(cursor)
        cursor.execute("SELECT pg_advisory_xact_lock(%s::bigint)",
                       (horizon_advisory_lock_key(intent.horizon),))
        lock_row = cursor.fetchone()
        if lock_row is not None and lock_row not in ((None,), ("",)):
            raise SimulationEntryStateError("horizon advisory-lock result is malformed")
        return self.get_entry_for_intent_on_cursor(
            cursor, intent.intent_id, expected_intent=intent)

    def load_open_occupancy_on_cursor(
            self, cursor) -> Mapping[str, SimulationEntryRecord]:
        cursor.execute(_ENTRY_SELECT +
                       " WHERE symbol = %s "
                       "AND horizon IN (%s, %s, %s, %s, %s, %s) "
                       "AND entry_status = 'ENTERED'" +
                       _ENTRY_NOT_RESOLVED_CLAUSE +
                       " ORDER BY horizon, publication_at, entry_id",
                       (SYMBOL, *HORIZONS))
        occupancy: dict[str, SimulationEntryRecord] = {}
        for row in self._fetchall(cursor):
            entry = self._decode_entry_row(row)
            if entry.horizon in occupancy:
                raise SimulationEntryStateError(
                    "more than one durable open entry exists for a horizon")
            occupancy[entry.horizon] = entry
        return MappingProxyType(occupancy)

    def load_checkpoint_on_cursor(self, cursor) -> ReconciliationCheckpoint:
        cursor.execute(
            "SELECT checkpoint_key, last_completed_publication_seq, "
            "checkpoint_version, runtime_started_at, updated_at "
            "FROM public.atom_v9_sim4_reconciliation_checkpoint "
            "WHERE checkpoint_key = %s",
            (SIM_RECONCILIATION_CHECKPOINT_KEY,),
        )
        row = cursor.fetchone()
        try:
            if row is None or len(row) != 5:
                raise ValueError("checkpoint row shape")
            return ReconciliationCheckpoint(*row)
        except (TypeError, ValueError) as error:
            raise SimulationEntryRowInvalidError("checkpoint row is invalid") from error

    def load_publication_page_on_cursor(self, cursor, *,
            after_completed_publication_seq: int,
            captured_publication_fence: int,
            after: PublicationCursor | None = None,
            limit: int = SIM4_RECONCILIATION_PAGE_SIZE
            ) -> tuple[PublishedSimulationIntent, ...]:
        completed = _integer("after_completed_publication_seq",
                             after_completed_publication_seq,
                             maximum=POSTGRES_BIGINT_MAX)
        fence = _integer("captured_publication_fence", captured_publication_fence,
                         maximum=POSTGRES_BIGINT_MAX)
        if completed > fence:
            raise ValueError("completed publication sequence exceeds captured fence")
        page_limit = _integer("limit", limit, minimum=1,
                              maximum=SIM4_RECONCILIATION_PAGE_SIZE)
        select = (
            "SELECT p.publication_seq, p.admitted_at, p.publication_at, "
            "p.horizon_order, "
            + ", ".join("i." + name for name in _INTENT_COLUMNS)
            + " FROM public.atom_v9_sim_intent_publications p "
            "JOIN public.atom_v9_sim_intents i ON i.intent_id = p.intent_id "
            "WHERE p.publication_seq > %s AND p.publication_seq <= %s"
        )
        parameters: tuple[object, ...] = (completed, fence)
        if after is not None:
            if not isinstance(after, PublicationCursor):
                raise ValueError("after must be a PublicationCursor")
            select += (
                " AND (p.publication_at, p.horizon_order, p.intent_id, "
                "p.publication_seq) > (%s, %s, %s, %s)"
            )
            parameters += (after.publication_at, after.horizon_order,
                           after.intent_id, after.publication_seq)
        select += (
            " ORDER BY p.publication_at, p.horizon_order, p.intent_id, "
            "p.publication_seq LIMIT %s"
        )
        cursor.execute(select, parameters + (page_limit,))
        publications: list[PublishedSimulationIntent] = []
        previous = after
        rows = self._fetchall(cursor)
        if len(rows) > page_limit:
            raise SimulationEntryRowInvalidError("publication page exceeds bounded limit")
        for row in rows:
            if row is None or len(row) != 4 + len(_INTENT_COLUMNS):
                raise SimulationEntryRowInvalidError("publication row has invalid shape")
            intent = self._decode_intent_columns(row[4:])
            try:
                published = PublishedSimulationIntent(
                    row[0], row[1], row[2], row[3], intent)
            except (TypeError, ValueError) as error:
                raise SimulationEntryRowInvalidError("publication row is invalid") from error
            if published.publication_seq > fence:
                raise SimulationEntryRowInvalidError("publication exceeds captured fence")
            if previous is not None:
                key = (published.publication_at, published.horizon_order,
                       published.intent.intent_id, published.publication_seq)
                old = (previous.publication_at, previous.horizon_order,
                       previous.intent_id, previous.publication_seq)
                if key <= old:
                    raise SimulationEntryRowInvalidError(
                        "publication page is not in semantic keyset order")
            publications.append(published)
            previous = published.cursor
        return tuple(publications)

    def compare_and_advance_checkpoint_on_cursor(self, cursor, *,
            expected_last_completed_publication_seq: int,
            expected_checkpoint_version: int,
            new_last_completed_publication_seq: int,
            capture_kind: str,
            captured_publication_fence: int,
            runtime_started_at: datetime) -> bool:
        self._verify_authority_on_cursor(cursor)
        for name, value in (
                ("expected_last_completed_publication_seq",
                 expected_last_completed_publication_seq),
                ("expected_checkpoint_version", expected_checkpoint_version),
                ("new_last_completed_publication_seq",
                 new_last_completed_publication_seq),
                ("captured_publication_fence", captured_publication_fence)):
            _integer(name, value, maximum=POSTGRES_BIGINT_MAX)
        if capture_kind not in ("ACTIVATION", "RECONCILIATION"):
            raise ValueError("invalid capture_kind")
        started = _utc_datetime("runtime_started_at", runtime_started_at)
        cursor.execute(
            "SELECT public.atom_v9_sim4_compare_and_advance_checkpoint("
            "%s, %s, %s, %s, %s, %s)",
            (expected_last_completed_publication_seq, expected_checkpoint_version,
             new_last_completed_publication_seq, capture_kind,
             captured_publication_fence, started),
        )
        row = cursor.fetchone()
        if row not in ((True,), (False,)):
            raise SimulationEntryStateError("checkpoint advance result is malformed")
        return row[0]

    def _load_horizon_occupancy_on_cursor(
            self, cursor, horizon: str) -> SimulationEntryRecord | None:
        cursor.execute(_ENTRY_SELECT +
                       " WHERE symbol = %s AND horizon = %s "
                       "AND entry_status = 'ENTERED'" +
                       _ENTRY_NOT_RESOLVED_CLAUSE +
                       " ORDER BY publication_at, entry_id",
                       (SYMBOL, horizon))
        rows = self._fetchall(cursor)
        if len(rows) > 1:
            raise SimulationEntryStateError(
                "more than one durable open entry exists for a horizon")
        return None if not rows else self._decode_entry_row(rows[0])

    @staticmethod
    def _insert_entry_on_cursor(cursor, entry: SimulationEntryRecord) -> bool:
        payload = json.dumps(json.loads(serialize_simulation_entry_record(entry)),
                             sort_keys=True, separators=(",", ":"))
        quote = entry.quote
        cursor.execute(
            "INSERT INTO public.atom_v9_sim_entries ("
            + ", ".join(_ENTRY_COLUMNS)
            + ") VALUES ("
            + ", ".join(("%s",) * len(_ENTRY_COLUMNS))
            + ") ON CONFLICT DO NOTHING RETURNING entry_id",
            (
                entry.entry_id, entry.entry_hash, entry.contract_version,
                entry.canonicalization_version, entry.simulator_version,
                entry.symbol, entry.horizon, entry.horizon_seconds,
                entry.intent_id, entry.publication_at, entry.entry_deadline_at,
                entry.decision, entry.intent_status, entry.entry_status,
                entry.quantity_shares, entry.blocking_entry_id,
                None if quote is None else quote.quote_id,
                None if quote is None else quote.quote_hash,
                None if quote is None else quote.source_spec,
                None if quote is None else quote.provider_event_ns,
                None if quote is None else quote.accepted_at,
                entry.entry_price, payload,
            ),
        )
        return cursor.fetchone() is not None

    def terminalize_in_transaction(self, cursor, intent: SimulationTradeIntent,
            *, requested_status: str,
            quote: SimulationExecutableQuote | None = None
            ) -> tuple[str, SimulationEntryRecord]:
        """Atomically choose/persist a terminal row under the horizon lock.

        The caller must already own an explicit transaction on the worker's
        authoritative session.  This method acquires the required per-horizon
        transaction advisory lock and performs no commit or rollback.
        """
        if not isinstance(intent, SimulationTradeIntent):
            raise ValueError("intent must be a SimulationTradeIntent")
        if requested_status not in ENTRY_STATUSES:
            raise ValueError("requested_status is invalid")
        existing = self.get_existing_entry_in_transaction(cursor, intent)
        if existing is not None:
            return IDEMPOTENT, existing

        if intent.status == "NO_TRADE":
            if requested_status != "SKIPPED_NO_TRADE" or quote is not None:
                raise ValueError("NO_TRADE intent requires SKIPPED_NO_TRADE")
            final_status = "SKIPPED_NO_TRADE"
            blocker = None
            final_quote = None
        elif intent.status == "UNAVAILABLE":
            if requested_status != "SKIPPED_UNAVAILABLE" or quote is not None:
                raise ValueError("UNAVAILABLE intent requires SKIPPED_UNAVAILABLE")
            final_status = "SKIPPED_UNAVAILABLE"
            blocker = None
            final_quote = None
        else:
            occupied = self._load_horizon_occupancy_on_cursor(cursor, intent.horizon)
            if occupied is not None:
                final_status = "SKIPPED_POSITION_OPEN"
                blocker = occupied.entry_id
                final_quote = None
            else:
                if requested_status not in (
                        "ENTERED", "SKIPPED_WINDOW_EXPIRED",
                        "SKIPPED_RESTART_GAP"):
                    raise ValueError("actionable intent requested an invalid terminal status")
                final_status = requested_status
                blocker = None
                final_quote = quote if requested_status == "ENTERED" else None
                if requested_status == "ENTERED" and quote is None:
                    raise ValueError("ENTERED requires an executable quote")
                if requested_status != "ENTERED" and quote is not None:
                    raise ValueError("skipped result cannot contain a quote")

        entry = build_simulation_entry_record(
            intent=intent, entry_status=final_status, quote=final_quote,
            blocking_entry_id=blocker,
        )
        if self._insert_entry_on_cursor(cursor, entry):
            return INSERTED, entry

        cursor.execute(_ENTRY_SELECT +
                       " WHERE intent_id = %s OR entry_id = %s OR entry_hash = %s "
                       "ORDER BY entry_id",
                       (entry.intent_id, entry.entry_id, entry.entry_hash))
        rows = self._fetchall(cursor)
        if len(rows) == 1:
            stored = self._decode_entry_row(rows[0])
            if stored == entry:
                return IDEMPOTENT, stored
        raise SimulationEntryConflictError("entry identity is already in use")
