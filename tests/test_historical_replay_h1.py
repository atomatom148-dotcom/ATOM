from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from quant.historical_replay import HistoricalSipQuote
from quant.historical_replay_h1 import main, run_h1_session
from quant.v9_v1_contract import HORIZONS


EASTERN = ZoneInfo("America/New_York")
NANOSECONDS = 1_000_000_000


def _session():
    opened = datetime(2026, 1, 5, 9, 30, tzinfo=EASTERN)
    return opened, opened.replace(hour=16, minute=0)


def _quote(
    symbol: str, at: datetime, *, fraction: int = 0, bid: float = 100.0,
) -> HistoricalSipQuote:
    exact = int(at.timestamp()) * NANOSECONDS + fraction
    return HistoricalSipQuote(
        symbol, exact, bid, bid + 0.2, 10.0, 8.0,
    )


def _canonical(*rows: HistoricalSipQuote) -> tuple[HistoricalSipQuote, ...]:
    order = {"COIN": 0, "QQQ": 1}
    return tuple(sorted(rows, key=lambda row: (
        row.provider_event_ns, order[row.symbol],
    )))


class _Reader:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.calls = []

    def read_session(self, *, session_open, session_close):
        self.calls.append((session_open, session_close))
        return self.rows


def _run(rows, *, run_id="h1-test", enforce_preflight=False,
         preflight_only=False):
    import quant.historical_replay_h1 as module

    opened, closed = _session()
    reader = _Reader(rows)
    context = (
        patch.object(module, "_coverage_reason_codes", return_value=())
        if not enforce_preflight else nullcontext()
    )
    with context:
        report = run_h1_session(
            reader=reader, session_open=opened, session_close=closed,
            replay_run_id=run_id, preflight_only=preflight_only,
        )
    assert reader.calls == [(opened, closed)]
    return report


def _dense_then_refresh():
    opened, _closed = _session()
    rows = []
    for offset in range(71):
        at = opened + timedelta(seconds=offset)
        rows.extend((
            _quote("COIN", at, bid=100.0 + offset / 100),
            _quote("QQQ", at, bid=500.0 + offset / 200),
        ))
    at = opened + timedelta(hours=1)
    rows.extend((
        _quote("COIN", at, bid=101.0),
        _quote("QQQ", at, bid=501.0),
    ))
    return _canonical(*rows)


def _complete_five_second_rows():
    opened, _closed = _session()
    rows = []
    for offset in range(0, 23_400, 5):
        at = opened + timedelta(seconds=offset)
        rows.extend((
            _quote("COIN", at, bid=100.0 + offset / 1_000_000),
            _quote("QQQ", at, bid=500.0 + offset / 1_000_000),
        ))
    return _canonical(*rows)


def _coverage(report, quant_id, horizon):
    return next(row for row in report.family_coverage
                if (row.quant_id, row.horizon) == (quant_id, horizon))


def _resolution(report, horizon):
    return next(row for row in report.resolution_coverage
                if row.horizon == horizon)


def test_h1_runs_reader_clock_families_v2_v1_v3_and_outcomes_end_to_end():
    report = _run(_dense_then_refresh())

    assert report.evidence_origin == "HISTORICAL_REPLAY"
    assert report.historical_session == "2026-01-05"
    assert report.quote_counts == (("COIN", 72), ("QQQ", 72))
    assert report.frame_count == 72
    assert report.persistence_writes == 0
    assert report.q10_status == "DATA_UNAVAILABLE"
    assert len(report.v3_coverage) == 6
    assert all(row.total == report.frame_count for row in report.v3_coverage)
    assert tuple(row.horizon for row in report.resolution_coverage) == HORIZONS
    assert all(row.forecasts == report.frame_count
               for row in report.resolution_coverage)
    assert {row.horizon for row in report.resolution_samples} == set(HORIZONS)
    assert len(report.v2_refreshes) == 2
    assert report.v2_refreshes[0].resolved_target_count == 0
    assert report.v2_refreshes[0].published is False
    assert report.v2_refreshes[1].resolved_target_count > 0
    assert report.v2_refreshes[1].published is True
    assert report.v2_refreshes[1].resolved_target_count > report.frame_count
    assert report.quote_coverage[0].symbol == "COIN"
    assert report.quote_coverage[0].max_gap_ns is not None
    assert report.qqq_attached_frame_count == report.frame_count
    assert report.qqq_fresh_frame_count == report.frame_count
    assert report.dataset_digest
    assert report.configuration_digest
    assert report.session_digest
    assert report.timings.persistence_seconds == 0.0
    assert report.timings.total_seconds >= 0.0
    assert report.execution_stage == "REPLAY_COMPLETE"
    assert report.data_status == "DATA_INCOMPLETE"
    assert "30S_ENDPOINT_GAP" in report.data_reason_codes
    assert report.replay_factor is None
    assert report.projected_seconds == ()


