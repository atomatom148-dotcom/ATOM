"""Phase C1 proofs for volatility/friction evidence."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.models import SetupState
from quant.vol_friction import VolFrictionPolicy, evaluate_vol_friction


POLICY = VolFrictionPolicy(minimum_volatility=0.01, maximum_friction=0.002)


class PhaseC1VolFrictionTests(unittest.TestCase):
    def test_evidence_at_thresholds_is_qualified(self) -> None:
        evidence = evaluate_vol_friction(0.01, 0.002, POLICY)

        self.assertEqual(evidence.setup_state, SetupState.QUALIFIED)
        self.assertEqual(evidence.volatility, 0.01)
        self.assertEqual(evidence.friction, 0.002)
        self.assertEqual(evidence.reason_codes, ())

    def test_excess_friction_is_blocked_before_volatility(self) -> None:
        evidence = evaluate_vol_friction(0.0, 0.003, POLICY)

        self.assertEqual(evidence.setup_state, SetupState.BLOCKED)
        self.assertEqual(evidence.reason_codes, ("FRICTION_TOO_HIGH",))

    def test_low_volatility_is_a_valid_non_setup(self) -> None:
        evidence = evaluate_vol_friction(0.009, 0.001, POLICY)

        self.assertEqual(evidence.setup_state, SetupState.NO_SETUP)
        self.assertEqual(evidence.reason_codes, ("VOLATILITY_TOO_LOW",))

    def test_missing_evidence_is_unavailable_not_zero(self) -> None:
        cases = (
            (None, 0.001, ("MISSING_VOLATILITY",)),
            (0.02, None, ("MISSING_FRICTION",)),
            (None, None, ("MISSING_VOLATILITY", "MISSING_FRICTION")),
        )
        for volatility, friction, reasons in cases:
            with self.subTest(volatility=volatility, friction=friction):
                evidence = evaluate_vol_friction(volatility, friction, POLICY)
                self.assertEqual(evidence.setup_state, SetupState.UNAVAILABLE)
                self.assertEqual(evidence.reason_codes, reasons)

    def test_invalid_evidence_is_unavailable(self) -> None:
        for value in (-1.0, math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value):
                volatility = evaluate_vol_friction(value, 0.001, POLICY)
                friction = evaluate_vol_friction(0.02, value, POLICY)
                self.assertEqual(volatility.setup_state, SetupState.UNAVAILABLE)
                self.assertEqual(volatility.reason_codes, ("INVALID_VOLATILITY",))
                self.assertEqual(friction.setup_state, SetupState.UNAVAILABLE)
                self.assertEqual(friction.reason_codes, ("INVALID_FRICTION",))

    def test_policy_rejects_invalid_thresholds(self) -> None:
        for value in (-1.0, math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    VolFrictionPolicy(value, 0.002)
                with self.assertRaises(ValueError):
                    VolFrictionPolicy(0.01, value)


if __name__ == "__main__":
    unittest.main()
