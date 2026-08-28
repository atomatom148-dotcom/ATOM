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
    Q3MagnitudeCalibration,
    V2BCalibration,
    _inv2,
    _small,
    _zero,
    v2b_component_hash,
)
from quant.v9_v2c_covariance import (
    EPSILON_ABSOLUTE,
    EPSILON_RELATIVE,
    METHOD_VERSION as V2C_VERSION,
    OAS_METHOD,
    V2CCovariance,
    _jacobi,
    _matrix,
    _psd,
)
from quant.v9_v2d_evidence_state import (
    CALIBRATION_METHOD_VERSION,
    COVARIANCE_METHOD_VERSION,
    EFFECTIVE_N_METHOD_VERSION,
    HORIZONS,
    MODEL_FAMILY,
    NUMERICAL_CANONICALIZATION_VERSION,
    STATE_SCHEMA_VERSION,
    STATE_VERSION,
    ComponentHash,
    DirectionalCalibrationState,
    HorizonEvidenceState,
    Q3MagnitudeState,
    V2EvidenceState,
    _all_finite,
    _digest,
    _directional,
    _missing,
    _q3,
    _reasons,
    serialize_v2_evidence_state,
    v2d_state_hash,
)

_OWNER = "ATOM-V9-V2A-EXTERNAL-2"
_OWNER_FILE = "owner.json"
_Q = "q1_momentum"
_H = "30S"


