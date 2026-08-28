from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import pytest
from spikes.v2_frozen_schema_feasibility import build_legacy, canonical_receipt
from spikes.v2a_external_parity import observations, targets
from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS,
    DIRECTIONAL_FAMILIES,
    HORIZON_SECONDS,
    MAGNITUDE_BPS,
    Q3,
    RawFamilyObservation,
    RawTarget,
    TargetIdentity,
    build_v2a_dataset,
)
from quant.v9_v2a_external import (
    build_external_v2a,
    build_external_v2b,
    build_external_v2c,
    build_external_v2d,
    cleanup_owned_workspace,
    validate_external_v2a,
    _effective_n,
    _effective_n_squared,
)
from quant.v9_v2b_calibration import v2b_component_hash
from quant.v9_v2d_evidence_state import serialize_v2_evidence_state

KW = dict(
    state_as_of=2e9,
    target_spec_id="gate-target",
    target_data_schema_version="gate-schema",
    target_source_spec_version="gate-source",
    formula_version="gate-q1",
    family_data_schema_version="gate-schema",
    family_source_spec_version="gate-source",
)


def build(tmp_path, n=16, **extra):
    return build_external_v2a(
        **KW, targets=targets(n), observations=observations(n), root=tmp_path, **extra
    )


def close(view, root):
    path = view.workspace
    view.close()
    cleanup_owned_workspace(path, root=root)
    assert not path.exists()


def representative(values, forecasts, *, constant_forecast=False):
    target_rows = []
    observation_rows = []
    for index, (target, forecast) in enumerate(zip(values, forecasts)):
        cutoff = float(index * 30)
        identity = TargetIdentity(f"representative-{index:03d}", cutoff, cutoff + 30)
        target_rows.append(
            RawTarget(
                index,
                identity.cycle_id,
                "COIN",
                "gate-target",
                "gate-schema",
                "gate-source",
                "30S",
                cutoff,
                cutoff + 30,
                cutoff + 30,
                float(target),
            )
        )
        observation_rows.append(
            RawFamilyObservation(
                index,
                identity,
                "COIN",
                "q1_momentum",
                "gate-q1",
                "gate-schema",
                "gate-source",
                "30S",
                DIRECTIONAL_BPS,
                float(forecast),
                cutoff,
                cutoff,
                cutoff,
                "FRESH",
            )
        )
    return target_rows, observation_rows


def assert_representative_parity(tmp_path, target_rows, observation_rows):
    legacy_dataset = build_v2a_dataset(
        state_as_of=2e9,
        horizon="30S",
        target_spec_id="gate-target",
        target_data_schema_version="gate-schema",
        target_source_spec_version="gate-source",
        family_versions=(("q1_momentum", "gate-q1", "gate-schema", "gate-source"),),
        targets=target_rows,
        observations=observation_rows,
    )
    from quant.v9_v2b_calibration import calibrate_v2b
    from quant.v9_v2c_covariance import build_v2c_covariance
    from quant.v9_v2d_evidence_state import build_v2d_evidence_state

    legacy_b = calibrate_v2b((legacy_dataset,))
    legacy_c = build_v2c_covariance(legacy_dataset, legacy_b)
    legacy_state = build_v2d_evidence_state(
        state_as_of=2e9,
        datasets=(legacy_dataset,),
        calibrations=(legacy_b,),
        covariances=(legacy_c,),
    )
    view = build_external_v2a(
        **KW, targets=target_rows, observations=observation_rows, root=tmp_path
    )
    external_b = build_external_v2b(view)
    external_c = build_external_v2c(view, external_b)
    external_state = build_external_v2d(view, external_b, external_c)
    assert view.dataset_hash == legacy_dataset.dataset_hash
    assert external_b == legacy_b
    assert v2b_component_hash(external_b, "30S") == v2b_component_hash(legacy_b, "30S")
    assert external_c == legacy_c
    assert serialize_v2_evidence_state(external_state) == serialize_v2_evidence_state(
        legacy_state
    )
    assert external_state.state_id == legacy_state.state_id
    assert canonical_receipt(external_state, len(target_rows)) == canonical_receipt(
        legacy_state, len(target_rows)
    )
    close(view, tmp_path)
    return legacy_dataset, legacy_b, legacy_c


