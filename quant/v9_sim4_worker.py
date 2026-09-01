"""Isolated SIM-4 executable-quote receiver and authoritative entry worker.

The module is intentionally self contained at the runtime boundary.  The
websocket thread validates and admits quotes, but the single worker thread
owns the PostgreSQL session, all reconciliation state, every deadline fence,
and every terminal decision.  Production code does not import or own this
runtime.

The public composition seam is :class:`SimulationEntryWorker`.  Network,
database, clocks, waits, and thread construction are injectable so the causal
ordering rules can be tested without real time or external services.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import logging
import math
import os
from queue import Empty, Full, Queue
import re
import signal
import ssl
import threading
import time
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import urlencode

from .v9_sim1_contract import SimulationTradeIntent
from .v9_sim4_entry import (
    IDEMPOTENT,
    INSERTED,
    PublicationCursor,
    PublishedSimulationIntent,
    SimulationEntryRecord,
    SimulationEntryStore,
    SimulationDatabaseConfigurationError,
    SimulationExecutableQuote,
    quote_is_executable_for_intent,
    select_executable_quote,
    validate_simulator_database_url,
)


SIM4_ENABLED_ENV = "ATOM_V9_SIM4_ENABLED"
SIM4_DATABASE_URL_ENV = "ATOM_V9_SIM4_DATABASE_URL"
SIM_PROJECT_REF_ENV = "ATOM_V9_SIM_PROJECT_REF"
AUTHX_CLIENT_ID_ENV = "ATOM_V9_SIM4_ALPACA_AUTHX_CLIENT_ID"
AUTHX_CLIENT_SECRET_ENV = "ATOM_V9_SIM4_ALPACA_AUTHX_CLIENT_SECRET"
AUTHX_ATTESTATION_ID_ENV = "ATOM_V9_SIM4_ALPACA_PROVISIONING_ATTESTATION_ID"
AUTHX_ATTESTATION_SHA256_ENV = (
    "ATOM_V9_SIM4_ALPACA_PROVISIONING_ATTESTATION_SHA256"
)

SIM4_QUOTE_SOURCE_SPEC = "ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1"
SIM4_WEBSOCKET_URL = "wss://stream.data.alpaca.markets/v2/sip"
SIM4_AUTHX_TOKEN_URL = "https://authx.alpaca.markets/v1/oauth2/token"
SIM4_SUBSCRIPTION_PAYLOAD = '{"action":"subscribe","quotes":["COIN"]}'
SIM4_SYMBOL = "COIN"
SIM4_RUNTIME_ROLE = "atom_v9_sim_entry_runtime"
SIM4_INSTALLATION_ID = "ATOM_TRUE_V9_SIM_INSTALLATION_1"
SIM4_CHECKPOINT_KEY = "ATOM_TRUE_V9_SIM4_RECONCILIATION_1"

SIM4_EVENT_QUEUE_CAPACITY = 256
SIM4_QUOTE_BUFFER_CAPACITY = 256
SIM4_PENDING_INTENT_CAPACITY = 256
SIM4_RECONCILE_QUERY_ROWS = 16
SIM4_RECONCILE_MAX_PAGES_PER_SLICE = 1
SIM4_BOUNDARY_RECHECK_SECONDS = 0.001
SIM4_RUNTIME_OWNER_RETRY_SECONDS = 0.100
SIM4_RUNTIME_OWNER_STARTUP_WAIT_SECONDS = 1.000
SIM4_PERIODIC_CAPTURE_SECONDS = 1.000
SIM4_PUBLIC_STOP_JOIN_SECONDS = 1.000
SIM4_TELEMETRY_LOG_INTERVAL_SECONDS = 1.000
SIM4_DATABASE_CONNECT_TIMEOUT_SECONDS = 5

SIM4_TOKEN_CONNECT_TIMEOUT_SECONDS = 5.0
SIM4_TOKEN_TOTAL_TIMEOUT_SECONDS = 10.0
SIM4_TOKEN_RESPONSE_MAX_BYTES = 16 * 1024
SIM4_WEBSOCKET_CONNECT_TIMEOUT_SECONDS = 10.0
SIM4_WEBSOCKET_ACK_TIMEOUT_SECONDS = 10.0
SIM4_WEBSOCKET_RECEIVE_TIMEOUT_SECONDS = 1.0
SIM4_WEBSOCKET_MESSAGE_MAX_BYTES = 1024 * 1024
SIM4_RECONNECT_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)
SIM4_RECONNECT_RESET_SECONDS = 60.0

SIM4_FAIL_CLOSED_COUNTERS = (
    "owner_failures",
    "auth_failures",
    "socket_failures",
    "quote_invalid",
    "quote_lock_contention",
    "quote_queue_full",
    "quote_buffer_full",
    "reconciliation_failures",
    "deadline_closure_failures",
    "terminal_failures",
)
_SIM4_LOGGER = logging.getLogger("atom.v9.sim4")

SIM4_RUNTIME_OWNER_NAMESPACE = "ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1"
SIM4_RUNTIME_OWNER_PAYLOAD = b"ATOM_TRUE_V9_SIM4_RUNTIME_OWNER_1\x00COIN"
SIM4_RUNTIME_OWNER_SHA256_FIRST_8 = "2766c300cde1d025"
SIM4_RUNTIME_OWNER_LOCK_KEY = 2839171023325220901

SIM4_ACTIVATION_NAMESPACE = "ATOM_TRUE_V9_SIM4_INTENT_HANDOFF_FENCE_1"
SIM4_ACTIVATION_PAYLOAD = b"ATOM_TRUE_V9_SIM4_INTENT_HANDOFF_FENCE_1\x00COIN"
SIM4_ACTIVATION_SHA256_FIRST_8 = "10148bea579e6cde"
SIM4_ACTIVATION_LOCK_KEY = 1158704842749668574

SIM4_HORIZON_LOCK_KEYS = MappingProxyType({
    "30S": 1464455111187090143,
    "1M": -258020115535043520,
    "5M": -4937564732027059942,
    "15M": -1356851238941253914,
    "30M": -2824415193672952787,
    "1H": 6209627528392171927,
})
SIM4_HORIZON_ORDER = MappingProxyType({
    "30S": 1, "1M": 2, "5M": 3, "15M": 4, "30M": 5, "1H": 6,
})

MAX_SIGNED_BIGINT = (1 << 63) - 1
_PROJECT_REF_RE = re.compile(r"[a-z0-9]{20}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RFC3339_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[Tt]"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?"
    r"(?P<zone>[Zz]|[+-]\d{2}:\d{2})$"
)
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# Presence of any of these variables in the dedicated worker is a deployment
# boundary violation.  Empty values still fail closed: the worker must not be
# handed production, publisher, service-role, trading, account, or order
# authority at all.
FORBIDDEN_ENVIRONMENT_NAMES = frozenset({
    "DATABASE_URL",
    "ATOM_V9_SIM_DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_KEY",
    "ATOM_V9_DATABASE_URL",
    "ATOM_V9_V4_DATABASE_URL",
    "ATOM_V9_V4_WRITER_DATABASE_URL",
    "ATOM_V9_WRITER_DATABASE_URL",
    "ATOM_V9_PUBLISHER_DATABASE_URL",
    "HISTORICAL_EVIDENCE_DATABASE_URL",
    "HISTORICAL_OUTCOME_DATABASE_URL",
    "HISTORICAL_SCORE_DATABASE_URL",
    "MASSIVE_API_KEY",
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "APCA_API_BASE_URL",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "ALPACA_API_SECRET",
    "ALPACA_BASE_URL",
    "ALPACA_BROKER_API_KEY",
    "ALPACA_BROKER_API_SECRET",
    "ALPACA_BROKER_BASE_URL",
    "BROKER_API_KEY",
    "BROKER_API_SECRET",
    "BROKER_BASE_URL",
    "BROKER_ACCOUNT_ID",
    "BROKER_ACCOUNT_URL",
    "BROKER_ORDERS_URL",
    "ACCOUNT_ENDPOINT",
    "ORDER_ENDPOINT",
    "ORDERS_ENDPOINT",
})

_OWNER_SQL = "SELECT pg_try_advisory_lock(%s::bigint)"
_OWNER_UNLOCK_SQL = "SELECT pg_advisory_unlock(%s::bigint)"
_BACKEND_PID_SQL = "SELECT pg_backend_pid()"
_ACTIVATION_TRY_SQL = "SELECT pg_try_advisory_xact_lock(%s::bigint)"
_DEADLINE_LOCK_SQL = "SELECT pg_advisory_xact_lock(%s::bigint)"
_FENCE_READER_SQL = "SELECT public.atom_v9_sim4_read_intent_admission_fence()"
_HORIZON_LOCK_SQL = "SELECT pg_advisory_xact_lock(%s::bigint)"


class Sim4ConfigurationError(RuntimeError):
    """The isolated runtime configuration is not freeze compliant."""


class Sim4AuthorityError(RuntimeError):
    """The authoritative owner session or database identity is invalid."""


class Sim4ProtocolError(RuntimeError):
    """AuthX, websocket, or quote input failed closed."""


class Sim4AuthenticationError(Sim4ProtocolError):
    """AuthX or websocket authentication failed closed."""


class Sim4GenerationFailed(RuntimeError):
    """The owned generation permanently lost decision authority."""


class _Cursor(Protocol):
    def execute(self, query: str, params: object = ...) -> object: ...
    def fetchone(self) -> object: ...
    def fetchall(self) -> Sequence[object]: ...
    def close(self) -> None: ...


class _Connection(Protocol):
    autocommit: bool
    def cursor(self) -> _Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SimulationWorkerConfig:
    database_url: str
    project_ref: str
    authx_client_id: str
    authx_client_secret: str
    provisioning_attestation_id: str
    provisioning_attestation_sha256: str


@dataclass(frozen=True, slots=True)
class ValidatedDatabaseURL:
    dsn: str
    project_ref: str
    host: str
    port: int
    database: str
    username: str
    endpoint_kind: str


def _required_nonempty(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not isinstance(value, str) or not value:
        raise Sim4ConfigurationError(f"missing required SIM-4 environment: {name}")
    return value


def sim4_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return true only for the one literal runtime-enable value."""

    values = os.environ if environ is None else environ
    return values.get(SIM4_ENABLED_ENV) == "true"


def validate_forbidden_environment(environ: Mapping[str, str]) -> None:
    present = sorted(name for name in FORBIDDEN_ENVIRONMENT_NAMES if name in environ)
    if present:
        # Names are safe to report; values are deliberately never included.
        raise Sim4ConfigurationError(
            "forbidden authority present in SIM-4 worker environment: "
            + ", ".join(present)
        )


