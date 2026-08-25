from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import math
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from quant.historical_replay import (
    ALLOWED_FORMULA_VERSIONS, DATA_SCHEMA_VERSION, REPLAY_METHOD_VERSION,
    SOURCE_SPEC_ROUND_LOTS, SOURCE_SPEC_SHARES, AlpacaHistoricalSipReader,
    HistoricalSipQuote, OneSessionReplayClock, ReplayFrame, TARGET_SPEC_ID,
    build_replay_v2_as_of, calculate_replay_families,
)
from quant.history import MidpointHistory, MidpointObservation
from quant.q1_momentum import FORMULA_VERSION as Q1_VERSION
from quant.q10_options_vol import FORMULA_VERSION as Q10_VERSION
from quant.quote_history import QuoteHistory
from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS, RawFamilyObservation, RawTarget, TargetIdentity,
)
from quant.v9_v2d_evidence_state import v2d_state_hash


EASTERN = ZoneInfo("America/New_York")
class _Response(BytesIO):
    def __init__(self, payload: object):
        super().__init__(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _Opener:
    def __init__(self, *payloads: object):
        self._payloads = iter(payloads)
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        return _Response(next(self._payloads))


def _payload(timestamp: str, *, bid: float = 100.0, ask: float | None = None,
             bid_size: float = 10.0, ask_size: float = 8.0) -> dict[str, object]:
    return {"t": timestamp, "bp": bid, "ap": bid + 0.2 if ask is None else ask,
            "bs": bid_size, "as": ask_size}


def _session(day: int = 5, *, month: int = 1):
    opened = datetime(2026, month, day, 9, 30, tzinfo=EASTERN)
    return opened, opened.replace(hour=16, minute=0)


def _ns(value: datetime, fraction: int = 0) -> int:
    return int(value.astimezone(timezone.utc).timestamp()) * 1_000_000_000 + fraction


def _quote(symbol: str, at: datetime, *, fraction: int = 0,
           bid: float = 100.0) -> HistoricalSipQuote:
    return HistoricalSipQuote(
        symbol, _ns(at, fraction), bid, bid + 0.2, 10.0, 8.0,
    )


def test_reader_uses_one_sip_request_per_page_and_preserves_provider_nanos():
    opened, closed = _session()
    first = {
        "quotes": {
            "COIN": [_payload("2026-01-05T14:30:00.000000001Z")],
        },
        "next_page_token": "page-2",
    }
    second = {
        "quotes": {
            "COIN": [_payload("2026-01-05T14:30:01.123456789Z", bid=101.0)],
            "QQQ": [
                _payload("2026-01-05T14:30:01.123456790Z", bid=501.0),
                _payload("2026-01-05T21:00:00.000000000Z", bid=502.0),
            ],
        },
        "next_page_token": None,
    }
    opener = _Opener(first, second)

    rows = AlpacaHistoricalSipReader(
        "key", "secret", opener=opener,
    ).read_session(session_open=opened, session_close=closed)

    assert len(opener.calls) == 2
    first_query = parse_qs(urlparse(opener.calls[0][0].full_url).query)
    second_query = parse_qs(urlparse(opener.calls[1][0].full_url).query)
    assert first_query["symbols"] == ["COIN,QQQ"]
    assert first_query["feed"] == ["sip"]
    assert first_query["asof"] == ["-"]
    assert first_query["currency"] == ["USD"]
    assert first_query["sort"] == ["asc"]
    assert first_query["start"] == ["2026-01-05T14:30:00.000000Z"]
    assert first_query["end"] == ["2026-01-05T21:00:00.000000Z"]
    assert second_query["page_token"] == ["page-2"]
    assert all(timeout == 30 for _, timeout in opener.calls)
    assert [row.provider_event_ns for row in rows] == sorted(
        row.provider_event_ns for row in rows
    )
    assert rows[0].provider_event_ns == 1_767_623_400_000_000_001
    assert rows[-1].provider_event_ns == 1_767_623_401_123_456_790
    assert all(row.source_spec_version == SOURCE_SPEC_SHARES for row in rows)
    assert all(row.data_schema_version == DATA_SCHEMA_VERSION for row in rows)


@pytest.mark.parametrize("change", [
    lambda row: {key: value for key, value in row.items() if key != "bs"},
    lambda row: {**row, "as": -1.0},
])
def test_reader_rejects_incomplete_or_invalid_sizes(change):
    opened, closed = _session()
    valid = _payload("2026-01-05T14:30:00Z")
    opener = _Opener({
        "quotes": {"COIN": [change(valid)], "QQQ": [valid]},
        "next_page_token": None,
    })
    with pytest.raises(ValueError):
        AlpacaHistoricalSipReader(
            "key", "secret", opener=opener,
        ).read_session(session_open=opened, session_close=closed)


@pytest.mark.parametrize("invalid", [
    {"bp": 0.0, "ap": 100.0},
    {"bp": 100.0, "ap": 0.0},
    {"bp": -1.0, "ap": 100.0},
    {"bp": 100.0, "ap": -1.0},
    {"bp": 101.0, "ap": 100.0},
])
def test_reader_skips_unusable_provider_top_of_book(invalid):
    opened, closed = _session()
    first = _payload("2026-01-05T14:30:00Z")
    bad = {**_payload("2026-01-05T14:30:00.500000000Z"), **invalid}
    good = _payload("2026-01-05T14:30:01Z")
    opener = _Opener({
        "quotes": {
            "COIN": [first, bad, good],
            "QQQ": [_payload("2026-01-05T14:30:01Z", bid=500.0)],
        },
        "next_page_token": None,
    })

    rows = AlpacaHistoricalSipReader(
        "key", "secret", opener=opener,
    ).read_session(session_open=opened, session_close=closed)

    assert [row.provider_event_ns for row in rows] == [
        _ns(opened),
        _ns(opened + timedelta(seconds=1)),
        _ns(opened + timedelta(seconds=1)),
    ]


def test_reader_reports_data_unavailable_when_all_coin_prices_are_unusable():
    opened, closed = _session()
    opener = _Opener({
        "quotes": {
            "COIN": [_payload("2026-01-05T14:30:00Z", bid=0.0, ask=0.0)],
            "QQQ": [_payload("2026-01-05T14:30:00Z", bid=500.0)],
        },
        "next_page_token": None,
    })

    with pytest.raises(RuntimeError, match="REPLAY_DATA_UNAVAILABLE"):
        AlpacaHistoricalSipReader(
            "key", "secret", opener=opener,
        ).read_session(session_open=opened, session_close=closed)


def test_reader_rejects_conflicting_identity_and_missing_coin():
    opened, closed = _session()
    timestamp = "2026-01-05T14:30:00Z"
    conflict = _Opener({
        "quotes": {
            "COIN": [_payload(timestamp), _payload(timestamp, bid=101.0)],
            "QQQ": [_payload(timestamp, bid=500.0)],
        },
        "next_page_token": None,
    })
    with pytest.raises(ValueError, match="conflicting"):
        AlpacaHistoricalSipReader(
            "key", "secret", opener=conflict,
        ).read_session(session_open=opened, session_close=closed)

    missing = _Opener({"quotes": {"QQQ": [_payload(timestamp, bid=500.0)]},
                       "next_page_token": None})
    with pytest.raises(RuntimeError, match="REPLAY_DATA_UNAVAILABLE"):
        AlpacaHistoricalSipReader(
            "key", "secret", opener=missing,
        ).read_session(session_open=opened, session_close=closed)


def test_reader_allows_missing_qqq_for_family_local_degradation():
    opened, closed = _session()
    opener = _Opener({
        "quotes": {"COIN": [_payload("2026-01-05T14:30:00Z")]},
        "next_page_token": None,
    })

    rows = AlpacaHistoricalSipReader(
        "key", "secret", opener=opener,
    ).read_session(session_open=opened, session_close=closed)
    frame, = OneSessionReplayClock(
        rows, session_open=opened, session_close=closed,
    ).frames()

    assert [row.symbol for row in rows] == ["COIN"]
    assert frame.qqq_source_as_of_ns is None
    assert frame.qqq_history.observations == ()


def test_reader_rejects_provider_rows_that_are_out_of_order():
    opened, closed = _session()
    opener = _Opener({
        "quotes": {
            "COIN": [
                _payload("2026-01-05T14:30:01Z"),
                _payload("2026-01-05T14:30:00Z"),
            ],
            "QQQ": [_payload("2026-01-05T14:30:00Z", bid=500.0)],
        },
        "next_page_token": None,
    })
    with pytest.raises(ValueError, match="out of order"):
        AlpacaHistoricalSipReader(
            "key", "secret", opener=opener,
        ).read_session(session_open=opened, session_close=closed)


def test_clock_is_causal_deterministic_and_does_not_fill_missing_seconds():
    opened, closed = _session()
    rows = (
        _quote("QQQ", opened, fraction=100_000_000, bid=500.0),
        _quote("COIN", opened, fraction=200_000_000),
        _quote("QQQ", opened, fraction=800_000_000, bid=501.0),
        _quote("COIN", opened, fraction=900_000_000, bid=101.0),
        _quote("QQQ", opened, fraction=950_000_000, bid=502.0),
        _quote("COIN", opened + timedelta(seconds=1),
               fraction=200_000_000, bid=102.0),
    )
    clock = OneSessionReplayClock(
        rows, session_open=opened, session_close=closed,
    )
    frames = tuple(clock.frames())
    repeated = tuple(OneSessionReplayClock(
        rows, session_open=opened, session_close=closed,
    ).frames())

    assert frames == repeated
    assert len(frames) == 2
    assert frames[0].clock_epoch == opened.timestamp() + 1
    assert frames[0].cutoff_epoch == frames[0].clock_epoch
    assert frames[0].cutoff_epoch > frames[0].coin_source_as_of_epoch
    assert frames[0].coin_source_as_of_ns == _ns(
        opened, fraction=900_000_000,
    )
    assert frames[0].coin_source_as_of_epoch <= frames[0].clock_epoch
    assert frames[0].qqq_source_as_of_epoch <= frames[0].clock_epoch
    assert len(frames[0].coin_history.observations) == 1
    assert len(frames[1].coin_history.observations) == 2
    assert frames[0].qqq_source_as_of_epoch < frames[0].cutoff_epoch
    assert frames[1].qqq_source_as_of_epoch < frames[1].cutoff_epoch
    assert len(frames[1].qqq_history.observations) == 2
    assert all(item.event_epoch <= frames[1].clock_epoch
               for item in frames[1].coin_history.observations)
    assert all(item.event_epoch <= frames[1].clock_epoch
               for item in frames[1].qqq_history.observations)


@pytest.mark.parametrize("month,day,utc_hour", [(1, 5, 14), (6, 1, 13)])
def test_clock_uses_timezone_aware_est_and_edt_boundaries(month, day, utc_hour):
    opened = datetime(2026, month, day, 9, 30, tzinfo=EASTERN)
    closed = opened.replace(hour=16, minute=0)
    rows = (_quote("COIN", opened), _quote("QQQ", opened, bid=500.0))
    rows = tuple(sorted(rows, key=lambda row: (row.provider_event_ns,
                                               ("COIN", "QQQ").index(row.symbol))))
    frame, = OneSessionReplayClock(
        rows, session_open=opened, session_close=closed,
    ).frames()
    assert datetime.fromtimestamp(frame.clock_epoch, timezone.utc).hour == utc_hour


def test_reader_and_clock_fail_closed_outside_one_complete_rth_session():
    opened, closed = _session()
    row = _quote("COIN", opened)
    with pytest.raises(ValueError, match="complete 09:30-16:00 ET"):
        OneSessionReplayClock(
            (row,), session_open=opened - timedelta(minutes=1),
            session_close=closed,
        )
    with pytest.raises(ValueError, match="complete 09:30-16:00 ET"):
        OneSessionReplayClock(
            (row,), session_open=opened,
            session_close=closed + timedelta(minutes=1),
        )


def test_clock_preserves_exact_source_ns_when_float_epochs_would_collide():
    opened, closed = _session()
    first = _quote("COIN", opened, fraction=999_999_900)
    second = _quote(
        "COIN", opened + timedelta(seconds=1), fraction=100,
        bid=101.0,
    )
    qqq = _quote("QQQ", opened, fraction=1, bid=500.0)
    rows = tuple(sorted((first, second, qqq), key=lambda row: (
        row.provider_event_ns, ("COIN", "QQQ").index(row.symbol),
    )))

    frames = tuple(OneSessionReplayClock(
        rows, session_open=opened, session_close=closed,
    ).frames())

    assert [frame.coin_source_as_of_ns for frame in frames] == [
        first.provider_event_ns, second.provider_event_ns,
    ]
    assert (frames[0].coin_history.observations[-1].event_epoch <
            frames[1].coin_history.observations[-1].event_epoch)
    assert all(frame.coin_source_as_of_ns <= frame.cutoff_ns for frame in frames)


@pytest.mark.parametrize("utc_hour", [13, 22])
def test_replay_frame_cannot_bypass_rth_with_direct_construction(utc_hour):
    exact = int(datetime(
        2026, 1, 5, utc_hour, 0, tzinfo=timezone.utc,
    ).timestamp() * 1_000_000_000)
    with pytest.raises(ValueError, match="current-session RTH"):
        ReplayFrame(
            exact, exact, exact, None,
            MidpointHistory(), MidpointHistory(), QuoteHistory(),
        )


def test_replay_frame_rejects_premarket_history_even_at_rth_cutoff():
    cutoff = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    exact = int(cutoff.timestamp() * 1_000_000_000)
    premarket = MidpointHistory((MidpointObservation(
        cutoff.timestamp() - 1, 100.0,
    ),))
    with pytest.raises(ValueError, match="current-session RTH"):
        ReplayFrame(
            exact, exact, exact, None,
            premarket, MidpointHistory(), QuoteHistory(),
        )


def test_replay_frame_binds_histories_to_exact_source_markers():
    opened, _closed = _session()
    open_ns = _ns(opened)
    qqq_history = MidpointHistory((MidpointObservation(
        opened.timestamp(), 500.0,
    ),))
    with pytest.raises(ValueError, match="source markers"):
        ReplayFrame(
            open_ns, open_ns, open_ns, None,
            MidpointHistory(), qqq_history, QuoteHistory(),
        )

    cutoff_ns = _ns(opened + timedelta(seconds=2))
    newer_coin = MidpointHistory((MidpointObservation(
        opened.timestamp() + 1, 100.0,
    ),))
    with pytest.raises(ValueError, match="source markers"):
        ReplayFrame(
            cutoff_ns, cutoff_ns, open_ns, None,
            newer_coin, MidpointHistory(), QuoteHistory(),
        )

    one_ulp = math.nextafter(opened.timestamp(), math.inf)
    two_ulps = math.nextafter(one_ulp, math.inf)
    ReplayFrame(
        cutoff_ns, cutoff_ns, open_ns, None,
        MidpointHistory((MidpointObservation(one_ulp, 100.0),)),
        MidpointHistory(), QuoteHistory(),
    )
    with pytest.raises(ValueError, match="source markers"):
        ReplayFrame(
            cutoff_ns, cutoff_ns, open_ns, None,
            MidpointHistory((MidpointObservation(two_ulps, 100.0),)),
            MidpointHistory(), QuoteHistory(),
        )


def test_reader_rejects_boolean_market_fields():
    opened, closed = _session()
    invalid = {**_payload("2026-01-05T14:30:00Z"), "bs": True}
    opener = _Opener({
        "quotes": {
            "COIN": [invalid],
            "QQQ": [_payload("2026-01-05T14:30:00Z", bid=500.0)],
        },
        "next_page_token": None,
    })
    with pytest.raises(ValueError, match="malformed"):
        AlpacaHistoricalSipReader(
            "key", "secret", opener=opener,
        ).read_session(session_open=opened, session_close=closed)


def test_reader_accepts_rfc3339_offset_and_rejects_invalid_calendar_date():
    opened, closed = _session()
    opener = _Opener({
        "quotes": {
            "COIN": [_payload("2026-01-05T09:30:00.000000001-05:00")],
            "QQQ": [_payload("2026-01-05T14:30:00.000000002Z", bid=500.0)],
        },
        "next_page_token": None,
    })
    rows = AlpacaHistoricalSipReader(
        "key", "secret", opener=opener,
    ).read_session(session_open=opened, session_close=closed)
    assert rows[0].provider_event_ns == 1_767_623_400_000_000_001

    invalid = _Opener({
        "quotes": {
            "COIN": [_payload("2026-02-31T14:30:00Z")],
            "QQQ": [_payload("2026-01-05T14:30:00Z", bid=500.0)],
        },
        "next_page_token": None,
    })
    with pytest.raises(ValueError, match="malformed"):
        AlpacaHistoricalSipReader(
            "key", "secret", opener=invalid,
        ).read_session(session_open=opened, session_close=closed)


@pytest.mark.parametrize("day,expected", [
    (datetime(2025, 10, 31, 9, 30, tzinfo=EASTERN), SOURCE_SPEC_ROUND_LOTS),
    (datetime(2025, 11, 3, 9, 30, tzinfo=EASTERN), SOURCE_SPEC_SHARES),
])
def test_reader_versions_quote_size_units_across_provider_boundary(day, expected):
    closed = day.replace(hour=16, minute=0)
    timestamp = day.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    opener = _Opener({
        "quotes": {
            "COIN": [_payload(timestamp)],
            "QQQ": [_payload(timestamp, bid=500.0)],
        },
        "next_page_token": None,
    })
    rows = AlpacaHistoricalSipReader(
        "key", "secret", opener=opener,
    ).read_session(session_open=day, session_close=closed)
    assert {row.source_spec_version for row in rows} == {expected}


def test_frozen_family_calculation_keeps_q10_unavailable():
    opened = datetime(2026, 1, 5, 9, 30, tzinfo=EASTERN)
    closed = opened.replace(hour=16, minute=0)
    rows = []
    for offset in range(32):
        at = opened + timedelta(seconds=offset)
        rows.extend((
            _quote("COIN", at, bid=100.0 + offset / 100),
            _quote("QQQ", at, fraction=1, bid=500.0 + offset / 200),
        ))
    rows.sort(key=lambda row: (row.provider_event_ns,
                               ("COIN", "QQQ").index(row.symbol)))
    frame = tuple(OneSessionReplayClock(
        rows, session_open=opened, session_close=closed,
    ).frames())[-1]

    result = calculate_replay_families(frame)

    assert result.q1_momentum.forecast_bps[0] is not None
    assert result.q3_volatility.volatility_bps[0] is not None
    assert result.q5_microstructure is not None
    assert result.q6_volume_liquidity is not None
    assert result.q10_options_vol is None


def _versions():
    return tuple(
        (quant_id, formula, DATA_SCHEMA_VERSION, SOURCE_SPEC_SHARES)
        for quant_id, formula in ALLOWED_FORMULA_VERSIONS.items()
    )


STATE_AS_OF = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc).timestamp()
TARGET_CUTOFF = STATE_AS_OF - 30.0


