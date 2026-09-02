"""E-1 read-only evidence scorecard — frozen statistics on synthetic rows."""

from __future__ import annotations

import io
import json
import math
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from quant import evidence_scorecard as sc
from quant.evidence_scorecard import Observation

ET = ZoneInfo("America/New_York")
SESSION = "2026-08-27"  # EDT: RTH 13:30–20:00 UTC


def _epoch(session: str, hour: int, minute: int, second: int = 0) -> float:
    day = date.fromisoformat(session)
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ET).timestamp()


def _obs(cutoff: float, forecast, outcome, *, horizon="15M", session=SESSION,
         layer="FAMILY", cell=("q1_momentum", "v1", "COIN", "15M")) -> Observation:
    return Observation(layer=layer, cell=cell, horizon=horizon, session=session,
                       cutoff_epoch=cutoff, forecast_bps=forecast, outcome_bps=outcome)


# --------------------------------------------------------------------------- #
# Sessions and RTH
# --------------------------------------------------------------------------- #

def test_rth_bounds_are_edt_aware():
    open_epoch, close_epoch = sc.session_rth_bounds(SESSION)
    assert open_epoch == datetime(2026, 8, 27, 13, 30, tzinfo=timezone.utc).timestamp()
    assert close_epoch == datetime(2026, 8, 27, 20, 0, tzinfo=timezone.utc).timestamp()


def test_rth_window_requires_full_interval_inside_session():
    assert sc.is_rth_window(_epoch(SESSION, 9, 30), "30S", SESSION)
    assert sc.is_rth_window(_epoch(SESSION, 15, 59, 30), "30S", SESSION)
    assert not sc.is_rth_window(_epoch(SESSION, 15, 59, 45), "30S", SESSION)
    assert not sc.is_rth_window(_epoch(SESSION, 9, 29, 59), "30S", SESSION)
    assert not sc.is_rth_window(_epoch(SESSION, 9, 0), "1M", SESSION)
    assert sc.is_rth_window(_epoch(SESSION, 15, 0), "1H", SESSION)
    assert not sc.is_rth_window(_epoch(SESSION, 15, 0, 1), "1H", SESSION)


def test_reader_refuses_regular_trading_hours():
    with pytest.raises(RuntimeError):
        sc.refuse_during_rth(datetime(2026, 9, 1, 10, 0, tzinfo=ET))
    with pytest.raises(RuntimeError):
        sc.refuse_during_rth(datetime(2026, 9, 1, 15, 59, 59, tzinfo=ET))
    sc.refuse_during_rth(datetime(2026, 9, 1, 8, 0, tzinfo=ET))
    sc.refuse_during_rth(datetime(2026, 9, 1, 16, 0, tzinfo=ET))
    sc.refuse_during_rth(datetime(2026, 9, 5, 12, 0, tzinfo=ET))  # Saturday


def test_default_sessions_are_prior_weekdays_sorted():
    assert sc.default_sessions(3, today=date(2026, 9, 2)) == [
        "2026-08-28", "2026-08-31", "2026-09-01"]
    with pytest.raises(ValueError):
        sc.default_sessions(0)


def test_market_session_of_uses_new_york_date():
    assert sc.market_session_of(_epoch(SESSION, 23, 30)) == SESSION
    assert sc.market_session_of(_epoch(SESSION, 23, 30) + 3600) == "2026-08-28"


# --------------------------------------------------------------------------- #
# Kinds, windows, correlation, quantiles
# --------------------------------------------------------------------------- #

def test_observation_kind_classification():
    assert sc.observation_kind(_obs(1.0, None, 2.0)) == "ABSTAIN"
    assert sc.observation_kind(_obs(1.0, 0.0, 2.0)) == "ABSTAIN"
    assert sc.observation_kind(_obs(1.0, math.nan, 2.0)) == "ABSTAIN"
    assert sc.observation_kind(_obs(1.0, 1.0, None)) == "UNRESOLVED"
    assert sc.observation_kind(_obs(1.0, 1.0, math.inf)) == "UNRESOLVED"
    assert sc.observation_kind(_obs(1.0, 1.0, 0.0)) == "TIE"
    assert sc.observation_kind(_obs(1.0, -1.0, 3.0)) == "DECIDED"


