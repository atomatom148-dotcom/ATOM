"""Bounded offline HIST8 acquisition, validation, derivation, and persistence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterator, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import parse_qsl, unquote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zlib


CORPUS_ID = "HIST8_20240901_20260901_V1"
DERIVATION_VERSION = "HIST8_DERIVE_1"
CALENDAR_VERSION = "HIST8_CALENDAR_1"
START = datetime(2024, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 1, tzinfo=timezone.utc)
PROJECT_REF = "pjbjpgnmniwcajqkuhge"
DATABASE_NAME = "postgres"
DATABASE_HOST = "db.pjbjpgnmniwcajqkuhge.supabase.co"
IMPORTER_ROLE = "atom_hist8_importer"
IMPORT_DATABASE_ENV = "ATOM_HIST8_IMPORT_DATABASE_URL"
INSTALLER_ROLE = "postgres"
INSTALL_DATABASE_ENV = "ATOM_HIST8_INSTALL_DATABASE_URL"
EQUITIES = ("COIN", "QQQ", "SPY", "NVDA", "XLE", "GLD")
INSTRUMENTS = (*EQUITIES, "BTC-USD", "NASDAQ")
TIMEFRAMES = ("1m", "5m", "15m", "30m", "1H")
TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "1H": 60}
PARTITIONS = {
    "training": (START, datetime(2026, 3, 1, tzinfo=timezone.utc)),
    "validation": (
        datetime(2026, 3, 1, tzinfo=timezone.utc),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    ),
    "test": (datetime(2026, 6, 1, tzinfo=timezone.utc), END),
}
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/bars"
COINBASE_URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
MASSIVE_URL = (
    "https://api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
    "2024-09-01/2026-09-01"
)
MASSIVE_FROZEN_PARAMS = {
    "adjusted": "false", "sort": "asc", "limit": "50000",
}

_ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.(?P<fraction>\d+))?(?:Z|[+-]\d{2}:\d{2})$"
)


class Hist8Error(RuntimeError):
    pass


class Hist8ConflictError(Hist8Error):
    pass


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, _request, _file, _code, _message, _headers, _new_url):
        return None


_NO_REDIRECT_OPENER = build_opener(_RejectRedirects())


def _no_redirect_urlopen(request: Request, *, timeout: int):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


@dataclass(frozen=True, slots=True)
class RawPage:
    source: str
    feed: str
    product: str
    instruments: tuple[str, ...]
    endpoint: str
    request_params: Mapping[str, str]
    retrieved_at: datetime
    http_status: int
    content_type: str | None
    content_encoding: str | None
    body: bytes

    def decoded_body(self) -> bytes:
        encoding = (self.content_encoding or "").lower().strip()
        if not encoding or encoding == "identity":
            return self.body
        if encoding == "gzip":
            return gzip.decompress(self.body)
        if encoding == "deflate":
            return zlib.decompress(self.body)
        raise Hist8Error(f"unsupported content encoding: {encoding}")

    def payload(self) -> object:
        try:
            return json.loads(
                self.decoded_body().decode("utf-8"), parse_float=Decimal,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation) as exc:
            raise Hist8Error("provider response is not valid decimal JSON") from exc


@dataclass(frozen=True, slots=True)
class SourceBar:
    instrument: str
    start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    trade_count: int | None
    vwap: Decimal | None
    artifact_id: str
    locator: str
    source: str
    feed: str
    product: str
    adjustment: str
    volume_unit: str


@dataclass(frozen=True, slots=True)
class Bar:
    bar_id: str
    content_hash: str
    corpus_id: str
    instrument: str
    timeframe: str
    bar_start_utc: datetime
    bar_end_utc: datetime
    session_date: str
    calendar_id: str
    calendar_sha256: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    trade_count: int | None
    vwap: Decimal | None
    volume_unit: str
    source: str
    feed: str
    product: str
    adjustment: str
    currency: str
    import_id: str
    derivation_version: str | None
    source_artifact_id: str | None
    source_record_locator: str | None
    lineage: tuple[str, ...]
    research_eligible: bool


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("nonfinite decimal")
        # Avoid Decimal.normalize(): it applies the active precision context and
        # can collapse distinct high-precision provider values before hashing.
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


def sha256(value: object) -> str:
    raw = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(raw).hexdigest()


def _exact_decimal_sum(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal(0)
    minimum_exponent = min(value.as_tuple().exponent for value in values)
    maximum_adjusted = max(value.adjusted() for value in values)
    precision = max(
        28,
        maximum_adjusted - minimum_exponent + 1 + len(str(len(values))),
    )
    with localcontext() as context:
        context.prec = precision
        return sum(values, Decimal(0))


def load_calendar(path: Path | None = None) -> dict[str, object]:
    target = path or Path(__file__).with_name("calendar_manifest.json")
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("calendar_manifest_version") != CALENDAR_VERSION:
        raise Hist8Error("calendar version mismatch")
    if data.get("corpus_id") != CORPUS_ID:
        raise Hist8Error("calendar corpus mismatch")
    if (data.get("start_inclusive") != "2024-09-01T00:00:00Z"
            or data.get("end_exclusive") != "2026-09-01T00:00:00Z"
            or data.get("timezone") != "America/New_York"
            or not data.get("timezone_database_version")):
        raise Hist8Error("calendar control metadata mismatch")
    expected_calendars = {instrument: "US_CASH_RTH" for instrument in EQUITIES}
    expected_calendars.update({"NASDAQ": "NASDAQ_CASH_RTH", "BTC-USD": "BTC_UTC_DAY"})
    if data.get("instrument_calendars") != expected_calendars:
        raise Hist8Error("instrument calendar binding mismatch")
    payload = {
        "btc_utc_dates": data.get("btc_utc_dates"),
        "us_cash_sessions": data.get("us_cash_sessions"),
    }
    if sha256(payload) != data.get("schedule_sha256"):
        raise Hist8Error("calendar schedule hash mismatch")
    sessions = data["us_cash_sessions"]
    if not isinstance(sessions, list) or not sessions:
        raise Hist8Error("calendar sessions missing")
    dates = [row["date"] for row in sessions]
    if dates != sorted(set(dates)):
        raise Hist8Error("calendar sessions are not unique and ordered")
    btc_dates = data["btc_utc_dates"]
    if btc_dates != sorted(set(btc_dates)) or len(btc_dates) != 730:
        raise Hist8Error("BTC UTC schedule mismatch")
    return data


def _iso_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise Hist8Error("provider timestamp must be a string")
    match = _ISO_TIMESTAMP.fullmatch(value)
    if match is None:
        raise Hist8Error("invalid provider timestamp")
    fraction = match.group("fraction") or ""
    if len(fraction) > 6 and any(digit != "0" for digit in fraction[6:]):
        raise Hist8Error("provider timestamp has sub-microsecond precision")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Hist8Error("invalid provider timestamp") from exc
    if parsed.tzinfo is None:
        raise Hist8Error("provider timestamp is naive")
    return parsed.astimezone(timezone.utc)


def _decimal(value: object, *, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise Hist8Error("boolean numerical value")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise Hist8Error("invalid decimal value") from exc
    if not number.is_finite():
        raise Hist8Error("nonfinite decimal value")
    return number


def _integer(value: object, *, name: str) -> int:
    number = _decimal(value)
    assert isinstance(number, Decimal)
    if number != number.to_integral_value():
        raise Hist8Error(f"{name} is not an integer")
    return int(number)


def _http_get(
    url: str, *, headers: Mapping[str, str], timeout: int = 30,
    opener: Callable[..., object] = _no_redirect_urlopen,
) -> tuple[int, Mapping[str, str], bytes]:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        response = opener(request, timeout=timeout)
        with response:
            final_url = response.geturl() if hasattr(response, "geturl") else url
            if final_url != url:
                raise Hist8Error("provider redirect is forbidden")
            return int(response.status), dict(response.headers.items()), response.read()
    except HTTPError as exc:
        with exc:
            return int(exc.code), dict(exc.headers.items()), exc.read()


def _build_page(
    *, source: str, feed: str, product: str, instruments: Sequence[str],
    endpoint: str, params: Mapping[str, str], headers: Mapping[str, str],
    opener: Callable[..., object], clock: Callable[[], datetime],
) -> RawPage:
    query = urlencode(params)
    url = endpoint + ("?" if "?" not in endpoint else "&") + query
    status, response_headers, body = _http_get(url, headers=headers, opener=opener)
    return RawPage(
        source, feed, product, tuple(instruments), endpoint, dict(params), clock(),
        status, response_headers.get("Content-Type"),
        response_headers.get("Content-Encoding"), body,
    )


def alpaca_pages(
    key: str, secret: str, *, opener: Callable[..., object] = _no_redirect_urlopen,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Iterator[RawPage]:
    if not key or not secret:
        raise Hist8Error("Alpaca credentials missing")
    token: str | None = None
    seen: set[str] = set()
    for _ in range(1000):
        params = {
            "symbols": ",".join(EQUITIES), "timeframe": "1Min",
            "start": START.isoformat().replace("+00:00", "Z"),
            "end": END.isoformat().replace("+00:00", "Z"),
            "limit": "10000", "adjustment": "raw", "feed": "sip",
            "sort": "asc", "asof": "2026-09-01", "currency": "USD",
        }
        if token is not None:
            params["page_token"] = token
        page = _build_page(
            source="ALPACA", feed="SIP", product="1Min trade OHLCV",
            instruments=EQUITIES, endpoint=ALPACA_URL, params=params,
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            opener=opener, clock=clock,
        )
        yield page
        if page.http_status != 200:
            raise Hist8Error(f"Alpaca HTTP {page.http_status}")
        payload = page.payload()
        if not isinstance(payload, dict) or "bars" not in payload:
            raise Hist8Error("malformed Alpaca page")
        next_token = payload.get("next_page_token")
        if next_token is None:
            return
        if not isinstance(next_token, str) or not next_token or next_token in seen:
            raise Hist8Error("invalid Alpaca pagination")
        seen.add(next_token)
        token = next_token
    raise Hist8Error("Alpaca page bound exceeded")


def coinbase_pages(
    *, opener: Callable[..., object] = _no_redirect_urlopen,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Iterator[RawPage]:
    cursor = START
    for _ in range(4000):
        if cursor >= END:
            return
        stop = min(cursor + timedelta(minutes=300), END)
        params = {
            "granularity": "60",
            "start": cursor.isoformat().replace("+00:00", "Z"),
            "end": stop.isoformat().replace("+00:00", "Z"),
        }
        page = _build_page(
            source="COINBASE", feed="EXCHANGE", product="BTC-USD granularity=60",
            instruments=("BTC-USD",), endpoint=COINBASE_URL, params=params,
            headers={"User-Agent": "ATOM-HIST8/1"}, opener=opener, clock=clock,
        )
        yield page
        if page.http_status != 200 or not isinstance(page.payload(), list):
            raise Hist8Error(f"Coinbase HTTP/payload failure {page.http_status}")
        cursor = stop
    raise Hist8Error("Coinbase request bound exceeded")


def _strip_secret_query(url: str) -> tuple[str, dict[str, str]]:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "api.massive.com"
            or parsed.port is not None or parsed.username is not None
            or parsed.password is not None or parsed.fragment):
        raise Hist8Error("Massive pagination resource mismatch")
    segments = unquote(parsed.path).strip("/").split("/")
    expected_prefix = [
        "v2", "aggs", "ticker", "I:COMP", "range", "1", "minute",
    ]
    if len(segments) != 9 or segments[:7] != expected_prefix:
        raise Hist8Error("Massive pagination resource mismatch")
    start_token, end_token = segments[7:]
    if start_token == "2024-09-01":
        page_start_ms = int(START.timestamp() * 1000)
    elif start_token.isascii() and start_token.isdigit():
        page_start_ms = int(start_token)
    else:
        raise Hist8Error("Massive pagination resource mismatch")
    frozen_start_ms = int(START.timestamp() * 1000)
    frozen_end_ms = int(END.timestamp() * 1000)
    if (not frozen_start_ms <= page_start_ms < frozen_end_ms
            or end_token not in {"2026-09-01", str(frozen_end_ms)}):
        raise Hist8Error("Massive pagination resource mismatch")
    supplied: dict[str, str] = {}
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_key = key.lower()
        if normalized_key not in {
            "adjusted", "sort", "limit", "cursor", "apikey",
        } or normalized_key in supplied:
            raise Hist8Error("Massive pagination parameter mismatch")
        supplied[normalized_key] = value
    for name, frozen_value in MASSIVE_FROZEN_PARAMS.items():
        if name in supplied and supplied[name] != frozen_value:
            raise Hist8Error("Massive pagination parameter mismatch")
    cursor = supplied.get("cursor")
    if not cursor:
        raise Hist8Error("Massive pagination parameter mismatch")
    # Provider next_url examples contain only a cursor. Rebuild every request
    # from the frozen semantic parameters, and never retain a URL API key.
    endpoint = f"https://api.massive.com{parsed.path}"
    return endpoint, {**MASSIVE_FROZEN_PARAMS, "cursor": cursor}


def massive_pages(
    key: str, *, opener: Callable[..., object] = _no_redirect_urlopen,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Iterator[RawPage]:
    if not key:
        raise Hist8Error("Massive credential missing")
    endpoint = MASSIVE_URL
    params = dict(MASSIVE_FROZEN_PARAMS)
    seen: set[str] = set()
    for _ in range(100):
        page = _build_page(
            source="MASSIVE", feed="I:COMP", product="I:COMP minute index OHLC",
            instruments=("NASDAQ",), endpoint=endpoint, params=params,
            headers={"Authorization": f"Bearer {key}", "User-Agent": "ATOM-HIST8/1"},
            opener=opener, clock=clock,
        )
        yield page
        if page.http_status != 200:
            raise Hist8Error(f"Massive HTTP {page.http_status}")
        payload = page.payload()
        if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
            raise Hist8Error("malformed Massive page")
        if payload.get("ticker") != "I:COMP":
            raise Hist8Error("Massive ticker identity mismatch")
        if payload.get("adjusted") is not False:
            raise Hist8Error("Massive adjustment identity mismatch")
        next_url = payload.get("next_url")
        if next_url is None:
            return
        if not isinstance(next_url, str) or not next_url or next_url in seen:
            raise Hist8Error("invalid Massive pagination")
        seen.add(next_url)
        endpoint, params = _strip_secret_query(next_url)
    raise Hist8Error("Massive page bound exceeded")


def _artifact_id(body: bytes) -> str:
    return "sha256:" + sha256(body)


def _manifest_id(payload: Mapping[str, object]) -> str:
    return "sha256:" + sha256(payload)


def _membership_sequence(row: Bar) -> int:
    delta = row.bar_start_utc - START
    total_seconds = delta.days * 86400 + delta.seconds
    minute_offset, remainder = divmod(total_seconds, 60)
    if (delta.microseconds or remainder or minute_offset < 0
            or row.bar_start_utc >= END):
        raise Hist8Error("snapshot member timestamp outside frozen minute grid")
    # Each timeframe receives two million slots (the window has 1,051,200
    # minutes); each instrument receives ten million slots.
    return (
        INSTRUMENTS.index(row.instrument) * 10_000_000
        + TIMEFRAMES.index(row.timeframe) * 2_000_000
        + minute_offset
    )


def _validate_database_url(
    dsn: str, *, expected_user: str, purpose: str,
) -> str:
    try:
        parsed = urlparse(dsn)
        port = parsed.port
    except ValueError as exc:
        raise Hist8Error(
            f"HIST8 {purpose} credential/project mismatch"
        ) from exc
    required_query = [
        ("sslmode", "verify-full"), ("sslrootcert", "system"),
    ]
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if (parsed.scheme not in ("postgres", "postgresql")
            or parsed.hostname != DATABASE_HOST
            or port not in (None, 5432)
            or parsed.username != expected_user
            or not parsed.password
            or parsed.path != f"/{DATABASE_NAME}"
            or parsed.fragment
            or sorted(query_pairs) != sorted(required_query)):
        raise Hist8Error(f"HIST8 {purpose} credential/project mismatch")
    return dsn


def install_schema(
    dsn: str | None = None, *, connector: Callable[..., object] | None = None,
    schema_path: Path | None = None,
) -> dict[str, object]:
    """Install only through the frozen direct endpoint with verified TLS."""
    chosen_dsn = _validate_database_url(
        dsn if dsn is not None else os.environ.get(INSTALL_DATABASE_ENV, ""),
        expected_user=INSTALLER_ROLE,
        purpose="installer",
    )
    if connector is None:
        try:
            import psycopg
        except ImportError as exc:
            raise Hist8Error("psycopg is required") from exc
        connector = psycopg.connect
    target = schema_path or Path(__file__).with_name("schema.sql")
    sql = target.read_text(encoding="utf-8")
    if (not sql.lstrip().startswith("-- ATOM-HIST8-CORPUS-AMENDMENT-1")
            or not sql.rstrip().endswith("COMMIT;")):
        raise Hist8Error("HIST8 schema artifact mismatch")
    with connector(
        chosen_dsn, autocommit=True, connect_timeout=15,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select current_user,current_database(),coalesce(
                       (select ssl from pg_stat_ssl where pid=pg_backend_pid()),
                       false
                   )"""
            )
            user, database, tls_active = cursor.fetchone()
            if (user != INSTALLER_ROLE or database != DATABASE_NAME
                    or tls_active is not True):
                raise Hist8Error("HIST8 installer endpoint identity mismatch")
            cursor.execute(
                "select set_config('atom.hist8_verified_project_ref', %s, false)",
                (PROJECT_REF,),
            )
            cursor.execute(sql)
            cursor.execute(
                """select to_regnamespace('atom_research_history') is not null,
                          exists (
                            select 1 from pg_roles
                            where rolname='atom_hist8_importer'
                          ),
                          (select count(*) from information_schema.tables
                           where table_schema='atom_research_history')"""
            )
            schema_exists, role_exists, table_count = cursor.fetchone()
    if schema_exists is not True or role_exists is not True or table_count != 3:
        raise Hist8Error("HIST8 schema installation readback mismatch")
    return {
        "project_ref": PROJECT_REF,
        "database": DATABASE_NAME,
        "host": DATABASE_HOST,
        "schema": "atom_research_history",
        "tables": table_count,
    }