def _frame() -> ReplayFrame:
    exact = int(STATE_AS_OF * 1_000_000_000)
    return ReplayFrame(
        exact, exact, exact, None,
        MidpointHistory(), MidpointHistory(), QuoteHistory(),
        replay_method_version=REPLAY_METHOD_VERSION,
    )


def _target(*, resolved_epoch: float = STATE_AS_OF) -> RawTarget:
    return RawTarget(
        1, "cycle", "COIN", TARGET_SPEC_ID, DATA_SCHEMA_VERSION,
        SOURCE_SPEC_SHARES, "30S", TARGET_CUTOFF, STATE_AS_OF,
        resolved_epoch, 1.0,
    )


def _observation(**changes) -> RawFamilyObservation:
    row = RawFamilyObservation(
        2, TargetIdentity("cycle", TARGET_CUTOFF, STATE_AS_OF),
        "COIN", "q1_momentum",
        Q1_VERSION, DATA_SCHEMA_VERSION, SOURCE_SPEC_SHARES, "30S",
        DIRECTIONAL_BPS, 1.0, TARGET_CUTOFF, TARGET_CUTOFF,
        TARGET_CUTOFF, "FRESH",
    )
    return replace(row, **changes)


def _build(*, frame=None, targets=None, observations=None, versions=None):
    return build_replay_v2_as_of(
        frame=_frame() if frame is None else frame,
        replay_run_id="h1-test-run",
        targets_by_horizon={} if targets is None else {"30S": targets},
        observations_by_horizon=(
            {} if observations is None else {"30S": observations}
        ),
        family_versions=_versions() if versions is None else versions,
    )


