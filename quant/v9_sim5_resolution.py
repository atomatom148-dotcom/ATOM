"""Exact immutable SIM-5 terminal-resolution contracts and persistence.

Authority: docs/sim-4a-exact-sim5-resolution-freeze.md
(Decision ID ATOM-SIM-4A-EXACT-SIM5-RESOLUTION-FREEZE-1).

SIM-5 closes only the positions successfully opened by SIM-4.  It adds one
immutable terminal resolution for each durable SIM-4 entry whose
``entry_status`` is exactly ``ENTERED``, then releases that horizon for
later SIM-4 entries only after the terminal resolution is durable.

This module is intentionally free of environment, clock, network, and
connection-opening behavior, matching quant/v9_sim4_entry.py.  The dedicated
worker supplies its already-open authoritative PostgreSQL session and owns
every transaction boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
from typing import Iterable, Mapping

from quant.v9_sim1_contract import HORIZON_SECONDS
from quant.v9_sim4_entry import (
    ENTRY_ID_PREFIX,
    QUOTE_ID_PREFIX,
    SIM_ENTRY_RUNTIME_ROLE,
    SimulationEntryRecord,
    SimulationExecutableQuote,
    datetime_to_epoch_microseconds,
    datetime_to_epoch_nanoseconds,
    horizon_advisory_lock_key,
)
from quant.v9_v4a_evidence import _canonical, _decanonical, canonical_sha256


SIM_RESOLUTION_CONTRACT_VERSION = "ATOM_TRUE_V9_SIM5_RESOLUTION_1"
SIM_RESOLUTION_SCHEMA_VERSION = "ATOM_TRUE_V9_SIM5_SCHEMA_1"
SIM_RESOLUTION_STORE_VERSION = "ATOM_TRUE_V9_SIM5_STORE_1"
SIM_RESOLUTION_RUNTIME_VERSION = "ATOM_TRUE_V9_SIM5_RUNTIME_1"
SIM_CANONICALIZATION_VERSION = "ATOM_TRUE_V9_SIM_CANONICAL_V4A_1"
SIMULATOR_VERSION = "ATOM_TRUE_V9_SIM_1"
SIMULATION_MODE = "PAPER_ONLY"
RESOLUTION_ID_PREFIX = "v9simresolution:"
SIM_RESOLUTION_TABLE = "public.atom_v9_sim_resolutions"
SIM5_ENABLED_ENV = "ATOM_V9_SIM5_ENABLED"
SYMBOL = "COIN"
INSTRUMENT = "COIN_SHARE"
RESOLUTION_WINDOW_SECONDS = 2

INSERTED = "INSERTED"
IDEMPOTENT = "IDEMPOTENT"

RESOLUTION_STATUSES = frozenset((
    "RESOLVED",
    "UNRESOLVED_WINDOW_EXPIRED",
    "UNRESOLVED_OBSERVATION_GAP",
))

_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_RESOLUTION_ID_RE = re.compile(r"v9simresolution:[0-9a-f]{64}\Z")
_ENTRY_ID_RE = re.compile(r"v9simentry:[0-9a-f]{64}\Z")
_QUOTE_ID_RE = re.compile(r"v9simquote:[0-9a-f]{64}\Z")


class SimulationResolutionError(RuntimeError):
    reason = "SIM5_ERROR"


class SimulationResolutionConflictError(SimulationResolutionError):
    reason = "SIM5_RESOLUTION_CONFLICT"


class SimulationResolutionRowInvalidError(SimulationResolutionError):
    reason = "SIM5_ROW_INVALID"


class SimulationResolutionRoleError(SimulationResolutionError):
    reason = "SIM5_ROLE_MISMATCH"


class SimulationResolutionStateError(SimulationResolutionError):
    reason = "SIM5_STATE_INVALID"


def _aware_datetime(name: str, value: object) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None or
            value.utcoffset() is None):
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def _utc_datetime(name: str, value: object) -> datetime:
    result = _aware_datetime(name, value)
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be UTC")
    return result.astimezone(timezone.utc)


def _integer(name: str, value: object, *, minimum: int = 0,
             maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside its allowed range")
    return value


def _finite_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite binary64 value")
    return value


def sim5_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether SIM-5 is enabled via the exact lowercase-only gate.

    Only the literal string ``"true"`` enables SIM-5.  Missing or any other
    value disables SIM-5 without disabling SIM-4 (freeze section 9).
    """
    source = os.environ if environ is None else environ
    return source.get(SIM5_ENABLED_ENV) == "true"


