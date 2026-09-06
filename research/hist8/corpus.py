"""Bounded offline HIST8 acquisition, validation, derivation, and persistence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
from http.client import HTTPException, IncompleteRead
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Iterator, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import parse_qsl, unquote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zlib


CORPUS_ID = "HIST8_20240901_20260901_V1"
DERIVATION_VERSION = "HIST8_DERIVE_1"
CALENDAR_VERSION = "HIST8_CALENDAR_1"
CALENDAR_SCHEDULE_SHA256 = (
    "74463f0a85b14361599d9abf0caa0f3cbce12c79e10a15c37ffcd58348f3d446"
)
START = datetime(2024, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 1, tzinfo=timezone.utc)
PROJECT_REF = "pjbjpgnmniwcajqkuhge"
DATABASE_NAME = "postgres"
DATABASE_HOST = "db.pjbjpgnmniwcajqkuhge.supabase.co"
IMPORTER_ROLE = "atom_hist8_importer"
IMPORT_DATABASE_ENV = "ATOM_HIST8_IMPORT_DATABASE_URL"
INSTALLER_ROLE = "postgres"
EQUITIES = ("COIN", "QQQ", "SPY", "NVDA", "XLE", "GLD")
INSTRUMENTS = (*EQUITIES, "BTC-USD", "NASDAQ")
SOURCE_INSTRUMENTS = (
    ("ALPACA", EQUITIES),
    ("COINBASE", ("BTC-USD",)),
    ("MASSIVE", ("NASDAQ",)),
)
INSTRUMENT_SOURCE = {
    instrument: source
    for source, instruments in SOURCE_INSTRUMENTS
    for instrument in instruments
}
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
MASSIVE_FROZEN_PARAMS = {"sort": "asc", "limit": "50000"}
ALPACA_FROZEN_PARAMS = {
    "symbols": ",".join(EQUITIES), "timeframe": "1Min",
    "start": "2024-09-01T00:00:00Z", "end": "2026-09-01T00:00:00Z",
    "limit": "10000", "adjustment": "raw", "feed": "sip",
    "sort": "asc", "asof": "2026-09-01", "currency": "USD",
}
COINBASE_WINDOW_MINUTES = 300
REPLAY_PAGE_BATCH_SIZE = 8
SNAPSHOT_SCAN_BATCH_SIZE = 10_000
SNAPSHOT_SESSION_BATCH_SIZE = 32
POSTGRES_BIGINT_MAX = (1 << 63) - 1
# PostgreSQL's documented implementation limits for unconstrained numeric.
POSTGRES_NUMERIC_MAX_INTEGER_DIGITS = 131_072
POSTGRES_NUMERIC_MAX_FRACTIONAL_DIGITS = 16_383
PROVIDER_RAW_BODY_MAX_BYTES = 16 * 1024 * 1024
PROVIDER_DECODED_BODY_MAX_BYTES = 64 * 1024 * 1024
PROVIDER_READ_CHUNK_BYTES = 64 * 1024
IMPORTER_CONNECT_TIMEOUT_SECONDS = 15
IMPORTER_SESSION_OPTIONS = (
    "-c statement_timeout=60000 "
    "-c lock_timeout=5000 "
    "-c idle_in_transaction_session_timeout=60000 "
    "-c timezone=UTC"
)
EXECUTION_CODE_PATHS = (
    "research/hist8/corpus.py",
    "research/hist8/schema.sql",
    "research/hist8/calendar_manifest.json",
    "tests/test_hist8_corpus.py",
)

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
        return _decode_provider_body(self.body, self.content_encoding)

    def payload(self) -> object:
        try:
            return json.loads(
                self.decoded_body().decode("utf-8"), parse_float=Decimal,
            )
        except (
            UnicodeDecodeError, ValueError, RecursionError, InvalidOperation,
            EOFError, OSError, zlib.error,
        ) as exc:
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
    price_unit: str
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
        if value.is_zero():
            return "0"
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


def _git_output(
    arguments: Sequence[str], *, directory: Path, input_bytes: bytes | None = None,
) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *arguments], input=input_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Hist8Error("execution code identity is unavailable") from exc
    if result.returncode != 0:
        raise Hist8Error("execution code identity is unavailable")
    return result.stdout.strip()


def _execution_code_identity() -> dict[str, object]:
    module_directory = Path(__file__).resolve().parent
    root_raw = _git_output(
        ("rev-parse", "--show-toplevel"), directory=module_directory,
    )
    try:
        repository_root = Path(root_raw.decode("utf-8")).resolve(strict=True)
    except (UnicodeDecodeError, OSError) as exc:
        raise Hist8Error("execution code identity is unavailable") from exc
    commit_raw = _git_output(
        ("rev-parse", "--verify", "HEAD^{commit}"),
        directory=repository_root,
    )
    try:
        commit = commit_raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise Hist8Error("execution code identity is unavailable") from exc
    if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
        raise Hist8Error("execution code identity is unavailable")
    files: dict[str, dict[str, object]] = {}
    for relative in EXECUTION_CODE_PATHS:
        target = (repository_root / relative).resolve(strict=True)
        if target.parent != (repository_root / relative).parent.resolve():
            raise Hist8Error("execution code path escapes repository")
        body = target.read_bytes()
        blob_raw = _git_output(
            ("hash-object", "--stdin"), directory=repository_root,
            input_bytes=body,
        )
        tree_raw = _git_output(
            ("ls-tree", "--full-tree", commit, "--", relative),
            directory=repository_root,
        )
        try:
            blob = blob_raw.decode("ascii")
            tree_entry = tree_raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Hist8Error("execution code identity is unavailable") from exc
        fields = tree_entry.split("\t", 1)
        header = fields[0].split()
        if (len(fields) != 2 or fields[1] != relative or len(header) != 3
                or header[0] != "100644" or header[1] != "blob"
                or header[2] != blob):
            raise Hist8Error("executed code differs from implementation commit")
        files[relative] = {
            "git_blob": blob,
            "sha256": hashlib.sha256(body).hexdigest(),
            "byte_length": len(body),
        }
    return {
        "identity_version": "HIST8_CODE_IDENTITY_1",
        "implementation_commit": commit,
        "files": files,
    }


def _require_reviewed_implementation(
    code_identity: Mapping[str, object], expected_commit: str,
) -> None:
    if (not isinstance(expected_commit, str)
            or re.fullmatch(r"[0-9a-f]{40,64}", expected_commit) is None
            or code_identity.get("implementation_commit") != expected_commit):
        raise Hist8Error("reviewed implementation commit mismatch")


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


def load_calendar(
    path: Path | None = None, *, expected_file_sha256: str | None = None,
) -> dict[str, object]:
    target = path or Path(__file__).resolve().with_name("calendar_manifest.json")
    try:
        body = target.read_bytes()
        data = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise Hist8Error("calendar artifact is unreadable") from exc
    if (expected_file_sha256 is not None
            and (re.fullmatch(r"[0-9a-f]{64}", expected_file_sha256) is None
                 or hashlib.sha256(body).hexdigest() != expected_file_sha256)):
        raise Hist8Error("calendar artifact identity mismatch")
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
    # Bind the complete reviewed calendar artifact: schedule rows, exception
    # annotations, source references, and calendar/timezone versions.
    payload = {
        key: data[key] for key in data if key != "schedule_sha256"
    }
    if (data.get("schedule_sha256") != CALENDAR_SCHEDULE_SHA256
            or sha256(payload) != CALENDAR_SCHEDULE_SHA256):
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


def _postgres_numeric_fits(value: object) -> bool:
    """Return whether an exact Decimal fits unconstrained PostgreSQL numeric."""
    if not isinstance(value, Decimal) or not value.is_finite():
        return False
    _sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        return False
    integer_digits = max(len(digits) + exponent, 0)
    fractional_digits = max(-exponent, 0)
    return (
        integer_digits <= POSTGRES_NUMERIC_MAX_INTEGER_DIGITS
        and fractional_digits <= POSTGRES_NUMERIC_MAX_FRACTIONAL_DIGITS
    )


def _postgres_numeric_fields_fit(row: SourceBar | Bar) -> bool:
    return all(
        value is None or _postgres_numeric_fits(value)
        for value in (
            row.open, row.high, row.low, row.close, row.volume, row.vwap,
        )
    )


def _read_bounded_provider_body(stream: object) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        # Read one byte beyond the limit so an exact-limit body is accepted
        # only after the stream proves that it has ended.
        size = min(PROVIDER_READ_CHUNK_BYTES, PROVIDER_RAW_BODY_MAX_BYTES - total + 1)
        chunk = stream.read(size)
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise Hist8Error("provider response body is not bytes")
        if not chunk:
            return b"".join(chunks)
        data = bytes(chunk)
        total += len(data)
        if total > PROVIDER_RAW_BODY_MAX_BYTES:
            raise Hist8Error("provider response body exceeds raw byte limit")
        chunks.append(data)


def _decompress_provider_body(body: bytes, *, wbits: int) -> bytes:
    decompressor = zlib.decompressobj(wbits)
    decoded = decompressor.decompress(
        body, PROVIDER_DECODED_BODY_MAX_BYTES + 1,
    )
    if (len(decoded) > PROVIDER_DECODED_BODY_MAX_BYTES
            or decompressor.unconsumed_tail):
        raise Hist8Error("provider decoded body exceeds byte limit")
    decoded += decompressor.flush(
        PROVIDER_DECODED_BODY_MAX_BYTES - len(decoded) + 1,
    )
    if len(decoded) > PROVIDER_DECODED_BODY_MAX_BYTES:
        raise Hist8Error("provider decoded body exceeds byte limit")
    if not decompressor.eof or decompressor.unused_data:
        raise zlib.error("incomplete or trailing compressed provider body")
    return decoded


def _decode_provider_body(body: bytes, content_encoding: str | None) -> bytes:
    if len(body) > PROVIDER_RAW_BODY_MAX_BYTES:
        raise Hist8Error("provider response body exceeds raw byte limit")
    encoding = (content_encoding or "").lower().strip()
    if not encoding or encoding == "identity":
        return body
    if encoding == "gzip":
        return _decompress_provider_body(
            body, wbits=16 + zlib.MAX_WBITS,
        )
    if encoding == "deflate":
        return _decompress_provider_body(body, wbits=zlib.MAX_WBITS)
    raise Hist8Error(f"unsupported content encoding: {encoding}")


def _validate_downloaded_provider_body(
    body: bytes, headers: Mapping[str, str],
) -> None:
    try:
        _decode_provider_body(body, headers.get("content-encoding"))
    except (EOFError, OSError, zlib.error) as exc:
        raise Hist8Error("provider response is not valid decimal JSON") from exc


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
            headers = {
                str(name).lower(): str(value)
                for name, value in response.headers.items()
            }
            try:
                body = _read_bounded_provider_body(response)
            except IncompleteRead as exc:
                raise Hist8Error("provider response body incomplete") from exc
            _validate_downloaded_provider_body(body, headers)
            return int(response.status), headers, body
    except HTTPError as exc:
        with exc:
            headers = {
                str(name).lower(): str(value)
                for name, value in exc.headers.items()
            }
            try:
                body = _read_bounded_provider_body(exc)
            except IncompleteRead as incomplete:
                raise Hist8Error(
                    "provider response body incomplete"
                ) from incomplete
            _validate_downloaded_provider_body(body, headers)
            return int(exc.code), headers, body
    except HTTPException as exc:
        raise Hist8Error("provider HTTP protocol failure") from exc


def _build_page(
    *, source: str, feed: str, product: str, instruments: Sequence[str],
    endpoint: str, params: Mapping[str, str], headers: Mapping[str, str],
    opener: Callable[..., object], clock: Callable[[], datetime],
) -> RawPage:
    try:
        query = urlencode(params)
    except (TypeError, ValueError) as exc:
        raise Hist8Error("provider request parameter encoding failure") from exc
    url = endpoint + ("?" if "?" not in endpoint else "&") + query
    status, response_headers, body = _http_get(url, headers=headers, opener=opener)
    return RawPage(
        source, feed, product, tuple(instruments), endpoint, dict(params), clock(),
        status, response_headers.get("content-type"),
        response_headers.get("content-encoding"), body,
    )


def _validate_provider_page_envelope(page: RawPage) -> object:
    payload = page.payload()
    if page.source == "ALPACA":
        if not isinstance(payload, dict):
            raise Hist8Error("malformed Alpaca page")
        bars = payload.get("bars")
        if (not isinstance(bars, dict)
                or not set(bars).issubset(EQUITIES)
                or any(not isinstance(rows, list) for rows in bars.values())):
            raise Hist8Error("malformed Alpaca page")
        return payload
    if page.source == "COINBASE":
        if not isinstance(payload, list):
            raise Hist8Error("malformed Coinbase page")
        return payload
    if page.source == "MASSIVE":
        if (not isinstance(payload, dict)
                or not isinstance(payload.get("results", []), list)):
            raise Hist8Error("malformed Massive page")
        if payload.get("ticker") != "I:COMP":
            raise Hist8Error("Massive ticker identity mismatch")
        if payload.get("status") != "OK":
            raise Hist8Error("Massive response status mismatch")
        return payload
    raise Hist8Error("unknown source")


def alpaca_pages(
    key: str, secret: str, *, opener: Callable[..., object] = _no_redirect_urlopen,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Iterator[RawPage]:
    if not key or not secret:
        raise Hist8Error("Alpaca credentials missing")
    token: str | None = None
    seen: set[str] = set()
    for _ in range(1000):
        params = dict(ALPACA_FROZEN_PARAMS)
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
        payload = _validate_provider_page_envelope(page)
        assert isinstance(payload, dict)
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
        stop = min(cursor + timedelta(minutes=COINBASE_WINDOW_MINUTES), END)
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
        if page.http_status != 200:
            raise Hist8Error(f"Coinbase HTTP/payload failure {page.http_status}")
        _validate_provider_page_envelope(page)
        cursor = stop
    raise Hist8Error("Coinbase request bound exceeded")


def _strip_secret_query(url: str) -> tuple[str, dict[str, str]]:
    try:
        if not isinstance(url, str) or not url:
            raise ValueError("pagination URL is empty")
        parsed = urlparse(url)
        scheme = parsed.scheme
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
        fragment = parsed.fragment
        decoded_path = unquote(parsed.path, errors="strict")
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise Hist8Error("Massive pagination resource mismatch") from exc
    if (scheme != "https" or hostname != "api.massive.com"
            or port is not None or username is not None
            or password is not None or fragment):
        raise Hist8Error("Massive pagination resource mismatch")
    segments = decoded_path.strip("/").split("/")
    expected_prefix = [
        "v2", "aggs", "ticker", "I:COMP", "range", "1", "minute",
    ]
    if len(segments) != 9 or segments[:7] != expected_prefix:
        raise Hist8Error("Massive pagination resource mismatch")
    start_token, end_token = segments[7:]
    frozen_start_ms = int(START.timestamp() * 1000)
    frozen_end_ms = int(END.timestamp() * 1000)
    if start_token == "2024-09-01":
        page_start_ms = frozen_start_ms
        canonical_start_token = start_token
    elif (start_token.isascii() and start_token.isdigit()
          and len(start_token) <= len(str(frozen_end_ms))):
        try:
            page_start_ms = int(start_token)
        except ValueError as exc:
            raise Hist8Error("Massive pagination resource mismatch") from exc
        canonical_start_token = str(page_start_ms)
    else:
        raise Hist8Error("Massive pagination resource mismatch")
    if (not frozen_start_ms <= page_start_ms < frozen_end_ms
            or end_token not in {"2026-09-01", str(frozen_end_ms)}):
        raise Hist8Error("Massive pagination resource mismatch")
    try:
        query_pairs = parse_qsl(
            parsed.query, keep_blank_values=True, errors="strict",
            max_num_fields=8,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise Hist8Error("Massive pagination parameter mismatch") from exc
    supplied: dict[str, str] = {}
    for key, value in query_pairs:
        normalized_key = key.lower()
        if normalized_key not in {
            "sort", "limit", "cursor", "apikey",
        } or normalized_key in supplied:
            raise Hist8Error("Massive pagination parameter mismatch")
        supplied[normalized_key] = value
    for name, frozen_value in MASSIVE_FROZEN_PARAMS.items():
        if name in supplied and supplied[name] != frozen_value:
            raise Hist8Error("Massive pagination parameter mismatch")
    cursor = supplied.get("cursor")
    if not cursor:
        raise Hist8Error("Massive pagination parameter mismatch")
    try:
        cursor.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise Hist8Error("Massive pagination parameter mismatch") from exc
    # Provider next_url examples contain only a cursor. Rebuild every request
    # from the frozen semantic parameters and canonical path encoding, and
    # never retain a URL API key or provider-controlled encoding variant.
    canonical_end_token = (
        "2026-09-01" if end_token == "2026-09-01" else str(frozen_end_ms)
    )
    endpoint = (
        "https://api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
        f"{canonical_start_token}/{canonical_end_token}"
    )
    return endpoint, {**MASSIVE_FROZEN_PARAMS, "cursor": cursor}


def massive_pages(
    key: str, *, opener: Callable[..., object] = _no_redirect_urlopen,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Iterator[RawPage]:
    if not key:
        raise Hist8Error("Massive credential missing")
    endpoint = MASSIVE_URL
    params = dict(MASSIVE_FROZEN_PARAMS)
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for _ in range(100):
        request_identity = (endpoint, tuple(sorted(params.items())))
        if request_identity in seen:
            raise Hist8Error("invalid Massive pagination")
        seen.add(request_identity)
        page = _build_page(
            source="MASSIVE", feed="I:COMP", product="I:COMP minute index OHLC",
            instruments=("NASDAQ",), endpoint=endpoint, params=params,
            headers={"Authorization": f"Bearer {key}", "User-Agent": "ATOM-HIST8/1"},
            opener=opener, clock=clock,
        )
        yield page
        if page.http_status != 200:
            raise Hist8Error(f"Massive HTTP {page.http_status}")
        payload = _validate_provider_page_envelope(page)
        assert isinstance(payload, dict)
        next_url = payload.get("next_url")
        if next_url is None:
            return
        if not isinstance(next_url, str) or not next_url:
            raise Hist8Error("invalid Massive pagination")
        endpoint, params = _strip_secret_query(next_url)
    raise Hist8Error("Massive page bound exceeded")


def _artifact_id(body: bytes) -> str:
    return "sha256:" + sha256(body)


def _manifest_id(payload: Mapping[str, object]) -> str:
    return "sha256:" + sha256(payload)


def _retrieval_manifest_payload(
    import_id: str, sequence_no: int, page: RawPage, instrument: str,
) -> dict[str, object]:
    return {
        "corpus_id": CORPUS_ID,
        "import_id": import_id,
        "sequence_no": sequence_no,
        "source": page.source,
        "feed": page.feed,
        "product": page.product,
        "instrument": instrument,
        "endpoint": page.endpoint,
        "request_params": dict(page.request_params),
        "retrieved_at": page.retrieved_at,
        "http_status": page.http_status,
        "content_type": page.content_type,
        "content_encoding": page.content_encoding,
        "artifact_id": _artifact_id(page.body),
        "byte_length": len(page.body),
    }


def _validate_page_identity(page: RawPage, instrument: str) -> None:
    if (instrument not in INSTRUMENTS or instrument not in page.instruments
            or not isinstance(page.body, bytes)
            or not isinstance(page.retrieved_at, datetime)
            or page.retrieved_at.tzinfo is None
            or page.retrieved_at.utcoffset() != timedelta(0)
            or type(page.http_status) is not int
            or not 100 <= page.http_status <= 599
            or not isinstance(page.request_params, Mapping)
            or any(not isinstance(key, str) or not isinstance(value, str)
                   for key, value in page.request_params.items())):
        raise Hist8Error("provider page identity mismatch")
    params = dict(page.request_params)
    if instrument in EQUITIES:
        expected = dict(ALPACA_FROZEN_PARAMS)
        token = params.pop("page_token", None)
        if (page.source != "ALPACA" or page.feed != "SIP"
                or page.product != "1Min trade OHLCV"
                or page.endpoint != ALPACA_URL or params != expected
                or token is not None
                and (not isinstance(token, str) or not token)):
            raise Hist8Error("provider page identity mismatch")
        return
    if instrument == "BTC-USD":
        if (page.source != "COINBASE" or page.feed != "EXCHANGE"
                or page.product != "BTC-USD granularity=60"
                or page.endpoint != COINBASE_URL
                or set(params) != {"granularity", "start", "end"}
                or params.get("granularity") != "60"):
            raise Hist8Error("provider page identity mismatch")
        try:
            start = _iso_utc(params["start"])
            stop = _iso_utc(params["end"])
        except (KeyError, Hist8Error):
            raise Hist8Error("provider page identity mismatch") from None
        start_text = start.isoformat().replace("+00:00", "Z")
        stop_text = stop.isoformat().replace("+00:00", "Z")
        offset = start - START
        if (params["start"] != start_text or params["end"] != stop_text
                or not START <= start < END
                or offset % timedelta(minutes=COINBASE_WINDOW_MINUTES)
                or stop != min(
                    start + timedelta(minutes=COINBASE_WINDOW_MINUTES), END
                )):
            raise Hist8Error("provider page identity mismatch")
        return
    if instrument == "NASDAQ":
        if (page.source != "MASSIVE" or page.feed != "I:COMP"
                or page.product != "I:COMP minute index OHLC"):
            raise Hist8Error("provider page identity mismatch")
        if page.endpoint == MASSIVE_URL and params == MASSIVE_FROZEN_PARAMS:
            return
        try:
            endpoint, normalized = _strip_secret_query(
                page.endpoint + "?" + urlencode(params)
            )
        except (Hist8Error, ValueError):
            raise Hist8Error("provider page identity mismatch") from None
        if endpoint != page.endpoint or normalized != params:
            raise Hist8Error("provider page identity mismatch")
        return
    raise Hist8Error("provider page identity mismatch")


def _first_page_request(instrument: str) -> tuple[str, dict[str, str]]:
    if instrument in EQUITIES:
        return ALPACA_URL, dict(ALPACA_FROZEN_PARAMS)
    if instrument == "BTC-USD":
        return COINBASE_URL, {
            "granularity": "60",
            "start": START.isoformat().replace("+00:00", "Z"),
            "end": min(
                START + timedelta(minutes=COINBASE_WINDOW_MINUTES), END,
            ).isoformat().replace("+00:00", "Z"),
        }
    if instrument == "NASDAQ":
        return MASSIVE_URL, dict(MASSIVE_FROZEN_PARAMS)
    raise Hist8Error("provider page identity mismatch")


def _next_page_request(
    page: RawPage, instrument: str,
) -> tuple[str, dict[str, str]] | None:
    payload = page.payload()
    if instrument in EQUITIES:
        if not isinstance(payload, Mapping):
            raise Hist8Error("malformed Alpaca page")
        token = payload.get("next_page_token")
        if token is None:
            return None
        if not isinstance(token, str) or not token:
            raise Hist8Error("invalid Alpaca pagination")
        return ALPACA_URL, {**ALPACA_FROZEN_PARAMS, "page_token": token}
    if instrument == "BTC-USD":
        params = dict(page.request_params)
        stop = _iso_utc(params["end"])
        if stop == END:
            return None
        return COINBASE_URL, {
            "granularity": "60",
            "start": stop.isoformat().replace("+00:00", "Z"),
            "end": min(
                stop + timedelta(minutes=COINBASE_WINDOW_MINUTES), END,
            ).isoformat().replace("+00:00", "Z"),
        }
    if instrument == "NASDAQ":
        if not isinstance(payload, Mapping):
            raise Hist8Error("malformed Massive page")
        next_url = payload.get("next_url")
        if next_url is None:
            return None
        if not isinstance(next_url, str) or not next_url:
            raise Hist8Error("invalid Massive pagination")
        return _strip_secret_query(next_url)
    raise Hist8Error("provider page identity mismatch")


def _verified_retrieval_record(
    record: Sequence[object], *, import_id: str, instrument: str,
) -> tuple[int, RawPage]:
    if len(record) != 19:
        raise Hist8ConflictError("retained retrieval record shape mismatch")
    (manifest_id, stored_corpus_id, stored_import_id, manifest_kind,
     sequence_no, source, feed, product, stored_instrument, endpoint,
     request_params, retrieved_at, http_status, content_type,
     content_encoding, artifact_id, artifact_byte_length, raw_byte_length,
     stored_body) = record
    if (stored_corpus_id != CORPUS_ID or stored_import_id != import_id
            or manifest_kind != "RETRIEVAL"
            or stored_instrument != instrument
            or not isinstance(sequence_no, int)
            or not isinstance(request_params, Mapping)
            or stored_body is None):
        raise Hist8ConflictError("retained retrieval manifest identity mismatch")
    body = bytes(stored_body)
    if (artifact_id != _artifact_id(body)
            or artifact_byte_length != len(body)
            or raw_byte_length != len(body)):
        raise Hist8ConflictError("retained raw artifact replay mismatch")
    page = RawPage(
        str(source), str(feed), str(product), (instrument,), str(endpoint),
        dict(request_params), retrieved_at, http_status, content_type,
        content_encoding, body,
    )
    try:
        _validate_page_identity(page, instrument)
        expected_manifest_id = _manifest_id(
            _retrieval_manifest_payload(
                import_id, sequence_no, page, instrument,
            )
        )
    except (Hist8Error, TypeError, ValueError) as exc:
        raise Hist8ConflictError(
            "retained retrieval manifest identity mismatch"
        ) from exc
    if manifest_id != expected_manifest_id:
        raise Hist8ConflictError("retained retrieval manifest identity mismatch")
    return sequence_no, page


def _snapshot_member_manifest_payload(
    import_id: str, sequence_no: int, instrument: str, timeframe: str,
    bar_start_utc: datetime, bar_id: str, content_hash: str,
    provenance_hash: str, research_eligible: bool,
) -> dict[str, object]:
    return {
        "corpus_id": CORPUS_ID,
        "import_id": import_id,
        "kind": "SNAPSHOT_MEMBER",
        "sequence_no": sequence_no,
        "instrument": instrument,
        "timeframe": timeframe,
        "bar_start_utc": bar_start_utc,
        "bar_id": bar_id,
        "content_hash": content_hash,
        "provenance_hash": provenance_hash,
        "research_eligible": research_eligible,
    }


def _verified_snapshot_member_record(
    record: Sequence[object], *, import_id: str,
) -> tuple[int, tuple[object, ...]]:
    if len(record) != 12:
        raise Hist8ConflictError("snapshot member record shape mismatch")
    (manifest_id, stored_corpus_id, stored_import_id, manifest_kind,
     sequence_no, instrument, timeframe, bar_start_utc, bar_id,
     content_hash, provenance_hash, research_eligible) = record
    if (stored_corpus_id != CORPUS_ID or stored_import_id != import_id
            or manifest_kind != "SNAPSHOT_MEMBER"
            or not isinstance(sequence_no, int)
            or not isinstance(instrument, str)
            or not isinstance(timeframe, str)
            or not isinstance(bar_start_utc, datetime)
            or not isinstance(bar_id, str)
            or not isinstance(content_hash, str)
            or not isinstance(provenance_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", provenance_hash)
            or not isinstance(research_eligible, bool)):
        raise Hist8ConflictError("snapshot member manifest identity mismatch")
    expected_manifest_id = _manifest_id(_snapshot_member_manifest_payload(
        import_id, sequence_no, instrument, timeframe, bar_start_utc,
        bar_id, content_hash, provenance_hash, research_eligible,
    ))
    if manifest_id != expected_manifest_id:
        raise Hist8ConflictError("snapshot member manifest identity mismatch")
    return sequence_no, (
        instrument, timeframe, bar_start_utc, bar_id, content_hash,
        provenance_hash, research_eligible,
    )


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
    connection: object, *, expected_implementation_commit: str,
    schema_path: Path | None = None,
) -> dict[str, object]:
    """Install over an already-authorized, verify-full privileged connection."""
    info = getattr(connection, "info", None)
    parameters = (
        getattr(info, "dsn_parameters", {}) if info is not None else {}
    ) or {}
    if (getattr(connection, "autocommit", None) is not True
            or getattr(info, "host", None) != DATABASE_HOST
            or str(getattr(info, "port", "")) != "5432"
            or getattr(info, "dbname", None) != DATABASE_NAME
            or getattr(info, "user", None) != INSTALLER_ROLE
            or parameters.get("sslmode") != "verify-full"
            or parameters.get("sslrootcert") != "system"
            or parameters.get("hostaddr") not in (None, "")):
        raise Hist8Error("HIST8 installer endpoint identity mismatch")
    code_identity = _execution_code_identity()
    _require_reviewed_implementation(
        code_identity, expected_implementation_commit,
    )
    canonical_target = Path(__file__).resolve().with_name("schema.sql")
    target = schema_path or canonical_target
    try:
        if target.resolve(strict=True) != canonical_target.resolve(strict=True):
            raise Hist8Error("HIST8 schema artifact mismatch")
        schema_bytes = target.read_bytes()
        sql = schema_bytes.decode("utf-8")
        expected_schema = code_identity["files"]["research/hist8/schema.sql"]
    except (KeyError, TypeError, UnicodeDecodeError, OSError) as exc:
        raise Hist8Error("HIST8 schema artifact mismatch") from exc
    if (not isinstance(expected_schema, Mapping)
            or expected_schema.get("sha256") != hashlib.sha256(
                schema_bytes
            ).hexdigest()
            or expected_schema.get("byte_length") != len(schema_bytes)
            or not sql.lstrip().startswith("-- ATOM-HIST8-CORPUS-AMENDMENT-1")
            or not sql.rstrip().endswith("COMMIT;")):
        raise Hist8Error("HIST8 schema artifact mismatch")
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
        "implementation_commit": code_identity["implementation_commit"],
    }


class Hist8Store:
    def __init__(self, connection_factory: Callable[[], object]) -> None:
        self._connection_factory = connection_factory
        # Parsing retained provider pages is expensive (especially a large
        # Massive page). Keep only a small rolling cache while independently
        # re-reading and re-hashing every retrieval manifest from PostgreSQL.
        self._provenance_cache: dict[
            tuple[str, str, str], dict[str, tuple[object, ...]]
        ] = {}

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
        return cls(lambda: psycopg.connect(
            dsn,
            connect_timeout=IMPORTER_CONNECT_TIMEOUT_SECONDS,
            options=IMPORTER_SESSION_OPTIONS,
        ))

    @staticmethod
    def _verify(connection: object) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "select current_user, current_database(), "
                "current_setting('session_replication_role'), "
                "current_setting('lo_compat_privileges'), "
                "current_setting('TimeZone')"
            )
            (user, database, replication_role, lo_compat_privileges,
             session_timezone) = (
                cursor.fetchone()
            )
        if (user != IMPORTER_ROLE or database != DATABASE_NAME
                or replication_role != "origin"
                or lo_compat_privileges != "off"
                or session_timezone != "UTC"):
            raise Hist8Error("HIST8 database identity mismatch")

    def _verify_canonical_provenance(
        self, cursor: object, rows: Sequence[Bar],
    ) -> None:
        canonical = [row for row in rows if row.timeframe == "1m"]
        if not canonical:
            return
        expected: dict[tuple[str, str, str, str], tuple[object, ...]] = {}
        for row in canonical:
            source_row = _source_bar_from_canonical(row)
            key = (
                row.import_id, row.instrument, source_row.artifact_id,
                source_row.locator,
            )
            payload = _source_bar_payload(source_row)
            prior = expected.get(key)
            if prior is not None and prior != payload:
                raise Hist8ConflictError("canonical provenance identity conflict")
            expected[key] = payload
        import_ids = sorted({key[0] for key in expected})
        instruments = sorted({key[1] for key in expected})
        artifact_ids = sorted({key[2] for key in expected})
        cursor.execute(
            """select m.manifest_id,m.corpus_id,m.import_id,
                      m.manifest_kind,m.sequence_no,m.source,m.feed,
                      m.product,m.instrument,m.endpoint,m.request_params,
                      m.retrieved_at,m.http_status,m.content_type,
                      m.content_encoding,m.artifact_id,
                      m.artifact_byte_length,r.byte_length,r.body
               from atom_research_history.manifests m
               left join atom_research_history.raw_responses r
                 on r.artifact_id=m.artifact_id
               where m.corpus_id=%s and m.manifest_kind='RETRIEVAL'
                 and m.import_id = any(%s) and m.instrument = any(%s)
                 and m.artifact_id = any(%s)""",
            (CORPUS_ID, import_ids, instruments, artifact_ids),
        )
        resolved: dict[tuple[str, str, str, str], tuple[object, ...]] = {}
        for record in cursor.fetchall():
            stored_import_id = record[2]
            stored_instrument = record[8]
            stored_artifact_id = record[15]
            if (not isinstance(stored_import_id, str)
                    or not isinstance(stored_instrument, str)
                    or not isinstance(stored_artifact_id, str)):
                raise Hist8ConflictError(
                    "canonical provenance retrieval identity mismatch"
                )
            _, page = _verified_retrieval_record(
                record, import_id=stored_import_id,
                instrument=stored_instrument,
            )
            page_key = (
                stored_import_id, stored_instrument, stored_artifact_id,
            )
            parsed = self._provenance_cache.get(page_key)
            if parsed is None:
                parsed = {}
                rejected = [0]
                for source_row in parse_source_page(
                    page, stored_instrument, rejection_counter=rejected,
                ):
                    payload = _source_bar_payload(source_row)
                    prior = parsed.get(source_row.locator)
                    if prior is not None and prior != payload:
                        raise Hist8ConflictError(
                            "canonical provenance locator conflict"
                        )
                    parsed[source_row.locator] = payload
                self._provenance_cache[page_key] = parsed
                while len(self._provenance_cache) > 8:
                    del self._provenance_cache[next(iter(self._provenance_cache))]
            for key in expected:
                if key[:3] != page_key:
                    continue
                payload = parsed.get(key[3])
                if payload is None:
                    continue
                prior = resolved.get(key)
                if prior is not None and prior != payload:
                    raise Hist8ConflictError(
                        "canonical provenance locator conflict"
                    )
                resolved[key] = payload
        for key, payload in expected.items():
            if resolved.get(key) != payload:
                raise Hist8ConflictError(
                    "canonical provenance does not resolve to retained source"
                )

    def stored_canonical_source_bar(
        self, instrument: str, session_date: str, start: datetime,
    ) -> SourceBar:
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select bar_id,content_hash,corpus_id,instrument,
                              timeframe,bar_start_utc,bar_end_utc,session_date,
                              calendar_id,calendar_sha256,open,high,low,close,
                              volume,trade_count,vwap,volume_unit,source,feed,
                              product,adjustment,price_unit,import_id,
                              derivation_version,source_artifact_id,
                              source_record_locator,lineage_json
                       from atom_research_history.bars
                       where corpus_id=%s and instrument=%s and timeframe='1m'
                         and session_date=%s and bar_start_utc=%s""",
                    (CORPUS_ID, instrument, session_date, start),
                )
                records = cursor.fetchall()
                if len(records) != 1:
                    raise Hist8ConflictError(
                        "flushed overlap canonical row missing or duplicated"
                    )
                stored = _verified_stored_bar(records[0])
                self._verify_canonical_provenance(cursor, (stored,))
        return _source_bar_from_canonical(stored)

    def add_attempt(
        self, import_id: str, kind: str, metadata: Mapping[str, object],
    ) -> None:
        if (kind not in {"IMPORT_ATTEMPT", "REPLAY_ATTEMPT"}
                or not isinstance(import_id, str)
                or not 1 <= len(import_id) <= 128):
            raise Hist8Error("attempt manifest identity mismatch")
        try:
            canonical_metadata = _canonical(dict(metadata))
        except (TypeError, ValueError) as exc:
            raise Hist8Error("attempt manifest identity mismatch") from exc
        if not isinstance(canonical_metadata, dict):
            raise Hist8Error("attempt manifest identity mismatch")
        payload = {"corpus_id": CORPUS_ID, "import_id": import_id,
                   "kind": kind, "sequence_no": 0,
                   "metadata": canonical_metadata}
        manifest_id = _manifest_id(payload)
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into atom_research_history.manifests
                    (manifest_id, corpus_id, manifest_kind, import_id, sequence_no,
                     metadata_json) values (%s,%s,%s,%s,0,%s)
                    on conflict do nothing""",
                    (manifest_id, CORPUS_ID, kind, import_id,
                     json.dumps(canonical_metadata)),
                )
            connection.commit()
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select manifest_id,corpus_id,import_id,manifest_kind,
                              sequence_no,metadata_json
                       from atom_research_history.manifests
                       where corpus_id=%s and import_id=%s
                         and manifest_kind=%s and sequence_no=0""",
                    (CORPUS_ID, import_id, kind),
                )
                records = cursor.fetchall()
        if len(records) != 1:
            raise Hist8ConflictError("attempt manifest readback mismatch")
        (stored_manifest_id, stored_corpus_id, stored_import_id,
         stored_kind, stored_sequence, stored_metadata) = records[0]
        try:
            canonical_stored_metadata = _canonical(stored_metadata)
            stored_identity = _manifest_id({
                "corpus_id": stored_corpus_id,
                "import_id": stored_import_id,
                "kind": stored_kind,
                "sequence_no": stored_sequence,
                "metadata": canonical_stored_metadata,
            })
        except (TypeError, ValueError) as exc:
            raise Hist8ConflictError(
                "attempt manifest readback mismatch"
            ) from exc
        if (stored_manifest_id != manifest_id
                or stored_identity != stored_manifest_id
                or stored_corpus_id != CORPUS_ID
                or stored_import_id != import_id or stored_kind != kind
                or stored_sequence != 0
                or canonical_stored_metadata != canonical_metadata):
            raise Hist8ConflictError("attempt manifest readback mismatch")

    def store_page(self, import_id: str, sequence: int, page: RawPage) -> int:
        if tuple(page.instruments) not in (
            EQUITIES, ("BTC-USD",), ("NASDAQ",),
        ):
            raise Hist8Error("provider page instrument set mismatch")
        for instrument in page.instruments:
            _validate_page_identity(page, instrument)
        artifact_id = _artifact_id(page.body)
        expected_manifests: dict[str, tuple[int, str]] = {}
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
                    payload = _retrieval_manifest_payload(
                        import_id, number, page, instrument,
                    )
                    manifest_id = _manifest_id(payload)
                    expected_manifests[manifest_id] = (number, instrument)
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
                    """select m.manifest_id,m.corpus_id,m.import_id,
                              m.manifest_kind,m.sequence_no,m.source,m.feed,
                              m.product,m.instrument,m.endpoint,m.request_params,
                              m.retrieved_at,m.http_status,m.content_type,
                              m.content_encoding,m.artifact_id,
                              m.artifact_byte_length,r.byte_length,r.body
                       from atom_research_history.manifests m
                       left join atom_research_history.raw_responses r
                         on r.artifact_id=m.artifact_id
                       where m.manifest_id = any(%s)""",
                    (list(expected_manifests),),
                )
                durable_manifests: set[str] = set()
                for record in cursor.fetchall():
                    expected = expected_manifests.get(record[0])
                    if expected is None:
                        raise Hist8ConflictError(
                            "retrieval provenance post-commit mismatch"
                        )
                    recorded_sequence, _recorded_page = (
                        _verified_retrieval_record(
                            record, import_id=import_id,
                            instrument=expected[1],
                        )
                    )
                    if recorded_sequence != expected[0]:
                        raise Hist8ConflictError(
                            "retrieval provenance post-commit mismatch"
                        )
                    durable_manifests.add(record[0])
                if durable_manifests != set(expected_manifests):
                    raise Hist8ConflictError("retrieval provenance post-commit mismatch")
        return sequence + len(page.instruments)

    def retrieval_pages(self, import_id: str, instrument: str) -> Iterator[RawPage]:
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select max(sequence_no)
                       from atom_research_history.manifests
                       where corpus_id=%s and import_id=%s
                         and manifest_kind='RETRIEVAL' and instrument=%s""",
                    (CORPUS_ID, import_id, instrument),
                )
                upper_sequence = cursor.fetchone()[0]
        if upper_sequence is None:
            return
        last_sequence = -1
        while last_sequence < upper_sequence:
            batch: list[tuple[int, RawPage]] = []
            with self._connection_factory() as connection:
                self._verify(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select m.manifest_id,m.corpus_id,m.import_id,
                                  m.manifest_kind,m.sequence_no,m.source,m.feed,
                                  m.product,m.instrument,m.endpoint,m.request_params,
                                  m.retrieved_at,m.http_status,m.content_type,
                                  m.content_encoding,m.artifact_id,
                                  m.artifact_byte_length,r.byte_length,r.body
                           from atom_research_history.manifests m
                           left join atom_research_history.raw_responses r
                             on r.artifact_id=m.artifact_id
                           where m.corpus_id=%s and m.import_id=%s
                             and m.manifest_kind='RETRIEVAL'
                             and m.instrument=%s and m.sequence_no>%s
                             and m.sequence_no<=%s
                           order by m.sequence_no
                           limit %s""",
                        (CORPUS_ID, import_id, instrument, last_sequence,
                         upper_sequence, REPLAY_PAGE_BATCH_SIZE),
                    )
                    records = cursor.fetchall()
                    for record in records:
                        batch.append(_verified_retrieval_record(
                            record, import_id=import_id,
                            instrument=instrument,
                        ))
            if not batch:
                raise Hist8ConflictError("retrieval replay sequence gap")
            last_sequence = batch[-1][0]
            for _, page in batch:
                yield page

    def sealed_snapshot_state(self, import_id: str) -> dict[str, object]:
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select corpus_id,import_id,manifest_kind,sequence_no,
                              manifest_id,metadata_json
                       from atom_research_history.manifests
                       where corpus_id=%s and import_id=%s
                         and manifest_kind='SNAPSHOT'""",
                    (CORPUS_ID, import_id),
                )
                rows = cursor.fetchall()
        if len(rows) != 1 or not isinstance(rows[0][5], Mapping):
            raise Hist8Error("sealed source snapshot missing or invalid")
        (stored_corpus_id, stored_import_id, manifest_kind, sequence_no,
         manifest_id, metadata) = rows[0]
        membership = metadata.get("membership_sha256")
        if (stored_corpus_id != CORPUS_ID
                or stored_import_id != import_id
                or manifest_kind != "SNAPSHOT"
                or sequence_no != 0
                or not isinstance(manifest_id, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_id)
                or not isinstance(membership, str)
                or not re.fullmatch(r"[0-9a-f]{64}", membership)):
            raise Hist8Error("sealed source snapshot missing or invalid")
        expected_manifest_id = _manifest_id({
            "corpus_id": stored_corpus_id,
            "import_id": stored_import_id,
            "kind": manifest_kind,
            "sequence_no": sequence_no,
            "metadata": metadata,
        })
        if manifest_id != expected_manifest_id:
            raise Hist8ConflictError(
                "sealed source snapshot manifest identity mismatch"
            )
        return {
            "manifest_id": manifest_id,
            "metadata": dict(metadata),
            "membership_sha256": membership,
        }

    def sealed_snapshot_digest(self, import_id: str) -> str:
        return str(self.sealed_snapshot_state(import_id)["membership_sha256"])

    def _write_bar_conflict(
        self, *, import_id: str, sequence: int, instrument: str,
        metadata: Mapping[str, object],
    ) -> None:
        canonical_metadata = _canonical(dict(metadata))
        if not isinstance(canonical_metadata, dict):
            raise Hist8ConflictError("bar conflict evidence mismatch")
        payload = {
            "corpus_id": CORPUS_ID, "import_id": import_id,
            "kind": "BAR_CONFLICT", "sequence_no": sequence,
            "instrument": instrument, "metadata": canonical_metadata,
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
                    (manifest_id, CORPUS_ID, import_id, sequence,
                     instrument, json.dumps(canonical_metadata)),
                )
            connection.commit()
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select manifest_id,metadata_json
                       from atom_research_history.manifests
                       where corpus_id=%s and import_id=%s
                         and manifest_kind='BAR_CONFLICT' and sequence_no=%s""",
                    (CORPUS_ID, import_id, sequence),
                )
                recorded = cursor.fetchone()
        if (recorded is None or recorded[0] != manifest_id
                or _canonical(recorded[1]) != canonical_metadata):
            raise Hist8ConflictError("bar conflict evidence mismatch")

    def _record_bar_conflict(self, row: Bar, existing: Bar) -> None:
        metadata = {
            "conflict_kind": "SAME_CANONICAL_KEY",
            "conflict_stage": "DATABASE_INSERT",
            "canonical_key": {
                "corpus_id": row.corpus_id,
                "instrument": row.instrument,
                "timeframe": row.timeframe,
                "bar_start_utc": row.bar_start_utc,
            },
            "existing": {
                "bar_id": existing.bar_id,
                "content_hash": existing.content_hash,
                "originating_import_id": existing.import_id,
            },
            "candidate": {
                "bar_id": row.bar_id,
                "content_hash": row.content_hash,
                "attempt_import_id": row.import_id,
                "source_artifact_id": row.source_artifact_id,
                "source_record_locator": row.source_record_locator,
                "semantic_payload": _content_payload(row),
            },
        }
        self._write_bar_conflict(
            import_id=row.import_id, sequence=_membership_sequence(row),
            instrument=row.instrument, metadata=metadata,
        )

    def record_source_bar_conflict(
        self, *, import_id: str, session_date: str, calendar_id: str,
        calendar_sha256: str, existing: SourceBar, candidate: SourceBar,
    ) -> None:
        if (_source_bar_payload(existing) == _source_bar_payload(candidate)
                or existing.instrument != candidate.instrument
                or existing.start != candidate.start):
            raise Hist8ConflictError("invalid provider bar conflict evidence")
        existing_bar = canonical_bar(
            existing, session_date=session_date,
            calendar_hash=calendar_sha256, calendar_id=calendar_id,
            import_id=import_id, eligible=False,
        )
        candidate_bar = canonical_bar(
            candidate, session_date=session_date,
            calendar_hash=calendar_sha256, calendar_id=calendar_id,
            import_id=import_id, eligible=False,
        )
        if existing_bar.content_hash == candidate_bar.content_hash:
            raise Hist8ConflictError("invalid provider bar conflict evidence")
        metadata = {
            "conflict_kind": "SAME_CANONICAL_KEY",
            "conflict_stage": "RETAINED_PROVIDER_ROWS",
            "canonical_key": {
                "corpus_id": CORPUS_ID,
                "instrument": candidate.instrument,
                "timeframe": "1m",
                "bar_start_utc": candidate.start,
            },
            "existing": {
                "bar_id": existing_bar.bar_id,
                "content_hash": existing_bar.content_hash,
                "attempt_import_id": import_id,
                "source_artifact_id": existing.artifact_id,
                "source_record_locator": existing.locator,
                "semantic_payload": _content_payload(existing_bar),
            },
            "candidate": {
                "bar_id": candidate_bar.bar_id,
                "content_hash": candidate_bar.content_hash,
                "attempt_import_id": import_id,
                "source_artifact_id": candidate.artifact_id,
                "source_record_locator": candidate.locator,
                "semantic_payload": _content_payload(candidate_bar),
            },
        }
        self._write_bar_conflict(
            import_id=import_id,
            sequence=_membership_sequence(candidate_bar),
            instrument=candidate.instrument, metadata=metadata,
        )

    def insert_bars(
        self, rows: Sequence[Bar], *, session_open: datetime,
        session_close: datetime, expected_minutes: int,
        expected_session_date: str, expected_calendar_id: str,
        expected_calendar_sha256: str, source_chain_complete: bool = True,
    ) -> tuple[int, int]:
        if not rows:
            return 0, 0
        _verify_materialized_session(
            rows, session_open=session_open, session_close=session_close,
            expected_minutes=expected_minutes,
            expected_session_date=expected_session_date,
            expected_calendar_id=expected_calendar_id,
            expected_calendar_sha256=expected_calendar_sha256,
            source_chain_complete=source_chain_complete,
        )
        if len({row.import_id for row in rows}) != 1:
            raise Hist8ConflictError("mixed snapshot attempt identity")
        keys = [(row.corpus_id, row.instrument, row.timeframe, row.bar_start_utc)
                for row in rows]
        if len(keys) != len(set(keys)):
            raise Hist8ConflictError("duplicate generated bar identity")
        inserted = 0
        conflict: tuple[Bar, Bar] | None = None
        try:
            with self._connection_factory() as connection:
                self._verify(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select bar_id,content_hash,corpus_id,instrument,
                                  timeframe,bar_start_utc,bar_end_utc,session_date,
                                  calendar_id,calendar_sha256,open,high,low,close,
                                  volume,trade_count,vwap,volume_unit,source,feed,
                                  product,adjustment,price_unit,import_id,
                                  derivation_version,source_artifact_id,
                                  source_record_locator,lineage_json
                           from atom_research_history.bars
                           where corpus_id=%s and instrument=%s and session_date=%s""",
                        (CORPUS_ID, rows[0].instrument, rows[0].session_date),
                    )
                    existing: dict[tuple[str, datetime], Bar] = {}
                    for record in cursor.fetchall():
                        stored = _verified_stored_bar(record)
                        key = (stored.timeframe, stored.bar_start_utc)
                        if key in existing:
                            raise Hist8ConflictError(
                                "duplicate stored bar identity"
                            )
                        existing[key] = stored
                    pending = []
                    for row in rows:
                        key = (row.timeframe, row.bar_start_utc)
                        if key in existing:
                            stored = existing[key]
                            if stored.content_hash != row.content_hash:
                                conflict = (row, stored)
                                raise Hist8ConflictError("same-key bar conflict")
                            continue
                        pending.append(row)
                    self._verify_canonical_provenance(
                        cursor, (*existing.values(), *pending),
                    )
                    if pending:
                        cursor.executemany(
                            """insert into atom_research_history.bars
                            (bar_id,content_hash,corpus_id,instrument,timeframe,bar_start_utc,
                             bar_end_utc,session_date,calendar_id,calendar_sha256,open,high,
                             low,close,volume,trade_count,vwap,volume_unit,source,feed,product,
                             adjustment,price_unit,import_id,derivation_version,
                             source_artifact_id,source_record_locator,lineage_json)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            on conflict do nothing""",
                            [_bar_values(row) for row in pending],
                        )
                        inserted = cursor.rowcount
                        if not 0 <= inserted <= len(pending):
                            raise Hist8ConflictError(
                                "bar insert affected-row count mismatch"
                            )
                    cursor.execute(
                        """select bar_id,content_hash,corpus_id,instrument,
                                  timeframe,bar_start_utc,bar_end_utc,session_date,
                                  calendar_id,calendar_sha256,open,high,low,close,
                                  volume,trade_count,vwap,volume_unit,source,feed,
                                  product,adjustment,price_unit,import_id,
                                  derivation_version,source_artifact_id,
                                  source_record_locator,lineage_json
                           from atom_research_history.bars
                           where corpus_id=%s and instrument=%s and session_date=%s""",
                        (CORPUS_ID, rows[0].instrument, rows[0].session_date),
                    )
                    verified: dict[tuple[str, datetime], Bar] = {}
                    for record in cursor.fetchall():
                        stored = _verified_stored_bar(record)
                        key = (stored.timeframe, stored.bar_start_utc)
                        if key in verified:
                            raise Hist8ConflictError(
                                "duplicate stored bar identity"
                            )
                        verified[key] = stored
                    self._verify_canonical_provenance(
                        cursor, tuple(verified.values()),
                    )
                    verified_attempt_rows: list[Bar] = []
                    for row in rows:
                        actual = verified.get((row.timeframe, row.bar_start_utc))
                        if actual is None:
                            raise Hist8ConflictError("bar readback missing")
                        if actual.content_hash != row.content_hash:
                            conflict = (row, actual)
                            raise Hist8ConflictError("same-key bar conflict")
                        verified_attempt_rows.append(replace(
                            actual, research_eligible=row.research_eligible,
                        ))
                    _verify_materialized_session(
                        verified_attempt_rows,
                        session_open=session_open,
                        session_close=session_close,
                        expected_minutes=expected_minutes,
                        expected_session_date=expected_session_date,
                        expected_calendar_id=expected_calendar_id,
                        expected_calendar_sha256=expected_calendar_sha256,
                        source_chain_complete=source_chain_complete,
                    )

                    members = []
                    expected_members = {}
                    for row in rows:
                        sequence = _membership_sequence(row)
                        actual = verified[(row.timeframe, row.bar_start_utc)]
                        provenance_hash = _bar_provenance_hash(actual)
                        payload = _snapshot_member_manifest_payload(
                            row.import_id, sequence, row.instrument,
                            row.timeframe, row.bar_start_utc, row.bar_id,
                            row.content_hash, provenance_hash,
                            row.research_eligible,
                        )
                        expected_members[sequence] = (
                            row.instrument, row.timeframe, row.bar_start_utc,
                            row.bar_id, row.content_hash, provenance_hash,
                            row.research_eligible,
                        )
                        members.append((
                            _manifest_id(payload), CORPUS_ID, row.import_id, sequence,
                            row.instrument, row.bar_id, row.content_hash,
                            provenance_hash, row.timeframe, row.bar_start_utc,
                            row.research_eligible,
                        ))
                    cursor.executemany(
                        """insert into atom_research_history.manifests
                        (manifest_id,corpus_id,manifest_kind,import_id,sequence_no,
                         instrument,member_bar_id,member_content_hash,
                         member_provenance_hash,member_timeframe,member_bar_start_utc,
                         member_research_eligible,metadata_json)
                        values (%s,%s,'SNAPSHOT_MEMBER',%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb)
                        on conflict (manifest_id) do nothing""", members,
                    )
                    cursor.execute(
                        """select manifest_id,corpus_id,import_id,manifest_kind,
                                  sequence_no,instrument,member_timeframe,
                                  member_bar_start_utc,member_bar_id,
                                  member_content_hash,member_provenance_hash,
                                  member_research_eligible
                           from atom_research_history.manifests
                           where corpus_id=%s and import_id=%s
                             and manifest_kind='SNAPSHOT_MEMBER'
                             and sequence_no = any(%s)""",
                        (CORPUS_ID, rows[0].import_id, list(expected_members)),
                    )
                    actual_members = {}
                    for record in cursor.fetchall():
                        sequence, member = _verified_snapshot_member_record(
                            record, import_id=rows[0].import_id,
                        )
                        if sequence in actual_members:
                            raise Hist8ConflictError(
                                "duplicate snapshot member identity"
                            )
                        actual_members[sequence] = member
                    if actual_members != expected_members:
                        raise Hist8ConflictError(
                            "snapshot membership readback mismatch"
                        )
        except Hist8ConflictError:
            if conflict is not None:
                self._record_bar_conflict(*conflict)
            raise
        return inserted, len(rows) - inserted

    def _verify_snapshot_derivations(
        self, import_id: str,
        source_statuses: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        calendar = load_calendar()
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select distinct b.instrument,b.session_date
                       from atom_research_history.manifests m
                       join atom_research_history.bars b
                         on b.bar_id=m.member_bar_id
                        and b.content_hash=m.member_content_hash
                       where m.corpus_id=%s and m.import_id=%s
                         and m.manifest_kind='SNAPSHOT_MEMBER'
                       order by b.instrument,b.session_date""",
                    (CORPUS_ID, import_id),
                )
                session_keys = cursor.fetchall()
        for offset in range(0, len(session_keys), SNAPSHOT_SESSION_BATCH_SIZE):
            batch = session_keys[offset:offset + SNAPSHOT_SESSION_BATCH_SIZE]
            instruments = [key[0] for key in batch]
            session_dates = [key[1] for key in batch]
            with self._connection_factory() as connection:
                self._verify(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """with target(instrument,session_date) as (
                             select * from unnest(%s::text[],%s::text[])
                           )
                           select m.manifest_id,m.corpus_id,m.import_id,
                                  m.manifest_kind,m.sequence_no,m.instrument,
                                  m.member_timeframe,m.member_bar_start_utc,
                                  m.member_bar_id,m.member_content_hash,
                                  m.member_provenance_hash,
                                  m.member_research_eligible,
                                  b.bar_id,b.content_hash,b.corpus_id,
                                  b.instrument,b.timeframe,b.bar_start_utc,
                                  b.bar_end_utc,b.session_date,b.calendar_id,
                                  b.calendar_sha256,b.open,b.high,b.low,b.close,
                                  b.volume,b.trade_count,b.vwap,b.volume_unit,
                                  b.source,b.feed,b.product,b.adjustment,
                                  b.price_unit,b.import_id,b.derivation_version,
                                  b.source_artifact_id,b.source_record_locator,
                                  b.lineage_json
                           from atom_research_history.manifests m
                           join atom_research_history.bars b
                             on b.bar_id=m.member_bar_id
                            and b.content_hash=m.member_content_hash
                           join target
                             on target.instrument=b.instrument
                            and target.session_date=b.session_date
                           where m.corpus_id=%s and m.import_id=%s
                             and m.manifest_kind='SNAPSHOT_MEMBER'
                           order by b.instrument,b.session_date,b.timeframe,
                                    b.bar_start_utc""",
                        (instruments, session_dates, CORPUS_ID, import_id),
                    )
                    records = cursor.fetchall()
            grouped: dict[tuple[str, str], list[Bar]] = {
                (str(instrument), str(session_date)): []
                for instrument, session_date in batch
            }
            seen: set[tuple[str, str, datetime]] = set()
            for record in records:
                sequence, member = _verified_snapshot_member_record(
                    record[:12], import_id=import_id,
                )
                (instrument, timeframe, bar_start_utc, bar_id,
                 content_hash, provenance_hash, eligible) = member
                row = _verified_stored_bar(record[12:])
                if (row.instrument != instrument or row.timeframe != timeframe
                        or row.bar_start_utc != bar_start_utc
                        or row.bar_id != bar_id
                        or row.content_hash != content_hash
                        or _bar_provenance_hash(row) != provenance_hash
                        or _membership_sequence(row) != sequence):
                    raise Hist8ConflictError(
                        "snapshot member bar identity mismatch"
                    )
                key = (row.instrument, row.timeframe, row.bar_start_utc)
                if key in seen:
                    raise Hist8ConflictError(
                        "duplicate snapshot member identity"
                    )
                seen.add(key)
                grouped[(row.instrument, row.session_date)].append(replace(
                    row, research_eligible=eligible,
                ))
            for (instrument, session_date), rows in grouped.items():
                definitions = _session_definitions(calendar, instrument)
                bounds = definitions.get(session_date)
                if bounds is None or not rows:
                    raise Hist8ConflictError(
                        "snapshot session boundary mismatch"
                    )
                _verify_materialized_session(
                    rows, session_open=bounds[0], session_close=bounds[1],
                    expected_minutes=bounds[2],
                    expected_session_date=session_date,
                    expected_calendar_id=str(
                        calendar["instrument_calendars"][instrument]
                    ),
                    expected_calendar_sha256=str(calendar["schedule_sha256"]),
                    source_chain_complete=(
                        source_statuses is None
                        or source_statuses[instrument]["availability"]
                        == "AVAILABLE"
                    ),
                )

    def seal_snapshot(
        self, import_id: str, metadata: Mapping[str, object], *,
        expected_membership_sha256: str | None = None,
    ) -> str:
        if (expected_membership_sha256 is not None
                and (not isinstance(expected_membership_sha256, str)
                     or re.fullmatch(
                         r"[0-9a-f]{64}", expected_membership_sha256,
                     ) is None)):
            raise Hist8Error("expected snapshot membership is invalid")
        digest = hashlib.sha256()
        counts: dict[str, int] = {}
        lock_connection = self._connection_factory()
        lock_acquired = False
        try:
            self._verify(lock_connection)
            # A session lock conflicts with the membership trigger's transaction
            # lock but survives commits. This freezes membership without holding
            # an MVCC snapshot while the evidence is scanned in short batches.
            with lock_connection.cursor() as lock_cursor:
                lock_cursor.execute(
                    "select pg_advisory_lock(hashtextextended(%s, 0))",
                    (import_id,),
                )
            lock_connection.commit()
            lock_acquired = True
            source_statuses = (
                None if "source_statuses" not in metadata
                else _validated_source_statuses(metadata["source_statuses"])
            )
            self._verify_snapshot_derivations(import_id, source_statuses)
            with self._connection_factory() as read_connection:
                self._verify(read_connection)
                with read_connection.cursor() as cursor:
                    cursor.execute(
                        """select max(sequence_no)
                           from atom_research_history.manifests
                           where corpus_id=%s and import_id=%s
                             and manifest_kind='SNAPSHOT_MEMBER'""",
                        (CORPUS_ID, import_id),
                    )
                    upper_sequence = cursor.fetchone()[0]
            last_sequence = -1
            while (upper_sequence is not None
                   and last_sequence < upper_sequence):
                with self._connection_factory() as read_connection:
                    self._verify(read_connection)
                    with read_connection.cursor() as cursor:
                        cursor.execute(
                            """select m.manifest_id,m.corpus_id,m.import_id,
                                      m.manifest_kind,m.sequence_no,m.instrument,
                                      m.member_timeframe,m.member_bar_start_utc,
                                      m.member_bar_id,m.member_content_hash,
                                      m.member_provenance_hash,
                                      m.member_research_eligible,
                                      b.bar_id,b.content_hash,b.corpus_id,
                                      b.instrument,b.timeframe,b.bar_start_utc,
                                      b.bar_end_utc,b.session_date,b.calendar_id,
                                      b.calendar_sha256,b.open,b.high,b.low,
                                      b.close,b.volume,b.trade_count,b.vwap,
                                      b.volume_unit,b.source,b.feed,b.product,
                                      b.adjustment,b.price_unit,b.import_id,
                                      b.derivation_version,b.source_artifact_id,
                                      b.source_record_locator,b.lineage_json
                               from atom_research_history.manifests m
                               left join atom_research_history.bars b
                                 on b.bar_id=m.member_bar_id
                                and b.content_hash=m.member_content_hash
                               where m.corpus_id=%s and m.import_id=%s
                                 and m.manifest_kind='SNAPSHOT_MEMBER'
                                 and m.sequence_no>%s and m.sequence_no<=%s
                               order by m.sequence_no
                               limit %s""",
                            (CORPUS_ID, import_id, last_sequence,
                             upper_sequence, SNAPSHOT_SCAN_BATCH_SIZE),
                        )
                        members = cursor.fetchall()
                if not members:
                    raise Hist8ConflictError("snapshot member scan gap")
                batch_items = []
                for record in members:
                    sequence, member = _verified_snapshot_member_record(
                        record[:12], import_id=import_id,
                    )
                    (instrument, timeframe, bar_start_utc, bar_id,
                     content_hash, provenance_hash, eligible) = member
                    referenced_bar = _verified_stored_bar(record[12:])
                    if (referenced_bar.bar_id != bar_id
                            or referenced_bar.content_hash != content_hash
                            or referenced_bar.instrument != instrument
                            or referenced_bar.timeframe != timeframe
                            or referenced_bar.bar_start_utc != bar_start_utc
                            or _bar_provenance_hash(referenced_bar)
                            != provenance_hash
                            or _membership_sequence(referenced_bar) != sequence):
                        raise Hist8ConflictError(
                            "snapshot member bar identity mismatch"
                        )
                    batch_items.append((
                        sequence, instrument, timeframe, bar_id, content_hash,
                        provenance_hash, eligible, referenced_bar,
                    ))
                with self._connection_factory() as provenance_connection:
                    self._verify(provenance_connection)
                    with provenance_connection.cursor() as provenance_cursor:
                        self._verify_canonical_provenance(
                            provenance_cursor,
                            tuple(item[7] for item in batch_items),
                        )
                for (sequence, instrument, timeframe, bar_id, content_hash,
                     provenance_hash, eligible, _referenced_bar) in batch_items:
                    digest.update(canonical_bytes((
                        instrument, timeframe, bar_id, content_hash,
                        provenance_hash, eligible,
                    )))
                    key = f"{instrument}/{timeframe}"
                    counts[key] = counts.get(key, 0) + 1
                    last_sequence = sequence
            membership_sha256 = digest.hexdigest()
            if (expected_membership_sha256 is not None
                    and membership_sha256 != expected_membership_sha256):
                raise Hist8ConflictError(
                    "replay membership differs from sealed source snapshot"
                )
            snapshot = {
                **dict(metadata), "membership_sha256": membership_sha256,
                "row_counts": {key: counts.get(key, 0) for key in
                               (f"{i}/{t}" for i in INSTRUMENTS for t in TIMEFRAMES)},
            }
            payload = {"corpus_id": CORPUS_ID, "import_id": import_id,
                       "kind": "SNAPSHOT", "sequence_no": 0, "metadata": snapshot}
            manifest_id = _manifest_id(payload)
            with lock_connection.cursor() as cursor:
                cursor.execute(
                    """insert into atom_research_history.manifests
                    (manifest_id,corpus_id,manifest_kind,import_id,sequence_no,metadata_json)
                    values (%s,%s,'SNAPSHOT',%s,0,%s) on conflict (manifest_id) do nothing""",
                    (manifest_id, CORPUS_ID, import_id,
                     json.dumps(_canonical(snapshot))),
                )
            lock_connection.commit()
            self._verify(lock_connection)
            recorded = self.sealed_snapshot_state(import_id)
            if (recorded["manifest_id"] != manifest_id
                    or _canonical(recorded["metadata"]) != _canonical(snapshot)):
                raise Hist8ConflictError("snapshot manifest readback mismatch")
            return membership_sha256
        finally:
            lock_connection.rollback()
            if lock_acquired:
                with lock_connection.cursor() as lock_cursor:
                    lock_cursor.execute(
                        "select pg_advisory_unlock(hashtextextended(%s, 0))",
                        (import_id,),
                    )
                    released = lock_cursor.fetchone()[0]
                lock_connection.commit()
                if released is not True:
                    raise Hist8ConflictError("snapshot advisory unlock mismatch")
            lock_connection.close()