def test_observation_rejects_bad_inputs():
    with pytest.raises(ValueError):
        _obs(1.0, 1.0, 1.0, horizon="2H")
    with pytest.raises(ValueError):
        _obs(math.nan, 1.0, 1.0)
    with pytest.raises(ValueError):
        _obs(1.0, 1.0, 1.0, layer="OTHER")
    with pytest.raises(ValueError):
        _obs(1.0, 1.0, 1.0, session="2026-13-01")


def test_independent_windows_keep_earliest_per_interval():
    rows = [
        _obs(105.0, 1.0, 1.0, horizon="30S"),
        _obs(100.0, 1.0, 1.0, horizon="30S"),
        _obs(120.0, 1.0, 1.0, horizon="30S"),
        _obs(100.0, -1.0, 1.0, horizon="30S"),  # same cutoff: smaller forecast wins
    ]
    cells, discarded = sc.select_independent_windows(rows)
    windows = cells[("FAMILY", ("q1_momentum", "v1", "COIN", "15M"))]
    assert discarded == 2
    assert [w.cutoff_epoch for w in windows] == [100.0, 120.0]
    assert windows[0].forecast_bps == -1.0


def test_independent_windows_are_per_cell():
    a = _obs(100.0, 1.0, 1.0, horizon="30S", cell=("q1", "v1", "COIN", "30S"))
    b = _obs(100.0, 1.0, 1.0, horizon="30S", cell=("q2", "v1", "COIN", "30S"))
    cells, discarded = sc.select_independent_windows([a, b])
    assert discarded == 0 and len(cells) == 2


def test_pearson_hand_values():
    assert sc.pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert sc.pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert sc.pearson([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)
    assert sc.pearson([1, 1, 1], [1, 2, 3]) is None
    assert sc.pearson([1], [1]) is None
    with pytest.raises(ValueError):
        sc.pearson([1, 2], [1])


def test_quantile_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0]
    assert sc.quantile(values, 0.0) == 1.0
    assert sc.quantile(values, 1.0) == 4.0
    assert sc.quantile(values, 0.5) == 2.5
    assert sc.quantile(values, 0.25) == 1.75
    with pytest.raises(ValueError):
        sc.quantile([], 0.5)
    with pytest.raises(ValueError):
        sc.quantile(values, 1.5)


# --------------------------------------------------------------------------- #
# Clustered bootstrap
# --------------------------------------------------------------------------- #

def test_bootstrap_single_session_is_degenerate():
    intervals = sc.clustered_bootstrap({"2026-08-27": [1.0, 3.0]}, sc._mean,
                                       resamples=50, seed=0)
    assert intervals == {"0.999": (2.0, 2.0), "0.95": (2.0, 2.0)}


def test_bootstrap_is_deterministic_and_session_clustered():
    sessions = {"2026-08-27": [1.0, 1.0], "2026-08-28": [3.0, 3.0]}
    first = sc.clustered_bootstrap(sessions, sc._mean, resamples=200, seed=0)
    second = sc.clustered_bootstrap(sessions, sc._mean, resamples=200, seed=0)
    assert first == second
    low, high = first["0.95"]
    # every resample mean is 1.0, 2.0, or 3.0 because whole sessions are drawn
    assert 1.0 <= low <= high <= 3.0
    assert first["0.999"][0] <= low and first["0.999"][1] >= high
    other = sc.clustered_bootstrap(sessions, sc._mean, resamples=200, seed=1)
    assert set(other) == {"0.999", "0.95"}


def test_bootstrap_rejects_empty_or_bad_parameters():
    with pytest.raises(ValueError):
        sc.clustered_bootstrap({"2026-08-27": []}, sc._mean)
    with pytest.raises(ValueError):
        sc.clustered_bootstrap({"2026-08-27": [1.0]}, sc._mean, resamples=0)
    with pytest.raises(ValueError):
        sc.clustered_bootstrap({"2026-08-27": [1.0]}, sc._mean, levels=(1.5,))


# --------------------------------------------------------------------------- #
# Cell metrics and labels — hand computed
# --------------------------------------------------------------------------- #