@dataclass(frozen=True, slots=True)
class SimulationResolutionRecord:
    contract_version: str
    canonicalization_version: str
    simulator_version: str
    resolution_id: str
    resolution_hash: str
    mode: str
    symbol: str
    instrument: str
    entry_id: str
    entry_hash: str
    source_cycle_id: str
    cutoff_at: datetime
    horizon: str
    horizon_seconds: int
    decision: str
    entry_quote_id: str
    entry_quote_hash: str
    entry_price: float
    resolution_target_at: datetime
    resolution_deadline_at: datetime
    resolution_status: str
    exit_quote: SimulationExecutableQuote | None
    exit_price: float | None
    return_bps: float | None

    def __post_init__(self) -> None:
        _validate_resolution(self)


_RESOLUTION_FIELD_NAMES = tuple(field.name for field in fields(SimulationResolutionRecord))
_RESOLUTION_HASH_FIELDS = tuple(name for name in _RESOLUTION_FIELD_NAMES
                                if name not in ("resolution_id", "resolution_hash"))
_QUOTE_FIELD_NAMES = tuple(field.name for field in fields(SimulationExecutableQuote))


def _resolution_math_payload(resolution: SimulationResolutionRecord) -> dict[str, object]:
    values = asdict(resolution)
    return {name: values[name] for name in _RESOLUTION_HASH_FIELDS}


def _quote_is_valid_exit(decision: str, target_at: datetime, deadline_at: datetime,
        entry_quote: SimulationExecutableQuote | None,
        candidate: SimulationExecutableQuote) -> bool:
    """Test one candidate quote against the closed observation window.

    Both window bounds are inclusive (freeze section 3).  When ``entry_quote``
    is supplied, the candidate must also be strictly causal to it: this is
    the cross-check against the actual SIM-4 entry quote, performed by
    ``validate_resolution_matches_entry`` and ``select_exit_quote``.  Passing
    ``entry_quote=None`` skips only that cross-record causal step, for the
    self-contained checks in ``_validate_resolution`` that have no access to
    the entry's own quote.
    """
    if not isinstance(candidate, SimulationExecutableQuote):
        return False
    target_ns = datetime_to_epoch_nanoseconds(target_at)
    deadline_ns = datetime_to_epoch_nanoseconds(deadline_at)
    accepted_ns = datetime_to_epoch_nanoseconds(candidate.accepted_at)
    if not (target_ns <= candidate.provider_event_ns <= deadline_ns):
        return False
    if not (target_ns <= accepted_ns <= deadline_ns):
        return False
    if candidate.provider_event_ns > accepted_ns:
        return False
    if entry_quote is not None:
        entry_accepted_ns = datetime_to_epoch_nanoseconds(entry_quote.accepted_at)
        if candidate.provider_event_ns <= entry_quote.provider_event_ns:
            return False
        if accepted_ns <= entry_accepted_ns:
            return False
    if decision == "LONG":
        return candidate.bid_size >= 1.0
    if decision == "SHORT":
        return candidate.ask_size >= 1.0
    return False


def select_exit_quote(*, decision: str, resolution_target_at: datetime,
        resolution_deadline_at: datetime,
        entry_quote: SimulationExecutableQuote,
        quotes: Iterable[SimulationExecutableQuote]
        ) -> SimulationExecutableQuote | None:
    """Select the complete frozen first-quote tuple for one entry's exit.

    Ordering matches the existing SIM-4 selection exactly:
    ``(accepted_at, provider_event_ns, quote_id)`` (freeze section 3).
    """
    if decision not in ("LONG", "SHORT"):
        raise ValueError("decision must be LONG or SHORT")
    if not isinstance(entry_quote, SimulationExecutableQuote):
        raise ValueError("entry_quote must be a SimulationExecutableQuote")
    target = _utc_datetime("resolution_target_at", resolution_target_at)
    deadline = _utc_datetime("resolution_deadline_at", resolution_deadline_at)
    eligible = [quote for quote in quotes
                if isinstance(quote, SimulationExecutableQuote)
                and _quote_is_valid_exit(decision, target, deadline, entry_quote, quote)]
    if not eligible:
        return None
    return min(eligible, key=lambda quote: (
        datetime_to_epoch_microseconds(quote.accepted_at),
        quote.provider_event_ns,
        quote.quote_id,
    ))


