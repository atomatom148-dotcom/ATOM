"""Focused contract tests for append-only V2 state recovery storage."""

from __future__ import annotations

from dataclasses import replace
import json

import pytest

from quant.evidence import DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION
from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS,
    HORIZON_SECONDS,
    RawFamilyObservation,
    RawTarget,
    TargetIdentity,
    build_v2a_dataset,
)
from quant.v9_v2b_calibration import calibrate_v2b
from quant.v9_v2c_covariance import build_v2c_covariance
from quant.v9_v2d_evidence_state import (
    build_v2d_evidence_state,
    serialize_v2_evidence_state,
)
from quant.v9_v2_build_receipt import (
    RECEIPT_SCHEMA_VERSION,
    V2BuildReceipt,
    seal_receipt,
    serialize_v2_build_receipt,
)
from quant.v9_v2_state_store import (
    FOUND,
    IDEMPOTENT,
    INSERTED,
    NOT_FOUND,
    PostgresV2StateStore,
    V2StateConflictError,
    V2StateInvalidError,
    V2StateRoleError,
    V2StateRowInvalidError,
)


DATABASE_URL = "postgresql://runtime"
RUNTIME_ROLE = "atom_v9_v4_runtime"


def _state(*, state_as_of: float = 10_000.0, coefficient: float | None = None):
    horizon = "30S"
    seconds = HORIZON_SECONDS[horizon]
    targets = []
    observations = []
    for index, (x, y) in enumerate(zip((0.0, 1.0, 3.0, 6.0),
                                       (2.0, 5.0, 9.0, 14.0))):
        cutoff = float(index * seconds)
        identity = TargetIdentity(f"{horizon}-{index}", cutoff, cutoff + seconds)
        targets.append(RawTarget(
            index, identity.cycle_id, "COIN", "COIN_MIDPOINT_LOG_RETURN_BPS_1",
            DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, horizon, cutoff, cutoff + seconds,
            cutoff + seconds, y,
        ))
        observations.append(RawFamilyObservation(
            index, identity, "COIN", "q1_momentum", "q1-f1",
            DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION,
            horizon, DIRECTIONAL_BPS, x, cutoff, cutoff, cutoff, "FRESH",
        ))
    dataset = build_v2a_dataset(
        state_as_of=state_as_of,
        horizon=horizon,
        target_spec_id="COIN_MIDPOINT_LOG_RETURN_BPS_1",
        target_data_schema_version=DATA_SCHEMA_VERSION,
        target_source_spec_version=SOURCE_SPEC_VERSION,
        family_versions=(("q1_momentum", "q1-f1", DATA_SCHEMA_VERSION,
                          SOURCE_SPEC_VERSION),),
        targets=targets,
        observations=observations,
    )
    calibration = calibrate_v2b((dataset,))
    item = replace(calibration.directional[0], status="MATURE")
    if coefficient is not None:
        item = replace(item, calibration_intercept=coefficient)
    calibration = replace(calibration, directional=(item,))
    covariance = build_v2c_covariance(dataset, calibration)
    return build_v2d_evidence_state(
        state_as_of=state_as_of,
        datasets=(dataset,),
        calibrations=(calibration,),
        covariances=(covariance,),
    )


def _receipt(state, **changes):
    value = V2BuildReceipt(
        receipt_schema_version=RECEIPT_SCHEMA_VERSION,
        state_id=state.state_id,
        state_as_of=state.state_as_of,
        stored_forecast_rows=4,
        resolved_evidence_rows=4,
        source_rows_read=4,
        eligible_rows=4,
        admitted_rows=4,
        rejected_rows=0,
        pages_read=1,
        page_size=4_096,
        first_source_identity="directional:30S:q1_momentum:first",
        last_source_identity="directional:30S:q1_momentum:last",
        per_horizon_admitted_counts=(("30S", 4),),
        per_family_horizon_admitted_counts=(("30S", "q1_momentum", 4),),
        per_family_horizon_effective_n=(("30S", "q1_momentum", 4.0),),
        build_elapsed_seconds=1.0,
        peak_rss_bytes=1_024,
        temporary_disk_peak_bytes=2_048,
        evidence_manifest_hash=state.evidence_manifest_hash,
        receipt_sha256="",
    )
    return seal_receipt(replace(value, **changes))


class Cursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.active = []
        self.calls = []
        self.closed = False

    def execute(self, sql, args=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, args))
        if normalized.startswith("SET LOCAL "):
            self.active = []
            return
        self.active = list(self.responses.pop(0))

    def fetchone(self):
        return self.active.pop(0) if self.active else None

    def fetchall(self):
        rows = list(self.active)
        self.active.clear()
        return rows

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, responses):
        self.cursor_value = Cursor(responses)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class Connector:
    def __init__(self, *connections):
        self.connections = list(connections)
        self.calls = []

    def __call__(self, database_url):
        self.calls.append(database_url)
        return self.connections.pop(0)


def _role():
    return [(RUNTIME_ROLE,)]


def _row(state, *, replacements=None, payload=None):
    values = [
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
        json.loads(serialize_v2_evidence_state(state)) if payload is None else payload,
    ]
    for index, value in (replacements or {}).items():
        values[index] = value
    return tuple(values)


def test_insert_is_atomic_content_addressed_and_uses_short_lived_connection():
    state = _state()
    connection = Connection([_role(), [(state.state_id,)]])
    connector = Connector(connection)

    assert PostgresV2StateStore(
        DATABASE_URL, connect=connector,
    ).insert(state) == INSERTED

    assert connector.calls == [DATABASE_URL]
    assert (connection.commits, connection.rollbacks) == (1, 0)
    assert connection.closed and connection.cursor_value.closed
    assert connection.cursor_value.calls[:3] == [
        ("SET LOCAL statement_timeout = '15s'", ()),
        ("SET LOCAL lock_timeout = '2s'", ()),
        ("SET LOCAL extra_float_digits = 3", ()),
    ]
    insert_sql, parameters = connection.cursor_value.calls[4]
    assert "INSERT INTO public.atom_v9_v2_states" in insert_sql
    assert "ON CONFLICT DO NOTHING RETURNING state_id" in insert_sql
    assert parameters[:12] == (
        state.state_id, state.state_hash, state.state_schema_version,
        state.state_version, state.model_family, state.symbol, state.state_as_of,
        state.target_spec_id, state.target_data_schema_version,
        state.target_source_spec_version,
        state.top_level_status, state.creation_status,
    )
    assert json.loads(parameters[12]) == json.loads(serialize_v2_evidence_state(state))


def test_insert_conflict_reread_is_validated_before_idempotency():
    state = _state()
    connection = Connection([_role(), [], [_row(state)]])
    assert PostgresV2StateStore(
        DATABASE_URL, connect=Connector(connection),
    ).insert(state) == IDEMPOTENT
    assert "WHERE state_id = %s OR state_hash = %s" in connection.cursor_value.calls[5][0]

    conflicting = Connection([
        _role(), [], [_row(state, replacements={1: "f" * 64})],
    ])
    with pytest.raises(V2StateConflictError):
        PostgresV2StateStore(
            DATABASE_URL, connect=Connector(conflicting),
        ).insert(state)
    assert (conflicting.commits, conflicting.rollbacks) == (0, 1)
    assert conflicting.closed and conflicting.cursor_value.closed


def test_insert_rejects_unavailable_or_wrong_target_state_before_connecting():
    unavailable = build_v2d_evidence_state(
        state_as_of=10_000.0, datasets=(), calibrations=(), covariances=(),
    )
    connector = Connector()
    with pytest.raises(V2StateInvalidError):
        PostgresV2StateStore(DATABASE_URL, connect=connector).insert(unavailable)
    assert connector.calls == []

    state = _state()
    wrong_target = replace(state, target_spec_id="OTHER")
    with pytest.raises(V2StateInvalidError):
        PostgresV2StateStore(DATABASE_URL, connect=connector).insert(wrong_target)
    assert connector.calls == []


