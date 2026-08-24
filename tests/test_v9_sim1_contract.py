from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
import json
import math
import unittest
from unittest.mock import patch

from quant.v9_v4a_evidence import _canonical, canonical_sha256
from quant.v9_sim1_contract import (
    HORIZONS, HORIZON_SECONDS, IDENTITY_PREFIX, INSTRUMENT,
    SIM_CANONICALIZATION_VERSION, SIM_INTENT_CONTRACT_VERSION,
    SIMULATION_MODE, SIMULATOR_VERSION, SYMBOL, SimulationTradeIntent,
    build_simulation_trade_intent, deserialize_simulation_trade_intent,
    serialize_simulation_trade_intent,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
UTC = timezone.utc


def build(**changes):
    values = dict(
        source_cycle_id="cycle-1", source_forecast_record_id="v9v4f:source",
        source_forecast_record_hash=HASH_A, source_v2_state_id="v9v2:state",
        source_v2_state_hash=HASH_B, source_v3_contract_version="V3-C",
        source_v3_model_version="V3-M",
        cutoff_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
        eligible_at=datetime(2026, 8, 24, 12, 0, 0, 1, tzinfo=UTC),
        horizon="30S", horizon_seconds=30, final_bps=1.25,
        source_v3_status="AVAILABLE",
    )
    values.update(changes)
    return build_simulation_trade_intent(**values)


class SimulationTradeIntentTests(unittest.TestCase):
    def test_exact_constants_horizons_and_fields(self):
        self.assertEqual(SIM_INTENT_CONTRACT_VERSION, "ATOM_TRUE_V9_SIM1_INTENT_1")
        self.assertEqual(SIMULATOR_VERSION, "ATOM_TRUE_V9_SIM_1")
        self.assertEqual(SIM_CANONICALIZATION_VERSION, "ATOM_TRUE_V9_SIM_CANONICAL_V4A_1")
        self.assertEqual((SIMULATION_MODE, IDENTITY_PREFIX, SYMBOL, INSTRUMENT),
                         ("PAPER_ONLY", "v9simintent:", "COIN", "COIN_SHARE"))
        expected = {"30S": 30, "1M": 60, "5M": 300, "15M": 900,
                    "30M": 1800, "1H": 3600}
        self.assertEqual(dict(HORIZON_SECONDS), expected)
        self.assertEqual(HORIZONS, tuple(expected))
        self.assertEqual(tuple(f.name for f in fields(SimulationTradeIntent)), (
            "contract_version", "canonicalization_version", "simulator_version",
            "intent_id", "intent_hash", "mode", "symbol", "instrument",
            "source_cycle_id", "source_forecast_record_id",
            "source_forecast_record_hash", "source_v2_state_id",
            "source_v2_state_hash", "source_v3_contract_version",
            "source_v3_model_version", "cutoff_at", "eligible_at", "horizon",
            "horizon_seconds", "final_bps", "source_v3_status", "decision",
            "status", "quantity_shares"))

    def test_frozen_slotted_and_no_nested_mutability(self):
        intent = build()
        with self.assertRaises(FrozenInstanceError):
            intent.status = "NO_TRADE"
        self.assertFalse(hasattr(intent, "__dict__"))
        with self.assertRaises(TypeError):
            HORIZON_SECONDS["X"] = 2

    def test_every_horizon_pair(self):
        for horizon, seconds in HORIZON_SECONDS.items():
            with self.subTest(horizon=horizon):
                self.assertEqual(build(horizon=horizon, horizon_seconds=seconds).horizon_seconds,
                                 seconds)
                with self.assertRaises(ValueError):
                    build(horizon=horizon, horizon_seconds=seconds + 1)
        with self.assertRaises(ValueError):
            build(horizon="2H", horizon_seconds=7200)

    def test_exact_decision_mapping_and_provisional_preservation(self):
        cases = ((2.0, "AVAILABLE", "LONG", "ACTIONABLE", 1),
                 (-2.0, "PROVISIONAL", "SHORT", "ACTIONABLE", 1),
                 (0.0, "AVAILABLE", "NO_TRADE", "NO_TRADE", 0),
                 (-0.0, "PROVISIONAL", "NO_TRADE", "NO_TRADE", 0),
                 (None, "UNAVAILABLE", "NO_TRADE", "UNAVAILABLE", 0))
        for value, source, decision, status, quantity in cases:
            intent = build(final_bps=value, source_v3_status=source)
            self.assertEqual((intent.decision, intent.status, intent.quantity_shares),
                             (decision, status, quantity))
            self.assertEqual(intent.source_v3_status, source)

    def test_invalid_status_numbers_and_direct_construction(self):
        for value in (math.nan, math.inf, -math.inf, True, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build(final_bps=value)
        with self.assertRaises(ValueError):
            build(final_bps=1.0, source_v3_status="UNAVAILABLE")
        with self.assertRaises(ValueError):
            build(source_v3_status="MATURE")
        base = build()
        for changes in (dict(decision="SHORT"), dict(status="NO_TRADE"),
                        dict(quantity_shares=True), dict(horizon_seconds=True)):
            with self.assertRaises(ValueError):
                replace(base, **changes)
        with self.assertRaises(ValueError):
            replace(base, intent_hash="f" * 64)
        with self.assertRaises(ValueError):
            replace(base, intent_id=IDENTITY_PREFIX + "f" * 64)

    def test_datetime_boundaries_and_equivalent_instants(self):
        naive = datetime(2026, 8, 24, 12)
        with self.assertRaises(ValueError):
            build(cutoff_at=naive)
        with self.assertRaises(ValueError):
            build(eligible_at=naive)
        cutoff = datetime(2026, 8, 24, 12, tzinfo=UTC)
        with self.assertRaises(ValueError):
            build(cutoff_at=cutoff, eligible_at=cutoff - timedelta(microseconds=1))
        east = timezone(timedelta(hours=2))
        equivalent = build(cutoff_at=cutoff.astimezone(east),
                           eligible_at=build().eligible_at.astimezone(east))
        self.assertEqual(equivalent.intent_hash, build().intent_hash)

    def test_canonical_golden_float_zero_and_determinism(self):
        self.assertEqual(_canonical(1.5), {"$float64": "0x1.8000000000000p+0"})
        positive = build(final_bps=0.0)
        negative = build(final_bps=-0.0)
        self.assertEqual(positive.intent_hash, negative.intent_hash)
        self.assertEqual(serialize_simulation_trade_intent(positive),
                         serialize_simulation_trade_intent(negative))
        self.assertEqual(build().intent_hash, build().intent_hash)
        self.assertEqual(build().intent_id, IDENTITY_PREFIX + build().intent_hash)

    def test_hash_covers_all_math_fields_and_excludes_identity_fields(self):
        base = build()
        variants = {
            "contract_version": "bad", "canonicalization_version": "bad",
            "simulator_version": "bad", "mode": "bad", "symbol": "bad",
            "instrument": "bad", "source_cycle_id": "cycle-2",
            "source_forecast_record_id": "v9v4f:other",
            "source_forecast_record_hash": "c" * 64,
            "source_v2_state_id": "v9v2:other", "source_v2_state_hash": "d" * 64,
            "source_v3_contract_version": "V3-C2", "source_v3_model_version": "V3-M2",
            "cutoff_at": base.cutoff_at + timedelta(microseconds=1),
            "eligible_at": base.eligible_at + timedelta(microseconds=1),
            "horizon": "1M", "horizon_seconds": 60, "final_bps": 2.0,
            "source_v3_status": "PROVISIONAL", "decision": "SHORT",
            "status": "NO_TRADE", "quantity_shares": 0,
        }
        math_payload = {f.name: getattr(base, f.name) for f in fields(base)
                        if f.name not in ("intent_id", "intent_hash")}
        for name, value in variants.items():
            changed = dict(math_payload)
            changed[name] = value
            self.assertNotEqual(canonical_sha256(changed), base.intent_hash, name)
        self.assertEqual(canonical_sha256(math_payload), base.intent_hash)

    def test_round_trip_strict_shape_and_tamper_detection(self):
        intent = build()
        encoded = serialize_simulation_trade_intent(intent)
        self.assertEqual(deserialize_simulation_trade_intent(encoded), intent)
        self.assertEqual(deserialize_simulation_trade_intent(json.loads(encoded)), intent)
        for mutation in ("missing", "unknown", "hash", "id"):
            payload = json.loads(encoded)
            if mutation == "missing":
                payload.pop("symbol")
            elif mutation == "unknown":
                payload["extra"] = 1
            elif mutation == "hash":
                payload["intent_hash"] = "f" * 64
            else:
                payload["intent_id"] = "v9simintent:tampered"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                deserialize_simulation_trade_intent(payload)
        for malformed in ("not json", "[]", '{"cutoff_at":{"$timestamp_utc":3}}'):
            with self.assertRaises(ValueError):
                deserialize_simulation_trade_intent(malformed)

    def test_pure_contract_operations_have_no_external_or_clock_side_effects(self):
        forbidden = ("builtins.open", "socket.socket", "sqlite3.connect",
                     "time.time", "urllib.request.urlopen")
        with patch(forbidden[0]) as file_open, patch(forbidden[1]) as network, \
                patch(forbidden[2]) as database, patch(forbidden[3]) as clock, \
                patch(forbidden[4]) as web:
            intent = build()
            self.assertEqual(deserialize_simulation_trade_intent(
                serialize_simulation_trade_intent(intent)), intent)
        for external in (file_open, network, database, clock, web):
            external.assert_not_called()


if __name__ == "__main__":
    unittest.main()
