from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
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

    wrong_ticker = _Response({"ticker": "SPY", "results": []})
    with pytest.raises(corpus.Hist8Error, match="ticker identity mismatch"):
        list(corpus.massive_pages("key", opener=lambda *_args, **_kwargs: wrong_ticker))

    page = corpus.RawPage(
        "MASSIVE", "I:COMP", "I:COMP minute index OHLC", ("NASDAQ",),
        corpus.MASSIVE_URL, {}, datetime(2026, 9, 2, tzinfo=UTC), 200,
        "application/json", None,
        (b'{"ticker":"I:COMP","results":[{"t":1000.5,"o":1,'
         b'"h":1,"l":1,"c":1}]}'),
    )
    with pytest.raises(corpus.Hist8Error, match="timestamp is not an integer"):
        corpus.parse_source_page(page, "NASDAQ")


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
    complete = corpus.canonical_bar(
        source, session_date="2025-01-02", calendar_hash="b" * 64,
        import_id="attempt-2", eligible=True,
    )
    assert incomplete.bar_id == complete.bar_id
    assert incomplete.content_hash == complete.content_hash
    assert incomplete.research_eligible is False
    assert complete.research_eligible is True


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
    assert isinstance(corpus.Hist8Store.from_environment(), corpus.Hist8Store)


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
    assert sql.lstrip().startswith("-- ATOM-HIST8-CORPUS-AMENDMENT-1")
    assert "\nBEGIN;" in sql and sql.rstrip().endswith("COMMIT;")
    assert "HIST8_IMPORTER_ROLE_ALREADY_EXISTS" in sql
    assert "acl.grantee NOT IN" in sql
    assert "'SNAPSHOT_MEMBER'" in sql
    assert "member_research_eligible boolean" in sql


def test_schema_enforces_importer_boundary_in_postgres() -> None:
    dsn = os.environ.get("H2C_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("CI PostgreSQL is not available")
    import psycopg

    sql = Path("research/hist8/schema.sql").read_text(encoding="utf-8")
    managed_roles = (
        "atom_hist8_importer", "hist8_forbidden", "anon",
        "authenticated", "service_role",
    )
    with psycopg.connect(dsn, autocommit=True) as connection:
        try:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated", "service_role"):
                    cursor.execute(
                        f"create role {role} nologin nosuperuser nocreatedb "
                        "nocreaterole noreplication nobypassrls"
                    )
                cursor.execute("create table public.coin_v8_market_bars (id bigint)")
                cursor.execute("create table public.coin_v8_ai_decision_logs (id bigint)")

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

                cursor.execute("create role hist8_forbidden nologin")
                cursor.execute(
                    "create schema atom_research_history authorization postgres"
                )
                cursor.execute(
                    "alter default privileges for role postgres in schema "
                    "atom_research_history grant select on tables to hist8_forbidden"
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
                    "alter default privileges for role postgres in schema "
                    "atom_research_history revoke select on tables from hist8_forbidden"
                )
                cursor.execute("drop schema atom_research_history")

                cursor.execute(sql)
                cursor.execute(
                    """select rolcanlogin, rolinherit, rolsuper, rolcreatedb,
                              rolcreaterole, rolreplication, rolbypassrls
                       from pg_roles where rolname='atom_hist8_importer'"""
                )
                assert cursor.fetchone() == (
                    True, False, False, False, False, False, False,
                )
                cursor.execute("set role atom_hist8_importer")
                artifact_id = "sha256:" + "e" * 64
                cursor.execute(
                    """insert into atom_research_history.raw_responses
                       (artifact_id, body, byte_length) values (%s,%s,%s)""",
                    (artifact_id, b"{}", 2),
                )
                cursor.execute(
                    "select body from atom_research_history.raw_responses "
                    "where artifact_id=%s", (artifact_id,),
                )
                assert bytes(cursor.fetchone()[0]) == b"{}"
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

                def importer_connection():
                    importer = psycopg.connect(dsn, autocommit=False)
                    importer.execute("set role atom_hist8_importer")
                    return importer

                store = corpus.Hist8Store(importer_connection)
                start = datetime(2025, 1, 2, 14, 30, tzinfo=UTC)
                source = _source_bar(start, artifact=artifact_id)
                incomplete = corpus.canonical_bar(
                    source, session_date="2025-01-02", calendar_hash="b" * 64,
                    import_id="attempt-incomplete", eligible=False,
                )
                complete = corpus.canonical_bar(
                    source, session_date="2025-01-02", calendar_hash="b" * 64,
                    import_id="attempt-complete", eligible=True,
                )
                assert store.insert_bars((incomplete,)) == (1, 0)
                assert store.insert_bars((complete,)) == (0, 1)
                incomplete_digest = store.seal_snapshot("attempt-incomplete", {})
                complete_digest = store.seal_snapshot("attempt-complete", {})
                assert incomplete_digest != complete_digest
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
                for role in managed_roles:
                    cursor.execute(f"drop role if exists {role}")
