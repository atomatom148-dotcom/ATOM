from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_ordinary_ci_runs_full_suite_on_pull_requests_and_main():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pull_request:" in workflow
    assert "branches: [main]" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "PYTHONPATH=. python -m pytest -q" in workflow
    assert "secrets." not in workflow


def test_market_open_gate_observes_deployment_without_competing_writer():
    acceptance = (ROOT / "tests" / "test_v9_market_open_acceptance.py").read_text()
    workflow = (
        ROOT / ".github" / "workflows" / "v9-market-open-acceptance.yml"
    ).read_text()
    for forbidden in (
        "ProductionV9Runtime", "LiveMarketState", "accept_quote(",
        "ALPACA_API_KEY", "ALPACA_SECRET_KEY",
    ):
        assert forbidden not in acceptance
        assert forbidden not in workflow
    assert 'base_url, "/api/live"' in acceptance
    assert "atom_v9_v4_forecasts" in acceptance
    assert "atom_v9_v4_outcomes" in acceptance
    assert "exchange-calendars" in workflow
    assert "connection.read_only = True" in acceptance
    assert "WHERE symbol='COIN' AND cutoff_at=%s" in acceptance
    assert 'f"COIN:{cutoff:.9f}"' not in acceptance
    assert acceptance.count("sum(row_count - 1)") == 2
    assert "_assert_duplicate_surplus_unchanged(" in acceptance
    assert "_assert_live_forecast_agreement(payload, forecast_30s)" in acceptance
    assert "live_status == forecast.status" in acceptance
    for exact_outcome_binding in (
        "outcome.forecast_record_id == forecast_30s.forecast_record_id",
        "outcome.target_identity == target_identity",
        "outcome.target_endpoint == forecast_30s.target_endpoint",
    ):
        assert exact_outcome_binding in acceptance
