from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib

import pytest

from quant.historical_evidence import HistoricalForecastEvidence, HistoricalReplayManifest
from quant.historical_evidence_verifier import (
    FORECAST_COLUMNS,
    HORIZONS, MANIFEST_COLUMNS, QUANTS, HistoricalEvidenceVerifier,
)

NOW = datetime(2026, 6, 15, 13, 30, tzinfo=timezone.utc)
CLOCK = lambda: datetime(2026, 8, 26, tzinfo=timezone.utc)
RUN = "h2a-2026-06-15-persistence-v3"


def forecast(cutoff=NOW, quant=QUANTS[0], horizon=HORIZONS[0], **changes):
    row = HistoricalForecastEvidence(
        RUN, cutoff, quant, horizon, None, "UNAVAILABLE", "NO_INPUT", "formula-1",
        "DIRECTIONAL_BPS", cutoff, cutoff, "data-1", "source-1")
    values = asdict(row) | changes
    # Bypass constructor only for deliberately corrupt database rows.
    stored = changes.pop("stored_hash", None) if "stored_hash" in changes else None
    values = asdict(row) | changes
    try:
        value = HistoricalForecastEvidence(**values)
        payload = asdict(value)
        digest = stored or value.content_sha256
    except ValueError:
        payload = values
        digest = stored or "0" * 64
    return tuple(payload[name] for name in FORECAST_COLUMNS[:-1]) + (digest,)


def rows(frames=1):
    for frame in range(frames):
        cutoff = NOW.replace(microsecond=frame)
        for quant in QUANTS:
            for horizon in HORIZONS:
                yield forecast(cutoff, quant, horizon)


def manifest(forecast_rows, frames=1, **changes):
    artifact = hashlib.sha256()
    unavailable = 0
    for row in forecast_rows:
        artifact.update(row[-1].encode("ascii"))
        unavailable += row[5] == "UNAVAILABLE" and row[4] is None
    value = HistoricalReplayManifest(
        RUN, "2026-06-15", "REPLAY_COMPLETE", "CERTIFIED", "a" * 40,
        "dcd7f3af8fba60047ff965a22fc9dbf5f05734f97913c502f3d972f21cf46385",
        "c1dda6101424404b94ad39973f4c6a4a0feb67e90b537bae7f94a264130e6b3e",
        "b" * 64, artifact.hexdigest(), frames, {"COIN": 1},
        frames * 72 - unavailable, unavailable, {}, {}, "data-1", "source-1", NOW)
    value = replace(value, **{k: v for k, v in changes.items() if k != "stored_hash"})
    payload = asdict(value)
    return tuple(payload[name] for name in MANIFEST_COLUMNS[:-1]) + (
        changes.get("stored_hash", value.content_sha256),)


class Cursor:
    def __init__(self, db):
        self.db, self.source, self.offset = db, (), 0

    def execute(self, sql, params=()):
        self.db.sql.append(sql)
        if self.db.interrupt and "forecasts" in sql:
            raise OSError("database interrupted")
        self.source = self.db.manifests if "replay_runs" in sql else self.db.forecasts
        self.offset = 0

    def fetchmany(self, size):
        self.db.max_fetch = max(self.db.max_fetch, size)
        if self.db.partial and self.offset >= self.db.partial:
            raise OSError("partial retrieval")
        if isinstance(self.source, tuple):
            result = self.source[self.offset:self.offset + size]
        else:
            result = tuple(next(self.source, None) for _ in range(size))
            result = tuple(row for row in result if row is not None)
        self.offset += len(result)
        return result

    def close(self): pass


class DB:
    def __init__(self, manifests, forecasts, *, interrupt=False, partial=0):
        self.manifests, self.forecasts = tuple(manifests), iter(forecasts)
        self.interrupt, self.partial = interrupt, partial
        self.sql, self.max_fetch = [], 0

    def cursor(self): return Cursor(self)


def verify(forecasts, manifest_rows=None, **db_options):
    forecasts = tuple(forecasts)
    manifest_rows = [manifest(forecasts)] if manifest_rows is None else manifest_rows
    db = DB(manifest_rows, forecasts, **db_options)
    receipt = HistoricalEvidenceVerifier(db, fetch_size=17, clock=CLOCK).verify(
        RUN,
        expected_dataset_digest="c1dda6101424404b94ad39973f4c6a4a0feb67e90b537bae7f94a264130e6b3e",
        expected_configuration_digest="dcd7f3af8fba60047ff965a22fc9dbf5f05734f97913c502f3d972f21cf46385")
    assert all(statement.lstrip().startswith("SELECT") for statement in db.sql)
    return receipt, db


def test_valid_receipt_is_deterministic_and_complete():
    evidence = tuple(rows())
    receipt, db = verify(evidence)
    assert receipt.verification_status == "VERIFIED"
    assert receipt.reason_codes == ()
    assert (receipt.frame_count, receipt.forecast_count, receipt.quant_count,
            receipt.horizon_count, receipt.unavailable_null_count) == (1, 72, 12, 6, 72)
    assert receipt.verified_at == "2026-08-26T00:00:00+00:00"
    assert db.max_fetch == 17


