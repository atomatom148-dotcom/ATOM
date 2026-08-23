import json
from unittest.mock import patch

import pytest
from quant.live_market import LiveMarketState
from quant.v9_v4d_integration import OperationalMetrics
from quant.web import create_app


def _request(app, path):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({"PATH_INFO": path}, start_response))
    return response


def test_every_request_path_is_contained_from_historical_work_even_on_failure():
    class PoisonStore:
        def counts(self):
            raise AssertionError("request attempted an evidence scan")

        def phase_e_cohorts(self, _as_of):
            raise AssertionError("request attempted a cohort rebuild")

    state = LiveMarketState()
    app = create_app(state=state, evidence_store=PoisonStore())
    poison = AssertionError("request attempted a historical build")
    with patch("quant.v9_production.PostgresV2StateBuilder.build", side_effect=poison), \
         patch("quant.v9_v2b_calibration.build_v2b_calibration", side_effect=poison), \
         patch("quant.v9_v2d_evidence_state.build_v2d_evidence_state", side_effect=poison), \
         patch("quant.web.calculate_momentum", side_effect=poison), \
         patch("quant.web.calculate_mean_reversion", side_effect=poison), \
         patch("quant.web.calculate_volatility", side_effect=poison):
        for path in ("/health", "/", "/api/live", "/api/dashboard"):
            assert _request(app, path)["status"] == "200 OK"


def test_failed_family_is_excluded_without_retry_imputation_or_cycle_failure():
    state = LiveMarketState()
    with patch("quant.live_market.calculate_momentum",
               side_effect=RuntimeError("unavailable")) as failed:
        assert state.accept_quote(bid=99.0, ask=101.0, event_epoch=100.0)
    snapshot = state.snapshot()
    assert failed.call_count == 1
    assert snapshot.momentum is None
    assert snapshot.mean_reversion is not None
    assert snapshot.volatility is not None


def test_latency_percentiles_are_available_at_bounded_telemetry_endpoint():
    ticks = iter((1.0, 1.001))
    metrics = OperationalMetrics()
    response = _request(create_app(
        metrics=metrics, monotonic_clock=lambda: next(ticks),
    ), "/health")
    assert response["status"] == "200 OK"

    ticks = iter((2.0, 2.001))
    payload = json.loads(_request(create_app(
        metrics=metrics, monotonic_clock=lambda: next(ticks),
    ), "/api/performance")["body"])
    distributions = dict(payload["distributions"])
    health = distributions["web_endpoint./health.duration_ms"]
    assert health["count"] == 1
    assert health["p50"] == health["p95"] == health["p99"] == pytest.approx(1.0)
