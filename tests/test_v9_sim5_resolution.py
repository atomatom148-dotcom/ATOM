from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
import json
import math
import unittest

from quant.v9_sim1_contract import build_simulation_trade_intent
from quant.v9_sim4_entry import (
    ENTRY_ID_PREFIX,
    QUOTE_ID_PREFIX,
    SIM4_QUOTE_SOURCE_SPEC,
    SIM_ENTRY_RUNTIME_ROLE,
    SimulationEntryRecord,
    SimulationExecutableQuote,
    build_simulation_entry_record,
    build_simulation_executable_quote,
    datetime_to_epoch_nanoseconds,
    horizon_advisory_lock_key,
    serialize_simulation_entry_record,
)
from quant.v9_sim5_resolution import (
    IDEMPOTENT,
    INSERTED,
    RESOLUTION_ID_PREFIX,
    RESOLUTION_WINDOW_SECONDS,
    RESOLUTION_STATUSES,
    SIM5_ENABLED_ENV,
    SIM_CANONICALIZATION_VERSION,
    SIM_RESOLUTION_CONTRACT_VERSION,
    SIM_RESOLUTION_TABLE,
    SIMULATION_MODE,
    SIMULATOR_VERSION,
    SYMBOL,
    SimulationResolutionConflictError,
    SimulationResolutionRecord,
    SimulationResolutionRoleError,
    SimulationResolutionRowInvalidError,
    SimulationResolutionStateError,
    SimulationResolutionStore,
    build_simulation_resolution_record,
    deserialize_simulation_resolution_record,
    select_exit_quote,
    serialize_simulation_resolution_record,
    sim5_enabled,
    validate_resolution_matches_entry,
)


UTC = timezone.utc
T0 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)


def build_intent(**changes):
    values = dict(
        source_cycle_id="cycle-1",
        source_forecast_record_id="v9v4f:source",
        source_forecast_record_hash="a" * 64,
        source_v2_state_id="v9v2:state",
        source_v2_state_hash="b" * 64,
        source_v3_contract_version="V3-C",
        source_v3_model_version="V3-M",
        cutoff_at=T0 - timedelta(seconds=1),
        eligible_at=T0,
        horizon="30S",
        horizon_seconds=30,
        final_bps=1.25,
        source_v3_status="AVAILABLE",
    )
    values.update(changes)
    return build_simulation_trade_intent(**values)


def build_quote(**changes):
    values = dict(
        source_spec=SIM4_QUOTE_SOURCE_SPEC,
        symbol="COIN",
        provider_event_ns=datetime_to_epoch_nanoseconds(T0) + 1,
        accepted_at=T0 + timedelta(microseconds=1),
        bid=100.0,
        ask=100.25,
        bid_size=2.0,
        ask_size=3.0,
    )
    values.update(changes)
    return build_simulation_executable_quote(**values)


def build_entry(**changes):
    intent_changes = {key: changes.pop(key) for key in
                       ("horizon", "horizon_seconds", "cutoff_at", "eligible_at",
                        "final_bps", "source_cycle_id")
                       if key in changes}
    intent = build_intent(**intent_changes)
    quote = changes.pop("quote", None) or build_quote()
    return build_simulation_entry_record(
        intent=intent, entry_status="ENTERED", quote=quote, **changes)


def target_and_deadline(entry: SimulationEntryRecord):
    target = entry.cutoff_at.astimezone(UTC) + timedelta(seconds=entry.horizon_seconds)
    return target, target + timedelta(seconds=RESOLUTION_WINDOW_SECONDS)


def resolution_row(resolution: SimulationResolutionRecord):
    exit_quote = resolution.exit_quote
    return (
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
        resolution.exit_price, resolution.return_bps,
        json.loads(serialize_simulation_resolution_record(resolution)),
    )