def validate_sim4_database_url(
    dsn: str, project_ref: str, *, expected_role: str = SIM4_RUNTIME_ROLE,
) -> ValidatedDatabaseURL:
    """Delegate the one canonical DSN grammar to the pure entry boundary."""

    try:
        identity = validate_simulator_database_url(
            dsn, project_ref=project_ref, required_role=expected_role,
        )
    except SimulationDatabaseConfigurationError as error:
        raise Sim4ConfigurationError(str(error)) from error
    username = (
        expected_role if identity.endpoint_kind == "DIRECT"
        else f"{expected_role}.{project_ref}"
    )
    return ValidatedDatabaseURL(
        dsn=dsn, project_ref=identity.project_ref, host=identity.hostname,
        port=identity.port, database=identity.database, username=username,
        endpoint_kind=identity.endpoint_kind,
    )


def load_sim4_config(environ: Mapping[str, str] | None = None) -> SimulationWorkerConfig:
    """Load enabled-runtime configuration without any credential fallback."""

    values = os.environ if environ is None else environ
    if values.get(SIM4_ENABLED_ENV) != "true":
        raise Sim4ConfigurationError("SIM-4 is not literally enabled")
    validate_forbidden_environment(values)
    project_ref = _required_nonempty(values, SIM_PROJECT_REF_ENV)
    database_url = _required_nonempty(values, SIM4_DATABASE_URL_ENV)
    validate_sim4_database_url(database_url, project_ref)
    client_id = _required_nonempty(values, AUTHX_CLIENT_ID_ENV)
    client_secret = _required_nonempty(values, AUTHX_CLIENT_SECRET_ENV)
    attestation_id = _required_nonempty(values, AUTHX_ATTESTATION_ID_ENV)
    attestation_sha256 = _required_nonempty(values, AUTHX_ATTESTATION_SHA256_ENV)
    if _SHA256_RE.fullmatch(attestation_sha256) is None:
        raise Sim4ConfigurationError(
            "provisioning attestation SHA-256 must be 64 lowercase hexadecimal characters"
        )
    return SimulationWorkerConfig(
        database_url=database_url,
        project_ref=project_ref,
        authx_client_id=client_id,
        authx_client_secret=client_secret,
        provisioning_attestation_id=attestation_id,
        provisioning_attestation_sha256=attestation_sha256,
    )


def _validate_golden_lock_constants() -> None:
    owner = hashlib.sha256(SIM4_RUNTIME_OWNER_PAYLOAD).digest()[:8].hex()
    activation = hashlib.sha256(SIM4_ACTIVATION_PAYLOAD).digest()[:8].hex()
    if owner != SIM4_RUNTIME_OWNER_SHA256_FIRST_8:
        raise AssertionError("SIM-4 owner-lock golden digest mismatch")
    if activation != SIM4_ACTIVATION_SHA256_FIRST_8:
        raise AssertionError("SIM-4 activation-lock golden digest mismatch")
    for horizon, expected in SIM4_HORIZON_LOCK_KEYS.items():
        payload = b"ATOM_TRUE_V9_SIM4_ENTRY_LOCK_1\x00COIN\x00" + horizon.encode("ascii")
        unsigned = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
        derived = unsigned if unsigned < (1 << 63) else unsigned - (1 << 64)
        if derived != expected:
            raise AssertionError(f"SIM-4 horizon-lock golden mismatch: {horizon}")


_validate_golden_lock_constants()


def _datetime_to_epoch_microseconds(value: datetime) -> int:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("UTC clock must return a timezone-aware datetime")
    converted = value.astimezone(timezone.utc)
    delta = converted - _UNIX_EPOCH
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


def _datetime_to_epoch_nanoseconds(value: datetime) -> int:
    return _datetime_to_epoch_microseconds(value) * 1000


def _epoch_microseconds_to_datetime(value: int) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("epoch microseconds must be an integer")
    try:
        return _UNIX_EPOCH + timedelta(microseconds=value)
    except (OverflowError, ValueError) as error:
        raise ValueError("derived UTC time is outside datetime range") from error


