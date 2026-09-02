"""E-1 read-only evidence scorecard: frozen statistics on synthetic rows."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from quant import evidence_scorecard as sc

NY = ZoneInfo("America/New_York")
TUESDAY = date(2026, 9, 1)


def _epoch(day: date, hour: int, minute: int, second: int = 0) -> float:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=NY).timestamp()


def _obs(cutoff: float, forecast, outcome, *, horizon="15M", key="k",
         cell=("q1", "f1", "COIN", "15M"), layer=sc.LAYER_FAMILY) -> sc.Observation:
    return sc.Observation(layer=layer, cell=cell, horizon=horizon, cutoff_epoch=cutoff,
                          forecast_bps=forecast, outcome_bps=outcome, record_key=key)


# --- window selection --------------------------------------------------------


def test_select_windows_keeps_earliest_per_epoch_interval_and_breaks_ties_by_key():
    a = _obs(1000.0, 1.0, 1.0, horizon="30S", key="b", cell=("q", "f", "COIN", "30S"))
    a_tie = _obs(1000.0, 2.0, 2.0, horizon="30S", key="a", cell=("q", "f", "COIN", "30S"))
    later_same = _obs(1010.0, 3.0, 3.0, horizon="30S", key="c", cell=("q", "f", "COIN", "30S"))
    next_interval = _obs(1020.0, 4.0, 4.0, horizon="30S", key="d", cell=("q", "f", "COIN", "30S"))
    other_cell = _obs(1000.0, 5.0, 5.0, horizon="30S", key="e", cell=("q2", "f", "COIN", "30S"))
    chosen = sc.select_windows([later_same, a, next_interval, a_tie, other_cell])
    assert [w.record_key for w in chosen] == ["a", "d", "e"]
    assert sc.interval_index(1000.0, "30S") == 33 and sc.interval_index(1020.0, "30S") == 34


def test_select_windows_rejects_unknown_horizon():
    with pytest.raises(ValueError):
        sc.select_windows([_obs(1.0, 1.0, 1.0, horizon="2H")])


def test_rth_window_requires_full_interval_inside_regular_hours():
    assert sc.is_rth_window(_epoch(TUESDAY, 9, 30), "30S") is True
    assert sc.is_rth_window(_epoch(TUESDAY, 9, 29, 59), "30S") is False
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 59, 30), "30S") is True
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 59, 31), "30S") is False
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 0), "1H") is True
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 0, 1), "1H") is False
    assert sc.is_rth_window(_epoch(date(2026, 9, 5), 10, 0), "1M") is False  # Saturday


def test_observation_kind_classifies_abstain_unresolved_tie_decided():
    assert sc.observation_kind(_obs(1.0, None, 5.0)) == sc.KIND_ABSTAIN
    assert sc.observation_kind(_obs(1.0, 0.0, 5.0)) == sc.KIND_ABSTAIN
    assert sc.observation_kind(_obs(1.0, math.nan, 5.0)) == sc.KIND_ABSTAIN
    assert sc.observation_kind(_obs(1.0, 2.0, None)) == sc.KIND_UNRESOLVED
    assert sc.observation_kind(_obs(1.0, 2.0, math.inf)) == sc.KIND_UNRESOLVED
    assert sc.observation_kind(_obs(1.0, 2.0, 0.0)) == sc.KIND_TIE
    assert sc.observation_kind(_obs(1.0, -2.0, 3.0)) == sc.KIND_DECIDED


# --- statistics ----------------------------------------------------------------


def test_percentile_interval_indices_at_frozen_levels():
    values = [float(i) for i in range(1, 2001)]
    assert sc.percentile_interval(values, 0.999) == (1.0, 2000.0)
    assert sc.percentile_interval(values, 0.95) == (50.0, 1951.0)
    with pytest.raises(ValueError):
        sc.percentile_interval([], 0.95)


def test_session_bootstrap_is_deterministic_and_resamples_sessions():
    by_session = {date(2026, 9, 1): [1.0, 1.0], date(2026, 9, 2): [-1.0, -1.0]}
    first = sc.session_bootstrap(by_session, sc._mean)
    second = sc.session_bootstrap(by_session, sc._mean)
    assert first == second and len(first) == sc.BOOTSTRAP_RESAMPLES
    assert set(first) <= {-1.0, 0.0, 1.0}
    assert first == sorted(first)
    assert sc.percentile_interval(first, 0.95) == (-1.0, 1.0)
    assert sc.session_bootstrap({}, sc._mean) == []


def test_hit_rate_by_magnitude_quartile_hand_computed():
    quartiles = sc.hit_rate_by_magnitude_quartile(
        [1, 2, 3, 4, 5, 6, 7, 8], [1, 0, 1, 0, 1, 1, 0, 0])
    assert [q["hit_rate"] for q in quartiles] == [0.5, 0.5, 1.0, 0.0]
    assert [q["n"] for q in quartiles] == [2, 2, 2, 2]
    assert quartiles[0]["min_abs_forecast_bps"] == 1 and quartiles[3]["max_abs_forecast_bps"] == 8
    assert sc.hit_rate_by_magnitude_quartile([1, 2, 3], [1, 1, 1]) == []


def test_label_cell_thresholds():
    assert sc.label_cell(100, 10, 0.01) == sc.LABEL_CANDIDATE
    assert sc.label_cell(100, 10, 0.0) == sc.LABEL_NOISE
    assert sc.label_cell(100, 10, -5.0) == sc.LABEL_NOISE
    assert sc.label_cell(100, 10, None) == sc.LABEL_NOISE
    assert sc.label_cell(99, 10, 5.0) == sc.LABEL_INSUFFICIENT
    assert sc.label_cell(100, 9, 5.0) == sc.LABEL_INSUFFICIENT


def test_cell_metrics_hand_computed_single_session():
    windows = [
        _obs(_epoch(TUESDAY, 8, 0), 1.0, 1.0, key="pre"),      # pre-market, excluded
        _obs(_epoch(TUESDAY, 9, 30), 2.0, 10.0, key="w1"),     # hit, +10
        _obs(_epoch(TUESDAY, 9, 45), -3.0, 5.0, key="w2"),     # miss, -5
        _obs(_epoch(TUESDAY, 10, 0), 1.0, 0.0, key="w3"),      # tie, 0
        _obs(_epoch(TUESDAY, 10, 15), 0.0, 4.0, key="w4"),     # abstain
        _obs(_epoch(TUESDAY, 10, 30), 4.0, -2.0, key="w5"),    # miss, -2
    ]
    m = sc.cell_metrics(windows, cost_bps=0.5, resamples=50)
    assert (m["n_windows"], m["n_excluded_non_rth"]) == (6, 1)
    assert (m["n_abstain"], m["n_unresolved"], m["n_ties"]) == (1, 0, 1)
    assert (m["n_decided"], m["n_economic"], m["n_sessions"]) == (3, 4, 1)
    assert m["hit_rate"] == pytest.approx(1 / 3)
    assert m["z_hit_descriptive"] == pytest.approx((1 / 3 - 0.5) * math.sqrt(3) / 0.5)
    assert m["mean_signed_bps"] == pytest.approx(0.75)          # (10 - 5 + 0 - 2) / 4
    assert m["mean_cost_adjusted_bps"] == pytest.approx(0.25)
    assert m["corr_forecast_outcome"] == pytest.approx(-16 / math.sqrt(26 * 86.75), abs=1e-9)
    assert m["calibration_corr"] == pytest.approx(0.5 / math.sqrt(5 * 56.75), abs=1e-9)
    assert m["hit_rate_by_magnitude_quartile"] == []
    # one session: every resample is that session, so intervals collapse
    assert m["bootstrap_mean_cost_adjusted_bps"]["interval_999"] == [0.25, 0.25]
    assert m["bootstrap_mean_cost_adjusted_bps"]["interval_95"] == [0.25, 0.25]
    assert m["bootstrap_hit_rate"]["interval_95"] == pytest.approx([1 / 3, 1 / 3])
    assert m["label"] == sc.LABEL_INSUFFICIENT


def test_cell_metrics_with_no_scored_windows_reports_nulls():
    m = sc.cell_metrics([_obs(_epoch(TUESDAY, 8, 0), 1.0, 1.0)], cost_bps=0.0, resamples=10)
    assert m["n_windows"] == 1 and m["n_excluded_non_rth"] == 1 and m["n_economic"] == 0
    assert m["hit_rate"] is None and m["mean_signed_bps"] is None
    assert m["bootstrap_mean_cost_adjusted_bps"]["interval_999"] is None
    assert m["label"] == sc.LABEL_INSUFFICIENT


def test_ties_count_as_zero_in_economic_mean_but_not_in_hit_rate():
    windows = [
        _obs(_epoch(TUESDAY, 9, 30), 1.0, 4.0, key="a"),
        _obs(_epoch(TUESDAY, 9, 45), 1.0, 0.0, key="b"),
        _obs(_epoch(TUESDAY, 10, 0), 1.0, 0.0, key="c"),
        _obs(_epoch(TUESDAY, 10, 15), 1.0, 0.0, key="d"),
    ]
    m = sc.cell_metrics(windows, cost_bps=0.0, resamples=10)
    assert m["hit_rate"] == 1.0 and m["n_decided"] == 1
    assert m["mean_signed_bps"] == pytest.approx(1.0) and m["n_economic"] == 4


def test_candidate_requires_wide_interval_above_zero_over_ten_sessions():
    sessions = [d for d in (date(2026, 8, 3 + i) for i in range(14)) if d.weekday() < 5][:10]
    assert len(sessions) == 10
    windows = []
    for day in sessions:
        for i in range(12):                      # 12 x 15M windows per session
            hour, minute = 9 + (i + 2) // 4, ((i + 2) % 4) * 15
            windows.append(_obs(_epoch(day, hour, minute), 1.0, 5.0, key=f"{day}-{i}"))
    m = sc.cell_metrics(windows, cost_bps=1.0, resamples=200)
    assert m["n_economic"] == 120 and m["n_sessions"] == 10
    assert m["mean_cost_adjusted_bps"] == pytest.approx(4.0)
    assert m["bootstrap_mean_cost_adjusted_bps"]["interval_999"] == [4.0, 4.0]
    assert m["label"] == sc.LABEL_CANDIDATE
    negative = sc.cell_metrics(
        [sc.Observation(w.layer, w.cell, w.horizon, w.cutoff_epoch, w.forecast_bps,
                        -w.outcome_bps, w.record_key) for w in windows],
        cost_bps=1.0, resamples=200)
    assert negative["label"] == sc.LABEL_NOISE


def test_score_layer_scores_every_cell_in_fixed_order():
    rows = [
        _obs(_epoch(TUESDAY, 9, 30), 1.0, 1.0, horizon="1H", cell=("q1", "f", "COIN", "1H"), key="a"),
        _obs(_epoch(TUESDAY, 9, 30), 1.0, 1.0, horizon="30S", cell=("q1", "f", "COIN", "30S"), key="b"),
        _obs(_epoch(TUESDAY, 9, 30), 1.0, 1.0, horizon="30S", cell=("q11", "f", "COIN", "30S"), key="c"),
    ]
    cells = sc.score_layer(rows, cost_bps=0.0, resamples=5)
    assert [(c["cell"]["quant_id"], c["cell"]["horizon"]) for c in cells] == [
        ("q1", "30S"), ("q1", "1H"), ("q11", "30S")]
    assert all(c["layer"] == sc.LAYER_FAMILY for c in cells)


def test_pearson_returns_none_on_degenerate_input():
    assert sc.pearson([1.0], [1.0]) is None
    assert sc.pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None
    assert sc.pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)


# --- guards and receipt ----------------------------------------------------------


def test_refuse_during_rth_has_no_override():
    with pytest.raises(SystemExit):
        sc.refuse_during_rth(datetime(2026, 9, 1, 10, 0, tzinfo=NY))
    with pytest.raises(SystemExit):
        sc.refuse_during_rth(datetime(2026, 9, 1, 9, 30, tzinfo=NY))
    sc.refuse_during_rth(datetime(2026, 9, 1, 8, 0, tzinfo=NY))
    sc.refuse_during_rth(datetime(2026, 9, 1, 16, 0, tzinfo=NY))
    sc.refuse_during_rth(datetime(2026, 9, 5, 10, 0, tzinfo=NY))


def test_recent_weekday_sessions_and_parse_sessions():
    assert sc.recent_weekday_sessions(3, date(2026, 9, 2)) == [
        date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)]
    assert sc.parse_sessions("2026-09-01, 2026-08-31,2026-09-01") == [
        date(2026, 8, 31), date(2026, 9, 1)]
    with pytest.raises(ValueError):
        sc.parse_sessions(" , ")


def test_session_epoch_bounds_cover_whole_eastern_days():
    lo, hi = sc.session_epoch_bounds([date(2026, 9, 1), date(2026, 8, 31)])
    assert lo == datetime(2026, 8, 31, 0, 0, tzinfo=NY).timestamp()
    assert hi == datetime(2026, 9, 2, 0, 0, tzinfo=NY).timestamp()


def test_receipt_is_read_only_and_hash_covers_body():
    receipt = sc.build_receipt(
        sessions=[date(2026, 9, 1)], cost_bps=2.0, cells=[{"layer": "FAMILY"}],
        rows_read={"forecasts": 1}, query_wall_seconds=0.5,
        generated_at=datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc))
    body = {k: v for k, v in receipt.items() if k != "sha256"}
    assert receipt["sha256"] == hashlib.sha256(sc.canonical_json(body).encode()).hexdigest()
    assert (receipt["forecast_writes"], receipt["outcome_writes"],
            receipt["evidence_writes"], receipt["read_only"]) == (0, 0, 0, True)
    assert receipt["bootstrap"] == {
        "method": "session_clustered_percentile", "resamples": 2000, "seed": 0,
        "intervals": [0.999, 0.95]}
    assert receipt["contract"] == "docs/e-1-evidence-scorecard-freeze.md"
    json.loads(sc.canonical_json(receipt))


def test_row_mappers_build_observations():
    fam = sc.family_observation(
        (7, "q1_momentum", "v1", "COIN", "15M", 1700000000.0, 3.5, None))
    assert fam.cell == ("q1_momentum", "v1", "COIN", "15M") and fam.record_key == "7"
    assert fam.forecast_bps == 3.5 and fam.outcome_bps is None


def test_v9_row_mapper_uses_existing_deserializers(monkeypatch):
    cutoff = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    seen = {}

    def fake_forecast(payload, *, expected_hash=None):
        seen["forecast"] = (payload, expected_hash)
        return SimpleNamespace(cutoff_at=cutoff, expected_return_bps=1.25)

    def fake_outcome(payload, *, expected_hash=None):
        seen["outcome"] = (payload, expected_hash)
        return SimpleNamespace(actual_return_bps=-2.0, target_timing_status="VERIFIED")

    monkeypatch.setitem(sys.modules, "quant.v9_v4a_evidence", SimpleNamespace(
        deserialize_forecast_record=fake_forecast,
        deserialize_outcome_record=fake_outcome))
    obs = sc.v9_observation(("fid", "fhash", "V3", "COIN", "15M", {"f": 1}, "ohash", {"o": 1}))
    assert obs.layer == sc.LAYER_V9 and obs.cell == ("V3", "COIN", "15M")
    assert obs.cutoff_epoch == cutoff.timestamp()
    assert (obs.forecast_bps, obs.outcome_bps) == (1.25, -2.0)
    assert seen == {"forecast": ({"f": 1}, "fhash"), "outcome": ({"o": 1}, "ohash")}
    unresolved = sc.v9_observation(("fid", "fhash", "V3", "COIN", "15M", {"f": 1}, None, None))
    assert unresolved.outcome_bps is None


def test_module_sql_and_source_contain_no_write_paths():
    source = Path(sc.__file__).read_text(encoding="utf-8")
    for sql in (sc.FAMILY_SQL, sc.V9_SQL, *sc.COUNT_SQL.values(), sc._WRITE_PRIVILEGE_SQL):
        lowered = sql.lower()
        assert not any(word in lowered for word in
                       ("insert ", "update ", "delete ", "truncate", "copy ", "alter ", "drop "))
    assert "connection.read_only = True" in source
    assert "statement_timeout={STATEMENT_TIMEOUT_MS}" in source
    assert sc.STATEMENT_TIMEOUT_MS <= 60_000
    assert "import psycopg" in source and not source.startswith("import psycopg")
    assert sc.READONLY_URL_ENV != "DATABASE_URL"
    assert "DATABASE_URL\")" not in source.replace(sc.READONLY_URL_ENV, "")


def test_main_refuses_without_readonly_url_and_on_weekend_sessions(monkeypatch):
    monkeypatch.delenv(sc.READONLY_URL_ENV, raising=False)
    monkeypatch.setattr(sc, "refuse_during_rth", lambda now=None: None)
    with pytest.raises(SystemExit):
        sc.main(["--sessions", "2026-09-01", "--cost-bps", "1"])
    monkeypatch.setenv(sc.READONLY_URL_ENV, "postgresql://read-only")
    with pytest.raises(SystemExit):
        sc.main(["--sessions", "2026-09-05", "--cost-bps", "1"])
    with pytest.raises(SystemExit):
        sc.main(["--sessions", "2026-09-01", "--cost-bps", "-1"])


def test_main_emits_receipt_from_read_seam(monkeypatch, capsys):
    monkeypatch.setenv(sc.READONLY_URL_ENV, "postgresql://read-only")
    monkeypatch.setattr(sc, "refuse_during_rth", lambda now=None: None)
    rows = [_obs(_epoch(TUESDAY, 9, 30), 2.0, 3.0, key="a")]
    monkeypatch.setattr(sc, "read_observations",
                        lambda url, sessions: (rows, [], {"forecasts": 1}, 0.01))
    assert sc.main(["--sessions", "2026-09-01", "--cost-bps", "0.5"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["sessions"] == ["2026-09-01"] and receipt["cost_bps"] == 0.5
    assert receipt["read_only"] is True and len(receipt["cells"]) == 1
    assert receipt["cells"][0]["label"] == sc.LABEL_INSUFFICIENT