def _twelve_session_cell(*, sessions: int = 12) -> list[Observation]:
    """12 sessions x 10 RTH 15M windows: 7 hits (+5), 2 misses (-1), 1 tie."""

    rows = []
    start = date(2026, 8, 3)  # Monday
    produced = 0
    day = start
    while produced < sessions:
        if day.weekday() < 5:
            session = day.isoformat()
            outcomes = [5.0] * 7 + [-1.0] * 2 + [0.0]
            for index, outcome in enumerate(outcomes):
                cutoff = _epoch(session, 10, 0) + index * 900.0
                rows.append(_obs(cutoff, 1.0, outcome, session=session))
            produced += 1
        day = date.fromordinal(day.toordinal() + 1)
    return rows


def test_cell_metrics_hand_computed_candidate():
    rows = _twelve_session_cell()
    rows.append(_obs(_epoch(SESSION, 8, 0), 1.0, 9.0))      # pre-market: excluded
    rows.append(_obs(_epoch(SESSION, 15, 50), 1.0, 9.0))    # 15M past close: excluded
    rows.append(_obs(_epoch(SESSION, 12, 0), None, 9.0))    # abstention
    rows.append(_obs(_epoch(SESSION, 12, 15), 2.0, None))   # unresolved
    metrics = sc.cell_metrics(rows, cost_bps=1.0, resamples=100)
    assert metrics["n_windows"] == 124
    assert metrics["n_excluded_non_rth"] == 2
    assert metrics["n_rth_windows"] == 122
    assert metrics["n_abstain"] == 1
    assert metrics["n_unresolved"] == 1
    assert metrics["n_ties"] == 12
    assert metrics["n_decided"] == 108
    assert metrics["n_economic"] == 120
    assert metrics["n_sessions"] == 12
    assert metrics["hit_rate"] == pytest.approx(7 / 9)
    assert metrics["z_hit_descriptive_only"] == pytest.approx(
        ((7 / 9) - 0.5) * math.sqrt(108) / 0.5)
    assert metrics["mean_signed_bps"] == pytest.approx(3.3)
    assert metrics["mean_cost_adjusted_bps"] == pytest.approx(2.3)
    assert metrics["corr_forecast_outcome"] is None          # constant forecast
    assert metrics["calibration_corr_abs"] is None
    quartiles = metrics["hit_rate_by_magnitude_quartile"]
    assert [q["n"] for q in quartiles] == [27, 27, 27, 27]
    assert all(q["hit_rate"] == pytest.approx(7 / 9) for q in quartiles)
    # identical sessions => degenerate bootstrap => interval collapses on 2.3
    assert metrics["bootstrap_mean_cost_adjusted_bps"]["0.999"] == pytest.approx([2.3, 2.3])
    assert metrics["bootstrap_hit_rate"]["0.95"] == pytest.approx([7 / 9, 7 / 9])
    assert metrics["label"] == "CANDIDATE"


def test_cell_metrics_cost_turns_candidate_into_noise():
    metrics = sc.cell_metrics(_twelve_session_cell(), cost_bps=4.0, resamples=100)
    assert metrics["mean_cost_adjusted_bps"] == pytest.approx(-0.7)
    assert metrics["label"] == "NOISE"


def test_cell_metrics_ties_count_as_zero_in_economic_not_in_hit_rate():
    session = SESSION
    rows = [_obs(_epoch(session, 10, 0) + i * 900.0, 1.0, o)
            for i, o in enumerate([4.0, 0.0, 0.0, 0.0])]
    metrics = sc.cell_metrics(rows, cost_bps=0.0, resamples=10)
    assert metrics["hit_rate"] == 1.0                 # one decided window, a hit
    assert metrics["mean_signed_bps"] == 1.0          # (4 + 0 + 0 + 0) / 4
    assert metrics["label"] == "INSUFFICIENT"


