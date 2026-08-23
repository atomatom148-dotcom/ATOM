import json
import os
import unittest
from unittest.mock import Mock, patch

import quant.v9_telemetry as telemetry_module
from quant.live_market import LiveMarketState, _observe_v9
from quant.v9_math_core import V9MathInput, V9MathState, V9QuantFamily
from quant.v9_telemetry import latest_v9_observation, record_v9_observation
from quant.web import create_app


def request(app, path):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({"PATH_INFO": path}, start_response))
    return response


class V9TelemetryTests(unittest.TestCase):
    def setUp(self):
        with telemetry_module._telemetry_lock:
            telemetry_module._latest_telemetry = None

    def tearDown(self):
        with telemetry_module._telemetry_lock:
            telemetry_module._latest_telemetry = None

    def test_disabled_endpoint_is_honest_and_does_no_work(self):
        state = Mock()
        store = Mock()
        clock = Mock()
        with patch.dict(os.environ, {}, clear=True), patch(
            "quant.web.latest_v9_observation"
        ) as latest:
            response = request(create_app(state=state, evidence_store=store,
                                          clock=clock), "/api/v9-math")

        self.assertEqual(json.loads(response["body"]), {
            "enabled": False, "status": "DISABLED", "family_count": 0,
            "non_null_variable_count": 0, "as_of_epoch": None,
        })
        latest.assert_not_called()
        state.snapshot.assert_not_called()
        store.assert_not_called()
        clock.assert_not_called()

    def test_enabled_endpoint_before_observation(self):
        with patch.dict(os.environ, {"V9_MATH_CORE_ENABLED": "true"}, clear=True):
            payload = json.loads(request(create_app(), "/api/v9-math")["body"])
        self.assertEqual(payload, {
            "enabled": True, "status": "NO_OBSERVATION_YET", "family_count": 0,
            "non_null_variable_count": 0, "as_of_epoch": None,
        })

    def test_success_reports_real_counts_epoch_and_exact_status(self):
        value = V9MathInput("COIN", 123.25, (
            V9QuantFamily("q1", "v1", (1.0, None, 0.0, None, 2.0, 3.0)),
            V9QuantFamily("q2", "v1", (None, None, 4.0, None, None, 5.0)),
        ))
        record_v9_observation(value, V9MathState("COIN", 123.25, "OBSERVING"))

        with patch.dict(os.environ, {"V9_MATH_CORE_ENABLED": "true"}, clear=True):
            payload = json.loads(request(create_app(), "/api/v9-math")["body"])
        self.assertEqual(payload, {
            "enabled": True, "status": "OBSERVING", "family_count": 2,
            "non_null_variable_count": 6, "as_of_epoch": 123.25,
        })

    def test_latest_success_replaces_previous_and_failure_preserves_it(self):
        first = V9MathInput("COIN", 1.0, (
            V9QuantFamily("q1", "v1", (1.0,) * 6),
        ))
        second = V9MathInput("COIN", 2.0, (
            V9QuantFamily("q1", "v1", (None,) * 6),
            V9QuantFamily("q2", "v1", (2.0,) * 6),
        ))
        record_v9_observation(first, V9MathState("COIN", 1.0, "OBSERVING"))
        record_v9_observation(second, V9MathState("COIN", 2.0, "OBSERVING"))
        latest = latest_v9_observation()
        self.assertEqual((latest.family_count, latest.non_null_variable_count,
                          latest.as_of_epoch), (2, 6, 2.0))

        with patch.dict(os.environ, {"V9_MATH_CORE_ENABLED": "true"}, clear=True), patch(
            "quant.live_market.build_v9_quant_snapshot", side_effect=RuntimeError("failed")
        ):
            _observe_v9(Mock(), symbol="COIN", as_of_epoch=3.0)
        self.assertEqual(latest_v9_observation(), latest)

    def test_enabled_cycle_records_observation_without_changing_evidence(self):
        evidence = Mock()
        with patch.dict(os.environ, {"V9_MATH_CORE_ENABLED": "true"}, clear=True):
            state = LiveMarketState(clock=lambda: 10.0, evidence_outbox=evidence)
            self.assertTrue(state.accept_quote(bid=99.0, ask=101.0, event_epoch=1.0))

        latest = latest_v9_observation()
        self.assertEqual(latest.status, "OBSERVING")
        self.assertEqual(latest.family_count, 3)
        self.assertLess(latest.non_null_variable_count, 72)
        self.assertEqual(latest.as_of_epoch, 1.0)
        evidence.put_nowait.assert_called_once()

    def test_endpoint_only_reads_telemetry(self):
        observation = telemetry_module.V9ObservationTelemetry(
            "OBSERVING", 1, 2, 3.0,
        )
        state = Mock()
        store = Mock()
        clock = Mock()
        with patch.dict(os.environ, {"V9_MATH_CORE_ENABLED": "true"}, clear=True), patch(
            "quant.web.latest_v9_observation", return_value=observation
        ) as latest, patch("quant.live_market.build_v9_quant_snapshot") as build, patch(
            "quant.live_market.V9MathCore.evaluate"
        ) as evaluate:
            payload = json.loads(request(create_app(
                state=state, evidence_store=store, clock=clock,
            ), "/api/v9-math")["body"])

        self.assertEqual(payload["status"], "OBSERVING")
        latest.assert_called_once_with()
        build.assert_not_called()
        evaluate.assert_not_called()
        state.snapshot.assert_not_called()
        store.assert_not_called()
        clock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