def test_h1_mathematical_digests_are_repeatable_and_exclude_timings_and_run_id():
    rows = _dense_then_refresh()
    first = _run(rows, run_id="run-a")
    second = _run(rows, run_id="run-b")

    assert first.dataset_digest == second.dataset_digest
    assert first.configuration_digest == second.configuration_digest
    assert first.session_digest == second.session_digest
    assert first.family_coverage == second.family_coverage
    assert first.v3_coverage == second.v3_coverage
    assert first.resolution_coverage == second.resolution_coverage
    assert first.v2_refreshes == second.v2_refreshes
    assert first.replay_run_id != second.replay_run_id


def test_h1_rejects_certification_when_usable_quotes_have_over_five_second_gap():
    opened, closed = _session()
    rows = [_quote("COIN", opened), _quote("QQQ", opened, bid=500.0)]
    rows.extend(
        _quote("COIN", opened + timedelta(seconds=offset), bid=100.1)
        for offset in range(6, 23_400, 5)
    )
    rows.extend(
        _quote("QQQ", opened + timedelta(seconds=offset), bid=500.1)
        for offset in range(5, 23_400, 5)
    )

    report = _run(_canonical(*rows), enforce_preflight=True)

    assert report.data_status == "DATA_INCOMPLETE"
    assert report.execution_stage == "PREFLIGHT_REJECTED"
    assert "COIN_INTERQUOTE_GAP" in report.data_reason_codes
    coin = report.quote_coverage[0]
    assert coin.max_gap_ns == 6 * NANOSECONDS
    assert coin.max_gap_start_ns == int(opened.timestamp()) * NANOSECONDS
    assert coin.max_gap_end_ns == (
        int(opened.timestamp()) + 6
    ) * NANOSECONDS
    assert coin.over_limit_gap_count == 1
    assert coin.p99_gap_ns == 5 * NANOSECONDS
    assert coin.first_quote_delay_ns == 0
    assert coin.last_quote_lead_ns == 4 * NANOSECONDS
    assert coin.count == 4_680
    assert report.quote_counts == (("COIN", 4_680), ("QQQ", 4_680))
    assert report.frame_count == 0
    assert report.timings.quant_seconds == 0.0
    assert report.timings.alignment_seconds == 0.0
    assert report.timings.resolution_seconds == 0.0
    assert report.timings.v2_seconds == 0.0
    assert report.timings.v1_seconds == 0.0
    assert report.timings.v3_seconds == 0.0
    assert report.timings.persistence_seconds == 0.0
    assert all(row.total == 0 for row in report.family_coverage)
    assert all(row.total == 0 for row in report.v3_coverage)
    assert all(row.forecasts == 0 for row in report.resolution_coverage)
    assert report.resolution_samples == ()
    assert report.v2_refreshes == ()
    assert report.qqq_attached_frame_count == 0
    assert report.qqq_fresh_frame_count == 0
    assert report.replay_factor is None
    assert report.projected_seconds == ()


def test_h1_preflight_gap_ties_keep_first_interval_and_count_all_violations():
    opened, _closed = _session()
    rows = _canonical(
        _quote("COIN", opened),
        _quote("QQQ", opened, bid=500.0),
        _quote("QQQ", opened + timedelta(seconds=1), bid=500.1),
        _quote("COIN", opened + timedelta(seconds=6), bid=100.1),
        _quote("COIN", opened + timedelta(seconds=12), bid=100.2),
    )

    report = _run(rows, enforce_preflight=True)
    coin = report.quote_coverage[0]

    assert coin.max_gap_ns == 6 * NANOSECONDS
    assert coin.max_gap_start_ns == int(opened.timestamp()) * NANOSECONDS
    assert coin.max_gap_end_ns == (
        int(opened.timestamp()) + 6
    ) * NANOSECONDS
    assert coin.over_limit_gap_count == 2