def _bar_values(row: Bar) -> tuple[object, ...]:
    values = asdict(row)
    return (
        values["bar_id"], values["content_hash"], values["corpus_id"],
        values["instrument"], values["timeframe"], values["bar_start_utc"],
        values["bar_end_utc"], values["session_date"], values["calendar_id"],
        values["calendar_sha256"], values["open"], values["high"], values["low"],
        values["close"], values["volume"], values["trade_count"], values["vwap"],
        values["volume_unit"], values["source"], values["feed"], values["product"],
        values["adjustment"], values["price_unit"], values["import_id"],
        values["derivation_version"], values["source_artifact_id"],
        values["source_record_locator"], json.dumps(list(row.lineage)),
    )


def _verified_stored_bar(record: Sequence[object]) -> Bar:
    if len(record) != 28 or not isinstance(record[27], list):
        raise Hist8ConflictError("stored bar record shape mismatch")
    stored = Bar(
        record[0], record[1], record[2], record[3], record[4], record[5],
        record[6], record[7], record[8], record[9], record[10], record[11],
        record[12], record[13], record[14], record[15], record[16], record[17],
        record[18], record[19], record[20], record[21], record[22], record[23],
        record[24], record[25], record[26], tuple(record[27]), False,
    )
    try:
        expected_hash = sha256(_content_payload(stored))
    except (TypeError, ValueError) as exc:
        raise Hist8ConflictError("stored bar identity mismatch") from exc
    if (stored.content_hash != expected_hash
            or stored.bar_id != "hist8bar:" + expected_hash):
        raise Hist8ConflictError("stored bar identity mismatch")
    _validate_bar_identity(stored)
    return stored


