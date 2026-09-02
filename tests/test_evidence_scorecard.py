"""E-1 (E-1A through E-1D) read-only evidence scorecard: frozen statistics on synthetic rows."""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from quant import evidence_scorecard as sc

NY = ZoneInfo("America/New_York")
TUESDAY = date(2026, 9, 1)
WEDNESDAY = date(2026, 9, 2)
FAMILY_CELL = ("q1", "f1", "COIN", "15M")


def _epoch(day: date, hour: int, minute: int, second: int = 0) -> float:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=NY).timestamp()


def _row(cutoff: float, forecast, outcome, *, horizon="15M", key="k", cell=FAMILY_CELL,
         layer=sc.LAYER_FAMILY, admissible=True, outcome_eligible=True) -> sc.Row:
    return sc.Row(layer=layer, cell=cell, horizon=horizon, cutoff_epoch=cutoff,
                  forecast_bps=forecast, outcome_bps=outcome, record_key=key,
                  admissible=admissible, outcome_eligible=outcome_eligible)


def _select(rows):
    selector = sc.CellSelector(rows[0].layer, rows[0].cell, rows[0].horizon)
    for row in rows:
        selector.feed(row)
    return selector


# --- window selection --------------------------------------------------------


def test_selector_spaces_by_horizon_and_reconciles_counts():
    rows = [
        _row(_epoch(TUESDAY, 8, 0), 1.0, 1.0, key="a"),                       # non-RTH
        _row(_epoch(TUESDAY, 9, 30), 1.0, 1.0, key="b"),                      # selected
        _row(_epoch(TUESDAY, 9, 35), 1.0, 1.0, key="c"),                      # overlap
        _row(_epoch(TUESDAY, 9, 40), 1.0, 1.0, key="d", admissible=False),    # inadmissible
        _row(_epoch(TUESDAY, 9, 45), 1.0, 1.0, key="e"),                      # selected
        _row(_epoch(TUESDAY, 10, 0), 1.0, 1.0, key="f"),                      # selected
        _row(_epoch(WEDNESDAY, 9, 30), 1.0, 1.0, key="g"),                    # new session
    ]
    selector = _select(rows)
    counts = selector.counts()
    assert (counts.n_rows, counts.n_inadmissible, counts.n_non_rth,
            counts.n_overlap_excluded, counts.n_windows) == (7, 1, 1, 1, 4)
    assert counts.n_population == 6
    assert counts.n_population == counts.n_non_rth + counts.n_overlap_excluded + counts.n_windows
    assert [w.record_key for w in selector.windows] == ["b", "e", "f", "g"]


def test_selector_1h_windows_do_not_overlap_across_utc_buckets():
    # 09:30 ET and 10:00 ET fall in different UTC hour buckets but overlap by 30 minutes.
    rows = [
        _row(_epoch(TUESDAY, 9, 30), 1.0, 1.0, horizon="1H", key="a", cell=("q", "f", "COIN", "1H")),
        _row(_epoch(TUESDAY, 10, 0), 1.0, 1.0, horizon="1H", key="b", cell=("q", "f", "COIN", "1H")),
        _row(_epoch(TUESDAY, 10, 30), 1.0, 1.0, horizon="1H", key="c", cell=("q", "f", "COIN", "1H")),
    ]
    selector = _select(rows)
    assert [w.record_key for w in selector.windows] == ["a", "c"]
    assert selector.counts().n_overlap_excluded == 1


def test_selector_rejects_out_of_order_rows_and_foreign_cells():
    selector = sc.CellSelector(sc.LAYER_FAMILY, FAMILY_CELL, "15M")
    selector.feed(_row(_epoch(TUESDAY, 10, 0), 1.0, 1.0, key="b"))
    with pytest.raises(ValueError):
        selector.feed(_row(_epoch(TUESDAY, 9, 45), 1.0, 1.0, key="a"))
    with pytest.raises(ValueError):
        selector.feed(_row(_epoch(TUESDAY, 10, 30), 1.0, 1.0, cell=("q2", "f1", "COIN", "15M")))
    with pytest.raises(ValueError):
        sc.CellSelector(sc.LAYER_FAMILY, ("q", "f", "COIN", "2H"), "2H")


