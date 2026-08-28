"""Explicit offline SQLite-spooled production V2 rebuild.

This module is deliberately absent from web startup.  Its command entry point
reads one repeatable-read snapshot in deterministic keyset pages, stages that
snapshot in an owned SQLite workspace, validates the complete frozen V2D
candidate and only then atomically publishes the state/receipt pair.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import math
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import sqlite3
import tempfile
import threading
import time
from typing import Callable, Iterator
from urllib.parse import urlparse

from .evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from .v9_production import (
    FORMULA_VERSIONS, FORMULA_VERSION_MAP, TARGET_SPEC_ID,
    V2_STATE_BUILD_EVIDENCE_PAGE_SIZE,
)
from .v9_v1_contract import DIRECTIONAL_BPS, HORIZONS, MAGNITUDE_BPS
from .v9_v2a_dataset import (
    RawFamilyObservation, RawTarget, TargetIdentity,
)
from .v9_v2a_external import (
    ExternalV2AView,
    build_external_v2a,
    build_external_v2b,
    build_external_v2c,
    build_external_v2d,
    cleanup_owned_workspace,
)
from .v9_v2d_evidence_state import (
    V2EvidenceState, deserialize_v2_evidence_state,
    serialize_v2_evidence_state,
)
from .v9_v2_build_receipt import (
    RESOURCE_RECEIPT_SCHEMA_VERSION, V2BuildReceipt, seal_receipt,
)
from .v9_v2_state_store import PostgresV2StateStore


_OWNER = "ATOM-V9-V2-EXTERNAL-REBUILD-1"
_LOCK_NAME = ".atom-v9-v2-external-rebuild.lock"
_DATABASE_LOCK_KEY = (1_096_044_365, 1_446_135_128)  # "ATOM", "V2EX"
_SQLITE_TMPDIR_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ExternalRebuildResult:
    state: V2EvidenceState
    receipt: V2BuildReceipt
    temporary_disk_peak_bytes: int
    publication_status: str | None


def _disk_bytes(workspace: Path) -> int:
    return sum(item.stat().st_size for item in workspace.rglob("*")
               if item.is_file() and not item.is_symlink())


def _workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="atom-v2-external-rebuild-", dir=root)).resolve()
    try:
        os.chmod(path, 0o700)
        (path / "owner.json").write_text(json.dumps({
            "owner": _OWNER, "path": str(path), "uid": os.getuid(),
        }, sort_keys=True), encoding="ascii")
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
    return path


def _validate_database_url(database_url: str) -> None:
    """Reject Supavisor transaction mode, which cannot own a session lock."""

    if "://" in database_url:
        parsed = urlparse(database_url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    else:
        fields = {}
        for token in shlex.split(database_url):
            if "=" in token:
                key, value = token.split("=", 1)
                fields[key.strip().lower()] = value.strip()
        hostname = fields.get("host", "").lower()
        try:
            port = int(fields["port"]) if "port" in fields else None
        except ValueError as error:
            raise ValueError("invalid database port") from error
    if hostname.endswith(".pooler.supabase.com") and port == 6543:
        raise ValueError(
            "external V2 rebuild requires Supabase session mode, not port 6543"
        )


def _cleanup(workspace: Path, root: Path) -> None:
    if (workspace.is_symlink() or
            not workspace.name.startswith("atom-v2-external-rebuild-") or
            workspace.resolve().parent != root.resolve()):
        raise ValueError("refusing to clean an unowned V2 workspace")
    marker = workspace / "owner.json"
    expected = {"owner": _OWNER, "path": str(workspace.resolve()), "uid": os.getuid()}
    try:
        actual = json.loads(marker.read_text(encoding="ascii"))
    except (OSError, ValueError) as error:
        raise ValueError("refusing to clean an unowned V2 workspace") from error
    if actual != expected:
        raise ValueError("refusing to clean an unowned V2 workspace")
    try:
        nested_mount = any(
            item.is_dir() and not item.is_symlink() and item.is_mount()
            for item in workspace.rglob("*")
        )
    except OSError as error:
        raise ValueError("refusing to clean an unowned V2 workspace") from error
    if nested_mount:
        raise ValueError("refusing to clean a mount-crossing V2 workspace")
    shutil.rmtree(workspace)


def _cleanup_stale_workspaces(root: Path) -> None:
    """Remove only marker-validated workspaces left by an interrupted run."""

    root = root.resolve()
    for workspace in sorted(root.glob("atom-v2-external-rebuild-*")):
        if (workspace.is_symlink() or not workspace.is_dir() or
                workspace.resolve().parent != root):
            raise ValueError("refusing to clean an unowned V2 workspace")
        _cleanup(workspace, root)


def _cleanup_rebuild_resources(
        spool: sqlite3.Connection | None,
        views: list[ExternalV2AView],
        workspace: Path,
        root: Path) -> None:
    """Attempt every owned cleanup step before reporting the first failure."""

    first_error: Exception | None = None

    def attempt(action: Callable[[], None]) -> None:
        nonlocal first_error
        try:
            action()
        except Exception as error:  # cleanup must continue for sibling resources
            if first_error is None:
                first_error = error

    if spool is not None:
        attempt(spool.close)
    for view in reversed(views):
        attempt(view.close)
        attempt(lambda view=view: cleanup_owned_workspace(
            view.workspace, root=workspace))
    # The parent workspace owns the entire subtree, so this final attempt is
    # safe even if a child marker was damaged and its stricter cleanup failed.
    attempt(lambda: _cleanup(workspace, root))
    if first_error is not None:
        raise first_error


@contextmanager
def _single_owner(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / _LOCK_NAME).open("a+b")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("V2_EXTERNAL_REBUILD_ALREADY_RUNNING") from error
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@contextmanager
def _database_owner(database_url: str, connect: Callable):
    """Hold one model-scoped PostgreSQL session lock through publication."""

    connection = connect(database_url)
    acquired = False
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT pg_catalog.pg_try_advisory_lock(%s,%s)",
                _DATABASE_LOCK_KEY,
            )
            row = cursor.fetchone()
            acquired = row == (True,)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
        if not acquired:
            raise RuntimeError("V2_EXTERNAL_REBUILD_ALREADY_RUNNING")
        yield connection
    finally:
        if acquired:
            try:
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        "SELECT pg_catalog.pg_advisory_unlock(%s,%s)",
                        _DATABASE_LOCK_KEY,
                    )
                    cursor.fetchone()
                finally:
                    close = getattr(cursor, "close", None)
                    if callable(close):
                        close()
            except Exception:
                # Closing the session below releases every session advisory
                # lock even if an explicit unlock cannot be confirmed.
                pass
        close = getattr(connection, "close", None)
        if callable(close):
            close()


@contextmanager
def _interrupt_signals():
    """Turn command-scoped termination signals into cooperative cancellation."""

    interrupted = threading.Event()
    previous = {}

    def request_stop(_signum, _frame) -> None:
        interrupted.set()

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, request_stop)
    try:
        yield interrupted.is_set
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _raise_if_interrupted(interrupt_check: Callable[[], bool] | None) -> None:
    if interrupt_check is not None and interrupt_check():
        raise InterruptedError("V2_EXTERNAL_REBUILD_INTERRUPTED")


@contextmanager
def _publication_commit_guard(interrupt_check):
    """Defer cooperative termination across PostgreSQL's commit boundary.

    Once COMMIT starts, PostgreSQL may atomically make both immutable rows
    durable even if the client disappears. Blocking the handled termination
    signals across the final check and COMMIT gives the CLI one explicit
    outcome: a signal wins before this boundary, or the complete pair commits.
    """

    signals = {signal.SIGINT, signal.SIGTERM}
    mask = getattr(signal, "pthread_sigmask", None)
    previous = None
    _raise_if_interrupted(interrupt_check)
    if callable(mask):
        previous = mask(signal.SIG_BLOCK, signals)
    try:
        _raise_if_interrupted(interrupt_check)
        yield
    finally:
        if previous is not None:
            mask(signal.SIG_SETMASK, previous)


@contextmanager
def _cancel_on_interrupt(connection, interrupt_check):
    """Cancel blocking PostgreSQL work after a command termination signal."""

    stop = threading.Event()
    watcher = None
    if interrupt_check is not None:
        def watch() -> None:
            mask = getattr(signal, "pthread_sigmask", None)
            previous = None
            if callable(mask):
                previous = mask(
                    signal.SIG_BLOCK,
                    {signal.SIGINT, signal.SIGTERM},
                )
            try:
                while not stop.wait(0.05):
                    if not interrupt_check():
                        continue
                    cancel = getattr(connection, "cancel_safe", None)
                    if not callable(cancel):
                        cancel = getattr(connection, "cancel", None)
                    if callable(cancel):
                        try:
                            cancel()
                        except Exception:
                            # The ordinary rebuild path will observe the signal or
                            # broken session and fail publication closed.
                            pass
                    return
            finally:
                if previous is not None:
                    mask(signal.SIG_SETMASK, previous)

        watcher = threading.Thread(
            target=watch, name="v2-external-db-cancel", daemon=True,
        )
        watcher.start()
    try:
        yield
    finally:
        stop.set()
        if watcher is not None:
            watcher.join(timeout=1.0)


def _configure_sqlite(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA temp_store=FILE")
    connection.executescript("""
    CREATE TABLE directional(
      forecast_id INTEGER PRIMARY KEY, quant_id TEXT, formula_version TEXT,
      cycle_id TEXT, symbol TEXT, horizon TEXT, cutoff REAL, maturity REAL,
      value REAL, created REAL, schema_version TEXT, source_version TEXT,
      source_as_of REAL, outcome REAL, resolved REAL,
      forecast_available REAL, outcome_available REAL
    );
    CREATE INDEX directional_horizon_order
      ON directional(horizon,cutoff,forecast_id);
    CREATE TABLE magnitude(
      forecast_id INTEGER PRIMARY KEY, quant_id TEXT, formula_version TEXT,
      cycle_id TEXT, symbol TEXT, horizon TEXT, cutoff REAL, maturity REAL,
      value REAL, created REAL, schema_version TEXT, source_version TEXT,
      resolved REAL, forecast_available REAL, outcome_available REAL
    );
    CREATE INDEX magnitude_horizon_order
      ON magnitude(horizon,cutoff,forecast_id);
    """)


def _read_pages(cursor, sqlite: sqlite3.Connection, *, state_as_of: float,
                volatility: bool, sample_disk: Callable[[], None],
                interrupt_check: Callable[[], bool] | None = None,
                ) -> tuple[int, int, int, str | None, str | None]:
    table = "volatility_forecasts" if volatility else "forecasts"
    outcome_table = "volatility_forecast_outcomes" if volatility else "forecast_outcomes"
    value = "f.forecast_volatility_bps" if volatility else "f.forecast_bps"
    numerical = ("o.resolved_epoch, " if volatility else
                 "f.source_as_of_epoch, o.outcome_bps, o.resolved_epoch, ")
    kinds = (("VOLATILITY_FORECAST", "VOLATILITY_OUTCOME") if volatility else
             ("DIRECTIONAL_FORECAST", "DIRECTIONAL_OUTCOME"))
    destination = "magnitude" if volatility else "directional"
    destination_columns = 15 if volatility else 17
    placeholders = ",".join("?" for _ in range(destination_columns))
    key = None
    pages = 0
    rows_read = 0
    resolved_rows = 0
    first_identity = None
    last_identity = None
    while True:
        _raise_if_interrupted(interrupt_check)
        predicate = ""
        parameters: list[object] = [
            5.0, state_as_of, kinds[0], kinds[1], DATA_SCHEMA_VERSION,
            SOURCE_SPEC_VERSION, state_as_of,
        ]
        if key is not None:
            predicate = ("AND (f.horizon,f.cutoff_epoch,f.forecast_id) "
                         "> (%s,%s,%s)")
            parameters.extend(key)
        parameters.append(V2_STATE_BUILD_EVIDENCE_PAGE_SIZE)
        cursor.execute(f"""
          SELECT f.forecast_id,f.quant_id,f.formula_version,f.cycle_id,
                 f.symbol,f.horizon,f.cutoff_epoch,f.maturity_epoch,{value},
                 f.created_epoch,f.data_schema_version,f.source_spec_version,
                 {numerical}extract(epoch FROM fp.commit_observed_at),
                 extract(epoch FROM op.commit_observed_at),
                 (o.forecast_id IS NOT NULL
                  AND o.resolved_epoch >= f.maturity_epoch
                  AND o.resolved_epoch <= f.maturity_epoch + %s
                  AND op.commit_observed_at <= to_timestamp(%s))
                 AS resolved_qualified
          FROM public.{table} AS f
          LEFT JOIN public.{outcome_table} AS o USING (forecast_id)
          JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
            %s,f.forecast_id) AS fp ON true
          LEFT JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
            %s,o.forecast_id) AS op ON o.forecast_id IS NOT NULL
          WHERE f.data_schema_version=%s AND f.source_spec_version=%s
            AND fp.commit_observed_at <= to_timestamp(%s)
            AND fp.commit_observed_at < to_timestamp(f.maturity_epoch)
            {predicate}
          ORDER BY f.horizon,f.cutoff_epoch,f.forecast_id LIMIT %s
        """, tuple(parameters))
        source_page = tuple(cursor.fetchall())
        _raise_if_interrupted(interrupt_check)
        if source_page:
            pages += 1
            resolved_page = tuple(
                row[:destination_columns] for row in source_page if row[-1] is True
            )
            if resolved_page:
                sqlite.executemany(
                    f"INSERT INTO {destination} VALUES({placeholders})",
                    resolved_page,
                )
            sqlite.commit()
            kind = "magnitude" if volatility else "directional"
            page_first = source_page[0]
            page_last = source_page[-1]
            if first_identity is None:
                first_identity = (
                    f"{kind}:{page_first[5]}:{float(page_first[6]).hex()}:"
                    f"{page_first[0]}")
            last_identity = (
                f"{kind}:{page_last[5]}:{float(page_last[6]).hex()}:"
                f"{page_last[0]}")
            rows_read += len(source_page)
            resolved_rows += len(resolved_page)
            sample_disk()
        if len(source_page) < V2_STATE_BUILD_EVIDENCE_PAGE_SIZE:
            return pages, rows_read, resolved_rows, first_identity, last_identity
        last = source_page[-1]
        next_key = (last[5], last[6], last[0])
        if key is not None and next_key <= key:
            raise RuntimeError("V2_EVIDENCE_PAGINATION_STALLED")
        key = next_key


def _iter_targets(sqlite: sqlite3.Connection, horizon: str) -> Iterator[RawTarget]:
    """Stream one horizon's targets from the local spool in canonical order."""

    for row in sqlite.execute(
            "SELECT forecast_id,quant_id,formula_version,cycle_id,symbol,"
            "horizon,cutoff,maturity,"
            "schema_version,source_version,outcome,resolved,"
            "max(outcome_available) OVER ("
            "PARTITION BY cycle_id,cutoff,maturity) "
            "FROM directional WHERE horizon=? ORDER BY cutoff,forecast_id",
            (horizon,)):
        (record_id, quant_id, formula, cycle, symbol, row_horizon, cutoff,
         maturity, schema, source, outcome, _resolved, outcome_available) = row
        if FORMULA_VERSION_MAP.get(str(quant_id)) != str(formula):
            continue
        yield RawTarget(
            int(record_id), str(cycle), str(symbol), TARGET_SPEC_ID, str(schema),
            str(source), str(row_horizon), float(cutoff), float(maturity),
            float(outcome_available), float(outcome),
        )


