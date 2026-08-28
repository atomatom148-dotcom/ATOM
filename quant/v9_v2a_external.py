"""Offline-only SQLite-backed V2A parity adapter.

The adapter preserves the frozen V2A byte contract while keeping evidence in
an owned disk workspace.  Python retains only one source row or duplicate
identity group at a time; canonical skeletons, family subsets and pair support
remain ordered SQLite relations.
"""

from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Iterable

from quant.v9_v2a_dataset import (
    DATASET_SCHEMA_VERSION,
    DIRECTIONAL_BPS,
    DIRECTIONAL_FAMILIES,
    HORIZON_SECONDS,
    MAGNITUDE_BPS,
    METHOD_VERSION,
    Q3,
    ExclusionCount,
    FamilyLineage,
    RawFamilyObservation,
    RawTarget,
)
from quant.v9_v2b_calibration import (
    ALPHA_BIAS,
    FORMULA_VERSION as V2B_VERSION,
    BiasDiagnostic,
    DirectionalCalibration,
    EffectiveN,
    V2BCalibration,
    v2b_component_hash,
)
from quant.v9_v2c_covariance import METHOD_VERSION as V2C_VERSION, V2CCovariance
from quant.v9_v2d_evidence_state import (
    CALIBRATION_METHOD_VERSION,
    COVARIANCE_METHOD_VERSION,
    EFFECTIVE_N_METHOD_VERSION,
    MODEL_FAMILY,
    NUMERICAL_CANONICALIZATION_VERSION,
    STATE_SCHEMA_VERSION,
    STATE_VERSION,
    ComponentHash,
    DirectionalCalibrationState,
    HorizonEvidenceState,
    Q3MagnitudeState,
    V2EvidenceState,
    _digest,
    _missing,
    serialize_v2_evidence_state,
    v2d_state_hash,
)

_OWNER = "ATOM-V9-V2A-EXTERNAL-2"
_Q = "q1_momentum"
_H = "30S"


