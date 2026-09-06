from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
from http.client import BadStatusLine, IncompleteRead
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import zlib

import pytest

from research.hist8 import corpus


UTC = timezone.utc
TEST_CODE_IDENTITY = {
    "identity_version": "HIST8_CODE_IDENTITY_1",
    "implementation_commit": "f" * 40,
    "files": {
        path: {
            "git_blob": "a" * 40,
            "sha256": "b" * 64,
            "byte_length": 1,
        }
        for path in corpus.EXECUTION_CODE_PATHS
    },
}


def _source_bar(start: datetime, *, artifact: str = "sha256:" + "a" * 64) -> corpus.SourceBar:
    return corpus.SourceBar(
        "SPY", start, Decimal("100"), Decimal("103"), Decimal("99"),
        Decimal("102"), Decimal("10"), 2, Decimal("101"), artifact,
        "$[0]", "ALPACA", "SIP", "SPY:1Min", "raw", "SHARES",
    )


def _raw_page(body: object, *, source: str = "ALPACA", instruments=("SPY",)) -> corpus.RawPage:
    if source == "ALPACA":
        feed = "SIP"
        product = "1Min trade OHLCV"
        endpoint = corpus.ALPACA_URL
        request_params = dict(corpus.ALPACA_FROZEN_PARAMS)
    elif source == "COINBASE":
        feed = "EXCHANGE"
        product = "BTC-USD granularity=60"
        endpoint = corpus.COINBASE_URL
        request_params = {
            "granularity": "60", "start": "2024-09-01T00:00:00Z",
            "end": "2024-09-01T05:00:00Z",
        }
    elif source == "MASSIVE":
        feed = "I:COMP"
        product = "I:COMP minute index OHLC"
        endpoint = corpus.MASSIVE_URL
        request_params = dict(corpus.MASSIVE_FROZEN_PARAMS)
    else:
        raise AssertionError(source)
    return corpus.RawPage(
        source, feed, product, instruments, endpoint, request_params,
        datetime(2026, 9, 2, tzinfo=UTC), 200, "application/json", None,
        json.dumps(body, separators=(",", ":")).encode(),
    )


def _retrieval_record(
    page: corpus.RawPage, instrument: str, *, import_id: str = "attempt",
    sequence_no: int = 1,
) -> tuple[object, ...]:
    payload = corpus._retrieval_manifest_payload(
        import_id, sequence_no, page, instrument,
    )
    artifact_id = "sha256:" + corpus.sha256(page.body)
    return (
        corpus._manifest_id(payload), corpus.CORPUS_ID, import_id,
        "RETRIEVAL", sequence_no, page.source, page.feed, page.product,
        instrument, page.endpoint, dict(page.request_params),
        page.retrieved_at, page.http_status, page.content_type,
        page.content_encoding, artifact_id, len(page.body), len(page.body),
        page.body,
    )


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload, separators=(",", ":")).encode()
        self._offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._offset
        start = self._offset
        self._offset = min(len(self._body), start + size)
        return self._body[start:self._offset]


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


def test_calendar_rejects_self_consistent_nonreviewed_schedule(tmp_path) -> None:
    manifest = corpus.load_calendar()
    tampered = dict(manifest)
    tampered["timezone_database_version"] = "unreviewed-tzdb"
    tampered["schedule_sha256"] = corpus.sha256({
        key: tampered[key] for key in tampered if key != "schedule_sha256"
    })
    path = tmp_path / "calendar_manifest.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(corpus.Hist8Error, match="calendar schedule hash mismatch"):
        corpus.load_calendar(path)


def test_calendar_file_bytes_are_bound_to_execution_identity() -> None:
    with pytest.raises(corpus.Hist8Error, match="artifact identity mismatch"):
        corpus.load_calendar(expected_file_sha256="0" * 64)


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


def test_retained_manifest_rejects_self_consistent_wrong_provider_binding() -> None:
    page = _raw_page([], source="COINBASE", instruments=("QQQ",))
    record = _retrieval_record(page, "QQQ")
    with pytest.raises(
        corpus.Hist8ConflictError,
        match="retained retrieval manifest identity mismatch",
    ):
        corpus._verified_retrieval_record(
            record, import_id="attempt", instrument="QQQ",
        )


@pytest.mark.parametrize("page", (
    replace(
        _raw_page({"bars": {"SPY": []}}),
        feed="IEX",
    ),
    replace(
        _raw_page({"bars": {"SPY": []}}),
        request_params={**corpus.ALPACA_FROZEN_PARAMS, "feed": "iex"},
    ),
))
def test_parser_rejects_provider_identity_drift(page) -> None:
    with pytest.raises(corpus.Hist8Error):
        corpus.parse_source_page(page, "SPY")


def test_malformed_source_rows_are_counted_and_valid_rows_survive() -> None:
    start = "2025-01-02T14:30:00Z"
    page = _raw_page({"bars": {"SPY": [
        {"t": start, "o": "100", "h": "101", "l": "99",
         "c": "100", "v": "5"},
        {"t": start, "o": "100", "h": "101", "l": "99", "v": "5"},
        {"t": "not-a-timestamp", "o": "100", "h": "101", "l": "99",
         "c": "100", "v": "5"},
        {"t": start, "o": "not-a-number", "h": "101", "l": "99",
         "c": "100", "v": "5"},
    ]}})
    rejected = [0]
    parsed = corpus.parse_source_page(
        page, "SPY", rejection_counter=rejected,
    )
    assert len(parsed) == 1
    assert parsed[0].open == Decimal("100")
    assert rejected == [3]


def test_alpaca_trade_count_is_bounded_to_postgresql_bigint() -> None:
    start = "2025-01-02T14:30:00Z"
    page = _raw_page({"bars": {"SPY": [
        {"t": start, "o": "100", "h": "101", "l": "99",
         "c": "100", "v": "5", "n": 9223372036854775807},
        {"t": start, "o": "100", "h": "101", "l": "99",
         "c": "100", "v": "5", "n": 9223372036854775808},
    ]}})
    rejected = [0]

    parsed = corpus.parse_source_page(
        page, "SPY", rejection_counter=rejected,
    )

    assert [row.trade_count for row in parsed] == [9223372036854775807]
    assert rejected == [1]


def test_provider_decimals_are_bounded_to_postgresql_numeric() -> None:
    assert corpus._postgres_numeric_fits(Decimal("1e131071"))
    assert corpus._postgres_numeric_fits(Decimal("1e-16383"))
    assert corpus._postgres_numeric_fits(Decimal(0))
    assert not corpus._postgres_numeric_fits(Decimal("1e131072"))
    assert not corpus._postgres_numeric_fits(Decimal("1e-16384"))
    assert not corpus._postgres_numeric_fits(Decimal("0e-1000000"))

    start = "2025-01-02T14:30:00Z"
    valid = {
        "t": start, "o": "100", "h": "101", "l": "99",
        "c": "100", "v": "5", "vw": "100",
    }
    page = _raw_page({"bars": {"SPY": [
        valid,
        {**valid, "o": "1e1000000", "h": "1e1000000",
         "l": "1e1000000", "c": "1e1000000"},
        {**valid, "v": "1e1000000"},
        {**valid, "vw": "1e-1000000"},
    ]}})
    rejected = [0]

    parsed = corpus.parse_source_page(
        page, "SPY", rejection_counter=rejected,
    )

    assert len(parsed) == 1
    assert rejected == [3]
    assert corpus.canonical_bytes(Decimal("0e-1000000")) == b'"0"'
    oversized = Decimal("1e1000000")
    with pytest.raises(corpus.Hist8Error, match="numeric capacity"):
        corpus.canonical_bar(
            replace(
                _source_bar(datetime(2025, 1, 2, 14, 30, tzinfo=UTC)),
                open=oversized, high=oversized,
                low=oversized, close=oversized,
            ),
            session_date="2025-01-02",
            calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
            import_id="attempt", eligible=False,
        )


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
    with pytest.raises(corpus.Hist8Error, match="pagination resource mismatch"):
        corpus._strip_secret_query(
            "https://api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
            + "9" * 5000 + "/2026-09-01?cursor=next"
        )
    for malformed_url in (
        "https://api.massive.com:notaport/v2/aggs/ticker/I%3ACOMP/range/1/"
        "minute/2024-09-01/2026-09-01?cursor=next",
        "https://[api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
        "2024-09-01/2026-09-01?cursor=next",
    ):
        with pytest.raises(
            corpus.Hist8Error, match="pagination resource mismatch",
        ):
            corpus._strip_secret_query(malformed_url)

    endpoint, params = corpus._strip_secret_query(
        corpus.MASSIVE_URL + "?cursor=next&apiKey=must-not-be-retained"
    )
    assert endpoint == corpus.MASSIVE_URL
    assert params == {
        "sort": "asc", "limit": "50000", "cursor": "next",
    }
    provider_cursor_endpoint, provider_cursor_params = corpus._strip_secret_query(
        "https://api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
        "1725148860000/2026-09-01?cursor=opaque"
    )
    assert provider_cursor_endpoint.endswith(
        "/I%3ACOMP/range/1/minute/1725148860000/2026-09-01"
    )
    assert provider_cursor_params == {
        "sort": "asc", "limit": "50000", "cursor": "opaque",
    }
    normalized_endpoint, normalized_params = corpus._strip_secret_query(
        "https://api.massive.com/v2/aggs/ticker/I%3aCOMP/range/1/minute/"
        "2024-09-01/2026-09-01?cursor=opaque"
    )
    assert normalized_endpoint == corpus.MASSIVE_URL
    assert normalized_params == {
        "sort": "asc", "limit": "50000", "cursor": "opaque",
    }
    with pytest.raises(corpus.Hist8Error, match="parameter mismatch"):
        corpus._strip_secret_query(
            corpus.MASSIVE_URL + "?cursor=\ud800"
        )
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

    documented_response = _Response({
        "ticker": "I:COMP", "status": "OK", "results": [],
    })
    assert len(list(corpus.massive_pages(
        "key", opener=lambda *_args, **_kwargs: documented_response,
    ))) == 1

    page = corpus.RawPage(
        "MASSIVE", "I:COMP", "I:COMP minute index OHLC", ("NASDAQ",),
        corpus.MASSIVE_URL, dict(corpus.MASSIVE_FROZEN_PARAMS),
        datetime(2026, 9, 2, tzinfo=UTC), 200,
        "application/json", None,
        (b'{"ticker":"I:COMP","status":"OK",'
         b'"results":[{"t":1000.5,"o":1,'
         b'"h":1,"l":1,"c":1}]}'),
    )
    with pytest.raises(corpus.Hist8Error, match="timestamp is not an integer"):
        corpus.parse_source_page(page, "NASDAQ")


def test_nasdaq_ohlc_is_bound_as_index_points() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    page = _raw_page({
        "ticker": "I:COMP", "status": "OK",
        "results": [{
            "t": int(start.timestamp() * 1000),
            "o": "19000.1", "h": "19001.2", "l": "18999.9",
            "c": "19000.8",
        }],
    }, source="MASSIVE", instruments=("NASDAQ",))
    source = corpus.parse_source_page(page, "NASDAQ")[0]
    bar = corpus.canonical_bar(
        source, session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        calendar_id="NASDAQ_CASH_RTH", import_id="attempt", eligible=False,
    )
    assert bar.price_unit == "INDEX_POINTS"
    assert bar.volume is None
    assert bar.volume_unit == "NOT_APPLICABLE"

    failed = _raw_page(
        {"ticker": "I:COMP", "status": "ERROR", "results": []},
        source="MASSIVE", instruments=("NASDAQ",),
    )
    with pytest.raises(corpus.Hist8Error, match="response status mismatch"):
        corpus.parse_source_page(failed, "NASDAQ")


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


def test_truncated_gzip_is_contained_to_one_provider(monkeypatch) -> None:
    calls = []
    stored = []
    real_alpaca_pages = corpus.alpaca_pages
    response = _Response({})
    response._body = gzip.compress(b'{"bars":{}}')[:-4]
    response.headers = {
        "Content-Type": "application/json", "Content-Encoding": "gzip",
    }

    def alpaca(*_args, **_kwargs):
        calls.append("ALPACA")
        yield from real_alpaca_pages(
            "key", "secret", opener=lambda *_args, **_kwargs: response,
        )

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
            assert import_id == "gzip-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "gzip-attempt")

    assert calls == ["ALPACA", "COINBASE", "MASSIVE"]
    assert stored == ["ALPACA", "COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 8
    assert result["source_statuses"]["SPY"] == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 1, "failure_type": "Hist8Error",
        "reason": "provider response is not valid decimal JSON",
    }
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["NASDAQ"]["availability"] == "AVAILABLE"