def test_h1_preflight_rejection_never_enters_clock_or_quant(monkeypatch):
    import quant.historical_replay_h1 as module

    opened, closed = _session()
    rows = _canonical(
        _quote("COIN", opened),
        _quote("QQQ", opened, bid=500.0),
        _quote("COIN", opened + timedelta(seconds=6), bid=100.1),
        _quote("QQQ", opened + timedelta(seconds=1), bid=500.1),
    )

    def unexpected(*_args, **_kwargs):
        raise AssertionError("preflight rejection entered replay")

    monkeypatch.setattr(module, "OneSessionReplayClock", unexpected)
    monkeypatch.setattr(module, "_calculate_provider_families", unexpected)
    monkeypatch.setattr(module, "build_replay_v2_as_of", unexpected)
    monkeypatch.setattr(module, "_build_v1", unexpected)
    monkeypatch.setattr(module, "synthesize_v3", unexpected)
    reader = _Reader(rows)
    report = run_h1_session(
        reader=reader, session_open=opened, session_close=closed,
        replay_run_id="preflight-reject",
    )

    assert reader.calls == [(opened, closed)]
    assert report.execution_stage == "PREFLIGHT_REJECTED"
    assert report.data_status == "DATA_INCOMPLETE"


def test_h1_preflight_only_accepts_complete_coverage_without_running_quant(
    monkeypatch,
):
    import quant.historical_replay_h1 as module

    def unexpected(*_args, **_kwargs):
        raise AssertionError("preflight-only entered replay")

    monkeypatch.setattr(module, "OneSessionReplayClock", unexpected)
    monkeypatch.setattr(module, "_calculate_provider_families", unexpected)
    report = _run(
        _complete_five_second_rows(),
        enforce_preflight=True, preflight_only=True,
    )

    assert report.execution_stage == "PREFLIGHT_ONLY"
    assert report.data_status == "DATA_COMPLETE"
    assert report.data_reason_codes == ()
    assert all(row.over_limit_gap_count == 0 for row in report.quote_coverage)
    assert report.frame_count == 0


def test_h1_complete_coverage_dispatches_into_replay(monkeypatch):
    import quant.historical_replay_h1 as module

    def entered(*_args, **_kwargs):
        raise RuntimeError("CERTIFIED_COVERAGE_ENTERED_REPLAY")

    monkeypatch.setattr(module, "OneSessionReplayClock", entered)
    opened, closed = _session()
    with pytest.raises(RuntimeError, match="CERTIFIED_COVERAGE_ENTERED_REPLAY"):
        run_h1_session(
            reader=_Reader(_complete_five_second_rows()),
            session_open=opened, session_close=closed,
            replay_run_id="certified-dispatch",
        )


def test_h1_rejected_preflight_digest_excludes_run_id_and_timings():
    opened, closed = _session()
    rows = _canonical(
        _quote("COIN", opened),
        _quote("QQQ", opened, bid=500.0),
        _quote("QQQ", opened + timedelta(seconds=1), bid=500.1),
        _quote("COIN", opened + timedelta(seconds=6), bid=100.1),
    )
    first_ticks = iter((0.0, 1.0, 2.0, 5.0))
    second_ticks = iter((100.0, 110.0, 130.0, 160.0))
    first = run_h1_session(
        reader=_Reader(rows), session_open=opened, session_close=closed,
        replay_run_id="preflight-a", monotonic_clock=lambda: next(first_ticks),
    )
    second = run_h1_session(
        reader=_Reader(rows), session_open=opened, session_close=closed,
        replay_run_id="preflight-b", monotonic_clock=lambda: next(second_ticks),
    )

    assert first.execution_stage == second.execution_stage == "PREFLIGHT_REJECTED"
    assert first.dataset_digest == second.dataset_digest
    assert first.configuration_digest == second.configuration_digest
    assert first.session_digest == second.session_digest
    assert first.replay_run_id != second.replay_run_id
    assert first.timings != second.timings