def _return_bps(decision: str, entry_price: float, exit_price: float) -> float:
    if decision == "LONG":
        value = 1.0e4 * math.log(exit_price / entry_price)
    elif decision == "SHORT":
        value = 1.0e4 * math.log(entry_price / exit_price)
    else:
        raise ValueError("decision must be LONG or SHORT")
    if not math.isfinite(value):
        raise ValueError("return_bps must be finite")
    return value


def _validate_resolution(resolution: SimulationResolutionRecord) -> None:
    exact = {
        "contract_version": SIM_RESOLUTION_CONTRACT_VERSION,
        "canonicalization_version": SIM_CANONICALIZATION_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "mode": SIMULATION_MODE,
        "symbol": SYMBOL,
        "instrument": INSTRUMENT,
    }
    for name, expected in exact.items():
        if getattr(resolution, name) != expected:
            raise ValueError(f"invalid {name}")

    if not isinstance(resolution.resolution_hash, str) or _HASH_RE.fullmatch(resolution.resolution_hash) is None:
        raise ValueError("invalid resolution_hash")
    if (not isinstance(resolution.resolution_id, str) or
            _RESOLUTION_ID_RE.fullmatch(resolution.resolution_id) is None):
        raise ValueError("invalid resolution_id")

    if not isinstance(resolution.entry_hash, str) or _HASH_RE.fullmatch(resolution.entry_hash) is None:
        raise ValueError("invalid entry_hash")
    if not isinstance(resolution.entry_id, str) or _ENTRY_ID_RE.fullmatch(resolution.entry_id) is None:
        raise ValueError("invalid entry_id")
    if resolution.entry_id != ENTRY_ID_PREFIX + resolution.entry_hash:
        raise ValueError("entry identity pair is invalid")

    if not isinstance(resolution.source_cycle_id, str) or not resolution.source_cycle_id:
        raise ValueError("source_cycle_id must be a nonempty string")

    cutoff = _aware_datetime("cutoff_at", resolution.cutoff_at)

    if resolution.horizon not in HORIZON_SECONDS:
        raise ValueError("invalid horizon")
    if (isinstance(resolution.horizon_seconds, bool) or
            not isinstance(resolution.horizon_seconds, int) or
            resolution.horizon_seconds != HORIZON_SECONDS[resolution.horizon]):
        raise ValueError("invalid horizon_seconds")
    if resolution.decision not in ("LONG", "SHORT"):
        raise ValueError("invalid decision")

    if not isinstance(resolution.entry_quote_hash, str) or _HASH_RE.fullmatch(resolution.entry_quote_hash) is None:
        raise ValueError("invalid entry_quote_hash")
    if (not isinstance(resolution.entry_quote_id, str) or
            _QUOTE_ID_RE.fullmatch(resolution.entry_quote_id) is None):
        raise ValueError("invalid entry_quote_id")
    if resolution.entry_quote_id != QUOTE_ID_PREFIX + resolution.entry_quote_hash:
        raise ValueError("entry quote identity pair is invalid")

    entry_price = _finite_float("entry_price", resolution.entry_price)
    if entry_price <= 0.0:
        raise ValueError("entry_price must be positive")

    target = _utc_datetime("resolution_target_at", resolution.resolution_target_at)
    deadline = _utc_datetime("resolution_deadline_at", resolution.resolution_deadline_at)
    expected_target = cutoff.astimezone(timezone.utc) + timedelta(seconds=resolution.horizon_seconds)
    if target != expected_target:
        raise ValueError("resolution_target_at must equal cutoff_at plus horizon_seconds")
    if deadline != target + timedelta(seconds=RESOLUTION_WINDOW_SECONDS):
        raise ValueError("resolution_deadline_at must be exactly two seconds after target")

    if resolution.resolution_status not in RESOLUTION_STATUSES:
        raise ValueError("invalid resolution_status")

    if resolution.resolution_status == "RESOLVED":
        if (not isinstance(resolution.exit_quote, SimulationExecutableQuote) or
                resolution.exit_price is None or resolution.return_bps is None):
            raise ValueError("RESOLVED resolution requires exit_quote, exit_price, and return_bps")
        exit_price = _finite_float("exit_price", resolution.exit_price)
        if exit_price <= 0.0:
            raise ValueError("exit_price must be positive")
        if not _quote_is_valid_exit(resolution.decision, target, deadline, None, resolution.exit_quote):
            raise ValueError("RESOLVED exit_quote is not a valid exit inside the observation window")
        expected_exit_price = (resolution.exit_quote.bid if resolution.decision == "LONG"
                                else resolution.exit_quote.ask)
        if exit_price != expected_exit_price:
            raise ValueError("exit_price does not match executable quote side")
        return_bps = _finite_float("return_bps", resolution.return_bps)
        expected_return = _return_bps(resolution.decision, entry_price, exit_price)
        if return_bps != expected_return:
            raise ValueError("return_bps does not match entry/exit prices")
    else:
        if (resolution.exit_quote is not None or resolution.exit_price is not None or
                resolution.return_bps is not None):
            raise ValueError("unresolved resolution contains forbidden executable fields")

    digest = canonical_sha256(_resolution_math_payload(resolution))
    if resolution.resolution_hash != digest or resolution.resolution_id != RESOLUTION_ID_PREFIX + digest:
        raise ValueError("resolution mathematical identity mismatch")