def test_cell_metrics_negative_forecast_sign_convention():
    rows = [_obs(_epoch(SESSION, 10, 0) + i * 900.0, -2.0, o)
            for i, o in enumerate([-3.0, 3.0])]
    metrics = sc.cell_metrics(rows, cost_bps=0.0, resamples=10)
    assert metrics["hit_rate"] == 0.5
    assert metrics["mean_signed_bps"] == pytest.approx(0.0)   # (+3 - 3) / 2
    assert metrics["corr_forecast_outcome"] is None           # constant forecast


def test_cell_metrics_correlation_and_calibration():
    rows = [_obs(_epoch(SESSION, 10, 0) + i * 900.0, f, o) for i, (f, o) in
            enumerate([(1.0, 2.0), (2.0, 4.0), (3.0, 6.0), (-1.0, -2.0)])]
    metrics = sc.cell_metrics(rows, cost_bps=0.0, resamples=10)
    assert metrics["corr_forecast_outcome"] == pytest.approx(1.0)
    assert metrics["calibration_corr_abs"] == pytest.approx(1.0)
    assert metrics["hit_rate"] == 1.0
    assert metrics["mean_signed_bps"] == pytest.approx(3.5)


def test_label_requires_sessions_windows_and_positive_interval():
    nine = sc.cell_metrics(_twelve_session_cell(sessions=9), cost_bps=0.0, resamples=20)
    assert nine["n_economic"] == 90 and nine["label"] == "INSUFFICIENT"
    assert sc.label_cell({"n_economic": 500, "n_sessions": 12,
                          "bootstrap_mean_cost_adjusted_bps": None}) == "INSUFFICIENT"
    assert sc.label_cell({"n_economic": 500, "n_sessions": 12,
                          "bootstrap_mean_cost_adjusted_bps": {"0.999": (0.0, 1.0)}}) == "NOISE"
    assert sc.label_cell({"n_economic": 500, "n_sessions": 12,
                          "bootstrap_mean_cost_adjusted_bps": {"0.999": (-5.0, -1.0)}}) == "NOISE"
    assert sc.label_cell({"n_economic": 500, "n_sessions": 12,
                          "bootstrap_mean_cost_adjusted_bps": {"0.999": (0.01, 1.0)}}) == "CANDIDATE"


def test_cell_metrics_rejects_non_finite_cost():
    with pytest.raises(ValueError):
        sc.cell_metrics(_twelve_session_cell(sessions=1), cost_bps=math.nan)


# --------------------------------------------------------------------------- #
# score(): partial sessions, every cell, ordering
# --------------------------------------------------------------------------- #

def test_score_excludes_partial_and_empty_sessions():
    full = [_obs(_epoch("2026-08-27", 9, 30) + i * 900.0, 1.0, 1.0, session="2026-08-27")
            for i in range(26)]                    # 09:30 .. 15:45 => coverage 0.96
    partial = [_obs(_epoch("2026-08-28", 9, 30) + i * 900.0, 1.0, 1.0, session="2026-08-28")
               for i in range(10)]                 # 09:30 .. 11:45 => coverage 0.35
    scored = sc.score(full + partial, sessions=["2026-08-27", "2026-08-28", "2026-08-31"],
                      cost_bps=0.0, resamples=10)
    assert scored["sessions_scored"] == ["2026-08-27"]
    assert set(scored["sessions_excluded_partial"]) == {"2026-08-28", "2026-08-31"}
    assert scored["session_coverage"]["2026-08-27"] == pytest.approx(6.25 / 6.5, abs=1e-6)
    assert scored["session_coverage"]["2026-08-31"] == 0.0
    assert scored["observations_in_scope"] == 26
    assert len(scored["cells"]) == 1
    assert scored["label_counts"] == {"INSUFFICIENT": 1, "NOISE": 0, "CANDIDATE": 0}