def test_incomplete_http_read_is_contained_to_one_provider(monkeypatch) -> None:
    calls = []
    stored = []

    class TruncatedResponse(_Response):
        def read(self, _size: int = -1) -> bytes:
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


def test_oversized_raw_http_body_is_contained_to_one_provider(monkeypatch) -> None:
    stored = []
    real_alpaca_pages = corpus.alpaca_pages
    response = _Response({})
    response._body = b"x" * 33
    requested_sizes = []
    original_read = response.read

    def bounded_read(size: int = -1) -> bytes:
        requested_sizes.append(size)
        return original_read(size)

    response.read = bounded_read

    def alpaca(*_args, **_kwargs):
        yield from real_alpaca_pages(
            "key", "secret", opener=lambda *_args, **_kwargs: response,
        )

    def coinbase(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "massive"}, source="MASSIVE",
            instruments=("NASDAQ",),
        )

    class Store:
        def store_page(self, _import_id, sequence, page):
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "PROVIDER_RAW_BODY_MAX_BYTES", 32)
    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "raw-limit-attempt")

    assert requested_sizes == [33]
    assert stored == ["COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 2
    assert result["source_statuses"]["SPY"] == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 0, "failure_type": "Hist8Error",
        "reason": "provider response body exceeds raw byte limit",
    }
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["NASDAQ"]["availability"] == "AVAILABLE"


@pytest.mark.parametrize("content_encoding", ("gzip", "deflate"))
def test_oversized_decoded_http_body_is_contained_to_one_provider(
    monkeypatch, content_encoding,
) -> None:
    stored = []
    real_alpaca_pages = corpus.alpaca_pages
    decoded = json.dumps({
        "bars": {symbol: [] for symbol in corpus.EQUITIES},
        "padding": "x" * 128,
    }).encode()
    response = _Response({})
    response._body = (
        gzip.compress(decoded) if content_encoding == "gzip"
        else zlib.compress(decoded)
    )
    response.headers = {
        "Content-Type": "application/json",
        "Content-Encoding": content_encoding,
    }

    def alpaca(*_args, **_kwargs):
        yield from real_alpaca_pages(
            "key", "secret", opener=lambda *_args, **_kwargs: response,
        )

    def coinbase(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "massive"}, source="MASSIVE",
            instruments=("NASDAQ",),
        )

    class Store:
        def store_page(self, _import_id, sequence, page):
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "PROVIDER_DECODED_BODY_MAX_BYTES", 64)
    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "decoded-limit-attempt")

    assert stored == ["COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 2
    assert result["source_statuses"]["SPY"] == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 0, "failure_type": "Hist8Error",
        "reason": "provider decoded body exceeds byte limit",
    }
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["NASDAQ"]["availability"] == "AVAILABLE"


def test_malformed_http_status_line_is_contained_to_one_provider(monkeypatch) -> None:
    calls = []
    stored = []

    def malformed_status_line(*_args, **_kwargs):
        raise BadStatusLine("malformed status")

    def alpaca(*_args, **_kwargs):
        calls.append("ALPACA")
        corpus._http_get(
            corpus.ALPACA_URL, headers={}, opener=malformed_status_line,
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
            assert import_id == "protocol-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "protocol-attempt")

    assert calls == ["ALPACA", "COINBASE", "MASSIVE"]
    assert stored == ["COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 2
    assert result["source_statuses"]["SPY"] == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 0, "failure_type": "Hist8Error",
        "reason": "provider HTTP protocol failure",
    }
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["NASDAQ"]["availability"] == "AVAILABLE"


@pytest.mark.parametrize(("malformed_body", "expected_reasons"), (
    (
        b'{"bars":{},"next_page_token":' + b"9" * 5000 + b"}",
        {"provider response is not valid decimal JSON", "invalid Alpaca pagination"},
    ),
    (
        b"[" * 10000 + b"0" + b"]" * 10000,
        {"provider response is not valid decimal JSON", "malformed Alpaca page"},
    ),
))
def test_json_parser_limits_are_contained_to_one_provider(
    monkeypatch, malformed_body, expected_reasons,
) -> None:
    stored = []
    real_alpaca_pages = corpus.alpaca_pages

    class MalformedResponse:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __init__(self):
            self._offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size: int = -1):
            if size < 0:
                size = len(malformed_body) - self._offset
            start = self._offset
            self._offset = min(len(malformed_body), start + size)
            return malformed_body[start:self._offset]

    def alpaca(*_args, **_kwargs):
        yield from real_alpaca_pages(
            "key", "secret",
            opener=lambda *_args, **_kwargs: MalformedResponse(),
        )

    def coinbase(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "massive"}, source="MASSIVE",
            instruments=("NASDAQ",),
        )

    class Store:
        def store_page(self, import_id, sequence, page):
            assert import_id == "json-limit-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "json-limit-attempt")

    assert stored == ["ALPACA", "COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 8
    status = result["source_statuses"]["SPY"]
    assert {key: value for key, value in status.items() if key != "reason"} == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 1, "failure_type": "Hist8Error",
    }
    assert status["reason"] in expected_reasons
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["NASDAQ"]["availability"] == "AVAILABLE"