def validate_resolution_matches_entry(resolution: SimulationResolutionRecord,
        entry: SimulationEntryRecord) -> None:
    """Prove every resolution field copied from its immutable SIM-4 entry.

    For a ``RESOLVED`` resolution this also proves the strict causal floor
    against the entry's actual executable quote (freeze section 3): the exit
    quote's provider-event time and accepted_at must be strictly greater
    than the entry quote's.
    """
    if not isinstance(resolution, SimulationResolutionRecord):
        raise ValueError("resolution must be a SimulationResolutionRecord")
    if not isinstance(entry, SimulationEntryRecord):
        raise ValueError("entry must be a SimulationEntryRecord")
    if entry.entry_status != "ENTERED":
        raise ValueError("only an ENTERED entry may be resolved")
    if entry.quote is None or entry.entry_price is None:
        raise ValueError("ENTERED entry is missing its executable quote or price")

    expected = {
        "entry_id": entry.entry_id,
        "entry_hash": entry.entry_hash,
        "source_cycle_id": entry.source_cycle_id,
        "cutoff_at": entry.cutoff_at,
        "horizon": entry.horizon,
        "horizon_seconds": entry.horizon_seconds,
        "decision": entry.decision,
        "entry_quote_id": entry.quote.quote_id,
        "entry_quote_hash": entry.quote.quote_hash,
        "entry_price": entry.entry_price,
    }
    for name, value in expected.items():
        if getattr(resolution, name) != value:
            raise ValueError(f"resolution {name} does not match immutable entry")

    if resolution.resolution_status == "RESOLVED":
        exit_quote = resolution.exit_quote
        entry_accepted_ns = datetime_to_epoch_nanoseconds(entry.quote.accepted_at)
        exit_accepted_ns = datetime_to_epoch_nanoseconds(exit_quote.accepted_at)
        if exit_quote.provider_event_ns <= entry.quote.provider_event_ns:
            raise ValueError("exit quote provider-event time is not strictly causal to the entry quote")
        if exit_accepted_ns <= entry_accepted_ns:
            raise ValueError("exit quote accepted_at is not strictly causal to the entry quote")