def test_rth_window_requires_full_interval_inside_regular_hours():
    assert sc.is_rth_window(_epoch(TUESDAY, 9, 30), "30S") is True
    assert sc.is_rth_window(_epoch(TUESDAY, 9, 29, 59), "30S") is False
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 59, 30), "30S") is True
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 59, 31), "30S") is False
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 0), "1H") is True
    assert sc.is_rth_window(_epoch(TUESDAY, 15, 0, 1), "1H") is False
    assert sc.is_rth_window(_epoch(date(2026, 9, 5), 10, 0), "1M") is False  # Saturday


def test_window_kind_precedence():
    assert sc.window_kind(_row(1.0, None, 5.0)) == sc.KIND_ABSTAIN
    assert sc.window_kind(_row(1.0, 0.0, None)) == sc.KIND_ABSTAIN
    assert sc.window_kind(_row(1.0, math.nan, 5.0)) == sc.KIND_ABSTAIN
    assert sc.window_kind(_row(1.0, 2.0, None)) == sc.KIND_INVALID_OUTCOME
    assert sc.window_kind(_row(1.0, 2.0, math.inf)) == sc.KIND_INVALID_OUTCOME
    assert sc.window_kind(_row(1.0, 2.0, 3.0, outcome_eligible=False)) == sc.KIND_INVALID_OUTCOME
    assert sc.window_kind(_row(1.0, 2.0, 0.0)) == sc.KIND_TIE
    assert sc.window_kind(_row(1.0, -2.0, 3.0)) == sc.KIND_DECIDED


# --- statistics ----------------------------------------------------------------


def test_percentile_interval_indices_at_frozen_levels_and_200k():
    values = [float(i) for i in range(1, 200_001)]
    assert sc.percentile_interval(values, 0.999) == (100.0, 199_901.0)
    assert sc.percentile_interval(values, 0.95) == (5000.0, 195_001.0)
    with pytest.raises(ValueError):
        sc.percentile_interval([], 0.95)


def test_session_bootstrap_ratio_of_sums_equals_pooled_mean():
    sums = {date(2026, 9, 1): 2.0, date(2026, 9, 2): -3.0}
    counts = {date(2026, 9, 1): 2, date(2026, 9, 2): 3}
    first = sc.session_bootstrap(sums, counts, random.Random(0), resamples=500)
    second = sc.session_bootstrap(sums, counts, random.Random(0), resamples=500)
    assert first == second and len(first) == 500 and first == sorted(first)
    # AA -> 4/4, AB -> -1/5, BB -> -6/6: exactly the pooled means of the drawn clusters
    assert set(first) <= {1.0, -0.2, -1.0}
    assert sc.session_bootstrap({}, {}, random.Random(0), resamples=5) == []


def test_hit_rate_by_magnitude_quartile_uses_frozen_rank_partition():
    ordered = [(1, 1), (2, 0), (2, 1), (4, 0), (5, 1), (6, 1), (7, 0), (8, 0)]
    quartiles = sc.hit_rate_by_magnitude_quartile(ordered)
    assert [q["hit_rate"] for q in quartiles] == [0.5, 0.5, 1.0, 0.0]
    assert [q["n"] for q in quartiles] == [2, 2, 2, 2]
    assert sc.hit_rate_by_magnitude_quartile([(1, 1), (2, 1), (3, 1)]) == []


def test_eligibility_minimums():
    assert sc.is_eligible(100, 10) is True
    assert sc.is_eligible(99, 10) is False
    assert sc.is_eligible(100, 9) is False


