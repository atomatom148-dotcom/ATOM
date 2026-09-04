from __future__ import annotations

import ast
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random

import pytest

from quant import gamma_challenger_study as study


BASE = datetime(2026, 9, 1, 13, 30, tzinfo=timezone.utc)


def rows(*, heteroskedastic: bool, sessions: int = 20, per_session: int = 25,
         null_at: int | None = None):
    rng = random.Random(91)
    result = []
    day = BASE
    for session in range(sessions):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        for index in range(per_session):
            magnitude = (.2 + 3.8 * ((index % per_session) + .5) / per_session
                         + session * 1e-6
                         if heteroskedastic else 1.0)
            sigma = (.35 + magnitude if heteroskedastic else 1.0)
            error = rng.gauss(0, sigma)
            expected = 1.0
            actual = expected + error
            q0 = 1.0
            if null_at == len(result):
                q0 = None
            result.append(study.StudyRow(
                f"r{len(result):04}", "cohort", "30S",
                (day + timedelta(seconds=index * 31)).timestamp(), expected, q0,
                magnitude, actual, True, True))
        day += timedelta(days=1)
    return result


def prepared(values):
    return study.select_windows(values, "30S")


def test_eta_zero_reproduces_baseline_scale_mathematics():
    values = prepared(rows(heteroskedastic=False, sessions=10))
    fit = study.fit_calibration(values.rows)
    assert fit is not None and fit.eta_hat == 0.0 and fit.gamma == 0.0
    assert fit.challenger_kappa_squared == pytest.approx(fit.baseline_kappa_squared)


def test_holdout_perturbation_cannot_move_calibration_fitted_parameters():
    calibration = prepared(rows(heteroskedastic=True, sessions=10))
    first = study.fit_calibration(calibration.rows)
    holdout = rows(heteroskedastic=False)
    study.score_holdout(prepared(holdout).rows, first, resamples=20)
    changed = [study.StudyRow(**{**asdict(row), "actual_return_bps": 10_000.0})
               for row in holdout]
    study.score_holdout(prepared(changed).rows, first, resamples=20)
    assert study.fit_calibration(calibration.rows) == first


def test_nulls_are_excluded_and_counted_never_imputed():
    selected = prepared(rows(heteroskedastic=True, sessions=2, null_at=3))
    assert selected.n_null_excluded == 1
    assert len(selected.rows) == selected.n_input - 1
    assert all(row.predictive_variance_bps2 is not None for row in selected.rows)


def test_pure_noise_magnitude_is_valid_fail_path():
    calibration = prepared(rows(heteroskedastic=False, sessions=10))
    holdout = prepared(rows(heteroskedastic=False))
    result = study.evaluate_horizon(calibration, holdout, "30S", resamples=100)
    assert result["convergence_status"] == "CONVERGED"
    assert result["eta_hat"] == 0.0
    assert result["final_verdict"] == "FAIL"


def test_constructed_heteroskedastic_evidence_exercises_positive_path():
    calibration = prepared(rows(heteroskedastic=True, sessions=10))
    holdout = prepared(rows(heteroskedastic=True))
    result = study.evaluate_horizon(calibration, holdout, "30S", resamples=500)
    assert result["eta_hat"] > 0.0 and result["delta_h"] > 0.0
    assert result["interval_999"][0] > 0.0
    assert result["quartile_verdict"] == "PASS"
    assert result["final_verdict"] == "PASS"


def test_quartile_gate_unavailable_below_effective_size_minimum():
    calibration = prepared(rows(heteroskedastic=True, sessions=10))
    tiny = prepared(rows(heteroskedastic=True, sessions=4, per_session=25))
    score = study.score_holdout(tiny.rows, study.fit_calibration(calibration.rows),
                                resamples=10)
    assert score["quartile_verdict"] == "UNAVAILABLE"
    assert "Q3_QUARTILE_EFFECTIVE_N_INSUFFICIENT" in score["quartile_reason_codes"]


def test_bootstrap_is_deterministic_under_seed_zero():
    calibration = prepared(rows(heteroskedastic=True, sessions=10))
    holdout = prepared(rows(heteroskedastic=True))
    fit = study.fit_calibration(calibration.rows)
    assert study.score_holdout(holdout.rows, fit, resamples=100) == study.score_holdout(
        holdout.rows, fit, resamples=100)


