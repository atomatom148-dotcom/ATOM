from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
from http.client import IncompleteRead
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from research.hist8 import corpus


UTC = timezone.utc


def _source_bar(start: datetime, *, artifact: str = "sha256:" + "a" * 64) -> corpus.SourceBar:
    return corpus.SourceBar(
        "SPY", start, Decimal("100"), Decimal("103"), Decimal("99"),
        Decimal("102"), Decimal("10"), 2, Decimal("101"), artifact,
        "$[0]", "ALPACA", "SIP", "SPY:1Min", "raw", "SHARES",
    )


def _raw_page(body: object, *, source: str = "ALPACA", instruments=("SPY",)) -> corpus.RawPage:
    return corpus.RawPage(
        source, "SIP", "1Min", instruments, "https://example.invalid",
        {}, datetime(2026, 9, 2, tzinfo=UTC), 200, "application/json", None,
        json.dumps(body, separators=(",", ":")).encode(),
    )


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload, separators=(",", ":")).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self._body


def test_calendar_is_complete_and_hash_bound() -> None:
    manifest = corpus.load_calendar()
    assert len(manifest["us_cash_sessions"]) == 500
    assert len(manifest["btc_utc_dates"]) == 730
    assert manifest["schedule_sha256"] == (
        "74463f0a85b14361599d9abf0caa0f3cbce12c79e10a15c37ffcd58348f3d446"
    )
    sessions = {row["date"]: row for row in manifest["us_cash_sessions"]}
    assert "2025-01-09" not in sessions
    assert sessions["2024-11-29"]["expected_minutes"] == 210
    assert sessions["2026-07-02"]["expected_minutes"] == 390
    tampered = dict(manifest)
    tampered["timezone_database_version"] = "different tzdb"
    assert corpus.sha256({
        key: tampered[key] for key in tampered if key != "schedule_sha256"
    }) != manifest["schedule_sha256"]


def test_alpaca_request_is_sip_raw_and_bounded() -> None:
    requests = []

    def opener(request, *, timeout):
        requests.append((request, timeout))
        return _Response({"bars": {symbol: [] for symbol in corpus.EQUITIES},
                          "next_page_token": None})

    pages = list(corpus.alpaca_pages("key", "secret", opener=opener))
    assert len(pages) == 1
    request, timeout = requests[0]
    query = parse_qs(urlparse(request.full_url).query)
    assert timeout == 30
    assert query["symbols"] == [",".join(corpus.EQUITIES)]
    assert query["timeframe"] == ["1Min"]
    assert query["feed"] == ["sip"]
    assert query["adjustment"] == ["raw"]
    assert query["asof"] == ["2026-09-01"]
    assert query["start"] == ["2024-09-01T00:00:00Z"]
    assert query["end"] == ["2026-09-01T00:00:00Z"]
    assert pages[0].body == _Response(
        {"bars": {symbol: [] for symbol in corpus.EQUITIES},
         "next_page_token": None}
    )._body


def test_parser_preserves_decimal_values_and_raw_lineage() -> None:
    page = _raw_page({"bars": {"SPY": [{
        "t": "2025-01-02T14:30:00Z", "o": 100.10, "h": 101.20,
        "l": 99.90, "c": 100.40, "v": 1200, "n": 4, "vw": 100.333,
    }]}})
    row = corpus.parse_source_page(page, "SPY")[0]
    assert row.open == Decimal("100.1")
    assert row.vwap == Decimal("100.333")
    assert row.artifact_id == "sha256:" + corpus.sha256(page.body)
    assert row.locator == "$.bars.SPY[0]"

    sub_microsecond = _raw_page({"bars": {"SPY": [{
        "t": "2025-01-02T14:30:00.000000001Z", "o": 100, "h": 101,
        "l": 99, "c": 100, "v": 1,
    }]}})
    with pytest.raises(corpus.Hist8Error, match="sub-microsecond"):
        corpus.parse_source_page(sub_microsecond, "SPY")


def test_canonical_decimal_hashing_preserves_precision_without_context_rounding() -> None:
    left = Decimal("12345678901234567890123456780")
    right = Decimal("12345678901234567890123456781")
    assert corpus.canonical_bytes(left) != corpus.canonical_bytes(right)
    assert corpus.canonical_bytes(Decimal("1.2300")) == b'"1.23"'


def test_massive_identity_pagination_and_fractional_timestamp_fail_closed() -> None:
    with pytest.raises(corpus.Hist8Error, match="pagination resource mismatch"):
        corpus._strip_secret_query(
            "https://api.massive.com/v2/aggs/ticker/SPY/range/1/minute/"
            "2024-09-01/2026-09-01?cursor=next"
        )

    endpoint, params = corpus._strip_secret_query(
        corpus.MASSIVE_URL + "?cursor=next&apiKey=must-not-be-retained"
    )
    assert endpoint == corpus.MASSIVE_URL
    assert params == {
        "adjusted": "false", "sort": "asc", "limit": "50000",
        "cursor": "next",
    }
    provider_cursor_endpoint, provider_cursor_params = corpus._strip_secret_query(
        "https://api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
        "1725148860000/2026-09-01?cursor=opaque"
    )
    assert provider_cursor_endpoint.endswith(
        "/I%3ACOMP/range/1/minute/1725148860000/2026-09-01"
    )
    assert provider_cursor_params == {
        "adjusted": "false", "sort": "asc", "limit": "50000",
        "cursor": "opaque",
    }
    for query in (
        "cursor=next&adjusted=true",
        "cursor=next&sort=desc",
        "cursor=next&limit=5",
        "cursor=next&unexpected=value",
        "cursor=one&cursor=two",
    ):
        with pytest.raises(corpus.Hist8Error, match="parameter mismatch"):
            corpus._strip_secret_query(corpus.MASSIVE_URL + "?" + query)

    wrong_ticker = _Response({"ticker": "SPY", "results": []})
    with pytest.raises(corpus.Hist8Error, match="ticker identity mismatch"):
        list(corpus.massive_pages("key", opener=lambda *_args, **_kwargs: wrong_ticker))

    wrong_adjustment = _Response({
        "ticker": "I:COMP", "adjusted": True, "results": [],
    })
    with pytest.raises(corpus.Hist8Error, match="adjustment identity mismatch"):
        list(corpus.massive_pages(
            "key", opener=lambda *_args, **_kwargs: wrong_adjustment,
        ))

    page = corpus.RawPage(
        "MASSIVE", "I:COMP", "I:COMP minute index OHLC", ("NASDAQ",),
        corpus.MASSIVE_URL, {}, datetime(2026, 9, 2, tzinfo=UTC), 200,
        "application/json", None,
        (b'{"ticker":"I:COMP","results":[{"t":1000.5,"o":1,'
         b'"h":1,"l":1,"c":1}]}'),
    )
    with pytest.raises(corpus.Hist8Error, match="timestamp is not an integer"):
        corpus.parse_source_page(page, "NASDAQ")