@dataclass(frozen=True, slots=True)
class MonotonicUTCAnchor:
    monotonic_ns: int
    utc_epoch_us: int

    def __post_init__(self) -> None:
        if isinstance(self.monotonic_ns, bool) or not isinstance(self.monotonic_ns, int):
            raise ValueError("monotonic anchor must be an integer")
        if isinstance(self.utc_epoch_us, bool) or not isinstance(self.utc_epoch_us, int):
            raise ValueError("UTC anchor must be an integer")

    def derived_epoch_ns(self, monotonic_now_ns: int) -> int:
        if isinstance(monotonic_now_ns, bool) or not isinstance(monotonic_now_ns, int):
            raise ValueError("monotonic clock must return an integer")
        elapsed_ns = monotonic_now_ns - self.monotonic_ns
        if elapsed_ns < 0:
            raise ValueError("monotonic clock moved backward")
        return self.utc_epoch_us * 1000 + elapsed_ns

    def derived_utc(self, monotonic_now_ns: int) -> datetime:
        if isinstance(monotonic_now_ns, bool) or not isinstance(monotonic_now_ns, int):
            raise ValueError("monotonic clock must return an integer")
        elapsed_ns = monotonic_now_ns - self.monotonic_ns
        if elapsed_ns < 0:
            raise ValueError("monotonic clock moved backward")
        # Every instant is independently rounded upward; skew never accumulates.
        epoch_us = self.utc_epoch_us + ((elapsed_ns + 999) // 1000)
        return _epoch_microseconds_to_datetime(epoch_us)


def capture_monotonic_utc_anchor(
    monotonic_ns: Callable[[], int], utc_clock: Callable[[], datetime],
) -> MonotonicUTCAnchor:
    """Capture the exact monotonic-then-UTC anchor pair."""

    mono = monotonic_ns()
    if isinstance(mono, bool) or not isinstance(mono, int):
        raise ValueError("monotonic clock must return an integer")
    utc_value = utc_clock()
    if (
        not isinstance(utc_value, datetime)
        or utc_value.tzinfo is None
        or utc_value.utcoffset() != timedelta(0)
    ):
        raise ValueError("UTC anchor clock must return a UTC datetime")
    utc_us = _datetime_to_epoch_microseconds(utc_value)
    return MonotonicUTCAnchor(mono, utc_us)


def parse_alpaca_provider_event_ns(value: object) -> int:
    """Parse one RFC3339 provider timestamp without binary floating point."""

    if not isinstance(value, str):
        raise Sim4ProtocolError("quote timestamp must be a string")
    matched = _RFC3339_RE.fullmatch(value)
    if matched is None:
        raise Sim4ProtocolError("quote timestamp is not exact RFC3339")
    zone = matched.group("zone")
    if zone in {"Z", "z"}:
        zone = "+00:00"
    try:
        parsed = datetime.fromisoformat(
            f"{matched.group('date')}T{matched.group('time')}{zone}"
        )
        whole = parsed.astimezone(timezone.utc).replace(microsecond=0) - _UNIX_EPOCH
    except (OverflowError, ValueError) as error:
        raise Sim4ProtocolError("quote timestamp is invalid") from error
    seconds = whole.days * 86_400 + whole.seconds
    fraction = (matched.group("fraction") or "").ljust(9, "0")
    result = seconds * 1_000_000_000 + int(fraction or "0")
    if result < 0 or result > MAX_SIGNED_BIGINT:
        raise Sim4ProtocolError("provider_event_ns is outside signed-bigint range")
    return result


def validate_provider_event_ns(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Sim4ProtocolError("provider_event_ns must be a non-Boolean integer")
    if value < 0 or value > MAX_SIGNED_BIGINT:
        raise Sim4ProtocolError("provider_event_ns is outside signed-bigint range")
    return value


def _finite_binary64(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Sim4ProtocolError(f"{name} must be numeric")
    try:
        converted = float(value)
    except OverflowError as error:
        raise Sim4ProtocolError(f"{name} must be finite") from error
    if not math.isfinite(converted):
        raise Sim4ProtocolError(f"{name} must be finite")
    return converted


@dataclass(frozen=True, slots=True)
class ParsedSIPQuote:
    provider_event_ns: int
    bid: float
    ask: float
    bid_size: float
    ask_size: float


def parse_sip_quote_message(item: object) -> ParsedSIPQuote:
    """Validate the exact quote channel/symbol/value schema before admission."""

    if not isinstance(item, Mapping):
        raise Sim4ProtocolError("SIP frame item must be an object")
    if item.get("T") != "q" or item.get("S") != SIM4_SYMBOL:
        raise Sim4ProtocolError("SIP frame is not a COIN quote")
    for key in ("bp", "ap", "bs", "as", "t"):
        if key not in item:
            raise Sim4ProtocolError("SIP quote is missing a required field")
    provider_event_ns = parse_alpaca_provider_event_ns(item["t"])
    bid = _finite_binary64("bid", item["bp"])
    ask = _finite_binary64("ask", item["ap"])
    bid_size = _finite_binary64("bid_size", item["bs"])
    ask_size = _finite_binary64("ask_size", item["as"])
    if bid <= 0.0 or ask < bid or bid_size < 0.0 or ask_size < 0.0:
        raise Sim4ProtocolError("SIP quote values are invalid")
    return ParsedSIPQuote(provider_event_ns, bid, ask, bid_size, ask_size)


@dataclass(frozen=True, slots=True)
class AuthXToken:
    access_token: str = field(repr=False)
    expires_in: int


class _HTTPSResponse(Protocol):
    status: int
    def read(self, amount: int | None = None) -> bytes: ...


TokenRequester = Callable[[str, bytes, Mapping[str, str], float, float, int], object]


def _default_token_requester(
    url: str,
    body: bytes,
    headers: Mapping[str, str],
    connect_timeout: float,
    total_timeout: float,
    response_limit: int,
) -> tuple[int, str, bytes]:
    """Issue the one redirect-free HTTPS token request.

    ``http.client`` is used deliberately: it does not follow redirects, and it
    lets the connect and remaining read budget be applied independently.
    """

    if url != SIM4_AUTHX_TOKEN_URL:
        raise Sim4ProtocolError("invalid AuthX token endpoint")
    absolute_deadline = time.monotonic() + total_timeout

    def remaining_budget() -> float:
        remaining = absolute_deadline - time.monotonic()
        if remaining <= 0.0:
            raise TimeoutError("AuthX token request timed out")
        return remaining

    connection = http.client.HTTPSConnection(
        "authx.alpaca.markets",
        443,
        timeout=connect_timeout,
        context=ssl.create_default_context(),
    )
    try:
        connection.connect()
        if connection.sock is None:
            raise OSError("AuthX TLS socket unavailable")
        connection.sock.settimeout(remaining_budget())
        connection.request(
            "POST", "/v1/oauth2/token", body=body, headers=dict(headers)
        )
        connection.sock.settimeout(remaining_budget())
        response = connection.getresponse()
        remaining_budget()
        response_body = bytearray()
        while True:
            if connection.sock is None:
                raise OSError("AuthX TLS socket unavailable")
            connection.sock.settimeout(remaining_budget())
            chunk = response.read1(min(4096, response_limit + 1 - len(response_body)))
            # A read that began in budget but completed at/after the absolute
            # deadline is late and cannot be accepted.
            remaining_budget()
            if not chunk:
                break
            response_body.extend(chunk)
            if len(response_body) > response_limit:
                raise Sim4ProtocolError("AuthX token response exceeds 16 KiB")
        return response.status, SIM4_AUTHX_TOKEN_URL, bytes(response_body)
    finally:
        connection.close()


class AuthXTokenClient:
    """Fetch and validate a short-lived data-only Broker AuthX token."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        requester: TokenRequester | None = None,
    ) -> None:
        if not isinstance(client_id, str) or not client_id:
            raise Sim4ConfigurationError("AuthX client ID is required")
        if not isinstance(client_secret, str) or not client_secret:
            raise Sim4ConfigurationError("AuthX client secret is required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._requester = requester or _default_token_requester

    def fetch(self) -> AuthXToken:
        body = urlencode((
            ("grant_type", "client_credentials"),
            ("client_id", self._client_id),
            ("client_secret", self._client_secret),
        )).encode("ascii")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
        }
        try:
            raw = self._requester(
                SIM4_AUTHX_TOKEN_URL,
                body,
                headers,
                SIM4_TOKEN_CONNECT_TIMEOUT_SECONDS,
                SIM4_TOKEN_TOTAL_TIMEOUT_SECONDS,
                SIM4_TOKEN_RESPONSE_MAX_BYTES,
            )
            if (
                not isinstance(raw, tuple)
                or len(raw) != 3
                or isinstance(raw[0], bool)
                or not isinstance(raw[0], int)
                or not isinstance(raw[1], str)
                or not isinstance(raw[2], (bytes, bytearray))
            ):
                raise Sim4ProtocolError("AuthX requester returned an invalid response")
            status, final_url, response_body = raw
            if len(response_body) > SIM4_TOKEN_RESPONSE_MAX_BYTES:
                raise Sim4ProtocolError("AuthX token response exceeds 16 KiB")
            if status != 200 or final_url != SIM4_AUTHX_TOKEN_URL:
                raise Sim4ProtocolError("AuthX token response was not an exact HTTP 200")
            payload = json.loads(bytes(response_body).decode("utf-8"))
            if not isinstance(payload, dict):
                raise Sim4ProtocolError("AuthX token response must be a JSON object")
            access_token = payload.get("access_token")
            token_type = payload.get("token_type")
            expires_in = payload.get("expires_in")
            if not isinstance(access_token, str) or not access_token:
                raise Sim4ProtocolError("AuthX response lacks an access token")
            if not isinstance(token_type, str) or token_type.lower() != "bearer":
                raise Sim4ProtocolError("AuthX token type is not Bearer")
            if (
                isinstance(expires_in, bool)
                or not isinstance(expires_in, int)
                or expires_in <= 0
            ):
                raise Sim4ProtocolError("AuthX token lifetime is invalid")
            return AuthXToken(access_token, expires_in)
        except Sim4ProtocolError:
            raise
        except BaseException as error:
            # The original exception may embed a URL or request body.  Never
            # chain it into logs or telemetry.
            raise Sim4ProtocolError("AuthX token request failed closed") from None


@dataclass(frozen=True, slots=True)
class AdmissionEnvelope:
    admission_sequence: int
    quote: object

    def __post_init__(self) -> None:
        if (
            isinstance(self.admission_sequence, bool)
            or not isinstance(self.admission_sequence, int)
            or self.admission_sequence <= 0
        ):
            raise ValueError("admission sequence must be a positive integer")


@dataclass(slots=True)
class Sim4Telemetry:
    """Fixed-cardinality, secret-free operational counters."""

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _status: str = "STANDBY"
    _counters: dict[str, int] = field(default_factory=lambda: {
        "owner_attempts": 0,
        "owner_acquired": 0,
        "owner_failures": 0,
        "auth_failures": 0,
        "socket_failures": 0,
        "quote_invalid": 0,
        "quote_admitted": 0,
        "quote_lock_contention": 0,
        "quote_queue_full": 0,
        "quote_buffer_full": 0,
        "reconciliation_failures": 0,
        "deadline_closure_failures": 0,
        "terminal_failures": 0,
    }, init=False, repr=False)

    def status(self, value: str) -> None:
        if value not in {
            "STANDBY", "RECOVERING", "READY", "STOPPING", "STOPPED", "FAILED",
        }:
            raise ValueError("invalid SIM-4 status")
        with self._lock:
            self._status = value

    def increment(self, name: str) -> None:
        with self._lock:
            if name not in self._counters:
                raise ValueError("invalid SIM-4 telemetry counter")
            self._counters[name] += 1

    def snapshot(self) -> Mapping[str, object]:
        with self._lock:
            return MappingProxyType({"status": self._status, **self._counters})


FailClosedTelemetrySnapshot = tuple[str, tuple[int, ...]]


def _fail_closed_telemetry_snapshot(
    telemetry: Sim4Telemetry,
) -> FailClosedTelemetrySnapshot:
    snapshot = telemetry.snapshot()
    return (
        str(snapshot["status"]),
        tuple(int(snapshot[name]) for name in SIM4_FAIL_CLOSED_COUNTERS),
    )


def _log_fail_closed_telemetry_changes(
    telemetry: Sim4Telemetry,
    previous: FailClosedTelemetrySnapshot,
    *,
    logger: Any | None = None,
) -> FailClosedTelemetrySnapshot:
    """Emit one fixed-field aggregate off every SIM-4 decision/ingress path."""

    current = _fail_closed_telemetry_snapshot(telemetry)
    changes = tuple(
        (name, current_value, current_value - previous_value)
        for name, current_value, previous_value in zip(
            SIM4_FAIL_CLOSED_COUNTERS, current[1], previous[1]
        )
        if current_value != previous_value
    )
    became_failed = current[0] == "FAILED" and previous[0] != "FAILED"
    if not changes and not became_failed:
        return current
    fields = " ".join(
        f"{name}={value} delta={delta}" for name, value, delta in changes
    ) or "counter_delta=0"
    # The message is constructed only from fixed names, a fixed status enum,
    # and integer counters.  It can never contain config, URLs, payloads,
    # exceptions, credentials, or tokens.  Logging failure is non-authoritative.
    try:
        target = _SIM4_LOGGER if logger is None else logger
        target.warning("SIM4_FAIL_CLOSED status=%s %s", current[0], fields)
    except Exception:
        pass
    return current


def _decode_frame(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, bytes):
        if len(value) > SIM4_WEBSOCKET_MESSAGE_MAX_BYTES:
            raise Sim4ProtocolError("websocket message exceeds 1 MiB")
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise Sim4ProtocolError("websocket frame is not UTF-8") from error
    elif isinstance(value, str):
        # The websocket-client public recv boundary has already materialized a
        # text message.  Reject by wire bytes immediately, before JSON parsing;
        # the character-count guard also avoids encoding an already-oversized
        # ASCII message solely to measure it.
        if len(value) > SIM4_WEBSOCKET_MESSAGE_MAX_BYTES:
            raise Sim4ProtocolError("websocket message exceeds 1 MiB")
        try:
            encoded_size = len(value.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise Sim4ProtocolError("websocket frame is not UTF-8") from error
        if encoded_size > SIM4_WEBSOCKET_MESSAGE_MAX_BYTES:
            raise Sim4ProtocolError("websocket message exceeds 1 MiB")
    else:
        raise Sim4ProtocolError("websocket frame must be text")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise Sim4ProtocolError("websocket frame is not JSON") from error
    if not isinstance(decoded, list) or not decoded:
        raise Sim4ProtocolError("websocket frame must be a nonempty array")
    if any(not isinstance(item, dict) for item in decoded):
        raise Sim4ProtocolError("websocket frame contains a non-object item")
    return decoded


def _authentication_ack(items: Sequence[Mapping[str, object]]) -> bool:
    return any(item.get("T") == "success" and item.get("msg") == "authenticated"
               for item in items)


def _subscription_ack_index(
    items: Sequence[Mapping[str, object]],
) -> int | None:
    for index, item in enumerate(items):
        if item.get("T") != "subscription":
            continue
        quotes = item.get("quotes")
        if isinstance(quotes, list) and quotes == [SIM4_SYMBOL]:
            return index
    return None


def _subscription_ack(items: Sequence[Mapping[str, object]]) -> bool:
    return _subscription_ack_index(items) is not None


def _is_receive_timeout(error: BaseException) -> bool:
    return (
        isinstance(error, TimeoutError)
        or error.__class__.__name__ == "WebSocketTimeoutException"
        or (isinstance(error, OSError) and "timed out" in str(error).lower())
    )


def _is_statement_timeout(error: BaseException) -> bool:
    return (
        getattr(error, "sqlstate", None) == "57014"
        or error.__class__.__name__ in {"QueryCanceled", "QueryCanceledError"}
    )


def _bounded_websocket_client_class():
    """Build the pinned websocket-client transport with pre-payload ceilings."""

    from websocket import WebSocket
    from websocket._abnf import continuous_frame, frame_buffer
    from websocket._exceptions import WebSocketPayloadException

    def message_too_large() -> WebSocketPayloadException:
        return WebSocketPayloadException("websocket message exceeds 1 MiB")

    class Sim4BoundedFrameBuffer(frame_buffer):
        def recv_length(self) -> None:
            # websocket-client 1.9.0 parses the complete declared frame length
            # here, immediately before mask and payload reads.  Rejecting here
            # prevents recv_strict(length) from allocating/aggregating cap+1.
            super().recv_length()
            if (
                self.length is not None
                and self.length > SIM4_WEBSOCKET_MESSAGE_MAX_BYTES
            ):
                self.clear()
                raise message_too_large()

    class Sim4BoundedContinuousFrame(continuous_frame):
        def add(self, frame: Any) -> None:
            accumulated = (
                0 if self.cont_data is None else len(self.cont_data[1])
            )
            incoming = len(frame.data)
            if (
                incoming > SIM4_WEBSOCKET_MESSAGE_MAX_BYTES - accumulated
            ):
                # Release any already-assembled fragments before failing the
                # connection; never concatenate a cap+1 logical message.
                self.cont_data = None
                self.recving_frames = None
                raise message_too_large()
            super().add(frame)

    class Sim4BoundedWebSocket(WebSocket):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            skip_utf8_validation = bool(
                kwargs.get("skip_utf8_validation", False)
            )
            fire_cont_frame = bool(kwargs.get("fire_cont_frame", False))
            self.frame_buffer = Sim4BoundedFrameBuffer(
                self._recv, skip_utf8_validation
            )
            self.cont_frame = Sim4BoundedContinuousFrame(
                fire_cont_frame, skip_utf8_validation
            )

    return Sim4BoundedWebSocket


class SIPWebSocketReceiver:
    """Non-authoritative, database-free SIP receiver.

    The owner worker starts this object only after acquiring its database
    session lock.  This class never receives a database object and its sole
    authority-bearing callback is the bounded quote-admission function.
    """

    def __init__(
        self,
        token_client: AuthXTokenClient,
        quote_callback: Callable[[ParsedSIPQuote], bool],
        *,
        websocket_factory: Callable[..., object] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        wait: Callable[[float], bool] | None = None,
        telemetry: Sim4Telemetry | None = None,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        if not callable(quote_callback):
            raise TypeError("quote_callback must be callable")
        if websocket_factory is None:
            from websocket import create_connection
            bounded_class = _bounded_websocket_client_class()

            def websocket_factory(url: str, **options: object) -> object:
                return create_connection(url, class_=bounded_class, **options)
        self._token_client = token_client
        self._quote_callback = quote_callback
        self._websocket_factory = websocket_factory
        self._monotonic = monotonic
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait
        self._telemetry = telemetry or Sim4Telemetry()
        self._thread_factory = thread_factory
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._socket_lock = threading.Lock()
        self._socket: object | None = None
        self._last_connection_stable_seconds = 0.0

    @property
    def ready_event(self) -> threading.Event:
        return self._ready

    def start(self) -> None:
        if self._thread is not None:
            return
        thread = self._thread_factory(
            target=self._run, name="v9-sim4-sip-receiver", daemon=True,
        )
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._ready.clear()
        # The exact 1.000s receive timeout bounds observation.  Socket close
        # stays on the receiver thread's own finalizer so public stop cannot
        # block in a websocket close handshake.

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _recv_until(
        self,
        stream: object,
        predicate: Callable[[Sequence[Mapping[str, object]]], bool],
        deadline: float,
    ) -> tuple[Mapping[str, object], ...]:
        while not self._stop.is_set():
            if self._monotonic() >= deadline:
                raise Sim4ProtocolError("websocket acknowledgement timed out")
            try:
                items = _decode_frame(stream.recv())
            except BaseException as error:
                if _is_receive_timeout(error):
                    continue
                raise Sim4ProtocolError("websocket acknowledgement failed") from None
            if any(item.get("T") == "error" for item in items):
                raise Sim4ProtocolError("websocket acknowledgement was rejected")
            # A recv that began inside the window but returned outside it is
            # late; acknowledgements must arrive within ten seconds.
            if self._monotonic() >= deadline:
                raise Sim4ProtocolError("websocket acknowledgement timed out")
            if predicate(items):
                return tuple(items)
        raise Sim4ProtocolError("websocket receiver stopped")

    def _process_stream_items(
        self, items: Sequence[Mapping[str, object]],
    ) -> None:
        for item in items:
            if item.get("T") == "q":
                try:
                    parsed = parse_sip_quote_message(item)
                except Sim4ProtocolError:
                    self._telemetry.increment("quote_invalid")
                    continue
                try:
                    self._quote_callback(parsed)
                except BaseException:
                    self._telemetry.increment("quote_invalid")
            elif item.get("T") == "error":
                raise Sim4ProtocolError("SIP stream returned an error")

    def _connect_once(self) -> float:
        try:
            token = self._token_client.fetch()
        except BaseException:
            raise Sim4AuthenticationError("AuthX token acquisition failed") from None
        stream = None
        stable_started: float | None = None
        self._last_connection_stable_seconds = 0.0
        try:
            stream = self._websocket_factory(
                SIM4_WEBSOCKET_URL,
                header=[f"Authorization: Bearer {token.access_token}"],
                timeout=SIM4_WEBSOCKET_CONNECT_TIMEOUT_SECONDS,
                redirect_limit=0,
                sslopt={"cert_reqs": ssl.CERT_REQUIRED},
            )
            with self._socket_lock:
                self._socket = stream
            stream.settimeout(SIM4_WEBSOCKET_RECEIVE_TIMEOUT_SECONDS)
            try:
                self._recv_until(
                    stream,
                    _authentication_ack,
                    self._monotonic() + SIM4_WEBSOCKET_ACK_TIMEOUT_SECONDS,
                )
                stream.send(SIM4_SUBSCRIPTION_PAYLOAD)
                subscription_items = self._recv_until(
                    stream,
                    _subscription_ack,
                    self._monotonic() + SIM4_WEBSOCKET_ACK_TIMEOUT_SECONDS,
                )
            except BaseException:
                raise Sim4AuthenticationError(
                    "websocket authentication failed"
                ) from None
            subscription_index = _subscription_ack_index(subscription_items)
            if subscription_index is None:
                raise Sim4AuthenticationError(
                    "websocket subscription acknowledgement is missing"
                )
            stable_started = self._monotonic()
            self._ready.set()
            self._process_stream_items(
                subscription_items[subscription_index + 1:]
            )
            while not self._stop.is_set():
                try:
                    items = _decode_frame(stream.recv())
                except BaseException as error:
                    if _is_receive_timeout(error):
                        continue
                    raise Sim4ProtocolError("SIP receive failed") from None
                self._process_stream_items(items)
            return self._monotonic() - stable_started
        finally:
            if stable_started is not None:
                self._last_connection_stable_seconds = max(
                    0.0, self._monotonic() - stable_started,
                )
            self._ready.clear()
            with self._socket_lock:
                self._socket = None
            if stream is not None:
                try:
                    stream.close()
                except BaseException:
                    pass

    def _run(self) -> None:
        delay_index = 0
        while not self._stop.is_set():
            stable_seconds = 0.0
            try:
                stable_seconds = self._connect_once()
            except Sim4AuthenticationError:
                stable_seconds = self._last_connection_stable_seconds
                self._telemetry.increment("auth_failures")
            except BaseException:
                stable_seconds = self._last_connection_stable_seconds
                self._telemetry.increment("socket_failures")
            if self._stop.is_set():
                return
            if stable_seconds >= SIM4_RECONNECT_RESET_SECONDS:
                delay_index = 0
            delay = SIM4_RECONNECT_DELAYS[min(delay_index, len(SIM4_RECONNECT_DELAYS) - 1)]
            if delay_index < len(SIM4_RECONNECT_DELAYS) - 1:
                delay_index += 1
            if self._wait(delay):
                return


@dataclass(frozen=True, slots=True)
class PublicationRecord:
    publication_seq: int
    publication_at: datetime
    horizon_order: int
    intent: SimulationTradeIntent
    discovered_epoch_ns: int

    @property
    def semantic_key(self) -> tuple[datetime, int, str, int]:
        return (
            self.publication_at,
            self.horizon_order,
            self.intent.intent_id,
            self.publication_seq,
        )


@dataclass(slots=True)
class PendingIntent:
    publication: PublicationRecord
    deadline_epoch_ns: int
    selected_quote: object | None = None
    admission_watermark: int | None = None
    publication_fence: int | None = None
    forced_status_after_deadline: str | None = None


@dataclass(slots=True)
class ReconciliationTarget:
    capture_kind: str
    lower_publication_seq: int
    fence_publication_seq: int
    expected_checkpoint_version: int
    cursor: tuple[datetime, int, str, int] | None = None
    page: list[PublicationRecord] = field(default_factory=list)
    page_complete: bool = False
    exhausted: bool = False
    waiting_until_epoch_ns: int | None = None
    retry_not_before_monotonic: float | None = None


@dataclass(slots=True)
class DeadlineClosure:
    deadline_epoch_ns: int
    admission_watermark: int
    candidates: dict[str, object | None]
    publication_fence: int | None = None
    reconciliation_complete: bool = False
    admitted_quotes: tuple[SimulationExecutableQuote, ...] = ()


def quote_is_eligible(intent: SimulationTradeIntent, quote: object) -> bool:
    """Apply the exact inclusive two-second executable-side predicate."""

    return (
        isinstance(quote, SimulationExecutableQuote)
        and quote_is_executable_for_intent(intent, quote)
    )


class SimulationEntryWorker:
    """Single authoritative SIM-4 database/decision worker."""

    def __init__(
        self,
        connection_factory: Callable[[], _Connection],
        project_ref: str,
        token_client: AuthXTokenClient,
        *,
        utc_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        monotonic: Callable[[], float] = time.monotonic,
        receiver_factory: Callable[[Callable[[ParsedSIPQuote], bool]], object] | None = None,
        websocket_factory: Callable[..., object] | None = None,
        telemetry: Sim4Telemetry | None = None,
        wait: Callable[[float], bool] | None = None,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        if not callable(connection_factory):
            raise TypeError("connection_factory must be callable")
        if not isinstance(project_ref, str) or _PROJECT_REF_RE.fullmatch(project_ref) is None:
            raise Sim4ConfigurationError("SIM project ref must be 20 lowercase alphanumerics")
        if not callable(utc_clock) or not callable(monotonic_ns) or not callable(monotonic):
            raise TypeError("worker clocks must be callable")
        self._connection_factory = connection_factory
        self._project_ref = project_ref
        self._token_client = token_client
        self._utc_clock = utc_clock
        self._monotonic_ns = monotonic_ns
        self._monotonic = monotonic
        self._wait = wait
        self._thread_factory = thread_factory
        self.telemetry = telemetry or Sim4Telemetry()
        if receiver_factory is None:
            receiver_factory = lambda callback: SIPWebSocketReceiver(
                token_client,
                callback,
                websocket_factory=websocket_factory,
                monotonic=monotonic,
                telemetry=self.telemetry,
            )
        self._receiver_factory = receiver_factory

        self._events: Queue[AdmissionEnvelope] = Queue(SIM4_EVENT_QUEUE_CAPACITY)
        self._quotes: deque[AdmissionEnvelope] = deque()
        self._admission_lock = threading.Lock()
        self._admission_enabled = False
        self._next_admission_sequence = 1
        self._anchor: MonotonicUTCAnchor | None = None

        self._state_condition = threading.Condition()
        self._state = "STANDBY"
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._receiver: object | None = None
        self._owner_connection: _Connection | None = None
        self._owner_backend_pid: int | None = None
        self._owner_acquired = False
        self._generation_failed = False

        self._runtime_started_at: datetime | None = None
        self._runtime_started_epoch_ns: int | None = None
        self._checkpoint_last = 0
        self._checkpoint_version = 0
        self._target: ReconciliationTarget | None = None
        self._pending: dict[str, PendingIntent] = {}
        self._deadline_closures: dict[int, DeadlineClosure] = {}
        self._last_drained_sequence = 0
        self._next_periodic_opportunity = math.inf
        self._ordinary_since_slice = True

    @classmethod
    def from_config(
        cls,
        config: SimulationWorkerConfig,
        *,
        connection_factory: Callable[[], _Connection] | None = None,
        token_requester: TokenRequester | None = None,
        websocket_factory: Callable[..., object] | None = None,
        **kwargs: object,
    ) -> "SimulationEntryWorker":
        validate_sim4_database_url(config.database_url, config.project_ref)
        if connection_factory is None:
            def connection_factory() -> _Connection:
                import psycopg
                return psycopg.connect(  # type: ignore[return-value]
                    config.database_url,
                    connect_timeout=SIM4_DATABASE_CONNECT_TIMEOUT_SECONDS,
                )
        token_client = AuthXTokenClient(
            config.authx_client_id,
            config.authx_client_secret,
            requester=token_requester,
        )
        return cls(
            connection_factory,
            config.project_ref,
            token_client,
            websocket_factory=websocket_factory,
            **kwargs,
        )

    @property
    def state(self) -> str:
        with self._state_condition:
            return self._state

    @property
    def admission_lock(self) -> threading.Lock:
        """Expose the exact mutex only for deterministic conformance tests."""

        return self._admission_lock

    @property
    def next_admission_sequence(self) -> int:
        with self._admission_lock:
            return self._next_admission_sequence

    def _set_state(self, value: str) -> None:
        self.telemetry.status(value)
        with self._state_condition:
            self._state = value
            self._state_condition.notify_all()

    def _stop_wait(self, seconds: float) -> bool:
        if self._wait is None:
            return self._stop_requested.wait(seconds)
        return bool(self._wait(seconds)) or self._stop_requested.is_set()

    def start(self) -> str:
        """Start once and wait at most one second for owner startup observation."""

        with self._state_condition:
            if self._thread is not None:
                return self._state
            thread = self._thread_factory(
                target=self._run, name="v9-sim4-owner-worker", daemon=True,
            )
            self._thread = thread
            thread.start()
            deadline = self._monotonic() + SIM4_RUNTIME_OWNER_STARTUP_WAIT_SECONDS
            while self._state in {"STANDBY", "RECOVERING"}:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    break
                self._state_condition.wait(remaining)
            return self._state

    def stop(self) -> None:
        """Stop intake first and return after at most the public one-second bound."""

        with self._admission_lock:
            self._admission_enabled = False
        receiver = self._receiver
        if receiver is not None:
            try:
                receiver.stop()
            except BaseException:
                pass
        self._stop_requested.set()
        with self._state_condition:
            if self._state not in {"STOPPED", "FAILED"}:
                self._set_state_without_condition("STOPPING")
            thread = self._thread
        if thread is not None:
            thread.join(SIM4_PUBLIC_STOP_JOIN_SECONDS)
        # The caller deliberately does not touch the owner connection.  If the
        # thread is still alive it retains ownership until its own finalizer.

    def _set_state_without_condition(self, value: str) -> None:
        self.telemetry.status(value)
        self._state = value
        self._state_condition.notify_all()

    def _build_quote(self, parsed: ParsedSIPQuote, accepted_at: datetime) -> object:
        from .v9_sim4_entry import build_simulation_executable_quote
        return build_simulation_executable_quote(
            source_spec=SIM4_QUOTE_SOURCE_SPEC,
            symbol=SIM4_SYMBOL,
            provider_event_ns=parsed.provider_event_ns,
            accepted_at=accepted_at,
            bid=parsed.bid,
            ask=parsed.ask,
            bid_size=parsed.bid_size,
            ask_size=parsed.ask_size,
        )

    def admit_parsed_quote(self, parsed: ParsedSIPQuote) -> bool:
        """Perform the exact nonblocking mutex/clock/sequence/put admission."""

        if not isinstance(parsed, ParsedSIPQuote):
            return False
        if not self._admission_lock.acquire(blocking=False):
            self.telemetry.increment("quote_lock_contention")
            return False
        try:
            if not self._admission_enabled or self._anchor is None or self._generation_failed:
                return False
            monotonic_now_ns = self._monotonic_ns()
            accepted_at = self._anchor.derived_utc(monotonic_now_ns)
            quote = self._build_quote(parsed, accepted_at)
            candidate = self._next_admission_sequence
            envelope = AdmissionEnvelope(candidate, quote)
            try:
                self._events.put_nowait(envelope)
            except Full:
                self.telemetry.increment("quote_queue_full")
                return False
            self._next_admission_sequence = candidate + 1
            self.telemetry.increment("quote_admitted")
            return True
        except BaseException:
            self.telemetry.increment("quote_invalid")
            return False
        finally:
            self._admission_lock.release()

    def _deadline_sample(self, deadline_epoch_ns: int) -> tuple[bool, int, int]:
        """Return strict-greater, exact derived ns, and immutable watermark."""

        with self._admission_lock:
            if self._anchor is None:
                raise Sim4GenerationFailed("deadline sampled before runtime anchor")
            monotonic_now_ns = self._monotonic_ns()
            derived_ns = self._anchor.derived_epoch_ns(monotonic_now_ns)
            watermark = self._next_admission_sequence - 1
            return derived_ns > deadline_epoch_ns, derived_ns, watermark

    def _candidate_connection(self) -> _Connection | None:
        connection = None
        cursor = None
        lock_acquired = False
        try:
            connection = self._connection_factory()
            connection.autocommit = True
            cursor = connection.cursor()
            self.telemetry.increment("owner_attempts")
            cursor.execute(_OWNER_SQL, (SIM4_RUNTIME_OWNER_LOCK_KEY,))
            row = cursor.fetchone()
            if row == (False,):
                return None
            if row != (True,):
                raise Sim4AuthorityError("runtime owner-lock result is malformed")
            lock_acquired = True
            cursor.execute(_BACKEND_PID_SQL)
            pid_row = cursor.fetchone()
            if (
                not isinstance(pid_row, (tuple, list))
                or len(pid_row) != 1
                or isinstance(pid_row[0], bool)
                or not isinstance(pid_row[0], int)
                or pid_row[0] <= 0
            ):
                raise Sim4AuthorityError("database backend PID is malformed")
            self._owner_backend_pid = pid_row[0]
            self._owner_acquired = True
            self.telemetry.increment("owner_acquired")
            return connection
        except BaseException as error:
            self.telemetry.increment("owner_failures")
            if isinstance(error, Sim4AuthorityError) and not lock_acquired:
                raise Sim4GenerationFailed(
                    "runtime owner-lock result was malformed"
                ) from None
            if lock_acquired:
                # An ownership response followed by any ambiguous session
                # state is generation-terminal; closing the local candidate
                # atomically releases any server-held session lock.
                if connection is not None:
                    try:
                        connection.close()
                    except BaseException:
                        pass
                raise Sim4GenerationFailed(
                    "runtime ownership became ambiguous during acquisition"
                ) from None
            return None
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except BaseException:
                    pass
            if connection is not None and not self._owner_acquired:
                try:
                    connection.close()
                except BaseException:
                    pass

    def _assert_backend_pid(self, cursor: _Cursor) -> None:
        cursor.execute(_BACKEND_PID_SQL)
        row = cursor.fetchone()
        if (
            not isinstance(row, (tuple, list))
            or len(row) != 1
            or isinstance(row[0], bool)
            or not isinstance(row[0], int)
            or row[0] != self._owner_backend_pid
        ):
            raise Sim4AuthorityError("authoritative database backend changed")

    def _begin_transaction(self) -> _Cursor:
        connection = self._owner_connection
        if connection is None or not self._owner_acquired:
            raise Sim4GenerationFailed("terminal transaction lacks owner authority")
        authority_cursor = connection.cursor()
        try:
            self._assert_backend_pid(authority_cursor)
        except BaseException:
            self._generation_failed = True
            with self._admission_lock:
                self._admission_enabled = False
            raise Sim4GenerationFailed(
                "authoritative database backend changed"
            ) from None
        finally:
            authority_cursor.close()
        connection.autocommit = False
        return connection.cursor()

    def _end_transaction(self, cursor: _Cursor, success: bool) -> None:
        connection = self._owner_connection
        try:
            if connection is None:
                return
            if success:
                connection.commit()
            else:
                connection.rollback()
        finally:
            try:
                cursor.close()
            finally:
                if connection is not None:
                    connection.autocommit = True

    def _verify_startup(self) -> SimulationEntryStore:
        connection = self._owner_connection
        if connection is None or self._owner_backend_pid is None:
            raise Sim4AuthorityError("owner connection is unavailable")
        store = SimulationEntryStore(
            connection,
            project_ref=self._project_ref,
            expected_backend_pid=self._owner_backend_pid,
        )
        cursor = connection.cursor()
        try:
            store.verify_startup_on_cursor(cursor)
        finally:
            cursor.close()
        return store

    def _wait_for_sip_readiness(self) -> bool:
        receiver = self._receiver_factory(self.admit_parsed_quote)
        self._receiver = receiver
        receiver.start()
        ready = getattr(receiver, "ready_event", None)
        if not isinstance(ready, threading.Event):
            # Event-like test doubles are accepted only when they expose the
            # same bounded wait/is_set surface.
            if ready is None or not callable(getattr(ready, "wait", None)):
                raise Sim4ConfigurationError("SIP receiver lacks readiness acknowledgement")
        while not self._stop_requested.is_set():
            if ready.wait(SIM4_RUNTIME_OWNER_RETRY_SECONDS):
                try:
                    self._enable_admission_with_anchor()
                except Sim4ProtocolError:
                    # The receiver cleared readiness while beginning its
                    # normal reconnect loop.  Wait on that same receiver.
                    continue
                return True
        return False

    def _enable_admission_with_anchor(self) -> None:
        receiver = self._receiver
        ready = None if receiver is None else getattr(receiver, "ready_event", None)
        with self._admission_lock:
            if ready is None or not ready.is_set():
                raise Sim4ProtocolError("SIP readiness was lost before anchor capture")
            # Exact order: monotonic sample, then UTC sample, both under the
            # admission mutex; only then does admission become true.
            self._anchor = capture_monotonic_utc_anchor(
                self._monotonic_ns, self._utc_clock,
            )
            self._admission_enabled = True

    def _activation_capture(self, store: SimulationEntryStore) -> int | None:
        cursor = self._begin_transaction()
        success = False
        try:
            cursor.execute("SET LOCAL statement_timeout = '100ms'")
            cursor.execute(_ACTIVATION_TRY_SQL, (SIM4_ACTIVATION_LOCK_KEY,))
            row = cursor.fetchone()
            if row == (False,):
                return None
            if row != (True,):
                raise Sim4AuthorityError("activation-lock result is malformed")
            cursor.execute(_FENCE_READER_SQL)
            fence_row = cursor.fetchone()
            fence = self._read_nonnegative_fence(fence_row)
            checkpoint = store.load_checkpoint_on_cursor(cursor)
            store.load_open_occupancy_on_cursor(cursor)
            with self._admission_lock:
                if self._anchor is None:
                    raise Sim4GenerationFailed("runtime anchor is unavailable")
                runtime_started_monotonic_ns = self._monotonic_ns()
                runtime_started = self._anchor.derived_utc(
                    runtime_started_monotonic_ns
                )
                runtime_started_ns = self._anchor.derived_epoch_ns(
                    runtime_started_monotonic_ns
                )
            self._runtime_started_at = runtime_started
            self._runtime_started_epoch_ns = runtime_started_ns
            self._checkpoint_last = checkpoint.last_completed_publication_seq
            self._checkpoint_version = checkpoint.checkpoint_version
            success = True
            return fence
        finally:
            self._end_transaction(cursor, success)

    @staticmethod
    def _read_nonnegative_fence(row: object) -> int:
        if (
            not isinstance(row, (tuple, list))
            or len(row) != 1
            or isinstance(row[0], bool)
            or not isinstance(row[0], int)
            or row[0] < 0
            or row[0] > MAX_SIGNED_BIGINT
        ):
            raise Sim4AuthorityError("publication fence result is malformed")
        return row[0]

    def _try_periodic_capture(self) -> int | None:
        cursor = self._begin_transaction()
        success = False
        fence: int | None = None
        yielded = False
        prove_backend_after_rollback = False
        try:
            cursor.execute("SET LOCAL statement_timeout = '100ms'")
            cursor.execute(_ACTIVATION_TRY_SQL, (SIM4_ACTIVATION_LOCK_KEY,))
            row = cursor.fetchone()
            if row == (False,):
                yielded = True
            elif row != (True,):
                raise Sim4AuthorityError("periodic capture lock result is malformed")
            else:
                cursor.execute(_FENCE_READER_SQL)
                fence = self._read_nonnegative_fence(cursor.fetchone())
                success = True
        except Sim4AuthorityError:
            # A malformed periodic capture is only a failed opportunity.  It
            # may yield after rollback, but only after the same owner session
            # proves its stable backend identity outside the failed tx.
            self.telemetry.increment("reconciliation_failures")
            yielded = True
            prove_backend_after_rollback = True
        except BaseException as error:
            if not _is_statement_timeout(error):
                raise
            self.telemetry.increment("reconciliation_failures")
            yielded = True
            prove_backend_after_rollback = True
        finally:
            self._end_transaction(cursor, success)
        if prove_backend_after_rollback:
            connection = self._owner_connection
            if connection is None:
                raise Sim4AuthorityError("owner connection is unavailable")
            authority_cursor = connection.cursor()
            try:
                self._assert_backend_pid(authority_cursor)
            finally:
                authority_cursor.close()
        if yielded:
            return None
        if fence is None:
            raise Sim4AuthorityError("periodic capture produced no fence")
        return fence

    def _capture_deadline_publication_fence(self) -> int:
        cursor = self._begin_transaction()
        success = False
        try:
            cursor.execute("SET LOCAL lock_timeout = '5000ms'")
            cursor.execute("SET LOCAL statement_timeout = '6000ms'")
            cursor.execute(_DEADLINE_LOCK_SQL, (SIM4_ACTIVATION_LOCK_KEY,))
            lock_row = cursor.fetchone()
            if lock_row not in (None, (None,), [None]):
                raise Sim4AuthorityError("deadline closure lock result is malformed")
            cursor.execute(_FENCE_READER_SQL)
            fence = self._read_nonnegative_fence(cursor.fetchone())
            success = True
            return fence
        except BaseException:
            self.telemetry.increment("deadline_closure_failures")
            raise Sim4GenerationFailed("deadline publication closure failed") from None
        finally:
            self._end_transaction(cursor, success)

    def _new_target(self, fence: int, capture_kind: str) -> None:
        if capture_kind not in {"ACTIVATION", "RECONCILIATION"}:
            raise Sim4AuthorityError("invalid reconciliation capture kind")
        if fence < self._checkpoint_last:
            raise Sim4AuthorityError("captured fence precedes durable checkpoint")
        if (
            fence == self._checkpoint_last
            and capture_kind == "RECONCILIATION"
        ):
            # The capture opportunity still occurred, but there is no closed
            # interval to reconcile or checkpoint.  Avoid an empty compare-
            # and-advance write/version increment every second.  An activation
            # target is intentionally retained even when empty so the current
            # generation's monotonic-derived runtime start becomes durable.
            self._target = None
            return
        self._target = ReconciliationTarget(
            capture_kind=capture_kind,
            lower_publication_seq=self._checkpoint_last,
            fence_publication_seq=fence,
            expected_checkpoint_version=self._checkpoint_version,
        )

    def _discover_publication(
        self, published: PublishedSimulationIntent,
    ) -> PublicationRecord:
        # Share the quote/deadline mutex so a timely actionable discovery is
        # registered before any later strict-greater deadline observation.
        # No database work occurs while this mutex is held.
        with self._admission_lock:
            if self._anchor is None:
                raise Sim4GenerationFailed(
                    "publication discovered before runtime anchor"
                )
            discovered = self._anchor.derived_epoch_ns(self._monotonic_ns())
            publication = PublicationRecord(
                published.publication_seq,
                published.publication_at,
                published.horizon_order,
                published.intent,
                discovered,
            )
            if published.intent.status == "ACTIONABLE":
                if self._runtime_started_at is None:
                    raise Sim4GenerationFailed("runtime start is unavailable")
                deadline_ns = (
                    _datetime_to_epoch_nanoseconds(publication.publication_at)
                    + 2_000_000_000
                )
                if discovered <= deadline_ns:
                    forced = (
                        "SKIPPED_RESTART_GAP"
                        if publication.publication_at <= self._runtime_started_at
                        else None
                    )
                    self._remember_pending(
                        PendingIntent(
                            publication,
                            deadline_ns,
                            forced_status_after_deadline=forced,
                        )
                    )
            return publication

    def _load_target_page(self, store: SimulationEntryStore) -> None:
        target = self._target
        connection = self._owner_connection
        if target is None or connection is None or target.page:
            return
        cursor = connection.cursor()
        try:
            after = None
            if target.cursor is not None:
                after = PublicationCursor(*target.cursor)
            # Entry module owns exact relational/canonical validation.  The
            # lower-bound kwarg is part of the merged checkpoint interval API.
            try:
                page = store.load_publication_page_on_cursor(
                    cursor,
                    after_completed_publication_seq=target.lower_publication_seq,
                    captured_publication_fence=target.fence_publication_seq,
                    after=after,
                    limit=SIM4_RECONCILE_QUERY_ROWS,
                )
            except TypeError:
                # Do not silently weaken to an API that scans outside the
                # durable checkpoint interval.
                raise Sim4GenerationFailed(
                    "entry publication pager lacks checkpoint lower-bound support"
                )
            discovered_page: list[PublicationRecord] = []
            for row in page:
                known = self._pending.get(row.intent.intent_id)
                if known is not None:
                    preserved = known.publication
                    if (
                        preserved.publication_seq != row.publication_seq
                        or preserved.publication_at != row.publication_at
                        or preserved.horizon_order != row.horizon_order
                        or preserved.intent != row.intent
                    ):
                        raise Sim4GenerationFailed(
                            "rediscovered publication conflicts with known pending intent"
                        )
                    discovered_page.append(preserved)
                else:
                    discovered_page.append(self._discover_publication(row))
            target.page = discovered_page
            target.page_complete = False
            target.waiting_until_epoch_ns = None
            if not target.page:
                target.exhausted = True
        finally:
            cursor.close()

    def _existing_entry(
        self, store: SimulationEntryStore, intent: SimulationTradeIntent,
    ) -> SimulationEntryRecord | None:
        """Probe immutable terminal precedence under the horizon xact lock."""

        cursor = self._begin_transaction()
        success = False
        try:
            entry = store.get_existing_entry_in_transaction(cursor, intent)
            success = True
            return entry
        finally:
            self._end_transaction(cursor, success)

    def _terminalize(
        self,
        store: SimulationEntryStore,
        publication: PublicationRecord,
        requested_status: str,
        quote: object | None = None,
    ) -> SimulationEntryRecord:
        cursor = self._begin_transaction()
        success = False
        try:
            typed_quote = quote if isinstance(quote, SimulationExecutableQuote) else None
            if requested_status == "ENTERED" and typed_quote is None:
                raise Sim4AuthorityError("ENTERED terminalization lacks an exact quote")
            result, entry = store.terminalize_in_transaction(
                cursor,
                publication.intent,
                requested_status=requested_status,
                quote=typed_quote,
            )
            if result not in {INSERTED, IDEMPOTENT}:
                raise Sim4AuthorityError("entry store returned an invalid terminal result")
            success = True
            return entry
        except BaseException:
            self.telemetry.increment("terminal_failures")
            raise
        finally:
            self._end_transaction(cursor, success)

    def _classify_publication(
        self,
        store: SimulationEntryStore,
        publication: PublicationRecord,
    ) -> bool:
        intent = publication.intent
        existing = self._existing_entry(store, intent)
        if existing is not None:
            self._pending.pop(intent.intent_id, None)
            return True
        if intent.status == "NO_TRADE":
            self._terminalize(store, publication, "SKIPPED_NO_TRADE")
            return True
        if intent.status == "UNAVAILABLE":
            self._terminalize(store, publication, "SKIPPED_UNAVAILABLE")
            return True
        if self._runtime_started_epoch_ns is None or self._runtime_started_at is None:
            raise Sim4GenerationFailed("runtime start is unavailable")
        publication_ns = _datetime_to_epoch_nanoseconds(publication.publication_at)
        deadline_ns = publication_ns + 2_000_000_000
        if publication.publication_at <= self._runtime_started_at:
            if publication.discovered_epoch_ns > deadline_ns:
                self._terminalize(store, publication, "SKIPPED_RESTART_GAP")
                return True
            self._remember_pending(
                PendingIntent(
                    publication, deadline_ns,
                    forced_status_after_deadline="SKIPPED_RESTART_GAP",
                )
            )
            return False
        closure = self._deadline_closures.get(deadline_ns)
        if closure is not None and closure.publication_fence is not None:
            if publication.publication_seq > closure.publication_fence:
                self._terminalize(store, publication, "SKIPPED_WINDOW_EXPIRED")
                self._pending.pop(intent.intent_id, None)
                return True
            quote = (
                closure.candidates[intent.intent_id]
                if intent.intent_id in closure.candidates
                else select_executable_quote(intent, closure.admitted_quotes)
            )
            requested = "ENTERED" if quote is not None else "SKIPPED_WINDOW_EXPIRED"
            self._terminalize(store, publication, requested, quote)
            self._pending.pop(intent.intent_id, None)
            return True
        if publication.discovered_epoch_ns > deadline_ns:
            # Without an earlier immutable publication fence, a first-late
            # discovery cannot inspect retained quotes.
            self._terminalize(store, publication, "SKIPPED_WINDOW_EXPIRED")
            return True
        self._remember_pending(PendingIntent(publication, deadline_ns))
        return False

    def _remember_pending(self, pending: PendingIntent) -> None:
        intent_id = pending.publication.intent.intent_id
        existing = self._pending.get(intent_id)
        if existing is not None:
            if (
                existing.publication != pending.publication
                or existing.deadline_epoch_ns != pending.deadline_epoch_ns
                or existing.forced_status_after_deadline
                != pending.forced_status_after_deadline
            ):
                raise Sim4GenerationFailed("pending intent identity changed")
            return
        if len(self._pending) >= SIM4_PENDING_INTENT_CAPACITY:
            raise Sim4GenerationFailed("bounded pending-intent capacity exhausted")
        self._pending[intent_id] = pending

    def _process_target_page(self, store: SimulationEntryStore) -> bool:
        target = self._target
        if target is None:
            return False
        if (
            target.retry_not_before_monotonic is not None
            and self._monotonic() < target.retry_not_before_monotonic
        ):
            return False
        target.retry_not_before_monotonic = None
        if target.exhausted and not target.page:
            return self._advance_checkpoint(store)
        self._load_target_page(store)
        if target.exhausted:
            return self._advance_checkpoint(store)
        all_terminal = True
        target.waiting_until_epoch_ns = None
        for publication in target.page:
            if not self._classify_publication(store, publication):
                all_terminal = False
        if not all_terminal:
            page_ids = {row.intent.intent_id for row in target.page}
            pending_deadlines = [
                pending.deadline_epoch_ns
                for intent_id, pending in self._pending.items()
                if intent_id in page_ids
            ]
            target.waiting_until_epoch_ns = min(
                pending_deadlines
                or [
                    _datetime_to_epoch_nanoseconds(row.publication_at)
                    + 2_000_000_000
                    for row in target.page
                ]
            )
            return False
        last = target.page[-1]
        target.cursor = last.semantic_key
        if len(target.page) < SIM4_RECONCILE_QUERY_ROWS:
            target.exhausted = True
        target.page.clear()
        target.page_complete = True
        target.waiting_until_epoch_ns = None
        self._ordinary_since_slice = False
        return True

    def _advance_checkpoint(self, store: SimulationEntryStore) -> bool:
        target = self._target
        if target is None or self._runtime_started_at is None:
            return False
        cursor = self._begin_transaction()
        success = False
        try:
            advanced = store.compare_and_advance_checkpoint_on_cursor(
                cursor,
                expected_last_completed_publication_seq=target.lower_publication_seq,
                expected_checkpoint_version=target.expected_checkpoint_version,
                new_last_completed_publication_seq=target.fence_publication_seq,
                capture_kind=target.capture_kind,
                captured_publication_fence=target.fence_publication_seq,
                runtime_started_at=self._runtime_started_at,
            )
            if not advanced:
                target.retry_not_before_monotonic = (
                    self._monotonic() + SIM4_RUNTIME_OWNER_RETRY_SECONDS
                )
                return False
            success = True
            self._checkpoint_last = target.fence_publication_seq
            self._checkpoint_version = target.expected_checkpoint_version + 1
            self._target = None
            for deadline_ns, closure in tuple(self._deadline_closures.items()):
                if (
                    closure.publication_fence is not None
                    and closure.publication_fence <= self._checkpoint_last
                    and not any(
                        pending.deadline_epoch_ns == deadline_ns
                        for pending in self._pending.values()
                    )
                ):
                    self._deadline_closures.pop(deadline_ns, None)
            return True
        finally:
            self._end_transaction(cursor, success)

    def _drain_one_quote_event(self) -> bool:
        try:
            envelope = self._events.get_nowait()
        except Empty:
            return False
        try:
            self._retain_admitted_quote(envelope, allow_safe_eviction=True)
            self._ordinary_since_slice = True
            return True
        finally:
            self._events.task_done()

    def _drain_through(self, watermark: int) -> None:
        while self._last_drained_sequence < watermark:
            try:
                envelope = self._events.get(timeout=SIM4_BOUNDARY_RECHECK_SECONDS)
            except Empty:
                continue
            try:
                if envelope.admission_sequence > watermark:
                    raise Sim4GenerationFailed("quote FIFO crossed its deadline watermark")
                self._retain_admitted_quote(envelope, allow_safe_eviction=False)
            finally:
                self._events.task_done()

    def _retain_admitted_quote(
        self,
        envelope: AdmissionEnvelope,
        *,
        allow_safe_eviction: bool,
    ) -> None:
        if allow_safe_eviction:
            self._evict_before_ordinary_capacity_check()
        if len(self._quotes) >= SIM4_QUOTE_BUFFER_CAPACITY:
            self.telemetry.increment("quote_buffer_full")
            # The frozen overflow rule retains every nonexpired older quote
            # and drops only this incoming buffer candidate.  It is still a
            # consumed FIFO envelope, so its immutable sequence is advanced
            # and a deadline watermark drain cannot stall on dropped input.
        else:
            self._quotes.append(envelope)
        self._last_drained_sequence = envelope.admission_sequence

    def _due_deadline(self) -> int | None:
        return min((pending.deadline_epoch_ns for pending in self._pending.values()), default=None)

    def _earliest_quote_expiry(self) -> int | None:
        expiries: list[int] = []
        for envelope in self._quotes:
            try:
                expiries.append(
                    _datetime_to_epoch_nanoseconds(envelope.quote.accepted_at)
                    + 2_000_000_000
                )
            except (AttributeError, TypeError, ValueError):
                continue
        return min(expiries, default=None)

    def _terminalize_forced_deadline_paths(
        self,
        store: SimulationEntryStore,
        deadline_ns: int,
    ) -> None:
        forced = sorted(
            (
                pending for pending in self._pending.values()
                if pending.deadline_epoch_ns == deadline_ns
                and pending.forced_status_after_deadline is not None
            ),
            key=lambda pending: (
                pending.publication.publication_at,
                pending.publication.horizon_order,
                pending.publication.intent.intent_id,
            ),
        )
        for pending in forced:
            status = pending.forced_status_after_deadline
            if status != "SKIPPED_RESTART_GAP":
                raise Sim4GenerationFailed("invalid forced deadline path")
            # Restart paths do not create a publication closure and never
            # inspect quotes; store-level collision precedence still applies.
            self._terminalize(store, pending.publication, status)
            self._pending.pop(pending.publication.intent.intent_id, None)

    def _begin_due_deadline(
        self,
        deadline_ns: int,
        *,
        sampled: tuple[bool, int, int] | None = None,
    ) -> bool:
        greater, _, watermark = (
            self._deadline_sample(deadline_ns) if sampled is None else sampled
        )
        if not greater:
            return False
        self._drain_through(watermark)
        admitted_quotes = tuple(
            envelope.quote
            for envelope in self._quotes
            if (
                envelope.admission_sequence <= watermark
                and isinstance(envelope.quote, SimulationExecutableQuote)
            )
        )
        due = [pending for pending in self._pending.values()
               if pending.deadline_epoch_ns == deadline_ns
               and pending.forced_status_after_deadline is None]
        candidates: dict[str, object | None] = {}
        for pending in due:
            candidates[pending.publication.intent.intent_id] = select_executable_quote(
                pending.publication.intent,
                admitted_quotes,
            )
            pending.admission_watermark = watermark
            pending.selected_quote = candidates[pending.publication.intent.intent_id]
        # Freeze the complete local quote input before the blocking DB closure;
        # rows not yet paged can derive only from this bounded snapshot.
        fence = self._capture_deadline_publication_fence()
        closure = DeadlineClosure(
            deadline_ns,
            watermark,
            candidates,
            fence,
            admitted_quotes=admitted_quotes,
        )
        self._deadline_closures[deadline_ns] = closure
        # Deadline work supersedes an incomplete activation/periodic runtime
        # cursor.  Rebuild from the durable checkpoint through the immutable
        # deadline fence so inverted publication sequences are reconsidered in
        # full semantic order.  Already-known discovery instants remain in
        # ``_pending`` and are preserved when those rows are rediscovered.
        self._new_target(fence, "RECONCILIATION")
        return True

    def _complete_deadline_if_reconciled(
        self, store: SimulationEntryStore, deadline_ns: int,
    ) -> bool:
        closure = self._deadline_closures.get(deadline_ns)
        if closure is None or closure.publication_fence is None:
            return False
        # A still-open target below or through the deadline fence means the
        # complete durable same-horizon predecessor set is not yet proven.
        if self._checkpoint_last < closure.publication_fence:
            return False
        due = sorted(
            (pending for pending in self._pending.values()
             if pending.deadline_epoch_ns == deadline_ns),
            key=lambda pending: (
                pending.publication.publication_at,
                pending.publication.horizon_order,
                pending.publication.intent.intent_id,
            ),
        )
        for pending in due:
            if pending.publication.publication_seq > closure.publication_fence:
                requested = "SKIPPED_WINDOW_EXPIRED"
                quote = None
            else:
                quote = closure.candidates.get(pending.publication.intent.intent_id)
                requested = "ENTERED" if quote is not None else "SKIPPED_WINDOW_EXPIRED"
            self._terminalize(store, pending.publication, requested, quote)
            self._pending.pop(pending.publication.intent.intent_id, None)
        closure.reconciliation_complete = True
        # Once the closed fence is durably checkpointed and no due pending row
        # remains, a first-late publication is independently expired by its
        # discovery time and cannot consult this cache.  Release the runtime
        # object to preserve finite memory over unlimited durable history.
        self._deadline_closures.pop(deadline_ns, None)
        return True

    def _evict_quotes_after_deadlines(self, now_epoch_ns: int) -> None:
        # Every already-due pending deadline preempts eviction, not only the
        # deadline that led to this call.  A slow closure for D1 may cross D2;
        # D2 must still fix/drain its watermark before a candidate is removed.
        earliest_pending_deadline = self._due_deadline()
        if (
            earliest_pending_deadline is not None
            and now_epoch_ns >= earliest_pending_deadline
        ):
            return
        # With no due pending boundary, a quote older than accepted_at+2s
        # cannot serve any timely future publication.
        retained: deque[AdmissionEnvelope] = deque()
        for envelope in self._quotes:
            try:
                expiry_ns = (
                    _datetime_to_epoch_nanoseconds(envelope.quote.accepted_at)
                    + 2_000_000_000
                )
            except (AttributeError, TypeError, ValueError):
                continue
            if now_epoch_ns <= expiry_ns:
                retained.append(envelope)
        self._quotes = retained

    def _evict_before_ordinary_capacity_check(self) -> None:
        """Free only provably unusable quotes before an ordinary append.

        A pending boundary at or before the sampled logical instant preempts
        eviction, including exact equality.  Its strict-greater watermark and
        fixed-set drain must execute first in the owner loop.
        """

        if self._anchor is None or not self._quotes:
            return
        now_epoch_ns = self._anchor.derived_epoch_ns(self._monotonic_ns())
        earliest = self._due_deadline()
        if earliest is not None and now_epoch_ns >= earliest:
            return
        self._evict_quotes_after_deadlines(now_epoch_ns)

    def _ready_loop(self, store: SimulationEntryStore, activation_fence: int) -> None:
        self._new_target(activation_fence, "ACTIVATION")
        self._next_periodic_opportunity = self._monotonic() + SIM4_PERIODIC_CAPTURE_SECONDS
        self._set_state("READY")
        while not self._stop_requested.is_set() and not self._generation_failed:
            boundary_recheck = False
            cached_deadline_retry_waiting = False
            due = self._due_deadline()
            if due is not None:
                cached_closure = self._deadline_closures.get(due)
                if cached_closure is not None:
                    target = self._target
                    processed_deadline_page = False
                    if (
                        target is not None
                        and not self._ordinary_since_slice
                        and self._drain_one_quote_event()
                    ):
                        continue
                    if (
                        target is not None
                        and target.retry_not_before_monotonic is not None
                        and self._monotonic() < target.retry_not_before_monotonic
                    ):
                        # Checkpoint retry backoff must yield to ordinary FIFO
                        # servicing rather than pausing the owner thread and
                        # filling the bounded receiver queue.
                        cached_deadline_retry_waiting = True
                    else:
                        if target is not None:
                            processed_deadline_page = self._process_target_page(
                                store
                            )
                        elif (
                            cached_closure.publication_fence is not None
                            and cached_closure.publication_fence > self._checkpoint_last
                        ):
                            self._new_target(
                                cached_closure.publication_fence, "RECONCILIATION",
                            )
                        completed = self._complete_deadline_if_reconciled(store, due)
                        if completed and self._anchor is not None:
                            self._evict_quotes_after_deadlines(
                                self._anchor.derived_epoch_ns(self._monotonic_ns())
                            )
                        if (
                            processed_deadline_page
                            and self._target is not None
                        ):
                            self._drain_one_quote_event()
                        # The first immutable watermark/fence pair drives all
                        # later work for D; never sample a replacement watermark.
                        continue
                if not cached_deadline_retry_waiting:
                    greater, now_ns, watermark = self._deadline_sample(due)
                    if greater:
                        self._terminalize_forced_deadline_paths(store, due)
                        if (
                            self._target is not None
                            and self._target.waiting_until_epoch_ns == due
                        ):
                            self._target.waiting_until_epoch_ns = None
                            self._process_target_page(store)
                        ordinary_due = any(
                            pending.deadline_epoch_ns == due
                            for pending in self._pending.values()
                        )
                        if not ordinary_due:
                            self._evict_quotes_after_deadlines(now_ns)
                            continue
                        if due not in self._deadline_closures:
                            # Reuse the first strict-greater observation and its
                            # watermark; no second sample may widen the fence.
                            self._begin_due_deadline(
                                due, sampled=(greater, now_ns, watermark),
                            )
                        processed_deadline_page = False
                        if self._target is not None:
                            processed_deadline_page = self._process_target_page(
                                store
                            )
                        elif (
                            self._deadline_closures[due].publication_fence is not None
                            and self._deadline_closures[due].publication_fence
                            > self._checkpoint_last
                        ):
                            self._new_target(
                                self._deadline_closures[due].publication_fence,
                                "RECONCILIATION",
                            )
                        completed = self._complete_deadline_if_reconciled(store, due)
                        if completed:
                            self._evict_quotes_after_deadlines(now_ns)
                        if (
                            processed_deadline_page
                            and self._target is not None
                        ):
                            self._drain_one_quote_event()
                        continue
                    if now_ns == due:
                        boundary_recheck = True

            quote_expiry = self._earliest_quote_expiry()
            if (
                quote_expiry is not None
                and self._anchor is not None
                and not cached_deadline_retry_waiting
            ):
                quote_now_ns = self._anchor.derived_epoch_ns(self._monotonic_ns())
                if quote_now_ns > quote_expiry:
                    if due is not None and quote_now_ns >= due:
                        # The independent clock read above may have crossed a
                        # deadline that the earlier deadline sample had not,
                        # even when this particular quote expired before D.
                        # Re-enter at the higher-priority boundary before any
                        # eviction.
                        continue
                    else:
                        self._evict_quotes_after_deadlines(quote_now_ns)
                        continue
                if quote_now_ns == quote_expiry:
                    boundary_recheck = True

            now = self._monotonic()
            if (
                not boundary_recheck
                and self._target is None
                and now >= self._next_periodic_opportunity
            ):
                fence = self._try_periodic_capture()
                opportunity_completed = self._monotonic()
                self._next_periodic_opportunity = (
                    opportunity_completed + SIM4_PERIODIC_CAPTURE_SECONDS
                )
                if fence is not None:
                    self._new_target(fence, "RECONCILIATION")

            if (
                not boundary_recheck
                and
                self._target is not None
                and self._target.waiting_until_epoch_ns is None
                and (
                    self._target.retry_not_before_monotonic is None
                    or self._monotonic() >= self._target.retry_not_before_monotonic
                )
                and (self._ordinary_since_slice or self._events.empty())
            ):
                self._process_target_page(store)
                continue

            if self._drain_one_quote_event():
                continue

            now = self._monotonic()
            timeout = SIM4_RUNTIME_OWNER_RETRY_SECONDS
            if self._target is None:
                timeout = min(
                    timeout,
                    max(0.0, self._next_periodic_opportunity - now),
                )
            if (
                due is not None
                and self._anchor is not None
                and not cached_deadline_retry_waiting
            ):
                derived_now = self._anchor.derived_epoch_ns(self._monotonic_ns())
                remaining = max(0, due - derived_now) / 1_000_000_000
                timeout = min(timeout, remaining if remaining > 0 else SIM4_BOUNDARY_RECHECK_SECONDS)
                if remaining == 0:
                    timeout = min(timeout, SIM4_BOUNDARY_RECHECK_SECONDS)
            if (
                quote_expiry is not None
                and self._anchor is not None
                and not cached_deadline_retry_waiting
            ):
                derived_now = self._anchor.derived_epoch_ns(self._monotonic_ns())
                quote_remaining = max(0, quote_expiry - derived_now) / 1_000_000_000
                timeout = min(
                    timeout,
                    quote_remaining if quote_remaining > 0
                    else SIM4_BOUNDARY_RECHECK_SECONDS,
                )
            if (
                self._target is not None
                and self._target.retry_not_before_monotonic is not None
            ):
                timeout = min(
                    timeout,
                    max(0.0, self._target.retry_not_before_monotonic - self._monotonic()),
                )
            try:
                envelope = self._events.get(timeout=max(timeout, 0.0))
            except Empty:
                continue
            try:
                self._retain_admitted_quote(envelope, allow_safe_eviction=True)
                self._ordinary_since_slice = True
            finally:
                self._events.task_done()

    def _run(self) -> None:
        store: SimulationEntryStore | None = None
        try:
            self._set_state("STANDBY")
            while not self._stop_requested.is_set() and self._owner_connection is None:
                candidate = self._candidate_connection()
                if candidate is not None:
                    self._owner_connection = candidate
                    break
                if self._stop_wait(SIM4_RUNTIME_OWNER_RETRY_SECONDS):
                    return
            if self._stop_requested.is_set() or self._owner_connection is None:
                return
            self._set_state("RECOVERING")
            store = self._verify_startup()
            if not self._wait_for_sip_readiness():
                return
            activation_fence = None
            while not self._stop_requested.is_set() and activation_fence is None:
                try:
                    activation_fence = self._activation_capture(store)
                except BaseException as error:
                    if not _is_statement_timeout(error):
                        raise
                    # A clean 100ms contention/timeout may yield only if the
                    # stable owned backend can still prove its identity.
                    cursor = self._owner_connection.cursor()
                    try:
                        self._assert_backend_pid(cursor)
                    finally:
                        cursor.close()
                    activation_fence = None
                if activation_fence is None:
                    self._stop_wait(SIM4_RUNTIME_OWNER_RETRY_SECONDS)
            if activation_fence is None:
                return
            self._ready_loop(store, activation_fence)
        except BaseException:
            self._generation_failed = True
            with self._admission_lock:
                self._admission_enabled = False
            self._set_state("FAILED")
        finally:
            with self._admission_lock:
                self._admission_enabled = False
            receiver = self._receiver
            if receiver is not None:
                try:
                    receiver.stop()
                except BaseException:
                    pass
                try:
                    receiver.join(SIM4_PUBLIC_STOP_JOIN_SECONDS)
                except BaseException:
                    pass
            # Intake is disabled and reconciliation has stopped.  Drain the
            # finite runtime queue without making decisions; durable intents
            # remain restart-recoverable and in-memory quotes are never
            # reconstructed by a successor.
            while True:
                try:
                    self._events.get_nowait()
                except Empty:
                    break
                else:
                    self._events.task_done()
            self._quotes.clear()
            self._pending.clear()
            self._deadline_closures.clear()
            self._target = None
            # Only this finalizer, after the decision loop and every terminal
            # transaction are impossible, may release the owner session.
            connection = self._owner_connection
            if connection is not None:
                cursor = None
                try:
                    if self._owner_acquired:
                        cursor = connection.cursor()
                        cursor.execute(_OWNER_UNLOCK_SQL, (SIM4_RUNTIME_OWNER_LOCK_KEY,))
                        row = cursor.fetchone()
                        if row not in ((True,), (False,)):
                            raise Sim4AuthorityError("owner unlock result is malformed")
                except BaseException:
                    pass
                finally:
                    if cursor is not None:
                        try:
                            cursor.close()
                        except BaseException:
                            pass
                    try:
                        connection.close()
                    except BaseException:
                        pass
            self._owner_connection = None
            self._owner_acquired = False
            if self.state != "FAILED":
                self._set_state("STOPPED")


def _install_termination_handlers(stop_event: threading.Event) -> None:
    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)


def wait_disabled_until_termination(
    *,
    stop_event: threading.Event | None = None,
    install_signal_handlers: bool = True,
) -> None:
    """Keep a disabled Render worker stable without DB or network activity."""

    event = stop_event or threading.Event()
    if install_signal_handlers:
        _install_termination_handlers(event)
    while not event.wait(60.0):
        pass


def main(
    environ: Mapping[str, str] | None = None,
    *,
    stop_event: threading.Event | None = None,
    connection_factory: Callable[[], _Connection] | None = None,
    token_requester: TokenRequester | None = None,
    websocket_factory: Callable[..., object] | None = None,
    install_signal_handlers: bool = True,
) -> int:
    """Run the dedicated worker; disabled mode performs zero DB/network I/O."""

    values = os.environ if environ is None else environ
    event = stop_event or threading.Event()
    if values.get(SIM4_ENABLED_ENV) != "true":
        wait_disabled_until_termination(
            stop_event=event, install_signal_handlers=install_signal_handlers,
        )
        return 0
    if install_signal_handlers:
        _install_termination_handlers(event)
    config = load_sim4_config(values)
    worker = SimulationEntryWorker.from_config(
        config,
        connection_factory=connection_factory,
        token_requester=token_requester,
        websocket_factory=websocket_factory,
    )
    telemetry_snapshot = _fail_closed_telemetry_snapshot(worker.telemetry)
    worker.start()
    next_telemetry_log = time.monotonic() + SIM4_TELEMETRY_LOG_INTERVAL_SECONDS
    try:
        while not event.wait(0.25):
            state = worker.state
            now = time.monotonic()
            if state == "FAILED" or now >= next_telemetry_log:
                telemetry_snapshot = _log_fail_closed_telemetry_changes(
                    worker.telemetry, telemetry_snapshot)
                next_telemetry_log = now + SIM4_TELEMETRY_LOG_INTERVAL_SECONDS
            if state == "FAILED":
                return 1
        return 0
    finally:
        worker.stop()
        _log_fail_closed_telemetry_changes(
            worker.telemetry, telemetry_snapshot)


if __name__ == "__main__":
    raise SystemExit(main())