def test_h1_invalid_preflight_only_remains_rejected():
    opened, closed = _session()
    report = run_h1_session(
        reader=_Reader((_quote("COIN", opened),)),
        session_open=opened, session_close=closed,
        replay_run_id="invalid-preflight-only", preflight_only=True,
    )

    assert report.execution_stage == "PREFLIGHT_REJECTED"
    assert report.data_status == "DATA_INCOMPLETE"


@pytest.mark.parametrize("preflight_only", [False, True])
@pytest.mark.parametrize(("case", "message"), (
    ("out_of_order", "canonical chronological order"),
    ("duplicate", "strictly increasing"),
    ("outside_session", "outside the replay session"),
))
def test_h1_preflight_preserves_clock_input_validation(
    case, message, preflight_only,
):
    opened, closed = _session()
    coin = _quote("COIN", opened)
    qqq = _quote("QQQ", opened, bid=500.0)
    rows = {
        "out_of_order": (qqq, coin),
        "duplicate": (coin, _quote("COIN", opened, bid=100.1)),
        "outside_session": (
            coin, qqq, _quote("COIN", closed, bid=100.1),
        ),
    }[case]

    with pytest.raises(ValueError, match=message):
        run_h1_session(
            reader=_Reader(rows), session_open=opened, session_close=closed,
            replay_run_id=f"invalid-{case}", preflight_only=preflight_only,
        )


def test_target_uses_first_accepted_quote_at_or_after_provider_endpoint():
    opened, _closed = _session()
    rows = _canonical(
        _quote("COIN", opened, bid=100.0),
        _quote("QQQ", opened, bid=500.0),
        _quote("COIN", opened + timedelta(seconds=29), bid=100.5),
        _quote("COIN", opened + timedelta(seconds=30),
               fraction=100, bid=101.0),
        _quote("COIN", opened + timedelta(seconds=30),
               fraction=200, bid=102.0),
        _quote("QQQ", opened + timedelta(seconds=30),
               fraction=50, bid=501.0),
    )

    report = _run(rows)
    sample = next(row for row in report.resolution_samples
                  if row.horizon == "30S")
    maturity = int((opened + timedelta(seconds=30)).timestamp()) * NANOSECONDS

    assert sample.maturity_ns == maturity
    assert sample.previous_observation_ns < maturity
    assert sample.endpoint_observation_ns == maturity + 200
    assert sample.endpoint_delay_ns == 200
    assert sample.resolution_cutoff_ns == maturity + 200
    assert sample.resolution_cutoff_ns >= sample.endpoint_observation_ns


def test_forecast_target_origin_is_selected_provider_time_not_logical_tick():
    opened, _closed = _session()
    rows = _canonical(
        _quote("QQQ", opened, fraction=100_000_000, bid=500.0),
        _quote("COIN", opened, fraction=200_000_000, bid=100.0),
        _quote("COIN", opened + timedelta(seconds=30),
               fraction=300_000_000, bid=101.0),
    )

    report = _run(rows)
    sample = next(row for row in report.resolution_samples
                  if row.horizon == "30S")
    cutoff_ns = int(opened.timestamp()) * NANOSECONDS + 200_000_000

    assert sample.cycle_id.endswith(str(cutoff_ns))
    assert sample.maturity_ns == cutoff_ns + 30 * NANOSECONDS
    assert sample.endpoint_observation_ns == (
        int(opened.timestamp()) * NANOSECONDS + 30 * NANOSECONDS +
        300_000_000
    )
    assert _resolution(report, "30S").resolved == 1


def test_target_maturing_at_close_remains_unresolved():
    opened, closed = _session()
    late = closed - timedelta(seconds=30)
    rows = _canonical(
        _quote("COIN", opened, bid=100.0),
        _quote("QQQ", opened, bid=500.0),
        _quote("COIN", late, bid=101.0),
        _quote("QQQ", late, bid=501.0),
    )

    report = _run(rows)
    coverage = _resolution(report, "30S")

    assert coverage.forecasts == 2
    assert coverage.session_eligible == 1
    assert coverage.session_unavailable == 1
    assert coverage.resolved == 1
    assert coverage.unresolved == 1
    assert all(sample.maturity_ns < report.session_close_ns
               for sample in report.resolution_samples)