def build_simulation_resolution_record(*, entry: SimulationEntryRecord,
        exit_quote: SimulationExecutableQuote | None = None,
        unresolved_status: str | None = None) -> SimulationResolutionRecord:
    """Build and deterministically identify one validated terminal resolution.

    Supply exactly one of ``exit_quote`` (for ``RESOLVED``) or
    ``unresolved_status`` (one of the two unresolved terminal statuses).
    """
    if not isinstance(entry, SimulationEntryRecord):
        raise ValueError("entry must be a SimulationEntryRecord")
    if entry.entry_status != "ENTERED":
        raise ValueError("only an ENTERED entry may be resolved")
    if entry.quote is None or entry.entry_price is None:
        raise ValueError("ENTERED entry is missing its executable quote or price")

    cutoff = entry.cutoff_at.astimezone(timezone.utc)
    target = cutoff + timedelta(seconds=entry.horizon_seconds)
    deadline = target + timedelta(seconds=RESOLUTION_WINDOW_SECONDS)

    if exit_quote is not None:
        if unresolved_status is not None:
            raise ValueError("cannot supply both exit_quote and unresolved_status")
        if not _quote_is_valid_exit(entry.decision, target, deadline, entry.quote, exit_quote):
            raise ValueError("exit_quote is not a valid causal exit inside the observation window")
        status = "RESOLVED"
        exit_price = exit_quote.bid if entry.decision == "LONG" else exit_quote.ask
        return_bps = _return_bps(entry.decision, entry.entry_price, exit_price)
    else:
        if unresolved_status not in ("UNRESOLVED_WINDOW_EXPIRED", "UNRESOLVED_OBSERVATION_GAP"):
            raise ValueError("unresolved_status must be a valid unresolved terminal status")
        status = unresolved_status
        exit_price = None
        return_bps = None

    values: dict[str, object] = {
        "contract_version": SIM_RESOLUTION_CONTRACT_VERSION,
        "canonicalization_version": SIM_CANONICALIZATION_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "mode": SIMULATION_MODE,
        "symbol": SYMBOL,
        "instrument": INSTRUMENT,
        "entry_id": entry.entry_id,
        "entry_hash": entry.entry_hash,
        "source_cycle_id": entry.source_cycle_id,
        "cutoff_at": cutoff,
        "horizon": entry.horizon,
        "horizon_seconds": entry.horizon_seconds,
        "decision": entry.decision,
        "entry_quote_id": entry.quote.quote_id,
        "entry_quote_hash": entry.quote.quote_hash,
        "entry_price": entry.entry_price,
        "resolution_target_at": target,
        "resolution_deadline_at": deadline,
        "resolution_status": status,
        "exit_quote": exit_quote,
        "exit_price": exit_price,
        "return_bps": return_bps,
    }
    digest = canonical_sha256(values)
    resolution = SimulationResolutionRecord(resolution_id=RESOLUTION_ID_PREFIX + digest,
                                            resolution_hash=digest,
                                            **values)  # type: ignore[arg-type]
    validate_resolution_matches_entry(resolution, entry)
    return resolution


def serialize_simulation_resolution_record(resolution: SimulationResolutionRecord) -> str:
    if not isinstance(resolution, SimulationResolutionRecord):
        raise ValueError("resolution must be a SimulationResolutionRecord")
    _validate_resolution(resolution)
    return json.dumps(_canonical(asdict(resolution)), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True)