def _bar_provenance_hash(row: Bar) -> str:
    if row.timeframe == "1m":
        if (not isinstance(row.source_artifact_id, str)
                or not isinstance(row.source_record_locator, str)
                or row.lineage):
            raise Hist8ConflictError("canonical provenance shape mismatch")
    elif (row.source_artifact_id is not None
          or row.source_record_locator is not None or not row.lineage):
        raise Hist8ConflictError("derived provenance shape mismatch")
    try:
        return sha256({
            "corpus_id": row.corpus_id,
            "instrument": row.instrument,
            "timeframe": row.timeframe,
            "bar_start_utc": row.bar_start_utc,
            "bar_id": row.bar_id,
            "content_hash": row.content_hash,
            "originating_import_id": row.import_id,
            "source_artifact_id": row.source_artifact_id,
            "source_record_locator": row.source_record_locator,
            "lineage": list(row.lineage),
        })
    except (TypeError, ValueError) as exc:
        raise Hist8ConflictError("bar provenance identity mismatch") from exc


def _validate_bar_identity(row: Bar) -> None:
    duration = 1 if row.timeframe == "1m" else TIMEFRAME_MINUTES.get(
        row.timeframe
    )
    if (row.corpus_id != CORPUS_ID or row.instrument not in INSTRUMENTS
            or duration is None or not isinstance(row.bar_start_utc, datetime)
            or row.bar_start_utc.tzinfo is None
            or row.bar_start_utc.utcoffset() != timedelta(0)
            or row.bar_start_utc.second or row.bar_start_utc.microsecond
            or row.bar_end_utc != row.bar_start_utc + timedelta(minutes=duration)
            or not isinstance(row.session_date, str)
            or not isinstance(row.calendar_id, str) or not row.calendar_id
            or not isinstance(row.calendar_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", row.calendar_sha256) is None
            or not isinstance(row.import_id, str)
            or not 1 <= len(row.import_id) <= 128
            or not isinstance(row.research_eligible, bool)):
        raise Hist8ConflictError("bar semantic identity mismatch")
    expected_calendar_id = (
        "BTC_UTC_DAY" if row.instrument == "BTC-USD"
        else "NASDAQ_CASH_RTH" if row.instrument == "NASDAQ"
        else "US_CASH_RTH"
    )
    if (row.calendar_id != expected_calendar_id
            or row.calendar_sha256 != CALENDAR_SCHEDULE_SHA256):
        raise Hist8ConflictError("bar calendar identity mismatch")
    if any(not _postgres_numeric_fits(value) or value <= 0
           for value in (row.open, row.high, row.low, row.close)):
        raise Hist8ConflictError("bar semantic identity mismatch")
    if (row.low > min(row.open, row.close)
            or max(row.open, row.close) > row.high
            or row.volume is not None and (
                not _postgres_numeric_fits(row.volume) or row.volume < 0
            )
            or row.trade_count is not None and (
                type(row.trade_count) is not int
                or not 0 <= row.trade_count <= POSTGRES_BIGINT_MAX
            )
            or row.vwap is not None and (
                not _postgres_numeric_fits(row.vwap) or row.vwap <= 0
            )):
        raise Hist8ConflictError("bar semantic identity mismatch")
    if row.instrument in EQUITIES:
        expected_source = (
            "ALPACA", "SIP", f"{row.instrument}:1Min", "raw", "SHARES",
        )
    elif row.instrument == "BTC-USD":
        expected_source = (
            "COINBASE", "EXCHANGE", "BTC-USD:60", "none", "BTC",
        )
    else:
        expected_source = (
            "MASSIVE", "I:COMP", "I:COMP:minute", "none",
            "NOT_APPLICABLE",
        )
    if ((row.source, row.feed, row.product, row.adjustment, row.volume_unit)
            != expected_source
            or row.price_unit != (
                "INDEX_POINTS" if row.instrument == "NASDAQ" else "USD"
            )
            or row.instrument == "NASDAQ" and row.volume is not None
            or row.instrument != "NASDAQ" and row.volume is None):
        raise Hist8ConflictError("bar source identity mismatch")
    if row.timeframe == "1m":
        if (row.derivation_version is not None
                or not isinstance(row.source_artifact_id, str)
                or re.fullmatch(
                    r"sha256:[0-9a-f]{64}", row.source_artifact_id,
                ) is None
                or not isinstance(row.source_record_locator, str)
                or not row.source_record_locator or row.lineage):
            raise Hist8ConflictError("canonical provenance shape mismatch")
    elif (row.derivation_version != DERIVATION_VERSION
          or row.source_artifact_id is not None
          or row.source_record_locator is not None or not row.lineage
          or any(not isinstance(item, str) or re.fullmatch(
              r"hist8bar:[0-9a-f]{64}\|[0-9a-f]{64}", item,
          ) is None for item in row.lineage)):
        raise Hist8ConflictError("derived provenance shape mismatch")
    try:
        expected_hash = sha256(_content_payload(row))
    except (TypeError, ValueError) as exc:
        raise Hist8ConflictError("bar semantic identity mismatch") from exc
    if (row.content_hash != expected_hash
            or row.bar_id != "hist8bar:" + expected_hash):
        raise Hist8ConflictError("bar semantic identity mismatch")


def _verify_materialized_session(
    rows: Sequence[Bar], *, session_open: datetime,
    session_close: datetime, expected_minutes: int,
    expected_session_date: str, expected_calendar_id: str,
    expected_calendar_sha256: str, source_chain_complete: bool = True,
) -> None:
    if (not rows or type(expected_minutes) is not int or expected_minutes <= 0
            or session_open.tzinfo is None
            or session_open.utcoffset() != timedelta(0)
            or session_open.second or session_open.microsecond
            or session_close != session_open + timedelta(minutes=expected_minutes)
            or not isinstance(expected_session_date, str)
            or not expected_session_date
            or not isinstance(expected_calendar_id, str)
            or not expected_calendar_id
            or type(source_chain_complete) is not bool
            or re.fullmatch(
                r"[0-9a-f]{64}", expected_calendar_sha256,
            ) is None):
        raise Hist8ConflictError("materialized session boundary mismatch")
    for row in rows:
        _validate_bar_identity(row)
    first = rows[0]
    common_identity = (
        first.corpus_id, first.instrument, first.session_date,
        first.calendar_id, first.calendar_sha256, first.volume_unit,
        first.source, first.feed, first.product, first.adjustment,
        first.price_unit,
    )
    if (first.session_date != expected_session_date
            or first.calendar_id != expected_calendar_id
            or first.calendar_sha256 != expected_calendar_sha256):
        raise Hist8ConflictError("materialized calendar identity mismatch")
    if any((
        row.corpus_id, row.instrument, row.session_date,
        row.calendar_id, row.calendar_sha256, row.volume_unit,
        row.source, row.feed, row.product, row.adjustment, row.price_unit,
    ) != common_identity for row in rows):
        raise Hist8ConflictError("materialized session identity mismatch")
    keys = [(row.timeframe, row.bar_start_utc) for row in rows]
    if len(keys) != len(set(keys)):
        raise Hist8ConflictError("duplicate materialized bar identity")
    canonical = {
        row.bar_start_utc: row for row in rows if row.timeframe == "1m"
    }
    expected_starts = tuple(
        session_open + timedelta(minutes=index)
        for index in range(expected_minutes)
    )
    if not set(canonical).issubset(expected_starts):
        raise Hist8ConflictError("canonical session membership mismatch")
    grid_complete = tuple(sorted(canonical)) == expected_starts
    eligible = grid_complete and source_chain_complete
    derived = [row for row in rows if row.timeframe != "1m"]
    if any(row.research_eligible is not eligible for row in canonical.values()):
        raise Hist8ConflictError("canonical eligibility mismatch")
    if not eligible:
        if derived:
            raise Hist8ConflictError("incomplete session has derived bars")
        return
    if any(not row.research_eligible for row in derived):
        raise Hist8ConflictError("derived eligibility mismatch")
    for timeframe, width in TIMEFRAME_MINUTES.items():
        actual = {
            row.bar_start_utc: row for row in derived
            if row.timeframe == timeframe
        }
        expected_derived_starts = tuple(
            session_open + timedelta(minutes=index)
            for index in range(0, expected_minutes - width + 1, width)
        )
        if tuple(sorted(actual)) != expected_derived_starts:
            raise Hist8ConflictError("derived window membership mismatch")
        for start in expected_derived_starts:
            row = actual[start]
            inputs = tuple(
                canonical[start + timedelta(minutes=index)]
                for index in range(width)
            )
            expected_lineage = tuple(
                f"{item.bar_id}|{item.content_hash}" for item in inputs
            )
            expected_volume = (
                None if first.instrument == "NASDAQ"
                else _exact_decimal_sum(tuple(
                    item.volume for item in inputs if item.volume is not None
                ))
            )
            if (expected_volume is not None
                    and not _postgres_numeric_fits(expected_volume)):
                raise Hist8ConflictError("derived aggregation mismatch")
            expected_trade_count = None
            if not any(item.trade_count is None for item in inputs):
                expected_trade_count = sum(
                    item.trade_count or 0 for item in inputs
                )
                if expected_trade_count > POSTGRES_BIGINT_MAX:
                    raise Hist8ConflictError("derived aggregation mismatch")
            if (row.lineage != expected_lineage
                    or row.open != inputs[0].open
                    or row.high != max(item.high for item in inputs)
                    or row.low != min(item.low for item in inputs)
                    or row.close != inputs[-1].close
                    or row.volume != expected_volume
                    or row.trade_count != expected_trade_count
                    or row.vwap is not None):
                raise Hist8ConflictError("derived aggregation mismatch")


def _source_bar_from_canonical(row: Bar) -> SourceBar:
    if (row.timeframe != "1m" or row.bar_end_utc - row.bar_start_utc
            != timedelta(minutes=1)
            or not isinstance(row.source_artifact_id, str)
            or not isinstance(row.source_record_locator, str)):
        raise Hist8ConflictError("canonical provenance shape mismatch")
    return SourceBar(
        row.instrument, row.bar_start_utc, row.open, row.high, row.low,
        row.close, row.volume, row.trade_count, row.vwap,
        row.source_artifact_id, row.source_record_locator, row.source,
        row.feed, row.product, row.adjustment, row.volume_unit,
    )


def _validate_source_bar(row: SourceBar) -> None:
    if (not isinstance(row, SourceBar)
            or not isinstance(row.start, datetime)
            or row.start.tzinfo is None or row.start.utcoffset() != timedelta(0)
            or row.start.second or row.start.microsecond):
        raise Hist8Error("bar timestamp is not UTC-minute aligned")
    if any(not _postgres_numeric_fits(value) or value <= 0 for value in
           (row.open, row.high, row.low, row.close)):
        raise Hist8Error("invalid OHLC")
    if row.low > min(row.open, row.close) or max(row.open, row.close) > row.high:
        raise Hist8Error("invalid OHLC ordering")
    if (row.volume is not None
            and (not _postgres_numeric_fits(row.volume) or row.volume < 0)):
        raise Hist8Error("invalid volume")
    if (row.trade_count is not None
            and (type(row.trade_count) is not int
                 or not 0 <= row.trade_count <= POSTGRES_BIGINT_MAX)):
        raise Hist8Error("invalid trade count")
    if (row.vwap is not None
            and (not _postgres_numeric_fits(row.vwap) or row.vwap <= 0)):
        raise Hist8Error("invalid vwap")
    if row.instrument == "NASDAQ" and row.volume is not None:
        raise Hist8Error("NASDAQ volume must be null")
    if row.instrument != "NASDAQ" and row.volume is None:
        raise Hist8Error("volume is required")
    if row.instrument in EQUITIES:
        expected_identity = (
            "ALPACA", "SIP", f"{row.instrument}:1Min", "raw", "SHARES",
        )
    elif row.instrument == "BTC-USD":
        expected_identity = (
            "COINBASE", "EXCHANGE", "BTC-USD:60", "none", "BTC",
        )
        if row.trade_count is not None or row.vwap is not None:
            raise Hist8Error("BTC-USD trade count and vwap must be null")
    elif row.instrument == "NASDAQ":
        expected_identity = (
            "MASSIVE", "I:COMP", "I:COMP:minute", "none",
            "NOT_APPLICABLE",
        )
        if row.trade_count is not None or row.vwap is not None:
            raise Hist8Error("NASDAQ trade count and vwap must be null")
    else:
        raise Hist8Error("unauthorized instrument")
    if (row.source, row.feed, row.product, row.adjustment, row.volume_unit
            ) != expected_identity:
        raise Hist8Error("provider source identity mismatch")


def _source_bar_payload(row: SourceBar) -> tuple[object, ...]:
    """Compare provider semantics without storage-page lineage."""
    return (
        row.instrument, row.start, row.open, row.high, row.low, row.close,
        row.volume, row.trade_count, row.vwap, row.source, row.feed,
        row.product, row.adjustment, row.volume_unit,
    )


def _parse_or_reject_source_row(
    factory: Callable[[], SourceBar], rejection_counter: list[int] | None,
) -> SourceBar | None:
    try:
        row = factory()
        _validate_source_bar(row)
        return row
    except Hist8Error:
        if rejection_counter is None:
            raise
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, OSError) as exc:
        if rejection_counter is None:
            raise Hist8Error("malformed provider bar") from exc
    assert rejection_counter is not None
    rejection_counter[0] += 1
    return None