def test_exact_frozen_chain_and_receipt_parity(tmp_path):
    view = build(tmp_path)
    legacy = build_legacy(16)
    b = build_external_v2b(view)
    c = build_external_v2c(view, b)
    state = build_external_v2d(view, b, c)
    assert view.dataset_hash == legacy[0].dataset_hash
    assert v2b_component_hash(b, "30S") == v2b_component_hash(legacy[1], "30S")
    assert c == legacy[2]
    assert serialize_v2_evidence_state(state) == serialize_v2_evidence_state(legacy[3])
    assert state.state_id == legacy[3].state_id
    assert canonical_receipt(state, 16) == canonical_receipt(legacy[3], 16)
    close(view, tmp_path)


def test_all_72_family_horizon_slots_have_exact_external_v2a_parity(tmp_path):
    versions = tuple(
        (quant_id, f"{quant_id}-frozen", "gate-schema", "gate-source")
        for quant_id in (*DIRECTIONAL_FAMILIES, Q3)
    )
    for horizon, seconds in HORIZON_SECONDS.items():
        target_rows = []
        observation_rows = []
        for index in range(4):
            cutoff = float(index * seconds)
            identity = TargetIdentity(f"{horizon}-{index}", cutoff, cutoff + seconds)
            target_rows.append(
                RawTarget(
                    index,
                    identity.cycle_id,
                    "COIN",
                    "gate-target",
                    "gate-schema",
                    "gate-source",
                    horizon,
                    cutoff,
                    cutoff + seconds,
                    cutoff + seconds,
                    float(index + 1),
                )
            )
            for family_index, (quant_id, formula, _schema, _source) in enumerate(
                versions
            ):
                # Q10's empty subset proves certified unavailability is not
                # confused with a missing lineage entry.
                if quant_id == "q10_options_vol":
                    continue
                observation_rows.append(
                    RawFamilyObservation(
                        index * 100 + family_index,
                        identity,
                        "COIN",
                        quant_id,
                        formula,
                        "gate-schema",
                        "gate-source",
                        horizon,
                        MAGNITUDE_BPS if quant_id == Q3 else DIRECTIONAL_BPS,
                        float(index + family_index + 1),
                        cutoff,
                        cutoff,
                        cutoff,
                        "FRESH",
                    )
                )
        legacy = build_v2a_dataset(
            state_as_of=2e9,
            horizon=horizon,
            target_spec_id="gate-target",
            target_data_schema_version="gate-schema",
            target_source_spec_version="gate-source",
            family_versions=versions,
            targets=target_rows,
            observations=observation_rows,
        )
        external = build_external_v2a(
            state_as_of=2e9,
            horizon=horizon,
            target_spec_id="gate-target",
            target_data_schema_version="gate-schema",
            target_source_spec_version="gate-source",
            family_versions=versions,
            targets=iter(target_rows),
            observations=iter(observation_rows),
            root=tmp_path,
        )
        assert external.dataset_hash == legacy.dataset_hash
        assert external.family_lineage == legacy.family_lineage
        assert external.training_start == legacy.training_start
        assert external.training_end == legacy.training_end
        assert external.skeleton_count == len(legacy.skeleton)
        assert external.observation_count == sum(
            len(subset.observations) for subset in legacy.directional_subsets
        ) + len(legacy.q3_subset.observations)
        assert external.connection.execute(
            "SELECT count(*) FROM admitted WHERE quant='q10_options_vol'"
        ).fetchone() == (0,)
        close(external, tmp_path)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("formula_version", "wrong", "FORMULA_VERSION_MISMATCH"),
        ("data_schema_version", "wrong", "DATA_SCHEMA_VERSION_MISMATCH"),
        ("source_spec_version", "wrong", "SOURCE_SPEC_VERSION_MISMATCH"),
    ],
)
def test_wrong_observation_lineage_is_a_frozen_exclusion(
    tmp_path, field, value, reason
):
    rows = list(observations(2))
    rows[0] = replace(rows[0], **{field: value})
    dataset, _, _ = assert_representative_parity(tmp_path, list(targets(2)), rows)
    assert dict((x.reason_code, x.count) for x in dataset.exclusions) == {reason: 1}


def test_frozen_exclusions_duplicate_selection_and_boundaries_match(tmp_path):
    target_rows = list(targets(5))
    observation_rows = list(observations(5))
    target_rows.append(replace(target_rows[1], record_id=99))
    observation_rows.append(replace(observation_rows[2], record_id=99))
    observation_rows.append(replace(observation_rows[3], record_id=98, value_bps=99.0))
    observation_rows.append(
        replace(observation_rows[0], record_id=97, formula_version="wrong")
    )
    missing = replace(
        observation_rows[0],
        record_id=96,
        target_identity=TargetIdentity("missing", 900.0, 930.0),
    )
    observation_rows.append(missing)
    dataset, _, _ = assert_representative_parity(
        tmp_path, target_rows, observation_rows
    )
    exclusions = dict((x.reason_code, x.count) for x in dataset.exclusions)
    assert exclusions == {
        "DUPLICATE_CONFLICT": 1,
        "FORMULA_VERSION_MISMATCH": 1,
        "MISSING_SYNCHRONIZED_FAMILY": 1,
    }
    assert dataset.skeleton[1].record_id == 1
    assert dataset.directional_subsets[0].observations[2].record_id == 2