def test_cell_metrics_hand_computed_single_session():
    rows = [
        _row(_epoch(TUESDAY, 9, 30), 2.0, 10.0, key="w1"),                       # hit, +10
        _row(_epoch(TUESDAY, 9, 45), -3.0, 5.0, key="w2"),                       # miss, -5
        _row(_epoch(TUESDAY, 10, 0), 1.0, 0.0, key="w3"),                        # tie, 0
        _row(_epoch(TUESDAY, 10, 15), 0.0, 4.0, key="w4"),                       # abstain
        _row(_epoch(TUESDAY, 10, 30), 4.0, -2.0, key="w5"),                      # miss, -2
        _row(_epoch(TUESDAY, 10, 45), 1.0, 3.0, key="w6", outcome_eligible=False),  # invalid
    ]
    selector = _select(rows)
    m = sc.cell_metrics(selector.counts(), selector.windows, resamples=50)
    assert (m["n_windows"], m["n_abstain"], m["n_invalid_outcome"], m["n_ties"]) == (6, 1, 1, 1)
    assert (m["n_decided"], m["n_economic"], m["n_sessions"], m["n_decided_sessions"]) == (3, 4, 1, 1)
    assert m["n_windows"] == m["n_abstain"] + m["n_invalid_outcome"] + m["n_ties"] + m["n_decided"]
    assert m["hit_rate"] == pytest.approx(1 / 3)
    assert m["z_hit_descriptive"] == pytest.approx((1 / 3 - 0.5) * math.sqrt(3) / 0.5)
    assert m["mean_signed_bps"] == pytest.approx(0.75)          # (10 - 5 + 0 - 2) / 4
    assert m["corr_forecast_outcome"] == pytest.approx(-16 / math.sqrt(26 * 86.75), abs=1e-9)
    assert m["calibration_corr"] == pytest.approx(0.5 / math.sqrt(5 * 56.75), abs=1e-9)
    assert m["hit_rate_by_magnitude_quartile"] == []
    assert m["bootstrap_mean_signed_bps"]["interval_999"] == [0.75, 0.75]
    assert m["bootstrap_mean_signed_bps"]["interval_95"] == [0.75, 0.75]
    assert m["bootstrap_hit_rate"]["interval_95"] == pytest.approx([1 / 3, 1 / 3])
    assert m["eligible"] is False


def test_tie_only_cell_reports_economic_interval_and_null_hit_interval():
    rows = [_row(_epoch(TUESDAY, 10, 15 * i), 1.0, 0.0, key=f"t{i}") for i in range(3)]
    selector = _select(rows)
    m = sc.cell_metrics(selector.counts(), selector.windows, resamples=10)
    assert (m["n_ties"], m["n_decided"], m["n_economic"]) == (3, 0, 3)
    assert (m["n_sessions"], m["n_decided_sessions"]) == (1, 0)
    assert m["hit_rate"] is None and m["z_hit_descriptive"] is None
    assert m["mean_signed_bps"] == 0.0
    assert m["bootstrap_mean_signed_bps"]["interval_999"] == [0.0, 0.0]
    assert m["bootstrap_hit_rate"]["interval_95"] is None


def test_session_counts_only_count_contributing_sessions():
    rows = [_row(_epoch(TUESDAY, 9, 30), 1.0, 2.0, key="a"),
            _row(_epoch(WEDNESDAY, 9, 30), 1.0, 0.0, key="b")]
    selector = _select(rows)
    m = sc.cell_metrics(selector.counts(), selector.windows, resamples=10)
    assert (m["n_sessions"], m["n_decided_sessions"]) == (2, 1)


def _ten_session_windows(outcome: float):
    sessions = [d for d in (date(2026, 8, 3 + i) for i in range(14)) if d.weekday() < 5][:10]
    rows = []
    for day in sessions:
        for i in range(12):
            hour, minute = 9 + (i + 2) // 4, ((i + 2) % 4) * 15
            rows.append(_row(_epoch(day, hour, minute), 1.0, outcome, key=f"{day}-{i:02d}"))
    return rows


