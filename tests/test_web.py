import inspect
import json
import subprocess
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from quant import web as web_module
from quant.history import MidpointHistory, MidpointObservation
from quant.evidence import HistoricalReplaySummary, PhaseECohortMetrics
from quant.live_market import LiveMarketState
from quant.q10_options_vol import OptionObservation, OptionSurface
from quant.v9_production import FORMULA_VERSION_MAP
from quant.v9_v4d_integration import OperationalMetrics
from quant.web import (DashboardEvidenceCache, FAMILY_NAMES, HORIZON_LABELS,
                       PHASE_E_FAMILY_NAMES, create_app, dashboard_data,
                       dashboard_page)


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

    def test_display_horizons_match_the_frozen_evidence_contract(self):
        self.assertEqual(HORIZON_LABELS, ("30S", "1M", "5M", "15M", "30M", "1H"))

    def test_unavailable_fields_are_null_and_not_fabricated(self):
        payload = dashboard_data()
        self.assertTrue(all(values == [None] * 6 for values in payload["final_numbers"].values()))
        self.assertEqual(payload["options_data"], {
            "status": "UNAVAILABLE", "as_of_epoch": None,
            "expiration": None, "calls": [], "puts": [],
        })
        self.assertEqual(payload["evidence"], {
            "Forecasts": None, "Resolved": None, "Status": "UNAVAILABLE",
        })
        self.assertEqual(len(payload["phase_e_cohorts"]), 72)
        self.assertTrue(all(row["effective_n"] is None
                            for row in payload["phase_e_cohorts"]))
        self.assertTrue(all(value is None for family in payload["quant_families"] for value in family["values"]))
        self.assertIsNone(payload["market"]["data_age"])
        self.assertIsNone(payload["market"]["event_epoch"])
        self.assertEqual(payload["v9"], {
            "forecast_cutoff": None, "forecast_age": None,
            "horizon_statuses": ["UNAVAILABLE"] * 6,
        })
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

    @patch.dict("os.environ", {"RENDER_GIT_COMMIT": "a" * 40}, clear=False)
    def test_health_reports_process_and_deployed_commit_without_readiness_work(self):
        class Store:
            def counts(self): raise AssertionError("health must not query evidence")
            def phase_e_cohorts(self, as_of):
                raise AssertionError("health must not evaluate Phase E")

        response = request(create_app(
            evidence_store=Store(),
            readiness_check=lambda: (_ for _ in ()).throw(
                AssertionError("health must not check readiness")),
        ), "/health")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(json.loads(response["body"]), {
            "status": "running", "commit": "a" * 40,
        })

    def test_ready_fails_closed_and_contains_callback_failures(self):
        missing = request(create_app(), "/ready")
        false = request(create_app(readiness_check=lambda: False), "/ready")
        failed = request(create_app(
            readiness_check=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        ), "/ready")
        for response in (missing, false, failed):
            self.assertEqual(response["status"], "503 Service Unavailable")
            self.assertEqual(json.loads(response["body"]), {
                "status": "not_ready",
            })

    def test_ready_requires_literal_true(self):
        response = request(
            create_app(readiness_check=lambda: True), "/ready",
        )
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(json.loads(response["body"]), {"status": "ready"})

    def test_main_preserves_handoff_ready_rolling_replacement_path(self):
        source = inspect.getsource(web_module.main)
        self.assertIn(
            'owner_status in {"WAITING", "WAITING_FOR_LEGACY_WRITER"}',
            source,
        )
        self.assertIn("and state.runtime_handoff_ready()", source)

    def test_unknown_route_does_not_query_evidence(self):
        class Store:
            def counts(self): raise AssertionError("unknown route must not query evidence")
            def phase_e_cohorts(self, as_of):
                raise AssertionError("unknown route must not evaluate Phase E")

        response = request(create_app(evidence_store=Store()), "/favicon.ico")
        self.assertEqual(response["status"], "404 Not Found")
        self.assertEqual(response["body"], b"Not Found")

    def test_unknown_paths_share_one_bounded_telemetry_distribution(self):
        metrics = OperationalMetrics()
        app = create_app(metrics=metrics, monotonic_clock=lambda: 1.0)

        for index in range(1_000):
            response = request(app, f"/missing-{index}")
            self.assertEqual(response["status"], "404 Not Found")

        distributions = dict(metrics.snapshot().distributions)
        self.assertEqual(
            tuple(distributions),
            ("web_endpoint.not_found.duration_ms",),
        )
        self.assertEqual(
            distributions["web_endpoint.not_found.duration_ms"].count,
            1_000,
        )

    def test_known_paths_use_fixed_endpoint_metric_names(self):
        metrics = OperationalMetrics()
        app = create_app(metrics=metrics, monotonic_clock=lambda: 1.0)

        request(app, "/health")
        request(app, "/ready")
        request(app, "/api/live")
        request(app, "/")

        self.assertEqual(set(dict(metrics.snapshot().distributions)), {
            "web_endpoint./health.duration_ms",
            "web_endpoint./ready.duration_ms",
            "web_endpoint./api/live.duration_ms",
            "web_endpoint./.duration_ms",
        })

    def test_page_uses_non_overlapping_live_and_evidence_loops(self):
        page = request(create_app(), "/")["body"].decode()
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]

        self.assertIn('fetch("/api/live", {', page)
        self.assertIn('signal: controller.signal', page)
        self.assertIn(
            "setTimeout(() => controller.abort(), 15000)", page)
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
            "market", "v9", "final_numbers", "v9_accuracy", "quant_families",
            "options_data",
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
            v3=SimpleNamespace(horizon_results=tuple(
                SimpleNamespace(horizon=horizon, status=status)
                for horizon, status in zip(
                    ("30S", "1M", "5M", "15M", "30M", "1H"),
                    ("MATURE", "PROVISIONAL", "UNAVAILABLE",
                     "MATURE", "PROVISIONAL", "UNAVAILABLE"),
                )
            )),
            final_numbers=(),
        )
        publication = replace(state.publication(), v9_output=v9_output)
        with patch.object(state, "publication", return_value=publication):
            payload = json.loads(request(
                create_app(state=state, clock=lambda: 105.0), "/api/live"
            )["body"])

        self.assertEqual(payload["market"]["event_epoch"], 106.0)
        self.assertEqual(payload["market"]["data_age"], -1.0)
        self.assertEqual(payload["v9"]["forecast_cutoff"], 100.0)
        self.assertEqual(payload["v9"]["forecast_age"], 5.0)
        self.assertEqual(payload["v9"]["horizon_statuses"], [
            "MATURE", "PROVISIONAL", "UNAVAILABLE",
            "MATURE", "PROVISIONAL", "UNAVAILABLE",
        ])

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

        state.publication = traced("publication", state.publication)

        def clock():
            order.append("clock")
            return 107.0

        request(create_app(state=state, clock=clock), "/api/live")

        self.assertEqual(order, ["publication", "clock"])

    def test_live_renderer_updates_every_market_field(self):
        page = request(create_app(), "/")["body"].decode()

        for field in ("symbol", "btc", "qqq", "ndx", "data_age", "last_cycle"):
            self.assertIn(f'data-dashboard-field="market.{field}"', page)
        for field in ("symbol", "qqq", "ndx", "data_age", "last_cycle"):
            self.assertIn(f'set("market.{field}", data.market.{field}', page)
        self.assertIn(
            'set("market.btc", btcLive ? data.market.btc : null', page)

    def test_initial_html_never_embeds_a_btc_quote_before_client_age_check(self):
        state = LiveMarketState()
        state.accept_g2_price(
            asset="BTC", price=70_000.0, event_epoch=1_700_000_000.0)
        page = request(create_app(
            state=state, clock=lambda: 1_700_000_001.0), "/")["body"].decode()

        self.assertIn(
            'data-dashboard-field="market.btc"></div>', page)
        self.assertNotIn(
            'data-dashboard-field="market.btc">70000.00</div>', page)

    def test_live_renderer_updates_final_quant_options_and_evidence_cells(self):
        page = request(create_app(), "/")["body"].decode()

        self.assertIn('data-dashboard-field="final_numbers.BPS.0"', page)
        self.assertIn('data-dashboard-field="quant_families.Momentum.0"', page)
        self.assertIn('data-dashboard-field="quant_families.Event/Session.5"', page)
        self.assertIn('data-dashboard-field="options_data.expiration"', page)
        self.assertIn('data-dashboard-field="evidence.Forecasts.0"', page)
        self.assertIn("Object.entries(data.final_numbers)", page)
        self.assertIn("Object.entries(accuracyRows)", page)
        self.assertIn("data.quant_families.forEach", page)
        self.assertIn('["calls", "puts"].forEach', page)
        self.assertIn("<h3>CALLS</h3>", page)
        self.assertIn("<h3>PUTS</h3>", page)
        self.assertIn("Object.entries(data.evidence)", page)

    def test_v9_accuracy_displays_existing_state_for_six_canonical_horizons(self):
        final_numbers = tuple(SimpleNamespace(
            final_bps=float(index + 1), move_percent=float(index + 11),
            range_lower_bps=float(index + 21), range_upper_bps=float(index + 31),
        ) for index in range(6))
        accuracy = (
            SimpleNamespace(horizon="30S", directional_wins=400,
                            directional_losses=20, directional_accuracy=400 / 420,
                            directional_effective_n=399.25, status="MATURE"),
            SimpleNamespace(horizon="1M", directional_wins=7,
                            directional_losses=3, directional_accuracy=0.7,
                            directional_effective_n=8.5, status="PROVISIONAL"),
        )
        output = SimpleNamespace(final_numbers=final_numbers, accuracy=accuracy)

        data = dashboard_data(v9_output=output)
        rendered = dashboard_page(data).decode()

        self.assertEqual([row["horizon"] for row in data["v9_accuracy"]],
                         ["30S", "1M", "5M", "15M", "30M", "1H"])
        self.assertEqual(data["v9_accuracy"][0], {
            "horizon": "30S", "directional_wins": 400,
            "directional_losses": 20, "directional_accuracy": 400 / 420,
            "directional_effective_n": 399.25, "status": "MATURE",
        })
        self.assertEqual(data["v9_accuracy"][1]["status"], "PROVISIONAL")
        self.assertEqual(data["v9_accuracy"][2]["status"], "UNAVAILABLE")
        self.assertEqual(data["v9_accuracy"][2]["directional_accuracy"], None)
        self.assertIn(">95.2%<", rendered)
        self.assertIn(">399.25<", rendered)
        self.assertIn(">MATURE<", rendered)
        self.assertIn(">PROVISIONAL<", rendered)
        self.assertIn(">—<", rendered)
        self.assertNotIn(">0%<", rendered)
        self.assertEqual(data["final_numbers"], {
            "BPS": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "MOVE%": [11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
            "RANGE": [f"{index + 21:.2f} to {index + 31:.2f}"
                      for index in range(6)],
        })
        self.assertIn("V9 DIRECTIONAL ACCURACY", rendered)

    def test_v9_accuracy_request_path_only_reads_published_live_output(self):
        class Store:
            def counts(self): raise AssertionError("must not scan historical evidence")
            def phase_e_cohorts(self, _as_of):
                raise AssertionError("must not scan historical evidence")

        state = LiveMarketState()
        output = SimpleNamespace(final_numbers=(), accuracy=())
        publication = replace(state.publication(), v9_output=output)
        with patch.object(state, "publication", return_value=publication):
            response = request(create_app(state=state, evidence_store=Store()), "/api/live")

        self.assertEqual(response["status"], "200 OK")
        self.assertTrue(all(row["status"] == "UNAVAILABLE"
                            for row in json.loads(response["body"])["v9_accuracy"]))

    def test_live_renderer_blanks_null_values_without_fake_zeroes(self):
        page = request(create_app(), "/")["body"].decode()

        self.assertIn('value == null ? "" : String(value)', page)
        self.assertIn('value == null ? "" : Number(value).toFixed(2)', page)
        self.assertNotIn('value || 0', page)

    def test_live_browser_revalidates_btc_age_and_blanks_on_poll_failure(self):
        page = request(create_app(), "/")["body"].decode()

        failure_handler = page.split("} catch (_) {", 1)[1].split("}", 1)[0]
        self.assertNotIn("render", failure_handler)
        self.assertIn('clearBtc(++btcRenderGeneration)', failure_handler)
        self.assertIn("Date.now() / 1000 - btcEvent", page)
        self.assertIn('btcAge >= 0 && btcAge < 5', page)
        self.assertIn("new AbortController()", page)
        self.assertIn("controller.abort()", page)
        self.assertIn("setTimeout(refreshLive, 250)", page)
        self.assertIn("btcEvent + 5 - Date.now() / 1000", page)
        self.assertIn("btcExpiryTimer = setTimeout", page)
        self.assertIn("generation !== btcRenderGeneration", page)

    def test_btc_expires_at_provider_deadline_while_next_fetch_hangs(self):
        page = request(create_app(), "/")["body"].decode()
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]
        payload = {
            "market": {
                "symbol": 100.0, "btc": 70_000.0, "qqq": None,
                "ndx": None, "data_age": 0.0, "last_cycle": None,
                "btc_event_epoch": 1_700_000_000.0,
                "btc_source_status": "LIVE",
            },
            "final_numbers": {}, "v9_accuracy": [], "quant_families": [],
            "options_data": {"expiration": None, "calls": [], "puts": []},
        }
        harness = f"""
const source = {json.dumps(script)};
let nowMs = 1700000004000;
let nextTimer = 1;
const timers = new Map();
global.Date.now = () => nowMs;
global.setTimeout = (fn, delay = 0) => {{
  const id = nextTimer++;
  timers.set(id, {{fn, due: nowMs + Number(delay)}});
  return id;
}};
global.clearTimeout = id => timers.delete(id);
const btcCell = {{dataset: {{dashboardField: "market.btc"}}, textContent: ""}};
const body = {{replaceChildren: () => {{}}}};
global.document = {{
  querySelectorAll: () => [btcCell],
  getElementById: () => body,
  createElement: () => ({{textContent: "", replaceChildren: () => {{}}}}),
}};
let fetchCalls = 0;
global.fetch = () => {{
  fetchCalls += 1;
  if (fetchCalls === 1) return Promise.resolve({{
    ok: true, json: () => Promise.resolve({json.dumps(payload)})
  }});
  return new Promise(() => {{}});
}};
async function flush() {{
  for (let i = 0; i < 12; i += 1) await Promise.resolve();
}}
async function advance(milliseconds) {{
  const target = nowMs + milliseconds;
  while (true) {{
    const due = [...timers.entries()]
      .filter(([, timer]) => timer.due <= target)
      .sort((a, b) => a[1].due - b[1].due || a[0] - b[0])[0];
    if (!due) break;
    timers.delete(due[0]);
    nowMs = due[1].due;
    due[1].fn();
    await flush();
  }}
  nowMs = target;
  await flush();
}}
(async () => {{
  eval(source);
  await advance(250);
  if (btcCell.textContent !== "70000.00")
    throw new Error("fresh BTC was not rendered: " + btcCell.textContent);
  await advance(850);
  if (btcCell.textContent !== "")
    throw new Error("BTC survived provider deadline: " + btcCell.textContent);
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
        result = subprocess.run(
            ["node", "-"], input=harness, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_phase_e_dashboard_mapping_order_format_and_raw_precision(self):
        quant_ids = tuple(
            quant_id for quant_id in PHASE_E_FAMILY_NAMES
            if quant_id != "q3_volatility"
        )
        cohorts = tuple(
            PhaseECohortMetrics(
                quant_id, FORMULA_VERSION_MAP[quant_id], "COIN",
                "1H" if index == 0 else "30S",
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
                    "q3_volatility", FORMULA_VERSION_MAP["q3_volatility"],
                    "COIN", "30S", 1, 1, 1,
                    1.0, 0.0, None, None, None, 1, False,
                ),)

        store = Store()
        cache = DashboardEvidenceCache(store, clock=lambda: 456.75)
        cache.refresh()
        app = create_app(evidence_cache=cache, clock=lambda: 456.75)
        payload = json.loads(request(app, "/api/dashboard")["body"])
        rows = payload["phase_e_cohorts"]

        self.assertEqual(store.phase_calls, [456.75, 456.75])
        self.assertEqual(payload["evidence"], {
            "Forecasts": 123, "Resolved": 98, "Status": "AVAILABLE",
        })
        populated = [row for row in rows if row["formula_version"] is not None]
        self.assertEqual([row["family"] for row in populated],
                         list(PHASE_E_FAMILY_NAMES.values()))
        self.assertIn("q3_volatility", [row["quant_id"] for row in rows])
        self.assertEqual(populated[0]["directional_accuracy"], 0.514)
        self.assertEqual(populated[0]["coverage"], 0.999123)
        self.assertEqual(populated[0]["rmse_bps"], 2.3456)

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

    def test_phase_e_dashboard_exposes_all_72_slots_without_fake_zeroes(self):
        observed = PhaseECohortMetrics(
            "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"], "COIN", "30S",
            21, 20, 19,
            0.95, 2.5, 0.75, 1.5, -0.5, 20, True,
        )
        superseded = PhaseECohortMetrics(
            "q1_momentum", "superseded-v0", "COIN", "30S", 999, 999, 999,
            1.0, 0.0, 1.0, 0.0, 0.0, 999, True,
        )
        wrong_symbol = PhaseECohortMetrics(
            "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"], "OTHER", "30S",
            888, 888, 888, 1.0, 0.0, 1.0, 0.0, 0.0, 888, True,
        )

        payload = dashboard_data(
            phase_e_cohorts=(superseded, wrong_symbol, observed),
            evidence_status="AVAILABLE",
        )
        rows = payload["phase_e_cohorts"]

        self.assertEqual(len(rows), 72)
        self.assertEqual(
            [(row["quant_id"], row["horizon"]) for row in rows],
            [(quant_id, horizon)
             for quant_id in PHASE_E_FAMILY_NAMES
             for horizon in ("30S", "1M", "5M", "15M", "30M", "1H")],
        )
        self.assertEqual(rows[0]["effective_n"], 20)
        missing = rows[1]
        self.assertIsNone(missing["forecast_count"])
        self.assertIsNone(missing["effective_n"])
        self.assertIsNone(missing["eligible"])
        self.assertIsNone(missing["directional_accuracy"])
        self.assertEqual(payload["evidence"]["Status"], "AVAILABLE")
        page = dashboard_page(payload).decode()
        self.assertIn(">Momentum / 1M<", page)
        self.assertNotIn(">null<", page)
        self.assertIn(">—</td>", page)
        self.assertIn('cohort.effective_n == null ? "—"', page)
        self.assertIn('cohort.coverage == null ? "—"', page)

    def test_options_display_labels_stale_surface_and_formats_prices(self):
        call = OptionObservation(
            "COIN-CALL", 100.0, 185.0, 10_000.0, "2026-09-25",
            15.899999999999999, 0.7303, 0.5515, 0.0102, -0.2, 0.1,
            15.35, 16.45,
        )
        put = OptionObservation(
            "COIN-PUT", 100.0, 185.0, 10_000.0, "2026-09-25",
            13.05, 0.6403, -0.4523, 0.0116, -0.2149, 0.1,
            11.65, 14.45,
        )
        surface = OptionSurface(100.0, "2026-09-25", (call,), (put,))
        state = LiveMarketState(clock=lambda: 131.0)
        self.assertTrue(state.accept_quote(bid=184.0, ask=186.0, event_epoch=100.0))
        state.accept_option_surface(surface, midpoint=185.0)

        payload = dashboard_data(snapshot=state.snapshot(), now_epoch=131.0,
                                 calculate_missing=False)
        page = dashboard_page(payload).decode()

        self.assertEqual(payload["options_data"]["status"], "STALE")
        self.assertEqual(payload["options_data"]["as_of_epoch"], 100.0)
        self.assertIn(">STALE<", page)
        self.assertIn(">15.90<", page)
        self.assertNotIn("15.899999999999999", page)

    def test_dashboard_requests_only_read_the_background_cache(self):
        first = PhaseECohortMetrics(
            "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"],
            "COIN", "30S", 1, 1, 1,
            1.0, 1.0, 1.0, 1.0, 1.0, 1, False,
        )
        refreshed = PhaseECohortMetrics(
            "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"],
            "COIN", "30S", 2, 2, 2,
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
        self.assertEqual(len(empty["phase_e_cohorts"]), 72)
        self.assertTrue(all(row["effective_n"] is None
                            for row in empty["phase_e_cohorts"]))
        self.assertEqual(empty["evidence"], {
            "Forecasts": 0, "Resolved": 0, "Status": "UNAVAILABLE",
        })

    def test_background_cache_keeps_new_counts_when_phase_e_fails(self):
        class Store:
            def counts(self): return (2_939_098, 2_887_635)
            def phase_e_cohorts(self, _as_of):
                raise RuntimeError("phase e unavailable")

        cache = DashboardEvidenceCache(Store(), clock=lambda: 100.0)
        snapshot = cache.refresh()

        self.assertEqual(snapshot.counts, (2_939_098, 2_887_635))
        self.assertEqual(snapshot.phase_e_cohorts, ())
        self.assertIsNone(snapshot.as_of_epoch)
        self.assertEqual(snapshot.status, "UNAVAILABLE")

    def test_failed_phase_e_refresh_does_not_retimestamp_stale_cohorts(self):
        cohort = PhaseECohortMetrics(
            "q1_momentum", "v1", "COIN", "30S", 1, 1, 1,
            1.0, 1.0, 1.0, 1.0, 1.0, 1, False,
        )

        class Store:
            def __init__(self):
                self.count_calls = 0
                self.phase_calls = 0
            def counts(self):
                self.count_calls += 1
                return (self.count_calls, self.count_calls)
            def phase_e_cohorts(self, _as_of):
                self.phase_calls += 1
                if self.phase_calls > 1:
                    raise RuntimeError("phase e unavailable")
                return (cohort,)

        refresh_times = iter((100.0, 200.0))
        cache = DashboardEvidenceCache(
            Store(), clock=lambda: next(refresh_times),
        )
        first = cache.refresh()
        stale = cache.refresh()

        self.assertEqual(first.as_of_epoch, 100.0)
        self.assertEqual(stale.counts, (2, 2))
        self.assertEqual(stale.phase_e_cohorts, (cohort,))
        self.assertEqual(stale.as_of_epoch, 100.0)
        self.assertEqual(stale.status, "AVAILABLE")

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

    def test_historical_replay_summary_is_cached_displayed_and_read_only(self):
        summary = HistoricalReplaySummary(
            7, 82_786, 5_463_876, 496_716, "2026-08-25",
        )

        class Store:
            def __init__(self):
                self.summary_calls = 0

            def counts(self):
                return (0, 0)

            def phase_e_cohorts(self, _as_of):
                return ()

            def historical_replay_summary(self):
                self.summary_calls += 1
                return summary

        store = Store()
        cache = DashboardEvidenceCache(store, clock=lambda: 100.0)
        cache.refresh()
        app = create_app(evidence_cache=cache, clock=lambda: 101.0)

        dashboard = json.loads(request(app, "/api/dashboard")["body"])
        endpoint = request(app, "/api/historical-replay")
        page = request(app, "/")["body"].decode()

        self.assertEqual(store.summary_calls, 1)
        self.assertEqual(endpoint["status"], "200 OK")
        self.assertEqual(json.loads(endpoint["body"]), {
            "certified_sessions": 7,
            "cutoff_count": 82_786,
            "available_slot_count": 5_463_876,
            "unavailable_slot_count": 496_716,
            "latest_session": "2026-08-25",
            "family_count": 12,
            "horizon_count": 6,
            "slots_per_cutoff": 72,
        })
        self.assertEqual(dashboard["historical_replay"]["Slots / Cutoff"], 72)
        self.assertEqual(
            dashboard["historical_replay"]["Available Slots"], 5_463_876,
        )
        self.assertIn("HISTORICAL REPLAY EVIDENCE", page)
        self.assertIn(">2026-08-25<", page)

    def test_historical_replay_endpoint_fails_closed_without_cached_summary(self):
        response = request(create_app(), "/api/historical-replay")
        self.assertEqual(response["status"], "503 Service Unavailable")

    def test_phase_e_horizons_have_fixed_display_order(self):
        cohorts = tuple(
            PhaseECohortMetrics(
                                "q1_momentum", FORMULA_VERSION_MAP["q1_momentum"],
                                "COIN", horizon,
                                1, 1, 1, 1.0, 1.0, 1.0, 1.0, 1.0, 1, False)
            for horizon in reversed(("30S", "1M", "5M", "15M", "30M", "1H"))
        )
        rows = dashboard_data(phase_e_cohorts=cohorts)["phase_e_cohorts"]
        q1_rows = [row for row in rows if row["quant_id"] == "q1_momentum"]
        self.assertEqual([row["horizon"] for row in q1_rows],
                         ["30S", "1M", "5M", "15M", "30M", "1H"])


if __name__ == "__main__":
    unittest.main()