def test_replay_v2_is_deterministic_and_accepts_exact_as_of_boundary():
    first = _build(targets=(_target(),), observations=(_observation(),))
    second = _build(targets=(_target(),), observations=(_observation(),))
    assert first.v2_state.state_as_of == STATE_AS_OF
    assert first.v2_state.state_hash == second.v2_state.state_hash
    assert first.replay_state_hash == second.replay_state_hash
    assert first.replay_state_id == second.replay_state_id
    assert first.evidence_origin == "HISTORICAL_REPLAY"
    assert first.replay_method_version == REPLAY_METHOD_VERSION
    assert first.replay_run_id == "h1-test-run"
    assert first.historical_session == "2026-01-05"


def test_replay_v2_rejects_future_target_before_dataset_construction():
    with pytest.raises(RuntimeError, match="REPLAY_LOOKAHEAD_VIOLATION"):
        _build(targets=(_target(resolved_epoch=STATE_AS_OF + 0.000001),))


@pytest.mark.parametrize("change", [
    {"forecast_cutoff_epoch": STATE_AS_OF + 0.000001},
    {"source_as_of_epoch": STATE_AS_OF + 0.000001},
    {"available_epoch": STATE_AS_OF + 0.000001},
    {"target_identity": TargetIdentity(
        "cycle", STATE_AS_OF + 0.000001, STATE_AS_OF + 30.000001,
    )},
])
def test_replay_v2_rejects_every_future_family_timestamp(change):
    with pytest.raises(RuntimeError, match="REPLAY_LOOKAHEAD_VIOLATION"):
        _build(targets=(_target(),), observations=(_observation(**change),))


