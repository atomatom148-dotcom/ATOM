from dataclasses import FrozenInstanceError
import math

import pytest

from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS, MAGNITUDE_BPS, Q3, RawFamilyObservation, RawTarget,
    TargetIdentity, build_v2a_dataset,
)


VERSIONS = (
    ("q1_momentum", "f1", "fs1", "src1"),
    ("q2_mean_reversion", "f2", "fs1", "src1"),
    (Q3, "f3", "fs1", "src1"),
)


def target(record_id, cutoff, *, value=4.0, resolved=None, cycle=None,
           schema="ts1"):
    return RawTarget(record_id, cycle or f"c{cutoff}", "COIN", "log-return-v1",
                     schema, "target-src1", "30S", cutoff, cutoff + 30,
                     cutoff + 31 if resolved is None else resolved, value)


def observation(record_id, target_row, quant="q1_momentum", *, value=2.0,
                formula=None, schema="fs1", source="src1", source_as_of=None,
                available=None, state="FRESH", numerical_type=None):
    cutoff = target_row.cutoff_epoch
    return RawFamilyObservation(
        record_id,
        TargetIdentity(target_row.cycle_id, cutoff, target_row.maturity_epoch),
        "COIN", quant, formula or {"q1_momentum": "f1",
                                   "q2_mean_reversion": "f2", Q3: "f3"}[quant],
        schema, source, "30S",
        numerical_type or (MAGNITUDE_BPS if quant == Q3 else DIRECTIONAL_BPS),
        value, cutoff, cutoff if source_as_of is None else source_as_of,
        cutoff if available is None else available, state)


def build(targets, observations=(), *, state=1000, versions=VERSIONS):
    return build_v2a_dataset(
        state_as_of=state, horizon="30S", target_spec_id="log-return-v1",
        target_data_schema_version="ts1", target_source_spec_version="target-src1",
        family_versions=versions, targets=targets, observations=observations)


def reasons(dataset):
    return {item.reason_code: item.count for item in dataset.exclusions}


def test_causal_resolution_boundaries_and_family_validity():
    included = target(1, 10, resolved=100)
    future = target(2, 40, resolved=100.001)
    observations = [
        observation(1, included),
        observation(2, included, quant="q2_mean_reversion", source_as_of=11),
        observation(3, included, quant="q2_mean_reversion", available=101),
        observation(4, included, quant="q2_mean_reversion", state="INVALID"),
        observation(5, included, quant=Q3, value=-1),
        observation(6, included, value=math.nan),
    ]
    dataset = build([included, future], observations, state=100)
    assert [x.record_id for x in dataset.skeleton] == [1]
    assert reasons(dataset)["TARGET_UNRESOLVED"] == 1
    assert reasons(dataset)["FORECAST_NOT_CAUSAL"] == 2
    assert reasons(dataset)["FUTURE_INPUT"] == 1
    assert reasons(dataset)["MALFORMED_RECORD"] == 1
    assert reasons(dataset)["NONFINITE_VALUE"] == 1


@pytest.mark.parametrize(
    "bad_target",
    (
        RawTarget(10, "early-resolution", "COIN", "log-return-v1", "ts1",
                  "target-src1", "30S", 10, 40, 39, 1.0),
        RawTarget(11, "wrong-maturity", "COIN", "log-return-v1", "ts1",
                  "target-src1", "30S", 10, 41, 41, 1.0),
    ),
)
def test_target_timing_requires_exact_endpoint_and_post_maturity_resolution(bad_target):
    result = build([bad_target])
    assert result.skeleton == ()
    assert reasons(result) == {"TARGET_TIMING_MISMATCH": 1}


def test_family_attachment_requires_exact_cutoff_and_causal_time_chain():
    t = target(1, 10, resolved=40)
    wrong_cutoff = observation(1, t)
    wrong_cutoff = RawFamilyObservation(
        wrong_cutoff.record_id, wrong_cutoff.target_identity, wrong_cutoff.symbol,
        wrong_cutoff.quant_id, wrong_cutoff.formula_version,
        wrong_cutoff.data_schema_version, wrong_cutoff.source_spec_version,
        wrong_cutoff.horizon, wrong_cutoff.numerical_type, wrong_cutoff.value_bps,
        11, wrong_cutoff.source_as_of_epoch, wrong_cutoff.available_epoch,
        wrong_cutoff.availability_state,
    )
    at_maturity = observation(2, t, available=40)
    after_maturity = observation(3, t, available=40.001)
    before_cutoff = observation(4, t, available=9)

    result = build([t], [wrong_cutoff, at_maturity, after_maturity, before_cutoff])

    assert result.directional_subsets[0].observations == ()
    assert reasons(result) == {
        "FAMILY_TARGET_MISMATCH": 1,
        "FORECAST_NOT_CAUSAL": 3,
    }


@pytest.mark.parametrize("quant", ["q1_momentum", Q3])
def test_only_fresh_family_observations_can_enter_subsets(quant):
    t = target(1, 10)
    observations = [
        observation(1, t, quant=quant, value=2, state="FRESH"),
        observation(2, t, quant=quant, value=2, state="MISSING"),
        observation(3, t, quant=quant, value=2, state="STALE"),
        observation(4, t, quant=quant, value=2, state="INVALID"),
    ]

    result = build([t], observations)
    subset = (result.q3_subset if quant == Q3 else
              result.directional_subsets[0])

    assert [row.record_id for row in subset.observations] == [1]
    assert subset.observations[0].value_bps == 2
    assert reasons(result)["FORECAST_NOT_CAUSAL"] == 3


