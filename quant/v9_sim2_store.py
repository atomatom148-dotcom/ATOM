"""Least-privilege, append-only persistence for SIM-1 trade intents."""

from __future__ import annotations

import json
from typing import Callable, Protocol

from quant.v9_sim1_contract import (
    SimulationTradeIntent,
    deserialize_simulation_trade_intent,
    serialize_simulation_trade_intent,
)


SIM_INTENT_STORE_VERSION = "ATOM_TRUE_V9_SIM2_STORE_1"
SIM_INTENT_SCHEMA_VERSION = "ATOM_TRUE_V9_SIM2_SCHEMA_1"
SIM_INTENT_TABLE = "public.atom_v9_sim_intents"
SIM_RUNTIME_ROLE = "atom_v9_sim_runtime"
INSERTED = "INSERTED"
IDEMPOTENT = "IDEMPOTENT"


class SimulationIntentError(RuntimeError):
    reason = "SIM2_ERROR"


class SimulationIntentConflictError(SimulationIntentError):
    reason = "SIM2_INTENT_CONFLICT"


class SimulationIntentRowInvalidError(SimulationIntentError):
    reason = "SIM2_ROW_INVALID"


class SimulationIntentRoleError(SimulationIntentError):
    reason = "SIM2_ROLE_MISMATCH"


class _Connection(Protocol):
    def cursor(self): ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


_COLUMNS = (
    "intent_id", "intent_hash", "contract_version",
    "canonicalization_version", "simulator_version", "symbol", "horizon",
    "horizon_seconds", "cutoff_at", "eligible_at", "source_v3_status",
    "decision", "status", "record_json",
)
_SELECT = "SELECT " + ", ".join(_COLUMNS) + " FROM public.atom_v9_sim_intents"


class SimulationIntentStore:
    """Persist intents using a caller-supplied, unprivileged connection factory."""

    def __init__(self, connection_factory: Callable[[], _Connection]):
        if not callable(connection_factory):
            raise TypeError("connection_factory must be callable")
        self._connection_factory = connection_factory

    @staticmethod
    def _verify_role(cursor) -> None:
        cursor.execute("SELECT current_user")
        row = cursor.fetchone()
        if row is None or row[0] != SIM_RUNTIME_ROLE:
            raise SimulationIntentRoleError("database role does not match SIM runtime")

    @staticmethod
    def _decode_row(row) -> SimulationTradeIntent:
        if row is None or len(row) != len(_COLUMNS):
            raise SimulationIntentRowInvalidError("stored intent row has invalid shape")
        values = dict(zip(_COLUMNS, row))
        payload = values["record_json"]
        try:
            if isinstance(payload, str):
                payload = json.loads(payload)
            intent = deserialize_simulation_trade_intent(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise SimulationIntentRowInvalidError("stored intent payload is invalid") from error
        canonical_payload = json.loads(serialize_simulation_trade_intent(intent))
        if payload != canonical_payload:
            raise SimulationIntentRowInvalidError(
                "stored intent payload is not canonical SIM-1 content")
        for name in _COLUMNS[:-1]:
            if values[name] != getattr(intent, name):
                raise SimulationIntentRowInvalidError(
                    f"stored intent column {name} does not match payload")
        return intent

    def _run(self, operation):
        connection = self._connection_factory()
        cursor = None
        try:
            cursor = connection.cursor()
            self._verify_role(cursor)
            result = operation(cursor)
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def insert(self, intent: SimulationTradeIntent) -> str:
        serialized = serialize_simulation_trade_intent(intent)
        record = json.loads(serialized)

        def operation(cursor):
            cursor.execute(
                "INSERT INTO public.atom_v9_sim_intents ("
                "intent_id, intent_hash, contract_version, canonicalization_version, "
                "simulator_version, symbol, horizon, horizon_seconds, cutoff_at, "
                "eligible_at, source_v3_status, decision, status, record_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING RETURNING intent_id",
                (intent.intent_id, intent.intent_hash, intent.contract_version,
                 intent.canonicalization_version, intent.simulator_version,
                 intent.symbol, intent.horizon, intent.horizon_seconds,
                 intent.cutoff_at, intent.eligible_at, intent.source_v3_status,
                 intent.decision, intent.status, json.dumps(record, sort_keys=True,
                                                            separators=(",", ":"))),
            )
            if cursor.fetchone() is not None:
                return INSERTED
            cursor.execute(
                _SELECT + " WHERE intent_id = %s OR intent_hash = %s",
                (intent.intent_id, intent.intent_hash),
            )
            stored = self._decode_row(cursor.fetchone())
            if stored != intent:
                raise SimulationIntentConflictError("intent identity is already in use")
            return IDEMPOTENT

        return self._run(operation)

    def get(self, intent_id: str) -> SimulationTradeIntent | None:
        def operation(cursor):
            cursor.execute(_SELECT + " WHERE intent_id = %s", (intent_id,))
            row = cursor.fetchone()
            return None if row is None else self._decode_row(row)

        return self._run(operation)