def _iter_observations(
        sqlite: sqlite3.Connection, horizon: str
) -> Iterator[RawFamilyObservation]:
    """Stream formula-qualified observations without retaining source pages."""

    for row in sqlite.execute(
            "SELECT * FROM directional WHERE horizon=? ORDER BY cutoff,forecast_id",
            (horizon,)):
        (record_id, quant_id, formula, cycle, symbol, row_horizon, cutoff,
         maturity, value, _created, schema, source, source_as_of, _outcome,
         _resolved, forecast_available, _outcome_available) = row
        if FORMULA_VERSION_MAP.get(str(quant_id)) != str(formula):
            continue
        # Certified-unavailable Q10/Q4 rows have no causal source timestamp.
        # They remain represented by the frozen family lineage but are not
        # fabricated into an observation.
        if str(quant_id) in {"q4_stat_arb", "q10_options_vol"} and source_as_of is None:
            continue
        identity = TargetIdentity(str(cycle), float(cutoff), float(maturity))
        source_epoch = float(cutoff if source_as_of is None else source_as_of)
        yield RawFamilyObservation(
            int(record_id), identity, str(symbol), str(quant_id), str(formula),
            str(schema), str(source), str(row_horizon), DIRECTIONAL_BPS,
            float(value), float(cutoff), source_epoch, float(forecast_available),
            "FRESH",
        )
    for row in sqlite.execute(
            "SELECT * FROM magnitude WHERE horizon=? ORDER BY cutoff,forecast_id",
            (horizon,)):
        (record_id, quant_id, formula, cycle, symbol, row_horizon, cutoff,
         maturity, value, _created, schema, source, _resolved,
         forecast_available, _outcome_available) = row
        if (str(quant_id) != "q3_volatility" or
                FORMULA_VERSION_MAP["q3_volatility"] != str(formula)):
            continue
        identity = TargetIdentity(str(cycle), float(cutoff), float(maturity))
        yield RawFamilyObservation(
            int(record_id), identity, str(symbol), str(quant_id), str(formula),
            str(schema), str(source), str(row_horizon), MAGNITUDE_BPS,
            float(value), float(cutoff), float(cutoff),
            float(forecast_available), "FRESH",
        )