@pytest.mark.parametrize("change", [
    {"source_as_of_epoch": TARGET_CUTOFF + 1},
    {"available_epoch": STATE_AS_OF},
    {"forecast_cutoff_epoch": TARGET_CUTOFF + 1},
])
def test_replay_v2_rejects_causal_attachment_violations(change):
    with pytest.raises(RuntimeError, match="REPLAY_LOOKAHEAD_VIOLATION"):
        _build(targets=(_target(),), observations=(_observation(**change),))


def test_replay_v2_rejects_premarket_targets_and_sources():
    premarket_cutoff = datetime(
        2026, 1, 5, 14, 29, 30, tzinfo=timezone.utc,
    ).timestamp()
    premarket_target = replace(
        _target(), cutoff_epoch=premarket_cutoff,
        maturity_epoch=premarket_cutoff + 30,
    )
    with pytest.raises(RuntimeError, match="REPLAY_TARGET_TIMING_VIOLATION"):
        _build(targets=(premarket_target,))

    premarket_source = datetime(
        2026, 1, 5, 14, 29, 59, tzinfo=timezone.utc,
    ).timestamp()
    with pytest.raises(RuntimeError, match="REPLAY_LOOKAHEAD_VIOLATION"):
        _build(
            targets=(_target(),),
            observations=(_observation(source_as_of_epoch=premarket_source),),
        )