def _finite(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _canonical_float(value):
    return float(value) or 0.0


def _ft(value):
    return {"$float64": _canonical_float(value).hex()}


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
    try:
        os.chmod(path, 0o700)
        (path / _OWNER_FILE).write_text(
            json.dumps({"owner": _OWNER, "path": str(path), "uid": os.getuid()}),
            encoding="ascii",
        )
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise
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
        data = json.loads((path / _OWNER_FILE).read_text(encoding="ascii"))
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
        if name == "complete_case_target_identities":
            if not directional:
                put("[]")
            else:
                marks = ",".join("?" for _ in directional)
                rows = con.execute(
                    f"SELECT s.cycle,s.cutoff,s.maturity FROM skeleton s WHERE (SELECT count(DISTINCT a.quant) FROM admitted a WHERE a.skeleton_ordinal=s.ordinal AND a.quant IN ({marks}))=? ORDER BY s.ordinal",
                    (*directional, len(directional)),
                )
                _stream_array(put, rows, _identity_json)
        elif name in ("directional_subsets", "q3_subset"):
            families = directional if name == "directional_subsets" else ([Q3] if q3 else [])
            if name == "q3_subset" and not q3:
                put("null")
                continue
            if name == "directional_subsets":
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
            if name == "directional_subsets":
                put("]")
        elif name == "exclusions":
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
        elif name == "family_lineage":
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
        elif name == "pair_support":
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
        elif name == "skeleton":
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
    resource_sampler=None,
    eligibility_observer=None,
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
        if resource_sampler is not None:
            resource_sampler()

    counts = {}

    def exclude(reason):
        counts[reason] = counts.get(reason, 0) + 1

    try:
        con = sqlite3.connect(workspace / "v2a.sqlite3")
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA temp_store=FILE")
        # SQLite may create and remove temporary sort files while a single
        # statement is still executing.  Sampling only between phases can
        # therefore under-report the rebuild's actual disk peak.  The progress
        # hook observes those transient files without retaining evidence rows
        # or changing any frozen mathematical operation.
        con.set_progress_handler(sample, 100_000)
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
            if eligibility_observer is not None:
                eligibility_observer()
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
                    _canonical_float(o.value_bps),
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


def _family_observation_count(view: ExternalV2AView, quant_id: str = _Q) -> int:
    return int(
        view.connection.execute(
            "SELECT count(*) FROM admitted WHERE quant=?", (quant_id,)
        ).fetchone()[0]
    )


def validate_external_v2a(view: ExternalV2AView) -> None:
    """Fail closed if the sealed owned workspace or staged bytes changed."""
    marker = json.loads(
        (view.workspace / _OWNER_FILE).read_text(encoding="ascii")
    )
    if marker != {"owner": _OWNER, "path": str(view.workspace), "uid": os.getuid()}:
        raise ValueError("workspace ownership validation failed")
    for payload, digest in view.connection.execute(
        "SELECT payload,payload_hash FROM observations"
    ):
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("corrupt staged payload")
    if _stream_hash(view) != view.dataset_hash:
        raise ValueError("external V2A parity mismatch")


def _effective_n_squared(view, mean):
    # Frozen effective_n over pair covariance scores; constant scores take the
    # common bounded pass used by the acceptance fixture.
    def values():
        return ((x - mean) ** 2 for x in _scores(view))

    n = _family_observation_count(view)
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


# The entry points below implement the frozen equations over disk-backed series
# for every family and horizon. Evidence cardinality never changes the number
# of Python objects retained by these functions.


@dataclass(frozen=True, slots=True)
class _ExternalSeries:
    view: ExternalV2AView
    quant_id: str
    formula: str
    data_schema_version: str
    source_spec_version: str
    magnitude: bool
    observation_count: int
    effective: EffectiveN


@dataclass(frozen=True, slots=True)
class _ExternalPreliminary:
    intercept: float
    slope: float
    residual_scale: float
    covariance: tuple[tuple[float, float], tuple[float, float]]


def _external_views(value) -> tuple[ExternalV2AView, ...]:
    views = (value,) if isinstance(value, ExternalV2AView) else tuple(value)
    if not views or any(not isinstance(view, ExternalV2AView) for view in views):
        raise ValueError("external V2 chain requires at least one V2A view")
    if len({view.horizon for view in views}) != len(views):
        raise ValueError("duplicate external V2A horizon")
    for view in views:
        validate_external_v2a(view)
    return views


def _lineage_row(view: ExternalV2AView, quant_id: str):
    row = next(
        (item for item in view.selected_family_versions if item[0] == quant_id),
        None,
    )
    if row is None:
        raise ValueError("family lineage is missing from external V2A view")
    return row


def _xy_rows(series: _ExternalSeries):
    for target, value in series.view.connection.execute(
        "SELECT target,value FROM admitted WHERE quant=? ORDER BY skeleton_ordinal",
        (series.quant_id,),
    ):
        yield float(value), abs(float(target)) if series.magnitude else float(target)


def _score_rows(series: _ExternalSeries):
    for x, y in _xy_rows(series):
        yield y - x


def _scratch_values(view: ExternalV2AView):
    return (
        row[0]
        for row in view.connection.execute(
            "SELECT value FROM effective_n_scores ORDER BY position"
        )
    )


def _effective_n_rows(view: ExternalV2AView, values) -> EffectiveN:
    """Frozen paired-IPS Effective N over a disk-backed ordered score stream."""
    con = view.connection
    con.execute("DROP TABLE IF EXISTS effective_n_scores")
    con.execute(
        "CREATE TABLE effective_n_scores("
        "position INTEGER PRIMARY KEY,value REAL NOT NULL)"
    )
    con.executemany(
        "INSERT INTO effective_n_scores VALUES(?,?)", enumerate(values)
    )
    n = int(con.execute("SELECT count(*) FROM effective_n_scores").fetchone()[0])
    if not n:
        return EffectiveN(0, 0.0, 1.0, 0.0, 0)
    mean = math.fsum(_scratch_values(view)) / n
    denominator = math.fsum((x - mean) ** 2 for x in _scratch_values(view))
    scale = math.fsum(x * x for x in _scratch_values(view)) + n * mean * mean
    if _small(denominator, scale):
        return EffectiveN(
            n, float(n), 1.0, float(n), 0,
            ("SERIAL_DEPENDENCE_UNIDENTIFIABLE",),
        )
    con.execute("DROP TABLE IF EXISTS autocorrelation_terms")
    con.execute(
        "CREATE TABLE autocorrelation_terms("
        "lag INTEGER PRIMARY KEY,value REAL NOT NULL)"
    )
    retained = 0
    odd_rho = None
    for lag in range(1, n):
        rho = math.fsum(
            left * right
            for left, right in con.execute(
                "SELECT (a.value-?),(b.value-?) "
                "FROM effective_n_scores a "
                "JOIN effective_n_scores b "
                "ON b.position=a.position+? ORDER BY a.position",
                (mean, mean, lag),
            )
        ) / denominator
        if lag % 2:
            odd_rho = rho
        elif odd_rho is not None and odd_rho + rho > 0.0:
            con.executemany(
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
        1.0 + 2.0 * math.fsum(
            row[0]
            for row in con.execute(
                "SELECT value FROM autocorrelation_terms ORDER BY lag"
            )
        ),
    )
    return EffectiveN(
        n, float(n), _zero(tau), _zero(min(float(n), max(1.0, n / tau))), retained
    )


def _external_series(
    view: ExternalV2AView, quant_id: str, *, magnitude: bool = False
) -> _ExternalSeries:
    _, formula, schema, source = _lineage_row(view, quant_id)
    count = _family_observation_count(view, quant_id)
    shell = _ExternalSeries(
        view, quant_id, formula, schema, source, magnitude, count,
        EffectiveN(0, 0.0, 1.0, 0.0, 0),
    )
    return replace(shell, effective=_effective_n_rows(view, _score_rows(shell)))


def _effective_n(
    view: ExternalV2AView, quant_id: str = _Q, *, magnitude: bool = False
) -> EffectiveN:
    """Backward-compatible public test seam for one admitted family series."""
    values = (
        (abs(target) if magnitude else target) - value
        for target, value in view.connection.execute(
            "SELECT target,value FROM admitted WHERE quant=? ORDER BY skeleton_ordinal",
            (quant_id,),
        )
    )
    return _effective_n_rows(view, values)


def _external_moments(series: _ExternalSeries):
    weight = series.effective.effective_n / series.observation_count
    return (
        series.effective.effective_n,
        weight * math.fsum(x for x, _ in _xy_rows(series)),
        weight * math.fsum(x * x for x, _ in _xy_rows(series)),
        weight * math.fsum(y for _, y in _xy_rows(series)),
        weight * math.fsum(x * y for x, y in _xy_rows(series)),
    )


def _external_preliminary(series: _ExternalSeries):
    if series.observation_count < 2 or series.effective.effective_n <= 2.0:
        return None
    s0, sx, sxx, sy, sxy = _external_moments(series)
    inverse = _inv2(s0, sx, sxx)
    if inverse is None:
        return None
    i00, i01, i11 = inverse
    intercept = i00 * sy + i01 * sxy
    slope = i01 * sy + i11 * sxy
    weight = series.effective.effective_n / series.observation_count
    scale = weight * math.fsum(
        (y - intercept - slope * x) ** 2 for x, y in _xy_rows(series)
    ) / series.effective.effective_n
    if not all(math.isfinite(value) for value in (intercept, slope, scale)) or scale < 0:
        return None
    covariance = (
        (scale * i00, scale * i01),
        (scale * i01, scale * i11),
    )
    if any(not math.isfinite(value) for row in covariance for value in row):
        return None
    return _ExternalPreliminary(
        _zero(intercept), _zero(slope), _zero(scale), covariance
    )


def _external_parameter_covariance(
    series: _ExternalSeries,
    intercept: float,
    slope: float,
    lambda_intercept: float,
    lambda_slope: float,
    free_intercept: bool,
    free_slope: bool,
    boundary: bool,
    prior: tuple[float, float],
):
    s0, sx, sxx, _, _ = _external_moments(series)
    if free_intercept and free_slope:
        inverse = _inv2(s0 + lambda_intercept, sx, sxx + lambda_slope)
        if inverse is None:
            return ((prior[0], 0.0), (0.0, prior[1])), 2.0, False
        i00, i01, i11 = inverse
        degrees = i00 * s0 + 2.0 * i01 * sx + i11 * sxx
        if series.effective.effective_n <= degrees:
            return ((prior[0], 0.0), (0.0, prior[1])), degrees, False
        factor = series.effective.effective_n / (
            series.effective.effective_n - degrees
        )
        weight = series.effective.effective_n / series.observation_count
        b00 = factor * weight * math.fsum(
            (y - intercept - slope * x) ** 2 for x, y in _xy_rows(series)
        )
        b01 = factor * weight * math.fsum(
            (y - intercept - slope * x) ** 2 * x for x, y in _xy_rows(series)
        )
        b11 = factor * weight * math.fsum(
            (y - intercept - slope * x) ** 2 * x * x
            for x, y in _xy_rows(series)
        )
        v00 = i00 * i00 * b00 + 2 * i00 * i01 * b01 + i01 * i01 * b11
        v01 = (
            i00 * i01 * b00
            + (i00 * i11 + i01 * i01) * b01
            + i01 * i11 * b11
        )
        v11 = i01 * i01 * b00 + 2 * i01 * i11 * b01 + i11 * i11 * b11
        if v00 < 0 and _small(v00, abs(v00) + abs(v11)):
            v00 = 0.0
        if v11 < 0 and _small(v11, abs(v00) + abs(v11)):
            v11 = 0.0
        if (
            v00 < 0
            or v11 < 0
            or v00 * v11 + 64 * math.ulp(1.0) * max(1.0, v00 * v11) < v01 * v01
        ):
            return ((prior[0], 0.0), (0.0, prior[1])), degrees, False
        if boundary:
            return ((_zero(2 * v00), 0.0), (0.0, _zero(2 * v11))), degrees, True
        return (
            (_zero(v00), _zero(v01)),
            (_zero(v01), _zero(v11)),
        ), degrees, True
    data_hessian = s0 if free_intercept else sxx
    penalty = lambda_intercept if free_intercept else lambda_slope
    degrees = (
        data_hessian / (data_hessian + penalty)
        if data_hessian + penalty > 0
        else 0.0
    )
    if series.effective.effective_n <= degrees or data_hessian + penalty <= 0:
        variance = prior[0] if free_intercept else prior[1]
        ok = False
    else:
        weight = series.effective.effective_n / series.observation_count
        meat = (
            series.effective.effective_n
            / (series.effective.effective_n - degrees)
            * weight
            * math.fsum(
                (y - intercept - slope * x) ** 2
                * ((1.0 if free_intercept else x) ** 2)
                for x, y in _xy_rows(series)
            )
        )
        variance = meat / (data_hessian + penalty) ** 2
        ok = math.isfinite(variance) and variance >= 0
        if not ok:
            variance = prior[0] if free_intercept else prior[1]
        elif boundary:
            variance *= 2.0
    return (
        ((_zero(variance) if free_intercept else 0.0), 0.0),
        (0.0, (_zero(variance) if free_slope else 0.0)),
    ), degrees, ok


def _external_bias(series: _ExternalSeries, intercept: float, slope: float):
    n = series.observation_count
    mean = math.fsum(
        y - intercept - slope * x for x, y in _xy_rows(series)
    ) / n
    if n < 2 or series.effective.effective_n <= 0:
        return BiasDiagnostic(
            _zero(mean), None, None, None, ALPHA_BIAS, "UNDETERMINED"
        )
    variance = math.fsum(
        ((y - intercept - slope * x) - mean) ** 2
        for x, y in _xy_rows(series)
    ) / (n - 1)
    standard_error = math.sqrt(max(0.0, variance) / series.effective.effective_n)
    if _small(standard_error, math.sqrt(max(0.0, variance))):
        return BiasDiagnostic(
            _zero(mean), 0.0, None, None, ALPHA_BIAS,
            "PASS" if _small(mean, math.sqrt(max(0.0, variance))) else "FAIL",
        )
    z = mean / standard_error
    probability = math.erfc(abs(z) / math.sqrt(2.0))
    return BiasDiagnostic(
        _zero(mean), _zero(standard_error), _zero(z), _zero(probability),
        ALPHA_BIAS, "PASS" if abs(z) <= 1.959963984540054 else "FAIL",
    )


def _finish_external_directional(
    series: _ExternalSeries,
    intercept,
    slope,
    covariance,
    degrees,
    boundary,
    identifiable,
    tau_intercept,
    tau_slope,
    lambda_intercept,
    lambda_slope,
    reasons,
):
    n = series.observation_count
    mean = math.fsum(
        y - intercept - slope * x for x, y in _xy_rows(series)
    ) / n
    mse = math.fsum(
        (y - intercept - slope * x) ** 2 for x, y in _xy_rows(series)
    ) / n
    variance = (
        math.fsum(
            ((y - intercept - slope * x) - mean) ** 2
            for x, y in _xy_rows(series)
        ) / (n - 1)
        if n > 1
        else 0.0
    )
    mature = (
        identifiable
        and n > 0
        and series.effective.effective_n > 2
        and "HYPERPRIOR_UNIDENTIFIABLE" not in reasons
        and "SERIAL_DEPENDENCE_UNIDENTIFIABLE" not in reasons
        and "RESIDUAL_SCALE_UNAVAILABLE" not in reasons
        and "RESIDUAL_SCALE_FALLBACK" not in reasons
        and not boundary
        and "TINY_EFFECTIVE_N" not in reasons
    )
    return DirectionalCalibration(
        series.quant_id,
        series.formula,
        series.view.horizon,
        series.data_schema_version,
        series.source_spec_version,
        series.view.dataset_hash,
        series.view.raw_resolved_count,
        series.view.skeleton_count,
        n,
        series.effective.kish_n,
        series.effective.serial_dependence_factor,
        series.effective.effective_n,
        tau_intercept,
        tau_slope,
        lambda_intercept,
        lambda_slope,
        _zero(intercept),
        _zero(slope),
        boundary,
        identifiable,
        covariance,
        _zero(degrees),
        _zero(math.fsum(x - y for x, y in _xy_rows(series)) / n),
        _zero(-mean),
        _zero(math.sqrt(mse)),
        _zero(
            math.fsum(
                abs(y - intercept - slope * x) for x, y in _xy_rows(series)
            ) / n
        ),
        _zero(variance),
        _zero(math.sqrt(variance)),
        _zero(n / series.view.skeleton_count) if series.view.skeleton_count else 0.0,
        _external_bias(series, intercept, slope),
        "MATURE" if mature else "PROVISIONAL",
        tuple(dict.fromkeys(reasons)),
    )


def _external_directional_result(series, prior, donors, pool):
    reasons = list(series.effective.reasons)
    n = series.observation_count
    effective_n = series.effective.effective_n
    tau_intercept, tau_slope = prior
    if not n:
        return DirectionalCalibration(
            series.quant_id, series.formula, series.view.horizon,
            series.data_schema_version, series.source_spec_version,
            series.view.dataset_hash, series.view.raw_resolved_count,
            series.view.skeleton_count, 0, 0.0, 1.0, 0.0,
            tau_intercept, tau_slope, None, None, 0.0, 1.0, False, False,
            ((0.0, 0.0), (0.0, 0.0)), 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            BiasDiagnostic(0.0, None, None, None, ALPHA_BIAS, "UNDETERMINED"),
            "UNAVAILABLE", ("NO_EVIDENCE",),
        )
    if donors < 2:
        reasons.append("HYPERPRIOR_UNIDENTIFIABLE")
        _, sx, sxx, _, _ = _external_moments(series)
        identifiable = not _small(
            sxx - sx * sx / effective_n,
            abs(sxx) + abs(sx * sx / effective_n),
        )
        if not identifiable:
            reasons.append("SLOPE_UNIDENTIFIABLE")
        return _finish_external_directional(
            series, 0.0, 1.0, ((0.0, 0.0), (0.0, 0.0)), 0.0,
            False, identifiable, tau_intercept, tau_slope, None, None, reasons,
        )
    s0, sx, sxx, sy, sxy = _external_moments(series)
    forecast_variance = sxx - sx * sx / s0
    identifiable = not _small(
        forecast_variance, abs(sxx) + abs(sx * sx / s0)
    )
    preliminary = _external_preliminary(series)
    scale = preliminary.residual_scale if preliminary is not None else 0.0
    if _small(
        scale,
        math.fsum(y * y for _, y in _xy_rows(series)) / n,
    ):
        if pool is not None and pool > 0:
            scale = pool
            reasons.append("RESIDUAL_SCALE_FALLBACK")
        else:
            reasons.append("RESIDUAL_SCALE_UNAVAILABLE")
            return _finish_external_directional(
                series, 0.0, 1.0,
                ((tau_intercept, 0.0), (0.0, tau_slope)), 0.0,
                False, identifiable, tau_intercept, tau_slope, None, None,
                reasons,
            )
    lambda_intercept = scale / tau_intercept if tau_intercept > 0 else None
    lambda_slope = scale / tau_slope if tau_slope > 0 else None
    if not identifiable:
        reasons.append("SLOPE_UNIDENTIFIABLE")
        slope = 1.0
        intercept = (
            (sy - sx) / (s0 + (lambda_intercept or 0.0))
            if tau_intercept > 0 else 0.0
        )
        covariance, degrees, ok = _external_parameter_covariance(
            series, intercept, slope, lambda_intercept or 0.0, 0.0,
            tau_intercept > 0, False, False, prior,
        )
        if not ok:
            reasons.append("TINY_EFFECTIVE_N")
        return _finish_external_directional(
            series, intercept, slope, covariance, degrees, False, False,
            tau_intercept, tau_slope, lambda_intercept, lambda_slope, reasons,
        )
    free_intercept, free_slope = tau_intercept > 0, tau_slope > 0
    if free_intercept and free_slope:
        inverse = _inv2(
            s0 + lambda_intercept, sx, sxx + lambda_slope
        )
        if inverse is None:
            reasons.append("NUMERICAL_SINGULARITY")
            return _finish_external_directional(
                series, 0.0, 1.0,
                ((tau_intercept, 0.0), (0.0, tau_slope)), 0.0,
                False, True, tau_intercept, tau_slope,
                lambda_intercept, lambda_slope, reasons,
            )
        i00, i01, i11 = inverse
        intercept = i00 * sy + i01 * (sxy + lambda_slope)
        slope = i01 * sy + i11 * (sxy + lambda_slope)
    elif free_intercept:
        slope = 1.0
        intercept = (sy - sx) / (s0 + lambda_intercept)
    elif free_slope:
        intercept = 0.0
        slope = (sxy + lambda_slope) / (sxx + lambda_slope)
    else:
        intercept, slope = 0.0, 1.0
    boundary = slope < 0.0
    if boundary:
        slope = 0.0
        intercept = sy / (s0 + (lambda_intercept or 0.0)) if free_intercept else 0.0
        reasons.append("SLOPE_BOUNDARY")
    covariance, degrees, ok = _external_parameter_covariance(
        series, intercept, slope, lambda_intercept or 0.0,
        lambda_slope or 0.0, free_intercept, free_slope, boundary, prior,
    )
    if not ok:
        reasons.append("TINY_EFFECTIVE_N")
    return _finish_external_directional(
        series, intercept, slope, covariance, degrees, boundary, True,
        tau_intercept, tau_slope, lambda_intercept, lambda_slope, reasons,
    )


def _finish_external_q3(
    series, alpha, beta, covariance, degrees, tau_alpha, tau_beta,
    lambda_alpha, lambda_beta, reasons,
):
    n = series.observation_count
    mean = math.fsum(
        y - alpha - beta * x for x, y in _xy_rows(series)
    ) / n
    mse = math.fsum(
        (y - alpha - beta * x) ** 2 for x, y in _xy_rows(series)
    ) / n
    variance = (
        math.fsum(
            ((y - alpha - beta * x) - mean) ** 2
            for x, y in _xy_rows(series)
        ) / (n - 1)
        if n > 1 else 0.0
    )
    mature = (
        series.effective.effective_n > 2
        and "HYPERPRIOR_UNIDENTIFIABLE" not in reasons
        and "SERIAL_DEPENDENCE_UNIDENTIFIABLE" not in reasons
        and "RESIDUAL_SCALE_UNAVAILABLE" not in reasons
        and "RESIDUAL_SCALE_FALLBACK" not in reasons
        and "TINY_EFFECTIVE_N" not in reasons
        and "BETA_BOUNDARY" not in reasons
        and "ALPHA_BOUNDARY" not in reasons
    )
    return Q3MagnitudeCalibration(
        Q3, series.formula, series.view.horizon, series.data_schema_version,
        series.source_spec_version, series.view.dataset_hash,
        "ABSOLUTE_DIRECTIONAL_TARGET_BPS", n, series.effective.kish_n,
        series.effective.serial_dependence_factor, series.effective.effective_n,
        _zero(alpha), _zero(beta), alpha == 0, beta == 0,
        tau_alpha, tau_beta, lambda_alpha, lambda_beta, covariance,
        _zero(math.fsum(x - y for x, y in _xy_rows(series)) / n),
        _zero(-mean),
        _zero(math.fsum(abs(y - alpha - beta * x) for x, y in _xy_rows(series)) / n),
        _zero(math.sqrt(mse)), _zero(variance),
        _zero(math.fsum((alpha + beta * x) ** 2 for x, _ in _xy_rows(series)) / n),
        _zero(n / series.view.skeleton_count) if series.view.skeleton_count else 0.0,
        _zero(degrees), "MATURE" if mature else "PROVISIONAL",
        tuple(dict.fromkeys(reasons)),
    )


def _external_q3_result(series, prior, donors, pool):
    reasons = list(series.effective.reasons)
    n = series.observation_count
    tau_alpha, tau_beta = prior
    if not n:
        return Q3MagnitudeCalibration(
            Q3, series.formula, series.view.horizon, series.data_schema_version,
            series.source_spec_version, series.view.dataset_hash,
            "ABSOLUTE_DIRECTIONAL_TARGET_BPS", 0, 0.0, 1.0, 0.0,
            0.0, 1.0, False, False, tau_alpha, tau_beta, None, None,
            ((0.0, 0.0), (0.0, 0.0)), 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, "UNAVAILABLE", ("NO_EVIDENCE",),
        )
    if donors < 2:
        reasons.append("HYPERPRIOR_UNIDENTIFIABLE")
        return _finish_external_q3(
            series, 0.0, 1.0, ((0.0, 0.0), (0.0, 0.0)), 0.0,
            tau_alpha, tau_beta, None, None, reasons,
        )
    s0, sx, sxx, sy, sxy = _external_moments(series)
    preliminary = _external_preliminary(series)
    scale = preliminary.residual_scale if preliminary else 0.0
    if _small(scale, math.fsum(y * y for _, y in _xy_rows(series)) / n):
        if pool is not None and pool > 0:
            scale = pool
            reasons.append("RESIDUAL_SCALE_FALLBACK")
        else:
            reasons.append("RESIDUAL_SCALE_UNAVAILABLE")
            return _finish_external_q3(
                series, 0.0, 1.0,
                ((tau_alpha, 0.0), (0.0, tau_beta)), 0.0,
                tau_alpha, tau_beta, None, None, reasons,
            )
    lambda_alpha = scale / tau_alpha if tau_alpha > 0 else None
    lambda_beta = scale / tau_beta if tau_beta > 0 else None
    candidates = []
    inverse = (
        _inv2(s0 + (lambda_alpha or 0.0), sx, sxx + (lambda_beta or 0.0))
        if tau_alpha > 0 and tau_beta > 0 else None
    )
    if tau_alpha > 0 and tau_beta > 0 and inverse:
        i00, i01, i11 = inverse
        alpha = i00 * sy + i01 * (sxy + lambda_beta)
        beta = i01 * sy + i11 * (sxy + lambda_beta)
        if alpha >= 0 and beta >= 0:
            candidates.append((alpha, beta, 0))
    if tau_beta > 0:
        candidates.append((0.0, max(0.0, (sxy + lambda_beta) / (sxx + lambda_beta)), 1))
    if tau_alpha > 0:
        candidates.append((max(0.0, sy / (s0 + lambda_alpha)), 0.0, 1))
    candidates.append((0.0, 0.0, 2))
    if tau_alpha == 0 and tau_beta > 0:
        candidates.append((0.0, max(0.0, (sxy + lambda_beta) / (sxx + lambda_beta)), 1))
    if tau_beta == 0 and tau_alpha > 0:
        candidates.append((max(0.0, (sy - sx) / (s0 + lambda_alpha)), 1.0, 0))
    if tau_alpha == 0 and tau_beta == 0:
        candidates.append((0.0, 1.0, 0))
    weight = series.effective.effective_n / n

    def key(candidate):
        alpha, beta, boundaries = candidate
        objective = weight * math.fsum(
            (y - alpha - beta * x) ** 2 for x, y in _xy_rows(series)
        )
        if tau_alpha > 0:
            objective += alpha * alpha / (tau_alpha / scale)
        elif alpha != 0:
            objective = math.inf
        if tau_beta > 0:
            objective += (beta - 1) ** 2 / (tau_beta / scale)
        elif beta != 1:
            objective = math.inf
        return (round(objective, 14), alpha * alpha + (beta - 1) ** 2,
                boundaries, alpha, beta)

    alpha, beta, _ = min(candidates, key=key)
    boundary = alpha == 0 or beta == 0
    if alpha == 0:
        reasons.append("ALPHA_BOUNDARY")
    if beta == 0:
        reasons.append("BETA_BOUNDARY")
    covariance, degrees, ok = _external_parameter_covariance(
        series, alpha, beta, lambda_alpha or 0.0, lambda_beta or 0.0,
        tau_alpha > 0, tau_beta > 0, boundary, prior,
    )
    if not ok:
        reasons.append("TINY_EFFECTIVE_N")
    return _finish_external_q3(
        series, alpha, beta, covariance, degrees, tau_alpha, tau_beta,
        lambda_alpha, lambda_beta, reasons,
    )


def build_external_v2b(view_or_views) -> V2BCalibration:
    """Build frozen V2B exactly from one or more bounded external V2A views."""
    views = _external_views(view_or_views)
    directional = [
        _external_series(view, quant_id)
        for view in views
        for quant_id in DIRECTIONAL_FAMILIES
        if any(row[0] == quant_id for row in view.selected_family_versions)
    ]
    preliminaries = {id(series): _external_preliminary(series) for series in directional}

    def cohort(series):
        view = series.view
        return (
            view.horizon, "COIN", view.target_spec_id,
            view.target_data_schema_version, view.target_source_spec_version,
            series.data_schema_version, series.source_spec_version,
        )

    priors = {}
    pools = {}
    for cohort_key in {cohort(series) for series in directional}:
        members = [series for series in directional if cohort(series) == cohort_key]
        donors = [
            preliminaries[id(series)] for series in members
            if preliminaries[id(series)] is not None
        ]
        priors[cohort_key] = (
            max(0.0, math.fsum(
                item.intercept ** 2 - item.covariance[0][0] for item in donors
            ) / len(donors)),
            max(0.0, math.fsum(
                (item.slope - 1) ** 2 - item.covariance[1][1] for item in donors
            ) / len(donors)),
        ) if len(donors) >= 2 else (0.0, 0.0)
        valid = [
            (series, preliminaries[id(series)]) for series in members
            if preliminaries[id(series)] is not None
        ]
        numerator = math.fsum(
            series.effective.effective_n * item.residual_scale
            for series, item in valid
        )
        pools[cohort_key] = (
            numerator / math.fsum(series.effective.effective_n for series, _ in valid)
            if valid and numerator > 0 else None
        )
    directional_results = tuple(
        _external_directional_result(
            series, priors[cohort(series)],
            sum(
                preliminaries[id(other)] is not None
                for other in directional if cohort(other) == cohort(series)
            ),
            pools[cohort(series)],
        )
        for series in directional
    )
    qseries = [
        _external_series(view, Q3, magnitude=True)
        for view in views
        if any(row[0] == Q3 for row in view.selected_family_versions)
    ]
    qpre = {id(series): _external_preliminary(series) for series in qseries}

    def qcohort(series):
        view = series.view
        return (
            "COIN", view.target_spec_id, view.target_data_schema_version,
            view.target_source_spec_version, series.formula,
            series.data_schema_version, series.source_spec_version,
        )

    qhyper = {}
    for cohort_key in {qcohort(series) for series in qseries}:
        members = [series for series in qseries if qcohort(series) == cohort_key]
        donors = []
        for series in members:
            preliminary = qpre[id(series)]
            y2 = math.fsum(y * y for _, y in _xy_rows(series))
            if preliminary is not None and series.observation_count and y2 > 0:
                donors.append((
                    series, preliminary,
                    math.sqrt(y2 / series.observation_count),
                ))
        if len(donors) >= 2:
            tau_alpha = max(0.0, math.fsum(
                (item.intercept / scale) ** 2
                - item.covariance[0][0] / (scale * scale)
                for _, item, scale in donors
            ) / len(donors))
            tau_beta = max(0.0, math.fsum(
                (item.slope - 1) ** 2 - item.covariance[1][1]
                for _, item, _ in donors
            ) / len(donors))
        else:
            tau_alpha = tau_beta = 0.0
        numerator = math.fsum(
            series.effective.effective_n * item.residual_scale
            for series, item, _ in donors
        )
        pool = (
            numerator / math.fsum(series.effective.effective_n for series, _, _ in donors)
            if donors and numerator > 0 else None
        )
        qhyper[cohort_key] = tau_alpha, tau_beta, len(donors), pool
    qresults = []
    for series in qseries:
        tau_alpha, tau_beta, count, pool = qhyper[qcohort(series)]
        target_second_moment = (
            math.fsum(y * y for _, y in _xy_rows(series)) / series.observation_count
            if series.observation_count else 0.0
        )
        qresults.append(_external_q3_result(
            series, (target_second_moment * tau_alpha, tau_beta), count, pool
        ))
    manifest = tuple(
        (horizon, next(view.dataset_hash for view in views if view.horizon == horizon))
        for horizon in HORIZONS if any(view.horizon == horizon for view in views)
    )
    return V2BCalibration(
        V2B_VERSION, manifest, directional_results, tuple(qresults), 0.0,
        "SCALE_CONDITIONING_UNAVAILABLE_PENDING_CAUSAL_V3_REPLAY",
    )


def build_external_v2c(
    view: ExternalV2AView, calibration: V2BCalibration
) -> V2CCovariance:
    """Build one frozen V2C horizon using disk-backed residual relations."""
    validate_external_v2a(view)
    manifest = dict(calibration.input_manifest)
    if (
        len(manifest) != len(calibration.input_manifest)
        or manifest.get(view.horizon) != view.dataset_hash
    ):
        raise ValueError("V2-B input manifest does not match external V2-A view")
    calibration_hash = v2b_component_hash(calibration, view.horizon)
    lineage_by_quant = {item.quant_id: item for item in view.family_lineage}
    quant_ids = tuple(
        quant_id for quant_id in DIRECTIONAL_FAMILIES
        if quant_id in lineage_by_quant
    )
    formulas = tuple(lineage_by_quant[q].formula_version for q in quant_ids)
    ordered_lineage = tuple(lineage_by_quant[q] for q in quant_ids)
    calibrations = {}
    for item in calibration.directional:
        key = (
            item.horizon, item.quant_id, item.formula_version,
            item.data_schema_version, item.source_spec_version, item.dataset_hash,
        )
        if key in calibrations:
            raise ValueError("duplicate V2-B directional calibration lineage")
        calibrations[key] = item
    selected = [
        calibrations.get((
            view.horizon, quant_id, lineage_by_quant[quant_id].formula_version,
            lineage_by_quant[quant_id].data_schema_version,
            lineage_by_quant[quant_id].source_spec_version, view.dataset_hash,
        ))
        for quant_id in quant_ids
    ]
    con = view.connection
    con.execute("DROP TABLE IF EXISTS external_residuals")
    con.execute(
        "CREATE TABLE external_residuals("
        "quant TEXT NOT NULL,ordinal INTEGER NOT NULL,value REAL NOT NULL,"
        "PRIMARY KEY(quant,ordinal))"
    )
    reasons = set()
    for quant_id, item in zip(quant_ids, selected):
        if item is None or item.status == "UNAVAILABLE":
            reasons.add("V2B_CALIBRATION_UNAVAILABLE")
            continue
        if item.status != "MATURE":
            reasons.add("V2B_CALIBRATION_PROVISIONAL")
        rows = []
        for ordinal, target, value in con.execute(
            "SELECT skeleton_ordinal,target,value FROM admitted "
            "WHERE quant=? ORDER BY skeleton_ordinal", (quant_id,)
        ):
            residual = target - (
                item.calibration_intercept + item.calibration_slope * value
            )
            if not math.isfinite(residual):
                reasons.add("NONFINITE_RESIDUAL")
                continue
            rows.append((quant_id, ordinal, residual))
            if len(rows) == 4096:
                con.executemany("INSERT INTO external_residuals VALUES(?,?,?)", rows)
                rows.clear()
        if rows:
            con.executemany("INSERT INTO external_residuals VALUES(?,?,?)", rows)

    def paired_rows(left_quant, right_quant):
        for left, right in con.execute(
            "SELECT a.value,b.value FROM external_residuals a "
            "JOIN external_residuals b ON b.ordinal=a.ordinal "
            "WHERE a.quant=? AND b.quant=? ORDER BY a.ordinal",
            (left_quant, right_quant),
        ):
            yield left, right

    p = len(quant_ids)
    counts = [[0.0] * p for _ in range(p)]
    effective_ns = [[0.0] * p for _ in range(p)]
    support = [[False] * p for _ in range(p)]
    pair_covariance = [[0.0] * p for _ in range(p)]
    for i in range(p):
        for j in range(i, p):
            n = int(con.execute(
                "SELECT count(*) FROM external_residuals a "
                "JOIN external_residuals b ON b.ordinal=a.ordinal "
                "WHERE a.quant=? AND b.quant=?",
                (quant_ids[i], quant_ids[j]),
            ).fetchone()[0])
            counts[i][j] = counts[j][i] = float(n)
            if n:
                left_mean = math.fsum(
                    left for left, _ in paired_rows(quant_ids[i], quant_ids[j])
                ) / n
                right_mean = math.fsum(
                    right for _, right in paired_rows(quant_ids[i], quant_ids[j])
                ) / n
                effective = _effective_n_rows(
                    view,
                    (
                        (left - left_mean) * (right - right_mean)
                        for left, right in paired_rows(quant_ids[i], quant_ids[j])
                    ),
                ).effective_n
                effective_ns[i][j] = effective_ns[j][i] = effective
                ok = n >= 2 and effective > 1.0
                support[i][j] = support[j][i] = ok
                covariance = (
                    math.fsum(_scratch_values(view)) / (n - 1) if ok else 0.0
                )
                pair_covariance[i][j] = pair_covariance[j][i] = covariance
            if not support[i][j]:
                reasons.add("PAIR_COVARIANCE_UNSUPPORTED")

    con.execute("DROP TABLE IF EXISTS external_complete_ordinals")
    con.execute(
        "CREATE TABLE external_complete_ordinals(ordinal INTEGER PRIMARY KEY)"
    )
    complete_n = 0
    if p:
        placeholders = ",".join("?" for _ in quant_ids)
        v2a_complete_n = int(con.execute(
            "SELECT count(*) FROM (SELECT skeleton_ordinal FROM admitted "
            f"WHERE quant IN ({placeholders}) GROUP BY skeleton_ordinal "
            "HAVING count(DISTINCT quant)=?)",
            (*quant_ids, p),
        ).fetchone()[0])
        con.execute(
            "INSERT INTO external_complete_ordinals "
            "SELECT ordinal FROM external_residuals "
            f"WHERE quant IN ({placeholders}) GROUP BY ordinal "
            "HAVING count(DISTINCT quant)=? ORDER BY ordinal",
            (*quant_ids, p),
        )
        complete_n = int(con.execute(
            "SELECT count(*) FROM external_complete_ordinals"
        ).fetchone()[0])
        if complete_n != v2a_complete_n:
            reasons.add("COMPLETE_CASE_INTEGRITY_REJECTED")

    def complete_values(quant_id):
        return (
            row[0]
            for row in con.execute(
                "SELECT r.value FROM external_complete_ordinals c "
                "JOIN external_residuals r ON r.ordinal=c.ordinal "
                "WHERE r.quant=? ORDER BY c.ordinal", (quant_id,)
            )
        )

    def complete_pairs(left_quant, right_quant):
        return (
            (left, right)
            for left, right in con.execute(
                "SELECT a.value,b.value FROM external_complete_ordinals c "
                "JOIN external_residuals a ON a.ordinal=c.ordinal AND a.quant=? "
                "JOIN external_residuals b ON b.ordinal=c.ordinal AND b.quant=? "
                "ORDER BY c.ordinal", (left_quant, right_quant),
            )
        )

    representatives = []
    groups = []
    if complete_n:
        for index in range(p):
            match = None
            for group_index, representative in enumerate(representatives):
                difference = max(
                    abs(left - right)
                    for left, right in complete_pairs(
                        quant_ids[index], quant_ids[representative]
                    )
                )
                rms_index = math.sqrt(
                    math.fsum(value * value for value in complete_values(quant_ids[index]))
                    / complete_n
                )
                rms_representative = math.sqrt(
                    math.fsum(
                        value * value
                        for value in complete_values(quant_ids[representative])
                    ) / complete_n
                )
                if difference <= EPSILON_RELATIVE * max(
                    rms_index, rms_representative, EPSILON_ABSOLUTE
                ):
                    match = group_index
                    break
            if match is None:
                representatives.append(index)
                groups.append([index])
            else:
                groups[match].append(index)
    duplicate_groups = tuple(
        tuple(quant_ids[index] for index in group)
        for group in groups if len(group) > 1
    )
    empirical = [[0.0] * p for _ in range(p)]
    candidate = None
    shrinkage = None
    delta = pooled = None
    dependence = False
    if complete_n >= 2 and p and representatives:
        means = [
            math.fsum(complete_values(quant_ids[index])) / complete_n
            for index in representatives
        ]
        dimension = len(representatives)
        empirical_collapsed = [[0.0] * dimension for _ in range(dimension)]
        for i, left_index in enumerate(representatives):
            for j, right_index in enumerate(representatives):
                empirical_collapsed[i][j] = math.fsum(
                    (left - means[i]) * (right - means[j])
                    for left, right in complete_pairs(
                        quant_ids[left_index], quant_ids[right_index]
                    )
                ) / complete_n
        if dimension == 1:
            sigma_collapsed = [empirical_collapsed[0][:]]
            delta = 1.0
            pooled = empirical_collapsed[0][0]
        else:
            trace = math.fsum(empirical_collapsed[i][i] for i in range(dimension))
            squared = math.fsum(
                empirical_collapsed[i][j] * empirical_collapsed[j][i]
                for i in range(dimension) for j in range(dimension)
            )
            numerator = (1.0 - 2.0 / dimension) * squared + trace * trace
            denominator = (
                (complete_n + 1.0 - 2.0 / dimension)
                * (squared - trace * trace / dimension)
            )
            delta = (
                min(1.0, max(0.0, numerator / denominator))
                if denominator > 0 else 1.0
            )
            pooled = trace / dimension
            sigma_collapsed = [
                [
                    (1.0 - delta) * empirical_collapsed[i][j]
                    + (delta * pooled if i == j else 0.0)
                    for j in range(dimension)
                ]
                for i in range(dimension)
            ]
        group_by_index = {
            member: group_index
            for group_index, group in enumerate(groups) for member in group
        }
        for group_i, members_i in enumerate(groups):
            for group_j, members_j in enumerate(groups):
                for i in members_i:
                    for j in members_j:
                        empirical[i][j] = empirical_collapsed[group_i][group_j]
        candidate = [
            [sigma_collapsed[group_by_index[i]][group_by_index[j]] for j in range(p)]
            for i in range(p)
        ]
        shrinkage = OAS_METHOD
        dependence = True
    else:
        reasons.add("COMPLETE_CASE_DEPENDENCE_UNAVAILABLE")
        positive = [
            pair_covariance[i][i] for i in range(p)
            if support[i][i]
            and math.isfinite(pair_covariance[i][i])
            and pair_covariance[i][i] > 0.0
        ]
        if positive:
            pooled = math.fsum(positive) / len(positive)
            diagonal = []
            for i in range(p):
                value = (
                    pair_covariance[i][i]
                    if support[i][i] and pair_covariance[i][i] > 0.0
                    else pooled
                )
                if value == pooled and not (
                    support[i][i] and pair_covariance[i][i] > 0.0
                ):
                    reasons.add("POOLED_VARIANCE_FALLBACK")
                diagonal.append(value)
            candidate = [
                [diagonal[i] if i == j else 0.0 for j in range(p)]
                for i in range(p)
            ]
    psd_matrix = [[0.0] * p for _ in range(p)]
    stable = [[0.0] * p for _ in range(p)]
    minimum_before = minimum_after = correction = relative = ridge = condition = None
    clipped = 0
    status = "UNAVAILABLE"
    if candidate is not None and all(
        math.isfinite(value) for row in candidate for value in row
    ):
        (
            psd_matrix, minimum_before, minimum_after, clipped, correction, relative
        ) = _psd(candidate)
        trace = math.fsum(psd_matrix[i][i] for i in range(p))
        if p and math.isfinite(trace) and trace > 0.0:
            ridge = max(EPSILON_ABSOLUTE, EPSILON_RELATIVE * trace / p)
            stable = [
                [psd_matrix[i][j] + (ridge if i == j else 0.0) for j in range(p)]
                for i in range(p)
            ]
            eigenvalues, _ = _jacobi(stable)
            condition = max(eigenvalues) / min(eigenvalues)
            material = relative > EPSILON_RELATIVE
            if material:
                reasons.add("MATERIAL_PSD_CORRECTION")
            mature = (
                dependence and complete_n >= 2 and all(selected)
                and all(item.status == "MATURE" for item in selected if item)
                and all(support[i][j] for i in range(p) for j in range(p))
                and pooled is not None and math.isfinite(pooled) and pooled > 0.0
                and not material
                and "COMPLETE_CASE_INTEGRITY_REJECTED" not in reasons
            )
            status = "MATURE" if mature else "PROVISIONAL"
    if status == "UNAVAILABLE":
        reasons.add("SUPPORTED_POSITIVE_SCALE_UNAVAILABLE")
        dependence = False
    return V2CCovariance(
        V2C_VERSION, view.horizon, view.dataset_hash, calibration_hash,
        quant_ids, formulas, ordered_lineage, _matrix(counts),
        _matrix(effective_ns), tuple(tuple(row) for row in support),
        _matrix(pair_covariance),
        tuple(quant_ids[index] for index in representatives), complete_n,
        duplicate_groups, _matrix(empirical), shrinkage, delta, pooled,
        _matrix(psd_matrix), _matrix(stable), minimum_before, minimum_after,
        clipped, correction, relative, ridge, condition, dependence, status,
        tuple(sorted(reasons)),
    )


def _assemble_external_horizon(
    view: ExternalV2AView,
    calibration: V2BCalibration,
    covariance: V2CCovariance,
):
    validate_external_v2a(view)
    horizon = view.horizon
    lineage_map = {item.quant_id: item for item in view.family_lineage}
    expected_ids = tuple(
        quant_id for quant_id in DIRECTIONAL_FAMILIES if quant_id in lineage_map
    )
    expected_formulas = tuple(lineage_map[q].formula_version for q in expected_ids)
    expected_lineage = tuple(lineage_map.get(q) for q in expected_ids)
    q3_lineage = lineage_map.get(Q3)
    b_items = tuple(
        item for item in calibration.directional if item.horizon == horizon
    )
    b_map = {
        (
            item.quant_id, item.formula_version, item.data_schema_version,
            item.source_spec_version, item.dataset_hash,
        ): item
        for item in b_items
    }
    ordered_b = tuple(
        b_map.get((
            quant_id, formula, lineage.data_schema_version,
            lineage.source_spec_version, view.dataset_hash,
        )) if lineage is not None else None
        for quant_id, formula, lineage in zip(
            expected_ids, expected_formulas, expected_lineage
        )
    )
    has_q3 = Q3 in lineage_map
    q3_items = tuple(
        item for item in calibration.q3_magnitude if item.horizon == horizon
    )
    q3_item = next((
        item for item in q3_items
        if has_q3 and q3_lineage is not None
        and (
            item.quant_id, item.formula_version, item.data_schema_version,
            item.source_spec_version, item.dataset_hash,
        ) == (
            Q3, q3_lineage.formula_version, q3_lineage.data_schema_version,
            q3_lineage.source_spec_version, view.dataset_hash,
        )
    ), None)
    manifest = dict(calibration.input_manifest)
    canonical_lineage = tuple(
        lineage_map[q] for q in (*DIRECTIONAL_FAMILIES, Q3) if q in lineage_map
    )
    integrity = (
        _all_finite((calibration, covariance))
        and calibration.formula_version == V2B_VERSION
        and len(manifest) == len(calibration.input_manifest)
        and manifest.get(horizon) == view.dataset_hash
        and covariance.method_version == V2C_VERSION
        and covariance.horizon == horizon
        and covariance.dataset_hash == view.dataset_hash
        and covariance.v2b_component_hash == v2b_component_hash(calibration, horizon)
        and all(item.horizon == horizon for item in b_items + q3_items)
        and len(b_map) == len(b_items)
        and view.family_lineage == canonical_lineage
        and all(item is not None for item in expected_lineage)
        and covariance.ordered_family_lineage == expected_lineage
        and expected_ids == tuple(q for q in DIRECTIONAL_FAMILIES if q in expected_ids)
        and len(b_items) == len(expected_ids)
        and all(ordered_b)
        and covariance.ordered_quant_ids == expected_ids
        and covariance.ordered_formula_versions == expected_formulas
        and isinstance(covariance.pair_support_boolean_matrix, tuple)
        and len(covariance.pair_support_boolean_matrix) == len(expected_ids)
        and all(
            isinstance(row, tuple) and len(row) == len(expected_ids)
            and all(isinstance(value, bool) for value in row)
            for row in covariance.pair_support_boolean_matrix
        )
        and len(covariance.stabilized_covariance_matrix) == len(expected_ids)
        and all(
            len(row) == len(expected_ids)
            for row in covariance.stabilized_covariance_matrix
        )
        and Q3 not in expected_ids
        and Q3 not in covariance.ordered_quant_ids
        and ((not has_q3 and not q3_items)
             or (has_q3 and len(q3_items) == 1 and q3_item is not None))
    )
    if not integrity:
        return _missing(horizon, "CROSS_LAYER_INTEGRITY_FAILURE"), False
    directional = tuple(_directional(item) for item in ordered_b if item is not None)
    usable = tuple(item for item in directional if item.status != "UNAVAILABLE")
    q3_state = _q3(q3_item)
    covariance_usable = (
        covariance.status != "UNAVAILABLE"
        and len(covariance.stabilized_covariance_matrix) == len(directional)
        and all(
            len(row) == len(directional)
            for row in covariance.stabilized_covariance_matrix
        )
    )
    reasons = set(covariance.reason_codes)
    reasons.update(reason for item in directional for reason in item.reason_codes)
    reasons.update(q3_state.reason_codes)
    if not usable:
        status = "UNAVAILABLE"
    elif not covariance_usable:
        status = "UNAVAILABLE"
        reasons.add("COVARIANCE_UNAVAILABLE")
    elif (
        all(item.status == "MATURE" for item in directional)
        and covariance.status == "MATURE"
        and (not has_q3 or q3_state.status == "MATURE")
    ):
        status = "MATURE"
    else:
        status = "PROVISIONAL"
    return HorizonEvidenceState(
        horizon, HORIZON_SECONDS[horizon], status, tuple(sorted(reasons)),
        directional, view.family_lineage, covariance.ordered_quant_ids,
        covariance.pair_support_boolean_matrix,
        covariance.stabilized_covariance_matrix if covariance_usable else None,
        covariance.dependence_modeled if covariance_usable else False,
        covariance.status, tuple(sorted(covariance.reason_codes)), q3_state,
    ), True


def build_external_v2d(
    view_or_views,
    calibration: V2BCalibration,
    covariance_or_covariances,
    *,
    state_as_of=None,
) -> V2EvidenceState:
    """Assemble a byte-identical six-horizon state without materializing V2A."""
    views = _external_views(view_or_views)
    covariances = (
        (covariance_or_covariances,)
        if isinstance(covariance_or_covariances, V2CCovariance)
        else tuple(covariance_or_covariances)
    )
    if len({item.horizon for item in covariances}) != len(covariances):
        raise ValueError("duplicate external V2C horizon")
    if state_as_of is None:
        state_as_of = max(view.state_as_of for view in views)
    if not _finite(state_as_of):
        raise ValueError("state_as_of must be a finite binary64 value")
    view_by_horizon = {view.horizon: view for view in views}
    covariance_by_horizon = {item.horizon: item for item in covariances}
    entries = tuple(calibration.input_manifest)
    manifest = dict(entries)
    expected_manifest = tuple(
        (horizon, view_by_horizon[horizon].dataset_hash)
        for horizon in HORIZONS
        if horizon in manifest and horizon in view_by_horizon
    )
    invalid_manifest = len(manifest) != len(entries) or entries != expected_manifest
    horizon_states = []
    hashes = []
    accepted_views = []
    accepted_indexes = []
    for horizon in HORIZONS:
        view = view_by_horizon.get(horizon)
        covariance = covariance_by_horizon.get(horizon)
        has_calibration = any(
            item.horizon == horizon for item in calibration.directional
        ) or any(item.horizon == horizon for item in calibration.q3_magnitude)
        if view is None and covariance is None and not has_calibration:
            horizon_states.append(_missing(horizon))
            continue
        if (
            view is None or covariance is None or not has_calibration
            or invalid_manifest or view.state_as_of > state_as_of
        ):
            horizon_states.append(_missing(horizon, "CROSS_LAYER_INTEGRITY_FAILURE"))
            continue
        horizon_state, accepted = _assemble_external_horizon(
            view, calibration, covariance
        )
        horizon_states.append(horizon_state)
        if accepted:
            accepted_views.append(view)
            accepted_indexes.append(len(horizon_states) - 1)
            hashes.extend((
                ComponentHash(horizon, "V2A", view.dataset_hash),
                ComponentHash(
                    horizon, "V2B", v2b_component_hash(calibration, horizon)
                ),
                ComponentHash(horizon, "V2C", _digest(covariance)),
            ))
    accepted_identities = {
        (
            view.target_spec_id, view.target_data_schema_version,
            view.target_source_spec_version,
        )
        for view in accepted_views
    }
    if len(accepted_identities) > 1:
        for index in accepted_indexes:
            horizon_states[index] = _missing(
                horizon_states[index].horizon, "CROSS_LAYER_INTEGRITY_FAILURE"
            )
        accepted_views.clear()
        accepted_indexes.clear()
        hashes.clear()
    heterogeneous = len({view.state_as_of for view in accepted_views}) > 1
    if heterogeneous:
        for index in accepted_indexes:
            horizon_state = horizon_states[index]
            horizon_states[index] = replace(
                horizon_state,
                status=(
                    "PROVISIONAL"
                    if horizon_state.status == "MATURE" else horizon_state.status
                ),
                reason_codes=_reasons(
                    horizon_state.reason_codes,
                    ("HETEROGENEOUS_COMPONENT_CUTOFF",),
                ),
            )
    horizon_tuple = tuple(horizon_states)
    component_tuple = tuple(sorted(set(hashes)))
    evidence_manifest = _digest(tuple(
        (item.horizon, item.layer, item.digest) for item in component_tuple
    ))
    starts = [
        view.training_start for view in accepted_views
        if view.training_start is not None
    ]
    ends = [
        view.training_end for view in accepted_views if view.training_end is not None
    ]
    identities = {
        (
            view.target_spec_id, view.target_data_schema_version,
            view.target_source_spec_version,
        )
        for view in accepted_views
    }
    identity = next(iter(identities)) if len(identities) == 1 else (None, None, None)
    exclusion = {}
    for view in accepted_views:
        for count in view.exclusions:
            exclusion[count.reason_code] = exclusion.get(count.reason_code, 0) + count.count
    statuses = tuple(item.status for item in horizon_tuple)
    top_status = (
        "MATURE" if all(item == "MATURE" for item in statuses)
        else "UNAVAILABLE" if all(item == "UNAVAILABLE" for item in statuses)
        else "PROVISIONAL"
    )
    top_reasons = {
        reason for item in horizon_tuple for reason in item.reason_codes
    }
    if heterogeneous:
        top_reasons.add("HETEROGENEOUS_COMPONENT_CUTOFF")
    shell = V2EvidenceState(
        STATE_SCHEMA_VERSION, STATE_VERSION, MODEL_FAMILY, "COIN",
        float(state_as_of), min(starts) if starts else None,
        max(ends) if ends else None, *identity, METHOD_VERSION, V2B_VERSION,
        V2C_VERSION, EFFECTIVE_N_METHOD_VERSION, CALIBRATION_METHOD_VERSION,
        COVARIANCE_METHOD_VERSION, NUMERICAL_CANONICALIZATION_VERSION,
        evidence_manifest, component_tuple, horizon_tuple,
        tuple(sorted(exclusion.items())), top_status, "VALID",
        tuple(sorted(top_reasons)), "", "",
    )
    digest = v2d_state_hash(shell)
    state = replace(shell, state_hash=digest, state_id="v9v2:" + digest)
    if not _all_finite(state):
        raise ValueError("non-finite float in assembled external V2D state")
    serialize_v2_evidence_state(state)
    return state
