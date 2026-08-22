from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import math
import random
import unittest

from quant.v9_v1_contract import (
    DIRECTIONAL_BPS,
    HORIZONS,
    HORIZON_SECONDS,
    MAGNITUDE_BPS,
    QUANT_IDS,
    V1SlotObservation,
    build_v1_input,
    build_v1_output,
    v1_input_hash,
)


class V9V1ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cutoff = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
        self.slots = [
            V1SlotObservation(
                quant_id=quant_id,
                formula_version=f"{quant_id}-frozen-v1",
                horizon=horizon,
                horizon_seconds=HORIZON_SECONDS[horizon],
                numerical_type=(MAGNITUDE_BPS if quant_id == "q3_volatility"
                                else DIRECTIONAL_BPS),
                value_bps=2.5,
                forecast_cutoff_at=self.cutoff - timedelta(seconds=10),
                source_as_of_at=self.cutoff - timedelta(seconds=11),
                available_at=self.cutoff - timedelta(seconds=9),
                data_schema_version="schema-1",
                source_spec_version="source-1",
            )
            for quant_id in QUANT_IDS for horizon in HORIZONS
        ]

    def build(self, slots=None, **changes):
        arguments = dict(
            cycle_id="cycle-1", cutoff_at=self.cutoff, target_spec_id="target-1",
            data_schema_version="schema-1", source_spec_version="source-1",
            slots=self.slots if slots is None else slots,
        )
        arguments.update(changes)
        return build_v1_input(**arguments)

    def with_slot(self, index=0, **changes):
        slots = list(self.slots)
        slots[index] = replace(slots[index], **changes)
        return slots

    def test_exact_canonical_dimensions_types_and_order(self) -> None:
        shuffled = list(self.slots)
        random.Random(17).shuffle(shuffled)
        contract = self.build(shuffled)
        self.assertEqual(len(contract.slots), 72)
        self.assertEqual(len({slot.quant_id for slot in contract.slots}), 12)
        self.assertTrue(all(sum(s.quant_id == q for s in contract.slots) == 6
                            for q in QUANT_IDS))
        self.assertEqual(tuple((s.quant_id, s.horizon) for s in contract.slots),
                         tuple((q, h) for q in QUANT_IDS for h in HORIZONS))
        self.assertEqual(contract.horizons, HORIZONS)
        for slot in contract.slots:
            expected = MAGNITUDE_BPS if slot.quant_id == "q3_volatility" else DIRECTIONAL_BPS
            self.assertEqual(slot.numerical_type, expected)

    def test_missing_stays_none_and_session_unavailable_discards_value(self) -> None:
        missing = self.build(self.with_slot(value_bps=None)).slots[0]
        self.assertEqual(missing.availability_state, "MISSING")
        self.assertIsNone(missing.value_bps)
        session = self.build(self.with_slot(value_bps=99.0,
                                            reason_code="SESSION_UNAVAILABLE")).slots[0]
        self.assertEqual((session.availability_state, session.reason_code),
                         ("MISSING", "SESSION_UNAVAILABLE"))
        self.assertIsNone(session.value_bps)

    def test_freshness_uses_family_forecast_cutoff(self) -> None:
        fresh = self.build().slots[0]
        self.assertEqual((fresh.availability_state, fresh.age_ms), ("FRESH", 10000))
        stale = self.build(self.with_slot(
            forecast_cutoff_at=self.cutoff - timedelta(seconds=10, microseconds=1)
        )).slots[0]
        self.assertEqual(stale.availability_state, "STALE")

    def test_semantic_invalid_observations(self) -> None:
        cases = (
            ({"numerical_type": MAGNITUDE_BPS}, "WRONG_NUMERICAL_TYPE"),
            ({"horizon_seconds": 31}, "WRONG_HORIZON_SECONDS"),
            ({"data_schema_version": "schema-2"}, "VERSION_MISMATCH"),
            ({"value_bps": math.nan}, "INVALID_NUMERIC_VALUE"),
            ({"value_bps": math.inf}, "INVALID_NUMERIC_VALUE"),
            ({"value_bps": -math.inf}, "INVALID_NUMERIC_VALUE"),
            ({"forecast_cutoff_at": self.cutoff + timedelta(microseconds=1)},
             "FUTURE_TIMESTAMP"),
            ({"source_as_of_at": self.cutoff + timedelta(microseconds=1)},
             "FUTURE_TIMESTAMP"),
            ({"available_at": self.cutoff + timedelta(microseconds=1)},
             "FUTURE_TIMESTAMP"),
        )
        for changes, reason in cases:
            with self.subTest(changes=changes):
                slot = self.build(self.with_slot(**changes)).slots[0]
                self.assertEqual((slot.availability_state, slot.reason_code),
                                 ("INVALID", reason))
                self.assertIsNone(slot.value_bps)
        q3_index = 2 * len(HORIZONS)
        q3 = self.build(self.with_slot(q3_index, value_bps=-0.01)).slots[q3_index]
        self.assertEqual((q3.availability_state, q3.reason_code),
                         ("INVALID", "NEGATIVE_MAGNITUDE"))
        self.assertIsNone(q3.value_bps)

    def test_structural_and_causality_rejections(self) -> None:
        cases = (
            self.slots + [self.slots[0]],
            self.with_slot(quant_id="q13_unknown"),
            self.with_slot(horizon="2H"),
            self.slots[:-1],
        )
        for slots in cases:
            with self.subTest(length=len(slots)), self.assertRaises(ValueError):
                self.build(slots)
        with self.assertRaises(ValueError):
            self.build(evidence_state_as_of=self.cutoff + timedelta(microseconds=1))
        with self.assertRaises(ValueError):
            self.build(symbol="QQQ")

    def test_contracts_are_deeply_immutable(self) -> None:
        contract = self.build()
        with self.assertRaises(FrozenInstanceError):
            contract.symbol = "QQQ"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            contract.slots[0].value_bps = 0.0  # type: ignore[misc]

    def test_sha256_hash_is_canonical_and_content_sensitive(self) -> None:
        first = self.build()
        shuffled = list(self.slots)
        random.Random(23).shuffle(shuffled)
        second = self.build(shuffled)
        self.assertEqual(v1_input_hash(first), v1_input_hash(second))
        digest = v1_input_hash(first)
        self.assertEqual(len(digest), 64)
        changed = self.build(self.with_slot(value_bps=2.6))
        self.assertNotEqual(digest, v1_input_hash(changed))
        invalid = self.build(self.with_slot(value_bps=math.nan))
        self.assertEqual(len(v1_input_hash(invalid)), 64)

    def test_evidence_references_default_to_none(self) -> None:
        contract = self.build()
        self.assertIsNone(contract.evidence_state_id)
        self.assertIsNone(contract.evidence_state_version)
        self.assertIsNone(contract.evidence_state_hash)
        self.assertIsNone(contract.evidence_state_as_of)
        self.assertIsNone(contract.evidence_training_start)
        self.assertIsNone(contract.evidence_training_end)

    def test_output_is_six_unavailable_non_synthesis_shells(self) -> None:
        output = build_v1_output(self.build(), model_version="no-synthesis-v1")
        self.assertEqual(output.computation_status, "UNAVAILABLE")
        self.assertEqual(tuple(r.horizon for r in output.horizon_results), HORIZONS)
        self.assertEqual(len(output.horizon_results), 6)
        for result in output.horizon_results:
            self.assertEqual(result.status, "UNAVAILABLE")
            self.assertIn("SYNTHESIS_NOT_IMPLEMENTED_V1", result.reason_codes)
            self.assertIsNone(result.expected_return_bps)
            self.assertIsNone(result.move_percent)
            self.assertIsNone(result.range_lower_bps)
            self.assertIsNone(result.range_upper_bps)
            self.assertIsNone(result.predictive_scale_bps)
            self.assertIsNone(result.effective_family_count)
            self.assertIsNone(result.meaningful_move_probabilities)


if __name__ == "__main__":
    unittest.main()