def test_replay_v2_rejects_observation_without_visible_resolved_target():
    with pytest.raises(RuntimeError, match="REPLAY_UNRESOLVED_OBSERVATION"):
        _build(observations=(_observation(),))


def test_replay_v2_rejects_q10_until_exact_historical_source_exists():
    q10_versions = (("q10_options_vol", Q10_VERSION, DATA_SCHEMA_VERSION,
                     SOURCE_SPEC_SHARES),)
    with pytest.raises(RuntimeError, match="REPLAY_Q10_DATA_UNAVAILABLE"):
        _build(versions=q10_versions)
    injected = replace(
        _observation(), quant_id="q10_options_vol", formula_version=Q10_VERSION,
    )
    with pytest.raises(RuntimeError, match="REPLAY_Q10_DATA_UNAVAILABLE"):
        _build(targets=(_target(),), observations=(injected,))


def test_replay_v2_binds_all_rows_and_versions_to_frame_lineage():
    mismatched_target = replace(
        _target(), source_spec_version=SOURCE_SPEC_ROUND_LOTS,
    )
    with pytest.raises(RuntimeError, match="REPLAY_LINEAGE_MISMATCH"):
        _build(targets=(mismatched_target,))
    mismatched_versions = tuple(
        (quant_id, formula, DATA_SCHEMA_VERSION,
         SOURCE_SPEC_ROUND_LOTS if quant_id == "q1_momentum"
         else SOURCE_SPEC_SHARES)
        for quant_id, formula in ALLOWED_FORMULA_VERSIONS.items()
    )
    with pytest.raises(RuntimeError, match="REPLAY_LINEAGE_MISMATCH"):
        _build(versions=mismatched_versions)