def test_score_orders_cells_by_layer_then_horizon():
    rows = [
        _obs(_epoch(SESSION, 9, 30), 1.0, 1.0, horizon="1H", layer="V9",
             cell=("ATOM-TRUE-V9-V3", "COIN", "1H")),
        _obs(_epoch(SESSION, 9, 30), 1.0, 1.0, horizon="30S", layer="V9",
             cell=("ATOM-TRUE-V9-V3", "COIN", "30S")),
        _obs(_epoch(SESSION, 9, 30), 1.0, 1.0, horizon="5M",
             cell=("q9_factor", "v1", "COIN", "5M")),
    ]
    # make the session count as full coverage
    rows += [_obs(_epoch(SESSION, 15, 45), 1.0, 1.0, horizon="5M",
                  cell=("q9_factor", "v1", "COIN", "5M"))]
    scored = sc.score(rows, sessions=[SESSION], cost_bps=0.0, resamples=10)
    assert [(c["layer"], c["horizon"]) for c in scored["cells"]] == [
        ("FAMILY", "5M"), ("V9", "30S"), ("V9", "1H")]


def test_score_rejects_invalid_session_strings():
    with pytest.raises(ValueError):
        sc.score([], sessions=["not-a-date"], cost_bps=0.0)


# --------------------------------------------------------------------------- #
# Receipt
# --------------------------------------------------------------------------- #

def test_receipt_is_canonical_hashed_and_read_only():
    scored = sc.score(_twelve_session_cell(), sessions=sorted({o.session for o in
                      _twelve_session_cell()}), cost_bps=1.0, resamples=20)
    receipt = sc.build_receipt(scored, cost_bps=1.0, rows_read={"FAMILY": 120, "V9": 0},
                               query_seconds=0.5, resamples=20)
    assert receipt["forecast_writes"] == 0 and receipt["outcome_writes"] == 0
    assert receipt["evidence_writes"] == 0 and receipt["read_only"] is True
    assert receipt["code_version"] == sc.CODE_VERSION
    assert receipt["bootstrap"] == {"resamples": 20, "seed": 0, "levels": ["0.999", "0.95"],
                                    "classification_level": "0.999"}
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    import hashlib
    assert receipt["receipt_sha256"] == hashlib.sha256(
        sc.canonical_json(body).encode("utf-8")).hexdigest()
    again = sc.build_receipt(scored, cost_bps=1.0, rows_read={"FAMILY": 120, "V9": 0},
                             query_seconds=0.5, resamples=20)
    assert again["receipt_sha256"] == receipt["receipt_sha256"]
    changed = sc.build_receipt(scored, cost_bps=2.0, rows_read={"FAMILY": 120, "V9": 0},
                               query_seconds=0.5, resamples=20)
    assert changed["receipt_sha256"] != receipt["receipt_sha256"]
    json.loads(sc.canonical_json(receipt))


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        sc.canonical_json({"x": math.nan})


# --------------------------------------------------------------------------- #
# Thin read-only database seam (fakes only; no driver)
# --------------------------------------------------------------------------- #

class _FakeCursor:
    def __init__(self, rows, log):
        self._rows = rows
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self._log.append((sql, params))

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, family_rows=(), v9_rows=()):
        self.family_rows = family_rows
        self.v9_rows = v9_rows
        self.log = []
        self.closed = False
        self._calls = 0

    def cursor(self):
        self._calls += 1
        rows = self.family_rows if self._calls % 2 == 1 else self.v9_rows
        return _FakeCursor(rows, self.log)

    def close(self):
        self.closed = True


def test_family_read_converts_rows_and_bounds_whole_day():
    cutoff = _epoch(SESSION, 10, 0)
    connection = _FakeConnection(family_rows=[
        ("q1_momentum", "v1", "COIN", "15M", cutoff, 2.5, -1.25),
        ("q2_mean_reversion", "v1", "COIN", "30S", cutoff, None, None),
    ])
    observations = sc.read_family_observations(connection, SESSION)
    assert observations[0] == Observation("FAMILY", ("q1_momentum", "v1", "COIN", "15M"),
                                          "15M", SESSION, cutoff, 2.5, -1.25)
    assert observations[1].forecast_bps is None and observations[1].outcome_bps is None
    sql, params = connection.log[0]
    assert "DISTINCT ON" in sql and "forecast_outcomes" in sql
    assert params["symbol"] == "COIN"
    assert params["start_epoch"] == _epoch(SESSION, 4, 0)
    assert params["end_epoch"] == _epoch(SESSION, 20, 0)


