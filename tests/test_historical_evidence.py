from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from quant.historical_evidence import (
    HistoricalEvidenceSpool, HistoricalEvidenceWriter,
    HistoricalForecastEvidence, build_manifest,
)
from quant.historical_replay_h1 import ReplayTimings


NOW = datetime(2026, 6, 15, 13, 30, tzinfo=timezone.utc)


def _rows(run_id="h1-june-15"):
    return tuple(HistoricalForecastEvidence(
        run_id, NOW, f"q{q}_family", horizon, None, "UNAVAILABLE",
        "MISSING_VALUE", "formula-1", "DIRECTIONAL_BPS", NOW, NOW,
        "data-1", "source-1",
    ) for q in range(1, 13) for horizon in ("30S", "1M", "5M", "15M", "30M", "1H"))


def _report(status="CERTIFIED"):
    timings = ReplayTimings(1, 1, 1, {f"q{x}_family": 1 for x in range(1, 13)},
                            1, 1, 1, 1, 0, 8)
    return SimpleNamespace(
        execution_stage="REPLAY_COMPLETE", data_status=status,
        replay_run_id="h1-june-15", historical_session="2026-06-15",
        configuration_digest="a" * 64, dataset_digest="b" * 64,
        session_digest="c" * 64, frame_count=1,
        quote_counts=(("COIN", 10), ("QQQ", 9)), timings=timings,
    )


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def execute(self, sql, params=()):
        self.connection.statements.append((sql, params))
        if self.connection.fail_on and self.connection.fail_on in sql:
            raise RuntimeError("injected partial failure")
        if "SELECT content_sha256 FROM" in sql:
            self.result = self.connection.existing
        elif "SELECT count(*), count(*) FILTER" in sql:
            self.result = self.connection.counts

    def fetchone(self):
        return self.result

    def close(self):
        pass


class Connection:
    def __init__(self, *, existing=None, counts=None, fail_on=None):
        self.existing = existing
        self.counts = counts
        self.fail_on = fail_on
        self.statements = []
        self.commits = self.rollbacks = 0

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_uncertified_run_is_rejected_before_database_access():
    with pytest.raises(ValueError, match=r"REPLAY_COMPLETE \+ CERTIFIED"):
        build_manifest(_report("DATA_INCOMPLETE"), _rows(), git_commit="93e63bf")


def test_certified_run_is_accepted_in_bounded_batches_and_keeps_all_72_slots():
    rows = _rows()
    manifest = build_manifest(_report(), rows, git_commit="93e63bf")
    connection = Connection()
    assert HistoricalEvidenceWriter(connection, batch_size=25).persist(manifest, rows) == 73
    inserts = [sql for sql, _ in connection.statements
               if "INSERT INTO public.atom_historical_replay_forecasts" in sql]
    assert len(inserts) == 3
    assert manifest.available_observation_count == 0
    assert manifest.unavailable_observation_count == 72
    assert all(row.expected_return_bps is None for row in rows)
    assert connection.commits == 1 and connection.rollbacks == 0


def test_disk_spool_is_reiterable_and_removes_its_private_temporary_file():
    rows = _rows()
    with HistoricalEvidenceSpool() as spool:
        assert spool.path.stat().st_mode & 0o777 == 0o600
        for row in rows:
            spool.append(row)
        path = spool.path
        assert len(spool) == 72 and spool.payload_bytes > 0
        assert tuple(spool) == rows
        assert tuple(spool) == rows
    assert not path.exists()


def test_disk_spool_persists_in_bounded_batches_without_materializing_session():
    with HistoricalEvidenceSpool() as spool:
        for row in _rows():
            spool.append(row)
        manifest = build_manifest(_report(), spool, git_commit="93e63bf")
        connection = Connection()
        assert HistoricalEvidenceWriter(connection, batch_size=25).persist(
            manifest, spool,
        ) == 73
        inserts = [sql for sql, _ in connection.statements
                   if "INSERT INTO public.atom_historical_replay_forecasts" in sql]
        assert len(inserts) == 3


def test_exact_retry_is_idempotent():
    rows = _rows()
    manifest = build_manifest(_report(), rows, git_commit="93e63bf")
    connection = Connection(existing=(manifest.content_sha256,), counts=(72, 72))
    assert HistoricalEvidenceWriter(connection).persist(manifest, rows) == 0
    assert connection.commits == 1


def test_compare_only_retry_refuses_missing_manifest_before_insert():
    rows = _rows()
    manifest = build_manifest(_report(), rows, git_commit="93e63bf")
    connection = Connection()
    with pytest.raises(RuntimeError, match="MANIFEST_MISSING"):
        HistoricalEvidenceWriter(connection).persist(
            manifest, rows, require_existing=True,
        )
    statements = [sql for sql, _params in connection.statements]
    assert not any(sql.startswith("INSERT INTO") for sql in statements)
    assert connection.rollbacks == 1 and connection.commits == 0


def test_same_identity_with_different_manifest_fails_closed():
    rows = _rows()
    manifest = build_manifest(_report(), rows, git_commit="93e63bf")
    connection = Connection(existing=("f" * 64,))
    with pytest.raises(RuntimeError, match="MANIFEST_CONFLICT"):
        HistoricalEvidenceWriter(connection).persist(manifest, rows)
    assert connection.rollbacks == 1 and connection.commits == 0


def test_same_identity_with_different_forecast_fails_closed():
    rows = _rows()
    manifest = build_manifest(_report(), rows, git_commit="93e63bf")
    connection = Connection(existing=(manifest.content_sha256,), counts=(72, 71))
    with pytest.raises(RuntimeError, match="FORECAST_CONFLICT"):
        HistoricalEvidenceWriter(connection).persist(manifest, rows)
    assert connection.rollbacks == 1


def test_partial_batch_failure_rolls_back_manifest_and_forecasts():
    rows = _rows()
    manifest = build_manifest(_report(), rows, git_commit="93e63bf")
    connection = Connection(fail_on="atom_historical_replay_forecasts")
    with pytest.raises(RuntimeError, match="injected partial failure"):
        HistoricalEvidenceWriter(connection).persist(manifest, rows)
    assert connection.rollbacks == 1 and connection.commits == 0


def test_migration_fences_runtime_roles_and_enforces_composite_identity():
    sql = open("supabase/migrations/20260826042317_create_historical_replay_evidence.sql",
               encoding="utf-8").read()
    assert "PRIMARY KEY (replay_run_id, cutoff_at, quant_id, horizon)" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql and "FORCE ROW LEVEL SECURITY" in sql
    assert "FROM PUBLIC, anon, authenticated, service_role" in sql
    assert "BEFORE UPDATE OR DELETE" in sql and "BEFORE TRUNCATE" in sql
