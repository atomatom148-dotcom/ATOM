"""H2-B read-only, bounded-memory verification of historical replay evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import os
import time
from typing import Callable

from quant.historical_evidence import HistoricalForecastEvidence, HistoricalReplayManifest


VERIFIER_VERSION = "H2-B-2"
DEFAULT_FETCH_SIZE = 2_000
QUANTS = tuple(f"q{i}_{name}" for i, name in enumerate((
    "momentum", "mean_reversion", "volatility", "stat_arb", "microstructure",
    "volume_liquidity", "relative_value", "cross_asset", "factor",
    "options_vol", "regime", "event_session"), 1))
HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")
SLOTS = frozenset((quant, horizon) for quant in QUANTS for horizon in HORIZONS)

MANIFEST_COLUMNS = (
    "replay_run_id", "historical_session", "execution_stage", "certification_status",
    "git_commit", "configuration_digest", "dataset_digest", "session_digest",
    "artifact_sha256", "frame_count", "quote_counts", "available_observation_count",
    "unavailable_observation_count", "stage_timings", "family_timings",
    "data_schema_version", "source_schema_version", "created_at", "content_sha256",
)
FORECAST_COLUMNS = (
    "replay_run_id", "cutoff_at", "quant_id", "horizon", "expected_return_bps",
    "availability_status", "unavailable_reason", "formula_version", "numerical_type",
    "source_as_of", "available_at", "data_schema_version", "source_schema_version",
    "content_sha256",
)


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    replay_run_id: str
    historical_session: str | None
    verification_status: str
    reason_codes: tuple[str, ...]
    manifest_count: int
    frame_count: int
    forecast_count: int
    cutoff_count: int
    quant_count: int
    horizon_count: int
    unavailable_null_count: int
    dataset_digest: str | None
    configuration_digest: str | None
    stored_content_hash_summary: str
    verifier_version: str
    verified_at: str

    def payload(self) -> dict[str, object]:
        return asdict(self)


def _as_manifest(row: tuple[object, ...]) -> tuple[HistoricalReplayManifest, str]:
    values = dict(zip(MANIFEST_COLUMNS, row, strict=True))
    stored_hash = str(values.pop("content_sha256"))
    values["historical_session"] = str(values["historical_session"])
    return HistoricalReplayManifest(**values), stored_hash


def _as_forecast(row: tuple[object, ...]) -> tuple[HistoricalForecastEvidence, str]:
    values = dict(zip(FORECAST_COLUMNS, row, strict=True))
    stored_hash = str(values.pop("content_sha256"))
    # H2-A hashed UTC datetimes. PostgreSQL decodes timestamptz values in the
    # connection's TimeZone, so an equivalent instant can otherwise serialize
    # with a different offset and fail the immutable per-row hash check.
    for field in ("cutoff_at", "source_as_of", "available_at"):
        value = values[field]
        if isinstance(value, datetime) and value.tzinfo is not None:
            values[field] = value.astimezone(timezone.utc)
    return HistoricalForecastEvidence(**values), stored_hash


class HistoricalEvidenceVerifier:
    """Verify immutable H2-A rows using SELECT statements and ``fetchmany`` only."""

    def __init__(self, connection, *, fetch_size: int = DEFAULT_FETCH_SIZE,
                 clock: Callable[[], datetime] | None = None):
        if not isinstance(fetch_size, int) or isinstance(fetch_size, bool) or fetch_size < 1:
            raise ValueError("fetch_size must be a positive integer")
        self.connection = connection
        self.fetch_size = fetch_size
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def verify(self, replay_run_id: str, *, expected_dataset_digest: str | None = None,
               expected_configuration_digest: str | None = None,
               expected_frame_count: int | None = None) -> VerificationReceipt:
        if not replay_run_id or len(replay_run_id) > 128:
            raise ValueError("replay_run_id must contain 1..128 characters")
        reasons: set[str] = set()
        manifest = None
        manifest_count = frame_count = forecast_count = cutoff_count = unavailable = 0
        quants: set[str] = set()
        horizons: set[str] = set()
        artifact = hashlib.sha256()
        manifest_cursor = self.connection.cursor()
        forecast_cursor = None
        try:
            manifest_cursor.execute(
                "SELECT " + ",".join(MANIFEST_COLUMNS) +
                " FROM public.atom_historical_replay_runs WHERE replay_run_id=%s",
                (replay_run_id,),
            )
            manifest_rows = manifest_cursor.fetchmany(2)
            manifest_cursor.close()
            manifest_count = len(manifest_rows)
            if manifest_count != 1:
                reasons.add("MISSING_MANIFEST" if manifest_count == 0 else "MULTIPLE_MANIFESTS")
            else:
                try:
                    manifest, stored_manifest_hash = _as_manifest(manifest_rows[0])
                    if manifest.content_sha256 != stored_manifest_hash:
                        reasons.add("MANIFEST_HASH_MISMATCH")
                    if manifest.execution_stage != "REPLAY_COMPLETE":
                        reasons.add("RUN_INCOMPLETE")
                    if manifest.certification_status != "CERTIFIED":
                        reasons.add("RUN_UNCERTIFIED")
                    frame_count = manifest.frame_count
                    if expected_frame_count is not None and manifest.frame_count != expected_frame_count:
                        reasons.add("FRAME_COUNT_MISMATCH")
                    required = (manifest.git_commit, manifest.session_digest,
                                manifest.data_schema_version, manifest.source_schema_version)
                    if any(not value for value in required):
                        reasons.add("MISSING_LINEAGE_OR_VERSION")
                    if expected_dataset_digest is not None and manifest.dataset_digest != expected_dataset_digest:
                        reasons.add("DATASET_DIGEST_MISMATCH")
                    if (expected_configuration_digest is not None and
                            manifest.configuration_digest != expected_configuration_digest):
                        reasons.add("CONFIGURATION_DIGEST_MISMATCH")
                except Exception:
                    reasons.add("INVALID_MANIFEST")

            # A named psycopg cursor is a PostgreSQL server-side portal.  Both
            # itersize and explicit fetchmany calls cap client-side transfer;
            # the 808,488-row result is never materialized by the client.
            forecast_cursor = self.connection.cursor(name="atom_h2b_forecasts")
            forecast_cursor.itersize = self.fetch_size
            quant_order = "CASE quant_id " + " ".join(
                f"WHEN '{quant}' THEN {index}" for index, quant in enumerate(QUANTS)
            ) + " END"
            horizon_order = "CASE horizon " + " ".join(
                f"WHEN '{horizon}' THEN {index}" for index, horizon in enumerate(HORIZONS)
            ) + " END"
            forecast_cursor.execute(
                "SELECT " + ",".join(FORECAST_COLUMNS) +
                " FROM public.atom_historical_replay_forecasts WHERE replay_run_id=%s"
                f" ORDER BY cutoff_at,{quant_order},{horizon_order}",
                (replay_run_id,),
            )
            current_cutoff = None
            cutoff_slots: set[tuple[str, str]] = set()
            previous_identity = None
            while True:
                batch = forecast_cursor.fetchmany(self.fetch_size)
                if not batch:
                    break
                for raw in batch:
                    forecast_count += 1
                    try:
                        row, stored_hash = _as_forecast(raw)
                        identity = (row.cutoff_at, row.quant_id, row.horizon)
                        if current_cutoff is None:
                            current_cutoff = row.cutoff_at
                        elif row.cutoff_at != current_cutoff:
                            cutoff_count += 1
                            if cutoff_slots != SLOTS:
                                reasons.add("MISSING_OR_INVALID_SLOTS")
                            current_cutoff, cutoff_slots = row.cutoff_at, set()
                        if identity == previous_identity or (row.quant_id, row.horizon) in cutoff_slots:
                            reasons.add("DUPLICATE_SLOT")
                        previous_identity = identity
                        cutoff_slots.add((row.quant_id, row.horizon))
                        quants.add(row.quant_id)
                        horizons.add(row.horizon)
                        unavailable += row.availability_status == "UNAVAILABLE" and row.expected_return_bps is None
                        if (not row.formula_version or not row.numerical_type or
                                not row.data_schema_version or not row.source_schema_version):
                            reasons.add("MISSING_LINEAGE_OR_VERSION")
                        if manifest is not None and (row.data_schema_version != manifest.data_schema_version or
                                                     row.source_schema_version != manifest.source_schema_version):
                            reasons.add("MISSING_LINEAGE_OR_VERSION")
                        if row.content_sha256 != stored_hash:
                            reasons.add("FORECAST_HASH_MISMATCH")
                        artifact.update(stored_hash.encode("ascii"))
                    except ValueError as error:
                        if "forecast" in str(error):
                            reasons.add("INVALID_AVAILABILITY_NULL_PAIRING")
                        else:
                            reasons.add("INVALID_FORECAST")
                    except Exception:
                        reasons.add("INVALID_FORECAST")
            if current_cutoff is not None:
                cutoff_count += 1
                if cutoff_slots != SLOTS:
                    reasons.add("MISSING_OR_INVALID_SLOTS")
            if manifest is not None:
                if forecast_count != manifest.frame_count * len(SLOTS) or cutoff_count != manifest.frame_count:
                    reasons.add("FORECAST_COUNT_MISMATCH")
                if artifact.hexdigest() != manifest.artifact_sha256:
                    reasons.add("ARTIFACT_HASH_MISMATCH")
                if unavailable != manifest.unavailable_observation_count:
                    reasons.add("AVAILABILITY_COUNT_MISMATCH")
        except Exception:
            reasons.add("DATABASE_INTERRUPTION_OR_PARTIAL_RETRIEVAL")
        finally:
            for cursor in (forecast_cursor, manifest_cursor):
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()

        digest = artifact.hexdigest()
        return VerificationReceipt(
            replay_run_id, str(manifest.historical_session) if manifest else None,
            "VERIFIED" if not reasons else "REJECTED", tuple(sorted(reasons)),
            manifest_count, frame_count, forecast_count, cutoff_count,
            len(quants), len(horizons), unavailable,
            manifest.dataset_digest if manifest else None,
            manifest.configuration_digest if manifest else None, digest, VERIFIER_VERSION,
            self.clock().astimezone(timezone.utc).isoformat(),
        )


def verify_from_environment(replay_run_id: str, **expected: str | None) -> VerificationReceipt:
    """Connect only through the dedicated H2 database URL; never log its value."""
    database_url = os.environ.get("HISTORICAL_EVIDENCE_DATABASE_URL")
    if not database_url:
        raise RuntimeError("HISTORICAL_EVIDENCE_DATABASE_URL is required")
    import psycopg
    with psycopg.connect(database_url) as connection:
        connection.read_only = True
        return HistoricalEvidenceVerifier(connection).verify(replay_run_id, **expected)


def main() -> int:
    """CLI emitting the receipt plus local performance observations as JSON."""
    import argparse
    import json
    import resource

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay_run_id")
    parser.add_argument("--dataset-digest")
    parser.add_argument("--configuration-digest")
    parser.add_argument("--frame-count", type=int)
    args = parser.parse_args()
    started = time.monotonic()
    receipt = verify_from_environment(
        args.replay_run_id, expected_dataset_digest=args.dataset_digest,
        expected_configuration_digest=args.configuration_digest,
        expected_frame_count=args.frame_count,
    )
    output = receipt.payload() | {
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0 if receipt.verification_status == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
