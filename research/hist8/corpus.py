"""Bounded offline HIST8 acquisition, validation, derivation, and persistence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Iterator, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
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
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class Hist8Error(RuntimeError):
    pass


class Hist8ConflictError(Hist8Error):
    pass


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
        normalized = value.normalize()
        text = format(normalized, "f")
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


def _http_get(
    url: str, *, headers: Mapping[str, str], timeout: int = 30,
    opener: Callable[..., object] = urlopen,
) -> tuple[int, Mapping[str, str], bytes]:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        response = opener(request, timeout=timeout)
        with response:
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
    key: str, secret: str, *, opener: Callable[..., object] = urlopen,
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
    *, opener: Callable[..., object] = urlopen,
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
    if parsed.scheme != "https" or parsed.hostname != "api.massive.com":
        raise Hist8Error("Massive pagination origin mismatch")
    safe = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() != "apikey"]
    endpoint = urlunparse(parsed._replace(query=""))
    return endpoint, dict(safe)


def massive_pages(
    key: str, *, opener: Callable[..., object] = urlopen,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> Iterator[RawPage]:
    if not key:
        raise Hist8Error("Massive credential missing")
    endpoint = MASSIVE_URL
    params = {"adjusted": "false", "sort": "asc", "limit": "50000"}
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


class Hist8Store:
    def __init__(self, connection_factory: Callable[[], object]) -> None:
        self._connection_factory = connection_factory

    @classmethod
    def from_environment(cls) -> "Hist8Store":
        dsn = os.environ.get(IMPORT_DATABASE_ENV, "")
        parsed = urlparse(dsn)
        if (parsed.scheme not in ("postgres", "postgresql")
                or parsed.hostname != DATABASE_HOST
                or parsed.username != IMPORTER_ROLE
                or parsed.path != f"/{DATABASE_NAME}"):
            raise Hist8Error("HIST8 importer credential/project mismatch")
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
                    cursor.execute(
                        """insert into atom_research_history.manifests
                        (manifest_id, corpus_id, manifest_kind, import_id, sequence_no,
                         source, feed, product, instrument, endpoint, request_params,
                         retrieved_at, http_status, content_type, content_encoding,
                         artifact_id, artifact_byte_length, metadata_json)
                        values (%s,%s,'RETRIEVAL',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb)
                        on conflict (manifest_id) do nothing""",
                        (_manifest_id(payload), CORPUS_ID, import_id, number,
                         page.source, page.feed, page.product, instrument,
                         page.endpoint, json.dumps(dict(page.request_params)),
                         page.retrieved_at, page.http_status, page.content_type,
                         page.content_encoding, artifact_id, len(page.body)),
                    )
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

    def insert_bars(self, rows: Sequence[Bar]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        keys = [(row.corpus_id, row.instrument, row.timeframe, row.bar_start_utc)
                for row in rows]
        if len(keys) != len(set(keys)):
            raise Hist8ConflictError("duplicate generated bar identity")
        inserted = 0
        with self._connection_factory() as connection:
            self._verify(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """select timeframe,bar_start_utc,content_hash from atom_research_history.bars
                    where corpus_id=%s and instrument=%s and session_date=%s""",
                    (CORPUS_ID, rows[0].instrument, rows[0].session_date),
                )
                existing = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
                pending = []
                for row in rows:
                    key = (row.timeframe, row.bar_start_utc)
                    if key in existing:
                        if existing[key] != row.content_hash:
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
                         source_artifact_id,source_record_locator,lineage_json,research_eligible)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        on conflict do nothing""", [_bar_values(row) for row in pending],
                    )
                    inserted = len(pending)
                cursor.execute(
                    """select timeframe,bar_start_utc,content_hash from atom_research_history.bars
                    where corpus_id=%s and instrument=%s and session_date=%s""",
                    (CORPUS_ID, rows[0].instrument, rows[0].session_date),
                )
                verified = {(r[0], r[1]): r[2] for r in cursor.fetchall()}
                for row in rows:
                    if verified.get((row.timeframe, row.bar_start_utc)) != row.content_hash:
                        raise Hist8ConflictError("bar readback mismatch")
        return inserted, len(rows) - inserted

    def seal_snapshot(self, import_id: str, metadata: Mapping[str, object]) -> str:
        digest = hashlib.sha256()
        counts: dict[str, int] = {}
        connection = self._connection_factory()
        self._verify(connection)
        try:
            with connection.cursor(name="hist8_snapshot") as cursor:
                cursor.execute(
                    """select instrument,timeframe,bar_id,content_hash,research_eligible
                    from atom_research_history.bars where corpus_id=%s
                    order by instrument,timeframe,bar_start_utc""", (CORPUS_ID,),
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
        values["research_eligible"],
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
                _decimal(item["v"]), None if item.get("n") is None else int(item["n"]),
                _decimal(item.get("vw"), nullable=True), artifact,
                f"$.bars.{instrument}[{index}]", "ALPACA", "SIP",
                f"{instrument}:1Min", "raw", "SHARES",
            ))
    elif page.source == "COINBASE":
        for index, item in enumerate(payload):
            if not isinstance(item, list) or len(item) < 6:
                raise Hist8Error("malformed Coinbase candle")
            start = datetime.fromtimestamp(int(item[0]), timezone.utc)
            rows.append(SourceBar(
                instrument, start, _decimal(item[3]), _decimal(item[2]),
                _decimal(item[1]), _decimal(item[4]), _decimal(item[5]), None,
                None, artifact, f"$[{index}]", "COINBASE", "EXCHANGE",
                "BTC-USD:60", "none", "BTC",
            ))
    elif page.source == "MASSIVE":
        for index, item in enumerate(payload.get("results", [])):
            start = datetime.fromtimestamp(int(item["t"]) / 1000, timezone.utc)
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
    if row.instrument == "BTC-USD":
        key = row.start.date().isoformat()
    else:
        candidates = (row.start.date(), (row.start - timedelta(hours=5)).date())
        key = next((item.isoformat() for item in candidates
                    if item.isoformat() in definitions), "")
    bounds = definitions.get(key)
    return key if bounds and bounds[0] <= row.start < bounds[1] else None