def test_q10_is_family_local_missing_and_does_not_suppress_exact_families():
    opened, _closed = _session()
    rows = []
    for offset in range(40):
        at = opened + timedelta(seconds=offset)
        rows.extend((
            _quote("COIN", at, bid=100.0 + offset / 100),
            _quote("QQQ", at, bid=500.0 + offset / 200),
        ))

    report = _run(_canonical(*rows))

    q10 = _coverage(report, "q10_options_vol", "30S")
    q1 = _coverage(report, "q1_momentum", "30S")
    q5 = _coverage(report, "q5_microstructure", "30S")
    assert q10.total == report.frame_count
    assert q10.available == 0
    assert q10.missing == report.frame_count
    assert q1.available > 0
    assert q5.available > 0


def test_hourly_v2_refresh_is_open_anchored_and_contains_resolved_only():
    opened, _closed = _session()
    rows = _canonical(
        _quote("COIN", opened, bid=100.0),
        _quote("QQQ", opened, bid=500.0),
        _quote("COIN", opened + timedelta(seconds=30), bid=101.0),
        _quote("QQQ", opened + timedelta(seconds=30), bid=501.0),
        _quote("COIN", opened + timedelta(hours=1), bid=102.0),
        _quote("QQQ", opened + timedelta(hours=1), bid=502.0),
    )

    report = _run(rows)
    first, second = report.v2_refreshes
    open_ns = int(opened.timestamp()) * NANOSECONDS

    assert first.anchor_ns == open_ns
    assert first.resolved_target_count == 0
    assert second.anchor_ns == open_ns + 3_600 * NANOSECONDS
    assert second.capture_cutoff_ns == second.anchor_ns
    assert second.resolved_target_count > 0
    assert second.max_resolved_epoch is not None
    assert second.max_resolved_epoch <= second.state_as_of_ns / NANOSECONDS
    assert second.state_as_of_ns == second.capture_cutoff_ns


def test_refreshed_v2_is_not_captured_before_provider_cutoff_reaches_state():
    opened, _closed = _session()
    rows = []
    for offset in range(71):
        at = opened + timedelta(seconds=offset)
        rows.extend((
            _quote("COIN", at, bid=100.0 + offset / 100),
            _quote("QQQ", at, bid=500.0 + offset / 200),
        ))
    for offset in (3_600, 3_601):
        at = opened + timedelta(seconds=offset)
        rows.extend((
            _quote("COIN", at, fraction=200_000_000,
                   bid=101.0 + (offset - 3_600) / 100),
            _quote("QQQ", at, fraction=100_000_000,
                   bid=501.0 + (offset - 3_600) / 100),
        ))

    report = _run(_canonical(*rows))
    second_refresh = report.v2_refreshes[1]
    thirty_seconds = next(row for row in report.v3_coverage
                          if row.horizon == "30S")

    assert second_refresh.published is True
    assert second_refresh.state_as_of_ns > (
        int((opened + timedelta(hours=1)).timestamp()) * NANOSECONDS +
        200_000_000
    )
    assert thirty_seconds.provisional == 1
    assert thirty_seconds.unavailable == report.frame_count - 1


def test_sparse_frames_catch_up_every_hourly_refresh_anchor():
    opened, _closed = _session()
    rows = _canonical(
        _quote("COIN", opened, bid=100.0),
        _quote("QQQ", opened, bid=500.0),
        _quote("COIN", opened + timedelta(hours=2), bid=102.0),
        _quote("QQQ", opened + timedelta(hours=2), bid=502.0),
    )

    report = _run(rows)
    open_ns = int(opened.timestamp()) * NANOSECONDS

    assert tuple(row.anchor_ns for row in report.v2_refreshes) == (
        open_ns, open_ns + 3_600 * NANOSECONDS,
        open_ns + 7_200 * NANOSECONDS,
    )
    assert report.v2_refreshes[1].capture_cutoff_ns == open_ns + 7_200 * NANOSECONDS
    assert report.v2_refreshes[2].capture_cutoff_ns == open_ns + 7_200 * NANOSECONDS