def parse_source_page(
    page: RawPage, instrument: str, *, rejection_counter: list[int] | None = None,
) -> tuple[SourceBar, ...]:
    _validate_page_identity(page, instrument)
    artifact = _artifact_id(page.body)
    payload = page.payload()
    rows: list[SourceBar] = []
    if page.source == "ALPACA":
        if not isinstance(payload, Mapping):
            raise Hist8Error("malformed Alpaca page")
        bars = payload.get("bars")
        if not isinstance(bars, Mapping):
            raise Hist8Error("malformed Alpaca page")
        source_rows = bars.get(instrument, [])
        if not isinstance(source_rows, list):
            raise Hist8Error("malformed Alpaca page")
        for index, item in enumerate(source_rows):
            def alpaca_row() -> SourceBar:
                if not isinstance(item, Mapping):
                    raise Hist8Error("malformed Alpaca bar")
                return SourceBar(
                    instrument, _iso_utc(item["t"]), _decimal(item["o"]),
                    _decimal(item["h"]), _decimal(item["l"]),
                    _decimal(item["c"]), _decimal(item["v"]),
                    None if item.get("n") is None else _integer(
                        item["n"], name="Alpaca trade count"
                    ),
                    _decimal(item.get("vw"), nullable=True), artifact,
                    f"$.bars.{instrument}[{index}]", "ALPACA", "SIP",
                    f"{instrument}:1Min", "raw", "SHARES",
                )
            row = _parse_or_reject_source_row(alpaca_row, rejection_counter)
            if row is not None:
                rows.append(row)
    elif page.source == "COINBASE":
        if not isinstance(payload, list):
            raise Hist8Error("malformed Coinbase page")
        for index, item in enumerate(payload):
            def coinbase_row() -> SourceBar:
                if not isinstance(item, list) or len(item) < 6:
                    raise Hist8Error("malformed Coinbase candle")
                timestamp = _integer(item[0], name="Coinbase timestamp")
                start = datetime.fromtimestamp(timestamp, timezone.utc)
                return SourceBar(
                    instrument, start, _decimal(item[3]), _decimal(item[2]),
                    _decimal(item[1]), _decimal(item[4]), _decimal(item[5]),
                    None, None, artifact, f"$[{index}]", "COINBASE",
                    "EXCHANGE", "BTC-USD:60", "none", "BTC",
                )
            row = _parse_or_reject_source_row(coinbase_row, rejection_counter)
            if row is not None:
                rows.append(row)
    elif page.source == "MASSIVE":
        if not isinstance(payload, Mapping):
            raise Hist8Error("malformed Massive page")
        if payload.get("ticker") != "I:COMP":
            raise Hist8Error("Massive ticker identity mismatch")
        if payload.get("status") != "OK":
            raise Hist8Error("Massive response status mismatch")
        source_rows = payload.get("results", [])
        if not isinstance(source_rows, list):
            raise Hist8Error("malformed Massive page")
        for index, item in enumerate(source_rows):
            def massive_row() -> SourceBar:
                if not isinstance(item, Mapping):
                    raise Hist8Error("malformed Massive bar")
                milliseconds = _integer(item["t"], name="Massive timestamp")
                if milliseconds % 1000:
                    raise Hist8Error("Massive timestamp is not second aligned")
                start = datetime.fromtimestamp(
                    milliseconds // 1000, timezone.utc,
                )
                return SourceBar(
                    instrument, start, _decimal(item["o"]),
                    _decimal(item["h"]), _decimal(item["l"]),
                    _decimal(item["c"]), None, None, None, artifact,
                    f"$.results[{index}]", "MASSIVE", "I:COMP",
                    "I:COMP:minute", "none", "NOT_APPLICABLE",
                )
            row = _parse_or_reject_source_row(massive_row, rejection_counter)
            if row is not None:
                rows.append(row)
    else:
        raise Hist8Error("unknown source")
    rows.sort(key=lambda row: row.start)
    return tuple(rows)


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
    if not _postgres_numeric_fields_fit(row):
        raise Hist8Error("provider decimal exceeds PostgreSQL numeric capacity")
    bar = Bar(
        "", "", CORPUS_ID, row.instrument, "1m", row.start,
        row.start + timedelta(minutes=1), session_date,
        calendar_id or (
            "BTC_UTC_DAY" if row.instrument == "BTC-USD"
            else "NASDAQ_CASH_RTH" if row.instrument == "NASDAQ"
            else "US_CASH_RTH"
        ),
        calendar_hash, row.open, row.high, row.low, row.close, row.volume,
        row.trade_count, row.vwap, row.volume_unit, row.source, row.feed,
        row.product, row.adjustment,
        "INDEX_POINTS" if row.instrument == "NASDAQ" else "USD",
        import_id, None, row.artifact_id,
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
    if any(not _postgres_numeric_fields_fit(row) for row in minutes):
        raise Hist8ConflictError("bar decimal exceeds PostgreSQL numeric capacity")
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
        if volume is not None and not _postgres_numeric_fits(volume):
            raise Hist8Error(
                "derived volume exceeds PostgreSQL numeric capacity"
            )
        trade_count = None
        if not any(item.trade_count is None for item in window):
            trade_count = sum(item.trade_count or 0 for item in window)
            if trade_count > POSTGRES_BIGINT_MAX:
                raise Hist8Error(
                    "derived trade count exceeds PostgreSQL bigint"
                )
        bar = Bar(
            "", "", CORPUS_ID, first.instrument, timeframe,
            first.bar_start_utc, last.bar_end_utc, first.session_date,
            first.calendar_id, first.calendar_sha256, first.open,
            max(item.high for item in window), min(item.low for item in window),
            last.close, volume, trade_count, None, first.volume_unit,
            first.source, first.feed, first.product, first.adjustment,
            first.price_unit,
            import_id, DERIVATION_VERSION, None, None,
            tuple(f"{item.bar_id}|{item.content_hash}" for item in window), True,
        )
        output.append(_finish_bar(bar))
    return tuple(output)


def materialize_instrument(
    store: Hist8Store, source_import_id: str, instrument: str,
    calendar: Mapping[str, object], *, attempt_id: str | None = None,
    source_unavailable: bool = False,
) -> dict[str, object]:
    if type(source_unavailable) is not bool:
        raise Hist8Error("source availability flag is invalid")
    unavailable_prefix_count = (
        _verify_unavailable_page_prefix(
            store.retrieval_pages(source_import_id, instrument), instrument,
        )
        if source_unavailable else None
    )
    write_attempt_id = attempt_id or source_import_id
    definitions = _session_definitions(calendar, instrument)
    rejected = duplicates = 0
    inserted = idempotent = eligible_sessions = incomplete_sessions = 0
    source_acquisition_incomplete_sessions = 0
    observed_minutes = missing_minutes = 0
    verified_retrieval_associations = 0
    usable_retrieval_associations = 0
    excluded_windows = {timeframe: 0 for timeframe in TIMEFRAMES[1:]}
    source_excluded_windows = {timeframe: 0 for timeframe in TIMEFRAMES[1:]}
    residual_tails = {timeframe: 0 for timeframe in TIMEFRAMES[1:]}
    seen_sessions: set[str] = set()
    calendar_hash = str(calendar["schedule_sha256"])
    calendar_id = str(calendar["instrument_calendars"][instrument])
    expected_request = _first_page_request(instrument)
    seen_requests: set[tuple[str, tuple[tuple[str, str], ...]]] = set()

    def flush_session(session_date: str, unique: Mapping[datetime, SourceBar]) -> None:
        nonlocal inserted, idempotent, eligible_sessions, incomplete_sessions
        nonlocal source_acquisition_incomplete_sessions
        nonlocal observed_minutes, missing_minutes
        opened, closed, expected = definitions[session_date]
        expected_times = {opened + timedelta(minutes=index) for index in range(expected)}
        grid_complete = (
            set(unique) == expected_times
            and closed == opened + timedelta(minutes=expected)
        )
        eligible = grid_complete and not source_unavailable
        seen_sessions.add(session_date)
        observed_minutes += len(unique)
        missing_minutes += len(expected_times - set(unique))
        if eligible:
            eligible_sessions += 1
        elif not grid_complete:
            incomplete_sessions += 1
        else:
            source_acquisition_incomplete_sessions += 1
        if not eligible:
            for timeframe, width in TIMEFRAME_MINUTES.items():
                excluded_windows[timeframe] += expected // width
                if grid_complete:
                    source_excluded_windows[timeframe] += expected // width
        for timeframe, width in TIMEFRAME_MINUTES.items():
            residual_tails[timeframe] += expected % width
        canonical = tuple(canonical_bar(
            unique[start], session_date=session_date, calendar_hash=calendar_hash,
            import_id=write_attempt_id, eligible=eligible, calendar_id=calendar_id,
        ) for start in sorted(unique))
        all_rows: list[Bar] = list(canonical)
        if eligible:
            for timeframe in TIMEFRAMES[1:]:
                all_rows.extend(derive_session(
                    canonical, timeframe, write_attempt_id, session_open=opened,
                ))
        added, same = store.insert_bars(
            all_rows, session_open=opened, session_close=closed,
            expected_minutes=expected,
            expected_session_date=session_date,
            expected_calendar_id=calendar_id,
            expected_calendar_sha256=calendar_hash,
            source_chain_complete=not source_unavailable,
        )
        inserted += added
        idempotent += same

    current_session: str | None = None
    current_rows: dict[datetime, SourceBar] = {}
    terminal_failure = False
    for page in store.retrieval_pages(source_import_id, instrument):
        verified_retrieval_associations += 1
        request_identity = (
            page.endpoint, tuple(sorted(dict(page.request_params).items())),
        )
        if (terminal_failure
                or (page.endpoint, dict(page.request_params)) != expected_request
                or request_identity in seen_requests):
            raise Hist8ConflictError("retained provider pagination mismatch")
        seen_requests.add(request_identity)
        if page.http_status != 200:
            if not source_unavailable:
                raise Hist8Error(f"stored provider failure {page.http_status}")
            terminal_failure = True
            continue
        invalid = [0]
        try:
            parsed_rows = parse_source_page(
                page, instrument, rejection_counter=invalid,
            )
        except Hist8ConflictError:
            raise
        except Hist8Error:
            if not source_unavailable:
                raise
            terminal_failure = True
            continue
        usable_retrieval_associations += 1
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
                stored = store.stored_canonical_source_bar(
                    instrument, session, row.start,
                )
                if _source_bar_payload(stored) != _source_bar_payload(row):
                    store.record_source_bar_conflict(
                        import_id=write_attempt_id, session_date=session,
                        calendar_id=calendar_id,
                        calendar_sha256=calendar_hash,
                        existing=stored, candidate=row,
                    )
                    raise Hist8ConflictError(
                        "conflicting duplicate provider bar after session flush"
                    )
                duplicates += 1
                continue
            if current_session is not None and session != current_session:
                flush_session(current_session, current_rows)
                current_rows = {}
            current_session = session
            prior = current_rows.get(row.start)
            if prior is not None:
                if _source_bar_payload(prior) != _source_bar_payload(row):
                    store.record_source_bar_conflict(
                        import_id=write_attempt_id, session_date=session,
                        calendar_id=calendar_id,
                        calendar_sha256=calendar_hash,
                        existing=prior, candidate=row,
                    )
                    raise Hist8ConflictError("conflicting duplicate provider bar")
                duplicates += 1
                continue
            current_rows[row.start] = row
        try:
            expected_request = _next_page_request(page, instrument)
        except Hist8ConflictError:
            raise
        except Hist8Error:
            if not source_unavailable:
                raise
            terminal_failure = True
    chain_complete = expected_request is None and not terminal_failure
    if source_unavailable and chain_complete:
        raise Hist8ConflictError(
            "unavailable retained provider pagination is complete"
        )
    if not source_unavailable and not chain_complete:
        raise Hist8ConflictError("retained provider pagination incomplete")
    if (unavailable_prefix_count is not None
            and verified_retrieval_associations != unavailable_prefix_count):
        raise Hist8ConflictError("retained provider prefix changed during replay")
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
        "verified_retrieval_associations": verified_retrieval_associations,
        "usable_retrieval_associations": usable_retrieval_associations,
        "source_chain_complete": chain_complete,
        "source_acquisition_incomplete_sessions": (
            source_acquisition_incomplete_sessions
        ),
    }
    for timeframe in TIMEFRAMES[1:]:
        result[f"excluded_{timeframe}_windows"] = excluded_windows[timeframe]
        result[f"source_excluded_{timeframe}_windows"] = (
            source_excluded_windows[timeframe]
        )
        result[f"residual_{timeframe}_tail_minutes"] = residual_tails[timeframe]
    return result