class ScriptedCursor:
    def __init__(self, steps):
        self.steps = list(steps)
        self.executed = []
        self.current = []
        self.closed = False

    def execute(self, sql, parameters=None):
        self.executed.append((sql, parameters))
        if not self.steps:
            raise AssertionError(f"unexpected SQL: {sql}")
        expected, rows = self.steps.pop(0)
        if expected not in sql:
            raise AssertionError(f"expected {expected!r}, got {sql!r}")
        self.current = list(rows)

    def fetchone(self):
        return None if not self.current else self.current.pop(0)

    def fetchall(self):
        rows = self.current
        self.current = []
        return rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def authority(pid=4321):
    return [(SIM_ENTRY_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE, pid)]


class SimulationResolutionContractTests(unittest.TestCase):
    def test_exact_constants_field_order_and_frozen_slotted_shape(self):
        self.assertEqual(SIM_RESOLUTION_CONTRACT_VERSION, "ATOM_TRUE_V9_SIM5_RESOLUTION_1")
        self.assertEqual(SIM_CANONICALIZATION_VERSION, "ATOM_TRUE_V9_SIM_CANONICAL_V4A_1")
        self.assertEqual(SIMULATOR_VERSION, "ATOM_TRUE_V9_SIM_1")
        self.assertEqual(SIMULATION_MODE, "PAPER_ONLY")
        self.assertEqual(RESOLUTION_ID_PREFIX, "v9simresolution:")
        self.assertEqual(SIM_RESOLUTION_TABLE, "public.atom_v9_sim_resolutions")
        self.assertEqual(SYMBOL, "COIN")
        self.assertEqual(RESOLUTION_WINDOW_SECONDS, 2)
        self.assertEqual(RESOLUTION_STATUSES, frozenset((
            "RESOLVED", "UNRESOLVED_WINDOW_EXPIRED", "UNRESOLVED_OBSERVATION_GAP")))
        self.assertEqual(tuple(f.name for f in fields(SimulationResolutionRecord)), (
            "contract_version", "canonicalization_version", "simulator_version",
            "resolution_id", "resolution_hash", "mode", "symbol", "instrument",
            "entry_id", "entry_hash", "source_cycle_id", "cutoff_at", "horizon",
            "horizon_seconds", "decision", "entry_quote_id", "entry_quote_hash",
            "entry_price", "resolution_target_at", "resolution_deadline_at",
            "resolution_status", "exit_quote", "exit_price", "return_bps"))
        entry = build_entry()
        target, deadline = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        resolution = build_simulation_resolution_record(entry=entry, exit_quote=exit_quote)
        self.assertFalse(hasattr(resolution, "__dict__"))
        from dataclasses import FrozenInstanceError
        with self.assertRaises(FrozenInstanceError):
            resolution.decision = "SHORT"
        for horizon, seconds in (("30S", 30), ("1M", 60), ("5M", 300),
                                 ("15M", 900), ("30M", 1800), ("1H", 3600)):
            resolved_entry = build_entry(horizon=horizon, horizon_seconds=seconds,
                                         source_cycle_id=f"cycle-{horizon}")
            resolved_target, _ = target_and_deadline(resolved_entry)
            self.assertEqual(resolved_entry.horizon_seconds, seconds)
        with self.assertRaises(ValueError):
            replace(resolution, horizon="2H")

    def test_target_is_cutoff_plus_horizon_never_entry_time(self):
        entry = build_entry(cutoff_at=T0 - timedelta(seconds=10), eligible_at=T0,
                            horizon="5M", horizon_seconds=300)
        target, deadline = target_and_deadline(entry)
        self.assertEqual(target, entry.cutoff_at.astimezone(UTC) + timedelta(seconds=300))
        self.assertNotEqual(target, entry.publication_at + timedelta(seconds=300))
        self.assertEqual(deadline, target + timedelta(seconds=2))
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        resolution = build_simulation_resolution_record(entry=entry, exit_quote=exit_quote)
        self.assertEqual(resolution.resolution_target_at, target)
        self.assertEqual(resolution.resolution_deadline_at, deadline)

    def test_window_bounds_inclusive_both_endpoints(self):
        entry = build_entry()
        target, deadline = target_and_deadline(entry)
        target_ns = datetime_to_epoch_nanoseconds(target)
        deadline_ns = datetime_to_epoch_nanoseconds(deadline)
        at_target = build_quote(provider_event_ns=target_ns, accepted_at=target,
                                bid=101.0, ask=101.5)
        at_deadline = build_quote(provider_event_ns=deadline_ns, accepted_at=deadline,
                                  bid=102.0, ask=102.5)
        before_target = build_quote(provider_event_ns=target_ns - 1,
                                    accepted_at=target - timedelta(microseconds=1))
        after_deadline = build_quote(provider_event_ns=deadline_ns + 1,
                                     accepted_at=deadline + timedelta(microseconds=1))
        self.assertEqual(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=entry.quote, quotes=[at_target]), at_target)
        self.assertEqual(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=entry.quote, quotes=[at_deadline]), at_deadline)
        self.assertIsNone(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=entry.quote, quotes=[before_target]))
        self.assertIsNone(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=entry.quote, quotes=[after_deadline]))

    def test_causal_floor_strictly_after_entry_quote(self):
        entry = build_entry()
        target, deadline = target_and_deadline(entry)
        same_provider_event = build_quote(
            provider_event_ns=entry.quote.provider_event_ns,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        same_accepted_at = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=entry.quote.accepted_at, bid=101.0, ask=101.5)
        self.assertIsNone(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=entry.quote, quotes=[same_provider_event]))
        self.assertIsNone(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=entry.quote, quotes=[same_accepted_at]))
        with self.assertRaises(ValueError):
            build_simulation_resolution_record(entry=entry, exit_quote=same_provider_event)
        with self.assertRaises(ValueError):
            build_simulation_resolution_record(entry=entry, exit_quote=same_accepted_at)

        # build_simulation_resolution_record and select_exit_quote both
        # apply this floor against the entry's actual executable quote (not
        # a self-contained approximation), and validate_resolution_matches_
        # entry re-derives the same check from a resolution/entry pair.
        valid = build_simulation_resolution_record(
            entry=entry, exit_quote=build_quote(
                provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
                accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5))
        validate_resolution_matches_entry(valid, entry)

    def test_selection_uses_deterministic_first_quote_tuple(self):
        entry = build_entry()
        target, deadline = target_and_deadline(entry)
        same_time = target + timedelta(microseconds=2)
        lower = build_quote(provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
                            accepted_at=same_time, bid=99.0, ask=99.25)
        higher = build_quote(provider_event_ns=datetime_to_epoch_nanoseconds(target) + 2,
                             accepted_at=same_time, bid=98.0, ask=98.25)
        later = build_quote(provider_event_ns=datetime_to_epoch_nanoseconds(target) + 3,
                            accepted_at=target + timedelta(microseconds=3))
        self.assertEqual(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=entry.quote, quotes=[later, higher, lower]), lower)

    def test_exit_side_and_minimum_size_requirements(self):
        long_entry = build_entry()
        short_entry = build_entry(final_bps=-1.0, source_cycle_id="cycle-short")
        target, deadline = target_and_deadline(long_entry)
        long_exit = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1),
            bid=101.0, ask=101.5, bid_size=1.0, ask_size=0.0)
        resolution = build_simulation_resolution_record(entry=long_entry, exit_quote=long_exit)
        self.assertEqual(resolution.exit_price, long_exit.bid)
        thin_bid = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1),
            bid_size=0.999999)
        self.assertIsNone(select_exit_quote(
            decision="LONG", resolution_target_at=target, resolution_deadline_at=deadline,
            entry_quote=long_entry.quote, quotes=[thin_bid]))

        target_s, deadline_s = target_and_deadline(short_entry)
        short_exit = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target_s) + 1,
            accepted_at=target_s + timedelta(microseconds=1),
            bid=99.0, ask=99.5, bid_size=0.0, ask_size=1.0)
        short_resolution = build_simulation_resolution_record(
            entry=short_entry, exit_quote=short_exit)
        self.assertEqual(short_resolution.exit_price, short_exit.ask)
        thin_ask = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target_s) + 1,
            accepted_at=target_s + timedelta(microseconds=1),
            ask_size=0.999999)
        self.assertIsNone(select_exit_quote(
            decision="SHORT", resolution_target_at=target_s, resolution_deadline_at=deadline_s,
            entry_quote=short_entry.quote, quotes=[thin_ask]))

    def test_exact_return_formulas_and_finite_rejection(self):
        long_entry = build_entry()
        target, _ = target_and_deadline(long_entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        resolution = build_simulation_resolution_record(entry=long_entry, exit_quote=exit_quote)
        expected = 1.0e4 * math.log(exit_quote.bid / long_entry.entry_price)
        self.assertEqual(resolution.return_bps, expected)

        short_entry = build_entry(final_bps=-1.0, source_cycle_id="cycle-short")
        target_s, _ = target_and_deadline(short_entry)
        exit_quote_s = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target_s) + 1,
            accepted_at=target_s + timedelta(microseconds=1), bid=99.0, ask=99.5)
        resolution_s = build_simulation_resolution_record(entry=short_entry, exit_quote=exit_quote_s)
        expected_s = 1.0e4 * math.log(short_entry.entry_price / exit_quote_s.ask)
        self.assertEqual(resolution_s.return_bps, expected_s)

        with self.assertRaises(ValueError):
            replace(resolution, return_bps=math.nan)
        with self.assertRaises(ValueError):
            replace(resolution, return_bps=math.inf)
        with self.assertRaises(ValueError):
            replace(resolution, exit_price=math.nan)

    def test_return_bps_hash_sensitivity_and_tamper_rejection(self):
        entry = build_entry()
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        resolution = build_simulation_resolution_record(entry=entry, exit_quote=exit_quote)
        self.assertTrue(resolution.resolution_id.startswith(RESOLUTION_ID_PREFIX))
        self.assertEqual(resolution.resolution_id, RESOLUTION_ID_PREFIX + resolution.resolution_hash)

        encoded = serialize_simulation_resolution_record(resolution)
        self.assertEqual(deserialize_simulation_resolution_record(encoded), resolution)
        payload = json.loads(encoded)
        self.assertIn("return_bps", payload)

        # Tampering with return_bps alone (without recomputing the hash)
        # must be rejected — it is inside the hash (freeze section 7).
        tampered = dict(payload)
        tampered["return_bps"] = {"$float64": (0.0).hex()}
        with self.assertRaises(ValueError):
            deserialize_simulation_resolution_record(tampered)

        tampered_hash = dict(payload)
        tampered_hash["resolution_hash"] = "f" * 64
        with self.assertRaises(ValueError):
            deserialize_simulation_resolution_record(tampered_hash)

        with self.assertRaises(ValueError):
            replace(resolution, resolution_hash="f" * 64)

    def test_skipped_entries_cannot_resolve(self):
        no_trade_entry = build_simulation_entry_record(
            intent=build_intent(final_bps=0.0), entry_status="SKIPPED_NO_TRADE")
        with self.assertRaises(ValueError):
            build_simulation_resolution_record(
                entry=no_trade_entry, unresolved_status="UNRESOLVED_OBSERVATION_GAP")

        expired_entry = build_simulation_entry_record(
            intent=build_intent(horizon="1M", horizon_seconds=60),
            entry_status="SKIPPED_WINDOW_EXPIRED")
        with self.assertRaises(ValueError):
            build_simulation_resolution_record(
                entry=expired_entry, unresolved_status="UNRESOLVED_OBSERVATION_GAP")

    def test_unresolved_statuses_forbid_executable_fields(self):
        entry = build_entry()
        for status in ("UNRESOLVED_WINDOW_EXPIRED", "UNRESOLVED_OBSERVATION_GAP"):
            resolution = build_simulation_resolution_record(
                entry=entry, unresolved_status=status)
            self.assertEqual(resolution.resolution_status, status)
            self.assertIsNone(resolution.exit_quote)
            self.assertIsNone(resolution.exit_price)
            self.assertIsNone(resolution.return_bps)
        with self.assertRaises(ValueError):
            build_simulation_resolution_record(entry=entry, unresolved_status="RESOLVED")
        with self.assertRaises(ValueError):
            build_simulation_resolution_record(entry=entry)  # neither supplied
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        with self.assertRaises(ValueError):
            build_simulation_resolution_record(
                entry=entry, exit_quote=exit_quote,
                unresolved_status="UNRESOLVED_OBSERVATION_GAP")

    def test_validate_resolution_matches_entry_cross_checks(self):
        entry = build_entry()
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        resolution = build_simulation_resolution_record(entry=entry, exit_quote=exit_quote)
        validate_resolution_matches_entry(resolution, entry)

        other_entry = build_entry(source_cycle_id="cycle-other")
        with self.assertRaises(ValueError):
            validate_resolution_matches_entry(resolution, other_entry)

        skipped = build_simulation_entry_record(
            intent=build_intent(final_bps=0.0), entry_status="SKIPPED_NO_TRADE")
        with self.assertRaises(ValueError):
            validate_resolution_matches_entry(resolution, skipped)

    def test_sim5_enabled_gate_exact_lowercase_true(self):
        self.assertEqual(SIM5_ENABLED_ENV, "ATOM_V9_SIM5_ENABLED")
        self.assertTrue(sim5_enabled({SIM5_ENABLED_ENV: "true"}))
        for value in ("True", "TRUE", "1", "yes", "", None):
            environ = {} if value is None else {SIM5_ENABLED_ENV: value}
            self.assertFalse(sim5_enabled(environ))
        self.assertFalse(sim5_enabled({}))