def test_provider_redirect_is_rejected_before_response_acceptance() -> None:
    response = _Response({"bars": {symbol: [] for symbol in corpus.EQUITIES}})
    response.geturl = lambda: "https://attacker.example/redirected"
    with pytest.raises(corpus.Hist8Error, match="redirect is forbidden"):
        corpus._http_get(
            corpus.ALPACA_URL, headers={"APCA-API-KEY-ID": "secret"},
            opener=lambda *_args, **_kwargs: response,
        )
    assert any(isinstance(handler, corpus._RejectRedirects)
               for handler in corpus._NO_REDIRECT_OPENER.handlers)


def test_provider_response_headers_are_case_insensitive() -> None:
    payload = {"bars": {"SPY": []}}
    response = _Response(payload)
    response._body = gzip.compress(response._body)
    response.headers = {
        "content-type": "application/json",
        "CoNtEnT-EnCoDiNg": "gzip",
    }
    page = corpus._build_page(
        source="ALPACA", feed="SIP", product="1Min",
        instruments=("SPY",), endpoint=corpus.ALPACA_URL, params={},
        headers={}, opener=lambda *_args, **_kwargs: response,
        clock=lambda: datetime(2026, 9, 2, tzinfo=UTC),
    )
    assert page.content_type == "application/json"
    assert page.content_encoding == "gzip"
    assert page.payload() == payload


def test_incomplete_http_read_is_contained_to_one_provider(monkeypatch) -> None:
    calls = []
    stored = []

    class TruncatedResponse(_Response):
        def read(self) -> bytes:
            raise IncompleteRead(b'{"partial":', 128)

    def alpaca(*_args, **_kwargs):
        calls.append("ALPACA")
        corpus._http_get(
            corpus.ALPACA_URL, headers={},
            opener=lambda *_args, **_kwargs: TruncatedResponse({}),
        )
        yield  # pragma: no cover

    def coinbase(*_args, **_kwargs):
        calls.append("COINBASE")
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        calls.append("MASSIVE")
        yield _raw_page(
            {"complete": "massive"}, source="MASSIVE",
            instruments=("NASDAQ",),
        )

    class Store:
        def store_page(self, import_id, sequence, page):
            assert import_id == "truncated-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "truncated-attempt")

    assert calls == ["ALPACA", "COINBASE", "MASSIVE"]
    assert stored == ["COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 2
    assert result["source_statuses"]["SPY"] == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 0, "failure_type": "Hist8Error",
        "reason": "provider response body incomplete",
    }
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["NASDAQ"]["availability"] == "AVAILABLE"


def test_acquisition_continues_after_provider_unavailability(monkeypatch) -> None:
    calls = []
    stored = []

    def alpaca(*_args, **_kwargs):
        calls.append("ALPACA")
        yield _raw_page(
            {"partial": "alpaca"}, source="ALPACA",
            instruments=corpus.EQUITIES,
        )
        raise corpus.Hist8Error("Alpaca HTTP 503")

    def coinbase(*_args, **_kwargs):
        calls.append("COINBASE")
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        calls.append("MASSIVE")
        raise OSError("unreachable")

    class Store:
        def store_page(self, import_id, sequence, page):
            assert import_id == "partial-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "partial-attempt")
    statuses = result["source_statuses"]

    assert calls == ["ALPACA", "COINBASE", "MASSIVE"]
    assert stored == ["ALPACA", "COINBASE"]
    assert result["retrieval_associations"] == 7
    assert statuses["SPY"] == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 1, "failure_type": "Hist8Error",
        "reason": "Alpaca HTTP 503",
    }
    assert statuses["BTC-USD"] == {
        "source": "COINBASE", "availability": "AVAILABLE",
        "retrieval_associations": 1,
    }
    assert statuses["NASDAQ"] == {
        "source": "MASSIVE", "availability": "UNAVAILABLE",
        "retrieval_associations": 0, "failure_type": "OSError",
        "reason": "provider transport unavailable",
    }


def test_complete_session_is_eligible_and_derives_deterministically() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    minute_bars = tuple(corpus.canonical_bar(
        _source_bar(start + timedelta(minutes=index)),
        session_date="2025-01-02", calendar_hash="b" * 64,
        import_id="attempt-1", eligible=True,
    ) for index in range(5))
    first = corpus.derive_session(
        minute_bars, "5m", "attempt-1", session_open=start,
    )[0]
    second = corpus.derive_session(
        minute_bars, "5m", "attempt-2", session_open=start,
    )[0]
    assert first.open == Decimal("100")
    assert first.high == Decimal("103")
    assert first.low == Decimal("99")
    assert first.close == Decimal("102")
    assert first.volume == Decimal("50")
    assert first.lineage == tuple(
        f"{row.bar_id}|{row.content_hash}" for row in minute_bars
    )
    assert first.bar_id == second.bar_id
    assert first.content_hash == second.content_hash