def _verify_unavailable_page_prefix(
    pages: Iterator[RawPage], instrument: str,
) -> int:
    expected_request = _first_page_request(instrument)
    seen_requests: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    terminal_failure = False
    count = 0
    for page in pages:
        request_identity = (
            page.endpoint, tuple(sorted(dict(page.request_params).items())),
        )
        if (terminal_failure
                or (page.endpoint, dict(page.request_params)) != expected_request
                or request_identity in seen_requests):
            raise Hist8ConflictError("retained provider pagination mismatch")
        seen_requests.add(request_identity)
        count += 1
        if page.http_status != 200:
            terminal_failure = True
            continue
        try:
            _validate_provider_page_envelope(page)
            next_request = _next_page_request(page, instrument)
        except Hist8ConflictError:
            raise
        except Hist8Error:
            # The acquisition commits each response before adapter validation.
            # A malformed successful response is valid terminal failure evidence.
            terminal_failure = True
            continue
        if next_request is None:
            raise Hist8ConflictError(
                "unavailable retained provider pagination is complete"
            )
        expected_request = next_request
    return count


def _validated_source_statuses(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, Mapping) or set(value) != set(INSTRUMENTS):
        raise Hist8Error("instrument source statuses missing or invalid")
    validated: dict[str, dict[str, object]] = {}
    for instrument in INSTRUMENTS:
        status = value[instrument]
        if not isinstance(status, Mapping):
            raise Hist8Error("instrument source status is invalid")
        availability = status.get("availability")
        expected_keys = {"source", "availability", "retrieval_associations"}
        if availability == "UNAVAILABLE":
            expected_keys.update(("failure_type", "reason"))
        count = status.get("retrieval_associations")
        if (set(status) != expected_keys
                or status.get("source") != INSTRUMENT_SOURCE[instrument]
                or availability not in ("AVAILABLE", "UNAVAILABLE")
                or type(count) is not int or count < 0):
            raise Hist8Error("instrument source status is invalid")
        if availability == "UNAVAILABLE" and (
            not isinstance(status.get("failure_type"), str)
            or not status["failure_type"]
            or not isinstance(status.get("reason"), str)
            or not status["reason"]
        ):
            raise Hist8Error("instrument source status is invalid")
        validated[instrument] = dict(status)
    return validated