def test_noncausal_and_page_boundary_omission_are_frozen_exclusions(tmp_path):
    noncausal = list(observations(2))
    noncausal[0] = replace(noncausal[0], available_epoch=31.0)
    dataset, _, _ = assert_representative_parity(tmp_path, list(targets(2)), noncausal)
    assert dataset.exclusions[0].reason_code == "FORECAST_NOT_CAUSAL"
    omitted = list(observations(4097))
    omitted.pop(4096)
    dataset, _, _ = assert_representative_parity(tmp_path, list(targets(4097)), omitted)
    assert dict((x.reason_code, x.count) for x in dataset.exclusions) == {}


def test_all_excluded_no_evidence_path_matches(tmp_path):
    rows = [replace(row, formula_version="wrong") for row in observations(3)]
    dataset, calibration, covariance = assert_representative_parity(
        tmp_path, list(targets(3)), rows
    )
    assert dataset.exclusions[0].count == 3
    assert calibration.directional[0].status == "UNAVAILABLE"
    assert covariance.status == "UNAVAILABLE"


@pytest.mark.parametrize(
    "values,forecasts,identifiable",
    [
        (
            [1, 3, 2, 6, 4, 8, 7, 9, 5, 12, 8, 14],
            [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6],
            True,
        ),
        ([1, 2, 4, 3, 7, 5, 8, 6], [2] * 8, False),
    ],
)
def test_non_degenerate_effective_n_bias_slope_and_covariance_parity(
    tmp_path, values, forecasts, identifiable
):
    dataset, calibration, covariance = assert_representative_parity(
        tmp_path, *representative(values, forecasts)
    )
    result = calibration.directional[0]
    assert result.effective_n < result.family_observation_count
    assert result.residual_variance > 0 and result.raw_bias_bps != 0
    assert result.slope_identifiable_flag is identifiable
    assert covariance.pair_support_boolean_matrix == ((True,),)
    assert covariance.pooled_variance > 0


def test_multiple_retained_lags_are_exact_and_disk_accumulated(tmp_path):
    forecasts = [float(index % 3) for index in range(20)]
    residuals = [float(index) for index in range(20)]
    values = [forecast + residual for forecast, residual in zip(forecasts, residuals)]
    target_rows, observation_rows = representative(values, forecasts)
    assert_representative_parity(tmp_path, target_rows, observation_rows)
    view = build_external_v2a(
        **KW, targets=target_rows, observations=observation_rows, root=tmp_path
    )
    effective = _effective_n(view)
    mean = sum(residuals) / len(residuals)
    covariance_effective = _effective_n_squared(view, mean)
    assert effective.retained_lags >= 4
    assert effective.effective_n < len(residuals)
    assert covariance_effective < len(residuals)
    assert (
        view.connection.execute(
            "SELECT count(*) FROM autocorrelation_terms"
        ).fetchone()[0]
        == effective.retained_lags
    )
    assert (
        view.connection.execute(
            "SELECT count(*) FROM covariance_autocorrelation_terms"
        ).fetchone()[0]
        >= 4
    )
    close(view, tmp_path)


