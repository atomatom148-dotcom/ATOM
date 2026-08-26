"""H2-C append-only historical outcome resolution and read-only scoring."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import math
import os
import resource
import time
from typing import Iterable, Iterator

from .historical_evidence_verifier import HistoricalEvidenceVerifier, QUANTS
from .historical_replay import AlpacaHistoricalSipReader, HistoricalSipQuote
from .v9_v1_contract import HORIZON_SECONDS

OUTCOME_SCHEMA_VERSION = "H2-C-1"
RESOLUTION_SPEC_VERSION = "COIN_MIDPOINT_LOG_RETURN_BPS_1"
DEFAULT_BATCH_SIZE = 2_000
HORIZONS = tuple(HORIZON_SECONDS)
Q3 = "q3_volatility"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class HistoricalOutcome:
    replay_run_id: str
    cutoff_at: datetime
    horizon: str
    actual_return_bps: float | None
    availability_status: str
    unavailable_reason: str | None
    cutoff_midpoint_at: datetime | None
    cutoff_midpoint: float | None
    target_midpoint_at: datetime | None
    target_midpoint: float | None
    data_schema_version: str
    source_schema_version: str
    resolved_at: datetime

    def __post_init__(self) -> None:
        if self.horizon not in HORIZONS:
            raise ValueError("invalid outcome horizon")
        if self.availability_status == "AVAILABLE":
            values = (self.actual_return_bps, self.cutoff_midpoint, self.target_midpoint)
            if (any(v is None or not math.isfinite(v) for v in values) or
                    self.cutoff_midpoint <= 0 or self.target_midpoint <= 0 or
                    self.unavailable_reason is not None or
                    self.cutoff_midpoint_at is None or self.target_midpoint_at is None):
                raise ValueError("invalid available outcome")
        elif self.availability_status != "UNAVAILABLE" or self.actual_return_bps is not None or not self.unavailable_reason:
            raise ValueError("invalid unavailable outcome")

    def content_payload(self) -> dict[str, object]:
        # resolved_at is audit provenance. Excluding it makes a later exact retry
        # idempotent while preserving the first immutable resolution timestamp.
        payload = asdict(self)
        payload.pop("resolved_at")
        for key in ("cutoff_at", "cutoff_midpoint_at", "target_midpoint_at"):
            if payload[key] is not None:
                payload[key] = _utc(payload[key]).isoformat()
        return payload

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.content_payload()).encode()).hexdigest()

    def payload(self) -> dict[str, object]:
        return asdict(self) | {"content_sha256": self.content_sha256}


def frozen_actual_return_bps(cutoff_midpoint: float, target_midpoint: float) -> float:
    if not all(math.isfinite(v) and v > 0 for v in (cutoff_midpoint, target_midpoint)):
        raise ValueError("midpoints must be positive and finite")
    return 10_000.0 * math.log(target_midpoint / cutoff_midpoint)


def resolve_slots(replay_run_id: str, slots: Iterable[tuple[datetime, str]],
                  quotes: Iterable[HistoricalSipQuote], *, session_open: datetime,
                  session_close: datetime, data_schema_version: str,
                  source_schema_version: str, resolved_at: datetime) -> Iterator[HistoricalOutcome]:
    coin = tuple(q for q in quotes if q.symbol == "COIN")
    times = tuple(q.provider_event_ns for q in coin)
    from bisect import bisect_left, bisect_right
    for cutoff_at, horizon in slots:
        cutoff_at = _utc(cutoff_at)
        cutoff_ns = round(cutoff_at.timestamp() * 1_000_000_000)
        maturity_ns = cutoff_ns + HORIZON_SECONDS[horizon] * 1_000_000_000
        ci = bisect_right(times, cutoff_ns) - 1
        ti = bisect_left(times, maturity_ns)
        reason = None
        cutoff = coin[ci] if ci >= 0 else None
        target = coin[ti] if ti < len(coin) else None
        previous = coin[ti - 1] if ti > 0 else None
        if not (_utc(session_open) <= cutoff_at < _utc(session_close)):
            reason = "CUTOFF_OUTSIDE_SESSION"
        elif maturity_ns >= round(_utc(session_close).timestamp() * 1_000_000_000):
            reason = "TARGET_OUTSIDE_SESSION"
        elif cutoff is None:
            reason = "CUTOFF_MIDPOINT_UNAVAILABLE"
        elif target is None:
            reason = "TARGET_MIDPOINT_UNAVAILABLE"
        elif previous is None or not (previous.provider_event_ns < maturity_ns <= target.provider_event_ns):
            reason = "STRICT_TARGET_BRACKET_UNAVAILABLE"
        common = dict(replay_run_id=replay_run_id, cutoff_at=cutoff_at, horizon=horizon,
                      data_schema_version=data_schema_version,
                      source_schema_version=source_schema_version,
                      resolved_at=_utc(resolved_at))
        if reason:
            yield HistoricalOutcome(actual_return_bps=None, availability_status="UNAVAILABLE",
                unavailable_reason=reason,
                cutoff_midpoint_at=None if cutoff is None else datetime.fromtimestamp(cutoff.event_epoch, timezone.utc),
                cutoff_midpoint=None if cutoff is None else cutoff.midpoint,
                target_midpoint_at=None if target is None else datetime.fromtimestamp(target.event_epoch, timezone.utc),
                target_midpoint=None if target is None else target.midpoint, **common)
        else:
            yield HistoricalOutcome(actual_return_bps=frozen_actual_return_bps(cutoff.midpoint, target.midpoint),
                availability_status="AVAILABLE", unavailable_reason=None,
                cutoff_midpoint_at=datetime.fromtimestamp(cutoff.event_epoch, timezone.utc),
                cutoff_midpoint=cutoff.midpoint,
                target_midpoint_at=datetime.fromtimestamp(target.event_epoch, timezone.utc),
                target_midpoint=target.midpoint, **common)


class HistoricalOutcomeResolver:
    """Verify first, then atomically insert/compare bounded outcome batches."""
    def __init__(self, connection, *, batch_size: int = DEFAULT_BATCH_SIZE):
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        self.connection, self.batch_size = connection, batch_size

    def resolve(self, replay_run_id: str, quotes: Iterable[HistoricalSipQuote], **expected) -> int:
        receipt = HistoricalEvidenceVerifier(self.connection).verify(replay_run_id, **expected)
        if receipt.verification_status != "VERIFIED":
            self.connection.rollback()
            raise RuntimeError("H2C_UNVERIFIED_REPLAY:" + ",".join(receipt.reason_codes))
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(%s,1))", (replay_run_id,))
            cursor.execute("SELECT DISTINCT cutoff_at,horizon FROM public.atom_historical_replay_forecasts WHERE replay_run_id=%s ORDER BY cutoff_at,horizon", (replay_run_id,))
            slots = cursor.fetchall()
            if len(slots) != receipt.frame_count * 6:
                raise RuntimeError("H2C_SLOT_COUNT_MISMATCH")
            cursor.execute("SELECT data_schema_version,source_schema_version,historical_session FROM public.atom_historical_replay_runs WHERE replay_run_id=%s", (replay_run_id,))
            versions = cursor.fetchone()
            from .historical_replay_h1 import _session
            session_open, session_close = _session(versions[2])
            rows = resolve_slots(replay_run_id, slots, quotes,
                session_open=session_open, session_close=session_close,
                data_schema_version=versions[0], source_schema_version=versions[1],
                resolved_at=datetime.now(timezone.utc))
            inserted = 0
            batch = []
            for row in rows:
                batch.append(row)
                if len(batch) == self.batch_size:
                    inserted += self._write(cursor, replay_run_id, batch); batch.clear()
            if batch:
                inserted += self._write(cursor, replay_run_id, batch)
            self.connection.commit()
            return inserted
        except Exception:
            self.connection.rollback(); raise
        finally:
            cursor.close()

    @staticmethod
    def _write(cursor, replay_run_id: str, rows: list[HistoricalOutcome]) -> int:
        values = [r.payload() for r in rows]
        expected = [{"cutoff_at": r.cutoff_at, "horizon": r.horizon,
                     "content_sha256": r.content_sha256} for r in rows]
        cursor.execute("SELECT count(*),count(*) FILTER (WHERE o.content_sha256=x.content_sha256) FROM jsonb_to_recordset(%s::jsonb) x(cutoff_at timestamptz,horizon text,content_sha256 text) LEFT JOIN public.atom_historical_replay_outcomes o ON o.replay_run_id=%s AND o.cutoff_at=x.cutoff_at AND o.horizon=x.horizon", (_canonical(expected), replay_run_id))
        total, identical = cursor.fetchone()
        if identical == total:
            return 0
        cursor.execute("SELECT count(*) FROM jsonb_to_recordset(%s::jsonb) x(cutoff_at timestamptz,horizon text) JOIN public.atom_historical_replay_outcomes o ON o.replay_run_id=%s AND o.cutoff_at=x.cutoff_at AND o.horizon=x.horizon", (_canonical(expected), replay_run_id))
        if cursor.fetchone()[0]:
            raise RuntimeError("H2C_OUTCOME_CONFLICT")
        cursor.execute("INSERT INTO public.atom_historical_replay_outcomes (replay_run_id,cutoff_at,horizon,actual_return_bps,availability_status,unavailable_reason,cutoff_midpoint_at,cutoff_midpoint,target_midpoint_at,target_midpoint,data_schema_version,source_schema_version,content_sha256,resolved_at) SELECT replay_run_id,cutoff_at,horizon,actual_return_bps,availability_status,unavailable_reason,cutoff_midpoint_at,cutoff_midpoint,target_midpoint_at,target_midpoint,data_schema_version,source_schema_version,content_sha256,resolved_at FROM jsonb_to_recordset(%s::jsonb) x(replay_run_id text,cutoff_at timestamptz,horizon text,actual_return_bps float8,availability_status text,unavailable_reason text,cutoff_midpoint_at timestamptz,cutoff_midpoint float8,target_midpoint_at timestamptz,target_midpoint float8,data_schema_version text,source_schema_version text,content_sha256 text,resolved_at timestamptz)", (_canonical(values),))
        return len(rows)

@dataclass(frozen=True, slots=True)
class ScoreMetric:
    quant_id: str
    horizon: str
    eligible_count: int
    resolved_count: int
    directional_wins: int | None
    directional_losses: int | None
    directional_accuracy: float | None
    rmse: float | None
    mae: float | None
    bias: float | None
    coverage: float

@dataclass(frozen=True, slots=True)
class ScoringReceipt:
    replay_run_id: str
    dataset_digest: str
    configuration_digest: str
    forecast_count: int
    outcome_count: int
    metrics: tuple[ScoreMetric, ...]
    content_hash_summary: str
    scorer_version: str = OUTCOME_SCHEMA_VERSION

    def payload(self) -> dict[str, object]:
        return asdict(self)


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def score(connection, replay_run_id: str, *, fetch_size: int = DEFAULT_BATCH_SIZE) -> ScoringReceipt:
    """Stream the immutable join; issue SELECT only and return a stable receipt."""
    cursor = connection.cursor()
    cursor.execute("SELECT dataset_digest,configuration_digest FROM public.atom_historical_replay_runs WHERE replay_run_id=%s", (replay_run_id,))
    manifest = cursor.fetchone()
    if manifest is None:
        raise RuntimeError("H2C_MANIFEST_MISSING")
    cursor.execute("SELECT count(*) FROM public.atom_historical_replay_forecasts WHERE replay_run_id=%s", (replay_run_id,))
    forecast_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM public.atom_historical_replay_outcomes WHERE replay_run_id=%s", (replay_run_id,))
    outcome_count = cursor.fetchone()[0]
    cursor.close()
    stream = connection.cursor(name="atom_h2c_scoring", binary=True)
    stream.itersize = fetch_size
    stream.execute("SELECT f.quant_id,f.horizon,f.expected_return_bps,f.availability_status,o.actual_return_bps,o.availability_status,o.content_sha256 FROM public.atom_historical_replay_forecasts f LEFT JOIN public.atom_historical_replay_outcomes o USING (replay_run_id,cutoff_at,horizon) WHERE f.replay_run_id=%s ORDER BY f.quant_id,f.horizon,f.cutoff_at", (replay_run_id,))
    states = {(q, h): [0, 0, 0, 0, 0.0, 0.0, 0.0] for q in QUANTS for h in HORIZONS}
    digest = hashlib.sha256()
    while True:
        batch = stream.fetchmany(fetch_size)
        if not batch: break
        for q, h, predicted, fs, actual, os_, outcome_hash in batch:
            state = states[(q, h)]
            if fs != "AVAILABLE": continue
            state[0] += 1
            if os_ != "AVAILABLE" or actual is None: continue
            state[1] += 1
            target = abs(actual) if q == Q3 else actual
            error = predicted - target
            state[4] += error * error; state[5] += abs(error); state[6] += error
            if q != Q3:
                if _sign(predicted) == _sign(actual): state[2] += 1
                else: state[3] += 1
            digest.update(f"{q}|{h}|{predicted.hex()}|{actual.hex()}|{outcome_hash}\n".encode())
    stream.close()
    metrics = []
    for q in QUANTS:
        for h in HORIZONS:
            eligible, resolved, wins, losses, squared, absolute, signed = states[(q, h)]
            metrics.append(ScoreMetric(q, h, eligible, resolved,
                None if q == Q3 else wins, None if q == Q3 else losses,
                None if q == Q3 or resolved == 0 else wins / resolved,
                None if resolved == 0 else math.sqrt(squared / resolved),
                None if resolved == 0 else absolute / resolved,
                None if resolved == 0 else signed / resolved,
                0.0 if eligible == 0 else resolved / eligible))
    return ScoringReceipt(replay_run_id, manifest[0], manifest[1], forecast_count,
                          outcome_count, tuple(metrics), digest.hexdigest())


def _connect(environment_variable: str, expected_role: str):
    database_url = os.environ.get(environment_variable)
    if not database_url:
        raise RuntimeError(f"{environment_variable} is required")
    import psycopg
    connection = psycopg.connect(database_url)
    cursor = connection.cursor()
    cursor.execute("SELECT current_user")
    role = cursor.fetchone()[0]
    cursor.close()
    if role != expected_role:
        connection.close()
        raise RuntimeError(f"H2C_DATABASE_ROLE_MISMATCH:{expected_role}")
    connection.commit()
    return connection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve-outcomes", help="explicit H2-C write command")
    resolve.add_argument("replay_run_id"); resolve.add_argument("--dataset-digest", required=True)
    resolve.add_argument("--configuration-digest", required=True); resolve.add_argument("--frame-count", type=int, required=True)
    scoring = commands.add_parser("score", help="read-only immutable scoring")
    scoring.add_argument("replay_run_id")
    args = parser.parse_args(); started = time.monotonic()
    environment_variable, expected_role = (
        ("HISTORICAL_SCORE_DATABASE_URL", "atom_historical_score_reader")
        if args.command == "score" else
        ("HISTORICAL_OUTCOME_DATABASE_URL", "atom_historical_outcome_resolver")
    )
    with _connect(environment_variable, expected_role) as connection:
        if args.command == "score":
            connection.read_only = True
            output = score(connection, args.replay_run_id).payload()
        else:
            # Re-fetch the same frozen SIP session identified by the verified manifest.
            c = connection.cursor(); c.execute("SELECT historical_session FROM public.atom_historical_replay_runs WHERE replay_run_id=%s", (args.replay_run_id,)); session = c.fetchone(); c.close()
            if session is None: raise RuntimeError("H2C_MANIFEST_MISSING")
            from .historical_replay_h1 import _session
            session_open, session_close = _session(session[0])
            quotes = AlpacaHistoricalSipReader.from_environment().read_session(session_open=session_open, session_close=session_close)
            inserted = HistoricalOutcomeResolver(connection).resolve(args.replay_run_id, quotes,
                expected_dataset_digest=args.dataset_digest,
                expected_configuration_digest=args.configuration_digest,
                expected_frame_count=args.frame_count)
            output = {"replay_run_id": args.replay_run_id, "inserted": inserted}
    output |= {"elapsed_seconds": round(time.monotonic()-started, 6),
               "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    print(_canonical(output)); return 0

if __name__ == "__main__":
    raise SystemExit(main())