def _provider_failure(exc: BaseException) -> dict[str, str]:
    reason = str(exc) if isinstance(exc, Hist8Error) else "provider transport unavailable"
    reason = " ".join(reason.split())[:256] or "provider unavailable"
    return {"failure_type": type(exc).__name__, "reason": reason}


def acquire(store: Hist8Store, import_id: str) -> dict[str, object]:
    sequence = 1
    statuses: dict[str, dict[str, object]] = {}
    sources: tuple[
        tuple[str, tuple[str, ...], Callable[[], Iterator[RawPage]]], ...
    ] = (
        ("ALPACA", EQUITIES, lambda: alpaca_pages(
            os.environ.get("ALPACA_API_KEY", ""),
            os.environ.get("ALPACA_API_SECRET", ""),
        )),
        ("COINBASE", ("BTC-USD",), coinbase_pages),
        ("MASSIVE", ("NASDAQ",), lambda: massive_pages(
            os.environ.get("MASSIVE_API_KEY", ""),
        )),
    )
    for source, instruments, page_factory in sources:
        association_counts = {instrument: 0 for instrument in instruments}
        failure: BaseException | None = None
        try:
            pages = iter(page_factory())
        except (Hist8Error, OSError) as exc:
            failure = exc
        else:
            while True:
                try:
                    page = next(pages)
                except StopIteration:
                    break
                except (Hist8Error, OSError) as exc:
                    failure = exc
                    break
                if (page.source != source
                        or tuple(page.instruments) != instruments):
                    failure = Hist8Error("provider source identity mismatch")
                    break
                # Storage/integrity errors are deliberately outside the provider
                # exception handlers and remain fatal to the whole attempt.
                sequence = store.store_page(import_id, sequence, page)
                for instrument in page.instruments:
                    association_counts[instrument] += 1
        for instrument in instruments:
            status: dict[str, object] = {
                "source": source,
                "availability": "AVAILABLE" if failure is None else "UNAVAILABLE",
                "retrieval_associations": association_counts[instrument],
            }
            if failure is not None:
                status.update(_provider_failure(failure))
            statuses[instrument] = status
    return {
        "retrieval_associations": sequence - 1,
        "source_statuses": _validated_source_statuses(statuses),
    }