def test_eligibility_is_snapshot_state_not_canonical_bar_identity() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    source = _source_bar(start)
    incomplete = corpus.canonical_bar(
        source, session_date="2025-01-02", calendar_hash="b" * 64,
        import_id="attempt-1", eligible=False,
    )
    reshuffled = replace(
        source, artifact_id="sha256:" + "c" * 64, locator="$[17]",
    )
    complete = corpus.canonical_bar(
        reshuffled, session_date="2025-01-02", calendar_hash="b" * 64,
        import_id="attempt-2", eligible=True,
    )
    assert incomplete.bar_id == complete.bar_id
    assert incomplete.content_hash == complete.content_hash
    assert incomplete.research_eligible is False
    assert complete.research_eligible is True


def test_derived_volume_sum_preserves_every_decimal_digit() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    volumes = [Decimal("10000000000000000000000000000")] + [Decimal(1)] * 4
    minutes = tuple(corpus.canonical_bar(
        replace(_source_bar(start + timedelta(minutes=index)), volume=volume),
        session_date="2025-01-02", calendar_hash="b" * 64,
        import_id="attempt", eligible=True,
    ) for index, volume in enumerate(volumes))
    derived = corpus.derive_session(
        minutes, "5m", "attempt", session_open=start,
    )[0]
    assert derived.volume == Decimal("10000000000000000000000000004")


def test_incomplete_session_is_stored_but_not_derived() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    body = {"bars": {"SPY": [
        {"t": start.isoformat(), "o": 100, "h": 101, "l": 99,
         "c": 100, "v": 1},
    ]}}

    class Store:
        inserted = []

        def retrieval_pages(self, import_id, instrument):
            assert (import_id, instrument) == ("source-1", "SPY")
            yield _raw_page(body)

        def insert_bars(self, rows):
            self.inserted.extend(rows)
            return len(rows), 0

    calendar = {
        "schedule_sha256": "c" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [{
            "date": "2025-01-02", "open_utc": "2025-01-02T14:30:00Z",
            "close_utc": "2025-01-02T14:32:00Z", "expected_minutes": 2,
        }],
    }
    store = Store()
    result = corpus.materialize_instrument(
        store, "source-1", "SPY", calendar, attempt_id="replay-1",
    )
    assert result["incomplete_sessions"] == 1
    assert len(store.inserted) == 1
    assert store.inserted[0].timeframe == "1m"
    assert store.inserted[0].research_eligible is False


def test_identical_overlap_with_different_lineage_is_idempotent_provider_data() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    item = {"t": start.isoformat(), "o": 100, "h": 101, "l": 99,
            "c": 100, "v": 1}

    class Store:
        inserted = []

        def retrieval_pages(self, _import_id, _instrument):
            yield _raw_page({"bars": {"SPY": [item]}})
            yield _raw_page({"bars": {"SPY": [item]}, "page": 2})

        def insert_bars(self, rows):
            self.inserted.extend(rows)
            return len(rows), 0

    calendar = {
        "schedule_sha256": "d" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [{
            "date": "2025-01-02", "open_utc": "2025-01-02T14:30:00Z",
            "close_utc": "2025-01-02T14:31:00Z", "expected_minutes": 1,
        }],
    }
    store = Store()
    result = corpus.materialize_instrument(store, "source", "SPY", calendar)
    assert result["provider_duplicates"] == 1
    assert result["eligible_sessions"] == 1
    assert len(store.inserted) == 1


def test_replay_pages_release_each_bounded_read_transaction() -> None:
    created_connections = []
    assert "cursor(name=" not in Path(
        "research/hist8/corpus.py"
    ).read_text(encoding="utf-8")
    retained = []
    for sequence in range(1, 10):
        body = json.dumps({"sequence": sequence}).encode()
        retained.append((
            sequence, "ALPACA", "SIP", "1Min", "SPY",
            corpus.ALPACA_URL, {}, datetime(2026, 9, 2, tzinfo=UTC),
            200, "application/json", None,
            "sha256:" + corpus.sha256(body), len(body), len(body), body,
        ))

    class Cursor:
        rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            if ("select current_user" in query
                    and "current_database()" in query):
                self.rows = [(corpus.IMPORTER_ROLE, corpus.DATABASE_NAME)]
            elif "select max(sequence_no)" in query:
                self.rows = [(retained[-1][0],)]
            elif "m.sequence_no>%s" in query:
                last_sequence, upper_sequence, limit = params[3:]
                self.rows = [
                    row for row in retained
                    if last_sequence < row[0] <= upper_sequence
                ][:limit]
            else:
                raise AssertionError(query)

        def fetchone(self):
            return self.rows[0]

        def fetchall(self):
            return list(self.rows)

    class Connection:
        active = False

        def __enter__(self):
            self.active = True
            return self

        def __exit__(self, *_args):
            self.active = False

        def cursor(self):
            return Cursor()

    def connection_factory():
        connection = Connection()
        created_connections.append(connection)
        return connection

    pages = list(corpus.Hist8Store(connection_factory).retrieval_pages(
        "source-import", "SPY",
    ))
    assert [json.loads(page.body)["sequence"] for page in pages] == list(
        range(1, 10)
    )
    assert len(created_connections) == 3
    assert all(connection.active is False for connection in created_connections)


def test_identical_insert_race_uses_actual_affected_row_count() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    row = corpus.canonical_bar(
        _source_bar(start), session_date="2025-01-02",
        calendar_hash="b" * 64, import_id="race-attempt", eligible=True,
    )
    state = {"bar_selects": 0}

    class Cursor:
        rows = []
        rowcount = -1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            if ("select current_user" in query
                    and "current_database()" in query):
                self.rows = [(corpus.IMPORTER_ROLE, corpus.DATABASE_NAME)]
            elif "select timeframe,bar_start_utc,bar_id" in query:
                state["bar_selects"] += 1
                self.rows = [] if state["bar_selects"] == 1 else [(
                    row.timeframe, row.bar_start_utc, row.bar_id,
                    row.content_hash, "winning-attempt",
                )]
            elif "select sequence_no,member_bar_id" in query:
                self.rows = [(
                    corpus._membership_sequence(row), row.bar_id,
                    row.content_hash, row.research_eligible,
                )]
            else:
                raise AssertionError(query)

        def executemany(self, query, params):
            if "insert into atom_research_history.bars" in query:
                self.rowcount = 0
            elif "insert into atom_research_history.manifests" not in query:
                raise AssertionError(query)

        def fetchone(self):
            return self.rows[0]

        def fetchall(self):
            return list(self.rows)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    store = corpus.Hist8Store(Connection)
    assert store.insert_bars((row,)) == (0, 1)


