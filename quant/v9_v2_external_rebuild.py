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
import shutil
import sqlite3
import tempfile
import time
from typing import Callable, Iterator

from .evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from .v9_production import (
    FORMULA_VERSIONS, FORMULA_VERSION_MAP, TARGET_SPEC_ID,
    V2_STATE_BUILD_EVIDENCE_PAGE_SIZE,
)
from .v9_v1_contract import DIRECTIONAL_BPS, HORIZONS, MAGNITUDE_BPS
from .v9_v2a_dataset import (
    RawFamilyObservation, RawTarget, TargetIdentity, build_v2a_dataset,
)
from .v9_v2b_calibration import build_v2b_calibration
from .v9_v2c_covariance import build_v2c_covariance
from .v9_v2d_evidence_state import (
    V2EvidenceState, build_v2d_evidence_state, deserialize_v2_evidence_state,
    serialize_v2_evidence_state,
)
from .v9_v2_build_receipt import (
    RECEIPT_SCHEMA_VERSION, V2BuildReceipt, seal_receipt,
)
from .v9_v2_state_store import PostgresV2StateStore


_OWNER = "ATOM-V9-V2-EXTERNAL-REBUILD-1"
_LOCK_NAME = ".atom-v9-v2-external-rebuild.lock"


@dataclass(frozen=True, slots=True)
class ExternalRebuildResult:
    state: V2EvidenceState
    receipt: V2BuildReceipt
    temporary_disk_peak_bytes: int
    publication_status: str | None


def _disk_bytes(workspace: Path) -> int:
    return sum(item.stat().st_size for item in workspace.iterdir()
               if item.is_file() and not item.is_symlink())


def _workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="atom-v2-external-rebuild-", dir=root)).resolve()
    os.chmod(path, 0o700)
    (path / "owner.json").write_text(json.dumps({
        "owner": _OWNER, "path": str(path), "uid": os.getuid(),
    }, sort_keys=True), encoding="ascii")
    return path


