import dataclasses
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest

from quant.v9_v3_synthesis import (
    CONTRACT_VERSION as V3_CONTRACT_VERSION, MODEL_VERSION, V3HorizonResult,
)
from quant.v9_v4a_evidence import (
    CONTRACT_VERSION, EVIDENCE_VERSION, REPLAY_METHOD_VERSION,
    MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS, TARGET_ENDPOINT_DELAY_REASON,
    DuplicateConflict, build_cohort, build_forecast, build_outcome,
    V4AWriter, canonical_sha256, canonical_target_identity,
    classify_duplicate, select_non_overlapping,
)


UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def upstream():
    slots = tuple(SimpleNamespace(quant_id=q, formula_version=f, horizon="1M")
                  for q, f in (("q2_mean_reversion", "f2"), ("q1_momentum", "f1")))
    v1 = SimpleNamespace(symbol="COIN", cutoff_at=T0, cycle_id="cycle",
                         contract_version="V9-V1",
                         target_spec_id="target-1", data_schema_version="data-1",
                         source_spec_version="source-1", slots=slots)
    v2 = SimpleNamespace(v2a_method_version="a", v2b_method_version="b",
        v2c_method_version="c", effective_n_method_version="n",
        calibration_method_version="cal", covariance_method_version="cov",
        numerical_canonicalization_version="hex", state_id="v2-state:one",
        state_version="V9-V2D-2", state_hash="1" * 64,
        state_as_of=T0.timestamp())
    result = V3HorizonResult("1M", 60, 1.25, 4.0, "MATURE",
                             ("q1_momentum",), (1.0,), 1, "FULL",
                             q3_diagnostic_magnitude_bps=None)
    return v1, v2, result


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.insert_count = 0
        self.last_insert_parameters = None
        self.closed = False
        self.statements = []

    def execute(self, sql, _parameters):
        self.statements.append((sql, _parameters))
        if sql.startswith("INSERT"):
            self.insert_count += 1
            self.last_insert_parameters = _parameters

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class V4AContractTests(unittest.TestCase):
    def forecast(self, origin="PRODUCTION"):
        return build_forecast(v1=upstream()[0], v2=upstream()[1],
                              result=upstream()[2], evidence_origin=origin)

    def test_frozen_versions_and_complete_v3_contract_identity(self):
        f = self.forecast()
        self.assertEqual((f.contract_version, f.evidence_version),
                         (CONTRACT_VERSION, EVIDENCE_VERSION))
        self.assertEqual(f.v3_contract_version, V3_CONTRACT_VERSION)
        self.assertEqual(f.v3_model_version, "ATOM-TRUE-V9-V3")

    def test_forecast_is_immutable_and_bps_can_remain_null(self):
        f = self.forecast()
        self.assertIsNone(f.q3_diagnostic_magnitude_bps)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            f.status = "changed"

    def test_forecast_preserves_exact_v2_state_provenance(self):
        f = self.forecast()
        self.assertEqual(f.v2_state_id, "v2-state:one")
        self.assertEqual(f.v2_state_version, "V9-V2D-2")
        self.assertEqual(f.v2_state_hash, "1" * 64)
        self.assertEqual(f.v2_state_as_of, T0.timestamp())

        cursor = FakeCursor([])
        V4AWriter(FakeConnection(cursor)).persist_forecast(f, T0)
        record_json = json.loads(cursor.last_insert_parameters[8])
        self.assertEqual(record_json["v2_state_id"], f.v2_state_id)
        self.assertEqual(record_json["v2_state_version"], f.v2_state_version)
        self.assertEqual(record_json["v2_state_hash"], f.v2_state_hash)
        self.assertEqual(record_json["v2_state_as_of"],
                         {"$float64": f.v2_state_as_of.hex()})

    def test_forecast_ledger_contains_complete_causal_identity(self):
        v1, v2, result = upstream()
        forecast = build_forecast(
            v1=v1, v2=v2, result=result, evidence_origin="PRODUCTION",
            cutoff_midpoint=101.25,
        )
        self.assertEqual(forecast.v1_contract_version, "V9-V1")
        self.assertRegex(forecast.v1_input_hash, r"^[0-9a-f]{64}$")
        self.assertEqual(forecast.v3_contract_version, V3_CONTRACT_VERSION)
        self.assertEqual(forecast.v3_model_version, MODEL_VERSION)
        self.assertEqual(forecast.target_spec_id, "target-1")
        self.assertEqual(forecast.data_schema_version, "data-1")
        self.assertEqual(forecast.source_spec_version, "source-1")
        self.assertEqual(forecast.cutoff_midpoint, 101.25)
        self.assertEqual(forecast.used_quant_ids, ("q1_momentum",))
        self.assertEqual(forecast.family_weights, (1.0,))
        self.assertEqual(forecast.directional_input_count, 1)
        self.assertEqual(forecast.covariance_mode, "FULL")
        self.assertFalse(forecast.q3_used)
        self.assertEqual((forecast.gamma, forecast.phi), (0.0, 1.0))

    def test_v2_state_provenance_changes_record_but_not_cohort_identity(self):
        v1, v2, result = upstream()
        original = build_forecast(v1=v1, v2=v2, result=result,
                                  evidence_origin="PRODUCTION")

        variants = []
        for changes in (
            {"state_id": "v2-state:two"},
            {"state_hash": "2" * 64},
            {"state_as_of": v2.state_as_of + 1.0},
        ):
            values = vars(v2).copy()
            values.update(changes)
            variants.append(build_forecast(
                v1=v1, v2=SimpleNamespace(**values), result=result,
                evidence_origin="PRODUCTION"))

        for variant in variants:
            self.assertEqual(variant.cohort_id, original.cohort_id)
            self.assertEqual(variant.cohort_hash, original.cohort_hash)
            self.assertNotEqual(variant.forecast_record_hash,
                                original.forecast_record_hash)
            self.assertNotEqual(variant.forecast_record_id,
                                original.forecast_record_id)

    def test_forecast_hash_deterministic_and_metadata_excluded(self):
        f = self.forecast()
        self.assertEqual(f.forecast_record_hash, self.forecast().forecast_record_hash)
        self.assertEqual(f.forecast_record_hash,
                         dataclasses.replace(f, persisted_at=T0 + timedelta(seconds=1)).forecast_record_hash)
        self.assertTrue(f.forecast_record_id.startswith("v9v4f:"))

    def test_evidence_origin_participates_in_forecast_hash(self):
        self.assertNotEqual(self.forecast().forecast_record_hash,
                            self.forecast("CAUSAL_REPLAY").forecast_record_hash)

    def test_rejects_non_durable_fixture_origin(self):
        with self.assertRaises(ValueError):
            self.forecast("TEST")

    def test_cohort_is_deterministic_and_map_is_order_independent(self):
        v1, v2, _ = upstream()
        one = build_cohort(v1=v1, v2=v2, horizon="1M",
                           family_formula_map={"q10_options_vol": "f10",
                                               "q2_mean_reversion": "f2",
                                               "q9_factor": "f9"})
        two = build_cohort(v1=v1, v2=v2, horizon="1M",
                           family_formula_map={"q9_factor": "f9",
                                               "q10_options_vol": "f10",
                                               "q2_mean_reversion": "f2"})
        self.assertEqual(one, two)
        self.assertTrue(one.cohort_id.startswith("v9v4cohort:"))
        payload = dict(one.payload)
        self.assertEqual(payload["compatible_family_formula_map"], (
            ("q2_mean_reversion", "f2"), ("q9_factor", "f9"),
            ("q10_options_vol", "f10")))
        self.assertEqual(payload["v2_method_lineage"], ("a", "b", "c", "n", "cal", "cov", "hex"))
        self.assertEqual(payload["replay_method_version"], REPLAY_METHOD_VERSION)

    def test_canonical_binary64_and_nonfinite_rejection(self):
        self.assertEqual(canonical_sha256({"x": 1.5}), canonical_sha256({"x": float.fromhex("0x1.8p0")}))
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                canonical_sha256(value)

    def test_duplicate_classification(self):
        self.assertEqual(classify_duplicate("abc", "abc"), "IDEMPOTENT")
        self.assertEqual(classify_duplicate(None, "abc"), "INSERT")
        with self.assertRaisesRegex(DuplicateConflict, "FORECAST_DUPLICATE_CONFLICT"):
            classify_duplicate("abc", "def")
        with self.assertRaisesRegex(DuplicateConflict, "OUTCOME_CONFLICT"):
            classify_duplicate("abc", "def", outcome=True)

    def test_outcome_contract_timing_and_hash(self):
        f = dataclasses.replace(self.forecast(), persisted_at=T0)
        observed = f.target_endpoint + timedelta(seconds=3)
        o = build_outcome(forecast=f, target_identity="close:1", endpoint_observation_at=observed,
                          target_resolved_at=observed + timedelta(seconds=1), actual_return_bps=2.5)
        self.assertEqual(o.endpoint_observation_at, observed)
        self.assertEqual(o.endpoint_observation_delay, 3.0)
        self.assertEqual(o.target_timing_status, "UNVERIFIED")
        self.assertIn("TARGET_TIMING_UNVERIFIED", o.reason_codes)
        self.assertFalse(o.proof_eligible)
        self.assertEqual(o.outcome_record_hash, dataclasses.replace(o, created_at=T0).outcome_record_hash)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            o.proof_eligible = True

    def test_first_observation_at_or_after_endpoint_is_verified(self):
        v1, v2, result = upstream()
        forecast = build_forecast(
            v1=v1, v2=v2, result=result, evidence_origin="PRODUCTION",
            cutoff_midpoint=100.0,
        )
        forecast = dataclasses.replace(
            forecast, persisted_at=T0,
            persistence_proof_eligible=True,
        )
        previous = forecast.target_endpoint - timedelta(microseconds=1)
        observed = forecast.target_endpoint + timedelta(microseconds=1)
        outcome = build_outcome(
            forecast=forecast,
            target_identity=canonical_target_identity(forecast),
            previous_observation_at=previous,
            endpoint_observation_at=observed,
            target_resolved_at=observed,
            actual_return_bps=2.5,
        )
        self.assertEqual(outcome.target_timing_status, "VERIFIED")
        self.assertTrue(outcome.proof_eligible)
        self.assertEqual(outcome.reason_codes, ())
        self.assertEqual(outcome.previous_observation_at, previous)

    def test_endpoint_observation_delay_is_bounded_at_five_seconds(self):
        forecast = dataclasses.replace(
            self.forecast(), persisted_at=T0,
            persistence_proof_eligible=True,
        )
        previous = forecast.target_endpoint - timedelta(microseconds=1)

        boundary = build_outcome(
            forecast=forecast,
            target_identity=canonical_target_identity(forecast),
            previous_observation_at=previous,
            endpoint_observation_at=(
                forecast.target_endpoint + timedelta(
                    seconds=MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS)),
            target_resolved_at=(
                forecast.target_endpoint + timedelta(
                    seconds=MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS)),
            actual_return_bps=2.5,
        )
        late = build_outcome(
            forecast=forecast,
            target_identity=canonical_target_identity(forecast),
            previous_observation_at=previous,
            endpoint_observation_at=(
                forecast.target_endpoint + timedelta(
                    seconds=MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS,
                    microseconds=1)),
            target_resolved_at=(
                forecast.target_endpoint + timedelta(
                    seconds=MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS,
                    microseconds=1)),
            actual_return_bps=2.5,
        )

        self.assertEqual(boundary.target_timing_status, "VERIFIED")
        self.assertTrue(boundary.proof_eligible)
        self.assertNotIn(TARGET_ENDPOINT_DELAY_REASON, boundary.reason_codes)
        self.assertEqual(late.target_timing_status, "VERIFIED")
        self.assertFalse(late.proof_eligible)
        self.assertIn(TARGET_ENDPOINT_DELAY_REASON, late.reason_codes)

    def test_overlap_revalidates_legacy_delay_claims(self):
        forecast = dataclasses.replace(
            self.forecast(), persisted_at=T0,
            persistence_proof_eligible=True,
        )
        late = build_outcome(
            forecast=forecast,
            target_identity=canonical_target_identity(forecast),
            previous_observation_at=forecast.target_endpoint - timedelta(seconds=1),
            endpoint_observation_at=forecast.target_endpoint + timedelta(hours=17),
            target_resolved_at=forecast.target_endpoint + timedelta(hours=17),
            actual_return_bps=2.5,
        )
        forged_legacy = dataclasses.replace(
            late, proof_eligible=True, reason_codes=(),
        )

        selection = select_non_overlapping(((forecast, forged_legacy),))
        forged_delay = dataclasses.replace(
            forged_legacy, endpoint_observation_delay=0.0,
        )

        self.assertEqual(selection.raw_resolved_n, 0)
        self.assertEqual(selection.selected_ids, ())
        self.assertEqual(
            select_non_overlapping(((forecast, forged_delay),)).raw_resolved_n,
            0,
        )

    def test_forecast_commit_observation_uses_strict_boundary(self):
        f = self.forecast()
        before = V4AWriter._apply_commit_proof(f, (
            f.forecast_record_id, f.forecast_record_hash,
            f.target_endpoint - timedelta(microseconds=1), f.target_endpoint,
            True, "POST_COMMIT_DB_OBSERVATION_V1",
        ))
        equal = V4AWriter._apply_commit_proof(f, (
            f.forecast_record_id, f.forecast_record_hash,
            f.target_endpoint, f.target_endpoint,
            False, "POST_COMMIT_DB_OBSERVATION_V1",
        ))
        after = V4AWriter._apply_commit_proof(f, (
            f.forecast_record_id, f.forecast_record_hash,
            f.target_endpoint + timedelta(microseconds=1), f.target_endpoint,
            False, "POST_COMMIT_DB_OBSERVATION_V1",
        ))
        self.assertTrue(before.persistence_proof_eligible)
        self.assertFalse(equal.persistence_proof_eligible)
        self.assertFalse(after.persistence_proof_eligible)
        self.assertEqual(
            equal.persistence_reason,
            "FORECAST_COMMITTED_AT_OR_AFTER_TARGET_ENDPOINT",
        )
        o = build_outcome(
            forecast=equal,
            target_identity="t",
            endpoint_observation_at=equal.target_endpoint,
            target_resolved_at=equal.target_endpoint,
            actual_return_bps=0.0,
        )
        self.assertIn(
            "FORECAST_COMMITTED_AT_OR_AFTER_TARGET_ENDPOINT", o.reason_codes,
        )

    def test_persist_forecast_starts_fail_closed_until_db_observation(self):
        f = self.forecast()
        cursor = FakeCursor([])
        stored = V4AWriter(FakeConnection(cursor)).persist_forecast(f, T0)
        self.assertFalse(stored.persistence_proof_eligible)
        self.assertIsNone(stored.persisted_at)
        self.assertEqual(stored.persistence_reason, "FORECAST_COMMIT_PROOF_MISSING")
        record_json = json.loads(cursor.last_insert_parameters[8])
        self.assertFalse(record_json["persistence_proof_eligible"])
        self.assertEqual(
            record_json["persistence_reason"], "FORECAST_COMMIT_PROOF_MISSING",
        )

    def test_record_and_read_proof_use_only_scoped_database_functions(self):
        f = self.forecast()
        observed = f.target_endpoint - timedelta(microseconds=1)
        row = (
            f.forecast_record_id, f.forecast_record_hash, observed,
            f.target_endpoint, True, "POST_COMMIT_DB_OBSERVATION_V1",
        )
        for method_name, sql_token in (
            ("record_forecast_commit_proof", "record_forecast_commit_proof"),
            ("read_forecast_commit_proof", "read_forecast_commit_proof"),
        ):
            cursor = FakeCursor([row])
            connection = FakeConnection(cursor)
            hydrated = getattr(V4AWriter(connection), method_name)(f)
            self.assertTrue(hydrated.persistence_proof_eligible)
            self.assertEqual(hydrated.persisted_at, observed)
            self.assertIn(sql_token, cursor.statements[0][0])
            self.assertEqual(connection.commits, 1)

    def test_overlap_boundary_order_and_digest(self):
        base = self.forecast()
        def pair(offset):
            f = dataclasses.replace(base, cutoff_at=T0 + timedelta(seconds=offset),
                                    forecast_record_id=f"v9v4f:{offset:064x}",
                                    forecast_record_hash=f"{offset:064x}")
            o = build_outcome(forecast=dataclasses.replace(f, persisted_at=f.cutoff_at),
                target_identity=str(offset), endpoint_observation_at=f.target_endpoint,
                target_resolved_at=f.target_endpoint, actual_return_bps=0.0)
            return f, dataclasses.replace(o, proof_eligible=True)
        pairs = [pair(60), pair(59), pair(0), pair(120)]
        a = select_non_overlapping(pairs)
        b = select_non_overlapping(reversed(pairs))
        self.assertEqual(a.selected_ids, (pairs[2][0].forecast_record_id,
                                          pairs[0][0].forecast_record_id,
                                          pairs[3][0].forecast_record_id))
        self.assertEqual(a, b)
        self.assertEqual(a.selected_digest, b.selected_digest)
        self.assertEqual((a.raw_resolved_n, a.non_overlapping_n), (4, 3))

    def test_overlap_excludes_entire_conflicting_forecast_group(self):
        first = self.forecast()
        first_outcome = build_outcome(
            forecast=dataclasses.replace(first, persisted_at=T0), target_identity="target",
            endpoint_observation_at=first.target_endpoint,
            target_resolved_at=first.target_endpoint, actual_return_bps=1.0)
        first_pair = first, dataclasses.replace(first_outcome, proof_eligible=True)
        conflict = dataclasses.replace(first, forecast_record_hash="a" * 64,
                                       forecast_record_id="v9v4f:" + "a" * 64)
        conflict_outcome = build_outcome(
            forecast=dataclasses.replace(conflict, persisted_at=T0), target_identity="target",
            endpoint_observation_at=conflict.target_endpoint,
            target_resolved_at=conflict.target_endpoint, actual_return_bps=2.0)
        conflict_pair = conflict, dataclasses.replace(conflict_outcome, proof_eligible=False)

        unrelated = dataclasses.replace(first, cutoff_at=T0 + timedelta(seconds=60),
            forecast_record_hash="b" * 64, forecast_record_id="v9v4f:" + "b" * 64)
        unrelated_outcome = build_outcome(
            forecast=dataclasses.replace(unrelated, persisted_at=unrelated.cutoff_at),
            target_identity="target", endpoint_observation_at=unrelated.target_endpoint,
            target_resolved_at=unrelated.target_endpoint, actual_return_bps=3.0)
        unrelated_pair = unrelated, dataclasses.replace(unrelated_outcome, proof_eligible=True)

        forward = select_non_overlapping((first_pair, conflict_pair, unrelated_pair))
        reverse = select_non_overlapping((unrelated_pair, conflict_pair, first_pair))
        self.assertEqual(forward, reverse)
        self.assertEqual(forward.raw_resolved_n, 1)
        self.assertEqual(forward.selected_ids, (unrelated.forecast_record_id,))
        self.assertEqual(forward.selected_digest, reverse.selected_digest)

    def test_overlap_identical_duplicates_are_canonical_not_conflicts(self):
        forecast = self.forecast()
        outcome = build_outcome(
            forecast=dataclasses.replace(forecast, persisted_at=T0), target_identity="target",
            endpoint_observation_at=forecast.target_endpoint,
            target_resolved_at=forecast.target_endpoint, actual_return_bps=1.0)
        pair = forecast, dataclasses.replace(outcome, proof_eligible=True)
        selection = select_non_overlapping((pair, pair))
        self.assertEqual(selection.non_overlapping_n, 1)
        self.assertEqual(selection.selected_ids, (forecast.forecast_record_id,))

    def test_overlap_excludes_conflicting_outcomes_only_for_their_key(self):
        forecast = self.forecast()
        outcome = build_outcome(
            forecast=dataclasses.replace(forecast, persisted_at=T0), target_identity="target",
            endpoint_observation_at=forecast.target_endpoint,
            target_resolved_at=forecast.target_endpoint, actual_return_bps=1.0)
        conflict = dataclasses.replace(outcome, outcome_record_hash="c" * 64,
                                       outcome_record_id="v9v4o:" + "c" * 64)
        conflicting_pairs = (
            (forecast, dataclasses.replace(outcome, proof_eligible=True)),
            (forecast, dataclasses.replace(conflict, proof_eligible=True)),
        )
        other_horizon = dataclasses.replace(
            forecast, horizon="5M", horizon_seconds=300,
            forecast_record_hash="d" * 64, forecast_record_id="v9v4f:" + "d" * 64)
        other_outcome = build_outcome(
            forecast=dataclasses.replace(other_horizon, persisted_at=T0),
            target_identity="target", endpoint_observation_at=other_horizon.target_endpoint,
            target_resolved_at=other_horizon.target_endpoint, actual_return_bps=4.0)
        other_pair = other_horizon, dataclasses.replace(other_outcome, proof_eligible=True)

        selection = select_non_overlapping((*conflicting_pairs, other_pair))
        self.assertEqual(selection.raw_resolved_n, 1)
        self.assertEqual(selection.selected_ids, (other_horizon.forecast_record_id,))

    def test_writer_locks_and_rejects_forecast_conflicts_without_insert(self):
        f = self.forecast()
        cursor = FakeCursor([(f.forecast_record_hash,)])
        connection = FakeConnection(cursor)
        writer = V4AWriter(connection)
        writer.persist_forecast(f, T0)
        self.assertEqual(writer.last_write_status, "IDEMPOTENT")
        self.assertEqual(cursor.insert_count, 0)
        self.assertEqual((connection.commits, connection.rollbacks), (1, 0))
        self.assertTrue(cursor.closed)

        conflicting = dataclasses.replace(f, forecast_record_hash="f" * 64,
                                           forecast_record_id="v9v4f:" + "f" * 64)
        cursor = FakeCursor([(f.forecast_record_hash,)])
        writer = V4AWriter(FakeConnection(cursor))
        stored = writer.persist_forecast(conflicting, T0)
        self.assertEqual(writer.last_write_status, "FORECAST_DUPLICATE_CONFLICT")
        self.assertEqual(cursor.insert_count, 0)
        self.assertFalse(stored.persistence_proof_eligible)
        self.assertEqual(
            cursor.statements[0][0],
            "SELECT pg_catalog.pg_advisory_xact_lock(%s)",
        )
        self.assertIsInstance(cursor.statements[0][1][0], int)

    def test_writer_locks_and_rejects_outcome_conflicts_without_insert(self):
        f = dataclasses.replace(self.forecast(), persisted_at=T0)
        o = build_outcome(forecast=f, target_identity="target",
                          endpoint_observation_at=f.target_endpoint,
                          target_resolved_at=f.target_endpoint, actual_return_bps=1.0)
        cursor = FakeCursor([(o.outcome_record_hash,)])
        writer = V4AWriter(FakeConnection(cursor))
        writer.persist_outcome(o, T0)
        self.assertEqual(writer.last_write_status, "IDEMPOTENT")
        self.assertEqual(cursor.insert_count, 0)

        conflicting = dataclasses.replace(o, outcome_record_hash="e" * 64,
                                           outcome_record_id="v9v4o:" + "e" * 64)
        cursor = FakeCursor([(o.outcome_record_hash,)])
        writer = V4AWriter(FakeConnection(cursor))
        writer.persist_outcome(conflicting, T0)
        self.assertEqual(writer.last_write_status, "OUTCOME_CONFLICT")
        self.assertEqual(cursor.insert_count, 0)
        self.assertEqual(
            cursor.statements[0][0],
            "SELECT pg_catalog.pg_advisory_xact_lock(%s)",
        )

    def test_writer_refuses_autocommit_that_would_release_lock_before_check(self):
        connection = FakeConnection(FakeCursor([]))
        connection.autocommit = True
        with self.assertRaisesRegex(ValueError, "requires a transaction"):
            V4AWriter(connection)

    def test_historical_multi_hash_groups_always_fail_closed(self):
        forecast = self.forecast()
        cursor = FakeCursor([
            (forecast.forecast_record_hash,), ("f" * 64,),
        ])
        writer = V4AWriter(FakeConnection(cursor))
        stored = writer.persist_forecast(forecast, T0)
        self.assertEqual(writer.last_write_status, "FORECAST_DUPLICATE_CONFLICT")
        self.assertEqual(cursor.insert_count, 0)
        self.assertFalse(stored.persistence_proof_eligible)

        persisted = dataclasses.replace(forecast, persisted_at=T0)
        outcome = build_outcome(
            forecast=persisted, target_identity="target",
            endpoint_observation_at=persisted.target_endpoint,
            target_resolved_at=persisted.target_endpoint,
            actual_return_bps=1.0,
        )
        cursor = FakeCursor([
            (outcome.outcome_record_hash,), ("e" * 64,),
        ])
        writer = V4AWriter(FakeConnection(cursor))
        writer.persist_outcome(outcome, T0)
        self.assertEqual(writer.last_write_status, "OUTCOME_CONFLICT")
        self.assertEqual(cursor.insert_count, 0)

    def test_logical_lock_key_is_stable_signed_and_kind_separated(self):
        key = self.forecast().logical_key
        forecast_key = V4AWriter._logical_lock_id("FORECAST", key)
        self.assertEqual(
            forecast_key, V4AWriter._logical_lock_id("FORECAST", key),
        )
        self.assertNotEqual(
            forecast_key, V4AWriter._logical_lock_id("OUTCOME", key),
        )
        self.assertTrue(-(2**63) <= forecast_key < 2**63)

    def test_advisory_lock_serializes_concurrent_logical_writers(self):
        class SharedDatabase:
            def __init__(self):
                self.rows = []
                self.locks = {}
                self.guard = threading.Lock()

        class Cursor:
            def __init__(self, connection):
                self.connection = connection
                self.rows = ()
            def execute(self, sql, parameters):
                if "pg_advisory_xact_lock" in sql:
                    with self.connection.database.guard:
                        lock = self.connection.database.locks.setdefault(
                            parameters[0], threading.Lock())
                    lock.acquire()
                    self.connection.held.append(lock)
                elif sql.startswith("SELECT forecast_record_hash"):
                    with self.connection.database.guard:
                        self.rows = tuple(self.connection.database.rows)
                elif sql.startswith("INSERT INTO atom_v9_v4_forecasts"):
                    with self.connection.database.guard:
                        self.connection.database.rows.append(
                            (parameters[1], parameters[8]))
            def fetchall(self): return self.rows
            def close(self): pass

        class Connection:
            autocommit = False
            def __init__(self, database):
                self.database = database
                self.held = []
            def cursor(self): return Cursor(self)
            def commit(self):
                while self.held:
                    self.held.pop().release()
            rollback = commit

        def persist(database, record, statuses, barrier):
            writer = V4AWriter(Connection(database))
            barrier.wait()
            writer.persist_forecast(record, T0)
            statuses.append(writer.last_write_status)

        forecast = self.forecast()
        for candidates, expected in (
            ((forecast, forecast), {"INSERT", "IDEMPOTENT"}),
            ((forecast, dataclasses.replace(
                forecast, forecast_record_hash="f" * 64,
                forecast_record_id="v9v4f:" + "f" * 64,
            )), {"INSERT", "FORECAST_DUPLICATE_CONFLICT"}),
        ):
            database, statuses = SharedDatabase(), []
            barrier = threading.Barrier(2)
            threads = [threading.Thread(
                target=persist, args=(database, candidate, statuses, barrier),
            ) for candidate in candidates]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=1)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(set(statuses), expected)
            self.assertEqual(len(database.rows), 1)


