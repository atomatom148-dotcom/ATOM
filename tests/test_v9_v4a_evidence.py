import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from quant.v9_v3_synthesis import MODEL_VERSION, V3HorizonResult
from quant.v9_v4a_evidence import (
    CONTRACT_VERSION, EVIDENCE_VERSION, REPLAY_METHOD_VERSION,
    DuplicateConflict, build_cohort, build_forecast, build_outcome,
    V4AWriter, canonical_sha256, classify_duplicate, select_non_overlapping,
)


UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def upstream():
    slots = tuple(SimpleNamespace(quant_id=q, formula_version=f, horizon="1M")
                  for q, f in (("q2_mean_reversion", "f2"), ("q1_momentum", "f1")))
    v1 = SimpleNamespace(symbol="COIN", cutoff_at=T0, cycle_id="cycle",
                         target_spec_id="target-1", data_schema_version="data-1",
                         source_spec_version="source-1", slots=slots)
    v2 = SimpleNamespace(v2a_method_version="a", v2b_method_version="b",
        v2c_method_version="c", effective_n_method_version="n",
        calibration_method_version="cal", covariance_method_version="cov",
        numerical_canonicalization_version="hex")
    result = V3HorizonResult("1M", 60, 1.25, 4.0, "AVAILABLE",
                             ("q1_momentum",), (1.0,), 1, "FULL",
                             q3_diagnostic_magnitude_bps=None)
    return v1, v2, result


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.insert_count = 0

    def execute(self, sql, _parameters):
        if sql.startswith("INSERT"):
            self.insert_count += 1

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class V4AContractTests(unittest.TestCase):
    def forecast(self, origin="PRODUCTION"):
        return build_forecast(v1=upstream()[0], v2=upstream()[1],
                              result=upstream()[2], evidence_origin=origin)

    def test_frozen_versions_and_nullable_v3_contract(self):
        f = self.forecast()
        self.assertEqual((f.contract_version, f.evidence_version),
                         (CONTRACT_VERSION, EVIDENCE_VERSION))
        self.assertIsNone(f.v3_contract_version)
        self.assertEqual(f.v3_model_version, "ATOM-TRUE-V9-V3")

    def test_forecast_is_immutable_and_bps_can_remain_null(self):
        f = self.forecast()
        self.assertIsNone(f.q3_diagnostic_magnitude_bps)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            f.status = "changed"

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

    def test_forecast_persistence_deadline_boundary(self):
        f = self.forecast()
        on_time = dataclasses.replace(f, persisted_at=f.target_endpoint,
                                      persistence_proof_eligible=True)
        late = dataclasses.replace(f, persisted_at=f.target_endpoint + timedelta(microseconds=1),
                                   persistence_proof_eligible=False,
                                   persistence_reason="FORECAST_PERSISTED_AFTER_TARGET_ENDPOINT")
        self.assertTrue(on_time.persistence_proof_eligible)
        o = build_outcome(forecast=late, target_identity="t", endpoint_observation_at=late.target_endpoint,
                          target_resolved_at=late.target_endpoint, actual_return_bps=0.0)
        self.assertIn("FORECAST_PERSISTED_AFTER_TARGET_ENDPOINT", o.reason_codes)

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

    def test_writer_preserves_forecast_conflicts_and_idempotency(self):
        f = self.forecast()
        cursor = FakeCursor([(f.forecast_record_hash,)])
        writer = V4AWriter(FakeConnection(cursor))
        writer.persist_forecast(f, T0)
        self.assertEqual(writer.last_write_status, "IDEMPOTENT")
        self.assertEqual(cursor.insert_count, 0)

        conflicting = dataclasses.replace(f, forecast_record_hash="f" * 64,
                                           forecast_record_id="v9v4f:" + "f" * 64)
        cursor = FakeCursor([(f.forecast_record_hash,)])
        writer = V4AWriter(FakeConnection(cursor))
        stored = writer.persist_forecast(conflicting, T0)
        self.assertEqual(writer.last_write_status, "FORECAST_DUPLICATE_CONFLICT")
        self.assertEqual(cursor.insert_count, 1)
        self.assertFalse(stored.persistence_proof_eligible)

    def test_writer_preserves_outcome_conflicts_and_idempotency(self):
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
        self.assertEqual(cursor.insert_count, 1)


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
        self.assertNotIn("ALTER TABLE PUBLIC.FORECASTS", self.upper)
        self.assertNotIn("ALTER TABLE PUBLIC.FORECAST_OUTCOMES", self.upper)
        self.assertNotIn("UNIQUE (SYMBOL, CUTOFF_AT, HORIZON, CYCLE_ID, V3_MODEL_VERSION)", self.upper)
        self.assertNotIn("UNIQUE (FORECAST_RECORD_ID, TARGET_IDENTITY)", self.upper)
        self.assertIn("FORECAST_RECORD_ID TEXT PRIMARY KEY", self.upper)
        self.assertIn("FORECAST_RECORD_HASH TEXT NOT NULL UNIQUE", self.upper)
        self.assertIn("OUTCOME_RECORD_ID TEXT PRIMARY KEY", self.upper)
        self.assertIn("OUTCOME_RECORD_HASH TEXT NOT NULL UNIQUE", self.upper)

    def test_database_mutation_rejection_and_least_privilege(self):
        self.assertEqual(self.upper.count("BEFORE UPDATE OR DELETE OR TRUNCATE"), 2)
        self.assertIn("GRANT SELECT, INSERT ON TABLE", self.upper)
        self.assertNotIn("GRANT UPDATE", self.upper)
        self.assertNotIn("GRANT DELETE", self.upper)
        self.assertNotIn("GRANT TRUNCATE", self.upper)


if __name__ == "__main__":
    unittest.main()
