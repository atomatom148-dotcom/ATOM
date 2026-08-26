"""Append-only persistence for certified H1 historical forecast evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Iterable


HISTORICAL_EVIDENCE_SCHEMA_VERSION = "H2-A-1"
DEFAULT_BATCH_SIZE = 2_000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HistoricalForecastEvidence:
    replay_run_id: str
    cutoff_at: datetime
    quant_id: str
    horizon: str
    expected_return_bps: float | None
    availability_status: str
    unavailable_reason: str | None
    formula_version: str
    numerical_type: str
    source_as_of: datetime
    available_at: datetime
    data_schema_version: str
    source_schema_version: str

    def __post_init__(self) -> None:
        if self.availability_status == "AVAILABLE":
            if (self.expected_return_bps is None or
                    not math.isfinite(self.expected_return_bps) or
                    self.unavailable_reason is not None):
                raise ValueError("available historical forecast is invalid")
        elif self.availability_status == "UNAVAILABLE":
            if self.expected_return_bps is not None or not self.unavailable_reason:
                raise ValueError("unavailable historical forecast is invalid")
        else:
            raise ValueError("historical forecast availability status is invalid")
        if self.source_as_of > self.cutoff_at or self.available_at > self.cutoff_at:
            raise ValueError("historical forecast lineage exceeds its cutoff")

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def content_sha256(self) -> str:
        return _sha256(self.payload())


@dataclass(frozen=True, slots=True)
class HistoricalReplayManifest:
    replay_run_id: str
    historical_session: str
    execution_stage: str
    certification_status: str
    git_commit: str
    configuration_digest: str
    dataset_digest: str
    session_digest: str
    artifact_sha256: str
    frame_count: int
    quote_counts: dict[str, int]
    available_observation_count: int
    unavailable_observation_count: int
    stage_timings: dict[str, object]
    family_timings: dict[str, float]
    data_schema_version: str
    source_schema_version: str
    created_at: datetime

    def payload(self) -> dict[str, object]:
        return asdict(self)

    @property
    def content_sha256(self) -> str:
        # Creation time is database provenance, not replay content. An exact
        # retry generated later must retain the same immutable content digest.
        payload = self.payload()
        payload.pop("created_at")
        return _sha256(payload)


def artifact_sha256(rows: Iterable[HistoricalForecastEvidence]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row.content_sha256.encode("ascii"))
    return digest.hexdigest()


def build_manifest(report, rows: tuple[HistoricalForecastEvidence, ...], *,
                   git_commit: str) -> HistoricalReplayManifest:
    if report.execution_stage != "REPLAY_COMPLETE" or report.data_status != "CERTIFIED":
        raise ValueError("only REPLAY_COMPLETE + CERTIFIED runs may persist")
    available = sum(row.availability_status == "AVAILABLE" for row in rows)
    unavailable = len(rows) - available
    timings = asdict(report.timings)
    family_timings = timings.pop("family_seconds")
    source_versions = {row.source_schema_version for row in rows}
    data_versions = {row.data_schema_version for row in rows}
    if len(rows) != report.frame_count * 72 or len(source_versions) != 1 or len(data_versions) != 1:
        raise ValueError("historical evidence must contain exactly 72 lineage-consistent slots per frame")
    return HistoricalReplayManifest(
        report.replay_run_id, report.historical_session, report.execution_stage,
        report.data_status, git_commit, report.configuration_digest,
        report.dataset_digest, report.session_digest, artifact_sha256(rows),
        report.frame_count, dict(report.quote_counts), available, unavailable,
        timings, family_timings, data_versions.pop(), source_versions.pop(),
        datetime.now(timezone.utc),
    )


class HistoricalEvidenceWriter:
    """Write one certified manifest and all its slots in one transaction."""

    def __init__(self, connection, *, batch_size: int = DEFAULT_BATCH_SIZE):
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        self.connection = connection
        self.batch_size = batch_size

    def persist(self, manifest: HistoricalReplayManifest,
                forecasts: tuple[HistoricalForecastEvidence, ...]) -> int:
        if manifest.execution_stage != "REPLAY_COMPLETE" or manifest.certification_status != "CERTIFIED":
            raise ValueError("only REPLAY_COMPLETE + CERTIFIED runs may persist")
        if artifact_sha256(forecasts) != manifest.artifact_sha256:
            raise ValueError("artifact digest does not match forecast evidence")
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(%s, 0))", (manifest.replay_run_id,))
            cursor.execute("SELECT content_sha256 FROM public.atom_historical_replay_runs WHERE replay_run_id=%s", (manifest.replay_run_id,))
            existing = cursor.fetchone()
            if existing is not None:
                if existing[0] != manifest.content_sha256:
                    raise RuntimeError("HISTORICAL_REPLAY_MANIFEST_CONFLICT")
                matched = identical = 0
                for offset in range(0, len(forecasts), self.batch_size):
                    batch = forecasts[offset:offset + self.batch_size]
                    expected = [{"cutoff_at": row.cutoff_at,
                                 "quant_id": row.quant_id,
                                 "horizon": row.horizon,
                                 "expected_sha256": row.content_sha256}
                                for row in batch]
                    cursor.execute("SELECT count(*), count(*) FILTER (WHERE content_sha256 = expected_sha256) FROM (SELECT f.content_sha256, x.expected_sha256 FROM public.atom_historical_replay_forecasts f JOIN jsonb_to_recordset(%s::jsonb) AS x(cutoff_at timestamptz, quant_id text, horizon text, expected_sha256 text) ON f.replay_run_id=%s AND f.cutoff_at=x.cutoff_at AND f.quant_id=x.quant_id AND f.horizon=x.horizon) checked", (_canonical(expected), manifest.replay_run_id))
                    counts = cursor.fetchone()
                    matched += counts[0]
                    identical += counts[1]
                if (matched, identical) != (len(forecasts), len(forecasts)):
                    raise RuntimeError("HISTORICAL_REPLAY_FORECAST_CONFLICT")
                self.connection.commit()
                return 0
            payload = manifest.payload() | {"content_sha256": manifest.content_sha256}
            cursor.execute("INSERT INTO public.atom_historical_replay_runs (replay_run_id,historical_session,execution_stage,certification_status,git_commit,configuration_digest,dataset_digest,session_digest,artifact_sha256,frame_count,quote_counts,available_observation_count,unavailable_observation_count,stage_timings,family_timings,data_schema_version,source_schema_version,created_at,content_sha256) SELECT replay_run_id,historical_session,execution_stage,certification_status,git_commit,configuration_digest,dataset_digest,session_digest,artifact_sha256,frame_count,quote_counts,available_observation_count,unavailable_observation_count,stage_timings,family_timings,data_schema_version,source_schema_version,created_at,content_sha256 FROM jsonb_to_record(%s::jsonb) AS x(replay_run_id text,historical_session date,execution_stage text,certification_status text,git_commit text,configuration_digest text,dataset_digest text,session_digest text,artifact_sha256 text,frame_count bigint,quote_counts jsonb,available_observation_count bigint,unavailable_observation_count bigint,stage_timings jsonb,family_timings jsonb,data_schema_version text,source_schema_version text,created_at timestamptz,content_sha256 text)", (_canonical(payload),))
            for offset in range(0, len(forecasts), self.batch_size):
                batch = forecasts[offset:offset + self.batch_size]
                values = [row.payload() | {"content_sha256": row.content_sha256} for row in batch]
                cursor.execute("INSERT INTO public.atom_historical_replay_forecasts (replay_run_id,cutoff_at,quant_id,horizon,expected_return_bps,availability_status,unavailable_reason,formula_version,numerical_type,source_as_of,available_at,data_schema_version,source_schema_version,content_sha256) SELECT replay_run_id,cutoff_at,quant_id,horizon,expected_return_bps,availability_status,unavailable_reason,formula_version,numerical_type,source_as_of,available_at,data_schema_version,source_schema_version,content_sha256 FROM jsonb_to_recordset(%s::jsonb) AS x(replay_run_id text,cutoff_at timestamptz,quant_id text,horizon text,expected_return_bps double precision,availability_status text,unavailable_reason text,formula_version text,numerical_type text,source_as_of timestamptz,available_at timestamptz,data_schema_version text,source_schema_version text,content_sha256 text)", (_canonical(values),))
            self.connection.commit()
            return 1 + len(forecasts)
        except Exception:
            self.connection.rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
