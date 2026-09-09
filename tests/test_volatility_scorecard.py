"""V-1B manifest scorecard contract tests using synthetic evidence only.

The tests deliberately do not contact GitHub, Render, Supabase, PostgreSQL, or
any market-data service.  Production boundaries are exercised through the
module's pure validators and injected transport/runtime seams.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import math
import os
import selectors
import shlex
import ssl
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest


# Load the authorized module without executing quant/__init__.py.  The local
# review mirror intentionally omits quant.models; production's isolated launch
# likewise creates a synthetic quant namespace and does not execute that file.
MODULE_PATH = Path(__file__).parents[1] / "quant" / "volatility_scorecard.py"
SPEC = importlib.util.spec_from_file_location("atom_v1b_test_subject", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
sc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sc
SPEC.loader.exec_module(sc)


UTC = timezone.utc
FAMILY_30S = sc.CELL_BY_ORDER[0]
V9_30S = sc.CELL_BY_ORDER[6]


class _SyntheticZoneInfo(tzinfo):
    """No-system-TZif stand-in for synthetic Aug/Sep 2026 math fixtures."""

    @classmethod
    def clear_cache(cls):
        return None

    def __init__(self, key):
        self.key = key

    def utcoffset(self, value):
        return timedelta(hours=0 if self.key == "UTC" else -4)

    def dst(self, value):
        return timedelta(0)

    def tzname(self, value):
        return self.key


@pytest.fixture(autouse=True)
def _synthetic_zoneinfo_isolation(monkeypatch):
    """Keep pure math tests independent of host `/usr/share/zoneinfo` bytes."""

    module = SimpleNamespace(TZPATH=())

    def reset_tzpath(value):
        module.TZPATH = tuple(value)

    module.reset_tzpath = reset_tzpath
    module.ZoneInfo = _SyntheticZoneInfo
    tzdata_module = SimpleNamespace(__name__="tzdata")
    state = sc.ZoneInfoIsolation(
        module=module,
        reset_tzpath=reset_tzpath,
        zoneinfo_class=_SyntheticZoneInfo,
        clear_cache_descriptor=_SyntheticZoneInfo.__dict__["clear_cache"],
        tzdata_module=tzdata_module,
        new_york=_SyntheticZoneInfo("America/New_York"),
        utc=_SyntheticZoneInfo("UTC"),
    )
    monkeypatch.setitem(sys.modules, "zoneinfo", module)
    monkeypatch.setitem(sys.modules, "tzdata", tzdata_module)
    monkeypatch.setattr(sc, "_ZONEINFO_ISOLATION", state)
    yield state


def test_zoneinfo_isolation_rejects_either_preloaded_module_before_import(
    monkeypatch,
):
    for preloaded in ("zoneinfo", "tzdata"):
        monkeypatch.setattr(sc, "_ZONEINFO_ISOLATION", None)
        monkeypatch.delitem(sys.modules, "zoneinfo", raising=False)
        monkeypatch.delitem(sys.modules, "tzdata", raising=False)
        monkeypatch.setitem(sys.modules, preloaded, object())
        imports = []
        monkeypatch.setattr(
            sc.importlib,
            "import_module",
            lambda name: imports.append(name),
        )
        with pytest.raises(
            sc.StartupIsolationError,
            match="ZONEINFO_LOADED_BEFORE_ISOLATION",
        ):
            sc._initialize_zoneinfo_isolation()
        assert imports == []


def _run_fake_zoneinfo_initialization(monkeypatch, tamper_after_new_york=None):
    events = []
    monkeypatch.setattr(sc, "_ZONEINFO_ISOLATION", None)
    monkeypatch.delitem(sys.modules, "zoneinfo", raising=False)
    monkeypatch.delitem(sys.modules, "tzdata", raising=False)
    module = SimpleNamespace(TZPATH=("/forbidden/system",))
    tzdata_module = SimpleNamespace(__name__="tzdata")

    class FakeZoneInfo:
        @classmethod
        def clear_cache(cls):
            events.append("clear_cache")

        def __init__(self, key):
            events.append(f"construct:{key}")
            self.key = key
            if key == "America/New_York":
                sys.modules["tzdata"] = tzdata_module
                if tamper_after_new_york is not None:
                    tamper_after_new_york(module, FakeZoneInfo)

    def reset_tzpath(value):
        events.append(("reset_tzpath", value))
        module.TZPATH = tuple(value)

    module.ZoneInfo = FakeZoneInfo
    module.reset_tzpath = reset_tzpath

    def import_module(name):
        events.append(f"import:{name}")
        if name == "zoneinfo":
            sys.modules["zoneinfo"] = module
            return module
        assert name == "tzdata"
        sys.modules["tzdata"] = tzdata_module
        return tzdata_module

    monkeypatch.setattr(sc.importlib, "import_module", import_module)
    return events, module, FakeZoneInfo, tzdata_module


def test_zoneinfo_isolation_resets_empty_then_clears_once_before_exact_keys(
    monkeypatch,
):
    events, module, zone_class, tzdata_module = _run_fake_zoneinfo_initialization(
        monkeypatch
    )
    state = sc._initialize_zoneinfo_isolation()
    assert events == [
        "import:zoneinfo",
        ("reset_tzpath", ()),
        "clear_cache",
        "import:tzdata",
        "construct:America/New_York",
        "construct:UTC",
    ]
    assert state.module is module
    assert state.reset_tzpath is module.__dict__["reset_tzpath"]
    assert state.zoneinfo_class is zone_class
    assert state.clear_cache_descriptor is zone_class.__dict__["clear_cache"]
    assert state.tzdata_module is tzdata_module
    assert module.TZPATH == ()
    assert (state.new_york.key, state.utc.key) == ("America/New_York", "UTC")
    assert sc._initialize_zoneinfo_isolation() is state
    assert events.count(("reset_tzpath", ())) == 1
    assert events.count("clear_cache") == 1


@pytest.mark.parametrize(
    "tampered_member", ("reset_tzpath", "clear_cache", "tzdata_module")
)
def test_zoneinfo_identity_tamper_after_new_york_stops_before_utc_construction(
    tampered_member, monkeypatch
):
    def tamper(module, zone_class):
        if tampered_member == "reset_tzpath":
            module.reset_tzpath = lambda value: None
        elif tampered_member == "clear_cache":
            zone_class.clear_cache = classmethod(lambda cls: None)
        else:
            sys.modules["tzdata"] = object()

    events, _module, _zone_class, _tzdata = _run_fake_zoneinfo_initialization(
        monkeypatch, tamper
    )
    with pytest.raises(sc.StartupIsolationError, match="ZONEINFO_"):
        sc._initialize_zoneinfo_isolation()
    assert "construct:America/New_York" in events
    assert "construct:UTC" not in events


@pytest.mark.parametrize(
    "mutate",
    (
        lambda state: replace(state, module=object()),
        lambda state: replace(state, reset_tzpath=object()),
        lambda state: replace(state, zoneinfo_class=type("OtherZone", (), {})),
        lambda state: replace(state, clear_cache_descriptor=object()),
        lambda state: replace(state, tzdata_module=object()),
        lambda state: replace(state, new_york=_SyntheticZoneInfo("UTC")),
        lambda state: replace(state, utc=_SyntheticZoneInfo("Etc/UTC")),
    ),
)
def test_zoneinfo_repeated_guard_rejects_each_retained_identity_or_key_change(
    mutate, _synthetic_zoneinfo_isolation
):
    with pytest.raises(sc.StartupIsolationError, match="ZONEINFO_ISOLATION_INVALID"):
        sc._validate_zoneinfo_isolation(mutate(_synthetic_zoneinfo_isolation))


def _synthetic_runtime_closure_modules(
    monkeypatch,
    zone_state,
    *,
    xnys_zone=None,
    helper_utc=None,
    events=None,
):
    observed_events = [] if events is None else events
    calendar = SimpleNamespace(
        name="XNYS",
        tz=zone_state.new_york if xnys_zone is None else xnys_zone,
    )

    def get_calendar(name):
        observed_events.append(("get_calendar", name))
        return calendar

    modules = {
        "exchange_calendars": SimpleNamespace(get_calendar=get_calendar),
        "exchange_calendars.calendar_helpers": SimpleNamespace(
            UTC=zone_state.utc if helper_utc is None else helper_utc
        ),
        "quant.v9_v4a_evidence": SimpleNamespace(
            MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS=5.0
        ),
        "quant.v9_v4b_accuracy": SimpleNamespace(),
        "quant.v9_v4c_predictive": SimpleNamespace(),
        "psycopg": SimpleNamespace(),
        "psycopg.conninfo": SimpleNamespace(),
    }
    for name, value in modules.items():
        monkeypatch.setitem(sys.modules, name, value)
    return calendar, modules


def test_runtime_closure_retains_exact_xnys_and_calendar_helpers_zone_objects(
    monkeypatch, _synthetic_zoneinfo_isolation
):
    state = _synthetic_zoneinfo_isolation
    events = []
    monkeypatch.setattr(
        sc,
        "_initialize_zoneinfo_isolation",
        lambda: events.append("zone_initialize") or state,
    )
    original_validate = sc._validate_zoneinfo_isolation

    def validate(observed, **kwargs):
        events.append("zone_validate")
        return original_validate(observed, **kwargs)

    monkeypatch.setattr(sc, "_validate_zoneinfo_isolation", validate)

    def load_closure():
        events.append("closure")
        _synthetic_runtime_closure_modules(
            monkeypatch, state, events=events
        )
        return frozenset(sys.modules)

    monkeypatch.setattr(sc, "_load_complete_runtime_closure", load_closure)
    initialized = sc._initialize_runtime_for_measurement()
    assert events[:3] == ["zone_initialize", "zone_validate", "closure"]
    assert ("get_calendar", "XNYS") in events
    assert initialized.zoneinfo_isolation is state
    assert initialized.xnys_calendar.tz is state.new_york
    assert sys.modules["exchange_calendars.calendar_helpers"].UTC is state.utc
    assert isinstance(initialized.xnys_calendar.tz, state.zoneinfo_class)
    assert isinstance(
        sys.modules["exchange_calendars.calendar_helpers"].UTC,
        state.zoneinfo_class,
    )
    assert initialized.xnys_calendar.tz.key == "America/New_York"
    assert sys.modules["exchange_calendars.calendar_helpers"].UTC.key == "UTC"


@pytest.mark.parametrize("wrong_target", ("xnys_class", "xnys_key", "utc_class", "utc_key"))
def test_runtime_closure_rejects_wrong_xnys_or_calendar_helpers_class_and_key(
    wrong_target, monkeypatch, _synthetic_zoneinfo_isolation
):
    state = _synthetic_zoneinfo_isolation
    other_class = timezone.utc
    wrong_key = _SyntheticZoneInfo("Etc/UTC")
    xnys_zone = (
        other_class
        if wrong_target == "xnys_class"
        else wrong_key
        if wrong_target == "xnys_key"
        else state.new_york
    )
    helper_utc = (
        other_class
        if wrong_target == "utc_class"
        else wrong_key
        if wrong_target == "utc_key"
        else state.utc
    )
    monkeypatch.setattr(sc, "_initialize_zoneinfo_isolation", lambda: state)

    def load_closure():
        _synthetic_runtime_closure_modules(
            monkeypatch,
            state,
            xnys_zone=xnys_zone,
            helper_utc=helper_utc,
        )
        return frozenset(sys.modules)

    monkeypatch.setattr(sc, "_load_complete_runtime_closure", load_closure)
    with pytest.raises(
        sc.OrchestrationFailure,
        match="RUNTIME_CLOSURE_INITIALIZATION_FAILED",
    ):
        sc._initialize_runtime_for_measurement()


def _window(
    index: int,
    *,
    session: date = date(2026, 9, 8),
    predicted: float | None = None,
    realized: float | None = None,
    available_at: datetime | None = None,
) -> sc.ValidWindow:
    cutoff = datetime.combine(session, datetime.min.time(), UTC) + timedelta(
        hours=14, minutes=30, seconds=31 * index
    )
    return sc.ValidWindow(
        session_date=session,
        cutoff_at=cutoff,
        record_identity=f"row-{session.isoformat()}-{index:04d}",
        predicted_volatility_bps=(
            float(predicted) if predicted is not None else 2.0 + (index % 7)
        ),
        realized_volatility_bps=(
            float(realized) if realized is not None else 1.0 + ((index * 3) % 11)
        ),
        outcome_available_at=available_at or cutoff,
    )


def _population(
    windows: tuple[sc.ValidWindow, ...] | list[sc.ValidWindow],
    *,
    spec: sc.CellSpec = FAMILY_30S,
    lineage: dict[str, str] | None = None,
    n_unselected: int = 0,
    n_inadmissible: int = 0,
    n_non_rth: int = 0,
    n_overlap: int = 0,
    n_null: int = 0,
    n_nonpositive: int = 0,
    n_kappa: int = 0,
    protocol_defect: bool = False,
) -> sc.CellPopulation:
    selected = tuple(windows)
    return sc.assemble_cell_population(
        spec=spec,
        lineage_identity=lineage or sc.family_lineage(spec.horizon),
        n_input=(
            n_unselected
            + n_inadmissible
            + n_non_rth
            + n_overlap
            + n_null
            + n_nonpositive
            + n_kappa
            + len(selected)
        ),
        n_unselected_lineage_rows=n_unselected,
        n_inadmissible=n_inadmissible,
        n_non_rth=n_non_rth,
        n_overlap_excluded=n_overlap,
        n_null_or_nonfinite_excluded=n_null,
        n_nonpositive_prediction_excluded=n_nonpositive,
        n_kappa_unavailable=n_kappa,
        windows=selected,
        protocol_defect=protocol_defect,
    )


def _ready_windows() -> tuple[sc.ValidWindow, ...]:
    """Fourteen full synthetic sessions; 120 regression / 119 gate rows."""

    sessions: list[date] = []
    cursor = date(2026, 9, 8)
    while len(sessions) < 14:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    rows: list[sc.ValidWindow] = []
    global_index = 0
    for session_index, session in enumerate(sessions):
        for within in range(10):
            cutoff = datetime.combine(session, datetime.min.time(), UTC) + timedelta(
                hours=14, minutes=30, seconds=31 * within
            )
            rows.append(
                sc.ValidWindow(
                    session_date=session,
                    cutoff_at=cutoff,
                    record_identity=f"r-{global_index:04d}",
                    predicted_volatility_bps=(
                        1.0 + (global_index % 13) + (session_index * 0.01)
                    ),
                    realized_volatility_bps=(
                        0.5 + ((global_index * 7) % 17) + (within * 0.02)
                    ),
                    outcome_available_at=cutoff,
                )
            )
            global_index += 1
    return tuple(rows)


# ---------------------------------------------------------------------------
# Closed registry, identities, and canonical primitives


def test_manifest_registry_is_closed_ordered_and_partitions_all_twelve_cells():
    assert tuple(sc.MANIFEST_REGISTRY) == (
        "v1b-early-4",
        "v1b-family-5m",
        "v1b-family-15m",
        "v1b-family-30m",
        "v1b-family-1h",
        "v1b-v9-5m",
        "v1b-v9-15m",
        "v1b-v9-30m",
        "v1b-v9-1h",
    )
    assert [sc.manifest_sequence(name) for name in sc.MANIFEST_REGISTRY] == list(
        range(1, 10)
    )
    assert [cell.cell_order for cell in sc.manifest_cells("v1b-early-4")] == [
        0,
        1,
        6,
        7,
    ]
    all_orders = [
        cell.cell_order
        for manifest_id in sc.MANIFEST_REGISTRY
        for cell in sc.manifest_cells(manifest_id)
    ]
    assert sorted(all_orders) == list(range(12))
    assert len(all_orders) == len(set(all_orders)) == 12
    with pytest.raises(sc.ContractError, match="INVALID_MANIFEST_ID"):
        sc.manifest_cells("v1b-unknown")


def test_canonical_json_and_digest_are_exact_and_reject_nonfinite_numbers():
    value = {"z": "λ", "a": [2, 1], "nested": {"b": True}}
    expected = '{"a":[2,1],"nested":{"b":true},"z":"λ"}'
    assert sc.canonical_json(value) == expected
    assert sc.canonical_sha256(value) == hashlib.sha256(
        expected.encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError):
        sc.canonical_json({"not_json": math.nan})


def test_timestamp_utc_requires_aware_datetime_and_emits_microseconds():
    value = datetime(2026, 9, 8, 16, 0, 0, 123, tzinfo=timezone(timedelta(hours=-4)))
    assert sc.timestamp_utc(value) == "2026-09-08T20:00:00.000123Z"
    with pytest.raises(sc.ContractError):
        sc.timestamp_utc(datetime(2026, 9, 8, 20, 0))


def test_cell_and_lineage_objects_have_exact_global_identity():
    assert [(c.cell_order, c.forecaster, c.horizon) for c in sc.ALL_CELLS] == [
        (0, "FAMILY-VOL", "30S"),
        (1, "FAMILY-VOL", "1M"),
        (2, "FAMILY-VOL", "5M"),
        (3, "FAMILY-VOL", "15M"),
        (4, "FAMILY-VOL", "30M"),
        (5, "FAMILY-VOL", "1H"),
        (6, "V9-VOL", "30S"),
        (7, "V9-VOL", "1M"),
        (8, "V9-VOL", "5M"),
        (9, "V9-VOL", "15M"),
        (10, "V9-VOL", "30M"),
        (11, "V9-VOL", "1H"),
    ]
    assert sc.family_lineage("30S") == {
        "quant_id": "q3_volatility",
        "formula_version": "realized-volatility-v1",
        "symbol": "COIN",
        "horizon": "30S",
    }
    sentinel = sc.v9_sentinel_lineage("30S")
    assert sentinel == {
        "v3_model_version": "__NO_ADMISSIBLE_V9_LINEAGE__",
        "symbol": "COIN",
        "horizon": "30S",
        "cohort_id": "__NO_ADMISSIBLE_V9_LINEAGE__",
        "cohort_hash": "0" * 64,
    }
    sc.validate_lineage_identity(V9_30S, sentinel)
    poisoned = {**sentinel, "cohort_id": "real-cohort"}
    with pytest.raises(sc.ProtocolDefect, match="reserved V9 sentinel"):
        sc.validate_lineage_identity(V9_30S, poisoned)


def test_v9_lineage_selection_is_outcome_blind_latest_then_utf8_greatest():
    boundary = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
    earlier = boundary - timedelta(seconds=1)
    candidates = [
        sc.V9LineageCandidate("v1", "COIN", "30S", "z", "1" * 64, earlier),
        sc.V9LineageCandidate("v2", "COIN", "30S", "a", "2" * 64, earlier),
        sc.V9LineageCandidate(
            "v9", "COIN", "30S", "future", "f" * 64, boundary + timedelta(microseconds=1)
        ),
    ]
    selected = sc.select_v9_lineage("30S", candidates, boundary)
    assert selected["v3_model_version"] == "v2"
    assert selected["cohort_id"] == "a"
    assert sc.select_v9_lineage("30S", [], boundary) == sc.v9_sentinel_lineage(
        "30S"
    )


# ---------------------------------------------------------------------------
# Frozen binary64 mathematics and population accounting


@pytest.mark.parametrize(
    ("realized", "forecast"),
    [(-1.0, 1.0), (1.0, 0.0), (1.0, -1.0), (math.nan, 1.0), (1.0, math.inf)],
)
def test_qlike_rejects_values_outside_frozen_domain(realized, forecast):
    with pytest.raises(ArithmeticError, match="QLIKE_ARITHMETIC_NONFINITE"):
        sc.qlike(realized, forecast)


def test_qlike_uses_underflow_safe_displayed_order_and_accepts_zero_realization():
    forecast = math.ulp(0.0)
    assert sc.qlike(0.0, forecast) == 2.0 * math.log(forecast)
    assert sc.qlike(4.0, 2.0) == pytest.approx(2.0 * math.log(2.0) + 4.0)


def test_percentile_indices_and_levels_are_frozen():
    values = [float(value) for value in range(1, 200_001)]
    assert sc.percentile_interval(values, 0.999) == (100.0, 199_901.0)
    assert sc.percentile_interval(values, 0.95) == (5_000.0, 195_001.0)
    with pytest.raises(ValueError, match="unfrozen interval"):
        sc.percentile_interval(values, 0.90)
    with pytest.raises(ValueError, match="no bootstrap"):
        sc.percentile_interval([], 0.999)


def test_spearman_uses_midranks_and_nulls_degenerate_inputs():
    assert sc.spearman([1.0, 2.0, 2.0, 4.0], [4.0, 1.0, 3.0, 2.0]) == pytest.approx(
        -0.6324555320336759
    )
    assert sc.spearman([1.0], [1.0]) is None
    assert sc.spearman([1.0, 1.0], [2.0, 3.0]) is None
    assert sc.spearman([1.0, math.nan], [2.0, 3.0]) is None


def test_mincer_zarnowitz_exact_fit_and_null_rules():
    fit = sc.mz_fit([1.0, 2.0, 3.0], [3.0, 5.0, 7.0])
    assert fit == sc.MZResult(1.0, 2.0, 1.0)
    assert sc.mz_fit([1.0], [2.0]) == sc.MZResult(None, None, None)
    assert sc.mz_fit([1.0, 1.0], [2.0, 3.0]) == sc.MZResult(None, None, None)
    constant_y = sc.mz_fit([1.0, 2.0], [3.0, 3.0])
    assert constant_y == sc.MZResult(3.0, 0.0, None)


def test_encompassing_ols_recovers_known_coefficients_and_rejects_rank_defect():
    rows: list[sc.RegressionWindow] = []
    for index, (persist, forecast) in enumerate(
        [(1.0, 2.0), (2.0, 1.0), (3.0, 4.0), (4.0, 2.0), (5.0, 6.0)]
    ):
        outcome = 7.0 + (3.0 * persist) + (2.0 * forecast)
        rows.append(sc.RegressionWindow(_window(index, predicted=forecast, realized=outcome), 0.0, persist))
    fit = sc.encompassing_ols(rows)
    assert fit == sc.OLSResult("OK", 7.0, 3.0, 2.0)
    collinear = [
        sc.RegressionWindow(_window(i, predicted=float(i + 1)), 0.0, float(i + 1))
        for i in range(4)
    ]
    assert sc.encompassing_ols(collinear).status == "RANK_DEFICIENT"


def test_encompassing_ols_strict_rank_threshold_rejects_below_and_accepts_above():
    persistence = (7.0, 9.0, 11.0, 13.0)
    orthogonal = (1.0, -1.0, -1.0, 1.0)

    def rows(scale):
        result = []
        for index, (persist, perturbation) in enumerate(
            zip(persistence, orthogonal, strict=True)
        ):
            forecast = persist + scale * perturbation
            realized = 1.0 + 2.0 * persist + 3.0 * forecast
            result.append(
                sc.RegressionWindow(
                    _window(index, predicted=forecast, realized=realized),
                    0.0,
                    persist,
                )
            )
        return result

    assert sc.encompassing_ols(rows(2.23 * 2.0**-20)).status == "RANK_DEFICIENT"
    assert sc.encompassing_ols(rows(2.24 * 2.0**-20)).status == "OK"


def test_persistence_uses_prior_twenty_and_causal_availability():
    rows = [_window(index, realized=float(index + 1)) for index in range(22)]
    regression, unavailable = sc.build_regression_population(rows)
    assert unavailable == 20
    assert len(regression) == 2
    assert regression[0].persist_1 == 20.0
    assert regression[0].persist_20 == math.fsum(float(i) for i in range(1, 21)) / 20
    assert regression[1].persist_1 == 21.0
    delayed = list(rows)
    delayed[0] = replace(
        delayed[0], outcome_available_at=delayed[20].cutoff_at + timedelta(seconds=1)
    )
    delayed_regression, delayed_unavailable = sc.build_regression_population(delayed)
    assert delayed_unavailable == 21
    assert len(delayed_regression) == 1


def test_persistence_twenty_uses_fsum_for_large_small_magnitude_mix():
    realized = [1.0e16, *([1.0] * 19), 2.0]
    rows = [_window(index, realized=value) for index, value in enumerate(realized)]
    regression, unavailable = sc.build_regression_population(rows)
    assert unavailable == 20
    assert len(regression) == 1
    assert regression[0].persist_20 == 500000000000001.0


def test_population_reconciles_input_and_regression_equations():
    rows = [_window(index) for index in range(23)]
    population = _population(
        rows,
        n_unselected=1,
        n_inadmissible=2,
        n_non_rth=3,
        n_overlap=4,
        n_null=5,
        n_nonpositive=6,
    )
    assert population.n_input == 44
    assert len(population.windows) == 23
    assert population.n_persist20_unavailable == 20
    assert len(population.regression) == 3
    assert population.n_unconditional_unavailable == 1
    assert len(population.windows) == (
        population.n_persist20_unavailable + len(population.regression)
    )
    with pytest.raises(sc.ProtocolDefect, match="input accounting"):
        replace(population, n_input=population.n_input + 1).validate()
    with pytest.raises(sc.ProtocolDefect, match="FAMILY kappa"):
        replace(population, n_kappa_unavailable=1, n_input=population.n_input + 1).validate()


def test_sentinel_cell_assigns_every_input_to_inadmissible_without_fake_windows():
    population = _population(
        [],
        spec=V9_30S,
        lineage=sc.v9_sentinel_lineage("30S"),
        n_inadmissible=7,
    )
    assert population.n_input == population.n_inadmissible == 7
    assert population.n_unselected_lineage_rows == 0
    cell = sc.evaluate_cell(population)
    assert cell["classification"] == "INSUFFICIENT"
    assert cell["session_dates"] == []
    assert cell["evidence_min_cutoff_at"] is None
    assert cell["evidence_max_cutoff_at"] is None
    assert cell["gate_unconditional"] == "UNAVAILABLE"
    assert cell["gate_seasonal"] == "UNAVAILABLE"
    assert set(cell["reason_codes"]) == {
        "INSUFFICIENT_REGRESSION_WINDOWS",
        "INSUFFICIENT_REGRESSION_SESSIONS",
        "INSUFFICIENT_UNCONDITIONAL_GATE_WINDOWS",
        "INSUFFICIENT_UNCONDITIONAL_GATE_SESSIONS",
        "INSUFFICIENT_SEASONAL_GATE_WINDOWS",
        "INSUFFICIENT_SEASONAL_GATE_SESSIONS",
    }


def test_causal_benchmarks_share_population_and_use_prior_rows_only():
    rows = [_window(index, realized=float(index + 1)) for index in range(24)]
    regression, _ = sc.build_regression_population(rows)
    attached, unavailable = sc.attach_causal_benchmarks(regression)
    assert unavailable == 1
    assert attached[0].unconditional is None and attached[0].seasonal is None
    assert attached[1].unconditional == attached[0].window.realized_volatility_bps
    assert attached[1].seasonal == attached[1].unconditional
    assert [row.unconditional is not None for row in attached] == [
        row.seasonal is not None for row in attached
    ]


@pytest.mark.parametrize("zero", (0.0, -0.0))
def test_descriptive_metrics_and_level_ratio_zero_behavior(zero):
    population = _population(
        [
            _window(0, predicted=1.0, realized=zero),
            _window(1, predicted=2.0, realized=zero),
        ]
    )
    metrics = sc.descriptive_metrics(population)
    assert metrics.mae_bps == pytest.approx(1.5)
    assert metrics.level_ratio is None
    assert metrics.coverage_90 == 1.0
    assert metrics.rank_corr is None


def test_v9_cohort_trace_accepts_exact_initial_rotation_and_rejects_drift():
    manifest_id = "v1b-v9-5m"
    expected_cell = sc.manifest_public_cells(manifest_id)[0]
    initial_lineage = {
        "v3_model_version": "v9.1",
        "symbol": "COIN",
        "horizon": "5M",
        "cohort_id": "cohort-a",
        "cohort_hash": "a" * 64,
    }
    final_lineage = {
        **initial_lineage,
        "v3_model_version": "v9.2",
        "cohort_id": "cohort-b",
        "cohort_hash": "b" * 64,
    }
    selected = [{**expected_cell, "lineage_identity": final_lineage}]
    events = [
        {
            "candidate_session": "2026-09-08",
            **expected_cell,
            "event_type": "INITIAL",
            "selected_lineage_identity": initial_lineage,
        },
        {
            "candidate_session": "2026-09-09",
            **expected_cell,
            "event_type": "ROTATION",
            "selected_lineage_identity": final_lineage,
        },
    ]
    sc.validate_cohort_trace(
        manifest_id,
        events,
        first_candidate_session="2026-09-08",
        boundary_session="2026-09-09",
        selected_lineages=selected,
    )

    mutations = (
        ("array required", None),
        ("nonmanifest/non-V9", [{**events[0], "cell_order": 0}]),
        ("wrong V9 cell", [{**events[0], "horizon": "15M"}]),
        ("outside examined range", [{**events[0], "candidate_session": "2026-09-07"}]),
        ("bad event type", [{**events[0], "event_type": "UNKNOWN"}]),
        ("first event must be INITIAL", [{**events[0], "event_type": "ROTATION"}]),
        (
            "not strictly candidate/cell ordered",
            [events[0], events[1], {**events[1], "candidate_session": "2026-09-08"}],
        ),
        ("invalid/redundant rotation", [events[0], {**events[1], "selected_lineage_identity": initial_lineage}]),
        ("missing V9 INITIAL", []),
    )
    for message, value in mutations:
        with pytest.raises(sc.ProtocolDefect, match=message):
            sc.validate_cohort_trace(
                manifest_id,
                value,
                first_candidate_session="2026-09-08",
                boundary_session="2026-09-09",
                selected_lineages=selected,
            )

    wrong_selected = [{**expected_cell, "lineage_identity": initial_lineage}]
    with pytest.raises(sc.ProtocolDefect, match="final lineage mismatch"):
        sc.validate_cohort_trace(
            manifest_id,
            events,
            first_candidate_session="2026-09-08",
            boundary_session="2026-09-09",
            selected_lineages=wrong_selected,
        )

    with pytest.raises(sc.ProtocolDefect, match="FAMILY manifest must be empty"):
        sc.validate_cohort_trace(
            "v1b-family-5m",
            events,
            first_candidate_session="2026-09-08",
            boundary_session="2026-09-09",
            selected_lineages=[],
        )


def test_xnys_candidate_enumeration_filters_exact_full_sessions_and_targets():
    first_day = date(2026, 9, 8)
    second_day = date(2026, 9, 9)
    first = sc.CalendarSession(
        first_day,
        datetime(2026, 9, 8, 13, 30, tzinfo=UTC),
        datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
    )
    shortened = sc.CalendarSession(
        second_day,
        datetime(2026, 9, 9, 13, 30, tzinfo=UTC),
        datetime(2026, 9, 9, 17, 0, tzinfo=UTC),
    )
    candidates = sc.enumerate_xnys_candidates(
        (first, shortened),
        amendment_merged_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
        scan_started_at=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
    )
    assert candidates == (first,)
    assert sc.qualifying_full_xnys_sessions((first, shortened)) == (first,)

    sessions = {first_day: first}
    assert sc._session_for_target(
        datetime(2026, 9, 8, 13, 31, tzinfo=UTC),
        datetime(2026, 9, 8, 13, 36, tzinfo=UTC),
        sessions,
    ) == first_day
    assert sc._session_for_target(
        datetime(2026, 9, 8, 13, 31, tzinfo=UTC),
        datetime(2026, 9, 8, 20, 1, tzinfo=UTC),
        sessions,
    ) is None
    assert sc._session_for_target(
        datetime(2026, 9, 8, 13, 31, tzinfo=UTC),
        datetime(2026, 9, 8, 13, 31, tzinfo=UTC),
        sessions,
    ) is None

    with pytest.raises(sc.ProtocolDefect, match="calendar row type"):
        sc.enumerate_xnys_candidates(
            (object(),),
            amendment_merged_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
            scan_started_at=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
        )
    with pytest.raises(sc.ProtocolDefect, match="not strictly ordered"):
        sc.qualifying_full_xnys_sessions((shortened, first))


def test_gate_loss_populations_and_summary_differences_are_exact():
    base = _window(0, predicted=2.0, realized=4.0)
    row = sc.RegressionWindow(base, persist_1=1.0, persist_20=1.5, unconditional=3.0, seasonal=3.0)
    result = sc.gate_loss_data([row], "unconditional")
    assert result.rows == (row,)
    assert result.candidate_losses == (5.386294361119891,)
    assert result.benchmark_losses == (3.9750023551139972,)
    assert result.difference_mean == -1.4112920060058936
    absent = replace(row, unconditional=None)
    empty = sc.gate_loss_data([absent], "unconditional")
    assert empty.rows == () and empty.candidate_mean is None
    with pytest.raises(ValueError, match="invalid benchmark"):
        sc.gate_loss_data([row], "persistence")


def test_bootstrap_streams_are_deterministic_and_grouped_by_session():
    sessions = [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    rows: list[sc.RegressionWindow] = []
    differences: list[float] = []
    for session_index, session in enumerate(sessions):
        for within in range(4):
            persist = float(1 + within + session_index)
            forecast = float(2 + (within * 2) + (session_index % 2))
            outcome = 1.0 + (0.5 * persist) + (1.5 * forecast)
            rows.append(
                sc.RegressionWindow(
                    _window(within, session=session, predicted=forecast, realized=outcome),
                    persist_1=persist,
                    persist_20=persist,
                )
            )
            differences.append(float(session_index + 1))
    first = sc.bootstrap_enc_b(rows, required=20, max_attempts=200)
    second = sc.bootstrap_enc_b(rows, required=20, max_attempts=200)
    assert first == second
    assert first.valid == 20 and first.attempted >= first.valid
    assert first.invalid == first.attempted - first.valid
    assert first.ci_0999 is not None and first.exhausted is False
    gate_first = sc.bootstrap_gate_mean(rows, differences, required=20, max_attempts=20)
    gate_second = sc.bootstrap_gate_mean(rows, differences, required=20, max_attempts=20)
    assert gate_first == gate_second
    assert gate_first.valid == gate_first.attempted == 20


def test_bootstrap_exhaustion_preserves_exact_attempt_valid_invalid_counters():
    rank_deficient = [
        sc.RegressionWindow(_window(i, predicted=1.0, realized=2.0), 1.0, 1.0)
        for i in range(3)
    ]
    result = sc.bootstrap_enc_b(rank_deficient, required=3, max_attempts=5)
    assert result == sc.BootstrapResult(5, 0, 5, None, None, True)


def test_bootstrap_uses_one_random_zero_stream_and_advances_after_invalid_draw(
    monkeypatch,
):
    day_one = date(2026, 9, 8)
    day_two = date(2026, 9, 9)
    rows = [
        sc.RegressionWindow(_window(0, session=day_one), 1.0, 1.0),
        sc.RegressionWindow(_window(1, session=day_one), 2.0, 2.0),
        sc.RegressionWindow(_window(0, session=day_two), 3.0, 3.0),
        sc.RegressionWindow(_window(1, session=day_two), 4.0, 4.0),
    ]
    scripts = [[day_two.isoformat(), day_one.isoformat()], [day_one.isoformat()] * 2]
    populations = []
    seeds = []

    class ScriptedRandom:
        def __init__(self, seed):
            seeds.append(seed)

        def choices(self, population, *, k):
            assert list(population) == [day_one.isoformat(), day_two.isoformat()]
            assert k == 2
            return scripts.pop(0)

    fits = iter(
        (
            sc.OLSResult("RANK_DEFICIENT", None, None, None),
            sc.OLSResult("OK", 0.0, 0.0, 2.0),
        )
    )

    def fit(sampled):
        populations.append([row.window.record_identity for row in sampled])
        return next(fits)

    monkeypatch.setattr(sc.random, "Random", ScriptedRandom)
    monkeypatch.setattr(sc, "encompassing_ols", fit)
    result = sc.bootstrap_enc_b(rows, required=1, max_attempts=2)
    assert seeds == [0]
    assert scripts == []
    assert populations == [
        [
            rows[2].window.record_identity,
            rows[3].window.record_identity,
            rows[0].window.record_identity,
            rows[1].window.record_identity,
        ],
        [
            rows[0].window.record_identity,
            rows[1].window.record_identity,
            rows[0].window.record_identity,
            rows[1].window.record_identity,
        ],
    ]
    assert result == sc.BootstrapResult(
        attempted=2,
        valid=1,
        invalid=1,
        ci_0999=(2.0, 2.0),
        ci_095=(2.0, 2.0),
        exhausted=False,
    )


# ---------------------------------------------------------------------------
# Readiness and classification precedence


def test_readiness_counts_apply_all_six_independent_minima():
    population = _population(_ready_windows())
    counts = sc.readiness_counts(population)
    assert counts.n_regression_windows == 120
    assert counts.n_unconditional_gate_windows == 119
    assert counts.n_seasonal_gate_windows == 119
    assert counts.n_regression_sessions >= 10
    assert counts.n_unconditional_gate_sessions >= 10
    assert counts.all_minima_pass is True
    public = counts.public(require_ready=True)
    assert public["all_minima_pass"] is True
    failing = replace(counts, n_seasonal_gate_windows=99)
    assert failing.all_minima_pass is False
    with pytest.raises(sc.ProtocolDefect, match="failing count"):
        failing.public(require_ready=True)


def test_manifest_readiness_rejects_wrong_cell_order_or_identity():
    counts = [
        sc.ReadinessCounts(spec, 100, 10, 100, 10, 100, 10)
        for spec in sc.manifest_cells("v1b-early-4")
    ]
    assert sc.manifest_is_ready("v1b-early-4", counts) is True
    with pytest.raises(sc.ProtocolDefect, match="identity/order"):
        sc.manifest_is_ready("v1b-early-4", list(reversed(counts)))


def test_insufficient_classification_runs_no_bootstrap_and_lists_all_failed_minima():
    cell = sc.evaluate_cell(_population([_window(index) for index in range(21)]))
    assert cell["classification"] == "INSUFFICIENT"
    assert cell["bootstrap_attempted_draws"] == 0
    assert cell["unconditional_bootstrap_attempted_draws"] == 0
    assert cell["seasonal_bootstrap_attempted_draws"] == 0
    assert cell["gate_unconditional"] in {"UNAVAILABLE", "NOT_RUN"}
    assert cell["reason_codes"] == sorted(set(cell["reason_codes"]))
    assert "INSUFFICIENT_REGRESSION_WINDOWS" in cell["reason_codes"]


def test_protocol_defect_precedes_minimum_and_suppresses_all_analytics():
    cell = sc.evaluate_cell(_population([], protocol_defect=True))
    assert cell["classification"] == "INVALID"
    assert cell["reason_codes"] == ["CELL_PROTOCOL_DEFECT"]
    for field in sc._ANALYTIC_FIELDS:
        assert cell[field] is None
    assert cell["bootstrap_attempted_draws"] == 0


def test_preinspection_defect_has_its_exact_specific_reason():
    cell = sc.evaluate_cell(
        _population([]), preinspected_confirmatory_statistic=True
    )
    assert cell["classification"] == "INVALID"
    assert cell["reason_codes"] == ["PREINSPECTED_CONFIRMATORY_STATISTIC"]


def test_informative_and_noise_require_all_three_completed_inferences(monkeypatch):
    population = _population(_ready_windows())
    monkeypatch.setattr(
        sc,
        "encompassing_ols",
        lambda rows: sc.OLSResult("OK", 0.0, 0.2, 0.8),
    )
    completed = iter(
        [
            sc.BootstrapResult(200_000, 200_000, 0, (0.1, 1.0), (0.2, 0.9), False),
            sc.BootstrapResult(200_000, 200_000, 0, (0.01, 0.5), (0.02, 0.4), False),
            sc.BootstrapResult(200_000, 200_000, 0, (0.03, 0.6), (0.04, 0.5), False),
        ]
    )
    monkeypatch.setattr(sc, "bootstrap_enc_b", lambda rows: next(completed))
    monkeypatch.setattr(
        sc, "bootstrap_gate_mean", lambda rows, differences: next(completed)
    )
    informative = sc.evaluate_cell(population)
    assert informative["classification"] == "INFORMATIVE"
    assert informative["reason_codes"] == []
    assert informative["gate_unconditional"] == "PASS"
    assert informative["gate_seasonal"] == "PASS"

    completed = iter(
        [
            sc.BootstrapResult(200_000, 200_000, 0, (0.0, 1.0), (0.0, 0.9), False),
            sc.BootstrapResult(200_000, 200_000, 0, (-0.01, 0.5), (-0.02, 0.4), False),
            sc.BootstrapResult(200_000, 200_000, 0, (0.03, 0.6), (0.04, 0.5), False),
        ]
    )
    noise = sc.evaluate_cell(population)
    assert noise["classification"] == "NOISE"
    assert noise["reason_codes"] == [
        "ENC_B_NOT_POSITIVE",
        "FAILED_UNCONDITIONAL_GATE",
    ]


def test_first_bootstrap_exhaustion_stops_later_bootstraps_and_masks_analytics(monkeypatch):
    population = _population(_ready_windows())
    monkeypatch.setattr(
        sc,
        "encompassing_ols",
        lambda rows: sc.OLSResult("OK", 0.0, 0.2, 0.8),
    )
    exhausted = sc.BootstrapResult(1_000_000, 199_999, 800_001, None, None, True)
    monkeypatch.setattr(sc, "bootstrap_enc_b", lambda rows: exhausted)
    called = []
    monkeypatch.setattr(
        sc,
        "bootstrap_gate_mean",
        lambda *args, **kwargs: called.append(True),
    )
    cell = sc.evaluate_cell(population)
    assert called == []
    assert cell["classification"] == "INVALID"
    assert cell["reason_codes"] == ["ENC_B_BOOTSTRAP_EXHAUSTED"]
    assert cell["bootstrap_attempted_draws"] == 1_000_000
    assert cell["bootstrap_valid_draws"] == 199_999
    assert cell["bootstrap_invalid_draws"] == 800_001
    for field in sc._ANALYTIC_FIELDS:
        assert cell[field] is None


@pytest.mark.parametrize(
    ("cells", "run_defect", "expected"),
    [
        ([{"classification": "INFORMATIVE"}], False, ("PASS", [])),
        ([{"classification": "NOISE"}], False, ("FAIL", ["NO_INFORMATIVE_CELL"])),
        ([{"classification": "INSUFFICIENT"}], False, ("FAIL", ["NO_INFORMATIVE_CELL"])),
        ([{"classification": "INVALID"}], False, ("INVALID", ["INVALID_CELL_PRESENT"])),
        ([{"classification": "INVALID"}], True, ("INVALID", ["INVALID_CELL_PRESENT", "RUN_PROTOCOL_DEFECT"])),
    ],
)
def test_manifest_overall_verdict_precedence(cells, run_defect, expected):
    assert sc.overall_verdict(cells, run_protocol_defect=run_defect) == expected


# ---------------------------------------------------------------------------
# Amendment 3 startup isolation and invocation-bound runtime bytes


def _startup_observation(
    *,
    mode: str = "normal",
    manifest_id: str = "v1b-early-4",
    recovery_hash: str = "a" * 64,
    environment: tuple[tuple[str, str], ...] | None = None,
) -> sc.StartupObservation:
    base = "/opt/python"
    stdlib = f"{base}/lib/python3.14"
    dynload = f"{stdlib}/lib-dynload"
    repository = "/srv/atom"
    site_packages = f"{base}/lib/python3.14/site-packages"
    executable = f"{base}/bin/python3.14"
    appended = (repository, site_packages)
    if mode == "probe":
        words = ("python", *sc.ISOLATED_PYTHON_ARGS, "-c", sc.PROBE_C_BODY)
    elif mode == "normal":
        words = (
            "python",
            *sc.ISOLATED_PYTHON_ARGS,
            "-c",
            sc.NORMAL_C_BODY,
            "--manifest-id",
            manifest_id,
        )
    else:
        words = (
            executable,
            *sc.ISOLATED_PYTHON_ARGS,
            "-c",
            sc.NORMAL_C_BODY,
            "--manifest-id",
            manifest_id,
            "--recovery-seal-file",
            f"/tmp/atom-v1b-seals/{recovery_hash}.json",
        )
    return sc.StartupObservation(
        version=(3, 14, 3),
        isolated=1,
        ignore_environment=1,
        no_user_site=1,
        no_site=1,
        safe_path=True,
        dont_write_bytecode=True,
        pycache_prefix="/dev/null/atom-v1b-no-pyc",
        base_prefix=base,
        base_exec_prefix=base,
        platlibdir="lib",
        cwd=repository,
        stdlib=stdlib,
        platstdlib=stdlib,
        purelib=site_packages,
        platlib=site_packages,
        sys_path=(stdlib, dynload, *appended),
        environment=(
            (("PYTHON_VERSION", "3.14.3"),)
            if environment is None
            else environment
        ),
        loaded_modules=frozenset({"sys", "os", "quant", "quant.volatility_scorecard"}),
        sys_origin="built-in",
        os_origin="frozen",
        os_path_origin="frozen",
        quant_package="quant",
        quant_origin=None,
        quant_file=None,
        quant_search_locations=(f"{repository}/quant",),
        executable=executable,
        which_python=executable,
        proc_self_exe=executable,
        proc_cmdline=words,
        q_lexists=False,
        u_is_dir=True,
        t_is_dir=True,
        y_is_dir=True,
        cwd_is_dir=True,
        quant_dir_is_dir=True,
        module_is_regular=True,
        executable_is_regular=True,
        executable_is_executable=True,
        devnull_is_char=True,
        ld_preload_lexists=False,
        purelib_is_dir=True,
        platlib_is_dir=True,
        quant_path=(f"{repository}/quant",),
        quant_loader_type="_frozen_importlib_external.NamespaceLoader",
        quant_loader_matches_spec=True,
        scorecard_package="quant",
        scorecard_spec_name="quant.volatility_scorecard",
        scorecard_origin=f"{repository}/quant/volatility_scorecard.py",
        scorecard_file=f"{repository}/quant/volatility_scorecard.py",
        scorecard_loader_type="_frozen_importlib_external.SourceFileLoader",
        scorecard_loader_name="quant.volatility_scorecard",
        scorecard_loader_path=f"{repository}/quant/volatility_scorecard.py",
        scorecard_loader_matches_spec=True,
        meta_path_types=(
            "_frozen_importlib.BuiltinImporter",
            "_frozen_importlib.FrozenImporter",
            "_frozen_importlib_external.PathFinder",
        ),
    )


def test_frozen_commands_have_all_isolation_flags_and_exact_embedded_child():
    sc.validate_command_constants()
    hook_source = "import sys;sys.excepthook=sys.unraisablehook=lambda *_:None;"
    assert len(hook_source.encode("ascii")) == 60
    assert sc.ISOLATED_PYTHON_ARGS == (
        "-I",
        "-S",
        "-B",
        "-X",
        "pycache_prefix=/dev/null/atom-v1b-no-pyc",
    )
    probe_words = shlex.split(sc.PROBE_START_COMMAND, posix=True)
    normal_words = shlex.split(sc.NORMAL_START_COMMAND_BOOTSTRAP, posix=True)
    recovery_words = shlex.split(sc.RECOVERY_START_COMMAND_TEMPLATE, posix=True)
    assert tuple(probe_words[:7]) == ("python", *sc.ISOLATED_PYTHON_ARGS, "-c")
    assert tuple(normal_words[:7]) == ("python", *sc.ISOLATED_PYTHON_ARGS, "-c")
    decoded = bytes.fromhex(sc.RECOVERY_CHILD_C_HEX)
    assert decoded == sc.NORMAL_C_BODY.encode("ascii")
    assert len(decoded) == sc.RECOVERY_CHILD_C_LEN == 3092
    assert len(sc.RECOVERY_CHILD_C_HEX) == sc.RECOVERY_CHILD_HEX_LEN == 6184
    assert sc.RECOVERY_CHILD_C_SHA256 == (
        "f79378de92204cfec2fe4818c341cc23b5dfb685179f05e5722441ce9a608d62"
    )
    assert hashlib.sha256(decoded).hexdigest() == (
        "f79378de92204cfec2fe4818c341cc23b5dfb685179f05e5722441ce9a608d62"
    )
    assert len(sc.PROBE_C_BODY.encode("ascii")) == 3100
    assert hashlib.sha256(sc.PROBE_C_BODY.encode("ascii")).hexdigest() == (
        "e4907f41ac3c60efdfe7874677d0214ccca0eab9f0ab6d56820b47633eefc143"
    )
    for body in (
        sc.PROBE_C_BODY,
        sc.NORMAL_C_BODY,
        recovery_words[7],
        decoded.decode("ascii"),
    ):
        assert body.startswith(hook_source)
        assert body.count(hook_source) == 1

    fake_sys = SimpleNamespace(excepthook=object(), unraisablehook=object())

    def only_sys_import(name, *args, **kwargs):
        assert name == "sys"
        return fake_sys

    exec(hook_source, {"__builtins__": {"__import__": only_sys_import}})
    assert fake_sys.excepthook is fake_sys.unraisablehook
    assert fake_sys.excepthook() is None
    assert fake_sys.excepthook(object(), object(), object()) is None


@pytest.mark.parametrize(
    "failure_source",
    (
        "raise OSError('synthetic bootstrap open')",
        "{}['missing']",
        "import os;os.stat('/atom-v1b-synthetic-missing')",
        "import sysconfig;sysconfig.get_paths(scheme='atom-v1b-missing')",
        "(_ for _ in ()).throw(RuntimeError('synthetic predicate refusal'))",
    ),
)
def test_installed_startup_hooks_make_representative_bootstrap_failures_silent(
    failure_source,
):
    hook_source = "import sys;sys.excepthook=sys.unraisablehook=lambda *_:None;"
    source = (
        hook_source
        + "assert sys.excepthook is sys.unraisablehook;"
        + failure_source
    )
    completed = sc.subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", source],
        stdin=sc.subprocess.DEVNULL,
        stdout=sc.subprocess.PIPE,
        stderr=sc.subprocess.PIPE,
        env={},
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr == b""


@pytest.mark.parametrize("mode", ["probe", "normal", "recovery"])
def test_startup_validator_accepts_only_exact_mode_specific_command(mode):
    observation = _startup_observation(mode=mode)
    kwargs = {"mode": mode}
    if mode != "probe":
        kwargs["manifest_id"] = "v1b-early-4"
    if mode == "recovery":
        kwargs["recovery_seal_path"] = f"/tmp/atom-v1b-seals/{'a' * 64}.json"
    sc.validate_startup_observation(observation, **kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", (3, 14, 2)),
        ("isolated", 0),
        ("ignore_environment", 0),
        ("no_user_site", 0),
        ("no_site", 0),
        ("safe_path", False),
        ("dont_write_bytecode", False),
        ("pycache_prefix", None),
        ("sys_origin", "python"),
        ("os_origin", "python"),
        ("os_path_origin", "python"),
        ("excepthook", object()),
        ("unraisablehook", object()),
    ],
)
def test_startup_validator_rejects_each_missing_interpreter_guard(field, value):
    observation = replace(_startup_observation(), **{field: value})
    with pytest.raises(sc.StartupIsolationError, match="STARTUP_FLAGS_INVALID"):
        sc.validate_startup_observation(
            observation, mode="normal", manifest_id="v1b-early-4"
        )


@pytest.mark.parametrize(
    "key",
    [
        "PYTHONPATH",
        "PYTHONHOME",
        "_PYTHON_SYSCONFIGDATA_NAME",
        "LD_PRELOAD",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "BASH_ENV",
        "GIT_CONFIG_COUNT",
        "OPENSSL_CONF",
        "ENV",
        "SHELLOPTS",
        "PS4",
        "KSHENV",
        "ZDOTDIR",
        "GCONV_PATH",
        "GLIBC_TUNABLES",
        "HTTPS_PROXY",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSLKEYLOGFILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    ],
)
def test_startup_validator_rejects_every_injection_family_even_when_empty(key):
    observation = _startup_observation(
        environment=(("PYTHON_VERSION", "3.14.3"), (key, ""))
    )
    with pytest.raises(sc.StartupIsolationError, match="STARTUP_ENVIRONMENT_INVALID"):
        sc.validate_startup_observation(
            observation, mode="normal", manifest_id="v1b-early-4"
        )


@pytest.mark.parametrize("secret", [sc.READONLY_URL_ENV, sc.GITHUB_TOKEN_ENV])
def test_probe_rejects_runtime_secret_key_presence_even_when_empty(secret):
    observation = _startup_observation(
        mode="probe",
        environment=(("PYTHON_VERSION", "3.14.3"), (secret, "")),
    )
    with pytest.raises(sc.StartupIsolationError, match="STARTUP_SECRET_PRESENT"):
        sc.validate_startup_observation(observation, mode="probe")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("q_lexists", True),
        ("ld_preload_lexists", True),
        ("which_python", "/opt/other/python"),
        ("quant_origin", "/srv/atom/quant/__init__.py"),
        ("quant_file", "/srv/atom/quant/__init__.py"),
        ("loaded_modules", frozenset({"sys", "quant", "sitecustomize"})),
        ("sys_path", ("/attacker",)),
        ("purelib_is_dir", False),
        ("platlib_is_dir", False),
        ("quant_path", ("/attacker/quant",)),
        ("quant_loader_type", "attacker.Loader"),
        ("quant_loader_matches_spec", False),
        ("scorecard_package", "attacker"),
        ("scorecard_spec_name", "attacker.volatility_scorecard"),
        ("scorecard_origin", "/attacker/volatility_scorecard.py"),
        ("scorecard_file", "/attacker/volatility_scorecard.py"),
        ("scorecard_loader_type", "attacker.Loader"),
        ("scorecard_loader_name", "attacker.volatility_scorecard"),
        ("scorecard_loader_path", "/attacker/volatility_scorecard.py"),
        ("scorecard_loader_matches_spec", False),
        ("meta_path_types", ("attacker.Finder",)),
    ],
)
def test_startup_validator_rejects_archive_preload_customization_and_path_drift(
    field, value
):
    observation = replace(_startup_observation(), **{field: value})
    with pytest.raises(sc.StartupIsolationError, match="STARTUP_STATE_INVALID"):
        sc.validate_startup_observation(
            observation, mode="normal", manifest_id="v1b-early-4"
        )


def test_startup_validator_rejects_extra_cli_option_and_wrong_manifest():
    observation = _startup_observation()
    extra = replace(observation, proc_cmdline=observation.proc_cmdline + ("--force",))
    with pytest.raises(sc.StartupIsolationError, match="STARTUP_CMDLINE_INVALID"):
        sc.validate_startup_observation(
            extra, mode="normal", manifest_id="v1b-early-4"
        )
    with pytest.raises(sc.StartupIsolationError, match="STARTUP_CMDLINE_INVALID"):
        sc.validate_startup_observation(
            observation, mode="normal", manifest_id="not-a-manifest"
        )


def test_startup_validator_does_not_replace_an_explicitly_empty_environment():
    observation = _startup_observation(environment=())
    assert observation.environment == ()
    with pytest.raises(
        sc.StartupIsolationError, match="STARTUP_ENVIRONMENT_INVALID"
    ):
        sc.validate_startup_observation(
            observation, mode="normal", manifest_id="v1b-early-4"
        )


def test_live_startup_guard_reads_only_environment_keys_and_python_version(
    monkeypatch,
):
    """Neither runtime credential value may be copied before startup passes."""

    value_reads = []

    class GuardedEnvironment(dict):
        def items(self):
            raise AssertionError("startup guard must never materialize environment values")

        def __getitem__(self, key):
            value_reads.append(key)
            if key in {sc.GITHUB_TOKEN_ENV, sc.READONLY_URL_ENV}:
                raise AssertionError("runtime secret value read before startup validation")
            return super().__getitem__(key)

        def get(self, key, default=None):
            value_reads.append(key)
            if key in {sc.GITHUB_TOKEN_ENV, sc.READONLY_URL_ENV}:
                raise AssertionError("runtime secret value read before startup validation")
            return super().get(key, default)

    guarded = GuardedEnvironment(
        {
            "PYTHON_VERSION": "3.14.3",
            sc.GITHUB_TOKEN_ENV: "synthetic-never-readable-token",
            sc.READONLY_URL_ENV: "synthetic-never-readable-uri",
        }
    )
    monkeypatch.setattr(sc.os, "environ", guarded)
    monkeypatch.setattr(
        __import__("shutil"), "which", lambda executable: sc.sys.executable
    )
    observation = sc.observe_live_startup()
    assert observation is not None
    assert "PYTHON_VERSION" in value_reads
    assert sc.GITHUB_TOKEN_ENV not in value_reads
    assert sc.READONLY_URL_ENV not in value_reads


class _ByteAccess:
    def __init__(self, values: dict[str, bytes]):
        self.values = values

    def record(self, candidate):
        try:
            value = self.values[candidate.logical_path]
        except KeyError as error:
            raise sc.ArtifactError("TEST_ARTIFACT_MISSING") from error
        return sc.FileRecord(
            candidate.logical_path, len(value), hashlib.sha256(value).hexdigest()
        )


def _artifact_plan() -> tuple[sc.RuntimeArtifactPlan, _ByteAccess]:
    roots = sc.RuntimeRoots(
        python_executable="/runtime/python",
        stdlib="/runtime/stdlib",
        platstdlib="/runtime/stdlib",
        purelib="/runtime/site",
        platlib="/runtime/site",
    )
    stdlib = (
        sc.FileCandidate("stdlib/z.py", "/runtime/stdlib/z.py"),
        sc.FileCandidate("stdlib/a.py", "/runtime/stdlib/a.py"),
    )
    dependency = (sc.FileCandidate("package/mod.py", "/runtime/site/mod.py"),)
    native = (sc.FileCandidate("/runtime/libm.so.6", "/runtime/libm.so.6"),)
    mappings = (
        sc.ProcMapEntry(0x1000, 0x2000, "r-xp", 0x200, "/runtime/libm.so.6"),
    )
    values = {
        "/runtime/python": b"python",
        "stdlib/z.py": b"z",
        "stdlib/a.py": b"a",
        "package/mod.py": b"dependency",
        "/runtime/libm.so.6": b"libm",
    }
    return (
        sc.RuntimeArtifactPlan(
            roots=roots,
            dependency_versions=(("package", "1.0"),),
            stdlib_files=stdlib,
            dependency_files=dependency,
            native_files=native,
            mappings=mappings,
            module_names=frozenset({"quant.volatility_scorecard", "package"}),
        ),
        _ByteAccess(values),
    )


def test_proc_maps_parser_and_aslr_neutral_libm_offsets():
    raw = (
        b"1000-2000 r-xp 00000200 08:01 1 /runtime/libm.so.6\n"
        b"3000-4000 r--p 00000000 00:00 0 [vvar]\n"
    )
    parsed = sc.parse_proc_maps(raw)
    assert parsed[0] == sc.ProcMapEntry(
        0x1000, 0x2000, "r-xp", 0x200, "/runtime/libm.so.6"
    )
    addresses = {b"exp": 0x1100, b"log": 0x1200}
    dispatch = sc.resolve_libm_dispatch(
        parsed,
        {"/runtime/libm.so.6"},
        symbol_resolver=lambda symbol: addresses[symbol],
    )
    assert dispatch == {
        "exp": {
            "loaded_native_path": "/runtime/libm.so.6",
            "file_offset": 0x300,
        },
        "log": {
            "loaded_native_path": "/runtime/libm.so.6",
            "file_offset": 0x400,
        },
    }
    with pytest.raises(sc.ArtifactError, match="PROC_MAPS_INVALID"):
        sc.parse_proc_maps(b"not-a-map\n")


def _required_native_paths(tmp_path):
    root = tmp_path.resolve()
    return (
        str(root / "bin/python3.14"),
        str(root / "lib/libpython3.14.so.1.0"),
        str(root / "lib/ld-linux-x86-64.so.2"),
        str(root / "lib/libc.so.6"),
        str(root / "lib/libm.so.6"),
        str(root / "lib-dynload/math.cpython-314-x86_64-linux-gnu.so"),
        str(root / "lib-dynload/_random.cpython-314-x86_64-linux-gnu.so"),
        str(root / "lib-dynload/_json.cpython-314-x86_64-linux-gnu.so"),
        str(root / "psycopg-binary.libs/libpq-a1b2.so.5.18"),
        str(root / "psycopg-binary.libs/libssl-c3d4.so.3"),
        str(root / "psycopg-binary.libs/libcrypto-e5f6.so.3"),
    )


def test_required_native_members_are_explicitly_classified_before_plan_acceptance(
    tmp_path,
):
    paths = _required_native_paths(tmp_path)
    classified = sc.classify_required_native_members(
        paths, python_executable=paths[0]
    )
    assert tuple(classified) == (
        "cpython_or_libpython",
        "dynamic_loader",
        "libc",
        "libm",
        "math",
        "_random",
        "_json",
        "libpq",
        "libssl",
        "libcrypto",
    )
    assert classified["cpython_or_libpython"] == paths[:2]
    assert classified["dynamic_loader"] == (paths[2],)
    assert classified["libc"] == (paths[3],)
    assert classified["libm"] == (paths[4],)
    assert classified["math"] == (paths[5],)
    assert classified["_random"] == (paths[6],)
    assert classified["_json"] == (paths[7],)
    assert classified["libpq"] == (paths[8],)
    assert classified["libssl"] == (paths[9],)
    assert classified["libcrypto"] == (paths[10],)


@pytest.mark.parametrize(
    ("member", "removed", "reason"),
    (
        ("cpython/libpython", (0, 1), "NATIVE_REQUIRED_CPYTHON_MISSING"),
        ("dynamic loader", (2,), "NATIVE_REQUIRED_DYNAMIC_LOADER_MISSING"),
        ("libc", (3,), "NATIVE_REQUIRED_LIBC_MISSING"),
        ("libm", (4,), "NATIVE_REQUIRED_LIBM_MISSING"),
        ("math", (5,), "NATIVE_REQUIRED_MATH_MISSING"),
        ("_random", (6,), "NATIVE_REQUIRED__RANDOM_MISSING"),
        ("_json", (7,), "NATIVE_REQUIRED__JSON_MISSING"),
        ("libpq", (8,), "NATIVE_REQUIRED_LIBPQ_MISSING"),
        ("libssl", (9,), "NATIVE_REQUIRED_LIBSSL_MISSING"),
        ("libcrypto", (10,), "NATIVE_REQUIRED_LIBCRYPTO_MISSING"),
    ),
)
def test_each_frozen_required_native_member_is_independently_mandatory(
    member, removed, reason, tmp_path
):
    paths = _required_native_paths(tmp_path)
    observed = tuple(path for index, path in enumerate(paths) if index not in removed)
    with pytest.raises(sc.ArtifactError, match=reason):
        sc.classify_required_native_members(
            observed,
            python_executable=paths[0],
        )


@pytest.mark.parametrize("suffix", (".pyc", ".pyo"))
@pytest.mark.parametrize(
    "loader_type",
    (
        importlib.machinery.SourcelessFileLoader,
        importlib.machinery.SourceFileLoader,
    ),
    ids=("sourceless-loader", "direct-bytecode-origin"),
)
def test_loaded_sourceless_or_direct_bytecode_origin_is_forbidden(
    suffix, loader_type, tmp_path, monkeypatch
):
    name = f"synthetic_bytecode_{suffix[1:]}_{loader_type.__name__}"
    origin = str((tmp_path / f"module{suffix}").resolve())
    loader = loader_type(name, origin)
    spec = importlib.util.spec_from_loader(name, loader, origin=origin)
    assert spec is not None
    module = SimpleNamespace(__spec__=spec, __file__=origin)
    monkeypatch.setitem(sys.modules, name, module)
    with pytest.raises(sc.ArtifactError, match="LOADED_BYTECODE_FORBIDDEN"):
        sc.validate_loaded_module_sources(
            (name,),
            covered_source_paths=(),
            covered_native_paths=(),
            namespace_roots=(str(tmp_path.resolve()),),
        )


def test_runtime_tree_walk_fails_closed_on_unreadable_subtree(
    tmp_path, monkeypatch
):
    calls = []

    def unreadable_walk(root, *, followlinks, onerror):
        calls.append((root, followlinks, onerror))
        onerror(PermissionError("synthetic unreadable subtree"))
        raise AssertionError("onerror must terminate traversal")

    monkeypatch.setattr(sc.os, "walk", unreadable_walk)
    root = str(tmp_path.resolve())
    with pytest.raises(sc.ArtifactError, match="ARTIFACT_TREE_UNREADABLE"):
        sc._walk_regular_candidates(root)
    assert len(calls) == 1
    assert calls[0][0] == root
    assert calls[0][1] is False
    assert callable(calls[0][2])


def test_runtime_tree_walk_stops_at_shared_deadline_equality(tmp_path):
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("pass\n", encoding="utf-8")
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    checks = 0

    def expire_during_walk():
        nonlocal checks
        checks += 1
        if checks == 5:
            clock.value = context.checkpoint_end_ns
        context.check(clock)

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._walk_regular_candidates(
            str(tmp_path.resolve()), check=expire_during_walk
        )
    assert checks == 5


@pytest.mark.parametrize(
    "phase", ("walk_create", "iterator_create", "iterator_next", "dir_sort", "file_sort")
)
def test_runtime_tree_walk_brackets_creation_advancement_and_sorts(
    phase, tmp_path, monkeypatch
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    triggered = []

    class Walker:
        def __iter__(self):
            if phase == "iterator_create":
                triggered.append(phase)
                clock.value = context.checkpoint_end_ns
            return self

        def __next__(self):
            if getattr(self, "done", False):
                raise StopIteration
            self.done = True
            if phase == "iterator_next":
                triggered.append(phase)
                clock.value = context.checkpoint_end_ns
            return str(tmp_path.resolve()), [], []

    def walk(root, *, followlinks, onerror):
        assert root == str(tmp_path.resolve())
        assert followlinks is False
        assert callable(onerror)
        if phase == "walk_create":
            triggered.append(phase)
            clock.value = context.checkpoint_end_ns
        return Walker()

    monkeypatch.setattr(sc.os, "walk", walk)
    original_call = sc._cooperative_call
    sort_calls = 0

    def intercept(check, operation, /, *args, **kwargs):
        nonlocal sort_calls
        if operation is sorted:
            sort_calls += 1
            target_call = 1 if phase == "dir_sort" else 2
            if phase in {"dir_sort", "file_sort"} and sort_calls == target_call:
                triggered.append(phase)
                selected_operation = operation

                def late_sort(*inner_args, **inner_kwargs):
                    result = selected_operation(*inner_args, **inner_kwargs)
                    clock.value = context.checkpoint_end_ns
                    return result

                operation = late_sort
        return original_call(check, operation, *args, **kwargs)

    monkeypatch.setattr(sc, "_cooperative_call", intercept)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._walk_regular_candidates(
            str(tmp_path.resolve()), check=context.checker(clock)
        )
    assert triggered == [phase]


def test_canonical_regular_artifact_path_is_accepted(tmp_path):
    path = tmp_path / "listed.py"
    path.write_text("pass\n", encoding="utf-8")
    observed = sc._validate_canonical_regular_path(str(path.resolve()))
    assert observed.st_ino == path.stat().st_ino
    assert observed.st_size == len(b"pass\n")


@pytest.mark.parametrize("phase", ("realpath", "lstat"))
def test_canonical_regular_path_discards_late_path_observation(
    phase, tmp_path, monkeypatch
):
    path = tmp_path / "listed.py"
    path.write_text("pass\n", encoding="utf-8")
    real = str(path.resolve())
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    original_realpath = sc.os.path.realpath
    original_lstat = sc.os.lstat

    def delayed_realpath(value):
        result = original_realpath(value)
        if phase == "realpath":
            clock.value = context.checkpoint_end_ns
        return result

    def delayed_lstat(value):
        result = original_lstat(value)
        if phase == "lstat":
            clock.value = context.checkpoint_end_ns
        return result

    monkeypatch.setattr(sc.os.path, "realpath", delayed_realpath)
    monkeypatch.setattr(sc.os, "lstat", delayed_lstat)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._validate_canonical_regular_path(
            real, check=context.checker(clock)
        )


def _synthetic_install_scheme(tmp_path):
    prefix = tmp_path / "prefix"
    stdlib = prefix / "lib" / "python3.14"
    purelib = stdlib / "site-packages"
    paths = {
        "stdlib": str(stdlib),
        "platstdlib": str(stdlib),
        "purelib": str(purelib),
        "platlib": str(purelib),
        "scripts": str(prefix / "bin"),
        "data": str(prefix),
        "include": str(prefix / "include" / "python3.14"),
        "platinclude": str(prefix / "include" / "python3.14"),
    }
    for value in set(paths.values()):
        Path(value).mkdir(parents=True, exist_ok=True)
    return paths


def test_install_scheme_roots_are_the_exact_canonical_deduplicated_set(tmp_path):
    paths = _synthetic_install_scheme(tmp_path)
    observed = sc._collect_install_scheme_roots(paths)
    expected = tuple(
        sorted(
            {paths[name] for name in sc.INSTALL_SCHEME_ROOT_NAMES},
            key=lambda item: (-len(Path(item).parts), item),
        )
    )
    assert sc.INSTALL_SCHEME_ROOT_NAMES == (
        "purelib",
        "platlib",
        "scripts",
        "data",
        "include",
        "platinclude",
    )
    assert observed == expected


def test_record_console_script_leading_parent_run_is_authenticated_not_opened(
    tmp_path,
):
    paths = _synthetic_install_scheme(tmp_path)
    base = Path(paths["purelib"])
    script = Path(paths["scripts"]) / "synthetic-cli"
    script.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    record_spelling = "../../../bin/synthetic-cli"

    class Distribution:
        def locate_file(self, package_path):
            return base if str(package_path) == "" else script

    candidate = sc._resolve_distribution_record_member(
        Distribution(),
        "synthetic",
        record_spelling,
        sc._collect_install_scheme_roots(paths),
    )
    assert candidate == sc.FileCandidate(
        "synthetic/../../../bin/synthetic-cli",
        str(script.resolve()),
    )
    assert ".." not in Path(candidate.real_path).parts


@pytest.mark.parametrize(
    ("record_spelling", "target_kind", "reason"),
    (
        ("../../bin/synthetic-cli", "script", "DEPENDENCY_PATH_NONCANONICAL"),
        (
            "../../../bin/../bin/synthetic-cli",
            "script",
            "DEPENDENCY_PATH_INVALID",
        ),
        ("../../../../outside", "outside", "DEPENDENCY_PATH_OUTSIDE_SCHEME"),
        ("../../../bin/synthetic-cli", "symlink", "DEPENDENCY_PATH_INVALID"),
    ),
)
def test_record_parent_escape_never_selects_alias_symlink_or_unapproved_root(
    record_spelling, target_kind, reason, tmp_path
):
    paths = _synthetic_install_scheme(tmp_path)
    base = Path(paths["purelib"])
    script = Path(paths["scripts"]) / "synthetic-cli"
    target = script
    if target_kind == "outside":
        target = tmp_path / "outside"
        target.write_text("outside\n", encoding="utf-8")
    elif target_kind == "symlink":
        real = Path(paths["scripts"]) / "real-cli"
        real.write_text("real\n", encoding="utf-8")
        script.symlink_to(real)
    else:
        script.write_text("script\n", encoding="utf-8")

    class Distribution:
        def locate_file(self, package_path):
            return base if str(package_path) == "" else target

    with pytest.raises(sc.ArtifactError, match=reason):
        sc._resolve_distribution_record_member(
            Distribution(),
            "synthetic",
            record_spelling,
            sc._collect_install_scheme_roots(paths),
        )


def test_governed_tzdata_members_are_exactly_new_york_and_utc():
    assert sc.GOVERNED_DEPENDENCY_DATA_PATHS == {
        "tzdata": (
            "tzdata/zoneinfo/America/New_York",
            "tzdata/zoneinfo/UTC",
        )
    }


@pytest.mark.parametrize(
    "omitted",
    (
        "tzdata/zoneinfo/America/New_York",
        "tzdata/zoneinfo/UTC",
    ),
)
def test_each_governed_tzdata_record_member_is_independently_required(
    omitted, tmp_path, monkeypatch
):
    paths = _synthetic_install_scheme(tmp_path)
    base = Path(paths["purelib"])
    governed = sc.GOVERNED_DEPENDENCY_DATA_PATHS["tzdata"]
    present = tuple(item for item in governed if item != omitted)
    for item in present:
        target = base / item
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"TZif synthetic fixture")

    class Distribution:
        metadata = {"Name": "tzdata"}
        version = "2025.3"
        files = present

        def locate_file(self, package_path):
            return base if str(package_path) == "" else base / str(package_path)

    monkeypatch.setattr(sc.sysconfig, "get_preferred_scheme", lambda kind: "prefix")
    monkeypatch.setattr(sc.sysconfig, "get_paths", lambda scheme: paths)
    monkeypatch.setattr(sc, "_walk_regular_candidates", lambda *args, **kwargs: ())
    monkeypatch.setattr(
        sc.importlib.metadata,
        "distribution",
        lambda name: Distribution(),
    )
    with pytest.raises(sc.ArtifactError, match="GOVERNED_DEPENDENCY_DATA_MISSING"):
        sc.collect_runtime_artifact_plan(
            {"tzdata": "2025.3"}, module_names=frozenset()
        )


@pytest.mark.parametrize("listed_form", ("symlink", "noncanonical_record"))
def test_dependency_metadata_listed_path_cannot_hide_symlink_or_alias(
    listed_form, tmp_path, monkeypatch
):
    roots = _synthetic_install_scheme(tmp_path)
    base = Path(roots["purelib"])
    package = base / "package"
    package.mkdir()
    target = package / "target.py"
    target.write_text("pass\n", encoding="utf-8")
    if listed_form == "symlink":
        listed = package / "listed.py"
        listed.symlink_to(target)
        listed_path = str(listed)
        record_path = "package/listed.py"
    else:
        listed_path = str(target)
        record_path = "package/./target.py"

    distribution = SimpleNamespace(
        metadata={"Name": "synthetic"},
        version="1.0",
        files=(record_path,),
        locate_file=lambda package_path: (
            str(base) if str(package_path) == "" else listed_path
        ),
    )
    monkeypatch.setattr(sc.sysconfig, "get_preferred_scheme", lambda kind: "prefix")
    monkeypatch.setattr(sc.sysconfig, "get_paths", lambda scheme: roots)
    monkeypatch.setattr(sc, "_walk_regular_candidates", lambda *args, **kwargs: ())
    monkeypatch.setattr(
        sc.importlib.metadata,
        "distribution",
        lambda name: distribution,
    )
    monkeypatch.setattr(sc, "GOVERNED_DEPENDENCY_DATA_PATHS", {})
    with pytest.raises(sc.ArtifactError, match="DEPENDENCY_PATH_INVALID"):
        sc.collect_runtime_artifact_plan(
            {"synthetic": "1.0"}, module_names=frozenset()
        )


def test_dependency_metadata_canonical_regular_candidate_is_preserved(
    tmp_path, monkeypatch
):
    roots = _synthetic_install_scheme(tmp_path)
    base = Path(roots["purelib"])
    listed = base / "package" / "listed.py"
    listed.parent.mkdir()
    listed.write_text("pass\n", encoding="utf-8")
    listed_path = str(listed.resolve())
    distribution = SimpleNamespace(
        metadata={"Name": "synthetic"},
        version="1.0",
        files=(Path("package/listed.py"),),
        locate_file=lambda package_path: (
            str(base) if str(package_path) == "" else listed_path
        ),
    )
    monkeypatch.setattr(sc.sysconfig, "get_preferred_scheme", lambda kind: "prefix")
    monkeypatch.setattr(sc.sysconfig, "get_paths", lambda scheme: roots)
    monkeypatch.setattr(sc, "_walk_regular_candidates", lambda *args, **kwargs: ())
    monkeypatch.setattr(
        sc.importlib.metadata,
        "distribution",
        lambda name: distribution,
    )
    monkeypatch.setattr(sc, "_cooperative_read_bytes", lambda *args, **kwargs: b"")
    monkeypatch.setattr(sc, "parse_proc_maps", lambda *args, **kwargs: ())
    monkeypatch.setattr(sc, "_collect_native_candidates", lambda *args, **kwargs: ())
    monkeypatch.setattr(
        sc, "classify_required_native_members", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(sc, "validate_loaded_module_sources", lambda *args, **kwargs: None)
    monkeypatch.setattr(sc, "GOVERNED_DEPENDENCY_DATA_PATHS", {})
    plan = sc.collect_runtime_artifact_plan(
        {"synthetic": "1.0"}, module_names=frozenset()
    )
    assert plan.dependency_files == (
        sc.FileCandidate("synthetic/package/listed.py", listed_path),
    )


@pytest.mark.parametrize(
    "phase",
    (
        "expected_items",
        "distribution",
        "metadata",
        "metadata_member",
        "version",
        "files",
        "files_iter",
        "files_next",
        "locate_file",
    ),
)
def test_each_dependency_metadata_primitive_is_deadline_bracketed(
    phase, tmp_path, monkeypatch
):
    roots = _synthetic_install_scheme(tmp_path)
    base = Path(roots["purelib"])
    listed = base / "package" / "listed.py"
    listed.parent.mkdir()
    listed.write_text("pass\n", encoding="utf-8")
    listed_path = str(listed.resolve())
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    triggered = []

    def expire(name):
        if phase == name:
            triggered.append(name)
            clock.value = context.checkpoint_end_ns

    class Metadata(dict):
        def __getitem__(self, key):
            value = super().__getitem__(key)
            expire("metadata_member")
            return value

    class Files:
        def __iter__(self):
            expire("files_iter")
            return self

        def __next__(self):
            if getattr(self, "done", False):
                raise StopIteration
            self.done = True
            expire("files_next")
            return Path("package/listed.py")

    class Distribution:
        @property
        def metadata(self):
            value = Metadata(Name="synthetic")
            expire("metadata")
            return value

        @property
        def version(self):
            expire("version")
            return "1.0"

        @property
        def files(self):
            value = Files()
            expire("files")
            return value

        def locate_file(self, package_path):
            expire("locate_file")
            return str(base) if str(package_path) == "" else listed_path

    distribution = Distribution()

    class ExpectedVersions(dict):
        def items(self):
            value = super().items()
            expire("expected_items")
            return value

    def distribution_lookup(name):
        assert name == "synthetic"
        expire("distribution")
        return distribution

    monkeypatch.setattr(sc.sysconfig, "get_preferred_scheme", lambda kind: "prefix")
    monkeypatch.setattr(sc.sysconfig, "get_paths", lambda scheme: roots)
    monkeypatch.setattr(sc, "_walk_regular_candidates", lambda *args, **kwargs: ())
    monkeypatch.setattr(sc.importlib.metadata, "distribution", distribution_lookup)
    monkeypatch.setattr(sc, "_cooperative_read_bytes", lambda *args, **kwargs: b"")
    monkeypatch.setattr(sc, "parse_proc_maps", lambda *args, **kwargs: ())
    monkeypatch.setattr(sc, "_collect_native_candidates", lambda *args, **kwargs: ())
    monkeypatch.setattr(
        sc, "classify_required_native_members", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(sc, "validate_loaded_module_sources", lambda *args, **kwargs: None)
    monkeypatch.setattr(sc, "GOVERNED_DEPENDENCY_DATA_PATHS", {})
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.collect_runtime_artifact_plan(
            ExpectedVersions(synthetic="1.0"),
            module_names=frozenset(),
            check=context.checker(clock),
        )
    assert triggered == [phase]


def test_local_artifact_rejects_lstat_open_identity_change(tmp_path, monkeypatch):
    path = tmp_path / "listed.py"
    path.write_text("pass\n", encoding="utf-8")
    real = str(path.resolve())
    observed = os.lstat(real)
    raced = SimpleNamespace(
        st_dev=observed.st_dev,
        st_ino=observed.st_ino + 1,
        st_mode=observed.st_mode,
        st_size=observed.st_size,
        st_mtime_ns=observed.st_mtime_ns,
        st_ctime_ns=observed.st_ctime_ns,
    )
    monkeypatch.setattr(
        sc,
        "_validate_canonical_regular_path",
        lambda candidate, check=None: raced,
    )
    with pytest.raises(sc.ArtifactError, match="ARTIFACT_CHANGED_DURING_READ"):
        sc.LocalFileAccess().record(sc.FileCandidate(real, real))


def test_local_artifact_reader_rejects_symlink_before_opening_target(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("pass\n", encoding="utf-8")
    link = tmp_path / "listed.py"
    link.symlink_to(target)
    listed = str(link.absolute())
    with pytest.raises(sc.ArtifactError, match="ARTIFACT_PATH_INVALID"):
        sc.LocalFileAccess().record(sc.FileCandidate(listed, listed))


def test_runtime_artifact_hashes_are_sorted_complete_and_approval_bound():
    plan, access = _artifact_plan()
    addresses = {b"exp": 0x1100, b"log": 0x1200}
    measured = sc.measure_runtime_artifacts(
        plan, access=access, symbol_resolver=lambda symbol: addresses[symbol]
    )
    expected_stdlib = [
        sc.FileRecord("stdlib/a.py", 1, hashlib.sha256(b"a").hexdigest()).public(),
        sc.FileRecord("stdlib/z.py", 1, hashlib.sha256(b"z").hexdigest()).public(),
    ]
    assert measured.components.stdlib_tree_sha256 == sc.canonical_sha256(
        expected_stdlib
    )
    assert measured.runtime_artifact_sha256 == sc.canonical_sha256(
        measured.components.public()
    )
    assert measured.libm_dispatch_sha256 == sc.canonical_sha256(
        measured.libm_dispatch
    )
    sc.verify_approved_artifacts(measured, measured.components.public())
    wrong = {**measured.components.public(), "stdlib_tree_sha256": "0" * 64}
    with pytest.raises(sc.ArtifactError, match="APPROVED_ARTIFACT_MISMATCH"):
        sc.verify_approved_artifacts(measured, wrong)


@pytest.mark.parametrize(
    "consumer", ("native_candidates", "required_members"),
)
def test_native_collection_consumers_reject_late_iterator_items(consumer):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)

    class LateOne:
        def __init__(self, value):
            self.value = value

        def __iter__(self):
            return self

        def __next__(self):
            if getattr(self, "done", False):
                raise StopIteration
            self.done = True
            clock.value = context.checkpoint_end_ns
            return self.value

    check = context.checker(clock)
    with pytest.raises(sc.GitHubAuthorityFailure):
        if consumer == "native_candidates":
            sc._collect_native_candidates(
                LateOne(sc.ProcMapEntry(1, 2, "r-xp", 0, "/lib/libm.so.6")),
                check=check,
            )
        else:
            sc.classify_required_native_members(
                LateOne("/not/consumed/after/deadline.so"),
                python_executable="/not/consumed/python",
                check=check,
            )


def test_measure_tree_discards_late_injected_file_record():
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    candidate = sc.FileCandidate("logical.py", "/synthetic/logical.py")

    class LateAccess:
        def record(self, observed):
            assert observed is candidate
            record = sc.FileRecord(
                candidate.logical_path, 1, hashlib.sha256(b"x").hexdigest()
            )
            clock.value = context.checkpoint_end_ns
            return record

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._measure_tree(
            (candidate,), LateAccess(), check=context.checker(clock)
        )


def test_libm_symbol_resolution_returning_at_deadline_is_discarded():
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)

    def late_symbol(symbol):
        assert symbol == b"exp"
        clock.value = context.checkpoint_end_ns
        return 0x1100

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.resolve_libm_dispatch(
            (), set(), symbol_resolver=late_symbol, check=context.checker(clock)
        )


@pytest.mark.parametrize("result_type", ("measurement", "manifest"))
def test_runtime_result_materialization_returning_at_deadline_is_discarded(
    result_type, monkeypatch
):
    plan, access = _artifact_plan()
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    original_call = sc._cooperative_call
    target = (
        sc.RuntimeMeasurement if result_type == "measurement" else sc.FrozenRuntime
    )
    triggered = []

    def intercept(check, operation, /, *args, **kwargs):
        if operation is target and not triggered:
            triggered.append(result_type)
            selected_operation = operation

            def late_operation(*inner_args, **inner_kwargs):
                result = selected_operation(*inner_args, **inner_kwargs)
                clock.value = context.checkpoint_end_ns
                return result

            operation = late_operation
        return original_call(check, operation, *args, **kwargs)

    monkeypatch.setattr(sc, "_cooperative_call", intercept)
    check = context.checker(clock)
    with pytest.raises(sc.GitHubAuthorityFailure):
        measured = sc.measure_runtime_artifacts(
            plan,
            access=access,
            symbol_resolver=lambda symbol: {b"exp": 0x1100, b"log": 0x1200}[symbol],
            check=check,
        )
        assert result_type == "manifest"
        sc.build_runtime_manifest({"synthetic": "identity"}, measured, check=check)
    assert triggered == [result_type]


def test_runtime_artifact_measurement_rejects_duplicate_logical_path():
    plan, access = _artifact_plan()
    duplicate = replace(plan, stdlib_files=(plan.stdlib_files[0], plan.stdlib_files[0]))
    with pytest.raises(sc.ArtifactError, match="ARTIFACT_LOGICAL_PATH_DUPLICATE"):
        sc.measure_runtime_artifacts(duplicate, access=access, include_dispatch=False)


def test_runtime_manifest_has_no_self_hash_and_cannot_be_rebaselined():
    plan, access = _artifact_plan()
    addresses = {b"exp": 0x1100, b"log": 0x1200}
    measured = sc.measure_runtime_artifacts(
        plan, access=access, symbol_resolver=lambda symbol: addresses[symbol]
    )
    scalars = {"render_service_id": sc.RENDER_SERVICE_ID, "libpq_version": 180006}
    frozen = sc.build_runtime_manifest(scalars, measured)
    assert "runtime_manifest_sha256" not in frozen.runtime_manifest_body
    assert frozen.runtime_manifest_sha256 == sc.canonical_sha256(
        frozen.runtime_manifest_body
    )
    sc.verify_runtime_unchanged(frozen, frozen)
    changed = replace(
        frozen,
        runtime_manifest_body={**frozen.runtime_manifest_body, "libpq_version": 170003},
    )
    with pytest.raises(sc.ArtifactError, match="RUNTIME_CHANGED"):
        sc.verify_runtime_unchanged(frozen, changed)
    with pytest.raises(sc.ArtifactError, match="RUNTIME_MANIFEST_SELF_HASH"):
        sc.build_runtime_manifest({**scalars, "runtime_manifest_sha256": "0" * 64}, measured)


def test_every_frozen_platform_and_libpq_scalar_read_is_immediately_bracketed(
    monkeypatch,
):
    events = []

    def observed(name, value):
        events.append(name)
        return value

    class PQ:
        def version(self):
            return observed("libpq_version", 180006)

    class Modules(dict):
        def __getitem__(self, key):
            return observed("pq_module", super().__getitem__(key))

    class Implementation:
        @property
        def cache_tag(self):
            return observed("cache_tag", "cpython-314")

    class FloatInfo:
        @property
        def radix(self):
            return observed("float_radix", 2)

        @property
        def mant_dig(self):
            return observed("float_mant_dig", 53)

        @property
        def max_exp(self):
            return observed("float_max_exp", 1024)

        @property
        def rounds(self):
            return observed("float_rounds", 1)

    class FakeSys:
        modules = Modules({"psycopg.pq": PQ()})

        @property
        def implementation(self):
            return observed("implementation", Implementation())

        @property
        def byteorder(self):
            return observed("byteorder", "little")

        @property
        def float_info(self):
            return observed("float_info", FloatInfo())

    class Environment:
        def get(self, key):
            return observed(
                f"environment:{key}",
                {
                    "RENDER_SERVICE_ID": sc.RENDER_SERVICE_ID,
                    sc.PYTHON_VERSION_ENV: "3.14.3",
                }[key],
            )

    fake_platform = SimpleNamespace(
        libc_ver=lambda: observed("libc", ("glibc", "2.36")),
        python_implementation=lambda: observed("python_implementation", "CPython"),
        python_version=lambda: observed("python_version", "3.14.3"),
        system=lambda: observed("platform_system", "Linux"),
        machine=lambda: observed("platform_machine", "x86_64"),
    )
    monkeypatch.setattr(sc, "sys", FakeSys())
    monkeypatch.setattr(sc, "os", SimpleNamespace(environ=Environment()))
    monkeypatch.setattr(sc, "platform", fake_platform)

    def check():
        events.append("check")

    identity = sc._production_runtime_scalar_identity(check=check)
    assert dict(identity) == {
        "render_service_id": sc.RENDER_SERVICE_ID,
        "render_runtime": "python",
        "python_implementation": "CPython",
        "python_version_source": sc.PYTHON_VERSION_ENV,
        "python_version_env": "3.14.3",
        "python_version": "3.14.3",
        "python_cache_tag": "cpython-314",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "byteorder": "little",
        "libc_name": "glibc",
        "libc_version": "2.36",
        "float_radix": 2,
        "float_mant_dig": 53,
        "float_max_exp": 1024,
        "float_rounds": 1,
        "libpq_version": 180006,
    }

    for name in (
        "pq_module",
        "libpq_version",
        "libc",
        "environment:RENDER_SERVICE_ID",
        f"environment:{sc.PYTHON_VERSION_ENV}",
        "python_implementation",
        "python_version",
        "platform_system",
        "platform_machine",
        "byteorder",
    ):
        index = events.index(name)
        assert events[index - 1 : index + 2] == ["check", name, "check"]
    for container, member in (
        ("implementation", "cache_tag"),
        ("float_info", "float_radix"),
        ("float_info", "float_mant_dig"),
        ("float_info", "float_max_exp"),
        ("float_info", "float_rounds"),
    ):
        member_index = events.index(member)
        assert events[member_index - 2 : member_index + 2] == [
            "check",
            container,
            member,
            "check",
        ]


def test_recovery_renderer_counts_exact_hex_bytes_without_capacity_guarantee():
    parts = _ready_schema_parts()
    seal = parts.seal.canonical_bytes
    sc.validate_seal(
        parts.seal.record(),
        expected_manifest_id=parts.manifest_id,
        expected_canonical_bytes=seal,
    )
    rendered = sc.render_recovery_start_command(
        parts.manifest_id, parts.seal.seal_record_sha256, seal
    )
    assert "<manifest_id>" not in rendered.command
    assert "<seal_record_sha256>" not in rendered.command
    assert "<seal_bytes_hex>" not in rendered.command
    assert seal.hex() in rendered.command
    assert rendered.command_bytes == len(rendered.command.encode("utf-8"))
    assert rendered.seal_bytes == len(seal)
    assert rendered.command_bytes == rendered.overhead_bytes + (2 * len(seal))
    assert not hasattr(rendered, "required_capacity_bytes")
    assert not hasattr(sc, "RECOVERY_CAPACITY_MARGIN_BYTES")
    assert not hasattr(sc, "recovery_capacity_passes")
    with pytest.raises(sc.ContractError, match="INVALID_SEAL_BYTES"):
        sc.render_recovery_start_command(
            parts.manifest_id, parts.seal.seal_record_sha256, seal[:-1]
        )
    with pytest.raises(sc.ContractError, match="INVALID_SEAL_DIGEST"):
        sc.render_recovery_start_command(parts.manifest_id, "A" * 64, seal)


def test_amendment_3a_and_3b_adoption_literals_are_exact():
    assert sc.BOOTSTRAP_AMENDMENT_ID == (
        "ATOM-V1A-AMENDMENT-3A-BOOTSTRAP-DEADLINE-CLOSURE-1"
    )
    assert sc.BOOTSTRAP_AMENDMENT_PATH == (
        "docs/v-1a-amendment-3a-bootstrap-deadline-closure.md"
    )
    assert sc.BOOTSTRAP_AMENDMENT_PR_NUMBER == 326
    assert sc.BOOTSTRAP_AMENDMENT_MERGE_SHA == (
        "9accee6056dfcd6a6ab06d7f538ce6e5b47ee4e9"
    )
    assert sc.BOOTSTRAP_AMENDMENT_MERGED_AT == "2026-09-07T23:37:59Z"
    assert sc.BOOTSTRAP_AMENDMENT_GIT_BLOB_SHA1 == (
        "62441ea2c05da92960b785c8331dcd7c7e3d91ef"
    )
    assert sc.BOOTSTRAP_AMENDMENT_SHA256 == (
        "312546ab6b75b2b81a70c8174070a3901fe934c7d3a63a0cefcc081c80db6125"
    )
    assert sc.CORRECTIVE_AMENDMENT_ID == (
        "ATOM-V1A-AMENDMENT-3B-V1B-CORRECTIVE-AUTHORIZATION-1"
    )
    assert sc.CORRECTIVE_AMENDMENT_PATH == (
        "docs/v-1a-amendment-3b-v1b-corrective-authorization.md"
    )
    assert sc.CORRECTIVE_AMENDMENT_PR_NUMBER == 332
    assert sc.CORRECTIVE_AMENDMENT_MERGE_SHA == (
        "8e08a58f696459970ec8f991a37e2c914a5bc911"
    )
    assert sc.CORRECTIVE_AMENDMENT_MERGED_AT == "2026-09-09T00:48:29Z"
    assert sc.CORRECTIVE_AMENDMENT_GIT_BLOB_SHA1 == (
        "d0af73c9ff3f4f69df464a8d1bcc7ea1ba59dada"
    )
    assert sc.CORRECTIVE_AMENDMENT_SHA256 == (
        "29891d4dad2d74cd679377b3f97442b643fea97894f02124c6c4b74519d8897f"
    )


def test_operational_payload_v2_capacity_is_exact_and_rejects_v1_fields():
    assert sc.OPERATIONAL_APPROVAL_SCHEMA_VERSION == (
        "ATOM-V1B-OPERATIONAL-APPROVAL-PAYLOAD-2"
    )
    assert sc.RECOVERY_TRANSPORT_POLICY == (
        "EXACT_SUBMISSION_OR_CONSUMING_INCIDENT"
    )
    capacity = {
        "mechanism": "Render native one-off Create job startCommand",
        "recovery_transport_policy": sc.RECOVERY_TRANSPORT_POLICY,
        "service_id": "srv-daa7thgae00c73a2lmn0",
    }
    assert sc._validate_capacity(capacity) == capacity
    for key, value in (
        ("accepted_render_startCommand_limit_bytes", 1),
        ("recovery_capacity_margin_bytes", 4096),
        ("vendor_evidence_reference", "obsolete"),
    ):
        with pytest.raises(sc.GitHubAuthorityFailure):
            sc._validate_capacity({**capacity, key: value})
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._validate_capacity(
            {**capacity, "recovery_transport_policy": "BEST_EFFORT"}
        )


def test_conditional_migration_033_is_exact_reader_only_select_surface():
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "033_authorize_v1_volatility_scorecard_reader.sql"
    )
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == (
        "7bcf916689b1780a6e71f4c0ff415576d520bdb7dbdb171dde48b7982e8a56b1"
    )
    assert text.count("GRANT SELECT ON TABLE") == 1
    assert text.count("CREATE POLICY ") == 2
    assert "public.volatility_forecasts," in text
    assert "public.volatility_forecast_outcomes\nTO atom_e1_scorecard_reader;" in text
    assert "CREATE POLICY volatility_forecasts_e1_scorecard_select" in text
    assert "CREATE POLICY volatility_forecast_outcomes_e1_scorecard_select" in text
    assert "current_user <> 'postgres'" in text
    assert "current_database() <> 'postgres'" in text
    for forbidden in (
        "GRANT INSERT",
        "GRANT UPDATE",
        "GRANT DELETE",
        "GRANT TRUNCATE",
        "GRANT REFERENCES",
        "GRANT TRIGGER",
        "ALTER ROLE",
        "CREATE ROLE",
        "CREATE FUNCTION",
    ):
        assert forbidden not in text


def test_first_parent_ancestry_requires_exact_membership(monkeypatch):
    ancestor = "a" * 40
    descendant = "b" * 40
    monkeypatch.setattr(
        sc,
        "_git_ascii",
        lambda *args: f"{descendant}\n{'c' * 40}\n{ancestor}",
    )
    sc._require_first_parent_ancestor(
        SimpleNamespace(), lambda: 0, ancestor, descendant
    )
    monkeypatch.setattr(
        sc,
        "_git_ascii",
        lambda *args: f"{descendant}\n{'c' * 40}",
    )
    with pytest.raises(sc.OrchestrationFailure, match="FIRST_PARENT_HISTORY_INVALID"):
        sc._require_first_parent_ancestor(
            SimpleNamespace(), lambda: 0, ancestor, descendant
        )


def test_unique_implementation_history_allows_only_one_complete_post_3b_merge():
    pre = "1" * 40
    corrective = sc.CORRECTIVE_AMENDMENT_MERGE_SHA
    disjoint = "2" * 40
    implementation = "3" * 40
    paths = {
        pre: frozenset({"docs/unrelated.md"}),
        corrective: frozenset({sc.CORRECTIVE_AMENDMENT_PATH}),
        disjoint: frozenset({"README.md"}),
        implementation: sc.IMPLEMENTATION_PATHS | {sc.CONDITIONAL_MIGRATION_PATH},
    }
    assert sc._select_unique_v1b_implementation(
        (pre, corrective, disjoint, implementation), paths.__getitem__
    ) == implementation


@pytest.mark.parametrize(
    ("chain", "paths", "reason"),
    (
        (
            ("1" * 40, sc.CORRECTIVE_AMENDMENT_MERGE_SHA, "2" * 40),
            {
                "1" * 40: frozenset({"quant/volatility_scorecard.py"}),
                sc.CORRECTIVE_AMENDMENT_MERGE_SHA: frozenset(
                    {sc.CORRECTIVE_AMENDMENT_PATH}
                ),
                "2" * 40: sc.IMPLEMENTATION_PATHS,
            },
            "PRE_AMENDMENT_IMPLEMENTATION",
        ),
        (
            (sc.CORRECTIVE_AMENDMENT_MERGE_SHA, "1" * 40, "2" * 40),
            {
                sc.CORRECTIVE_AMENDMENT_MERGE_SHA: frozenset(
                    {sc.CORRECTIVE_AMENDMENT_PATH}
                ),
                "1" * 40: sc.IMPLEMENTATION_PATHS,
                "2" * 40: sc.IMPLEMENTATION_PATHS,
            },
            "IMPLEMENTATION_MERGE_NOT_UNIQUE",
        ),
        (
            (sc.CORRECTIVE_AMENDMENT_MERGE_SHA, "1" * 40),
            {
                sc.CORRECTIVE_AMENDMENT_MERGE_SHA: frozenset(
                    {sc.CORRECTIVE_AMENDMENT_PATH}
                ),
                "1" * 40: frozenset(
                    {
                        "quant/volatility_scorecard.py",
                        "quant/volatility_scorecard-renamed.py",
                    }
                ),
            },
            "IMPLEMENTATION_DIFF_INVALID",
        ),
    ),
)
def test_unique_implementation_history_rejects_pre_3b_duplicate_and_rename(
    chain, paths, reason
):
    with pytest.raises(sc.OrchestrationFailure, match=reason):
        sc._select_unique_v1b_implementation(chain, paths.__getitem__)


def test_changed_then_restored_implementation_is_still_two_integrations():
    corrective = sc.CORRECTIVE_AMENDMENT_MERGE_SHA
    changed = "1" * 40
    restored = "2" * 40
    paths = {
        corrective: frozenset({sc.CORRECTIVE_AMENDMENT_PATH}),
        changed: sc.IMPLEMENTATION_PATHS,
        restored: sc.IMPLEMENTATION_PATHS,
    }
    with pytest.raises(
        sc.OrchestrationFailure, match="IMPLEMENTATION_MERGE_NOT_UNIQUE"
    ):
        sc._select_unique_v1b_implementation(
            (corrective, changed, restored), paths.__getitem__
        )


def test_direct_push_has_no_unique_associated_merged_pr():
    class Client:
        _seams = SimpleNamespace(monotonic_ns=lambda: 0)

        def get_paginated_json(
            self,
            collection_path,
            *,
            context,
            page_validator,
            collection_validator,
        ):
            assert collection_path.endswith("/commits/" + ("1" * 40) + "/pulls")
            return collection_validator((), context)

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._associated_merged_pr(
            Client(),
            sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
            "1" * 40,
            expected_number=None,
        )


def test_probe_usage_refuses_before_any_observation_and_emits_exact_line():
    calls: list[str] = []
    output: list[bytes] = []
    dependencies = sc.ProbeDependencies(
        observe_startup=lambda: calls.append("observe"),
        validate_startup=lambda observation: calls.append("validate"),
        load_complete_closure=lambda: calls.append("closure"),
        collect_plan=lambda modules: calls.append("plan"),
        file_access=SimpleNamespace(),
        source_identity=lambda: calls.append("identity"),
        utc_now=lambda: datetime.now(UTC),
        write_stdout=output.append,
    )
    assert sc.run_provenance_probe(["unexpected"], dependencies) == 2
    assert calls == []
    assert output == [
        b'{"mode":"V1B_PROVENANCE","reason":"INVALID_PROBE_ARGUMENTS","status":"USAGE_ERROR"}\n'
    ]


def _synthetic_github_tls_trust():
    pem = "-----BEGIN CERTIFICATE-----\nsynthetic\n-----END CERTIFICATE-----\n"
    raw = pem.encode("ascii")
    return sc.GithubTlsTrustObservation(
        reported_cafile_path="/etc/ssl/certs/ca-certificates.crt",
        canonical_cafile_path="/etc/ssl/certs/ca-certificates.crt",
        cafile_size_bytes=len(raw),
        cafile_sha256=hashlib.sha256(raw).hexdigest(),
        pem_ascii=pem,
    )


def test_probe_success_is_one_canonical_nonsecret_record_and_40_hex_source_sha():
    plan, access = _artifact_plan()
    output: list[bytes] = []
    order: list[str] = []
    observation = object()

    def validate(observed):
        assert observed is observation
        order.append("startup")

    dependencies = sc.ProbeDependencies(
        observe_startup=lambda: observation,
        validate_startup=validate,
        load_complete_closure=lambda: order.append("closure") or plan.module_names,
        collect_plan=lambda modules: order.append("plan") or plan,
        file_access=access,
        source_identity=lambda: order.append("identity")
        or sc.SourceIdentity("b" * 40, sc.RENDER_SERVICE_ID),
        utc_now=lambda: datetime(2026, 9, 7, 12, 34, 56, 789, tzinfo=UTC),
        write_stdout=output.append,
        observe_github_tls_trust=lambda: order.append("github_tls_trust")
        or _synthetic_github_tls_trust(),
    )
    assert sc.run_provenance_probe([], dependencies) == 0
    assert order == [
        "startup",
        "closure",
        "github_tls_trust",
        "plan",
        "identity",
    ]
    assert len(output) == 1 and output[0].endswith(b"\n")
    record = json.loads(output[0])
    assert set(record) == {
        "schema_version",
        "render_service_id",
        "execution_source_sha",
        "python_version",
        "runtime_artifact_components",
        "runtime_artifact_sha256",
        "probe_generated_at_utc",
        "github_tls_trust",
    }
    assert record["github_tls_trust"] == _synthetic_github_tls_trust().public()
    assert record["execution_source_sha"] == "b" * 40
    assert record["probe_generated_at_utc"] == "2026-09-07T12:34:56.000789Z"
    serialized = output[0].decode("utf-8")
    assert "credential" not in serialized.lower()
    assert "dispatch" not in serialized.lower()


def test_probe_handled_failure_emits_only_exact_blocked_line():
    output: list[bytes] = []
    dependencies = sc.ProbeDependencies(
        observe_startup=lambda: (_ for _ in ()).throw(sc.StartupIsolationError("x")),
        validate_startup=lambda observation: None,
        load_complete_closure=lambda: frozenset(),
        collect_plan=lambda modules: None,
        file_access=SimpleNamespace(),
        source_identity=lambda: None,
        utc_now=lambda: datetime.now(UTC),
        write_stdout=output.append,
    )
    assert sc.run_provenance_probe([], dependencies) == 1
    assert output == [
        b'{"mode":"V1B_PROVENANCE","reason":"PROVENANCE_PROBE_FAILED","status":"BLOCKED"}\n'
    ]


def test_probe_partial_success_write_never_attempts_a_second_failure_line():
    plan, access = _artifact_plan()
    attempts = []
    observed_prefixes = []

    def partial_writer(raw):
        attempts.append(raw)
        observed_prefixes.append(raw[:17])
        raise OSError("synthetic short stdout write")

    dependencies = sc.ProbeDependencies(
        observe_startup=lambda: object(),
        validate_startup=lambda observation: None,
        load_complete_closure=lambda: plan.module_names,
        collect_plan=lambda modules: plan,
        file_access=access,
        source_identity=lambda: sc.SourceIdentity("b" * 40, sc.RENDER_SERVICE_ID),
        utc_now=lambda: datetime(2026, 9, 7, 12, 34, 56, tzinfo=UTC),
        write_stdout=partial_writer,
        observe_github_tls_trust=_synthetic_github_tls_trust,
    )
    assert sc.run_provenance_probe([], dependencies) == 1
    assert len(attempts) == 1
    assert observed_prefixes == [b'{"execution_sourc']
    assert json.loads(attempts[0])["schema_version"] == (
        "ATOM-V1B-RUNTIME-PROBE-1"
    )


def _without_github_tls_overrides(monkeypatch):
    for key in (
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "SSLKEYLOGFILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    ):
        monkeypatch.delenv(key, raising=False)


def _default_verify_paths(reported):
    return SimpleNamespace(
        openssl_cafile_env="SSL_CERT_FILE",
        openssl_cafile=reported,
        cafile=reported,
        # capath is deliberately unusable and must never be observed.
        capath=object(),
    )


def test_github_tls_observation_accepts_intermediate_alias_and_binds_exact_bytes(
    tmp_path, monkeypatch
):
    _without_github_tls_overrides(monkeypatch)
    canonical_root = tmp_path / "canonical"
    canonical_root.mkdir()
    raw = (
        b"-----BEGIN CERTIFICATE-----\n"
        b"synthetic-ascii-ca\n"
        b"-----END CERTIFICATE-----\n"
    )
    target = canonical_root / "bundle.pem"
    target.write_bytes(raw)
    alias_root = tmp_path / "reported"
    alias_root.symlink_to(canonical_root, target_is_directory=True)
    reported = str(alias_root / "bundle.pem")
    observations = []

    def default_paths():
        observations.append("get_default_verify_paths")
        return _default_verify_paths(reported)

    observed = sc.observe_github_tls_trust(
        get_default_verify_paths=default_paths
    )
    assert observations == ["get_default_verify_paths"]
    assert observed.reported_cafile_path == reported
    assert observed.canonical_cafile_path == str(target.resolve())
    assert observed.cafile_size_bytes == len(raw)
    assert observed.cafile_sha256 == hashlib.sha256(raw).hexdigest()
    assert observed.pem_ascii == raw.decode("ascii")
    assert observed.public() == {
        "source": "ssl.get_default_verify_paths().cafile",
        "reported_cafile_path": reported,
        "canonical_cafile_path": str(target.resolve()),
        "cafile_size_bytes": len(raw),
        "cafile_sha256": hashlib.sha256(raw).hexdigest(),
    }


@pytest.mark.parametrize(
    "override",
    (
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "SSLKEYLOGFILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    ),
)
def test_github_tls_observation_rejects_even_empty_override_before_default_query(
    override, tmp_path, monkeypatch
):
    _without_github_tls_overrides(monkeypatch)
    monkeypatch.setenv(override, "")
    calls = []
    with pytest.raises(sc.ArtifactError, match="GITHUB_TLS_TRUST_OVERRIDE_PRESENT"):
        sc.observe_github_tls_trust(
            get_default_verify_paths=lambda: calls.append("queried")
        )
    assert calls == []


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"openssl_cafile_env": "OTHER"}, "GITHUB_TLS_DEFAULT_PATH_INVALID"),
        ({"openssl_cafile": "relative.pem", "cafile": "relative.pem"},
         "GITHUB_TLS_DEFAULT_PATH_INVALID"),
        ({"openssl_cafile": "", "cafile": ""},
         "GITHUB_TLS_DEFAULT_PATH_INVALID"),
        ({"cafile": "/different.pem"}, "GITHUB_TLS_DEFAULT_PATH_INVALID"),
    ),
)
def test_github_tls_observation_requires_exact_compiled_and_effective_cafile(
    changes, reason, tmp_path, monkeypatch
):
    _without_github_tls_overrides(monkeypatch)
    target = tmp_path / "bundle.pem"
    target.write_text("ASCII CA\n", encoding="ascii")
    values = vars(_default_verify_paths(str(target.resolve()))).copy()
    values.update(changes)
    with pytest.raises(sc.ArtifactError, match=reason):
        sc.observe_github_tls_trust(
            get_default_verify_paths=lambda: SimpleNamespace(**values)
        )


def test_github_tls_observation_reads_in_exact_deadline_chunks_and_rejects_nonascii(
    tmp_path, monkeypatch
):
    _without_github_tls_overrides(monkeypatch)
    raw = b"A" * sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES + b"B"
    target = tmp_path / "bundle.pem"
    target.write_bytes(raw)
    read_sizes = []
    original_read = sc.os.read

    def observed_read(descriptor, size):
        read_sizes.append(size)
        return original_read(descriptor, size)

    monkeypatch.setattr(sc.os, "read", observed_read)
    observed = sc.observe_github_tls_trust(
        get_default_verify_paths=lambda: _default_verify_paths(
            str(target.resolve())
        )
    )
    assert observed.cafile_size_bytes == len(raw)
    assert read_sizes == [sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES, 1, 1]

    target.write_bytes(b"ASCII\n\xff")
    with pytest.raises(sc.ArtifactError, match="GITHUB_TLS_BUNDLE_NOT_ASCII"):
        sc.observe_github_tls_trust(
            get_default_verify_paths=lambda: _default_verify_paths(
                str(target.resolve())
            )
        )


@pytest.mark.parametrize("change", ("retarget", "mutate", "reported_alias"))
def test_each_github_checkpoint_must_freshly_resolve_and_match_approved_bundle(
    change, tmp_path, monkeypatch
):
    _without_github_tls_overrides(monkeypatch)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = first_root / "bundle.pem"
    second = second_root / "bundle.pem"
    first.write_text("FIRST ASCII CA\n", encoding="ascii")
    second.write_text("SECOND ASCII CA\n", encoding="ascii")
    alias = tmp_path / "reported.pem"
    alias.symlink_to(first)
    reported = str(alias)
    calls = []

    def default_paths():
        calls.append(reported)
        return _default_verify_paths(reported)

    approved_observation = sc.observe_github_tls_trust(
        get_default_verify_paths=default_paths
    )
    approved = approved_observation.public()
    if change == "retarget":
        alias.unlink()
        alias.symlink_to(second)
    elif change == "mutate":
        first.write_text("MUTATED ASCII CA\n", encoding="ascii")
    else:
        second_alias = tmp_path / "second-reported.pem"
        second_alias.symlink_to(first)
        reported = str(second_alias)

    current = sc.observe_github_tls_trust(
        get_default_verify_paths=default_paths
    )
    with pytest.raises(sc.ArtifactError, match="GITHUB_TLS_TRUST_MISMATCH"):
        sc.verify_github_tls_trust(current, approved)
    assert len(calls) == 2


def test_github_ssl_context_is_exactly_one_cadata_only_tls12_http11_store():
    trust = _synthetic_github_tls_trust()
    calls = []

    class Context:
        verify_mode = None
        check_hostname = False
        minimum_version = None

        def load_verify_locations(self, *args, **kwargs):
            calls.append(("load_verify_locations", args, kwargs))

        def set_alpn_protocols(self, protocols):
            calls.append(("alpn", protocols))

        def get_ca_certs(self, *, binary_form):
            calls.append(("get_ca_certs", binary_form))
            return [b"accepted-ca"]

    context = Context()

    def factory(protocol):
        calls.append(("context_factory", protocol))
        return context

    assert sc.build_github_ssl_context(trust, context_factory=factory) is context
    assert calls == [
        ("context_factory", ssl.PROTOCOL_TLS_CLIENT),
        ("load_verify_locations", (), {"cadata": trust.pem_ascii}),
        ("alpn", ["http/1.1"]),
        ("get_ca_certs", True),
    ]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2


@pytest.mark.parametrize("failure", ("load", "zero_accepted", "property"))
def test_github_ssl_context_fails_closed_on_store_or_property_defect(failure):
    trust = _synthetic_github_tls_trust()

    class Context:
        verify_mode = None
        check_hostname = False
        minimum_version = None

        def load_verify_locations(self, *args, **kwargs):
            if failure == "load":
                raise ssl.SSLError("synthetic invalid PEM")

        def set_alpn_protocols(self, protocols):
            return None

        def get_ca_certs(self, *, binary_form):
            if failure == "property":
                self.check_hostname = False
            return [] if failure == "zero_accepted" else [b"accepted"]

    with pytest.raises(sc.ArtifactError, match="GITHUB_TLS_CONTEXT_INVALID"):
        sc.build_github_ssl_context(
            trust, context_factory=lambda protocol: Context()
        )


def test_probe_resnapshots_modules_after_cafile_observation_before_baseline(
    monkeypatch,
):
    plan, access = _artifact_plan()
    marker = "synthetic_lazy_codec_loaded_by_cafile_observation"
    output = []

    def observe_trust():
        monkeypatch.setitem(sys.modules, marker, SimpleNamespace())
        return _synthetic_github_tls_trust()

    def collect_plan(module_names):
        assert marker in module_names
        return replace(plan, module_names=frozenset(module_names))

    dependencies = sc.ProbeDependencies(
        observe_startup=lambda: object(),
        validate_startup=lambda observation: None,
        load_complete_closure=lambda: frozenset(sys.modules),
        collect_plan=collect_plan,
        file_access=access,
        source_identity=lambda: sc.SourceIdentity("b" * 40, sc.RENDER_SERVICE_ID),
        utc_now=lambda: datetime(2026, 9, 7, 12, 34, 56, tzinfo=UTC),
        write_stdout=output.append,
        observe_github_tls_trust=observe_trust,
        post_trust_module_names=lambda: frozenset(sys.modules),
    )
    assert sc.run_provenance_probe([], dependencies) == 0
    assert json.loads(output[0])["schema_version"] == (
        "ATOM-V1B-RUNTIME-PROBE-1"
    )


def test_production_probe_wires_post_cafile_module_snapshot():
    dependencies = sc._production_probe_dependencies()
    assert dependencies.post_trust_module_names is sc._cooperative_module_snapshot


def test_evidence_runtime_resnapshots_modules_after_cafile_before_first_plan(
    monkeypatch, _synthetic_zoneinfo_isolation
):
    marker = "synthetic_lazy_codec_loaded_by_evidence_cafile_observation"
    initialized = SimpleNamespace(
        xnys_calendar=object(),
        home_dir=Path("/synthetic/home"),
        v4a=object(),
        v4b=object(),
        v4c=object(),
        psycopg_module=object(),
        conninfo_module=object(),
        zoneinfo_isolation=_synthetic_zoneinfo_isolation,
        module_names=frozenset(sys.modules),
    )
    monkeypatch.setattr(
        sc, "_initialize_runtime_for_measurement", lambda: initialized
    )

    def observe_trust():
        monkeypatch.setitem(sys.modules, marker, SimpleNamespace())
        return _synthetic_github_tls_trust()

    monkeypatch.setattr(sc, "observe_github_tls_trust", observe_trust)

    class BaselineReached(Exception):
        pass

    def collect_plan(expected, *, module_names, **kwargs):
        assert marker in module_names
        raise BaselineReached

    monkeypatch.setattr(sc, "collect_runtime_artifact_plan", collect_plan)
    with pytest.raises(BaselineReached):
        sc.build_production_dependencies(SimpleNamespace())


def test_evidence_runtime_order_is_closure_cafile_baseline_context_remeasurement(
    monkeypatch, _synthetic_zoneinfo_isolation
):
    events = []
    marker = "synthetic_cafile_lazy_module"
    initialized = SimpleNamespace(
        xnys_calendar=object(),
        home_dir=Path("/synthetic/home"),
        v4a=object(),
        v4b=object(),
        v4c=object(),
        psycopg_module=object(),
        conninfo_module=object(),
        zoneinfo_isolation=_synthetic_zoneinfo_isolation,
        module_names=frozenset({"pre-cafile-snapshot-must-not-be-used"}),
    )

    def initialize():
        events.append("complete_closure")
        return initialized

    monkeypatch.setattr(sc, "_initialize_runtime_for_measurement", initialize)

    def observe_trust():
        events.append("cafile_observation")
        monkeypatch.setitem(sys.modules, marker, SimpleNamespace())
        return _synthetic_github_tls_trust()

    monkeypatch.setattr(sc, "observe_github_tls_trust", observe_trust)
    snapshot_calls = 0

    def snapshot(*, check=None):
        nonlocal snapshot_calls
        snapshot_calls += 1
        events.append(f"module_snapshot_{snapshot_calls}")
        return frozenset(sys.modules)

    monkeypatch.setattr(sc, "_cooperative_module_snapshot", snapshot)
    plans = (SimpleNamespace(name="baseline"), SimpleNamespace(name="post-context"))
    plan_calls = 0

    def collect(expected, *, module_names, **kwargs):
        nonlocal plan_calls
        plan_calls += 1
        events.append(f"artifact_plan_{plan_calls}")
        assert marker in module_names
        return plans[plan_calls - 1]

    monkeypatch.setattr(sc, "collect_runtime_artifact_plan", collect)
    measurements = (
        SimpleNamespace(
            name="baseline-measurement",
            components=SimpleNamespace(public=lambda: {"baseline": True}),
        ),
        SimpleNamespace(
            name="post-context-measurement",
            components=SimpleNamespace(public=lambda: {"baseline": True}),
        ),
    )
    measure_calls = 0

    def measure(plan, **kwargs):
        nonlocal measure_calls
        measure_calls += 1
        events.append(f"artifact_measurement_{measure_calls}")
        assert plan is plans[measure_calls - 1]
        return measurements[measure_calls - 1]

    monkeypatch.setattr(sc, "measure_runtime_artifacts", measure)
    runtimes = (
        SimpleNamespace(plan=plans[0], measurement=measurements[0]),
        SimpleNamespace(plan=plans[1], measurement=measurements[1]),
    )
    state_calls = 0

    def runtime_state(plan, measurement, **kwargs):
        nonlocal state_calls
        state_calls += 1
        events.append(f"runtime_state_{state_calls}")
        return runtimes[state_calls - 1]

    monkeypatch.setattr(sc, "_runtime_state_from_measurement", runtime_state)
    frozen_context = object()
    monkeypatch.setattr(
        sc,
        "build_github_ssl_context",
        lambda trust: events.append("cadata_only_context") or frozen_context,
    )
    monkeypatch.setattr(
        sc,
        "_verify_runtime_remeasurement",
        lambda *args, **kwargs: events.append("post_context_runtime_equality"),
    )

    class Complete(Exception):
        pass

    def build_client(*, plan, measurement, ssl_context):
        events.append("github_client")
        assert plan is plans[0]
        assert measurement is measurements[0]
        assert ssl_context is frozen_context
        raise Complete

    monkeypatch.setattr(
        sc.GithubClient,
        "for_frozen_runtime",
        staticmethod(build_client),
    )
    with pytest.raises(Complete):
        sc.build_production_dependencies(SimpleNamespace())
    assert events == [
        "complete_closure",
        "cafile_observation",
        "module_snapshot_1",
        "artifact_plan_1",
        "artifact_measurement_1",
        "runtime_state_1",
        "cadata_only_context",
        "module_snapshot_2",
        "artifact_plan_2",
        "artifact_measurement_2",
        "runtime_state_2",
        "post_context_runtime_equality",
        "github_client",
    ]


# ---------------------------------------------------------------------------
# GitHub authority transport, exact deadlines, pagination, and stage routing


class _MutableClock:
    def __init__(self, value: int = 0):
        self.value = value
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        return self.value


def test_cooperative_native_call_checks_immediately_before_and_after_return():
    events = []

    def check():
        events.append("check")

    def success():
        events.append("operation")
        return "accepted"

    assert sc._cooperative_call(check, success) == "accepted"
    assert events == ["check", "operation", "check"]

    events.clear()

    def failure():
        events.append("operation")
        raise ValueError("synthetic primitive failure")

    with pytest.raises(ValueError, match="synthetic primitive failure"):
        sc._cooperative_call(check, failure)
    assert events == ["check", "operation", "check"]


@pytest.mark.parametrize("raises", (False, True), ids=("success", "exception"))
def test_cooperative_native_call_discards_any_result_returned_at_equality(raises):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    events = []

    def operation():
        events.append("operation")
        clock.value = context.checkpoint_end_ns
        if raises:
            raise ValueError("late primitive exception")
        return "late result"

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._cooperative_call(context.checker(clock), operation)
    assert events == ["operation"]


@pytest.mark.parametrize("phase", ("iter", "next", "materialize"))
def test_cooperative_collection_materialization_checks_each_native_boundary(
    phase, monkeypatch
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)

    class OneItem:
        def __iter__(self):
            if phase == "iter":
                clock.value = context.checkpoint_end_ns
            return self

        def __next__(self):
            if phase == "next":
                clock.value = context.checkpoint_end_ns
            if getattr(self, "yielded", False):
                raise StopIteration
            self.yielded = True
            return "item"

    original_call = sc._cooperative_call

    def intercept(check, operation, /, *args, **kwargs):
        if phase == "materialize" and operation is tuple:
            def late_tuple(values):
                result = tuple(values)
                clock.value = context.checkpoint_end_ns
                return result

            operation = late_tuple
        return original_call(check, operation, *args, **kwargs)

    monkeypatch.setattr(sc, "_cooperative_call", intercept)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._cooperative_tuple(OneItem(), check=context.checker(clock))


@pytest.mark.parametrize(
    "phase",
    ("encoder_init", "hash_init", "iterencode", "next", "hexdigest"),
)
def test_cooperative_canonical_hash_rejects_each_late_native_phase(
    phase, monkeypatch
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    original_encoder = sc.json.JSONEncoder
    original_sha256 = sc.hashlib.sha256

    class LateIterator:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __iter__(self):
            return self

        def __next__(self):
            item = next(self.wrapped)
            clock.value = context.checkpoint_end_ns
            return item

    class Encoder:
        def __init__(self, **kwargs):
            self.wrapped = original_encoder(**kwargs)

        def iterencode(self, value):
            pieces = self.wrapped.iterencode(value)
            if phase == "iterencode":
                clock.value = context.checkpoint_end_ns
            return LateIterator(iter(pieces)) if phase == "next" else pieces

    def encoder_factory(**kwargs):
        result = Encoder(**kwargs)
        if phase == "encoder_init":
            clock.value = context.checkpoint_end_ns
        return result

    class Digest:
        def __init__(self):
            self.wrapped = original_sha256()

        def update(self, value):
            self.wrapped.update(value)

        def hexdigest(self):
            result = self.wrapped.hexdigest()
            if phase == "hexdigest":
                clock.value = context.checkpoint_end_ns
            return result

    def digest_factory():
        result = Digest()
        if phase == "hash_init":
            clock.value = context.checkpoint_end_ns
        return result

    monkeypatch.setattr(sc.json, "JSONEncoder", encoder_factory)
    monkeypatch.setattr(sc.hashlib, "sha256", digest_factory)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._cooperative_canonical_sha256(
            {"payload": "bounded"}, check=context.checker(clock)
        )


@pytest.mark.parametrize("phase", ("iter", "next", "frozenset"))
def test_module_snapshot_rejects_late_iteration_or_materialization(
    phase, monkeypatch
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)

    class Modules:
        def __iter__(self):
            if phase == "iter":
                clock.value = context.checkpoint_end_ns
            return self

        def __next__(self):
            if getattr(self, "done", False):
                raise StopIteration
            self.done = True
            if phase == "next":
                clock.value = context.checkpoint_end_ns
            return "synthetic.module"

    monkeypatch.setattr(sc, "sys", SimpleNamespace(modules=Modules()))
    original_call = sc._cooperative_call

    def intercept(check, operation, /, *args, **kwargs):
        if phase == "frozenset" and operation is frozenset:
            def late_frozenset(values):
                result = frozenset(values)
                clock.value = context.checkpoint_end_ns
                return result

            operation = late_frozenset
        return original_call(check, operation, *args, **kwargs)

    monkeypatch.setattr(sc, "_cooperative_call", intercept)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._cooperative_module_snapshot(check=context.checker(clock))


@pytest.mark.parametrize(
    "phase", ("decode", "splitlines", "line_split", "result_tuple")
)
def test_proc_mapping_parser_rejects_late_bounded_native_phase(
    phase, monkeypatch
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)

    class Line(str):
        def split(self, *args, **kwargs):
            result = super().split(*args, **kwargs)
            if phase == "line_split":
                clock.value = context.checkpoint_end_ns
            return result

    class Text(str):
        def splitlines(self, *args, **kwargs):
            result = [Line(item) for item in super().splitlines(*args, **kwargs)]
            if phase == "splitlines":
                clock.value = context.checkpoint_end_ns
            return result

    class Raw(bytes):
        def decode(self, *args, **kwargs):
            result = Text(super().decode(*args, **kwargs))
            if phase == "decode":
                clock.value = context.checkpoint_end_ns
            return result

    original_call = sc._cooperative_call

    def intercept(check, operation, /, *args, **kwargs):
        if (
            phase == "result_tuple"
            and operation is tuple
            and args
            and isinstance(args[0], list)
            and args[0]
            and isinstance(args[0][0], sc.ProcMapEntry)
        ):
            def late_tuple(values):
                result = tuple(values)
                clock.value = context.checkpoint_end_ns
                return result

            operation = late_tuple
        return original_call(check, operation, *args, **kwargs)

    monkeypatch.setattr(sc, "_cooperative_call", intercept)
    raw = Raw(b"1000-2000 r-xp 00000000 00:00 1 /lib/libm.so.6\n")
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.parse_proc_maps(raw, check=context.checker(clock))


def test_github_deadlines_are_exact_monotonic_literals_and_equality_fails():
    assert sc.GITHUB_CONNECT_TIMEOUT_NS == 10_000_000_000
    assert sc.GITHUB_READ_IDLE_TIMEOUT_NS == 20_000_000_000
    assert sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS == 60_000_000_000
    assert sc.GITHUB_PAGINATION_TOTAL_TIMEOUT_NS == 180_000_000_000
    assert sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS == 300_000_000_000

    start = 123
    context = sc.GithubDeadlineContext.begin_checkpoint(lambda: start)
    assert context.check(
        lambda: start + sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS - 1
    ) == (start + sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS - 1)
    with pytest.raises(sc.GitHubAuthorityFailure):
        context.check(lambda: start + sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS)

    paged = context.begin_pagination(lambda: start + 7)
    page_end = start + 7 + sc.GITHUB_PAGINATION_TOTAL_TIMEOUT_NS
    assert paged.check(lambda: page_end - 1) == page_end - 1
    with pytest.raises(sc.GitHubAuthorityFailure):
        paged.check(lambda: page_end)


def test_github_deadline_rejects_noninteger_and_negative_monotonic_values():
    for value in (-1, 1.5, True):
        with pytest.raises(sc.GitHubAuthorityFailure):
            sc.GithubDeadlineContext.begin_checkpoint(lambda value=value: value)


@pytest.mark.parametrize(
    "raw",
    [
        b"HTTP/1.1 302 Found\r\nContent-Length: 0\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nLocation: https://evil.example/\r\nContent-Length: 0\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
        b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\n{}",
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\n{}",
    ],
)
def test_github_http_parser_rejects_redirects_location_and_incomplete_framing(raw):
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._parse_http_response(raw)


def test_github_http_parser_accepts_only_complete_identity_json_framing():
    raw = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/vnd.github+json\r\n"
        b"Content-Length: 11\r\n\r\n"
        b'{"ok":true}'
    )
    response = sc._parse_http_response(raw)
    assert response.status == 200
    assert response.body == b'{"ok":true}'
    assert response.header_values(b"CONTENT-TYPE") == (
        b"application/vnd.github+json",
    )
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._json_no_duplicates(b'{"x":1,"x":2}')


class _FakeSelector:
    def __init__(self, clock: _MutableClock, advance_to: int, ready=()):
        self.clock = clock
        self.advance_to = advance_to
        self.ready = ready
        self.registered = None
        self.closed = False

    def register(self, fileobj, events):
        self.registered = (fileobj, events)

    def select(self, timeout):
        assert timeout >= 0
        self.clock.value = self.advance_to
        return self.ready

    def close(self):
        self.closed = True


class _WantReadTLS:
    def recv(self, size):
        raise ssl.SSLWantReadError()


def test_read_idle_timeout_is_absolute_and_equality_fails():
    clock = _MutableClock(0)
    selectors_created = []

    def selector_factory():
        selector = _FakeSelector(
            clock, sc.GITHUB_READ_IDLE_TIMEOUT_NS, ready=()
        )
        selectors_created.append(selector)
        return selector

    seams = sc.GithubTransportSeams(
        monotonic_ns=clock,
        selector_factory=selector_factory,
    )
    context = sc.GithubDeadlineContext(
        checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS
    )
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._recv_to_tls_eof(
            _WantReadTLS(), seams, context, sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS
        )
    assert len(selectors_created) == 1
    assert selectors_created[0].registered[1] == selectors.EVENT_READ
    assert selectors_created[0].closed is True


class _SlowDripTLS:
    def __init__(self, clock: _MutableClock):
        self.clock = clock
        self.calls = 0

    def recv(self, size):
        self.calls += 1
        self.clock.value += sc.GITHUB_READ_IDLE_TIMEOUT_NS - 1_000_000_000
        return b"x"


def test_read_idle_resets_on_octet_but_never_resets_request_total():
    clock = _MutableClock(0)
    seams = sc.GithubTransportSeams(monotonic_ns=clock)
    context = sc.GithubDeadlineContext(
        checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS
    )
    tls = _SlowDripTLS(clock)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._recv_to_tls_eof(
            tls, seams, context, sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS
        )
    assert tls.calls == 4
    assert clock.value > sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS


class _BoundedResponseTLS:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.recv_calls = []

    def recv(self, size):
        self.recv_calls.append(size)
        return self.chunks.pop(0)


def test_github_raw_response_bound_is_exact_and_crossing_chunk_is_discarded():
    assert sc.GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES == 67_108_864
    assert sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES == 65_536
    clock = _MutableClock(0)
    seams = sc.GithubTransportSeams(monotonic_ns=clock)
    context = sc.GithubDeadlineContext(
        checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS
    )
    tls = _BoundedResponseTLS((b"abcd", b"x", b""))
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._recv_to_tls_eof(
            tls,
            seams,
            context,
            sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS,
            raw_limit_bytes=4,
        )
    # The cap-sized prefix is not returned or parsed, and no further input is
    # consumed after the single chunk that crosses the retained-buffer bound.
    assert tls.recv_calls == [5, 1]


def test_github_raw_response_exact_boundary_requires_clean_eof():
    clock = _MutableClock(0)
    tls = _BoundedResponseTLS((b"ab", b"cd", b""))
    assert sc._recv_to_tls_eof(
        tls,
        sc.GithubTransportSeams(monotonic_ns=clock),
        sc.GithubDeadlineContext(
            checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS
        ),
        sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS,
        raw_limit_bytes=4,
    ) == b"abcd"
    assert tls.recv_calls == [5, 3, 1]


def test_tls_eof_final_byte_materialization_cannot_return_at_deadline(
    monkeypatch,
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    native_bytearray = bytearray
    native_bytes = bytes

    class LateBytesBuffer:
        def __init__(self):
            self.data = native_bytearray()

        def __len__(self):
            return len(self.data)

        def extend(self, value):
            self.data.extend(value)

        def __bytes__(self):
            result = native_bytes(self.data)
            clock.value = context.checkpoint_end_ns
            return result

    monkeypatch.setattr(sc, "bytearray", LateBytesBuffer, raising=False)
    tls = _BoundedResponseTLS((b"ok", b""))
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._recv_to_tls_eof(
            tls,
            sc.GithubTransportSeams(monotonic_ns=clock),
            context,
            sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS,
            raw_limit_bytes=4,
        )
    assert tls.recv_calls == [5, 3]


@pytest.mark.parametrize(
    "phase", ("wire_find", "wire_slice", "head_replace", "response_object")
)
def test_http_framing_discards_late_search_slice_and_materialization(
    phase, monkeypatch
):
    raw = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/vnd.github+json\r\n"
        b"Content-Length: 11\r\n\r\n"
        b'{"ok":true}'
    )
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    original_call = sc._cooperative_call
    triggered = []

    def intercept(check, operation, /, *args, **kwargs):
        operation_name = getattr(operation, "__name__", "")
        is_target = (
            (phase == "wire_find" and getattr(operation, "__self__", None) is raw
             and operation_name == "find")
            or (phase == "wire_slice" and operation_name == "<lambda>"
                and args and args[0] is raw)
            or (phase == "head_replace" and operation_name == "replace")
            or (phase == "response_object" and operation is sc.GithubHTTPResponse)
        )
        if is_target and not triggered:
            triggered.append(phase)
            selected_operation = operation

            def late_operation(*inner_args, **inner_kwargs):
                result = selected_operation(*inner_args, **inner_kwargs)
                clock.value = context.checkpoint_end_ns
                return result

            operation = late_operation
        return original_call(check, operation, *args, **kwargs)

    monkeypatch.setattr(sc, "_cooperative_call", intercept)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._parse_http_response(raw, check=context.checker(clock))
    assert triggered == [phase]


def test_flat_large_json_is_finite_by_wire_cap_and_checked_after_decode(
    monkeypatch,
):
    # A flat JSON scalar invokes no object-pairs hook.  Its parser work is
    # nevertheless finite because the authenticated wire input is capped, and
    # the request deadline is checked after the bounded decode/parse returns.
    raw = b'"' + b"x" * (1024 * 1024) + b'"'
    assert len(raw) < sc.GITHUB_RAW_WIRE_RESPONSE_MAX_BYTES
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    original_loads = sc.json.loads
    loads_lengths = []
    pair_hook_calls = []

    def observed_loads(text, **kwargs):
        loads_lengths.append(len(text.encode("utf-8")))
        original_hook = kwargs["object_pairs_hook"]

        def observed_hook(items):
            pair_hook_calls.append(items)
            return original_hook(items)

        kwargs["object_pairs_hook"] = observed_hook
        value = original_loads(text, **kwargs)
        clock.value = context.checkpoint_end_ns
        return value

    monkeypatch.setattr(sc.json, "loads", observed_loads)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._json_no_duplicates(raw, check=context.checker(clock))
    assert loads_lengths == [len(raw)]
    assert pair_hook_calls == []


@pytest.mark.parametrize("phase", ("hash_init", "update", "hexdigest"))
def test_deadline_bound_response_digest_discards_each_late_hash_phase(
    phase, monkeypatch
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    original_sha256 = sc.hashlib.sha256

    class Digest:
        def __init__(self):
            self.wrapped = original_sha256()

        def update(self, value):
            self.wrapped.update(value)
            if phase == "update":
                clock.value = context.checkpoint_end_ns

        def hexdigest(self):
            result = self.wrapped.hexdigest()
            if phase == "hexdigest":
                clock.value = context.checkpoint_end_ns
            return result

    def digest_factory():
        result = Digest()
        if phase == "hash_init":
            clock.value = context.checkpoint_end_ns
        return result

    monkeypatch.setattr(sc.hashlib, "sha256", digest_factory)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._checked_sha256_bytes(b"bounded", check=context.checker(clock))


def test_chunked_decoder_copies_peer_chunk_in_deadline_work_slices():
    payload = b"x" * (sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES + 1)
    body = f"{len(payload):x}\r\n".encode("ascii") + payload + b"\r\n0\r\n\r\n"
    checks = []
    decoded, trailers = sc._decode_chunked(
        body, check=lambda: checks.append(len(checks)) or 0
    )
    assert decoded == payload
    assert trailers == {}
    assert len(checks) >= 7


def test_chunked_decoder_deadline_equality_stops_before_second_work_slice():
    payload = b"x" * (sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES + 1)
    body = f"{len(payload):x}\r\n".encode("ascii") + payload + b"\r\n0\r\n\r\n"
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    calls = 0

    def expire_before_second_slice():
        nonlocal calls
        calls += 1
        if calls == 4:
            clock.value = context.checkpoint_end_ns
        return context.check(clock)

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._decode_chunked(body, check=expire_before_second_slice)
    assert calls == 4


def test_chunked_decoder_final_byte_materialization_is_deadline_bracketed(
    monkeypatch,
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    native_bytearray = bytearray
    native_bytes = bytes

    class LateBytesBuffer:
        def __init__(self):
            self.data = native_bytearray()

        def extend(self, value):
            self.data.extend(value)

        def __bytes__(self):
            result = native_bytes(self.data)
            clock.value = context.checkpoint_end_ns
            return result

    monkeypatch.setattr(sc, "bytearray", LateBytesBuffer, raising=False)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._decode_chunked(
            b"2\r\nok\r\n0\r\n\r\n", check=context.checker(clock)
        )


@pytest.mark.parametrize(
    "invalid_limit",
    (0, -1, True, 1.5, 67_108_865),
)
def test_github_raw_response_bound_rejects_invalid_internal_values(invalid_limit):
    clock = _MutableClock(0)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._recv_to_tls_eof(
            _BoundedResponseTLS((b"",)),
            sc.GithubTransportSeams(monotonic_ns=clock),
            sc.GithubDeadlineContext(
                checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS
            ),
            sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS,
            raw_limit_bytes=invalid_limit,
        )


def test_local_artifact_hash_reads_exact_size_in_checked_64k_chunks(
    tmp_path, monkeypatch
):
    raw = b"a" * sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES + b"b"
    path = tmp_path / "native.so"
    path.write_bytes(raw)
    real = str(path.resolve())
    read_sizes = []
    checks = []
    original_read = sc.os.read

    def observed_read(descriptor, size):
        read_sizes.append(size)
        return original_read(descriptor, size)

    monkeypatch.setattr(sc.os, "read", observed_read)
    record = sc.LocalFileAccess(check=lambda: checks.append(len(checks))).record(
        sc.FileCandidate(real, real)
    )
    assert record == sc.FileRecord(real, len(raw), hashlib.sha256(raw).hexdigest())
    assert read_sizes == [sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES, 1, 1]
    assert len(checks) >= 18


def test_local_artifact_hash_deadline_equality_stops_after_current_chunk(
    tmp_path, monkeypatch
):
    path = tmp_path / "native.so"
    path.write_bytes(b"a" * (sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES + 1))
    real = str(path.resolve())
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    original_read = sc.os.read
    read_sizes = []

    def deadline_read(descriptor, size):
        read_sizes.append(size)
        chunk = original_read(descriptor, size)
        clock.value = context.checkpoint_end_ns
        return chunk

    monkeypatch.setattr(sc.os, "read", deadline_read)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.LocalFileAccess(check=context.checker(clock)).record(
            sc.FileCandidate(real, real)
        )
    assert read_sizes == [sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES]


def test_local_artifact_hash_rejects_growth_instead_of_accepting_prefix(
    tmp_path, monkeypatch
):
    path = tmp_path / "native.so"
    path.write_bytes(b"fixed")
    real = str(path.resolve())
    original_read = sc.os.read
    calls = 0

    def growing_read(descriptor, size):
        nonlocal calls
        calls += 1
        if calls == 2:
            return b"x"
        return original_read(descriptor, size)

    monkeypatch.setattr(sc.os, "read", growing_read)
    with pytest.raises(sc.ArtifactError, match="ARTIFACT_CHANGED_DURING_READ"):
        sc.LocalFileAccess().record(sc.FileCandidate(real, real))
    assert calls == 2


def test_local_artifact_hash_rejects_early_eof_without_partial_digest(
    tmp_path, monkeypatch
):
    path = tmp_path / "native.so"
    path.write_bytes(b"abcdef")
    real = str(path.resolve())
    original_read = sc.os.read
    calls = []

    def short_then_eof(descriptor, size):
        calls.append(size)
        if len(calls) == 1:
            return original_read(descriptor, 3)
        return b""

    monkeypatch.setattr(sc.os, "read", short_then_eof)
    with pytest.raises(sc.ArtifactError, match="ARTIFACT_READ_FAILED"):
        sc.LocalFileAccess().record(sc.FileCandidate(real, real))
    assert calls == [6, 3]


def _authenticate_path_fixture(monkeypatch, path, expected, clock):
    blob_sha = "b" * 40
    monkeypatch.setattr(
        sc,
        "_local_tree_entry",
        lambda context, clock_ns, execution_sha, repository_path: (
            "100644",
            blob_sha,
            expected,
        ),
    )
    monkeypatch.setattr(
        sc,
        "_github_blob",
        lambda client, context, observed_sha: expected,
    )
    client = SimpleNamespace(_seams=SimpleNamespace(monotonic_ns=clock))
    context = sc.GithubDeadlineContext(checkpoint_end_ns=10)
    return client, context


def test_authenticated_worktree_streams_exact_size_in_checked_work_chunks(
    tmp_path, monkeypatch
):
    expected = b"a" * sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES + b"b"
    path = tmp_path / "reviewed.py"
    path.write_bytes(expected)
    clock = _MutableClock(0)
    client, context = _authenticate_path_fixture(
        monkeypatch, path, expected, clock
    )
    original_read = sc.os.read
    read_sizes = []

    def observed_read(descriptor, size):
        read_sizes.append(size)
        return original_read(descriptor, size)

    monkeypatch.setattr(sc.os, "read", observed_read)
    assert sc._authenticate_path(
        client,
        context,
        "a" * 40,
        str(path),
        require_worktree=True,
    ) == expected
    assert read_sizes == [sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES, 1, 1]


@pytest.mark.parametrize("defect", ("early_eof", "growth"))
def test_authenticated_worktree_rejects_partial_or_growing_bytes(
    defect, tmp_path, monkeypatch
):
    expected = b"abcdef"
    path = tmp_path / "reviewed.py"
    path.write_bytes(expected)
    clock = _MutableClock(0)
    client, context = _authenticate_path_fixture(
        monkeypatch, path, expected, clock
    )
    original_read = sc.os.read
    calls = 0

    def defective_read(descriptor, size):
        nonlocal calls
        calls += 1
        if defect == "early_eof":
            return original_read(descriptor, 3) if calls == 1 else b""
        if calls == 2:
            return b"x"
        return original_read(descriptor, size)

    monkeypatch.setattr(sc.os, "read", defective_read)
    with pytest.raises(sc.OrchestrationFailure, match="WORKTREE_SOURCE_INVALID"):
        sc._authenticate_path(
            client,
            context,
            "a" * 40,
            str(path),
            require_worktree=True,
        )
    assert calls == 2


def test_authenticated_worktree_deadline_equality_stops_after_current_read(
    tmp_path, monkeypatch
):
    expected = b"a" * (sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES + 1)
    path = tmp_path / "reviewed.py"
    path.write_bytes(expected)
    clock = _MutableClock(0)
    client, context = _authenticate_path_fixture(
        monkeypatch, path, expected, clock
    )
    original_read = sc.os.read
    read_sizes = []

    def deadline_read(descriptor, size):
        read_sizes.append(size)
        chunk = original_read(descriptor, size)
        clock.value = context.checkpoint_end_ns
        return chunk

    monkeypatch.setattr(sc.os, "read", deadline_read)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._authenticate_path(
            client,
            context,
            "a" * 40,
            str(path),
            require_worktree=True,
        )
    assert read_sizes == [sc.GITHUB_DEADLINE_WORK_CHUNK_BYTES]


class _SendAdvancesToDeadlineTLS:
    def __init__(self, clock: _MutableClock):
        self.clock = clock
        self.closed = False
        self.send_calls = 0

    def send(self, view):
        self.send_calls += 1
        self.clock.value = sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS
        return len(view)

    def close(self):
        self.closed = True


def test_request_total_includes_request_write_and_does_not_retry(monkeypatch):
    clock = _MutableClock(0)
    token_calls = []
    tls = _SendAdvancesToDeadlineTLS(clock)
    resolver_calls = []
    connect_calls = []
    monkeypatch.setattr(
        sc,
        "_resolve_api_github_addresses",
        lambda *args: resolver_calls.append(args) or (("AF_INET", "192.0.2.1", 443),),
    )
    monkeypatch.setattr(
        sc,
        "_connect_tls",
        lambda *args: connect_calls.append(args) or tls,
    )
    seams = sc.GithubTransportSeams(
        monotonic_ns=clock,
        ssl_context_factory=lambda: object(),
        token_reader=lambda: token_calls.append(True) or "synthetic-token",
    )
    client = sc.GithubClient(approved_executable="/runtime/python", seams=seams)
    context = sc.GithubDeadlineContext.begin_checkpoint(clock)
    with pytest.raises(sc.GitHubAuthorityFailure):
        client.get_json(sc.GITHUB_REPOSITORY_PATH, context=context)
    assert len(resolver_calls) == len(connect_calls) == len(token_calls) == 1
    assert tls.send_calls == 1
    assert tls.closed is True


def test_request_total_includes_json_semantic_validation(monkeypatch):
    clock = _MutableClock(0)

    class CompleteTLS:
        def __init__(self):
            self.chunks = [
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: 11\r\n\r\n"
                b'{"ok":true}',
                b"",
            ]
            self.closed = False

        def send(self, view):
            return len(view)

        def recv(self, size):
            return self.chunks.pop(0)

        def close(self):
            self.closed = True

    tls = CompleteTLS()
    monkeypatch.setattr(
        sc,
        "_resolve_api_github_addresses",
        lambda *args: (("AF_INET", "192.0.2.1", 443),),
    )
    monkeypatch.setattr(sc, "_connect_tls", lambda *args: tls)
    client = sc.GithubClient(
        approved_executable="/runtime/python",
        seams=sc.GithubTransportSeams(
            monotonic_ns=clock,
            ssl_context_factory=lambda: object(),
            token_reader=lambda: "synthetic-token",
        ),
    )

    def validator(value, status, headers, request_check):
        assert value == {"ok": True}
        assert status == 200
        clock.value = sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS
        request_check()
        return value

    with pytest.raises(sc.GitHubAuthorityFailure):
        client.get_json(
            sc.GITHUB_REPOSITORY_PATH,
            context=sc.GithubDeadlineContext.begin_checkpoint(clock),
            validator=validator,
        )
    assert tls.closed is True


class _PaginationClient:
    def __init__(self, pages, clock=lambda: 0):
        self._seams = SimpleNamespace(monotonic_ns=clock)
        self.pages = list(pages)
        self.targets = []

    def get_json(self, target, *, context, allowed_statuses, validator):
        self.targets.append(target)
        response, value = self.pages.pop(0)
        request_check = lambda: context.check(self._seams.monotonic_ns)
        return response, validator(
            value, response.status, response.headers, request_check
        )


def test_pagination_is_increasing_complete_same_origin_and_same_path():
    collection = sc.GITHUB_APPROVAL_COMMENTS_COLLECTION_PATH
    next_link = (
        f'<https://api.github.com{collection}?per_page=100&page=2>; rel="next"'
    ).encode("ascii")
    pages = [
        (sc.GithubHTTPResponse(200, {b"link": (next_link,)}, b""), [{"id": 1}]),
        (sc.GithubHTTPResponse(200, {}, b""), [{"id": 2}]),
    ]
    client = _PaginationClient(pages)
    result = sc.GithubClient.get_paginated_json(
        client,
        collection,
        context=sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        page_validator=lambda value, check: value,
    )
    assert result == ({"id": 1}, {"id": 2})
    assert client.targets == [
        f"{collection}?per_page=100&page=1",
        f"{collection}?per_page=100&page=2",
    ]
    evil = b'<https://evil.example/repos/atomatom148-dotcom/ATOM/issues/325/comments?per_page=100&page=2>; rel="next"'
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._next_page_from_link((evil,), collection, 1)


def test_pagination_total_includes_aggregate_semantic_validation():
    clock = _MutableClock(0)
    collection = sc.GITHUB_APPROVAL_COMMENTS_COLLECTION_PATH
    client = _PaginationClient(
        [(sc.GithubHTTPResponse(200, {}, b""), [{"id": 1}])],
        clock,
    )
    observed = []

    def validate_collection(items, paged_context):
        observed.append(items)
        clock.value = sc.GITHUB_PAGINATION_TOTAL_TIMEOUT_NS
        paged_context.check(clock)
        return items

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.GithubClient.get_paginated_json(
            client,
            collection,
            context=sc.GithubDeadlineContext.begin_checkpoint(clock),
            page_validator=lambda value, check: value,
            collection_validator=validate_collection,
        )
    assert observed == [({"id": 1},)]
    assert client.targets == [f"{collection}?per_page=100&page=1"]


def test_each_paginated_page_receives_a_fresh_subordinate_request_deadline(
    monkeypatch,
):
    clock = _MutableClock(0)
    collection = sc.GITHUB_APPROVAL_COMMENTS_COLLECTION_PATH
    page_two = (
        f"https://api.github.com{collection}?per_page=100&page=2"
    )
    bodies = (b'[{"id":1}]', b'[{"id":2}]')
    link = f'<{page_two}>; rel="next"'.encode("ascii")

    def response(body, link_value=None):
        headers = [
            b"HTTP/1.1 200 OK",
            b"Content-Type: application/json",
            f"Content-Length: {len(body)}".encode("ascii"),
        ]
        if link_value is not None:
            headers.append(b"Link: " + link_value)
        return b"\r\n".join(headers) + b"\r\n\r\n" + body

    class TLS:
        def __init__(self, raw):
            self.chunks = [raw, b""]
            self.closed = False

        def send(self, value):
            return len(value)

        def recv(self, size):
            return self.chunks.pop(0)

        def close(self):
            self.closed = True

    all_tls = [TLS(response(bodies[0], link)), TLS(response(bodies[1]))]
    tls_objects = list(all_tls)
    request_starts = []
    token_reads = []

    def resolve(*args):
        request_starts.append(clock.value)
        return (("AF_INET", "192.0.2.1", 443),)

    monkeypatch.setattr(sc, "_resolve_api_github_addresses", resolve)
    monkeypatch.setattr(sc, "_connect_tls", lambda *args: tls_objects.pop(0))
    client = sc.GithubClient(
        approved_executable="/runtime/python",
        seams=sc.GithubTransportSeams(
            monotonic_ns=clock,
            ssl_context_factory=lambda: object(),
            token_reader=lambda: token_reads.append(clock.value) or "synthetic-token",
        ),
    )
    validation_times = iter((59_000_000_000, 118_000_000_000))

    def page_validator(value, request_check):
        clock.value = next(validation_times)
        request_check()
        return value

    result = client.get_paginated_json(
        collection,
        context=sc.GithubDeadlineContext.begin_checkpoint(clock),
        page_validator=page_validator,
    )
    assert result == ({"id": 1}, {"id": 2})
    assert request_starts == [0, 59_000_000_000]
    assert token_reads == request_starts
    assert all(tls.closed for tls in all_tls)


def test_checkpoint_git_run_uses_exact_remaining_deadline_and_hardened_process(
    monkeypatch,
):
    clock = _MutableClock(7_000_000_000)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=12_000_000_000)
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return sc.subprocess.CompletedProcess(arguments, 0, stdout=b"proof\n")

    monkeypatch.setattr(sc.subprocess, "run", run)
    completed = sc._checkpoint_git_run(
        context,
        clock,
        "rev-parse",
        "HEAD",
        check=True,
    )
    assert completed.stdout == b"proof\n"
    assert calls == [
        (
            ("git", "-c", "credential.helper=", "rev-parse", "HEAD"),
            {
                "cwd": os.getcwd(),
                "stdin": sc.subprocess.DEVNULL,
                "stdout": sc.subprocess.PIPE,
                "stderr": sc.subprocess.DEVNULL,
                "check": True,
                "close_fds": True,
                "text": False,
                "timeout": 5.0,
                "env": {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
            },
        )
    ]


def test_checkpoint_git_run_cannot_finish_at_deadline_and_never_retries(
    monkeypatch,
):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=1_000_000_000)
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs["timeout"]))
        clock.value = context.checkpoint_end_ns
        return sc.subprocess.CompletedProcess(arguments, 0, stdout=b"proof")

    monkeypatch.setattr(sc.subprocess, "run", run)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._checkpoint_git_run(context, clock, "cat-file", "blob", check=True)
    assert calls == [
        (("git", "-c", "credential.helper=", "cat-file", "blob"), 1.0)
    ]


def test_checkpoint_git_timeout_is_sanitized_and_never_retried(monkeypatch):
    clock = _MutableClock(0)
    context = sc.GithubDeadlineContext(checkpoint_end_ns=2_000_000_000)
    calls = []

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs["timeout"]))
        raise sc.subprocess.TimeoutExpired(arguments, kwargs["timeout"])

    monkeypatch.setattr(sc.subprocess, "run", run)
    with pytest.raises(sc.OrchestrationFailure) as caught:
        sc._git_read(context, clock, "show", "HEAD:requirements.txt")
    assert str(caught.value) == "LOCAL_GIT_PROOF_FAILED"
    assert caught.value.__cause__ is None
    assert calls == [
        (
            (
                "git",
                "-c",
                "credential.helper=",
                "show",
                "HEAD:requirements.txt",
            ),
            2.0,
        )
    ]


@pytest.mark.parametrize(
    ("stage", "route"),
    [
        (sc.AuthorityStage.NEW_SEAL_BEFORE_EVIDENCE, "BLOCKED"),
        (
            sc.AuthorityStage.NEW_SEAL_AFTER_EVIDENCE_BEFORE_SEAL,
            "PRE-CELL INVALID (null seal)",
        ),
        (
            sc.AuthorityStage.SEALED_OR_ACCEPTED_RECOVERY_BEFORE_COMPLETE_CELLS,
            "PRE-CELL INVALID (consuming)",
        ),
        (
            sc.AuthorityStage.FINAL_AFTER_COMPLETE_TRUTHFUL_CELLS,
            "POST-EVALUATION AUTHORITY INVALID",
        ),
    ],
)
def test_github_deadline_and_authority_failures_route_by_stage(stage, route):
    assert sc.route_authority_failure(stage) == route


class _ResolverTestStream:
    def __init__(self, name, descriptor, events):
        self.name = name
        self.descriptor = descriptor
        self.events = events
        self.closed = False

    def fileno(self):
        self.events.append(f"{self.name}:fileno")
        return self.descriptor

    def close(self):
        self.events.append(f"{self.name}:close")
        self.closed = True


class _ResolverTestProcess:
    def __init__(self, events, *, pid=4321):
        self.events = events
        self.pid = pid
        self.stdin = _ResolverTestStream("stdin", 21, events)
        self.stdout = _ResolverTestStream("stdout", 22, events)
        self.exited = False

    def poll(self):
        self.events.append("poll")
        return 0 if self.exited else None

    def wait(self):
        self.events.append("wait")
        return 0

    def kill(self):
        self.events.append("kill")
        self.exited = True


class _ResolverReadySelector:
    def __init__(self, events):
        self.events = events

    def register(self, fileobj, events):
        self.events.append(("register", fileobj, events))

    def select(self, timeout):
        self.events.append(("select", timeout))
        return [] if timeout == 0 else [(object(), selectors.EVENT_READ)]

    def close(self):
        self.events.append("selector:close")


def _install_successful_resolver_process(monkeypatch):
    events = []
    process = _ResolverTestProcess(events)
    chunks = iter(
        (
            b'{"addresses":[["AF_INET","192.0.2.1",443]]}\n',
            b"",
        )
    )
    popen_calls = []

    def popen(arguments, **kwargs):
        events.append("popen")
        popen_calls.append((arguments, kwargs))
        return process

    def read(descriptor, size):
        assert descriptor == process.stdout.descriptor
        assert size == 4096
        events.append("read")
        return next(chunks)

    def write(descriptor, value):
        assert descriptor == process.stdin.descriptor
        assert value == b"\x01"
        events.append("ack")
        process.exited = True
        return 1

    def close(descriptor):
        assert descriptor == 23
        events.append("pidfd:close")

    monkeypatch.setattr(sc.os, "read", read)
    monkeypatch.setattr(sc.os, "write", write)
    monkeypatch.setattr(
        sc.os,
        "set_blocking",
        lambda descriptor, enabled: events.append(
            ("set_blocking", descriptor, enabled)
        ),
    )
    monkeypatch.setattr(sc.os, "close", close)
    seams = sc.GithubTransportSeams(
        monotonic_ns=lambda: 0,
        selector_factory=lambda: _ResolverReadySelector(events),
        popen_factory=popen,
        pidfd_open=lambda pid, flags: (
            events.append(("pidfd_open", pid, flags)) or 23
        ),
        child_map_auditor=lambda pid, pidfd, end, clock: events.append(
            ("audit", pid, pidfd, end, clock())
        ),
        token_reader=lambda: (_ for _ in ()).throw(
            AssertionError("resolver must not read the token")
        ),
        socket_factory=lambda *args: (_ for _ in ()).throw(
            AssertionError("resolver must not open a network socket")
        ),
        fatal_termination=lambda code: (_ for _ in ()).throw(
            AssertionError(f"unexpected fatal termination {code}")
        ),
    )
    return events, process, popen_calls, seams


def test_resolver_success_closes_child_streams_and_pidfd_before_return(
    monkeypatch,
):
    events, process, popen_calls, seams = _install_successful_resolver_process(
        monkeypatch
    )
    context = sc.GithubDeadlineContext(checkpoint_end_ns=1_000_000)
    addresses = sc._resolve_api_github_addresses(
        seams,
        context,
        1_000_000,
        os.path.realpath(sys.executable),
    )
    events.append("returned")
    assert addresses == (("AF_INET", "192.0.2.1", 443),)
    assert len(popen_calls) == 1
    arguments, kwargs = popen_calls[0]
    assert arguments == (
        os.path.realpath(sys.executable),
        "-I",
        "-S",
        "-B",
        "-X",
        "pycache_prefix=/dev/null/atom-v1b-no-pyc",
        "-c",
        sc._RESOLVER_CHILD_SOURCE,
    )
    assert kwargs == {
        "stdin": sc.subprocess.PIPE,
        "stdout": sc.subprocess.PIPE,
        "stderr": sc.subprocess.DEVNULL,
        "close_fds": True,
        "env": {"PYTHON_VERSION": "3.14.3"},
        "bufsize": 0,
        "text": False,
    }
    assert process.stdin.closed is process.stdout.closed is True
    assert events.index("ack") < events.index("stdin:close")
    assert events.index("stdin:close") < events.index("wait")
    assert events.index("wait") < events.index("stdout:close")
    assert events.index("stdout:close") < events.index("pidfd:close")
    assert events.index("pidfd:close") < events.index("returned")


def test_late_popen_is_quarantined_before_ack_token_or_socket(
    monkeypatch,
):
    clock = _MutableClock(0)
    events = []
    process = _ResolverTestProcess(events)

    def late_popen(*args, **kwargs):
        events.append("popen")
        clock.value = sc.GITHUB_CONNECT_TIMEOUT_NS
        return process

    monkeypatch.setattr(
        sc,
        "_kill_reap",
        lambda observed, *, fatal_termination: events.append(
            ("quarantined", observed, fatal_termination)
        ),
    )
    monkeypatch.setattr(
        sc.os,
        "write",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("late resolver must not be acknowledged")
        ),
    )
    fatal = lambda code: (_ for _ in ()).throw(AssertionError(code))
    seams = sc.GithubTransportSeams(
        monotonic_ns=clock,
        popen_factory=late_popen,
        token_reader=lambda: (_ for _ in ()).throw(
            AssertionError("late resolver must not expose token")
        ),
        socket_factory=lambda *args: (_ for _ in ()).throw(
            AssertionError("late resolver must not create socket")
        ),
        fatal_termination=fatal,
    )
    client = sc.GithubClient(
        approved_executable=os.path.realpath(sys.executable),
        seams=seams,
        ssl_context=object(),
    )
    with pytest.raises(sc.GitHubAuthorityFailure):
        client.get_json(
            sc.GITHUB_REPOSITORY_PATH,
            context=sc.GithubDeadlineContext.begin_checkpoint(clock),
        )
    assert events == ["popen", ("quarantined", process, fatal)]


def test_unresolved_resolver_reap_invokes_nonreturning_fatal_termination(
    monkeypatch,
):
    events = []

    class UnreapableProcess(_ResolverTestProcess):
        def wait(self):
            events.append("wait")
            raise OSError("synthetic wait failure")

    class FatalTermination(BaseException):
        pass

    process = UnreapableProcess(events, pid=9876)
    monkeypatch.setattr(
        sc.os,
        "waitpid",
        lambda pid, flags: (
            events.append(("waitpid", pid, flags)),
            (_ for _ in ()).throw(OSError("synthetic waitpid failure")),
        )[1],
    )

    def fatal(code):
        events.append(("fatal", code))
        raise FatalTermination

    with pytest.raises(FatalTermination):
        sc._kill_reap(process, fatal_termination=fatal)
    assert events == [
        "stdin:close",
        "poll",
        "kill",
        "wait",
        ("waitpid", 9876, 0),
        ("fatal", 1),
    ]
    assert process.stdout.closed is False


def _resolver_audit_fixture(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    executable = tmp_path / "python3.14"
    native = tmp_path / "libm.so.6"
    executable.write_bytes(b"synthetic-python-executable")
    native.write_bytes(b"synthetic-libm")
    os.chmod(executable, 0o755)
    executable_path = str(executable.resolve())
    native_path = str(native.resolve())
    executable_record = sc.FileRecord(
        executable_path,
        executable.stat().st_size,
        hashlib.sha256(executable.read_bytes()).hexdigest(),
    )
    native_record = sc.FileRecord(
        native_path,
        native.stat().st_size,
        hashlib.sha256(native.read_bytes()).hexdigest(),
    )
    components = sc.ArtifactComponents(
        executable_record.sha256,
        sc.canonical_sha256([]),
        sc.canonical_sha256([]),
        sc.canonical_sha256([native_record.public()]),
    )
    roots = sc.RuntimeRoots(
        executable_path,
        str(tmp_path / "stdlib"),
        str(tmp_path / "stdlib"),
        str(tmp_path / "site"),
        str(tmp_path / "site"),
    )
    plan = sc.RuntimeArtifactPlan(
        roots=roots,
        dependency_versions=(),
        stdlib_files=(),
        dependency_files=(),
        native_files=(sc.FileCandidate(native_path, native_path),),
        mappings=(),
        module_names=frozenset({"quant.volatility_scorecard"}),
    )
    measurement = sc.RuntimeMeasurement(
        components=components,
        runtime_artifact_sha256=sc.canonical_sha256(components.public()),
        libm_dispatch=None,
        libm_dispatch_sha256=None,
        dependency_versions=plan.dependency_versions,
        module_names=plan.module_names,
        python_executable_record=executable_record,
        native_records=(native_record,),
    )
    proc_root = tmp_path / "proc"
    child = proc_root / "4321"
    child.mkdir(parents=True)
    (child / "exe").symlink_to(executable)
    maps = (
        f"1000-2000 r-xp 00000000 08:01 1 {executable_path}\n"
        f"2000-3000 r-xp 00000000 08:01 2 {native_path}\n"
        "ffffffffff600000-ffffffffff601000 --xp 00000000 00:00 0 [vsyscall]\n"
    ).encode()
    (child / "maps").write_bytes(maps)
    pidfd_path = tmp_path / "pidfd"
    pidfd_path.write_bytes(b"live")
    pidfd = os.open(pidfd_path, os.O_RDONLY)
    return SimpleNamespace(
        plan=plan,
        measurement=measurement,
        baseline=sc._resolver_child_audit_baseline(plan, measurement),
        proc_root=str(proc_root.resolve()),
        child=child,
        maps=maps,
        pidfd=pidfd,
        executable=executable,
        native=native,
    )


def _audit_resolver_fixture(fixture, *, file_access=None, liveness=None):
    return sc._audit_resolver_child_maps(
        fixture.baseline,
        4321,
        fixture.pidfd,
        10_000,
        lambda: 0,
        proc_root=fixture.proc_root,
        file_access=file_access,
        pidfd_liveness_check=(lambda *args: None) if liveness is None else liveness,
    )


def test_resolver_child_map_audit_accepts_only_stable_approved_executable_subset(
    tmp_path,
):
    fixture = _resolver_audit_fixture(tmp_path)
    try:
        _audit_resolver_fixture(fixture)
    finally:
        os.close(fixture.pidfd)


def test_resolver_child_map_audit_rejects_changed_or_unreadable_maps(
    tmp_path, monkeypatch
):
    fixture = _resolver_audit_fixture(tmp_path)
    try:
        observed = iter(
            (
                fixture.maps,
                fixture.maps + b"4000-5000 r--p 00000000 00:00 0 [heap]\n",
            )
        )
        real_read = sc._read_complete_proc_file

        def changing_read(path, *args):
            if path.endswith("/maps"):
                return next(observed)
            return real_read(path, *args)

        monkeypatch.setattr(sc, "_read_complete_proc_file", changing_read)
        with pytest.raises(sc.GitHubAuthorityFailure):
            _audit_resolver_fixture(fixture)
    finally:
        os.close(fixture.pidfd)

    monkeypatch.setattr(sc, "_read_complete_proc_file", real_read)
    fixture = _resolver_audit_fixture(tmp_path / "unreadable")
    try:
        (fixture.child / "maps").unlink()
        with pytest.raises(sc.GitHubAuthorityFailure):
            _audit_resolver_fixture(fixture)
    finally:
        os.close(fixture.pidfd)


@pytest.mark.parametrize(
    "extra_line",
    [
        "3000-4000 r-xp 00000000 08:01 3 {extra}\n",
        "3000-4000 r-xp 00000000 00:00 0 [anon:malicious]\n",
        "3000-4000 r-xp 00000000 08:01 3 {native} (deleted)\n",
    ],
)
def test_resolver_child_map_audit_rejects_extra_anonymous_or_deleted_executable(
    tmp_path, extra_line
):
    fixture = _resolver_audit_fixture(tmp_path)
    extra = tmp_path / "libextra.so"
    extra.write_bytes(b"not-approved")
    rendered = extra_line.format(extra=extra.resolve(), native=fixture.native.resolve())
    special = b"ffffffffff600000-ffffffffff601000"
    split = fixture.maps.index(special)
    (fixture.child / "maps").write_bytes(
        fixture.maps[:split] + rendered.encode() + fixture.maps[split:]
    )
    try:
        with pytest.raises(sc.GitHubAuthorityFailure):
            _audit_resolver_fixture(fixture)
    finally:
        os.close(fixture.pidfd)


def test_resolver_child_map_audit_rejects_wrong_exe_digest_and_signaled_pidfd(
    tmp_path,
):
    fixture = _resolver_audit_fixture(tmp_path)
    other = tmp_path / "other-python"
    other.write_bytes(b"other")
    (fixture.child / "exe").unlink()
    (fixture.child / "exe").symlink_to(other)
    try:
        with pytest.raises(sc.GitHubAuthorityFailure):
            _audit_resolver_fixture(fixture)
    finally:
        os.close(fixture.pidfd)

    fixture = _resolver_audit_fixture(tmp_path / "digest")
    wrong_access = _ByteAccess(
        {
            str(fixture.executable.resolve()): b"different-executable-bytes",
            str(fixture.native.resolve()): fixture.native.read_bytes(),
        }
    )
    try:
        with pytest.raises(sc.GitHubAuthorityFailure):
            _audit_resolver_fixture(fixture, file_access=wrong_access)
        with pytest.raises(sc.GitHubAuthorityFailure):
            _audit_resolver_fixture(
                fixture,
                liveness=lambda *args: (_ for _ in ()).throw(
                    sc.GitHubAuthorityFailure()
                ),
            )
    finally:
        os.close(fixture.pidfd)


def test_frozen_github_client_constructor_wires_only_approved_child_auditor(
    tmp_path, monkeypatch
):
    fixture = _resolver_audit_fixture(tmp_path)
    sentinel = object()
    seen = []

    def auditor_factory(plan, measurement):
        seen.append((plan, measurement))
        return sentinel

    fake_seams = SimpleNamespace(
        child_map_auditor=sentinel,
        ssl_context_factory=lambda: object(),
    )
    frozen_context = object()
    monkeypatch.setattr(sc, "make_production_child_map_auditor", auditor_factory)
    monkeypatch.setattr(
        sc,
        "GithubTransportSeams",
        lambda *, child_map_auditor: (
            fake_seams
            if child_map_auditor is sentinel
            else (_ for _ in ()).throw(AssertionError("wrong auditor"))
        ),
    )
    try:
        client = sc.GithubClient.for_frozen_runtime(
            plan=fixture.plan,
            measurement=fixture.measurement,
            ssl_context=frozen_context,
        )
        assert seen == [(fixture.plan, fixture.measurement)]
        assert client._approved_executable == str(fixture.executable.resolve())
        assert client._seams.child_map_auditor is sentinel
        assert client._ssl_context is frozen_context
    finally:
        os.close(fixture.pidfd)


def test_resolver_audit_baseline_rejects_unapproved_native_record(tmp_path):
    fixture = _resolver_audit_fixture(tmp_path)
    try:
        extra = sc.FileRecord("/runtime/libextra.so", 1, "f" * 64)
        changed = replace(
            fixture.measurement,
            native_records=fixture.measurement.native_records + (extra,),
        )
        with pytest.raises(sc.GitHubAuthorityFailure):
            sc._resolver_child_audit_baseline(fixture.plan, changed)
    finally:
        os.close(fixture.pidfd)


def _window_approval_projection(
    *,
    ruleset_id: int = 501,
    execution_sha: str = "b" * 40,
    manifest_id: str = "v1b-early-4",
    opened_at: str = "2026-09-07T12:00:00.000000Z",
):
    return {
        "schema_version": "ATOM-V1B-NO-MAIN-UPDATE-WINDOW-1",
        "repository": sc.GITHUB_REPOSITORY,
        "repository_id": sc.GITHUB_REPOSITORY_ID,
        "ruleset_id": ruleset_id,
        "name": "ATOM-V1B-NO-MAIN-UPDATE-1",
        "target": "branch",
        "source_type": "Repository",
        "source": sc.GITHUB_REPOSITORY,
        "enforcement": "active",
        "conditions": {
            "ref_name": {"include": ["refs/heads/main"], "exclude": []}
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}},
        ],
        "bypass_actors": [],
        "created_at": "2026-09-07T12:00:00Z",
        "updated_at": "2026-09-07T12:00:00Z",
        "execution_source_sha": execution_sha,
        "manifest_id": manifest_id,
        "opened_at_utc": opened_at,
    }


def _ruleset_readback(window, *, include_bypass=True):
    value = {
        "id": window["ruleset_id"],
        "name": window["name"],
        "target": window["target"],
        "source_type": window["source_type"],
        "source": window["source"],
        "enforcement": window["enforcement"],
        "conditions": window["conditions"],
        "rules": window["rules"],
        "created_at": window["created_at"],
        "updated_at": window["updated_at"],
    }
    if include_bypass:
        value["bypass_actors"] = []
    return value


def test_no_ref_window_requires_exact_update_delete_force_push_rules_and_no_bypass():
    window = _window_approval_projection()
    assert sc._validate_window(window) == window
    sc.validate_ruleset_projection(_ruleset_readback(window), window)
    # Metadata-read responses may omit the write-authorized bypass list.
    sc.validate_ruleset_projection(
        _ruleset_readback(window, include_bypass=False), window
    )
    for mutation in (
        {**window, "bypass_actors": [{"actor_type": "OrganizationAdmin"}]},
        {**window, "enforcement": "evaluate"},
        {**window, "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}},
        {**window, "rules": window["rules"][:-1]},
    ):
        with pytest.raises(sc.GitHubAuthorityFailure):
            sc._validate_window(mutation)
    bad_readback = _ruleset_readback(window)
    bad_readback["bypass_actors"] = [{}]
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.validate_ruleset_projection(bad_readback, window)


def test_repository_and_ref_predicates_require_public_exact_main_at_e_not_descendant():
    repository = {
        "id": sc.GITHUB_REPOSITORY_ID,
        "full_name": sc.GITHUB_REPOSITORY,
        "default_branch": "main",
        "private": False,
        "owner": {"login": sc.GITHUB_OWNER_LOGIN},
    }
    sc.validate_repository_metadata(repository)
    ref = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": "b" * 40}}
    sc.validate_main_ref(ref, "b" * 40)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.validate_main_ref(ref, "c" * 40)
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.validate_repository_metadata({**repository, "default_branch": "develop"})
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.validate_repository_metadata({**repository, "private": True})


def _approval_comment(
    *,
    comment_id: int,
    ruleset_id: int,
    execution_sha: str = "b" * 40,
    opened_at: str,
    created_at: str,
    review_id: int,
    schema_version: str = sc.OPERATIONAL_APPROVAL_SCHEMA_VERSION,
):
    window = _window_approval_projection(
        ruleset_id=ruleset_id,
        execution_sha=execution_sha,
        opened_at=opened_at,
    )
    payload = {
        "schema_version": schema_version,
        "provenance": {"execution_source_sha": execution_sha},
        "control_plane_evidence_sha256": "d" * 64,
    }
    approval = sc.ApprovalComment(
        comment_id=comment_id,
        created_at=created_at,
        canonical_body=(f"approval-{comment_id}\n").encode(),
        payload=payload,
        window=window,
        review_comment_id=review_id,
        reviewer_user_id=999,
        reviewer_login="independent-reviewer",
    )
    review = sc.ReviewComment(
        comment_id=review_id,
        author_id=999,
        author_login="independent-reviewer",
        created_at="2026-09-07T10:00:00Z",
        canonical_body=(f"review-{review_id}\n").encode(),
        approval_payload_sha256=sc.canonical_sha256(payload),
    )
    return approval, review


class _CapturedPageValidators(RuntimeError):
    pass


class _CommentPageCaptureClient:
    def __init__(self, clock):
        self._seams = SimpleNamespace(monotonic_ns=clock)
        self.page_validator = None
        self.collection_validator = None

    def get_json(
        self,
        target,
        *,
        context,
        allowed_statuses=frozenset({200}),
        validator=None,
    ):
        if target == sc.GITHUB_REPOSITORY_PATH:
            value = {
                "id": sc.GITHUB_REPOSITORY_ID,
                "full_name": sc.GITHUB_REPOSITORY,
                "default_branch": "main",
                "private": False,
                "owner": {"login": sc.GITHUB_OWNER_LOGIN},
            }
        elif target == sc.GITHUB_MAIN_REF_PATH:
            value = {
                "ref": "refs/heads/main",
                "object": {"type": "commit", "sha": "b" * 40},
            }
        else:
            raise AssertionError("comment validator capture stops before rulesets")
        response = sc.GithubHTTPResponse(200, {}, b"")
        if validator is not None:
            value = validator(
                value,
                response.status,
                response.headers,
                lambda: context.check(self._seams.monotonic_ns),
            )
        return response, value

    def get_paginated_json(
        self,
        collection_path,
        *,
        context,
        page_validator,
        collection_validator,
    ):
        assert collection_path == sc.GITHUB_APPROVAL_COMMENTS_COLLECTION_PATH
        self.page_validator = page_validator
        self.collection_validator = collection_validator
        raise _CapturedPageValidators


def test_comment_item_semantics_use_originating_request_checker():
    clock = _MutableClock(0)
    client = _CommentPageCaptureClient(clock)
    with pytest.raises(_CapturedPageValidators):
        sc.verify_github_checkpoint(
            client=client,
            expected_execution_sha="b" * 40,
            manifest_id="v1b-early-4",
            artifact_components_validator=lambda value: value,
            immutable_fact_validator=lambda *args: None,
        )
    assert client.page_validator is not None
    unrelated = {"id": 1, "body": "ordinary unrelated comment"}
    checks = []
    assert client.page_validator(
        [unrelated], lambda: checks.append(len(checks)) or 0
    ) == ()
    assert len(checks) >= 4

    request_end = sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS
    calls = 0

    def expiring_request_check():
        nonlocal calls
        calls += 1
        if calls == 3:
            clock.value = request_end
        return sc.GithubDeadlineContext(
            checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS
        ).check(clock, request_end)

    with pytest.raises(sc.GitHubAuthorityFailure):
        client.page_validator([unrelated], expiring_request_check)
    assert calls == 3


def test_cross_page_comment_traversal_uses_pagination_checker():
    clock = _MutableClock(0)
    client = _CommentPageCaptureClient(clock)
    with pytest.raises(_CapturedPageValidators):
        sc.verify_github_checkpoint(
            client=client,
            expected_execution_sha="b" * 40,
            manifest_id="v1b-early-4",
            artifact_components_validator=lambda value: value,
            immutable_fact_validator=lambda *args: None,
        )
    approval, _review = _approval_comment(
        comment_id=20,
        ruleset_id=501,
        opened_at="2026-09-07T12:00:00.000000Z",
        created_at="2026-09-07T12:05:00Z",
        review_id=19,
    )
    calls = 0

    def pagination_clock():
        nonlocal calls
        calls += 1
        return (
            sc.GITHUB_PAGINATION_TOTAL_TIMEOUT_NS
            if calls == 2
            else 0
        )

    client._seams.monotonic_ns = pagination_clock
    paged = sc.GithubDeadlineContext(
        checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS,
        pagination_end_ns=sc.GITHUB_PAGINATION_TOTAL_TIMEOUT_NS,
    )
    assert client.collection_validator is not None
    with pytest.raises(sc.GitHubAuthorityFailure):
        client.collection_validator((approval, approval), paged)
    assert calls == 2


class _AssociatedPRPageCaptureClient:
    def __init__(self):
        self.page_validator = None

    def get_paginated_json(
        self,
        collection_path,
        *,
        context,
        page_validator,
        collection_validator,
    ):
        self.page_validator = page_validator
        raise _CapturedPageValidators


def test_associated_pr_item_semantics_use_originating_request_checker():
    client = _AssociatedPRPageCaptureClient()
    with pytest.raises(_CapturedPageValidators):
        sc._associated_merged_pr(
            client,
            sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
            "b" * 40,
            expected_number=325,
        )
    assert client.page_validator is not None
    item = {
        "number": 325,
        "merge_commit_sha": "b" * 40,
        "merged_at": "2026-09-07T12:05:00Z",
    }
    checks = []
    assert client.page_validator(
        [item], lambda: checks.append(len(checks)) or 0
    ) == (item,)
    assert len(checks) >= 4

    clock = _MutableClock(0)
    request_end = sc.GITHUB_REQUEST_TOTAL_TIMEOUT_NS
    calls = 0

    def expiring_request_check():
        nonlocal calls
        calls += 1
        if calls == 3:
            clock.value = request_end
        return sc.GithubDeadlineContext(
            checkpoint_end_ns=sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS
        ).check(clock, request_end)

    with pytest.raises(sc.GitHubAuthorityFailure):
        client.page_validator([item], expiring_request_check)
    assert calls == 3


class _RulesetClassificationClient:
    def __init__(self, status_by_id, windows):
        self._seams = SimpleNamespace(monotonic_ns=lambda: 0)
        self.status_by_id = status_by_id
        self.windows = windows
        self.calls = []

    def get_json(self, target, *, context, allowed_statuses, validator=None):
        self.calls.append(target)
        ruleset_id = int(target.split("/rulesets/", 1)[1].split("?", 1)[0])
        status = self.status_by_id[ruleset_id]
        value = _ruleset_readback(self.windows[ruleset_id]) if status == 200 else {}
        response = sc.GithubHTTPResponse(status, {}, b"")
        if validator is not None:
            value = validator(
                value,
                status,
                response.headers,
                lambda: context.check(self._seams.monotonic_ns),
            )
        return response, value


def test_approval_classification_allows_one_current_and_only_older_closed_windows():
    old, old_review = _approval_comment(
        comment_id=10,
        ruleset_id=500,
        opened_at="2026-09-07T11:00:00.000000Z",
        created_at="2026-09-07T11:05:00Z",
        review_id=9,
    )
    current, current_review = _approval_comment(
        comment_id=20,
        ruleset_id=501,
        opened_at="2026-09-07T12:00:00.000000Z",
        created_at="2026-09-07T12:05:00Z",
        review_id=19,
    )
    windows = {500: old.window, 501: current.window}
    client = _RulesetClassificationClient({500: 404, 501: 200}, windows)
    selection = sc.classify_v1b_approvals(
        client=client,
        context=sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        approvals=[old, current],
        reviews={9: old_review, 19: current_review},
        expected_execution_sha="b" * 40,
        manifest_id="v1b-early-4",
    )
    assert selection.current is current
    assert [item.state for item in selection.repository_fingerprints] == [
        sc.ApprovalState.HISTORICAL_CLOSED,
        sc.ApprovalState.CURRENT,
    ]


def test_approval_classification_examines_closed_v1_but_never_selects_it_current():
    old, old_review = _approval_comment(
        comment_id=10,
        ruleset_id=500,
        opened_at="2026-09-07T11:00:00.000000Z",
        created_at="2026-09-07T11:05:00Z",
        review_id=9,
        schema_version="ATOM-V1B-OPERATIONAL-APPROVAL-PAYLOAD-1",
    )
    current, current_review = _approval_comment(
        comment_id=20,
        ruleset_id=501,
        opened_at="2026-09-07T12:00:00.000000Z",
        created_at="2026-09-07T12:05:00Z",
        review_id=19,
    )
    windows = {500: old.window, 501: current.window}
    selection = sc.classify_v1b_approvals(
        client=_RulesetClassificationClient({500: 404, 501: 200}, windows),
        context=sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        approvals=[old, current],
        reviews={9: old_review, 19: current_review},
        expected_execution_sha="b" * 40,
        manifest_id="v1b-early-4",
    )
    assert selection.current is current
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.classify_v1b_approvals(
            client=_RulesetClassificationClient({500: 200}, {500: old.window}),
            context=sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
            approvals=[old],
            reviews={9: old_review},
            expected_execution_sha="b" * 40,
            manifest_id="v1b-early-4",
        )


def test_approval_classification_rejects_zero_multiple_or_wrong_e_current_windows():
    first, first_review = _approval_comment(
        comment_id=10,
        ruleset_id=500,
        opened_at="2026-09-07T11:00:00.000000Z",
        created_at="2026-09-07T11:05:00Z",
        review_id=9,
    )
    second, second_review = _approval_comment(
        comment_id=20,
        ruleset_id=501,
        opened_at="2026-09-07T12:00:00.000000Z",
        created_at="2026-09-07T12:05:00Z",
        review_id=19,
    )
    reviews = {9: first_review, 19: second_review}
    windows = {500: first.window, 501: second.window}
    context = sc.GithubDeadlineContext.begin_checkpoint(lambda: 0)
    for statuses in ({500: 404, 501: 404}, {500: 200, 501: 200}):
        with pytest.raises(sc.GitHubAuthorityFailure):
            sc.classify_v1b_approvals(
                client=_RulesetClassificationClient(statuses, windows),
                context=context,
                approvals=[first, second],
                reviews=reviews,
                expected_execution_sha="b" * 40,
                manifest_id="v1b-early-4",
            )
    wrong, wrong_review = _approval_comment(
        comment_id=30,
        ruleset_id=502,
        execution_sha="c" * 40,
        opened_at="2026-09-07T13:00:00.000000Z",
        created_at="2026-09-07T13:05:00Z",
        review_id=29,
    )
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.classify_v1b_approvals(
            client=_RulesetClassificationClient({502: 200}, {502: wrong.window}),
            context=context,
            approvals=[wrong],
            reviews={29: wrong_review},
            expected_execution_sha="b" * 40,
            manifest_id="v1b-early-4",
        )


class _CheckpointOrderClient:
    def __init__(self, selection, clock, events):
        self._seams = SimpleNamespace(monotonic_ns=clock)
        self.selection = selection
        self.events = events

    def get_json(
        self,
        target,
        *,
        context,
        allowed_statuses=frozenset({200}),
        validator=None,
    ):
        if target == sc.GITHUB_REPOSITORY_PATH:
            self.events.append("repository")
            value = {
                "id": sc.GITHUB_REPOSITORY_ID,
                "full_name": sc.GITHUB_REPOSITORY,
                "default_branch": "main",
                "private": False,
                "owner": {"login": sc.GITHUB_OWNER_LOGIN},
            }
        elif target == sc.GITHUB_MAIN_REF_PATH:
            self.events.append("main_ref")
            value = {
                "ref": "refs/heads/main",
                "object": {"type": "commit", "sha": "b" * 40},
            }
        else:
            self.events.append("ruleset")
            value = _ruleset_readback(self.selection.current.window)
        response = sc.GithubHTTPResponse(200, {}, b"")
        if validator is not None:
            value = validator(
                value,
                response.status,
                response.headers,
                lambda: context.check(self._seams.monotonic_ns),
            )
        return response, value

    def get_paginated_json(
        self,
        collection_path,
        *,
        context,
        page_validator,
        collection_validator,
    ):
        self.events.append("approval_comments")
        assert collection_path == sc.GITHUB_APPROVAL_COMMENTS_COLLECTION_PATH
        assert collection_validator is not None
        context.check(self._seams.monotonic_ns)
        return self.selection


def _checkpoint_order_fixture(clock, events):
    approval, review = _approval_comment(
        comment_id=20,
        ruleset_id=501,
        opened_at="2026-09-07T12:00:00.000000Z",
        created_at="2026-09-07T12:05:00Z",
        review_id=19,
    )
    selection = sc.ApprovalSelection(
        current=approval,
        current_review=review,
        repository_fingerprints=(
            sc.ApprovalFingerprint(
                approval.comment_id,
                501,
                sc.ApprovalState.CURRENT,
                approval.body_sha256,
            ),
        ),
    )
    return _CheckpointOrderClient(selection, clock, events)


def test_initial_approval_trust_correlation_precedes_every_other_github_endpoint():
    clock = _MutableClock(0)
    events = []
    client = _checkpoint_order_fixture(clock, events)
    trust = _synthetic_github_tls_trust().public()
    client.selection.current.payload["provenance"]["github_tls_trust"] = trust
    snapshot = sc.verify_github_checkpoint(
        client=client,
        expected_execution_sha="b" * 40,
        manifest_id="v1b-early-4",
        artifact_components_validator=lambda value: value,
        immutable_fact_validator=lambda *args: None,
        local_tls_trust=trust,
    )
    assert snapshot.selection is client.selection
    assert events[0] == "approval_comments"
    assert events[1:] == [
        "repository",
        "main_ref",
        "ruleset",
        "ruleset",
        "main_ref",
    ]

    events.clear()
    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.verify_github_checkpoint(
            client=client,
            expected_execution_sha="b" * 40,
            manifest_id="v1b-early-4",
            artifact_components_validator=lambda value: value,
            immutable_fact_validator=lambda *args: None,
            local_tls_trust={**trust, "cafile_sha256": "0" * 64},
        )
    assert events == ["approval_comments"]


def test_final_runtime_finalizer_is_inside_closing_github_checkpoint():
    clock = _MutableClock(0)
    events = []
    client = _checkpoint_order_fixture(clock, events)

    def immutable_validator(client, context, execution_sha):
        events.append("immutable_source")
        assert execution_sha == "b" * 40
        context.check(clock)

    def finalizer(selection, context):
        events.append("runtime_finalizer")
        assert selection is client.selection
        context.check(clock)

    snapshot = sc.verify_github_checkpoint(
        client=client,
        expected_execution_sha="b" * 40,
        manifest_id="v1b-early-4",
        artifact_components_validator=lambda value: value,
        immutable_fact_validator=immutable_validator,
        finalizer=finalizer,
    )
    assert snapshot.selection is client.selection
    assert events == [
        "approval_comments",
        "repository",
        "main_ref",
        "ruleset",
        "immutable_source",
        "ruleset",
        "main_ref",
        "runtime_finalizer",
    ]


def test_final_runtime_finalizer_cannot_escape_checkpoint_deadline():
    clock = _MutableClock(0)
    events = []
    client = _checkpoint_order_fixture(clock, events)

    def finalizer(selection, context):
        events.append("runtime_finalizer")
        assert selection is client.selection
        clock.value = sc.GITHUB_CHECKPOINT_TOTAL_TIMEOUT_NS

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc.verify_github_checkpoint(
            client=client,
            expected_execution_sha="b" * 40,
            manifest_id="v1b-early-4",
            artifact_components_validator=lambda value: value,
            immutable_fact_validator=lambda client, context, sha: events.append(
                "immutable_source"
            ),
            finalizer=finalizer,
        )
    assert events[-1] == "runtime_finalizer"


# ---------------------------------------------------------------------------
# Amendment 2A identity, seal, and receipt schemas
# ---------------------------------------------------------------------------


def _authority_proof():
    table_true = {name: True for name in sc.SIX_TABLES}
    table_false = {name: False for name in sc.SIX_TABLES}
    return {
        "current_user": sc.READER_ROLE,
        "session_user": sc.READER_ROLE,
        "dsn_login_user": sc.READER_ROLE,
        "dsn_password_present": True,
        "dsn_password_fallbacks_absent": True,
        "dsn_sslmode": "verify-full",
        "dsn_sslrootcert": sc.CA_REPOSITORY_PATH,
        "sslrootcert_sha256": sc.CA_SHA256,
        "dsn_sslcertmode": "disable",
        "dsn_require_auth": "scram-sha-256",
        "dsn_tls_fallbacks_absent": True,
        "tls_active": True,
        "dsn_identity_overrides_absent": True,
        "current_database": "postgres",
        "database_owner": "postgres",
        "database_create": False,
        "database_temporary": True,
        "database_temporary_public_only": True,
        "session_temp_schema_created": False,
        "effective_host": sc.DIRECT_HOST,
        "effective_port": 5432,
        "project_binding_verified": True,
        "schema_public_usage": True,
        "schema_public_create": False,
        "non_system_schema_create_privilege_count": 0,
        "schema_atom_v9_internal_usage": True,
        "proof_functions_execute": {name: True for name in sc.PROOF_FUNCTIONS},
        "proof_function_definitions": sc.json_clone(sc.EXPECTED_PROOF_DEFINITIONS),
        "non_system_security_definer_execute_privilege_count": 0,
        "reader_role_attributes": {
            "rolcanlogin": True,
            "rolinherit": False,
            "rolsuper": False,
            "rolcreatedb": False,
            "rolcreaterole": False,
            "rolreplication": False,
            "rolbypassrls": False,
        },
        "reader_role_memberships": [],
        "six_tables_select": table_true,
        "six_tables_insert": table_false,
        "six_tables_update": table_false,
        "six_tables_delete": table_false,
        "six_tables_truncate": table_false,
        "non_system_relation_write_privilege_count": 0,
        "six_tables_rls_enabled": table_true,
        "six_tables_permissive_full_read": table_true,
        "six_tables_restrictive_select": table_false,
        "transaction_isolation": "repeatable read",
        "read_only_transaction": True,
        "verification_status": "PASS",
    }


def _runtime_identity():
    dependency_versions = {
        "exchange-calendars": "4.13.2",
        "korean-lunar-calendar": "0.3.1",
        "numpy": "2.4.2",
        "pandas": "3.0.0",
        "psycopg": "3.3.5",
        "psycopg-binary": "3.3.5",
        "pyluach": "2.3.0",
        "python-dateutil": "2.9.0.post0",
        "six": "1.17.0",
        "toolz": "1.1.0",
        "tzdata": "2025.3",
    }
    components = {
        "python_executable_sha256": "1" * 64,
        "stdlib_tree_sha256": "2" * 64,
        "dependency_tree_sha256": "3" * 64,
        "loaded_native_tree_sha256": "4" * 64,
    }
    dispatch = {
        "exp": {
            "loaded_native_path": "/usr/lib/x86_64-linux-gnu/libm.so.6",
            "file_offset": 4096,
        },
        "log": {
            "loaded_native_path": "/usr/lib/x86_64-linux-gnu/libm.so.6",
            "file_offset": 8192,
        },
    }
    value = {
        "render_service_id": "srv-daa7thgae00c73a2lmn0",
        "render_runtime": "python",
        "python_implementation": "CPython",
        "python_version_source": "PYTHON_VERSION",
        "python_version_env": "3.14.3",
        "python_version": "3.14.3",
        "python_cache_tag": "cpython-314",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "byteorder": "little",
        "libc_name": "glibc",
        "libc_version": "2.36",
        "float_radix": 2,
        "float_mant_dig": 53,
        "float_max_exp": 1024,
        "float_rounds": 1,
        "libpq_version": 180006,
        "dependency_versions": dependency_versions,
        "runtime_artifact_components": components,
        "runtime_artifact_sha256": sc.canonical_sha256(components),
        "libm_dispatch": dispatch,
        "libm_dispatch_sha256": sc.canonical_sha256(dispatch),
    }
    value["runtime_manifest_sha256"] = sc.canonical_sha256(value)
    return value, dependency_versions, 180006


def test_frozen_dependency_and_libpq_literals_are_exact_not_discovered_baselines():
    assert sc.EXPECTED_LIBPQ_VERSION == 180006
    assert dict(sc.EXPECTED_DEPENDENCY_VERSIONS) == {
        "exchange-calendars": "4.13.2",
        "korean-lunar-calendar": "0.3.1",
        "numpy": "2.4.2",
        "pandas": "3.0.0",
        "psycopg": "3.3.5",
        "psycopg-binary": "3.3.5",
        "pyluach": "2.3.0",
        "python-dateutil": "2.9.0.post0",
        "six": "1.17.0",
        "toolz": "1.1.0",
        "tzdata": "2025.3",
    }


def _ready_schema_parts(
    *,
    amendment_merged_at_utc="2026-09-05T15:45:58.000000Z",
    scan_started_at="2026-09-21T20:30:00.000000Z",
    first_candidate_session="2026-09-08",
    boundary_session="2026-09-21",
    boundary_as_of_at="2026-09-21T20:00:00.000000Z",
):
    manifest_id = "v1b-family-5m"
    expected_cell = sc.manifest_public_cells(manifest_id)[0]
    lineage = sc.family_lineage("5M")
    selected_lineages = [{**expected_cell, "lineage_identity": lineage}]
    counts = [
        {
            **expected_cell,
            "n_regression_windows": 101,
            "n_regression_sessions": 10,
            "n_unconditional_gate_windows": 100,
            "n_unconditional_gate_sessions": 10,
            "n_seasonal_gate_windows": 100,
            "n_seasonal_gate_sessions": 10,
            "all_minima_pass": True,
        }
    ]
    runtime, dependencies, libpq = _runtime_identity()
    context = sc.IdentityContext(
        verified_main_sha="a" * 40,
        v1a_merge_sha=sc.V1A_MERGE_SHA,
        amendment_merge_sha=sc.AMENDMENT_MERGE_SHA,
        tls_amendment_merge_sha=sc.TLS_AMENDMENT_MERGE_SHA,
        manifest_id=manifest_id,
        database_identity={
            "supabase_project_ref": "afyiydxbjgzaiswnbcyj",
            "database_name": "postgres",
        },
        runtime_manifest_sha256=runtime["runtime_manifest_sha256"],
    )
    semantic_calls = []
    readiness_body, readiness = sc.build_readiness(
        context=context,
        amendment_merged_at_utc=amendment_merged_at_utc,
        scan_started_at=scan_started_at,
        first_candidate_session=first_candidate_session,
        boundary_session=boundary_session,
        boundary_as_of_at=boundary_as_of_at,
        selected_lineages=selected_lineages,
        cohort_trace=[],
        counts=counts,
        semantic_ready_validator=semantic_calls.append,
    )
    run_body, run_identity = sc.build_run_identity(
        readiness_identity_body=readiness_body,
        readiness=readiness,
    )
    authority = _authority_proof()
    seal = sc.build_seal(
        initial_authority_proof=authority,
        readiness_identity_body=readiness_body,
        readiness=readiness,
        run_identity_body=run_body,
        run_identity=run_identity,
    )
    return SimpleNamespace(
        manifest_id=manifest_id,
        expected_cell=expected_cell,
        lineage=lineage,
        context=context,
        readiness_body=readiness_body,
        readiness=readiness,
        run_body=run_body,
        run_identity=run_identity,
        authority=authority,
        runtime=runtime,
        dependencies=dependencies,
        libpq=libpq,
        seal=seal,
        semantic_calls=semantic_calls,
    )


def _evaluated_cell(parts, *, classification="INFORMATIVE"):
    value = {key: 0 for key in sc.INT_CELL_KEYS}
    value.update({key: None for key in sc.NULLABLE_SCALAR_METRIC_KEYS})
    value.update({key: None for key in sc.NULLABLE_INTERVAL_KEYS})
    sessions = [f"2026-09-{day:02d}" for day in range(8, 18)]
    value.update(
        {
            **parts.expected_cell,
            "lineage_identity": parts.lineage,
            "session_dates": sessions,
            "evidence_min_cutoff_at": "2026-09-08T13:31:00.000000Z",
            "evidence_max_cutoff_at": "2026-09-17T13:31:00.000000Z",
            "n_input": 122,
            "n_windows": 122,
            "n_sessions": 10,
            "n_persist20_unavailable": 21,
            "n_regression_windows": 101,
            "n_regression_sessions": 10,
            "n_unconditional_unavailable": 1,
            "n_unconditional_gate_windows": 100,
            "n_unconditional_gate_sessions": 10,
            "n_seasonal_gate_windows": 100,
            "n_seasonal_gate_sessions": 10,
            "mae_bps": 1.0,
            "rank_corr": 0.25,
            "level_ratio": 1.1,
            "coverage_90": 0.9,
            "mz_a": 0.1,
            "mz_b": 1.0,
            "mz_r2": 0.2,
            "persist_rank_corr": 0.1,
            "enc_b": 0.3,
            "enc_b_ci_0999": [0.1, 0.5],
            "enc_b_ci_095": [0.2, 0.4],
            "bootstrap_attempted_draws": 200000,
            "bootstrap_valid_draws": 200000,
            "bootstrap_invalid_draws": 0,
            "unconditional_rank_corr": 0.05,
            "seasonal_rank_corr": 0.06,
            "qlike_candidate": 1.0,
            "qlike_unconditional": 1.2,
            "qlike_seasonal": 1.3,
            "d_unconditional": 0.2,
            "d_unconditional_ci_0999": [0.1, 0.3],
            "d_unconditional_ci_095": [0.15, 0.25],
            "d_seasonal": 0.3,
            "d_seasonal_ci_0999": [0.1, 0.5],
            "d_seasonal_ci_095": [0.2, 0.4],
            "unconditional_bootstrap_attempted_draws": 200000,
            "unconditional_bootstrap_valid_draws": 200000,
            "unconditional_bootstrap_invalid_draws": 0,
            "seasonal_bootstrap_attempted_draws": 200000,
            "seasonal_bootstrap_valid_draws": 200000,
            "seasonal_bootstrap_invalid_draws": 0,
            "gate_unconditional": "PASS",
            "gate_seasonal": "PASS",
            "classification": classification,
            "reason_codes": [],
        }
    )
    return value


def test_readiness_run_identity_and_seal_are_exact_and_self_hashed():
    parts = _ready_schema_parts()
    assert parts.semantic_calls == [parts.readiness_body]
    assert set(parts.readiness_body) == set(sc.READINESS_BODY_KEYS)
    assert set(parts.readiness) == set(sc.READINESS_KEYS)
    assert parts.readiness["readiness_identity"] == sc.canonical_sha256(
        parts.readiness_body
    )
    assert set(parts.run_body) == set(sc.RUN_IDENTITY_BODY_KEYS)
    assert parts.run_identity == sc.canonical_sha256(parts.run_body)
    assert parts.seal.canonical_bytes.endswith(b"\n")
    assert parts.seal.canonical_bytes == sc.canonical_line(parts.seal.record())
    assert parts.seal.seal_record_sha256 == sc.canonical_sha256(
        {key: parts.seal.record()[key] for key in sc.SEAL_BODY_KEYS}
    )
    sc.validate_seal(
        parts.seal.record(),
        expected_manifest_id=parts.manifest_id,
        expected_canonical_bytes=parts.seal.canonical_bytes,
    )


def test_identity_builders_reject_semantic_hash_key_and_boundary_drift():
    parts = _ready_schema_parts()
    with pytest.raises(RuntimeError, match="earliest boundary not proven"):
        sc.build_readiness(
            context=parts.context,
            amendment_merged_at_utc="2026-09-05T15:45:58.000000Z",
            scan_started_at="2026-09-08T13:30:00.000000Z",
            first_candidate_session="2026-09-08",
            boundary_session="2026-09-21",
            boundary_as_of_at="2026-09-21T20:00:00.000000Z",
            selected_lineages=parts.readiness["selected_lineages"],
            cohort_trace=[],
            counts=parts.readiness["counts"],
            semantic_ready_validator=lambda _: (_ for _ in ()).throw(
                RuntimeError("earliest boundary not proven")
            ),
        )
    extra = sc.json_clone(parts.readiness_body)
    extra["not_frozen"] = True
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_readiness(extra, parts.readiness)
    changed = sc.json_clone(parts.readiness)
    changed["boundary_session"] = "2026-09-22"
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_readiness(parts.readiness_body, changed)
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_run_identity(
            parts.run_body,
            "0" * 64,
            parts.readiness_body,
            parts.readiness,
        )
    record = parts.seal.record()
    record["initial_authority_proof"]["database_create"] = True
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_seal(record)


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("database_temporary",), False),
        (("session_temp_schema_created",), True),
        (("reader_role_memberships",), ["extra_role"]),
        (("reader_role_attributes", "rolbypassrls"), True),
        (("six_tables_select", "public.forecasts"), False),
        (("six_tables_insert", "public.forecasts"), True),
        (("proof_functions_execute", sc.PROOF_FUNCTIONS[0]), False),
    ],
)
def test_authority_proof_rejects_privilege_or_catalog_drift(path, bad_value):
    proof = _authority_proof()
    target = proof
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad_value
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_authority_proof(proof)


@pytest.mark.parametrize(
    ("mutator", "expected_dependencies", "expected_libpq"),
    [
        (lambda value: value.update(python_version="3.14.4"), None, None),
        (lambda value: value.update(libpq_version=True), None, True),
        (
            lambda value: value["runtime_artifact_components"].update(
                stdlib_tree_sha256="f" * 64
            ),
            None,
            None,
        ),
        (
            lambda value: value["libm_dispatch"]["log"].update(
                loaded_native_path="relative/libm.so"
            ),
            None,
            None,
        ),
        (lambda value: None, {"numpy": "wrong"}, None),
    ],
)
def test_runtime_identity_rejects_frozen_version_byte_dispatch_or_dependency_drift(
    mutator, expected_dependencies, expected_libpq
):
    runtime, dependencies, libpq = _runtime_identity()
    mutator(runtime)
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_runtime_identity(
            runtime,
            expected_dependency_versions=(
                dependencies
                if expected_dependencies is None
                else expected_dependencies
            ),
            expected_libpq_version=(
                libpq if expected_libpq is None else expected_libpq
            ),
        )


def test_evaluated_receipt_round_trip_binds_seal_runtime_cells_and_filename():
    parts = _ready_schema_parts()
    cell = _evaluated_cell(parts)
    receipt = sc.build_evaluated_receipt(
        seal=parts.seal,
        generated_at_utc="2026-09-21T20:01:00.000000Z",
        runtime_identity=parts.runtime,
        final_authority_proof=parts.authority,
        cells=[cell],
        expected_dependency_versions=parts.dependencies,
        expected_libpq_version=parts.libpq,
    )
    obj = receipt.object()
    assert receipt.terminal is True
    assert receipt.schema_version == "ATOM-V1B-MANIFEST-RECEIPT-1"
    assert obj["overall_status"] == "PASS"
    assert obj["overall_reason_codes"] == []
    assert obj["bootstrap"] == {
        "resamples_required": 200000,
        "max_attempts": 1000000,
        "seed": 0,
        "interval_levels": [0.999, 0.95],
        "cluster": "XNYS_SESSION_DATE",
        "sampling_operation": "random.Random(0).choices(sessions,k=len(sessions))",
        "loss_function": "QLIKE(r,f)=log(f^2)+r^2/f^2",
        "gates": ["unconditional", "seasonal"],
    }
    assert obj["seal_record_sha256"] == parts.seal.seal_record_sha256
    assert receipt.filename.endswith(f"-{receipt.receipt_sha256}.json")
    assert receipt.canonical_bytes == sc.canonical_line(obj)
    assert sc.validate_receipt(
        receipt.canonical_bytes,
        receipt.filename,
        seal=parts.seal,
        expected_dependency_versions=parts.dependencies,
        expected_libpq_version=parts.libpq,
    ) == receipt
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_receipt(
            receipt.canonical_bytes,
            receipt.filename.replace(receipt.receipt_sha256, "0" * 64),
            seal=parts.seal,
            expected_dependency_versions=parts.dependencies,
            expected_libpq_version=parts.libpq,
        )
    tampered = receipt.canonical_bytes.replace(b'"overall_status":"PASS"', b'"overall_status":"FAIL"')
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_receipt(
            tampered,
            receipt.filename,
            seal=parts.seal,
            expected_dependency_versions=parts.dependencies,
            expected_libpq_version=parts.libpq,
        )


def test_evaluated_receipt_accepts_read_only_runtime_identity_mapping():
    """Production RuntimeState.identity is immutable, not a plain dict."""

    parts = _ready_schema_parts()
    immutable_runtime = MappingProxyType(sc.json_clone(parts.runtime))
    receipt = sc.build_evaluated_receipt(
        seal=parts.seal,
        generated_at_utc="2026-09-21T20:01:00.000000Z",
        runtime_identity=immutable_runtime,
        final_authority_proof=parts.authority,
        cells=[_evaluated_cell(parts)],
        expected_dependency_versions=parts.dependencies,
        expected_libpq_version=parts.libpq,
    )
    assert receipt.object()["runtime_identity"] == parts.runtime


def _prior_evaluated_receipt_with_cell(parts, cell):
    receipt = sc.build_evaluated_receipt(
        seal=parts.seal,
        generated_at_utc="2026-09-21T20:01:00.000000Z",
        runtime_identity=parts.runtime,
        final_authority_proof=parts.authority,
        cells=[_evaluated_cell(parts)],
        expected_dependency_versions=parts.dependencies,
        expected_libpq_version=parts.libpq,
    )
    value = receipt.object()
    value["cells"] = [cell]
    body = {key: item for key, item in value.items() if key != "receipt_sha256"}
    value["receipt_sha256"] = sc.canonical_sha256(body)
    raw = sc.canonical_line(value)
    path = (
        "docs/v-1b-volatility-scorecard-receipt-"
        f"{parts.manifest_id}-{value['evaluation_session']}-"
        f"{value['run_identity']}-{value['receipt_sha256']}.json"
    )
    return raw, path


def _rehash_prior_receipt(value):
    body = {key: item for key, item in value.items() if key != "receipt_sha256"}
    value["receipt_sha256"] = sc.canonical_sha256(body)
    if value["schema_version"] == "ATOM-V1B-MANIFEST-RECEIPT-1":
        path = (
            "docs/v-1b-volatility-scorecard-receipt-"
            f"{value['manifest_id']}-{value['evaluation_session']}-"
            f"{value['run_identity']}-{value['receipt_sha256']}.json"
        )
    else:
        path = (
            "docs/v-1b-volatility-scorecard-negative-"
            f"{value['manifest_id']}-{value['receipt_sha256']}.json"
        )
    return sc.canonical_line(value), path


def _coherently_rewrite_evaluated_readiness(parts, receipt, updates):
    """Rebind every nested digest after a forged readiness-time mutation."""

    record = parts.seal.record()
    readiness_body = record["readiness_identity_body"]
    readiness = record["readiness"]
    for key, value in updates.items():
        readiness_body[key] = value
        readiness[key] = value
    readiness["readiness_identity"] = sc.canonical_sha256(readiness_body)

    run_body = record["run_identity_body"]
    run_body["readiness_identity"] = readiness["readiness_identity"]
    run_body["evaluation_session"] = readiness["boundary_session"]
    run_body["evaluation_as_of_at"] = readiness["boundary_as_of_at"]
    record["run_identity"] = sc.canonical_sha256(run_body)
    record["seal_record_sha256"] = sc.canonical_sha256(
        {key: record[key] for key in sc.SEAL_BODY_KEYS}
    )

    value = receipt.object()
    value["readiness"] = sc.json_clone(readiness)
    value["run_identity"] = record["run_identity"]
    value["evaluation_session"] = readiness["boundary_session"]
    value["evaluation_as_of_at"] = readiness["boundary_as_of_at"]
    value["seal_record_sha256"] = record["seal_record_sha256"]
    return _rehash_prior_receipt(value)


def _coherently_rewrite_evaluated_verified_main(parts, receipt, verified_sha):
    record = parts.seal.record()
    readiness_body = record["readiness_identity_body"]
    readiness_body["verified_main_sha"] = verified_sha
    readiness = record["readiness"]
    readiness["readiness_identity"] = sc.canonical_sha256(readiness_body)

    run_body = record["run_identity_body"]
    run_body["verified_main_sha"] = verified_sha
    run_body["readiness_identity"] = readiness["readiness_identity"]
    record["run_identity"] = sc.canonical_sha256(run_body)
    record["seal_record_sha256"] = sc.canonical_sha256(
        {key: record[key] for key in sc.SEAL_BODY_KEYS}
    )

    value = receipt.object()
    value["verified_main_sha"] = verified_sha
    value["readiness"] = sc.json_clone(readiness)
    value["run_identity"] = record["run_identity"]
    value["seal_record_sha256"] = record["seal_record_sha256"]
    return _rehash_prior_receipt(value)


@pytest.mark.parametrize(
    ("case", "mutate"),
    (
        (
            "first accounting equation",
            lambda cell: cell.__setitem__("n_input", cell["n_input"] + 1),
        ),
        (
            "second accounting equation",
            lambda cell: cell.__setitem__("n_persist20_unavailable", 20),
        ),
        (
            "gate accounting equation",
            lambda cell: cell.__setitem__("n_unconditional_unavailable", 2),
        ),
        (
            "bootstrap attempted arithmetic",
            lambda cell: cell.__setitem__("bootstrap_attempted_draws", 200001),
        ),
        (
            "completed bootstrap frontier",
            lambda cell: (
                cell.__setitem__("bootstrap_valid_draws", 199999),
                cell.__setitem__("bootstrap_invalid_draws", 1),
            ),
        ),
        (
            "bootstrap hard cap",
            lambda cell: (
                cell.__setitem__("seasonal_bootstrap_attempted_draws", 1000001),
                cell.__setitem__("seasonal_bootstrap_invalid_draws", 800001),
            ),
        ),
        (
            "interval endpoint ordering",
            lambda cell: cell.__setitem__("enc_b_ci_0999", [0.5, 0.1]),
        ),
        (
            "nested interval ordering",
            lambda cell: (
                cell.__setitem__("d_unconditional_ci_0999", [0.2, 0.25]),
                cell.__setitem__("d_unconditional_ci_095", [0.1, 0.3]),
            ),
        ),
        (
            "informative coefficient threshold",
            lambda cell: cell.__setitem__("enc_b_ci_0999", [0.0, 0.5]),
        ),
        (
            "informative gate threshold",
            lambda cell: cell.__setitem__("gate_unconditional", "FAIL"),
        ),
        (
            "completed analytic null matrix",
            lambda cell: cell.__setitem__("enc_b", None),
        ),
        (
            "classification reason derivation",
            lambda cell: cell.__setitem__("reason_codes", ["ENC_B_NOT_POSITIVE"]),
        ),
    ),
)
def test_prior_evaluated_receipt_rejects_forged_cell_semantics(case, mutate):
    parts = _ready_schema_parts()
    cell = _evaluated_cell(parts)
    mutate(cell)
    raw, path = _prior_evaluated_receipt_with_cell(parts, cell)
    with pytest.raises(sc.ProtocolDefect, match="cell|bootstrap|interval|classification|gate"):
        sc.validate_prior_receipt(
            raw,
            path,
            expected_amendment_merged_at_utc=parts.readiness[
                "amendment_merged_at_utc"
            ],
        )


def test_prior_evaluated_receipt_rejects_internally_valid_forged_amendment_time():
    authenticated = "2026-09-05T15:45:58.000000Z"
    forged_parts = _ready_schema_parts(
        amendment_merged_at_utc="2026-09-06T15:45:58.000000Z"
    )
    receipt = sc.build_evaluated_receipt(
        seal=forged_parts.seal,
        generated_at_utc="2026-09-21T20:31:00.000000Z",
        runtime_identity=forged_parts.runtime,
        final_authority_proof=forged_parts.authority,
        cells=[_evaluated_cell(forged_parts)],
        expected_dependency_versions=forged_parts.dependencies,
        expected_libpq_version=forged_parts.libpq,
    )
    with pytest.raises(
        sc.ProtocolDefect,
        match="authenticated amendment time mismatch",
    ):
        sc.validate_prior_receipt(
            receipt.canonical_bytes,
            receipt.filename,
            expected_amendment_merged_at_utc=authenticated,
        )


def test_prior_evaluated_receipt_rejects_coherent_all_zero_verified_main_sha():
    parts = _ready_schema_parts()
    receipt = sc.build_evaluated_receipt(
        seal=parts.seal,
        generated_at_utc="2026-09-21T20:31:00.000000Z",
        runtime_identity=parts.runtime,
        final_authority_proof=parts.authority,
        cells=[_evaluated_cell(parts)],
        expected_dependency_versions=parts.dependencies,
        expected_libpq_version=parts.libpq,
    )
    raw, path = _coherently_rewrite_evaluated_verified_main(
        parts,
        receipt,
        "0" * 40,
    )
    forged = json.loads(raw)
    assert forged["verified_main_sha"] == "0" * 40
    assert forged["receipt_sha256"] == sc.canonical_sha256(
        {key: value for key, value in forged.items() if key != "receipt_sha256"}
    )
    with pytest.raises(
        sc.ProtocolDefect,
        match="prior evaluated verified revision is null",
    ):
        sc.validate_prior_receipt(
            raw,
            path,
            expected_amendment_merged_at_utc=parts.readiness[
                "amendment_merged_at_utc"
            ],
        )


@pytest.mark.parametrize(
    ("case", "readiness_times"),
    (
        (
            "boundary equals scan",
            {"scan_started_at": "2026-09-21T20:00:00.000000Z"},
        ),
        (
            "boundary follows scan",
            {"scan_started_at": "2026-09-21T19:59:59.999999Z"},
        ),
        (
            "boundary is not exact New York close",
            {"boundary_as_of_at": "2026-09-21T19:59:59.000000Z"},
        ),
        (
            "boundary date mismatches New York date",
            {"boundary_session": "2026-09-20"},
        ),
        (
            "boundary precedes first candidate",
            {"first_candidate_session": "2026-09-22"},
        ),
    ),
)
def test_prior_evaluated_receipt_rejects_coherent_forged_readiness_times(
    case, readiness_times
):
    authenticated = "2026-09-05T15:45:58.000000Z"
    parts = _ready_schema_parts(amendment_merged_at_utc=authenticated)
    receipt = sc.build_evaluated_receipt(
        seal=parts.seal,
        generated_at_utc="2026-09-21T21:00:00.000000Z",
        runtime_identity=parts.runtime,
        final_authority_proof=parts.authority,
        cells=[_evaluated_cell(parts)],
        expected_dependency_versions=parts.dependencies,
        expected_libpq_version=parts.libpq,
    )
    raw, path = _coherently_rewrite_evaluated_readiness(
        parts,
        receipt,
        readiness_times,
    )
    assert (
        json.loads(raw)["readiness"]["amendment_merged_at_utc"]
        == authenticated
    )
    with pytest.raises(
        sc.ProtocolDefect,
        match="boundary precedes first candidate|prior readiness time relationship",
    ):
        sc.validate_prior_receipt(
            raw,
            path,
            expected_amendment_merged_at_utc=authenticated,
        )


@pytest.mark.parametrize(
    "lineage",
    (
        {
            "v3_model_version": "",
            "symbol": "COIN",
            "horizon": "5M",
            "cohort_id": "cohort-a",
            "cohort_hash": "a" * 64,
        },
        {
            "v3_model_version": "V9-SYNTHETIC",
            "symbol": "COIN",
            "horizon": "5M",
            "cohort_id": "",
            "cohort_hash": "a" * 64,
        },
        {
            "v3_model_version": "V9-SYNTHETIC",
            "symbol": "COIN",
            "horizon": "5M",
            "cohort_id": "cohort-a",
            "cohort_hash": "not-a-lowercase-hex-digest",
        },
        {
            "v3_model_version": "__NO_ADMISSIBLE_V9_LINEAGE__",
            "symbol": "COIN",
            "horizon": "5M",
            "cohort_id": "cohort-a",
            "cohort_hash": "0" * 64,
        },
        {
            "v3_model_version": "V9-SYNTHETIC",
            "symbol": "COIN",
            "horizon": "5M",
            "cohort_id": "__NO_ADMISSIBLE_V9_LINEAGE__",
            "cohort_hash": "a" * 64,
        },
    ),
)
def test_receipt_lineage_validator_rejects_empty_invalid_or_partial_v9_sentinel(
    lineage,
):
    expected = sc.manifest_public_cells("v1b-v9-5m")[0]
    wrapper = {**expected, "lineage_identity": lineage}
    with pytest.raises(sc.ProtocolDefect, match="lineage|sentinel"):
        sc.validate_selected_lineages("v1b-v9-5m", [wrapper])


def test_negative_receipts_preserve_null_or_consuming_seal_routes():
    parts = _ready_schema_parts()
    generated = "2026-09-21T20:01:00.000000Z"
    blocked = sc.build_blocked_receipt(
        manifest_id=parts.manifest_id,
        generated_at_utc=generated,
        observed_main_sha=None,
        expected_main_sha="a" * 40,
        observed_v1a_merge_sha=None,
        observed_user=None,
        observed_database=None,
        observed_effective_host=None,
        project_binding_verified=None,
        read_only=None,
        unverified_merge_identities=frozenset({"amendment", "tls"}),
    )
    assert blocked.terminal is False
    assert [
        blocked.object()[key]
        for key in ("readiness", "sealed_run_identity", "seal_record_sha256")
    ] == [None, None, None]
    unsealed = sc.build_pre_cell_invalid_receipt(
        manifest_id=parts.manifest_id,
        generated_at_utc=generated,
        verified_main_sha="a" * 40,
        v1a_merge_sha=None,
        evaluation_session=None,
        evaluation_as_of_at=None,
        database_identity=None,
        authority_proof=None,
    )
    assert unsealed.terminal is False
    consuming = sc.build_pre_cell_invalid_receipt(
        manifest_id=parts.manifest_id,
        generated_at_utc=generated,
        verified_main_sha="a" * 40,
        v1a_merge_sha=sc.V1A_MERGE_SHA,
        evaluation_session=parts.readiness["boundary_session"],
        evaluation_as_of_at=parts.readiness["boundary_as_of_at"],
        database_identity=parts.readiness_body["database_identity"],
        authority_proof=parts.authority,
        seal=parts.seal,
    )
    assert consuming.terminal is True
    post = sc.build_post_eval_authority_invalid_receipt(
        seal=parts.seal,
        generated_at_utc=generated,
        database_identity=parts.readiness_body["database_identity"],
    )
    assert post.terminal is True
    for receipt in (blocked, unsealed, consuming, post):
        kwargs = {"seal": parts.seal} if receipt.terminal else {}
        assert sc.validate_receipt(
            receipt.canonical_bytes, receipt.filename, **kwargs
        ) == receipt


def test_negative_receipt_rejects_partial_seal_triple_and_noncanonical_bytes():
    parts = _ready_schema_parts()
    receipt = sc.build_pre_cell_invalid_receipt(
        manifest_id=parts.manifest_id,
        generated_at_utc="2026-09-21T20:01:00.000000Z",
        verified_main_sha="a" * 40,
        v1a_merge_sha=None,
        evaluation_session=None,
        evaluation_as_of_at=None,
        database_identity=None,
        authority_proof=None,
    )
    obj = receipt.object()
    obj["sealed_run_identity"] = parts.run_identity
    body = {key: value for key, value in obj.items() if key != "receipt_sha256"}
    obj["receipt_sha256"] = sc.canonical_sha256(body)
    raw = sc.canonical_line(obj)
    filename = (
        f"docs/v-1b-volatility-scorecard-negative-{parts.manifest_id}-"
        f"{obj['receipt_sha256']}.json"
    )
    with pytest.raises(sc.ProtocolDefect, match="all-null/all-nonnull"):
        sc.validate_receipt(raw, filename)
    with pytest.raises(sc.ProtocolDefect, match="one final LF"):
        sc.validate_receipt(receipt.canonical_bytes[:-1], receipt.filename)
    with pytest.raises(sc.ProtocolDefect, match="noncanonical"):
        sc.validate_receipt(
            json.dumps(receipt.object(), indent=2).encode() + b"\n",
            receipt.filename,
        )


def test_prior_consuming_negative_reconstructs_all_three_seal_cross_bindings():
    parts = _ready_schema_parts()
    receipt = sc.build_pre_cell_invalid_receipt(
        manifest_id=parts.manifest_id,
        generated_at_utc="2026-09-21T20:01:00.000000Z",
        verified_main_sha="a" * 40,
        v1a_merge_sha=sc.V1A_MERGE_SHA,
        evaluation_session=parts.readiness["boundary_session"],
        evaluation_as_of_at=parts.readiness["boundary_as_of_at"],
        database_identity=parts.readiness_body["database_identity"],
        authority_proof=parts.authority,
        seal=parts.seal,
    )
    expected_amendment_time = parts.readiness["amendment_merged_at_utc"]
    validated = sc.validate_prior_receipt(
        receipt.canonical_bytes,
        receipt.filename,
        expected_amendment_merged_at_utc=expected_amendment_time,
    )
    assert validated.terminal is True
    assert validated.seal_record_sha256 == parts.seal.seal_record_sha256

    mutations = (
        lambda value: value["readiness"].__setitem__(
            "readiness_identity", "0" * 64
        ),
        lambda value: value.__setitem__("sealed_run_identity", "0" * 64),
        lambda value: value.__setitem__("seal_record_sha256", "0" * 64),
    )
    for mutate in mutations:
        value = sc.json_clone(receipt.object())
        mutate(value)
        body = {key: item for key, item in value.items() if key != "receipt_sha256"}
        value["receipt_sha256"] = sc.canonical_sha256(body)
        raw = sc.canonical_line(value)
        path = (
            "docs/v-1b-volatility-scorecard-negative-"
            f"{parts.manifest_id}-{value['receipt_sha256']}.json"
        )
        with pytest.raises(sc.ProtocolDefect):
            sc.validate_prior_receipt(
                raw,
                path,
                expected_amendment_merged_at_utc=expected_amendment_time,
            )


@pytest.mark.parametrize(
    ("case", "mutate"),
    (
        (
            "malformed generated timestamp",
            lambda value: value.__setitem__(
                "generated_at_utc", "2026-09-21T20:31:00Z"
            ),
        ),
        (
            "wrong reader",
            lambda value: value.__setitem__("reader_identity", "other_reader"),
        ),
        (
            "malformed verified SHA",
            lambda value: value.__setitem__("verified_main_sha", "A" * 40),
        ),
        (
            "null verified SHA",
            lambda value: value.__setitem__("verified_main_sha", "0" * 40),
        ),
        (
            "malformed scan timestamp",
            lambda value: value["readiness"].__setitem__(
                "scan_started_at", "not-a-timestamp"
            ),
        ),
        (
            "malformed boundary timestamp",
            lambda value: value["readiness"].__setitem__(
                "boundary_as_of_at", "2026-09-21T20:00:00Z"
            ),
        ),
        (
            "authenticated amendment mismatch",
            lambda value: value["readiness"].__setitem__(
                "amendment_merged_at_utc", "2026-09-06T15:45:58.000000Z"
            ),
        ),
        (
            "boundary before first candidate",
            lambda value: (
                value["readiness"].__setitem__("boundary_session", "2026-09-07"),
                value["readiness"].__setitem__(
                    "boundary_as_of_at", "2026-09-07T20:00:00.000000Z"
                ),
                value.__setitem__("evaluation_session", "2026-09-07"),
                value.__setitem__(
                    "evaluation_as_of_at", "2026-09-07T20:00:00.000000Z"
                ),
            ),
        ),
        (
            "boundary close is not before scan",
            lambda value: (
                value["readiness"].__setitem__(
                    "boundary_as_of_at", value["readiness"]["scan_started_at"]
                ),
                value.__setitem__(
                    "evaluation_as_of_at", value["readiness"]["scan_started_at"]
                ),
            ),
        ),
        (
            "boundary is not the exact New York close",
            lambda value: (
                value["readiness"].__setitem__(
                    "boundary_as_of_at", "2026-09-21T19:59:59.000000Z"
                ),
                value.__setitem__(
                    "evaluation_as_of_at", "2026-09-21T19:59:59.000000Z"
                ),
            ),
        ),
    ),
)
def test_prior_consuming_negative_rejects_forged_time_and_identity_fields(
    case, mutate
):
    parts = _ready_schema_parts()
    expected_amendment_time = parts.readiness["amendment_merged_at_utc"]
    receipt = sc.build_pre_cell_invalid_receipt(
        manifest_id=parts.manifest_id,
        generated_at_utc="2026-09-21T20:31:00.000000Z",
        verified_main_sha="a" * 40,
        v1a_merge_sha=sc.V1A_MERGE_SHA,
        evaluation_session=parts.readiness["boundary_session"],
        evaluation_as_of_at=parts.readiness["boundary_as_of_at"],
        database_identity=parts.readiness_body["database_identity"],
        authority_proof=parts.authority,
        seal=parts.seal,
    )
    value = receipt.object()
    mutate(value)
    raw, path = _rehash_prior_receipt(value)
    with pytest.raises(sc.ProtocolDefect):
        sc.validate_prior_receipt(
            raw,
            path,
            expected_amendment_merged_at_utc=expected_amendment_time,
        )


# ---------------------------------------------------------------------------
# Direct-host URI, pinned CA, and libpq effective-connection contract
# ---------------------------------------------------------------------------


def _database_uri():
    return (
        "postgresql://atom_e1_scorecard_reader:p%40ss%3Aphrase@"
        "db.afyiydxbjgzaiswnbcyj.supabase.co:5432/postgres?"
        "sslmode=verify-full&"
        "sslrootcert=certs/supabase-prod-ca-2021.crt&"
        "sslcertmode=disable&require_auth=scram-sha-256&gssencmode=disable"
    )


def _expected_conninfo():
    return {
        "user": "atom_e1_scorecard_reader",
        "password": "p@ss:phrase",
        "host": "db.afyiydxbjgzaiswnbcyj.supabase.co",
        "port": "5432",
        "dbname": "postgres",
        "sslmode": "verify-full",
        "sslrootcert": "certs/supabase-prod-ca-2021.crt",
        "sslcertmode": "disable",
        "require_auth": "scram-sha-256",
        "gssencmode": "disable",
    }


def test_database_environment_uses_one_untouched_uri_and_dual_parser(tmp_path):
    uri = _database_uri()
    calls = []

    def parser(raw):
        calls.append(raw)
        return _expected_conninfo()

    parsed = sc.validate_database_environment(
        {sc.READONLY_URL_ENV: uri},
        conninfo_parser=parser,
        home_dir=tmp_path,
    )
    assert calls == [uri]
    assert parsed._uri_for_single_connect() == uri
    assert parsed.user == sc.READER_ROLE
    assert parsed.host == sc.DIRECT_HOST
    assert parsed.port == 5432
    assert parsed.dbname == "postgres"
    assert parsed.password_present is True
    assert parsed.password_fallbacks_absent is True
    assert parsed.tls_fallbacks_absent is True
    assert parsed.identity_overrides_absent is True
    assert "p@ss" not in repr(parsed)
    assert "p%40ss" not in repr(parsed)


@pytest.mark.parametrize(
    "uri",
    [
        _database_uri().replace(
            "db.afyiydxbjgzaiswnbcyj.supabase.co", "aws-0-us-west-1.pooler.supabase.com"
        ),
        _database_uri().replace("sslmode=verify-full", "sslmode=require"),
        _database_uri() + "&sslmode=verify-full",
        _database_uri().replace(":p%40ss%3Aphrase@", ":@"),
        _database_uri().replace("/postgres?", "/template1?"),
        _database_uri().replace("sslmode=", "%73slmode="),
        _database_uri().replace(
            "gssencmode=disable", "gssencmode=disable&hostaddr=127.0.0.1"
        ),
    ],
)
def test_database_uri_rejects_pooler_weaker_tls_duplicates_and_overrides(uri):
    with pytest.raises(sc.DatabaseContractError) as caught:
        sc.validate_database_uri(
            uri,
            environ={sc.READONLY_URL_ENV: uri},
            conninfo_parser=lambda _: (_ for _ in ()).throw(
                AssertionError("libpq parser must not receive raw-invalid URI")
            ),
        )
    assert caught.value.route is sc.DatabaseFailureRoute.BLOCKED
    assert caught.value.defect is sc.DatabaseDefect.URI_INVALID
    assert "p@ss" not in str(caught.value)
    assert "p%40ss" not in str(caught.value)


def test_database_environment_rejects_ambient_pg_source_and_default_file(tmp_path):
    uri = _database_uri()
    with pytest.raises(sc.DatabaseContractError) as caught:
        sc.validate_database_environment(
            {sc.READONLY_URL_ENV: uri, "PGHOST": "other-host"},
            conninfo_parser=lambda _: _expected_conninfo(),
            home_dir=tmp_path,
        )
    assert caught.value.defect is sc.DatabaseDefect.AMBIENT_SOURCE

    (tmp_path / ".pgpass").write_text("synthetic-only", encoding="utf-8")
    with pytest.raises(sc.DatabaseContractError) as caught:
        sc.validate_database_environment(
            {sc.READONLY_URL_ENV: uri},
            conninfo_parser=lambda _: _expected_conninfo(),
            home_dir=tmp_path,
        )
    assert caught.value.defect is sc.DatabaseDefect.AMBIENT_SOURCE


def test_database_failure_stage_routes_are_explicit_and_not_exception_inferred():
    assert {
        stage: sc.route_for_database_stage(stage)
        for stage in sc.DatabaseFailureStage
    } == {
        sc.DatabaseFailureStage.NEW_BEFORE_EVIDENCE: sc.DatabaseFailureRoute.BLOCKED,
        sc.DatabaseFailureStage.NEW_AFTER_EVIDENCE_BEFORE_SEAL: sc.DatabaseFailureRoute.PRE_CELL_INVALID,
        sc.DatabaseFailureStage.SEALED_OR_RECOVERY: sc.DatabaseFailureRoute.PRE_CELL_INVALID,
        sc.DatabaseFailureStage.FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS: sc.DatabaseFailureRoute.POST_EVALUATION_AUTHORITY_INVALID,
    }


def test_pinned_ca_matches_exact_bytes_mode_git_blob_and_repository_path():
    root = MODULE_PATH.parents[1]
    ca_bytes = (root / sc.CA_REPOSITORY_PATH).read_bytes()
    seen = []

    def tracked(path):
        seen.append(path)
        return sc.GitBlobObservation("100644", sc.CA_GIT_BLOB_SHA1, ca_bytes)

    observed = sc.verify_pinned_ca(root, cwd=root, git_blob_reader=tracked)
    assert seen == ["certs/supabase-prod-ca-2021.crt"]
    assert observed == sc.PinnedCAObservation(
        "certs/supabase-prod-ca-2021.crt",
        1367,
        "700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7",
        "3d693669b23c340c57a3457bdc8b6fefe1806cc5",
    )
    with pytest.raises(sc.DatabaseContractError) as caught:
        sc.verify_pinned_ca(
            root,
            cwd=root,
            git_blob_reader=lambda _: sc.GitBlobObservation(
                "100755", sc.CA_GIT_BLOB_SHA1, ca_bytes
            ),
        )
    assert caught.value.defect is sc.DatabaseDefect.PINNED_CA


def _synthetic_connection(parsed, *, duplicate=False, wrong_host=False):
    options = []
    values = _expected_conninfo()
    if wrong_host:
        values = {**values, "host": "other.invalid"}
    for key, value in values.items():
        options.append(SimpleNamespace(keyword=key.encode(), val=value.encode()))
    if duplicate:
        options.append(SimpleNamespace(keyword=b"host", val=parsed.host.encode()))
    return SimpleNamespace(
        pgconn=SimpleNamespace(info=options),
        info=SimpleNamespace(
            host=parsed.host,
            port=parsed.port,
            dbname=parsed.dbname,
            user=parsed.user,
        ),
    )


def test_postconnect_pqconninfo_requires_every_exact_effective_tls_target_option(tmp_path):
    parsed = sc.validate_database_environment(
        {sc.READONLY_URL_ENV: _database_uri()},
        conninfo_parser=lambda _: _expected_conninfo(),
        home_dir=tmp_path,
    )
    sc.verify_postconnect_conninfo(
        _synthetic_connection(parsed),
        parsed,
        stage=sc.DatabaseFailureStage.NEW_BEFORE_EVIDENCE,
    )
    for bad in (
        _synthetic_connection(parsed, duplicate=True),
        _synthetic_connection(parsed, wrong_host=True),
    ):
        with pytest.raises(sc.DatabaseContractError) as caught:
            sc.verify_postconnect_conninfo(
                bad,
                parsed,
                stage=sc.DatabaseFailureStage.SEALED_OR_RECOVERY,
            )
        assert caught.value.route is sc.DatabaseFailureRoute.PRE_CELL_INVALID
        assert caught.value.defect is sc.DatabaseDefect.CONNINFO


class _SnapshotCursor:
    def __init__(self, events, observed_start):
        self.events = events
        self.observed_start = observed_start
        self.last_sql = None
        self.closed = False

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.events.append(("execute", sql, params))

    def fetchall(self):
        assert self.last_sql == sc.SCAN_STARTED_SQL
        return [(self.observed_start,)]

    def close(self):
        self.closed = True
        self.events.append(("cursor_close",))


class _Transaction:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        self.events.append(("transaction_enter",))
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.events.append(("transaction_exit", exc_type))
        return False


class _SnapshotConnection:
    def __init__(self, parsed, observed_start, events):
        effective = _synthetic_connection(parsed)
        self.pgconn = effective.pgconn
        self.info = effective.info
        self.autocommit = False
        self.read_only = False
        self.isolation_level = None
        self.events = events
        self._cursor = _SnapshotCursor(events, observed_start)
        self.closed = False

    def transaction(self):
        self.events.append(("transaction", self.read_only, self.isolation_level))
        return _Transaction(self.events)

    def cursor(self):
        self.events.append(("cursor",))
        return self._cursor

    def close(self):
        self.closed = True
        self.events.append(("connection_close",))


def _parsed_database_uri(tmp_path):
    return sc.validate_database_environment(
        {sc.READONLY_URL_ENV: _database_uri()},
        conninfo_parser=lambda _: _expected_conninfo(),
        home_dir=tmp_path,
    )


def _ca_observation():
    return sc.PinnedCAObservation(
        sc.CA_REPOSITORY_PATH,
        sc.CA_SIZE_BYTES,
        sc.CA_SHA256,
        sc.CA_GIT_BLOB_SHA1,
    )


def test_snapshot_connects_once_sets_read_only_rr_and_takes_timestamp_as_first_sql(
    tmp_path, monkeypatch
):
    parsed = _parsed_database_uri(tmp_path)
    ca = _ca_observation()
    observed_start = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    events = []
    connection = _SnapshotConnection(parsed, observed_start, events)
    connect_calls = []
    authority_stages = []
    ca_stages = []

    def connect(uri):
        connect_calls.append(uri)
        events.append(("connect",))
        return connection

    def authority(cursor, observed_parsed, observed_ca, *, stage):
        assert cursor is connection._cursor
        assert observed_parsed is parsed
        assert observed_ca == ca
        assert events[-1][0] == "execute"
        assert events[-1][1] == sc.SCAN_STARTED_SQL
        authority_stages.append(stage)
        events.append(("authority", stage))
        return _authority_proof()

    monkeypatch.setattr(sc, "authority_check", authority)

    def ca_recheck(stage):
        ca_stages.append(stage)
        return ca

    with sc.open_v1b_snapshot(
        parsed,
        ca,
        connect=connect,
        repeatable_read_value="REPEATABLE_READ",
        ca_recheck=ca_recheck,
    ) as session:
        assert connect_calls == [_database_uri()]
        assert connection.read_only is True
        assert connection.isolation_level == "REPEATABLE_READ"
        assert session.scan_started_at == observed_start
        assert session.recovery_started_at is None
        assert session.initial_authority_proof == _authority_proof()
        assert events[0] == ("connect",)
        assert next(event for event in events if event[0] == "execute") == (
            "execute",
            sc.SCAN_STARTED_SQL,
            None,
        )
        assert authority_stages == [sc.DatabaseFailureStage.NEW_BEFORE_EVIDENCE]
    assert ca_stages == [sc.DatabaseFailureStage.NEW_BEFORE_EVIDENCE]
    assert connection._cursor.closed is True
    assert connection.closed is True
    assert events[-1] == ("connection_close",)


def test_snapshot_recovery_preserves_sealed_scan_start_and_requires_later_clock(
    tmp_path, monkeypatch
):
    parsed = _parsed_database_uri(tmp_path)
    ca = _ca_observation()
    sealed = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    recovery = sealed + timedelta(microseconds=1)
    events = []
    connection = _SnapshotConnection(parsed, recovery, events)
    monkeypatch.setattr(sc, "authority_check", lambda *args, **kwargs: _authority_proof())
    with sc.open_v1b_snapshot(
        parsed,
        ca,
        connect=lambda uri: connection,
        repeatable_read_value="REPEATABLE_READ",
        ca_recheck=lambda stage: ca,
        recovery_seal_accepted=True,
        sealed_scan_started_at=sealed,
    ) as session:
        assert session.scan_started_at == sealed
        assert session.recovery_started_at == recovery

    nonlater = _SnapshotConnection(parsed, sealed, [])
    with pytest.raises(sc.DatabaseContractError) as caught:
        with sc.open_v1b_snapshot(
            parsed,
            ca,
            connect=lambda uri: nonlater,
            repeatable_read_value="REPEATABLE_READ",
            ca_recheck=lambda stage: ca,
            recovery_seal_accepted=True,
            sealed_scan_started_at=sealed,
        ):
            raise AssertionError("invalid recovery timestamp must not yield")
    assert caught.value.route is sc.DatabaseFailureRoute.PRE_CELL_INVALID
    assert caught.value.defect is sc.DatabaseDefect.SNAPSHOT
    assert nonlater.closed is True


@pytest.mark.parametrize(
    ("fault", "recovery", "expected_route"),
    (
        ("transaction_enter", False, sc.DatabaseFailureRoute.BLOCKED),
        ("cursor", False, sc.DatabaseFailureRoute.BLOCKED),
        ("transaction_exit", False, sc.DatabaseFailureRoute.BLOCKED),
        ("transaction_enter", True, sc.DatabaseFailureRoute.PRE_CELL_INVALID),
        ("cursor", True, sc.DatabaseFailureRoute.PRE_CELL_INVALID),
        ("transaction_exit", True, sc.DatabaseFailureRoute.PRE_CELL_INVALID),
    ),
)
def test_snapshot_context_failures_are_sanitized_and_stage_routed(
    tmp_path, monkeypatch, fault, recovery, expected_route
):
    parsed = _parsed_database_uri(tmp_path)
    ca = _ca_observation()
    sealed = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    observed = sealed + timedelta(microseconds=1) if recovery else sealed
    events = []

    class FailingTransaction(_Transaction):
        def __enter__(self):
            if fault == "transaction_enter":
                raise RuntimeError("RAW_TRANSACTION_ENTER_DETAIL")
            return super().__enter__()

        def __exit__(self, exc_type, exc, traceback):
            if fault == "transaction_exit":
                raise RuntimeError("RAW_TRANSACTION_EXIT_DETAIL")
            return super().__exit__(exc_type, exc, traceback)

    class FailingConnection(_SnapshotConnection):
        def transaction(self):
            self.events.append(("transaction", self.read_only, self.isolation_level))
            return FailingTransaction(self.events)

        def cursor(self):
            if fault == "cursor":
                raise RuntimeError("RAW_CURSOR_DETAIL")
            return super().cursor()

    connection = FailingConnection(parsed, observed, events)
    monkeypatch.setattr(sc, "authority_check", lambda *args, **kwargs: _authority_proof())
    arguments = {}
    if recovery:
        arguments = {
            "recovery_seal_accepted": True,
            "sealed_scan_started_at": sealed,
        }
    with pytest.raises(sc.DatabaseContractError) as caught:
        with sc.open_v1b_snapshot(
            parsed,
            ca,
            connect=lambda uri: connection,
            repeatable_read_value="REPEATABLE_READ",
            ca_recheck=lambda stage: ca,
            **arguments,
        ):
            pass
    assert caught.value.route is expected_route
    assert caught.value.defect is sc.DatabaseDefect.SNAPSHOT
    assert "RAW_" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert connection.closed is True


def test_snapshot_final_authority_recheck_is_stage_bound_and_exact(tmp_path, monkeypatch):
    parsed = _parsed_database_uri(tmp_path)
    ca = _ca_observation()
    events = []
    connection = _SnapshotConnection(
        parsed, datetime(2026, 9, 8, 13, 30, tzinfo=UTC), events
    )
    proofs = [_authority_proof(), _authority_proof()]
    stages = []

    def authority(*args, stage, **kwargs):
        stages.append(stage)
        return proofs[len(stages) - 1]

    monkeypatch.setattr(sc, "authority_check", authority)
    with sc.open_v1b_snapshot(
        parsed,
        ca,
        connect=lambda uri: connection,
        repeatable_read_value="REPEATABLE_READ",
        ca_recheck=lambda stage: ca,
    ) as session:
        assert session.final_authority_check() == proofs[1]
    assert stages == [
        sc.DatabaseFailureStage.NEW_BEFORE_EVIDENCE,
        sc.DatabaseFailureStage.FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS,
    ]

    changed = _authority_proof()
    changed["tls_active"] = False
    connection = _SnapshotConnection(
        parsed, datetime(2026, 9, 8, 13, 30, tzinfo=UTC), []
    )
    sequence = iter((_authority_proof(), changed))
    monkeypatch.setattr(sc, "authority_check", lambda *args, **kwargs: next(sequence))
    with sc.open_v1b_snapshot(
        parsed,
        ca,
        connect=lambda uri: connection,
        repeatable_read_value="REPEATABLE_READ",
        ca_recheck=lambda stage: ca,
    ) as session:
        with pytest.raises(sc.DatabaseContractError) as caught:
            session.final_authority_check()
    assert caught.value.route is sc.DatabaseFailureRoute.POST_EVALUATION_AUTHORITY_INVALID
    assert caught.value.defect is sc.DatabaseDefect.AUTHORITY


def test_snapshot_final_ca_and_local_git_share_final_checkpoint_deadline(
    monkeypatch,
):
    ca = _ca_observation()
    proof = _authority_proof()
    clock_state = _MutableClock(4_000_000_000)
    terminal_events = []

    def clock():
        terminal_events.append("check")
        return clock_state()

    context = sc.GithubDeadlineContext(checkpoint_end_ns=10_000_000_000)
    git_calls = []
    rechecks = []

    def run(arguments, **kwargs):
        git_calls.append((arguments, kwargs))
        return sc.subprocess.CompletedProcess(arguments, 0, stdout=b"tracked-ca")

    monkeypatch.setattr(sc.subprocess, "run", run)
    monkeypatch.setattr(
        sc,
        "authority_check",
        lambda cursor, parsed, observed_ca, *, stage: (
            terminal_events.append("authority"),
            rechecks.append(("database", stage, observed_ca)),
            proof,
        )[2],
    )

    def deadline_ca(stage, observed_context, observed_clock):
        rechecks.append(("ca", stage, observed_context, observed_clock))
        assert observed_context is context
        assert observed_clock is clock
        assert sc._git_read(
            observed_context,
            observed_clock,
            "show",
            "HEAD:certs/supabase-prod-ca-2021.crt",
        ) == b"tracked-ca"
        terminal_events.append("ca_complete")
        return ca

    session = sc.SnapshotSession(
        connection=object(),
        cursor=object(),
        parsed=SimpleNamespace(),
        initial_ca=ca,
        initial_authority_proof=proof,
        scan_started_at=datetime(2026, 9, 8, 13, 30, tzinfo=UTC),
        recovery_started_at=None,
        _ca_recheck=lambda stage: (_ for _ in ()).throw(
            AssertionError("final check must not create a fresh CA context")
        ),
        _ca_recheck_deadline=deadline_ca,
    )
    assert session.final_authority_check(context=context, clock_ns=clock) == proof
    stage = sc.DatabaseFailureStage.FINAL_AUTHORITY_AFTER_TRUTHFUL_CELLS
    assert rechecks == [
        ("ca", stage, context, clock),
        ("database", stage, ca),
    ]
    assert len(git_calls) == 1
    arguments, kwargs = git_calls[0]
    assert arguments == (
        "git",
        "-c",
        "credential.helper=",
        "show",
        "HEAD:certs/supabase-prod-ca-2021.crt",
    )
    assert kwargs["timeout"] == 6.0
    assert kwargs["timeout"] > 0.0
    assert terminal_events[-4:] == [
        "ca_complete",
        "check",
        "authority",
        "check",
    ]


def _authority_rows():
    definitions = ("synthetic-forecast-proof-definition", "synthetic-legacy-proof-definition")
    rows = {
        sc.AUTHORITY_CORE_SQL: [
            (
                sc.READER_ROLE,
                sc.READER_ROLE,
                "postgres",
                "postgres",
                False,
                True,
                True,
                False,
                0,
                True,
                True,
                False,
                True,
            )
        ],
        sc.AUTHORITY_ROLE_SQL: [(101, True, False, False, False, False, False, False)],
        sc.AUTHORITY_MEMBERSHIPS_SQL: [],
        sc.AUTHORITY_SCHEMA_CREATE_COUNT_SQL: [(0,)],
        sc.AUTHORITY_RELATION_WRITE_COUNT_SQL: [(0,)],
        sc.AUTHORITY_TABLES_SQL: [
            (table, 1000 + index, True, True, False, False, False, False, True, False)
            for index, table in enumerate(sc.SIX_TABLES)
        ],
        sc.AUTHORITY_FUNCTIONS_SQL: [
            (
                signature,
                sc.EXPECTED_PROOF_DEFINITIONS[signature]["oid"],
                "atom_v9_proof_owner",
                "sql",
                "f",
                True,
                False,
                False,
                "s",
                "u",
                sc.EXPECTED_PROOF_DEFINITIONS[signature]["prorows"],
                ["search_path=pg_catalog"],
                definition,
                True,
            )
            for signature, definition in zip(
                sc.PROOF_FUNCTIONS, definitions, strict=True
            )
        ],
        sc.AUTHORITY_OTHER_SECURITY_DEFINER_COUNT_SQL: [(0,)],
        sc.SHOW_TRANSACTION_ISOLATION_SQL: [("repeatable read",)],
        sc.SHOW_TRANSACTION_READ_ONLY_SQL: [("on",)],
    }
    return rows, definitions


class _AuthorityCursor:
    def __init__(self, rows):
        self.rows = rows
        self.current = None
        self.calls = []

    def execute(self, sql, params=None):
        assert sql in self.rows
        if sql == sc.AUTHORITY_OTHER_SECURITY_DEFINER_COUNT_SQL:
            assert params == {"approved_oids": [42475, 49997]}
        elif params is not None:
            raise AssertionError("unexpected authority query parameters")
        self.current = sql
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows[self.current]


def test_authority_check_builds_exact_catalog_wide_proof_and_rejects_membership(
    tmp_path, monkeypatch
):
    parsed = _parsed_database_uri(tmp_path)
    rows, definitions = _authority_rows()
    expected_hashes = {
        definition.encode(): sc.EXPECTED_PROOF_DEFINITIONS[signature][
            "definition_sha256"
        ]
        for signature, definition in zip(
            sc.PROOF_FUNCTIONS, definitions, strict=True
        )
    }
    real_sha256 = hashlib.sha256

    def controlled_sha256(value=b""):
        if value in expected_hashes:
            return SimpleNamespace(hexdigest=lambda: expected_hashes[value])
        return real_sha256(value)

    monkeypatch.setattr(sc.hashlib, "sha256", controlled_sha256)
    cursor = _AuthorityCursor(rows)
    proof = sc.authority_check(
        cursor,
        parsed,
        _ca_observation(),
        stage=sc.DatabaseFailureStage.NEW_BEFORE_EVIDENCE,
    )
    assert proof == _authority_proof()
    assert [sql for sql, _ in cursor.calls] == [
        sc.AUTHORITY_CORE_SQL,
        sc.AUTHORITY_ROLE_SQL,
        sc.AUTHORITY_MEMBERSHIPS_SQL,
        sc.AUTHORITY_SCHEMA_CREATE_COUNT_SQL,
        sc.AUTHORITY_RELATION_WRITE_COUNT_SQL,
        sc.AUTHORITY_TABLES_SQL,
        sc.AUTHORITY_FUNCTIONS_SQL,
        sc.AUTHORITY_OTHER_SECURITY_DEFINER_COUNT_SQL,
        sc.SHOW_TRANSACTION_ISOLATION_SQL,
        sc.SHOW_TRANSACTION_READ_ONLY_SQL,
    ]

    bad_rows, _ = _authority_rows()
    bad_rows[sc.AUTHORITY_MEMBERSHIPS_SQL] = [("unexpected_membership",)]
    with pytest.raises(sc.DatabaseContractError) as caught:
        sc.authority_check(
            _AuthorityCursor(bad_rows),
            parsed,
            _ca_observation(),
            stage=sc.DatabaseFailureStage.NEW_AFTER_EVIDENCE_BEFORE_SEAL,
        )
    assert caught.value.route is sc.DatabaseFailureRoute.PRE_CELL_INVALID
    assert caught.value.defect is sc.DatabaseDefect.AUTHORITY


def _xnys_session(day: date) -> sc.CalendarSession:
    """A complete regular XNYS session during New York daylight time."""

    return sc.CalendarSession(
        session_date=day,
        market_open=datetime.combine(day, datetime.min.time(), UTC)
        + timedelta(hours=13, minutes=30),
        market_close=datetime.combine(day, datetime.min.time(), UTC)
        + timedelta(hours=20),
    )


def _historical_family_5m_population(
    sessions: tuple[sc.CalendarSession, ...],
) -> sc.EvidencePopulation:
    rows = []
    record_id = 1
    for session in sessions:
        for within_session in range(13):
            cutoff = session.market_open + timedelta(
                minutes=1 + (within_session * 6)
            )
            maturity = cutoff + timedelta(minutes=5)
            forecast_proof = sc.LegacyPublicationProof(
                sc.FAMILY_FORECAST_KIND,
                record_id,
                str(10_000 + record_id),
                cutoff + timedelta(seconds=1),
                sc.PROOF_METHOD,
            )
            outcome_proof = sc.LegacyPublicationProof(
                sc.FAMILY_OUTCOME_KIND,
                record_id,
                str(20_000 + record_id),
                maturity + timedelta(seconds=1),
                sc.PROOF_METHOD,
            )
            rows.append(
                sc.FamilyEvidenceRow(
                    forecast_id=record_id,
                    forecast_inserting_xid=forecast_proof.inserting_xid,
                    quant_id="q3_volatility",
                    formula_version="realized-volatility-v1",
                    cycle_id=f"cycle-{record_id}",
                    symbol="COIN",
                    horizon="5M",
                    cutoff_epoch=cutoff.timestamp(),
                    maturity_epoch=maturity.timestamp(),
                    cutoff_midpoint=100.0,
                    forecast_volatility_bps=2.0 + (record_id % 7),
                    created_epoch=cutoff.timestamp(),
                    data_schema_version="synthetic-v1",
                    source_spec_version="synthetic-v1",
                    outcome_inserting_xid=outcome_proof.inserting_xid,
                    maturity_midpoint=101.0,
                    realized_move_bps=1.0 + (record_id % 11),
                    resolved_epoch=maturity.timestamp(),
                    forecast_proof=forecast_proof,
                    outcome_proof=outcome_proof,
                )
            )
            record_id += 1
    return sc.EvidencePopulation(
        upper_as_of=sessions[-1].market_close,
        family_rows=tuple(rows),
        v9_rows=(),
        source_counts={
            "public.volatility_forecasts": len(rows),
            "public.volatility_forecast_outcomes": len(rows),
            "public.atom_v9_v4_forecasts": 0,
            "public.atom_v9_v4_outcomes": 0,
        },
    )


@pytest.mark.parametrize("formula_version", ("", "模型/β—other"))
def test_family_other_formula_versions_are_counted_as_unselected_not_invalid(
    formula_version,
):
    session = _xnys_session(date(2026, 9, 4))
    candidate = _xnys_session(date(2026, 9, 8))
    cutoff = session.market_open + timedelta(minutes=1)
    maturity = cutoff + timedelta(minutes=5)
    forecast_proof = sc.LegacyPublicationProof(
        sc.FAMILY_FORECAST_KIND,
        1,
        "10001",
        cutoff + timedelta(seconds=1),
        sc.PROOF_METHOD,
    )
    outcome_proof = sc.LegacyPublicationProof(
        sc.FAMILY_OUTCOME_KIND,
        1,
        "20001",
        maturity + timedelta(seconds=1),
        sc.PROOF_METHOD,
    )
    raw = (
        1,
        forecast_proof.inserting_xid,
        "q3_volatility",
        formula_version,
        "cycle-1",
        "COIN",
        "5M",
        cutoff.timestamp(),
        maturity.timestamp(),
        100.0,
        2.0,
        cutoff.timestamp(),
        "synthetic-v1",
        "synthetic-v1",
        outcome_proof.inserting_xid,
        101.0,
        1.0,
        maturity.timestamp(),
    )
    row = sc._validate_family_row(
        raw,
        forecast_proof=forecast_proof,
        outcome_proof=outcome_proof,
    )
    evidence = sc.EvidencePopulation(
        candidate.market_close,
        (row,),
        (),
        {
            "public.volatility_forecasts": 1,
            "public.volatility_forecast_outcomes": 1,
            "public.atom_v9_v4_forecasts": 0,
            "public.atom_v9_v4_outcomes": 0,
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("V9 primitive unexpectedly used")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=forbidden,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )
    _lineages, populations = sc.build_candidate_populations(
        "v1b-family-5m",
        evidence,
        candidate,
        (session, candidate),
        primitives,
    )
    population = populations[0]
    assert population.protocol_defect is False
    assert population.n_input == 1
    assert population.n_unselected_lineage_rows == 1
    assert population.n_inadmissible == 0
    assert population.n_non_rth == 0
    assert population.windows == ()


@pytest.mark.parametrize("formula_version", ("", "模型/β—other"))
def test_family_other_formula_is_lineage_rejected_before_selected_payload_validation(
    formula_version,
):
    """Unselected formulas cannot turn irrelevant payload defects into INVALID."""

    session = _xnys_session(date(2026, 9, 4))
    candidate = _xnys_session(date(2026, 9, 8))
    cutoff = session.market_open + timedelta(minutes=1)
    maturity = cutoff + timedelta(minutes=5)
    raw = (
        1,
        "10001",
        "q3_volatility",
        formula_version,
        None,  # selected-formula cycle validation is deliberately violated
        "COIN",
        "5M",
        cutoff.timestamp(),
        maturity.timestamp(),
        object(),
        object(),
        "not-an-epoch",
        None,
        [],
        "not-an-xid",
        None,  # deliberately partial/malformed selected-formula outcome
        object(),
        "not-an-epoch",
    )
    mismatched_forecast_proof = sc.LegacyPublicationProof(
        sc.FAMILY_FORECAST_KIND,
        1,
        "99991",
        cutoff + timedelta(seconds=1),
        sc.PROOF_METHOD,
    )
    mismatched_outcome_proof = sc.LegacyPublicationProof(
        sc.FAMILY_OUTCOME_KIND,
        1,
        "99992",
        maturity + timedelta(seconds=1),
        sc.PROOF_METHOD,
    )
    row = sc._validate_family_row(
        raw,
        forecast_proof=mismatched_forecast_proof,
        outcome_proof=mismatched_outcome_proof,
    )
    evidence = sc.EvidencePopulation(
        candidate.market_close,
        (row,),
        (),
        {
            "public.volatility_forecasts": 1,
            "public.volatility_forecast_outcomes": 1,
            "public.atom_v9_v4_forecasts": 0,
            "public.atom_v9_v4_outcomes": 0,
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("unselected FAMILY payload reached a V9 primitive")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=forbidden,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )
    _lineages, populations = sc.build_candidate_populations(
        "v1b-family-5m",
        evidence,
        candidate,
        (session, candidate),
        primitives,
    )
    assert populations[0].n_input == 1
    assert populations[0].n_unselected_lineage_rows == 1
    assert populations[0].protocol_defect is False

    # The narrow lineage-first rule does not weaken the outer stream identity.
    for index, replacement in (
        (0, 0),
        (2, "other-quant"),
        (3, None),
        (5, "ETH"),
        (6, "2H"),
    ):
        malformed = list(raw)
        malformed[index] = replacement
        with pytest.raises(ValueError):
            sc._validate_family_row(
                tuple(malformed),
                forecast_proof=None,
                outcome_proof=None,
            )


@pytest.mark.parametrize("cutoff_epoch", (math.nan, -math.inf, 1.0e300))
def test_family_other_formula_extreme_cutoff_counts_only_as_unselected(
    cutoff_epoch,
):
    """SQL-bounded nonselected rows never enter proof or metric semantics."""

    session = _xnys_session(date(2026, 9, 8))
    maturity = session.market_open + timedelta(minutes=6)
    raw = (
        1,
        "10001",
        "q3_volatility",
        "other-formula",
        None,
        "COIN",
        "5M",
        cutoff_epoch,
        maturity.timestamp(),
        object(),
        object(),
        object(),
        None,
        None,
        "malformed-outcome-xid",
        object(),
        object(),
        object(),
    )
    mismatched = sc.LegacyPublicationProof(
        sc.FAMILY_FORECAST_KIND,
        1,
        "99999",
        session.market_open,
        sc.PROOF_METHOD,
    )
    row = sc._validate_family_row(
        raw,
        forecast_proof=mismatched,
        outcome_proof=replace(mismatched, evidence_kind=sc.FAMILY_OUTCOME_KIND),
    )
    assert row.forecast_proof is None
    assert row.outcome_proof is None
    evidence = sc.EvidencePopulation(
        session.market_close,
        (row,),
        (),
        {
            "public.volatility_forecasts": 1,
            "public.volatility_forecast_outcomes": 1,
            "public.atom_v9_v4_forecasts": 0,
            "public.atom_v9_v4_outcomes": 0,
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("unselected FAMILY payload reached inference")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=forbidden,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )
    _lineages, populations = sc.build_candidate_populations(
        "v1b-family-5m", evidence, session, (session,), primitives
    )
    assert populations[0].n_input == 1
    assert populations[0].n_unselected_lineage_rows == 1
    assert populations[0].windows == ()

    selected = list(raw)
    selected[3] = "realized-volatility-v1"
    with pytest.raises(ValueError):
        sc._validate_family_row(
            tuple(selected), forecast_proof=None, outcome_proof=None
        )


def test_family_overlap_uses_raw_binary64_epoch_before_datetime_rounding():
    """Match E-1's strict raw-float overlap comparison below one microsecond."""

    session = _xnys_session(date(2026, 9, 8))
    first_cutoff = session.market_open.timestamp() + 60.0
    delta = 2.384185791015625e-7
    second_cutoff = first_cutoff + 300.0 - delta
    assert second_cutoff < first_cutoff + 300.0
    rows = []
    for record_id, cutoff_epoch in enumerate(
        (first_cutoff, second_cutoff), start=1
    ):
        maturity_epoch = cutoff_epoch + 300.0
        forecast_proof = sc.LegacyPublicationProof(
            sc.FAMILY_FORECAST_KIND,
            record_id,
            str(10_000 + record_id),
            datetime.fromtimestamp(cutoff_epoch + 1.0, UTC),
            sc.PROOF_METHOD,
        )
        outcome_proof = sc.LegacyPublicationProof(
            sc.FAMILY_OUTCOME_KIND,
            record_id,
            str(20_000 + record_id),
            datetime.fromtimestamp(maturity_epoch + 1.0, UTC),
            sc.PROOF_METHOD,
        )
        rows.append(
            sc.FamilyEvidenceRow(
                forecast_id=record_id,
                forecast_inserting_xid=forecast_proof.inserting_xid,
                quant_id="q3_volatility",
                formula_version="realized-volatility-v1",
                cycle_id=f"cycle-{record_id}",
                symbol="COIN",
                horizon="5M",
                cutoff_epoch=cutoff_epoch,
                maturity_epoch=maturity_epoch,
                cutoff_midpoint=100.0,
                forecast_volatility_bps=2.0,
                created_epoch=cutoff_epoch,
                data_schema_version="synthetic-v1",
                source_spec_version="synthetic-v1",
                outcome_inserting_xid=outcome_proof.inserting_xid,
                maturity_midpoint=101.0,
                realized_move_bps=1.0,
                resolved_epoch=maturity_epoch,
                forecast_proof=forecast_proof,
                outcome_proof=outcome_proof,
            )
        )
    evidence = sc.EvidencePopulation(
        session.market_close,
        tuple(rows),
        (),
        {
            "public.volatility_forecasts": 2,
            "public.volatility_forecast_outcomes": 2,
            "public.atom_v9_v4_forecasts": 0,
            "public.atom_v9_v4_outcomes": 0,
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("V9 primitive unexpectedly used")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=forbidden,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )
    _lineages, populations = sc.build_candidate_populations(
        "v1b-family-5m", evidence, session, (session,), primitives
    )
    population = populations[0]
    assert population.n_input == 2
    assert population.n_overlap_excluded == 1
    assert tuple(window.record_identity for window in population.windows) == (
        "00000000000000000001",
    )


def test_family_stream_sql_projection_is_the_exact_eighteen_column_row_shape():
    projection = sc.FAMILY_STREAM_SQL.split("SELECT ", 1)[1].split("\nFROM ", 1)[0]
    columns = tuple(item.strip() for item in projection.split(","))
    assert columns == (
        "f.forecast_id",
        "f.xmin::text::xid8::text AS forecast_inserting_xid",
        "f.quant_id",
        "f.formula_version",
        "f.cycle_id",
        "f.symbol",
        "f.horizon",
        "f.cutoff_epoch",
        "f.maturity_epoch",
        "f.cutoff_midpoint",
        "f.forecast_volatility_bps",
        "f.created_epoch",
        "f.data_schema_version",
        "f.source_spec_version",
        "o.xmin::text::xid8::text AS outcome_inserting_xid",
        "o.maturity_midpoint",
        "o.realized_move_bps",
        "o.resolved_epoch",
    )
    assert sc.FAMILY_STREAM_SQL.count("o.realized_move_bps") == 1


def test_post_amendment_candidate_uses_complete_historical_xnys_sessions():
    """The post-T_amend boundary must not erase pre-amendment evidence."""

    historical_days = (
        date(2026, 8, 21),
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    )
    historical_sessions = tuple(_xnys_session(day) for day in historical_days)
    candidate = _xnys_session(date(2026, 9, 8))
    evidence = _historical_family_5m_population(historical_sessions)

    def forbidden(*args, **kwargs):
        raise AssertionError("V9 primitives are not used by a FAMILY-only manifest")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=forbidden,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )
    result = sc.scan_manifest_candidates(
        "v1b-family-5m",
        evidence,
        completed=(candidate,),
        full_sessions=historical_sessions + (candidate,),
        primitives=primitives,
    )

    assert result.first_candidate_session == date(2026, 9, 8)
    assert result.completed_candidates == (candidate,)
    assert result.boundary is not None
    assert result.boundary.session == candidate
    assert len(result.boundary.populations) == 1
    population = result.boundary.populations[0]
    counts = result.boundary.counts[0]
    assert population.n_non_rth == 0
    assert len(population.windows) == 143
    assert counts == sc.ReadinessCounts(
        sc.CELL_BY_ORDER[2], 123, 10, 122, 10, 122, 10
    )
    assert sc.manifest_is_ready("v1b-family-5m", (counts,))


def test_scorecard_cli_accepts_only_the_closed_manifest_registry_and_recovery_option():
    for manifest_id in sc.MANIFEST_REGISTRY:
        invocation = sc.parse_scorecard_cli(("--manifest-id", manifest_id))
        assert invocation == sc.Invocation(
            manifest_id, None, sc.InvocationMode.NEW_SEAL
        )

    recovery_path = "/tmp/atom-v1b-seals/" + ("a" * 64) + ".json"
    invocation = sc.parse_scorecard_cli(
        (
            "--manifest-id",
            "v1b-family-5m",
            "--recovery-seal-file",
            recovery_path,
        )
    )
    assert invocation == sc.Invocation(
        "v1b-family-5m", recovery_path, sc.InvocationMode.RECOVERY
    )


@pytest.mark.parametrize(
    "argv",
    (
        (),
        ("--manifest-id",),
        ("--manifest-id", "unknown"),
        ("--manifest-id=v1b-family-5m",),
        ("--manifest-id", "v1b-family-5m", "--force", "1"),
        ("--manifest-id", "v1b-family-5m", "--manifest-id", "v1b-family-5m"),
        ("--manifest-id", "v1b-family-5m", "--recovery-seal-file"),
        (
            "--recovery-seal-file",
            "/tmp/atom-v1b-seals/" + ("a" * 64) + ".json",
            "--manifest-id",
            "v1b-family-5m",
        ),
        (
            "--manifest-id",
            "v1b-family-5m",
            "--recovery-seal-file",
            "/tmp/seal.json",
            "--recovery-seal-file",
            "/tmp/seal.json",
        ),
    ),
)
def test_scorecard_cli_rejects_missing_unknown_duplicate_and_extra_inputs(argv):
    with pytest.raises(sc.ContractError, match="INVALID_MANIFEST_ID"):
        sc.parse_scorecard_cli(argv)


def test_public_scorecard_main_writes_exact_usage_line_without_entering_runtime(
    monkeypatch,
):
    output = []
    dependencies = SimpleNamespace(write_stdout=output.append)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid CLI must not enter the orchestration state machine")

    monkeypatch.setattr(sc, "run_scorecard", forbidden)
    assert sc.scorecard_main(("--manifest-id", "not-in-the-registry"), dependencies) == 2
    assert output == [
        b'{"mode":"V1B","reason":"INVALID_MANIFEST_ID","status":"USAGE_ERROR"}\n'
    ]


def test_public_scorecard_main_writes_exact_invalid_recovery_line_before_runtime(
    tmp_path, monkeypatch
):
    output = []
    dependencies = SimpleNamespace(write_stdout=output.append)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid recovery bytes must not enter orchestration")

    monkeypatch.setattr(sc, "run_scorecard", forbidden)
    missing = tmp_path / ("a" * 64 + ".json")
    assert sc.scorecard_main(
        (
            "--manifest-id",
            "v1b-family-5m",
            "--recovery-seal-file",
            str(missing),
        ),
        dependencies,
    ) == 2
    assert output == [
        b'{"manifest_id":"v1b-family-5m","mode":"V1B",'
        b'"reason":"INVALID_RECOVERY_SEAL","status":"USAGE_ERROR"}\n'
    ]


def test_public_scorecard_main_dispatches_normal_and_exact_recovery_invocations(
    tmp_path, monkeypatch
):
    parts = _ready_schema_parts()
    seal_path = tmp_path / f"{parts.seal.seal_record_sha256}.json"
    seal_path.write_bytes(parts.seal.canonical_bytes)
    calls = []
    dependencies = SimpleNamespace(write_stdout=lambda raw: None)

    def run(invocation, recovery_seal, observed_dependencies):
        calls.append((invocation, recovery_seal, observed_dependencies))
        return 17 + len(calls)

    monkeypatch.setattr(sc, "run_scorecard", run)
    assert sc.scorecard_main(
        ("--manifest-id", "v1b-family-5m"), dependencies
    ) == 18
    assert calls[0] == (
        sc.Invocation("v1b-family-5m", None, sc.InvocationMode.NEW_SEAL),
        None,
        dependencies,
    )

    assert sc.scorecard_main(
        (
            "--manifest-id",
            "v1b-family-5m",
            "--recovery-seal-file",
            str(seal_path),
        ),
        dependencies,
    ) == 19
    invocation, recovery, observed_dependencies = calls[1]
    assert invocation == sc.Invocation(
        "v1b-family-5m", str(seal_path), sc.InvocationMode.RECOVERY
    )
    assert recovery is not None
    assert recovery.canonical_bytes == parts.seal.canonical_bytes
    assert recovery.seal_record_sha256 == parts.seal.seal_record_sha256
    assert observed_dependencies is dependencies


def test_zero_argument_main_delegates_to_public_scorecard_main(monkeypatch):
    calls = []

    def scorecard_main(argv=None, dependencies=None):
        calls.append((argv, dependencies))
        return 23

    monkeypatch.setattr(sc, "scorecard_main", scorecard_main)
    assert sc.main() == 23
    assert calls == [(None, None)]


@pytest.mark.parametrize("recovery", (False, True))
def test_production_startup_failure_uses_stage_correct_official_receipt(
    tmp_path, monkeypatch, recovery
):
    parts = _ready_schema_parts()
    output = []
    argv = ["--manifest-id", parts.manifest_id]
    if recovery:
        seal_path = tmp_path / f"{parts.seal.seal_record_sha256}.json"
        seal_path.write_bytes(parts.seal.canonical_bytes)
        argv.extend(("--recovery-seal-file", str(seal_path)))

    def startup_failure(**kwargs):
        raise sc.StartupIsolationError("synthetic guarded-start failure")

    def forbidden(*args, **kwargs):
        raise AssertionError("dependency construction must not follow startup failure")

    monkeypatch.setattr(sc, "_write_stdout_bytes", output.append)
    monkeypatch.setattr(sc, "assert_production_startup", startup_failure)
    monkeypatch.setattr(sc, "build_production_dependencies", forbidden)
    assert sc.scorecard_main(tuple(argv)) == 1
    if recovery:
        assert output == []
    else:
        assert len(output) == 1
        receipt = json.loads(output[0])
        assert receipt["schema_version"] == "ATOM-V1B-MANIFEST-BLOCKED-RECEIPT-1"
        assert receipt["readiness"] is None
        assert receipt["sealed_run_identity"] is None
        assert receipt["seal_record_sha256"] is None


def test_recovery_seal_reader_accepts_exact_bytes_and_rejects_path_or_content_drift(
    tmp_path,
):
    parts = _ready_schema_parts()
    seal_path = tmp_path / f"{parts.seal.seal_record_sha256}.json"
    seal_path.write_bytes(parts.seal.canonical_bytes)
    invocation = sc.Invocation(
        parts.manifest_id, str(seal_path), sc.InvocationMode.RECOVERY
    )
    observed = sc.read_recovery_seal(invocation)
    assert observed is not None
    assert observed.canonical_bytes == parts.seal.canonical_bytes
    assert observed.seal_record_sha256 == parts.seal.seal_record_sha256

    relative = sc.Invocation(
        parts.manifest_id, seal_path.name, sc.InvocationMode.RECOVERY
    )
    with pytest.raises(sc.OrchestrationFailure, match="INVALID_RECOVERY_SEAL"):
        sc.read_recovery_seal(relative)

    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(parts.seal.canonical_bytes.rstrip(b"\n"))
    with pytest.raises(sc.OrchestrationFailure, match="INVALID_RECOVERY_SEAL"):
        sc.read_recovery_seal(
            sc.Invocation(parts.manifest_id, str(malformed), sc.InvocationMode.RECOVERY)
        )

    mismatched_manifest = sc.Invocation(
        "v1b-family-15m", str(seal_path), sc.InvocationMode.RECOVERY
    )
    with pytest.raises(sc.OrchestrationFailure, match="INVALID_RECOVERY_SEAL"):
        sc.read_recovery_seal(mismatched_manifest)

    symlink = tmp_path / "seal-link.json"
    symlink.symlink_to(seal_path)
    with pytest.raises(sc.OrchestrationFailure, match="INVALID_RECOVERY_SEAL"):
        sc.read_recovery_seal(
            sc.Invocation(parts.manifest_id, str(symlink), sc.InvocationMode.RECOVERY)
        )


def _orchestration_runtime_state():
    identity, dependency_versions, _libpq_version = _runtime_identity()
    components = sc.ArtifactComponents(**identity["runtime_artifact_components"])
    module_names = frozenset({"quant.volatility_scorecard", "math"})
    measurement = sc.RuntimeMeasurement(
        components=components,
        runtime_artifact_sha256=identity["runtime_artifact_sha256"],
        libm_dispatch=identity["libm_dispatch"],
        libm_dispatch_sha256=identity["libm_dispatch_sha256"],
        dependency_versions=tuple(sorted(dependency_versions.items())),
        module_names=module_names,
        python_executable_record=sc.FileRecord(
            "/usr/local/bin/python3.14",
            1,
            identity["runtime_artifact_components"]["python_executable_sha256"],
        ),
        native_records=(
            sc.FileRecord(
                "/usr/lib/x86_64-linux-gnu/libm.so.6",
                1,
                identity["runtime_artifact_components"][
                    "loaded_native_tree_sha256"
                ],
            ),
        ),
    )
    manifest_body = {
        key: identity[key]
        for key in sc.RUNTIME_IDENTITY_KEYS
        if key != "runtime_manifest_sha256"
    }
    frozen = sc.FrozenRuntime(
        runtime_manifest_body=manifest_body,
        runtime_manifest_sha256=identity["runtime_manifest_sha256"],
        artifact_components=components.public(),
        module_names=module_names,
    )
    return sc.RuntimeState(
        plan=SimpleNamespace(name="synthetic-runtime-plan"),
        measurement=measurement,
        frozen=frozen,
        identity=identity,
    )


def _orchestration_checkpoint(runtime, manifest_id, *, receipts=()):
    execution_sha = "a" * 40
    payload = {
            "provenance": {
                "execution_source_sha": execution_sha,
                "runtime_artifact_components": runtime.measurement.components.public(),
            },
            "capacity": {
                "mechanism": "Render native one-off Create job startCommand",
                "recovery_transport_policy": "EXACT_SUBMISSION_OR_CONSUMING_INCIDENT",
                "service_id": "srv-daa7thgae00c73a2lmn0",
            },
        }
    window = {
            "execution_source_sha": execution_sha,
            "manifest_id": manifest_id,
        }
    current = sc.ApprovalComment(
        comment_id=20,
        created_at="2026-09-07T12:05:00Z",
        canonical_body=b"synthetic canonical approval body\n",
        payload=payload,
        window=window,
        review_comment_id=19,
        reviewer_user_id=999,
        reviewer_login="independent-reviewer",
    )
    review = sc.ReviewComment(
        comment_id=19,
        author_id=999,
        author_login="independent-reviewer",
        created_at="2026-09-07T12:00:00Z",
        canonical_body=b"synthetic canonical review body\n",
        approval_payload_sha256=sc.canonical_sha256(payload),
    )
    selection = sc.ApprovalSelection(
        current=current,
        current_review=review,
        repository_fingerprints=(
            sc.ApprovalFingerprint(
                current.comment_id,
                501,
                sc.ApprovalState.CURRENT,
                current.body_sha256,
            ),
        ),
    )
    return sc.RepositoryCheckpoint(
        execution_sha=execution_sha,
        selection=selection,
        facts=sc.ImmutableRepositoryFacts(
            execution_sha=execution_sha,
            implementation_merge_sha="f" * 40,
            amendment_merged_at_utc="2026-09-05T15:45:58.000000Z",
            receipts=tuple(receipts),
            history_sha256="e" * 64,
        ),
    )


def _terminal_early_prior_receipt():
    return sc.PriorReceipt(
        path="docs/v-1b-volatility-scorecard-receipt-v1b-early-4-synthetic.json",
        raw=b"synthetic prior receipt is not re-parsed by the state-machine seam\n",
        manifest_id="v1b-early-4",
        schema_version="ATOM-V1B-MANIFEST-RECEIPT-1",
        terminal=True,
        receipt_sha256="d" * 64,
        seal_record_sha256="c" * 64,
    )


def _routing_dependencies(runtime, checkpoint, output):
    def remeasure_runtime(initial, check):
        if check is not None:
            check()
        return initial

    def repository_checkpoint(
        stage,
        execution_sha,
        manifest_id,
        current_runtime,
        initial,
        finalizer,
    ):
        if finalizer is not None:
            runtime_finalizer = finalizer(lambda: None)
            runtime_finalizer(lambda: None)
        return checkpoint

    return sc.OrchestrationDependencies(
        validate_startup=lambda invocation: None,
        execution_identity=lambda: sc.ExecutionIdentity(
            "a" * 40, "a" * 40, "a" * 40
        ),
        prepare_runtime=lambda: runtime,
        remeasure_runtime=remeasure_runtime,
        repository_checkpoint=repository_checkpoint,
        open_snapshot=lambda seal: (_ for _ in ()).throw(
            AssertionError("patched snapshot runner owns this synthetic path")
        ),
        load_evidence=lambda *args: (_ for _ in ()).throw(
            AssertionError("evidence must not be read by routing fixture")
        ),
        calendar_sessions=lambda *args: (),
        primitives=SimpleNamespace(),
        emit_seal=lambda raw: hashlib.sha256(raw).hexdigest(),
        write_stdout=output.append,
        utc_now=lambda: datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
    )


def test_public_scorecard_main_reaches_exact_wait_without_opening_snapshot():
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(runtime, "v1b-family-5m")
    output = []
    dependencies = _routing_dependencies(runtime, checkpoint, output)
    assert sc.scorecard_main(
        ("--manifest-id", "v1b-family-5m"), dependencies
    ) == 0
    assert output == [
        b'{"manifest_id":"v1b-family-5m","mode":"V1B",'
        b'"readiness_status":"WAIT_FIRST_MANIFEST"}\n'
    ]


@pytest.mark.parametrize("failure_point", ("partial_write", "flush"))
def test_wait_output_sink_failure_is_one_attempt_without_fallback(failure_point):
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(runtime, "v1b-family-5m")
    attempted = []

    def failing_sink(raw):
        attempted.append(raw[:11] if failure_point == "partial_write" else raw)
        raise OSError(f"synthetic {failure_point} failure")

    dependencies = _routing_dependencies(runtime, checkpoint, [])
    dependencies = replace(dependencies, write_stdout=failing_sink)
    invocation = sc.Invocation(
        "v1b-family-5m", None, sc.InvocationMode.NEW_SEAL
    )
    assert sc.run_scorecard(invocation, None, dependencies) == 1
    assert len(attempted) == 1
    assert attempted[0] == (
        sc._wait_line("v1b-family-5m")[:11]
        if failure_point == "partial_write"
        else sc._wait_line("v1b-family-5m")
    )


@pytest.mark.parametrize(
    "output",
    (
        b'{"manifest_id":"v1b-family-5m","mode":"V1B",'
        b'"readiness_status":"HOLD"}\n',
        b'{"schema_version":"ATOM-V1B-MANIFEST-RECEIPT-1"}\n',
    ),
    ids=("hold", "evaluated-receipt"),
)
@pytest.mark.parametrize("failure_point", ("partial_write", "flush"))
def test_hold_and_final_receipt_sink_failures_are_one_attempt_without_fallback(
    output, failure_point, monkeypatch
):
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(
        runtime,
        "v1b-family-5m",
        receipts=(_terminal_early_prior_receipt(),),
    )
    attempted = []

    def failing_sink(raw):
        attempted.append(raw[:13] if failure_point == "partial_write" else raw)
        raise OSError(f"synthetic {failure_point} failure")

    dependencies = replace(
        _routing_dependencies(runtime, checkpoint, []),
        write_stdout=failing_sink,
    )
    monkeypatch.setattr(sc, "_run_snapshot", lambda state, deps: output)
    invocation = sc.Invocation(
        "v1b-family-5m", None, sc.InvocationMode.NEW_SEAL
    )
    assert sc.run_scorecard(invocation, None, dependencies) == 1
    assert attempted == [
        output[:13] if failure_point == "partial_write" else output
    ]


@pytest.mark.parametrize("failure_point", ("partial_write", "flush"))
def test_partial_seal_sink_failure_never_attempts_a_negative_receipt(
    failure_point, monkeypatch
):
    parts = _ready_schema_parts()
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(
        runtime,
        parts.manifest_id,
        receipts=(_terminal_early_prior_receipt(),),
    )
    candidate = _xnys_session(date(2026, 9, 8))
    scan = sc.ScanResult(
        first_candidate_session=candidate.session_date,
        completed_candidates=(candidate,),
        boundary=sc.CandidateResult(candidate, (), (), (), ()),
    )
    snapshot = sc.SnapshotSession(
        connection=object(),
        cursor=object(),
        parsed=SimpleNamespace(),
        initial_ca=SimpleNamespace(),
        initial_authority_proof=parts.authority,
        scan_started_at=candidate.market_close,
        recovery_started_at=None,
        _ca_recheck=lambda stage: SimpleNamespace(),
    )

    class SnapshotContext:
        def __enter__(self):
            return snapshot

        def __exit__(self, exc_type, exc, traceback):
            return False

    seal_attempts = []
    receipt_attempts = []

    def failing_seal_sink(raw):
        seal_attempts.append(
            raw[:17] if failure_point == "partial_write" else raw
        )
        raise OSError(f"synthetic seal {failure_point} failure")

    dependencies = sc.OrchestrationDependencies(
        validate_startup=lambda invocation: None,
        execution_identity=lambda: sc.ExecutionIdentity(
            "a" * 40, "a" * 40, "a" * 40
        ),
        prepare_runtime=lambda: runtime,
        remeasure_runtime=lambda initial, check: initial,
        repository_checkpoint=lambda *args: checkpoint,
        open_snapshot=lambda seal: SnapshotContext(),
        load_evidence=lambda *args: SimpleNamespace(),
        calendar_sessions=lambda *args: (candidate,),
        primitives=SimpleNamespace(),
        emit_seal=failing_seal_sink,
        write_stdout=receipt_attempts.append,
        utc_now=lambda: datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(sc, "enumerate_xnys_candidates", lambda *args, **kwargs: (candidate,))
    monkeypatch.setattr(sc, "_evidence_first_date", lambda *args, **kwargs: candidate.session_date)
    monkeypatch.setattr(sc, "qualifying_full_xnys_sessions", lambda sessions: (candidate,))
    monkeypatch.setattr(sc, "scan_manifest_candidates", lambda *args, **kwargs: scan)
    monkeypatch.setattr(sc, "_ready_scan_projection", lambda observed: {"ready": True})
    monkeypatch.setattr(
        sc,
        "_readiness_parts",
        lambda **kwargs: (
            parts.readiness_body,
            parts.readiness,
            parts.run_body,
            parts.run_identity,
        ),
    )
    invocation = sc.Invocation(parts.manifest_id, None, sc.InvocationMode.NEW_SEAL)
    state = sc.InvocationState(
        invocation=invocation,
        phase=sc.InvocationPhase.INITIAL_AUTHORITY,
        expected_sha="a" * 40,
        checkpoint=checkpoint,
        runtime=runtime,
    )
    with pytest.raises(sc.OutputSinkFailure):
        sc._run_snapshot(state, dependencies)
    assert len(seal_attempts) == 1
    assert receipt_attempts == []

    # The public orchestrator treats that ambiguous sink state as terminal and
    # never tries to append a negative receipt to a possibly partial seal.
    monkeypatch.setattr(
        sc,
        "_run_snapshot",
        lambda state, deps: (_ for _ in ()).throw(sc.OutputSinkFailure()),
    )
    assert sc.run_scorecard(invocation, None, dependencies) == 1
    assert receipt_attempts == []


def test_final_authority_event_order_ends_with_runtime_then_receipt(monkeypatch):
    parts = _ready_schema_parts()
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(
        runtime,
        parts.manifest_id,
        receipts=(_terminal_early_prior_receipt(),),
    )
    candidate = _xnys_session(date(2026, 9, 8))
    scan = sc.ScanResult(
        first_candidate_session=candidate.session_date,
        completed_candidates=(candidate,),
        boundary=sc.CandidateResult(candidate, (), (), (), ()),
    )
    events = []

    final_context = sc.GithubDeadlineContext(checkpoint_end_ns=1_000_000)

    def final_clock():
        events.append("final_runtime_deadline_check")
        return 0

    class ObservedSnapshot(sc.SnapshotSession):
        def final_authority_check(self, *, context=None, clock_ns=None):
            assert context is final_context
            assert clock_ns is final_clock
            events.append("final_database_authority")
            return parts.authority

        def close_after_final_authority(self):
            events.append("snapshot_database_close")

    snapshot = ObservedSnapshot(
        connection=object(),
        cursor=object(),
        parsed=SimpleNamespace(),
        initial_ca=SimpleNamespace(),
        initial_authority_proof=parts.authority,
        scan_started_at=candidate.market_close,
        recovery_started_at=None,
        _ca_recheck=lambda stage: SimpleNamespace(),
    )

    class SnapshotContext:
        def __enter__(self):
            events.append("snapshot_enter")
            return snapshot

        def __exit__(self, exc_type, exc, traceback):
            events.append("snapshot_exit")
            return False

    runtime_checks = 0

    def repository_checkpoint(
        stage,
        execution_sha,
        manifest_id,
        current_runtime,
        initial,
        finalizer,
    ):
        if stage is sc.AuthorityStage.FINAL_AFTER_COMPLETE_TRUTHFUL_CELLS:
            events.append("final_github_and_source")
            events.append("final_ruleset_and_ref_reread_complete")
            assert finalizer is not None

            runtime_finalizer = finalizer(final_context, final_clock)
            final_checkpoint_check = final_context.checker(final_clock)
            events.append("closing_github_ca_and_zone")
            runtime_finalizer(final_checkpoint_check)
            events.append("final_repository_checkpoint_return")
        else:
            events.append("preseal_github_and_source")
            assert finalizer is None
        return checkpoint

    def remeasure(initial, check):
        nonlocal runtime_checks
        runtime_checks += 1
        if runtime_checks == 1:
            assert check is None
        else:
            assert check is not None
            check()
        events.append(
            "final_runtime_remeasurement"
            if runtime_checks == 2
            else "preseal_runtime_remeasurement"
        )
        return initial

    dependencies = sc.OrchestrationDependencies(
        validate_startup=lambda invocation: None,
        execution_identity=lambda: sc.ExecutionIdentity(
            "a" * 40, "a" * 40, "a" * 40
        ),
        prepare_runtime=lambda: runtime,
        remeasure_runtime=remeasure,
        repository_checkpoint=repository_checkpoint,
        open_snapshot=lambda seal: SnapshotContext(),
        load_evidence=lambda *args: SimpleNamespace(),
        calendar_sessions=lambda *args: (candidate,),
        primitives=SimpleNamespace(),
        emit_seal=lambda raw: (
            events.append("seal"), hashlib.sha256(raw).hexdigest()
        )[1],
        write_stdout=lambda raw: None,
        utc_now=lambda: (
            events.append("generated_at"),
            datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
        )[1],
    )
    monkeypatch.setattr(sc, "enumerate_xnys_candidates", lambda *args, **kwargs: (candidate,))
    monkeypatch.setattr(sc, "_evidence_first_date", lambda *args, **kwargs: candidate.session_date)
    monkeypatch.setattr(sc, "qualifying_full_xnys_sessions", lambda sessions: (candidate,))
    monkeypatch.setattr(sc, "scan_manifest_candidates", lambda *args, **kwargs: scan)
    monkeypatch.setattr(sc, "_ready_scan_projection", lambda observed: {"ready": True})
    monkeypatch.setattr(
        sc,
        "_readiness_parts",
        lambda **kwargs: (
            parts.readiness_body,
            parts.readiness,
            parts.run_body,
            parts.run_identity,
        ),
    )

    class Receipt:
        canonical_bytes = b"synthetic evaluated receipt\n"

    def build_receipt(**kwargs):
        events.append("receipt_construction")
        return Receipt()

    monkeypatch.setattr(sc, "build_evaluated_receipt", build_receipt)
    state = sc.InvocationState(
        invocation=sc.Invocation(
            parts.manifest_id, None, sc.InvocationMode.NEW_SEAL
        ),
        phase=sc.InvocationPhase.INITIAL_AUTHORITY,
        expected_sha="a" * 40,
        checkpoint=checkpoint,
        runtime=runtime,
    )
    assert sc._run_snapshot(state, dependencies) == Receipt.canonical_bytes
    non_deadline_events = [
        event for event in events if event != "final_runtime_deadline_check"
    ]
    assert non_deadline_events == [
        "snapshot_enter",
        "preseal_github_and_source",
        "preseal_runtime_remeasurement",
        "seal",
        "final_github_and_source",
        "final_ruleset_and_ref_reread_complete",
        "final_database_authority",
        "snapshot_database_close",
        "closing_github_ca_and_zone",
        "final_runtime_remeasurement",
        "final_repository_checkpoint_return",
        "generated_at",
        "receipt_construction",
        "snapshot_exit",
    ]
    closing_index = events.index("final_ruleset_and_ref_reread_complete")
    database_index = events.index("final_database_authority")
    close_index = events.index("snapshot_database_close")
    ca_zone_index = events.index("closing_github_ca_and_zone")
    runtime_index = events.index("final_runtime_remeasurement")
    checkpoint_return_index = events.index("final_repository_checkpoint_return")
    deadline_indexes = [
        index
        for index, event in enumerate(events)
        if event == "final_runtime_deadline_check"
    ]
    assert deadline_indexes
    assert closing_index < database_index < close_index < ca_zone_index < runtime_index
    assert events[database_index - 1] == "final_runtime_deadline_check"
    assert events[close_index + 1] == "final_runtime_deadline_check"
    assert events[runtime_index - 1] == "final_runtime_deadline_check"
    assert events[runtime_index + 1] == "final_runtime_deadline_check"
    assert all(
        closing_index < index < checkpoint_return_index
        for index in deadline_indexes
    )


@pytest.mark.parametrize("emitter", ("blocked", "pre_cell", "post_authority"))
@pytest.mark.parametrize("failure_point", ("partial_write", "flush"))
def test_negative_receipt_sink_failure_is_one_attempt_without_fallback(
    emitter, failure_point
):
    parts = _ready_schema_parts()
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(runtime, parts.manifest_id)
    attempted = []

    def failing_sink(raw):
        attempted.append(raw[:19] if failure_point == "partial_write" else raw)
        raise OSError(f"synthetic negative {failure_point} failure")

    dependencies = replace(
        _routing_dependencies(runtime, checkpoint, []),
        write_stdout=failing_sink,
    )
    state = sc.InvocationState(
        invocation=sc.Invocation(
            parts.manifest_id, None, sc.InvocationMode.NEW_SEAL
        ),
        expected_sha="a" * 40,
        checkpoint=checkpoint,
        runtime=runtime,
    )
    if emitter == "blocked":
        result = sc._emit_blocked(state, dependencies)
    elif emitter == "pre_cell":
        result = sc._emit_pre_cell(state, dependencies)
    else:
        state.seal = parts.seal
        state.phase = sc.InvocationPhase.FINISHED
        result = sc._emit_post_authority(state, dependencies)
    assert result == 1
    assert len(attempted) == 1


def test_pre_cell_emitter_serializes_constant_read_only_database_identity():
    runtime = _orchestration_runtime_state()
    manifest_id = "v1b-family-5m"
    checkpoint = _orchestration_checkpoint(
        runtime, manifest_id, receipts=(_terminal_early_prior_receipt(),)
    )
    output = []
    dependencies = _routing_dependencies(runtime, checkpoint, output)
    state = sc.InvocationState(
        invocation=sc.Invocation(manifest_id, None, sc.InvocationMode.NEW_SEAL),
        phase=sc.InvocationPhase.EVIDENCE_READ,
        expected_sha="a" * 40,
        checkpoint=checkpoint,
        runtime=runtime,
        snapshot=SimpleNamespace(
            parsed=SimpleNamespace(
                user=sc.READER_ROLE,
                dbname="postgres",
                host=sc.DIRECT_HOST,
            ),
            initial_authority_proof=_authority_proof(),
        ),
    )
    assert sc._emit_pre_cell(state, dependencies) == 1
    receipt = json.loads(output[0])
    assert receipt["schema_version"] == (
        "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1"
    )
    assert receipt["database_identity"] == dict(sc.DATABASE_IDENTITY)


def test_context_exit_after_complete_truthful_cells_routes_post_evaluation_invalid(
    monkeypatch,
):
    parts = _ready_schema_parts()
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(
        runtime,
        parts.manifest_id,
        receipts=(_terminal_early_prior_receipt(),),
    )
    output = []
    dependencies = _routing_dependencies(runtime, checkpoint, output)
    events = []

    class FailingLateTransactionContext:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, exc_type, exc, traceback):
            events.append(("exit", exc_type))
            raise sc.DatabaseContractError(
                sc.DatabaseFailureStage.NEW_BEFORE_EVIDENCE,
                sc.DatabaseDefect.SNAPSHOT,
            )

    def synthetic_snapshot_run(state, observed_dependencies):
        assert observed_dependencies is dependencies
        with FailingLateTransactionContext():
            state.seal = parts.seal
            # Production sets FINISHED immediately before returning the
            # evaluated bytes while still inside the snapshot context.
            state.phase = sc.InvocationPhase.FINISHED
            return b"evaluated bytes that must not escape a failed teardown\n"

    monkeypatch.setattr(sc, "_run_snapshot", synthetic_snapshot_run)
    invocation = sc.Invocation(parts.manifest_id, None, sc.InvocationMode.NEW_SEAL)
    assert sc.run_scorecard(invocation, None, dependencies) == 1
    assert events == ["enter", ("exit", None)]
    assert len(output) == 1
    receipt = json.loads(output[0])
    assert receipt["schema_version"] == (
        "ATOM-V1B-MANIFEST-POST-EVALUATION-AUTHORITY-INVALID-RECEIPT-1"
    )
    assert receipt["stage"] == "POST_EVALUATION_AUTHORITY_RECHECK"
    assert receipt["reason_codes"] == ["FINAL_AUTHORITY_RECHECK_FAILED"]
    assert receipt["sealed_run_identity"] == parts.run_identity
    assert receipt["seal_record_sha256"] == parts.seal.seal_record_sha256


def test_unrelated_generic_failure_after_truthful_cells_remains_consuming_pre_cell(
    monkeypatch,
):
    parts = _ready_schema_parts()
    runtime = _orchestration_runtime_state()
    checkpoint = _orchestration_checkpoint(
        runtime,
        parts.manifest_id,
        receipts=(_terminal_early_prior_receipt(),),
    )
    output = []
    dependencies = _routing_dependencies(runtime, checkpoint, output)

    def synthetic_snapshot_run(state, observed_dependencies):
        assert observed_dependencies is dependencies
        state.seal = parts.seal
        state.phase = sc.InvocationPhase.TRUTHFUL_CELLS
        raise RuntimeError("generic post-cell construction defect")

    monkeypatch.setattr(sc, "_run_snapshot", synthetic_snapshot_run)
    invocation = sc.Invocation(parts.manifest_id, None, sc.InvocationMode.NEW_SEAL)
    assert sc.run_scorecard(invocation, None, dependencies) == 1
    receipt = json.loads(output[0])
    assert receipt["schema_version"] == (
        "ATOM-V1B-MANIFEST-PRE-CELL-INVALID-RECEIPT-1"
    )
    assert receipt["stage"] == "EVALUATION_STARTED"
    assert receipt["reason_codes"] == ["EVALUATION_CONSTRUCTION_FAILED"]
    assert receipt["sealed_run_identity"] == parts.run_identity
    assert receipt["seal_record_sha256"] == parts.seal.seal_record_sha256


def _v9_kappa_row(
    index: int,
    *,
    q0: float = 4.0,
    forecast_contract: str = "ATOM_TRUE_V9_V4_1",
    forecast_evidence: str = "ATOM_TRUE_V9_V4A_1",
    outcome_contract: str = "ATOM_TRUE_V9_V4_1",
    outcome_evidence: str = "ATOM_TRUE_V9_V4A_1",
) -> sc.V9EvidenceRow:
    cutoff = datetime(2026, 9, 1, 13, 30, tzinfo=UTC) + timedelta(
        seconds=31 * index
    )
    endpoint = cutoff + timedelta(seconds=30)
    record_id = f"v9-kappa-{index:04d}"
    record_hash = hashlib.sha256(record_id.encode("ascii")).hexdigest()
    cohort_hash = "c" * 64
    forecast = SimpleNamespace(
        forecast_record_id=record_id,
        forecast_record_hash=record_hash,
        v3_model_version="V9-SYNTHETIC",
        symbol="COIN",
        horizon="30S",
        horizon_seconds=30,
        cohort_id="kappa-cohort",
        cohort_hash=cohort_hash,
        cutoff_at=cutoff,
        target_endpoint=endpoint,
        evidence_origin="PRODUCTION",
        persistence_proof_eligible=True,
        persisted_at=cutoff + timedelta(seconds=1),
        expected_return_bps=0.5,
        predictive_variance_bps2=q0,
        contract_version=forecast_contract,
        evidence_version=forecast_evidence,
    )
    outcome = SimpleNamespace(
        outcome_record_id=f"outcome-{record_id}",
        outcome_record_hash=hashlib.sha256(
            f"outcome-{record_id}".encode("ascii")
        ).hexdigest(),
        forecast_record_id=record_id,
        target_identity=f"target-{record_id}",
        target_endpoint=endpoint,
        endpoint_observation_at=endpoint,
        proof_eligible=True,
        target_timing_status="VERIFIED",
        created_at=endpoint + timedelta(seconds=2),
        target_resolved_at=endpoint + timedelta(seconds=1),
        actual_return_bps=1.5,
        contract_version=outcome_contract,
        evidence_version=outcome_evidence,
    )
    proof = sc.V9ForecastCommitProof(
        forecast_record_id=record_id,
        forecast_record_hash=record_hash,
        commit_observed_at=cutoff + timedelta(seconds=1),
        target_endpoint=endpoint,
        proof_eligible=True,
        proof_method=sc.PROOF_METHOD,
    )
    return sc.V9EvidenceRow(
        forecast_record_id=record_id,
        forecast_record_hash=record_hash,
        symbol="COIN",
        cutoff_at=cutoff,
        target_endpoint=endpoint,
        horizon="30S",
        cycle_id=f"cycle-{index}",
        v3_model_version="V9-SYNTHETIC",
        persisted_at=cutoff - timedelta(seconds=1),
        forecast=forecast,
        forecast_proof=proof,
        outcome=outcome,
    )


def _outcome_variant(
    row: sc.V9EvidenceRow,
    *,
    outcome_id: str,
    created_at: datetime,
    proof_eligible: bool = True,
    timing_status: str = "VERIFIED",
    target_identity: str | None = None,
    actual_return_bps: float = 1.5,
):
    return SimpleNamespace(
        **{
            **vars(row.outcome),
            "outcome_record_id": outcome_id,
            "outcome_record_hash": hashlib.sha256(
                outcome_id.encode("ascii")
            ).hexdigest(),
            "created_at": created_at,
            "proof_eligible": proof_eligible,
            "target_timing_status": timing_status,
            "target_identity": (
                f"target-{row.forecast_record_id}"
                if target_identity is None
                else target_identity
            ),
            "actual_return_bps": actual_return_bps,
        }
    )


def test_v9_target_outcome_selects_verified_by_created_time_then_identifier():
    row = _v9_kappa_row(1)
    base_time = row.target_endpoint + timedelta(seconds=1)
    earlier_high_id = _outcome_variant(
        row, outcome_id="z-earlier", created_at=base_time
    )
    later_low_id = _outcome_variant(
        row, outcome_id="a-later", created_at=base_time + timedelta(microseconds=1)
    )
    unverified_earliest = _outcome_variant(
        row,
        outcome_id="0-unverified",
        created_at=base_time - timedelta(seconds=1),
        proof_eligible=False,
        timing_status="UNVERIFIED",
    )
    assert (
        sc._select_v9_target_outcome(
            (later_low_id, unverified_earliest, earlier_high_id)
        )
        is earlier_high_id
    )

    tied_high = _outcome_variant(
        row, outcome_id="z-tied", created_at=base_time
    )
    tied_low = _outcome_variant(
        row, outcome_id="a-tied", created_at=base_time
    )
    assert sc._select_v9_target_outcome((tied_high, tied_low)) is tied_low


def test_unverified_empty_target_outcome_loads_but_never_becomes_target():
    row = _v9_kappa_row(1)
    empty = _outcome_variant(
        row,
        outcome_id="a-unverified-empty-target",
        created_at=row.target_endpoint + timedelta(seconds=1),
        proof_eligible=False,
        timing_status="UNVERIFIED",
        target_identity="",
    )
    valid = _outcome_variant(
        row,
        outcome_id="b-valid-target",
        created_at=row.target_endpoint + timedelta(seconds=2),
    )
    by_json = {"empty": empty, "valid": valid}
    rows = (
        (
            empty.outcome_record_id,
            empty.outcome_record_hash,
            empty.forecast_record_id,
            empty.target_identity,
            "empty",
            empty.created_at,
        ),
        (
            valid.outcome_record_id,
            valid.outcome_record_hash,
            valid.forecast_record_id,
            valid.target_identity,
            "valid",
            valid.created_at,
        ),
    )

    class Cursor:
        def __init__(self):
            self.remaining = list(rows)
            self.closed = False

        def execute(self, sql, params):
            assert sql == sc.V9_OUTCOME_STREAM_SQL
            assert params == {"synthetic": True}

        def fetchmany(self, size):
            assert size == sc.PROOF_BATCH_SIZE
            if not self.remaining:
                return []
            result = self.remaining[:size]
            self.remaining = self.remaining[size:]
            return result

        def close(self):
            self.closed = True

    cursor = Cursor()

    class Connection:
        def cursor(self, *, name):
            assert name == "v1b_v9_outcome_stream"
            return cursor

    decoder_calls = []

    def deserialize(value, *, expected_hash):
        decoder_calls.append((value, expected_hash))
        outcome = by_json[value]
        assert expected_hash == outcome.outcome_record_hash
        return outcome

    grouped, count = sc._load_v9_outcomes(
        Connection(),
        {"synthetic": True},
        deserialize_outcome_record=deserialize,
    )
    assert cursor.closed is True
    assert count == 2
    assert decoder_calls == []
    envelopes = grouped[row.forecast_record_id]
    assert tuple(envelope.record_json for envelope in envelopes) == (
        "empty",
        "valid",
    )
    opaque = replace(
        row,
        outcome=None,
        outcomes=(),
        outcome_envelopes=envelopes,
    )
    materialized = sc._materialize_v9_row(
        opaque, SimpleNamespace(deserialize_outcome_record=deserialize)
    )
    assert decoder_calls == [
        ("empty", empty.outcome_record_hash),
        ("valid", valid.outcome_record_hash),
    ]
    assert materialized.outcomes == (empty, valid)
    assert materialized.outcome is valid


def test_v9_target_selection_does_not_skip_earlier_verified_ineligible_outcome():
    row = _v9_kappa_row(1)
    base_time = row.target_endpoint + timedelta(seconds=1)
    earlier_ineligible = _outcome_variant(
        row,
        outcome_id="z-earlier-ineligible",
        created_at=base_time,
        proof_eligible=False,
    )
    later_eligible = _outcome_variant(
        row,
        outcome_id="a-later-eligible",
        created_at=base_time + timedelta(microseconds=1),
        proof_eligible=True,
    )
    selected = sc._select_v9_target_outcome(
        (later_eligible, earlier_ineligible)
    )
    assert selected is earlier_ineligible
    selected_row = replace(
        row,
        outcome=selected,
        outcomes=(later_eligible, earlier_ineligible),
    )
    assert sc.v9_outcome_is_available(
        selected_row, datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
    ) is False


@pytest.mark.parametrize("embedded_horizon_seconds", (29, 31))
def test_v9_embedded_horizon_seconds_must_equal_frozen_outer_interval(
    embedded_horizon_seconds,
):
    cutoff = datetime(2026, 9, 1, 13, 30, tzinfo=UTC)
    endpoint = cutoff + timedelta(seconds=30)
    record_id = "v9-horizon-seconds"
    record_hash = hashlib.sha256(record_id.encode("ascii")).hexdigest()

    def deserialize(record_json, *, expected_hash):
        assert record_json == {"synthetic": True}
        assert expected_hash == record_hash
        return SimpleNamespace(
            forecast_record_id=record_id,
            forecast_record_hash=record_hash,
            symbol="COIN",
            cutoff_at=cutoff,
            target_endpoint=endpoint,
            horizon="30S",
            horizon_seconds=embedded_horizon_seconds,
            cycle_id="cycle-horizon",
            v3_model_version="V9-SYNTHETIC",
        )

    row = (
        record_id,
        record_hash,
        "COIN",
        cutoff,
        endpoint,
        "30S",
        "cycle-horizon",
        "V9-SYNTHETIC",
        {"synthetic": True},
        cutoff - timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="horizon"):
        sc._validate_v9_forecast(row, deserialize_forecast_record=deserialize)


def _v9_kappa_target() -> sc.V9EvidenceRow:
    target = _v9_kappa_row(10_000)
    target_cutoff = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
    endpoint = target_cutoff + timedelta(seconds=30)
    forecast = SimpleNamespace(
        **{
            **vars(target.forecast),
            "cutoff_at": target_cutoff,
            "target_endpoint": endpoint,
        }
    )
    proof = sc.V9ForecastCommitProof(
        target.forecast_record_id,
        target.forecast_record_hash,
        target_cutoff + timedelta(seconds=1),
        endpoint,
        True,
        sc.PROOF_METHOD,
    )
    return replace(
        target,
        cutoff_at=target_cutoff,
        target_endpoint=endpoint,
        persisted_at=target_cutoff - timedelta(seconds=1),
        forecast=forecast,
        forecast_proof=proof,
    )


def _kappa_evidence(rows):
    return sc.EvidencePopulation(
        upper_as_of=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
        family_rows=(),
        v9_rows=tuple(rows),
        source_counts={
            "public.volatility_forecasts": 0,
            "public.volatility_forecast_outcomes": 0,
            "public.atom_v9_v4_forecasts": len(rows),
            "public.atom_v9_v4_outcomes": len(rows),
        },
    )


def test_v9_negative_and_zero_variance_have_distinct_receipt_accounting():
    session = _xnys_session(date(2026, 9, 1))
    negative = _v9_kappa_row(1, q0=-1.0)
    zero = _v9_kappa_row(2, q0=0.0)
    negative_zero = _v9_kappa_row(3, q0=-0.0)
    evidence = _kappa_evidence((negative, zero, negative_zero))
    lineage = {
        "v3_model_version": "V9-SYNTHETIC",
        "symbol": "COIN",
        "horizon": "30S",
        "cohort_id": "kappa-cohort",
        "cohort_hash": "c" * 64,
    }
    population = sc._v9_population(
        V9_30S,
        lineage,
        evidence,
        evidence.upper_as_of,
        {session.session_date: session},
        SimpleNamespace(),
    )
    assert population.n_input == 3
    assert population.n_null_or_nonfinite_excluded == 1
    assert population.n_nonpositive_prediction_excluded == 2
    assert population.n_kappa_unavailable == 0
    assert population.windows == ()

    # The official cell/receipt shape preserves the two mutually exclusive
    # exclusions and the complete accounting equation.
    cell = sc.evaluate_cell(population)
    assert cell["classification"] == "INSUFFICIENT"
    assert cell["n_input"] == 3
    assert cell["n_null_or_nonfinite_excluded"] == 1
    assert cell["n_nonpositive_prediction_excluded"] == 2
    assert (
        cell["n_unselected_lineage_rows"]
        + cell["n_inadmissible"]
        + cell["n_non_rth"]
        + cell["n_overlap_excluded"]
        + cell["n_null_or_nonfinite_excluded"]
        + cell["n_nonpositive_prediction_excluded"]
        + cell["n_kappa_unavailable"]
        + cell["n_windows"]
        == cell["n_input"]
    )
    sc.validate_cell(cell, V9_30S.public())


def _retarget_v9_lineage(row, *, cutoff, model, cohort, cohort_hash):
    endpoint = cutoff + timedelta(minutes=5)
    forecast = SimpleNamespace(
        **{
            **vars(row.forecast),
            "v3_model_version": model,
            "horizon": "5M",
            "horizon_seconds": 300,
            "cohort_id": cohort,
            "cohort_hash": cohort_hash,
            "cutoff_at": cutoff,
            "target_endpoint": endpoint,
            "persisted_at": cutoff + timedelta(seconds=1),
        }
    )
    outcome = SimpleNamespace(
        **{
            **vars(row.outcome),
            "target_endpoint": endpoint,
            "endpoint_observation_at": endpoint,
            "target_resolved_at": endpoint + timedelta(seconds=1),
            "created_at": endpoint + timedelta(seconds=2),
        }
    )
    proof = sc.V9ForecastCommitProof(
        row.forecast_record_id,
        row.forecast_record_hash,
        cutoff + timedelta(seconds=1),
        endpoint,
        True,
        sc.PROOF_METHOD,
    )
    return replace(
        row,
        cutoff_at=cutoff,
        target_endpoint=endpoint,
        horizon="5M",
        v3_model_version=model,
        persisted_at=cutoff,
        forecast=forecast,
        forecast_proof=proof,
        outcome=outcome,
        outcomes=(outcome,),
    )


def test_historical_schedule_start_preserves_pre_rotation_v9_lineage_evidence():
    """A later lineage must not erase the old lineage's earlier candidate history."""

    old = _retarget_v9_lineage(
        _v9_kappa_row(1),
        cutoff=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
        model="V9-OLD",
        cohort="old-cohort",
        cohort_hash="1" * 64,
    )
    new = _retarget_v9_lineage(
        _v9_kappa_row(2),
        cutoff=datetime(2026, 9, 9, 14, 0, tzinfo=UTC),
        model="V9-NEW",
        cohort="new-cohort",
        cohort_hash="2" * 64,
    )
    early_candidate = _xnys_session(date(2026, 9, 8))
    final_candidate = _xnys_session(date(2026, 9, 10))
    evidence = sc.EvidencePopulation(
        final_candidate.market_close,
        (),
        (old, new),
        {
            "public.volatility_forecasts": 0,
            "public.volatility_forecast_outcomes": 0,
            "public.atom_v9_v4_forecasts": 2,
            "public.atom_v9_v4_outcomes": 2,
        },
    )
    spec = sc.CELL_BY_ORDER[8]
    assert sc._select_lineage(spec, evidence, early_candidate.market_close) == {
        "v3_model_version": "V9-OLD",
        "symbol": "COIN",
        "horizon": "5M",
        "cohort_id": "old-cohort",
        "cohort_hash": "1" * 64,
    }
    assert sc._select_lineage(spec, evidence, final_candidate.market_close) == {
        "v3_model_version": "V9-NEW",
        "symbol": "COIN",
        "horizon": "5M",
        "cohort_id": "new-cohort",
        "cohort_hash": "2" * 64,
    }
    assert sc._evidence_first_date(
        "v1b-v9-5m",
        evidence,
        (early_candidate, final_candidate),
        SimpleNamespace(),
    ) == date(2026, 8, 21)


def test_historical_schedule_rechecks_same_v9_lineage_when_outcome_becomes_available():
    row = _retarget_v9_lineage(
        _v9_kappa_row(3),
        cutoff=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
        model="V9-STABLE",
        cohort="stable-cohort",
        cohort_hash="3" * 64,
    )
    early_candidate = _xnys_session(date(2026, 9, 8))
    final_candidate = _xnys_session(date(2026, 9, 10))
    late_observation = datetime(2026, 9, 9, 18, 0, tzinfo=UTC)
    late_outcome = SimpleNamespace(
        **{
            **vars(row.outcome),
            "endpoint_observation_at": late_observation,
            "target_resolved_at": late_observation,
            "created_at": late_observation,
        }
    )
    row = replace(row, outcome=late_outcome, outcomes=(late_outcome,))
    evidence = sc.EvidencePopulation(
        final_candidate.market_close,
        (),
        (row,),
        {
            "public.volatility_forecasts": 0,
            "public.volatility_forecast_outcomes": 0,
            "public.atom_v9_v4_forecasts": 1,
            "public.atom_v9_v4_outcomes": 1,
        },
    )
    spec = sc.CELL_BY_ORDER[8]
    expected_lineage = {
        "v3_model_version": "V9-STABLE",
        "symbol": "COIN",
        "horizon": "5M",
        "cohort_id": "stable-cohort",
        "cohort_hash": "3" * 64,
    }
    assert sc._select_lineage(spec, evidence, early_candidate.market_close) == (
        expected_lineage
    )
    assert sc.v9_outcome_is_available(row, early_candidate.market_close) is False
    assert sc._select_lineage(spec, evidence, final_candidate.market_close) == (
        expected_lineage
    )
    assert sc.v9_outcome_is_available(row, final_candidate.market_close) is True
    assert sc._evidence_first_date(
        "v1b-v9-5m",
        evidence,
        (early_candidate, final_candidate),
        SimpleNamespace(),
    ) == date(2026, 8, 21)


def test_corrupt_v9_outcome_is_decoded_only_for_candidate_selected_lineage():
    losing = _retarget_v9_lineage(
        _v9_kappa_row(4),
        cutoff=datetime(2026, 9, 4, 14, 0, tzinfo=UTC),
        model="V9-LOSING",
        cohort="losing-cohort",
        cohort_hash="4" * 64,
    )
    selected = _retarget_v9_lineage(
        _v9_kappa_row(5),
        cutoff=datetime(2026, 9, 7, 14, 0, tzinfo=UTC),
        model="V9-SELECTED",
        cohort="selected-cohort",
        cohort_hash="5" * 64,
    )
    corrupt = sc.V9OutcomeEnvelope(
        "corrupt-outcome",
        "6" * 64,
        losing.forecast_record_id,
        f"target-{losing.forecast_record_id}",
        "corrupt-payload",
        losing.target_endpoint + timedelta(seconds=1),
    )
    losing_opaque = replace(
        losing,
        outcome=None,
        outcomes=(),
        outcome_envelopes=(corrupt,),
    )
    losing_control = replace(losing_opaque, outcome_envelopes=())
    selected_without_outcome = replace(
        selected, outcome=None, outcomes=(), outcome_envelopes=()
    )
    candidate = _xnys_session(date(2026, 9, 8))
    decoder_calls = []

    def corrupt_decoder(payload, *, expected_hash):
        decoder_calls.append((payload, expected_hash))
        raise ValueError("synthetic corrupt outcome")

    def forbidden(*args, **kwargs):
        raise AssertionError("no selected outcome may reach calibration")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=corrupt_decoder,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )

    def evidence(rows):
        return sc.EvidencePopulation(
            candidate.market_close,
            (),
            rows,
            {
                "public.volatility_forecasts": 0,
                "public.volatility_forecast_outcomes": 0,
                "public.atom_v9_v4_forecasts": 2,
                "public.atom_v9_v4_outcomes": 1,
            },
        )

    corrupt_lineages, corrupt_populations = sc.build_candidate_populations(
        "v1b-v9-5m",
        evidence((losing_opaque, selected_without_outcome)),
        candidate,
        (candidate,),
        primitives,
    )
    control_lineages, control_populations = sc.build_candidate_populations(
        "v1b-v9-5m",
        evidence((losing_control, selected_without_outcome)),
        candidate,
        (candidate,),
        primitives,
    )
    assert decoder_calls == []
    assert corrupt_lineages == control_lineages
    assert corrupt_populations == control_populations
    assert corrupt_populations[0].n_input == 2
    assert corrupt_populations[0].n_unselected_lineage_rows == 1
    assert corrupt_populations[0].n_inadmissible == 1

    selected_corrupt = replace(
        selected_without_outcome,
        outcome_envelopes=(
            replace(corrupt, forecast_record_id=selected.forecast_record_id),
        ),
    )
    with pytest.raises(sc.ProtocolDefect, match="selected-lineage V9 outcome invalid"):
        sc.build_candidate_populations(
            "v1b-v9-5m",
            evidence((losing_control, selected_corrupt)),
            candidate,
            (candidate,),
            primitives,
        )
    assert decoder_calls == [("corrupt-payload", "6" * 64)]


def test_selected_lineage_inadmissible_forecast_never_decodes_its_outcome():
    candidate = _xnys_session(date(2026, 9, 8))
    valid = _retarget_v9_lineage(
        _v9_kappa_row(6),
        cutoff=datetime(2026, 9, 7, 14, 0, tzinfo=UTC),
        model="V9-SAME",
        cohort="same-cohort",
        cohort_hash="7" * 64,
    )
    invalid = _retarget_v9_lineage(
        _v9_kappa_row(7),
        cutoff=datetime(2026, 9, 4, 14, 0, tzinfo=UTC),
        model="V9-SAME",
        cohort="same-cohort",
        cohort_hash="7" * 64,
    )
    corrupt = sc.V9OutcomeEnvelope(
        "invalid-forecast-outcome",
        "8" * 64,
        invalid.forecast_record_id,
        f"target-{invalid.forecast_record_id}",
        "must-stay-opaque",
        invalid.target_endpoint + timedelta(seconds=1),
    )
    invalid = replace(
        invalid,
        forecast_proof=None,
        outcome=None,
        outcomes=(),
        outcome_envelopes=(corrupt,),
    )
    valid = replace(valid, outcome=None, outcomes=(), outcome_envelopes=())
    evidence = sc.EvidencePopulation(
        candidate.market_close,
        (),
        (invalid, valid),
        {
            "public.volatility_forecasts": 0,
            "public.volatility_forecast_outcomes": 0,
            "public.atom_v9_v4_forecasts": 2,
            "public.atom_v9_v4_outcomes": 1,
        },
    )
    decoder_calls = []

    def decoder(*args, **kwargs):
        decoder_calls.append((args, kwargs))
        raise ValueError("inadmissible forecast outcome decoded")

    def forbidden(*args, **kwargs):
        raise AssertionError("no admissible outcome reached inference")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=decoder,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )
    lineages, populations = sc.build_candidate_populations(
        "v1b-v9-5m", evidence, candidate, (candidate,), primitives
    )
    assert lineages[0]["lineage_identity"]["cohort_id"] == "same-cohort"
    assert decoder_calls == []
    assert populations[0].n_input == 2
    assert populations[0].n_unselected_lineage_rows == 0
    assert populations[0].n_inadmissible == 2
    assert populations[0].windows == ()


def test_future_selected_lineage_outcome_is_opaque_at_earlier_candidate():
    early_candidate = _xnys_session(date(2026, 9, 8))
    final_candidate = _xnys_session(date(2026, 9, 10))
    row = _retarget_v9_lineage(
        _v9_kappa_row(8),
        cutoff=datetime(2026, 9, 7, 14, 0, tzinfo=UTC),
        model="V9-FUTURE-OUTCOME",
        cohort="future-outcome-cohort",
        cohort_hash="9" * 64,
    )
    envelope = sc.V9OutcomeEnvelope(
        "future-corrupt-outcome",
        "a" * 64,
        row.forecast_record_id,
        f"target-{row.forecast_record_id}",
        "future-corrupt-payload",
        datetime(2026, 9, 9, 18, 0, tzinfo=UTC),
    )
    row = replace(row, outcome=None, outcomes=(), outcome_envelopes=(envelope,))
    evidence = sc.EvidencePopulation(
        final_candidate.market_close,
        (),
        (row,),
        {
            "public.volatility_forecasts": 0,
            "public.volatility_forecast_outcomes": 0,
            "public.atom_v9_v4_forecasts": 1,
            "public.atom_v9_v4_outcomes": 1,
        },
    )
    decoder_calls = []

    def decoder(*args, **kwargs):
        decoder_calls.append((args, kwargs))
        raise ValueError("future outcome decoded at earlier candidate")

    def forbidden(*args, **kwargs):
        raise AssertionError("outcome is not yet candidate-visible")

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=forbidden,
        calibration_observation=forbidden,
        calibrate_scale=forbidden,
        select_non_overlapping=forbidden,
        deserialize_forecast_record=forbidden,
        deserialize_outcome_record=decoder,
        canonical_target_identity=forbidden,
        apply_forecast_commit_proof=forbidden,
    )
    _lineages, populations = sc.build_candidate_populations(
        "v1b-v9-5m",
        evidence,
        early_candidate,
        (early_candidate, final_candidate),
        primitives,
    )
    assert decoder_calls == []
    assert populations[0].n_input == 1
    assert populations[0].n_inadmissible == 1
    assert populations[0].windows == ()


@pytest.mark.parametrize(
    "defect", ("invalid_id", "invalid_hash", "invalid_target", "duplicate_id")
)
def test_future_v9_outer_identity_defect_stays_opaque_until_visible(defect):
    early_candidate = _xnys_session(date(2026, 9, 8))
    later_candidate = _xnys_session(date(2026, 9, 10))
    row = _retarget_v9_lineage(
        _v9_kappa_row(80),
        cutoff=datetime(2026, 9, 7, 14, 0, tzinfo=UTC),
        model="V9-FUTURE-OUTER",
        cohort="future-outer-cohort",
        cohort_hash="a" * 64,
    )
    created = datetime(2026, 9, 9, 18, 0, tzinfo=UTC)
    envelope = sc.V9OutcomeEnvelope(
        "future-outer-outcome",
        "b" * 64,
        row.forecast_record_id,
        f"target-{row.forecast_record_id}",
        "first-valid-payload",
        created,
    )
    if defect == "invalid_id":
        envelopes = (replace(envelope, outcome_record_id=""),)
    elif defect == "invalid_hash":
        envelopes = (replace(envelope, outcome_record_hash="B" * 64),)
    elif defect == "invalid_target":
        envelopes = (replace(envelope, target_identity=None),)
    else:
        envelopes = (
            envelope,
            replace(
                envelope,
                record_json="duplicate-payload-must-not-decode",
                created_at=created + timedelta(microseconds=1),
            ),
        )
    opaque = replace(
        row,
        outcome=None,
        outcomes=(),
        outcome_envelopes=envelopes,
    )
    control = replace(opaque, outcome_envelopes=())
    decoder_calls = []

    def decoder(payload, *, expected_hash):
        decoder_calls.append((payload, expected_hash))
        assert payload == "first-valid-payload"
        return SimpleNamespace(
            outcome_record_id=envelope.outcome_record_id,
            outcome_record_hash=envelope.outcome_record_hash,
            forecast_record_id=envelope.forecast_record_id,
            target_identity=envelope.target_identity,
            created_at=envelope.created_at,
            target_timing_status="UNVERIFIED",
        )

    primitives = SimpleNamespace(deserialize_outcome_record=decoder)
    assert sc._materialize_v9_row(
        opaque, primitives, as_of=early_candidate.market_close
    ) == control
    assert decoder_calls == []

    with pytest.raises(
        sc.ProtocolDefect, match="selected-lineage V9 outcome invalid"
    ):
        sc._materialize_v9_row(
            opaque, primitives, as_of=later_candidate.market_close
        )
    assert decoder_calls == (
        [("first-valid-payload", "b" * 64)]
        if defect == "duplicate_id"
        else []
    )


def test_causal_kappa_does_not_decode_future_same_lineage_forecast_outcome():
    target = _v9_kappa_target()
    future = _v9_kappa_row(9)
    future_cutoff = target.cutoff_at + timedelta(seconds=1)
    future_endpoint = future_cutoff + timedelta(seconds=30)
    forecast = SimpleNamespace(
        **{
            **vars(future.forecast),
            "cutoff_at": future_cutoff,
            "target_endpoint": future_endpoint,
            "persisted_at": future_cutoff + timedelta(microseconds=1),
        }
    )
    proof = sc.V9ForecastCommitProof(
        future.forecast_record_id,
        future.forecast_record_hash,
        future_cutoff + timedelta(microseconds=1),
        future_endpoint,
        True,
        sc.PROOF_METHOD,
    )
    envelope = sc.V9OutcomeEnvelope(
        "future-kappa-corrupt",
        "b" * 64,
        future.forecast_record_id,
        f"target-{future.forecast_record_id}",
        "future-kappa-corrupt-payload",
        future_endpoint + timedelta(seconds=1),
    )
    future = replace(
        future,
        cutoff_at=future_cutoff,
        target_endpoint=future_endpoint,
        persisted_at=future_cutoff,
        forecast=forecast,
        forecast_proof=proof,
        outcome=None,
        outcomes=(),
        outcome_envelopes=(envelope,),
    )
    decoder_calls = []
    primitives = sc.V4Primitives(
        governed_accuracy_evidence=lambda *args: tuple(args[4]),
        calibration_observation=lambda **kwargs: SimpleNamespace(**kwargs),
        calibrate_scale=lambda *args, **kwargs: SimpleNamespace(
            status="IMMATURE", kappa=None
        ),
        select_non_overlapping=lambda pairs: SimpleNamespace(selected_ids=()),
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: (
            decoder_calls.append((args, kwargs)),
            (_ for _ in ()).throw(ValueError("future kappa outcome decoded")),
        )[1],
        canonical_target_identity=lambda *args, **kwargs: "unused",
        apply_forecast_commit_proof=lambda *args, **kwargs: None,
    )
    assert sc._causal_kappa(target, _kappa_evidence((future,)), primitives) is None
    assert decoder_calls == []


def _governed_v4_pairs(horizon, cohort_id, cohort_hash, as_of, pairs):
    assert horizon == "30S"
    assert cohort_id == "kappa-cohort"
    assert cohort_hash == "c" * 64
    assert as_of == datetime(2026, 9, 8, 14, 59, 59, 999999, tzinfo=UTC)
    return tuple(
        (forecast, outcome)
        for forecast, outcome in pairs
        if forecast.contract_version == "ATOM_TRUE_V9_V4_1"
        and forecast.evidence_version == "ATOM_TRUE_V9_V4A_1"
        and outcome.contract_version == "ATOM_TRUE_V9_V4_1"
        and outcome.evidence_version == "ATOM_TRUE_V9_V4A_1"
    )


def test_causal_kappa_applies_unchanged_governed_filter_before_overlap_selection():
    target = _v9_kappa_target()
    valid = _v9_kappa_row(1)
    wrong_rows = (
        _v9_kappa_row(2, forecast_contract="WRONG"),
        _v9_kappa_row(3, forecast_evidence="WRONG"),
        _v9_kappa_row(4, outcome_contract="WRONG"),
        _v9_kappa_row(5, outcome_evidence="WRONG"),
    )
    calls = []

    def governed(*args):
        calls.append(("governed", tuple(pair[0].forecast_record_id for pair in args[4])))
        return _governed_v4_pairs(*args)

    def select(pairs):
        identifiers = tuple(pair[0].forecast_record_id for pair in pairs)
        calls.append(("select", identifiers))
        assert identifiers == (valid.forecast_record_id,)
        return SimpleNamespace(selected_ids=identifiers)

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=governed,
        calibration_observation=lambda **kwargs: SimpleNamespace(**kwargs),
        calibrate_scale=lambda rows, **kwargs: SimpleNamespace(
            status="MATURE", kappa=1.25
        ),
        select_non_overlapping=select,
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: None,
        canonical_target_identity=lambda forecast: (
            f"target-{forecast.forecast_record_id}"
        ),
        apply_forecast_commit_proof=lambda *args, **kwargs: None,
    )
    baseline = sc._causal_kappa(target, _kappa_evidence((valid,)), primitives)
    extended = sc._causal_kappa(
        target, _kappa_evidence((valid,) + wrong_rows), primitives
    )

    assert baseline == extended == 1.25
    assert calls == [
        ("governed", (valid.forecast_record_id,)),
        ("select", (valid.forecast_record_id,)),
        (
            "governed",
            (valid.forecast_record_id,)
            + tuple(row.forecast_record_id for row in wrong_rows),
        ),
        ("select", (valid.forecast_record_id,)),
    ]


def test_v9_wrong_target_unverified_variant_reaches_governed_filter_not_loader_failure():
    target = _v9_kappa_target()
    prior = _v9_kappa_row(1)
    valid = _outcome_variant(
        prior,
        outcome_id="valid-outcome",
        created_at=prior.target_endpoint + timedelta(seconds=1),
    )
    wrong = _outcome_variant(
        prior,
        outcome_id="wrong-target-unverified",
        created_at=prior.target_endpoint + timedelta(seconds=2),
        proof_eligible=False,
        timing_status="UNVERIFIED",
        target_identity="wrong-target",
    )
    row = replace(prior, outcome=valid, outcomes=(valid, wrong))
    calls = []

    def governed(horizon, cohort_id, cohort_hash, as_of, pairs):
        pairs = tuple(pairs)
        calls.append(
            (
                "governed",
                tuple(item[1].outcome_record_id for item in pairs),
            )
        )
        return tuple(
            pair
            for pair in pairs
            if pair[1].proof_eligible is True
            and pair[1].target_timing_status == "VERIFIED"
            and pair[1].target_identity
            == f"target-{pair[0].forecast_record_id}"
        )

    def select(pairs):
        pairs = tuple(pairs)
        calls.append(("select", tuple(item[1].outcome_record_id for item in pairs)))
        assert pairs == ((prior.forecast, valid),)
        return SimpleNamespace(selected_ids=(prior.forecast_record_id,))

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=governed,
        calibration_observation=lambda **kwargs: SimpleNamespace(**kwargs),
        calibrate_scale=lambda rows, **kwargs: SimpleNamespace(
            status="MATURE", kappa=2.0
        ),
        select_non_overlapping=select,
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: None,
        canonical_target_identity=lambda forecast: (
            f"target-{forecast.forecast_record_id}"
        ),
        apply_forecast_commit_proof=lambda *args, **kwargs: None,
    )
    assert sc._causal_kappa(target, _kappa_evidence((row,)), primitives) == 2.0
    assert calls == [
        ("governed", ("valid-outcome", "wrong-target-unverified")),
        ("select", ("valid-outcome",)),
    ]


@pytest.mark.parametrize("second_actual", (1.5, 9.5))
def test_identical_and_conflicting_v9_outcomes_both_reach_governed_selector(
    second_actual,
):
    target = _v9_kappa_target()
    prior = _v9_kappa_row(1)
    first = _outcome_variant(
        prior,
        outcome_id="outcome-a",
        created_at=prior.target_endpoint + timedelta(seconds=1),
        actual_return_bps=1.5,
    )
    second = _outcome_variant(
        prior,
        outcome_id="outcome-b",
        created_at=prior.target_endpoint + timedelta(seconds=2),
        actual_return_bps=second_actual,
    )
    row = replace(prior, outcome=first, outcomes=(first, second))
    seen = []

    def governed(*args):
        pairs = tuple(args[4])
        seen.append(("governed", tuple(pair[1].outcome_record_id for pair in pairs)))
        return pairs

    def select(pairs):
        pairs = tuple(pairs)
        seen.append(("select", tuple(pair[1].outcome_record_id for pair in pairs)))
        # The unchanged selector owns duplicate/conflict disposition.  This
        # synthetic result models exclusion without the scorecard choosing.
        return SimpleNamespace(selected_ids=())

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=governed,
        calibration_observation=lambda **kwargs: SimpleNamespace(**kwargs),
        calibrate_scale=lambda rows, **kwargs: SimpleNamespace(
            status="UNAVAILABLE", kappa=None
        ),
        select_non_overlapping=select,
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: None,
        canonical_target_identity=lambda forecast: (
            f"target-{forecast.forecast_record_id}"
        ),
        apply_forecast_commit_proof=lambda *args, **kwargs: None,
    )
    assert sc._causal_kappa(target, _kappa_evidence((row,)), primitives) is None
    expected = ("outcome-a", "outcome-b")
    assert seen == [("governed", expected), ("select", expected)]


def test_causal_kappa_maps_one_selected_forecast_id_to_one_canonical_pair():
    """A V4 selector ID must never expand back into duplicate outcomes."""

    target = _v9_kappa_target()

    def exact_record_shape(row, outcomes):
        forecast = SimpleNamespace(
            **{
                **vars(row.forecast),
                "logical_key": (
                    row.forecast.symbol,
                    row.forecast.cutoff_at,
                    row.forecast.horizon,
                    row.cycle_id,
                    row.forecast.v3_model_version,
                ),
            }
        )
        shaped = tuple(
            SimpleNamespace(
                **{
                    **vars(outcome),
                    "logical_key": (
                        outcome.forecast_record_id,
                        outcome.target_identity,
                    ),
                    "endpoint_observation_delay": 0.0,
                }
            )
            for outcome in outcomes
        )
        return replace(
            row,
            forecast=forecast,
            outcome=shaped[0],
            outcomes=shaped,
        )

    rows = []
    for index in range(251):
        row = _v9_kappa_row(index)
        if index == 0:
            outcomes = (
                _outcome_variant(
                    row,
                    outcome_id="canonical-outcome-a",
                    created_at=row.target_endpoint + timedelta(seconds=1),
                    target_identity="target-a",
                    actual_return_bps=1.5,
                ),
                _outcome_variant(
                    row,
                    outcome_id="duplicate-outcome-b",
                    created_at=row.target_endpoint + timedelta(seconds=2),
                    target_identity="target-b",
                    actual_return_bps=9.5,
                ),
            )
        else:
            outcomes = (row.outcome,)
        rows.append(exact_record_shape(row, outcomes))

    selector_pairs = []
    observations = []

    def select(pairs):
        pairs = tuple(pairs)
        selector_pairs.append(pairs)
        assert tuple(
            outcome.outcome_record_id
            for forecast, outcome in pairs
            if forecast.forecast_record_id == rows[0].forecast_record_id
        ) == ("canonical-outcome-a", "duplicate-outcome-b")
        selected_ids = tuple(dict.fromkeys(pair[0].forecast_record_id for pair in pairs))
        assert len(selected_ids) == 251
        return SimpleNamespace(selected_ids=selected_ids)

    def observation(**kwargs):
        observations.append(kwargs)
        return SimpleNamespace(**kwargs)

    def calibrate(values, *, calibration_end):
        values = tuple(values)
        assert len(values) == 1
        assert values[0].forecast_record_id == rows[0].forecast_record_id
        assert values[0].actual_bps == 1.5
        return SimpleNamespace(status="MATURE", kappa=1.75)

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=lambda *args: tuple(args[4]),
        calibration_observation=observation,
        calibrate_scale=calibrate,
        select_non_overlapping=select,
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: None,
        canonical_target_identity=lambda forecast: (
            f"target-{forecast.forecast_record_id}"
        ),
        apply_forecast_commit_proof=lambda *args, **kwargs: None,
    )
    assert sc._causal_kappa(target, _kappa_evidence(tuple(rows)), primitives) == 1.75
    assert len(selector_pairs) == 1
    assert len(selector_pairs[0]) == 252
    assert len(observations) == 1
    assert observations[0]["actual_bps"] == 1.5


def test_causal_kappa_preserves_nonpositive_q0_through_governance_and_withholding():
    target = _v9_kappa_target()
    rows = tuple(
        _v9_kappa_row(
            index,
            q0=(-1.0 if index == 0 else 0.0 if index == 1 else 4.0),
        )
        for index in range(253)
    )
    selected_inputs = []
    calibrated = []

    def governed(*args):
        result = _governed_v4_pairs(*args)
        assert len(result) == 253
        assert [result[index][0].predictive_variance_bps2 for index in range(3)] == [
            -1.0,
            0.0,
            4.0,
        ]
        return result

    def select(pairs):
        pairs = tuple(pairs)
        selected_inputs.append(
            tuple(pair[0].predictive_variance_bps2 for pair in pairs)
        )
        return SimpleNamespace(
            selected_ids=tuple(pair[0].forecast_record_id for pair in pairs)
        )

    def observation(**kwargs):
        return SimpleNamespace(**kwargs)

    def calibrate(observations, *, calibration_end):
        observations = tuple(observations)
        calibrated.append(
            (
                tuple(item.q0_bps2 for item in observations),
                calibration_end,
            )
        )
        # This is the only seam allowed to discard nonpositive q0.
        usable = tuple(item for item in observations if item.q0_bps2 > 0)
        return SimpleNamespace(
            status="MATURE" if len(usable) == 1 else "UNAVAILABLE",
            kappa=1.5 if len(usable) == 1 else None,
        )

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=governed,
        calibration_observation=observation,
        calibrate_scale=calibrate,
        select_non_overlapping=select,
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: None,
        canonical_target_identity=lambda forecast: (
            f"target-{forecast.forecast_record_id}"
        ),
        apply_forecast_commit_proof=lambda *args, **kwargs: None,
    )
    assert sc._causal_kappa(target, _kappa_evidence(rows), primitives) == 1.5
    assert len(selected_inputs) == 1
    assert len(selected_inputs[0]) == 253
    assert selected_inputs[0][:3] == (-1.0, 0.0, 4.0)
    assert calibrated == [
        (
            (-1.0, 0.0, 4.0),
            rows[2].cutoff_at,
        )
    ]

    # A latest zero-q0 pair remains one of the withheld latest 250.  Removing
    # it before selection would change split from one calibration pair to none.
    latest_zero = tuple(
        _v9_kappa_row(index, q0=0.0 if index == 250 else 4.0)
        for index in range(251)
    )
    calibrated.clear()
    selected_inputs.clear()

    def governed_latest(*args):
        result = _governed_v4_pairs(*args)
        assert len(result) == 251
        assert result[-1][0].predictive_variance_bps2 == 0.0
        return result

    latest_primitives = replace(
        primitives, governed_accuracy_evidence=governed_latest
    )
    assert (
        sc._causal_kappa(target, _kappa_evidence(latest_zero), latest_primitives)
        == 1.5
    )
    assert len(selected_inputs[0]) == 251
    assert selected_inputs[0][-1] == 0.0
    assert calibrated == [((4.0,), latest_zero[0].cutoff_at)]


def test_causal_kappa_calibration_session_id_is_utc_date_not_new_york_date():
    """Amendment 2A fixes V4 calibration session_id to UTC calendar date."""

    first_cutoff = datetime(2026, 9, 9, 1, 0, tzinfo=UTC)

    def retime(row, cutoff):
        endpoint = cutoff + timedelta(seconds=30)
        forecast = SimpleNamespace(
            **{
                **vars(row.forecast),
                "cutoff_at": cutoff,
                "target_endpoint": endpoint,
                "persisted_at": cutoff + timedelta(seconds=1),
            }
        )
        outcome = SimpleNamespace(
            **{
                **vars(row.outcome),
                "target_endpoint": endpoint,
                "endpoint_observation_at": endpoint,
                "created_at": endpoint + timedelta(seconds=2),
                "target_resolved_at": endpoint + timedelta(seconds=1),
            }
        )
        proof = sc.V9ForecastCommitProof(
            row.forecast_record_id,
            row.forecast_record_hash,
            cutoff + timedelta(seconds=1),
            endpoint,
            True,
            sc.PROOF_METHOD,
        )
        return replace(
            row,
            cutoff_at=cutoff,
            target_endpoint=endpoint,
            persisted_at=cutoff - timedelta(seconds=1),
            forecast=forecast,
            forecast_proof=proof,
            outcome=outcome,
            outcomes=(outcome,),
        )

    rows = tuple(
        retime(_v9_kappa_row(index), first_cutoff + timedelta(seconds=31 * index))
        for index in range(251)
    )
    target = retime(
        _v9_kappa_row(10_000), datetime(2026, 9, 10, 15, 0, tzinfo=UTC)
    )
    observations = []

    def observation(**kwargs):
        observations.append(kwargs)
        return SimpleNamespace(**kwargs)

    primitives = sc.V4Primitives(
        governed_accuracy_evidence=lambda *args: tuple(args[4]),
        calibration_observation=observation,
        calibrate_scale=lambda rows, **kwargs: SimpleNamespace(
            status="MATURE", kappa=1.0
        ),
        select_non_overlapping=lambda pairs: SimpleNamespace(
            selected_ids=tuple(
                forecast.forecast_record_id for forecast, _outcome in pairs
            )
        ),
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: None,
        canonical_target_identity=lambda forecast: (
            f"target-{forecast.forecast_record_id}"
        ),
        apply_forecast_commit_proof=lambda *args, **kwargs: None,
    )
    assert sc._causal_kappa(target, _kappa_evidence(rows), primitives) == 1.0
    assert len(observations) == 1
    assert observations[0]["cutoff"] == first_cutoff
    assert first_cutoff.astimezone(sc._new_york_zone()).date().isoformat() == (
        "2026-09-08"
    )
    assert observations[0]["session_id"] == "2026-09-09"


def test_every_durable_v9_row_validates_nonsentinel_lineage_before_filtering():
    as_of = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
    base = _v9_kappa_row(1)

    reserved_forecast = SimpleNamespace(
        **{
            **vars(base.forecast),
            "v3_model_version": "__NO_ADMISSIBLE_V9_LINEAGE__",
            "cohort_id": "__NO_ADMISSIBLE_V9_LINEAGE__",
            "cohort_hash": "0" * 64,
            # Make the row independently inadmissible.  Durable-row lineage
            # validation must happen before this outcome-blind filter.
            "evidence_origin": "REPLAY",
        }
    )
    reserved = replace(
        base,
        v3_model_version="__NO_ADMISSIBLE_V9_LINEAGE__",
        forecast=reserved_forecast,
    )
    with pytest.raises(sc.ProtocolDefect, match="reserved V9 sentinel"):
        sc._select_lineage(
            V9_30S, _kappa_evidence((reserved,)), as_of
        )

    malformed_forecast = SimpleNamespace(
        **{
            **vars(base.forecast),
            "horizon": "1M",
            "cohort_hash": "not-a-64-lowercase-hex-digest",
        }
    )
    nonselected = replace(
        base,
        horizon="1M",
        target_endpoint=base.cutoff_at + timedelta(minutes=1),
        forecast=malformed_forecast,
    )
    with pytest.raises(sc.ProtocolDefect, match="lineage value"):
        sc._select_lineage(
            V9_30S, _kappa_evidence((nonselected,)), as_of
        )


def test_population_loader_reconciles_streams_and_closes_every_cursor(monkeypatch):
    upper = datetime(2026, 9, 8, 19, 59, tzinfo=UTC)
    scan_start = upper + timedelta(minutes=1)

    class Cursor:
        def __init__(self, rows):
            self.rows = list(rows)
            self.closed = False

        def execute(self, sql, params=None):
            self.sql = sql
            self.params = params

        def fetchall(self):
            rows, self.rows = self.rows, []
            return rows

        def fetchmany(self, size):
            assert size == sc.PROOF_BATCH_SIZE
            if not self.rows:
                return []
            return [self.rows.pop(0)]

        def close(self):
            self.closed = True

    counts = Cursor(((1, 1, 1, 1),))
    lookup = Cursor(())
    family_stream = Cursor(((1, None, None, "realized-volatility-v1") + (None,) * 10 + ("22",),))
    v9_stream = Cursor((("opaque-v9-row",),))

    class Connection:
        def cursor(self, name=None):
            if name is None:
                return lookup
            return {
                "v1b_family_stream": family_stream,
                "v1b_v9_forecast_stream": v9_stream,
            }[name]

    family = sc.FamilyEvidenceRow(
        forecast_id=1,
        forecast_inserting_xid="11",
        quant_id="q3_volatility",
        formula_version="realized-volatility-v1",
        cycle_id="cycle-1",
        symbol="COIN",
        horizon="5M",
        cutoff_epoch=upper.timestamp() - 600,
        maturity_epoch=upper.timestamp() - 300,
        cutoff_midpoint=100.0,
        forecast_volatility_bps=2.0,
        created_epoch=upper.timestamp() - 599,
        data_schema_version="synthetic-v1",
        source_spec_version="synthetic-v1",
        outcome_inserting_xid="22",
        maturity_midpoint=101.0,
        realized_move_bps=1.0,
        resolved_epoch=upper.timestamp() - 299,
        forecast_proof=None,
        outcome_proof=None,
    )
    cutoff = upper - timedelta(minutes=1)
    endpoint = cutoff + timedelta(seconds=30)
    forecast = SimpleNamespace(
        persisted_at=cutoff + timedelta(seconds=1),
        persistence_proof_eligible=True,
    )
    outer = {
        "forecast_record_id": "v9-1",
        "forecast_record_hash": "a" * 64,
        "symbol": "COIN",
        "cutoff_at": cutoff,
        "target_endpoint": endpoint,
        "horizon": "30S",
        "cycle_id": "cycle-v9",
        "v3_model_version": "V9-SYNTHETIC",
        "persisted_at": cutoff,
    }
    proof = sc.V9ForecastCommitProof(
        "v9-1",
        "a" * 64,
        cutoff + timedelta(seconds=1),
        endpoint,
        True,
        sc.PROOF_METHOD,
    )
    monkeypatch.setattr(sc, "_load_legacy_proofs", lambda *args, **kwargs: {})
    monkeypatch.setattr(sc, "_validate_family_row", lambda *args, **kwargs: family)
    monkeypatch.setattr(
        sc, "_load_v9_outcomes", lambda *args, **kwargs: ({"v9-1": ()}, 1)
    )
    monkeypatch.setattr(
        sc, "_validate_v9_forecast", lambda *args, **kwargs: (outer, forecast)
    )
    monkeypatch.setattr(
        sc, "_load_v9_proofs", lambda *args, **kwargs: {"v9-1": proof}
    )

    population = sc.load_evidence_population(
        SimpleNamespace(
            cursor=counts,
            connection=Connection(),
            scan_started_at=scan_start,
        ),
        upper,
        deserialize_forecast_record=lambda *args, **kwargs: None,
        deserialize_outcome_record=lambda *args, **kwargs: None,
        canonical_target_identity=lambda value: "target-v9-1",
        apply_forecast_commit_proof=lambda value, proof_row: value,
        stage_after_first_read=sc.DatabaseFailureStage.SEALED_OR_RECOVERY,
    )

    assert population.family_rows == (family,)
    assert population.v9_rows[0].forecast_proof == proof
    assert population.source_counts == {
        "public.volatility_forecasts": 1,
        "public.volatility_forecast_outcomes": 1,
        "public.atom_v9_v4_forecasts": 1,
        "public.atom_v9_v4_outcomes": 1,
    }
    assert lookup.closed and family_stream.closed and v9_stream.closed


def test_ready_scan_projection_freezes_population_windows_and_regression():
    candidate = _xnys_session(date(2026, 9, 8))
    population = _population(_ready_windows())
    counts = sc.readiness_counts(population)
    lineage = {
        "cell_order": population.spec.cell_order,
        "forecaster": population.spec.forecaster,
        "horizon": population.spec.horizon,
        "lineage_identity": dict(population.lineage_identity),
    }
    scan = sc.ScanResult(
        first_candidate_session=candidate.session_date,
        completed_candidates=(candidate,),
        boundary=sc.CandidateResult(
            candidate,
            (lineage,),
            (),
            (population,),
            (counts,),
        ),
    )

    projection = sc._ready_scan_projection(scan)

    assert projection["first_candidate_session"] == "2026-09-08"
    assert projection["boundary_session"] == "2026-09-08"
    assert projection["selected_lineages"] == [lineage]
    assert projection["counts"] == [counts.public(require_ready=True)]
    projected = projection["populations"][0]
    assert len(projected["windows"]) == len(population.windows)
    assert len(projected["regression"]) == len(population.regression)
    assert projected["accounting"]["protocol_defect"] is False


def test_authority_comment_parser_accepts_linked_payload_v2():
    execution_sha = "b" * 40
    components = {"synthetic-component": "a" * 64}
    provenance = {
        "schema_version": "ATOM-V1B-RUNTIME-PROVENANCE-1",
        "render_service_id": sc.RENDER_SERVICE_ID,
        "render_build_id": "build-1",
        "render_deploy_id": "build-1",
        "repository": sc.GITHUB_REPOSITORY,
        "execution_source_sha": execution_sha,
        "build_command": "pip install -r requirements.txt",
        "python_version": "3.14.3",
        "runtime_artifact_components": components,
        "runtime_artifact_sha256": sc.canonical_sha256(components),
        "probe_generated_at_utc": "2026-09-09T01:00:00.000000Z",
        "github_tls_trust": {
            "source": "ssl.get_default_verify_paths().cafile",
            "reported_cafile_path": "/etc/ssl/certs/ca-certificates.crt",
            "canonical_cafile_path": "/etc/ssl/certs/ca-certificates.crt",
            "cafile_size_bytes": 1,
            "cafile_sha256": "c" * 64,
        },
    }
    window = _window_approval_projection(
        execution_sha=execution_sha,
        opened_at="2026-09-09T01:05:00.000000Z",
    )
    payload = {
        "schema_version": sc.OPERATIONAL_APPROVAL_SCHEMA_VERSION,
        "provenance": provenance,
        "provenance_sha256": sc.canonical_sha256(provenance),
        "capacity": {
            "mechanism": "Render native one-off Create job startCommand",
            "service_id": sc.RENDER_SERVICE_ID,
            "recovery_transport_policy": sc.RECOVERY_TRANSPORT_POLICY,
        },
        "no_ref_update_window": window,
        "no_ref_update_window_sha256": sc.canonical_sha256(window),
        "probe_job_id": "job-probe-1",
        "probe_observation_sha256": "d" * 64,
        "control_plane_evidence_sha256": "e" * 64,
        "pat_scope_evidence_sha256": "f" * 64,
        "incident_record_id": "ATOM-SEC-INCIDENT-V1B-READER-CREDENTIAL-2026-09-06",
        "incident_finalization_sha256": "1" * 64,
        "rotation_status": "COMPLETED",
        "rotation_completion_timestamp": "2026-09-09T01:04:00.000000Z",
    }
    payload_hash = sc.canonical_sha256(payload)
    review_body = {
        "schema_version": "ATOM-V1B-OPERATIONAL-REVIEW-1",
        "approval_payload_sha256": payload_hash,
        "verdict": "PASS",
        "material_findings": 0,
    }
    approval_body = {
        "schema_version": "ATOM-V1B-OPERATIONAL-APPROVAL-1",
        "payload": payload,
        "approval_payload_sha256": payload_hash,
        "independent_review_comment_id": 101,
        "independent_reviewer_user_id": 999,
        "independent_reviewer_login": "independent-reviewer",
    }

    def envelope(comment_id, user_id, login, created_at, body):
        return {
            "id": comment_id,
            "user": {"id": user_id, "login": login},
            "created_at": created_at,
            "updated_at": created_at,
            "body": sc.canonical_json(body) + "\n",
        }

    comments = (
        envelope(
            101,
            999,
            "independent-reviewer",
            "2026-09-09T01:06:00Z",
            review_body,
        ),
        envelope(
            102,
            sc.GITHUB_OWNER_ID,
            sc.GITHUB_OWNER_LOGIN,
            "2026-09-09T01:07:00Z",
            approval_body,
        ),
    )
    approvals, reviews = sc.parse_authority_comments(
        comments,
        artifact_components_validator=lambda value: value,
    )

    assert len(approvals) == 1
    assert approvals[0].payload == payload
    assert approvals[0].review_comment_id == 101
    assert reviews[101].approval_payload_sha256 == payload_hash


def test_tls_connector_retries_address_and_completes_nonblocking_handshake(
    monkeypatch,
):
    class RawSocket:
        def __init__(self, result, socket_error=0):
            self.result = result
            self.socket_error = socket_error
            self.closed = False

        def setblocking(self, value):
            assert value is False

        def connect_ex(self, sockaddr):
            self.sockaddr = sockaddr
            return self.result

        def getsockopt(self, level, option):
            assert (level, option) == (sc.socket.SOL_SOCKET, sc.socket.SO_ERROR)
            return self.socket_error

        def close(self):
            self.closed = True

    class TLSSocket:
        def __init__(self):
            self.handshakes = 0
            self.closed = False

        def setblocking(self, value):
            assert value is False

        def do_handshake(self):
            self.handshakes += 1
            if self.handshakes == 1:
                raise sc.ssl.SSLWantReadError()
            if self.handshakes == 2:
                raise sc.ssl.SSLWantWriteError()

        def selected_alpn_protocol(self):
            return "http/1.1"

        def fileno(self):
            return -1 if self.closed else 7

        def close(self):
            self.closed = True

    failed = RawSocket(sc.errno.ECONNREFUSED)
    connected = RawSocket(sc.errno.EINPROGRESS)
    sockets = iter((failed, connected))
    tls = TLSSocket()

    class Context:
        def wrap_socket(self, raw, **kwargs):
            assert raw is connected
            assert kwargs == {
                "server_hostname": sc.GITHUB_API_HOST,
                "do_handshake_on_connect": False,
                "suppress_ragged_eofs": False,
            }
            return tls

    waits = []
    monkeypatch.setattr(
        sc,
        "_selector_wait",
        lambda seams, target, event, context, end: waits.append(event),
    )
    seams = sc.GithubTransportSeams(
        monotonic_ns=lambda: 0,
        socket_factory=lambda *args: next(sockets),
    )
    result = sc._connect_tls(
        seams,
        Context(),
        sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        sc.GITHUB_CONNECT_TIMEOUT_NS,
        (
            ("AF_INET", "192.0.2.1", 443),
            ("AF_INET", "192.0.2.2", 443),
        ),
    )

    assert result is tls
    assert failed.closed is True
    assert connected.closed is False
    assert waits == [
        sc.selectors.EVENT_WRITE,
        sc.selectors.EVENT_READ,
        sc.selectors.EVENT_WRITE,
    ]


def test_receipt_tree_scan_filters_and_byte_sorts_paths(monkeypatch):
    paths = (
        b"docs/irrelevant.md",
        b"docs/v-1b-volatility-scorecard-receipt-v1b-late-1.json",
        b"docs/v-1b-volatility-scorecard-receipt-v1b-early-4.json",
    )
    monkeypatch.setattr(
        sc,
        "_git_read",
        lambda *args, **kwargs: b"\0".join(paths) + b"\0",
    )
    result = sc._receipt_paths_at(
        sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        lambda: 0,
        "b" * 40,
    )
    assert result == tuple(
        sorted(
            (path.decode("ascii") for path in paths[1:]),
            key=lambda item: item.encode("utf-8"),
        )
    )


def test_publication_proof_readers_validate_complete_and_missing_rows():
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchall(self):
            return self.rows

    upper = datetime(2026, 9, 9, 1, 0, tzinfo=UTC)
    observed = upper - timedelta(seconds=2)
    legacy_cursor = Cursor(
        ((sc.FAMILY_FORECAST_KIND, 7, "123", observed, sc.PROOF_METHOD),)
    )
    legacy = sc._load_legacy_proofs(
        legacy_cursor,
        kind=sc.FAMILY_FORECAST_KIND,
        record_ids=(7,),
        upper_as_of=upper,
    )
    assert legacy[7].inserting_xid == "123"

    endpoint = upper + timedelta(seconds=30)
    v9_cursor = Cursor(
        (
            (1, "missing", None, None, None, None, None, None),
            (
                2,
                "present",
                "present",
                "a" * 64,
                observed,
                endpoint,
                True,
                sc.PROOF_METHOD,
            ),
        )
    )
    v9 = sc._load_v9_proofs(
        v9_cursor,
        (
            ("missing", "b" * 64, endpoint),
            ("present", "a" * 64, endpoint),
        ),
    )
    assert v9["missing"] is None
    present = v9["present"]
    assert present is not None
    assert present.proof_eligible is True


def test_local_tree_entry_parses_exact_blob_and_reads_its_bytes(monkeypatch):
    path = "quant/volatility_scorecard.py"
    blob = "a" * 40
    calls = []

    def git_read(context, clock_ns, *arguments):
        calls.append(arguments)
        if arguments[0] == "ls-tree":
            return f"100644 blob {blob}\t{path}\0".encode("ascii")
        assert arguments == ("cat-file", "blob", blob)
        return b"reviewed-source"

    monkeypatch.setattr(sc, "_git_read", git_read)
    result = sc._local_tree_entry(
        sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        lambda: 0,
        "b" * 40,
        path,
    )
    assert result == ("100644", blob, b"reviewed-source")
    assert len(calls) == 2


def test_repository_facts_authentication_completes_unique_integration(monkeypatch):
    execution_sha = "e" * 40
    implementation_sha = "d" * 40
    implementation_head = "c" * 40
    tree_sha = "a" * 40
    merged_at = datetime(2026, 9, 8, 1, 0, tzinfo=UTC)
    corrective_at = merged_at + timedelta(hours=1)

    def git_ascii(context, clock_ns, *arguments):
        if arguments == ("rev-parse", "HEAD"):
            return execution_sha
        if arguments[:2] == ("rev-parse", f"{execution_sha}^{{tree}}"):
            return tree_sha
        if arguments[:2] == ("rev-parse", f"{implementation_sha}^{{tree}}"):
            return tree_sha
        if arguments[0:3] == ("rev-list", "--first-parent", "--reverse"):
            return "\n".join(
                (sc.CORRECTIVE_AMENDMENT_MERGE_SHA, implementation_sha)
            )
        raise AssertionError(arguments)

    monkeypatch.setattr(sc, "_git_ascii", git_ascii)
    monkeypatch.setattr(
        sc,
        "_github_commit",
        lambda *args, **kwargs: {"commit": {"tree": {"sha": tree_sha}}},
    )
    fixed_times = iter((merged_at, merged_at, merged_at, merged_at))
    monkeypatch.setattr(
        sc,
        "_authenticate_fixed_merge",
        lambda *args, **kwargs: next(fixed_times),
    )
    exact_times = iter((merged_at, corrective_at))
    monkeypatch.setattr(
        sc,
        "_authenticate_exact_amendment_merge",
        lambda *args, **kwargs: next(exact_times),
    )
    monkeypatch.setattr(sc, "_require_first_parent_ancestor", lambda *args: None)
    monkeypatch.setattr(
        sc,
        "_commit_diff_paths",
        lambda context, clock_ns, commit: (
            frozenset({sc.CORRECTIVE_AMENDMENT_PATH})
            if commit == sc.CORRECTIVE_AMENDMENT_MERGE_SHA
            else sc.IMPLEMENTATION_PATHS
        ),
    )
    monkeypatch.setattr(
        sc,
        "_associated_merged_pr",
        lambda *args, **kwargs: {
            "user": {
                "id": sc.GITHUB_OWNER_ID,
                "login": sc.GITHUB_OWNER_LOGIN,
            },
            "head": {"sha": implementation_head},
            "created_at": "2026-09-08T03:00:00Z",
        },
    )
    monkeypatch.setattr(sc, "_authenticate_bound_path", lambda *args: None)
    migration_entry = ("100644", "9" * 40, b"migration")
    monkeypatch.setattr(
        sc, "_local_tree_entry_optional", lambda *args: migration_entry
    )
    monkeypatch.setattr(sc, "EVIDENCE_ARTIFACTS", ())
    monkeypatch.setattr(sc, "_receipt_paths_at", lambda *args: ())
    client = SimpleNamespace(_seams=SimpleNamespace(monotonic_ns=lambda: 0))

    facts = sc.authenticate_immutable_repository_facts(
        client,
        sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        execution_sha,
    )

    assert facts.execution_sha == execution_sha
    assert facts.implementation_merge_sha == implementation_sha
    assert facts.receipts == ()
    assert facts.history_sha256 == sc.canonical_sha256([])


def test_github_commit_blob_and_associated_pr_validators_accept_exact_objects():
    commit_sha = "b" * 40
    blob_sha = "a" * 40
    blob_bytes = b"exact reviewed bytes"
    merged_at = "2026-09-09T01:00:00Z"

    class Client:
        _seams = SimpleNamespace(monotonic_ns=lambda: 0)

        def get_json(self, target, *, context, validator, **kwargs):
            if target.endswith("/commits/" + commit_sha):
                value = {
                    "sha": commit_sha,
                    "commit": {
                        "verification": {
                            "verified": True,
                            "reason": "valid",
                            "signature": "signed",
                            "payload": "payload",
                        },
                        "tree": {"sha": "c" * 40},
                        "committer": {"date": merged_at},
                    },
                }
            elif target.endswith("/git/blobs/" + blob_sha):
                encoded = sc.base64.b64encode(blob_bytes).decode("ascii")
                value = {
                    "sha": blob_sha,
                    "encoding": "base64",
                    "size": len(blob_bytes),
                    "content": encoded,
                }
            elif target.endswith("/pulls/333"):
                value = {
                    "number": 333,
                    "merged": True,
                    "merge_commit_sha": commit_sha,
                    "base": {
                        "ref": "main",
                        "repo": {"full_name": sc.GITHUB_REPOSITORY},
                    },
                    "merged_by": {
                        "id": sc.GITHUB_OWNER_ID,
                        "login": sc.GITHUB_OWNER_LOGIN,
                    },
                    "merged_at": merged_at,
                }
            else:
                raise AssertionError(target)
            return SimpleNamespace(status=200, headers={}), validator(
                value, 200, {}, lambda: context.check(self._seams.monotonic_ns)
            )

        def get_paginated_json(
            self,
            target,
            *,
            context,
            page_validator,
            collection_validator,
        ):
            item = {
                "number": 333,
                "merge_commit_sha": commit_sha,
                "merged_at": merged_at,
            }
            check = lambda: context.check(self._seams.monotonic_ns)
            page = page_validator([item], check)
            return collection_validator(tuple(page), context)

    client = Client()
    context = sc.GithubDeadlineContext.begin_checkpoint(lambda: 0)
    assert sc._github_commit(client, context, commit_sha)["sha"] == commit_sha
    assert sc._github_blob(client, context, blob_sha) == blob_bytes
    assert sc._associated_merged_pr(
        client, context, commit_sha, expected_number=333
    )["number"] == 333


def test_commit_diff_paths_decodes_complete_no_rename_change_set(monkeypatch):
    commit_sha = "b" * 40
    parent_sha = "a" * 40
    monkeypatch.setattr(
        sc,
        "_git_ascii",
        lambda *args: f"{commit_sha} {parent_sha}",
    )
    monkeypatch.setattr(
        sc,
        "_git_read",
        lambda *args: b"old/name.py\0new/name.py\0",
    )
    assert sc._commit_diff_paths(
        sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
        lambda: 0,
        commit_sha,
    ) == frozenset({"old/name.py", "new/name.py"})


def test_fixed_and_exact_amendment_authentication_accept_matching_bytes(
    monkeypatch,
):
    execution_sha = "e" * 40
    merge_sha = "d" * 40
    predecessor_sha = "c" * 40
    path = "docs/corrective.md"
    decision_id = "CORRECTIVE-1"
    merged_at = "2026-09-09T01:00:00Z"
    content = (decision_id + "\n").encode("ascii")
    blob_sha = "a" * 40
    client = SimpleNamespace(_seams=SimpleNamespace(monotonic_ns=lambda: 0))
    context = sc.GithubDeadlineContext.begin_checkpoint(lambda: 0)
    detail = {
        "merged_at": merged_at,
        "user": {
            "id": sc.GITHUB_OWNER_ID,
            "login": sc.GITHUB_OWNER_LOGIN,
        },
    }
    monkeypatch.setattr(
        sc,
        "_checkpoint_git_run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        sc,
        "_github_commit",
        lambda *args: {"commit": {"committer": {"date": merged_at}}},
    )
    monkeypatch.setattr(sc, "_associated_merged_pr", lambda *args, **kwargs: detail)
    monkeypatch.setattr(sc, "_authenticate_path", lambda *args, **kwargs: content)

    assert sc._authenticate_fixed_merge(
        client,
        context,
        execution_sha,
        merge_sha,
        332,
        path,
        decision_id,
    ) == datetime(2026, 9, 9, 1, 0, tzinfo=UTC)

    monkeypatch.setattr(sc, "_require_first_parent_ancestor", lambda *args: None)
    monkeypatch.setattr(
        sc, "_commit_diff_paths", lambda *args: frozenset({path})
    )
    monkeypatch.setattr(
        sc, "_local_tree_entry", lambda *args: ("100644", blob_sha, content)
    )
    monkeypatch.setattr(sc, "_github_blob", lambda *args: content)
    assert sc._authenticate_exact_amendment_merge(
        client,
        context,
        execution_sha,
        predecessor_sha=predecessor_sha,
        merge_sha=merge_sha,
        pr_number=332,
        merged_at_text=merged_at,
        path=path,
        decision_id=decision_id,
        git_blob_sha1=blob_sha,
        raw_sha256=hashlib.sha256(content).hexdigest(),
    ) == datetime(2026, 9, 9, 1, 0, tzinfo=UTC)


def test_loaded_specless_runtime_names_are_limited_to_frozen_exceptions(
    monkeypatch,
):
    main_module = sc.ModuleType("__main__")
    main_module.__file__ = None
    main_module.__package__ = None
    main_module.__loader__ = importlib.machinery.BuiltinImporter
    main_module.__spec__ = None

    DeprecatedType = type("_DeprecatedType", (), {})
    DeprecatedType.__module__ = "typing"
    deprecated_io = DeprecatedType()
    deprecated_io.__module__ = "typing"
    deprecated_io.__spec__ = None
    deprecated_re = DeprecatedType()
    deprecated_re.__module__ = "typing"
    deprecated_re.__spec__ = None

    cython_runtime = sc.ModuleType("cython_runtime")
    cython_runtime.__spec__ = None
    cython_runtime.__file__ = None
    cython_runtime.__loader__ = None
    cython_runtime.__package__ = None

    cython_name = "_cython_3_1_0"
    cython_module = sc.ModuleType(cython_name)
    cython_module.__spec__ = None
    cython_module.__file__ = None
    cython_module.__loader__ = None
    cython_module.__package__ = None
    generated_type = type("GeneratedCythonType", (), {})
    generated_type.__module__ = cython_name
    cython_module._common_types_metatype = object()
    cython_module.cython_function_or_method = generated_type
    cython_module.generator = generated_type

    modules = {
        "__main__": main_module,
        "typing.io": deprecated_io,
        "typing.re": deprecated_re,
        "cython_runtime": cython_runtime,
        cython_name: cython_module,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sc.validate_loaded_module_sources(
        tuple(modules),
        covered_source_paths=(),
        covered_native_paths=(),
        namespace_roots=(),
    )


def test_runtime_file_walk_and_cooperative_reader_cover_regular_tree(
    tmp_path,
):
    root = tmp_path.resolve()
    nested = root / "nested"
    excluded = root / "excluded"
    nested.mkdir()
    excluded.mkdir()
    first = root / "a.py"
    second = nested / "b.so"
    ignored_cache = nested / "c.pyc"
    excluded_file = excluded / "d.py"
    first.write_bytes(b"alpha")
    second.write_bytes(b"beta")
    ignored_cache.write_bytes(b"cache")
    excluded_file.write_bytes(b"excluded")
    checks = []

    candidates = sc._walk_regular_candidates(
        str(root),
        excluded_roots=(str(excluded.resolve()),),
        check=lambda: checks.append(True),
    )

    assert candidates == (
        sc.FileCandidate(first.as_posix(), str(first.resolve())),
        sc.FileCandidate(second.as_posix(), str(second.resolve())),
    )
    assert sc._cooperative_read_bytes(
        str(first.resolve()), check=lambda: checks.append(True)
    ) == b"alpha"
    assert checks


def test_native_candidate_collection_keeps_regular_and_allowed_kernel_maps(
    tmp_path,
):
    library = tmp_path / "libsynthetic.so"
    library.write_bytes(b"elf")
    canonical = str(library.resolve())
    candidates = sc._collect_native_candidates(
        (
            sc.ProcMapEntry(1, 2, "rw-p", 0, None),
            sc.ProcMapEntry(2, 3, "r-xp", 0, "[vdso]"),
            sc.ProcMapEntry(3, 4, "r-xp", 0, canonical),
            sc.ProcMapEntry(4, 5, "r-xp", 4096, canonical),
        )
    )
    assert candidates == (sc.FileCandidate(canonical, canonical),)


@pytest.mark.parametrize("endpoint_delay", (5, 5.000000000000001))
def test_runtime_closure_requires_exact_binary64_endpoint_delay(
    endpoint_delay,
    monkeypatch,
    _synthetic_zoneinfo_isolation,
):
    state = _synthetic_zoneinfo_isolation
    monkeypatch.setattr(sc, "_initialize_zoneinfo_isolation", lambda: state)

    def load_closure():
        _calendar, modules = _synthetic_runtime_closure_modules(
            monkeypatch, state
        )
        modules["quant.v9_v4a_evidence"].MAX_ENDPOINT_OBSERVATION_DELAY_SECONDS = (
            endpoint_delay
        )
        return frozenset(sys.modules)

    monkeypatch.setattr(sc, "_load_complete_runtime_closure", load_closure)
    with pytest.raises(sc.OrchestrationFailure, match="V4A_OVERLAP_CONTRACT_CHANGED"):
        sc._initialize_runtime_for_measurement()


def test_production_calendar_reader_returns_strict_utc_sessions(monkeypatch):
    days = (date(2026, 9, 8), date(2026, 9, 9))

    class Label:
        def __init__(self, value):
            self.value = value

        def date(self):
            return self.value

    labels = tuple(Label(day) for day in days)

    class Calendar:
        name = "XNYS"

        def sessions_in_range(self, start, end):
            assert (start, end) == ("2026-09-08", "2026-09-09")
            return labels

        def is_session(self, label):
            return label in labels

        def session_open(self, label):
            return datetime.combine(label.date(), datetime.min.time(), UTC) + timedelta(
                hours=13, minutes=30
            )

        def session_close(self, label):
            return datetime.combine(label.date(), datetime.min.time(), UTC) + timedelta(
                hours=20
            )

    monkeypatch.setattr(sc, "_ZONEINFO_ISOLATION", object())
    monkeypatch.setattr(sc, "_validate_zoneinfo_isolation", lambda value: None)
    read = sc._production_calendar_reader(Calendar())
    assert read(days[0], days[1]) == tuple(
        sc.CalendarSession(
            day,
            datetime.combine(day, datetime.min.time(), UTC)
            + timedelta(hours=13, minutes=30),
            datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=20),
        )
        for day in days
    )


def test_associated_pr_rejects_missing_repository_without_attribute_access():
    commit_sha = "b" * 40

    class Client:
        _seams = SimpleNamespace(monotonic_ns=lambda: 0)

        def get_paginated_json(
            self,
            target,
            *,
            context,
            page_validator,
            collection_validator,
        ):
            item = {
                "number": 333,
                "merge_commit_sha": commit_sha,
                "merged_at": "2026-09-09T01:00:00Z",
            }
            check = lambda: context.check(self._seams.monotonic_ns)
            return collection_validator(tuple(page_validator([item], check)), context)

        def get_json(self, target, *, context, validator):
            detail = {
                "number": 333,
                "merged": True,
                "merge_commit_sha": commit_sha,
                "base": {"ref": "main", "repo": None},
                "merged_by": {
                    "id": sc.GITHUB_OWNER_ID,
                    "login": sc.GITHUB_OWNER_LOGIN,
                },
                "merged_at": "2026-09-09T01:00:00Z",
            }
            return None, validator(
                detail,
                200,
                {},
                lambda: context.check(self._seams.monotonic_ns),
            )

    with pytest.raises(sc.GitHubAuthorityFailure):
        sc._associated_merged_pr(
            Client(),
            sc.GithubDeadlineContext.begin_checkpoint(lambda: 0),
            commit_sha,
            expected_number=333,
        )
