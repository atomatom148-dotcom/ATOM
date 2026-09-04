from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
import json
import math
import unittest

from quant import v9_sim4_entry as sim4_entry_module
from quant.v9_sim1_contract import build_simulation_trade_intent
from quant.v9_sim4_entry import (
    ENTRY_ID_PREFIX,
    ENTRY_STATUSES,
    ENTRY_WINDOW_SECONDS,
    HORIZON_ORDER,
    IDEMPOTENT,
    INSERTED,
    POSTGRES_BIGINT_MAX,
    QUOTE_ID_PREFIX,
    SIM4_ADVISORY_LOCK_NAMESPACE,
    SIM4_QUOTE_SOURCE_SPEC,
    SIM_CANONICALIZATION_VERSION,
    SIM_ENTRY_CONTRACT_VERSION,
    SIM_ENTRY_RUNTIME_ROLE,
    SIM_EXECUTABLE_QUOTE_CONTRACT_VERSION,
    SIM_INSTALLATION_ID,
    SIM_PUBLISHER_RUNTIME_ROLE,
    SIM_RECONCILIATION_CHECKPOINT_KEY,
    PublicationCursor,
    PublishedSimulationIntent,
    ReconciliationCheckpoint,
    SimulationDatabaseConfigurationError,
    SimulationEntryBackendError,
    SimulationEntryConflictError,
    SimulationEntryRecord,
    SimulationEntryRoleError,
    SimulationEntryRowInvalidError,
    SimulationEntryStateError,
    SimulationEntryStore,
    SimulationExecutableQuote,
    build_simulation_entry_record,
    build_simulation_executable_quote,
    ceil_nanoseconds_to_microseconds,
    datetime_to_epoch_microseconds,
    datetime_to_epoch_nanoseconds,
    deserialize_simulation_entry_record,
    deserialize_simulation_executable_quote,
    discover_supabase_project_ref,
    epoch_microseconds_to_datetime,
    horizon_advisory_lock_key,
    monotonic_derived_utc,
    quote_is_executable_for_intent,
    select_executable_quote,
    serialize_simulation_entry_record,
    serialize_simulation_executable_quote,
    validate_simulator_database_url,
    validate_entry_matches_intent,
)
from quant.v9_v4a_evidence import canonical_sha256


UTC = timezone.utc
PROJECT_REF = "abcdefghijklmnopqrst"
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


def entry_row(entry):
    quote = entry.quote
    return (
        entry.entry_id,
        entry.entry_hash,
        entry.contract_version,
        entry.canonicalization_version,
        entry.simulator_version,
        entry.symbol,
        entry.horizon,
        entry.horizon_seconds,
        entry.intent_id,
        entry.publication_at,
        entry.entry_deadline_at,
        entry.decision,
        entry.intent_status,
        entry.entry_status,
        entry.quantity_shares,
        entry.blocking_entry_id,
        None if quote is None else quote.quote_id,
        None if quote is None else quote.quote_hash,
        None if quote is None else quote.source_spec,
        None if quote is None else quote.provider_event_ns,
        None if quote is None else quote.accepted_at,
        entry.entry_price,
        json.loads(serialize_simulation_entry_record(entry)),
    )