def test_exact_versions_are_isolated():
    rows = [target(1, 10), target(2, 40, schema="other")]
    obs = [observation(1, rows[0], formula="wrong"),
           observation(2, rows[0], schema="wrong"),
           observation(3, rows[0], source="wrong")]
    result = build(rows, obs)
    assert reasons(result) == {"DATA_SCHEMA_VERSION_MISMATCH": 2,
                               "FORMULA_VERSION_MISMATCH": 1,
                               "SOURCE_SPEC_VERSION_MISMATCH": 1}


def test_declared_family_lineage_is_canonical_complete_and_hash_bound():
    t = target(1, 10)
    base = build([t], versions=tuple(reversed(VERSIONS)))
    changed = build([t], versions=(
        ("q1_momentum", "f1", "fs2", "src1"),
        ("q2_mean_reversion", "f2", "fs1", "src1"),
        (Q3, "f3", "fs1", "src1"),
    ))

    assert tuple(item.quant_id for item in base.family_lineage) == (
        "q1_momentum", "q2_mean_reversion", Q3,
    )
    assert base.family_lineage[0].data_schema_version == "fs1"
    assert base.dataset_hash != changed.dataset_hash
    with pytest.raises(ValueError, match="invalid lineage"):
        build([t], versions=(("not-a-family", "f", "s", "src"),))


def test_duplicate_collapse_conflict_and_permutation_are_deterministic():
    t = target(7, 10)
    identical = [observation(9, t), observation(3, t)]
    first = build([t], identical)
    assert first.directional_subsets[0].observations[0].record_id == 3
    conflict = identical + [observation(2, t, value=9)]
    a = build([t], conflict)
    b = build([t], list(reversed(conflict)))
    assert not a.directional_subsets[0].observations
    assert reasons(a)["DUPLICATE_CONFLICT"] == 1
    assert a == b


def test_target_conflicts_exclude_identity_without_price_identity():
    a = target(8, 10, value=1, cycle="immutable-cycle")
    b = target(2, 10, value=2, cycle="immutable-cycle")
    result = build([a, b])
    assert result.skeleton == ()
    assert reasons(result)["TARGET_CONFLICT"] == 1
    assert TargetIdentity("immutable-cycle", 10, 40) == TargetIdentity("immutable-cycle", 10, 40)


def test_one_skeleton_spacing_and_all_subsets_reuse_it():
    targets = [target(1, 10), target(2, 20), target(3, 40), target(4, 71)]
    obs = [observation(1, targets[0]), observation(2, targets[1]),
           observation(3, targets[2], quant="q1_momentum"),
           observation(4, targets[0], quant="q2_mean_reversion"),
           observation(5, targets[2], quant="q2_mean_reversion"),
           observation(6, targets[0], quant=Q3, value=5)]
    result = build(list(reversed(targets)), list(reversed(obs)))
    assert [t.cutoff_epoch for t in result.skeleton] == [10, 40, 71]
    assert reasons(result)["OVERLAP_REMOVED"] == 1
    assert [o.target_identity for o in result.directional_subsets[0].observations] == [
        result.skeleton[0].identity, result.skeleton[1].identity]
    assert result.pair_support[0].target_identities == (
        result.skeleton[0].identity, result.skeleton[1].identity)
    assert result.complete_case_target_identities == result.pair_support[0].target_identities
    assert result.q3_subset.quant_id == Q3
    assert all(s.quant_id != Q3 for s in result.directional_subsets)


def test_exact_identity_only_and_missing_never_becomes_zero():
    t = target(1, 10)
    wrong = target(2, 40)
    result = build([t], [observation(1, wrong)])
    assert result.directional_subsets[0].observations == ()
    assert reasons(result)["MISSING_SYNCHRONIZED_FAMILY"] == 1


def test_immutable_lossless_hash_is_order_independent_and_sensitive():
    targets = [target(1, 10), target(2, 40)]
    obs = [observation(1, targets[0], value=-0.0), observation(2, targets[1])]
    base = build(targets, obs)
    shuffled = build(list(reversed(targets)), list(reversed(obs)))
    plus_zero = build(targets, [observation(1, targets[0], value=0.0), obs[1]])
    changed = build(targets, [obs[0], observation(2, targets[1], value=2.0000000000000004)])
    assert len(base.dataset_hash) == 64
    assert base.dataset_hash == shuffled.dataset_hash == plus_zero.dataset_hash
    assert changed.dataset_hash != base.dataset_hash
    version_changed = build(targets, obs, versions=(("q1_momentum", "f1", "fs1", "src1"),))
    assert version_changed.dataset_hash != base.dataset_hash
    with pytest.raises(FrozenInstanceError):
        base.symbol = "OTHER"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nonfinite_targets_never_enter_hash(bad):
    result = build([target(1, 10, value=bad)])
    assert result.skeleton == ()
    assert reasons(result)["NONFINITE_VALUE"] == 1