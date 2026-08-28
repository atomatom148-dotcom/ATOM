"""Full-horizon integration contract for the offline external V2 command."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import quant.v9_v2_external_rebuild as external_rebuild_module
from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.v9_production import (
    FORMULA_VERSIONS, FORMULA_VERSION_MAP, PostgresV2StateBuilder,
)
from quant.v9_v1_contract import (
    HORIZONS, HORIZON_SECONDS, MAGNITUDE_BPS, QUANT_IDS, V1SlotObservation,
    build_v1_input,
)
from quant.v9_v2_external_rebuild import (
    _cancel_on_interrupt,
    _cleanup_stale_workspaces,
    _configure_sqlite,
    _interrupt_signals,
    _publication_commit_guard,
    _read_pages,
    main,
    rebuild_external_v2,
)
from quant.v9_v2_build_receipt import (
    RESOURCE_RECEIPT_SCHEMA_VERSION,
    deserialize_v2_build_receipt,
    serialize_v2_build_receipt,
)
from quant.v9_v2d_evidence_state import serialize_v2_evidence_state
from quant.v9_v3_synthesis import synthesize_v3


NOW = 2_000_000_000.0


def _source_rows():
    directional = []
    magnitude = []
    record_id = 1
    for horizon in HORIZONS:
        seconds = HORIZON_SECONDS[horizon]
        for sample in range(4):
            cutoff = float(sample * seconds)
            maturity = cutoff + seconds
            for quant_id, formula in FORMULA_VERSIONS:
                if quant_id == "q3_volatility":
                    magnitude.append((
                        record_id, quant_id, formula, f"{horizon}-{sample}",
                        "COIN", horizon, cutoff, maturity, float(sample + 1),
                        cutoff, DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION,
                        maturity, cutoff, maturity,
                    ))
                else:
                    # Q10 is deliberately certified unavailable without a
                    # source-as-of proof; all other frozen families are causal.
                    source_as_of = None if quant_id == "q10_options_vol" else cutoff
                    if (
                        horizon == "30S" and sample == 0
                        and quant_id == "q1_momentum"
                    ):
                        source_as_of = cutoff + 1.0
                    directional.append((
                        record_id, quant_id, formula, f"{horizon}-{sample}",
                        "COIN", horizon, cutoff, maturity,
                        float(sample + record_id % 3), cutoff,
                        DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION,
                        source_as_of, float(sample * 2 + 1), maturity,
                        cutoff, maturity,
                    ))
                record_id += 1
    return directional, magnitude


class Cursor:
    def __init__(self, directional, magnitude):
        self.directional = directional
        self.magnitude = magnitude
        self.volatility = False
        self.parameters = ()
        self.snapshot = False
        self.external = False
        self.advisory = None

    def execute(self, sql, parameters):
        self.parameters = parameters
        if "pg_try_advisory_lock" in sql:
            self.advisory = "lock"
        elif "pg_advisory_unlock" in sql:
            self.advisory = "unlock"
        else:
            self.advisory = None
        self.snapshot = "transaction_timestamp" in sql
        self.volatility = "volatility_forecasts" in sql
        self.external = "LEFT JOIN public." in sql

    def fetchone(self):
        if self.advisory is not None:
            return (True,)
        return (NOW,)

    def fetchall(self):
        rows = self.magnitude if self.volatility else self.directional
        has_key = (
            len(self.parameters) > 8 if self.external else len(self.parameters) > 7
        )
        if has_key:
            key = tuple(self.parameters[-4:-1])
            rows = [row for row in rows if (row[5], row[6], row[0]) > key]
        page = rows[:4096]
        return [(*row, True) for row in page] if self.external else page

    def close(self): pass


class Connection:
    def __init__(self, directional, magnitude):
        self.cursor_value = Cursor(directional, magnitude)
    def cursor(self): return self.cursor_value
    def rollback(self): pass
    def close(self): pass


def _connect_factory():
    directional, magnitude = _source_rows()
    return lambda _url: Connection(directional, magnitude)


def test_source_reader_counts_unresolved_forecasts_without_admitting_them():
    resolved = (
        1, "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"], "cycle-1",
        "COIN", "30S", 0.0, 30.0, 1.0, 0.0, DATA_SCHEMA_VERSION,
        SOURCE_SPEC_VERSION, 0.0, Decimal("2.0"), 30.0, 0.0, 30.0, True,
    )
    unresolved = (
        2, "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"], "cycle-2",
        "COIN", "30S", 30.0, 60.0, 1.0, 30.0, DATA_SCHEMA_VERSION,
        SOURCE_SPEC_VERSION, None, None, None, 30.0, None, False,
    )

    class SourceCursor:
        def execute(self, _sql, _parameters):
            return None

        def fetchall(self):
            return (resolved, unresolved)

    spool = sqlite3.connect(":memory:")
    try:
        _configure_sqlite(spool)
        pages, stored, resolved_count, first, last = _read_pages(
            SourceCursor(), spool, state_as_of=NOW - 1, volatility=False,
            sample_disk=lambda: None,
        )
        assert (pages, stored, resolved_count) == (1, 2, 1)
        assert first.endswith(":1")
        assert last.endswith(":2")
        assert spool.execute("SELECT count(*) FROM directional").fetchone() == (1,)
        assert spool.execute("SELECT outcome FROM directional").fetchone() == (2.0,)
    finally:
        spool.close()


def test_database_owner_fails_before_workspace_when_lock_is_unavailable(tmp_path):
    directional, magnitude = _source_rows()

    class LockedCursor(Cursor):
        def fetchone(self):
            if self.advisory == "lock":
                return (False,)
            return super().fetchone()

    class LockedConnection(Connection):
        def __init__(self):
            self.cursor_value = LockedCursor(directional, magnitude)

    with pytest.raises(RuntimeError, match="V2_EXTERNAL_REBUILD_ALREADY_RUNNING"):
        rebuild_external_v2(
            database_url="postgresql://fixture", workspace_root=tmp_path,
            state_as_of=NOW - 1, connect=lambda _url: LockedConnection(),
            publish=False,
        )
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))


def test_external_rebuild_rejects_transaction_pooler_before_connect(tmp_path):
    connected = False

    def connect(_url):
        nonlocal connected
        connected = True
        raise AssertionError("unsafe connection must not be opened")

    with pytest.raises(ValueError, match="session mode"):
        rebuild_external_v2(
            database_url=(
                "postgresql://user:pass@aws-0-us-east-1.pooler.supabase.com:6543/db"
            ),
            workspace_root=tmp_path,
            connect=connect,
            publish=False,
        )
    assert connected is False


def test_interrupt_watcher_cancels_blocking_database_work():
    interrupted = external_rebuild_module.threading.Event()
    cancelled = external_rebuild_module.threading.Event()

    class BlockingConnection:
        def cancel_safe(self):
            cancelled.set()

    with _cancel_on_interrupt(BlockingConnection(), interrupted.is_set):
        interrupted.set()
        assert cancelled.wait(timeout=1.0)


def test_stale_workspace_janitor_requires_exact_owner_marker(tmp_path):
    stale = tmp_path / "atom-v2-external-rebuild-stale"
    stale.mkdir()
    (stale / "owner.json").write_text(json.dumps({
        "owner": external_rebuild_module._OWNER,
        "path": str(stale.resolve()),
        "uid": external_rebuild_module.os.getuid(),
    }, sort_keys=True), encoding="ascii")
    (stale / "partial.sqlite3").write_bytes(b"partial")
    _cleanup_stale_workspaces(tmp_path)
    assert not stale.exists()

    foreign = tmp_path / "atom-v2-external-rebuild-foreign"
    foreign.mkdir()
    (foreign / "owner.json").write_text("{}", encoding="ascii")
    with pytest.raises(ValueError, match="unowned"):
        _cleanup_stale_workspaces(tmp_path)
    assert foreign.exists()


def test_parent_workspace_initialization_failure_does_not_leak(
        tmp_path, monkeypatch):
    original = Path.write_text

    def fail_owner(self, *args, **kwargs):
        if self.name == "owner.json":
            raise OSError("synthetic marker failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_owner)
    with pytest.raises(OSError, match="marker failure"):
        external_rebuild_module._workspace(tmp_path)
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))


def test_interruption_cleans_workspace_and_does_not_publish(tmp_path):
    checks = 0

    def interrupted():
        nonlocal checks
        checks += 1
        return checks >= 5

    class RejectingStore:
        def insert_with_receipt(
                self, _state, _receipt, *, connection, interrupt_check,
                commit_guard):
            assert connection is not None
            assert interrupt_check is interrupted
            assert callable(commit_guard)
            raise AssertionError("interrupted candidate must not publish")

    with pytest.raises(InterruptedError):
        rebuild_external_v2(
            database_url="postgresql://fixture", workspace_root=tmp_path,
            state_as_of=NOW - 1, connect=_connect_factory(),
            store=RejectingStore(), publish=True,
            interrupt_check=interrupted,
        )
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))


def test_late_interruption_cancels_before_atomic_publication(
        tmp_path, monkeypatch):
    interrupted = False
    published = False
    original = external_rebuild_module.seal_receipt

    def seal_and_interrupt(receipt):
        nonlocal interrupted
        sealed = original(receipt)
        interrupted = True
        return sealed

    class Store:
        def insert_with_receipt(
                self, _state, _receipt, *, connection, interrupt_check,
                commit_guard):
            nonlocal published
            assert connection is not None
            assert callable(interrupt_check)
            assert callable(commit_guard)
            published = True
            return "INSERTED"

    monkeypatch.setattr(
        external_rebuild_module, "seal_receipt", seal_and_interrupt
    )
    with pytest.raises(InterruptedError, match="V2_EXTERNAL_REBUILD_INTERRUPTED"):
        rebuild_external_v2(
            database_url="postgresql://fixture", workspace_root=tmp_path,
            state_as_of=NOW - 1, connect=_connect_factory(), store=Store(),
            publish=True, interrupt_check=lambda: interrupted,
        )
    assert published is False
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))


@pytest.mark.skipif(
    not hasattr(external_rebuild_module.signal, "pthread_sigmask"),
    reason="POSIX signal masks are unavailable",
)
def test_publication_commit_guard_defers_sigterm_until_atomic_boundary():
    with _interrupt_signals() as interrupted:
        with _publication_commit_guard(interrupted):
            external_rebuild_module.os.kill(
                external_rebuild_module.os.getpid(),
                external_rebuild_module.signal.SIGTERM,
            )
            assert interrupted() is False
        assert interrupted() is True


def test_external_pipeline_builds_all_72_slots_matches_legacy_and_restores_v3(
        tmp_path, monkeypatch):
    connect = _connect_factory()
    legacy = PostgresV2StateBuilder("postgresql://fixture", connect=connect).build(
        state_as_of=NOW - 1)

    def reject_legacy(*_args, **_kwargs):
        raise AssertionError("legacy full-memory builder invoked")

    monkeypatch.setattr(PostgresV2StateBuilder, "build", reject_legacy)
    # The offline command must use the SQLite-backed A→D path, not merely
    # avoid the legacy Postgres orchestration wrapper while continuing to call
    # its full-memory layer builders directly.
    for name in (
        "build_v2a_dataset",
        "build_v2b_calibration",
        "build_v2c_covariance",
        "build_v2d_evidence_state",
    ):
        monkeypatch.setattr(
            external_rebuild_module, name, reject_legacy, raising=False
        )
    result = rebuild_external_v2(
        database_url="postgresql://fixture", workspace_root=tmp_path,
        state_as_of=NOW - 1, connect=_connect_factory(), publish=False,
    )
    assert serialize_v2_evidence_state(result.state) == serialize_v2_evidence_state(legacy)
    assert result.state.state_hash == legacy.state_hash
    assert result.state.state_id == legacy.state_id
    assert result.state.evidence_manifest_hash == legacy.evidence_manifest_hash
    assert result.state.creation_status == "VALID"
    assert tuple(item.horizon for item in result.state.horizon_state_tuple) == HORIZONS
    expected_slots = {
        (horizon, quant_id)
        for horizon in HORIZONS
        for quant_id in QUANT_IDS
    }
    admitted = result.receipt.per_family_horizon_admitted_counts
    assert {(horizon, quant_id) for horizon, quant_id, _count in admitted} == expected_slots
    assert {
        (horizon, quant_id)
        for horizon, quant_id, _effective_n
        in result.receipt.per_family_horizon_effective_n
    } == expected_slots
    assert len(admitted) == 72
    assert all(count == 0 for horizon, quant_id, count
               in admitted
               if quant_id == "q10_options_vol")
    assert all(
        count == (3 if (horizon, quant_id) == ("30S", "q1_momentum") else 4)
        for horizon, quant_id, count in admitted
        if quant_id != "q10_options_vol"
    )
    directional, magnitude = _source_rows()
    assert result.receipt.source_rows_read == len(directional) + len(magnitude)
    assert result.receipt.resolved_evidence_rows == 288
    assert result.receipt.eligible_rows == 263
    assert result.receipt.admitted_rows == 263
    assert result.receipt.rejected_rows == 25
    assert result.receipt.pages_read == 2
    assert result.receipt.receipt_schema_version == RESOURCE_RECEIPT_SCHEMA_VERSION
    assert result.receipt.state_id == result.state.state_id
    assert (result.receipt.evidence_manifest_hash ==
            result.state.evidence_manifest_hash)
    assert (result.receipt.temporary_disk_peak_bytes ==
            result.temporary_disk_peak_bytes)
    receipt_bytes = serialize_v2_build_receipt(result.receipt)
    assert deserialize_v2_build_receipt(receipt_bytes) == result.receipt
    assert result.temporary_disk_peak_bytes > 0
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))

    cutoff = datetime.fromtimestamp(NOW, timezone.utc)
    state_as_of = datetime.fromtimestamp(result.state.state_as_of, timezone.utc)
    slots = []
    versions = dict(FORMULA_VERSIONS)
    for quant_id in QUANT_IDS:
        for horizon in HORIZONS:
            slots.append(V1SlotObservation(
                quant_id, versions[quant_id], horizon, HORIZON_SECONDS[horizon],
                MAGNITUDE_BPS if quant_id == "q3_volatility" else "DIRECTIONAL_BPS",
                None, cutoff, cutoff, cutoff, "MISSING", DATA_SCHEMA_VERSION,
                SOURCE_SPEC_VERSION,
            ))
    v1 = build_v1_input(
        cycle_id="restore", cutoff_at=cutoff,
        target_spec_id=result.state.target_spec_id,
        data_schema_version=result.state.target_data_schema_version,
        source_spec_version=result.state.target_source_spec_version, slots=slots,
        evidence_state_id=result.state.state_id,
        evidence_state_version=result.state.state_version,
        evidence_state_hash=result.state.state_hash,
        evidence_state_as_of=state_as_of,
    )
    output = synthesize_v3(v1, result.state)
    assert len(output.horizon_results) == 6
    assert v1.evidence_state_id == result.state.state_id
    assert all(
        "V2_EVIDENCE_VERSION_MISMATCH" not in item.reason_codes
        for item in output.horizon_results
    )
    mismatched = synthesize_v3(
        replace(v1, evidence_state_id="v9v2:" + "0" * 64), result.state
    )
    assert all(
        "V2_EVIDENCE_VERSION_MISMATCH" in item.reason_codes
        for item in mismatched.horizon_results
    )


def test_external_pipeline_is_deterministic_and_cleans_after_publish_failure(
        tmp_path):
    first = rebuild_external_v2(
        database_url="postgresql://fixture", workspace_root=tmp_path,
        state_as_of=NOW - 1, connect=_connect_factory(), publish=False,
    )
    second = rebuild_external_v2(
        database_url="postgresql://fixture", workspace_root=tmp_path,
        state_as_of=NOW - 1, connect=_connect_factory(), publish=False,
    )
    assert serialize_v2_evidence_state(first.state) == serialize_v2_evidence_state(
        second.state
    )
    assert first.state.state_id == second.state.state_id
    assert first.receipt.receipt_sha256 == second.receipt.receipt_sha256
    assert first.temporary_disk_peak_bytes == second.temporary_disk_peak_bytes
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))


def test_external_pipeline_rejects_boolean_state_as_of(tmp_path):
    with pytest.raises(ValueError, match="outside the source snapshot"):
        rebuild_external_v2(
            database_url="postgresql://fixture", workspace_root=tmp_path,
            state_as_of=True, connect=_connect_factory(), publish=False,
        )
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))

    class RejectingStore:
        def insert_with_receipt(
                self, state, receipt, *, connection, interrupt_check,
                commit_guard):
            assert connection is not None
            assert interrupt_check is None
            assert callable(commit_guard)
            assert state.state_id == receipt.state_id
            assert state.evidence_manifest_hash == receipt.evidence_manifest_hash
            raise RuntimeError("synthetic publication failure")

    with pytest.raises(RuntimeError, match="synthetic publication failure"):
        rebuild_external_v2(
            database_url="postgresql://fixture", workspace_root=tmp_path,
            state_as_of=NOW - 1, connect=_connect_factory(),
            store=RejectingStore(), publish=True,
        )
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))


def test_external_pipeline_fresh_process_has_bounded_rss_and_cleans(tmp_path):
    script = (
        Path(__file__).parents[1]
        / "spikes"
        / "v9_v2_external_rebuild_parity.py"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source-rows",
            "8208",
            "--root",
            str(tmp_path),
            "--max-rss-delta-bytes",
            str(128 * 1024 * 1024),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    result = json.loads(completed.stdout)
    assert result["state"] == "VALID"
    assert result["receipt"] == "PRESENT"
    assert result["source_rows_read"] == 8_208
    assert result["family_horizon_slots"] == 72
    assert result["pages_read"] == 3
    assert result["state_id_match"] is True
    assert result["manifest_match"] is True
    assert result["cleanup"] is True
    assert result["peak_rss_delta_bytes"] < 128 * 1024 * 1024
    assert result["temporary_disk_peak_bytes"] > 0
    assert not list(tmp_path.glob("atom-v2-external-rebuild-*"))


def test_command_dispatches_external_pipeline_not_legacy(tmp_path, monkeypatch, capsys):
    called = []
    state = type("State", (), {
        "state_id": "id", "state_hash": "a" * 64,
        "evidence_manifest_hash": "b" * 64,
    })()
    receipt = type("Receipt", (), {
        "receipt_sha256": "c" * 64,
    })()
    monkeypatch.setattr(
        "quant.v9_v2_external_rebuild.rebuild_external_v2",
        lambda **kwargs: (called.append(kwargs) or type("Result", (), {
            "state": state, "receipt": receipt, "temporary_disk_peak_bytes": 123,
            "publication_status": None,
        })()),
    )
    monkeypatch.setattr(
        PostgresV2StateBuilder, "build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy full-memory builder invoked")),
    )
    assert main(["--database-url", "postgresql://fixture",
                 "--workspace-root", str(tmp_path)]) == 0
    assert called and called[0]["publish"] is False
    assert '"temporary_disk_peak_bytes": 123' in capsys.readouterr().out

    called.clear()
    assert main(["--database-url", "postgresql://fixture",
                 "--workspace-root", str(tmp_path), "--publish"]) == 0
    assert called and called[0]["publish"] is True