def test_latest_is_exact_bounded_causal_lookup_without_ttl():
    state = _state(state_as_of=10_000.0)
    connection = Connection([_role(), [_row(state)]])
    result = PostgresV2StateStore(
        DATABASE_URL, connect=Connector(connection),
    ).latest(requested_cutoff=9_999_999_999.0)

    assert result == (state, FOUND)
    assert connection.cursor_value.calls[:3] == [
        ("SET LOCAL statement_timeout = '15s'", ()),
        ("SET LOCAL lock_timeout = '2s'", ()),
        ("SET LOCAL extra_float_digits = 3", ()),
    ]
    sql, parameters = connection.cursor_value.calls[4]
    assert "state_schema_version = %s" in sql
    assert "state_version = %s" in sql
    assert "model_family = %s" in sql
    assert "symbol = %s" in sql
    assert "target_spec_id = %s" in sql
    assert "target_data_schema_version = %s" in sql
    assert "target_source_spec_version = %s" in sql
    assert "state_as_of <= %s" in sql
    assert "ORDER BY state_as_of DESC, state_id DESC LIMIT 2" in sql
    assert "INTERVAL" not in sql.upper()
    assert parameters[-1] == 9_999_999_999.0
    assert connection.commits == 1 and connection.rollbacks == 0
    assert connection.closed and connection.cursor_value.closed


def test_latest_not_found_is_explicit_and_committed():
    connection = Connection([_role(), []])
    assert PostgresV2StateStore(
        DATABASE_URL, connect=Connector(connection),
    ).latest(requested_cutoff=10_000.0) == (None, NOT_FOUND)
    assert (connection.commits, connection.rollbacks) == (1, 0)


@pytest.mark.parametrize(
    "index,replacement",
    (
        (0, "v9v2:" + "f" * 64),
        (1, "f" * 64),
        (2, "wrong-schema"),
        (3, "wrong-state"),
        (4, "wrong-model"),
        (5, "BTC"),
        (6, 9_999.0),
        (7, "wrong-target"),
        (8, "wrong-data-schema"),
        (9, "wrong-source-schema"),
        (10, "MATURE"),
        (11, "INVALID"),
    ),
)
def test_latest_rejects_every_relational_payload_mismatch(index, replacement):
    state = _state()
    connection = Connection([
        _role(), [_row(state, replacements={index: replacement})],
    ])
    with pytest.raises(V2StateRowInvalidError):
        PostgresV2StateStore(
            DATABASE_URL, connect=Connector(connection),
        ).latest(requested_cutoff=10_000.0)
    assert (connection.commits, connection.rollbacks) == (0, 1)


def test_latest_rejects_noncanonical_payload_and_future_payload_under_old_row_time():
    state = _state(state_as_of=10_000.0)
    payload = json.loads(serialize_v2_evidence_state(state))
    payload["unexpected"] = "value"
    malformed = Connection([_role(), [_row(state, payload=payload)]])
    with pytest.raises(V2StateRowInvalidError):
        PostgresV2StateStore(
            DATABASE_URL, connect=Connector(malformed),
        ).latest(requested_cutoff=10_000.0)

    future = _state(state_as_of=10_001.0)
    disguised = Connection([
        _role(), [_row(future, replacements={6: 10_000.0})],
    ])
    with pytest.raises(V2StateRowInvalidError):
        PostgresV2StateStore(
            DATABASE_URL, connect=Connector(disguised),
        ).latest(requested_cutoff=10_000.0)


def test_latest_rejects_same_as_of_ambiguity():
    first = _state(state_as_of=10_000.0)
    second = _state(state_as_of=10_000.0, coefficient=1.25)
    assert first.state_hash != second.state_hash
    connection = Connection([_role(), [_row(first), _row(second)]])
    with pytest.raises(V2StateConflictError):
        PostgresV2StateStore(
            DATABASE_URL, connect=Connector(connection),
        ).latest(requested_cutoff=10_000.0)
    assert (connection.commits, connection.rollbacks) == (0, 1)


