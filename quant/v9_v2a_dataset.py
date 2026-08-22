"""Offline construction of the immutable V9 V2-A causal evidence dataset.

The live evidence tables do not have a ``target_identity`` column.  Their
smallest immutable target identity is therefore ``(cycle_id, cutoff_epoch,
maturity_epoch)`` within the symbol/horizon/version cohort.  In particular,
prices and outcomes are never used as identity.  This module is deliberately
pure: callers read/normalize append-only evidence and pass it here; it has no
database or live-path integration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Iterable


DATASET_SCHEMA_VERSION = "V9-V2A-DATASET-1"
METHOD_VERSION = "V9-V2A-1"
SYMBOL = "COIN"
HORIZON_SECONDS = dict(zip(("30S", "1M", "5M", "15M", "30M", "1H"),
                           (30, 60, 300, 900, 1800, 3600)))
DIRECTIONAL_FAMILIES = (
    "q1_momentum", "q2_mean_reversion", "q4_stat_arb",
    "q5_microstructure", "q6_volume_liquidity", "q7_relative_value",
    "q8_cross_asset", "q9_factor", "q10_options_vol", "q11_regime",
    "q12_event_session",
)
Q3 = "q3_volatility"
DIRECTIONAL_BPS = "DIRECTIONAL_BPS"
MAGNITUDE_BPS = "MAGNITUDE_BPS"


@dataclass(frozen=True, slots=True, order=True)
class TargetIdentity:
    cycle_id: str
    cutoff_epoch: float
    maturity_epoch: float


@dataclass(frozen=True, slots=True)
class RawTarget:
    record_id: int
    cycle_id: str
    symbol: str
    target_spec_id: str
    data_schema_version: str
    source_spec_version: str
    horizon: str
    cutoff_epoch: float
    maturity_epoch: float
    resolved_epoch: float
    target_bps: float


@dataclass(frozen=True, slots=True)
class RawFamilyObservation:
    record_id: int
    target_identity: TargetIdentity
    symbol: str
    quant_id: str
    formula_version: str
    data_schema_version: str
    source_spec_version: str
    horizon: str
    numerical_type: str
    value_bps: float
    forecast_cutoff_epoch: float
    source_as_of_epoch: float
    available_epoch: float
    availability_state: str
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class TargetOrigin:
    identity: TargetIdentity
    record_id: int
    cutoff_epoch: float
    resolved_epoch: float
    target_bps: float


@dataclass(frozen=True, slots=True)
class FamilyObservation:
    target_identity: TargetIdentity
    record_id: int
    quant_id: str
    formula_version: str
    value_bps: float
    numerical_type: str
    forecast_cutoff_epoch: float
    source_as_of_epoch: float
    available_epoch: float
    data_schema_version: str
    source_spec_version: str


@dataclass(frozen=True, slots=True)
class FamilySubset:
    quant_id: str
    formula_version: str
    observations: tuple[FamilyObservation, ...]


@dataclass(frozen=True, slots=True)
class PairSupport:
    left_quant_id: str
    right_quant_id: str
    target_identities: tuple[TargetIdentity, ...]


@dataclass(frozen=True, slots=True)
class ExclusionCount:
    reason_code: str
    count: int


@dataclass(frozen=True, slots=True)
class V2ADataset:
    dataset_schema_version: str
    method_version: str
    symbol: str
    state_as_of: float
    training_start: float | None
    training_end: float | None
    target_spec_id: str
    target_data_schema_version: str
    target_source_spec_version: str
    horizon: str
    raw_resolved_count: int
    skeleton: tuple[TargetOrigin, ...]
    directional_subsets: tuple[FamilySubset, ...]
    q3_subset: FamilySubset | None
    pair_support: tuple[PairSupport, ...]
    complete_case_target_identities: tuple[TargetIdentity, ...]
    exclusions: tuple[ExclusionCount, ...]
    dataset_hash: str


def _finite(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _identity(target: RawTarget) -> TargetIdentity:
    return TargetIdentity(target.cycle_id, target.cutoff_epoch,
                          target.maturity_epoch)


def _float_token(value: float) -> str:
    if not _finite(value):
        raise ValueError("non-finite float in canonical dataset")
    return (0.0 if value == 0.0 else float(value)).hex()


def _canonical(value: object) -> object:
    if isinstance(value, float):
        return {"$float64": _float_token(value)}
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {key: _canonical(item) for key, item in asdict(value).items()
                if key != "dataset_hash"}
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    return value


def _hash(dataset: V2ADataset) -> str:
    encoded = json.dumps(_canonical(dataset), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_v2a_dataset(
    *, state_as_of: float, horizon: str, target_spec_id: str,
    target_data_schema_version: str, target_source_spec_version: str,
    family_versions: Iterable[tuple[str, str, str, str]],
    targets: Iterable[RawTarget], observations: Iterable[RawFamilyObservation],
    symbol: str = SYMBOL,
) -> V2ADataset:
    """Build one horizon/target-version cohort without writes or estimation.

    ``family_versions`` entries are ``(quant_id, formula_version,
    data_schema_version, source_spec_version)`` and explicitly select exact
    compatible family cohorts.  No compatibility is inferred.
    """
    if symbol != SYMBOL or horizon not in HORIZON_SECONDS or not _finite(state_as_of):
        raise ValueError("invalid symbol, horizon, or state_as_of")
    counts: dict[str, int] = {}
    exclude = lambda reason: counts.__setitem__(reason, counts.get(reason, 0) + 1)
    selected_targets: dict[TargetIdentity, list[RawTarget]] = {}
    raw_resolved = 0
    for row in targets:
        numeric = (row.cutoff_epoch, row.maturity_epoch, row.resolved_epoch,
                   row.target_bps)
        if not row.cycle_id:
            exclude("MALFORMED_RECORD")
            continue
        if any(not _finite(x) for x in numeric):
            exclude("NONFINITE_VALUE")
            continue
        if row.resolved_epoch > state_as_of:
            exclude("TARGET_UNRESOLVED"); continue
        raw_resolved += 1
        if (row.symbol != symbol or row.horizon != horizon or
                row.target_spec_id != target_spec_id):
            exclude("OUTSIDE_VERSION_COHORT"); continue
        if row.data_schema_version != target_data_schema_version:
            exclude("DATA_SCHEMA_VERSION_MISMATCH"); continue
        if row.source_spec_version != target_source_spec_version:
            exclude("SOURCE_SPEC_VERSION_MISMATCH"); continue
        selected_targets.setdefault(_identity(row), []).append(row)

    canonical_targets: list[TargetOrigin] = []
    for identity, rows in selected_targets.items():
        content = {(r.target_bps, r.resolved_epoch) for r in rows}
        if len(content) != 1:
            exclude("TARGET_CONFLICT"); continue
        representative = min(rows, key=lambda r: r.record_id)
        canonical_targets.append(TargetOrigin(identity, representative.record_id,
                                                representative.cutoff_epoch,
                                                representative.resolved_epoch,
                                                representative.target_bps))
    canonical_targets.sort(key=lambda r: (r.cutoff_epoch, r.identity, r.record_id))
    skeleton: list[TargetOrigin] = []
    for target in canonical_targets:
        if not skeleton or target.cutoff_epoch >= skeleton[-1].cutoff_epoch + HORIZON_SECONDS[horizon]:
            skeleton.append(target)
        else:
            exclude("OVERLAP_REMOVED")
    skeleton_ids = {row.identity for row in skeleton}

    version_rows = tuple(family_versions)
    versions = {q: (formula, schema, source)
                for q, formula, schema, source in version_rows}
    if len(versions) != len(version_rows):
        raise ValueError("family_versions contains a duplicate quant_id")
    eligible: dict[tuple[str, TargetIdentity], list[RawFamilyObservation]] = {}
    for row in observations:
        if row.quant_id not in (*DIRECTIONAL_FAMILIES, Q3) or row.symbol != symbol or row.horizon != horizon:
            exclude("MALFORMED_RECORD"); continue
        if row.target_identity not in skeleton_ids:
            exclude("MISSING_SYNCHRONIZED_FAMILY"); continue
        wanted = versions.get(row.quant_id)
        if wanted is None:
            exclude("OUTSIDE_VERSION_COHORT"); continue
        if row.formula_version != wanted[0]:
            exclude("FORMULA_VERSION_MISMATCH"); continue
        if row.data_schema_version != wanted[1]:
            exclude("DATA_SCHEMA_VERSION_MISMATCH"); continue
        if row.source_spec_version != wanted[2]:
            exclude("SOURCE_SPEC_VERSION_MISMATCH"); continue
        times = (row.forecast_cutoff_epoch, row.source_as_of_epoch, row.available_epoch)
        if not _finite(row.value_bps) or any(not _finite(x) for x in times):
            exclude("NONFINITE_VALUE"); continue
        expected = MAGNITUDE_BPS if row.quant_id == Q3 else DIRECTIONAL_BPS
        if row.numerical_type != expected or (row.quant_id == Q3 and row.value_bps < 0):
            exclude("MALFORMED_RECORD"); continue
        if row.forecast_cutoff_epoch > state_as_of or row.available_epoch > state_as_of:
            exclude("FUTURE_INPUT"); continue
        if row.source_as_of_epoch > row.forecast_cutoff_epoch:
            exclude("FORECAST_NOT_CAUSAL"); continue
        if row.availability_state != "FRESH":
            exclude("FORECAST_NOT_CAUSAL"); continue
        eligible.setdefault((row.quant_id, row.target_identity), []).append(row)

    by_family: dict[str, list[FamilyObservation]] = {q: [] for q in versions}
    for (quant_id, identity), rows in eligible.items():
        mathematical = {(r.value_bps, r.numerical_type, r.forecast_cutoff_epoch,
                         r.source_as_of_epoch, r.available_epoch,
                         r.data_schema_version, r.source_spec_version) for r in rows}
        if len(mathematical) != 1:
            exclude("DUPLICATE_CONFLICT"); continue
        row = min(rows, key=lambda r: r.record_id)
        by_family[quant_id].append(FamilyObservation(
            identity, row.record_id, quant_id, row.formula_version,
            0.0 if row.value_bps == 0.0 else row.value_bps, row.numerical_type,
            row.forecast_cutoff_epoch, row.source_as_of_epoch, row.available_epoch,
            row.data_schema_version, row.source_spec_version))
    order = {t.identity: index for index, t in enumerate(skeleton)}
    subsets = []
    for quant_id in DIRECTIONAL_FAMILIES:
        if quant_id in versions:
            rows = tuple(sorted(by_family[quant_id], key=lambda r: order[r.target_identity]))
            subsets.append(FamilySubset(quant_id, versions[quant_id][0], rows))
    q3_subset = None
    if Q3 in versions:
        q3_subset = FamilySubset(Q3, versions[Q3][0], tuple(sorted(
            by_family[Q3], key=lambda r: order[r.target_identity])))
    supports = {s.quant_id: {r.target_identity for r in s.observations} for s in subsets}
    pairs = tuple(PairSupport(a.quant_id, b.quant_id,
                              tuple(t.identity for t in skeleton
                                    if t.identity in supports[a.quant_id] and t.identity in supports[b.quant_id]))
                  for i, a in enumerate(subsets) for b in subsets[i + 1:])
    complete = tuple(t.identity for t in skeleton
                     if all(t.identity in supports[s.quant_id] for s in subsets)) if subsets else ()
    start = canonical_targets[0].cutoff_epoch if canonical_targets else None
    end = canonical_targets[-1].cutoff_epoch if canonical_targets else None
    diagnostics = tuple(ExclusionCount(k, counts[k]) for k in sorted(counts))
    draft = V2ADataset(DATASET_SCHEMA_VERSION, METHOD_VERSION, symbol, state_as_of,
                       start, end, target_spec_id, target_data_schema_version,
                       target_source_spec_version, horizon, raw_resolved,
                       tuple(skeleton), tuple(subsets), q3_subset, pairs, complete,
                       diagnostics, "")
    return V2ADataset(**{**asdict(draft), "skeleton": draft.skeleton,
                         "directional_subsets": draft.directional_subsets,
                         "q3_subset": draft.q3_subset, "pair_support": draft.pair_support,
                         "complete_case_target_identities": draft.complete_case_target_identities,
                         "exclusions": draft.exclusions, "dataset_hash": _hash(draft)})