def test_receipt_canonical_json_and_sha256_are_stable():
    kwargs = dict(verified_main_sha="f47947a", horizon="30S", cohort_identity="c",
                  calibration_sessions=[date(2026, 8, 31)],
                  holdout_sessions=[date(2026, 9, 1)],
                  result={"final_verdict": "FAIL", "eta_hat": 0.0},
                  current_user=study.READONLY_ROLE)
    first = study.build_receipt(**kwargs)
    second = study.build_receipt(**kwargs)
    body = {key: value for key, value in first.items() if key != "sha256"}
    assert first == second
    assert first["sha256"] == hashlib.sha256(study.canonical_json(body).encode()).hexdigest()
    assert json.loads(study.canonical_json(first)) == first


def test_read_only_identity_no_fallback_and_no_forbidden_imports(monkeypatch):
    source = Path(study.__file__).read_text()
    tree = ast.parse(source)
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
               for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(name and ("broker" in name or "sim" in name or name == "quant.web")
                   for name in imports)
    lowered = study.STREAM_SQL.lower()
    assert not any(token in lowered for token in ("insert ", "update ", "delete ",
                                                   "truncate", "alter ", "drop ",
                                                   "grant ", "create ", "copy "))
    assert "connection.read_only = True" in source
    assert "holds evidence write privilege" in source
    assert study.READONLY_ROLE == "atom_e1_scorecard_reader"
    assert study.READONLY_URL_ENV == "ATOM_E1_SCORECARD_READONLY_DATABASE_URL"
    assert "DATABASE_URL\")" not in source.replace(study.READONLY_URL_ENV, "")
    monkeypatch.delenv(study.READONLY_URL_ENV, raising=False)
    with pytest.raises(SystemExit):
        study.configured_database_url()
    with pytest.raises(SystemExit):
        study.verify_reader_identity("postgres")


def test_minimum_evidence_is_insufficient_not_fail():
    small = prepared(rows(heteroskedastic=True, sessions=2))
    assert study.evaluate_horizon(small, small, "30S", resamples=10)[
        "final_verdict"] == "INSUFFICIENT"


def test_frozen_split_uses_all_pre_adoption_and_first_twenty_post_sessions():
    values = rows(heteroskedastic=True, sessions=25, per_session=1)
    all_sessions = sorted({study.session_of(row.cutoff_epoch) for row in values})
    pilot, holdout = study.frozen_session_split(values, all_sessions[3])
    assert pilot == tuple(all_sessions[:3])
    assert holdout == tuple(all_sessions[3:23])


def test_forbidden_e2_ratio_is_absent():
    source = Path(study.__file__).read_text()
    assert "abs(mu)" not in source and "abs(expected_return" not in source


def test_one_shot_runner_uses_readonly_connection_all_horizons_and_append_only_receipts(
        monkeypatch, tmp_path, capsys):
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    calls = []
    monkeypatch.setenv(study.READONLY_URL_ENV, "postgresql://readonly")
    monkeypatch.setattr(study, "open_readonly_connection",
                        lambda url: connection if url == "postgresql://readonly" else None)

    def fake_read_rows(received, *, horizon, lo, hi):
        assert received is connection
        calls.append(horizon)
        return ()

    monkeypatch.setattr(study, "read_rows", fake_read_rows)
    verdicts = study.run_once(
        verified_main_sha="abc123", receipts_dir=tmp_path,
        now=datetime(2026, 9, 5, tzinfo=timezone.utc))

    assert calls == list(study.HORIZONS)
    assert verdicts == {horizon: "INSUFFICIENT" for horizon in study.HORIZONS}
    assert connection.closed
    receipts = sorted(tmp_path.glob("g-1-*.json"))
    assert len(receipts) == 12
    assert len([path for path in receipts if "pilot" in path.name]) == 6
    assert len([path for path in receipts if "confirmatory" in path.name]) == 6
    with pytest.raises(SystemExit, match="refused to overwrite"):
        study.run_once(verified_main_sha="abc123", receipts_dir=tmp_path,
                       now=datetime(2026, 9, 5, tzinfo=timezone.utc))

    monkeypatch.setattr(study, "run_once", lambda **kwargs: verdicts)
    assert study.main(["--verified-main-sha", "abc123"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"{horizon}: INSUFFICIENT" for horizon in study.HORIZONS]