class SimulationResolutionStoreTests(unittest.TestCase):
    def test_insert_resolved_acquires_horizon_lock_and_never_commits(self):
        entry = build_entry()
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        cursor = ScriptedCursor([
            ("current_user", authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE entry_id", []),
            ("INSERT INTO public.atom_v9_sim_resolutions", [("inserted",)]),
        ])
        connection = FakeConnection(cursor)
        store = SimulationResolutionStore(connection)
        result, resolution = store.terminalize_resolution_in_transaction(
            cursor, entry, exit_quote=exit_quote)
        self.assertEqual(result, INSERTED)
        self.assertEqual(resolution.resolution_status, "RESOLVED")
        lock_sql, lock_parameters = cursor.executed[1]
        self.assertEqual(lock_sql, "SELECT pg_advisory_xact_lock(%s::bigint)")
        self.assertEqual(lock_parameters, (horizon_advisory_lock_key(entry.horizon),))
        self.assertEqual((connection.commit_calls, connection.rollback_calls), (0, 0))

    def test_existing_terminal_is_idempotent(self):
        entry = build_entry()
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        existing = build_simulation_resolution_record(entry=entry, exit_quote=exit_quote)
        cursor = ScriptedCursor([
            ("current_user", authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE entry_id", [resolution_row(existing)]),
        ])
        store = SimulationResolutionStore(FakeConnection(cursor))
        result, resolution = store.terminalize_resolution_in_transaction(
            cursor, entry, exit_quote=exit_quote)
        self.assertEqual((result, resolution), (IDEMPOTENT, existing))
        self.assertEqual(len(cursor.executed), 3)

    def test_replaying_with_a_different_candidate_still_returns_the_durable_row(self):
        # Matches the SIM-4 entry store's own idempotent design: an existing
        # durable terminal row always wins over whatever this call requests.
        entry = build_entry()
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        existing = build_simulation_resolution_record(entry=entry, exit_quote=exit_quote)
        different_exit = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 2,
            accepted_at=target + timedelta(microseconds=2), bid=105.0, ask=105.5)
        cursor = ScriptedCursor([
            ("current_user", authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE entry_id", [resolution_row(existing)]),
        ])
        store = SimulationResolutionStore(FakeConnection(cursor))
        result, resolution = store.terminalize_resolution_in_transaction(
            cursor, entry, exit_quote=different_exit)
        self.assertEqual((result, resolution), (IDEMPOTENT, existing))

    def test_concurrent_writer_conflict_fails_closed(self):
        # Our own get-check sees nothing (no committed row yet); our insert
        # loses the ON CONFLICT DO NOTHING race to a concurrently committed,
        # differing row; the re-query finds that row and it does not match
        # our candidate, so this must fail closed rather than silently
        # report success or silently adopt the other writer's row.
        entry = build_entry()
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        different_exit = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 2,
            accepted_at=target + timedelta(microseconds=2), bid=105.0, ask=105.5)
        concurrently_stored = build_simulation_resolution_record(
            entry=entry, exit_quote=different_exit)
        cursor = ScriptedCursor([
            ("current_user", authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE entry_id", []),
            ("INSERT INTO public.atom_v9_sim_resolutions", []),
            ("entry_id = %s OR resolution_id", [resolution_row(concurrently_stored)]),
        ])
        store = SimulationResolutionStore(FakeConnection(cursor))
        with self.assertRaises(SimulationResolutionConflictError):
            store.terminalize_resolution_in_transaction(cursor, entry, exit_quote=exit_quote)

    def test_role_and_backend_authority_fail_closed(self):
        cursor = ScriptedCursor([("current_user", [("wrong", "wrong", 1)])])
        store = SimulationResolutionStore(FakeConnection(cursor))
        with self.assertRaises(SimulationResolutionRoleError):
            store._verify_authority_on_cursor(cursor)

        cursor2 = ScriptedCursor([("current_user", authority(pid=2))])
        store2 = SimulationResolutionStore(FakeConnection(cursor2), expected_backend_pid=1)
        with self.assertRaises(SimulationResolutionStateError):
            store2._verify_authority_on_cursor(cursor2)

    def test_decode_row_rejects_relational_tamper(self):
        entry = build_entry()
        target, _ = target_and_deadline(entry)
        exit_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(target) + 1,
            accepted_at=target + timedelta(microseconds=1), bid=101.0, ask=101.5)
        resolution = build_simulation_resolution_record(entry=entry, exit_quote=exit_quote)
        bad = list(resolution_row(resolution))
        # exit_quote_id column (index 21) disagrees with the nested payload.
        bad[21] = "v9simquote:" + "0" * 64
        with self.assertRaises(SimulationResolutionRowInvalidError):
            SimulationResolutionStore._decode_resolution_row(tuple(bad))

        wrong_shape = tuple(resolution_row(resolution))[:-1]
        with self.assertRaises(SimulationResolutionRowInvalidError):
            SimulationResolutionStore._decode_resolution_row(wrong_shape)

    def test_only_an_entered_entry_may_be_terminalized(self):
        skipped = build_simulation_entry_record(
            intent=build_intent(final_bps=0.0), entry_status="SKIPPED_NO_TRADE")
        cursor = ScriptedCursor([])
        store = SimulationResolutionStore(FakeConnection(cursor))
        with self.assertRaises(ValueError):
            store.terminalize_resolution_in_transaction(
                cursor, skipped, unresolved_status="UNRESOLVED_OBSERVATION_GAP")
        self.assertEqual(cursor.executed, [])


if __name__ == "__main__":
    unittest.main()
