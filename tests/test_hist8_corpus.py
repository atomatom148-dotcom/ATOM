from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
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
        "e09c47b90120d051a2b2d6a4320323162eb1893b64ea90fe54142e74c1017ea2"
    )
    sessions = {row["date"]: row for row in manifest["us_cash_sessions"]}
    assert "2025-01-09" not in sessions
    assert sessions["2024-11-29"]["expected_minutes"] == 210
    assert sessions["2026-07-02"]["expected_minutes"] == 390


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


def test_complete_session_is_eligible_and_derives_deterministically() -> None:
    start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
    minute_bars = tuple(corpus.canonical_bar(
        _source_bar(start + timedelta(minutes=index)),
        session_date="2025-01-02", calendar_hash="b" * 64,
        import_id="attempt-1", eligible=True,
    ) for index in range(5))
    first = corpus.derive_session(minute_bars, "5m", "attempt-1")[0]
    second = corpus.derive_session(minute_bars, "5m", "attempt-2")[0]
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


def test_database_url_must_bind_exact_project_database_and_role(monkeypatch) -> None:
    bad_urls = (
        "", "postgresql://atom_hist8_importer:x@example.com/postgres",
        f"postgresql://postgres:x@{corpus.DATABASE_HOST}/postgres",
        f"postgresql://atom_hist8_importer:x@{corpus.DATABASE_HOST}/other",
    )
    for value in bad_urls:
        monkeypatch.setenv(corpus.IMPORT_DATABASE_ENV, value)
        with pytest.raises(corpus.Hist8Error, match="credential/project mismatch"):
            corpus.Hist8Store.from_environment()


def test_schema_has_exact_private_surface_and_append_only_grants() -> None:
    sql = Path("research/hist8/schema.sql").read_text(encoding="utf-8")
    assert sql.count("CREATE TABLE atom_research_history.") == 3
    assert "CREATE SCHEMA IF NOT EXISTS atom_research_history" in sql
    assert "GRANT SELECT, INSERT ON atom_research_history.raw_responses" in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql
    assert "GRANT TRUNCATE" not in sql
    assert sql.count("FORCE ROW LEVEL SECURITY") == 3
    assert "HIST8_EFFECTIVE_PRIVILEGE_BOUNDARY_UNSATISFIED" in sql