def test_eligible_cell_metrics_over_ten_sessions():
    selector = _select(_ten_session_windows(5.0))
    m = sc.cell_metrics(selector.counts(), selector.windows, resamples=200)
    assert m["n_economic"] == 120 and m["n_sessions"] == 10 and m["eligible"] is True
    assert m["bootstrap_mean_signed_bps"]["interval_999"] == [5.0, 5.0]


def test_assign_labels_within_budget():
    cells = [
        {"eligible": True, "bootstrap_mean_signed_bps": {"interval_999": [1.0, 2.0]}},
        {"eligible": True, "bootstrap_mean_signed_bps": {"interval_999": [-1.0, 2.0]}},
        {"eligible": True, "bootstrap_mean_signed_bps": {"interval_999": [0.0, 1.0]}},
        {"eligible": False, "bootstrap_mean_signed_bps": {"interval_999": [9.0, 9.0]}},
    ]
    budget = sc.assign_labels(cells)
    assert [c["label"] for c in cells] == [sc.LABEL_CANDIDATE, sc.LABEL_NOISE,
                                           sc.LABEL_NOISE, sc.LABEL_INSUFFICIENT]
    assert all(c["classification_reason"] is None for c in cells)
    assert budget == {"n_cells_eligible": 3, "multiplicity_budget": 100,
                      "expected_false_candidates": pytest.approx(0.0015),
                      "multiplicity_budget_exceeded": False, "usable_for_e2": True}


def test_assign_labels_exactly_one_hundred_is_permitted():
    cells = [{"eligible": True, "bootstrap_mean_signed_bps": {"interval_999": [1.0, 2.0]}}
             for _ in range(100)]
    budget = sc.assign_labels(cells)
    assert budget["multiplicity_budget_exceeded"] is False and budget["usable_for_e2"] is True
    assert all(c["label"] == sc.LABEL_CANDIDATE for c in cells)


def test_assign_labels_over_budget_withholds_without_relabeling():
    cells = [{"eligible": True, "bootstrap_mean_signed_bps": {"interval_999": [1.0, 2.0]}}
             for _ in range(101)]
    cells.append({"eligible": False, "bootstrap_mean_signed_bps": {"interval_999": None}})
    budget = sc.assign_labels(cells)
    assert budget["n_cells_eligible"] == 101
    assert budget["multiplicity_budget_exceeded"] is True and budget["usable_for_e2"] is False
    eligible = cells[:101]
    assert all(c["label"] is None and c["classification_reason"] == sc.REASON_BUDGET
               for c in eligible)
    assert cells[101]["label"] == sc.LABEL_INSUFFICIENT
    assert cells[101]["classification_reason"] is None
    # descriptive statistics untouched
    assert cells[0]["bootstrap_mean_signed_bps"]["interval_999"] == [1.0, 2.0]


def test_score_cells_fixed_order_and_both_layers():
    rows = [
        _row(_epoch(TUESDAY, 9, 30), 1.0, 1.0, horizon="1H", cell=("q1", "f", "COIN", "1H"), key="a"),
        _row(_epoch(TUESDAY, 9, 30), 1.0, 1.0, horizon="30S", cell=("q1", "f", "COIN", "30S"), key="b"),
        _row(_epoch(TUESDAY, 9, 30), 1.0, 1.0, horizon="30S", layer=sc.LAYER_V9,
             cell=("V3", "COIN", "30S", "cohort:a", "hash:a"), key="c"),
    ]
    cells = sc.score_cells(sc.select_cells(rows), resamples=5)
    assert [(c["layer"], c["cell"]["horizon"]) for c in cells] == [
        ("FAMILY", "30S"), ("FAMILY", "1H"), ("V9", "30S")]
    assert cells[2]["cell"] == {"v3_model_version": "V3", "symbol": "COIN", "horizon": "30S",
                                "cohort_id": "cohort:a", "cohort_hash": "hash:a"}


