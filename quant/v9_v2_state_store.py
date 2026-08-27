"""Least-privilege, append-only recovery storage for immutable V2D states."""

from __future__ import annotations

import json
import math
from typing import Callable, Protocol

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.v9_v2a_dataset import SYMBOL
from quant.v9_v2d_evidence_state import (
    MODEL_FAMILY,
    STATE_SCHEMA_VERSION,
    STATE_VERSION,
    V2EvidenceState,
    deserialize_v2_evidence_state,
    serialize_v2_evidence_state,
)
from quant.v9_v2_build_receipt import V2BuildReceipt, serialize_v2_build_receipt


V2_STATE_TABLE = "public.atom_v9_v2_states"
V2_RUNTIME_ROLE = "atom_v9_v4_runtime"
V2_TARGET_SPEC_ID = "COIN_MIDPOINT_LOG_RETURN_BPS_1"
V2_STATEMENT_TIMEOUT = "15s"
V2_LOCK_TIMEOUT = "2s"

INSERTED = "INSERTED"
IDEMPOTENT = "IDEMPOTENT"
FOUND = "FOUND"
NOT_FOUND = "NOT_FOUND"


class V2StateStoreError(RuntimeError):
    reason = "V2_STATE_STORE_ERROR"


class V2StateConflictError(V2StateStoreError):
    reason = "V2_STATE_CONFLICT"


class V2StateInvalidError(V2StateStoreError):
    reason = "V2_STATE_INVALID"


class V2StateRowInvalidError(V2StateStoreError):
    reason = "V2_STATE_ROW_INVALID"


class V2StateRoleError(V2StateStoreError):
    reason = "V2_STATE_ROLE_MISMATCH"


class _Connection(Protocol):
    def cursor(self): ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


_COLUMNS = (
    "state_id",
    "state_hash",
    "state_schema_version",
    "state_version",
    "model_family",
    "symbol",
    "state_as_of",
    "target_spec_id",
    "target_data_schema_version",
    "target_source_spec_version",
    "top_level_status",
    "creation_status",
    "state_json",
)
_SELECT = "SELECT " + ", ".join(_COLUMNS) + f" FROM {V2_STATE_TABLE}"


def _validate_lookup_identity(*, symbol: str, target_spec_id: str,
                              target_data_schema_version: str,
                              target_source_spec_version: str) -> None:
    if (
        symbol != SYMBOL
        or target_spec_id != V2_TARGET_SPEC_ID
        or target_data_schema_version != DATA_SCHEMA_VERSION
        or target_source_spec_version != SOURCE_SPEC_VERSION
    ):
        raise V2StateInvalidError("unsupported V2 state compatibility identity")


def _validate_state(state: V2EvidenceState) -> str:
    """Return canonical JSON after enforcing the production recovery cohort."""

    try:
        serialized = serialize_v2_evidence_state(state)
        decoded = deserialize_v2_evidence_state(serialized)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise V2StateInvalidError("V2 state does not satisfy its frozen contract") from error
    if decoded != state:
        raise V2StateInvalidError("V2 state is not canonical")
    _validate_lookup_identity(
        symbol=state.symbol,
        target_spec_id=state.target_spec_id,
        target_data_schema_version=state.target_data_schema_version,
        target_source_spec_version=state.target_source_spec_version,
    )
    if (
        state.state_schema_version != STATE_SCHEMA_VERSION
        or state.state_version != STATE_VERSION
        or state.model_family != MODEL_FAMILY
        or state.creation_status != "VALID"
        or state.top_level_status not in ("MATURE", "PROVISIONAL")
    ):
        raise V2StateInvalidError("V2 state is not eligible for recovery storage")
    if (
        isinstance(state.state_as_of, bool)
        or not isinstance(state.state_as_of, (int, float))
        or not math.isfinite(float(state.state_as_of))
    ):
        raise V2StateInvalidError("V2 state_as_of must be finite")
    return serialized