def intent_row(intent):
    return (
        intent.intent_id,
        intent.intent_hash,
        intent.contract_version,
        intent.canonicalization_version,
        intent.simulator_version,
        intent.symbol,
        intent.horizon,
        intent.horizon_seconds,
        intent.cutoff_at,
        intent.eligible_at,
        intent.source_v3_status,
        intent.decision,
        intent.status,
        json.loads(__import__(
            "quant.v9_sim1_contract", fromlist=["serialize_simulation_trade_intent"]
        ).serialize_simulation_trade_intent(intent)),
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
        self.close_calls = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


class SimulationEntryContractTests(unittest.TestCase):
    def test_exact_constants_fields_and_immutable_shapes(self):
        self.assertEqual(SIM_EXECUTABLE_QUOTE_CONTRACT_VERSION,
                         "ATOM_TRUE_V9_SIM4_QUOTE_1")
        self.assertEqual(SIM_ENTRY_CONTRACT_VERSION, "ATOM_TRUE_V9_SIM4_ENTRY_1")
        self.assertEqual(SIM_CANONICALIZATION_VERSION,
                         "ATOM_TRUE_V9_SIM_CANONICAL_V4A_1")
        self.assertEqual(ENTRY_WINDOW_SECONDS, 2)
        self.assertEqual(SIM4_ADVISORY_LOCK_NAMESPACE,
                         "ATOM_TRUE_V9_SIM4_ENTRY_LOCK_1")
        self.assertEqual(tuple(f.name for f in fields(SimulationExecutableQuote)), (
            "contract_version", "canonicalization_version", "quote_id",
            "quote_hash", "source_spec", "symbol", "provider_event_ns",
            "accepted_at", "bid", "ask", "bid_size", "ask_size"))
        self.assertEqual(tuple(f.name for f in fields(SimulationEntryRecord)), (
            "contract_version", "canonicalization_version", "simulator_version",
            "entry_id", "entry_hash", "mode", "symbol", "instrument",
            "intent_id", "intent_hash", "source_cycle_id", "cutoff_at",
            "publication_at", "entry_deadline_at", "horizon", "horizon_seconds",
            "decision", "intent_status", "entry_status", "quantity_shares",
            "blocking_entry_id", "quote", "entry_price"))
        quote = build_quote()
        entry = build_simulation_entry_record(
            intent=build_intent(), entry_status="ENTERED", quote=quote)
        for value in (quote, entry):
            self.assertFalse(hasattr(value, "__dict__"))
            with self.assertRaises(FrozenInstanceError):
                value.symbol = "QQQ"
        self.assertEqual(ENTRY_STATUSES, frozenset((
            "ENTERED", "SKIPPED_NO_TRADE", "SKIPPED_UNAVAILABLE",
            "SKIPPED_POSITION_OPEN", "SKIPPED_WINDOW_EXPIRED",
            "SKIPPED_RESTART_GAP")))

    def test_quote_round_trip_identity_and_v4a_float_vectors(self):
        quote = build_quote()
        self.assertTrue(quote.quote_id.startswith(QUOTE_ID_PREFIX))
        self.assertEqual(quote.quote_id, QUOTE_ID_PREFIX + quote.quote_hash)
        encoded = serialize_simulation_executable_quote(quote)
        self.assertEqual(deserialize_simulation_executable_quote(encoded), quote)
        self.assertEqual(deserialize_simulation_executable_quote(json.loads(encoded)), quote)
        self.assertIn('"$float64":"0x1.9000000000000p+6"', encoded)
        plus = build_quote(bid_size=0.0)
        minus = build_quote(bid_size=-0.0)
        self.assertEqual(plus.quote_hash, minus.quote_hash)
        east = timezone(timedelta(hours=3))
        equivalent = build_quote(accepted_at=build_quote().accepted_at.astimezone(east))
        self.assertEqual(equivalent.quote_hash, quote.quote_hash)

    def test_quote_hash_all_fields_and_excludes_identity(self):
        quote = build_quote()
        payload = {field.name: getattr(quote, field.name) for field in fields(quote)
                   if field.name not in ("quote_id", "quote_hash")}
        self.assertEqual(canonical_sha256(payload), quote.quote_hash)
        variants = {
            "contract_version": "other",
            "canonicalization_version": "other",
            "source_spec": "other",
            "symbol": "QQQ",
            "provider_event_ns": quote.provider_event_ns + 1,
            "accepted_at": quote.accepted_at + timedelta(microseconds=1),
            "bid": 99.0,
            "ask": 101.0,
            "bid_size": 4.0,
            "ask_size": 5.0,
        }
        for name, changed in variants.items():
            candidate = dict(payload)
            candidate[name] = changed
            self.assertNotEqual(canonical_sha256(candidate), quote.quote_hash, name)

    def test_quote_rejects_bad_values_shape_and_tampering(self):
        for name, value in (
            ("provider_event_ns", True), ("provider_event_ns", -1),
            ("provider_event_ns", POSTGRES_BIGINT_MAX + 1),
            ("bid", True), ("bid", 1), ("bid", math.nan),
            ("ask", math.inf), ("bid_size", -1.0), ("ask_size", -1.0),
        ):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                build_quote(**{name: value})
        with self.assertRaises(ValueError):
            build_quote(bid=2.0, ask=1.0)
        with self.assertRaises(ValueError):
            build_quote(accepted_at=T0.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            replace(build_quote(), quote_hash="f" * 64)
        payload = json.loads(serialize_simulation_executable_quote(build_quote()))
        for mutation in ("missing", "extra", "raw-float", "hash"):
            changed = dict(payload)
            if mutation == "missing":
                changed.pop("bid")
            elif mutation == "extra":
                changed["extra"] = 1
            elif mutation == "raw-float":
                changed["bid"] = 100.0
            else:
                changed["quote_hash"] = "f" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                deserialize_simulation_executable_quote(changed)

    def test_entry_status_mappings_and_prices(self):
        long_intent = build_intent()
        short_intent = build_intent(final_bps=-1.0)
        long_entry = build_simulation_entry_record(
            intent=long_intent, entry_status="ENTERED", quote=build_quote())
        short_entry = build_simulation_entry_record(
            intent=short_intent, entry_status="ENTERED", quote=build_quote())
        self.assertEqual((long_entry.entry_price, long_entry.quantity_shares),
                         (build_quote().ask, 1))
        self.assertEqual(short_entry.entry_price, build_quote().bid)
        no_trade = build_simulation_entry_record(
            intent=build_intent(final_bps=0.0), entry_status="SKIPPED_NO_TRADE")
        unavailable = build_simulation_entry_record(
            intent=build_intent(final_bps=None, source_v3_status="UNAVAILABLE"),
            entry_status="SKIPPED_UNAVAILABLE")
        blocker = long_entry.entry_id
        collision = build_simulation_entry_record(
            intent=build_intent(horizon="1M", horizon_seconds=60),
            entry_status="SKIPPED_POSITION_OPEN", blocking_entry_id=blocker)
        expired = build_simulation_entry_record(
            intent=build_intent(horizon="5M", horizon_seconds=300),
            entry_status="SKIPPED_WINDOW_EXPIRED")
        restart = build_simulation_entry_record(
            intent=build_intent(horizon="15M", horizon_seconds=900),
            entry_status="SKIPPED_RESTART_GAP")
        for entry in (no_trade, unavailable, collision, expired, restart):
            self.assertEqual(entry.quantity_shares, 0)
            self.assertIsNone(entry.quote)
            self.assertIsNone(entry.entry_price)
        self.assertEqual(collision.blocking_entry_id, blocker)

    def test_entry_exact_publication_deadline_round_trip_and_nested_tamper(self):
        intent = build_intent()
        entry = build_simulation_entry_record(
            intent=intent, entry_status="ENTERED", quote=build_quote())
        self.assertEqual(entry.publication_at, intent.eligible_at)
        self.assertEqual(entry.entry_deadline_at - entry.publication_at,
                         timedelta(seconds=2))
        self.assertEqual(entry.entry_id, ENTRY_ID_PREFIX + entry.entry_hash)
        encoded = serialize_simulation_entry_record(entry)
        self.assertEqual(deserialize_simulation_entry_record(encoded), entry)
        payload = json.loads(encoded)
        payload["quote"]["quote_hash"] = "f" * 64
        with self.assertRaises(ValueError):
            deserialize_simulation_entry_record(payload)
        payload = json.loads(encoded)
        payload["entry_hash"] = "f" * 64
        with self.assertRaises(ValueError):
            deserialize_simulation_entry_record(payload)
        with self.assertRaises(ValueError):
            replace(entry, entry_deadline_at=entry.entry_deadline_at
                    + timedelta(microseconds=1))
        with self.assertRaises(ValueError):
            replace(entry, intent_id="v9simintent:" + "f" * 64)
        with self.assertRaises(ValueError):
            replace(entry, cutoff_at=entry.publication_at + timedelta(microseconds=1))
        validate_entry_matches_intent(entry, intent)
        with self.assertRaises(ValueError):
            validate_entry_matches_intent(
                entry, build_intent(source_cycle_id="different-cycle"))

    def test_window_boundaries_and_directional_size(self):
        intent = build_intent()
        publication_ns = datetime_to_epoch_nanoseconds(intent.eligible_at)
        deadline = intent.eligible_at + timedelta(seconds=2)
        deadline_ns = datetime_to_epoch_nanoseconds(deadline)
        self.assertFalse(quote_is_executable_for_intent(
            intent, build_quote(provider_event_ns=publication_ns)))
        self.assertTrue(quote_is_executable_for_intent(
            intent, build_quote(provider_event_ns=publication_ns + 1)))
        self.assertTrue(quote_is_executable_for_intent(
            intent, build_quote(provider_event_ns=deadline_ns,
                                accepted_at=deadline)))
        self.assertFalse(quote_is_executable_for_intent(
            intent, build_quote(provider_event_ns=deadline_ns + 1,
                                accepted_at=deadline)))
        self.assertFalse(quote_is_executable_for_intent(
            intent, build_quote(accepted_at=T0 - timedelta(microseconds=1))))
        self.assertFalse(quote_is_executable_for_intent(
            intent, build_quote(accepted_at=deadline + timedelta(microseconds=1))))
        self.assertFalse(quote_is_executable_for_intent(
            intent, build_quote(provider_event_ns=publication_ns + 1001,
                                accepted_at=T0 + timedelta(microseconds=1))))
        self.assertFalse(quote_is_executable_for_intent(
            intent, build_quote(ask_size=0.999999)))
        self.assertTrue(quote_is_executable_for_intent(
            build_intent(final_bps=-1.0), build_quote(bid_size=1.0, ask_size=0.0)))
        self.assertFalse(quote_is_executable_for_intent(
            build_intent(final_bps=-1.0), build_quote(bid_size=0.0)))

    def test_selection_uses_complete_tuple_not_arrival(self):
        same_time = T0 + timedelta(microseconds=2)
        lower = build_quote(provider_event_ns=datetime_to_epoch_nanoseconds(T0) + 1,
                            accepted_at=same_time, bid=99.0, ask=99.25)
        higher = build_quote(provider_event_ns=datetime_to_epoch_nanoseconds(T0) + 2,
                             accepted_at=same_time, bid=98.0, ask=98.25)
        later = build_quote(provider_event_ns=datetime_to_epoch_nanoseconds(T0) + 3,
                            accepted_at=T0 + timedelta(microseconds=3))
        self.assertEqual(select_executable_quote(build_intent(), [later, higher, lower]),
                         lower)
        self.assertIsNone(select_executable_quote(
            build_intent(), [build_quote(ask_size=0.0)]))

    def test_integer_time_helpers_no_float_or_accumulated_rounding(self):
        self.assertEqual(datetime_to_epoch_microseconds(T0), 1_788_264_000_000_000)
        self.assertEqual(datetime_to_epoch_nanoseconds(T0),
                         1_788_264_000_000_000_000)
        self.assertEqual(epoch_microseconds_to_datetime(
            datetime_to_epoch_microseconds(T0)), T0)
        self.assertEqual([ceil_nanoseconds_to_microseconds(value)
                          for value in (0, 1, 999, 1000, 1001)],
                         [0, 1, 1, 1, 2])
        self.assertEqual(monotonic_derived_utc(
            anchor_utc=T0, anchor_monotonic_ns=100, monotonic_now_ns=101),
            T0 + timedelta(microseconds=1))
        self.assertEqual(monotonic_derived_utc(
            anchor_utc=T0, anchor_monotonic_ns=100, monotonic_now_ns=1101),
            T0 + timedelta(microseconds=2))
        with self.assertRaises(ValueError):
            monotonic_derived_utc(
                anchor_utc=T0, anchor_monotonic_ns=101, monotonic_now_ns=100)
        with self.assertRaises(ValueError):
            ceil_nanoseconds_to_microseconds(True)

    def test_golden_horizon_lock_keys(self):
        expected = {
            "30S": 1464455111187090143,
            "1M": -258020115535043520,
            "5M": -4937564732027059942,
            "15M": -1356851238941253914,
            "30M": -2824415193672952787,
            "1H": 6209627528392171927,
        }
        self.assertEqual({h: horizon_advisory_lock_key(h) for h in expected}, expected)
        with self.assertRaises(ValueError):
            horizon_advisory_lock_key("2H")


class SimulatorDatabaseIdentityTests(unittest.TestCase):
    def direct(self, role=SIM_ENTRY_RUNTIME_ROLE, ref=PROJECT_REF,
               port=5432, sslmode="require"):
        return (f"postgresql://{role}:secret@db.{ref}.supabase.co:{port}"
                f"/postgres?sslmode={sslmode}")

    def pooler(self, role=SIM_ENTRY_RUNTIME_ROLE, ref=PROJECT_REF,
               port=5432, sslmode="verify-full"):
        return (f"postgres://{role}.{ref}:secret@aws-0-us-west-1."
                f"pooler.supabase.com:{port}/postgres?sslmode={sslmode}")

    def test_exact_direct_and_session_identities(self):
        direct = validate_simulator_database_url(
            self.direct(), project_ref=PROJECT_REF,
            required_role=SIM_ENTRY_RUNTIME_ROLE)
        self.assertEqual((direct.endpoint_kind, direct.project_ref, direct.role,
                          direct.port, direct.database),
                         ("DIRECT", PROJECT_REF, SIM_ENTRY_RUNTIME_ROLE, 5432,
                          "postgres"))
        pooler = validate_simulator_database_url(
            self.pooler(role=SIM_PUBLISHER_RUNTIME_ROLE), project_ref=PROJECT_REF,
            required_role=SIM_PUBLISHER_RUNTIME_ROLE)
        self.assertEqual(pooler.endpoint_kind, "SESSION_POOLER")
        self.assertEqual(discover_supabase_project_ref(self.direct()), PROJECT_REF)
        self.assertEqual(discover_supabase_project_ref(self.pooler()), PROJECT_REF)
        self.assertIsNone(discover_supabase_project_ref(
            "postgresql://role:p@render.example:5432/postgres"))

    def test_fail_closed_dsn_matrix(self):
        invalid = (
            self.direct(port=6543),
            self.pooler(port=6543),
            self.direct(sslmode="disable"),
            self.direct().replace("?sslmode=require", ""),
            self.direct().replace("/postgres", "/other"),
            self.direct().replace("supabase.co", "example.com"),
            self.direct().replace("db.abcdefghijklmnopqrst", "db.ABCDEFGHIJKLMNOPQRST"),
            self.direct(role=SIM_PUBLISHER_RUNTIME_ROLE),
            self.pooler().replace(f".{PROJECT_REF}:", ":"),
            self.pooler().replace(f".{PROJECT_REF}:", f".{PROJECT_REF}.extra:"),
            self.direct().replace("?sslmode=require", "?sslmode=require&host=x"),
            self.direct().replace(":secret@", "@"),
        )
        for database_url in invalid:
            with self.subTest(database_url=database_url), self.assertRaises(
                    SimulationDatabaseConfigurationError):
                validate_simulator_database_url(
                    database_url, project_ref=PROJECT_REF,
                    required_role=SIM_ENTRY_RUNTIME_ROLE)
        for project_ref in (PROJECT_REF.upper(), "short", PROJECT_REF + "x"):
            with self.assertRaises(SimulationDatabaseConfigurationError):
                validate_simulator_database_url(
                    self.direct(), project_ref=project_ref,
                    required_role=SIM_ENTRY_RUNTIME_ROLE)
        with self.assertRaises(SimulationDatabaseConfigurationError):
            validate_simulator_database_url(
                self.direct(), project_ref=PROJECT_REF, required_role="postgres")


class SimulationEntryStoreTests(unittest.TestCase):
    def authority(self, pid=4321):
        return [(SIM_ENTRY_RUNTIME_ROLE, SIM_ENTRY_RUNTIME_ROLE, pid)]

    def test_startup_verifies_role_installation_sidecars_and_keeps_connection(self):
        cursor = ScriptedCursor([
            ("current_user", self.authority()),
            ("installation_id", [(SIM_INSTALLATION_ID, PROJECT_REF)]),
            ("NOT EXISTS", [(True, True)]),
        ])
        connection = FakeConnection(cursor)
        store = SimulationEntryStore(connection, project_ref=PROJECT_REF)
        self.assertEqual(store.verify_startup(), 4321)
        self.assertEqual(store.backend_pid, 4321)
        self.assertTrue(cursor.closed)
        self.assertEqual((connection.commit_calls, connection.rollback_calls,
                          connection.close_calls), (0, 0, 0))

    def test_role_and_backend_changes_fail_closed(self):
        cursor = ScriptedCursor([("current_user", [("wrong", "wrong", 1)])])
        with self.assertRaises(SimulationEntryRoleError):
            SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF,
                                 ).verify_startup_on_cursor(cursor)
        cursor = ScriptedCursor([("current_user", self.authority(pid=2))])
        with self.assertRaises(SimulationEntryBackendError):
            SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF,
                                 expected_backend_pid=1).verify_startup_on_cursor(cursor)

    def test_checkpoint_and_bounded_semantic_publication_page(self):
        checkpoint_time = T0 + timedelta(seconds=3)
        cursor = ScriptedCursor([
            ("checkpoint_key", [(
                SIM_RECONCILIATION_CHECKPOINT_KEY, 4, 2, T0, checkpoint_time)]),
        ])
        store = SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF)
        checkpoint = store.load_checkpoint_on_cursor(cursor)
        self.assertEqual((checkpoint.last_completed_publication_seq,
                          checkpoint.checkpoint_version), (4, 2))

        first = build_intent(horizon="30S", horizon_seconds=30)
        second = build_intent(horizon="1M", horizon_seconds=60)
        rows = [
            (5, first.eligible_at, first.eligible_at, 1, *intent_row(first)),
            (7, second.eligible_at, second.eligible_at, 2, *intent_row(second)),
        ]
        cursor = ScriptedCursor([("publication_seq >", rows)])
        page = store.load_publication_page_on_cursor(
            cursor, after_completed_publication_seq=4,
            captured_publication_fence=7)
        self.assertEqual(tuple(item.publication_seq for item in page), (5, 7))
        self.assertEqual(page[-1].cursor,
                         PublicationCursor(T0, 2, second.intent_id, 7))
        sql, parameters = cursor.executed[0]
        self.assertIn("p.publication_seq, p.admitted_at, p.publication_at", sql)
        self.assertIn("p.publication_seq > %s AND p.publication_seq <= %s", sql)
        self.assertEqual(parameters[:2], (4, 7))

    def test_published_value_rejects_sidecar_mismatch(self):
        intent = build_intent()
        self.assertEqual(PublishedSimulationIntent(
            1, T0, T0, HORIZON_ORDER["30S"], intent
        ).cursor.publication_seq, 1)
        with self.assertRaises(ValueError):
            PublishedSimulationIntent(
                1, T0, T0 + timedelta(microseconds=1), 1, intent)
        with self.assertRaises(ValueError):
            PublishedSimulationIntent(1, T0, T0, 2, intent)
        with self.assertRaises(ValueError):
            ReconciliationCheckpoint("wrong", 0, 0, None, T0)

    def test_insert_entered_acquires_lock_and_never_commits(self):
        intent = build_intent()
        quote = build_quote()
        cursor = ScriptedCursor([
            ("current_user", self.authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE intent_id", []),
            ("entry_status = 'ENTERED'", []),
            ("INSERT INTO public.atom_v9_sim_entries", [("inserted",)]),
        ])
        connection = FakeConnection(cursor)
        store = SimulationEntryStore(connection, project_ref=PROJECT_REF)
        result, entry = store.terminalize_in_transaction(
            cursor, intent, requested_status="ENTERED", quote=quote)
        self.assertEqual(result, INSERTED)
        self.assertEqual(entry.entry_status, "ENTERED")
        lock_sql, lock_parameters = cursor.executed[1]
        self.assertEqual(lock_sql, "SELECT pg_advisory_xact_lock(%s::bigint)")
        self.assertEqual(lock_parameters, (horizon_advisory_lock_key("30S"),))
        self.assertEqual((connection.commit_calls, connection.rollback_calls,
                          connection.close_calls), (0, 0, 0))

    def test_durable_collision_overrides_requested_entry_with_exact_blocker(self):
        blocker_intent = build_intent(
            cutoff_at=T0 - timedelta(seconds=6),
            eligible_at=T0 - timedelta(seconds=5))
        blocker_quote = build_quote(
            provider_event_ns=datetime_to_epoch_nanoseconds(
                blocker_intent.eligible_at) + 1,
            accepted_at=blocker_intent.eligible_at + timedelta(microseconds=1))
        blocker = build_simulation_entry_record(
            intent=blocker_intent, entry_status="ENTERED", quote=blocker_quote)
        requested = build_intent(source_cycle_id="cycle-2")
        cursor = ScriptedCursor([
            ("current_user", self.authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE intent_id", []),
            ("entry_status = 'ENTERED'", [entry_row(blocker)]),
            ("INSERT INTO public.atom_v9_sim_entries", [("inserted",)]),
        ])
        store = SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF)
        result, entry = store.terminalize_in_transaction(
            cursor, requested, requested_status="ENTERED", quote=build_quote())
        self.assertEqual(result, INSERTED)
        self.assertEqual(entry.entry_status, "SKIPPED_POSITION_OPEN")
        self.assertEqual(entry.blocking_entry_id, blocker.entry_id)
        self.assertIsNone(entry.quote)

    def test_existing_terminal_is_idempotent_before_occupancy(self):
        intent = build_intent()
        existing = build_simulation_entry_record(
            intent=intent, entry_status="SKIPPED_WINDOW_EXPIRED")
        cursor = ScriptedCursor([
            ("current_user", self.authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE intent_id", [entry_row(existing)]),
        ])
        store = SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF)
        result, record = store.terminalize_in_transaction(
            cursor, intent, requested_status="ENTERED", quote=build_quote())
        self.assertEqual((result, record), (IDEMPOTENT, existing))
        self.assertEqual(len(cursor.executed), 3)

    def test_existing_terminal_must_match_immutable_source_intent(self):
        expected_intent = build_intent(source_cycle_id="expected")
        wrong_intent = build_intent(source_cycle_id="wrong")
        wrong_entry = build_simulation_entry_record(
            intent=wrong_intent, entry_status="SKIPPED_WINDOW_EXPIRED")
        cursor = ScriptedCursor([
            ("current_user", self.authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE intent_id", [entry_row(wrong_entry)]),
        ])
        store = SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF)
        with self.assertRaises(SimulationEntryRowInvalidError):
            store.terminalize_in_transaction(
                cursor, expected_intent,
                requested_status="SKIPPED_WINDOW_EXPIRED")

    def test_invalid_stored_relational_content_and_conflict_fail_closed(self):
        intent = build_intent()
        expected = build_simulation_entry_record(
            intent=intent, entry_status="SKIPPED_WINDOW_EXPIRED")
        bad = list(entry_row(expected))
        bad[14] = 1
        with self.assertRaises(SimulationEntryRowInvalidError):
            SimulationEntryStore._decode_entry_row(tuple(bad))

        different = build_simulation_entry_record(
            intent=intent, entry_status="SKIPPED_RESTART_GAP")
        cursor = ScriptedCursor([
            ("current_user", self.authority()),
            ("pg_advisory_xact_lock", [(None,)]),
            ("WHERE intent_id", []),
            ("entry_status = 'ENTERED'", []),
            ("INSERT INTO public.atom_v9_sim_entries", []),
            ("intent_id = %s OR entry_id", [entry_row(different)]),
        ])
        store = SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF)
        with self.assertRaises(SimulationEntryConflictError):
            store.terminalize_in_transaction(
                cursor, intent, requested_status="SKIPPED_WINDOW_EXPIRED")

    def test_multiple_open_entries_fail_closed(self):
        intent1 = build_intent()
        intent2 = build_intent(source_cycle_id="cycle-2")
        entry1 = build_simulation_entry_record(
            intent=intent1, entry_status="ENTERED", quote=build_quote())
        entry2 = build_simulation_entry_record(
            intent=intent2, entry_status="ENTERED", quote=build_quote())
        cursor = ScriptedCursor([
            ("entry_status = 'ENTERED'", [entry_row(entry1), entry_row(entry2)]),
        ])
        store = SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF)
        with self.assertRaises(SimulationEntryStateError):
            store.load_open_occupancy_on_cursor(cursor)
        sql, parameters = cursor.executed[0]
        self.assertIn("WHERE symbol = %s", sql)
        self.assertIn("horizon IN (%s, %s, %s, %s, %s, %s)", sql)
        self.assertIn("ORDER BY horizon, publication_at, entry_id", sql)
        self.assertEqual(parameters, ("COIN", "30S", "1M", "5M", "15M",
                                      "30M", "1H"))

    def test_horizon_release_queries_exclude_durably_resolved_entries(self):
        # SIM-5 freeze (docs/sim-4a-exact-sim5-resolution-freeze.md,
        # section 10): "minimum query/locking change needed so a durably
        # resolved entry no longer blocks its horizon."  Both occupancy
        # queries must anti-join against atom_v9_sim_resolutions by
        # entry_id, and only a provably valid canonical terminal row may
        # satisfy that anti-join. The base SELECT must alias the entries
        # table so that anti-join can reference entry_id unambiguously.
        self.assertIn(" FROM public.atom_v9_sim_entries AS e", sim4_entry_module._ENTRY_SELECT)
        self.assertIn(
            "NOT EXISTS (SELECT 1 FROM public.atom_v9_sim_resolutions AS r "
            "WHERE r.entry_id = e.entry_id AND ",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn(
            "r.resolution_id = 'v9simresolution:' || r.resolution_hash",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "jsonb_typeof(r.record_json) = 'object'",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "jsonb_array_length(jsonb_path_query_array(r.record_json, '$.*')) = 24",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "r.record_json ->> 'resolution_hash' = r.resolution_hash",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "r.exit_quote_event_ns BETWEEN",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "r.record_json #>> '{exit_quote,provider_event_ns}' = r.exit_quote_event_ns::text",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn("r.entry_hash = e.entry_hash", sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn(
            "r.source_cycle_id = e.record_json ->> 'source_cycle_id'",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "r.cutoff_at = CAST(e.record_json #>> '{cutoff_at,$timestamp_utc}' AS timestamptz)",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn("r.horizon = e.horizon", sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn(
            "r.horizon_seconds = e.horizon_seconds",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn("r.decision = e.decision", sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn("r.entry_quote_id = e.quote_id", sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn(
            "r.entry_quote_hash = e.quote_hash",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn("r.entry_price = e.entry_price", sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn("r.mode = e.record_json ->> 'mode'", sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn("r.symbol = e.symbol", sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE)
        self.assertIn(
            "r.instrument = e.record_json ->> 'instrument'",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "e.record_json #>> '{quote,provider_event_ns}' = e.quote_event_ns::text",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "e.record_json #>> '{quote,accepted_at,$timestamp_utc}' = to_char(e.quote_accepted_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertIn(
            "e.record_json #>> '{entry_price,$float64}' = "
            + sim4_entry_module._ENTRY_PRICE_CANONICAL_TOKEN_SQL,
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertNotIn(
            "e.record_json #>> '{entry_price,$float64}' = encode(float8send(e.entry_price), 'hex')",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )
        self.assertNotIn(
            "pg_input_is_valid",
            sim4_entry_module._ENTRY_NOT_RESOLVED_CLAUSE,
        )

        entry1 = build_simulation_entry_record(
            intent=build_intent(), entry_status="ENTERED", quote=build_quote())
        cursor = ScriptedCursor([
            ("entry_status = 'ENTERED'", []),
        ])
        store = SimulationEntryStore(FakeConnection(cursor), project_ref=PROJECT_REF)
        occupancy = store.load_open_occupancy_on_cursor(cursor)
        self.assertEqual(occupancy, {})
        sql, parameters = cursor.executed[0]
        self.assertIn(
            "NOT EXISTS (SELECT 1 FROM public.atom_v9_sim_resolutions AS r "
            "WHERE r.entry_id = e.entry_id AND ", sql)
        self.assertIn("ORDER BY horizon, publication_at, entry_id", sql)
        self.assertEqual(parameters, ("COIN", "30S", "1M", "5M", "15M", "30M", "1H"))

        cursor_keep = ScriptedCursor([
            ("entry_status = 'ENTERED'", [entry_row(entry1)]),
        ])
        store_keep = SimulationEntryStore(FakeConnection(cursor_keep), project_ref=PROJECT_REF)
        occupancy_keep = store_keep.load_open_occupancy_on_cursor(cursor_keep)
        self.assertEqual(occupancy_keep, {"30S": entry1})

        cursor2 = ScriptedCursor([
            ("entry_status = 'ENTERED'", []),
        ])
        store2 = SimulationEntryStore(FakeConnection(cursor2), project_ref=PROJECT_REF)
        blocker = store2._load_horizon_occupancy_on_cursor(cursor2, "30S")
        self.assertIsNone(blocker)
        sql2, parameters2 = cursor2.executed[0]
        self.assertIn(
            "NOT EXISTS (SELECT 1 FROM public.atom_v9_sim_resolutions AS r "
            "WHERE r.entry_id = e.entry_id AND ", sql2)
        self.assertIn("ORDER BY publication_at, entry_id", sql2)
        self.assertEqual(parameters2, ("COIN", "30S"))
        del entry1  # constructed only to prove ENTERED entries build cleanly

    def test_canonical_entry_price_token_matches_float8_in_postgres(self):
        import os
        from urllib.parse import urlsplit

        database_url = os.environ.get("H2C_TEST_DATABASE_URL")
        if not database_url or os.environ.get("CI") != "true":
            self.skipTest("explicit CI PostgreSQL required")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg required")

        parsed = urlsplit(database_url)
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.port != 5432
            or parsed.username != "postgres"
            or parsed.path != "/postgres"
            or parsed.query
            or parsed.fragment
        ):
            self.fail("SIM-5 float-token integration requires the local CI Postgres DSN")

        with psycopg.connect(database_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                for entry_price in (
                    float.fromhex("0x0.0000000000001p-1022"),
                    0.1,
                    1.0,
                    100.25,
                    177.06,
                    float.fromhex("0x1.fffffffffffffp+1023"),
                ):
                    with self.subTest(entry_price=entry_price):
                        cursor.execute(
                            "SELECT "
                            "e.token = "
                            "encode(float8send(e.entry_price), 'hex'), "
                            "e.token = "
                            + sim4_entry_module._ENTRY_PRICE_CANONICAL_TOKEN_SQL
                            + " FROM (VALUES (%s::text, %s::double precision)) "
                            "AS e(token, entry_price)",
                            (entry_price.hex(), entry_price),
                        )
                        self.assertEqual(cursor.fetchone(), (False, True))
                for invalid_token in ("not-a-float", "177.06"):
                    with self.subTest(invalid_token=invalid_token):
                        cursor.execute(
                            "SELECT e.token = "
                            + sim4_entry_module._ENTRY_PRICE_CANONICAL_TOKEN_SQL
                            + " FROM (VALUES (%s::text, %s::double precision)) "
                            "AS e(token, entry_price)",
                            (invalid_token, 177.06),
                        )
                        self.assertEqual(cursor.fetchone(), (False,))

    def test_horizon_lock_accepts_only_postgres_void_representations(self):
        intent = build_intent()
        existing = build_simulation_entry_record(
            intent=intent, entry_status="SKIPPED_WINDOW_EXPIRED")
        for lock_rows in ([], [(None,)], [("",)]):
            with self.subTest(lock_rows=lock_rows):
                cursor = ScriptedCursor([
                    ("current_user", self.authority()),
                    ("pg_advisory_xact_lock", lock_rows),
                    ("WHERE intent_id", [entry_row(existing)]),
                ])
                store = SimulationEntryStore(
                    FakeConnection(cursor), project_ref=PROJECT_REF)
                self.assertEqual(
                    store.get_existing_entry_in_transaction(cursor, intent),
                    existing)
                self.assertIn("current_user", cursor.executed[0][0])
                lock_sql, lock_parameters = cursor.executed[1]
                self.assertEqual(lock_sql,
                                 "SELECT pg_advisory_xact_lock(%s::bigint)")
                self.assertEqual(lock_parameters,
                                 (horizon_advisory_lock_key("30S"),))
                self.assertIn("WHERE intent_id", cursor.executed[2][0])
                self.assertEqual(len(cursor.executed), 3)
        for lock_rows in ([("x",)], [(True,)], [(0,)], [(None, None)],
                          [("", "")], [[None]]):
            with self.subTest(lock_rows=lock_rows):
                cursor = ScriptedCursor([
                    ("current_user", self.authority()),
                    ("pg_advisory_xact_lock", lock_rows),
                ])
                store = SimulationEntryStore(
                    FakeConnection(cursor), project_ref=PROJECT_REF)
                with self.assertRaises(SimulationEntryStateError):
                    store.get_existing_entry_in_transaction(cursor, intent)
                self.assertEqual(len(cursor.executed), 2)


if __name__ == "__main__":
    unittest.main()