def test_replay_v2_pins_target_and_frozen_family_formula_versions():
    wrong_target = replace(_target(), target_spec_id="WRONG_TARGET")
    with pytest.raises(RuntimeError, match="REPLAY_TARGET_SPEC_MISMATCH"):
        _build(targets=(wrong_target,))

    wrong_versions = (("q1_momentum", "WRONG_FORMULA", DATA_SCHEMA_VERSION,
                       SOURCE_SPEC_SHARES),)
    with pytest.raises(RuntimeError, match="REPLAY_FORMULA_LINEAGE_MISMATCH"):
        _build(versions=wrong_versions)

    undeclared = replace(_observation(), quant_id="q2_mean_reversion")
    with pytest.raises(RuntimeError, match="REPLAY_FORMULA_LINEAGE_MISMATCH"):
        _build(targets=(_target(),), observations=(undeclared,))

    with pytest.raises(RuntimeError, match="REPLAY_BASELINE_FAMILY_SET_MISMATCH"):
        _build(versions=())


def test_replay_v2_snapshots_one_shot_inputs_before_all_checks():
    future = _observation(source_as_of_epoch=STATE_AS_OF + 0.000001)
    with pytest.raises(RuntimeError, match="REPLAY_LOOKAHEAD_VIOLATION"):
        _build(targets=iter((_target(),)), observations=iter((future,)))