def test_v9_read_uses_existing_decoders_and_verified_only():
    cutoff_at = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)
    seen = []

    def decode_forecast(payload, *, expected_hash):
        seen.append(("forecast", payload, expected_hash))
        return SimpleNamespace(cutoff_at=cutoff_at, expected_return_bps=0.75)

    def decode_outcome(payload, *, expected_hash):
        seen.append(("outcome", payload, expected_hash))
        return SimpleNamespace(actual_return_bps=-3.0, target_timing_status="VERIFIED")

    connection = _FakeConnection(family_rows=[], v9_rows=[
        ("ATOM-TRUE-V9-V3", "COIN", "15M", "f" * 64, {"f": 1}, "o" * 64, {"o": 1}),
        ("ATOM-TRUE-V9-V3", "COIN", "15M", "a" * 64, {"f": 2}, None, None),
    ])
    connection._calls = 1  # next cursor serves v9 rows
    observations = sc.read_v9_observations(
        connection, SESSION, decode_forecast=decode_forecast, decode_outcome=decode_outcome)
    assert observations[0].cell == ("ATOM-TRUE-V9-V3", "COIN", "15M")
    assert observations[0].cutoff_epoch == cutoff_at.timestamp()
    assert observations[0].forecast_bps == 0.75 and observations[0].outcome_bps == -3.0
    assert observations[1].outcome_bps is None
    assert seen[0] == ("forecast", {"f": 1}, "f" * 64)
    assert seen[1] == ("outcome", {"o": 1}, "o" * 64)


def test_v9_read_fails_closed_on_non_verified_outcome():
    connection = _FakeConnection(family_rows=[], v9_rows=[
        ("ATOM-TRUE-V9-V3", "COIN", "15M", "f" * 64, {}, "o" * 64, {}),
    ])
    connection._calls = 1
    with pytest.raises(RuntimeError):
        sc.read_v9_observations(
            connection, SESSION,
            decode_forecast=lambda payload, *, expected_hash: SimpleNamespace(
                cutoff_at=datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc),
                expected_return_bps=1.0),
            decode_outcome=lambda payload, *, expected_hash: SimpleNamespace(
                actual_return_bps=1.0, target_timing_status="UNVERIFIED"))


def test_statement_timeout_is_bounded_by_freeze():
    assert sc.STATEMENT_TIMEOUT_SECONDS <= 60
    assert sc.BOOTSTRAP_RESAMPLES == 2000 and sc.BOOTSTRAP_SEED == 0
    assert sc.INTERVAL_LEVELS == (0.999, 0.95) and sc.CLASSIFICATION_LEVEL == 0.999
    assert sc.MIN_ECONOMIC_WINDOWS == 100 and sc.MIN_SESSIONS == 10


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #

def test_main_emits_receipt_outside_rth_and_closes_connection(monkeypatch):
    cutoff = _epoch(SESSION, 10, 0)
    connection = _FakeConnection(
        family_rows=[("q1_momentum", "v1", "COIN", "15M", cutoff, 1.0, 2.0)], v9_rows=[])
    fake_seam = SimpleNamespace(
        deserialize_forecast_record=lambda payload, *, expected_hash: None,
        deserialize_outcome_record=lambda payload, *, expected_hash: None)
    import sys
    monkeypatch.setitem(sys.modules, "quant.v9_v4a_evidence", fake_seam)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = sc.main(["--cost-bps", "6", "--sessions", SESSION],
                       connection=connection, now=datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc))
    assert code == 0 and connection.closed
    receipt = json.loads(buffer.getvalue())
    assert receipt["cost_bps"] == 6.0 and receipt["read_only"] is True
    assert receipt["rows_read"] == {"FAMILY": 1, "V9": 0}
    assert receipt["sessions_requested"] == [SESSION]
    assert len(receipt["receipt_sha256"]) == 64


def test_main_refuses_rth_and_frozen_resamples():
    connection = _FakeConnection()
    with pytest.raises(RuntimeError):
        sc.main(["--cost-bps", "6", "--sessions", SESSION], connection=connection,
                now=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc))  # 10:00 ET Tuesday
    with pytest.raises(SystemExit):
        sc.main(["--cost-bps", "6", "--sessions", SESSION, "--resamples", "10"],
                connection=connection, now=datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc))