class V4AMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (Path(__file__).parents[1] / "migrations" /
                   "008_create_v9_v4a_evidence.sql").read_text()
        cls.upper = " ".join(cls.sql.upper().split())

    def test_exactly_two_tables_and_no_existing_evidence_table_mutation(self):
        self.assertEqual(self.upper.count("CREATE TABLE"), 2)
        self.assertIn("CREATE TABLE PUBLIC.ATOM_V9_V4_FORECASTS", self.upper)
        self.assertIn("CREATE TABLE PUBLIC.ATOM_V9_V4_OUTCOMES", self.upper)
        self.assertNotIn("UPDATE PUBLIC.FORECASTS", self.upper)
        self.assertNotIn("DELETE FROM PUBLIC.FORECASTS", self.upper)
        self.assertNotIn("TRUNCATE TABLE PUBLIC.FORECASTS", self.upper)
        self.assertNotIn("INSERT INTO PUBLIC.FORECASTS", self.upper)
        self.assertNotIn("UNIQUE (SYMBOL, CUTOFF_AT, HORIZON, CYCLE_ID, V3_MODEL_VERSION)", self.upper)
        self.assertNotIn("UNIQUE (FORECAST_RECORD_ID, TARGET_IDENTITY)", self.upper)
        self.assertIn("FORECAST_RECORD_ID TEXT PRIMARY KEY", self.upper)
        self.assertIn("FORECAST_RECORD_HASH TEXT NOT NULL UNIQUE", self.upper)
        self.assertIn("OUTCOME_RECORD_ID TEXT PRIMARY KEY", self.upper)
        self.assertIn("OUTCOME_RECORD_HASH TEXT NOT NULL UNIQUE", self.upper)

    def test_database_mutation_rejection_and_least_privilege(self):
        self.assertEqual(self.upper.count("BEFORE UPDATE OR DELETE ON"), 2)
        self.assertEqual(self.upper.count("BEFORE TRUNCATE ON"), 2)
        self.assertEqual(self.upper.count("FOR EACH ROW"), 2)
        self.assertEqual(self.upper.count("FOR EACH STATEMENT"), 2)
        self.assertIn("GRANT SELECT, INSERT ON TABLE", self.upper)
        self.assertNotIn("GRANT UPDATE", self.upper)
        self.assertNotIn("GRANT DELETE", self.upper)
        self.assertNotIn("GRANT TRUNCATE", self.upper)