class PostgresV2StateStore:
    """Persist and restore V2D states through short-lived runtime connections."""

    def __init__(self, database_url: str, *, connect: Callable | None = None):
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        if connect is None:
            import psycopg

            def default_connect(url: str):
                return psycopg.connect(
                    url,
                    connect_timeout=5,
                    keepalives=1,
                    keepalives_idle=5,
                    keepalives_interval=2,
                    keepalives_count=3,
                )

            connect = default_connect
        if not callable(connect):
            raise TypeError("connect must be callable")
        self._database_url = database_url
        self._connect = connect

    @staticmethod
    def _verify_role(cursor) -> None:
        cursor.execute("SELECT current_user", ())
        row = cursor.fetchone()
        if row is None or row[0] != V2_RUNTIME_ROLE:
            raise V2StateRoleError("database role does not match V2 runtime")

    @staticmethod
    def _configure_transaction(cursor) -> None:
        cursor.execute(f"SET LOCAL statement_timeout = '{V2_STATEMENT_TIMEOUT}'", ())
        cursor.execute(f"SET LOCAL lock_timeout = '{V2_LOCK_TIMEOUT}'", ())
        # Supabase may use extra_float_digits=0, which rounds float8 text
        # results and breaks exact relational-to-canonical payload checks.
        cursor.execute("SET LOCAL extra_float_digits = 3", ())

    @staticmethod
    def _decode_row(row: object, *, requested_cutoff: float | None = None,
                    target_spec_id: str = V2_TARGET_SPEC_ID,
                    target_data_schema_version: str = DATA_SCHEMA_VERSION,
                    target_source_spec_version: str = SOURCE_SPEC_VERSION,
                    ) -> V2EvidenceState:
        if not isinstance(row, (tuple, list)) or len(row) != len(_COLUMNS):
            raise V2StateRowInvalidError("stored V2 state row has invalid shape")
        values = dict(zip(_COLUMNS, row))
        payload = values["state_json"]
        try:
            canonical_payload = json.loads(payload) if isinstance(payload, str) else payload
            if not isinstance(canonical_payload, dict):
                raise ValueError("state payload is not an object")
            state = deserialize_v2_evidence_state(canonical_payload)
            reserialized = json.loads(serialize_v2_evidence_state(state))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise V2StateRowInvalidError("stored V2 state payload is invalid") from error
        if canonical_payload != reserialized:
            raise V2StateRowInvalidError("stored V2 state payload is not canonical")
        relational = {
            "state_id": state.state_id,
            "state_hash": state.state_hash,
            "state_schema_version": state.state_schema_version,
            "state_version": state.state_version,
            "model_family": state.model_family,
            "symbol": state.symbol,
            "state_as_of": state.state_as_of,
            "target_spec_id": state.target_spec_id,
            "target_data_schema_version": state.target_data_schema_version,
            "target_source_spec_version": state.target_source_spec_version,
            "top_level_status": state.top_level_status,
            "creation_status": state.creation_status,
        }
        for name, expected in relational.items():
            if values[name] != expected:
                raise V2StateRowInvalidError(
                    f"stored V2 state column {name} does not match payload")
        try:
            _validate_lookup_identity(
                symbol=state.symbol,
                target_spec_id=state.target_spec_id,
                target_data_schema_version=state.target_data_schema_version,
                target_source_spec_version=state.target_source_spec_version,
            )
        except V2StateInvalidError as error:
            raise V2StateRowInvalidError(
                "stored V2 state compatibility identity is unsupported") from error
        if (
            state.target_spec_id != target_spec_id
            or state.target_data_schema_version != target_data_schema_version
            or state.target_source_spec_version != target_source_spec_version
        ):
            raise V2StateRowInvalidError("stored V2 state target identity is incompatible")
        if requested_cutoff is not None and state.state_as_of > requested_cutoff:
            raise V2StateRowInvalidError("stored V2 state is newer than requested cutoff")
        return state

    def _run(self, operation):
        connection = self._connect(self._database_url)
        cursor = None
        try:
            cursor = connection.cursor()
            self._configure_transaction(cursor)
            self._verify_role(cursor)
            result = operation(cursor)
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                connection.close()

    def insert(self, state: V2EvidenceState) -> str:
        serialized = _validate_state(state)
        record = json.loads(serialized)

        def operation(cursor):
            cursor.execute(
                f"INSERT INTO {V2_STATE_TABLE} ("
                "state_id, state_hash, state_schema_version, state_version, "
                "model_family, symbol, state_as_of, target_spec_id, "
                "target_data_schema_version, target_source_spec_version, "
                "top_level_status, creation_status, state_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING RETURNING state_id",
                (
                    state.state_id,
                    state.state_hash,
                    state.state_schema_version,
                    state.state_version,
                    state.model_family,
                    state.symbol,
                    state.state_as_of,
                    state.target_spec_id,
                    state.target_data_schema_version,
                    state.target_source_spec_version,
                    state.top_level_status,
                    state.creation_status,
                    json.dumps(record, sort_keys=True, separators=(",", ":")),
                ),
            )
            if cursor.fetchone() is not None:
                return INSERTED
            cursor.execute(
                _SELECT + " WHERE state_id = %s OR state_hash = %s",
                (state.state_id, state.state_hash),
            )
            rows = cursor.fetchall()
            if len(rows) != 1:
                raise V2StateConflictError("V2 state identity is already in use")
            try:
                stored = self._decode_row(rows[0])
            except V2StateRowInvalidError as error:
                raise V2StateConflictError("conflicting V2 state row is invalid") from error
            if stored != state:
                raise V2StateConflictError("V2 state identity is already in use")
            return IDEMPOTENT

        return self._run(operation)

    def insert_with_receipt(self, state: V2EvidenceState,
                            receipt: V2BuildReceipt) -> str:
        """Atomically append the proof before making its state publishable."""
        if receipt.state_id != state.state_id or receipt.state_as_of != state.state_as_of:
            raise V2StateInvalidError("V2 receipt does not identify its state")
        serialized_receipt = serialize_v2_build_receipt(receipt)
        serialized_state = _validate_state(state)

        def operation(cursor):
            cursor.execute(
                "INSERT INTO public.atom_v9_v2_build_receipts "
                "(receipt_sha256,state_id,state_as_of,receipt_json) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING receipt_sha256",
                (receipt.receipt_sha256, state.state_id, state.state_as_of,
                 serialized_receipt),
            )
            inserted_receipt = cursor.fetchone() is not None
            cursor.execute(
                f"INSERT INTO {V2_STATE_TABLE} (state_id,state_hash,state_schema_version,"
                "state_version,model_family,symbol,state_as_of,target_spec_id,"
                "target_data_schema_version,target_source_spec_version,top_level_status,"
                "creation_status,state_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING state_id",
                (state.state_id, state.state_hash, state.state_schema_version,
                 state.state_version, state.model_family, state.symbol, state.state_as_of,
                 state.target_spec_id, state.target_data_schema_version,
                 state.target_source_spec_version, state.top_level_status,
                 state.creation_status, serialized_state),
            )
            inserted_state = cursor.fetchone() is not None
            if inserted_receipt != inserted_state:
                raise V2StateConflictError("V2 state and receipt append conflict")
            return INSERTED if inserted_state else IDEMPOTENT

        return self._run(operation)

    def latest(
        self,
        *,
        requested_cutoff: float,
        symbol: str = SYMBOL,
        target_spec_id: str = V2_TARGET_SPEC_ID,
        target_data_schema_version: str = DATA_SCHEMA_VERSION,
        target_source_spec_version: str = SOURCE_SPEC_VERSION,
    ) -> tuple[V2EvidenceState | None, str]:
        if (
            isinstance(requested_cutoff, bool)
            or not isinstance(requested_cutoff, (int, float))
            or not math.isfinite(float(requested_cutoff))
        ):
            raise ValueError("requested_cutoff must be a finite epoch")
        _validate_lookup_identity(
            symbol=symbol,
            target_spec_id=target_spec_id,
            target_data_schema_version=target_data_schema_version,
            target_source_spec_version=target_source_spec_version,
        )
        cutoff = float(requested_cutoff)

        def operation(cursor):
            cursor.execute(
                _SELECT
                + " WHERE state_schema_version = %s AND state_version = %s "
                "AND model_family = %s AND symbol = %s AND target_spec_id = %s "
                "AND target_data_schema_version = %s "
                "AND target_source_spec_version = %s AND state_as_of <= %s "
                "ORDER BY state_as_of DESC, state_id DESC LIMIT 2",
                (
                    STATE_SCHEMA_VERSION,
                    STATE_VERSION,
                    MODEL_FAMILY,
                    symbol,
                    target_spec_id,
                    target_data_schema_version,
                    target_source_spec_version,
                    cutoff,
                ),
            )
            rows = cursor.fetchall()
            if not rows:
                return None, NOT_FOUND
            if len(rows) > 1:
                if any(
                    not isinstance(row, (tuple, list)) or len(row) != len(_COLUMNS)
                    for row in rows[:2]
                ):
                    raise V2StateRowInvalidError(
                        "stored V2 state row has invalid shape")
                if rows[0][6] == rows[1][6]:
                    raise V2StateConflictError(
                        "multiple V2 states exist at the latest state_as_of")
            state = self._decode_row(
                rows[0],
                requested_cutoff=cutoff,
                target_spec_id=target_spec_id,
                target_data_schema_version=target_data_schema_version,
                target_source_spec_version=target_source_spec_version,
            )
            return state, FOUND

        return self._run(operation)


__all__ = [
    "FOUND",
    "IDEMPOTENT",
    "INSERTED",
    "NOT_FOUND",
    "PostgresV2StateStore",
    "V2StateConflictError",
    "V2StateInvalidError",
    "V2StateRoleError",
    "V2StateRowInvalidError",
    "V2StateStoreError",
]
