import json
import unittest

from quant.history import MidpointHistory, MidpointObservation
from quant.web import FAMILY_NAMES, HORIZON_LABELS, create_app, dashboard_data


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

        self.assertIn('<div class=value>123.46</div>', page)
        self.assertIn('<div class=value>1.23s</div>', page)
        self.assertIn('<div class=value>22:13:20 UTC</div>', page)
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

    def test_mobile_market_grid_uses_readable_responsive_columns(self):
        page = request(create_app(), "/")["body"].decode()
        self.assertIn(
            ".market{grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}",
            page,
        )

    def test_health_only_reports_process_running(self):
        response = request(create_app(), "/health")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(json.loads(response["body"]), {"status": "running"})


if __name__ == "__main__":
    unittest.main()
