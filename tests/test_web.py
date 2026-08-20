import json
import unittest

from quant.history import MidpointHistory, MidpointObservation
from quant.evidence import PhaseECohortMetrics
from quant.web import (FAMILY_NAMES, HORIZON_LABELS, PHASE_E_FAMILY_NAMES,
                       create_app, dashboard_data)


def request(app, path):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = dict(headers)

    response["body"] = b"".join(app({"PATH_INFO": path}, start_response))
    return response


class WebSurfaceTests(unittest.TestCase):
    def test_page_route_loads_and_renders_nulls_as_blanks(self):
        response = request(create_app(), "/")
        self.assertEqual(response["status"], "200 OK")
        page = response["body"].decode()
        self.assertIn("ATOM QUANT", page)
        self.assertIn("12 QUANT FAMILIES", page)
        self.assertNotIn(">None<", page)

    def test_json_route_has_frozen_order_and_only_q1_q3_outputs(self):
        history = MidpointHistory(
            MidpointObservation(float(second), 100.0 + second / 100.0)
            for second in range(0, 3601, 30)
        )
        response = request(create_app(history, cutoff_epoch=3600.0), "/api/dashboard")
        self.assertEqual(response["status"], "200 OK")
        payload = json.loads(response["body"])
        self.assertEqual(payload["horizons"], list(HORIZON_LABELS))
        self.assertEqual([item["name"] for item in payload["quant_families"]], list(FAMILY_NAMES))
        for family in payload["quant_families"][:3]:
            self.assertEqual(len(family["values"]), 6)
            self.assertTrue(all(isinstance(value, (float, int)) for value in family["values"]))
        for family in payload["quant_families"][3:]:
            self.assertEqual(family["values"], [None] * 6)

    def test_unavailable_fields_are_null_and_not_fabricated(self):
        payload = dashboard_data()
        self.assertTrue(all(values == [None] * 6 for values in payload["final_numbers"].values()))
        self.assertTrue(all(value is None for value in payload["options_data"].values()))
        self.assertTrue(all(value is None for value in payload["evidence"].values()))
        self.assertTrue(all(value is None for family in payload["quant_families"] for value in family["values"]))
        self.assertIsNone(payload["market"]["data_age"])
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

    def test_page_formats_q1_q3_to_two_decimal_places(self):
        history = MidpointHistory(
            MidpointObservation(float(second), 100.0 + second / 100.0)
            for second in range(0, 3601, 30)
        )
        app = create_app(history, cutoff_epoch=3600.0, clock=lambda: 3600.0)
        payload = json.loads(request(app, "/api/dashboard")["body"])
        page = request(app, "/")["body"].decode()

        for family in payload["quant_families"][:3]:
            for value in family["values"]:
                self.assertIn(f">{value:.2f}</td>", page)

    def test_mobile_market_grid_uses_two_non_overlapping_columns(self):
        page = request(create_app(), "/")["body"].decode()
        self.assertIn(".market{grid-template-columns:repeat(2,minmax(0,1fr))}", page)

    def test_health_only_reports_process_running(self):
        response = request(create_app(), "/health")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(json.loads(response["body"]), {"status": "running"})

    def test_page_polls_dashboard_every_second_without_cache_or_reload(self):
        page = request(create_app(), "/")["body"].decode()

        self.assertIn('fetch("/api/dashboard", {cache: "no-store"})', page)
        self.assertIn("setInterval(refreshDashboard, 1000)", page)
        self.assertNotIn("location.reload", page)
        self.assertNotIn("window.location", page)

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
        self.assertIn('data-dashboard-field="options_data.Strike.0"', page)
        self.assertIn('data-dashboard-field="evidence.Forecasts.0"', page)
        self.assertIn("Object.entries(data.final_numbers)", page)
        self.assertIn("data.quant_families.forEach", page)
        self.assertIn("Object.entries(data.options_data)", page)
        self.assertIn("Object.entries(data.evidence)", page)

    def test_live_renderer_blanks_null_values_without_fake_zeroes(self):
        page = request(create_app(), "/")["body"].decode()

        self.assertIn('value == null ? "" : String(value)', page)
        self.assertIn('value == null ? "" : Number(value).toFixed(2)', page)
        self.assertNotIn('value || 0', page)

    def test_poll_failure_keeps_values_and_allows_interval_to_retry(self):
        page = request(create_app(), "/")["body"].decode()

        failure_handler = page.split("} catch (_) {", 1)[1].split("}", 1)[0]
        self.assertNotIn("render", failure_handler)
        self.assertNotIn("textContent", failure_handler)
        self.assertIn("setInterval(refreshDashboard, 1000)", page)

    def test_phase_e_dashboard_mapping_order_format_and_raw_precision(self):
        quant_ids = tuple(PHASE_E_FAMILY_NAMES)
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
                return cohorts + (PhaseECohortMetrics(
                    "q3_volatility", "v1", "COIN", "30S", 1, 1, 1,
                    1.0, 0.0, None, None, None, 1, False,
                ),)

        store = Store()
        app = create_app(evidence_store=store, clock=lambda: 456.75)
        payload = json.loads(request(app, "/api/dashboard")["body"])
        rows = payload["phase_e_cohorts"]

        self.assertEqual(store.phase_calls, [456.75])
        self.assertEqual(payload["evidence"], {"Forecasts": 123, "Resolved": 98})
        self.assertEqual([row["family"] for row in rows], list(PHASE_E_FAMILY_NAMES.values()))
        self.assertNotIn("q3_volatility", [row["quant_id"] for row in rows])
        self.assertEqual(rows[0]["directional_accuracy"], 0.514)
        self.assertEqual(rows[0]["coverage"], 0.999123)
        self.assertEqual(rows[0]["rmse_bps"], 2.3456)

        page = request(create_app(evidence_store=store, clock=lambda: 456.75), "/")["body"].decode()
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