def test_large_nondegenerate_fresh_process_is_bounded_and_cleans(tmp_path):
    command = [
        sys.executable,
        str(Path(__file__).parents[1] / "spikes" / "v2a_external_parity.py"),
        "65537",
        "--root",
        str(tmp_path),
        "--nondegenerate",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    result = json.loads(completed.stdout)
    assert result["nondegenerate"] is True
    budget = 128 * 1024 * 1024
    # Linux carries an invoking process's historical ru_maxrss through fork
    # and exec. The dedicated gate starts below budget and checks the absolute
    # peak; a full-suite parent may already exceed it, so only the child's
    # additional high-water allocation is meaningful there.
    if result["baseline_rss_bytes"] < budget:
        assert result["external_v2a_peak_rss_bytes"] < budget
        assert result["external_verification_peak_rss_bytes"] < budget
    else:
        assert (
            result["external_verification_peak_rss_bytes"]
            - result["baseline_rss_bytes"]
            < budget
        )
    assert result["workspace_removed"] is True
    assert not list(tmp_path.iterdir())


def test_all_frozen_boundaries_match_legacy_hashes_with_non_linear_ram(tmp_path):
    # These identities were produced by the frozen concrete builder and are
    # also retained in docs/v2-frozen-schema-measurements.json.
    expected = {
        65_535: "d87f7415940e10cb0b6832dfb62d32091919aa9d061cccceb92187461d382671",
        65_536: "1e73a620e46dfe14f6ffb256bdbcd433df2e23191a170b6ae0495faf2e5ef633",
        65_537: "f12651038f83c688f1d9c9460a14f6eb231be6de4aa0c48bbab1ad2d79afaf07",
        200_000: "c7b8269c84ecd4c0cf63a88bf0580c5b4f5fdca323cfa1fe8a942227ea5fc81d",
    }
    results = []
    script = str(Path(__file__).parents[1] / "spikes" / "v2a_external_parity.py")
    for rows, digest in expected.items():
        completed = subprocess.run(
            [sys.executable, script, str(rows), "--root", str(tmp_path), "--v2a-only"],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        results.append(result)
        assert result["dataset_hash"] == digest
        assert result["workspace_removed"] is True
        growth = max(
            0, result["external_v2a_peak_rss_bytes"] - result["baseline_rss_bytes"]
        )
        if result["baseline_rss_bytes"] < 128 * 1024 * 1024:
            assert result["external_v2a_peak_rss_bytes"] < 128 * 1024 * 1024
        else:
            assert growth < 128 * 1024 * 1024
        assert not list(tmp_path.iterdir())
    retry = json.loads(
        subprocess.run(
            [sys.executable, script, "200000", "--root", str(tmp_path), "--v2a-only"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert retry["dataset_hash"] == results[-1]["dataset_hash"]
    assert (
        retry["peak_temporary_disk_bytes"] == results[-1]["peak_temporary_disk_bytes"]
    )
    nondegenerate = json.loads(
        subprocess.run(
            [
                sys.executable,
                script,
                "200000",
                "--root",
                str(tmp_path),
                "--v2a-only",
                "--nondegenerate",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert nondegenerate["dataset_hash"] == (
        "df1ed50de4c11f40d8807582210d97547c8f56c4b2d2279ab1f58fa3f57abe41"
    )
    assert nondegenerate["workspace_removed"] is True
    assert (
        max(
            0,
            nondegenerate["external_v2a_peak_rss_bytes"]
            - nondegenerate["baseline_rss_bytes"],
        )
        < 128 * 1024 * 1024
    )
    peaks = [
        max(0, item["external_v2a_peak_rss_bytes"] - item["baseline_rss_bytes"])
        for item in results
    ]
    assert max(peaks) - min(peaks) < 32 * 1024 * 1024


def test_corruption_interruption_disk_full_mismatch_and_cleanup_guard(
    tmp_path, monkeypatch
):
    view = build(tmp_path, 2)
    view.connection.execute(
        "UPDATE observations SET payload_hash=? WHERE record_id=1", ("0" * 64,)
    )
    view.connection.commit()
    with pytest.raises(ValueError, match="corrupt"):
        validate_external_v2a(view)
    close(view, tmp_path)
    view = build(tmp_path, 2)
    view.dataset_hash = "0" * 64
    with pytest.raises(ValueError, match="parity mismatch"):
        build_external_v2b(view)
    close(view, tmp_path)
    for phase in ("ingestion", "ordered_pass"):
        with pytest.raises(InterruptedError):
            build(tmp_path, 2, interrupt=phase)
        assert not list(tmp_path.iterdir())
    view = build(tmp_path, 2)
    workspace = view.workspace
    view.close()
    link = tmp_path / "atom-v2a-external-link"
    link.symlink_to(workspace, target_is_directory=True)
    with pytest.raises(ValueError, match="unowned"):
        cleanup_owned_workspace(link, root=tmp_path)
    assert workspace.exists()
    link.unlink()
    cleanup_owned_workspace(workspace, root=tmp_path)
    import quant.v9_v2a_external as module

    monkeypatch.setattr(
        module.sqlite3,
        "connect",
        lambda *_: (_ for _ in ()).throw(
            module.sqlite3.OperationalError("database or disk is full")
        ),
    )
    with pytest.raises(module.sqlite3.OperationalError, match="disk is full"):
        build(tmp_path, 2)
    assert not list(tmp_path.iterdir())
    unowned = tmp_path / "not-owned"
    unowned.mkdir()
    with pytest.raises(ValueError, match="unowned"):
        cleanup_owned_workspace(unowned, root=tmp_path)