def _content_payload(row: Bar) -> dict[str, object]:
    payload = asdict(row)
    for key in ("bar_id", "content_hash", "import_id"):
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


def derive_session(minutes: Sequence[Bar], timeframe: str, import_id: str) -> tuple[Bar, ...]:
    width = TIMEFRAME_MINUTES[timeframe]
    if not minutes or any(row.timeframe != "1m" or not row.research_eligible
                          for row in minutes):
        return ()
    output: list[Bar] = []
    for offset in range(0, len(minutes) - width + 1, width):
        window = minutes[offset:offset + width]
        if len(window) != width or any(
            following.bar_start_utc - previous.bar_start_utc != timedelta(minutes=1)
            for previous, following in zip(window, window[1:])
        ):
            continue
        first, last = window[0], window[-1]
        volume = None if first.instrument == "NASDAQ" else sum(
            (item.volume for item in window if item.volume is not None), Decimal(0)
        )
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
                all_rows.extend(derive_session(canonical, timeframe, write_attempt_id))
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
    attempt_id = chosen if acquire_sources else f"hist8-replay-{uuid.uuid4()}"
    store.add_attempt(attempt_id, kind, {
        "authorization": "ATOM-HIST8-CORPUS-AMENDMENT-1",
        "source_import_id": chosen,
        "project_ref": PROJECT_REF, "database": DATABASE_NAME,
        "schema": "atom_research_history", "calendar_sha256": calendar["schedule_sha256"],
        "partitions": PARTITIONS,
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
    return {"source_import_id": chosen, "attempt_id": attempt_id,
            "membership_sha256": membership,
            "instrument_results": results}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "replay"))
    parser.add_argument("--import-id")
    args = parser.parse_args(argv)
    if args.command == "replay" and not args.import_id:
        parser.error("replay requires --import-id")
    result = execute(args.import_id, acquire_sources=args.command == "run")
    print(json.dumps(_canonical(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALPACA_URL", "CALENDAR_VERSION", "CORPUS_ID", "DATABASE_HOST",
    "DATABASE_NAME", "DERIVATION_VERSION", "END", "EQUITIES", "Hist8Error",
    "Hist8ConflictError", "Hist8Store", "IMPORTER_ROLE", "INSTRUMENTS",
    "MASSIVE_URL", "PARTITIONS", "PROJECT_REF", "RawPage", "START", "SourceBar", "TIMEFRAMES",
    "alpaca_pages", "canonical_bar", "canonical_bytes", "coinbase_pages",
    "derive_session", "execute", "load_calendar", "massive_pages",
    "materialize_instrument", "parse_source_page", "sha256",
]