@pytest.mark.parametrize("manifest_rows,reason", [
    ([], "MISSING_MANIFEST"),
    ([manifest(tuple(rows())), manifest(tuple(rows()))], "MULTIPLE_MANIFESTS"),
    ([manifest(tuple(rows()), execution_stage="STARTED")], "RUN_INCOMPLETE"),
    ([manifest(tuple(rows()), certification_status="PENDING")], "RUN_UNCERTIFIED"),
    ([manifest(tuple(rows()), stored_hash="f" * 64)], "MANIFEST_HASH_MISMATCH"),
    ([manifest(tuple(rows()), dataset_digest="f" * 64)], "DATASET_DIGEST_MISMATCH"),
    ([manifest(tuple(rows()), configuration_digest="f" * 64)], "CONFIGURATION_DIGEST_MISMATCH"),
    ([manifest(tuple(rows()), git_commit="")], "MISSING_LINEAGE_OR_VERSION"),
])
def test_manifest_rejections(manifest_rows, reason):
    receipt, _ = verify(tuple(rows()), manifest_rows)
    assert receipt.verification_status == "REJECTED" and reason in receipt.reason_codes


def test_missing_and_duplicate_slots_reject():
    evidence = list(rows())
    missing, _ = verify(evidence[:-1], [manifest(evidence)])
    duplicate_evidence = evidence + [evidence[-1]]
    duplicate, _ = verify(duplicate_evidence, [manifest(evidence)])
    assert "MISSING_OR_INVALID_SLOTS" in missing.reason_codes
    assert "DUPLICATE_SLOT" in duplicate.reason_codes


def test_invalid_null_pairing_missing_lineage_and_forecast_hash_reject():
    evidence = list(rows())
    evidence[0] = forecast(expected_return_bps=1.0)
    receipt, _ = verify(evidence, [manifest(evidence)])
    assert "INVALID_AVAILABILITY_NULL_PAIRING" in receipt.reason_codes
    evidence = list(rows())
    evidence[0] = forecast(formula_version="")
    receipt, _ = verify(evidence, [manifest(evidence)])
    assert "MISSING_LINEAGE_OR_VERSION" in receipt.reason_codes
    evidence = list(rows())
    evidence[0] = forecast(stored_hash="f" * 64)
    receipt, _ = verify(evidence, [manifest(evidence)])
    assert "FORECAST_HASH_MISMATCH" in receipt.reason_codes


@pytest.mark.parametrize("option", [{"interrupt": True}, {"partial": 17}])
def test_database_interruption_or_partial_retrieval_fails_closed(option):
    receipt, _ = verify(tuple(rows()), **option)
    assert receipt.verification_status == "REJECTED"
    assert "DATABASE_INTERRUPTION_OR_PARTIAL_RETRIEVAL" in receipt.reason_codes


def test_11229_by_72_verification_is_streamed_in_bounded_batches(monkeypatch):
    # A single-pass source plus fetchmany proves no full-result materialization.
    from types import SimpleNamespace
    import quant.historical_evidence_verifier as module

    frames, stored_hash = 11_229, "a" * 64
    count = frames * 72
    artifact = hashlib.sha256()
    for _ in range(count):
        artifact.update(stored_hash.encode("ascii"))

    def compact_rows():
        for frame in range(frames):
            cutoff = frame
            for quant in QUANTS:
                for horizon in HORIZONS:
                    yield (cutoff, quant, horizon, stored_hash)

    def decode(raw):
        cutoff, quant, horizon, digest = raw
        return SimpleNamespace(
            cutoff_at=cutoff, quant_id=quant, horizon=horizon,
            availability_status="UNAVAILABLE", expected_return_bps=None,
            formula_version="formula-1", numerical_type="DIRECTIONAL_BPS",
            data_schema_version="data-1", source_schema_version="source-1",
            content_sha256=digest), digest

    monkeypatch.setattr(module, "_as_forecast", decode)
    base_rows = tuple(rows())
    values = dict(zip(MANIFEST_COLUMNS, manifest(base_rows, frames=frames)))
    values.update(artifact_sha256=artifact.hexdigest(), available_observation_count=0,
                  unavailable_observation_count=count)
    obj = HistoricalReplayManifest(**{k: values[k] for k in MANIFEST_COLUMNS[:-1]})
    manifest_row = tuple(asdict(obj)[name] for name in MANIFEST_COLUMNS[:-1]) + (obj.content_sha256,)
    db = DB([manifest_row], compact_rows())
    receipt = HistoricalEvidenceVerifier(db, fetch_size=997, clock=CLOCK).verify(RUN)
    assert receipt.verification_status == "VERIFIED"
    assert receipt.frame_count == 11_229 and receipt.forecast_count == 808_488
    assert db.max_fetch == 997


def test_artifact_and_expected_frame_count_mismatches_reject():
    evidence = tuple(rows())
    receipt, _ = verify(evidence, [manifest(evidence, artifact_sha256="f" * 64)])
    assert "ARTIFACT_HASH_MISMATCH" in receipt.reason_codes
    db = DB([manifest(evidence)], evidence)
    receipt = HistoricalEvidenceVerifier(db, clock=CLOCK).verify(
        RUN, expected_frame_count=11_229)
    assert "FRAME_COUNT_MISMATCH" in receipt.reason_codes


def test_manifest_availability_total_mismatch_rejects():
    evidence = tuple(rows())
    receipt, _ = verify(
        evidence, [manifest(evidence, unavailable_observation_count=71,
                            available_observation_count=1)])
    assert "AVAILABILITY_COUNT_MISMATCH" in receipt.reason_codes