def test_pearson_returns_none_on_degenerate_input():
    assert sc.pearson([1.0], [1.0]) is None
    assert sc.pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None
    assert sc.pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)


# --- row mappers ---------------------------------------------------------------


def test_family_rows_apply_proof_and_timing_rules():
    maturity = 1_700_000_900.0
    observed_early = datetime.fromtimestamp(maturity - 1, timezone.utc)
    observed_late = datetime.fromtimestamp(maturity + 1, timezone.utc)
    batch = [
        (1, "q1", "f1", "COIN", "15M", maturity - 900, maturity, 2.0, 3.0, maturity + 1.0),
        (2, "q1", "f1", "COIN", "15M", maturity - 900, maturity, 2.0, 3.0, maturity + 6.0),
        (3, "q1", "f1", "COIN", "15M", maturity - 900, maturity, 2.0, 3.0, maturity + 1.0),
        (4, "q1", "f1", "COIN", "15M", maturity - 900, maturity, 2.0, None, None),
        (5, "q1", "f1", "COIN", "15M", maturity - 900, maturity, 2.0, 3.0, maturity + 1.0),
    ]
    forecast_proofs = {1: observed_early, 2: observed_early, 3: observed_late, 5: observed_early}
    outcome_proofs = {1: observed_early, 2: observed_early, 3: observed_early}
    rows = sc.family_rows(batch, forecast_proofs, outcome_proofs)
    assert [(r.admissible, r.outcome_eligible) for r in rows] == [
        (True, True),     # proof before maturity, resolved within 5s
        (True, False),    # resolved after the bound
        (False, False),   # commit observed after maturity
        (False, False),   # no forecast proof
        (True, False),    # no outcome proof
    ]
    assert rows[0].record_key == "1".zfill(20) and rows[0].cell == ("q1", "f1", "COIN", "15M")


def test_v9_rows_hydrate_through_authoritative_seam(monkeypatch):
    cutoff = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    calls = []

    def fake_forecast(payload, *, expected_hash=None):
        return SimpleNamespace(cutoff_at=cutoff, expected_return_bps=1.25,
                               persistence_proof_eligible=None, payload=payload,
                               expected_hash=expected_hash)

    def fake_apply(record, row):
        calls.append(row)
        return SimpleNamespace(cutoff_at=record.cutoff_at,
                               expected_return_bps=record.expected_return_bps,
                               persistence_proof_eligible=(row is not None and row[4] is True))

    def fake_outcome(payload, *, expected_hash=None):
        return SimpleNamespace(actual_return_bps=-2.0, target_timing_status="VERIFIED",
                               proof_eligible=payload.get("ok", False))

    monkeypatch.setitem(sys.modules, "quant.v9_v4a_evidence", SimpleNamespace(
        V4AWriter=SimpleNamespace(_apply_commit_proof=staticmethod(fake_apply)),
        deserialize_forecast_record=fake_forecast,
        deserialize_outcome_record=fake_outcome))
    proof_row = ("fid1", "fhash", cutoff, cutoff, True, "M")
    batch = [
        ("fid1", "fhash", "V3", "COIN", "15M", "cohort:a", "hash:a", {"f": 1}, "ohash", {"ok": True}),
        ("fid2", "fhash", "V3", "COIN", "15M", "cohort:a", "hash:a", {"f": 2}, "ohash", {"ok": True}),
        ("fid3", "fhash", "V3", "COIN", "15M", "cohort:a", "hash:a", {"f": 3}, "ohash", {"ok": False}),
        ("fid4", "fhash", "V3", "COIN", "15M", "cohort:a", "hash:a", {"f": 4}, None, None),
    ]
    rows = sc.v9_rows(batch, {"fid1": proof_row, "fid2": None,
                              "fid3": ("fid3", "h", cutoff, cutoff, True, "M")})
    assert [(r.admissible, r.outcome_eligible) for r in rows] == [
        (True, True), (False, False), (True, False), (False, False)]
    assert rows[0].cell == ("V3", "COIN", "15M", "cohort:a", "hash:a")
    assert rows[0].cutoff_epoch == cutoff.timestamp() and rows[0].outcome_bps == -2.0
    assert calls[0] == proof_row and calls[1] is None


