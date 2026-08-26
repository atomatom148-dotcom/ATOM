from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

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
    def __init__(self, db, name=None):
        self.db, self.name, self.source, self.offset = db, name, (), 0
        self.itersize = None

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
        self.sql, self.max_fetch, self.cursors = [], 0, []

    def cursor(self, name=None):
        cursor = Cursor(self, name)
        self.cursors.append(cursor)
        return cursor


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
    assert (receipt.exact_hash_match_count, receipt.one_ulp_legacy_match_count) == (72, 0)
    assert receipt.verified_at == "2026-08-26T00:00:00+00:00"
    assert db.max_fetch == 17
    assert db.cursors[0].name is None
    assert db.cursors[1].name == "atom_h2b_forecasts"
    assert db.cursors[1].itersize == 17
    assert "CASE quant_id" in db.sql[1] and "CASE horizon" in db.sql[1]


def test_postgresql_timestamptz_offset_is_normalized_to_h2a_utc_payload():
    evidence = tuple(rows())
    database_timezone = timezone(-timedelta(hours=5))
    decoded = []
    for raw in evidence:
        values = dict(zip(FORECAST_COLUMNS, raw, strict=True))
        for field in ("cutoff_at", "source_as_of", "available_at"):
            values[field] = values[field].astimezone(database_timezone)
        decoded.append(tuple(values[field] for field in FORECAST_COLUMNS))

    receipt, _ = verify(decoded, [manifest(evidence)])
    first = HistoricalForecastEvidence(*evidence[0][:-1])
    canonical_payload = json.dumps(
        asdict(first), sort_keys=True, separators=(",", ":"), default=str,
    )

    assert decoded[0][1].isoformat() == "2026-06-15T08:30:00-05:00"
    assert canonical_payload == (
        '{"availability_status":"UNAVAILABLE","available_at":"2026-06-15 '
        '13:30:00+00:00","cutoff_at":"2026-06-15 13:30:00+00:00",'
        '"data_schema_version":"data-1","expected_return_bps":null,'
        '"formula_version":"formula-1","horizon":"30S",'
        '"numerical_type":"DIRECTIONAL_BPS","quant_id":"q1_momentum",'
        '"replay_run_id":"h2a-2026-06-15-persistence-v3",'
        '"source_as_of":"2026-06-15 13:30:00+00:00",'
        '"source_schema_version":"source-1","unavailable_reason":"NO_INPUT"}'
    )
    assert receipt.verification_status == "VERIFIED"
    assert "FORECAST_HASH_MISMATCH" not in receipt.reason_codes


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


def available_forecast(database_value, hashed_value, **changes):
    original = HistoricalForecastEvidence(
        RUN, NOW, QUANTS[1], "15M", hashed_value,
        "AVAILABLE", None, "formula-1", "DIRECTIONAL_BPS", NOW, NOW,
        "data-1", "source-1")
    payload = asdict(original) | changes | {"expected_return_bps": database_value}
    return tuple(payload[name] for name in FORECAST_COLUMNS[:-1]) + (original.content_sha256,)


def replace_slot(evidence, replacement):
    identity = (replacement[1], replacement[2], replacement[3])
    return [replacement if (row[1], row[2], row[3]) == identity else row for row in evidence]


def test_available_exact_hash_match_is_accepted_without_legacy_repair():
    evidence = replace_slot(list(rows()), available_forecast(1.0, 1.0))

    receipt, _ = verify(evidence)

    assert receipt.verification_status == "VERIFIED"
    assert (receipt.exact_hash_match_count, receipt.one_ulp_legacy_match_count) == (72, 0)


def test_confirmed_negative_direction_one_ulp_legacy_hash_is_accepted():
    database_value = -8.52740738334745
    hashed_value = math.nextafter(database_value, -math.inf)
    assert hashed_value == -8.527407383347452
    evidence = replace_slot(list(rows()), available_forecast(database_value, hashed_value))

    receipt, _ = verify(evidence)

    assert receipt.verification_status == "VERIFIED"
    assert (receipt.exact_hash_match_count, receipt.one_ulp_legacy_match_count) == (71, 1)


def test_positive_direction_one_ulp_legacy_hash_is_accepted():
    database_value = 1.0
    hashed_value = math.nextafter(database_value, math.inf)
    evidence = replace_slot(list(rows()), available_forecast(database_value, hashed_value))

    receipt, _ = verify(evidence)

    assert receipt.verification_status == "VERIFIED"
    assert (receipt.exact_hash_match_count, receipt.one_ulp_legacy_match_count) == (71, 1)


def test_two_ulp_forecast_hash_mismatch_rejects():
    database_value = 1.0
    one_ulp = math.nextafter(database_value, math.inf)
    hashed_value = math.nextafter(one_ulp, math.inf)
    evidence = replace_slot(list(rows()), available_forecast(database_value, hashed_value))

    receipt, _ = verify(evidence)

    assert receipt.verification_status == "REJECTED"
    assert "FORECAST_HASH_MISMATCH" in receipt.reason_codes


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_non_finite_available_forecast_rejects(value):
    evidence = list(rows())
    raw = list(evidence[0])
    raw[4:7] = [value, "AVAILABLE", None]
    evidence[0] = tuple(raw)

    receipt, _ = verify(evidence, [manifest(evidence)])

    assert receipt.verification_status == "REJECTED"
    assert "INVALID_AVAILABILITY_NULL_PAIRING" in receipt.reason_codes


def test_altered_non_numeric_field_cannot_use_one_ulp_compatibility():
    database_value = 1.0
    hashed_value = math.nextafter(database_value, math.inf)
    replacement = available_forecast(
        database_value, hashed_value, formula_version="altered-formula")
    evidence = replace_slot(list(rows()), replacement)

    receipt, _ = verify(evidence)

    assert receipt.verification_status == "REJECTED"
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
    assert receipt.cutoff_count == 11_229
    assert db.max_fetch == 997
    assert db.cursors[1].itersize == 997


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