if __name__ == "__main__":
    unittest.main()

class V4CommitObservationMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (Path(__file__).parents[1] / "migrations" /
                   "014_add_v4_forecast_commit_observations.sql").read_text()
        cls.upper = " ".join(cls.sql.upper().split())

    def test_private_append_only_proof_store_and_no_backfill(self):
        self.assertIn("CREATE SCHEMA ATOM_V9_INTERNAL", self.upper)
        self.assertIn("CREATE TABLE ATOM_V9_INTERNAL.FORECAST_COMMIT_PROOFS", self.upper)
        self.assertIn("BEFORE UPDATE OR DELETE", self.upper)
        self.assertIn("BEFORE TRUNCATE", self.upper)
        self.assertNotIn("UPDATE PUBLIC.ATOM_V9_V4_FORECASTS", self.upper)
        self.assertNotIn("TRACK_COMMIT_TIMESTAMP", self.upper)
        self.assertNotIn("ALTER SYSTEM", self.upper)

    def test_separate_transaction_installation_fence_and_strict_boundary(self):
        self.assertIn("V_XID = PG_CATALOG.PG_CURRENT_XACT_ID()", self.upper)
        self.assertIn("V_XID <= V_NOT_BEFORE_XID", self.upper)
        self.assertIn("(COMMIT_OBSERVED_AT < TARGET_ENDPOINT) STORED", self.upper)
        self.assertIn("POST_COMMIT_DB_OBSERVATION_V1", self.upper)

    def test_runtime_has_function_only_access(self):
        self.assertIn(
            "REVOKE ALL ON TABLE ATOM_V9_INTERNAL.FORECAST_COMMIT_PROOFS "
            "FROM PUBLIC, ANON, AUTHENTICATED, SERVICE_ROLE, ATOM_V9_V4_RUNTIME",
            self.upper,
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION "
            "ATOM_V9_INTERNAL.RECORD_FORECAST_COMMIT_PROOF(TEXT) "
            "TO ATOM_V9_V4_RUNTIME",
            self.upper,
        )
        self.assertIn("CREATE ROLE ATOM_V9_PROOF_OWNER WITH NOLOGIN NOINHERIT NOSUPERUSER", self.upper)

    def test_supabase_owner_handoff_is_transactional_and_revoked(self):
        self.assertEqual(
            self.upper.count("GRANT ATOM_V9_PROOF_OWNER TO POSTGRES"), 1,
        )
        self.assertEqual(
            self.upper.count("REVOKE ATOM_V9_PROOF_OWNER FROM POSTGRES"), 1,
        )
        self.assertLess(
            self.upper.index("GRANT ATOM_V9_PROOF_OWNER TO POSTGRES"),
            self.upper.index("OWNER TO ATOM_V9_PROOF_OWNER"),
        )
        self.assertGreater(
            self.upper.index("REVOKE ATOM_V9_PROOF_OWNER FROM POSTGRES"),
            self.upper.rindex("OWNER TO ATOM_V9_PROOF_OWNER"),
        )