# --- guards, receipt, command line ---------------------------------------------


def test_session_helpers():
    assert sc.recent_weekday_sessions(3, date(2026, 9, 2)) == [
        date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)]
    assert sc.parse_sessions("2026-09-01, 2026-08-31,2026-09-01") == [
        date(2026, 8, 31), date(2026, 9, 1)]
    with pytest.raises(ValueError):
        sc.parse_sessions(" , ")
    lo, hi = sc.session_epoch_bounds([date(2026, 9, 1), date(2026, 8, 31)])
    assert lo == datetime(2026, 8, 31, 0, 0, tzinfo=NY).timestamp()
    assert hi == datetime(2026, 9, 2, 0, 0, tzinfo=NY).timestamp()
    assert [list(b) for b in sc.batched([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]


def test_receipt_fields_and_hash():
    receipt = sc.build_receipt(
        sessions=[date(2026, 9, 1)], cells=[{"layer": "FAMILY"}],
        budget={"n_cells_eligible": 0, "multiplicity_budget": 100,
                "expected_false_candidates": 0.0, "multiplicity_budget_exceeded": False,
                "usable_for_e2": True},
        rows_read={"forecasts": 1}, proof_rows={"DIRECTIONAL_FORECAST": 1},
        snapshot="100:100:", current_user="atom_e1_scorecard_reader",
        query_wall_seconds=0.5,
        generated_at=datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc))
    body = {k: v for k, v in receipt.items() if k != "sha256"}
    assert receipt["sha256"] == hashlib.sha256(sc.canonical_json(body).encode()).hexdigest()
    assert (receipt["forecast_writes"], receipt["outcome_writes"], receipt["evidence_writes"],
            receipt["read_only"], receipt["rls_full_read_verified"]) == (0, 0, 0, True, True)
    assert receipt["current_user"] == "atom_e1_scorecard_reader"
    assert receipt["cost_bps"] == 0.0 and receipt["snapshot"] == "100:100:"
    assert receipt["bootstrap"]["resamples"] == 200_000 and receipt["bootstrap"]["seed"] == 0
    assert receipt["classification"]["multiplicity_budget"] == 100
    json.loads(sc.canonical_json(receipt))


def test_frozen_constants():
    assert sc.BOOTSTRAP_RESAMPLES == 200_000 and sc.BOOTSTRAP_SEED == 0
    assert (sc.INTERVAL_WIDE, sc.INTERVAL_NARROW) == (0.999, 0.95)
    assert (sc.MIN_ECONOMIC_WINDOWS, sc.MIN_SESSIONS, sc.MULTIPLICITY_BUDGET) == (100, 10, 100)
    assert sc.COST_BPS == 0.0 and sc.PROOF_BATCH == 65_536
    assert sc.FALSE_CANDIDATE_RATE == pytest.approx(0.0005)
    assert sc.OUTCOME_RESOLUTION_BOUND_SECONDS == 5.0
    assert sc.READONLY_URL_ENV != "DATABASE_URL"
    assert sc.READONLY_ROLE == "atom_e1_scorecard_reader"


def test_module_sql_and_source_contain_no_write_paths():
    source = Path(sc.__file__).read_text(encoding="utf-8")
    for sql in (sc.GUARD_SQL, sc.RLS_FULL_READ_SQL, sc.FAMILY_STREAM_SQL, sc.FAMILY_PROOF_SQL,
                sc.V9_STREAM_SQL, sc.V9_PROOF_SQL, *sc.COUNT_SQL.values()):
        lowered = sql.lower()
        assert not any(word in lowered for word in
                       ("insert ", "update ", "delete ", "truncate", "copy ", "alter ",
                        "drop ", "grant ", "create "))
    assert "connection.read_only = True" in source
    assert "rolbypassrls" not in source and "BYPASSRLS" not in source.replace("full-read", "")
    assert "verify_full_read(current_user" in source
    assert "verify_reader_identity(current_user)" in source
    assert "atom_historical_score_reader" not in source
    assert "IsolationLevel.REPEATABLE_READ" in source
    assert "statement_timeout={STATEMENT_TIMEOUT_MS}" in source and sc.STATEMENT_TIMEOUT_MS <= 60_000
    assert "read_legacy_evidence_publications_for_cohorts" not in source
    assert "read_legacy_evidence_publications_for_records" in sc.FAMILY_PROOF_SQL
    assert "read_forecast_commit_proof" in sc.V9_PROOF_SQL
    assert "import psycopg" in source and not source.startswith("import psycopg")
    assert "DATABASE_URL\")" not in source.replace(sc.READONLY_URL_ENV, "")


def test_main_refuses_without_readonly_url_and_on_weekend_sessions(monkeypatch):
    monkeypatch.delenv(sc.READONLY_URL_ENV, raising=False)
    with pytest.raises(SystemExit):
        sc.main(["--sessions", "2026-09-01"])
    monkeypatch.setenv(sc.READONLY_URL_ENV, "postgresql://read-only")
    with pytest.raises(SystemExit):
        sc.main(["--sessions", "2026-09-05"])


def test_main_emits_receipt_from_read_seam(monkeypatch, capsys):
    monkeypatch.setenv(sc.READONLY_URL_ENV, "postgresql://read-only")
    selectors = sc.select_cells([_row(_epoch(TUESDAY, 9, 30), 2.0, 3.0, key="a")])
    monkeypatch.setattr(sc, "read_and_select", lambda url, sessions: (
        selectors, {"forecasts": 1}, {"DIRECTIONAL_FORECAST": 1}, "1:1:",
        "atom_e1_scorecard_reader", 0.01))
    original_score_cells = sc.score_cells
    monkeypatch.setattr(sc, "score_cells",
                        lambda s, **kw: original_score_cells(s, resamples=5))
    assert sc.main(["--sessions", "2026-09-01"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["sessions"] == ["2026-09-01"] and receipt["cost_bps"] == 0.0
    assert receipt["read_only"] is True and receipt["rls_full_read_verified"] is True
    assert receipt["current_user"] == "atom_e1_scorecard_reader"
    assert len(receipt["cells"]) == 1
    assert receipt["cells"][0]["label"] == sc.LABEL_INSUFFICIENT
    assert receipt["cells"][0]["classification_reason"] is None
    assert receipt["classification"]["usable_for_e2"] is True


def test_verify_full_read_refuses_anything_short_of_permissive_true_policy():
    ok = [(t, True, True, False) for t in sc.EVIDENCE_TABLES]
    sc.verify_full_read("reader", ok)
    with pytest.raises(SystemExit):
        sc.verify_full_read("reader", ok[:3])                       # a table missing
    for bad in (
        [("public.forecasts", False, True, False)],                 # no SELECT privilege
        [("public.forecasts", True, False, False)],                 # no permissive USING (true)
        [("public.forecasts", True, True, True)],                   # restrictive policy applies
    ):
        rows = bad + [r for r in ok if r[0] != "public.forecasts"]
        with pytest.raises(SystemExit):
            sc.verify_full_read("reader", rows)


def test_verify_reader_identity_accepts_only_the_dedicated_role():
    sc.verify_reader_identity("atom_e1_scorecard_reader")
    for other in ("postgres", "atom_historical_score_reader", "supabase_read_only_user",
                  "atom_v9_v4_runtime", ""):
        with pytest.raises(SystemExit):
            sc.verify_reader_identity(other)