def test_wrong_runtime_role_fails_closed_and_releases_resources():
    connection = Connection([[('postgres',)]])
    with pytest.raises(V2StateRoleError):
        PostgresV2StateStore(
            DATABASE_URL, connect=Connector(connection),
        ).latest(requested_cutoff=10_000.0)
    assert (connection.commits, connection.rollbacks) == (0, 1)
    assert connection.closed and connection.cursor_value.closed


def test_store_opens_one_new_connection_per_operation():
    state = _state()
    insert_connection = Connection([_role(), [(state.state_id,)]])
    latest_connection = Connection([_role(), [_row(state)]])
    connector = Connector(insert_connection, latest_connection)
    store = PostgresV2StateStore(DATABASE_URL, connect=connector)

    assert store.insert(state) == INSERTED
    assert store.latest(requested_cutoff=state.state_as_of) == (state, FOUND)
    assert connector.calls == [DATABASE_URL, DATABASE_URL]
    assert insert_connection.closed and latest_connection.closed


def test_connection_is_closed_even_when_cursor_cleanup_fails():
    connection = Connection([_role(), []])
    original_close = connection.cursor_value.close

    def failing_close():
        original_close()
        raise RuntimeError("cursor close failed")

    connection.cursor_value.close = failing_close
    with pytest.raises(RuntimeError, match="cursor close failed"):
        PostgresV2StateStore(
            DATABASE_URL, connect=Connector(connection),
        ).latest(requested_cutoff=10_000.0)

    assert connection.cursor_value.closed
    assert connection.closed


@pytest.mark.parametrize(
    "changes",
    (
        {"state_id": "v9v2:" + "f" * 64},
        {"state_as_of": 9_999.0},
    ),
)
def test_insert_with_receipt_rejects_identity_mismatch_before_connecting(changes):
    state = _state()
    connector = Connector()

    with pytest.raises(V2StateInvalidError, match="does not identify"):
        PostgresV2StateStore(
            DATABASE_URL,
            connect=connector,
        ).insert_with_receipt(state, _receipt(state, **changes))

    assert connector.calls == []


@pytest.mark.parametrize(
    ("receipt_rows", "state_rows", "expected"),
    (
        ([("receipt",)], [("state",)], INSERTED),
        ([], [], IDEMPOTENT),
    ),
)
def test_insert_with_receipt_commits_only_matching_atomic_outcomes(
    receipt_rows,
    state_rows,
    expected,
):
    state = _state()
    responses = [_role(), receipt_rows, state_rows]
    if not receipt_rows and not state_rows:
        receipt = _receipt(state)
        responses.extend([
            [(json.loads(serialize_v2_build_receipt(receipt)),)],
            [_row(state)],
        ])
    connection = Connection(responses)

    result = PostgresV2StateStore(
        DATABASE_URL,
        connect=Connector(connection),
    ).insert_with_receipt(state, _receipt(state))

    assert result == expected
    assert (connection.commits, connection.rollbacks) == (1, 0)
    assert any(
        "atom_v9_v2_build_receipts" in sql
        for sql, _ in connection.cursor_value.calls
    )


@pytest.mark.parametrize(
    ("receipt_inserted", "state_inserted"),
    (
        (True, False),
        (False, True),
    ),
)
def test_insert_with_receipt_rolls_back_split_append(
    receipt_inserted,
    state_inserted,
):
    state = _state()
    receipt_rows = [("receipt",)] if receipt_inserted else []
    state_rows = [(state.state_id,)] if state_inserted else []
    connection = Connection([_role(), receipt_rows, state_rows])

    with pytest.raises(V2StateConflictError, match="append conflict"):
        PostgresV2StateStore(
            DATABASE_URL,
            connect=Connector(connection),
        ).insert_with_receipt(state, _receipt(state))

    assert (connection.commits, connection.rollbacks) == (0, 1)
    assert connection.closed and connection.cursor_value.closed