class Hist8Store:
    def __init__(self, connection_factory: Callable[[], object]) -> None:
        self._connection_factory = connection_factory

    @classmethod
    def from_environment(cls) -> "Hist8Store":
        dsn = _validate_database_url(
            os.environ.get(IMPORT_DATABASE_ENV, ""),
            expected_user=IMPORTER_ROLE,
            purpose="importer",
        )
        try:
            import psycopg
        except ImportError as exc:
            raise Hist8Error("psycopg is required") from exc
        return cls(lambda: psycopg.connect(dsn, connect_timeout=15))

    @staticmethod
    def _verify(connection: object) -> None:
        with connection.cursor() as cursor:
            cursor.execute("select current_user, current_database()")
            user, database = cursor.fetchone()
        if user != IMPORTER_ROLE or database != DATABASE_NAME:
            raise Hist8Error("HIST8 database identity mismatch")

    def add_attempt(self, import_id: str, kind: str, metadata: Mapping[str, object]) -> None:
        payload = {"corpus_id": CORPUS_ID, "import_id": import_id,
                   "kind": kind, "sequence_no": 0, "metadata": metadata}
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into atom_research_history.manifests
                    (manifest_id, corpus_id, manifest_kind, import_id, sequence_no,
                     metadata_json) values (%s,%s,%s,%s,0,%s)
                    on conflict (manifest_id) do nothing""",
                    (_manifest_id(payload), CORPUS_ID, kind, import_id,
                     json.dumps(_canonical(metadata))),
                )

    def store_page(self, import_id: str, sequence: int, page: RawPage) -> int:
        artifact_id = _artifact_id(page.body)
        manifest_ids: list[str] = []
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into atom_research_history.raw_responses
                    (artifact_id, body, byte_length) values (%s,%s,%s)
                    on conflict (artifact_id) do nothing""",
                    (artifact_id, page.body, len(page.body)),
                )
                cursor.execute(
                    "select body, byte_length from atom_research_history.raw_responses where artifact_id=%s",
                    (artifact_id,),
                )
                stored_body, stored_length = cursor.fetchone()
                readback = bytes(stored_body)
                if (readback != page.body or stored_length != len(page.body)
                        or _artifact_id(readback) != artifact_id):
                    raise Hist8ConflictError("raw artifact identity conflict")
                for offset, instrument in enumerate(page.instruments):
                    number = sequence + offset
                    payload = {
                        "corpus_id": CORPUS_ID, "import_id": import_id,
                        "sequence_no": number, "source": page.source,
                        "feed": page.feed, "product": page.product,
                        "instrument": instrument, "endpoint": page.endpoint,
                        "request_params": dict(page.request_params),
                        "retrieved_at": page.retrieved_at,
                        "http_status": page.http_status,
                        "content_type": page.content_type,
                        "content_encoding": page.content_encoding,
                        "artifact_id": artifact_id, "byte_length": len(page.body),
                    }
                    manifest_id = _manifest_id(payload)
                    manifest_ids.append(manifest_id)
                    cursor.execute(
                        """insert into atom_research_history.manifests
                        (manifest_id, corpus_id, manifest_kind, import_id, sequence_no,
                         source, feed, product, instrument, endpoint, request_params,
                         retrieved_at, http_status, content_type, content_encoding,
                         artifact_id, artifact_byte_length, metadata_json)
                        values (%s,%s,'RETRIEVAL',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb)
                        on conflict (manifest_id) do nothing""",
                        (manifest_id, CORPUS_ID, import_id, number,
                         page.source, page.feed, page.product, instrument,
                         page.endpoint, json.dumps(dict(page.request_params)),
                        page.retrieved_at, page.http_status, page.content_type,
                        page.content_encoding, artifact_id, len(page.body)),
                    )
            # End the atomic byte/provenance transaction before attesting it.
            connection.commit()
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "select body,byte_length from atom_research_history.raw_responses "
                    "where artifact_id=%s", (artifact_id,),
                )
                committed = cursor.fetchone()
                if committed is None:
                    raise Hist8ConflictError("raw artifact missing after commit")
                committed_body, committed_length = committed
                durable = bytes(committed_body)
                if (durable != page.body or committed_length != len(page.body)
                        or _artifact_id(durable) != artifact_id):
                    raise Hist8ConflictError("raw artifact post-commit mismatch")
                cursor.execute(
                    """select manifest_id,artifact_id,artifact_byte_length
                       from atom_research_history.manifests
                       where manifest_id = any(%s)""", (manifest_ids,),
                )
                durable_manifests = {
                    row[0]: (row[1], row[2]) for row in cursor.fetchall()
                }
                if durable_manifests != {
                    manifest_id: (artifact_id, len(page.body))
                    for manifest_id in manifest_ids
                }:
                    raise Hist8ConflictError("retrieval provenance post-commit mismatch")
        return sequence + len(page.instruments)

    def retrieval_pages(self, import_id: str, instrument: str) -> Iterator[RawPage]:
        connection = self._connection_factory()
        self._verify(connection)
        try:
            with connection.cursor(name="hist8_raw_replay") as cursor:
                cursor.execute(
                    """select m.source,m.feed,m.product,m.instrument,m.endpoint,
                    m.request_params,m.retrieved_at,m.http_status,m.content_type,
                    m.content_encoding,r.body
                    from atom_research_history.manifests m
                    join atom_research_history.raw_responses r using (artifact_id)
                    where m.corpus_id=%s and m.import_id=%s
                      and m.manifest_kind='RETRIEVAL' and m.instrument=%s
                    order by m.sequence_no""", (CORPUS_ID, import_id, instrument),
                )
                for row in cursor:
                    yield RawPage(
                        row[0], row[1], row[2], (row[3],), row[4], row[5], row[6],
                        row[7], row[8], row[9], bytes(row[10]),
                    )
        finally:
            connection.close()

    def sealed_snapshot_digest(self, import_id: str) -> str:
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select metadata_json->>'membership_sha256'
                       from atom_research_history.manifests
                       where corpus_id=%s and import_id=%s
                         and manifest_kind='SNAPSHOT'""",
                    (CORPUS_ID, import_id),
                )
                rows = cursor.fetchall()
        if (len(rows) != 1 or not isinstance(rows[0][0], str)
                or len(rows[0][0]) != 64
                or any(character not in "0123456789abcdef" for character in rows[0][0])):
            raise Hist8Error("sealed source snapshot missing or invalid")
        return rows[0][0]

    def _record_bar_conflict(
        self, row: Bar, existing_bar_id: str, existing_content_hash: str,
        existing_import_id: str,
    ) -> None:
        sequence = _membership_sequence(row)
        metadata = _canonical({
            "conflict_kind": "SAME_CANONICAL_KEY",
            "canonical_key": {
                "corpus_id": row.corpus_id,
                "instrument": row.instrument,
                "timeframe": row.timeframe,
                "bar_start_utc": row.bar_start_utc,
            },
            "existing": {
                "bar_id": existing_bar_id,
                "content_hash": existing_content_hash,
                "originating_import_id": existing_import_id,
            },
            "candidate": {
                "bar_id": row.bar_id,
                "content_hash": row.content_hash,
                "attempt_import_id": row.import_id,
                "source_artifact_id": row.source_artifact_id,
                "source_record_locator": row.source_record_locator,
                "semantic_payload": _content_payload(row),
            },
        })
        payload = {
            "corpus_id": CORPUS_ID, "import_id": row.import_id,
            "kind": "BAR_CONFLICT", "sequence_no": sequence,
            "instrument": row.instrument, "metadata": metadata,
        }
        manifest_id = _manifest_id(payload)
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into atom_research_history.manifests
                       (manifest_id,corpus_id,manifest_kind,import_id,sequence_no,
                        instrument,metadata_json)
                       values (%s,%s,'BAR_CONFLICT',%s,%s,%s,%s)
                       on conflict do nothing""",
                    (manifest_id, CORPUS_ID, row.import_id, sequence,
                     row.instrument, json.dumps(metadata)),
                )
            connection.commit()
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select manifest_id,metadata_json
                       from atom_research_history.manifests
                       where corpus_id=%s and import_id=%s
                         and manifest_kind='BAR_CONFLICT' and sequence_no=%s""",
                    (CORPUS_ID, row.import_id, sequence),
                )
                recorded = cursor.fetchone()
        if (recorded is None or recorded[0] != manifest_id
                or _canonical(recorded[1]) != metadata):
            raise Hist8ConflictError("bar conflict evidence mismatch")

    def insert_bars(self, rows: Sequence[Bar]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        keys = [(row.corpus_id, row.instrument, row.timeframe, row.bar_start_utc)
                for row in rows]
        if len(keys) != len(set(keys)):
            raise Hist8ConflictError("duplicate generated bar identity")
        inserted = 0
        conflict: tuple[Bar, str, str, str] | None = None
        try:
            with self._connection_factory() as connection:
                self._verify(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select timeframe,bar_start_utc,bar_id,content_hash,import_id
                           from atom_research_history.bars
                           where corpus_id=%s and instrument=%s and session_date=%s""",
                        (CORPUS_ID, rows[0].instrument, rows[0].session_date),
                    )
                    existing = {
                        (record[0], record[1]): (record[2], record[3], record[4])
                        for record in cursor.fetchall()
                    }
                    pending = []
                    for row in rows:
                        key = (row.timeframe, row.bar_start_utc)
                        if key in existing:
                            existing_bar_id, existing_hash, existing_import_id = (
                                existing[key]
                            )
                            if existing_hash != row.content_hash:
                                conflict = (
                                    row, existing_bar_id, existing_hash,
                                    existing_import_id,
                                )
                                raise Hist8ConflictError("same-key bar conflict")
                            continue
                        pending.append(row)
                    if pending:
                        cursor.executemany(
                            """insert into atom_research_history.bars
                            (bar_id,content_hash,corpus_id,instrument,timeframe,bar_start_utc,
                             bar_end_utc,session_date,calendar_id,calendar_sha256,open,high,
                             low,close,volume,trade_count,vwap,volume_unit,source,feed,product,
                             adjustment,currency,import_id,derivation_version,
                             source_artifact_id,source_record_locator,lineage_json)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            on conflict do nothing""",
                            [_bar_values(row) for row in pending],
                        )
                        inserted = len(pending)
                    cursor.execute(
                        """select timeframe,bar_start_utc,bar_id,content_hash,import_id
                           from atom_research_history.bars
                           where corpus_id=%s and instrument=%s and session_date=%s""",
                        (CORPUS_ID, rows[0].instrument, rows[0].session_date),
                    )
                    verified = {
                        (record[0], record[1]): (record[2], record[3], record[4])
                        for record in cursor.fetchall()
                    }
                    for row in rows:
                        actual = verified.get((row.timeframe, row.bar_start_utc))
                        if actual is None:
                            raise Hist8ConflictError("bar readback missing")
                        if actual[1] != row.content_hash:
                            conflict = (row, actual[0], actual[1], actual[2])
                            raise Hist8ConflictError("same-key bar conflict")

                    members = []
                    expected_members = {}
                    for row in rows:
                        sequence = _membership_sequence(row)
                        payload = {
                            "corpus_id": CORPUS_ID, "import_id": row.import_id,
                            "kind": "SNAPSHOT_MEMBER", "sequence_no": sequence,
                            "instrument": row.instrument, "timeframe": row.timeframe,
                            "bar_start_utc": row.bar_start_utc, "bar_id": row.bar_id,
                            "content_hash": row.content_hash,
                            "research_eligible": row.research_eligible,
                        }
                        expected_members[sequence] = (
                            row.bar_id, row.content_hash, row.research_eligible,
                        )
                        members.append((
                            _manifest_id(payload), CORPUS_ID, row.import_id, sequence,
                            row.instrument, row.bar_id, row.content_hash, row.timeframe,
                            row.bar_start_utc, row.research_eligible,
                        ))
                    cursor.executemany(
                        """insert into atom_research_history.manifests
                        (manifest_id,corpus_id,manifest_kind,import_id,sequence_no,
                         instrument,member_bar_id,member_content_hash,member_timeframe,
                         member_bar_start_utc,member_research_eligible,metadata_json)
                        values (%s,%s,'SNAPSHOT_MEMBER',%s,%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb)
                        on conflict (manifest_id) do nothing""", members,
                    )
                    cursor.execute(
                        """select sequence_no,member_bar_id,member_content_hash,
                                  member_research_eligible
                           from atom_research_history.manifests
                           where corpus_id=%s and import_id=%s
                             and manifest_kind='SNAPSHOT_MEMBER'
                             and sequence_no = any(%s)""",
                        (CORPUS_ID, rows[0].import_id, list(expected_members)),
                    )
                    actual_members = {
                        record[0]: (record[1], record[2], record[3])
                        for record in cursor.fetchall()
                    }
                    if actual_members != expected_members:
                        raise Hist8ConflictError(
                            "snapshot membership readback mismatch"
                        )
        except Hist8ConflictError:
            if conflict is not None:
                self._record_bar_conflict(*conflict)
            raise
        return inserted, len(rows) - inserted

    def seal_snapshot(self, import_id: str, metadata: Mapping[str, object]) -> str:
        digest = hashlib.sha256()
        counts: dict[str, int] = {}
        connection = self._connection_factory()
        self._verify(connection)
        try:
            with connection.cursor() as lock_cursor:
                lock_cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (import_id,),
                )
            with connection.cursor(name="hist8_snapshot") as cursor:
                cursor.execute(
                    """select m.instrument,m.member_timeframe,m.member_bar_id,
                              m.member_content_hash,m.member_research_eligible
                       from atom_research_history.manifests m
                       join atom_research_history.bars b
                         on b.bar_id=m.member_bar_id
                        and b.content_hash=m.member_content_hash
                       where m.corpus_id=%s and m.import_id=%s
                         and m.manifest_kind='SNAPSHOT_MEMBER'
                       order by m.sequence_no""", (CORPUS_ID, import_id),
                )
                for instrument, timeframe, bar_id, content_hash, eligible in cursor:
                    digest.update(canonical_bytes((instrument, timeframe, bar_id,
                                                   content_hash, eligible)))
                    key = f"{instrument}/{timeframe}"
                    counts[key] = counts.get(key, 0) + 1
            snapshot = {
                **dict(metadata), "membership_sha256": digest.hexdigest(),
                "row_counts": {key: counts.get(key, 0) for key in
                               (f"{i}/{t}" for i in INSTRUMENTS for t in TIMEFRAMES)},
            }
            payload = {"corpus_id": CORPUS_ID, "import_id": import_id,
                       "kind": "SNAPSHOT", "sequence_no": 0, "metadata": snapshot}
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into atom_research_history.manifests
                    (manifest_id,corpus_id,manifest_kind,import_id,sequence_no,metadata_json)
                    values (%s,%s,'SNAPSHOT',%s,0,%s) on conflict (manifest_id) do nothing""",
                    (_manifest_id(payload), CORPUS_ID, import_id,
                     json.dumps(_canonical(snapshot))),
                )
            connection.commit()
            return digest.hexdigest()
        finally:
            connection.close()


def _bar_values(row: Bar) -> tuple[object, ...]:
    values = asdict(row)
    return (
        values["bar_id"], values["content_hash"], values["corpus_id"],
        values["instrument"], values["timeframe"], values["bar_start_utc"],
        values["bar_end_utc"], values["session_date"], values["calendar_id"],
        values["calendar_sha256"], values["open"], values["high"], values["low"],
        values["close"], values["volume"], values["trade_count"], values["vwap"],
        values["volume_unit"], values["source"], values["feed"], values["product"],
        values["adjustment"], values["currency"], values["import_id"],
        values["derivation_version"], values["source_artifact_id"],
        values["source_record_locator"], json.dumps(list(row.lineage)),
    )


def _validate_source_bar(row: SourceBar) -> None:
    if (row.start.tzinfo is None or row.start.utcoffset() != timedelta(0)
            or row.start.second or row.start.microsecond):
        raise Hist8Error("bar timestamp is not UTC-minute aligned")
    if any(value is None or not value.is_finite() or value <= 0 for value in
           (row.open, row.high, row.low, row.close)):
        raise Hist8Error("invalid OHLC")
    if row.low > min(row.open, row.close) or max(row.open, row.close) > row.high:
        raise Hist8Error("invalid OHLC ordering")
    if row.volume is not None and (not row.volume.is_finite() or row.volume < 0):
        raise Hist8Error("invalid volume")
    if row.trade_count is not None and row.trade_count < 0:
        raise Hist8Error("invalid trade count")
    if row.vwap is not None and (not row.vwap.is_finite() or row.vwap <= 0):
        raise Hist8Error("invalid vwap")
    if row.instrument == "NASDAQ" and row.volume is not None:
        raise Hist8Error("NASDAQ volume must be null")
    if row.instrument != "NASDAQ" and row.volume is None:
        raise Hist8Error("volume is required")


def _source_bar_payload(row: SourceBar) -> tuple[object, ...]:
    """Compare provider semantics without storage-page lineage."""
    return (
        row.instrument, row.start, row.open, row.high, row.low, row.close,
        row.volume, row.trade_count, row.vwap, row.source, row.feed,
        row.product, row.adjustment, row.volume_unit,
    )


def parse_source_page(
    page: RawPage, instrument: str, *, rejection_counter: list[int] | None = None,
) -> tuple[SourceBar, ...]:
    artifact = _artifact_id(page.body)
    payload = page.payload()
    rows: list[SourceBar] = []
    if page.source == "ALPACA":
        source_rows = payload.get("bars", {}).get(instrument, [])
        for index, item in enumerate(source_rows):
            rows.append(SourceBar(
                instrument, _iso_utc(item["t"]), _decimal(item["o"]),
                _decimal(item["h"]), _decimal(item["l"]), _decimal(item["c"]),
                _decimal(item["v"]),
                None if item.get("n") is None else _integer(
                    item["n"], name="Alpaca trade count"
                ),
                _decimal(item.get("vw"), nullable=True), artifact,
                f"$.bars.{instrument}[{index}]", "ALPACA", "SIP",
                f"{instrument}:1Min", "raw", "SHARES",
            ))
    elif page.source == "COINBASE":
        for index, item in enumerate(payload):
            if not isinstance(item, list) or len(item) < 6:
                raise Hist8Error("malformed Coinbase candle")
            timestamp = _integer(item[0], name="Coinbase timestamp")
            start = datetime.fromtimestamp(timestamp, timezone.utc)
            rows.append(SourceBar(
                instrument, start, _decimal(item[3]), _decimal(item[2]),
                _decimal(item[1]), _decimal(item[4]), _decimal(item[5]), None,
                None, artifact, f"$[{index}]", "COINBASE", "EXCHANGE",
                "BTC-USD:60", "none", "BTC",
            ))
    elif page.source == "MASSIVE":
        if payload.get("ticker") != "I:COMP":
            raise Hist8Error("Massive ticker identity mismatch")
        for index, item in enumerate(payload.get("results", [])):
            milliseconds = _integer(item["t"], name="Massive timestamp")
            if milliseconds % 1000:
                raise Hist8Error("Massive timestamp is not second aligned")
            start = datetime.fromtimestamp(milliseconds // 1000, timezone.utc)
            rows.append(SourceBar(
                instrument, start, _decimal(item["o"]), _decimal(item["h"]),
                _decimal(item["l"]), _decimal(item["c"]), None, None, None,
                artifact, f"$.results[{index}]", "MASSIVE", "I:COMP",
                "I:COMP:minute", "none", "NOT_APPLICABLE",
            ))
    else:
        raise Hist8Error("unknown source")
    rows.sort(key=lambda row: row.start)
    valid: list[SourceBar] = []
    for row in rows:
        try:
            _validate_source_bar(row)
        except Hist8Error:
            if rejection_counter is None:
                raise
            rejection_counter[0] += 1
            continue
        valid.append(row)
    return tuple(valid)


def _session_definitions(calendar: Mapping[str, object], instrument: str) -> dict[str, tuple[datetime, datetime, int]]:
    if instrument == "BTC-USD":
        return {
            day: (
                datetime.fromisoformat(day).replace(tzinfo=timezone.utc),
                datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(days=1),
                1440,
            ) for day in calendar["btc_utc_dates"]
        }
    return {
        row["date"]: (_iso_utc(row["open_utc"]), _iso_utc(row["close_utc"]),
                      int(row["expected_minutes"]))
        for row in calendar["us_cash_sessions"]
    }


def _session_for(row: SourceBar, definitions: Mapping[str, tuple[datetime, datetime, int]]) -> str | None:
    key = row.start.date().isoformat()
    bounds = definitions.get(key)
    return key if bounds and bounds[0] <= row.start < bounds[1] else None


def _content_payload(row: Bar) -> dict[str, object]:
    payload = asdict(row)
    # Eligibility is snapshot state, while retrieval artifact/locator identify
    # the first immutable provenance row rather than provider semantics. Omitting
    # both lets a page reshuffle backfill reuse that original row and lineage.
    for key in (
        "bar_id", "content_hash", "import_id", "research_eligible",
        "source_artifact_id", "source_record_locator",
    ):
        payload.pop(key)
    payload["lineage"] = list(row.lineage)
    return payload


def _finish_bar(row: Bar) -> Bar:
    digest = sha256(_content_payload(row))
    return replace(row, content_hash=digest, bar_id="hist8bar:" + digest)


def canonical_bar(
    row: SourceBar, *, session_date: str, calendar_hash: str,
    import_id: str, eligible: bool, calendar_id: str | None = None,
) -> Bar:
    bar = Bar(
        "", "", CORPUS_ID, row.instrument, "1m", row.start,
        row.start + timedelta(minutes=1), session_date,
        calendar_id or ("BTC_UTC_DAY" if row.instrument == "BTC-USD" else "US_CASH_RTH"),
        calendar_hash, row.open, row.high, row.low, row.close, row.volume,
        row.trade_count, row.vwap, row.volume_unit, row.source, row.feed,
        row.product, row.adjustment, "USD", import_id, None, row.artifact_id,
        row.locator, (), eligible,
    )
    return _finish_bar(bar)


def derive_session(
    minutes: Sequence[Bar], timeframe: str, import_id: str, *, session_open: datetime,
) -> tuple[Bar, ...]:
    width = TIMEFRAME_MINUTES[timeframe]
    if not minutes or any(row.timeframe != "1m" or not row.research_eligible
                          for row in minutes):
        return ()
    if minutes[0].bar_start_utc != session_open:
        raise Hist8Error("derivation must anchor at session open")
    output: list[Bar] = []
    for offset in range(0, len(minutes) - width + 1, width):
        window = minutes[offset:offset + width]
        if len(window) != width or any(
            following.bar_start_utc - previous.bar_start_utc != timedelta(minutes=1)
            for previous, following in zip(window, window[1:])
        ):
            continue
        first, last = window[0], window[-1]
        volume = None if first.instrument == "NASDAQ" else _exact_decimal_sum(tuple(
            item.volume for item in window if item.volume is not None
        ))
        trade_count = None if any(item.trade_count is None for item in window) else sum(
            item.trade_count or 0 for item in window
        )
        bar = Bar(
            "", "", CORPUS_ID, first.instrument, timeframe,
            first.bar_start_utc, last.bar_end_utc, first.session_date,
            first.calendar_id, first.calendar_sha256, first.open,
            max(item.high for item in window), min(item.low for item in window),
            last.close, volume, trade_count, None, first.volume_unit,
            first.source, first.feed, first.product, first.adjustment, "USD",
            import_id, DERIVATION_VERSION, None, None,
            tuple(f"{item.bar_id}|{item.content_hash}" for item in window), True,
        )
        output.append(_finish_bar(bar))
    return tuple(output)


def materialize_instrument(
    store: Hist8Store, source_import_id: str, instrument: str,
    calendar: Mapping[str, object], *, attempt_id: str | None = None,
) -> dict[str, int]:
    write_attempt_id = attempt_id or source_import_id
    definitions = _session_definitions(calendar, instrument)
    rejected = duplicates = 0
    inserted = idempotent = eligible_sessions = incomplete_sessions = 0
    observed_minutes = missing_minutes = 0
    excluded_windows = {timeframe: 0 for timeframe in TIMEFRAMES[1:]}
    residual_tails = {timeframe: 0 for timeframe in TIMEFRAMES[1:]}
    seen_sessions: set[str] = set()
    calendar_hash = str(calendar["schedule_sha256"])
    calendar_id = str(calendar["instrument_calendars"][instrument])

    def flush_session(session_date: str, unique: Mapping[datetime, SourceBar]) -> None:
        nonlocal inserted, idempotent, eligible_sessions, incomplete_sessions
        nonlocal observed_minutes, missing_minutes
        opened, closed, expected = definitions[session_date]
        expected_times = {opened + timedelta(minutes=index) for index in range(expected)}
        complete = set(unique) == expected_times and closed == opened + timedelta(minutes=expected)
        seen_sessions.add(session_date)
        observed_minutes += len(unique)
        missing_minutes += len(expected_times - set(unique))
        if complete:
            eligible_sessions += 1
        else:
            incomplete_sessions += 1
            for timeframe, width in TIMEFRAME_MINUTES.items():
                excluded_windows[timeframe] += expected // width
        for timeframe, width in TIMEFRAME_MINUTES.items():
            residual_tails[timeframe] += expected % width
        canonical = tuple(canonical_bar(
            unique[start], session_date=session_date, calendar_hash=calendar_hash,
            import_id=write_attempt_id, eligible=complete, calendar_id=calendar_id,
        ) for start in sorted(unique))
        all_rows: list[Bar] = list(canonical)
        if complete:
            for timeframe in TIMEFRAMES[1:]:
                all_rows.extend(derive_session(
                    canonical, timeframe, write_attempt_id, session_open=opened,
                ))
        added, same = store.insert_bars(all_rows)
        inserted += added
        idempotent += same

    current_session: str | None = None
    current_rows: dict[datetime, SourceBar] = {}
    for page in store.retrieval_pages(source_import_id, instrument):
        if page.http_status != 200:
            raise Hist8Error(f"stored provider failure {page.http_status}")
        invalid = [0]
        parsed_rows = parse_source_page(page, instrument, rejection_counter=invalid)
        rejected += invalid[0]
        for row in parsed_rows:
            if not START <= row.start < END:
                rejected += 1
                continue
            session = _session_for(row, definitions)
            if session is None:
                rejected += 1
                continue
            if current_session is not None and session < current_session:
                raise Hist8ConflictError("provider bars are not session ordered")
            if current_session is not None and session != current_session:
                flush_session(current_session, current_rows)
                current_rows = {}
            current_session = session
            prior = current_rows.get(row.start)
            if prior is not None:
                if _source_bar_payload(prior) != _source_bar_payload(row):
                    raise Hist8ConflictError("conflicting duplicate provider bar")
                duplicates += 1
                continue
            current_rows[row.start] = row
    if current_session is not None:
        flush_session(current_session, current_rows)
    for session_date in set(definitions) - seen_sessions:
        expected = definitions[session_date][2]
        incomplete_sessions += 1
        missing_minutes += expected
        for timeframe, width in TIMEFRAME_MINUTES.items():
            excluded_windows[timeframe] += expected // width
            residual_tails[timeframe] += expected % width
    result = {
        "inserted": inserted, "idempotent": idempotent,
        "provider_duplicates": duplicates, "rejected": rejected,
        "expected_minutes": sum(row[2] for row in definitions.values()),
        "observed_minutes": observed_minutes, "missing_minutes": missing_minutes,
        "eligible_sessions": eligible_sessions,
        "incomplete_sessions": incomplete_sessions,
    }
    for timeframe in TIMEFRAMES[1:]:
        result[f"excluded_{timeframe}_windows"] = excluded_windows[timeframe]
        result[f"residual_{timeframe}_tail_minutes"] = residual_tails[timeframe]
    return result


def acquire(store: Hist8Store, import_id: str) -> int:
    sequence = 1
    sources = (
        alpaca_pages(os.environ.get("ALPACA_API_KEY", ""),
                     os.environ.get("ALPACA_API_SECRET", "")),
        coinbase_pages(),
        massive_pages(os.environ.get("MASSIVE_API_KEY", "")),
    )
    for pages in sources:
        for page in pages:
            sequence = store.store_page(import_id, sequence, page)
    return sequence - 1


def execute(import_id: str | None = None, *, acquire_sources: bool = True) -> dict[str, object]:
    chosen = import_id or f"hist8-{uuid.uuid4()}"
    if len(chosen) > 128:
        raise Hist8Error("import id too long")
    calendar = load_calendar()
    store = Hist8Store.from_environment()
    kind = "IMPORT_ATTEMPT" if acquire_sources else "REPLAY_ATTEMPT"
    source_membership = (
        None if acquire_sources else store.sealed_snapshot_digest(chosen)
    )
    attempt_id = chosen if acquire_sources else f"hist8-replay-{uuid.uuid4()}"
    store.add_attempt(attempt_id, kind, {
        "authorization": "ATOM-HIST8-CORPUS-AMENDMENT-1",
        "source_import_id": chosen,
        "project_ref": PROJECT_REF, "database": DATABASE_NAME,
        "schema": "atom_research_history", "calendar_sha256": calendar["schedule_sha256"],
        "partitions": PARTITIONS,
        "expected_membership_sha256": source_membership,
    })
    retrieval_associations = acquire(store, chosen) if acquire_sources else 0
    results = {instrument: materialize_instrument(
        store, chosen, instrument, calendar, attempt_id=attempt_id,
    )
               for instrument in INSTRUMENTS}
    membership = store.seal_snapshot(attempt_id, {
        "attempt_kind": kind, "retrieval_associations": retrieval_associations,
        "source_import_id": chosen,
        "instrument_results": results,
    })
    if source_membership is not None and membership != source_membership:
        raise Hist8ConflictError(
            "replay membership differs from sealed source snapshot"
        )
    return {"source_import_id": chosen, "attempt_id": attempt_id,
            "membership_sha256": membership,
            "instrument_results": results}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "run", "replay"))
    parser.add_argument("--import-id")
    args = parser.parse_args(argv)
    if args.command == "replay" and not args.import_id:
        parser.error("replay requires --import-id")
    if args.command == "install":
        if args.import_id:
            parser.error("install does not accept --import-id")
        result = install_schema()
    else:
        result = execute(args.import_id, acquire_sources=args.command == "run")
    print(json.dumps(_canonical(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALPACA_URL", "CALENDAR_VERSION", "CORPUS_ID", "DATABASE_HOST",
    "DATABASE_NAME", "DERIVATION_VERSION", "END", "EQUITIES", "Hist8Error",
    "Hist8ConflictError", "Hist8Store", "IMPORTER_ROLE", "INSTALL_DATABASE_ENV",
    "INSTRUMENTS", "MASSIVE_URL", "PARTITIONS", "PROJECT_REF", "RawPage",
    "START", "SourceBar", "TIMEFRAMES",
    "alpaca_pages", "canonical_bar", "canonical_bytes", "coinbase_pages",
    "derive_session", "execute", "install_schema", "load_calendar", "massive_pages",
    "materialize_instrument", "parse_source_page", "sha256",
]