def test_sealed_snapshot_recomputes_manifest_identity() -> None:
    import_id = "source-attempt"
    metadata = {
        "membership_sha256": "a" * 64,
        "source_statuses": {},
    }

    class Cursor:
        rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            if ("select current_user" in query
                    and "current_database()" in query):
                self.rows = [(corpus.IMPORTER_ROLE, corpus.DATABASE_NAME)]
            elif "manifest_kind='SNAPSHOT'" in query:
                assert params == (corpus.CORPUS_ID, import_id)
                self.rows = [(
                    corpus.CORPUS_ID, import_id, "SNAPSHOT", 0,
                    "sha256:" + "b" * 64, metadata,
                )]
            else:
                raise AssertionError(query)

        def fetchone(self):
            return self.rows[0]

        def fetchall(self):
            return list(self.rows)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    store = corpus.Hist8Store(Connection)
    with pytest.raises(
        corpus.Hist8ConflictError, match="manifest identity mismatch"
    ):
        store.sealed_snapshot_state(import_id)


def test_database_url_must_bind_exact_project_database_and_role(monkeypatch) -> None:
    import psycopg

    bad_urls = (
        "", "postgresql://atom_hist8_importer:x@example.com/postgres",
        f"postgresql://postgres:x@{corpus.DATABASE_HOST}/postgres",
        f"postgresql://atom_hist8_importer:x@{corpus.DATABASE_HOST}/other",
        f"postgresql://atom_hist8_importer:x@{corpus.DATABASE_HOST}/postgres",
        f"postgresql://atom_hist8_importer:x@{corpus.DATABASE_HOST}:5432/postgres"
        "?sslmode=verify-full&sslrootcert=system&host=other.example",
    )
    for value in bad_urls:
        monkeypatch.setenv(corpus.IMPORT_DATABASE_ENV, value)
        with pytest.raises(corpus.Hist8Error, match="credential/project mismatch"):
            corpus.Hist8Store.from_environment()
    monkeypatch.setenv(
        corpus.IMPORT_DATABASE_ENV,
        f"postgresql://atom_hist8_importer:x@{corpus.DATABASE_HOST}:5432/postgres"
        "?sslmode=verify-full&sslrootcert=system",
    )
    connections = []

    def connect(dsn, **options):
        connections.append((dsn, options))
        return object()

    monkeypatch.setattr(psycopg, "connect", connect)
    store = corpus.Hist8Store.from_environment()
    assert isinstance(store, corpus.Hist8Store)
    assert store._connection_factory() is not None
    assert connections[0][1] == {
        "connect_timeout": corpus.IMPORTER_CONNECT_TIMEOUT_SECONDS,
        "options": corpus.IMPORTER_SESSION_OPTIONS,
    }
    assert "statement_timeout=60000" in corpus.IMPORTER_SESSION_OPTIONS
    assert "lock_timeout=5000" in corpus.IMPORTER_SESSION_OPTIONS
    assert "idle_in_transaction_session_timeout=60000" in (
        corpus.IMPORTER_SESSION_OPTIONS
    )


def test_schema_installer_verifies_direct_tls_endpoint_before_sql() -> None:
    events = []
    assert "ATOM_HIST8_INSTALL_DATABASE_URL" not in Path(
        "research/hist8/corpus.py"
    ).read_text(encoding="utf-8")

    class Cursor:
        def __init__(self):
            self.readbacks = iter([
                ("postgres", "postgres", True),
                (True, True, 3),
            ])

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            events.append((query, params))

        def fetchone(self):
            return next(self.readbacks)

    class Info:
        def __init__(self, host=corpus.DATABASE_HOST):
            self.host = host
            self.port = 5432
            self.dbname = "postgres"
            self.user = "postgres"
            self.dsn_parameters = {
                "sslmode": "verify-full", "sslrootcert": "system",
            }

    class Connection:
        def __init__(self, host=corpus.DATABASE_HOST):
            self._cursor = Cursor()
            self.autocommit = True
            self.info = Info(host)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return self._cursor

    result = corpus.install_schema(Connection())
    assert result["project_ref"] == corpus.PROJECT_REF
    assert "pg_stat_ssl" in events[0][0]
    assert "set_config('atom.hist8_verified_project_ref'" in events[1][0]
    assert events[1][1] == (corpus.PROJECT_REF,)
    assert "CREATE ROLE atom_hist8_importer" in events[2][0]

    with pytest.raises(corpus.Hist8Error, match="endpoint identity"):
        corpus.install_schema(Connection(host="wrong.example"))