class V4ProofAuthorizationMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = (Path(__file__).parents[1] / "migrations" /
                   "016_authorize_v4_proof_reader_and_harden_search_path.sql").read_text()
        cls.upper = " ".join(cls.sql.upper().split())

    def test_proof_owner_policy_and_role_guard_are_exact(self):
        self.assertIn(
            "CREATE POLICY ATOM_V9_V4_FORECASTS_PROOF_OWNER_SELECT "
            "ON PUBLIC.ATOM_V9_V4_FORECASTS FOR SELECT "
            "TO ATOM_V9_PROOF_OWNER USING (TRUE)",
            self.upper,
        )
        for attribute in (
            "NOT ROLCANLOGIN", "NOT ROLINHERIT", "NOT ROLSUPER",
            "NOT ROLCREATEDB", "NOT ROLCREATEROLE", "NOT ROLREPLICATION",
            "NOT ROLBYPASSRLS",
        ):
            self.assertIn(attribute, self.upper)
        self.assertNotIn("ALTER ROLE", self.upper)

    def test_legacy_trigger_search_path_is_hardened_without_evidence_dml(self):
        self.assertIn(
            "ALTER FUNCTION PUBLIC.REJECT_EVIDENCE_MUTATION() "
            "SET SEARCH_PATH = PG_CATALOG",
            self.upper,
        )
        for operation in ("UPDATE ", "DELETE FROM", "TRUNCATE ", "INSERT INTO"):
            self.assertNotIn(operation, self.upper)
        self.assertNotIn("GRANT ", self.upper)
        self.assertNotIn("ATOM_V9_INTERNAL.", self.upper)
