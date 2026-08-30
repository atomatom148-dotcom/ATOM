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
from .historical_replay import (
    AlpacaHistoricalSipReader, DATA_SCHEMA_VERSION, SYMBOLS, HistoricalSipQuote,
    HistoricalSipRetrievalProof, OneSessionReplayClock,
)
from .v9_v1_contract import HORIZON_SECONDS

OUTCOME_SCHEMA_VERSION = "H2-C-1"
RESOLUTION_SPEC_VERSION = "COIN_MIDPOINT_LOG_RETURN_BPS_1"
DEFAULT_BATCH_SIZE = 2_000
SCORING_STATEMENT_TIMEOUT = "30min"
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
    resolution_spec_version: str
    outcome_source_dataset_digest: str
    resolved_at: datetime

    def __post_init__(self) -> None:
        if self.horizon not in HORIZONS:
            raise ValueError("invalid outcome horizon")
        if self.resolution_spec_version != RESOLUTION_SPEC_VERSION:
            raise ValueError("invalid resolution spec version")
        if (not isinstance(self.outcome_source_dataset_digest, str) or
                len(self.outcome_source_dataset_digest) != 64 or
                any(character not in "0123456789abcdef"
                    for character in self.outcome_source_dataset_digest)):
            raise ValueError("invalid outcome source dataset digest")
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


def _frame_cutoff_at(provider_event_ns: int) -> datetime:
    # This is the exact conversion frozen H1 used when persisting its frame.
    return datetime.fromtimestamp(provider_event_ns / 1_000_000_000, timezone.utc)


def _accepted_coin_quotes(quotes: tuple[HistoricalSipQuote, ...], *,
                          session_open: datetime,
                          session_close: datetime) -> tuple[HistoricalSipQuote, ...]:
    coin_by_ns = {row.provider_event_ns: row for row in quotes if row.symbol == "COIN"}
    accepted = [coin_by_ns[frame.coin_source_as_of_ns] for frame in
                OneSessionReplayClock(quotes, session_open=session_open,
                                      session_close=session_close).frames()]
    coin = tuple(row for row in quotes if row.symbol == "COIN")
    close_ns = round(_utc(session_close).timestamp() * 1_000_000_000)
    # Preserve H1's outcome-only 16:00 close drain of the last fractional-second quote.
    if (coin and (not accepted or coin[-1].provider_event_ns >
                  accepted[-1].provider_event_ns) and
            coin[-1].provider_event_ns < close_ns):
        accepted.append(coin[-1])
    return tuple(accepted)