def _finite(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _ft(value):
    return {"$float64": (0.0 if value == 0.0 else float(value)).hex()}


def _row_object(keys, values):
    return {k: (_ft(v) if isinstance(v, float) else v) for k, v in zip(keys, values)}


@dataclass(slots=True)
class ExternalV2AView:
    workspace: Path
    connection: sqlite3.Connection
    state_as_of: float
    target_spec_id: str
    target_data_schema_version: str
    target_source_spec_version: str
    formula_version: str
    family_data_schema_version: str
    family_source_spec_version: str
    raw_resolved_count: int
    skeleton_count: int
    observation_count: int
    training_start: float | None
    training_end: float | None
    exclusions: tuple[ExclusionCount, ...]
    dataset_hash: str
    peak_disk_bytes: int
    horizon: str = _H
    selected_family_versions: tuple[tuple[str, str, str, str], ...] = ()

    @property
    def family_lineage(self):
        return tuple(
            FamilyLineage(q, f, s, src)
            for q, f, s, src in self.selected_family_versions
        )

    def close(self):
        self.connection.close()

    def disk_bytes(self):
        return sum(p.stat().st_size for p in self.workspace.iterdir() if p.is_file())


def _owned_workspace(root):
    path = Path(tempfile.mkdtemp(prefix="atom-v2a-external-", dir=root)).resolve()
    os.chmod(path, 0o700)
    (path / "owner.json").write_text(
        json.dumps({"owner": _OWNER, "path": str(path), "uid": os.getuid()}),
        encoding="ascii",
    )
    return path


def cleanup_owned_workspace(path, *, root=None):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("refusing to clean an unowned workspace")
    path = path.resolve()
    if root is not None and path.parent != Path(root).resolve():
        raise ValueError("workspace is outside the configured root")
    if not path.name.startswith("atom-v2a-external-"):
        raise ValueError("refusing to clean an unowned workspace")
    try:
        data = json.loads((path / "owner.json").read_text(encoding="ascii"))
    except (OSError, ValueError) as error:
        raise ValueError("refusing to clean an unowned workspace") from error
    if data != {"owner": _OWNER, "path": str(path), "uid": os.getuid()}:
        raise ValueError("refusing to clean an unowned workspace")
    shutil.rmtree(path)


def _identity_json(row):
    return json.dumps(
        _row_object(
            ("cutoff_epoch", "cycle_id", "maturity_epoch"), (row[1], row[0], row[2])
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _stream_array(put, rows, encode):
    put("[")
    for index, row in enumerate(rows):
        if index:
            put(",")
        put(encode(row))
    put("]")


def _stream_hash(view):
    con = view.connection
    h = hashlib.sha256()

    def put(value):
        h.update(value.encode("ascii"))

    def scalar(value):
        return json.dumps(
            _ft(value) if isinstance(value, float) else value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    directional = [
        q for q, _, _, _ in view.selected_family_versions if q in DIRECTIONAL_FAMILIES
    ]
    q3 = next((x for x in view.selected_family_versions if x[0] == Q3), None)
    fields = [
        ("complete_case_target_identities", "complete"),
        ("dataset_schema_version", DATASET_SCHEMA_VERSION),
        ("directional_subsets", "subsets"),
        ("exclusions", "exclusions"),
        ("family_lineage", "lineage"),
        ("horizon", view.horizon),
        ("method_version", METHOD_VERSION),
        ("pair_support", "pairs"),
        ("q3_subset", "q3"),
        ("raw_resolved_count", view.raw_resolved_count),
        ("skeleton", "skeleton"),
        ("state_as_of", view.state_as_of),
        ("symbol", "COIN"),
        ("target_data_schema_version", view.target_data_schema_version),
        ("target_source_spec_version", view.target_source_spec_version),
        ("target_spec_id", view.target_spec_id),
        ("training_end", view.training_end),
        ("training_start", view.training_start),
    ]
    put("{")
    for fi, (name, value) in enumerate(fields):
        if fi:
            put(",")
        put(json.dumps(name) + ":")
        if value == "complete":
            if not directional:
                put("[]")
            else:
                marks = ",".join("?" for _ in directional)
                rows = con.execute(
                    f"SELECT s.cycle,s.cutoff,s.maturity FROM skeleton s WHERE (SELECT count(DISTINCT a.quant) FROM admitted a WHERE a.skeleton_ordinal=s.ordinal AND a.quant IN ({marks}))=? ORDER BY s.ordinal",
                    (*directional, len(directional)),
                )
                _stream_array(put, rows, _identity_json)
        elif value in ("subsets", "q3"):
            families = directional if value == "subsets" else ([Q3] if q3 else [])
            if value == "q3" and not q3:
                put("null")
                continue
            if value == "subsets":
                put("[")
            for family_index, q in enumerate(families):
                if family_index:
                    put(",")
                version = next(x for x in view.selected_family_versions if x[0] == q)
                put('{"formula_version":' + scalar(version[1]) + ',"observations":')
                keys = (
                    "available_epoch",
                    "data_schema_version",
                    "forecast_cutoff_epoch",
                    "formula_version",
                    "numerical_type",
                    "quant_id",
                    "record_id",
                    "source_as_of_epoch",
                    "source_spec_version",
                    "target_identity",
                    "value_bps",
                )
                rows = con.execute(
                    "SELECT available,family_schema,forecast,formula,numerical,quant,record_id,source_as_of,family_source,cycle,cutoff,maturity,value FROM admitted WHERE quant=? ORDER BY skeleton_ordinal",
                    (q,),
                )

                def encode(row):
                    identity = _row_object(
                        ("cutoff_epoch", "cycle_id", "maturity_epoch"),
                        (row[10], row[9], row[11]),
                    )
                    return json.dumps(
                        _row_object(keys, (*row[:9], identity, row[12])),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=True,
                    )

                _stream_array(put, rows, encode)
                put(',"quant_id":' + scalar(q) + "}")
            if value == "subsets":
                put("]")
        elif value == "exclusions":
            put(
                json.dumps(
                    [
                        {"count": x.count, "reason_code": x.reason_code}
                        for x in view.exclusions
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        elif value == "lineage":
            put(
                json.dumps(
                    [
                        {
                            "data_schema_version": s,
                            "formula_version": f,
                            "quant_id": q,
                            "source_spec_version": src,
                        }
                        for q, f, s, src in view.selected_family_versions
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        elif value == "pairs":
            put("[")
            pi = 0
            for i, left in enumerate(directional):
                for right in directional[i + 1 :]:
                    if pi:
                        put(",")
                    put(
                        '{"left_quant_id":'
                        + scalar(left)
                        + ',"right_quant_id":'
                        + scalar(right)
                        + ',"target_identities":'
                    )
                    rows = con.execute(
                        "SELECT s.cycle,s.cutoff,s.maturity FROM skeleton s JOIN admitted a ON a.skeleton_ordinal=s.ordinal AND a.quant=? JOIN admitted b ON b.skeleton_ordinal=s.ordinal AND b.quant=? ORDER BY s.ordinal",
                        (left, right),
                    )
                    _stream_array(put, rows, _identity_json)
                    put("}")
                    pi += 1
            put("]")
        elif value == "skeleton":
            keys = (
                "cutoff_epoch",
                "identity",
                "record_id",
                "resolved_epoch",
                "target_bps",
            )
            rows = con.execute(
                "SELECT cutoff,cycle,maturity,target_record,resolved,target FROM skeleton ORDER BY ordinal"
            )

            def enc(row):
                return json.dumps(
                    _row_object(
                        keys,
                        (
                            row[0],
                            _row_object(
                                ("cutoff_epoch", "cycle_id", "maturity_epoch"),
                                (row[0], row[1], row[2]),
                            ),
                            row[3],
                            row[4],
                            row[5],
                        ),
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                )

            _stream_array(put, rows, enc)
        else:
            put(scalar(value))
    put("}")
    return h.hexdigest()


def build_external_v2a(
    *,
    state_as_of,
    target_spec_id,
    target_data_schema_version,
    target_source_spec_version,
    formula_version=None,
    family_data_schema_version=None,
    family_source_spec_version=None,
    family_versions=None,
    targets: Iterable[RawTarget],
    observations: Iterable[RawFamilyObservation],
    root=None,
    interrupt=None,
    horizon=_H,
):
    if horizon not in HORIZON_SECONDS or not _finite(state_as_of):
        raise ValueError("invalid horizon or state_as_of")
    if family_versions is None:
        family_versions = (
            (
                _Q,
                formula_version,
                family_data_schema_version,
                family_source_spec_version,
            ),
        )
    rows = tuple(family_versions)
    versions = {q: (f, s, src) for q, f, s, src in rows}
    if len(rows) != len(versions):
        raise ValueError("family_versions contains a duplicate quant_id")
    family_order = (*DIRECTIONAL_FAMILIES, Q3)
    if any(
        q not in family_order
        or any(not isinstance(x, str) or not x for x in (q, f, s, src))
        for q, f, s, src in rows
    ):
        raise ValueError("family_versions contains invalid lineage")
    selected = tuple((q, *versions[q]) for q in family_order if q in versions)
    workspace = _owned_workspace(root)
    con = None
    peak = 0
    succeeded = False

    def sample():
        nonlocal peak
        peak = max(
            peak, sum(p.stat().st_size for p in workspace.iterdir() if p.is_file())
        )

    counts = {}

    def exclude(reason):
        counts[reason] = counts.get(reason, 0) + 1

    try:
        con = sqlite3.connect(workspace / "v2a.sqlite3")
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA temp_store=FILE")
        con.executescript("""
CREATE TABLE targets(cycle TEXT,cutoff REAL,maturity REAL,record_id INTEGER,resolved REAL,target REAL,PRIMARY KEY(cycle,cutoff,maturity,record_id));
CREATE TABLE canonical_targets(cycle TEXT,cutoff REAL,maturity REAL,record_id INTEGER,resolved REAL,target REAL,PRIMARY KEY(cycle,cutoff,maturity));
CREATE TABLE skeleton(ordinal INTEGER PRIMARY KEY,cycle TEXT,cutoff REAL,maturity REAL,target_record INTEGER,resolved REAL,target REAL,UNIQUE(cycle,cutoff,maturity));
CREATE TABLE observations(quant TEXT,cycle TEXT,cutoff REAL,maturity REAL,record_id INTEGER,value REAL,forecast REAL,source_as_of REAL,available REAL,formula TEXT,family_schema TEXT,family_source TEXT,numerical TEXT,payload BLOB,payload_hash TEXT);
CREATE INDEX observations_order ON observations(quant,cycle,cutoff,maturity,record_id);
CREATE TABLE canonical_observations(quant TEXT,cycle TEXT,cutoff REAL,maturity REAL,record_id INTEGER,value REAL,forecast REAL,source_as_of REAL,available REAL,formula TEXT,family_schema TEXT,family_source TEXT,numerical TEXT,PRIMARY KEY(quant,cycle,cutoff,maturity));
CREATE TABLE admitted(skeleton_ordinal INTEGER,cycle TEXT,cutoff REAL,maturity REAL,target_record INTEGER,resolved REAL,target REAL,record_id INTEGER,value REAL,forecast REAL,source_as_of REAL,available REAL,formula TEXT,family_schema TEXT,family_source TEXT,numerical TEXT,quant TEXT,PRIMARY KEY(quant,skeleton_ordinal));
""")
        raw = 0
        seconds = HORIZON_SECONDS[horizon]
        for i, t in enumerate(targets):
            if interrupt == "ingestion" and i == 1:
                raise InterruptedError("interrupted during ingestion")
            if not t.cycle_id:
                exclude("MALFORMED_RECORD")
                continue
            if not all(
                _finite(x)
                for x in (
                    t.cutoff_epoch,
                    t.maturity_epoch,
                    t.resolved_epoch,
                    t.target_bps,
                )
            ):
                exclude("NONFINITE_VALUE")
                continue
            if (
                t.maturity_epoch != t.cutoff_epoch + seconds
                or t.resolved_epoch < t.maturity_epoch
            ):
                exclude("TARGET_TIMING_MISMATCH")
                continue
            if t.resolved_epoch > state_as_of:
                exclude("TARGET_UNRESOLVED")
                continue
            raw += 1
            if (t.symbol, t.horizon, t.target_spec_id) != (
                "COIN",
                horizon,
                target_spec_id,
            ):
                exclude("OUTSIDE_VERSION_COHORT")
                continue
            if t.data_schema_version != target_data_schema_version:
                exclude("DATA_SCHEMA_VERSION_MISMATCH")
                continue
            if t.source_spec_version != target_source_spec_version:
                exclude("SOURCE_SPEC_VERSION_MISMATCH")
                continue
            con.execute(
                "INSERT INTO targets VALUES(?,?,?,?,?,?)",
                (
                    t.cycle_id,
                    t.cutoff_epoch,
                    t.maturity_epoch,
                    t.record_id,
                    t.resolved_epoch,
                    t.target_bps,
                ),
            )
            if (i + 1) % 4096 == 0:
                sample()
                con.commit()
                sample()
        sample()
        con.commit()
        sample()
        pending = None
        representative = None
        conflict = False
        for row in con.execute(
            "SELECT cycle,cutoff,maturity,record_id,resolved,target FROM targets ORDER BY cycle,cutoff,maturity,record_id"
        ):
            key = row[:3]
            if pending is not None and key != pending:
                if conflict:
                    exclude("TARGET_CONFLICT")
                else:
                    con.execute(
                        "INSERT INTO canonical_targets VALUES(?,?,?,?,?,?)",
                        representative,
                    )
            if key != pending:
                pending = key
                representative = row
                mathematical = row[4:]
                conflict = False
            elif row[4:] != mathematical:
                conflict = True
        if pending is not None:
            if conflict:
                exclude("TARGET_CONFLICT")
            else:
                con.execute(
                    "INSERT INTO canonical_targets VALUES(?,?,?,?,?,?)", representative
                )
        sample()
        con.commit()
        sample()
        previous = None
        ordinal = 0
        for row in con.execute(
            "SELECT cycle,cutoff,maturity,record_id,resolved,target FROM canonical_targets ORDER BY cutoff,cycle,maturity,record_id"
        ):
            if previous is not None and row[1] < previous + seconds:
                exclude("OVERLAP_REMOVED")
                continue
            previous = row[1]
            con.execute("INSERT INTO skeleton VALUES(?,?,?,?,?,?,?)", (ordinal, *row))
            ordinal += 1
        sample()
        con.commit()
        sample()
        for i, o in enumerate(observations):
            if (
                o.quant_id not in family_order
                or o.symbol != "COIN"
                or o.horizon != horizon
            ):
                exclude("MALFORMED_RECORD")
                continue
            target = con.execute(
                "SELECT cutoff,maturity FROM skeleton WHERE cycle=? AND cutoff=? AND maturity=?",
                (
                    o.target_identity.cycle_id,
                    o.target_identity.cutoff_epoch,
                    o.target_identity.maturity_epoch,
                ),
            ).fetchone()
            if target is None:
                exclude("MISSING_SYNCHRONIZED_FAMILY")
                continue
            wanted = versions.get(o.quant_id)
            if wanted is None:
                exclude("OUTSIDE_VERSION_COHORT")
                continue
            if o.formula_version != wanted[0]:
                exclude("FORMULA_VERSION_MISMATCH")
                continue
            if o.data_schema_version != wanted[1]:
                exclude("DATA_SCHEMA_VERSION_MISMATCH")
                continue
            if o.source_spec_version != wanted[2]:
                exclude("SOURCE_SPEC_VERSION_MISMATCH")
                continue
            if not _finite(o.value_bps) or not all(
                _finite(x)
                for x in (
                    o.forecast_cutoff_epoch,
                    o.source_as_of_epoch,
                    o.available_epoch,
                )
            ):
                exclude("NONFINITE_VALUE")
                continue
            expected = MAGNITUDE_BPS if o.quant_id == Q3 else DIRECTIONAL_BPS
            if o.numerical_type != expected or (o.quant_id == Q3 and o.value_bps < 0):
                exclude("MALFORMED_RECORD")
                continue
            if o.forecast_cutoff_epoch > state_as_of or o.available_epoch > state_as_of:
                exclude("FUTURE_INPUT")
                continue
            if o.forecast_cutoff_epoch != target[0]:
                exclude("FAMILY_TARGET_MISMATCH")
                continue
            if (
                not (
                    o.source_as_of_epoch
                    <= o.forecast_cutoff_epoch
                    <= o.available_epoch
                    < target[1]
                )
                or o.availability_state != "FRESH"
            ):
                exclude("FORECAST_NOT_CAUSAL")
                continue
            payload = repr(o).encode()
            digest = hashlib.sha256(payload).hexdigest()
            con.execute(
                "INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    o.quant_id,
                    o.target_identity.cycle_id,
                    o.target_identity.cutoff_epoch,
                    o.target_identity.maturity_epoch,
                    o.record_id,
                    0.0 if o.value_bps == 0.0 else o.value_bps,
                    o.forecast_cutoff_epoch,
                    o.source_as_of_epoch,
                    o.available_epoch,
                    o.formula_version,
                    o.data_schema_version,
                    o.source_spec_version,
                    o.numerical_type,
                    payload,
                    digest,
                ),
            )
            if (i + 1) % 4096 == 0:
                sample()
                con.commit()
                sample()
        sample()
        con.commit()
        sample()
        pending = None
        conflict = False
        for row in con.execute(
            "SELECT quant,cycle,cutoff,maturity,record_id,value,forecast,source_as_of,available,formula,family_schema,family_source,numerical FROM observations ORDER BY quant,cycle,cutoff,maturity,record_id"
        ):
            key = row[:4]
            if pending is not None and key != pending:
                if conflict:
                    exclude("DUPLICATE_CONFLICT")
                else:
                    con.execute(
                        "INSERT INTO canonical_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        representative,
                    )
            if key != pending:
                pending = key
                representative = row
                mathematical = (row[5:9], row[10:13])
                conflict = False
            elif (row[5:9], row[10:13]) != mathematical:
                conflict = True
        if pending is not None:
            if conflict:
                exclude("DUPLICATE_CONFLICT")
            else:
                con.execute(
                    "INSERT INTO canonical_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    representative,
                )
        sample()
        con.commit()
        sample()
        admitted = 0
        for row in con.execute(
            "SELECT s.ordinal,s.cycle,s.cutoff,s.maturity,s.target_record,s.resolved,s.target,o.record_id,o.value,o.forecast,o.source_as_of,o.available,o.formula,o.family_schema,o.family_source,o.numerical,o.quant FROM skeleton s JOIN canonical_observations o ON o.cycle=s.cycle AND o.cutoff=s.cutoff AND o.maturity=s.maturity ORDER BY o.quant,s.ordinal"
        ):
            if interrupt == "ordered_pass" and admitted == 1:
                raise InterruptedError("interrupted during ordered pass")
            con.execute(
                "INSERT INTO admitted VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row
            )
            admitted += 1
            if admitted % 4096 == 0:
                sample()
        sample()
        con.commit()
        sample()
        first = con.execute(
            "SELECT cutoff FROM canonical_targets ORDER BY cutoff,cycle,maturity,record_id LIMIT 1"
        ).fetchone()
        last = con.execute(
            "SELECT cutoff FROM canonical_targets ORDER BY cutoff DESC,cycle DESC,maturity DESC,record_id DESC LIMIT 1"
        ).fetchone()
        primary = selected[0] if selected else (_Q, "", "", "")
        view = ExternalV2AView(
            workspace,
            con,
            state_as_of,
            target_spec_id,
            target_data_schema_version,
            target_source_spec_version,
            primary[1],
            primary[2],
            primary[3],
            raw,
            ordinal,
            admitted,
            first[0] if first else None,
            last[0] if last else None,
            tuple(ExclusionCount(k, counts[k]) for k in sorted(counts)),
            "",
            0,
            horizon,
            selected,
        )
        view.dataset_hash = _stream_hash(view)
        sample()
        view.peak_disk_bytes = peak
        succeeded = True
        return view
    finally:
        if not succeeded:
            if con is not None:
                con.close()
            cleanup_owned_workspace(workspace, root=root)


def _scores(view):
    for target, value in view.connection.execute(
        "SELECT target,value FROM admitted WHERE quant=? ORDER BY skeleton_ordinal",
        (_Q,),
    ):
        yield target - value


def validate_external_v2a(view: ExternalV2AView) -> None:
    """Fail closed if the sealed owned workspace or staged bytes changed."""
    marker = json.loads((view.workspace / "owner.json").read_text(encoding="ascii"))
    if marker != {"owner": _OWNER, "path": str(view.workspace), "uid": os.getuid()}:
        raise ValueError("workspace ownership validation failed")
    for payload, digest in view.connection.execute(
        "SELECT payload,payload_hash FROM observations"
    ):
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("corrupt staged payload")
    if _stream_hash(view) != view.dataset_hash:
        raise ValueError("external V2A parity mismatch")


def _effective_n(view: ExternalV2AView) -> EffectiveN:
    n = view.observation_count
    if not n:
        return EffectiveN(0, 0.0, 1.0, 0.0, 0)
    mean = math.fsum(_scores(view)) / n
    denominator = math.fsum((x - mean) ** 2 for x in _scores(view))
    scale = math.fsum(x * x for x in _scores(view)) + n * mean * mean
    if abs(denominator) <= 64 * math.ulp(1.0) * max(1.0, scale):
        return EffectiveN(
            n, float(n), 1.0, float(n), 0, ("SERIAL_DEPENDENCE_UNIDENTIFIABLE",)
        )
    view.connection.execute("DROP TABLE IF EXISTS autocorrelation_terms")
    view.connection.execute(
        "CREATE TABLE autocorrelation_terms(lag INTEGER PRIMARY KEY,value REAL)"
    )
    retained = 0
    # Only one adjacent odd/even Geyer pair is live at a time.  Frozen IPS
    # stops at the first non-positive pair, so later autocorrelations cannot
    # affect either the retained lag or the weighted sum.
    odd_rho = None
    for lag in range(1, n):
        products = (
            a[0] * a[1]
            for a in view.connection.execute(
                "SELECT (a.target-a.value-?),(b.target-b.value-?) FROM admitted a JOIN admitted b ON b.quant=a.quant AND b.skeleton_ordinal=a.skeleton_ordinal+? WHERE a.quant=? ORDER BY a.skeleton_ordinal",
                (mean, mean, lag, _Q),
            )
        )
        rho = math.fsum(products) / denominator
        if lag % 2:
            odd_rho = rho
        elif odd_rho is not None and odd_rho + rho > 0:
            view.connection.executemany(
                "INSERT INTO autocorrelation_terms VALUES(?,?)",
                (
                    (lag - 1, (1.0 - (lag - 1) / n) * odd_rho),
                    (lag, (1.0 - lag / n) * rho),
                ),
            )
            retained = lag
        else:
            break
    tau = max(
        1.0,
        1.0
        + 2.0
        * math.fsum(
            row[0]
            for row in view.connection.execute(
                "SELECT value FROM autocorrelation_terms ORDER BY lag"
            )
        ),
    )
    return EffectiveN(n, float(n), tau, min(float(n), max(1.0, n / tau)), retained)


def _require_phase1b_calibration_scope(view: ExternalV2AView) -> None:
    """Keep the legacy proof-only V2B helper fenced from Phase 1C-A views."""

    expected = (
        (
            _Q,
            view.formula_version,
            view.family_data_schema_version,
            view.family_source_spec_version,
        ),
    )
    if view.horizon != _H or view.selected_family_versions != expected:
        raise ValueError(
            "external V2B remains proof-only for q1_momentum/30S; "
            "Phase 1C-A exposes V2A only"
        )


def build_external_v2b(view: ExternalV2AView) -> V2BCalibration:
    _require_phase1b_calibration_scope(view)
    validate_external_v2a(view)
    en = _effective_n(view)
    n = view.observation_count
    if not n:
        bias = BiasDiagnostic(0.0, None, None, None, ALPHA_BIAS, "UNDETERMINED")
        item = DirectionalCalibration(
            _Q,
            view.formula_version,
            _H,
            view.family_data_schema_version,
            view.family_source_spec_version,
            view.dataset_hash,
            view.raw_resolved_count,
            view.skeleton_count,
            0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            None,
            None,
            0.0,
            1.0,
            False,
            False,
            ((0.0, 0.0), (0.0, 0.0)),
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            bias,
            "UNAVAILABLE",
            ("NO_EVIDENCE",),
        )
        return V2BCalibration(
            V2B_VERSION,
            ((_H, view.dataset_hash),),
            (item,),
            (),
            0.0,
            "SCALE_CONDITIONING_UNAVAILABLE_PENDING_CAUSAL_V3_REPLAY",
        )
    weight = en.effective_n / n
    sx = weight * math.fsum(
        row[0]
        for row in view.connection.execute(
            "SELECT value FROM admitted WHERE quant=? ORDER BY skeleton_ordinal", (_Q,)
        )
    )
    sxx = weight * math.fsum(
        row[0] * row[0]
        for row in view.connection.execute(
            "SELECT value FROM admitted WHERE quant=? ORDER BY skeleton_ordinal", (_Q,)
        )
    )
    centered_forecast = sxx - sx * sx / en.effective_n
    identifiable = not (
        abs(centered_forecast)
        <= 64 * math.ulp(1.0) * max(1.0, abs(sxx) + abs(sx * sx / en.effective_n))
    )
    reasons = list(en.reasons) + ["HYPERPRIOR_UNIDENTIFIABLE"]
    if not identifiable:
        reasons.append("SLOPE_UNIDENTIFIABLE")
    residual_mean = math.fsum(_scores(view)) / n
    variance = (
        math.fsum((x - residual_mean) ** 2 for x in _scores(view)) / (n - 1)
        if n > 1
        else 0.0
    )
    if n < 2:
        bias = BiasDiagnostic(
            residual_mean, None, None, None, ALPHA_BIAS, "UNDETERMINED"
        )
    elif abs(math.sqrt(variance)) <= 64 * math.ulp(1.0) * max(1.0, math.sqrt(variance)):
        bias = BiasDiagnostic(
            residual_mean,
            0.0,
            None,
            None,
            ALPHA_BIAS,
            (
                "PASS"
                if abs(residual_mean)
                <= 64 * math.ulp(1.0) * max(1.0, math.sqrt(variance))
                else "FAIL"
            ),
        )
    else:
        se = math.sqrt(variance / en.effective_n)
        z = residual_mean / se
        bias = BiasDiagnostic(
            residual_mean,
            se,
            z,
            math.erfc(abs(z) / math.sqrt(2)),
            ALPHA_BIAS,
            "PASS" if abs(z) <= 1.959963984540054 else "FAIL",
        )
    raw = (
        math.fsum(
            row[0] - row[1]
            for row in view.connection.execute(
                "SELECT value,target FROM admitted WHERE quant=? ORDER BY skeleton_ordinal",
                (_Q,),
            )
        )
        / n
    )
    mse = math.fsum(x * x for x in _scores(view)) / n
    mae = math.fsum(abs(x) for x in _scores(view)) / n
    item = DirectionalCalibration(
        _Q,
        view.formula_version,
        _H,
        view.family_data_schema_version,
        view.family_source_spec_version,
        view.dataset_hash,
        view.raw_resolved_count,
        view.skeleton_count,
        n,
        en.kish_n,
        en.serial_dependence_factor,
        en.effective_n,
        0.0,
        0.0,
        None,
        None,
        0.0,
        1.0,
        False,
        identifiable,
        ((0.0, 0.0), (0.0, 0.0)),
        0.0,
        raw,
        -residual_mean,
        math.sqrt(mse),
        mae,
        variance,
        math.sqrt(variance),
        n / view.skeleton_count,
        bias,
        "PROVISIONAL",
        tuple(dict.fromkeys(reasons)),
    )
    return V2BCalibration(
        V2B_VERSION,
        ((_H, view.dataset_hash),),
        (item,),
        (),
        0.0,
        "SCALE_CONDITIONING_UNAVAILABLE_PENDING_CAUSAL_V3_REPLAY",
    )


def build_external_v2c(
    view: ExternalV2AView, calibration: V2BCalibration
) -> V2CCovariance:
    n = view.observation_count
    if not n:
        return V2CCovariance(
            V2C_VERSION,
            _H,
            view.dataset_hash,
            v2b_component_hash(calibration, _H),
            (_Q,),
            (view.formula_version,),
            view.family_lineage,
            ((0.0,),),
            ((0.0,),),
            ((False,),),
            ((0.0,),),
            (),
            0,
            (),
            ((0.0,),),
            None,
            None,
            None,
            ((0.0,),),
            ((0.0,),),
            None,
            None,
            0,
            None,
            None,
            None,
            None,
            False,
            "UNAVAILABLE",
            (
                "COMPLETE_CASE_DEPENDENCE_UNAVAILABLE",
                "PAIR_COVARIANCE_UNSUPPORTED",
                "SUPPORTED_POSITIVE_SCALE_UNAVAILABLE",
                "V2B_CALIBRATION_UNAVAILABLE",
            ),
        )
    mean = math.fsum(_scores(view)) / n
    scores = ((x - mean) ** 2 for x in _scores(view))
    en = _effective_n_squared(view, mean)
    supported = n >= 2 and en > 1.0
    covariance = math.fsum(scores) / (n - 1) if supported else 0.0
    reasons = {"V2B_CALIBRATION_PROVISIONAL"}
    if not supported:
        reasons.add("PAIR_COVARIANCE_UNSUPPORTED")
    # For p=1 OAS is the population residual variance.
    empirical = math.fsum((x - mean) ** 2 for x in _scores(view)) / n if n >= 2 else 0.0
    if n >= 2:
        candidate = empirical
        if candidate > 0.0:
            ridge = max(
                float.fromhex("0x0.0000000000001p-1022"),
                math.sqrt(math.ulp(1.0)) * candidate,
            )
            stable = candidate + ridge
            status = "PROVISIONAL"
            dependence = True
        else:
            ridge = None
            stable = 0.0
            status = "UNAVAILABLE"
            dependence = False
            reasons.add("SUPPORTED_POSITIVE_SCALE_UNAVAILABLE")
        matrices = (((empirical,),), ((candidate,),), ((stable,),))
    else:
        reasons.update(
            (
                "COMPLETE_CASE_DEPENDENCE_UNAVAILABLE",
                "SUPPORTED_POSITIVE_SCALE_UNAVAILABLE",
            )
        )
        status = "UNAVAILABLE"
        dependence = False
        ridge = None
        stable = 0.0
        matrices = (((0.0,),), ((0.0,),), ((0.0,),))
    return V2CCovariance(
        V2C_VERSION,
        _H,
        view.dataset_hash,
        v2b_component_hash(calibration, _H),
        (_Q,),
        (view.formula_version,),
        view.family_lineage,
        ((float(n),),),
        ((en,),),
        ((supported,),),
        ((covariance,),),
        (_Q,),
        n,
        (),
        matrices[0],
        "STANDARD_COMPLETE_CASE_OAS" if n >= 2 else None,
        1.0 if n >= 2 else None,
        empirical if n >= 2 else None,
        matrices[1],
        matrices[2],
        candidate if n >= 2 else None,
        candidate if n >= 2 else None,
        0,
        0.0 if n >= 2 else None,
        0.0 if n >= 2 else None,
        ridge,
        1.0 if ridge is not None else None,
        dependence,
        status,
        tuple(sorted(reasons)),
    )


def _effective_n_squared(view, mean):
    # Frozen effective_n over pair covariance scores; constant scores take the
    # common bounded pass used by the acceptance fixture.
    def values():
        return ((x - mean) ** 2 for x in _scores(view))

    n = view.observation_count
    m = math.fsum(values()) / n
    den = math.fsum((x - m) ** 2 for x in values())
    scale = math.fsum(x * x for x in values()) + n * m * m
    if abs(den) <= 64 * math.ulp(1.0) * max(1.0, scale):
        return float(n)
    # Exact fallback delegates to a temporary scalar table without RAM growth.
    view.connection.execute("DROP TABLE IF EXISTS covariance_scores")
    view.connection.execute(
        "CREATE TABLE covariance_scores(i INTEGER PRIMARY KEY,v REAL)"
    )
    view.connection.executemany(
        "INSERT INTO covariance_scores VALUES(?,?)", enumerate(values())
    )
    view.connection.execute("DROP TABLE IF EXISTS covariance_autocorrelation_terms")
    view.connection.execute(
        "CREATE TABLE covariance_autocorrelation_terms(lag INTEGER PRIMARY KEY,value REAL)"
    )
    odd_rho = None
    for lag in range(1, n):
        rho = (
            math.fsum(
                r[0]
                for r in view.connection.execute(
                    "SELECT (a.v-?)*(b.v-?) FROM covariance_scores a JOIN covariance_scores b ON b.i=a.i+? ORDER BY a.i",
                    (m, m, lag),
                )
            )
            / den
        )
        if lag % 2:
            odd_rho = rho
        elif odd_rho is not None and odd_rho + rho > 0:
            view.connection.executemany(
                "INSERT INTO covariance_autocorrelation_terms VALUES(?,?)",
                (
                    (lag - 1, (1.0 - (lag - 1) / n) * odd_rho),
                    (lag, (1.0 - lag / n) * rho),
                ),
            )
        else:
            break
    tau = max(
        1.0,
        1
        + 2
        * math.fsum(
            row[0]
            for row in view.connection.execute(
                "SELECT value FROM covariance_autocorrelation_terms ORDER BY lag"
            )
        ),
    )
    return min(float(n), max(1.0, n / tau))


def build_external_v2d(view, calibration, covariance) -> V2EvidenceState:
    cal = calibration.directional[0]
    directional = DirectionalCalibrationState(
        cal.quant_id,
        cal.formula_version,
        cal.data_schema_version,
        cal.source_spec_version,
        cal.dataset_hash,
        cal.calibration_intercept,
        cal.calibration_slope,
        cal.calibration_parameter_covariance_2x2,
        cal.effective_n,
        cal.residual_variance,
        cal.residual_standard_deviation,
        cal.status,
        tuple(sorted(cal.reason_codes)),
    )
    hs_reasons = tuple(
        sorted(
            set(cal.reason_codes)
            | set(covariance.reason_codes)
            | {"Q3_EVIDENCE_UNAVAILABLE"}
            | (
                {"COVARIANCE_UNAVAILABLE"}
                if covariance.status == "UNAVAILABLE" and cal.status != "UNAVAILABLE"
                else set()
            )
        )
    )
    horizon = HorizonEvidenceState(
        _H,
        30,
        "UNAVAILABLE" if covariance.status == "UNAVAILABLE" else "PROVISIONAL",
        hs_reasons,
        (directional,),
        view.family_lineage,
        (_Q,),
        covariance.pair_support_boolean_matrix,
        (
            covariance.stabilized_covariance_matrix
            if covariance.status != "UNAVAILABLE"
            else None
        ),
        covariance.dependence_modeled,
        covariance.status,
        covariance.reason_codes,
        Q3MagnitudeState("UNAVAILABLE", ("Q3_EVIDENCE_UNAVAILABLE",)),
    )
    components = tuple(
        sorted(
            (
                ComponentHash(_H, "V2A", view.dataset_hash),
                ComponentHash(_H, "V2B", v2b_component_hash(calibration, _H)),
                ComponentHash(_H, "V2C", _digest(covariance)),
            )
        )
    )
    manifest = _digest(tuple((x.horizon, x.layer, x.digest) for x in components))
    horizons = (horizon, *(_missing(h) for h in ("1M", "5M", "15M", "30M", "1H")))
    reasons = tuple(sorted({r for h in horizons for r in h.reason_codes}))
    top_status = (
        "MATURE"
        if all(h.status == "MATURE" for h in horizons)
        else (
            "UNAVAILABLE"
            if all(h.status == "UNAVAILABLE" for h in horizons)
            else "PROVISIONAL"
        )
    )
    state = V2EvidenceState(
        STATE_SCHEMA_VERSION,
        STATE_VERSION,
        MODEL_FAMILY,
        "COIN",
        view.state_as_of,
        view.training_start,
        view.training_end,
        view.target_spec_id,
        view.target_data_schema_version,
        view.target_source_spec_version,
        METHOD_VERSION,
        V2B_VERSION,
        V2C_VERSION,
        EFFECTIVE_N_METHOD_VERSION,
        CALIBRATION_METHOD_VERSION,
        COVARIANCE_METHOD_VERSION,
        NUMERICAL_CANONICALIZATION_VERSION,
        manifest,
        components,
        horizons,
        tuple((x.reason_code, x.count) for x in view.exclusions),
        top_status,
        "VALID",
        reasons,
        "",
        "",
    )
    digest = v2d_state_hash(state)
    state = replace(state, state_hash=digest, state_id="v9v2:" + digest)
    serialize_v2_evidence_state(state)
    return state
