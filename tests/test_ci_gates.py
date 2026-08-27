from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_ordinary_ci_runs_full_suite_on_pull_requests_and_main():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pull_request:" in workflow
    assert "branches: [main]" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" in workflow
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-python@v5" not in workflow
    assert "PYTHONPATH=. python -m pytest -q" in workflow
    assert "secrets." not in workflow


def test_sonar_ci_publishes_python_coverage_for_analysis():
    workflow = (ROOT / ".github" / "workflows" / "sonar.yml").read_text()
    properties = (ROOT / "sonar-project.properties").read_text()

    assert "pull_request:" in workflow
    assert "branches: [main]" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "fetch-depth: 0" in workflow
    assert "pytest-cov" in workflow
    assert "--cov=quant --cov-report=xml:coverage.xml" in workflow
    assert "SonarSource/sonarqube-scan-action@1a6d90ebcb0e6a6b1d87e37ba693fe453195ae25" in workflow
    assert "SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}" in workflow

    assert "sonar.organization=atomatom148-dotcom" in properties
    assert "sonar.projectKey=atomatom148-dotcom_ATOM" in properties
    assert "sonar.sources=quant" in properties
    assert "sonar.tests=tests" in properties
    assert "sonar.python.coverage.reportPaths=coverage.xml" in properties


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