def _cleanup(workspace: Path, root: Path) -> None:
    if workspace.is_symlink() or workspace.resolve().parent != root.resolve():
        raise ValueError("refusing to clean an unowned V2 workspace")
    marker = workspace / "owner.json"
    expected = {"owner": _OWNER, "path": str(workspace.resolve()), "uid": os.getuid()}
    try:
        actual = json.loads(marker.read_text(encoding="ascii"))
    except (OSError, ValueError) as error:
        raise ValueError("refusing to clean an unowned V2 workspace") from error
    if actual != expected:
        raise ValueError("refusing to clean an unowned V2 workspace")
    shutil.rmtree(workspace)


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
                volatility: bool, sample_disk: Callable[[], None]
                ) -> tuple[int, int, str | None, str | None]:
    table = "volatility_forecasts" if volatility else "forecasts"
    outcome_table = "volatility_forecast_outcomes" if volatility else "forecast_outcomes"
    value = "f.forecast_volatility_bps" if volatility else "f.forecast_bps"
    numerical = ("o.resolved_epoch, " if volatility else
                 "f.source_as_of_epoch, o.outcome_bps, o.resolved_epoch, ")
    kinds = (("VOLATILITY_FORECAST", "VOLATILITY_OUTCOME") if volatility else
             ("DIRECTIONAL_FORECAST", "DIRECTIONAL_OUTCOME"))
    destination = "magnitude" if volatility else "directional"
    placeholders = ",".join("?" for _ in range(15 if volatility else 17))
    key = None
    pages = 0
    rows_read = 0
    first_identity = None
    last_identity = None
    while True:
        predicate = ""
        parameters: list[object] = [
            kinds[0], kinds[1], DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION,
            5.0, state_as_of,
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
                 extract(epoch FROM op.commit_observed_at)
          FROM public.{table} AS f
          JOIN public.{outcome_table} AS o USING (forecast_id)
          JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
            %s,f.forecast_id) AS fp ON true
          JOIN LATERAL atom_v9_internal.read_legacy_evidence_publication(
            %s,o.forecast_id) AS op ON true
          WHERE f.data_schema_version=%s AND f.source_spec_version=%s
            AND fp.commit_observed_at < to_timestamp(f.maturity_epoch)
            AND o.resolved_epoch >= f.maturity_epoch
            AND o.resolved_epoch <= f.maturity_epoch + %s
            AND op.commit_observed_at <= to_timestamp(%s) {predicate}
          ORDER BY f.horizon,f.cutoff_epoch,f.forecast_id LIMIT %s
        """, tuple(parameters))
        page = tuple(cursor.fetchall())
        if page:
            pages += 1
            sqlite.executemany(f"INSERT INTO {destination} VALUES({placeholders})", page)
            sqlite.commit()
            kind = "magnitude" if volatility else "directional"
            page_first = page[0]
            page_last = page[-1]
            if first_identity is None:
                first_identity = (
                    f"{kind}:{page_first[5]}:{float(page_first[6]).hex()}:"
                    f"{page_first[0]}")
            last_identity = (
                f"{kind}:{page_last[5]}:{float(page_last[6]).hex()}:"
                f"{page_last[0]}")
            rows_read += len(page)
            sample_disk()
        if len(page) < V2_STATE_BUILD_EVIDENCE_PAGE_SIZE:
            return pages, rows_read, first_identity, last_identity
        last = page[-1]
        next_key = (last[5], last[6], last[0])
        if key is not None and next_key <= key:
            raise RuntimeError("V2_EVIDENCE_PAGINATION_STALLED")
        key = next_key


def _raw_rows(sqlite: sqlite3.Connection, horizon: str
              ) -> tuple[list[RawTarget], list[RawFamilyObservation]]:
    targets: list[RawTarget] = []
    observations: list[RawFamilyObservation] = []
    available_by_identity = {
        TargetIdentity(str(cycle), float(cutoff), float(maturity)): float(available)
        for cycle, cutoff, maturity, available in sqlite.execute(
            "SELECT cycle_id,cutoff,maturity,max(outcome_available) FROM directional "
            "WHERE horizon=? GROUP BY cycle_id,cutoff,maturity", (horizon,))
    }
    for row in sqlite.execute(
            "SELECT * FROM directional WHERE horizon=? ORDER BY cutoff,forecast_id",
            (horizon,)):
        (record_id, quant_id, formula, cycle, symbol, row_horizon, cutoff,
         maturity, value, _created, schema, source, source_as_of, outcome,
         _resolved, forecast_available, _outcome_available) = row
        if FORMULA_VERSION_MAP.get(str(quant_id)) != str(formula):
            continue
        identity = TargetIdentity(str(cycle), float(cutoff), float(maturity))
        targets.append(RawTarget(
            int(record_id), str(cycle), str(symbol), TARGET_SPEC_ID, str(schema),
            str(source), str(row_horizon), float(cutoff), float(maturity),
            available_by_identity[identity], float(outcome),
        ))
        # Certified-unavailable Q10/Q4 rows have no causal source timestamp.
        # They remain represented by the frozen family lineage but are not
        # fabricated into an observation.
        if str(quant_id) in {"q4_stat_arb", "q10_options_vol"} and source_as_of is None:
            continue
        source_epoch = float(cutoff if source_as_of is None else source_as_of)
        observations.append(RawFamilyObservation(
            int(record_id), identity, str(symbol), str(quant_id), str(formula),
            str(schema), str(source), str(row_horizon), DIRECTIONAL_BPS,
            float(value), float(cutoff), source_epoch, float(forecast_available),
            "FRESH",
        ))
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
        observations.append(RawFamilyObservation(
            int(record_id), identity, str(symbol), str(quant_id), str(formula),
            str(schema), str(source), str(row_horizon), MAGNITUDE_BPS,
            float(value), float(cutoff), float(cutoff),
            float(forecast_available), "FRESH",
        ))
    return targets, observations


def rebuild_external_v2(*, database_url: str, workspace_root: Path,
                        state_as_of: float | None = None,
                        connect: Callable | None = None,
                        store: PostgresV2StateStore | None = None,
                        publish: bool = True) -> ExternalRebuildResult:
    """Build all 72 frozen slots and optionally publish one atomic pair."""
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    if connect is None:
        import psycopg
        connect = psycopg.connect
    root = Path(workspace_root).resolve()
    with _single_owner(root):
        workspace = _workspace(root)
        sqlite = None
        started = time.perf_counter()
        peak_disk = 0
        def sample_disk() -> None:
            nonlocal peak_disk
            peak_disk = max(peak_disk, _disk_bytes(workspace))
        try:
            sqlite = sqlite3.connect(workspace / "v2.sqlite3")
            _configure_sqlite(sqlite)
            sample_disk()
            source = connect(database_url)
            try:
                cursor = source.cursor()
                try:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY", ())
                    cursor.execute("SELECT extract(epoch FROM pg_catalog.transaction_timestamp())", ())
                    snapshot = cursor.fetchone()
                    if snapshot is None or not math.isfinite(float(snapshot[0])):
                        raise RuntimeError("V2_RESOLVED_EVIDENCE_UNAVAILABLE")
                    snapshot_as_of = float(snapshot[0])
                    candidate_as_of = snapshot_as_of if state_as_of is None else float(state_as_of)
                    if (not math.isfinite(candidate_as_of) or candidate_as_of <= 0.0 or
                            candidate_as_of > snapshot_as_of):
                        raise ValueError("state_as_of is outside the source snapshot")
                    (directional_pages, directional_rows, directional_first,
                     directional_last) = _read_pages(
                        cursor, sqlite, state_as_of=candidate_as_of,
                        volatility=False, sample_disk=sample_disk)
                    (magnitude_pages, magnitude_rows, magnitude_first,
                     magnitude_last) = _read_pages(
                        cursor, sqlite, state_as_of=candidate_as_of,
                        volatility=True, sample_disk=sample_disk)
                    integrity = sqlite.execute("PRAGMA quick_check").fetchone()
                    if integrity != ("ok",):
                        raise RuntimeError("V2_EXTERNAL_WORKSPACE_CORRUPT")
                finally:
                    close = getattr(cursor, "close", None)
                    if callable(close): close()
                rollback = getattr(source, "rollback", None)
                if callable(rollback): rollback()
            finally:
                close = getattr(source, "close", None)
                if callable(close): close()

            versions = tuple((quant_id, version, DATA_SCHEMA_VERSION,
                              SOURCE_SPEC_VERSION)
                             for quant_id, version in FORMULA_VERSIONS)
            datasets = []
            eligible_rows = 0
            for horizon in HORIZONS:
                targets, observations = _raw_rows(sqlite, horizon)
                eligible_rows += len(observations)
                datasets.append(build_v2a_dataset(
                    state_as_of=candidate_as_of, horizon=horizon,
                    target_spec_id=TARGET_SPEC_ID,
                    target_data_schema_version=DATA_SCHEMA_VERSION,
                    target_source_spec_version=SOURCE_SPEC_VERSION,
                    family_versions=versions, targets=targets,
                    observations=observations,
                ))
                del targets, observations
            datasets_tuple = tuple(datasets)
            calibration = build_v2b_calibration(datasets_tuple)
            covariances = tuple(build_v2c_covariance(dataset, calibration)
                                for dataset in datasets_tuple)
            state = build_v2d_evidence_state(
                state_as_of=candidate_as_of, datasets=datasets_tuple,
                calibrations=(calibration,), covariances=covariances,
            )
            encoded = serialize_v2_evidence_state(state)
            if deserialize_v2_evidence_state(encoded) != state:
                raise RuntimeError("V2_EXTERNAL_CANDIDATE_NOT_CANONICAL")
            if state.creation_status != "VALID" or state.top_level_status == "UNAVAILABLE":
                raise RuntimeError("V2_STATE_NOT_USABLE")
            horizon_counts = []
            family_counts = []
            effective_ns = []
            for dataset, horizon_state in zip(datasets_tuple, state.horizon_state_tuple):
                subsets = (*dataset.directional_subsets,
                           *((dataset.q3_subset,) if dataset.q3_subset else ()))
                horizon_counts.append((dataset.horizon,
                                       sum(len(item.observations) for item in subsets)))
                family_counts.extend((dataset.horizon, item.quant_id,
                                      len(item.observations)) for item in subsets)
                effective_ns.extend((horizon_state.horizon, item.quant_id,
                                     item.effective_n)
                                    for item in horizon_state.directional_calibrations)
                if horizon_state.q3.quant_id is not None:
                    effective_ns.append((horizon_state.horizon,
                                         horizon_state.q3.quant_id,
                                         float(horizon_state.q3.effective_n or 0.0)))
            admitted = sum(count for _horizon, count in horizon_counts)
            source_rows = directional_rows + magnitude_rows
            first_identity = directional_first or magnitude_first
            last_identity = magnitude_last or directional_last
            sample_disk()
            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
            receipt = seal_receipt(V2BuildReceipt(
                RECEIPT_SCHEMA_VERSION, state.state_id, state.state_as_of,
                source_rows, source_rows, source_rows, eligible_rows, admitted,
                source_rows - admitted, directional_pages + magnitude_pages,
                V2_STATE_BUILD_EVIDENCE_PAGE_SIZE,
                first_identity, last_identity,
                tuple(horizon_counts), tuple(family_counts), tuple(effective_ns),
                time.perf_counter() - started, rss,
                state.evidence_manifest_hash, "",
            ))
            publication = None
            if publish:
                publication_store = store or PostgresV2StateStore(database_url)
                publication = publication_store.insert_with_receipt(state, receipt)
            return ExternalRebuildResult(state, receipt, peak_disk, publication)
        finally:
            if sqlite is not None:
                sqlite.close()
            _cleanup(workspace, root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--state-as-of", type=float)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    result = rebuild_external_v2(
        database_url=args.database_url, workspace_root=args.workspace_root,
        state_as_of=args.state_as_of, publish=not args.validate_only,
    )
    print(json.dumps({
        "state_id": result.state.state_id,
        "state_hash": result.state.state_hash,
        "evidence_manifest_hash": result.state.evidence_manifest_hash,
        "receipt_sha256": result.receipt.receipt_sha256,
        "temporary_disk_peak_bytes": result.temporary_disk_peak_bytes,
        "publication_status": result.publication_status,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