def test_fractional_final_second_is_resolution_only_close_drain():
    opened, closed = _session()
    late = closed - timedelta(seconds=32)
    final_second = closed - timedelta(seconds=1)
    rows = _canonical(
        _quote("COIN", opened, bid=100.0),
        _quote("QQQ", opened, bid=500.0),
        _quote("COIN", late, bid=101.0),
        _quote("QQQ", late, bid=501.0),
        _quote("COIN", final_second, fraction=500_000_000, bid=102.0),
    )

    report = _run(rows)
    coverage = _resolution(report, "30S")

    assert report.frame_count == 2
    assert coverage.forecasts == 2
    assert coverage.resolved == 2
    assert coverage.unresolved == 0
    assert report.quote_coverage[0].last_quote_lead_ns == 500_000_000


def test_cli_accepts_preflight_only_and_emits_json(monkeypatch, capsys):
    import quant.historical_replay_h1 as module

    monkeypatch.setattr(
        module.AlpacaHistoricalSipReader, "from_environment",
        classmethod(lambda _cls: object()),
    )
    observed = {}

    def run(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            execution_stage="PREFLIGHT_ONLY", data_status="DATA_COMPLETE",
            to_dict=lambda: {"status": "PASS"},
        )

    monkeypatch.setattr(module, "run_h1_session", run)

    assert main((
        "2026-01-05", "--run-id", "cli-run", "--preflight-only",
    )) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "PASS"}
    assert observed["replay_run_id"] == "cli-run"
    assert observed["session_open"].astimezone(EASTERN).hour == 9
    assert observed["session_close"].astimezone(EASTERN).hour == 16
    assert observed["preflight_only"] is True


def test_cli_fails_closed_when_session_data_is_incomplete(monkeypatch, capsys):
    import quant.historical_replay_h1 as module

    opened, _closed = _session()
    reader = _Reader(_canonical(
        _quote("COIN", opened),
        _quote("QQQ", opened, bid=500.0),
        _quote("QQQ", opened + timedelta(seconds=1), bid=500.1),
        _quote("COIN", opened + timedelta(seconds=6), bid=100.1),
    ))
    monkeypatch.setattr(
        module.AlpacaHistoricalSipReader, "from_environment",
        classmethod(lambda _cls: reader),
    )

    assert main(("2026-01-05",)) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["data_status"] == "DATA_INCOMPLETE"
    assert payload["execution_stage"] == "PREFLIGHT_REJECTED"
    assert "COIN_INTERQUOTE_GAP" in payload["data_reason_codes"]
    coin = next(row for row in payload["quote_coverage"]
                if row["symbol"] == "COIN")
    assert coin["max_gap_ns"] == 6 * NANOSECONDS
    assert coin["max_gap_start_ns"] == int(opened.timestamp()) * NANOSECONDS
    assert coin["max_gap_end_ns"] == (
        int(opened.timestamp()) + 6
    ) * NANOSECONDS
    assert coin["over_limit_gap_count"] == 1
    assert reader.calls == [_session()]


@pytest.mark.parametrize(("stage", "status", "expected"), (
    ("PREFLIGHT_ONLY", "DATA_COMPLETE", 0),
    ("REPLAY_COMPLETE", "CERTIFIED", 0),
    ("PREFLIGHT_ONLY", "CERTIFIED", 2),
    ("REPLAY_COMPLETE", "DATA_COMPLETE", 2),
    ("PREFLIGHT_REJECTED", "DATA_INCOMPLETE", 2),
))
def test_cli_accepts_only_valid_stage_status_pairs(
    monkeypatch, capsys, stage, status, expected,
):
    import quant.historical_replay_h1 as module

    monkeypatch.setattr(
        module.AlpacaHistoricalSipReader, "from_environment",
        classmethod(lambda _cls: object()),
    )
    monkeypatch.setattr(
        module, "run_h1_session",
        lambda **_kwargs: SimpleNamespace(
            execution_stage=stage, data_status=status,
            to_dict=lambda: {
                "execution_stage": stage, "data_status": status,
            },
        ),
    )

    assert main(("2026-01-05",)) == expected
    assert json.loads(capsys.readouterr().out) == {
        "execution_stage": stage, "data_status": status,
    }


@pytest.mark.parametrize("bad", ["", "x" * 129])
def test_h1_rejects_invalid_run_identity(bad):
    opened, closed = _session()
    with pytest.raises(ValueError, match="replay_run_id"):
        run_h1_session(
            reader=_Reader(()), session_open=opened, session_close=closed,
            replay_run_id=bad,
        )