def deserialize_simulation_resolution_record(
        payload: str | Mapping[str, object]) -> SimulationResolutionRecord:
    """Strictly decode a resolution and fail closed on malformed or tampered data."""
    try:
        canonical = json.loads(payload) if isinstance(payload, str) else dict(payload)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("resolution payload is not valid JSON") from error
    if not isinstance(canonical, dict) or set(canonical) != set(_RESOLUTION_FIELD_NAMES):
        raise ValueError("resolution payload has missing or unknown fields")
    try:
        value = _decanonical(canonical)
        if not isinstance(value, dict) or set(value) != set(_RESOLUTION_FIELD_NAMES):
            raise ValueError("resolution payload does not match the contract")
        nested = value.get("exit_quote")
        if nested is not None:
            if not isinstance(nested, dict) or set(nested) != set(_QUOTE_FIELD_NAMES):
                raise ValueError("resolution exit_quote does not match the contract")
            value["exit_quote"] = SimulationExecutableQuote(**nested)
        resolution = SimulationResolutionRecord(**value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("resolution payload does not match the contract") from error
    if canonical != json.loads(serialize_simulation_resolution_record(resolution)):
        raise ValueError("resolution payload is not canonical")
    return resolution


_RESOLUTION_COLUMNS = (
    "resolution_id", "resolution_hash", "contract_version",
    "canonicalization_version", "simulator_version", "mode", "symbol",
    "instrument", "entry_id", "entry_hash", "source_cycle_id", "cutoff_at",
    "horizon", "horizon_seconds", "decision", "entry_quote_id",
    "entry_quote_hash", "entry_price", "resolution_target_at",
    "resolution_deadline_at", "resolution_status", "exit_quote_id",
    "exit_quote_hash", "exit_quote_source_spec", "exit_quote_event_ns",
    "exit_quote_accepted_at", "exit_price", "return_bps", "record_json",
)
_RESOLUTION_DIRECT_COLUMNS = _RESOLUTION_COLUMNS[:21]
_RESOLUTION_SELECT = "SELECT " + ", ".join(_RESOLUTION_COLUMNS) + " FROM " + SIM_RESOLUTION_TABLE


class SimulationResolutionStore:
    """Cursor-scoped access on the worker's already-owned backend session.

    This class never opens or closes a connection and never commits or rolls
    back, matching ``SimulationEntryStore``.  It shares the same
    ``atom_v9_sim_entry_runtime`` role and the same per-horizon advisory
    locks as SIM-4 entry admission.
    """

    def __init__(self, connection, *, expected_backend_pid: int | None = None):
        if connection is None:
            raise TypeError("connection is required")
        if expected_backend_pid is not None:
            _integer("expected_backend_pid", expected_backend_pid, minimum=1)
        self._connection = connection
        self._backend_pid = expected_backend_pid

    @property
    def backend_pid(self) -> int | None:
        return self._backend_pid

    @staticmethod
    def _fetchall(cursor):
        rows = cursor.fetchall()
        return [] if rows is None else list(rows)

    def _verify_authority_on_cursor(self, cursor) -> int:
        cursor.execute("SELECT current_user, session_user, pg_backend_pid()")
        row = cursor.fetchone()
        if row is None or len(row) != 3:
            raise SimulationResolutionRoleError("database authority result is malformed")
        if row[0] != SIM_ENTRY_RUNTIME_ROLE or row[1] != SIM_ENTRY_RUNTIME_ROLE:
            raise SimulationResolutionRoleError("database role does not match SIM-4 entry runtime")
        try:
            pid = _integer("pg_backend_pid", row[2], minimum=1)
        except ValueError as error:
            raise SimulationResolutionRoleError("database backend PID is malformed") from error
        if self._backend_pid is None:
            self._backend_pid = pid
        elif pid != self._backend_pid:
            raise SimulationResolutionStateError("authoritative database backend changed")
        return pid

    @staticmethod
    def _decode_resolution_row(row) -> SimulationResolutionRecord:
        if row is None or len(row) != len(_RESOLUTION_COLUMNS):
            raise SimulationResolutionRowInvalidError("stored resolution row has invalid shape")
        values = dict(zip(_RESOLUTION_COLUMNS, row))
        payload = values["record_json"]
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            resolution = deserialize_simulation_resolution_record(payload)
            if payload != json.loads(serialize_simulation_resolution_record(resolution)):
                raise ValueError("resolution JSON is not canonical")
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise SimulationResolutionRowInvalidError("stored resolution payload is invalid") from error
        for name in _RESOLUTION_DIRECT_COLUMNS:
            if values[name] != getattr(resolution, name):
                raise SimulationResolutionRowInvalidError(
                    f"stored resolution column {name} does not match payload")
        exit_quote = resolution.exit_quote
        expected_exit = (
            (None, None, None, None, None) if exit_quote is None else
            (exit_quote.quote_id, exit_quote.quote_hash, exit_quote.source_spec,
             exit_quote.provider_event_ns, exit_quote.accepted_at)
        )
        relational = (
            values["exit_quote_id"], values["exit_quote_hash"],
            values["exit_quote_source_spec"], values["exit_quote_event_ns"],
            values["exit_quote_accepted_at"],
        )
        if relational != expected_exit:
            raise SimulationResolutionRowInvalidError(
                "stored exit quote columns do not match payload")
        return resolution

    def get_resolution_for_entry_on_cursor(self, cursor, entry_id: str, *,
            expected_entry: SimulationEntryRecord | None = None
            ) -> SimulationResolutionRecord | None:
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("entry_id must be a nonempty string")
        cursor.execute(_RESOLUTION_SELECT + " WHERE entry_id = %s", (entry_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        resolution = self._decode_resolution_row(row)
        if resolution.entry_id != entry_id:
            raise SimulationResolutionRowInvalidError(
                "stored resolution does not match requested entry identity")
        if expected_entry is not None:
            if entry_id != expected_entry.entry_id:
                raise ValueError("entry_id does not match expected_entry")
            try:
                validate_resolution_matches_entry(resolution, expected_entry)
            except ValueError as error:
                raise SimulationResolutionRowInvalidError(
                    "stored resolution does not match immutable entry") from error
        return resolution

    @staticmethod
    def _insert_resolution_on_cursor(cursor, resolution: SimulationResolutionRecord) -> bool:
        payload = json.dumps(json.loads(serialize_simulation_resolution_record(resolution)),
                             sort_keys=True, separators=(",", ":"))
        exit_quote = resolution.exit_quote
        cursor.execute(
            "INSERT INTO public.atom_v9_sim_resolutions ("
            + ", ".join(_RESOLUTION_COLUMNS)
            + ") VALUES ("
            + ", ".join(("%s",) * len(_RESOLUTION_COLUMNS))
            + ") ON CONFLICT DO NOTHING RETURNING resolution_id",
            (
                resolution.resolution_id, resolution.resolution_hash,
                resolution.contract_version, resolution.canonicalization_version,
                resolution.simulator_version, resolution.mode, resolution.symbol,
                resolution.instrument, resolution.entry_id, resolution.entry_hash,
                resolution.source_cycle_id, resolution.cutoff_at, resolution.horizon,
                resolution.horizon_seconds, resolution.decision,
                resolution.entry_quote_id, resolution.entry_quote_hash,
                resolution.entry_price, resolution.resolution_target_at,
                resolution.resolution_deadline_at, resolution.resolution_status,
                None if exit_quote is None else exit_quote.quote_id,
                None if exit_quote is None else exit_quote.quote_hash,
                None if exit_quote is None else exit_quote.source_spec,
                None if exit_quote is None else exit_quote.provider_event_ns,
                None if exit_quote is None else exit_quote.accepted_at,
                resolution.exit_price, resolution.return_bps, payload,
            ),
        )
        return cursor.fetchone() is not None

    def terminalize_resolution_in_transaction(self, cursor,
            entry: SimulationEntryRecord, *,
            exit_quote: SimulationExecutableQuote | None = None,
            unresolved_status: str | None = None
            ) -> tuple[str, SimulationResolutionRecord]:
        """Atomically choose/persist the one terminal resolution under lock.

        The caller must already own an explicit transaction on the worker's
        authoritative session.  This method acquires the same per-horizon
        transaction advisory lock SIM-4 entry admission uses (freeze
        section 9: "the existing per-horizon advisory lock") and performs no
        commit or rollback.  An existing durable resolution for this
        ``entry_id`` always wins (idempotent replay); a different resolution
        already occupying this identity is a conflict.
        """
        if not isinstance(entry, SimulationEntryRecord):
            raise ValueError("entry must be a SimulationEntryRecord")
        if entry.entry_status != "ENTERED":
            raise ValueError("only an ENTERED entry may be resolved")
        self._verify_authority_on_cursor(cursor)
        cursor.execute("SELECT pg_advisory_xact_lock(%s::bigint)",
                       (horizon_advisory_lock_key(entry.horizon),))
        lock_row = cursor.fetchone()
        if lock_row is not None and lock_row not in ((None,), ("",)):
            raise SimulationResolutionStateError("horizon advisory-lock result is malformed")

        existing = self.get_resolution_for_entry_on_cursor(
            cursor, entry.entry_id, expected_entry=entry)
        if existing is not None:
            return IDEMPOTENT, existing

        resolution = build_simulation_resolution_record(
            entry=entry, exit_quote=exit_quote, unresolved_status=unresolved_status)

        if self._insert_resolution_on_cursor(cursor, resolution):
            return INSERTED, resolution

        cursor.execute(_RESOLUTION_SELECT +
                       " WHERE entry_id = %s OR resolution_id = %s OR resolution_hash = %s "
                       "ORDER BY resolution_id",
                       (resolution.entry_id, resolution.resolution_id, resolution.resolution_hash))
        rows = self._fetchall(cursor)
        if len(rows) == 1:
            stored = self._decode_resolution_row(rows[0])
            if stored == resolution:
                return IDEMPOTENT, stored
        raise SimulationResolutionConflictError("resolution identity is already in use")