def test_massive_pagination_integer_limit_is_contained_to_one_provider(
    monkeypatch,
) -> None:
    stored = []
    real_massive_pages = corpus.massive_pages
    oversized_next_url = (
        "https://api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
        + "9" * 5000 + "/2026-09-01?cursor=next"
    )

    def alpaca(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "alpaca"}, instruments=corpus.EQUITIES,
        )

    def coinbase(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        yield from real_massive_pages(
            "key", opener=lambda *_a, **_k: _Response({
                "ticker": "I:COMP", "status": "OK", "results": [],
                "next_url": oversized_next_url,
            }),
        )

    class Store:
        def store_page(self, import_id, sequence, page):
            assert import_id == "massive-integer-limit-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "massive-integer-limit-attempt")

    assert stored == ["ALPACA", "COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 8
    assert result["source_statuses"]["NASDAQ"] == {
        "source": "MASSIVE", "availability": "UNAVAILABLE",
        "retrieval_associations": 1, "failure_type": "Hist8Error",
        "reason": "Massive pagination resource mismatch",
    }
    assert result["source_statuses"]["SPY"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"


@pytest.mark.parametrize(("malformed_next_url", "mismatch_kind"), (
    (
        "https://api.massive.com:notaport/v2/aggs/ticker/I%3ACOMP/range/1/"
        "minute/2024-09-01/2026-09-01?cursor=next",
        "resource",
    ),
    (
        "https://[api.massive.com/v2/aggs/ticker/I%3ACOMP/range/1/minute/"
        "2024-09-01/2026-09-01?cursor=next",
        "resource",
    ),
    (corpus.MASSIVE_URL + "?cursor=\ud800", "parameter"),
))
def test_massive_malformed_pagination_url_is_contained_to_one_provider(
    monkeypatch, malformed_next_url, mismatch_kind,
) -> None:
    stored = []
    real_massive_pages = corpus.massive_pages

    def alpaca(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "alpaca"}, instruments=corpus.EQUITIES,
        )

    def coinbase(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        yield from real_massive_pages(
            "key", opener=lambda *_a, **_k: _Response({
                "ticker": "I:COMP", "status": "OK", "results": [],
                "next_url": malformed_next_url,
            }),
        )

    class Store:
        def store_page(self, import_id, sequence, page):
            assert import_id == "massive-malformed-url-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "massive-malformed-url-attempt")

    assert stored == ["ALPACA", "COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 8
    assert result["source_statuses"]["NASDAQ"] == {
        "source": "MASSIVE", "availability": "UNAVAILABLE",
        "retrieval_associations": 1, "failure_type": "Hist8Error",
        "reason": f"Massive pagination {mismatch_kind} mismatch",
    }
    assert result["source_statuses"]["SPY"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"


def test_provider_request_parameter_encoding_failure_is_controlled() -> None:
    with pytest.raises(
        corpus.Hist8Error, match="request parameter encoding failure",
    ):
        corpus._build_page(
            source="ALPACA", feed="SIP", product="1Min trade OHLCV",
            instruments=corpus.EQUITIES, endpoint=corpus.ALPACA_URL,
            params={**corpus.ALPACA_FROZEN_PARAMS, "page_token": "\ud800"},
            headers={},
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("unencodable request reached opener")
            ),
            clock=lambda: datetime.now(UTC),
        )


def test_massive_normalized_request_loop_is_contained_to_one_provider(
    monkeypatch,
) -> None:
    stored = []
    calls = [0]
    real_massive_pages = corpus.massive_pages
    first_next_url = (
        corpus.MASSIVE_URL.replace("I%3A", "I%3a")
        + "?cursor=repeat&apiKey=first"
    )
    second_next_url = corpus.MASSIVE_URL + "?cursor=repeat&apiKey=second"
    assert corpus._strip_secret_query(first_next_url) == (
        corpus._strip_secret_query(second_next_url)
    )

    def alpaca(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "alpaca"}, instruments=corpus.EQUITIES,
        )

    def coinbase(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def opener(*_args, **_kwargs):
        calls[0] += 1
        if calls[0] == 1:
            next_url = first_next_url
        elif calls[0] == 2:
            next_url = second_next_url
        else:
            raise AssertionError("normalized Massive request was repeated")
        return _Response({
            "ticker": "I:COMP", "status": "OK", "results": [],
            "next_url": next_url,
        })

    def massive(*_args, **_kwargs):
        yield from real_massive_pages("key", opener=opener)

    class Store:
        def store_page(self, import_id, sequence, page):
            assert import_id == "massive-normalized-loop-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "massive-normalized-loop-attempt")

    assert calls == [2]
    assert stored == ["ALPACA", "COINBASE", "MASSIVE", "MASSIVE"]
    assert result["retrieval_associations"] == 9
    assert result["source_statuses"]["NASDAQ"] == {
        "source": "MASSIVE", "availability": "UNAVAILABLE",
        "retrieval_associations": 2, "failure_type": "Hist8Error",
        "reason": "invalid Massive pagination",
    }
    assert result["source_statuses"]["SPY"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"


def test_malformed_alpaca_page_shape_is_contained_to_one_provider(
    monkeypatch,
) -> None:
    stored = []
    real_alpaca_pages = corpus.alpaca_pages

    def alpaca(*_args, **_kwargs):
        yield from real_alpaca_pages(
            "key", "secret",
            opener=lambda *_args, **_kwargs: _Response({
                "bars": None, "next_page_token": None,
            }),
        )

    def coinbase(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "coinbase"}, source="COINBASE",
            instruments=("BTC-USD",),
        )

    def massive(*_args, **_kwargs):
        yield _raw_page(
            {"complete": "massive"}, source="MASSIVE",
            instruments=("NASDAQ",),
        )

    class Store:
        def store_page(self, import_id, sequence, page):
            assert import_id == "alpaca-shape-attempt"
            stored.append(page.source)
            return sequence + len(page.instruments)

    monkeypatch.setattr(corpus, "alpaca_pages", alpaca)
    monkeypatch.setattr(corpus, "coinbase_pages", coinbase)
    monkeypatch.setattr(corpus, "massive_pages", massive)
    result = corpus.acquire(Store(), "alpaca-shape-attempt")

    assert stored == ["ALPACA", "COINBASE", "MASSIVE"]
    assert result["retrieval_associations"] == 8
    assert result["source_statuses"]["SPY"] == {
        "source": "ALPACA", "availability": "UNAVAILABLE",
        "retrieval_associations": 1, "failure_type": "Hist8Error",
        "reason": "malformed Alpaca page",
    }
    assert result["source_statuses"]["BTC-USD"]["availability"] == "AVAILABLE"
    assert result["source_statuses"]["NASDAQ"]["availability"] == "AVAILABLE"

    with pytest.raises(corpus.Hist8Error, match="malformed Alpaca page"):
        list(real_alpaca_pages(
            "key", "secret",
            opener=lambda *_args, **_kwargs: _Response({
                "bars": {"SPY": {}}, "next_page_token": None,
            }),
        ))


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
        session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
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
        source, session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt-1", eligible=False,
    )
    reshuffled = replace(
        source, artifact_id="sha256:" + "c" * 64, locator="$[17]",
    )
    complete = corpus.canonical_bar(
        reshuffled, session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
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
        session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt", eligible=True,
    ) for index, volume in enumerate(volumes))
    derived = corpus.derive_session(
        minutes, "5m", "attempt", session_open=start,
    )[0]
    assert derived.volume == Decimal("10000000000000000000000000004")


def test_derived_volume_cannot_overflow_postgresql_numeric() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    volumes = [
        Decimal("9e131071"), Decimal("9e131071"),
        Decimal(0), Decimal(0), Decimal(0),
    ]
    minutes = tuple(corpus.canonical_bar(
        replace(_source_bar(start + timedelta(minutes=index)), volume=volume),
        session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt", eligible=True,
    ) for index, volume in enumerate(volumes))

    with pytest.raises(corpus.Hist8Error, match="derived volume"):
        corpus.derive_session(
            minutes, "5m", "attempt", session_open=start,
        )


def test_derived_trade_count_cannot_overflow_postgresql_bigint() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    counts = [9223372036854775807, 1, 0, 0, 0]
    minutes = tuple(corpus.canonical_bar(
        replace(
            _source_bar(start + timedelta(minutes=index)),
            trade_count=trade_count,
        ),
        session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt", eligible=True,
    ) for index, trade_count in enumerate(counts))

    with pytest.raises(corpus.Hist8Error, match="trade count"):
        corpus.derive_session(
            minutes, "5m", "attempt", session_open=start,
        )

    oversized = corpus._finish_bar(replace(
        minutes[0], trade_count=9223372036854775808,
    ))
    with pytest.raises(
        corpus.Hist8ConflictError, match="bar semantic identity mismatch",
    ):
        corpus._validate_bar_identity(oversized)


@pytest.mark.parametrize("mutation", (
    "open", "high", "low", "close", "volume", "trade_count", "vwap",
    "short_lineage", "reversed_lineage", "wrong_lineage_hash",
))
def test_independent_session_verifier_rejects_rehashed_derived_tampering(
    mutation,
) -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    minutes = tuple(corpus.canonical_bar(
        _source_bar(start + timedelta(minutes=index)),
        session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt", eligible=True,
    ) for index in range(5))
    derived = corpus.derive_session(
        minutes, "5m", "attempt", session_open=start,
    )[0]
    changes = {
        "open": {"open": Decimal("101")},
        "high": {"high": Decimal("104")},
        "low": {"low": Decimal("98")},
        "close": {"close": Decimal("101")},
        "volume": {"volume": Decimal("51")},
        "trade_count": {"trade_count": 11},
        "vwap": {"vwap": Decimal("101")},
        "short_lineage": {"lineage": derived.lineage[:-1]},
        "reversed_lineage": {"lineage": tuple(reversed(derived.lineage))},
        "wrong_lineage_hash": {
            "lineage": (*derived.lineage[:-1], "hist8bar:" + "c" * 64
                        + "|" + "d" * 64),
        },
    }[mutation]
    tampered = corpus._finish_bar(replace(derived, **changes))
    rows = (*minutes, tampered)
    with pytest.raises(
        corpus.Hist8ConflictError, match="derived aggregation mismatch",
    ):
        corpus._verify_materialized_session(
            rows, session_open=start,
            session_close=start + timedelta(minutes=5), expected_minutes=5,
            expected_session_date="2025-01-02",
            expected_calendar_id="US_CASH_RTH",
            expected_calendar_sha256=corpus.CALENDAR_SCHEDULE_SHA256,
        )


def test_independent_session_verifier_rejects_membership_and_eligibility_drift() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    minutes = tuple(corpus.canonical_bar(
        _source_bar(start + timedelta(minutes=index)),
        session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt", eligible=True,
    ) for index in range(5))
    derived = corpus.derive_session(
        minutes, "5m", "attempt", session_open=start,
    )[0]
    kwargs = {
        "session_open": start,
        "session_close": start + timedelta(minutes=5),
        "expected_minutes": 5,
        "expected_session_date": "2025-01-02",
        "expected_calendar_id": "US_CASH_RTH",
        "expected_calendar_sha256": corpus.CALENDAR_SCHEDULE_SHA256,
    }
    with pytest.raises(
        corpus.Hist8ConflictError, match="derived window membership mismatch",
    ):
        corpus._verify_materialized_session(minutes, **kwargs)
    with pytest.raises(
        corpus.Hist8ConflictError, match="incomplete session has derived bars",
    ):
        corpus._verify_materialized_session((
            *(replace(row, research_eligible=False) for row in minutes[:-1]),
            derived,
        ), **kwargs)
    with pytest.raises(
        corpus.Hist8ConflictError, match="canonical eligibility mismatch",
    ):
        corpus._verify_materialized_session(
            (replace(minutes[0], research_eligible=False), *minutes[1:], derived),
            **kwargs,
        )
    with pytest.raises(
        corpus.Hist8ConflictError, match="derived eligibility mismatch",
    ):
        corpus._verify_materialized_session(
            (*minutes, replace(derived, research_eligible=False)), **kwargs,
        )


@pytest.mark.parametrize("field,value", (
    ("calendar_id", "WRONG_CALENDAR"),
    ("calendar_sha256", "0" * 64),
    ("session_date", "2025-01-03"),
))
def test_independent_session_verifier_rejects_rehashed_calendar_drift(
    field, value,
) -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    row = corpus.canonical_bar(
        _source_bar(start), session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt", eligible=True,
    )
    tampered = corpus._finish_bar(replace(row, **{field: value}))
    with pytest.raises(
        corpus.Hist8ConflictError,
        match="(?:bar|materialized) calendar identity mismatch",
    ):
        corpus._verify_materialized_session(
            (tampered,), session_open=start,
            session_close=start + timedelta(minutes=1), expected_minutes=1,
            expected_session_date="2025-01-02",
            expected_calendar_id="US_CASH_RTH",
            expected_calendar_sha256=corpus.CALENDAR_SCHEDULE_SHA256,
        )


def test_independent_session_verifier_rejects_out_of_session_canonical_bar() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    row = corpus.canonical_bar(
        _source_bar(start + timedelta(days=1)), session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="attempt", eligible=False,
    )
    with pytest.raises(
        corpus.Hist8ConflictError, match="canonical session membership mismatch",
    ):
        corpus._verify_materialized_session(
            (row,), session_open=start,
            session_close=start + timedelta(minutes=1), expected_minutes=1,
            expected_session_date="2025-01-02",
            expected_calendar_id="US_CASH_RTH",
            expected_calendar_sha256=corpus.CALENDAR_SCHEDULE_SHA256,
        )


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

        def insert_bars(self, rows, **_kwargs):
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


def test_unavailable_source_materializes_valid_prefix_as_ineligible() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    first = _raw_page({
        "bars": {"SPY": [{
            "t": start.isoformat(), "o": 100, "h": 101, "l": 99,
            "c": 100, "v": 1,
        }]},
        "next_page_token": "page-2",
    })
    terminal = replace(
        _raw_page({"error": "unavailable"}),
        request_params={
            **corpus.ALPACA_FROZEN_PARAMS, "page_token": "page-2",
        },
        http_status=503,
    )

    class Store:
        inserted = []

        def retrieval_pages(self, *_args):
            yield first
            yield terminal

        def insert_bars(self, rows, **_kwargs):
            self.inserted.extend(rows)
            return len(rows), 0

    calendar = {
        "schedule_sha256": "b" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [{
            "date": "2025-01-02", "open_utc": "2025-01-02T14:30:00Z",
            "close_utc": "2025-01-02T14:31:00Z", "expected_minutes": 1,
        }],
    }
    store = Store()
    result = corpus.materialize_instrument(
        store, "source", "SPY", calendar, source_unavailable=True,
    )
    assert len(store.inserted) == 1
    assert store.inserted[0].timeframe == "1m"
    assert store.inserted[0].research_eligible is False
    assert result["verified_retrieval_associations"] == 2
    assert result["usable_retrieval_associations"] == 1
    assert result["source_chain_complete"] is False
    assert result["source_acquisition_incomplete_sessions"] == 1
    assert result["eligible_sessions"] == 0
    assert result["incomplete_sessions"] == 0


def test_unavailable_source_rejects_complete_or_post_terminal_chain() -> None:
    complete = _raw_page({"bars": {"SPY": []}, "next_page_token": None})
    terminal = replace(complete, http_status=503)

    class Store:
        def __init__(self, pages):
            self.pages = pages

        def retrieval_pages(self, *_args):
            yield from self.pages

        def insert_bars(self, *_args, **_kwargs):
            raise AssertionError("no bars should be inserted")

    calendar = {
        "schedule_sha256": "b" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [],
    }
    with pytest.raises(
        corpus.Hist8ConflictError,
        match="unavailable retained provider pagination is complete",
    ):
        corpus.materialize_instrument(
            Store((complete,)), "source", "SPY", calendar,
            source_unavailable=True,
        )
    with pytest.raises(
        corpus.Hist8ConflictError, match="retained provider pagination mismatch",
    ):
        corpus.materialize_instrument(
            Store((terminal, complete)), "source", "SPY", calendar,
            source_unavailable=True,
        )


def test_unavailable_source_keeps_rows_from_invalid_continuation_page() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    page = _raw_page({
        "bars": {"SPY": [{
            "t": (start + timedelta(minutes=index)).isoformat(),
            "o": 100, "h": 101, "l": 99, "c": 100, "v": 1,
        } for index in range(5)]},
        "next_page_token": 7,
    })

    class Store:
        inserted = []

        def retrieval_pages(self, *_args):
            yield page

        def insert_bars(self, rows, **kwargs):
            assert kwargs["source_chain_complete"] is False
            self.inserted.extend(rows)
            return len(rows), 0

    calendar = {
        "schedule_sha256": corpus.CALENDAR_SCHEDULE_SHA256,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [{
            "date": "2025-01-02", "open_utc": "2025-01-02T14:30:00Z",
            "close_utc": "2025-01-02T14:35:00Z", "expected_minutes": 5,
        }],
    }
    store = Store()
    result = corpus.materialize_instrument(
        store, "source", "SPY", calendar, source_unavailable=True,
    )
    assert len(store.inserted) == 5
    assert {row.timeframe for row in store.inserted} == {"1m"}
    assert not any(row.research_eligible for row in store.inserted)
    assert result["usable_retrieval_associations"] == 1
    assert result["source_acquisition_incomplete_sessions"] == 1
    assert result["source_excluded_5m_windows"] == 1


def test_materialization_rejects_noncontiguous_coinbase_pages() -> None:
    first = _raw_page([], source="COINBASE", instruments=("BTC-USD",))
    second = replace(first, request_params={
        "granularity": "60", "start": "2024-09-01T10:00:00Z",
        "end": "2024-09-01T15:00:00Z",
    })

    class Store:
        def retrieval_pages(self, *_args):
            yield first
            yield second

        def insert_bars(self, *_args, **_kwargs):
            raise AssertionError("pagination must fail before insertion")

    calendar = {
        "schedule_sha256": "d" * 64,
        "instrument_calendars": {"BTC-USD": "BTC_UTC_DAY"},
        "btc_utc_dates": [],
    }
    with pytest.raises(
        corpus.Hist8ConflictError, match="retained provider pagination mismatch",
    ):
        corpus.materialize_instrument(Store(), "source", "BTC-USD", calendar)


def test_materialization_rejects_incomplete_alpaca_page_chain() -> None:
    page = _raw_page({
        "bars": {"SPY": []}, "next_page_token": "missing-page",
    })

    class Store:
        def retrieval_pages(self, *_args):
            yield page

        def insert_bars(self, *_args, **_kwargs):
            raise AssertionError("empty pages must not insert")

    calendar = {
        "schedule_sha256": "d" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [],
    }
    with pytest.raises(
        corpus.Hist8ConflictError, match="retained provider pagination incomplete",
    ):
        corpus.materialize_instrument(Store(), "source", "SPY", calendar)


def test_identical_overlap_with_different_lineage_is_idempotent_provider_data() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    item = {"t": start.isoformat(), "o": 100, "h": 101, "l": 99,
            "c": 100, "v": 1}

    class Store:
        inserted = []

        def retrieval_pages(self, _import_id, _instrument):
            yield _raw_page({
                "bars": {"SPY": [item]}, "next_page_token": "page-2",
            })
            yield replace(
                _raw_page({"bars": {"SPY": [item]}, "page": 2}),
                request_params={
                    **corpus.ALPACA_FROZEN_PARAMS, "page_token": "page-2",
                },
            )

        def insert_bars(self, rows, **_kwargs):
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


def test_identical_overlap_after_session_flush_uses_stored_canonical_row() -> None:
    first = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    second = datetime(2025, 1, 3, 14, 30, tzinfo=UTC)

    def item(start):
        return {"t": start.isoformat(), "o": 100, "h": 101, "l": 99,
                "c": 100, "v": 1}

    class Store:
        canonical = {}

        def retrieval_pages(self, _import_id, _instrument):
            yield _raw_page({
                "bars": {"SPY": [item(first), item(second)]},
                "page": 1, "next_page_token": "page-2",
            })
            yield replace(
                _raw_page({
                    "bars": {"SPY": [item(first), item(second)]},
                    "page": 2,
                }),
                request_params={
                    **corpus.ALPACA_FROZEN_PARAMS, "page_token": "page-2",
                },
            )

        def insert_bars(self, rows, **_kwargs):
            for row in rows:
                if row.timeframe == "1m":
                    self.canonical[row.bar_start_utc] = (
                        corpus._source_bar_from_canonical(row)
                    )
            return len(rows), 0

        def stored_canonical_source_bar(
            self, instrument, session_date, start,
        ):
            assert instrument == "SPY"
            assert session_date == first.date().isoformat()
            return self.canonical[start]

    calendar = {
        "schedule_sha256": "d" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [
            {"date": first.date().isoformat(),
             "open_utc": first.isoformat().replace("+00:00", "Z"),
             "close_utc": (first + timedelta(minutes=1)).isoformat().replace(
                 "+00:00", "Z"
             ), "expected_minutes": 1},
            {"date": second.date().isoformat(),
             "open_utc": second.isoformat().replace("+00:00", "Z"),
             "close_utc": (second + timedelta(minutes=1)).isoformat().replace(
                 "+00:00", "Z"
             ), "expected_minutes": 1},
        ],
    }
    result = corpus.materialize_instrument(Store(), "source", "SPY", calendar)
    assert result["provider_duplicates"] == 2
    assert result["eligible_sessions"] == 2
    assert result["inserted"] == 2


def test_conflicting_rows_are_recorded_before_materialization_aborts() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    original = {"t": start.isoformat(), "o": 100, "h": 102, "l": 99,
                "c": 100, "v": 1}
    changed = {**original, "c": 101}

    class Store:
        conflicts = []

        def retrieval_pages(self, _import_id, _instrument):
            yield _raw_page({
                "bars": {"SPY": [original, changed]},
                "next_page_token": None,
            })

        def record_source_bar_conflict(self, **evidence):
            self.conflicts.append(evidence)

        def insert_bars(self, *_args, **_kwargs):
            raise AssertionError("conflicting rows must not be inserted")

    calendar = {
        "schedule_sha256": "d" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [{
            "date": "2025-01-02", "open_utc": "2025-01-02T14:30:00Z",
            "close_utc": "2025-01-02T14:31:00Z", "expected_minutes": 1,
        }],
    }
    store = Store()
    with pytest.raises(
        corpus.Hist8ConflictError, match="conflicting duplicate provider bar",
    ):
        corpus.materialize_instrument(store, "source", "SPY", calendar)
    assert len(store.conflicts) == 1
    conflict = store.conflicts[0]
    assert conflict["import_id"] == "source"
    assert conflict["session_date"] == "2025-01-02"
    assert conflict["existing"].locator == "$.bars.SPY[0]"
    assert conflict["candidate"].locator == "$.bars.SPY[1]"


def test_conflicting_overlap_after_session_flush_fails_closed() -> None:
    first = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    second = datetime(2025, 1, 3, 14, 30, tzinfo=UTC)
    original = {"t": first.isoformat(), "o": 100, "h": 102, "l": 99,
                "c": 100, "v": 1}
    changed = {**original, "c": 101}
    later = {"t": second.isoformat(), "o": 100, "h": 101, "l": 99,
             "c": 100, "v": 1}

    class Store:
        canonical = {}
        conflicts = []

        def retrieval_pages(self, _import_id, _instrument):
            yield _raw_page({
                "bars": {"SPY": [original, later]}, "page": 1,
                "next_page_token": "page-2",
            })
            yield replace(
                _raw_page({"bars": {"SPY": [changed]}, "page": 2}),
                request_params={
                    **corpus.ALPACA_FROZEN_PARAMS, "page_token": "page-2",
                },
            )

        def insert_bars(self, rows, **_kwargs):
            for row in rows:
                if row.timeframe == "1m":
                    self.canonical[row.bar_start_utc] = (
                        corpus._source_bar_from_canonical(row)
                    )
            return len(rows), 0

        def stored_canonical_source_bar(self, _instrument, _session, start):
            return self.canonical[start]

        def record_source_bar_conflict(self, **evidence):
            self.conflicts.append(evidence)

    calendar = {
        "schedule_sha256": "d" * 64,
        "instrument_calendars": {"SPY": "US_CASH_RTH"},
        "us_cash_sessions": [
            {"date": first.date().isoformat(),
             "open_utc": first.isoformat().replace("+00:00", "Z"),
             "close_utc": (first + timedelta(minutes=1)).isoformat().replace(
                 "+00:00", "Z"
             ), "expected_minutes": 1},
            {"date": second.date().isoformat(),
             "open_utc": second.isoformat().replace("+00:00", "Z"),
             "close_utc": (second + timedelta(minutes=1)).isoformat().replace(
                 "+00:00", "Z"
             ), "expected_minutes": 1},
        ],
    }
    store = Store()
    with pytest.raises(
        corpus.Hist8ConflictError, match="after session flush"
    ):
        corpus.materialize_instrument(store, "source", "SPY", calendar)
    assert len(store.conflicts) == 1
    assert store.conflicts[0]["existing"].close == Decimal("100")
    assert store.conflicts[0]["candidate"].close == Decimal("101")


def test_replay_pages_release_each_bounded_read_transaction() -> None:
    created_connections = []
    assert "cursor(name=" not in Path(
        "research/hist8/corpus.py"
    ).read_text(encoding="utf-8")
    retained = []
    for sequence in range(1, 10):
        body = json.dumps({"sequence": sequence}).encode()
        page = corpus.RawPage(
            "ALPACA", "SIP", "1Min trade OHLCV", ("SPY",),
            corpus.ALPACA_URL, dict(corpus.ALPACA_FROZEN_PARAMS),
            datetime(2026, 9, 2, tzinfo=UTC), 200, "application/json",
            None, body,
        )
        manifest_id = corpus._manifest_id(
            corpus._retrieval_manifest_payload(
                "source-import", sequence, page, "SPY",
            )
        )
        retained.append((
            manifest_id, corpus.CORPUS_ID, "source-import", "RETRIEVAL",
            sequence, "ALPACA", "SIP", "1Min trade OHLCV", "SPY",
            corpus.ALPACA_URL, dict(corpus.ALPACA_FROZEN_PARAMS),
            datetime(2026, 9, 2, tzinfo=UTC), 200, "application/json",
            None, "sha256:" + corpus.sha256(body), len(body), len(body), body,
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
                self.rows = [(
                    corpus.IMPORTER_ROLE, corpus.DATABASE_NAME,
                    "origin", "off", "UTC",
                )]
            elif "select max(sequence_no)" in query:
                self.rows = [(retained[-1][4],)]
            elif "m.sequence_no>%s" in query:
                last_sequence, upper_sequence, limit = params[3:]
                self.rows = [
                    row for row in retained
                    if last_sequence < row[4] <= upper_sequence
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
    retained[0] = (*retained[0][:9], "https://tampered.invalid",
                   *retained[0][10:])
    with pytest.raises(
        corpus.Hist8ConflictError, match="retrieval manifest identity"
    ):
        list(corpus.Hist8Store(connection_factory).retrieval_pages(
            "source-import", "SPY",
        ))


def test_identical_insert_race_uses_actual_affected_row_count(monkeypatch) -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    row = corpus.canonical_bar(
        _source_bar(start), session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="race-attempt", eligible=True,
    )
    state = {"bar_selects": 0}
    winning = replace(row, import_id="winning-attempt")
    stored_record = list(corpus._bar_values(winning))
    stored_record[-1] = list(winning.lineage)
    monkeypatch.setattr(
        corpus.Hist8Store, "_verify_canonical_provenance",
        lambda _self, _cursor, _rows: None,
    )

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
                self.rows = [(
                    corpus.IMPORTER_ROLE, corpus.DATABASE_NAME,
                    "origin", "off", "UTC",
                )]
            elif "select bar_id,content_hash,corpus_id" in query:
                state["bar_selects"] += 1
                self.rows = (
                    [] if state["bar_selects"] == 1
                    else [tuple(stored_record)]
                )
            elif ("select manifest_id,corpus_id,import_id,manifest_kind"
                  in query and "manifest_kind='SNAPSHOT_MEMBER'" in query):
                sequence = corpus._membership_sequence(row)
                payload = corpus._snapshot_member_manifest_payload(
                    row.import_id, sequence, row.instrument, row.timeframe,
                    row.bar_start_utc, row.bar_id, row.content_hash,
                    corpus._bar_provenance_hash(winning),
                    row.research_eligible,
                )
                self.rows = [(
                    corpus._manifest_id(payload), corpus.CORPUS_ID,
                    row.import_id, "SNAPSHOT_MEMBER", sequence,
                    row.instrument, row.timeframe, row.bar_start_utc,
                    row.bar_id, row.content_hash,
                    corpus._bar_provenance_hash(winning),
                    row.research_eligible,
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
    assert store.insert_bars(
        (row,), session_open=start,
        session_close=start + timedelta(minutes=1), expected_minutes=1,
        expected_session_date=row.session_date,
        expected_calendar_id=row.calendar_id,
        expected_calendar_sha256=row.calendar_sha256,
    ) == (0, 1)


def test_insert_recomputes_stored_bar_hash() -> None:
    row = corpus.canonical_bar(
        _source_bar(datetime(2025, 1, 2, 14, 30, tzinfo=UTC)),
        session_date="2025-01-02",
        calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
        import_id="source-attempt", eligible=True,
    )
    corrupted = list(corpus._bar_values(row))
    corrupted[13] = Decimal("101")
    corrupted[-1] = list(row.lineage)

    class Cursor:
        rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            if ("select current_user" in query
                    and "current_database()" in query):
                self.rows = [(
                    corpus.IMPORTER_ROLE, corpus.DATABASE_NAME,
                    "origin", "off", "UTC",
                )]
            elif "select bar_id,content_hash,corpus_id" in query:
                self.rows = [tuple(corrupted)]
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

    with pytest.raises(corpus.Hist8ConflictError, match="stored bar identity"):
        corpus.Hist8Store(Connection).insert_bars(
            (row,), session_open=row.bar_start_utc,
            session_close=row.bar_end_utc, expected_minutes=1,
            expected_session_date=row.session_date,
            expected_calendar_id=row.calendar_id,
            expected_calendar_sha256=row.calendar_sha256,
        )


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
                self.rows = [(
                    corpus.IMPORTER_ROLE, corpus.DATABASE_NAME,
                    "origin", "off", "UTC",
                )]
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


def test_attempt_manifest_conflict_is_committed_then_verified(monkeypatch) -> None:
    import_id = "attempt-integrity"
    metadata = {
        "authorization": "ATOM-HIST8-CORPUS-AMENDMENT-1",
        "project_ref": corpus.PROJECT_REF,
    }
    payload = {
        "corpus_id": corpus.CORPUS_ID, "import_id": import_id,
        "kind": "IMPORT_ATTEMPT", "sequence_no": 0,
        "metadata": metadata,
    }
    events = []

    class Cursor:
        rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            events.append((query, params))
            if "select manifest_id,corpus_id,import_id,manifest_kind" in query:
                self.rows = [(
                    corpus._manifest_id(payload), corpus.CORPUS_ID,
                    import_id, "IMPORT_ATTEMPT", 0,
                    {**metadata, "project_ref": "corrupted-project"},
                )]

        def fetchall(self):
            return list(self.rows)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

        def commit(self):
            events.append(("COMMIT", None))

    store = corpus.Hist8Store(Connection)
    monkeypatch.setattr(store, "_verify", lambda _connection: None)

    with pytest.raises(
        corpus.Hist8ConflictError, match="attempt manifest readback mismatch",
    ):
        store.add_attempt(import_id, "IMPORT_ATTEMPT", metadata)

    assert any(query == "COMMIT" for query, _params in events)


def test_replay_membership_mismatch_precedes_snapshot_write(monkeypatch) -> None:
    events = []

    class Cursor:
        rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            events.append((query, params))
            if "select max(sequence_no)" in query:
                self.rows = [(None,)]
            elif "pg_advisory_unlock" in query:
                self.rows = [(True,)]

        def fetchone(self):
            return self.rows[0]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

        def commit(self):
            events.append(("COMMIT", None))

        def rollback(self):
            events.append(("ROLLBACK", None))

        def close(self):
            events.append(("CLOSE", None))

    store = corpus.Hist8Store(Connection)
    monkeypatch.setattr(store, "_verify", lambda _connection: None)
    monkeypatch.setattr(
        store, "_verify_snapshot_derivations",
        lambda _import_id, _source_statuses=None: None,
    )

    with pytest.raises(
        corpus.Hist8ConflictError,
        match="replay membership differs from sealed source snapshot",
    ):
        store.seal_snapshot(
            "replay-attempt", {},
            expected_membership_sha256="a" * 64,
        )

    assert not any(
        "insert into atom_research_history.manifests" in query.lower()
        for query, _params in events if isinstance(query, str)
    )


def test_snapshot_derivation_validation_precedes_seal_write(monkeypatch) -> None:
    events = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, params=None):
            events.append((query, params))

        def fetchone(self):
            return (True,)

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            events.append(("COMMIT", None))

        def rollback(self):
            events.append(("ROLLBACK", None))

        def close(self):
            events.append(("CLOSE", None))

    store = corpus.Hist8Store(Connection)
    monkeypatch.setattr(store, "_verify", lambda _connection: None)
    monkeypatch.setattr(
        store, "_verify_snapshot_derivations",
        lambda _import_id, _source_statuses=None: (_ for _ in ()).throw(
            corpus.Hist8ConflictError("derived seal mismatch")
        ),
    )
    with pytest.raises(corpus.Hist8ConflictError, match="derived seal mismatch"):
        store.seal_snapshot("attempt", {})
    assert not any(
        "insert into atom_research_history.manifests" in query.lower()
        for query, _params in events if isinstance(query, str)
    )
    assert any("pg_advisory_unlock" in query for query, _params in events)


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
    assert "timezone=UTC" in corpus.IMPORTER_SESSION_OPTIONS


@pytest.mark.parametrize(
    ("replication_role", "lo_compat_privileges", "session_timezone"),
    (
        ("replica", "off", "UTC"),
        ("local", "off", "UTC"),
        ("origin", "on", "UTC"),
        ("origin", "off", "America/New_York"),
    ),
)
def test_store_rejects_unsafe_database_session(
    replication_role, lo_compat_privileges, session_timezone,
) -> None:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query):
            return None

        def fetchone(self):
            return (
                corpus.IMPORTER_ROLE, corpus.DATABASE_NAME, replication_role,
                lo_compat_privileges, session_timezone,
            )

    class Connection:
        def cursor(self):
            return Cursor()

    with pytest.raises(corpus.Hist8Error, match="database identity mismatch"):
        corpus.Hist8Store._verify(Connection())


def test_schema_installer_verifies_direct_tls_endpoint_before_sql(
    monkeypatch, tmp_path,
) -> None:
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

    schema_bytes = Path("research/hist8/schema.sql").read_bytes()
    installer_identity = {
        **TEST_CODE_IDENTITY,
        "files": {
            **TEST_CODE_IDENTITY["files"],
            "research/hist8/schema.sql": {
                "git_blob": "c" * 40,
                "sha256": corpus.sha256(schema_bytes),
                "byte_length": len(schema_bytes),
            },
        },
    }
    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: installer_identity,
    )
    result = corpus.install_schema(
        Connection(), expected_implementation_commit="f" * 40,
    )
    assert result["project_ref"] == corpus.PROJECT_REF
    assert result["implementation_commit"] == "f" * 40
    assert "pg_stat_ssl" in events[0][0]
    assert "set_config('atom.hist8_verified_project_ref'" in events[1][0]
    assert events[1][1] == (corpus.PROJECT_REF,)
    assert "CREATE ROLE atom_hist8_importer" in events[2][0]

    with pytest.raises(corpus.Hist8Error, match="endpoint identity"):
        corpus.install_schema(
            Connection(host="wrong.example"),
            expected_implementation_commit="f" * 40,
        )

    substituted = tmp_path / "schema.sql"
    substituted.write_text(
        "-- ATOM-HIST8-CORPUS-AMENDMENT-1\n"
        "BEGIN; SELECT 'unreviewed'; COMMIT;\n",
        encoding="utf-8",
    )
    event_count = len(events)
    with pytest.raises(corpus.Hist8Error, match="schema artifact mismatch"):
        corpus.install_schema(
            Connection(), expected_implementation_commit="f" * 40,
            schema_path=substituted,
        )
    assert len(events) == event_count

    bad_identity = {
        **installer_identity,
        "files": {
            **installer_identity["files"],
            "research/hist8/schema.sql": {
                **installer_identity["files"]["research/hist8/schema.sql"],
                "sha256": "0" * 64,
            },
        },
    }
    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: bad_identity,
    )

    class NoCursorConnection(Connection):
        def cursor(self):
            raise AssertionError("identity mismatch must precede cursor use")

    with pytest.raises(corpus.Hist8Error, match="schema artifact mismatch"):
        corpus.install_schema(
            NoCursorConnection(), expected_implementation_commit="f" * 40,
        )

    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: installer_identity,
    )
    with pytest.raises(
        corpus.Hist8Error, match="reviewed implementation commit mismatch",
    ):
        corpus.install_schema(
            NoCursorConnection(), expected_implementation_commit="e" * 40,
        )


def test_execute_rejects_unreviewed_commit_before_database_access(monkeypatch) -> None:
    monkeypatch.setattr(corpus, "load_calendar", lambda **_kwargs: {})
    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: TEST_CODE_IDENTITY,
    )
    monkeypatch.setattr(
        corpus.Hist8Store, "from_environment",
        classmethod(lambda _cls: (_ for _ in ()).throw(
            AssertionError("commit mismatch must precede database access")
        )),
    )
    with pytest.raises(
        corpus.Hist8Error, match="reviewed implementation commit mismatch",
    ):
        corpus.execute(
            "attempt", expected_implementation_commit="e" * 40,
        )


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

    class Store:
        attempts = []
        seal_inputs = []

        def sealed_snapshot_state(self, import_id):
            assert import_id == "source-attempt"
            return {
                "manifest_id": "sha256:" + "d" * 64,
                "membership_sha256": "a" * 64,
                "metadata": {
                    "code_identity": TEST_CODE_IDENTITY,
                    "source_statuses": statuses,
                },
            }

        def add_attempt(self, import_id, kind, metadata):
            self.attempts.append((import_id, kind, metadata))

        def retrieval_pages(self, import_id, instrument):
            raise AssertionError((import_id, instrument))
            return iter(())

        def seal_snapshot(
            self, import_id, metadata, *, expected_membership_sha256=None,
        ):
            self.seal_inputs.append((
                import_id, metadata, expected_membership_sha256,
            ))
            raise corpus.Hist8ConflictError(
                "replay membership differs from sealed source snapshot"
            )

    store = Store()
    monkeypatch.setattr(
        corpus.Hist8Store, "from_environment", classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(corpus, "load_calendar", lambda **_kwargs: {
        "schedule_sha256": "c" * 64,
    })
    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: TEST_CODE_IDENTITY,
    )
    monkeypatch.setattr(
        corpus, "materialize_instrument",
        lambda _store, _source, instrument, _calendar, **_kwargs: (
            materialized.append((
                instrument, _kwargs.get("source_unavailable"),
            )) or {
                "inserted": 0, "verified_retrieval_associations": 0,
            }
        ),
    )
    with pytest.raises(corpus.Hist8ConflictError, match="differs from sealed"):
        corpus.execute(
            "source-attempt", expected_implementation_commit="f" * 40,
            acquire_sources=False,
        )
    assert store.attempts[0][1] == "REPLAY_ATTEMPT"
    assert store.attempts[0][2]["expected_membership_sha256"] == "a" * 64
    assert store.attempts[0][2]["source_snapshot_manifest_id"] == (
        "sha256:" + "d" * 64
    )
    assert store.attempts[0][2]["code_identity"] == TEST_CODE_IDENTITY
    assert store.seal_inputs[0][2] == "a" * 64
    assert materialized == [
        (instrument, instrument == "NASDAQ")
        for instrument in corpus.INSTRUMENTS
    ]


def test_replay_rejects_different_execution_code_identity(monkeypatch) -> None:
    source_identity = {
        **TEST_CODE_IDENTITY,
        "implementation_commit": "e" * 40,
    }

    class Store:
        def sealed_snapshot_state(self, import_id):
            assert import_id == "source-attempt"
            return {
                "manifest_id": "sha256:" + "d" * 64,
                "membership_sha256": "a" * 64,
                "metadata": {"code_identity": source_identity},
            }

        def add_attempt(self, *_args, **_kwargs):
            raise AssertionError("identity mismatch must precede replay writes")

    monkeypatch.setattr(
        corpus.Hist8Store, "from_environment",
        classmethod(lambda _cls: Store()),
    )
    monkeypatch.setattr(corpus, "load_calendar", lambda **_kwargs: {
        "schedule_sha256": "c" * 64,
    })
    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: TEST_CODE_IDENTITY,
    )

    with pytest.raises(
        corpus.Hist8ConflictError, match="code identity differs",
    ):
        corpus.execute(
            "source-attempt", expected_implementation_commit="f" * 40,
            acquire_sources=False,
        )


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
            yield replace(
                _raw_page(
                    {"partial": "massive"}, source="MASSIVE",
                    instruments=("NASDAQ",),
                ),
                http_status=403,
            )

        def seal_snapshot(
            self, import_id, metadata, *, expected_membership_sha256=None,
        ):
            assert expected_membership_sha256 is None
            self.snapshots.append((import_id, metadata))
            return "e" * 64

    store = Store()
    materialized = []
    monkeypatch.setattr(
        corpus.Hist8Store, "from_environment", classmethod(lambda _cls: store),
    )
    monkeypatch.setattr(corpus, "load_calendar", lambda **_kwargs: {
        "schedule_sha256": "c" * 64,
    })
    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: TEST_CODE_IDENTITY,
    )
    monkeypatch.setattr(corpus, "acquire", lambda *_args: {
        "retrieval_associations": 8, "source_statuses": statuses,
    })
    monkeypatch.setattr(
        corpus, "materialize_instrument",
        lambda _store, _source, instrument, _calendar, **_kwargs: (
            materialized.append((
                instrument, _kwargs.get("source_unavailable"),
            )) or {
                "inserted": 3, "verified_retrieval_associations": 1,
            }
        ),
    )

    result = corpus.execute(
        "partial-source", expected_implementation_commit="f" * 40,
        acquire_sources=True,
    )

    assert result["membership_sha256"] == "e" * 64
    assert materialized == [
        (instrument, instrument == "NASDAQ")
        for instrument in corpus.INSTRUMENTS
    ]
    assert result["instrument_results"]["NASDAQ"]["inserted"] == 3
    assert result["instrument_results"]["NASDAQ"]["availability"] == "UNAVAILABLE"
    snapshot_metadata = store.snapshots[0][1]
    assert snapshot_metadata["retrieval_associations"] == 8
    assert snapshot_metadata["source_statuses"] == statuses
    assert snapshot_metadata["code_identity"] == TEST_CODE_IDENTITY
    assert store.attempts[0][2]["code_identity"] == TEST_CODE_IDENTITY


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
                "metadata": {
                    "code_identity": TEST_CODE_IDENTITY,
                    "source_statuses": statuses,
                },
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
    monkeypatch.setattr(corpus, "load_calendar", lambda **_kwargs: {
        "schedule_sha256": "c" * 64,
    })
    monkeypatch.setattr(
        corpus, "_execution_code_identity", lambda: TEST_CODE_IDENTITY,
    )
    def materialize(store, source_import_id, instrument, *_args, **_kwargs):
        if instrument == "NASDAQ":
            tuple(store.retrieval_pages(source_import_id, instrument))
        return {"inserted": 0, "verified_retrieval_associations": 0}

    monkeypatch.setattr(corpus, "materialize_instrument", materialize)
    with pytest.raises(
        corpus.Hist8ConflictError, match="artifact replay mismatch"
    ):
        corpus.execute(
            "partial-source", expected_implementation_commit="f" * 40,
            acquire_sources=False,
        )


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
    assert "HIST8_FUTURE_ROUTINE_DEFAULT_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_FUTURE_TABLE_DEFAULT_BOUNDARY_UNSATISFIED" in sql
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
    assert "member_provenance_hash text" in sql
    assert "HIST8_EXISTING_INSTALLATION_ROLE_MISMATCH" in sql
    assert "pg_get_functiondef(routine.oid)" in sql
    assert "column_object.attnotnull" in sql
    assert "pg_get_indexdef(index_object.oid)" in sql
    assert "pg_get_triggerdef(trigger_object.oid, true)" in sql
    assert "trigger_object.tgisinternal" in sql
    assert "FROM pg_rewrite rewrite_object" in sql
    assert "manifests_import_id_sequence_no_manifest_kind_key" in sql
    assert "hist8_retrieval_source_identity" in sql
    assert "hist8_bar_source_identity" in sql
    assert "hist8_bar_calendar_identity" in sql
    assert "hist8_bar_price_unit_semantics" in sql
    assert "price_unit text NOT NULL" in sql
    assert "currency text NOT NULL" not in sql
    assert "pg_parameter_acl" in sql
    assert "edge.is_grantable" in sql
    assert "FROM pg_shdepend dependency" in sql
    assert "pg_publication_namespace" in sql
    assert "pg_subscription_rel" in sql
    assert "has_foreign_data_wrapper_privilege" in sql
    assert "HIST8_FUTURE_SEQUENCE_DEFAULT_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_FUTURE_SCHEMA_DEFAULT_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_CUSTOM_CATALOG_ROUTINE_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_CUSTOM_CATALOG_RELATION_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_CUSTOM_CATALOG_SEQUENCE_BOUNDARY_UNSATISFIED" in sql
    assert "membership.grantor = 10::oid" in sql
    assert "AND NOT membership.inherit_option" in sql
    assert "AND NOT membership.set_option" in sql
    assert "HIST8_LO_COMPAT_PRIVILEGES_BOUNDARY_UNSATISFIED" in sql
    assert "HIST8_MAINTAIN_PRIVILEGE_BOUNDARY_UNSATISFIED" in sql


