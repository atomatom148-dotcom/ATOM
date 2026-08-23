import json
import subprocess
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from quant.history import MidpointHistory, MidpointObservation
from quant.evidence import PhaseECohortMetrics
from quant.live_market import LiveMarketState
from quant.web import (DashboardEvidenceCache, FAMILY_NAMES, HORIZON_LABELS,
                       PHASE_E_FAMILY_NAMES, create_app, dashboard_data)


def request(app, path):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({"PATH_INFO": path}, start_response))
    return response


class ImmediateThread:
    def __init__(self, *, target, args, daemon):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


class WebSurfaceTests(unittest.TestCase):
    def test_page_route_loads_and_renders_nulls_as_blanks(self):
        response = request(create_app(), "/")
        self.assertEqual(response["status"], "200 OK")
        page = response["body"].decode()
        self.assertIn("ATOM QUANT", page)
        self.assertIn("12 QUANT FAMILIES", page)
        self.assertNotIn(">None<", page)

    def test_json_route_has_frozen_order_without_request_time_calculation(self):
        history = MidpointHistory(
            MidpointObservation(float(second), 100.0 + second / 100.0)
            for second in range(0, 3601, 30)
        )
        response = request(create_app(history, cutoff_epoch=3600.0), "/api/dashboard")
        self.assertEqual(response["status"], "200 OK")
        payload = json.loads(response["body"])
        self.assertEqual(payload["horizons"], list(HORIZON_LABELS))
        self.assertEqual([item["name"] for item in payload["quant_families"]], list(FAMILY_NAMES))
        for family in payload["quant_families"]:
            self.assertEqual(len(family["values"]), 6)
            self.assertEqual(family["values"], [None] * 6)

    def test_unavailable_fields_are_null_and_not_fabricated(self):
        payload = dashboard_data()
        self.assertTrue(all(values == [None] * 6 for values in payload["final_numbers"].values()))
        self.assertEqual(payload["options_data"], {"expiration": None, "calls": [], "puts": []})
        self.assertTrue(all(value is None for value in payload["evidence"].values()))
        self.assertTrue(all(value is None for family in payload["quant_families"] for value in family["values"]))
        self.assertIsNone(payload["market"]["data_age"])
        self.assertIsNone(payload["market"]["event_epoch"])
        self.assertEqual(payload["v9"], {"forecast_cutoff": None, "forecast_age": None})
        self.assertIsNone(payload["market"]["last_cycle"])

    def test_page_formats_live_values_without_rounding_api_values(self):
        history = MidpointHistory((MidpointObservation(1_700_000_000.0, 123.4567),))
        app = create_app(history, cutoff_epoch=1_700_000_000.0, clock=lambda: 1_700_000_001.234)

        page = request(app, "/")["body"].decode()
        payload = json.loads(request(app, "/api/dashboard")["body"])

        self.assertIn('data-dashboard-field="market.symbol">123.46</div>', page)
        self.assertIn('data-dashboard-field="market.data_age">1.23s</div>', page)
        self.assertIn('data-dashboard-field="market.last_cycle">22:13:20 UTC</div>', page)
        self.assertEqual(payload["market"]["symbol"], 123.4567)
        self.assertAlmostEqual(payload["market"]["data_age"], 1.234)
        self.assertEqual(payload["market"]["last_cycle"], 1_700_000_000.0)

    def test_page_does_not_calculate_q1_q3_from_request_history(self):
        history = MidpointHistory(
            MidpointObservation(float(second), 100.0 + second / 100.0)
            for second in range(0, 3601, 30)
        )
        app = create_app(history, cutoff_epoch=3600.0, clock=lambda: 3600.0)
        payload = json.loads(request(app, "/api/dashboard")["body"])
        page = request(app, "/")["body"].decode()

        self.assertTrue(all(value is None for family in payload["quant_families"]
                            for value in family["values"]))
        self.assertNotIn(">None<", page)

    def test_request_routes_never_invoke_history_calculators(self):
        app = create_app()
        with patch("quant.web.calculate_momentum", side_effect=AssertionError), \
             patch("quant.web.calculate_mean_reversion", side_effect=AssertionError), \
             patch("quant.web.calculate_volatility", side_effect=AssertionError):
            for path in ("/", "/api/dashboard", "/api/live"):
                self.assertEqual(request(app, path)["status"], "200 OK")

    def test_mobile_market_grid_uses_two_non_overlapping_columns(self):
        page = request(create_app(), "/")["body"].decode()
        self.assertIn(".market{grid-template-columns:repeat(2,minmax(0,1fr))}", page)

    def test_health_only_reports_process_running(self):
        class Store:
            def counts(self): raise AssertionError("health must not query evidence")
            def phase_e_cohorts(self, as_of):
                raise AssertionError("health must not evaluate Phase E")

        response = request(create_app(evidence_store=Store()), "/health")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(json.loads(response["body"]), {"status": "running"})

    def test_unknown_route_does_not_query_evidence(self):
        class Store:
            def counts(self): raise AssertionError("unknown route must not query evidence")
            def phase_e_cohorts(self, as_of):
                raise AssertionError("unknown route must not evaluate Phase E")

        response = request(create_app(evidence_store=Store()), "/favicon.ico")
        self.assertEqual(response["status"], "404 Not Found")
        self.assertEqual(response["body"], b"Not Found")

    def test_page_uses_non_overlapping_live_and_evidence_loops(self):
        page = request(create_app(), "/")["body"].decode()
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]

        self.assertIn('fetch("/api/live", {cache: "no-store"})', page)
        self.assertIn('fetch("/api/dashboard", {cache: "no-store"})', page)
        self.assertIn("setTimeout(refreshLive, 250)", page)
        self.assertIn("setTimeout(refreshEvidence, 30000)", page)
        self.assertNotIn("setInterval", page)
        self.assertNotIn("location.reload", page)
        self.assertNotIn("window.location", page)
        syntax_check = subprocess.run(
            ["node", "--check", "-"], input=script, text=True, capture_output=True)
        self.assertEqual(syntax_check.returncode, 0, syntax_check.stderr)

    def test_live_endpoint_is_read_only_and_uses_provider_time_for_age(self):
        class Store:
            def counts(self): raise AssertionError("live must not read evidence")
            def phase_e_cohorts(self, as_of):
                raise AssertionError("live must not calculate Phase E")

        state = LiveMarketState()
        state.update_market_display(
            coin_midpoint=100.01, coin_event_epoch=100.0,
            qqq_midpoint=500.01, qqq_event_epoch=101.0,
        )
        app = create_app(state=state, evidence_store=Store(), clock=lambda: 105.0)
        first = request(app, "/api/live")
        second = request(app, "/api/live")
        self.assertEqual(first["status"], "200 OK")
        payload = json.loads(first["body"])
        self.assertEqual(set(payload), {
            "market", "v9", "final_numbers", "quant_families", "options_data",
        })
        self.assertEqual(payload["market"]["symbol"], 100.01)
        self.assertEqual(payload["market"]["qqq"], 500.01)
        self.assertEqual(payload["market"]["data_age"], 5.0)
        self.assertEqual(json.loads(second["body"])["market"]["data_age"], 5.0)

    def test_live_endpoint_exposes_signed_market_and_v9_ages(self):
        state = LiveMarketState()
        state.update_market_display(
            coin_midpoint=100.01, coin_event_epoch=106.0,
            qqq_midpoint=500.01, qqq_event_epoch=106.0,
        )
        v9_output = SimpleNamespace(
            v1=SimpleNamespace(cutoff_at=datetime.fromtimestamp(100.0, timezone.utc)),
            final_numbers=(),
        )
        with patch.object(state, "v9_output", return_value=v9_output):
            payload = json.loads(request(
                create_app(state=state, clock=lambda: 105.0), "/api/live"
            )["body"])

        self.assertEqual(payload["market"]["event_epoch"], 106.0)
        self.assertEqual(payload["market"]["data_age"], -1.0)
        self.assertEqual(payload["v9"]["forecast_cutoff"], 100.0)
        self.assertEqual(payload["v9"]["forecast_age"], 5.0)

    def test_live_endpoint_falls_back_to_history_event_epoch(self):
        state = LiveMarketState()
        self.assertTrue(state.accept_quote(
            bid=100.0, ask=100.02, event_epoch=106.0,
        ))
        payload = json.loads(request(
            create_app(state=state, clock=lambda: 107.0), "/api/live"
        )["body"])

        self.assertEqual(payload["market"]["symbol"], (100.0 + 100.02) / 2.0)
        self.assertEqual(payload["market"]["event_epoch"], 106.0)
        self.assertEqual(payload["market"]["data_age"], 1.0)

    def test_live_endpoint_samples_clock_after_capturing_live_state(self):
        state = LiveMarketState()
        order = []

        def traced(name, function):
            def wrapper(*args, **kwargs):
                order.append(name)
                return function(*args, **kwargs)
            return wrapper

        for name in ("snapshot", "cross_asset_state", "market_display", "v9_output"):
            setattr(state, name, traced(name, getattr(state, name)))

        def clock():
            order.append("clock")
            return 107.0

        request(create_app(state=state, clock=clock), "/api/live")

        self.assertGreater(order.index("clock"), order.index("snapshot"))
        self.assertGreater(order.index("clock"), order.index("cross_asset_state"))
        self.assertGreater(order.index("clock"), order.index("market_display"))
        self.assertGreater(order.index("clock"), order.index("v9_output"))

    def test_live_renderer_updates_every_market_field(self):
        page = request(create_app(), "/")["body"].decode()

        for field in ("symbol", "btc", "qqq", "ndx", "data_age", "last_cycle"):
            self.assertIn(f'data-dashboard-field="market.{field}"', page)
            self.assertIn(f'set("market.{field}", data.market.{field}', page)

    def test_live_renderer_updates_final_quant_options_and_evidence_cells(self):
        page = request(create_app(), "/")["body"].decode()

        self.assertIn('data-dashboard-field="final_numbers.BPS.0"', page)
        self.assertIn('data-dashboard-field="quant_families.Momentum.0"', page)
        self.assertIn('data-dashboard-field="quant_families.Event/Session.5"', page)
        self.assertIn('data-dashboard-field="options_data.expiration"', page)
        self.assertIn('data-dashboard-field="evidence.Forecasts.0"', page)
        self.assertIn("Object.entries(data.final_numbers)", page)
        self.assertIn("data.quant_families.forEach", page)
        self.assertIn('["calls", "puts"].forEach', page)
        self.assertIn("<h3>CALLS</h3>", page)
        self.assertIn("<h3>PUTS</h3>", page)
        self.assertIn("Object.entries(data.evidence)", page)

    def test_live_renderer_blanks_null_values_without_fake_zeroes(self):
        page = request(create_app(), "/")["body"].decode()

        self.assertIn('value == null ? "" : String(value)', page)
        self.assertIn('value == null ? "" : Number(value).toFixed(2)', page)
        self.assertNotIn('value || 0', page)

    def test_poll_failure_keeps_values_and_allows_timeout_to_retry(self):
        page = request(create_app(), "/")["body"].decode()

        failure_handler = page.split("} catch (_) {", 1)[1].split("}", 1)[0]
        self.assertNotIn("render", failure_handler)
        self.assertNotIn("textContent", failure_handler)
        self.assertIn("setTimeout(refreshLive, 250)", page)

    def test_phase_e_dashboard_mapping_order_format_and_raw_precision(self):
        quant_ids = tuple(
            quant_id for quant_id in PHASE_E_FAMILY_NAMES
            if quant_id != "q3_volatility"
        )
        cohorts = tuple(
            PhaseECohortMetrics(
                quant_id, "v1", "COIN", "1H" if index == 0 else "30S",
                21, 20, 19, 0.999123, 2.3456, 0.514, 1.2345,
                None if index == 1 else -0.126, 20, index % 2 == 0,
            )
            for index, quant_id in enumerate(reversed(quant_ids))
        )

        class Store:
            def __init__(self): self.phase_calls = []
            def counts(self): return (123, 98)
            def phase_e_cohorts(self, as_of):
                self.phase_calls.append(as_of)
                return cohorts
            def volatility_phase_e_cohorts(self, as_of):
                self.phase_calls.append(as_of)
                return (PhaseECohortMetrics(
                    "q3_volatility", "v1", "COIN", "30S", 1, 1, 1,
                    1.0, 0.0, None, None, None, 1, False,
                ),)

        store = Store()
        cache = DashboardEvidenceCache(store, clock=lambda: 456.75)
        cache.refresh()
        app = create_app(evidence_cache=cache, clock=lambda: 456.75)
        payload = json.loads(request(app, "/api/dashboard")["body"])
        rows = payload["phase_e_cohorts"]

        self.assertEqual(store.phase_calls, [456.75, 456.75])
        self.assertEqual(payload["evidence"], {"Forecasts": 123, "Resolved": 98})
        self.assertEqual([row["family"] for row in rows], list(PHASE_E_FAMILY_NAMES.values()))
        self.assertIn("q3_volatility", [row["quant_id"] for row in rows])
        self.assertEqual(rows[0]["directional_accuracy"], 0.514)
        self.assertEqual(rows[0]["coverage"], 0.999123)
        self.assertEqual(rows[0]["rmse_bps"], 2.3456)

        page_app = create_app(evidence_cache=cache, clock=lambda: 456.75)
        page = request(page_app, "/")["body"].decode()
        self.assertIn("FAMILY/HORIZON", page)
        self.assertIn("EFFECTIVE N", page)
        self.assertIn(">YES<", page)
        self.assertIn(">NO<", page)
        self.assertIn(">51.4%<", page)
        self.assertIn(">99.9%<", page)
        self.assertIn(">2.35<", page)
        self.assertIn(">1.23<", page)
        self.assertIn(">-0.13<", page)
        self.assertNotIn(">None<", page)

    def test_dashboard_requests_only_read_the_background_cache(self):
        first = PhaseECohortMetrics(
            "q1_momentum", "v1", "COIN", "30S", 1, 1, 1,
            1.0, 1.0, 1.0, 1.0, 1.0, 1, False,
        )
        refreshed = PhaseECohortMetrics(
            "q1_momentum", "v1", "COIN", "30S", 2, 2, 2,
            1.0, 2.0, 1.0, 2.0, 1.0, 2, False,
        )

        class Store:
            def __init__(self):
                self.phase_calls = []
                self.count_calls = 0

            def counts(self):
                self.count_calls += 1
                return (self.count_calls, self.count_calls)

            def phase_e_cohorts(self, as_of):
                self.phase_calls.append(as_of)
                return (first,) if len(self.phase_calls) == 1 else (refreshed,)

        request_times = iter((101.0, 399.999, 400.0, 401.0))
        store = Store()
        history = MidpointHistory((MidpointObservation(90.0, 100.0),))
        refresh_times = iter((100.0, 400.0))
        cache = DashboardEvidenceCache(store, clock=lambda: next(refresh_times))
        cache.refresh()
        app = create_app(history, evidence_cache=cache,
                         clock=lambda: next(request_times))
        payloads = [json.loads(request(app, "/api/dashboard")["body"])
                    for _ in range(2)]
        cache.refresh()
        payloads.extend(json.loads(request(app, "/api/dashboard")["body"])
                        for _ in range(2))

        self.assertEqual(store.phase_calls, [100.0, 400.0])
        self.assertEqual(
            [payload["phase_e_cohorts"][0]["effective_n"]
             if payload["phase_e_cohorts"] else 0 for payload in payloads],
            [1, 1, 2, 2],
        )
        self.assertEqual([payload["evidence"]["Forecasts"] for payload in payloads],
                         [1, 1, 2, 2])
        for payload, expected_age in zip(
                payloads, (11.0, 309.999, 310.0, 311.0)):
            self.assertAlmostEqual(payload["market"]["data_age"], expected_age)

    def test_background_cache_refresh_fails_open_with_or_without_prior_state(self):
        cohort = PhaseECohortMetrics(
            "q1_momentum", "v1", "COIN", "30S", 1, 1, 1,
            1.0, 1.0, 1.0, 1.0, 1.0, 1, False,
        )

        class Store:
            def __init__(self, fail_first=False):
                self.calls = 0
                self.fail_first = fail_first

            def counts(self): return (0, 0)

            def phase_e_cohorts(self, as_of):
                self.calls += 1
                if self.fail_first or self.calls > 1:
                    raise RuntimeError("phase e unavailable")
                return (cohort,)

        stale_store = Store()
        stale_cache = DashboardEvidenceCache(stale_store, clock=lambda: 100.0)
        stale_cache.refresh()
        stale_app = create_app(evidence_cache=stale_cache, clock=lambda: 100.0)
        first = json.loads(request(stale_app, "/api/dashboard")["body"])
        stale_cache.refresh()
        stale = json.loads(request(stale_app, "/api/dashboard")["body"])
        self.assertEqual(stale["phase_e_cohorts"], first["phase_e_cohorts"])
        self.assertEqual(stale_store.calls, 2)

        empty_cache = DashboardEvidenceCache(Store(fail_first=True), clock=lambda: 100.0)
        empty_cache.refresh()
        empty_app = create_app(evidence_cache=empty_cache, clock=lambda: 100.0)
        empty = json.loads(request(empty_app, "/api/dashboard")["body"])
        self.assertEqual(empty["phase_e_cohorts"], [])

    def test_phase_e_endpoint_uses_same_snapshot_without_scanning(self):
        cohort = PhaseECohortMetrics(
            "q1_momentum", "v1", "COIN", "30S", 1, 1, 1,
            1.0, 1.0, 1.0, 1.0, 1.0, 1, False,
        )

        class Store:
            def __init__(self): self.calls = []
            def counts(self): return (0, 0)
            def phase_e_cohorts(self, as_of):
                self.calls.append(as_of)
                return (cohort,)

        store = Store()
        cache = DashboardEvidenceCache(store, clock=lambda: 100.0)
        cache.refresh()
        app = create_app(evidence_cache=cache, clock=lambda: 101.0)
        request(app, "/api/dashboard")
        response = request(app, "/api/phase-e")

        self.assertEqual(store.calls, [100.0])
        self.assertEqual(json.loads(response["body"])["as_of_epoch"], 100.0)

    def test_phase_e_horizons_have_fixed_display_order(self):
        cohorts = tuple(
            PhaseECohortMetrics("q1_momentum", "v1", "COIN", horizon,
                                1, 1, 1, 1.0, 1.0, 1.0, 1.0, 1.0, 1, False)
            for horizon in reversed(("30S", "1M", "5M", "15M", "30M", "1H"))
        )
        rows = dashboard_data(phase_e_cohorts=cohorts)["phase_e_cohorts"]
        self.assertEqual([row["horizon"] for row in rows],
                         ["30S", "1M", "5M", "15M", "30M", "1H"])


if __name__ == "__main__":
    unittest.main()