def test_replay_v2_run_identity_is_part_of_replay_provenance_hash():
    first = build_replay_v2_as_of(
        frame=_frame(), replay_run_id="run-a",
        targets_by_horizon={}, observations_by_horizon={},
        family_versions=_versions(),
    )
    second = build_replay_v2_as_of(
        frame=_frame(), replay_run_id="run-b",
        targets_by_horizon={}, observations_by_horizon={},
        family_versions=_versions(),
    )
    assert first.v2_state.state_hash == second.v2_state.state_hash
    assert first.replay_state_hash != second.replay_state_hash
    assert first.replay_state_id != second.replay_state_id
    with pytest.raises(ValueError, match="identity"):
        replace(first, replay_run_id="tampered-run")
    tampered_v2 = replace(first.v2_state, top_level_status="MATURE")
    with pytest.raises(ValueError, match="inner identity"):
        replace(first, v2_state=tampered_v2)


def _rehash_v2(state):
    digest = v2d_state_hash(state)
    return replace(state, state_hash=digest, state_id=f"v9v2:{digest}")


def test_replay_envelope_rejects_canonical_unauthorized_inner_states():
    baseline = _build()
    first_horizon = baseline.v2_state.horizon_state_tuple[0]
    forged_lineage = (
        replace(first_horizon.family_lineage[0], formula_version="WRONG_FORMULA"),
        *first_horizon.family_lineage[1:],
    )
    forged_horizon = replace(first_horizon, family_lineage=forged_lineage)
    forged_formula = _rehash_v2(replace(
        baseline.v2_state,
        horizon_state_tuple=(forged_horizon,
                             *baseline.v2_state.horizon_state_tuple[1:]),
    ))
    with pytest.raises(ValueError, match="not an authorized baseline"):
        replace(baseline, v2_state=forged_formula)

    after_hours = datetime(
        2026, 1, 5, 22, 0, tzinfo=timezone.utc,
    ).timestamp()
    forged_time = _rehash_v2(replace(
        baseline.v2_state, state_as_of=after_hours,
    ))
    with pytest.raises(ValueError, match="not an authorized baseline"):
        replace(baseline, v2_state=forged_time)

    promoted_horizon = replace(first_horizon, status="MATURE")
    promoted_status = _rehash_v2(replace(
        baseline.v2_state, top_level_status="PROVISIONAL",
        horizon_state_tuple=(promoted_horizon,
                             *baseline.v2_state.horizon_state_tuple[1:]),
    ))
    with pytest.raises(ValueError, match="not an authorized baseline"):
        replace(baseline, v2_state=promoted_status)