def resolve_slots(replay_run_id: str, slots: Iterable[tuple[datetime, str]],
                  quotes: Iterable[HistoricalSipQuote], *, session_open: datetime,
                  session_close: datetime, data_schema_version: str,
                  source_schema_version: str, outcome_source_dataset_digest: str,
                  resolved_at: datetime) -> Iterator[HistoricalOutcome]:
    materialized = tuple(quotes)
    accepted = _accepted_coin_quotes(materialized, session_open=session_open,
                                     session_close=session_close)
    # The drain quote is never a forecast frame. Determine frames independently.
    frame_ns = tuple(frame.coin_source_as_of_ns for frame in OneSessionReplayClock(
        materialized, session_open=session_open, session_close=session_close).frames())
    by_cutoff: dict[datetime, HistoricalSipQuote] = {}
    coin_by_ns = {row.provider_event_ns: row for row in materialized if row.symbol == "COIN"}
    for ns in frame_ns:
        key = _frame_cutoff_at(ns)
        if key in by_cutoff:
            raise RuntimeError("H2C_AMBIGUOUS_CUTOFF_MAPPING")
        by_cutoff[key] = coin_by_ns[ns]
    accepted_times = tuple(row.provider_event_ns for row in accepted)
    from bisect import bisect_left
    close_ns = round(_utc(session_close).timestamp() * 1_000_000_000)
    for cutoff_at, horizon in slots:
        cutoff_at = _utc(cutoff_at)
        cutoff = by_cutoff.get(cutoff_at)
        if cutoff is None:
            raise RuntimeError("H2C_EXACT_CUTOFF_MAPPING_MISSING")
        maturity_ns = cutoff.provider_event_ns + HORIZON_SECONDS[horizon] * 1_000_000_000
        ti = bisect_left(accepted_times, maturity_ns)
        target = accepted[ti] if ti < len(accepted) else None
        previous = accepted[ti - 1] if ti > 0 else None
        reason = None
        if maturity_ns >= close_ns:
            reason = "TARGET_OUTSIDE_SESSION"
        elif target is None:
            reason = "TARGET_MIDPOINT_UNAVAILABLE"
        elif previous is None or not (previous.provider_event_ns < maturity_ns <= target.provider_event_ns):
            reason = "STRICT_TARGET_BRACKET_UNAVAILABLE"
        common = dict(replay_run_id=replay_run_id, cutoff_at=cutoff_at, horizon=horizon,
                      data_schema_version=data_schema_version,
                      source_schema_version=source_schema_version,
                      resolution_spec_version=RESOLUTION_SPEC_VERSION,
                      outcome_source_dataset_digest=outcome_source_dataset_digest,
                      resolved_at=_utc(resolved_at))
        if reason:
            yield HistoricalOutcome(actual_return_bps=None, availability_status="UNAVAILABLE",
                unavailable_reason=reason,
                cutoff_midpoint_at=_frame_cutoff_at(cutoff.provider_event_ns),
                cutoff_midpoint=cutoff.midpoint,
                target_midpoint_at=None if target is None else _frame_cutoff_at(target.provider_event_ns),
                target_midpoint=None if target is None else target.midpoint, **common)
        else:
            yield HistoricalOutcome(actual_return_bps=frozen_actual_return_bps(cutoff.midpoint, target.midpoint),
                availability_status="AVAILABLE", unavailable_reason=None,
                cutoff_midpoint_at=_frame_cutoff_at(cutoff.provider_event_ns),
                cutoff_midpoint=cutoff.midpoint,
                target_midpoint_at=_frame_cutoff_at(target.provider_event_ns),
                target_midpoint=target.midpoint, **common)