def rebuild_external_v2(*, database_url: str, workspace_root: Path,
                        state_as_of: float | None = None,
                        connect: Callable | None = None,
                        store: PostgresV2StateStore | None = None,
                        publish: bool = False,
                        interrupt_check: Callable[[], bool] | None = None,
                        ) -> ExternalRebuildResult:
    """Build all 72 frozen slots and optionally publish one atomic pair."""
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    _validate_database_url(database_url)
    if connect is None:
        import psycopg

        def connect_source(url: str):
            return psycopg.connect(
                url,
                connect_timeout=5,
                keepalives=1,
                keepalives_idle=5,
                keepalives_interval=2,
                keepalives_count=3,
            )

        connect = connect_source
    root = Path(workspace_root).resolve()
    with (_SQLITE_TMPDIR_LOCK, _single_owner(root),
          _database_owner(database_url, connect) as source,
          _cancel_on_interrupt(source, interrupt_check)):
        _cleanup_stale_workspaces(root)
        _raise_if_interrupted(interrupt_check)
        workspace = _workspace(root)
        previous_sqlite_tmpdir = os.environ.get("SQLITE_TMPDIR")
        # This command is an explicit single-owner offline process.  Scope
        # SQLite's process-level temporary-file root so external sorts and
        # journals are measured and removed with the owned workspace.
        os.environ["SQLITE_TMPDIR"] = str(workspace)
        sqlite = None
        views: list[ExternalV2AView] = []
        started = time.perf_counter()
        peak_disk = 0

        def sample_disk() -> None:
            nonlocal peak_disk
            _raise_if_interrupted(interrupt_check)
            peak_disk = max(peak_disk, _disk_bytes(workspace))

        try:
            sqlite = sqlite3.connect(workspace / "v2.sqlite3")
            _configure_sqlite(sqlite)
            # The top-level spool also performs windowed/ordered passes.  Its
            # transient temp files live under SQLITE_TMPDIR and can disappear
            # before a phase-boundary sample, so observe them during execution.
            sqlite.set_progress_handler(sample_disk, 100_000)
            sample_disk()
            cursor = source.cursor()
            try:
                cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
                    (),
                )
                cursor.execute(
                    "SELECT extract(epoch FROM "
                    "pg_catalog.transaction_timestamp())",
                    (),
                )
                snapshot = cursor.fetchone()
                if snapshot is None or not math.isfinite(float(snapshot[0])):
                    raise RuntimeError("V2_RESOLVED_EVIDENCE_UNAVAILABLE")
                snapshot_as_of = float(snapshot[0])
                if isinstance(state_as_of, bool):
                    raise ValueError("state_as_of is outside the source snapshot")
                candidate_as_of = (
                    snapshot_as_of if state_as_of is None else float(state_as_of)
                )
                if (not math.isfinite(candidate_as_of) or
                        candidate_as_of <= 0.0 or
                        candidate_as_of > snapshot_as_of):
                    raise ValueError("state_as_of is outside the source snapshot")
                (directional_pages, directional_rows,
                 directional_resolved_rows, directional_first,
                 directional_last) = _read_pages(
                    cursor, sqlite, state_as_of=candidate_as_of,
                    volatility=False, sample_disk=sample_disk,
                    interrupt_check=interrupt_check)
                (magnitude_pages, magnitude_rows,
                 magnitude_resolved_rows, magnitude_first,
                 magnitude_last) = _read_pages(
                    cursor, sqlite, state_as_of=candidate_as_of,
                    volatility=True, sample_disk=sample_disk,
                    interrupt_check=interrupt_check)
                integrity = sqlite.execute("PRAGMA quick_check").fetchone()
                if integrity != ("ok",):
                    raise RuntimeError("V2_EXTERNAL_WORKSPACE_CORRUPT")
            finally:
                close = getattr(cursor, "close", None)
                if callable(close): close()
            rollback = getattr(source, "rollback", None)
            if callable(rollback): rollback()

            versions = tuple((quant_id, version, DATA_SCHEMA_VERSION,
                              SOURCE_SPEC_VERSION)
                             for quant_id, version in FORMULA_VERSIONS)
            eligible_rows = 0

            def mark_eligible() -> None:
                nonlocal eligible_rows
                eligible_rows += 1

            for horizon in HORIZONS:
                baseline_disk = _disk_bytes(workspace)
                view = build_external_v2a(
                    state_as_of=candidate_as_of,
                    horizon=horizon,
                    target_spec_id=TARGET_SPEC_ID,
                    target_data_schema_version=DATA_SCHEMA_VERSION,
                    target_source_spec_version=SOURCE_SPEC_VERSION,
                    family_versions=versions,
                    targets=_iter_targets(sqlite, horizon),
                    observations=_iter_observations(sqlite, horizon),
                    root=workspace,
                    resource_sampler=sample_disk,
                    eligibility_observer=mark_eligible,
                )
                views.append(view)
                peak_disk = max(
                    peak_disk,
                    baseline_disk + view.peak_disk_bytes,
                    _disk_bytes(workspace),
                )
            views_tuple = tuple(views)
            calibration = build_external_v2b(views_tuple)
            sample_disk()
            covariances = tuple(
                build_external_v2c(view, calibration) for view in views_tuple
            )
            sample_disk()
            state = build_external_v2d(
                views_tuple,
                calibration,
                covariances,
                state_as_of=candidate_as_of,
            )
            sample_disk()
            encoded = serialize_v2_evidence_state(state)
            if deserialize_v2_evidence_state(encoded) != state:
                raise RuntimeError("V2_EXTERNAL_CANDIDATE_NOT_CANONICAL")
            if state.creation_status != "VALID" or state.top_level_status == "UNAVAILABLE":
                raise RuntimeError("V2_STATE_NOT_USABLE")
            horizon_counts = []
            family_counts = []
            effective_ns = []
            for view, horizon_state in zip(views_tuple, state.horizon_state_tuple):
                admitted_for_horizon = int(view.connection.execute(
                    "SELECT count(*) FROM admitted"
                ).fetchone()[0])
                horizon_counts.append((view.horizon, admitted_for_horizon))
                for quant_id, _formula, _schema, _source in view.selected_family_versions:
                    admitted_for_family = int(view.connection.execute(
                        "SELECT count(*) FROM admitted WHERE quant=?", (quant_id,)
                    ).fetchone()[0])
                    family_counts.append(
                        (view.horizon, quant_id, admitted_for_family)
                    )
                effective_ns.extend((horizon_state.horizon, item.quant_id,
                                     item.effective_n)
                                    for item in horizon_state.directional_calibrations)
                if horizon_state.q3.quant_id is not None:
                    effective_ns.append((horizon_state.horizon,
                                         horizon_state.q3.quant_id,
                                         float(horizon_state.q3.effective_n or 0.0)))
            admitted = sum(count for _horizon, count in horizon_counts)
            source_rows = directional_rows + magnitude_rows
            resolved_rows = directional_resolved_rows + magnitude_resolved_rows
            first_identity = directional_first or magnitude_first
            last_identity = magnitude_last or directional_last
            sample_disk()
            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
            receipt = seal_receipt(V2BuildReceipt(
                receipt_schema_version=RESOURCE_RECEIPT_SCHEMA_VERSION,
                state_id=state.state_id,
                state_as_of=state.state_as_of,
                stored_forecast_rows=source_rows,
                resolved_evidence_rows=resolved_rows,
                source_rows_read=source_rows,
                eligible_rows=eligible_rows,
                admitted_rows=admitted,
                rejected_rows=source_rows - admitted,
                pages_read=directional_pages + magnitude_pages,
                page_size=V2_STATE_BUILD_EVIDENCE_PAGE_SIZE,
                first_source_identity=first_identity,
                last_source_identity=last_identity,
                per_horizon_admitted_counts=tuple(horizon_counts),
                per_family_horizon_admitted_counts=tuple(family_counts),
                per_family_horizon_effective_n=tuple(effective_ns),
                build_elapsed_seconds=time.perf_counter() - started,
                peak_rss_bytes=rss,
                evidence_manifest_hash=state.evidence_manifest_hash,
                receipt_sha256="",
                temporary_disk_peak_bytes=peak_disk,
            ))
            publication = None
            _raise_if_interrupted(interrupt_check)
            if publish:
                publication_store = store or PostgresV2StateStore(database_url)
                publication = publication_store.insert_with_receipt(
                    state,
                    receipt,
                    connection=source,
                    interrupt_check=interrupt_check,
                    commit_guard=lambda: _publication_commit_guard(
                        interrupt_check
                    ),
                )
            return ExternalRebuildResult(state, receipt, peak_disk, publication)
        except sqlite3.OperationalError as error:
            if str(error) == "interrupted":
                _raise_if_interrupted(interrupt_check)
            raise
        finally:
            try:
                _cleanup_rebuild_resources(sqlite, views, workspace, root)
            finally:
                if previous_sqlite_tmpdir is None:
                    os.environ.pop("SQLITE_TMPDIR", None)
                else:
                    os.environ["SQLITE_TMPDIR"] = previous_sqlite_tmpdir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--state-as-of", type=float)
    publication = parser.add_mutually_exclusive_group()
    publication.add_argument("--publish", action="store_true")
    publication.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    with _interrupt_signals() as interrupt_check:
        result = rebuild_external_v2(
            database_url=args.database_url, workspace_root=args.workspace_root,
            state_as_of=args.state_as_of, publish=args.publish,
            interrupt_check=interrupt_check,
        )
    receipt = result.receipt
    print(json.dumps({
        "state": getattr(result.state, "creation_status", None),
        "state_id": result.state.state_id,
        "state_hash": result.state.state_hash,
        "top_level_status": getattr(result.state, "top_level_status", None),
        "evidence_manifest_hash": result.state.evidence_manifest_hash,
        "receipt_present": True,
        "receipt_state_id_match": (
            getattr(receipt, "state_id", result.state.state_id) ==
            result.state.state_id
        ),
        "receipt_sha256": receipt.receipt_sha256,
        "stored_forecast_rows": getattr(receipt, "stored_forecast_rows", None),
        "resolved_evidence_rows": getattr(
            receipt, "resolved_evidence_rows", None
        ),
        "source_rows_read": getattr(receipt, "source_rows_read", None),
        "eligible_rows": getattr(receipt, "eligible_rows", None),
        "admitted_rows": getattr(receipt, "admitted_rows", None),
        "rejected_rows": getattr(receipt, "rejected_rows", None),
        "pages_read": getattr(receipt, "pages_read", None),
        "build_elapsed_seconds": getattr(receipt, "build_elapsed_seconds", None),
        "peak_rss_bytes": getattr(receipt, "peak_rss_bytes", None),
        "temporary_disk_peak_bytes": result.temporary_disk_peak_bytes,
        "cleanup": True,
        "publication_status": result.publication_status,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