def _unavailable_instrument_result(
    calendar: Mapping[str, object], instrument: str,
) -> dict[str, int]:
    definitions = _session_definitions(calendar, instrument)
    expected_minutes = sum(row[2] for row in definitions.values())
    result = {
        "inserted": 0, "idempotent": 0, "provider_duplicates": 0,
        "rejected": 0, "expected_minutes": expected_minutes,
        "observed_minutes": 0, "missing_minutes": expected_minutes,
        "eligible_sessions": 0, "incomplete_sessions": len(definitions),
    }
    for timeframe, width in TIMEFRAME_MINUTES.items():
        result[f"excluded_{timeframe}_windows"] = sum(
            row[2] // width for row in definitions.values()
        )
        result[f"residual_{timeframe}_tail_minutes"] = sum(
            row[2] % width for row in definitions.values()
        )
    return result


def execute(
    import_id: str | None = None, *, expected_implementation_commit: str,
    acquire_sources: bool = True,
) -> dict[str, object]:
    chosen = import_id or f"hist8-{uuid.uuid4()}"
    if len(chosen) > 128:
        raise Hist8Error("import id too long")
    code_identity = _execution_code_identity()
    _require_reviewed_implementation(
        code_identity, expected_implementation_commit,
    )
    try:
        calendar_artifact = code_identity["files"][
            "research/hist8/calendar_manifest.json"
        ]
        expected_calendar_file_sha256 = calendar_artifact["sha256"]
    except (KeyError, TypeError) as exc:
        raise Hist8Error("calendar artifact identity mismatch") from exc
    if not isinstance(expected_calendar_file_sha256, str):
        raise Hist8Error("calendar artifact identity mismatch")
    calendar = load_calendar(
        expected_file_sha256=expected_calendar_file_sha256,
    )
    store = Hist8Store.from_environment()
    kind = "IMPORT_ATTEMPT" if acquire_sources else "REPLAY_ATTEMPT"
    source_snapshot = (
        None if acquire_sources else store.sealed_snapshot_state(chosen)
    )
    source_membership = (
        None if source_snapshot is None
        else str(source_snapshot["membership_sha256"])
    )
    source_snapshot_manifest_id = (
        None if source_snapshot is None else str(source_snapshot["manifest_id"])
    )
    if (source_snapshot is not None
            and _canonical(source_snapshot["metadata"].get("code_identity"))
            != _canonical(code_identity)):
        raise Hist8ConflictError(
            "replay execution code identity differs from source snapshot"
        )
    source_statuses = (
        None if source_snapshot is None else _validated_source_statuses(
            source_snapshot["metadata"].get("source_statuses")
        )
    )
    attempt_id = chosen if acquire_sources else f"hist8-replay-{uuid.uuid4()}"
    store.add_attempt(attempt_id, kind, {
        "authorization": "ATOM-HIST8-CORPUS-AMENDMENT-1",
        "source_import_id": chosen,
        "project_ref": PROJECT_REF, "database": DATABASE_NAME,
        "schema": "atom_research_history", "calendar_sha256": calendar["schedule_sha256"],
        "code_identity": code_identity,
        "partitions": PARTITIONS,
        "expected_membership_sha256": source_membership,
        "source_snapshot_manifest_id": source_snapshot_manifest_id,
    })
    if acquire_sources:
        acquisition = acquire(store, chosen)
        retrieval_associations = int(acquisition["retrieval_associations"])
        source_statuses = _validated_source_statuses(
            acquisition["source_statuses"]
        )
    else:
        retrieval_associations = 0
    assert source_statuses is not None
    results: dict[str, dict[str, object]] = {}
    for instrument in INSTRUMENTS:
        source_status = source_statuses[instrument]
        metrics: dict[str, object] = materialize_instrument(
            store, chosen, instrument, calendar, attempt_id=attempt_id,
            source_unavailable=source_status["availability"] == "UNAVAILABLE",
        )
        if (metrics.get("verified_retrieval_associations")
                != source_status["retrieval_associations"]):
            raise Hist8ConflictError(
                "retrieval association count differs from sealed source status"
            )
        results[instrument] = {**source_status, **metrics}
    membership = store.seal_snapshot(attempt_id, {
        "attempt_kind": kind, "retrieval_associations": retrieval_associations,
        "source_import_id": chosen,
        "source_snapshot_manifest_id": source_snapshot_manifest_id,
        "code_identity": code_identity,
        "source_statuses": source_statuses,
        "instrument_results": results,
    }, expected_membership_sha256=source_membership)
    return {"source_import_id": chosen, "attempt_id": attempt_id,
            "membership_sha256": membership,
            "source_statuses": source_statuses, "instrument_results": results}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "replay"))
    parser.add_argument("--import-id")
    parser.add_argument("--implementation-commit", required=True)
    args = parser.parse_args(argv)
    if args.command == "replay" and not args.import_id:
        parser.error("replay requires --import-id")
    result = execute(
        args.import_id,
        expected_implementation_commit=args.implementation_commit,
        acquire_sources=args.command == "run",
    )
    print(json.dumps(_canonical(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALPACA_URL", "CALENDAR_VERSION", "CORPUS_ID", "DATABASE_HOST",
    "DATABASE_NAME", "DERIVATION_VERSION", "END", "EQUITIES", "Hist8Error",
    "Hist8ConflictError", "Hist8Store", "IMPORTER_ROLE", "INSTRUMENTS",
    "MASSIVE_URL", "PARTITIONS", "PROJECT_REF", "RawPage",
    "START", "SourceBar", "TIMEFRAMES",
    "alpaca_pages", "canonical_bar", "canonical_bytes", "coinbase_pages",
    "derive_session", "execute", "install_schema", "load_calendar", "massive_pages",
    "materialize_instrument", "parse_source_page", "sha256",
]