class HistoricalOutcomeResolver:
    """Verify first, then atomically insert/compare bounded outcome batches."""
    def __init__(self, connection, *, batch_size: int = DEFAULT_BATCH_SIZE):
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        self.connection, self.batch_size = connection, batch_size

    def resolve(self, replay_run_id: str, quotes: Iterable[HistoricalSipQuote], *,
                retrieval_proof: HistoricalSipRetrievalProof | None = None,
                **expected) -> int:
        # Materialize and authenticate the re-fetch before acquiring the advisory
        # lock or attempting any outcome write.
        materialized = tuple(quotes)
        receipt = HistoricalEvidenceVerifier(self.connection).verify(replay_run_id, **expected)
        if receipt.verification_status != "VERIFIED":
            self.connection.rollback()
            raise RuntimeError("H2C_UNVERIFIED_REPLAY:" + ",".join(receipt.reason_codes))
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT historical_session,dataset_digest,quote_counts,data_schema_version,source_schema_version FROM public.atom_historical_replay_runs WHERE replay_run_id=%s", (replay_run_id,))
            manifest = cursor.fetchone()
            if manifest is None:
                raise RuntimeError("H2C_MANIFEST_MISSING")
            historical_session, dataset_digest, quote_counts, data_version, source_version = manifest
            from .historical_replay_h1 import (_retrieval_proof_valid, _session,
                                                canonical_sha256)
            session_open, session_close = _session(historical_session)
            open_ns = round(session_open.timestamp() * 1_000_000_000)
            close_ns = round(session_close.timestamp() * 1_000_000_000)
            if not _retrieval_proof_valid(retrieval_proof, open_ns=open_ns,
                                          close_ns=close_ns,
                                          retained_count=len(materialized)):
                raise RuntimeError("H2C_RETRIEVAL_PROOF_INVALID")
            # Clock construction validates ordering, session bounds, symbols, and
            # every quote's frozen schema lineage.
            frame_count = sum(1 for _ in OneSessionReplayClock(
                materialized, session_open=session_open,
                session_close=session_close).frames())
            actual_counts = {symbol: sum(row.symbol == symbol for row in materialized)
                             for symbol in SYMBOLS}
            if actual_counts != dict(quote_counts):
                raise RuntimeError("H2C_QUOTE_COUNT_MISMATCH")
            actual_digest = canonical_sha256(tuple(
                (row.symbol, row.provider_event_ns, row.bid, row.ask,
                 row.bid_size, row.ask_size, row.source,
                 row.data_schema_version, row.source_spec_version)
                for row in materialized))
            if actual_digest != dataset_digest or actual_digest != receipt.dataset_digest:
                raise RuntimeError("H2C_DATASET_DIGEST_MISMATCH")
            if (frame_count != receipt.frame_count or data_version != DATA_SCHEMA_VERSION or
                    any(row.data_schema_version != data_version or
                        row.source_spec_version != source_version
                        for row in materialized)):
                raise RuntimeError("H2C_LINEAGE_MISMATCH")

            cursor.execute("SELECT pg_catalog.pg_advisory_xact_lock(hashtextextended(%s,1))", (replay_run_id,))
            cursor.execute("SELECT DISTINCT cutoff_at,horizon FROM public.atom_historical_replay_forecasts WHERE replay_run_id=%s ORDER BY cutoff_at,horizon", (replay_run_id,))
            slots = cursor.fetchall()
            if len(slots) != receipt.frame_count * 6:
                raise RuntimeError("H2C_SLOT_COUNT_MISMATCH")
            rows = resolve_slots(replay_run_id, slots, materialized,
                session_open=session_open, session_close=session_close,
                data_schema_version=data_version, source_schema_version=source_version,
                outcome_source_dataset_digest=dataset_digest,
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
        cursor.execute("INSERT INTO public.atom_historical_replay_outcomes (replay_run_id,cutoff_at,horizon,actual_return_bps,availability_status,unavailable_reason,cutoff_midpoint_at,cutoff_midpoint,target_midpoint_at,target_midpoint,data_schema_version,source_schema_version,resolution_spec_version,outcome_source_dataset_digest,content_sha256,resolved_at) SELECT replay_run_id,cutoff_at,horizon,actual_return_bps,availability_status,unavailable_reason,cutoff_midpoint_at,cutoff_midpoint,target_midpoint_at,target_midpoint,data_schema_version,source_schema_version,resolution_spec_version,outcome_source_dataset_digest,content_sha256,resolved_at FROM jsonb_to_recordset(%s::jsonb) x(replay_run_id text,cutoff_at timestamptz,horizon text,actual_return_bps float8,availability_status text,unavailable_reason text,cutoff_midpoint_at timestamptz,cutoff_midpoint float8,target_midpoint_at timestamptz,target_midpoint float8,data_schema_version text,source_schema_version text,resolution_spec_version text,outcome_source_dataset_digest text,content_sha256 text,resolved_at timestamptz)", (_canonical(values),))
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


@dataclass(frozen=True, slots=True)
class OutcomeVerificationReceipt:
    replay_run_id: str
    outcome_count: int
    outcome_available_count: int
    outcome_unavailable_count: int
    outcome_ordered_content_sha256: str

    def payload(self) -> dict[str, object]:
        return asdict(self)


OUTCOME_VERIFICATION_COLUMNS = (
    "replay_run_id", "cutoff_at", "horizon", "actual_return_bps",
    "availability_status", "unavailable_reason", "cutoff_midpoint_at",
    "cutoff_midpoint", "target_midpoint_at", "target_midpoint",
    "data_schema_version", "source_schema_version", "resolution_spec_version",
    "outcome_source_dataset_digest", "resolved_at", "content_sha256",
)


def verify_outcomes(connection, replay_run_id: str, *,
                    fetch_size: int = DEFAULT_BATCH_SIZE) -> OutcomeVerificationReceipt:
    """Rehash immutable outcomes and return their frozen read-only receipt."""
    if not replay_run_id or len(replay_run_id) > 128:
        raise ValueError("replay_run_id must contain 1..128 characters")
    if isinstance(fetch_size, bool) or not isinstance(fetch_size, int) or fetch_size < 1:
        raise ValueError("fetch_size must be a positive integer")
    setup = connection.cursor()
    setup.execute(f"SET LOCAL statement_timeout = '{SCORING_STATEMENT_TIMEOUT}'")
    setup.close()
    cursor = connection.cursor(name="atom_h2c_outcomes")
    cursor.itersize = fetch_size
    cursor.execute(
        "SELECT " + ",".join(OUTCOME_VERIFICATION_COLUMNS) + " "
        "FROM public.atom_historical_replay_outcomes "
        "WHERE replay_run_id=%s "
        "ORDER BY cutoff_at ASC,convert_to(horizon,'UTF8') ASC",
        (replay_run_id,),
    )
    digest = hashlib.sha256()
    total = available = unavailable = 0
    try:
        while True:
            batch = cursor.fetchmany(fetch_size)
            if not batch:
                break
            for row in batch:
                values = dict(zip(OUTCOME_VERIFICATION_COLUMNS, row, strict=True))
                stored_hash = values.pop("content_sha256")
                if (not isinstance(stored_hash, str) or len(stored_hash) != 64 or
                        any(character not in "0123456789abcdef" for character in stored_hash)):
                    raise RuntimeError("H2C_INVALID_OUTCOME_HASH")
                try:
                    outcome = HistoricalOutcome(**values)
                except (TypeError, ValueError) as error:
                    raise RuntimeError("H2C_INVALID_OUTCOME_PAYLOAD") from error
                if outcome.replay_run_id != replay_run_id:
                    raise RuntimeError("H2C_OUTCOME_REPLAY_ID_MISMATCH")
                if outcome.content_sha256 != stored_hash:
                    raise RuntimeError("H2C_OUTCOME_HASH_MISMATCH")
                if total:
                    digest.update(b"\n")
                digest.update(stored_hash.encode("ascii"))
                total += 1
                available += outcome.availability_status == "AVAILABLE"
                unavailable += outcome.availability_status == "UNAVAILABLE"
    finally:
        cursor.close()
    return OutcomeVerificationReceipt(
        replay_run_id, total, available, unavailable, digest.hexdigest(),
    )


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def score(connection, replay_run_id: str, *, fetch_size: int = DEFAULT_BATCH_SIZE) -> ScoringReceipt:
    """Page through the immutable join read-only and return a stable receipt."""
    if fetch_size <= 0:
        raise ValueError("fetch_size must be positive")
    cursor = connection.cursor()
    # Scoring is the sole long-running read on this role. Override any shorter
    # role/connection default for this transaction only; retain a finite bound.
    cursor.execute(f"SET LOCAL statement_timeout = '{SCORING_STATEMENT_TIMEOUT}'")
    cursor.execute("SELECT dataset_digest,configuration_digest FROM public.atom_historical_replay_runs WHERE replay_run_id=%s", (replay_run_id,))
    manifest = cursor.fetchone()
    if manifest is None:
        raise RuntimeError("H2C_MANIFEST_MISSING")
    cursor.execute("SELECT count(*) FROM public.atom_historical_replay_forecasts WHERE replay_run_id=%s", (replay_run_id,))
    forecast_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM public.atom_historical_replay_outcomes WHERE replay_run_id=%s", (replay_run_id,))
    outcome_count = cursor.fetchone()[0]
    cursor.close()
    states = {(q, h): [0, 0, 0, 0, 0.0, 0.0, 0.0] for q in QUANTS for h in HORIZONS}
    digest = hashlib.sha256()
    # Preserve the former ORDER BY quant_id,horizon,cutoff_at byte order while
    # making each bounded query follow the forecast primary key
    # (replay_run_id,cutoff_at,quant_id,horizon).  A separate cutoff stream for
    # each identity keeps every metric's floating-point addition order and the
    # receipt digest exactly unchanged; it also lets LIMIT stop the index scan.
    for quant_id, horizon in sorted(states):
        page_after = None
        while True:
            stream = connection.cursor(binary=True)
            keyset = ("" if page_after is None else
                      " AND (f.cutoff_at,f.quant_id,f.horizon)>(%s,%s,%s)")
            params = ((replay_run_id, quant_id, horizon, fetch_size)
                      if page_after is None else
                      (replay_run_id, quant_id, horizon, page_after,
                       quant_id, horizon, fetch_size))
            stream.execute("SELECT f.quant_id,f.horizon,f.expected_return_bps,f.availability_status,o.actual_return_bps,o.availability_status,o.content_sha256,o.resolution_spec_version,o.outcome_source_dataset_digest,f.cutoff_at FROM public.atom_historical_replay_forecasts f LEFT JOIN public.atom_historical_replay_outcomes o USING (replay_run_id,cutoff_at,horizon) WHERE f.replay_run_id=%s AND f.quant_id=%s AND f.horizon=%s" + keyset + " ORDER BY f.cutoff_at,f.quant_id,f.horizon LIMIT %s", params)
            batch = stream.fetchmany(fetch_size)
            stream.close()
            if not batch: break
            for q, h, predicted, fs, actual, os_, outcome_hash, resolution_version, source_digest, cutoff_at in batch:
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
                digest.update(f"{q}|{h}|{predicted.hex()}|{actual.hex()}|{outcome_hash}|{resolution_version}|{source_digest}\n".encode())
            page_after = batch[-1][9]
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
    connection.read_only = expected_role == "atom_historical_score_reader"
    cursor = connection.cursor()
    cursor.execute("SELECT current_user")
    role = cursor.fetchone()[0]
    cursor.close()
    if role != expected_role:
        connection.close()
        raise RuntimeError(f"H2C_DATABASE_ROLE_MISMATCH:{expected_role}")
    connection.commit()
    return connection


def verify_outcomes_from_environment(replay_run_id: str) -> OutcomeVerificationReceipt:
    with _connect("HISTORICAL_SCORE_DATABASE_URL",
                  "atom_historical_score_reader") as connection:
        connection.read_only = True
        return verify_outcomes(connection, replay_run_id)


def score_from_environment(replay_run_id: str) -> ScoringReceipt:
    with _connect("HISTORICAL_SCORE_DATABASE_URL",
                  "atom_historical_score_reader") as connection:
        connection.read_only = True
        return score(connection, replay_run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve-outcomes", help="explicit H2-C write command")
    resolve.add_argument("replay_run_id"); resolve.add_argument("--dataset-digest", required=True)
    resolve.add_argument("--configuration-digest", required=True); resolve.add_argument("--frame-count", type=int, required=True)
    verify = commands.add_parser("verify-outcomes", help="read-only immutable outcome receipt")
    verify.add_argument("replay_run_id")
    scoring = commands.add_parser("score", help="read-only immutable scoring")
    scoring.add_argument("replay_run_id")
    args = parser.parse_args(); started = time.monotonic()
    environment_variable, expected_role = (
        ("HISTORICAL_SCORE_DATABASE_URL", "atom_historical_score_reader")
        if args.command in {"score", "verify-outcomes"} else
        ("HISTORICAL_OUTCOME_DATABASE_URL", "atom_historical_outcome_resolver")
    )
    with _connect(environment_variable, expected_role) as connection:
        if args.command == "score":
            connection.read_only = True
            output = score(connection, args.replay_run_id).payload()
        elif args.command == "verify-outcomes":
            connection.read_only = True
            output = verify_outcomes(connection, args.replay_run_id).payload()
        else:
            # Re-fetch the same frozen SIP session identified by the verified manifest.
            c = connection.cursor(); c.execute("SELECT historical_session FROM public.atom_historical_replay_runs WHERE replay_run_id=%s", (args.replay_run_id,)); session = c.fetchone(); c.close()
            if session is None: raise RuntimeError("H2C_MANIFEST_MISSING")
            from .historical_replay_h1 import _session
            session_open, session_close = _session(session[0])
            reader = AlpacaHistoricalSipReader.from_environment()
            quotes = reader.read_session(session_open=session_open, session_close=session_close)
            inserted = HistoricalOutcomeResolver(connection).resolve(args.replay_run_id, quotes,
                retrieval_proof=reader.last_retrieval_proof,
                expected_dataset_digest=args.dataset_digest,
                expected_configuration_digest=args.configuration_digest,
                expected_frame_count=args.frame_count)
            output = {"replay_run_id": args.replay_run_id, "inserted": inserted}
    output |= {"elapsed_seconds": round(time.monotonic()-started, 6),
               "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    print(_canonical(output)); return 0

if __name__ == "__main__":
    raise SystemExit(main())