def test_schema_enforces_importer_boundary_in_postgres(monkeypatch) -> None:
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
    lo_compat_database_set = False
    large_object_create_routines = []
    future_table_default_roles = []
    future_routine_default_roles = []
    restore_public_sequence_default = False
    restore_public_schema_default = False
    with psycopg.connect(dsn, autocommit=True) as connection:
        test_host = str(connection.info.host or "")
        if test_host not in {
            "localhost", "127.0.0.1", "::1", "postgres",
        } and not test_host.startswith("/"):
            pytest.fail("H2C_TEST_DATABASE_URL must target disposable local PostgreSQL")
        with connection.cursor() as preflight_cursor:
            preflight_cursor.execute(
                """select current_user = 'postgres',
                          current_database() = 'postgres',
                          not exists (
                            select 1 from pg_roles
                            where rolname::text = any(%s::text[])
                          ),
                          to_regnamespace('atom_research_history') is null,
                          to_regnamespace('hist8_visible') is null,
                          to_regclass('public.coin_v8_market_bars') is null,
                          to_regclass('public.coin_v8_ai_decision_logs') is null,
                          to_regclass('public.hist8_column_forbidden') is null,
                          to_regclass('public.hist8_trigger_forbidden') is null,
                          to_regclass('public.hist8_forbidden_sequence') is null,
                          to_regprocedure('public.hist8_callable()') is null,
                          to_regprocedure(
                            'information_schema.hist8_escape()'
                          ) is null,
                          to_regclass(
                            'information_schema.hist8_escape_view'
                          ) is null,
                          to_regclass(
                            'information_schema.hist8_escape_seq'
                          ) is null,
                          current_setting('lo_compat_privileges') = 'off',
                          not exists (
                            select 1
                            from pg_db_role_setting setting
                            cross join lateral
                              unnest(setting.setconfig) config(value)
                            where setting.setrole=0
                              and setting.setdatabase in (
                                0, (select oid from pg_database
                                    where datname=current_database())
                              )
                              and split_part(config.value,'=',1)=
                                'lo_compat_privileges'
                          ),
                          not exists (
                            select 1 from pg_publication
                            where pubname in ('hist8_all','hist8_explicit')
                          ),
                          not exists (
                            select 1 from pg_foreign_data_wrapper
                            where fdwname = 'hist8_fdw'
                          )""",
                (list(managed_roles),),
            )
            if not all(preflight_cursor.fetchone()):
                pytest.fail(
                    "H2C_TEST_DATABASE_URL is not a pristine disposable database"
                )
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
                    """select role.rolname, exists (
                         select 1
                         from unnest(coalesce(defaults.defaclacl,
                           acldefault('r',role.oid))) entry(aclitem)
                         cross join lateral
                           aclexplode(array[entry.aclitem]) acl
                         where acl.grantee=0
                           and acl.privilege_type='SELECT'
                       )
                       from pg_roles role
                       left join pg_default_acl defaults
                         on defaults.defaclrole=role.oid
                        and defaults.defaclnamespace=0
                        and defaults.defaclobjtype='r'
                       where role.rolsuper
                          or role.rolname='pg_database_owner'
                       order by role.rolname"""
                )
                future_table_default_roles = cursor.fetchall()
                assert future_table_default_roles
                for role, _was_public in future_table_default_roles:
                    cursor.execute(
                        pgsql.SQL(
                            "alter default privileges for role {} "
                            "grant select on tables to public"
                        ).format(pgsql.Identifier(role))
                    )
                with pytest.raises(
                    psycopg.Error, match="FUTURE_TABLE_DEFAULT_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                for role, _was_public in future_table_default_roles:
                    cursor.execute(
                        pgsql.SQL(
                            "alter default privileges for role {} "
                            "revoke select on tables from public"
                        ).format(pgsql.Identifier(role))
                    )

                cursor.execute(
                    """select role.rolname, exists (
                         select 1
                         from aclexplode(coalesce(defaults.defaclacl,
                           acldefault('f',role.oid))) acl
                         where acl.grantee=0
                           and acl.privilege_type='EXECUTE'
                       )
                       from pg_roles role
                       left join pg_default_acl defaults
                         on defaults.defaclrole=role.oid
                        and defaults.defaclnamespace=0
                        and defaults.defaclobjtype='f'
                       where role.rolsuper
                          or role.rolname='pg_database_owner'
                       order by role.rolname"""
                )
                future_routine_default_roles = cursor.fetchall()
                assert future_routine_default_roles
                for role, _was_public in future_routine_default_roles:
                    cursor.execute(
                        pgsql.SQL(
                            "alter default privileges for role {} "
                            "grant execute on functions to public"
                        ).format(pgsql.Identifier(role))
                    )
                with pytest.raises(
                    psycopg.Error, match="FUTURE_ROUTINE_DEFAULT_BOUNDARY"
                ):
                    cursor.execute(sql)
                connection.rollback()
                for role, _was_public in future_routine_default_roles:
                    cursor.execute(
                        pgsql.SQL(
                            "alter default privileges for role {} "
                            "revoke execute on functions from public"
                        ).format(pgsql.Identifier(role))
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
                cursor.execute(
                    "grant execute on function "
                    "extensions.hist8_extension_callable() to public"
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
                cursor.execute(
                    "grant execute on function public.hist8_callable() to public"
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

                cursor.execute("create publication hist8_all for all tables")
                with pytest.raises(
                    psycopg.Error, match="REPLICATION_BOUNDARY_UNSATISFIED",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop publication hist8_all")

                cursor.execute(
                    "create foreign data wrapper hist8_fdw no handler"
                )
                cursor.execute(
                    "grant usage on foreign data wrapper hist8_fdw to public"
                )
                with pytest.raises(
                    psycopg.Error, match="FOREIGN_SERVER_BOUNDARY_UNSATISFIED",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop foreign data wrapper hist8_fdw")

                cursor.execute(
                    "select exists (select 1 from pg_default_acl defaults "
                    "cross join lateral aclexplode(defaults.defaclacl) acl "
                    "where defaults.defaclrole='postgres'::regrole "
                    "and defaults.defaclnamespace=0 "
                    "and defaults.defaclobjtype='S' and acl.grantee=0 "
                    "and acl.privilege_type='USAGE')"
                )
                restore_public_sequence_default = cursor.fetchone()[0]
                cursor.execute(
                    "alter default privileges for role postgres "
                    "grant usage on sequences to public"
                )
                with pytest.raises(
                    psycopg.Error, match="FUTURE_SEQUENCE_DEFAULT_BOUNDARY",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke usage on sequences from public"
                )

                cursor.execute(
                    "select exists (select 1 from pg_default_acl defaults "
                    "cross join lateral aclexplode(defaults.defaclacl) acl "
                    "where defaults.defaclrole='postgres'::regrole "
                    "and defaults.defaclnamespace=0 "
                    "and defaults.defaclobjtype='n' and acl.grantee=0 "
                    "and acl.privilege_type='USAGE')"
                )
                restore_public_schema_default = cursor.fetchone()[0]
                cursor.execute(
                    "alter default privileges for role postgres "
                    "grant usage on schemas to public"
                )
                with pytest.raises(
                    psycopg.Error, match="FUTURE_SCHEMA_DEFAULT_BOUNDARY",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke usage on schemas from public"
                )

                cursor.execute(
                    "create function information_schema.hist8_escape() "
                    "returns bigint "
                    "language sql security definer set search_path=pg_catalog "
                    "as 'select count(*) from public.coin_v8_market_bars'"
                )
                cursor.execute(
                    "grant execute on function "
                    "information_schema.hist8_escape() to public"
                )
                with pytest.raises(
                    psycopg.Error, match="CUSTOM_CATALOG_ROUTINE_BOUNDARY",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "drop function information_schema.hist8_escape()"
                )

                cursor.execute(
                    "create view information_schema.hist8_escape_view as "
                    "select id from public.coin_v8_market_bars"
                )
                cursor.execute(
                    "grant select on "
                    "information_schema.hist8_escape_view to public"
                )
                with pytest.raises(
                    psycopg.Error, match="CUSTOM_CATALOG_RELATION_BOUNDARY",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "drop view information_schema.hist8_escape_view"
                )

                cursor.execute(
                    "create sequence information_schema.hist8_escape_seq"
                )
                cursor.execute(
                    "grant usage, select, update on sequence "
                    "information_schema.hist8_escape_seq to public"
                )
                with pytest.raises(
                    psycopg.Error, match="CUSTOM_CATALOG_SEQUENCE_BOUNDARY",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "drop sequence information_schema.hist8_escape_seq"
                )

                cursor.execute(sql)
                # An ambiguous disconnect after COMMIT can be retried without
                # mutating the exact prior installation.
                cursor.execute(sql)

                # PostgreSQL 16+ creates this administration-only edge when a
                # non-superuser CREATEROLE installer creates the importer.
                # Reproduce it under the bootstrap-superuser fixture: the
                # exact edge is accepted, but any SET capability is rejected.
                cursor.execute(
                    "grant atom_hist8_importer to postgres with "
                    "admin true, inherit false, set false"
                )
                cursor.execute(sql)
                cursor.execute(
                    "grant atom_hist8_importer to postgres with set true"
                )
                with pytest.raises(
                    psycopg.Error, match="EXISTING_INSTALLATION_ROLE_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "revoke atom_hist8_importer from postgres"
                )
                cursor.execute(sql)

                cursor.execute(
                    "select lo_from_bytea(0, decode('deadbeef','hex'))"
                )
                large_object_oid = cursor.fetchone()[0]
                cursor.execute(
                    pgsql.SQL(
                        "alter database {} set lo_compat_privileges=on"
                    ).format(pgsql.Identifier(current_database_name))
                )
                lo_compat_database_set = True
                with pytest.raises(
                    psycopg.Error, match="LO_COMPAT_PRIVILEGES_BOUNDARY",
                ):
                    cursor.execute(sql)
                connection.rollback()
                with psycopg.connect(dsn, autocommit=True) as bypass_connection:
                    with bypass_connection.cursor() as bypass_cursor:
                        bypass_cursor.execute("set role atom_hist8_importer")
                        bypass_cursor.execute(
                            "select lo_get(%s)", (large_object_oid,),
                        )
                        assert bytes(bypass_cursor.fetchone()[0]) == bytes.fromhex(
                            "deadbeef"
                        )
                cursor.execute(
                    pgsql.SQL(
                        "alter database {} reset lo_compat_privileges"
                    ).format(pgsql.Identifier(current_database_name))
                )
                lo_compat_database_set = False
                cursor.execute(sql)
                with psycopg.connect(dsn, autocommit=True) as safe_connection:
                    with safe_connection.cursor() as safe_cursor:
                        safe_cursor.execute("set role atom_hist8_importer")
                        with pytest.raises(
                            psycopg.Error,
                            match="permission denied for large object",
                        ):
                            safe_cursor.execute(
                                "select lo_get(%s)", (large_object_oid,),
                            )
                cursor.execute("select lo_unlink(%s)", (large_object_oid,))
                assert cursor.fetchone()[0] == 1
                large_object_oid = None

                cursor.execute(
                    "grant select on atom_research_history.raw_responses "
                    "to atom_hist8_importer with grant option"
                )
                with pytest.raises(
                    psycopg.Error, match="HIST8_IMPORTER_ACL_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "revoke grant option for select on "
                    "atom_research_history.raw_responses "
                    "from atom_hist8_importer cascade"
                )
                cursor.execute(sql)

                cursor.execute(
                    "grant set on parameter session_replication_role "
                    "to atom_hist8_importer"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="IMPORTER_ACL_MISMATCH|PARAMETER_PRIVILEGE_BOUNDARY",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "revoke set on parameter session_replication_role "
                    "from atom_hist8_importer"
                )
                cursor.execute(sql)

                cursor.execute(
                    "alter role atom_hist8_importer "
                    "set session_replication_role=replica"
                )
                with pytest.raises(
                    psycopg.Error, match="EXISTING_INSTALLATION_ROLE_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "alter role atom_hist8_importer "
                    "reset session_replication_role"
                )
                cursor.execute(sql)

                cursor.execute(
                    "create publication hist8_explicit for table "
                    "atom_research_history.bars"
                )
                with pytest.raises(
                    psycopg.Error, match="REPLICATION_BOUNDARY_UNSATISFIED",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute("drop publication hist8_explicit")
                cursor.execute(sql)

                cursor.execute("show server_version_num")
                if int(cursor.fetchone()[0]) >= 170000:
                    cursor.execute(
                        "grant maintain on public.coin_v8_market_bars to public"
                    )
                    with pytest.raises(
                        psycopg.Error,
                        match="MAINTAIN_PRIVILEGE_BOUNDARY_UNSATISFIED",
                    ):
                        cursor.execute(sql)
                    connection.rollback()
                    cursor.execute(
                        "revoke maintain on public.coin_v8_market_bars from public"
                    )
                    cursor.execute(sql)

                cursor.execute(
                    "create view atom_research_history.hist8_forbidden_view "
                    "as select id from public.coin_v8_market_bars"
                )
                cursor.execute(
                    "grant select on "
                    "atom_research_history.hist8_forbidden_view "
                    "to atom_hist8_importer"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_TABLE_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select to_regclass(" 
                    "'atom_research_history.hist8_forbidden_view') is not null"
                )
                assert cursor.fetchone()[0] is True
                cursor.execute(
                    "drop view atom_research_history.hist8_forbidden_view"
                )
                cursor.execute(sql)

                cursor.execute(
                    """create or replace function
                         atom_research_history.guard_snapshot_membership()
                       returns trigger
                       language plpgsql
                       security invoker
                       set search_path = pg_catalog
                       as $function$
                       begin
                         if false then
                           raise exception 'HIST8 import evidence is sealed';
                         end if;
                         return new;
                       end
                       $function$"""
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_PROTECTION_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select position('if false' in lower(prosrc)) > 0 "
                    "from pg_proc where oid="
                    "'atom_research_history.guard_snapshot_membership()'"
                    "::regprocedure"
                )
                assert cursor.fetchone()[0] is True
                guard_start = sql.index(
                    "CREATE OR REPLACE FUNCTION "
                    "atom_research_history.guard_snapshot_membership()"
                )
                guard_end = sql.index("$function$;", guard_start) + len(
                    "$function$;"
                )
                cursor.execute(sql[guard_start:guard_end])
                cursor.execute(sql)

                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "alter column body drop not null"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_PROTECTION_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select attnotnull from pg_attribute where attrelid="
                    "'atom_research_history.raw_responses'::regclass "
                    "and attname='body'"
                )
                assert cursor.fetchone()[0] is False
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "alter column body set not null"
                )
                cursor.execute(sql)

                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "alter column created_at set default "
                    "'2000-01-01 00:00:00+00'::timestamptz"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_PROTECTION_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "alter column created_at set default current_timestamp"
                )
                cursor.execute(sql)

                cursor.execute(
                    "drop index "
                    "atom_research_history.hist8_manifests_import_idx"
                )
                cursor.execute(
                    "create index hist8_manifests_import_idx on "
                    "atom_research_history.manifests (created_at)"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_PROTECTION_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select pg_get_indexdef("
                    "'atom_research_history.hist8_manifests_import_idx'"
                    "::regclass)"
                )
                assert cursor.fetchone()[0].endswith("(created_at)")
                cursor.execute(
                    "drop index "
                    "atom_research_history.hist8_manifests_import_idx"
                )
                cursor.execute(
                    "create index hist8_manifests_import_idx on "
                    "atom_research_history.manifests "
                    "(corpus_id, import_id, manifest_kind, sequence_no)"
                )
                cursor.execute(sql)

                cursor.execute(
                    "drop trigger hist8_snapshot_membership_guard on "
                    "atom_research_history.manifests"
                )
                cursor.execute(
                    "create trigger hist8_snapshot_membership_guard "
                    "before insert on atom_research_history.manifests "
                    "for each row when (false) execute function "
                    "atom_research_history.guard_snapshot_membership()"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_PROTECTION_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select tgqual is not null from pg_trigger where "
                    "tgrelid='atom_research_history.manifests'::regclass "
                    "and tgname='hist8_snapshot_membership_guard'"
                )
                assert cursor.fetchone()[0] is True
                cursor.execute(
                    "drop trigger hist8_snapshot_membership_guard on "
                    "atom_research_history.manifests"
                )
                cursor.execute(
                    "create trigger hist8_snapshot_membership_guard "
                    "before insert on atom_research_history.manifests "
                    "for each row execute function "
                    "atom_research_history.guard_snapshot_membership()"
                )
                cursor.execute(sql)

                cursor.execute(
                    """do $disable_hist8_fk$
                       declare trigger_name name;
                       begin
                         for trigger_name in
                           select trigger_object.tgname
                           from pg_trigger trigger_object
                           join pg_constraint constraint_object
                             on constraint_object.oid =
                                trigger_object.tgconstraint
                           where trigger_object.tgrelid =
                             'atom_research_history.manifests'::regclass
                             and trigger_object.tgisinternal
                             and constraint_object.conname =
                               'hist8_snapshot_member_bar_fk'
                         loop
                           execute format(
                             'alter table atom_research_history.manifests '
                             'disable trigger %I', trigger_name
                           );
                         end loop;
                       end
                       $disable_hist8_fk$"""
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_PROTECTION_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select count(*) from pg_trigger trigger_object "
                    "join pg_constraint constraint_object on "
                    "constraint_object.oid=trigger_object.tgconstraint "
                    "where trigger_object.tgrelid="
                    "'atom_research_history.manifests'::regclass "
                    "and trigger_object.tgisinternal "
                    "and trigger_object.tgenabled='D' "
                    "and constraint_object.conname="
                    "'hist8_snapshot_member_bar_fk'"
                )
                assert cursor.fetchone()[0] == 2
                cursor.execute(
                    """do $enable_hist8_fk$
                       declare trigger_name name;
                       begin
                         for trigger_name in
                           select trigger_object.tgname
                           from pg_trigger trigger_object
                           join pg_constraint constraint_object
                             on constraint_object.oid =
                                trigger_object.tgconstraint
                           where trigger_object.tgrelid =
                             'atom_research_history.manifests'::regclass
                             and trigger_object.tgisinternal
                             and constraint_object.conname =
                               'hist8_snapshot_member_bar_fk'
                         loop
                           execute format(
                             'alter table atom_research_history.manifests '
                             'enable trigger %I', trigger_name
                           );
                         end loop;
                       end
                       $enable_hist8_fk$"""
                )
                cursor.execute(sql)

                cursor.execute(
                    "create rule hist8_forbidden_rewrite as on insert to "
                    "atom_research_history.raw_responses do also nothing"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_TABLE_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select exists (select 1 from pg_rewrite where "
                    "ev_class='atom_research_history.raw_responses'::regclass "
                    "and rulename='hist8_forbidden_rewrite')"
                )
                assert cursor.fetchone()[0] is True
                cursor.execute(
                    "drop rule hist8_forbidden_rewrite on "
                    "atom_research_history.raw_responses"
                )
                cursor.execute(
                    "select not exists (select 1 from pg_rewrite where "
                    "ev_class='atom_research_history.raw_responses'::regclass "
                    "and rulename='hist8_forbidden_rewrite')"
                )
                assert cursor.fetchone()[0] is True
                cursor.execute(sql)
                cursor.execute("alter role atom_hist8_importer inherit")
                with pytest.raises(
                    psycopg.Error, match="EXISTING_INSTALLATION_ROLE_MISMATCH"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    "select rolinherit from pg_roles "
                    "where rolname='atom_hist8_importer'"
                )
                assert cursor.fetchone()[0] is True
                cursor.execute("alter role atom_hist8_importer noinherit")
                cursor.execute(sql)
                cursor.execute(
                    "grant atom_hist8_importer to hist8_forbidden"
                )
                with pytest.raises(
                    psycopg.Error, match="EXISTING_INSTALLATION_ROLE_MISMATCH"
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    """select exists (
                         select 1 from pg_auth_members
                         where roleid='atom_hist8_importer'::regrole
                           and member='hist8_forbidden'::regrole
                       )"""
                )
                assert cursor.fetchone()[0] is True
                cursor.execute(
                    "revoke atom_hist8_importer from hist8_forbidden"
                )
                cursor.execute(sql)
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "drop constraint hist8_raw_length_matches"
                )
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "add constraint hist8_raw_length_matches check (true)"
                )
                with pytest.raises(
                    psycopg.Error,
                    match="EXISTING_INSTALLATION_PROTECTION_MISMATCH",
                ):
                    cursor.execute(sql)
                connection.rollback()
                cursor.execute(
                    """select pg_get_constraintdef(oid, true)
                       from pg_constraint
                       where conrelid=
                         'atom_research_history.raw_responses'::regclass
                         and conname='hist8_raw_length_matches'"""
                )
                assert cursor.fetchone()[0] == "CHECK (true)"
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "drop constraint hist8_raw_length_matches"
                )
                cursor.execute(
                    "alter table atom_research_history.raw_responses "
                    "add constraint hist8_raw_length_matches "
                    "check (byte_length = octet_length(body))"
                )
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
                    importer.execute("set timezone='UTC'")
                    importer.execute("set role atom_hist8_importer")
                    return importer

                store = corpus.Hist8Store(importer_connection)
                with importer_connection() as timezone_connection:
                    corpus.Hist8Store._verify(timezone_connection)
                    timezone_connection.execute(
                        "set timezone='America/New_York'"
                    )
                    with pytest.raises(
                        corpus.Hist8Error, match="database identity mismatch",
                    ):
                        corpus.Hist8Store._verify(timezone_connection)
                attempt_metadata = {
                    "authorization": "ATOM-HIST8-CORPUS-AMENDMENT-1",
                    "project_ref": corpus.PROJECT_REF,
                }
                store.add_attempt(
                    "attempt-integrity", "IMPORT_ATTEMPT", attempt_metadata,
                )
                cursor.execute(
                    "alter table atom_research_history.manifests disable "
                    "trigger hist8_manifests_reject_update_delete"
                )
                cursor.execute(
                    """update atom_research_history.manifests
                       set metadata_json=%s::jsonb
                       where import_id='attempt-integrity'
                         and manifest_kind='IMPORT_ATTEMPT'""",
                    (json.dumps({
                        **attempt_metadata,
                        "project_ref": "corrupted-project",
                    }),),
                )
                cursor.execute(
                    "alter table atom_research_history.manifests enable "
                    "trigger hist8_manifests_reject_update_delete"
                )
                with pytest.raises(
                    corpus.Hist8ConflictError,
                    match="attempt manifest readback mismatch",
                ):
                    store.add_attempt(
                        "attempt-integrity", "IMPORT_ATTEMPT",
                        attempt_metadata,
                    )
                with pytest.raises(
                    corpus.Hist8ConflictError,
                    match="replay membership differs from sealed source snapshot",
                ):
                    store.seal_snapshot(
                        "attempt-replay-mismatch", {},
                        expected_membership_sha256="a" * 64,
                    )
                cursor.execute(
                    """select count(*)
                       from atom_research_history.manifests
                       where import_id='attempt-replay-mismatch'
                         and manifest_kind='SNAPSHOT'"""
                )
                assert cursor.fetchone()[0] == 0
                page = _raw_page(
                    {"retained": "first"}, instruments=corpus.EQUITIES,
                )
                artifact_id = "sha256:" + corpus.sha256(page.body)
                assert store.store_page("raw-attempt-1", 1, page) == 7
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
                        _raw_page(
                            {"retained": "late-association"},
                            instruments=corpus.EQUITIES,
                        ),
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

                start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
                provider_item = {
                    "t": start.isoformat(), "o": 100, "h": 103, "l": 99,
                    "c": 102, "v": 10, "n": 2, "vw": 101,
                }
                provider_item_2 = {
                    **provider_item,
                    "t": (start + timedelta(minutes=1)).isoformat(),
                }
                in_page_conflict = _raw_page({
                    "bars": {"SPY": [
                        provider_item, {**provider_item, "c": 101},
                    ]},
                    "next_page_token": None,
                }, instruments=corpus.EQUITIES)
                assert store.store_page(
                    "attempt-page-conflict", 1, in_page_conflict,
                ) == 7
                conflict_calendar = {
                    "schedule_sha256": corpus.CALENDAR_SCHEDULE_SHA256,
                    "instrument_calendars": {"SPY": "US_CASH_RTH"},
                    "us_cash_sessions": [{
                        "date": "2025-01-02",
                        "open_utc": start.isoformat().replace("+00:00", "Z"),
                        "close_utc": (
                            start + timedelta(minutes=1)
                        ).isoformat().replace("+00:00", "Z"),
                        "expected_minutes": 1,
                    }],
                }
                with pytest.raises(
                    corpus.Hist8ConflictError,
                    match="conflicting duplicate provider bar",
                ):
                    corpus.materialize_instrument(
                        store, "attempt-page-conflict", "SPY",
                        conflict_calendar,
                    )
                cursor.execute(
                    """select metadata_json
                       from atom_research_history.manifests
                       where import_id='attempt-page-conflict'
                         and manifest_kind='BAR_CONFLICT'"""
                )
                retained_conflicts = cursor.fetchall()
                assert len(retained_conflicts) == 1
                retained_conflict = retained_conflicts[0][0]
                assert retained_conflict["conflict_stage"] == (
                    "RETAINED_PROVIDER_ROWS"
                )
                assert retained_conflict["existing"][
                    "source_record_locator"
                ] == "$.bars.SPY[0]"
                assert retained_conflict["candidate"][
                    "source_record_locator"
                ] == "$.bars.SPY[1]"
                assert retained_conflict["existing"]["content_hash"] != (
                    retained_conflict["candidate"]["content_hash"]
                )
                canonical_page = _raw_page({
                    "bars": {"SPY": [provider_item]}, "page": 1,
                }, instruments=corpus.EQUITIES)
                reshuffled_page = _raw_page({
                    "bars": {"SPY": [provider_item, provider_item_2]},
                    "page": 2,
                }, instruments=corpus.EQUITIES)
                assert store.store_page(
                    "attempt-incomplete", 1, canonical_page
                ) == 7
                assert store.store_page(
                    "attempt-complete", 1, reshuffled_page
                ) == 7
                source = corpus.parse_source_page(canonical_page, "SPY")[0]
                complete_sources = corpus.parse_source_page(
                    reshuffled_page, "SPY"
                )
                incomplete = corpus.canonical_bar(
                    source, session_date="2025-01-02",
                    calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
                    import_id="attempt-incomplete", eligible=False,
                )
                complete_rows = tuple(corpus.canonical_bar(
                    complete_source,
                    session_date="2025-01-02",
                    calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
                    import_id="attempt-complete", eligible=True,
                ) for complete_source in complete_sources)
                complete = complete_rows[0]
                assert store.insert_bars(
                    (incomplete,), session_open=incomplete.bar_start_utc,
                    session_close=incomplete.bar_end_utc + timedelta(minutes=1),
                    expected_minutes=2,
                    expected_session_date="2025-01-02",
                    expected_calendar_id="US_CASH_RTH",
                    expected_calendar_sha256=corpus.CALENDAR_SCHEDULE_SHA256,
                ) == (1, 0)
                assert store.insert_bars(
                    complete_rows, session_open=complete.bar_start_utc,
                    session_close=complete.bar_start_utc + timedelta(minutes=2),
                    expected_minutes=2,
                    expected_session_date="2025-01-02",
                    expected_calendar_id="US_CASH_RTH",
                    expected_calendar_sha256=corpus.CALENDAR_SCHEDULE_SHA256,
                ) == (1, 1)
                conflict_page = _raw_page({
                    "bars": {"SPY": [{**provider_item, "c": 101}]},
                    "page": 3,
                }, instruments=corpus.EQUITIES)
                assert store.store_page(
                    "attempt-conflict", 1, conflict_page
                ) == 7
                conflicting = corpus.canonical_bar(
                    corpus.parse_source_page(conflict_page, "SPY")[0],
                    session_date="2025-01-02",
                    calendar_hash=corpus.CALENDAR_SCHEDULE_SHA256,
                    import_id="attempt-conflict", eligible=True,
                )
                with pytest.raises(
                    corpus.Hist8ConflictError, match="same-key bar conflict"
                ):
                    store.insert_bars(
                        (conflicting,), session_open=conflicting.bar_start_utc,
                        session_close=conflicting.bar_end_utc,
                        expected_minutes=1,
                        expected_session_date="2025-01-02",
                        expected_calendar_id="US_CASH_RTH",
                        expected_calendar_sha256=(
                            corpus.CALENDAR_SCHEDULE_SHA256
                        ),
                    )
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
                monkeypatch.setattr(corpus, "load_calendar", lambda **_kwargs: {
                    "schedule_sha256": corpus.CALENDAR_SCHEDULE_SHA256,
                    "instrument_calendars": {"SPY": "US_CASH_RTH"},
                    "us_cash_sessions": [{
                        "date": "2025-01-02",
                        "open_utc": start.isoformat().replace("+00:00", "Z"),
                        "close_utc": (
                            start + timedelta(minutes=2)
                        ).isoformat().replace("+00:00", "Z"),
                        "expected_minutes": 2,
                    }],
                })
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
                assert cursor.fetchone() == (
                    "sha256:" + corpus.sha256(canonical_page.body),
                    "$.bars.SPY[0]",
                )
                cursor.execute(
                    "alter table atom_research_history.bars "
                    "disable trigger hist8_bars_reject_update_delete"
                )
                cursor.execute(
                    "update atom_research_history.bars "
                    "set source_record_locator='$.bars.SPY[99]' "
                    "where bar_id=%s", (incomplete.bar_id,),
                )
                cursor.execute(
                    "alter table atom_research_history.bars "
                    "enable trigger hist8_bars_reject_update_delete"
                )
                with pytest.raises(
                    corpus.Hist8ConflictError,
                    match="provenance does not resolve",
                ):
                    store.insert_bars(
                        (complete,), session_open=complete.bar_start_utc,
                        session_close=complete.bar_end_utc,
                        expected_minutes=1,
                        expected_session_date="2025-01-02",
                        expected_calendar_id="US_CASH_RTH",
                        expected_calendar_sha256=(
                            corpus.CALENDAR_SCHEDULE_SHA256
                        ),
                    )
                cursor.execute(
                    "alter table atom_research_history.bars "
                    "disable trigger hist8_bars_reject_update_delete"
                )
                cursor.execute(
                    "update atom_research_history.bars "
                    "set source_record_locator='$.bars.SPY[0]' "
                    "where bar_id=%s", (incomplete.bar_id,),
                )
                cursor.execute(
                    "alter table atom_research_history.bars "
                    "enable trigger hist8_bars_reject_update_delete"
                )
                cursor.execute(
                    """select import_id,member_research_eligible,
                              member_provenance_hash
                       from atom_research_history.manifests
                       where manifest_kind='SNAPSHOT_MEMBER'
                       order by import_id,member_bar_start_utc"""
                )
                original_provenance = corpus._bar_provenance_hash(incomplete)
                assert cursor.fetchall() == [
                    ("attempt-complete", True, original_provenance),
                    (
                        "attempt-complete", True,
                        corpus._bar_provenance_hash(complete_rows[1]),
                    ),
                    ("attempt-incomplete", False, original_provenance),
                ]
        finally:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute("reset role")
                if lo_compat_database_set and current_database_name:
                    cursor.execute(
                        pgsql.SQL(
                            "alter database {} reset lo_compat_privileges"
                        ).format(pgsql.Identifier(current_database_name))
                    )
                cursor.execute("drop publication if exists hist8_all")
                cursor.execute("drop publication if exists hist8_explicit")
                cursor.execute(
                    "drop sequence if exists "
                    "information_schema.hist8_escape_seq"
                )
                cursor.execute(
                    "drop view if exists "
                    "information_schema.hist8_escape_view"
                )
                cursor.execute(
                    "drop function if exists "
                    "information_schema.hist8_escape()"
                )
                cursor.execute(
                    "drop foreign data wrapper if exists hist8_fdw cascade"
                )
                cursor.execute(
                    "select exists (select 1 from pg_roles "
                    "where rolname='atom_hist8_importer')"
                )
                if cursor.fetchone()[0]:
                    cursor.execute(
                        "alter role atom_hist8_importer "
                        "reset session_replication_role"
                    )
                    cursor.execute(
                        "revoke set on parameter session_replication_role "
                        "from atom_hist8_importer"
                    )
                cursor.execute(
                    "select current_setting('server_version_num')::integer, "
                    "to_regclass('public.coin_v8_market_bars') is not null"
                )
                server_version, legacy_table_exists = cursor.fetchone()
                if server_version >= 170000 and legacy_table_exists:
                    cursor.execute(
                        "revoke maintain on public.coin_v8_market_bars from public"
                    )
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
                for role, was_public in future_table_default_roles:
                    cursor.execute(
                        pgsql.SQL(
                            "alter default privileges for role {} "
                            "revoke select on tables from public"
                        ).format(pgsql.Identifier(role))
                    )
                    if was_public:
                        cursor.execute(
                            pgsql.SQL(
                                "alter default privileges for role {} "
                                "grant select on tables to public"
                            ).format(pgsql.Identifier(role))
                        )
                for role, was_public in future_routine_default_roles:
                    cursor.execute(
                        pgsql.SQL(
                            "alter default privileges for role {} "
                            "revoke execute on functions from public"
                        ).format(pgsql.Identifier(role))
                    )
                    if was_public:
                        cursor.execute(
                            pgsql.SQL(
                                "alter default privileges for role {} "
                                "grant execute on functions to public"
                            ).format(pgsql.Identifier(role))
                        )
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke select on tables from hist8_forbidden"
                )
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke usage on schemas from hist8_forbidden"
                )
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke usage on sequences from public"
                )
                if restore_public_sequence_default:
                    cursor.execute(
                        "alter default privileges for role postgres "
                        "grant usage on sequences to public"
                    )
                cursor.execute(
                    "alter default privileges for role postgres "
                    "revoke usage on schemas from public"
                )
                if restore_public_schema_default:
                    cursor.execute(
                        "alter default privileges for role postgres "
                        "grant usage on schemas to public"
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