def test_replay_must_equal_the_sealed_source_snapshot(monkeypatch) -> None:
    statuses = {
        instrument: {
            "source": corpus.INSTRUMENT_SOURCE[instrument],
            "availability": (
                "UNAVAILABLE" if instrument == "NASDAQ" else "AVAILABLE"
            ),
            "retrieval_associations": 0,
            **({"failure_type": "Hist8Error", "reason": "Massive unavailable"}
               if instrument == "NASDAQ" else {}),
        }
        for instrument in corpus.INSTRUMENTS
    }
    materialized = []
    unavailable_replays = []

    class Store:
        attempts = []

        def sealed_snapshot_state(self, import_id):
            assert import_id == "source-attempt"
            return {
                "manifest_id": "sha256:" + "d" * 64,
                "membership_sha256": "a" * 64,
                "metadata": {"source_statuses": statuses},
            }

        def add_attempt(self, import_id, kind, metadata):
            self.attempts.append((import_id, kind, metadata))

        def retrieval_pages(self, import_id, instrument):
            unavailable_replays.append((import_id, instrument))
            return iter(())

        def seal_snapshot(self, import_id, metadata):
            return "b" * 64

    store = Store()
    monkeypatch.setattr(
        corpus.Hist8Store, "from_environment", classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(corpus, "load_calendar", lambda: {
        "schedule_sha256": "c" * 64,
    })
    monkeypatch.setattr(
        corpus, "materialize_instrument",
        lambda _store, _source, instrument, _calendar, **_kwargs: (
            materialized.append(instrument) or {
                "inserted": 0, "verified_retrieval_associations": 0,
            }
        ),
    )
    monkeypatch.setattr(
        corpus, "_unavailable_instrument_result",
        lambda *_args, **_kwargs: {"inserted": 0},
    )
    with pytest.raises(corpus.Hist8ConflictError, match="differs from sealed"):
        corpus.execute("source-attempt", acquire_sources=False)
    assert store.attempts[0][1] == "REPLAY_ATTEMPT"
    assert store.attempts[0][2]["expected_membership_sha256"] == "a" * 64
    assert store.attempts[0][2]["source_snapshot_manifest_id"] == (
        "sha256:" + "d" * 64
    )
    assert materialized == list(corpus.INSTRUMENTS[:-1])
    assert unavailable_replays == [("source-attempt", "NASDAQ")]


def test_execute_seals_partial_availability_without_substitution(monkeypatch) -> None:
    statuses = {
        instrument: {
            "source": corpus.INSTRUMENT_SOURCE[instrument],
            "availability": (
                "UNAVAILABLE" if instrument == "NASDAQ" else "AVAILABLE"
            ),
            "retrieval_associations": 1,
            **({"failure_type": "Hist8Error", "reason": "Massive HTTP 403"}
               if instrument == "NASDAQ" else {}),
        }
        for instrument in corpus.INSTRUMENTS
    }

    class Store:
        attempts = []
        snapshots = []

        def add_attempt(self, import_id, kind, metadata):
            self.attempts.append((import_id, kind, metadata))

        def retrieval_pages(self, import_id, instrument):
            assert (import_id, instrument) == ("partial-source", "NASDAQ")
            yield _raw_page(
                {"partial": "massive"}, source="MASSIVE",
                instruments=("NASDAQ",),
            )

        def seal_snapshot(self, import_id, metadata):
            self.snapshots.append((import_id, metadata))
            return "e" * 64

    store = Store()
    materialized = []
    monkeypatch.setattr(
        corpus.Hist8Store, "from_environment", classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(corpus, "load_calendar", lambda: {
        "schedule_sha256": "c" * 64,
    })
    monkeypatch.setattr(corpus, "acquire", lambda *_args: {
        "retrieval_associations": 8, "source_statuses": statuses,
    })
    monkeypatch.setattr(
        corpus, "materialize_instrument",
        lambda _store, _source, instrument, _calendar, **_kwargs: (
            materialized.append(instrument) or {
                "inserted": 3, "verified_retrieval_associations": 1,
            }
        ),
    )
    monkeypatch.setattr(
        corpus, "_unavailable_instrument_result",
        lambda *_args, **_kwargs: {"inserted": 0},
    )

    result = corpus.execute("partial-source", acquire_sources=True)

    assert result["membership_sha256"] == "e" * 64
    assert materialized == list(corpus.INSTRUMENTS[:-1])
    assert result["instrument_results"]["NASDAQ"]["inserted"] == 0
    assert result["instrument_results"]["NASDAQ"]["availability"] == "UNAVAILABLE"
    snapshot_metadata = store.snapshots[0][1]
    assert snapshot_metadata["retrieval_associations"] == 8
    assert snapshot_metadata["source_statuses"] == statuses


def test_unavailable_replay_still_verifies_retained_artifacts(monkeypatch) -> None:
    statuses = {
        instrument: {
            "source": corpus.INSTRUMENT_SOURCE[instrument],
            "availability": (
                "UNAVAILABLE" if instrument == "NASDAQ" else "AVAILABLE"
            ),
            "retrieval_associations": 1 if instrument == "NASDAQ" else 0,
            **({"failure_type": "Hist8Error", "reason": "Massive HTTP 503"}
               if instrument == "NASDAQ" else {}),
        }
        for instrument in corpus.INSTRUMENTS
    }

    class Store:
        def sealed_snapshot_state(self, _import_id):
            return {
                "manifest_id": "sha256:" + "f" * 64,
                "membership_sha256": "a" * 64,
                "metadata": {"source_statuses": statuses},
            }

        def add_attempt(self, *_args, **_kwargs):
            return None

        def retrieval_pages(self, _import_id, instrument):
            assert instrument == "NASDAQ"
            raise corpus.Hist8ConflictError(
                "retained raw artifact replay mismatch"
            )
            yield  # pragma: no cover

        def seal_snapshot(self, *_args, **_kwargs):
            raise AssertionError("corrupt retained bytes must block sealing")

    monkeypatch.setattr(
        corpus.Hist8Store, "from_environment", classmethod(lambda _cls: Store()),
    )
    monkeypatch.setattr(corpus, "load_calendar", lambda: {
        "schedule_sha256": "c" * 64,
    })
    monkeypatch.setattr(
        corpus, "materialize_instrument",
        lambda *_args, **_kwargs: {
            "inserted": 0, "verified_retrieval_associations": 0,
        },
    )
    monkeypatch.setattr(
        corpus, "_unavailable_instrument_result",
        lambda *_args, **_kwargs: {"inserted": 0},
    )
    with pytest.raises(
        corpus.Hist8ConflictError, match="artifact replay mismatch"
    ):
        corpus.execute("partial-source", acquire_sources=False)


def test_schema_has_exact_private_surface_and_append_only_grants() -> None:
    sql = Path("research/hist8/schema.sql").read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE atom_research_history.") == 3
    assert "CREATE SCHEMA atom_research_history AUTHORIZATION postgres" in sql
    assert "GRANT SELECT, INSERT ON atom_research_history.raw_responses" in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql
    assert "GRANT TRUNCATE" not in sql
    assert sql.count("FORCE ROW LEVEL SECURITY") == 3
    assert "HIST8_EFFECTIVE_PRIVILEGE_BOUNDARY_UNSATISFIED" in sql
    assert sql.lstrip().startswith("-- ATOM-HIST8-CORPUS-AMENDMENT-1")
    assert "\nBEGIN;" in sql and sql.rstrip().endswith("COMMIT;")
    assert "HIST8_IMPORTER_ROLE_ALREADY_EXISTS" in sql
    assert "acl.grantee NOT IN" in sql
    assert "'SNAPSHOT_MEMBER'" in sql
    assert "member_research_eligible boolean" in sql
    assert "HIST8_RESEARCH_SCHEMA_ALREADY_EXISTS" in sql
    assert "HIST8_EFFECTIVE_SEQUENCE_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_EFFECTIVE_ROUTINE_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_EFFECTIVE_SCHEMA_USAGE_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_FOREIGN_SCHEMA_ACCESS_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_OTHER_DATABASE_CONNECT_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_DATABASE_PRIVILEGE_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_EFFECTIVE_COLUMN_PRIVILEGE_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_EFFECTIVE_LARGE_OBJECT_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_EFFECTIVE_LARGE_OBJECT_CREATE_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_ENDPOINT_IDENTITY_UNVERIFIED" in sql
    assert "'BAR_CONFLICT'" in sql
    assert "'REFERENCES'" in sql and "'TRIGGER'" in sql
    assert "NEW.manifest_kind IN ('SNAPSHOT_MEMBER', 'RETRIEVAL')" in sql
    assert "'extensions','atom_research_history'" not in sql
    assert "hist8_bars_session_lookup_idx" in sql


def test_schema_enforces_importer_boundary_in_postgres() -> None:
    dsn = os.environ.get("H2C_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("CI PostgreSQL is not available")
    import psycopg
    from psycopg import sql as pgsql

    sql = Path("research/hist8/schema.sql").read_text(encoding="utf-8")
    managed_roles = (
        "atom_hist8_importer", "hist8_forbidden", "anon",
        "authenticated", "service_role",
    )
    other_connectable_databases = []
    current_database_name = None
    restore_public_create = False
    restore_public_temporary = False
    extensions_schema_created = False
    large_object_oid = None
    large_object_create_routines = []
    with psycopg.connect(dsn, autocommit=True) as connection:
        try:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated", "service_role"):
                    cursor.execute(
                        f"create role {role} nologin nosuperuser nocreatedb "
                        "nocreaterole noreplication nobypassrls"
                    )
                cursor.execute("create role hist8_forbidden nologin")
                cursor.execute("create table public.coin_v8_market_bars (id bigint)")
                cursor.execute("create table public.coin_v8_ai_decision_logs (id bigint)")

                with pytest.raises(
                    psycopg.Error, match="ENDPOINT_IDENTITY_UNVERIFIED"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select count(*) from pg_roles "
                    "where rolname='atom_hist8_importer'"
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "select set_config('atom.hist8_verified_project_ref',%s,false)",
                    (corpus.PROJECT_REF,),
                )

                cursor.execute(
                    "create role atom_hist8_importer login noinherit nosuperuser "
                    "nocreatedb nocreaterole noreplication nobypassrls"
                )
                with pytest.raises(psycopg.Error, match="ROLE_ALREADY_EXISTS"):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select to_regnamespace('atom_research_history') is null"
                )
                assert cursor.fetchone()[0] is True
                cursor.execute("drop role atom_hist8_importer")

                cursor.execute(
                    "create schema atom_research_history authorization postgres"
                )
                with pytest.raises(psycopg.Error, match="SCHEMA_ALREADY_EXISTS"):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select count(*) from pg_roles "
                    "where rolname='atom_hist8_importer'"
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute("drop schema atom_research_history")

                cursor.execute(
                    """select current_database(),
                              has_database_privilege(
                                'public',current_database(),'CREATE'
                              ),
                              has_database_privilege(
                                'public',current_database(),'TEMPORARY'
                              )"""
                )
                (current_database_name, restore_public_create,
                 restore_public_temporary) = cursor.fetchone()
                cursor.execute(
                    pgsql.SQL(
                        "grant create,temporary on database {} to public"
                    ).format(pgsql.Identifier(current_database_name))
                )
                with pytest.raises(
                    psycopg.Error, match="DATABASE_PRIVILEGE_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    pgsql.SQL(
                        "revoke create,temporary on database {} from public"
                    ).format(pgsql.Identifier(current_database_name))
                )

                with pytest.raises(
                    psycopg.Error, match="OTHER_DATABASE_CONNECT_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    """select datname from pg_database
                       where datname <> current_database() and datallowconn
                         and has_database_privilege('public',oid,'CONNECT')
                       order by datname"""
                )
                other_connectable_databases = [row[0] for row in cursor.fetchall()]
                assert other_connectable_databases
                for database in other_connectable_databases:
                    cursor.execute(
                        pgsql.SQL("revoke connect on database {} from public").format(
                            pgsql.Identifier(database)
                        )
                    )

                cursor.execute(
                    """select format('%I.%I(%s)', n.nspname, p.proname,
                                      pg_catalog.oidvectortypes(p.proargtypes)),
                              exists (
                                select 1
                                from aclexplode(coalesce(
                                  p.proacl, acldefault('f', p.proowner)
                                )) acl
                                where acl.grantee=0
                                  and acl.privilege_type='EXECUTE'
                              )
                       from pg_proc p
                       join pg_namespace n on n.oid=p.pronamespace
                       where n.nspname='pg_catalog'
                         and p.proname in (
                           'lo_creat','lo_create','lo_from_bytea','lo_import'
                         )
                       order by p.oid"""
                )
                large_object_create_routines = cursor.fetchall()
                assert large_object_create_routines
                for routine, _was_public in large_object_create_routines:
                    cursor.execute(
                        pgsql.SQL(
                            "grant execute on function {} to public"
                        ).format(pgsql.SQL(routine))
                    )
                with pytest.raises(
                    psycopg.Error, match="LARGE_OBJECT_CREATE_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                for routine, _was_public in large_object_create_routines:
                    cursor.execute(
                        pgsql.SQL(
                            "revoke execute on function {} from public"
                        ).format(pgsql.SQL(routine))
                    )

                cursor.execute(
                    "alter default privileges for role postgres "
                    "grant usage on schemas to hist8_forbidden"
                )
                with pytest.raises(
                    psycopg.Error, match="FOREIGN_SCHEMA_ACCESS_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke usage on schemas from hist8_forbidden"
                )

                cursor.execute(
                    "alter default privileges for role postgres "
                    "grant select on tables to hist8_forbidden"
                )
                with pytest.raises(
                    psycopg.Error, match="FOREIGN_ROLE_ACCESS_BOUNDARY_UNSATISFIED"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select count(*) from information_schema.tables "
                    "where table_schema='atom_research_history'"
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "select count(*) from pg_roles "
                    "where rolname='atom_hist8_importer'"
                )
                assert cursor.fetchone()[0] == 0
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke select on tables from hist8_forbidden"
                )

                cursor.execute(
                    "create table public.hist8_column_forbidden "
                    "(secret bigint, ordinary bigint)"
                )
                cursor.execute(
                    "revoke all on public.hist8_column_forbidden from public"
                )
                cursor.execute(
                    "grant select(secret) on public.hist8_column_forbidden to public"
                )
                with pytest.raises(
                    psycopg.Error, match="COLUMN_PRIVILEGE_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop table public.hist8_column_forbidden")

                cursor.execute(
                    "create table public.hist8_trigger_forbidden (id bigint)"
                )
                cursor.execute(
                    "revoke all on public.hist8_trigger_forbidden from public"
                )
                cursor.execute(
                    "grant trigger on public.hist8_trigger_forbidden to public"
                )
                with pytest.raises(
                    psycopg.Error, match="EFFECTIVE_PRIVILEGE_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop table public.hist8_trigger_forbidden")

                cursor.execute("select to_regnamespace('extensions')")
                assert cursor.fetchone()[0] is None
                cursor.execute("create schema extensions")
                extensions_schema_created = True
                cursor.execute("grant usage on schema extensions to public")
                cursor.execute(
                    "create function extensions.hist8_extension_callable() "
                    "returns integer language sql immutable as 'select 1'"
                )
                with pytest.raises(
                    psycopg.Error, match="ROUTINE_BOUNDARY_UNSATISFIED"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop schema extensions cascade")
                extensions_schema_created = False

                cursor.execute("select lo_create(0)")
                large_object_oid = cursor.fetchone()[0]
                cursor.execute(
                    pgsql.SQL(
                        "grant select on large object {} to public"
                    ).format(pgsql.Literal(large_object_oid))
                )
                with pytest.raises(
                    psycopg.Error, match="LARGE_OBJECT_BOUNDARY_UNSATISFIED"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("select lo_unlink(%s)", (large_object_oid,))
                assert cursor.fetchone()[0] == 1
                large_object_oid = None

                cursor.execute(
                    "create function public.hist8_callable() returns integer "
                    "language sql immutable as 'select 1'"
                )
                with pytest.raises(
                    psycopg.Error, match="ROUTINE_BOUNDARY_UNSATISFIED"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop function public.hist8_callable()")

                cursor.execute("create sequence public.hist8_forbidden_sequence")
                cursor.execute(
                    "grant usage,select,update on sequence "
                    "public.hist8_forbidden_sequence to public"
                )
                with pytest.raises(
                    psycopg.Error, match="SEQUENCE_BOUNDARY_UNSATISFIED"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop sequence public.hist8_forbidden_sequence")

                cursor.execute("create schema hist8_visible")
                cursor.execute("grant usage on schema hist8_visible to public")
                with pytest.raises(
                    psycopg.Error, match="SCHEMA_USAGE_BOUNDARY_UNSATISFIED"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop schema hist8_visible")

                cursor.execute(sql)
                cursor.execute(
                    """select rolcanlogin, rolinherit, rolsuper, rolcreatedb,
                              rolcreaterole, rolreplication, rolbypassrls
                       from pg_roles where rolname='atom_hist8_importer'"""
                )
                assert cursor.fetchone() == (
                    True, False, False, False, False, False, False,
                )

                def importer_connection():
                    importer = psycopg.connect(dsn, autocommit=False)
                    importer.execute("set role atom_hist8_importer")
                    return importer

                store = corpus.Hist8Store(importer_connection)
                page = _raw_page({"retained": "first"})
                artifact_id = "sha256:" + corpus.sha256(page.body)
                assert store.store_page("raw-attempt-1", 1, page) == 2
                corrupted_body = page.body.replace(b"first", b"FIRST")
                assert len(corrupted_body) == len(page.body)
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "disable trigger hist8_raw_reject_update_delete"
                )
                cursor.execute(
                    "update atom_research_history.raw_responses set body=%s "
                    "where artifact_id=%s", (corrupted_body, artifact_id),
                )
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "enable trigger hist8_raw_reject_update_delete"
                )
                with pytest.raises(
                    corpus.Hist8ConflictError, match="artifact replay mismatch"
                ):
                    list(store.retrieval_pages("raw-attempt-1", "SPY"))
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "disable trigger hist8_raw_reject_update_delete"
                )
                cursor.execute(
                    "update atom_research_history.raw_responses set body=%s "
                    "where artifact_id=%s", (page.body, artifact_id),
                )
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "enable trigger hist8_raw_reject_update_delete"
                )
                replayed_pages = list(
                    store.retrieval_pages("raw-attempt-1", "SPY")
                )
                assert [item.body for item in replayed_pages] == [page.body]
                raw_snapshot_digest = store.seal_snapshot("raw-attempt-1", {})
                raw_snapshot = store.sealed_snapshot_state("raw-attempt-1")
                assert raw_snapshot["membership_sha256"] == raw_snapshot_digest
                with pytest.raises(
                    psycopg.Error, match="import evidence is sealed"
                ):
                    store.store_page(
                        "raw-attempt-1", 2,
                        _raw_page({"retained": "late-association"}),
                    )
                cursor.execute("set role atom_hist8_importer")
                cursor.execute(
                    "select body from atom_research_history.raw_responses "
                    "where artifact_id=%s", (artifact_id,),
                )
                assert bytes(cursor.fetchone()[0]) == page.body
                with pytest.raises(psycopg.Error):
                    cursor.execute(
                        "update atom_research_history.raw_responses "
                        "set body=body where artifact_id=%s", (artifact_id,),
                    )
                cursor.execute("reset role")
                cursor.execute(
                    """select count(*) from information_schema.tables
                       where table_schema='atom_research_history'"""
                )
                assert cursor.fetchone()[0] == 3

                reshuffled_page = _raw_page({"retained": "reshuffled"})
                reshuffled_artifact = "sha256:" + corpus.sha256(
                    reshuffled_page.body
                )
                assert store.store_page("raw-attempt-2", 1, reshuffled_page) == 2
                start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
                source = _source_bar(start, artifact=artifact_id)
                incomplete = corpus.canonical_bar(
                    source, session_date="2025-01-02", calendar_hash="b" * 64,
                    import_id="attempt-incomplete", eligible=False,
                )
                complete = corpus.canonical_bar(
                    replace(
                        source, artifact_id=reshuffled_artifact, locator="$[17]",
                    ),
                    session_date="2025-01-02", calendar_hash="b" * 64,
                    import_id="attempt-complete", eligible=True,
                )
                assert store.insert_bars((incomplete,)) == (1, 0)
                assert store.insert_bars((complete,)) == (0, 1)
                conflicting = corpus.canonical_bar(
                    replace(source, close=Decimal("101")),
                    session_date="2025-01-02", calendar_hash="b" * 64,
                    import_id="attempt-conflict", eligible=True,
                )
                with pytest.raises(
                    corpus.Hist8ConflictError, match="same-key bar conflict"
                ):
                    store.insert_bars((conflicting,))
                cursor.execute(
                    """select metadata_json
                       from atom_research_history.manifests
                       where import_id='attempt-conflict'
                         and manifest_kind='BAR_CONFLICT'"""
                )
                conflict_metadata = cursor.fetchone()[0]
                assert conflict_metadata["conflict_kind"] == "SAME_CANONICAL_KEY"
                assert conflict_metadata["existing"]["content_hash"] == (
                    incomplete.content_hash
                )
                assert conflict_metadata["candidate"]["content_hash"] == (
                    conflicting.content_hash
                )
                incomplete_digest = store.seal_snapshot("attempt-incomplete", {})
                complete_digest = store.seal_snapshot("attempt-complete", {})
                assert incomplete_digest != complete_digest
                assert store.sealed_snapshot_digest(
                    "attempt-incomplete"
                ) == incomplete_digest
                with pytest.raises(corpus.Hist8Error, match="snapshot missing"):
                    store.sealed_snapshot_digest("not-an-attempt")
                cursor.execute(
                    """select source_artifact_id,source_record_locator
                       from atom_research_history.bars
                       where bar_id=%s""", (incomplete.bar_id,),
                )
                assert cursor.fetchone() == (artifact_id, "$[0]")
                cursor.execute(
                    """select import_id,member_research_eligible
                       from atom_research_history.manifests
                       where manifest_kind='SNAPSHOT_MEMBER'
                       order by import_id"""
                )
                assert cursor.fetchall() == [
                    ("attempt-complete", True), ("attempt-incomplete", False),
                ]
        finally:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute("reset role")
                cursor.execute("drop schema if exists atom_research_history cascade")
                cursor.execute("drop table if exists public.coin_v8_market_bars")
                cursor.execute("drop table if exists public.coin_v8_ai_decision_logs")
                cursor.execute("drop table if exists public.hist8_column_forbidden")
                cursor.execute("drop table if exists public.hist8_trigger_forbidden")
                cursor.execute("drop function if exists public.hist8_callable()")
                cursor.execute("drop sequence if exists public.hist8_forbidden_sequence")
                cursor.execute("drop schema if exists hist8_visible")
                if extensions_schema_created:
                    cursor.execute("drop schema if exists extensions cascade")
                if large_object_oid is not None:
                    cursor.execute("select lo_unlink(%s)", (large_object_oid,))
                for routine, was_public in large_object_create_routines:
                    cursor.execute(
                        pgsql.SQL(
                            "revoke execute on function {} from public"
                        ).format(pgsql.SQL(routine))
                    )
                    if was_public:
                        cursor.execute(
                            pgsql.SQL(
                                "grant execute on function {} to public"
                            ).format(pgsql.SQL(routine))
                        )
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke select on tables from hist8_forbidden"
                )
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke usage on schemas from hist8_forbidden"
                )
                for database in other_connectable_databases:
                    cursor.execute(
                        pgsql.SQL("grant connect on database {} to public").format(
                            pgsql.Identifier(database)
                        )
                    )
                if current_database_name:
                    cursor.execute(
                        pgsql.SQL(
                            "revoke create,temporary on database {} from public"
                        ).format(pgsql.Identifier(current_database_name))
                    )
                    if restore_public_create:
                        cursor.execute(
                            pgsql.SQL(
                                "grant create on database {} to public"
                            ).format(pgsql.Identifier(current_database_name))
                        )
                    if restore_public_temporary:
                        cursor.execute(
                            pgsql.SQL(
                                "grant temporary on database {} to public"
                            ).format(pgsql.Identifier(current_database_name))
                        )
                for role in managed_roles:
                    cursor.execute(f"drop role if exists {role}")
